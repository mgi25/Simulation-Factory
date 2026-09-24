extends Node3D

## Category 3, Test #2 redesign - the premium multiplying-shell scene.
##
## A **playback consumer**. There is no body, no collider, no integration step,
## no random source, no force and no response law in this file, and every
## rendered frame is a pure function of the timestamp handed to `set_time`.
## The one rule the Phase 1 document states - a consumer may read a trajectory
## and may not compute one - is enforced here by not having anything to compute
## with: ball positions come from `flights`, panel states come from
## `panel_states`, shell angles come from `theta0 + omega*t`, and every effect
## is keyed to an event that is already in the stream.
##
## Every constant below is mirrored in `satisfying/multishell_visual.py` and a
## test parses this file and compares the two, because a measurement predicted
## from a Python constant is a measurement of a render nobody made if the two
## have drifted.
##
## ## What is different from the rejected single-ball scene
##
## That one was a `Node2D` drawing five concentric polylines with `draw_line`.
## This is a `Node3D` with real material: every panel is three chamfered slabs
## extruded **backwards**, away from the camera, with a pillar wherever a panel
## actually ends. The camera is perspective, so a panel's receding flank is visible
## and the outermost shell - which is extruded 3.2 units against the
## innermost's 0.9 - shows fourteen times the flank at the same framing, and
## 3.6 times the whole wall once each panel's 5.3 px face is counted in.
## Nothing is drawn outside the canonical collision silhouette: the flank is
## behind the play plane and therefore projects *inside* the front face, and
## every ball is at z = 0 in front of every flank.
##
## ## The camera frames the frontier, not the arena
##
## `_view_radius_at` opens the framing one shell each time the canonical
## high-water frontier advances, read from the `shell_exit` stream and nothing
## else. It is monotone, it is 90% static, and its last step lands seven to
## nine seconds before the escape, so the climax is rendered by a camera that
## has not moved. Without it, frame one is a 15 px ball in the middle of five
## rings, which is what was rejected.

const EXPECTED_SCHEMA := "category3-test2-two-team-shell-race/3.0.0"
const EXPECTED_CONFIG_DIGEST := \
	"4a3ab8ba22ae7c54981700823cc5b4eaf147c72fc5ab609a244d9cbaeb6ce572"
const EXPECTED_SHELL_COUNT := 5

# ---------------------------------------------------------------- composition
const FRAME_WIDTH := 1080
const FRAME_HEIGHT := 1920
## Phase 4A. The arena sits on the frame's own vertical axis, the framed radius
## is the frontier's material edge times a fixed fraction rather than plus a
## fixed number of units, and the frontier therefore occupies exactly
## 65.20% of the frame width at every stage. These five numbers must agree with
## `satisfying.multishell_visual`; `test_multishell_visual` compares them.
const VIEW_PAD_FRACTION := 0.055
## Phase 4C. 0.652 fitted the whole arena inside the band that clears the
## Shorts action rail and 0.850 fitted it inside the frame; the human review
## rejected both for the same reason. The rule is now "keep the interesting
## action large even if parts of the arena are cropped", so this is allowed
## above 1.0 - at 1.200 the outer wall's material diameter is 1296 px in a
## 1080 px frame and its left and right caps are off screen on purpose.
## Selected from rendered frames on seed 17964 against 1.00 and 1.10: it is the
## only one of the three whose late frame is not emptier than its opening.
## See `satisfying.multishell_visual` and `tools/two_team_phase4c_lab.py`.
const FRONTIER_WIDTH_FRACTION := 1.200
const VIEW_DIAMETER_FRACTION := FRONTIER_WIDTH_FRACTION * (1.0 + VIEW_PAD_FRACTION)
## The frame fraction the A/B/C comparison sweeps. It defaults to the constant
## above and `test_the_scene_defaults_to_the_declared_frame_fraction` is what
## keeps the default honest; only the laboratory tool ever sets it.
var frontier_width := FRONTIER_WIDTH_FRACTION
var view_diameter := VIEW_DIAMETER_FRACTION


func set_frontier_width(fraction: float) -> void:
	frontier_width = fraction
	view_diameter = fraction * (1.0 + VIEW_PAD_FRACTION)


## The depth ramp the "massive final wall" sweep varies. Defaults to the
## constant and only the laboratory tool ever sets it.
var panel_depth: Array = PANEL_DEPTH.duplicate()


func set_panel_depth(values: Array) -> void:
	if values.size() == panel_depth.size():
		panel_depth = values.duplicate()
const ARENA_CENTRE_X_FRACTION := 0.500
const ARENA_CENTRE_Y_FRACTION := 0.450
const CAMERA_HFOV_DEGREES := 47.0
const CAMERA_NEAR := 0.20
## `keep_aspect = KEEP_WIDTH` makes Godot read this as the near plane's *width*
## and derive the height from the aspect. Phase 2A multiplied it by H/W, which
## set the width to the height and opened the horizontal field from 47 to 74.4
## degrees - so every framing this project reported between Phase 2A and Phase
## 4A described a render nobody made, and the arena filled 46.9% of the frame
## where the report said 83.4%. See `satisfying.multishell_visual`.
const CAMERA_FRUSTUM_SIZE := 2.0 * CAMERA_NEAR * tan(
	deg_to_rad(CAMERA_HFOV_DEGREES) * 0.5)
const CAMERA_FRUSTUM_OFFSET := Vector2(
	(0.5 - ARENA_CENTRE_X_FRACTION) * CAMERA_FRUSTUM_SIZE,
	(ARENA_CENTRE_Y_FRACTION - 0.5) * CAMERA_FRUSTUM_SIZE
		* float(FRAME_HEIGHT) / float(FRAME_WIDTH))
const FRAME_LEAD_SECONDS := 0.14
## 0.40 s: the slowest the 4C brief allows, and the only value in its
## 0.25-0.40 band whose induced screen velocity stays under the gate now that
## the opening frames shell 2 instead of shell 1.
const FRAME_EASE_SECONDS := 0.40
## `[trigger_region, extent_shell]`. The camera holds `extent_shell` until the
## canonical high-water frontier reaches `trigger_region`. **One move**, not
## two and not four: the brief allows a single reframe and requires the last
## 6-10 s to be static, which rules out triggering on the outermost region.
const CAMERA_STAGE_PLAN := [[0, 2], [2, 4]]
const EVENT_GUARD_BEFORE_SECONDS := 0.12
const EVENT_GUARD_AFTER_SECONDS := 0.22
const EVENT_GUARD_MAX_DEFER_SECONDS := 0.90
const STRONG_NEAR_MISS_RADII := 0.75

# ---------------------------------------------------------------------- balls
const BALL_DRAW_SCALE := 1.30
const HALO_SCALE := 1.90
const BALL_RIM_SCALE := 1.24
# Draw order along z. Everything the physics cares about is at z = 0; these are
# the presentation layers around it. The rim, the trail and the halo sit just
# *in front* of the play plane so that they read over a panel rather than being
# occluded by one, and the core sphere - which is the canonical position - is
# at z = 0 exactly.
const BALL_RIM_Z := 0.02
const TRAIL_Z := 0.06
const HALO_Z := 0.12
const EFFECT_Z := 0.16
const MAX_DAMAGE_MARKS := 6
const TRAIL_SECONDS := 0.115
const TRAIL_SAMPLES := 20
const TRAIL_HEAD_WIDTH := 0.78
const TRAIL_TAIL_WIDTH := 0.24

# ---------------------------------------------------------------------- walls
## Nothing at z = 0 moves: the front face is still the canonical collision
## silhouette on every shell. All of the added mass is behind it.
const PANEL_DEPTH := [0.70, 1.25, 2.15, 3.60, 6.20]
const POST_DEPTH_FACTOR := 0.55
const PANEL_CHAMFER := 0.085
const PANEL_CHAMFER_BY_SHELL := [0.085, 0.085, 0.100, 0.115, 0.135]
const PANEL_SEGMENTS := 3
const SHELL_ALBEDO_VALUE := [1.00, 0.97, 0.94, 0.91, 0.88]
const SHELL_METALLIC := [0.05, 0.15, 0.25, 0.35, 0.45]
const SHELL_ROUGHNESS := [0.55, 0.49, 0.43, 0.37, 0.31]

# --------------------------------------------------------------------- damage
## Halved: in 4B the bright part of a wound is a hairline in the bottom of a
## dark chip, not a lit bar lying on the panel.
const DAMAGE_EMISSION_ENERGY := [0.00, 0.55, 1.30, 2.10, 0.00]
const DAMAGE_CRACK_COUNT := [0, 2, 4, 6, 0]
const DAMAGE_MARK_CHORD := 0.30
const DAMAGE_CHIP_RGB := Color(0.115, 0.130, 0.160)
const DAMAGE_CHIP_DEPTH := 0.055
## Wear below the first damage state. `fraction` is canonical and on every
## damage event; 4A read only the quantised ledger, so a panel at a third of
## its threshold was drawn identical to an untouched one - and on the final
## wall that is nearly every panel.
const DAMAGE_WEAR_FLOOR := 0.04
const DAMAGE_WEAR_FACE_LOSS := 0.60
const DAMAGE_WEAR_CHIP_SCALE := 0.85
const DAMAGE_CLUSTER_CHORD := 0.13
const DAMAGE_CLUSTER_GROWTH := 0.34
const DAMAGE_CLUSTER_GROWTH_MAX := 2.10
## A crack is a `width x span*thickness` rectangle rolled by the tilt, and its
## rotated radial extent is `span*cos(tilt) + width/thickness*sin(tilt)`. At 34
## degrees that stays inside the panel for any span up to 1.128, so 1.10 is the
## longest crack that never puts a pixel outside the canonical silhouette -
## which is the same rule the 4A marks were held to and the reason they were
## bars rather than lines.
const DAMAGE_CRACK_SPAN := 1.10
const DAMAGE_CRACK_WIDTH := 0.035
const DAMAGE_CRACK_TILT_DEGREES := 34.0
const DAMAGE_BRANCH_COUNT := [0, 0, 1, 2, 0]
const DAMAGE_BRANCH_SPREAD_DEGREES := 26.0
const DAMAGE_BRANCH_LENGTH := 0.62
## The broken lip around a chip: the bright edge where material was knocked
## away. A dark notch alone reads as a painted dot; a dark notch with a lit rim
## reads as a hole, because that is what a chip in a lit solid does.
const DAMAGE_RIM_RGB := Color(0.800, 0.815, 0.855)
const DAMAGE_RIM_ENERGY := 0.60
const DAMAGE_RIM_MARGIN := 0.070
## How tall the lip is radially, as a share of the panel's own thickness. The
## first version sized it as the chip plus the margin on both axes, which is
## 0.344 against a 0.300 panel, so every wound stuck out past the band it was
## supposed to be a hole in and read as a plate stuck on a wall.
const DAMAGE_RIM_SPAN := 0.92
## The connection in "connected crack network": from `critical` upward a seam
## joins consecutive wounds along the chord, so a panel with three wounds shows
## one fissure system rather than three separate injuries.
const DAMAGE_SEAM_STATES := [false, false, true, true, false]
const DAMAGE_SEAM_WIDTH := 0.030
const DAMAGE_SEAM_MIN_CHORD := 0.16
## A worn panel stops taking a clean highlight before it ever cracks. This is
## the one part of a wound no added geometry can supply - it is a property of
## the whole face rather than a shape on it.
const DAMAGE_WEAR_ROUGHNESS := 0.55
const DAMAGE_STATE_ROUGHNESS := [0.00, 0.22, 0.40, 0.55, 0.00]
## The brief's "tiny local Cyan/Orange stress tint", on the localised glow
## only and only where both teams really did wear the panel down.
const DAMAGE_TEAM_TINT := 0.20
const DAMAGE_TEAM_TINT_MIN_SHARE := 0.20
## A chip, its broken lip, one crack, two branches and the seam to the next
## wound. The lip is what turned the 4B wound from a mark into a hole.
const MARK_PARTS := 6
const MARK_PART_CHIP := 0
const MARK_PART_RIM := 1
const MARK_PART_CRACK := 2
const MARK_PART_BRANCH_A := 3
const MARK_PART_BRANCH_B := 4
const MARK_PART_SEAM := 5
const FRACTURE_GAP := 0.20
const FRACTURE_TILT_DEGREES := 9.0
const FRACTURE_RECESS := 0.10
## Each of a fractured panel's three sub-slabs recedes by a different amount,
## so the section boundaries throw their own edges and the slab reads as three
## pieces that have shifted. Inward only: a fractured panel still never
## occupies a pixel a healthy one did not.
const FRACTURE_SEGMENT_RECESS := [0.06, 0.22, 0.12]

# --------------------------------------------------------------------- events
const SPAWN_FLASH_SECONDS := 0.30
const SPAWN_FLASH_RADIUS := 3.10
const SPAWN_LINK_SECONDS := 0.18
const NEAR_MISS_SECONDS := 0.16
const BREAK_FLASH_SECONDS := 0.16
const BREAK_RETRACT_SECONDS := 0.30
## The wall is seen to give before it goes. Lengthened from 0.10 so the flare
## is four frames at 30 fps rather than three, which is the difference between
## a cue and a single bright frame.
const BREAK_STRESS_SECONDS := 0.14
## Five, inside the brief's 3-6. The slab has to be seen to come apart into
## substantial pieces of itself rather than to shatter, so the count stays low
## and each chunk keeps the panel's own radial thickness.
const BREAK_FRAGMENT_COUNT := 5
const BREAK_FRAGMENT_SECONDS := 0.42
const BREAK_FRAGMENT_CHORD_FRACTION := 0.22
const BREAK_FRAGMENT_DEPTH_FRACTION := 0.60
const BREAK_FRAGMENT_OUT_SPEED := 5.2
const BREAK_FRAGMENT_SPIN_DEGREES := 220.0
const FLOOD_WINDOW_SECONDS := 1.80
const FLOOD_MIN_BALLS := 2
const FLOOD_RESPONSE_SECONDS := 0.55
const FLOOD_POST_ENERGY := 5.4
const BREAK_DEBRIS_SECONDS := 0.26
const BREAK_DEBRIS_COUNT := 5
const BREAK_RING_SECONDS := 0.34
# World units, so it is the same fraction of whatever shell it happens on. 2.2
# was the first value and it was 47 px at the final framing - smaller than the
# panel it destroyed, and unreadable as an event.
const BREAK_RING_RADIUS := 3.40
const BREAK_DEBRIS_SIZE := 0.22
const BREAK_DEBRIS_SPEED := 6.0
const BREAK_DEBRIS_SPEED_SPREAD := 5.0
const ESCAPE_FLARE_SECONDS := 0.60
const ESCAPE_RING_SECONDS := 0.75
const RELEASE_SECONDS := 0.55
const END_HOLD_SECONDS := 0.40

