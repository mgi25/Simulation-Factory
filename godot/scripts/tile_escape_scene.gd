extends Node3D

## Category 3, Test #1 — HIT EVERY TILE TO ESCAPE. The presentation layer.
##
## **This scene has no physics.** It loads a playback document written by
## `satisfying.tile_playback` and evaluates it. There is no `RigidBody`, no
## `move_and_slide`, no integration and no `delta` anywhere in this file: the
## ball's position at time `t` is `p + v*dt - 0.5*g*dt^2` on the flight that
## was already in progress at `t`, which is a closed form the Python solver
## computed the coefficients for. Two consequences, and they are the reason the
## scene is written this way:
##
## * **The frame rate cannot change the run.** Render at 24, 30, 60 or 1000 fps
##   and each frame samples the same curve at a different instant. There is no
##   accumulated error to differ.
## * **A rendering bug cannot become a physics bug.** The worst this file can do
##   is draw the right run wrongly, which a still will show.
##
## `tile_escape_render.gd` drives it, and an `--audit=1` pass makes the claim
## checkable rather than merely stated: the scene records the frame on which it
## first drew each tile lit and the ball position it computed, and Python
## compares both against the canonical document.
##
## ## Why 3D with an orthographic camera, and not 2D
##
## The brief rules out the reference channel's thin concentric rings and asks
## for "slight physical depth". A `Line2D` cannot have depth; an extruded 3D
## tile can. But a perspective camera would make the projection non-linear, and
## then "the arena occupies 86% of the frame width" stops being a number Python
## can predict and check.
##
## So: orthographic, straight down -Z, `KEEP_WIDTH`. World-to-pixel is then an
## exact scalar, `viewport_width / camera.size`, and
## `satisfying.tile_readability` predicts every pixel measurement from the
## playback document alone. The depth comes from the tile mesh instead - each
## tile is a **chamfered slab**, a large back rectangle and a smaller front one
## joined by four sloped rim faces. Straight-on orthographic sees all four rims,
## a directional light gives each a different shade, and the tile reads as a
## raised physical block rather than as a painted line. A plain `BoxMesh` would
## not: its sides are exactly parallel to the view direction and invisible.
##
## ## Inactive against activated
##
## The one thing that must survive a phone screen, motion, and 50 of 51 tiles
## lit. Three separate channels carry it, so losing one still leaves two:
##
## 1. **Luminance.** Inactive tiles are near the background; activated ones are
##    bright. Measured, not asserted - `tile_readability.still_report` reads the
##    rendered PNG back.
## 2. **Hue.** Inactive is cold slate, activated is amber. Opposite sides of the
##    wheel, so the difference survives a greyscale or colour-blind check.
## 3. **Emission and glow.** An activated tile emits and blooms; an inactive one
##    is lit only by the scene. That is the channel that reads at thumbnail size
##    when the tile is four pixels tall.
##
## ## Hit feedback, and the duplicate problem
##
## A new activation pulses hard: emission spikes and the slab recoils outward,
## decaying over `NEW_HIT_PULSE_SECONDS`. A repeat hit on an already-lit tile
## gets a **different and much smaller** response - a brief brightness tap, no
## recoil at all, `DUP_HIT_PULSE_SCALE` of the magnitude and a third of the
## duration. The brief asks that a duplicate not falsely imply progress, and
## with roughly two duplicates per activation at this operating point a
## duplicate that looked like an activation would make the progress reading
## noise. The two responses are deliberately different in *kind* (brightness
## only, against brightness plus motion) and not merely in degree.

const HOOK_DEFAULT := "HIT EVERY TILE TO ESCAPE"

# --- Composition -----------------------------------------------------------
# The arena's width as a fraction of the frame's. A 17-gon is nearly circular,
# so in a 9:16 frame it occupies a square band across the middle and leaves
# about a quarter of the height clear above and below - which is where the hook
# and the counter go. 0.86 rather than the Phase 1 renderer's 0.88 because the
# chamfered slab is thicker than a drawn line and needs the extra margin.
const ARENA_WIDTH_FRACTION := 0.86
const HOOK_TOP_FRACTION := 0.075
const COUNTER_TOP_FRACTION := 0.815
const DEBUG_TOP_FRACTION := 0.905
const SAFE_MARGIN_FRACTION := 0.05

# --- Tile geometry, in simulation world units ------------------------------
const TILE_RADIAL_THICKNESS := 0.62
const TILE_DEPTH := 0.55
const TILE_CHAMFER := 0.13
# The drawn gap at each end of a tile, as a fraction of its length. Cosmetic:
# the physics uses the whole segment, and a ball landing in a drawn gap
# activates the tile it geometrically hit. Named here, and not on the config,
# because it is the one place in Category 3 where what is drawn is not exactly
# what is simulated.
const TILE_GAP_FRACTION := 0.075

# --- Ball ------------------------------------------------------------------
# The ball is drawn larger than the collision radius. At 85 wu/s in a
# circumradius-10 arena the physical ball is 0.9 wu across and reads as 42 px
# in a 1080-wide frame - small enough to lose against a lit wall. The drawn
# radius is a presentation constant and the *collision* radius stays the
# config's, so nothing about the trajectory changes.
const BALL_DRAW_SCALE := 1.45
const BALL_DEPTH := 0.9

# --- Motion treatment ------------------------------------------------------
# The trail is a time window, not a frame count, so it looks the same at every
# frame rate - which is the whole reason a 30 fps render and a 60 fps one can
# be compared at all.
#
# The length was chosen against a measurement, not a preference. At 85 wu/s and
# 46.44 px/wu the ball travels 131.6 px between two frames at 30 fps and 65.8 px
# at 60, while its drawn diameter is only 60.6 px: consecutive frames do not
# overlap and the ball strobes. A trail closes that gap only if the streak it
# draws is longer than the step. Four lengths were rendered and compared in
# `output/category3_v3/trail/`:
#
#   0.00 s (none)   no direction cue at all, and a visible strobe
#   0.05 s / 197 px covers the 30 fps step nominally, but the trail fades
#                   quadratically, so the *visible* streak is about 130 px and
#                   only just reaches the previous frame's ball
#   0.09 s / 355 px a clean streak; visible length ~230 px, comfortably over
#                   the 30 fps step and 3.5x the 60 fps one
#   0.14 s / 553 px a comet that crosses half the arena and competes with the
#                   tiles for attention
#
# 0.09 s, therefore. `tile_readability.strobe_report` measures the result on
# the rendered frames rather than trusting this arithmetic.
const TRAIL_SECONDS := 0.09
# Samples are spaced so that consecutive ones overlap: at 85 wu/s the ball
# covers 7.65 wu in the trail window, and 34 samples put them 0.22 wu apart
# against a drawn ball radius of 0.65 wu. Overlap is what makes the trail a
# streak rather than a dotted line.
const TRAIL_SAMPLES := 34
const TRAIL_HEAD_WIDTH := 0.95
const TRAIL_TAIL_WIDTH := 0.20
const HALO_SCALE := 2.4