# ------------------------------------------------------------------- overlay
## Two pieces of type and no third. The hook states the question in the band
## above the arena, which a centred 65%-wide disc leaves empty in a 9:16 frame,
## and the payoff answers it in the team's own colour. There is no score, no
## population counter and no per-team tally: the two growing populations are
## the score, and a number on top of them would be a worse version of the same
## information competing with it for the same eye.
const HOOK_TEXT := "WHO ESCAPES FIRST?"
const HOOK_TOP_FRACTION := 0.082
const HOOK_SIZE_FRACTION := 0.0315
## The hook steps back once the arena is busy, rather than cutting: at four
## balls the question has been answered by the picture and the type is only
## competing with it.
## The hook leaves. 4A faded it to 0.22 and left a ghost of the question over
## the whole race, which is what the human review objected to. It is now solid
## for the brief's 1.5-2.0 s, gone over half a second, and then not drawn.
const HOOK_HOLD_SECONDS := 1.85
const HOOK_FADE_SECONDS := 0.55
const HOOK_FADE_TO := 0.0
## The payoff. It lands on the canonical escape instant, not on the release
## beat, so the word and the ball leaving the arena are the same frame.
const WINNER_SIZE_FRACTION := 0.052
const WINNER_TOP_FRACTION := 0.735
const WINNER_ALT_TOP_FRACTION := 0.150
const WINNER_BAND_FRACTION := 0.105
const WINNER_RISE_SECONDS := 0.22
const WINNER_RELEASE_SAMPLES := 25
const TEXT_PRIMARY := Color(0.94, 0.96, 1.00)
const SAFE_MARGIN_FRACTION := 0.075

# --------------------------------------------------------------------- colour
const BACKGROUND := Color(0.020, 0.026, 0.042)
const FLOOR_COLOUR := Color(0.075, 0.100, 0.165)
## Two teams, two hues, and nothing else in the frame may use either of them.
## The damage ramp below moved from amber to red-to-white-hot and the
## opening-post highlight from cyan to steel to pay for it.
const TEAM_RGB := [
	Color(0.140, 0.880, 1.000),
	Color(1.000, 0.540, 0.130),
]
const TEAM_NAMES := ["CYAN", "ORANGE"]
## A descendant keeps its team's hue exactly. Generation reads as emission only.
const GENERATION_ENERGY_STEP := 0.09
const GENERATION_ENERGY_MAX := 1.36
const PANEL_RGB := Color(0.400, 0.440, 0.500)
# The lit face. A panel collision surface is 0.30 units thick - 5.3 px at the
# final framing - and a 5.3 px line that *emits* reads as a wall where a 5.3 px
# line that is merely lit reads as a pencil stroke. The plate is exactly the
# front face, drawn 0.004 in front of it so it never z-fights, and its energy
# sits below the glow threshold so it lifts the panel without blooming the
# whole ring. Damage takes it away: a worn panel loses its sheen before it
# gains a crack.
const FACE_RGB := Color(0.620, 0.680, 0.780)
const FACE_ENERGY := 0.62
const FACE_Z := 0.004
# The back rim, and the reason the five shells look different from each other.
#
# The depth ramp puts an 18.9 px flank on the outer shell and a 1.3 px flank on
# the inner one at the final framing, but a *shaded* flank against a dark field
# reads as nothing and the first render of this scene showed five identical
# bright hoops. Lighting the back edge as well turns each panel into a well
# seen down its own axis: two bright lines with dark wall between them, and the
# gap between the lines **is** the depth. Inner shell: the two lines touch.
# Outer shell: they are 19 px apart. Nobody has to be told which wall is
# heavier.
#
# The rim is at z = -depth, so it projects *inside* the front face and can
# never put a pixel outside the canonical silhouette.
const BACK_RGB := Color(0.340, 0.430, 0.560)
const BACK_ENERGY := 0.30
const MARK_Z := 0.010
const STRESS_Z := 0.024
## Exposed material, then heat. 4B ran crimson to magenta to pink and the human
## review called it "red/pink marks rather than physical destruction". 4C keeps
## the separation from both team hues and buys it by *desaturating* rather than
## by rotating: a chipped material first shows fresh unweathered surface, which
## is not coloured at all, and only a critical panel glows - which is
## incandescence, warm and washing out to white.
const CRACK_RGB := Color(0.760, 0.790, 0.840)
const CRITICAL_RGB := Color(1.000, 0.820, 0.700)
const FRACTURE_RGB := Color(1.000, 0.930, 0.870)
const BREAK_FLASH_RGB := Color(1.000, 0.940, 0.960)
const POST_RGB := Color(0.330, 0.370, 0.440)
## **The pink the human review kept seeing.** A pillar flanking a broken panel
## keeps this cast for the rest of the run, so a late frame carried up to 62
## saturated magenta pillars - a coloured dot beside every break, which is the
## floating marker the brief bans. It keeps its job and loses its colour.
const POST_HOT_RGB := Color(1.000, 0.870, 0.760)
# A pillar that flanks an opening is the one the ball clips when it aims at the
# hole and misses, so it is the one the viewer has to see. It gets a cool cap
# and a little more depth; the pillars between two panels do not.
const POST_EDGE_RGB := Color(0.700, 0.780, 0.900)
const POST_EDGE_ENERGY := 1.60
# Pillars between two panels still read as the joints that hold the ring
# together, just quietly.
const POST_BASE_ENERGY := 0.26
const POST_EDGE_DEPTH := 1.35
# How far the backdrop sits behind the play plane. Behind every flank, and
# rescaled with the framing each frame so the pool of light around the arena is
# the same shape at every stage.
const BACKDROP_Z := -6.0
# The arena throws light into the 71% of the frame it cannot fill. The pool is
# sized from the *framing* rather than from the arena, so it is a halo around
# shell 0 at the opening and a halo around the whole arena at the climax
# instead of a uniform wash over the hook.
const GLOW_POOL_Z := -4.0
const GLOW_POOL_RADII := 2.60
const GLOW_POOL_RGB := Color(0.105, 0.215, 0.430)
const GLOW_POOL_ALPHA := 0.42

var playback: Dictionary = {}
# The control, not a mode. `--fixed=1` pins the framing to the whole arena for
# the whole run, which is the "fixed camera preferred" reading of the brief. It
# exists so the reason this phase does not use it is a picture rather than an
# assertion: at that framing the ball is 15 px wide in frame one. Every proof
# render leaves it false.
var fixed_framing := false
var release_seconds := RELEASE_SECONDS
var hold_seconds := END_HOLD_SECONDS
var show_debug := false

var _width := FRAME_WIDTH
var _height := FRAME_HEIGHT
var _camera: Camera3D
var _time := 0.0
var _render_time := 0.0
var _duration := 0.0
var _view_radius := 1.0
var _pixels_per_unit := 1.0

# Shell nodes, rotated as rigid bodies of drawing - never of physics.
var _shell_roots: Array[Node3D] = []
var _shell_omega: PackedFloat64Array = PackedFloat64Array()
var _shell_theta0: PackedFloat64Array = PackedFloat64Array()

# Panels, flat arrays indexed by `_panel_index[shell][slot]`.
var _panel_index: Array = []
var _panel_slabs: Array = []          # Array[Array[MeshInstance3D]] of PANEL_SEGMENTS
var _panel_materials: Array = []      # Array[StandardMaterial3D], one per panel
var _panel_marks: Array = []          # Array[Array[MeshInstance3D]]
var _panel_mark_material: Array = []  # Array[StandardMaterial3D]
var _panel_shell: PackedInt32Array = PackedInt32Array()
var _panel_slot: PackedInt32Array = PackedInt32Array()
var _panel_chord: PackedFloat64Array = PackedFloat64Array()
var _panel_break_time: PackedFloat64Array = PackedFloat64Array()
var _panel_transitions: Array = []    # Array[Array] of [t, state_index]
var _panel_face_material: Array = []  # Array[StandardMaterial3D]
var _panel_back_material: Array = []  # Array[StandardMaterial3D]
var _panel_stress: Array = []         # Array[MeshInstance3D]
var _panel_stress_material: Array = []

# Posts: one per shell vertex.
var _posts: Array = []
var _post_materials: Array = []
var _post_index: Array = []
var _post_edge: Array = []

# Balls.
var _ball_ids: PackedInt32Array = PackedInt32Array()
var _ball_birth: PackedFloat64Array = PackedFloat64Array()
var _ball_colour: Array[Color] = []
var _ball_team: PackedInt32Array = PackedInt32Array()
var _ball_energy: PackedFloat64Array = PackedFloat64Array()
var _ball_flights: Array = []
var _ball_core: Array[MeshInstance3D] = []
var _ball_rim: Array[MeshInstance3D] = []
var _ball_halo: Array[MeshInstance3D] = []
var _ball_core_material: Array = []
var _ball_halo_material: Array = []
var _ball_trail: Array = []
var _ball_trail_material: Array = []
var _ball_row_of := {}

# Effects, all keyed to canonical events.
var _spawns: Array = []
var _spawn_flash: Array[MeshInstance3D] = []
var _spawn_flash_material: Array = []
var _spawn_link: Array[MeshInstance3D] = []
var _spawn_link_material: Array = []
var _near_misses: Array = []
var _near_miss_spark: Array[MeshInstance3D] = []
var _near_miss_material: Array = []
var _breaks: Array = []
var _break_ring: Array[MeshInstance3D] = []
var _break_ring_material: Array = []
var _debris: Array[MeshInstance3D] = []
var _debris_material: Array = []
var _fragments: Array[MeshInstance3D] = []
var _fragment_material: Array = []
var _passage_exits: Array = []
var _passage_uses: Array = []
var _escape := {}
var _escape_ring: MeshInstance3D
var _escape_ring_material: StandardMaterial3D

var _hook_label: Label
var _winner_label: Label
var _panel_impacts := {}
var _panel_clusters := {}
var _panel_wear := {}
## Per panel key: `{state: [[row_index, centre, length], ...]}` - the seams that
## join consecutive wounds into one crack network from `critical` upward.
var _panel_seams := {}
## Per panel key: `[lead_team, tint]`, read from the canonical `team_cumulative`
## on the damage stream. Nothing is accumulated here that the simulation did
## not already publish.
var _panel_teams := {}
var _panel_rim_material: StandardMaterial3D
var _backdrop: MeshInstance3D
var _glow_pool: MeshInstance3D
var _radial_texture: GradientTexture2D
var _halo_texture: GradientTexture2D
var _configured := false
var _stages: Array = []
var _debug_crosshair: Array = []
var _debug_markers: Array = []
var _debug_outlines: Array = []
const DEBUG_COLOURS := [
	Color(1.00, 0.30, 0.30, 0.95), Color(1.00, 0.82, 0.20, 0.95),
	Color(0.30, 1.00, 0.50, 0.95), Color(0.25, 0.75, 1.00, 0.95),
	Color(0.85, 0.35, 1.00, 0.95),
]


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------


func configure(document: Dictionary, width: int, height: int) -> void:
	playback = document
	_width = width
	_height = height
	_duration = float(playback["summary"]["duration"])
	_build()
	_configured = true
	set_time(0.0)


func validate_document() -> String:
	if str(playback.get("schema", "")) != EXPECTED_SCHEMA:
		return "schema is %s, this renderer reads %s" % [
			playback.get("schema"), EXPECTED_SCHEMA]
	if str(playback.get("config_digest", "")) != EXPECTED_CONFIG_DIGEST:
		return "config digest is not the frozen Phase 1 operating configuration"
	var shells: Array = playback.get("shells", [])
	if shells.size() != EXPECTED_SHELL_COUNT:
		return "the visual proof is built for %d shells, got %d" % [
			EXPECTED_SHELL_COUNT, shells.size()]
	if not bool(playback["summary"].get("escaped", false)):
		return "a proof candidate must reach a canonical escape"
	var previous := -INF
	for event in playback.get("events", []):
		var at := float(event["t"])
		if at < previous:
			return "canonical event order is not monotone in time"
		previous = at
	return ""


func playback_duration() -> float:
	return _duration


func render_duration() -> float:
	return _duration + release_seconds + hold_seconds


func world_to_pixel_scale() -> float:
	return _pixels_per_unit


func view_radius() -> float:
	return _view_radius


func frame_mark_count() -> int:
	## Camera transitions, which under 4B is two rather than one per shell.
	return maxi(0, _camera_stages().size() - 1)


# --------------------------------------------------------------------------
# The camera schedule
# --------------------------------------------------------------------------


func _shell_view_radii() -> PackedFloat64Array:
	## Proportional pad, so the frontier is the same size on screen at every
	## stage. A constant pad is a shrinking fraction as the arena opens out, and
	## that is what made the Phase 3B frontier creep from 73% to 81% of the frame.
	var out := PackedFloat64Array()
	for shell in playback["shells"]:
		out.append((float(shell["radius"]) + 0.5 * float(shell["thickness"]))
			* (1.0 + VIEW_PAD_FRACTION))
	return out


func _frontier_reached() -> Dictionary:
	## The first instant the canonical high-water frontier reached each region.
	## Read from the `shell_exit` stream and from nothing else, so the camera
	## consumes the race rather than a schedule that merely runs beside it.
	var limit := int(playback["shells"].size()) - 1
	var reached := {}
	var high_water := 0
	for event in playback["events"]:
		if str(event["kind"]) != "shell_exit":
			continue
		var target: int = mini(int(event["to_region"]), limit)
		while high_water < target:
			high_water += 1
			if not reached.has(high_water):
				reached[high_water] = float(event["t"])
	return reached


func _protected_instants() -> PackedFloat64Array:
	## Moments a camera move may not run across: the first clone, every panel
	## break, every strong near miss, and the escape.
	var out := PackedFloat64Array()
	var first_spawn := true
	for event in playback["events"]:
		var kind := str(event["kind"])
		if kind == "ball_spawn" and first_spawn:
			first_spawn = false
			out.append(float(event["t"]))
		elif kind == "panel_break":
			out.append(float(event["t"]))
		elif kind == "near_miss" and float(
				event["arc_separation_ball_radii"]) <= STRONG_NEAR_MISS_RADII:
			out.append(float(event["t"]))
		elif kind == "escape":
			out.append(float(event["t"]))
	var sorted_out := Array(out)
	sorted_out.sort()
	return PackedFloat64Array(sorted_out)


func _guarded(start: float, guards: PackedFloat64Array) -> bool:
	var low := start - EVENT_GUARD_BEFORE_SECONDS
	var high := start + FRAME_EASE_SECONDS + EVENT_GUARD_AFTER_SECONDS
	for guard in guards:
		if guard >= low and guard <= high:
			return true
	return false


func _clear_start(wanted: float, floor_t: float,
		guards: PackedFloat64Array) -> float:
	## Protection may pull a move **earlier** and never later. Deferring a
	## blocked move past the frontier crossing that triggered it is what left
	## balls outside the frame for 63 and 98 frames on 17964 and 3762; the
	## trigger is the instant the old framing stops being big enough, so there
	## is no slack after it to spend.
	if not _guarded(wanted, guards) and wanted >= floor_t:
		return wanted
	var best := -1.0
	for guard in guards:
		var option: float = guard - EVENT_GUARD_BEFORE_SECONDS - FRAME_EASE_SECONDS
		if option < floor_t or option > wanted:
			continue
		if wanted - option > EVENT_GUARD_MAX_DEFER_SECONDS:
			continue
		if _guarded(option, guards):
			continue
		if best < 0.0 or option > best:
			best = option
	if best < 0.0:
		return maxf(wanted, floor_t)
	return best