# --- Feedback timing -------------------------------------------------------
const NEW_HIT_PULSE_SECONDS := 0.30
const NEW_HIT_PUSH := 0.30
const DUP_HIT_PULSE_SECONDS := 0.10
const DUP_HIT_PULSE_SCALE := 0.22
const COMPLETION_PULSE_SECONDS := 0.9
const COMPLETION_HOLD_SECONDS := 2.0

# --- The ending ------------------------------------------------------------
# Beat 1. The final tile's response, against a normal activation's 0.30 s /
# 2.6 energy / 0.30 push. Three times the recoil and four times the peak
# energy, held twice as long: the brief asks that "that was the last one" be
# unmistakable, and a difference of degree at these magnitudes reads as a
# difference in kind.
const FINAL_HIT_SECONDS := 0.55
const FINAL_HIT_ENERGY := 11.0
const FINAL_HIT_PUSH := 0.92
# The shock ring leaves the contact point and crosses half the arena. Its
# radius is in world units, so it is the same size relative to the arena at
# every output resolution.
#
# **A scaled ring thickens as it grows**, which is not obvious until it is on
# screen: the mesh is built at radius 1.0 and animated with a uniform scale, so
# a 0.42 wu rim at radius 13 is a 5.5 wu band - a khaki donut wider than the
# frame that buried the arena, the ball and the wave under it. The rim is built
# thin enough that it is still a line at full extent: 0.085 * 6.0 = 0.51 wu,
# which is 24 px at delivery size and about a third of a tile.
const SHOCK_RING_SECONDS := 0.55
const SHOCK_RING_START_RADIUS := 0.9
const SHOCK_RING_RADIUS := 6.0
const SHOCK_RING_SEGMENTS := 72
const SHOCK_RING_WIDTH := 0.085
const SHOCK_RING_ALPHA := 0.55

# Beat 2. Each tile's own flare as the wave front passes it. Shorter than an
# activation pulse, because fifty-one of them overlapping at activation length
# would be one long flash rather than a wave.
const RIPPLE_TILE_SECONDS := 0.30
const RIPPLE_ENERGY := 3.4
const RIPPLE_PUSH := 0.20

# Beat 3. The gate flares in a different hue before it moves, so the section is
# identified as a section before it is seen to open; then it retracts outward
# and shrinks away.
#
# There is deliberately **no glow behind the opening**. One was built - a bar of
# light on the wall line, spanning the gate arc - on the theory that a phone
# frame needs the doorway marked. The render says otherwise: nine missing tiles
# in a ring of fifty-one read as an opening at 270 px without help, and the bar
# read as a lens flare parked outside the arena, still sitting there through the
# closing hold. The cyan flare on the tiles themselves does the whole job.
const GATE_FLARE_LEAD_SECONDS := 0.16
const GATE_FLARE_ENERGY := 6.5
const GATE_RETRACT_WU := 3.1

# Beat 5. The hook steps back so the escape owns the frame.
const HOOK_CLIMAX_ALPHA := 0.34

# --- Colour ----------------------------------------------------------------
const BACKGROUND := Color(0.027, 0.031, 0.047)
const FLOOR_COLOUR := Color(0.043, 0.050, 0.070)
const TILE_INACTIVE := Color(0.105, 0.125, 0.170)
const TILE_INACTIVE_EMISSION := Color(0.035, 0.048, 0.075)
const TILE_ACTIVE := Color(1.0, 0.560, 0.180)
const TILE_ACTIVE_EMISSION := Color(1.0, 0.470, 0.110)
const TILE_COMPLETE_EMISSION := Color(1.0, 0.760, 0.330)
# The last tile goes white, not brighter amber: a hue nothing else in the frame
# has ever used, so the eye cannot mistake it for a very good ordinary hit.
const TILE_FINAL_EMISSION := Color(1.0, 0.960, 0.880)
const SHOCK_RING_COLOUR := Color(1.0, 0.88, 0.62)
# The gate announces itself in cyan - the opposite end of the wheel from the
# amber the whole arena is lit in, and the same family as the ball and its
# trail, which is the association the shot wants: this is where the ball goes.
const GATE_EMISSION := Color(0.45, 0.88, 1.0)
const BALL_COLOUR := Color(1.0, 1.0, 1.0)
const TRAIL_COLOUR := Color(0.45, 0.78, 1.0)
const TEXT_PRIMARY := Color(0.925, 0.941, 0.972)
const TEXT_DIM := Color(0.47, 0.51, 0.59)

var playback: Dictionary = {}
var hook_text := HOOK_DEFAULT
var trail_mode := "temporal"
## The trail window, in seconds. Settable so the render driver can put two
## lengths side by side; `TRAIL_SECONDS` is the default and the reason for it.
var trail_seconds := TRAIL_SECONDS
var show_counter := true
var show_debug := false
## Play the Phase 4 ending. Off by default so every Phase 3 render, still and
## audit reproduces exactly as it did: with this false the scene is the Phase 3
## scene, line for line.
var climax_enabled := false

var _width := 1080
var _height := 1920
var _camera: Camera3D
var _tiles: Array[MeshInstance3D] = []
var _tile_materials: Array[StandardMaterial3D] = []
var _tile_home: Array[Vector3] = []
var _tile_normal: Array[Vector3] = []
var _ball: MeshInstance3D
var _halo: MeshInstance3D
var _trail: Array[MeshInstance3D] = []
var _trail_material: StandardMaterial3D
var _gradient: GradientTexture2D
var _hook_label: Label
var _counter_label: Label
var _debug_label: Label

var _flight_times: PackedFloat64Array = PackedFloat64Array()
var _activation_times: PackedFloat64Array = PackedFloat64Array()
var _last_new_hit: PackedFloat64Array = PackedFloat64Array()
var _last_dup_hit: PackedFloat64Array = PackedFloat64Array()
var _gravity := 0.0
var _total_tiles := 0
var _completion := -1.0
var _end_seconds := 0.0
var _pixels_per_unit := 1.0
var _time := 0.0

# --- The ending, all read from the document's `completion` block ------------
var _has_completion := false
var _climax := false
var _timeline: Array = []
var _final_tile := -1
var _final_seconds := 0.0
var _final_contact := Vector2.ZERO
var _ripple_phase: PackedFloat64Array = PackedFloat64Array()
var _is_gate: PackedByteArray = PackedByteArray()
var _escape_t := 0.0
var _escape_p := Vector2.ZERO
var _escape_v := Vector2.ZERO
var _confirm_seconds := 0.0
var _gate_open_at := 0.0
var _gate_open_seconds := 0.0
var _release_at := 0.0
var _total_render_seconds := 0.0
var _shock_ring: MeshInstance3D
var _shock_material: StandardMaterial3D


func configure(document: Dictionary, width: int, height: int) -> void:
	playback = document
	_width = width
	_height = height
	_gravity = float(document["config"]["gravity"])
	_total_tiles = int(document["total_tiles"])
	_completion = -1.0
	_end_seconds = float(document["end_seconds"])
	if document.get("completion_seconds") != null:
		_completion = float(document["completion_seconds"])

	_flight_times = PackedFloat64Array()
	for flight in document["flights"]:
		_flight_times.append(float(flight["t"]))
	_activation_times = PackedFloat64Array()
	for entry in document["activations"]:
		_activation_times.append(float(entry["t"]))

	_last_new_hit = PackedFloat64Array()
	_last_dup_hit = PackedFloat64Array()
	for _i in _total_tiles:
		_last_new_hit.append(-1.0e9)
		_last_dup_hit.append(-1.0e9)

	_read_completion(document)
	_build()


func _read_completion(document: Dictionary) -> void:
	## Parse the `completion` block, or leave the scene in its Phase 3 state.
	##
	## Every number the ending uses comes from here. The scene never computes a
	## gate side, an escape flight or a beat offset - `satisfying.tile_completion`
	## did, and a renderer that recomputed any of them would be a second opinion
	## about the physics, which is the one thing this architecture forbids.
	_has_completion = false
	_climax = false
	_timeline = []
	_is_gate = PackedByteArray()
	_ripple_phase = PackedFloat64Array()
	for _i in _total_tiles:
		_is_gate.append(0)
		_ripple_phase.append(0.0)
	if not document.has("completion") or document["completion"] == null:
		return
	var block: Dictionary = document["completion"]
	if int(block.get("format", -1)) != 1:
		push_error("tile_escape: completion format %s, this renderer reads 1"
			% block.get("format"))
		return

	_final_tile = int(block["final_tile"])
	_final_seconds = float(block["final_seconds"])
	_final_contact = Vector2(
		float(block["final_contact"][0]), float(block["final_contact"][1]))
	var phases: Array = block["ripple_phase"]
	for i in mini(phases.size(), _total_tiles):
		_ripple_phase[i] = float(phases[i])
	for entry in block["route"]["gate_tiles"]:
		var index := int(entry)
		if index >= 0 and index < _total_tiles:
			_is_gate[index] = 1
	var escape: Dictionary = block["escape"]
	_escape_t = float(escape["t"])
	_escape_p = Vector2(float(escape["p"][0]), float(escape["p"][1]))
	_escape_v = Vector2(float(escape["v"][0]), float(escape["v"][1]))
	var timing: Dictionary = block["timing"]
	_confirm_seconds = float(timing["confirm_seconds"])
	_gate_open_at = float(timing["gate_open_at_seconds"])
	_gate_open_seconds = float(timing["gate_open_seconds"])
	_release_at = float(timing["release_at_seconds"])
	_timeline = block["timeline"]
	_total_render_seconds = float(block["total_render_seconds"])
	_has_completion = true
	_climax = climax_enabled


## The run's own length plus the completion hold. The renderer's clip mode uses
## it so the video is as long as the run was, and no longer.
func playback_duration() -> float:
	var end := float(playback.get("end_seconds", 0.0))
	if _completion >= 0.0:
		end = maxf(end, _completion)
	return end + COMPLETION_HOLD_SECONDS


## How long the video is. With the ending on this is the completion block's own
## total; without it, the Phase 3 run length plus the prototype hold.
func render_duration() -> float:
	if _climax:
		return _total_render_seconds
	return playback_duration()


func has_completion() -> bool:
	return _has_completion


## Simulation time at a render instant, from the document's timeline.
##
## Below the completion this is the identity - the segment is `locked` with
## rate 1.0 - and that is the property the whole ending rests on: turning the
## climax on cannot move one frame of the run that earned it.
func sim_time_at(render_t: float) -> float:
	if not _climax or _timeline.is_empty():
		return render_t
	for segment in _timeline:
		if render_t < float(segment["render_end"]):
			return float(segment["sim_start"]) 				+ (render_t - float(segment["render_start"])) * float(segment["sim_rate"])
	var last: Dictionary = _timeline[_timeline.size() - 1]
	return float(last["sim_start"]) 		+ (float(last["render_end"]) - float(last["render_start"])) * float(last["sim_rate"])


func climax_state_at(render_t: float) -> String:
	if not _climax or _timeline.is_empty():
		return "locked"
	for segment in _timeline:
		if render_t < float(segment["render_end"]):
			return str(segment["state"])
	return str(_timeline[_timeline.size() - 1]["state"])


func world_to_pixel_scale() -> float:
	return _pixels_per_unit


# ---------------------------------------------------------------------------
# Building
# ---------------------------------------------------------------------------


func _build() -> void:
	for child in get_children():
		child.queue_free()
	_tiles.clear()
	_tile_materials.clear()
	_tile_home.clear()
	_tile_normal.clear()
	_trail.clear()

	var arena: Dictionary = playback["arena"]
	var circumradius := float(arena["circumradius"])

	_build_environment()
	_build_camera(circumradius)
	_build_floor(arena)
	_build_tiles(arena)
	_build_ball()
	_build_climax_props()
	_build_overlay()