func _camera_stages() -> Array:
	## `[stage, extent_shell, start, settled, radius]`, outward and monotone.
	if not _stages.is_empty():
		return _stages
	var radii := _shell_view_radii()
	var reached := _frontier_reached()
	var guards := _protected_instants()
	var previous_end := 0.0
	for index in CAMERA_STAGE_PLAN.size():
		var plan: Array = CAMERA_STAGE_PLAN[index]
		var trigger: int = int(plan[0])
		var extent: int = int(plan[1])
		if index == 0:
			_stages.append([0, extent, 0.0, 0.0, radii[extent]])
			continue
		if not reached.has(trigger):
			continue
		var wanted: float = float(reached[trigger]) - FRAME_LEAD_SECONDS
		var start := _clear_start(wanted, previous_end, guards)
		var settled := start + FRAME_EASE_SECONDS
		previous_end = settled
		_stages.append([index, extent, start, settled, radii[extent]])
	return _stages


func _smoothstep01(u: float) -> float:
	if u <= 0.0:
		return 0.0
	if u >= 1.0:
		return 1.0
	return u * u * (3.0 - 2.0 * u)


func _view_radius_at(t: float) -> float:
	var radii := _shell_view_radii()
	if fixed_framing:
		return radii[radii.size() - 1]
	var stages := _camera_stages()
	var radius: float = float(stages[0][4])
	for index in range(1, stages.size()):
		var stage: Array = stages[index]
		var previous := radius
		radius = previous + (float(stage[4]) - previous) * _smoothstep01(
			(t - float(stage[2])) / FRAME_EASE_SECONDS)
	return radius


func camera_stage_at(t: float) -> int:
	## Which stage the composition is in: the last one that has settled.
	var stages := _camera_stages()
	var current := 0
	for index in range(1, stages.size()):
		if t >= float(stages[index][3]):
			current = int(stages[index][0])
	return current


func _camera_distance(view: float) -> float:
	var half_width_units := view / view_diameter
	return half_width_units / tan(deg_to_rad(CAMERA_HFOV_DEGREES) * 0.5)


func _apply_camera(t: float) -> void:
	_view_radius = _view_radius_at(t)
	_pixels_per_unit = float(_width) * view_diameter / (2.0 * _view_radius)
	var distance := _camera_distance(_view_radius)
	# The eye stays on the one invariant world centre.  An asymmetric frustum
	# places that optical axis at the Shorts-safe composition point; unlike a
	# lateral camera translation it gives the same principal point at every Z,
	# so slabs with different depths remain concentric.
	_camera.set_frustum(
		CAMERA_FRUSTUM_SIZE, CAMERA_FRUSTUM_OFFSET, CAMERA_NEAR, 400.0)
	_camera.position = Vector3(0.0, 0.0, distance)
	_camera.rotation = Vector3.ZERO

	# Fill the frame at the backdrop plane, whatever the framing. The quad sits
	# behind every flank, so it can never occlude the arena.
	if _backdrop != null:
		var half_width := (distance - BACKDROP_Z) * tan(
			deg_to_rad(CAMERA_HFOV_DEGREES) * 0.5)
		var half_height := half_width * float(_height) / float(_width)
		_backdrop.transform = Transform3D(
			Basis(Vector3(2.1 * half_width, 0.0, 0.0),
				Vector3(0.0, 2.1 * half_height, 0.0), Vector3(0.0, 0.0, 1.0)),
			Vector3(0.0, 0.0, BACKDROP_Z))
	if _glow_pool != null:
		var pool := 2.0 * GLOW_POOL_RADII * _view_radius
		_glow_pool.transform = Transform3D(
			Basis(Vector3(pool, 0.0, 0.0), Vector3(0.0, pool, 0.0),
				Vector3(0.0, 0.0, 1.0)),
			Vector3(0.0, 0.0, GLOW_POOL_Z))
	_update_debug_overlay()


# --------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------


func _build() -> void:
	_radial_texture = _radial_gradient(1.0, 0.0, 0.55)
	_halo_texture = _radial_gradient(0.85, 0.0, 0.18)
	_build_environment()
	_build_camera()
	_build_backdrop()
	# `_read_impacts` moved ahead of `_build_shells`: a panel now allocates one
	# wound's worth of geometry per cluster it actually has, rather than six
	# slots for every panel in the arena whether it is ever touched or not.
	# Across the review candidates that is about 160 wounds instead of 1,380
	# slots, which is what makes four parts per wound affordable.
	_read_impacts()
	_read_wear()
	_read_damage_teams()
	_build_shells()
	_read_panel_states()
	_build_balls()
	_read_events()
	_resolve_passage_uses()
	_build_effects()
	_build_overlay()
	if show_debug:
		_build_debug_overlay()
		_update_debug_overlay()


func _circle_points(centre: Vector2, radius: float, segments: int = 96) -> PackedVector2Array:
	var points := PackedVector2Array()
	for index in segments + 1:
		var angle := TAU * float(index) / float(segments)
		points.append(centre + radius * Vector2(cos(angle), sin(angle)))
	return points


func _debug_line(parent: Node, colour: Color, width: float) -> Line2D:
	var line := Line2D.new()
	line.default_color = colour
	line.width = width
	line.antialiased = true
	parent.add_child(line)
	return line


func _build_debug_overlay() -> void:
	## Measurement media only: five slab-midpoint markers, the canonical centre
	## crosshair, and the five collision-shell outlines in screen space.
	var layer := CanvasLayer.new()
	layer.name = "CentreAlignmentDiagnostic"
	layer.layer = 50
	add_child(layer)
	_debug_crosshair.append(_debug_line(layer, Color(1.0, 1.0, 1.0, 0.95), 2.0))
	_debug_crosshair.append(_debug_line(layer, Color(1.0, 1.0, 1.0, 0.95), 2.0))
	for shell_id in EXPECTED_SHELL_COUNT:
		_debug_markers.append(_debug_line(layer, DEBUG_COLOURS[shell_id], 2.0))
		var colour: Color = DEBUG_COLOURS[shell_id]
		_debug_outlines.append(_debug_line(
			layer, Color(colour.r, colour.g, colour.b, 0.30), 1.0))


func _update_debug_overlay() -> void:
	if _debug_crosshair.is_empty() or _camera == null:
		return
	var canonical := _camera.unproject_position(Vector3.ZERO)
	_debug_crosshair[0].points = PackedVector2Array([
		canonical + Vector2(-22.0, 0.0), canonical + Vector2(22.0, 0.0)])
	_debug_crosshair[1].points = PackedVector2Array([
		canonical + Vector2(0.0, -22.0), canonical + Vector2(0.0, 22.0)])
	for shell_id in EXPECTED_SHELL_COUNT:
		var centre := _camera.unproject_position(Vector3(
			0.0, 0.0, -0.5 * float(panel_depth[shell_id])))
		_debug_markers[shell_id].points = _circle_points(
			centre, 4.0 + 3.0 * shell_id, 32)
		var radius := float(playback["shells"][shell_id]["radius"]) * _pixels_per_unit
		_debug_outlines[shell_id].points = _circle_points(canonical, radius)


func _build_environment() -> void:
	var world := WorldEnvironment.new()
	var environment := Environment.new()
	environment.background_mode = Environment.BG_COLOR
	environment.background_color = BACKGROUND
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.ambient_light_color = Color(0.30, 0.40, 0.62)
	environment.ambient_light_energy = 0.72
	# The glow threshold sits above the panel body's brightness and below a
	# damage mark's, so bloom is a signal - a marked panel blooms, an unmarked
	# one does not - rather than a haze over everything.
	environment.glow_enabled = true
	environment.glow_intensity = 0.80
	environment.glow_strength = 1.10
	environment.glow_bloom = 0.24
	environment.glow_blend_mode = Environment.GLOW_BLEND_MODE_ADDITIVE
	environment.glow_hdr_threshold = 0.95
	world.environment = environment
	add_child(world)

	# One key from the upper left and a cooler fill from the lower right. Their
	# only job is to give a slab's chamfer rims and its receding flank four
	# different shades, which is what makes a 5 px face read as a wall.
	var key := DirectionalLight3D.new()
	key.light_energy = 1.35
	key.light_color = Color(0.88, 0.93, 1.00)
	key.look_at_from_position(Vector3(-9.0, 13.0, 16.0), Vector3.ZERO, Vector3.UP)
	add_child(key)

	var fill := DirectionalLight3D.new()
	fill.light_energy = 0.42
	fill.light_color = Color(0.42, 0.58, 1.00)
	fill.look_at_from_position(Vector3(11.0, -8.0, 12.0), Vector3.ZERO, Vector3.UP)
	add_child(fill)


func _build_camera() -> void:
	_camera = Camera3D.new()
	_camera.projection = Camera3D.PROJECTION_FRUSTUM
	# KEEP_WIDTH makes `fov` the horizontal angle, which is what ties it to
	# VIEW_DIAMETER_FRACTION. Under KEEP_HEIGHT the framing would depend on the
	# aspect ratio and every pixel number in the report would be wrong.
	_camera.keep_aspect = Camera3D.KEEP_WIDTH
	_camera.near = CAMERA_NEAR
	_camera.far = 400.0
	add_child(_camera)
	_apply_camera(0.0)


func _build_backdrop() -> void:
	## A place rather than a void.
	##
	## A disc that clears the Shorts action rail covers 28.7% of a 9:16 frame at
	## the final framing, and that is geometry rather than a choice: the largest
	## centred disc that fits at all covers 44.2%. So 71% of the frame is
	## outside the arena when the escape happens, and if it is black the shot is
	## a small object in a void - which is half of what "excessive empty black
	## space" meant. The backdrop is a single quad carrying a radial gradient
	## centred on the arena, rescaled with the framing in `_apply_camera` so the
	## pool of light is the same shape at every stage.
	var outer := float(playback["shells"][-1]["radius"])

	_backdrop = MeshInstance3D.new()
	_backdrop.name = "Backdrop"
	var backdrop_quad := QuadMesh.new()
	backdrop_quad.size = Vector2(1.0, 1.0)
	_backdrop.mesh = backdrop_quad
	var backdrop_material := StandardMaterial3D.new()
	backdrop_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	backdrop_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	backdrop_material.albedo_texture = _radial_gradient(1.0, 0.0, 0.42)
	backdrop_material.albedo_color = Color(0.125, 0.180, 0.310, 1.0)
	_backdrop.material_override = backdrop_material
	add_child(_backdrop)

	# The arena interior, one clear step above the backdrop. It says "the balls
	# live in here" in frame one, before anything has happened.
	_glow_pool = MeshInstance3D.new()
	_glow_pool.name = "GlowPool"
	var pool_quad := QuadMesh.new()
	pool_quad.size = Vector2(1.0, 1.0)
	_glow_pool.mesh = pool_quad
	var pool_material := StandardMaterial3D.new()
	pool_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	pool_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	pool_material.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
	pool_material.albedo_texture = _radial_gradient(1.0, 0.0, 0.30)
	pool_material.albedo_color = Color(GLOW_POOL_RGB, GLOW_POOL_ALPHA)
	_glow_pool.material_override = pool_material
	add_child(_glow_pool)

	var floor_disc := MeshInstance3D.new()
	floor_disc.name = "Floor"
	floor_disc.mesh = _disc_mesh(outer * 1.02, 96)
	var floor_material := StandardMaterial3D.new()
	floor_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	floor_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	floor_material.albedo_texture = _radial_gradient(1.0, 0.10, 0.62)
	floor_material.albedo_color = FLOOR_COLOUR
	floor_disc.material_override = floor_material
	floor_disc.position = Vector3(0.0, 0.0, -0.22)
	add_child(floor_disc)