func _build_climax_props() -> void:
	## The shock ring, built once and hidden unless the ending is playing.
	##
	## Unshaded, additive and with culling disabled, so it cannot fall foul of
	## the winding trap that cost this scene its first two renders - a
	## counter-clockwise ring would simply be invisible, and that is exactly the
	## bug that is hardest to see in a still.
	##
	## It is the only prop. A second one - a bar of light behind the opening -
	## was built and removed; see the note on GATE_FLARE_LEAD_SECONDS.
	if not _has_completion:
		return

	_shock_material = StandardMaterial3D.new()
	_shock_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	_shock_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	_shock_material.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
	_shock_material.cull_mode = BaseMaterial3D.CULL_DISABLED
	_shock_material.albedo_color = SHOCK_RING_COLOUR
	_shock_ring = MeshInstance3D.new()
	_shock_ring.name = "ShockRing"
	_shock_ring.mesh = _annulus_mesh(1.0, SHOCK_RING_WIDTH, SHOCK_RING_SEGMENTS)
	_shock_ring.material_override = _shock_material
	# In front of the tiles and behind the ball, so the ring passes over the
	# arena without ever standing between the viewer and the thing escaping.
	_shock_ring.position = Vector3(_final_contact.x, _final_contact.y, 0.30)
	_shock_ring.visible = false
	add_child(_shock_ring)


func _annulus_mesh(radius: float, width: float, segments: int) -> ArrayMesh:
	## A flat ring in the XY plane, built once and scaled to animate.
	var vertices := PackedVector3Array()
	var indices := PackedInt32Array()
	var inner := maxf(0.01, radius - width * 0.5)
	var outer := radius + width * 0.5
	for k in segments:
		var angle := TAU * float(k) / float(segments)
		vertices.append(Vector3(inner * cos(angle), inner * sin(angle), 0.0))
		vertices.append(Vector3(outer * cos(angle), outer * sin(angle), 0.0))
	for k in segments:
		var a := 2 * k
		var b := 2 * k + 1
		var c := 2 * ((k + 1) % segments)
		var d := 2 * ((k + 1) % segments) + 1
		indices.append_array([a, b, d, a, d, c])
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_INDEX] = indices
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	return mesh


func _build_environment() -> void:
	var world := WorldEnvironment.new()
	var environment := Environment.new()
	environment.background_mode = Environment.BG_COLOR
	environment.background_color = BACKGROUND
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.ambient_light_color = Color(0.32, 0.40, 0.58)
	environment.ambient_light_energy = 0.55
	# Restrained glow, and the reason the activated/inactive difference reads at
	# thumbnail size: an emissive tile blooms a little past its own edge, an
	# inactive one does not bloom at all. The threshold sits above the inactive
	# tile's brightness on purpose, so the bloom is a *signal* and not a haze
	# over the whole frame.
	environment.glow_enabled = true
	environment.glow_intensity = 0.55
	environment.glow_strength = 1.0
	environment.glow_bloom = 0.10
	environment.glow_blend_mode = Environment.GLOW_BLEND_MODE_ADDITIVE
	environment.glow_hdr_threshold = 0.90
	world.environment = environment
	add_child(world)

	# One key from the upper left. Its only job is to shade the four chamfer
	# rims differently from the tile face, which is what makes a slab look
	# raised under an orthographic camera.
	var key := DirectionalLight3D.new()
	key.light_energy = 1.25
	key.light_color = Color(0.86, 0.91, 1.0)
	key.look_at_from_position(Vector3(-6.0, 9.0, 12.0), Vector3.ZERO, Vector3.UP)
	add_child(key)

	var fill := DirectionalLight3D.new()
	fill.light_energy = 0.35
	fill.light_color = Color(0.55, 0.68, 1.0)
	fill.look_at_from_position(Vector3(8.0, -6.0, 9.0), Vector3.ZERO, Vector3.UP)
	add_child(fill)


func _build_camera(circumradius: float) -> void:
	_camera = Camera3D.new()
	_camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	_camera.keep_aspect = Camera3D.KEEP_WIDTH
	# `size` under KEEP_WIDTH is the horizontal extent in world units, so the
	# arena's share of the frame width is exactly ARENA_WIDTH_FRACTION and the
	# pixel scale below is exact rather than fitted.
	_camera.size = (2.0 * circumradius) / ARENA_WIDTH_FRACTION
	_camera.near = 0.05
	_camera.far = 200.0
	# `look_at` needs the node in the tree; `look_at_from_position` does not, and
	# the camera is built before it is parented.
	_camera.look_at_from_position(Vector3(0.0, 0.0, 60.0), Vector3.ZERO, Vector3.UP)
	add_child(_camera)
	_pixels_per_unit = float(_width) / _camera.size


func _build_floor(arena: Dictionary) -> void:
	## The arena interior, one shade above the background. It says "the ball
	## lives in here" in frame one, before any tile has lit.
	var vertices := PackedVector3Array()
	var indices := PackedInt32Array()
	var points: Array = arena["vertices"]
	vertices.append(Vector3.ZERO)
	for point in points:
		vertices.append(Vector3(float(point[0]), float(point[1]), 0.0))
	for k in points.size():
		indices.append(0)
		indices.append(1 + k)
		indices.append(1 + ((k + 1) % points.size()))

	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_INDEX] = indices
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)

	var material := StandardMaterial3D.new()
	material.albedo_color = FLOOR_COLOUR
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	# A single flat unshaded polygon seen from one side. Which way its triangles
	# wind is not information anybody needs, and culling it is one more way for
	# the arena interior to silently vanish.
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	var instance := MeshInstance3D.new()
	instance.name = "Floor"
	instance.mesh = mesh
	instance.material_override = material
	instance.position = Vector3(0.0, 0.0, -0.4)
	add_child(instance)


func _chamfered_slab(length: float, thickness: float, depth: float, chamfer: float) -> ArrayMesh:
	## A slab whose front face is inset on all four sides, joined to the back by
	## four sloped rims.
	##
	## This is the whole reason the camera can stay orthographic. A `BoxMesh`
	## seen straight down its own axis shows one flat rectangle and no depth at
	## all - its side faces are exactly parallel to the view direction. The
	## rims here are not parallel to it, so a directional light gives the top,
	## bottom, left and right rims four different shades and the tile reads as a
	## raised block. Cheap, too: twelve triangles.
	var hl := length * 0.5
	var ht := thickness * 0.5
	var fl := maxf(0.02, hl - chamfer)
	var ft := maxf(0.02, ht - chamfer)

	var vertices := PackedVector3Array([
		Vector3(-hl, -ht, 0.0), Vector3(hl, -ht, 0.0),
		Vector3(hl, ht, 0.0), Vector3(-hl, ht, 0.0),
		Vector3(-fl, -ft, depth), Vector3(fl, -ft, depth),
		Vector3(fl, ft, depth), Vector3(-fl, ft, depth),
	])
	# **Clockwise**, seen from +Z. Godot's front face is the clockwise winding,
	# not the counter-clockwise one a lot of graphics writing assumes, and a
	# counter-clockwise slab is silently culled: the second render of this scene
	# showed the arena floor and not one of its fifty-one tiles.
	var indices := PackedInt32Array([
		6, 5, 4, 7, 6, 4,          # front face
		5, 1, 0, 4, 5, 0,          # bottom rim
		6, 2, 1, 5, 6, 1,          # right rim
		7, 3, 2, 6, 7, 2,          # top rim
		4, 0, 3, 7, 4, 3,          # left rim
	])

	var surface := SurfaceTool.new()
	surface.begin(Mesh.PRIMITIVE_TRIANGLES)
	# Smooth group -1 is flat shading. Averaged normals would blend each rim
	# into the face and into its neighbours, which is exactly the shading
	# difference the chamfer exists to create - a smoothed slab looks like a
	# painted line again.
	surface.set_smooth_group(-1)
	for index in indices:
		surface.add_vertex(vertices[index])
	surface.generate_normals()
	return surface.commit()


func _build_tiles(arena: Dictionary) -> void:
	var container := Node3D.new()
	container.name = "Tiles"
	add_child(container)

	for entry in arena["tiles"]:
		var start := Vector3(float(entry["start"][0]), float(entry["start"][1]), 0.0)
		var end := Vector3(float(entry["end"][0]), float(entry["end"][1]), 0.0)
		var normal := Vector3(
			float(entry["outward_normal"][0]), float(entry["outward_normal"][1]), 0.0)
		var full_length := start.distance_to(end)
		var drawn_length := full_length * (1.0 - 2.0 * TILE_GAP_FRACTION)

		var mesh := _chamfered_slab(
			drawn_length, TILE_RADIAL_THICKNESS, TILE_DEPTH, TILE_CHAMFER)
		var material := StandardMaterial3D.new()
		material.albedo_color = TILE_INACTIVE
		material.emission_enabled = true
		material.emission = TILE_INACTIVE_EMISSION
		material.emission_energy_multiplier = 1.0
		material.roughness = 0.55
		material.metallic = 0.10

		var instance := MeshInstance3D.new()
		instance.name = "Tile%02d" % int(entry["index"])
		instance.mesh = mesh
		instance.material_override = material
		# The slab sits just inside the wall line, centred on the tile, with its
		# long axis along the wall. `basis` is built from the wall direction so
		# a tile is never drawn at an angle the ball did not bounce off.
		var along := (end - start).normalized()
		var home := (start + end) * 0.5 - normal * (TILE_RADIAL_THICKNESS * 0.5)
		# `Basis(along, normal, +Z)` is **mirrored**, and that is not a cosmetic
		# detail: the arena's vertices run counter-clockwise, so for every side
		# `along.cross(normal)` points at -Z and the basis has determinant -1.
		# A mirrored basis reverses every triangle's winding, backface culling
		# then removes the whole slab, and the first render of this scene drew
		# an empty arena with a ball bouncing around inside nothing. Building
		# the second axis as `depth.cross(along)` makes the basis right-handed
		# by construction. The slab is symmetric across that axis, so the shape
		# is unchanged - only its handedness is.
		var depth := Vector3(0.0, 0.0, 1.0)
		instance.transform = Transform3D(
			Basis(along, depth.cross(along), depth), home)
		container.add_child(instance)

		_tiles.append(instance)
		_tile_materials.append(material)
		_tile_home.append(home)
		_tile_normal.append(normal)


func _build_ball() -> void:
	var radius := float(playback["config"]["ball_radius"]) * BALL_DRAW_SCALE

	if trail_mode == "temporal":
		_trail_material = StandardMaterial3D.new()
		_trail_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		_trail_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		_trail_material.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
		_trail_material.albedo_color = TRAIL_COLOUR
		_trail_material.billboard_mode = BaseMaterial3D.BILLBOARD_ENABLED
		_trail_material.vertex_color_use_as_albedo = true
		var container := Node3D.new()
		container.name = "Trail"
		add_child(container)
		for i in TRAIL_SAMPLES:
			var quad := QuadMesh.new()
			quad.size = Vector2(2.0 * radius, 2.0 * radius)
			var node := MeshInstance3D.new()
			node.mesh = quad
			# Each sample owns its material so its alpha can differ; sharing one
			# would make the whole trail a single opacity and defeat the point.
			var sample_material: StandardMaterial3D = _trail_material.duplicate()
			sample_material.albedo_texture = _radial_gradient()
			node.material_override = sample_material
			node.visible = false
			container.add_child(node)
			_trail.append(node)

	if trail_mode != "none":
		var halo_mesh := QuadMesh.new()
		halo_mesh.size = Vector2(radius * 2.0 * HALO_SCALE, radius * 2.0 * HALO_SCALE)
		var halo_material := StandardMaterial3D.new()
		halo_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		halo_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		halo_material.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
		halo_material.albedo_color = Color(0.55, 0.78, 1.0, 0.20)
		halo_material.billboard_mode = BaseMaterial3D.BILLBOARD_ENABLED
		halo_material.albedo_texture = _radial_gradient()
		_halo = MeshInstance3D.new()
		_halo.name = "Halo"
		_halo.mesh = halo_mesh
		_halo.material_override = halo_material
		add_child(_halo)

	var sphere := SphereMesh.new()
	sphere.radius = radius
	sphere.height = radius * 2.0
	sphere.radial_segments = 32
	sphere.rings = 16
	var ball_material := StandardMaterial3D.new()
	ball_material.albedo_color = BALL_COLOUR
	ball_material.emission_enabled = true
	ball_material.emission = Color(0.80, 0.90, 1.0)
	ball_material.emission_energy_multiplier = 1.6
	ball_material.roughness = 0.25
	_ball = MeshInstance3D.new()
	_ball.name = "Ball"
	_ball.mesh = sphere
	_ball.material_override = ball_material
	_ball.position = Vector3(0.0, 0.0, BALL_DEPTH)
	add_child(_ball)