func _build_shells() -> void:
	var container := Node3D.new()
	container.name = "Shells"
	add_child(container)

	# One shared chip material for the whole arena: a chip is absence of
	# material and its colour never depends on the state, so a per-panel copy
	# would be 230 identical StandardMaterial3Ds.
	var chip_material := StandardMaterial3D.new()
	chip_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	chip_material.albedo_color = DAMAGE_CHIP_RGB

	# And one shared lip. A broken edge does not get hotter as the panel gets
	# worse - it is just broken - so the rim is state-independent and one
	# material serves the whole arena, exactly like the chip.
	_panel_rim_material = StandardMaterial3D.new()
	_panel_rim_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	_panel_rim_material.albedo_color = DAMAGE_RIM_RGB
	_panel_rim_material.emission_enabled = true
	_panel_rim_material.emission = DAMAGE_RIM_RGB
	_panel_rim_material.emission_energy_multiplier = DAMAGE_RIM_ENERGY

	var running := 0
	for shell in playback["shells"]:
		var shell_id := int(shell["shell_id"])
		var radius := float(shell["radius"])
		var thickness := float(shell["thickness"])
		var count := int(shell["panel_count"])
		var slot_width := float(shell["slot_width"])
		var chord := float(shell["chord_length"])
		var depth: float = panel_depth[shell_id]

		var root := Node3D.new()
		root.name = "Shell%d" % shell_id
		container.add_child(root)
		_shell_roots.append(root)
		_shell_theta0.append(float(shell["theta0"]))
		_shell_omega.append(float(shell["omega"]))

		var open_slots := {}
		for slot in shell["open_slots"]:
			open_slots[int(slot)] = true

		# Pillars only where a panel actually ends. A pillar is the panel
		# capsule own round cap, so a vertex with open slots on both sides has
		# no material there at all, and the first render drew a line of
		# disconnected dots floating in every opening. Its radius is the
		# canonical half-thickness; only its depth is a drawing choice.
		var post_row := {}
		for vertex in count:
			var before: bool = not open_slots.has((vertex - 1 + count) % count)
			var after: bool = not open_slots.has(vertex % count)
			if not (before or after):
				continue
			var edge: bool = before != after
			var angle := vertex * slot_width
			var post := MeshInstance3D.new()
			post.name = "S%dPost%02d" % [shell_id, vertex]
			var mesh := CylinderMesh.new()
			mesh.top_radius = 0.5 * thickness
			mesh.bottom_radius = 0.5 * thickness * 1.05
			var post_depth: float = depth * POST_DEPTH_FACTOR * (
				POST_EDGE_DEPTH if edge else 1.0)
			mesh.height = post_depth
			mesh.radial_segments = 10
			mesh.rings = 0
			post.mesh = mesh
			var material := StandardMaterial3D.new()
			material.albedo_color = POST_RGB * float(SHELL_ALBEDO_VALUE[shell_id])
			material.metallic = float(SHELL_METALLIC[shell_id])
			material.roughness = float(SHELL_ROUGHNESS[shell_id]) * 0.8
			material.emission_enabled = true
			material.emission = POST_EDGE_RGB if edge else FACE_RGB
			material.emission_energy_multiplier = \
				POST_EDGE_ENERGY if edge else POST_BASE_ENERGY
			post.material_override = material
			_post_edge.append(edge)
			# A CylinderMesh runs along +Y; the pillar has to run along -Z.
			post.transform = Transform3D(
				Basis(Vector3.RIGHT, Vector3.BACK, Vector3.UP),
				Vector3(radius * cos(angle), radius * sin(angle),
					-0.5 * post_depth))
			root.add_child(post)
			post_row[vertex] = _posts.size()
			_posts.append(post)
			_post_materials.append(material)
		_post_index.append(post_row)

		var panel_row := {}
		for slot in count:
			if open_slots.has(slot):
				continue
			panel_row[slot] = running
			running += 1
			_panel_shell.append(shell_id)
			_panel_slot.append(slot)
			_panel_chord.append(chord)
			_panel_break_time.append(-1.0)
			_panel_transitions.append([])

			var material := StandardMaterial3D.new()
			material.albedo_color = PANEL_RGB * float(SHELL_ALBEDO_VALUE[shell_id])
			material.metallic = float(SHELL_METALLIC[shell_id])
			material.roughness = float(SHELL_ROUGHNESS[shell_id])
			material.emission_enabled = true
			material.emission = CRITICAL_RGB
			material.emission_energy_multiplier = 0.0
			_panel_materials.append(material)

			var mark_material := StandardMaterial3D.new()
			mark_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
			mark_material.albedo_color = CRACK_RGB
			mark_material.emission_enabled = true
			mark_material.emission = CRACK_RGB
			mark_material.emission_energy_multiplier = 0.0
			_panel_mark_material.append(mark_material)

			var face_material := StandardMaterial3D.new()
			face_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
			face_material.albedo_color = FACE_RGB
			face_material.emission_enabled = true
			face_material.emission = FACE_RGB
			face_material.emission_energy_multiplier = FACE_ENERGY
			_panel_face_material.append(face_material)

			var back_material := StandardMaterial3D.new()
			back_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
			back_material.albedo_color = BACK_RGB
			back_material.emission_enabled = true
			back_material.emission = BACK_RGB
			back_material.emission_energy_multiplier = BACK_ENERGY
			_panel_back_material.append(back_material)

			# `critical` and `fractured` glow *around* the panel rather than
			# recolouring it. The body keeps its own material in every state.
			var stress_material := StandardMaterial3D.new()
			stress_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
			stress_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
			stress_material.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
			stress_material.albedo_texture = _radial_texture
			stress_material.albedo_color = Color(CRITICAL_RGB, 0.0)
			_panel_stress_material.append(stress_material)
			var stress := MeshInstance3D.new()
			var stress_quad := QuadMesh.new()
			stress_quad.size = Vector2(chord * 0.80, chord * 0.80)
			stress.mesh = stress_quad
			stress.material_override = stress_material
			stress.visible = false
			root.add_child(stress)
			_panel_stress.append(stress)

			var chamfer: float = PANEL_CHAMFER_BY_SHELL[shell_id]
			var piece_length := chord / float(PANEL_SEGMENTS)
			var slabs: Array[MeshInstance3D] = []
			for segment in PANEL_SEGMENTS:
				var slab := MeshInstance3D.new()
				slab.name = "S%dP%02dS%d" % [shell_id, slot, segment]
				slab.mesh = _chamfered_slab(
					piece_length, thickness, depth,
					chamfer, segment == 0, segment == PANEL_SEGMENTS - 1)
				slab.material_override = material
				root.add_child(slab)
				# The lit face rides the slab as a child, so it splits when the
				# panel fractures and retracts when it breaks without a single
				# line of code knowing about it.
				# Inset only where the sub-slab is the *end* of its panel. The
				# first version inset both ends of all three, so every healthy
				# panel was drawn as three bright bars with two dark gaps -
				# every panel in the arena looked pre-fractured, and the two
				# gaps that are supposed to mean `fractured` meant nothing.
				var trim_low: float = chamfer if segment == 0 else 0.0
				var trim_high: float = chamfer \
					if segment == PANEL_SEGMENTS - 1 else 0.0
				var plate := MeshInstance3D.new()
				var plate_quad := QuadMesh.new()
				plate_quad.size = Vector2(
					piece_length - trim_low - trim_high, thickness)
				plate.mesh = plate_quad
				plate.material_override = face_material
				plate.position = Vector3(
					0.5 * (trim_low - trim_high), 0.0, FACE_Z)
				slab.add_child(plate)

				var back := MeshInstance3D.new()
				var back_quad := QuadMesh.new()
				back_quad.size = Vector2(
					piece_length - trim_low - trim_high - 2.0 * chamfer,
					thickness - 2.0 * chamfer)
				back.mesh = back_quad
				back.material_override = back_material
				back.position = Vector3(
					0.5 * (trim_low - trim_high), 0.0, -depth - 0.004)
				slab.add_child(back)
				slabs.append(slab)
			_panel_slabs.append(slabs)

			# **A wound, not a marker.** Six parts: a dark chip where the
			# material went, the **lit lip of broken material around it**, a
			# hairline in the bottom of the pit, two branches that only appear
			# once the panel is critical, and the seam that joins this wound to
			# the next one. Each part runs from just in front of the face back
			# into the wall, so it protrudes through the inset flank and is read
			# on the flank too - which on the outer shells is most of what is on
			# screen.
			#
			# The lip is the 4C addition and it is the one that changed the read.
			# A dark notch with a bright hairline in it is still a mark lying on
			# a surface; a dark notch with a *lit broken edge* is a hole, because
			# a chip in a lit solid catches light on its rim and nothing drawn on
			# a wall does.
			var clusters: Array = _panel_clusters.get(
				"%d:%d" % [shell_id, slot], [])
			var wounds: int = mini(clusters.size(), MAX_DAMAGE_MARKS)
			var marks: Array[MeshInstance3D] = []
			for _m in wounds * MARK_PARTS:
				marks.append(null)
			for wound in wounds:
				# The lip is added first, so the chip's own dark box is drawn over
				# its middle: what survives is a ring of bright broken material
				# around a dark pit.
				var rim := MeshInstance3D.new()
				var rim_box := BoxMesh.new()
				rim_box.size = Vector3(
					DAMAGE_MARK_CHORD + 2.0 * DAMAGE_RIM_MARGIN,
					thickness * DAMAGE_RIM_SPAN,
					depth * 0.50)
				rim.mesh = rim_box
				rim.material_override = _panel_rim_material
				rim.visible = false
				root.add_child(rim)
				marks[wound * MARK_PARTS + MARK_PART_RIM] = rim

				var chip := MeshInstance3D.new()
				var chip_box := BoxMesh.new()
				chip_box.size = Vector3(
					DAMAGE_MARK_CHORD, thickness * 0.68, depth * 0.55)
				chip.mesh = chip_box
				chip.material_override = chip_material
				chip.visible = false
				root.add_child(chip)
				marks[wound * MARK_PARTS + MARK_PART_CHIP] = chip

				for part in [MARK_PART_CRACK, MARK_PART_BRANCH_A,
					MARK_PART_BRANCH_B]:
					var line := MeshInstance3D.new()
					var line_box := BoxMesh.new()
					var span: float = DAMAGE_CRACK_SPAN if part == MARK_PART_CRACK \
						else DAMAGE_CRACK_SPAN * DAMAGE_BRANCH_LENGTH
					var width: float = DAMAGE_CRACK_WIDTH if part == MARK_PART_CRACK \
						else DAMAGE_CRACK_WIDTH * 0.68
					line_box.size = Vector3(
						width, thickness * span,
						depth * (0.80 if part == MARK_PART_CRACK else 0.45))
					line.mesh = line_box
					line.material_override = mark_material
					line.visible = false
					root.add_child(line)
					marks[wound * MARK_PARTS + part] = line

				# The seam, one unit long along the chord and scaled at apply time
				# to the gap between this wound and the next, so one mesh serves
				# every seam this wound can ever have.
				var seam := MeshInstance3D.new()
				var seam_box := BoxMesh.new()
				seam_box.size = Vector3(1.0, DAMAGE_SEAM_WIDTH, depth * 0.62)
				seam.mesh = seam_box
				seam.material_override = mark_material
				seam.visible = false
				root.add_child(seam)
				marks[wound * MARK_PARTS + MARK_PART_SEAM] = seam
			_panel_marks.append(marks)
		_panel_index.append(panel_row)


func _chamfered_slab(length: float, thickness: float, depth: float,
		chamfer: float, cap_low: bool, cap_high: bool) -> ArrayMesh:
	## A slab whose **front** face at z = 0 is the canonical collision
	## silhouette and whose body recedes to z = -depth, inset by `chamfer`.
	##
	## The front face is full size and the back is smaller, so under the
	## perspective camera the flank is visible and lies *inside* the front
	## face. Ends are only chamfered where the slab is the end of its panel:
	## chamfering an internal join would draw a seam through a healthy panel
	## and make it look pre-fractured.
	var hl := length * 0.5
	var ht := thickness * 0.5
	var low: float = -hl + (chamfer if cap_low else 0.0)
	var high: float = hl - (chamfer if cap_high else 0.0)
	var ft := maxf(0.02, ht - chamfer)

	var vertices := PackedVector3Array([
		Vector3(-hl, -ht, 0.0), Vector3(hl, -ht, 0.0),
		Vector3(hl, ht, 0.0), Vector3(-hl, ht, 0.0),
		Vector3(low, -ft, -depth), Vector3(high, -ft, -depth),
		Vector3(high, ft, -depth), Vector3(low, ft, -depth),
	])
	# **Clockwise seen from +Z.** Godot's front face is the clockwise winding,
	# and a counter-clockwise slab is silently culled - Test #1 rendered an
	# arena with none of its fifty-one tiles visible before this was found.
	var indices := PackedInt32Array([
		2, 1, 0, 3, 2, 0,          # front face, at z = 0
		1, 5, 4, 0, 1, 4,          # lower flank
		2, 6, 5, 1, 2, 5,          # outer flank
		3, 7, 6, 2, 3, 6,          # upper flank
		0, 4, 7, 3, 0, 7,          # inner flank
	])

	var surface := SurfaceTool.new()
	surface.begin(Mesh.PRIMITIVE_TRIANGLES)
	# Flat shading: averaged normals would blend each flank into the face, and
	# the flank's separate shade is the entire reason it reads as depth.
	surface.set_smooth_group(-1)
	for index in indices:
		surface.add_vertex(vertices[index])
	surface.generate_normals()
	return surface.commit()


func _oriented_basis(along: Vector2, scale_x: float, scale_y: float) -> Basis:
	## `Basis(along, +Z x along, +Z)`, with the two in-plane axes pre-scaled.
	##
	## Building the second axis as `z.cross(x)` makes the basis right-handed by
	## construction. A mirrored basis reverses every triangle's winding and
	## backface culling then removes the whole slab, which is how Test #1 first
	## rendered an arena with none of its fifty-one tiles visible.
	var x := Vector3(along.x, along.y, 0.0)
	var z := Vector3(0.0, 0.0, 1.0)
	var y := z.cross(x)
	return Basis(x * scale_x, y * scale_y, z)


func _panel_basis(along: Vector2) -> Basis:
	return _oriented_basis(along, 1.0, 1.0)


func _disc_mesh(radius: float, segments: int) -> ArrayMesh:
	var vertices := PackedVector3Array()
	var uvs := PackedVector2Array()
	var indices := PackedInt32Array()
	vertices.append(Vector3.ZERO)
	uvs.append(Vector2(0.5, 0.5))
	for k in segments:
		var angle := TAU * float(k) / float(segments)
		vertices.append(Vector3(radius * cos(angle), radius * sin(angle), 0.0))
		uvs.append(Vector2(0.5 + 0.5 * cos(angle), 0.5 - 0.5 * sin(angle)))
	for k in segments:
		indices.append(0)
		indices.append(1 + ((k + 1) % segments))
		indices.append(1 + k)
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_TEX_UV] = uvs
	arrays[Mesh.ARRAY_INDEX] = indices
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	return mesh


func _ring_gradient(peak: float) -> GradientTexture2D:
	## Transparent at the centre, brightest at `peak` of the radius, gone at the
	## rim: a shockwave rather than a blob. `_radial_gradient` is monotone from
	## the centre out and cannot express this, which is why it is separate.
	var gradient := Gradient.new()
	gradient.set_offset(0, 0.0)
	gradient.set_color(0, Color(1, 1, 1, 0.0))
	gradient.set_offset(1, 1.0)
	gradient.set_color(1, Color(1, 1, 1, 0.0))
	gradient.add_point(clampf(peak - 0.13, 0.02, 0.96), Color(1, 1, 1, 0.25))
	gradient.add_point(clampf(peak, 0.03, 0.97), Color(1, 1, 1, 1.0))
	gradient.add_point(clampf(peak + 0.09, 0.04, 0.98), Color(1, 1, 1, 0.30))
	var texture := GradientTexture2D.new()
	texture.gradient = gradient
	texture.fill = GradientTexture2D.FILL_RADIAL
	texture.fill_from = Vector2(0.5, 0.5)
	texture.fill_to = Vector2(1.0, 0.5)
	texture.width = 256
	texture.height = 256
	return texture


func _radial_gradient(inner: float, outer: float, falloff: float) -> GradientTexture2D:
	## Built once at configure time and never from a per-frame path. Test #1
	## made 125,000 of these in one audit, took a render from 0.6 s to 28.8 s
	## and crashed the engine during shutdown after writing a correct file.
	var gradient := Gradient.new()
	gradient.set_offset(0, 0.0)
	gradient.set_color(0, Color(1, 1, 1, inner))
	gradient.set_offset(1, 1.0)
	gradient.set_color(1, Color(1, 1, 1, outer))
	gradient.add_point(clampf(falloff, 0.02, 0.98),
		Color(1, 1, 1, inner * 0.35 + outer * 0.65))
	var texture := GradientTexture2D.new()
	texture.gradient = gradient
	texture.fill = GradientTexture2D.FILL_RADIAL
	texture.fill_from = Vector2(0.5, 0.5)
	texture.fill_to = Vector2(1.0, 0.5)
	texture.width = 256
	texture.height = 256
	return texture


# --------------------------------------------------------------------------
# Reading the document
# --------------------------------------------------------------------------

const DAMAGE_STATES_ORDER := ["healthy", "damaged", "critical", "fractured", "broken"]