func _radial_gradient() -> GradientTexture2D:
	## Built once and shared. An earlier draft called this from `_apply_ball`,
	## so every frame allocated thirty-four 128x128 gradient textures: a 3,697
	## frame audit made 125,000 of them, ran twenty-eight seconds instead of
	## one, and took the engine down with a stack overflow during shutdown
	## *after* it had written a perfectly good audit file. The texture does not
	## depend on time, so there was never a reason to rebuild it.
	if _gradient != null:
		return _gradient
	var gradient := Gradient.new()
	gradient.set_color(0, Color(1.0, 1.0, 1.0, 1.0))
	gradient.set_color(1, Color(1.0, 1.0, 1.0, 0.0))
	var texture := GradientTexture2D.new()
	texture.gradient = gradient
	texture.fill = GradientTexture2D.FILL_RADIAL
	texture.fill_from = Vector2(0.5, 0.5)
	texture.fill_to = Vector2(1.0, 0.5)
	texture.width = 128
	texture.height = 128
	_gradient = texture
	return texture


func _label(size: int, colour: Color, top: float, letter_spacing: int = 0) -> Label:
	var label := Label.new()
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	label.vertical_alignment = VERTICAL_ALIGNMENT_TOP
	label.add_theme_font_size_override("font_size", size)
	label.add_theme_color_override("font_color", colour)
	if letter_spacing != 0:
		label.add_theme_constant_override("line_spacing", letter_spacing)
	label.set_anchors_preset(Control.PRESET_TOP_WIDE)
	label.offset_top = top
	label.offset_bottom = top + float(size) * 2.2
	# The safe margin keeps text off the edge where a phone's rounded corners
	# and a platform's own UI live.
	label.offset_left = float(_width) * SAFE_MARGIN_FRACTION
	label.offset_right = -float(_width) * SAFE_MARGIN_FRACTION
	return label


func _build_overlay() -> void:
	var layer := CanvasLayer.new()
	layer.name = "Overlay"
	add_child(layer)

	var root := Control.new()
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	layer.add_child(root)

	# The hook sits above the arena, in the band a near-circular arena leaves
	# empty in a 9:16 frame. No background panel: at this size the type is
	# already well clear of the arena's top vertex, and a panel would be the
	# busiest object in a frame whose whole argument is restraint.
	_hook_label = _label(int(float(_height) * 0.0305), TEXT_PRIMARY,
		float(_height) * HOOK_TOP_FRACTION)
	_hook_label.text = hook_text
	root.add_child(_hook_label)

	_counter_label = _label(int(float(_height) * 0.058), TEXT_PRIMARY,
		float(_height) * COUNTER_TOP_FRACTION)
	_counter_label.visible = show_counter
	root.add_child(_counter_label)

	_debug_label = _label(int(float(_height) * 0.019), TEXT_DIM,
		float(_height) * DEBUG_TOP_FRACTION)
	_debug_label.visible = show_debug
	root.add_child(_debug_label)


# ---------------------------------------------------------------------------
# Evaluating the playback. No integration anywhere below this line.
# ---------------------------------------------------------------------------


func _flight_index_at(t: float) -> int:
	var lo := 0
	var hi := _flight_times.size() - 1
	while lo < hi:
		var mid := (lo + hi + 1) / 2
		if _flight_times[mid] <= t:
			lo = mid
		else:
			hi = mid - 1
	return lo


## The ball at time `t`, in **doubles**.
##
## Separate from `position_at` because a `Vector2` stores 32-bit components in
## a standard Godot build, and rounding the playback to float32 costs about
## 5e-7 world units. That is a ten-thousandth of a pixel and nobody could see
## it - but it is also a hundred times the tolerance the playback audit exists
## to enforce, and an audit that had to allow 5e-7 could no longer tell "the
## renderer replayed the document" from "the renderer computed something very
## close to it". GDScript's own `float` is a double, so evaluating here and
## narrowing only at the point of drawing keeps the audit exact.
func position_pair(raw: float) -> Array:
	# Past the run's end the ball is on the escape flight, if the document
	# carries one and the ending is on. That flight is the *same* record the
	# canonical run left in `flights[-1]`, so evaluating it here is the
	# continuation the solver would have produced - the wall it would have hit
	# is simply not there any more.
	if _climax and _has_completion and raw > _end_seconds:
		var dt := raw - _escape_t
		return [
			_escape_p.x + _escape_v.x * dt,
			_escape_p.y + _escape_v.y * dt - 0.5 * _gravity * dt * dt,
		]
	# Otherwise clamped to the run's end, exactly as `tile_playback.position_at`
	# does. The document defines the trajectory on [0, end_seconds]; past that
	# the last flight would carry the ball straight through the wall, and during
	# the completion hold that is several arena widths off frame.
	var t := minf(raw, _end_seconds)
	var flight: Dictionary = playback["flights"][_flight_index_at(t)]
	var dt := maxf(0.0, t - float(flight["t"]))
	var px := float(flight["p"][0])
	var py := float(flight["p"][1])
	var vx := float(flight["v"][0])
	var vy := float(flight["v"][1])
	return [
		px + vx * dt,
		py + vy * dt - 0.5 * _gravity * dt * dt,
	]


func position_at(raw: float) -> Vector2:
	var pair := position_pair(raw)
	return Vector2(pair[0], pair[1])


func activated_count_at(t: float) -> int:
	var lo := 0
	var hi := _activation_times.size()
	while lo < hi:
		var mid := (lo + hi) / 2
		if _activation_times[mid] <= t:
			lo = mid + 1
		else:
			hi = mid
	return lo


## Set the world to simulation time `t`. Every frame of every render goes
## through here and nothing else advances state, which is what makes the
## rendered frame a pure function of `t`.
func set_time(t: float) -> void:
	_time = t
	_apply_hits(t)
	_apply_tiles(t)
	_apply_ball(t)
	_apply_overlay(t)
	if _climax:
		# A still or an audit that addresses the scene in *simulation* time
		# still has to be a complete picture, so the ending is applied at the
		# render instant the timeline maps that simulation time back to. Below
		# the completion that is the identity and this does nothing.
		_apply_climax(_render_time_for(t))