func _read_panel_states() -> void:
	## `panel_states` is the whole damage ledger. A renderer that re-derived a
	## state by accumulating the `damage` stream would be computing physics; the
	## rule here is the Phase 1 document's own - draw the last state entered at
	## or before `t`, and draw nothing once it has broken.
	var order := {}
	for index in DAMAGE_STATES_ORDER.size():
		order[DAMAGE_STATES_ORDER[index]] = index
	for entry in playback["panel_states"]:
		var shell_id := int(entry["shell_id"])
		var panel_id := int(entry["panel_id"])
		var row: Dictionary = _panel_index[shell_id]
		if not row.has(panel_id):
			continue
		var index: int = row[panel_id]
		var transitions := []
		for transition in entry["transitions"]:
			transitions.append([float(transition["t"]),
				int(order.get(str(transition["state"]), 0))])
		_panel_transitions[index] = transitions
		if entry["break_time"] != null:
			_panel_break_time[index] = float(entry["break_time"])


func _read_wear() -> void:
	## `[t, fraction]` per panel from the canonical `damage` stream: the
	## continuous version of the five-state ledger, not a second opinion on it.
	for event in playback["events"]:
		if str(event["kind"]) != "damage":
			continue
		var key := "%d:%d" % [int(event["shell_id"]), int(event["panel_id"])]
		if not _panel_wear.has(key):
			_panel_wear[key] = []
		_panel_wear[key].append([float(event["t"]), float(event["fraction"])])


func _wear_at(index: int, t: float) -> float:
	var rows: Array = _panel_wear.get(_panel_key(index), [])
	var wear := 0.0
	for row in rows:
		if float(row[0]) <= t:
			wear = float(row[1])
		else:
			break
	return wear


func _read_impacts() -> void:
	## Where each panel was hit, along its own chord, in time order, and the
	## wounds those impacts add up to.
	##
	## `panel_local_offset` is on every canonical collision, so a crack starts
	## where the ball actually hit rather than at a decorative position. Two
	## impacts within `DAMAGE_CLUSTER_CHORD` of each other are the same wound
	## and the second deepens the first: repeated hits in one area build on one
	## another instead of drawing a second identical marker beside the first.
	for event in playback["events"]:
		if str(event["kind"]) != "collision":
			continue
		var shell_id := int(event["shell_id"])
		var panel_id := int(event["panel_id"])
		var key := "%d:%d" % [shell_id, panel_id]
		var offset := float(event["panel_local_offset"])
		if not _panel_impacts.has(key):
			_panel_impacts[key] = []
		_panel_impacts[key].append(offset)
		if not _panel_clusters.has(key):
			_panel_clusters[key] = []
		var row: Array = _panel_clusters[key]
		var merged := false
		for cluster in row:
			if absf(float(cluster[0]) - offset) <= DAMAGE_CLUSTER_CHORD:
				cluster[1] = int(cluster[1]) + 1
				merged = true
				break
		if not merged:
			# [offset, weight, index, tilt_sign, growth]
			row.append([offset, 1, row.size(),
				1 if (shell_id * 7 + panel_id * 3 + row.size()) % 2 == 0 else -1,
				1.0])
	for key in _panel_clusters:
		var row: Array = _panel_clusters[key]
		for cluster in row:
			cluster[4] = minf(DAMAGE_CLUSTER_GROWTH_MAX,
				1.0 + DAMAGE_CLUSTER_GROWTH * float(int(cluster[1]) - 1))
		# Worst wound first, ties by the order the wounds appeared. A panel hit
		# twelve times in one place and once elsewhere shows the deep one.
		row.sort_custom(func(a, b):
			if int(a[1]) != int(b[1]):
				return int(a[1]) > int(b[1])
			return int(a[2]) < int(b[2]))
	_build_seams()


func _build_seams() -> void:
	## The fissures that join a panel's wounds into one crack network.
	##
	## `critical` asks for a *connected* network and up to 4B a panel with three
	## wounds drew three unconnected injuries however bad it got - the count
	## went up, the structure did not change. A seam joins consecutive shown
	## wounds **in chord order**, and it invents nothing: both endpoints are
	## canonical impact positions and the state comes from the canonical ledger.
	##
	## Precomputed per state because the shown set is a function of the state,
	## and deterministic for the same reason the wounds are.
	for key in _panel_clusters:
		var row: Array = _panel_clusters[key]
		var by_state := {}
		for state in DAMAGE_SEAM_STATES.size():
			if not bool(DAMAGE_SEAM_STATES[state]):
				continue
			var wanted: int = mini(int(DAMAGE_CRACK_COUNT[state]), row.size())
			if wanted < 2:
				continue
			# The shown set is the first `wanted` of the worst-first row; the
			# seams run along the chord, so they are ordered by offset.
			var shown := []
			for index in wanted:
				shown.append([float(row[index][0]), index])
			shown.sort_custom(func(a, b): return float(a[0]) < float(b[0]))
			var seams := []
			for pair in shown.size() - 1:
				var low: Array = shown[pair]
				var high: Array = shown[pair + 1]
				var length: float = absf(float(high[0]) - float(low[0]))
				if length < DAMAGE_SEAM_MIN_CHORD:
					continue
				seams.append([int(low[1]),
					0.5 * (float(low[0]) + float(high[0])), length])
			if not seams.is_empty():
				by_state[state] = seams
		if not by_state.is_empty():
			_panel_seams[key] = by_state


func _read_damage_teams() -> void:
	## Which team has worn each panel down, from `team_cumulative`.
	##
	## The brief allows "a tiny local Cyan/Orange stress tint" where both teams
	## contributed. `both` is deliberately not "the minority is non-zero" - one
	## glancing hit out of nineteen is not two teams wearing a panel down
	## together, and a tint that fired on it would be noise.
	for event in playback["events"]:
		if str(event["kind"]) != "damage":
			continue
		var totals: Array = event["team_cumulative"]
		var total := 0.0
		for value in totals:
			total += float(value)
		var lead := 0
		for index in totals.size():
			if float(totals[index]) > float(totals[lead]):
				lead = index
		var minority: float = 0.0
		if total > 0.0:
			minority = (total - float(totals[lead])) / total
		_panel_teams["%d:%d" % [int(event["shell_id"]), int(event["panel_id"])]] = [
			lead,
			DAMAGE_TEAM_TINT if minority >= DAMAGE_TEAM_TINT_MIN_SHARE else 0.0,
		]


func _panel_state_at(index: int, t: float) -> int:
	var state := 0
	for transition in _panel_transitions[index]:
		if float(transition[0]) <= t:
			state = int(transition[1])
		else:
			break
	return state


func _read_events() -> void:
	for event in playback["events"]:
		var kind := str(event["kind"])
		if kind == "ball_spawn":
			_spawns.append({
				"t": float(event["t"]),
				"ball_id": int(event["ball_id"]),
				"parent_id": int(event["parent_id"]),
			})
		elif kind == "near_miss":
			_near_misses.append({
				"t": float(event["t"]),
				"shell_id": int(event["shell_id"]),
				"panel_id": int(event["panel_id"]),
				"ball_id": int(event["ball_id"]),
				"position": Vector2(float(event["ball_position"][0]),
					float(event["ball_position"][1])),
				"radii": float(event["arc_separation_ball_radii"]),
			})
		elif kind == "panel_break":
			_breaks.append({
				"t": float(event["t"]),
				"shell_id": int(event["shell_id"]),
				"panel_id": int(event["panel_id"]),
				"position": Vector2(float(event["position"][0]),
					float(event["position"][1])),
				"contributors": int(event["contributors"]),
			})
		elif kind == "shell_exit" and str(event.get("route", "")) == "break":
			_passage_exits.append({
				"t": float(event["t"]),
				"shell_id": int(event["shell_id"]),
				"panel_id": int(event["panel_id"]),
				"ball_id": int(event["ball_id"]),
			})
		elif kind == "escape":
			_escape = {
				"t": float(event["t"]),
				"ball_id": int(event["ball_id"]),
				"team_id": int(event["team_id"]),
				"position": Vector2(float(event["position"][0]),
					float(event["position"][1])),
			}


# --------------------------------------------------------------------------
# Balls
# --------------------------------------------------------------------------


func _resolve_passage_uses() -> void:
	## An exit through a slot that broke open within the window. Derived from
	## the canonical streams only: `panel_break` opens the slot and a
	## `shell_exit` with `route == "break"` on that slot is a ball using it.
	var opened := {}
	for entry in _breaks:
		var key := "%d:%d" % [int(entry["shell_id"]), int(entry["panel_id"])]
		if not opened.has(key):
			opened[key] = float(entry["t"])
	for exit_event in _passage_exits:
		var key := "%d:%d" % [int(exit_event["shell_id"]), int(exit_event["panel_id"])]
		if not opened.has(key):
			continue
		var at: float = float(opened[key])
		var when: float = float(exit_event["t"])
		if when < at or when > at + FLOOD_WINDOW_SECONDS:
			continue
		_passage_uses.append(exit_event)


func _build_balls() -> void:
	## One colour per ball, from `team_id` and nothing else. Every descendant is
	## exactly its team's hue for the whole run; generation lifts the emission
	## and never the hue, because "which colour is winning" is the only question
	## the video asks and a paled fourth-generation cyan stops answering it.
	var container := Node3D.new()
	container.name = "Balls"
	add_child(container)

	var radius := float(playback["config"]["ball_radius"]) * BALL_DRAW_SCALE
	var sphere := SphereMesh.new()
	sphere.radius = radius
	sphere.height = 2.0 * radius
	sphere.radial_segments = 24
	sphere.rings = 12
	var unit_quad := QuadMesh.new()
	unit_quad.size = Vector2(1.0, 1.0)
	var halo_quad := QuadMesh.new()
	halo_quad.size = Vector2(2.0 * radius * HALO_SCALE, 2.0 * radius * HALO_SCALE)
	var rim_mesh := _disc_mesh(radius * BALL_RIM_SCALE, 28)

	for ball in playback["balls"]:
		var ball_id := int(ball["ball_id"])
		var generation := int(ball["generation"])
		var team: int = int(ball["team_id"]) % TEAM_RGB.size()
		var colour: Color = TEAM_RGB[team]
		var energy: float = minf(GENERATION_ENERGY_MAX,
			1.0 + GENERATION_ENERGY_STEP * float(generation))
		_ball_team.append(team)

		_ball_row_of[ball_id] = _ball_ids.size()
		_ball_ids.append(ball_id)
		_ball_birth.append(float(ball["birth_time"]))
		_ball_colour.append(colour)
		_ball_energy.append(energy)
		_ball_flights.append(playback["flights"].get(str(ball_id), []))

		var trail_material := StandardMaterial3D.new()
		trail_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		trail_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		trail_material.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
		trail_material.albedo_color = colour
		_ball_trail_material.append(trail_material)

		var segments: Array[MeshInstance3D] = []
		for _s in TRAIL_SAMPLES - 1:
			var piece := MeshInstance3D.new()
			piece.mesh = unit_quad
			piece.material_override = trail_material
			piece.visible = false
			container.add_child(piece)
			segments.append(piece)
		_ball_trail.append(segments)

		var halo_material := StandardMaterial3D.new()
		halo_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		halo_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		halo_material.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
		halo_material.albedo_texture = _halo_texture
		halo_material.albedo_color = colour
		_ball_halo_material.append(halo_material)
		var halo := MeshInstance3D.new()
		halo.name = "Halo%d" % ball_id
		halo.mesh = halo_quad
		halo.material_override = halo_material
		halo.visible = false
		container.add_child(halo)
		_ball_halo.append(halo)

		# The dark rim. Seven balls inside two drawn diameters happens - seed
		# 7183 at 15.6 s - and seven bright discs with no rims are one blob.
		var rim_material := StandardMaterial3D.new()
		rim_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		rim_material.albedo_color = Color(0.020, 0.028, 0.048)
		var rim := MeshInstance3D.new()
		rim.name = "Rim%d" % ball_id
		rim.mesh = rim_mesh
		rim.material_override = rim_material
		rim.visible = false
		container.add_child(rim)
		_ball_rim.append(rim)

		var core_material := StandardMaterial3D.new()
		core_material.albedo_color = colour
		core_material.metallic = 0.0
		core_material.roughness = 0.22
		core_material.emission_enabled = true
		core_material.emission = colour
		core_material.emission_energy_multiplier = 1.55 * energy
		_ball_core_material.append(core_material)
		var core := MeshInstance3D.new()
		core.name = "Ball%d" % ball_id
		core.mesh = sphere
		core.material_override = core_material
		core.visible = false
		container.add_child(core)
		_ball_core.append(core)


func position_of(ball_id: int, t: float) -> Vector2:
	## Evaluate the canonical flight in progress. Gravity is zero and speed is
	## constant, so a flight record *is* the trajectory and this is exact.
	if not _ball_row_of.has(ball_id):
		return Vector2.ZERO
	return _position_row(int(_ball_row_of[ball_id]), t)


func _position_row(row: int, t: float) -> Vector2:
	## For drawing. `Vector2` is 32-bit, which is fine for a transform and not
	## fine for the audit - see `_position_pair`.
	var pair := _position_pair(row, t)
	return Vector2(pair[0], pair[1])


func _position_pair(row: int, t: float) -> Array:
	## The same evaluation in **doubles**.
	##
	## A Godot `Vector2` holds 32-bit floats. Reporting the audit through one
	## costs about 1e-6 world units, which is a million times the arithmetic
	## the scene actually does, and it made the first audit of this phase read
	## 1.18e-06 where the true figure is at the limit of a double. GDScript's
	## own `float` is a double, so the audit path never narrows.
	var flights: Array = _ball_flights[row]
	if flights.is_empty():
		return [0.0, 0.0]
	var lo := 0
	var hi := flights.size() - 1
	if t > float(flights[0]["t"]):
		while lo < hi:
			var mid := int((lo + hi + 1) / 2)
			if float(flights[mid]["t"]) <= t:
				lo = mid
			else:
				hi = mid - 1
	var flight: Dictionary = flights[lo]
	var dt := t - float(flight["t"])
	return [float(flight["x"]) + float(flight["vx"]) * dt,
		float(flight["y"]) + float(flight["vy"]) * dt]


func population_at(t: float) -> int:
	var count := 0
	for row in _ball_birth.size():
		if _ball_birth[row] <= t:
			count += 1
	return count


# --------------------------------------------------------------------------
# Effects, all keyed to canonical events
# --------------------------------------------------------------------------