## Set the world to **render** time `r`, which is what a clip of the ending is
## indexed by. Simulation time comes from the document's timeline; everything
## else follows from it.
func set_render_time(r: float) -> void:
	var t := sim_time_at(r)
	_time = t
	_apply_hits(t)
	_apply_tiles(t)
	_apply_ball(t)
	_apply_overlay(t)
	if _climax:
		_apply_climax(r)


func _render_time_for(sim_t: float) -> float:
	## The first render instant that shows simulation time `sim_t`.
	##
	## The inverse of `sim_time_at`, which is only well defined because the
	## timeline is monotonic: every segment has a rate of zero or a positive
	## one, so simulation time never goes backwards and "the first render
	## instant" is the right choice at a hold.
	if not _climax or _timeline.is_empty():
		return sim_t
	for segment in _timeline:
		var rate := float(segment["sim_rate"])
		var sim_start := float(segment["sim_start"])
		var render_start := float(segment["render_start"])
		var render_end := float(segment["render_end"])
		if rate <= 0.0:
			if is_equal_approx(sim_t, sim_start):
				return render_start
			continue
		var reached: float = sim_start + (render_end - render_start) * rate
		if sim_t <= reached:
			return render_start + (sim_t - sim_start) / rate
	return float(_timeline[_timeline.size() - 1]["render_end"])


func _apply_climax(render_t: float) -> void:
	## The ending, as a pure function of render time.
	##
	## Nothing accumulates. Every envelope below is evaluated from `since`, the
	## render seconds elapsed since the fifty-first activation, so a still taken
	## at any instant of the ending is identical whether it was reached by
	## rendering every frame before it or by jumping straight there - the same
	## property the rest of the scene has, and the reason the climax stills and
	## the climax clip cannot disagree.
	var since := render_t - _final_seconds
	if since < 0.0:
		_hide_climax_props()
		return

	var gate_phase := clampf(
		(since - _gate_open_at) / maxf(_gate_open_seconds, 0.001), 0.0, 1.0)
	var gate_flare := 0.0
	var flare_from := _gate_open_at - GATE_FLARE_LEAD_SECONDS
	if since >= flare_from and since < _gate_open_at:
		gate_flare = (since - flare_from) / maxf(GATE_FLARE_LEAD_SECONDS, 0.001)
	elif gate_phase > 0.0:
		gate_flare = 1.0 - gate_phase

	for i in _total_tiles:
		var material := _tile_materials[i]
		var push := 0.0
		var energy := material.emission_energy_multiplier
		var emission := material.emission

		# Beat 2: the wave. `_ripple_phase[i]` is this tile's share of the
		# journey around the ring, so the front reaches it at that fraction of
		# `confirm_seconds` and it then flares on its own short envelope.
		var wave_at := _ripple_phase[i] * _confirm_seconds
		var since_wave := since - wave_at
		if since_wave >= 0.0 and since_wave < RIPPLE_TILE_SECONDS:
			var w := since_wave / RIPPLE_TILE_SECONDS
			var ripple := 1.0 - w * w
			emission = emission.lerp(TILE_COMPLETE_EMISSION, ripple)
			energy += RIPPLE_ENERGY * ripple
			push += RIPPLE_PUSH * ripple

		# Beat 1: the fifty-first tile itself.
		if i == _final_tile and since < FINAL_HIT_SECONDS:
			var f := since / FINAL_HIT_SECONDS
			var flash := (1.0 - f) * (1.0 - f)
			emission = emission.lerp(TILE_FINAL_EMISSION, flash)
			energy += FINAL_HIT_ENERGY * flash
			push += FINAL_HIT_PUSH * flash

		# Beat 3: the gate. It is named in cyan first and only then moves, so
		# the viewer reads "that section" before reading "that section opened".
		if _is_gate[i] == 1:
			if gate_flare > 0.0:
				emission = emission.lerp(GATE_EMISSION, gate_flare)
				energy += GATE_FLARE_ENERGY * gate_flare
			if gate_phase > 0.0:
				# Ease out: the section leaves quickly and settles, which reads
				# as a mechanism opening rather than a tile drifting away.
				var e := 1.0 - (1.0 - gate_phase) * (1.0 - gate_phase)
				push += GATE_RETRACT_WU * e
				energy *= (1.0 - e)
				var shrink := maxf(0.02, 1.0 - e)
				_tiles[i].scale = Vector3(shrink, shrink, shrink)
			else:
				_tiles[i].scale = Vector3.ONE
		material.emission = emission
		material.emission_energy_multiplier = energy
		if push != 0.0:
			# Added to whatever `_apply_tiles` already set this frame, read
			# back along the normal rather than accumulated in a variable: this
			# function runs after that one on every frame and neither of them
			# remembers anything between frames.
			var existing: float = (_tiles[i].position - _tile_home[i]).dot(_tile_normal[i])
			_tiles[i].position = _tile_home[i] + _tile_normal[i] * (existing + push)

	_apply_shock_ring(since)
	if _hook_label != null:
		var fade := clampf((since - _release_at) / 0.35, 0.0, 1.0)
		_hook_label.add_theme_color_override("font_color", Color(
			TEXT_PRIMARY.r, TEXT_PRIMARY.g, TEXT_PRIMARY.b,
			lerpf(1.0, HOOK_CLIMAX_ALPHA, fade)))


func _apply_shock_ring(since: float) -> void:
	if _shock_ring == null:
		return
	if since < 0.0 or since >= SHOCK_RING_SECONDS:
		_shock_ring.visible = false
		return
	var f := since / SHOCK_RING_SECONDS
	# Radius eases out and alpha falls off as the square, so the ring is
	# brightest where it leaves the tile and thins as it crosses the arena
	# rather than arriving at the far wall as a hard line.
	var radius: float = SHOCK_RING_START_RADIUS + (
		SHOCK_RING_RADIUS - SHOCK_RING_START_RADIUS) * (1.0 - (1.0 - f) * (1.0 - f))
	_shock_ring.visible = true
	_shock_ring.scale = Vector3(radius, radius, 1.0)
	_shock_material.albedo_color = Color(
		SHOCK_RING_COLOUR.r, SHOCK_RING_COLOUR.g, SHOCK_RING_COLOUR.b,
		SHOCK_RING_ALPHA * (1.0 - f) * (1.0 - f))


func _hide_climax_props() -> void:
	if _shock_ring != null:
		_shock_ring.visible = false


func _apply_hits(t: float) -> void:
	## The most recent new hit and the most recent duplicate hit on each tile,
	## at or before `t`.
	##
	## Recomputed from the collision list every frame rather than carried
	## forward, so a still taken at 20 s is identical whether it was reached by
	## rendering 1,200 frames or by jumping straight there. A scene that
	## accumulated this would give a clip and a still different pictures of the
	## same instant, which is the class of bug this whole architecture exists to
	## make impossible.
	for i in _total_tiles:
		_last_new_hit[i] = -1.0e9
		_last_dup_hit[i] = -1.0e9
	for hit in playback["collisions"]:
		var when := float(hit["t"])
		if when > t:
			break
		var index := int(hit["tile"])
		if bool(hit["new"]):
			_last_new_hit[index] = when
		else:
			_last_dup_hit[index] = when


func _apply_tiles(t: float) -> void:
	var complete_at := _completion
	# With the ending on, the whole-arena response is the Phase 4 wave and not
	# this flat pulse. Leaving both in would hold every tile at the completion
	# colour for the length of the hold, which is exactly the brightness the
	# wave needs to rise out of - the first render of the climax was a
	# uniformly gold arena with an invisible ripple crossing it.
	var completing := complete_at >= 0.0 and t >= complete_at and not _climax
	var completion_pulse := 0.0
	if completing:
		completion_pulse = maxf(0.0,
			1.0 - (t - complete_at) / COMPLETION_PULSE_SECONDS)

	for i in _total_tiles:
		var material := _tile_materials[i]
		var lit := _last_new_hit[i] > -1.0e8
		var push := 0.0

		if lit:
			var since_new := t - _last_new_hit[i]
			# A decaying pulse, strongest at the instant of contact. `1 - x^2`
			# rather than a linear ramp so the tile is still visibly brighter a
			# tenth of a second later, which is about when the eye arrives.
			var pulse := 0.0
			if since_new < NEW_HIT_PULSE_SECONDS:
				var x := since_new / NEW_HIT_PULSE_SECONDS
				pulse = 1.0 - x * x
			# The duplicate response: brightness only, never a push, and capped
			# well under the new-hit pulse.
			var dup := 0.0
			var since_dup := t - _last_dup_hit[i]
			if _last_dup_hit[i] > -1.0e8 and since_dup < DUP_HIT_PULSE_SECONDS:
				var y := since_dup / DUP_HIT_PULSE_SECONDS
				dup = DUP_HIT_PULSE_SCALE * (1.0 - y * y)

			material.albedo_color = TILE_ACTIVE
			var emission := TILE_ACTIVE_EMISSION
			var energy := 1.35 + 2.6 * pulse + 1.1 * dup
			if completing:
				emission = TILE_ACTIVE_EMISSION.lerp(
					TILE_COMPLETE_EMISSION, completion_pulse)
				energy += 1.8 * completion_pulse
			material.emission = emission
			material.emission_energy_multiplier = energy
			push = NEW_HIT_PUSH * pulse
		else:
			material.albedo_color = TILE_INACTIVE
			material.emission = TILE_INACTIVE_EMISSION
			material.emission_energy_multiplier = 1.0

		# Outward, along the wall's own normal: the ball is travelling outward
		# when it arrives, so the tile recoiling away from the arena centre is
		# the direction the impact actually had. Inward would read as the wall
		# reaching for the ball.
		_tiles[i].position = _tile_home[i] + _tile_normal[i] * push


func _apply_ball(t: float) -> void:
	var here := position_at(t)
	_ball.position = Vector3(here.x, here.y, BALL_DEPTH)
	if _halo != null:
		_halo.position = Vector3(here.x, here.y, BALL_DEPTH - 0.05)

	if trail_mode != "temporal":
		return
	for i in _trail.size():
		# Sample backwards along the *canonical* path, so the trail bends at a
		# wall exactly where the ball did. A straight streak behind the ball
		# would draw a line through the wall on the frame after a bounce.
		var age := trail_seconds * float(i + 1) / float(_trail.size())
		var node := _trail[i]
		if t - age < 0.0:
			node.visible = false
			continue
		var fade := 1.0 - float(i) / float(_trail.size())
		var at := position_at(t - age)
		node.visible = true
		node.position = Vector3(at.x, at.y, BALL_DEPTH - 0.02)
		var width: float = TRAIL_TAIL_WIDTH + (TRAIL_HEAD_WIDTH - TRAIL_TAIL_WIDTH) * fade
		node.scale = Vector3(width, width, 1.0)
		# Only the alpha changes per frame. The texture was assigned at build
		# time and the mesh size is fixed; `scale` carries the taper.
		var material: StandardMaterial3D = node.material_override
		material.albedo_color = Color(
			TRAIL_COLOUR.r, TRAIL_COLOUR.g, TRAIL_COLOUR.b, 0.42 * fade * fade)


func _apply_overlay(t: float) -> void:
	var count := activated_count_at(t)
	if _counter_label != null:
		_counter_label.text = "%d / %d" % [count, _total_tiles]
		var colour := TEXT_PRIMARY
		if count >= _total_tiles:
			colour = TILE_ACTIVE
		elif count >= _total_tiles - 1:
			# One tile left. The counter is the only thing in the frame that
			# says so in words, and it changes colour a beat before the arena
			# does.
			colour = Color(1.0, 0.82, 0.55)
		_counter_label.add_theme_color_override("font_color", colour)
	if _debug_label != null and show_debug:
		_debug_label.text = "seed %d   t=%.2fs   %d collisions" % [
			int(playback["seed"]), t, int(playback["collisions"].size())]


## What the scene drew, for the audit. Reported rather than recomputed, so a
## disagreement between this and the canonical document is a real disagreement.
func audit_state() -> Dictionary:
	var lit: Array[int] = []
	for i in _total_tiles:
		if _last_new_hit[i] > -1.0e8:
			lit.append(i)
	var here := position_pair(_time)
	return {
		"t": _time,
		"activated": lit.size(),
		"lit": lit,
		"ball": here,
	}