func _build_effects() -> void:
	var container := Node3D.new()
	container.name = "Effects"
	add_child(container)

	# `_radial_gradient(inner, outer, ...)` interpolates *alpha* from `inner` at
	# the centre to `outer` at the rim, so the first version of this line -
	# `(0.0, 0.0, ...)` for both - built two fully transparent textures and the
	# spawn flash, the near-miss spark, the break ring and the escape ring were
	# all invisible for four render passes. They are not subtle effects; they
	# were simply not there.
	var flash_texture := _radial_gradient(1.0, 0.0, 0.40)
	var ring_texture := _ring_gradient(0.74)
	var unit_quad := QuadMesh.new()
	unit_quad.size = Vector2(1.0, 1.0)

	for spawn in _spawns:
		var colour: Color = _ball_colour[int(_ball_row_of[spawn["ball_id"]])]

		var flash_material := StandardMaterial3D.new()
		flash_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		flash_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		flash_material.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
		flash_material.albedo_texture = flash_texture
		flash_material.albedo_color = colour
		var flash := MeshInstance3D.new()
		flash.mesh = unit_quad
		flash.material_override = flash_material
		flash.visible = false
		container.add_child(flash)
		_spawn_flash.append(flash)
		_spawn_flash_material.append(flash_material)

		# The umbilical. One ball visibly becoming two is the highest-leverage
		# shot in the video and it is over in under a second, so the two
		# canonical positions are joined for 0.18 s and nothing else happens.
		var link_material := StandardMaterial3D.new()
		link_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		link_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		link_material.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
		link_material.albedo_color = colour
		var link := MeshInstance3D.new()
		link.mesh = unit_quad
		link.material_override = link_material
		link.visible = false
		container.add_child(link)
		_spawn_link.append(link)
		_spawn_link_material.append(link_material)

	for _entry in _near_misses:
		var spark_material := StandardMaterial3D.new()
		spark_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		spark_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		spark_material.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
		spark_material.albedo_texture = flash_texture
		spark_material.albedo_color = Color(1.0, 0.95, 0.86)
		var spark := MeshInstance3D.new()
		spark.mesh = unit_quad
		spark.material_override = spark_material
		spark.visible = false
		container.add_child(spark)
		_near_miss_spark.append(spark)
		_near_miss_material.append(spark_material)

	for _entry in _breaks:
		var ring_material := StandardMaterial3D.new()
		ring_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		ring_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		ring_material.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
		ring_material.albedo_texture = ring_texture
		ring_material.albedo_color = BREAK_FLASH_RGB
		var ring := MeshInstance3D.new()
		ring.mesh = unit_quad
		ring.material_override = ring_material
		ring.visible = false
		container.add_child(ring)
		_break_ring.append(ring)
		_break_ring_material.append(ring_material)

		var debris_material := StandardMaterial3D.new()
		debris_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		debris_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		debris_material.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
		debris_material.albedo_color = CRACK_RGB
		debris_material.albedo_texture = flash_texture
		_debris_material.append(debris_material)
		for _k in BREAK_DEBRIS_COUNT:
			var spark := MeshInstance3D.new()
			spark.mesh = unit_quad
			spark.material_override = debris_material
			spark.visible = false
			container.add_child(spark)
			_debris.append(spark)

		# **Chunks of the panel, not particles.** A fragment is a box with the
		# panel's own radial thickness and a share of its depth, in the panel's
		# own material dimmed - so what leaves the wall is recognisably the
		# wall. Four of them, laid along the chord, is the brief's 3-6 and is
		# what makes the failure read as "it came apart" rather than as a puff.
		var shell_id := int(_breaks[_break_ring.size() - 1]["shell_id"])
		var panel_id := int(_breaks[_break_ring.size() - 1]["panel_id"])
		var shell: Dictionary = playback["shells"][shell_id]
		var chord := float(shell["chord_length"])
		var thickness := float(shell["thickness"])
		var depth: float = panel_depth[shell_id]
		var fragment_material := StandardMaterial3D.new()
		fragment_material.albedo_color = PANEL_RGB \
			* float(SHELL_ALBEDO_VALUE[shell_id]) * 0.82
		fragment_material.metallic = float(SHELL_METALLIC[shell_id])
		fragment_material.roughness = float(SHELL_ROUGHNESS[shell_id])
		fragment_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		_fragment_material.append(fragment_material)
		for piece in BREAK_FRAGMENT_COUNT:
			var chunk := MeshInstance3D.new()
			var chunk_box := BoxMesh.new()
			chunk_box.size = Vector3(
				chord * BREAK_FRAGMENT_CHORD_FRACTION, thickness,
				depth * BREAK_FRAGMENT_DEPTH_FRACTION)
			chunk.mesh = chunk_box
			chunk.material_override = fragment_material
			chunk.visible = false
			container.add_child(chunk)
			_fragments.append(chunk)

	_escape_ring_material = StandardMaterial3D.new()
	_escape_ring_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	_escape_ring_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	_escape_ring_material.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
	_escape_ring_material.albedo_texture = ring_texture
	_escape_ring_material.albedo_color = Color(1.0, 0.97, 0.90)
	_escape_ring = MeshInstance3D.new()
	_escape_ring.mesh = unit_quad
	_escape_ring.material_override = _escape_ring_material
	_escape_ring.visible = false
	container.add_child(_escape_ring)


func _label(size: int, colour: Color, top: float) -> Label:
	var label := Label.new()
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	label.vertical_alignment = VERTICAL_ALIGNMENT_TOP
	label.add_theme_font_size_override("font_size", size)
	label.add_theme_color_override("font_color", colour)
	label.set_anchors_preset(Control.PRESET_TOP_WIDE)
	label.offset_top = top
	label.offset_bottom = top + float(size) * 2.2
	label.offset_left = float(_width) * SAFE_MARGIN_FRACTION
	label.offset_right = -float(_width) * SAFE_MARGIN_FRACTION
	label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return label


func _build_overlay() -> void:
	var layer := CanvasLayer.new()
	layer.name = "Overlay"
	add_child(layer)

	var root := Control.new()
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	layer.add_child(root)

	var hook_size := int(float(_height) * HOOK_SIZE_FRACTION)
	var hook_top := float(_height) * HOOK_TOP_FRACTION
	_hook_label = _label(hook_size, TEXT_PRIMARY, hook_top)
	_hook_label.text = HOOK_TEXT
	root.add_child(_hook_label)

	# **No team legend.** The brief offers a "cyan dot vs orange dot" beside the
	# question and makes it conditional: add an indicator only if the two colours
	# are not self-explanatory. At frame zero they are - two balls, 73 px across,
	# one of each colour, on a black field, under the words. The first render
	# with the dots in settled it the other way round as well: at this type size
	# they landed inside the words and the hook read "WHO(o)ESCAPES FI(o)RST?".
	# So the overlay is one line at the top and one at the bottom, and nothing
	# else.

	# **The banner goes to whichever end the escaping ball is not at.** 4A
	# pinned it at 0.735 of the height; on a candidate whose escape happens low
	# the payoff is then covered by its own caption. The choice is made from
	# the canonical escape position under the canonical final framing, so it is
	# deterministic and `winner_banner_placement` predicts it exactly.
	var winner_size := int(float(_height) * WINNER_SIZE_FRACTION)
	var winner_top: float = WINNER_TOP_FRACTION
	if not _escape.is_empty():
		# The escapee keeps flying through the release beat while the banner is
		# on screen, so the whole swept extent is what has to clear it - not the
		# position at the escape instant. On 1176 those differ by 101 px and the
		# instant-only version put the caption under the ball.
		var view := _view_radius_at(float(_escape["t"]))
		var scale := float(_width) * view_diameter / (2.0 * view)
		var ball_px := float(playback["config"]["ball_radius"]) \
			* BALL_DRAW_SCALE * scale
		var row := int(_ball_row_of[int(_escape["ball_id"])])
		var low := INF
		var high := -INF
		for index in WINNER_RELEASE_SAMPLES:
			var t: float = _duration + release_seconds * float(index) \
				/ float(WINNER_RELEASE_SAMPLES - 1)
			var point := _position_row(row, t)
			var py := float(_height) * ARENA_CENTRE_Y_FRACTION - point.y * scale
			low = minf(low, py - ball_px)
			high = maxf(high, py + ball_px)
		if not _band_clear(WINNER_TOP_FRACTION, low, high):
			winner_top = WINNER_ALT_TOP_FRACTION
	_winner_label = _label(winner_size, TEXT_PRIMARY,
		float(_height) * winner_top)
	_winner_label.visible = false
	if not _escape.is_empty():
		var team: int = int(_escape.get("team_id", 0)) % TEAM_NAMES.size()
		_winner_label.text = "%s ESCAPES!" % TEAM_NAMES[team]
		_winner_label.add_theme_color_override("font_color", TEAM_RGB[team])
	root.add_child(_winner_label)


func _band_clear(top_fraction: float, low: float, high: float) -> bool:
	var band_top := top_fraction * float(_height)
	var band_bottom := band_top + WINNER_BAND_FRACTION * float(_height)
	return not (high > band_top and low < band_bottom)


func _apply_overlay(render_t: float) -> void:
	if _hook_label != null:
		# Solid, then gone. The label is *hidden* rather than made transparent
		# once the fade completes, so no residue of the question can survive a
		# grade, a codec or a thumbnail - which is what the review saw.
		var fade: float = clampf(
			(render_t - HOOK_HOLD_SECONDS) / HOOK_FADE_SECONDS, 0.0, 1.0)
		var alpha: float = lerpf(1.0, HOOK_FADE_TO, fade)
		_hook_label.visible = alpha > 0.002
		_hook_label.add_theme_color_override("font_color", Color(
			TEXT_PRIMARY.r, TEXT_PRIMARY.g, TEXT_PRIMARY.b, alpha))
	if _winner_label != null and not _escape.is_empty():
		var at := float(_escape["t"])
		if render_t < at:
			_winner_label.visible = false
		else:
			_winner_label.visible = true
			var rise: float = clampf(
				(render_t - at) / WINNER_RISE_SECONDS, 0.0, 1.0)
			_winner_label.modulate = Color(1.0, 1.0, 1.0, rise)


# --------------------------------------------------------------------------
# The clock
# --------------------------------------------------------------------------


func set_time(t: float) -> void:
	## Simulation time. The only way in, and there is no `_process`: a scene
	## that accumulated `delta` would give a still and a clip different pictures
	## of the same instant, and would drift against the canonical times at a
	## rate that depends on how fast the render happened to run.
	set_render_time(clampf(t, 0.0, _duration))


func set_render_time(r: float) -> void:
	_render_time = clampf(r, 0.0, render_duration())
	_time = minf(_render_time, _duration)
	_apply_camera(_time)
	_apply_shells(_time)
	_apply_panels(_time)
	_apply_balls(_render_time)
	_apply_effects(_render_time)
	_apply_overlay(_render_time)


func playback_time() -> float:
	return _time


func _escapee_time() -> float:
	## Only the escaping ball has a canonical flight worth continuing past the
	## document's end: it is outside the arena and there is nothing out there
	## for it to hit. Every other ball is mid-flight with walls in front of it,
	## so continuing one would draw it through a panel. They hold instead, and
	## `--release=0` renders the hard cut for comparison.
	return minf(_render_time, _duration + release_seconds)


# --------------------------------------------------------------------------
# Per frame
# --------------------------------------------------------------------------


func _apply_shells(t: float) -> void:
	for shell_id in _shell_roots.size():
		var angle: float = _shell_theta0[shell_id] + _shell_omega[shell_id] * t
		_shell_roots[shell_id].rotation = Vector3(0.0, 0.0, angle)


func _apply_panels(t: float) -> void:
	for index in _panel_materials.size():
		var shell_id := _panel_shell[index]
		var slot := _panel_slot[index]
		var shell: Dictionary = playback["shells"][shell_id]
		var radius := float(shell["radius"])
		var slot_width := float(shell["slot_width"])
		var chord: float = _panel_chord[index]
		var depth: float = panel_depth[shell_id]
		var state := _panel_state_at(index, t)
		var broken_at: float = _panel_break_time[index]

		# The panel's chord in the shell's own frame. The shell node carries
		# the rotation, so a panel can never be drawn at an angle the ball did
		# not bounce off.
		var a := Vector2(radius * cos(slot * slot_width),
			radius * sin(slot * slot_width))
		var b := Vector2(radius * cos((slot + 1) * slot_width),
			radius * sin((slot + 1) * slot_width))
		var centre := (a + b) * 0.5
		var along := (b - a).normalized()
		var basis := _panel_basis(along)

		var retract := 0.0
		if broken_at >= 0.0 and t >= broken_at:
			retract = ease_out_cubic(
				clampf((t - broken_at) / BREAK_RETRACT_SECONDS, 0.0, 1.0))
		var fractured: bool = state >= 3
		# Which end of the panel carries the deepest section, from the panel's
		# own identity, so neighbouring panels do not fracture into the same
		# shape and no two renders of one seed differ.
		var tilt_parity: float = 1.0 if (shell_id * 5 + slot * 3) % 2 == 0 else -1.0
		var gap: float = FRACTURE_GAP if fractured else 0.0
		var piece := chord / float(PANEL_SEGMENTS)
		var slabs: Array = _panel_slabs[index]

		for segment in PANEL_SEGMENTS:
			var slab: MeshInstance3D = slabs[segment]
			if retract >= 0.999:
				slab.visible = false
				continue
			slab.visible = true
			# Cut the gaps out of the sub-slabs rather than pushing them apart,
			# so the panel's two ends stay exactly where they were and a
			# fractured panel never occupies a pixel a healthy one did not.
			var low := -0.5 * chord + segment * piece
			var high := low + piece
			if segment > 0:
				low += 0.5 * gap
			if segment < PANEL_SEGMENTS - 1:
				high -= 0.5 * gap
			var offset := 0.5 * (low + high)
			var length := maxf(0.02, high - low)
			if retract > 0.0:
				# Retract toward the nearest flanking post: material leaves
				# along its own chord and recedes behind the shell, so the
				# passage is clear and nothing is left to clutter it.
				length = maxf(0.02, length * (1.0 - retract))
				var anchor := -0.5 * chord if segment == 0 else (
					0.5 * chord if segment == PANEL_SEGMENTS - 1 else offset)
				offset = lerpf(offset, anchor, retract)
			var tilt := deg_to_rad(FRACTURE_TILT_DEGREES) * float(segment - 1) \
				if fractured else 0.0
			# Each section recedes by its own amount once the panel fractures, so
			# the boundaries between them throw edges and the slab reads as three
			# pieces that have shifted rather than one piece with two lines drawn
			# on it. Inward only - a fractured panel still never occupies a pixel
			# a healthy one did not, which is what keeps presentation off the
			# collision silhouette until the canonical break.
			var recess := -depth * 0.6 * retract
			if fractured:
				recess -= FRACTURE_RECESS + float(FRACTURE_SEGMENT_RECESS[
					segment if tilt_parity > 0.0 else PANEL_SEGMENTS - 1 - segment])
			# Scale the local x axis by building the basis with a pre-scaled
			# column: `Basis.scaled` scales rows, which is the *global* axes,
			# and would shear a panel that is not axis-aligned. Then roll about
			# the slab's own long axis, which leaves that column untouched.
			var oriented := _oriented_basis(along, length / piece, 1.0).rotated(
				Vector3(along.x, along.y, 0.0), tilt)
			slab.transform = Transform3D(oriented,
				Vector3(centre.x + along.x * offset,
					centre.y + along.y * offset, recess))

		_apply_panel_marks(index, state, t, chord, centre, along, basis, depth,
			_wear_at(index, t))

		# The panel body keeps its own material in every state. A recolour of
		# the whole panel is the thing the redesign exists to avoid, and the
		# first render of this scene did it anyway - forty panels rendered a
		# flat orange-brown at `damaged` because the body emission was on. So
		# the body only ever goes white-hot, only at a break, and only for
		# 0.12 s; everything else is the marks, the stress glow and the face.
		var material: StandardMaterial3D = _panel_materials[index]
		var flashing: bool = broken_at >= 0.0 and t >= broken_at \
			and t < broken_at + BREAK_FLASH_SECONDS
		material.emission = BREAK_FLASH_RGB
		material.emission_energy_multiplier = 16.0 if flashing else 0.0
		# **Surface roughness, which the brief asks for at `damaged` and which
		# no amount of added geometry supplies.** A beaten panel stops taking a
		# clean specular highlight before it has a single crack on it, because
		# that is a property of the whole face rather than a shape on it.
		# Continuous in the canonical `fraction` below the first damage state
		# and stepped by the ledger above it, so the two halves of one read
		# meet without a discontinuity.
		var roughness: float = float(SHELL_ROUGHNESS[shell_id])
		if state == 0:
			roughness += DAMAGE_WEAR_ROUGHNESS * clampf(
				_wear_at(index, t), 0.0, 1.0)
		else:
			roughness += float(DAMAGE_STATE_ROUGHNESS[state])
		material.roughness = minf(1.0, roughness)

		# A worn panel loses its sheen before it gains a crack, which is a
		# reading a viewer gets without being told and without the panel
		# changing colour.
		# A worn panel loses its sheen before it gains a crack. 4A made that a
		# five-step ladder, so the whole of `healthy` was one flat value; the
		# canonical `fraction` makes it continuous, and on the final wall that
		# is the difference between a pristine ring and one being worn down.
		var wear := _wear_at(index, t)
		var face: StandardMaterial3D = _panel_face_material[index]
		var face_energy: float = FACE_ENERGY * [1.0, 0.72, 0.45, 0.22, 0.0][state]
		if state == 0:
			face_energy *= 1.0 - DAMAGE_WEAR_FACE_LOSS * clampf(wear, 0.0, 1.0)
		if flashing:
			face_energy = 9.0
		face.emission_energy_multiplier = face_energy * (1.0 - retract)
		face.albedo_color = Color(FACE_RGB, 1.0)
		var back: StandardMaterial3D = _panel_back_material[index]
		back.emission_energy_multiplier = BACK_ENERGY \
			* [1.0, 0.80, 0.58, 0.34, 0.0][state] * (1.0 - retract)

		var stress: MeshInstance3D = _panel_stress[index]
		var stress_material: StandardMaterial3D = _panel_stress_material[index]
		if state < 2 or retract >= 0.999:
			stress.visible = false
		else:
			stress.visible = true
			stress.transform = Transform3D(Basis.IDENTITY,
				Vector3(centre.x, centre.y, STRESS_Z))
			var glow: float = (0.16 if state == 2 else 0.30) * (1.0 - retract)
			var hot: Color = CRITICAL_RGB if state == 2 else FRACTURE_RGB
			# **The brief's "tiny local Cyan/Orange stress tint".** Where both
			# teams really have worn this panel down, its glow leans a fifth of
			# the way toward whichever of them has done more - and no further,
			# and on this localised glow only. The panel body, the chip, the lip
			# and the cracks are never tinted, because the wall has to keep
			# looking like a wall.
			var team_row: Array = _panel_teams.get(_panel_key(index), [])
			if team_row.size() == 2 and float(team_row[1]) > 0.0:
				hot = hot.lerp(TEAM_RGB[int(team_row[0])], float(team_row[1]))
			stress_material.albedo_color = Color(hot, glow)


func ease_out_cubic(u: float) -> float:
	var v := 1.0 - clampf(u, 0.0, 1.0)
	return 1.0 - v * v * v


func _apply_panel_marks(index: int, state: int, t: float, chord: float,
		centre: Vector2, along: Vector2, basis: Basis, depth: float,
		wear: float) -> void:
	## Damage that happened *to the material*: a dark chip where it went, the
	## lit lip of broken material around it, a hairline in the bottom of the
	## pit, branches once the panel is critical, and a seam joining this wound
	## to the next one so the network is connected rather than repeated.
	##
	## The 4A version drew up to six identical bright bars of a fixed width at
	## the first six impact offsets, at up to 4.0 emission on an unshaded
	## material - a row of lit markers lying on a wall, which is what the human
	## review called "UI annotations". 4B made it a pit with a hairline in it and
	## the review still called it marks. 4C adds the two things a pit was
	## missing: **a lit broken edge**, which is what makes a dark notch read as a
	## hole rather than as a dot, and **a connection between wounds**, which is
	## what makes three injuries read as one failing panel.
	var marks: Array = _panel_marks[index]
	if marks.is_empty():
		return
	var clusters: Array = _panel_clusters.get(_panel_key(index), [])
	var wanted: int = mini(DAMAGE_CRACK_COUNT[state], clusters.size())
	var branches: int = DAMAGE_BRANCH_COUNT[state]
	# A scuff at the heaviest wound, below the first damage state: the chip and
	# its lip, scaled by how worn the panel canonically is, and no crack.
	var scuff := 0.0
	if state == 0 and wear >= DAMAGE_WEAR_FLOOR and not clusters.is_empty():
		wanted = 1
		scuff = DAMAGE_WEAR_CHIP_SCALE * sqrt(clampf(wear, 0.0, 1.0))
	var broken_at: float = _panel_break_time[index]
	var breaking := broken_at >= 0.0 and t >= broken_at - BREAK_STRESS_SECONDS
	if broken_at >= 0.0 and t >= broken_at:
		wanted = 0
	# The seams this panel shows in this state, by the wound they start from.
	var seams := {}
	var seam_rows: Dictionary = _panel_seams.get(_panel_key(index), {})
	if seam_rows.has(state) and wanted > 0:
		for row in seam_rows[state]:
			seams[int(row[0])] = row
	var material: StandardMaterial3D = _panel_mark_material[index]
	var colour := CRACK_RGB
	if state >= 3:
		colour = FRACTURE_RGB
	elif state == 2:
		colour = CRITICAL_RGB
	material.albedo_color = colour
	material.emission = colour
	var energy: float = DAMAGE_EMISSION_ENERGY[state]
	if breaking and broken_at >= 0.0 and t < broken_at:
		# The wall is seen to give before it goes: the crack network it
		# already has flares over the last seventh of a second rather than a
		# new effect appearing out of nowhere at the break.
		var u := clampf((t - (broken_at - BREAK_STRESS_SECONDS))
			/ BREAK_STRESS_SECONDS, 0.0, 1.0)
		energy = lerpf(energy, 9.0, u * u)
	material.emission_energy_multiplier = energy

	var wounds: int = marks.size() / MARK_PARTS
	for wound in wounds:
		var shown: bool = wound < wanted
		var cluster: Array = clusters[wound] if wound < clusters.size() else []
		var offset: float = float(cluster[0]) if not cluster.is_empty() else 0.0
		var growth: float = float(cluster[4]) if not cluster.is_empty() else 1.0
		var tilt_sign: float = float(cluster[3]) if not cluster.is_empty() else 1.0
		var chip_width: float = DAMAGE_MARK_CHORD * growth
		var limit := maxf(0.0, 0.5 * chord - 0.5 * chip_width)
		offset = clampf(offset, -limit, limit)
		var here := Vector3(centre.x + along.x * offset,
			centre.y + along.y * offset, 0.0)
		for part in MARK_PARTS:
			var node: MeshInstance3D = marks[wound * MARK_PARTS + part]
			if node == null:
				continue
			var draw := shown
			if part == MARK_PART_CRACK:
				draw = shown and scuff <= 0.0
			elif part == MARK_PART_BRANCH_A:
				draw = shown and scuff <= 0.0 and branches >= 1
			elif part == MARK_PART_BRANCH_B:
				draw = shown and scuff <= 0.0 and branches >= 2
			elif part == MARK_PART_SEAM:
				draw = shown and scuff <= 0.0 and seams.has(wound)
			if not draw:
				node.visible = false
				continue
			node.visible = true
			if part == MARK_PART_CHIP or part == MARK_PART_RIM:
				# The chip grows with the wound, which is the whole of
				# "repeated impacts build on one another", and its lip grows
				# with it so the hole stays a hole. Below the first damage
				# state both are scaled down to a scuff instead.
				#
				# Built with `_oriented_basis` rather than `Basis.scaled`:
				# `scaled` multiplies the basis *rows*, which are the global
				# axes, so it stretches a diagonal panel's chip along world X
				# instead of along its own chord. The panel slabs already
				# avoid it for the same reason.
				var chip_scale: float = growth if scuff <= 0.0 else scuff
				var chip_thick: float = 1.0 if scuff <= 0.0 else scuff
				# The lip sits a hair deeper than the chip so the chip's own
				# box wins the middle of it and only the ring survives.
				var z: float = MARK_Z - 0.275 * depth
				if part == MARK_PART_RIM:
					z -= 0.020 * depth
				node.transform = Transform3D(
					_oriented_basis(along, chip_scale, chip_thick),
					here + Vector3(0.0, 0.0, z))
				continue
			if part == MARK_PART_SEAM:
				# A fissure along the chord between this wound and the next.
				# Both endpoints are canonical impact offsets, so the network
				# is as tied to where the ball hit as the wounds are.
				var row: Array = seams[wound]
				var seam_centre: float = clampf(float(row[1]),
					-0.5 * chord, 0.5 * chord)
				var seam_length: float = float(row[2])
				node.transform = Transform3D(
					_oriented_basis(along, seam_length, 1.0),
					Vector3(centre.x + along.x * seam_centre,
						centre.y + along.y * seam_centre,
						MARK_Z - 0.30 * depth))
				continue
			# The crack and its branches lean out of the chip. The roll is
			# about the panel's own normal, so a rotated crack stays inside the
			# panel's radial thickness - see DAMAGE_CRACK_SPAN.
			var tilt: float = deg_to_rad(DAMAGE_CRACK_TILT_DEGREES) * tilt_sign
			var slide := 0.0
			if part >= MARK_PART_BRANCH_A:
				var side: float = 1.0 if part == MARK_PART_BRANCH_A else -1.0
				tilt += deg_to_rad(DAMAGE_BRANCH_SPREAD_DEGREES) * side * tilt_sign
				slide = 0.30 * chip_width * side
			var rolled := _rolled_basis(basis, tilt)
			node.transform = Transform3D(rolled,
				here + Vector3(along.x * slide, along.y * slide,
					MARK_Z - (0.40 if part == MARK_PART_CRACK else 0.22) * depth))


func _rolled_basis(basis: Basis, tilt: float) -> Basis:
	## Roll about the panel's own outward normal - the basis's third column -
	## so the crack turns in the plane of the wall and never tips out of it.
	return basis.rotated(basis.z.normalized(), tilt)


func _panel_key(index: int) -> String:
	return "%d:%d" % [_panel_shell[index], _panel_slot[index]]


func _apply_balls(render_t: float) -> void:
	var sim_t := minf(render_t, _duration)
	var escapee: int = int(_escape.get("ball_id", -1))
	for row in _ball_ids.size():
		var born: float = _ball_birth[row]
		var core: MeshInstance3D = _ball_core[row]
		var rim: MeshInstance3D = _ball_rim[row]
		var halo: MeshInstance3D = _ball_halo[row]
		var trail: Array = _ball_trail[row]
		if born > sim_t:
			core.visible = false
			rim.visible = false
			halo.visible = false
			for piece in trail:
				piece.visible = false
			continue

		# Only the escapee runs on past the document's end.
		var own_t := sim_t
		if _ball_ids[row] == escapee:
			own_t = _escapee_time()
		var point := _position_row(row, own_t)

		# A child fades in from 1.6x over its first 0.10 s, so a spawn is a
		# thing that arrives rather than a thing that is suddenly there.
		var age := own_t - born
		var birth_scale := 1.0
		if born > 0.0 and age < 0.10:
			birth_scale = lerpf(1.60, 1.0, clampf(age / 0.10, 0.0, 1.0))

		core.visible = true
		core.transform = Transform3D(
			Basis.IDENTITY.scaled(Vector3.ONE * birth_scale),
			Vector3(point.x, point.y, 0.0))
		rim.visible = true
		rim.transform = Transform3D(
			Basis.IDENTITY.scaled(Vector3.ONE * birth_scale),
			Vector3(point.x, point.y, BALL_RIM_Z))

		var flare := 1.0
		if _ball_ids[row] == escapee and _escape.has("t") \
				and render_t >= float(_escape["t"]):
			flare = 1.0 + 2.0 * (1.0 - clampf(
				(render_t - float(_escape["t"])) / ESCAPE_FLARE_SECONDS, 0.0, 1.0))
		halo.visible = true
		halo.transform = Transform3D(
			Basis.IDENTITY.scaled(Vector3.ONE * birth_scale * flare),
			Vector3(point.x, point.y, HALO_Z))
		var halo_material: StandardMaterial3D = _ball_halo_material[row]
		halo_material.albedo_color = Color(_ball_colour[row],
			clampf(0.55 * _ball_energy[row] * flare, 0.0, 1.0))

		_apply_trail(row, own_t, point)


func _apply_trail(row: int, t: float, head: Vector2) -> void:
	## Sampled backwards along the canonical path, so it bends at a wall
	## instead of drawing through one. It is a time window, so it looks
	## identical at any frame rate.
	var trail: Array = _ball_trail[row]
	var born: float = _ball_birth[row]
	var previous := head
	var radius := float(playback["config"]["ball_radius"]) * BALL_DRAW_SCALE
	for index in trail.size():
		var piece: MeshInstance3D = trail[index]
		var at := t - TRAIL_SECONDS * float(index + 1) / float(TRAIL_SAMPLES - 1)
		if at < born:
			piece.visible = false
			continue
		var point := _position_row(row, at)
		var delta := previous - point
		var length := delta.length()
		if length < 1e-6:
			piece.visible = false
			previous = point
			continue
		var fraction := float(index) / float(trail.size())
		var width := lerpf(TRAIL_HEAD_WIDTH, TRAIL_TAIL_WIDTH, fraction) * radius
		var along := delta / length
		piece.visible = true
		piece.transform = Transform3D(
			_oriented_basis(along, length, width),
			Vector3(0.5 * (previous.x + point.x), 0.5 * (previous.y + point.y),
				TRAIL_Z))
		previous = point
	var material: StandardMaterial3D = _ball_trail_material[row]
	material.albedo_color = Color(_ball_colour[row], 0.62)


func _apply_effects(render_t: float) -> void:
	var sim_t := minf(render_t, _duration)
	# Post lighting accumulates with `maxf` over near misses and breaks, so it
	# has to start from nothing each frame or a still would show every post
	# that has ever been lit.
	_reset_posts()

	for index in _spawns.size():
		var spawn: Dictionary = _spawns[index]
		var at := float(spawn["t"])
		var flash: MeshInstance3D = _spawn_flash[index]
		var link: MeshInstance3D = _spawn_link[index]
		var since := sim_t - at
		if since < 0.0 or since > SPAWN_FLASH_SECONDS:
			flash.visible = false
		else:
			var u := since / SPAWN_FLASH_SECONDS
			var point := _position_row(int(_ball_row_of[spawn["ball_id"]]), at)
			flash.visible = true
			flash.transform = Transform3D(
				Basis.IDENTITY.scaled(
					Vector3.ONE * (2.0 * SPAWN_FLASH_RADIUS * (0.25 + 0.75 * u))),
				Vector3(point.x, point.y, EFFECT_Z))
			var material: StandardMaterial3D = _spawn_flash_material[index]
			material.albedo_color = Color(material.albedo_color, 0.85 * (1.0 - u))
		if since < 0.0 or since > SPAWN_LINK_SECONDS:
			link.visible = false
		else:
			var u2 := since / SPAWN_LINK_SECONDS
			var child := _position_row(int(_ball_row_of[spawn["ball_id"]]), sim_t)
			var parent := _position_row(int(_ball_row_of[spawn["parent_id"]]), sim_t)
			var delta := child - parent
			var length := delta.length()
			if length < 1e-6:
				link.visible = false
			else:
				link.visible = true
				link.transform = Transform3D(
					_oriented_basis(delta / length, length,
						0.16 * (1.0 - u2) + 0.04),
					Vector3(0.5 * (child.x + parent.x), 0.5 * (child.y + parent.y),
						EFFECT_Z))
				var link_material: StandardMaterial3D = _spawn_link_material[index]
				link_material.albedo_color = Color(link_material.albedo_color,
					0.9 * (1.0 - u2))

	for index in _near_misses.size():
		var miss: Dictionary = _near_misses[index]
		var spark: MeshInstance3D = _near_miss_spark[index]
		var since := sim_t - float(miss["t"])
		if since < 0.0 or since > NEAR_MISS_SECONDS:
			spark.visible = false
			continue
		var u := since / NEAR_MISS_SECONDS
		# Closer misses spark harder. `arc_separation_ball_radii` is canonical,
		# so the brightness is the physics rather than a flourish.
		var closeness := clampf(1.0 - float(miss["radii"]) / 3.0, 0.15, 1.0)
		var point: Vector2 = miss["position"]
		spark.visible = true
		spark.transform = Transform3D(
			Basis.IDENTITY.scaled(Vector3.ONE * (3.2 * (0.30 + 0.70 * u))),
			Vector3(point.x, point.y, EFFECT_Z))
		var material: StandardMaterial3D = _near_miss_material[index]
		material.albedo_color = Color(1.0, 0.95, 0.86,
			closeness * (1.0 - u) * 0.95)
		_light_post(int(miss["shell_id"]), int(miss["panel_id"]),
			closeness * (1.0 - u) * 5.0)

	var debris_cursor := 0
	for index in _breaks.size():
		var entry: Dictionary = _breaks[index]
		var at := float(entry["t"])
		var since := sim_t - at
		var ring: MeshInstance3D = _break_ring[index]
		var point: Vector2 = entry["position"]
		if since < 0.0 or since > BREAK_RING_SECONDS:
			ring.visible = false
		else:
			var u := since / BREAK_RING_SECONDS
			ring.visible = true
			ring.transform = Transform3D(
				Basis.IDENTITY.scaled(
					Vector3.ONE * (2.0 * BREAK_RING_RADIUS * (0.15 + 0.85 * u))),
				Vector3(point.x, point.y, EFFECT_Z))
			var material: StandardMaterial3D = _break_ring_material[index]
			material.albedo_color = Color(BREAK_FLASH_RGB, 0.9 * (1.0 - u))
		# The chunks. Laid out along the panel's own chord and thrown outward
		# along its normal, so they are its pieces leaving rather than sparks
		# from a point. Presentation only: no fragment has a collider and
		# nothing here is read back by anything.
		var shell_id := int(entry["shell_id"])
		var out_dir := point.normalized() if point.length() > 1e-6 else Vector2.UP
		var along_dir := Vector2(-out_dir.y, out_dir.x)
		var chord := float(playback["shells"][shell_id]["chord_length"])
		for piece in BREAK_FRAGMENT_COUNT:
			var chunk: MeshInstance3D = _fragments[index * BREAK_FRAGMENT_COUNT + piece]
			if since < 0.0 or since > BREAK_FRAGMENT_SECONDS:
				chunk.visible = false
				continue
			var fu := since / BREAK_FRAGMENT_SECONDS
			var share := (float(piece) + 0.5) / float(BREAK_FRAGMENT_COUNT) - 0.5
			var out_speed: float = BREAK_FRAGMENT_OUT_SPEED \
				* (0.70 + 0.30 * absf(share) * 2.0)
			var along_speed: float = BREAK_FRAGMENT_OUT_SPEED * share * 1.10
			var travel := out_dir * out_speed * since \
				+ along_dir * (chord * share + along_speed * since)
			var spin: float = deg_to_rad(BREAK_FRAGMENT_SPIN_DEGREES) \
				* (1.0 if piece % 2 == 0 else -1.0) * since
			chunk.visible = true
			chunk.transform = Transform3D(
				_oriented_basis(along_dir, 1.0, 1.0).rotated(
					Vector3(out_dir.x, out_dir.y, 0.0), spin),
				Vector3(point.x + travel.x, point.y + travel.y,
					-0.25 * float(panel_depth[shell_id]) - 2.0 * since))
		var fragment_material: StandardMaterial3D = _fragment_material[index]
		if since >= 0.0 and since <= BREAK_FRAGMENT_SECONDS:
			# Gone quickly: the scene already holds up to eighteen balls and
			# the brief is explicit that fragments may not become clutter.
			fragment_material.albedo_color = Color(
				PANEL_RGB * float(SHELL_ALBEDO_VALUE[shell_id]) * 0.82,
				clampf(1.6 * (1.0 - since / BREAK_FRAGMENT_SECONDS), 0.0, 1.0))

		# Deterministic sparks: the direction comes from a hash of the panel's
		# own identity, so two renders of one seed throw the same debris.
		var seed_value := int(entry["shell_id"]) * 1009 + int(entry["panel_id"]) * 97
		for k in BREAK_DEBRIS_COUNT:
			var spark: MeshInstance3D = _debris[debris_cursor]
			debris_cursor += 1
			if since < 0.0 or since > BREAK_DEBRIS_SECONDS:
				spark.visible = false
				continue
			var u := since / BREAK_DEBRIS_SECONDS
			var hashed := float((seed_value + k * 7919) % 6271) / 6271.0
			var angle := TAU * hashed
			var speed := BREAK_DEBRIS_SPEED + BREAK_DEBRIS_SPEED_SPREAD \
				* float((seed_value + k * 104729) % 977) / 977.0
			spark.visible = true
			spark.transform = Transform3D(
				Basis.IDENTITY.scaled(
					Vector3.ONE * (BREAK_DEBRIS_SIZE * (1.0 - 0.55 * u))),
				Vector3(point.x + cos(angle) * speed * since * (1.0 - 0.5 * u),
					point.y + sin(angle) * speed * since * (1.0 - 0.5 * u),
					EFFECT_Z))
		var debris_material: StandardMaterial3D = _debris_material[index]
		if since >= 0.0 and since <= BREAK_DEBRIS_SECONDS:
			debris_material.albedo_color = Color(CRACK_RGB,
				0.95 * (1.0 - since / BREAK_DEBRIS_SECONDS))
		# The arena remembers: the two posts either side of a broken panel keep
		# a warm cast for the rest of the run, so a viewer reading the outer
		# shell late can see where it has been worn through.
		if since >= 0.0:
			_light_post(int(entry["shell_id"]), int(entry["panel_id"]),
				1.6 if since > 0.8 else lerpf(7.0, 1.6, since / 0.8))

	# **Break, hole, ball through hole.** When a ball uses a passage soon after
	# it opened, the passage itself answers for half a second - its two
	# flanking pillars, nothing global. No screen shake and no flash, because
	# the satisfaction is meant to be the sequence.
	#
	# The brief asks for the stronger version, several balls pouring through at
	# once, and no candidate has one: every shell rotates, so a broken slot is
	# a gap sweeping past the population rather than a door. This is the tier
	# that does fire - twice per run - and on 1176 the second one is the
	# winning escape through the final wall.
	for use in _passage_uses:
		var since := sim_t - float(use["t"])
		if since < 0.0 or since > FLOOD_RESPONSE_SECONDS:
			continue
		var fade := 1.0 - since / FLOOD_RESPONSE_SECONDS
		_light_post(int(use["shell_id"]), int(use["panel_id"]),
			FLOOD_POST_ENERGY * fade * fade)

	if _escape.has("t"):
		var since := render_t - float(_escape["t"])
		if since < 0.0 or since > ESCAPE_RING_SECONDS:
			_escape_ring.visible = false
		else:
			var u := since / ESCAPE_RING_SECONDS
			var point: Vector2 = _escape["position"]
			var outer := float(playback["shells"][-1]["radius"])
			_escape_ring.visible = true
			_escape_ring.transform = Transform3D(
				Basis.IDENTITY.scaled(Vector3.ONE * (outer * 2.4 * (0.05 + 0.95 * u))),
				Vector3(point.x, point.y, EFFECT_Z))
			_escape_ring_material.albedo_color = Color(1.0, 0.97, 0.90,
				0.55 * (1.0 - u))


func _light_post(shell_id: int, panel_id: int, energy: float) -> void:
	## A panel's two flanking pillars are its own capsule caps, so lighting
	## them is lighting the thing the ball actually clipped or broke through.
	if shell_id < 0 or shell_id >= _post_index.size():
		return
	var row: Dictionary = _post_index[shell_id]
	var count := int(playback["shells"][shell_id]["panel_count"])
	for vertex in [panel_id % count, (panel_id + 1) % count]:
		if not row.has(vertex):
			continue
		var index := int(row[vertex])
		var material: StandardMaterial3D = _post_materials[index]
		if energy <= _post_base_energy(index):
			continue
		material.emission = POST_HOT_RGB
		material.emission_energy_multiplier = maxf(
			material.emission_energy_multiplier, energy)


func _post_base_energy(index: int) -> float:
	return POST_EDGE_ENERGY if bool(_post_edge[index]) else POST_BASE_ENERGY


func _reset_posts() -> void:
	## Back to the pillar's *resting* glow, not to nothing. The first version
	## reset to zero, which switched off the cool caps on every opening-edge
	## pillar on the first frame and left the openings unmarked for the whole
	## run - the one feature the composition most needs to read.
	for index in _post_materials.size():
		var material: StandardMaterial3D = _post_materials[index]
		material.emission = POST_EDGE_RGB if bool(_post_edge[index]) else FACE_RGB
		material.emission_energy_multiplier = _post_base_energy(index)


# --------------------------------------------------------------------------
# Audit
# --------------------------------------------------------------------------


func audit_state() -> Dictionary:
	## What the scene computed this frame, for Python to diff against the
	## document. Doubles throughout: a Godot `Vector2` is 32-bit and reporting
	## through one costs a hundred times the audit tolerance.
	var balls := []
	for row in _ball_ids.size():
		if _ball_birth[row] > _time:
			continue
		var pair := _position_pair(row, _time)
		balls.append({
			"ball_id": int(_ball_ids[row]),
			"x": float(pair[0]),
			"y": float(pair[1]),
		})
	var states := []
	for index in _panel_materials.size():
		states.append({
			"shell_id": int(_panel_shell[index]),
			"panel_id": int(_panel_slot[index]),
			"state": DAMAGE_STATES_ORDER[_panel_state_at(index, _time)],
		})
	var projected_centres := []
	var centre_max_error := 0.0
	for depth in panel_depth:
		var pixel := _camera.unproject_position(Vector3(0.0, 0.0, -0.5 * float(depth)))
		projected_centres.append([float(pixel.x), float(pixel.y)])
	for a in projected_centres:
		for b in projected_centres:
			centre_max_error = maxf(centre_max_error, Vector2(
				float(a[0]) - float(b[0]), float(a[1]) - float(b[1])).length())
	# The wounds the scene built, so Python can diff them against its own
	# derivation rather than against a second copy of the same rule. This is
	# the check the 1.778x frustum error would have failed in Phase 2A.
	var wounds := []
	for key in _panel_clusters:
		var row: Array = _panel_clusters[key]
		var parts: PackedStringArray = str(key).split(":")
		for cluster in row:
			wounds.append({
				"shell_id": int(parts[0]),
				"panel_id": int(parts[1]),
				"offset": float(cluster[0]),
				"weight": int(cluster[1]),
				"index": int(cluster[2]),
				"tilt_sign": int(cluster[3]),
				"growth": float(cluster[4]),
			})
	wounds.sort_custom(func(a, b):
		if a["shell_id"] != b["shell_id"]:
			return a["shell_id"] < b["shell_id"]
		if a["panel_id"] != b["panel_id"]:
			return a["panel_id"] < b["panel_id"]
		return a["index"] < b["index"])
	# The wear the scene is drawing with, so Python can diff it against its own
	# read of the same `damage` stream rather than trusting that both read it
	# the same way.
	var wear_rows := []
	for key in _panel_wear:
		var parts: PackedStringArray = str(key).split(":")
		var shell_id := int(parts[0])
		var panel_id := int(parts[1])
		if shell_id >= _panel_index.size():
			continue
		var row: Dictionary = _panel_index[shell_id]
		if not row.has(panel_id):
			continue
		wear_rows.append({
			"shell_id": shell_id,
			"panel_id": panel_id,
			"wear": _wear_at(int(row[panel_id]), _time),
		})
	wear_rows.sort_custom(func(a, b):
		if a["shell_id"] != b["shell_id"]:
			return a["shell_id"] < b["shell_id"]
		return a["panel_id"] < b["panel_id"])
	var passages := []
	for use in _passage_uses:
		passages.append({
			"t": float(use["t"]),
			"shell_id": int(use["shell_id"]),
			"panel_id": int(use["panel_id"]),
			"ball_id": int(use["ball_id"]),
		})
	var stage_rows := []
	for stage in _camera_stages():
		stage_rows.append({
			"stage": int(stage[0]),
			"extent_shell": int(stage[1]),
			"start": float(stage[2]),
			"settled": float(stage[3]),
			"radius": float(stage[4]),
		})
	return {
		"t": float(_time),
		"render_t": float(_render_time),
		"view_radius": float(_view_radius),
		"pixels_per_unit": float(_pixels_per_unit),
		"population": population_at(_time),
		"balls": balls,
		"panels": states,
		"projected_shell_centres": projected_centres,
		"centre_max_error_px": centre_max_error,
		"camera_stage": camera_stage_at(_time),
		"camera_stages": stage_rows,
		"wounds": wounds,
		"wear": wear_rows,
		"passage_uses": passages,
		"hook_visible": _hook_label != null and _hook_label.visible,
		"winner_visible": _winner_label != null and _winner_label.visible,
		"winner_top": (_winner_label.offset_top / float(_height)
			if _winner_label != null else -1.0),
	}
