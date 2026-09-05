extends Node3D

## The premium-toy marble machine: display platform, hero bowl, curved track.
##
## A third scene beside `race_scene.gd` and `neon_scene.gd`, playing the same
## replay through the same two-method contract - `build(replay, mode)` then
## `present(tick)` every frame - and disagreeing with the second about
## everything visual.
##
## ## What this scene is for
##
## One question, and not the one V1 or V1.1 answered. V1 asked whether a
## paused frame reads as three-dimensional; it does. V1.1 asked whether the
## machine reads as premium; the honest answer, once the frames were actually
## measured, is that it reads as a dark industrial factory. This scene asks
## whether the same machine can look like a *toy* - something moulded,
## glossy, bright and collectible, photographed for a product advertisement.
##
## Nothing about the race changes to find out. The simulation, the course, the
## replay format, the winner and the two-dimensional physics are untouched,
## and this file runs none of them. `deck_height` below is character for
## character the neon scene's, because a racer's world height has to keep
## coming out of the same function the surface under it is generated from -
## that is the guarantee V1 bought and it would be silly to spend it on a
## repaint.
##
## ## What actually changes
##
## Measured against the committed V1.1 heroes, four things:
##
## **Warmth.** V1.1 puts 0.8-1.3% warm pixels in frame against the concept
## reference's 18.8%, and every warm pixel it has is a marble. There is a warm
## fill light here, warm hardware on every module, warm underlighting and a
## warm practical at the bowl - so warmth is structural rather than decorative
## and survives in the variants whose accent colour is cool.
##
## **Value and neutrality.** 41-50% of V1.1's lit pixels are achromatic and
## its deck albedo renders as #9A9790 - a grey card. Every surface here is
## tinted and the running surfaces sit near #F2E8D6. The environment that
## metallic surfaces mirror is a lit dome rather than a black void, which is
## why almost nothing here is metallic at all.
##
## **Rounding.** V1.1's channels are straight extrusions with square lips: a
## sampled 12-pixel stripe varies by under 3/255 across its width, which is
## the signature of a flat facet. Every component here is swept, lathed or
## filleted through `toy_geometry.gd`, so every edge carries a highlight band
## whose width is its own radius.
##
## **Marble scale.** V1.1's marbles are 0.55-0.93% of frame against the
## reference's 5.86%. `MARBLE_SCALE` and a field of eight put them at roughly
## six times the area, which is what makes the hero of a marble run the
## marble.
##
## ## One channel per section, not four
##
## The neon scene splits each section into every separately-walled run and
## sweeps a beam through each. On the chute that produces four parallel
## striped decks, and the measurement says those stripes land at a 9-pixel
## pitch that aliases into moire at phone scale - the industrial reading gets
## *sharper* when the image gets smaller, which is exactly backwards.
##
## This scene takes the envelope instead: at each sampled height, the union of
## everything walled on both sides, as one moulded channel. It is simpler, it
## is guaranteed to have something under every racer for the same reason the
## neon builder is - the width is the course's own clear span and not a number
## chosen by eye - and it gives each section one continuous flowing silhouette
## rather than a repeated one, which is the brief's actual rule.
##
## ## Determinism
##
## As in both siblings: the offline renderer seeks to `frame / fps` and draws.
## Nothing here integrates, accumulates or randomises, and the one moving
## machine part is a function of the playhead. Two renders of one replay are
## identical.

const ToyMaterials := preload("res://scripts/toy_materials.gd")
const Geo := preload("res://scripts/toy_geometry.gd")

const PIXELS_PER_UNIT := 100.0

# --- presentation heights -------------------------------------------------
#
# Identical to the neon scene's, and deliberately so. They are the mapping
# V1 proved, the racers' world Y comes out of them, and this revision is
# about surface and light rather than about where anything is.
const H_START := 0.0
const H_RIM := -2.60
const BOWL_DEPTH := 2.60
const H_THROAT := -6.20
const H_BRIDGE_END := -9.20
const H_FINISH_DROP := 0.55

const FLOOR_RHO := 0.26
const FLANGE_OUTER := 1.20
const BOWL_PROFILE_POWER := 1.9

# --- the marbles ----------------------------------------------------------

# One, and measured rather than chosen.
#
# The brief asks for the marbles to be bigger, and the obvious lever is a
# multiplier on the drawn radius. It does not work, and the replay says why:
# across all 616 frames of the reference run the closest pair of racers is
# 57-60 course pixels apart, against a simulation diameter of 60. The field
# is in contact essentially always - a marble run is a pile-up - so *any*
# multiplier above 1.0 draws intersecting spheres in 100% of frames. At the
# 1.70 this scene was first built with, two touching marbles overlapped by
# 42 pixels of a 102-pixel diameter and the pile in the bowl rendered as one
# fused blob rather than as eight collectibles.
#
# So apparent size is bought the other way the brief offers - "increase
# apparent marble size, use tighter framing, use fewer marbles if necessary"
# - with eight racers instead of sixteen and hero lenses that fill the frame
# with the module they are about. That is also the honest way round: it makes
# the marbles bigger *in the picture*, which is what was actually asked for,
# without drawing a field that is not the field the simulation produced.
const MARBLE_SCALE := 1.00
const MARBLE_SEGMENTS := 56
const MARBLE_RINGS := 28

# --- the channel ----------------------------------------------------------

# The moulded cross-section, in world units. `CHANNEL_MARGIN` is how far past
# the course's clear span the running surface reaches - the wall stands
# outside the span, so a racer touching the simulation wall is still over
# floor.
const CHANNEL_MARGIN := 18.0        # course pixels
const CHANNEL_DROP := 0.34          # shell depth below the running surface
const CHANNEL_WALL := 0.30          # wall height above it
const CHANNEL_FILLET := 0.13
const CHANNEL_ROUNDS := 4
# The warm beam under a channel, deeper than the pearl lip standing on it.
const FASCIA_DEPTH := 0.17
# The dark beam the brass lip stands on, and how much of the channel's width
# it takes. Deep and narrow: a keel, not a second deck.
const KEEL_DEPTH := 0.46
const KEEL_INSET := 0.62
const CHANNEL_STEP := 34.0          # course px between cross-sections
const EDGE_SMOOTHING := 3
const MIN_SPAN := 60.0
const WALL_SIN_MIN := 0.25

# The acrylic guard rail standing on the channel's wall, as a round bar.
const RAIL_RADIUS := 0.055
const RAIL_LIFT := 0.30
const RAIL_INSET := 0.055

# --- the bowl -------------------------------------------------------------

# How thick the vessel's wall is: the gap between the pearl running surface
# and the dark shell moulded under it.
const BOWL_WALL := 0.20
const BOWL_RINGS := 40
const BOWL_SEGMENTS := 96
# The rim: a filleted lip standing proud of the running surface, and the
# outer flange it stands on.
const RIM_THICKNESS := 0.16
const RIM_RISE := 0.13
# The acrylic wall on the rim, in bowl radii out and world units up.
const GLASS_FLARE := 0.20
const GLASS_RISE := 1.02
const GLASS_ROUNDS := 10
# The near opening, either side of the point of the disc closest to the lens.
# The brief allows a partial wall where a full one would cost readability,
# and this is that: the acrylic is unbroken across the far three quarters
# where it is silhouetted, and open where it would sit between the camera and
# every marble.
const GLASS_GAP_HALF := 46.0
# The lit ring under the rim, and the cradle outside it.
# Outside the rim rather than under it. At 1.06 the ring sat inside the
# flange and every lens high enough to see into the bowl had the rim in front
# of it, so the one coloured thing on the hero object was invisible in every
# frame. At 1.34 it is a lit band around the outside of the vessel, below the
# acrylic's flare and above the cradle, and it reads from any angle.
const RING_RHO := 1.34
const RING_DROP := 0.46
const CRADLE_RHO := 1.44
const CRADLE_DROP := 1.34
const CRADLE_LEGS := 6
const RIM_CLAMPS := 10
const DRAIN_WELL_DEPTH := 3.20

# --- the start platform ---------------------------------------------------

const PLATFORM_OVERHANG := 130.0
const PLATFORM_THICKNESS := 0.56
const PLATFORM_FILLET := 0.20
const BAY_RECESS := 0.10
const GUARD_HEIGHT := 0.62
const FASCIA_HEIGHT := 0.52
const GATE_HEIGHT := 0.70
const SIGN_RISE := 2.30
const SIGN_SIZE := Vector3(3.30, 0.72, 0.20)
const LEG_RADIUS := 0.17

# --- the mechanical toy element -------------------------------------------
#
# One rotating distributor at the end of the curved track. Its whole job is
# to establish the visual vocabulary for moving machinery - a rounded casing,
# a warm hub, a readable silhouette - and it is deliberately not in the
# racing line: the brief asks for no gameplay to be built around it and a
# decorative part cannot change a frozen replay.
const ELEMENT_Z := 3760.0            # course pixels
const ELEMENT_OFFSET := 3.05         # world units to the side of the centre
const ELEMENT_RADIUS := 1.02
const ELEMENT_CASING := 0.30
const ELEMENT_BLADES := 5
const ELEMENT_HUB := 0.30
# Turns per second of replay. Slow enough to read as machinery rather than as
# a fan, and a pure function of the playhead so two renders agree.
const ELEMENT_RPS := 0.16

# --- the room -------------------------------------------------------------

const ROOM_FLOOR_Y := -15.5
# Both ranks are far enough out to be behind the machine rather than beside
# it. The bowl is 4.7 units in radius and its acrylic flares past 5.6; a rank
# at 9 was inside that silhouette from any three-quarter lens.
const PYLON_NEAR_X := 16.0
const PYLON_NEAR := Vector3(1.15, 17.0, 1.15)
const PYLON_NEAR_SPACING := 19.0
const PYLON_MID_X := 21.5
const PYLON_MID := Vector3(2.10, 30.0, 2.10)
const PYLON_MID_SPACING := 16.0
# The sweep: how far out its foot stands and how high its curve carries.
const SWEEP_RADIUS := 34.0
const SWEEP_HEIGHT := 40.0
const FLOOR_SIZE := 108.0

# --- the camera -----------------------------------------------------------
#
# Four lenses, and three of them are fixed. The brief's question is whether
# the object is desirable, and a shot that is wherever the leaders happen to
# have got to answers a different one - so the hero framings are product
# photography: a chosen aim, a chosen distance, a chosen azimuth, held.
#
# `follow` is the fourth and it is the only one that moves. It is what the
# motion proof is cut from, and its job is to show highlights travelling,
# parallax between the three ranks of room, and the marbles staying readable
# while they move. It is not a gameplay camera and nothing depends on it.
#
# Each entry is (aim course-y, aim lift, distance, elevation, azimuth, fov).
const SHOTS := {
	# A - establishing, and shot from *below* the machine looking back up it.
	#
	# Every downstream-facing lens tried before this one framed the bowl and
	# nothing else, because the machine descends nine units over thirty-four
	# and a camera above the start is looking at the back of its own subject.
	# From past the track, looking back, the three modules stack the way the
	# reference's hero does - track in the foreground, bowl above and beyond
	# it, feeder and platform highest - and the nine units of drop become
	# nine units of *frame height* rather than nine units of recession.
	"a": {
		"aim": 2060.0, "lift": 2.20, "distance": 16.0,
		"elevation": 34.0, "azimuth": 158.0, "fov": 46.0,
	},
	# B - bowl hero. Round the side rather than over the chute. Any lens on
	# the machine's centre line has the feed between it and the bowl, which is
	# how the first pass filled seventy percent of this frame with the
	# underside of a ramp. From sixty-odd degrees round, the acrylic wall is
	# seen across its own flare, the cradle stands clear below it, and the
	# field is against the bowl's far wall rather than behind its near one.
	"b": {
		"aim": 1812.0, "lift": 2.80, "distance": 19.0,
		"elevation": 30.0, "azimuth": 56.0, "fov": 36.0,
	},
	# C - track hero. Low and well round, so the curve is seen along its own
	# length with the girder, the legs and the floor under it in frame.
	"c": {
		"aim": 3020.0, "lift": 0.95, "distance": 11.2,
		"elevation": 23.0, "azimuth": -46.0, "fov": 42.0,
	},
}
const SHOT_FOLLOW := "follow"

const FOLLOW_FOV := 42.0
const FOLLOW_LEAD := 620.0
# Far enough that the bowl never fills the frame on its own. The aim height
# is `deck_height` on the machine's centre line, and inside the bowl that is
# the *floor* - two and a half units below the rim - so a lens close enough
# to frame the field on the chute dives into the basin as the field reaches
# it. At seventeen units the middle of the clip was one marble against a wall
# of cream; the lift below holds the aim near the rim instead of the floor.
const FOLLOW_DISTANCE := 25.0
const FOLLOW_ELEVATION := 40.0
const FOLLOW_LIFT := 1.90
const FOLLOW_ORBIT := Vector2(14.0, 30.0)
const FOLLOW_ORBIT_SPAN := Vector2(500.0, 3400.0)
const FOLLOW_DIP := 6.0

# --- the shutter ----------------------------------------------------------

const SHUTTER_SECONDS := 0.28
const SHUTTER_TRAVEL := 1.9
const PLAYHEAD_SNAP := 1.0e-6

var camera_mode := "production"

var _course: Dictionary = {}
var _meta: Dictionary = {}
var _frames: Array = []
var _racer_meta: Array = []

var _course_width := 1080.0
var _course_top := 0.0
var _course_bottom := 4120.0

var _bowl_cx := 540.0
var _bowl_cy := 1820.0
var _bowl_r := 470.0
var _bowl_top := 1350.0
var _drain_half := 110.0
var _drain_y := 1820.0

var _gate_y := 740.0
var _platform_top := 430.0
var _platform_left := 95.0
var _platform_right := 985.0
var _throat_end := 2200.0
var _bridge_top := 2200.0
var _bridge_end := 3800.0

var _palette: ToyMaterials
var _camera: Camera3D
var _shot := SHOT_FOLLOW
var _variant := ToyMaterials.VARIANT_A

var _racer_nodes: Array[Node3D] = []
var _racer_spheres: Array[MeshInstance3D] = []
var _racer_radius: Array[float] = []

var _shutter_leaves: Array[Node3D] = []
var _shutter_home: Array[float] = []
var _gate_tick := -1.0

var _element: Node3D = null

var _physics_hz := 120.0
var _ticks_per_frame := 2.0


# --- lifecycle ------------------------------------------------------------

func build(replay: Dictionary, mode := "production") -> void:
	camera_mode = mode
	_course = replay.get("course", {})
	_meta = _course.get("metadata", {})
	_frames = replay.get("frames", [])
	_racer_meta = replay.get("racers", [])
	_course_width = maxf(1.0, float(_course.get("width", 1080.0)))
	_course_top = float(_course.get("top", 0.0))
	_course_bottom = float(_course.get("bottom", 4120.0))
	_physics_hz = maxf(1.0, float(replay.get("physics_hz", 120.0)))
	_ticks_per_frame = maxf(1.0, float(replay.get("ticks_per_frame", 2.0)))

	_variant = _variant_argument()
	_shot = _shot_argument()

	_read_machine()
	_gate_tick = _find_gate_tick()

	_palette = ToyMaterials.new(_variant)

	_build_environment()
	_build_lights()
	_build_camera()
	_build_room()
	_build_start_platform()
	_build_channel("chute", true)
	_build_bowl()
	_build_channel("throat", false, 0.04, false, 0.16)
	_build_channel("bridge", true)
	_build_channel("finish", false)
	_build_element()
	_build_racers()


func present(tick: float) -> void:
	if _frames.size() < 1:
		return
	var last := float(_frames.size() - 1)
	var playhead := clampf(tick / _ticks_per_frame, 0.0, last)
	var whole := roundf(playhead)
	if absf(playhead - whole) < PLAYHEAD_SNAP:
		playhead = whole

	var index := int(floor(playhead))
	var next_index := mini(index + 1, _frames.size() - 1)
	var blend := playhead - float(index)

	var frame: Dictionary = _frames[index]
	var next_frame: Dictionary = _frames[next_index]

	_update_camera(frame, next_frame, blend)
	_update_racers(frame.get("racers", []), next_frame.get("racers", []), blend)
	_update_gate(tick)
	_update_element(playhead)


# --- arguments ------------------------------------------------------------

func _argument(name: String) -> String:
	for argument in OS.get_cmdline_user_args():
		var arg: String = argument
		if arg == name:
			return "1"
		if arg.begins_with(name + "="):
			var value := arg.substr(name.length() + 1)
			return "" if value == "0" else value
	return ""


func _variant_argument() -> String:
	## `--toy-variant=a|b|c` picks a palette at render time.
	##
	## At render time rather than by editing a constant, for the reason every
	## other sweep in this project takes its parameter that way: the three
	## comparison frames have to come out of one build of one scene from one
	## replay, or what is being compared is not only the palette.
	var value := _argument("--toy-variant")
	return value if ToyMaterials.VARIANTS.has(value) else ToyMaterials.VARIANT_A


func _shot_argument() -> String:
	## `--toy-shot=a|b|c` selects a fixed hero lens; absent means the move.
	var value := _argument("--toy-shot")
	return value if SHOTS.has(value) else SHOT_FOLLOW


func _camera_override() -> Dictionary:
	## `--toy-cam=aim,lift,distance,elevation,azimuth,fov` replaces the lens.
	##
	## The art-iteration tool. Choosing a product lens is a matter of looking
	## at eight of them side by side, and re-rendering eight framings one
	## constant-edit at a time is how an afternoon disappears. With this the
	## whole sweep is one command and one build, and the framing that wins can
	## then be written into `SHOTS` as a number that was chosen by eye rather
	## than argued for.
	var value := _argument("--toy-cam")
	if value == "" or value == "1":
		return {}
	var parts := value.split(",", false)
	if parts.size() < 6:
		return {}
	return {
		"aim": parts[0].to_float(),
		"lift": parts[1].to_float(),
		"distance": parts[2].to_float(),
		"elevation": parts[3].to_float(),
		"azimuth": parts[4].to_float(),
		"fov": parts[5].to_float(),
	}


# --- the machine ----------------------------------------------------------

func _read_machine() -> void:
	## Where the parts are, taken from the course and not guessed.
	_bowl_cx = float(_meta.get("bowl_centre_x", _course_width * 0.5))
	_bowl_cy = float(_meta.get("bowl_centre_y", 1820.0))
	_bowl_r = maxf(1.0, float(_meta.get("bowl_radius", 470.0)))
	_bowl_top = float(_meta.get("bowl_top", _bowl_cy - _bowl_r))
	_drain_half = maxf(1.0, float(_meta.get("drain_half", 110.0)))
	_drain_y = float(_meta.get("drain_y", _bowl_cy))
	_gate_y = float(_meta.get("gate_y", 740.0))
	_platform_top = float(_meta.get("platform_top", 430.0))
	_platform_left = float(_meta.get("platform_left", 95.0))
	_platform_right = float(_meta.get("platform_right", 985.0))
	_throat_end = float(_meta.get("throat_end", 2200.0))
	_bridge_top = float(_meta.get("bridge_top", _throat_end))
	_bridge_end = float(_meta.get("bridge_end", 3800.0))


func _find_gate_tick() -> float:
	for frame in _frames:
		var entry: Dictionary = frame
		if bool(entry.get("gates_open", false)):
			return float(entry.get("tick", 0))
	return -1.0


# --- the presentation mapping ---------------------------------------------
#
# Character for character the neon scene's. See the file header.

func to_world(sim_x: float, sim_y: float, height: float) -> Vector3:
	return Vector3(
		(sim_x - _course_width * 0.5) / PIXELS_PER_UNIT,
		height + deck_height(sim_x, sim_y),
		sim_y / PIXELS_PER_UNIT)


func to_units(pixels: float) -> float:
	return pixels / PIXELS_PER_UNIT


func bowl_rho(sim_x: float, sim_y: float) -> float:
	var dx := sim_x - _bowl_cx
	var dy := sim_y - _bowl_cy
	return sqrt(dx * dx + dy * dy) / _bowl_r


func bowl_profile(rho: float) -> float:
	if rho <= FLOOR_RHO:
		return 1.0
	if rho >= 1.0:
		return 0.0
	var q := (rho - FLOOR_RHO) / (1.0 - FLOOR_RHO)
	return 1.0 - pow(q, BOWL_PROFILE_POWER)


func bowl_surface_y(rho: float) -> float:
	return H_RIM - BOWL_DEPTH * bowl_profile(clampf(rho, 0.0, FLANGE_OUTER))


func deck_height(sim_x: float, sim_y: float) -> float:
	if sim_y <= _gate_y:
		return H_START
	if sim_y <= _bowl_top:
		var chute := (sim_y - _gate_y) / maxf(1.0, _bowl_top - _gate_y)
		return lerpf(H_START, H_RIM, smoothstep(0.0, 1.0, chute))
	if sim_y <= _drain_y:
		return bowl_surface_y(bowl_rho(sim_x, sim_y))
	if sim_y <= _throat_end:
		var throat := (sim_y - _drain_y) / maxf(1.0, _throat_end - _drain_y)
		return lerpf(
			bowl_surface_y(bowl_rho(sim_x, sim_y)),
			H_THROAT,
			smoothstep(0.0, 1.0, throat))
	if sim_y <= _bridge_end:
		var bridge := (sim_y - _throat_end) / maxf(1.0, _bridge_end - _throat_end)
		return lerpf(H_THROAT, H_BRIDGE_END, bridge)
	var tail := clampf(
		(sim_y - _bridge_end) / maxf(1.0, _course_bottom - _bridge_end), 0.0, 1.0)
	return H_BRIDGE_END - H_FINISH_DROP * tail


# --- environment ----------------------------------------------------------

func _build_environment() -> void:
	## A lit dome, not a void. This is the single largest change in the file.
	##
	## The neon environment is a black chamber with a sky so dark that its
	## hemispherical average is linear 0.017 - an ambient irradiance of about
	## 0.012 against a key of 1.56, which is a key-to-fill ratio of 1:131.
	## Every surface not facing the key falls to the background, and every
	## metallic surface mirrors nothing. That single number is most of why the
	## machine reads as a dark factory, and no amount of raising albedo fixes
	## it, because albedo is multiplied by the light that is not there.
	##
	## This is a softbox: a bright sky, a warm horizon, a mid-value ground
	## bounce, and ambient energy that puts the ratio near 1:5. It is what
	## makes a moulded surface show its shading gradient, what fills a
	## shadow instead of crushing it, and what the acrylic and the small
	## amount of warm metal have to reflect.
	var environment := Environment.new()
	environment.background_mode = Environment.BG_SKY

	var sky_material := ProceduralSkyMaterial.new()
	sky_material.sky_top_color = _palette.color("sky_top")
	sky_material.sky_horizon_color = _palette.color("sky_horizon")
	sky_material.sky_curve = 0.35
	sky_material.ground_horizon_color = _palette.color("sky_horizon")
	sky_material.ground_bottom_color = _palette.color("ground")
	sky_material.ground_curve = 0.30
	sky_material.sun_angle_max = 0.0
	sky_material.energy_multiplier = 1.0

	var sky := Sky.new()
	sky.sky_material = sky_material
	sky.radiance_size = Sky.RADIANCE_SIZE_256
	sky.process_mode = Sky.PROCESS_MODE_QUALITY
	environment.sky = sky

	environment.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	environment.ambient_light_sky_contribution = 1.0
	environment.ambient_light_energy = 1.05
	environment.reflected_light_source = Environment.REFLECTION_SOURCE_SKY

	# The dome lights and reflects at full strength; it is only *drawn* dim.
	# The reference concept holds its environment at mean luma 0.145 against a
	# subject at 0.387 - a ratio of 2.7 - and that gap is what a bright object
	# needs to be silhouetted against. The first pass lit the room with the
	# same dome it lit the machine with and the two came out the same value,
	# which is a machine with nothing behind it rather than a machine in a
	# room. Splitting the two is one multiplier.
	environment.background_energy_multiplier = 0.34

	# AgX rather than ACES. ACES rolls a saturated blue towards cyan and a
	# saturated red towards orange, which is tolerable on a machine whose only
	# saturated objects are eight marbles and fatal on one where the marbles
	# are the subject. AgX holds hue through the shoulder, which is what keeps
	# a cobalt marble cobalt where it catches the key.
	environment.tonemap_mode = Environment.TONE_MAPPER_AGX
	environment.tonemap_white = 4.0
	environment.tonemap_exposure = 0.90

	# Haze rather than darkness. The neon fog light is #0C121D, so everything
	# past thirty-four units fades *towards black* - which is how a background
	# ends up as one quantised colour covering a fifth of the frame. This fog
	# is brighter than the structure it falls on, so distance reads as air.
	environment.fog_enabled = true
	environment.fog_mode = Environment.FOG_MODE_DEPTH
	environment.fog_light_color = _palette.color("backdrop")
	environment.fog_light_energy = 1.0
	environment.fog_density = 0.55
	environment.fog_depth_begin = 38.0
	environment.fog_depth_end = 124.0
	environment.fog_depth_curve = 1.6
	environment.fog_sky_affect = 0.0

	# Seasoning, and the brief asks for the picture to be attractive without
	# it. `--toy-no-glow` renders the same frame with it off, out of one build
	# of one scene from one replay, so the claim can be looked at rather than
	# asserted. The threshold is above every emissive material in the palette
	# - nothing here is load-bearing bloom.
	environment.glow_enabled = _argument("--toy-no-glow") == ""
	environment.glow_intensity = 0.30
	environment.glow_strength = 1.0
	environment.glow_bloom = 0.05
	environment.glow_blend_mode = Environment.GLOW_BLEND_MODE_SOFTLIGHT
	environment.glow_hdr_threshold = 1.30
	environment.glow_hdr_scale = 1.4
	environment.set_glow_level(1, 0.0)
	environment.set_glow_level(2, 0.4)
	environment.set_glow_level(3, 1.0)
	environment.set_glow_level(4, 0.7)
	environment.set_glow_level(5, 0.3)
	environment.set_glow_level(6, 0.0)

	# Contact darkening, softer than the neon scene's. On a bright machine an
	# aggressive occlusion term reads as dirt in every fillet; on a dark one
	# it was the only thing seating anything.
	environment.ssao_enabled = true
	environment.ssao_radius = 0.55
	environment.ssao_intensity = 1.85
	environment.ssao_power = 1.9
	environment.ssao_detail = 0.5
	environment.ssao_light_affect = 0.25

	var world := WorldEnvironment.new()
	world.name = "WorldEnvironment"
	world.environment = environment
	add_child(world)


func _build_lights() -> void:
	## Product photography: a soft key, a warm fill, a cool rim.
	##
	## The neon rig spends 33% of its luminous energy on non-key light and
	## every watt of it is blue - a measured B/R of 1.51, which is the cold
	## cast the brief names. Here the fill is warm and the rim is cool, so the
	## two off-key sources pull against each other instead of together, and
	## the machine has a warm side and a cool side rather than a blue cast.
	var key := DirectionalLight3D.new()
	key.name = "KeyLight"
	key.light_color = Color(1.0, 0.968, 0.918)
	key.light_energy = 1.90
	key.light_specular = 1.0
	key.shadow_enabled = true
	key.directional_shadow_mode = DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS
	key.directional_shadow_max_distance = 88.0
	key.directional_shadow_split_1 = 0.09
	key.directional_shadow_split_2 = 0.22
	key.directional_shadow_split_3 = 0.50
	key.directional_shadow_blend_splits = true
	key.shadow_bias = 0.026
	key.shadow_normal_bias = 1.0
	# Softer than the neon scene's 0.92. A product shot has open shadows; a
	# fully opaque one on a bright surface reads as a hole cut in it.
	key.shadow_opacity = 0.72
	# The reference's own key, measured off the specular blob on its legend
	# racers: about fifty-six degrees of elevation, ten to fifteen degrees to
	# camera right. A lower key rakes across a moulded surface and turns every
	# fillet into a band; this one sits high enough to put a clean highlight
	# on the top of a sphere, which is what a product shot does.
	key.rotation_degrees = Vector3(-56.0, 24.0, 0.0)
	add_child(key)

	# The warm fill, and the single most important light in the file after
	# the key. It comes from the opposite side so the shadow side of every
	# moulded form is warm rather than blue, which is what a bounce card does
	# in a product studio.
	var fill := DirectionalLight3D.new()
	fill.name = "WarmFill"
	fill.light_color = Color(1.0, 0.812, 0.612)
	fill.light_energy = 0.76
	fill.light_specular = 0.35
	fill.shadow_enabled = false
	fill.rotation_degrees = Vector3(-22.0, -128.0, 0.0)
	add_child(fill)

	# The cool rim, from behind and low, to draw the top edge of every
	# component against the backdrop. Small energy: it is an edge, not a
	# second key.
	var rim := DirectionalLight3D.new()
	rim.name = "CoolRim"
	rim.light_color = Color(0.706, 0.843, 1.0)
	rim.light_energy = 0.70
	rim.light_specular = 1.0
	rim.shadow_enabled = false
	rim.rotation_degrees = Vector3(-12.0, 172.0, 0.0)
	add_child(rim)

	_build_zone_lights()


func _build_zone_lights() -> void:
	## Cool at the top of the machine, warm at the bottom.
	##
	## The reference's governing law, and it took measuring the thing to see
	## it: its track albedo never changes. The same light-grey surface is
	## sampled at value 0.73-0.81 in all seven zones while its red-over-blue
	## ratio climbs monotonically from 0.93 at the start to 1.27 at the
	## finish. Value held, hue ramped - and ramped by the *light*, not by the
	## paint. Warm pixels follow the same curve: 1-2% of rows in the top third
	## of the frame, 4-6% in the middle, 13-35% in the bottom.
	##
	## So zone colour here is two large soft practicals rather than a tinted
	## material per section. It costs two lights, it survives a change of
	## palette, and it is why a cream channel reads cool where it leaves the
	## platform and warm where it reaches the track - which a viewer reads as
	## one machine passing through places, rather than as several components
	## that happen to share a colour.
	var cool := OmniLight3D.new()
	cool.name = "ZoneCool"
	cool.light_color = _palette.color("accent_cool")
	cool.light_energy = 5.20
	cool.omni_range = 20.0
	cool.omni_attenuation = 1.5
	cool.shadow_enabled = false
	cool.position = Vector3(0.0, H_START + 3.4, to_units(_gate_y) - 1.5)
	add_child(cool)

	var warm := OmniLight3D.new()
	warm.name = "ZoneWarm"
	warm.light_color = _palette.color("accent_warm")
	warm.light_energy = 9.50
	warm.omni_range = 26.0
	warm.omni_attenuation = 1.4
	warm.shadow_enabled = false
	warm.position = Vector3(
		0.0, H_BRIDGE_END + 3.0, to_units((_bridge_top + _bridge_end) * 0.5))
	add_child(warm)

	# A third, low and warm, washing the hall floor under the machine. The
	# reference's warmth rises towards the bottom of frame and most of it is
	# bounce rather than fixture; this is that bounce, and it is what stops
	# the floor being the single flat dark value the V1.1 background was.
	var bounce := OmniLight3D.new()
	bounce.name = "ZoneBounce"
	bounce.light_color = _palette.color("hardware")
	bounce.light_energy = 4.20
	bounce.omni_range = 26.0
	bounce.omni_attenuation = 1.2
	bounce.shadow_enabled = false
	bounce.position = Vector3(0.0, ROOM_FLOOR_Y + 1.6, to_units(_bowl_cy) + 8.0)
	add_child(bounce)


func _build_camera() -> void:
	_camera = Camera3D.new()
	_camera.name = "Camera3D"
	_camera.projection = Camera3D.PROJECTION_PERSPECTIVE
	_camera.keep_aspect = Camera3D.KEEP_HEIGHT
	_camera.near = 0.15
	_camera.far = 320.0
	_camera.fov = float(SHOTS[_shot]["fov"]) if SHOTS.has(_shot) else FOLLOW_FOV
	add_child(_camera)


func _update_camera(frame: Dictionary, next_frame: Dictionary,
		blend: float) -> void:
	var override := _camera_override()
	if not override.is_empty():
		_camera.fov = float(override["fov"])
		_place_camera(override)
		return
	if SHOTS.has(_shot):
		_place_camera(SHOTS[_shot])
		return

	# The move. One flowing shot with a slow orbit under it, every term a
	# smoothstep of the aim's course height, so seeking anywhere gives the
	# same framing and nothing accumulates.
	var top := lerpf(
		float(frame.get("camera_y", 0.0)),
		float(next_frame.get("camera_y", 0.0)),
		blend)
	var aim_y := top + FOLLOW_LEAD
	var bowl := smoothstep(_bowl_top, _drain_y, aim_y)
	var orbit := lerpf(FOLLOW_ORBIT.x, FOLLOW_ORBIT.y,
		smoothstep(FOLLOW_ORBIT_SPAN.x, FOLLOW_ORBIT_SPAN.y, aim_y))
	_place_camera({
		"aim": aim_y,
		"lift": FOLLOW_LIFT,
		"distance": FOLLOW_DISTANCE,
		"elevation": FOLLOW_ELEVATION - FOLLOW_DIP * bowl,
		"azimuth": orbit,
		"fov": FOLLOW_FOV,
	})


func _place_camera(shot: Dictionary) -> void:
	var aim_y := float(shot["aim"])
	var aim := Vector3(
		0.0,
		deck_height(_bowl_cx, aim_y) + float(shot["lift"]),
		to_units(aim_y))
	var elevation := deg_to_rad(float(shot["elevation"]))
	var distance := float(shot["distance"])
	var offset := Vector3(
		0.0, distance * sin(elevation), -distance * cos(elevation))
	offset = offset.rotated(Vector3.UP, deg_to_rad(float(shot["azimuth"])))
	_camera.position = aim + offset
	_camera.look_at(aim, Vector3.UP)


# --- course sampling ------------------------------------------------------
#
# The same two measurements the neon scene takes, and taken the same way:
# what a piece blocks at a height, and what is left clear between the pieces.
# What differs is what is done with the answer - see `_envelope`.

func _piece_span(spec: Dictionary, y: float) -> Vector2:
	var piece_y := float(spec.get("y", 0.0))
	if str(spec.get("type", "")) == "circle":
		var radius := float(spec.get("radius", 0.0))
		if absf(y - piece_y) > radius:
			return Vector2.ZERO
		var half := sqrt(maxf(1.0, radius * radius - pow(y - piece_y, 2.0)))
		var centre := float(spec.get("x", 0.0))
		return Vector2(centre - half, centre + half)

	var half_w := float(spec.get("width", 0.0)) * 0.5
	var half_h := float(spec.get("height", 0.0)) * 0.5
	var angle := deg_to_rad(float(spec.get("rotation_degrees", 0.0)))
	if absf(sin(angle)) < WALL_SIN_MIN:
		return Vector2.ZERO

	var cos_a := cos(angle)
	var sin_a := sin(angle)
	var piece_x := float(spec.get("x", 0.0))
	var corners: Array[Vector2] = []
	for signs in [Vector2(-1.0, -1.0), Vector2(1.0, -1.0),
			Vector2(1.0, 1.0), Vector2(-1.0, 1.0)]:
		corners.append(Vector2(
			piece_x + signs.x * half_w * cos_a - signs.y * half_h * sin_a,
			piece_y + signs.x * half_w * sin_a + signs.y * half_h * cos_a))

	var lowest := INF
	var highest := -INF
	for index in 4:
		var here: Vector2 = corners[index]
		var next: Vector2 = corners[(index + 1) % 4]
		if absf(here.y - y) < 1.0e-6:
			lowest = minf(lowest, here.x)
			highest = maxf(highest, here.x)
		if (here.y - y) * (next.y - y) >= 0.0 or here.y == next.y:
			continue
		var t := (y - here.y) / (next.y - here.y)
		var crossing := here.x + t * (next.x - here.x)
		lowest = minf(lowest, crossing)
		highest = maxf(highest, crossing)
	if lowest > highest:
		return Vector2.ZERO
	return Vector2(lowest, highest)


func _clear_spans(section: String, y: float) -> Array:
	var blocked: Array = []
	for raw in _course.get("pieces", []):
		var spec: Dictionary = raw
		if str(spec.get("section", "")) != section:
			continue
		if str(spec.get("role", "")) == "gate":
			continue
		var span := _piece_span(spec, y)
		if span != Vector2.ZERO:
			blocked.append(span)
	blocked.sort_custom(func(a, b): return a.x < b.x)

	var spans: Array = []
	if blocked.size() < 2:
		return spans
	var cursor: float = (blocked[0] as Vector2).y
	for index in range(1, blocked.size()):
		var span: Vector2 = blocked[index]
		if span.x - cursor > MIN_SPAN:
			spans.append(Vector2(cursor, span.x))
		cursor = maxf(cursor, span.y)
	return spans


func _section_bounds(section: String) -> Vector2:
	for raw in _course.get("sections", []):
		var entry: Dictionary = raw
		if str(entry.get("name", "")) == section:
			return Vector2(
				float(entry.get("top", 0.0)), float(entry.get("bottom", 0.0)))
	return Vector2.ZERO


func _envelope(section: String) -> Array:
	## One channel through a section, as cross-sections of (left, right, y).
	##
	## The union of everything walled on both sides at each sampled height,
	## rather than each walled run separately. Where the chute splits into two
	## spouts the envelope spans both and the wedge between them, so the deck
	## runs on through - which is the whole point. A racer is always inside
	## some clear span, so it is always inside their union, so there is always
	## floor under it; and one continuous component is the silhouette the
	## brief asks for where four parallel striped ones are the silhouette it
	## rejects.
	var bounds := _section_bounds(section)
	if bounds == Vector2.ZERO:
		return []
	var start := bounds.x
	var finish := bounds.y
	if finish <= start:
		return []
	var steps := maxi(2, int((finish - start) / CHANNEL_STEP))

	var raw: Array = []
	for step in steps + 1:
		var y := start + float(step) * (finish - start) / float(steps)
		var spans := _clear_spans(section, y)
		if spans.is_empty():
			continue
		var left := INF
		var right := -INF
		for entry in spans:
			var span: Vector2 = entry
			left = minf(left, span.x)
			right = maxf(right, span.y)
		raw.append(Vector3(left - CHANNEL_MARGIN, right + CHANNEL_MARGIN, y))
	return _smooth(raw)


func _smooth(samples: Array) -> Array:
	## Round the scallop out of a swept edge.
	##
	## A wall is a chain of overlapping boxes, so a curved wall's measured
	## edge has a shallow corner at each joint. Averaging over a window a
	## little wider than one box removes them and leaves the curve, which is
	## two orders of magnitude longer, untouched. Doubly worth it here: a
	## moulded component with facet joints in its rim is a fabricated one.
	if samples.size() < 3:
		return samples
	var smoothed: Array = []
	for index in samples.size():
		var left := 0.0
		var right := 0.0
		var count := 0
		for offset in range(-EDGE_SMOOTHING, EDGE_SMOOTHING + 1):
			var at := clampi(index + offset, 0, samples.size() - 1)
			var sample: Vector3 = samples[at]
			left += sample.x
			right += sample.y
			count += 1
		var here: Vector3 = samples[index]
		smoothed.append(Vector3(left / count, right / count, here.z))
	return smoothed


# --- the channel ----------------------------------------------------------

func _build_channel(section: String, rails: bool, wall := CHANNEL_WALL,
		cap := true, sink := 0.0) -> void:
	## One moulded component per section: shell, running surface, rails.
	##
	## `wall` and `sink` exist for the throat, which is the one section that
	## begins *inside another object*. Its top plane at the drain is the bowl
	## floor, so a channel built there with the standard wall and an end cap
	## put a capped wedge up through the basin and out of the drain - clearly
	## visible in both hero frames as a grey blade lying in the bowl. Dropped
	## below the floor, walled at a tenth of the height and left open at the
	## ends, it is a tube inside the drain well where it belongs.
	var samples := _envelope(section)
	if samples.size() < 2:
		return

	var root := Node3D.new()
	root.name = "Channel_%s" % section
	add_child(root)

	var path: Array = []
	var sections: Array = []
	var normals: Array = []
	for raw in samples:
		var sample: Vector3 = raw
		var centre := (sample.x + sample.y) * 0.5
		var half := maxf(to_units((sample.y - sample.x) * 0.5), 0.20)
		path.append(Vector3(
			to_units(centre - _course_width * 0.5),
			deck_height(centre, sample.z) - sink,
			to_units(sample.z)))
		var built: Array = Geo.channel_section(
			half, CHANNEL_DROP, wall, CHANNEL_FILLET, CHANNEL_ROUNDS)
		sections.append(built[0])
		normals.append(built[1])

	var body := MeshInstance3D.new()
	body.name = "Body"
	body.mesh = Geo.sweep_profiles(path, sections, normals, cap)
	body.material_override = _palette.track()
	root.add_child(body)

	if rails:
		_build_rails(root, path, sections)
	_build_channel_supports(root, path, sections, section)
	if section != "throat":
		_build_fascia(root, path, sections)
		_build_channel_accent(root, path, sections, section)
	if section == "chute":
		_build_splitter(root)


func _build_fascia(root: Node3D, path: Array, sections: Array) -> void:
	## A warm beam under the running surface, down the whole component.
	##
	## The reference's own construction, measured off it: every beam in the
	## concept is a thin bright top lip - about an eighth of the deck's depth
	## - standing on a much deeper *brass* fascia, and that fascia is where a
	## third of the image's warm coverage lives. A machine whose channels are
	## one cream extrusion top to bottom cannot get there, and this scene's
	## first passes could not: warmth was a light and a handful of clamps, and
	## the frame came out monochrome cream.
	##
	## It is also what gives a component thickness. A pearl channel on its own
	## reads as a shell of no particular depth; the same channel with a dark
	## warm beam under it reads as a moulded part on a chassis.
	var fascia_path: Array = []
	var profiles: Array = []
	var normals: Array = []
	for index in path.size():
		var profile: Array = sections[index]
		var half := 0.0
		for raw in profile:
			half = maxf(half, absf((raw as Vector2).x))
		var here: Vector3 = path[index]
		fascia_path.append(Vector3(
			here.x, here.y - CHANNEL_DROP - FASCIA_DEPTH * 0.42, here.z))
		var built: Array = Geo.beam_section(
			maxf(half - 0.035, 0.06), FASCIA_DEPTH, 0.075, 3)
		profiles.append(built[0])
		normals.append(built[1])

	var beam := MeshInstance3D.new()
	beam.name = "Fascia"
	beam.mesh = Geo.sweep_profiles(fascia_path, profiles, normals, true)
	beam.material_override = _palette.hardware()
	root.add_child(beam)

	# And under the brass, the keel: a deep dark beam, which is the half of
	# the reference's hierarchy this scene was missing entirely. Its concept
	# holds structure at value 0.15 against a track at 0.75 - a one-to-five
	# ratio - and that ratio is *why* a light track reads as a light track.
	# Before this the machine was cream on cream from its running surface to
	# its underside and the only dark thing in frame was the room, so the
	# components had no thickness and the picture had no anchor.
	var keel_path: Array = []
	var keel_profiles: Array = []
	var keel_normals: Array = []
	for index in path.size():
		var here: Vector3 = fascia_path[index]
		var profile: Array = profiles[index]
		var half := 0.0
		for raw in profile:
			half = maxf(half, absf((raw as Vector2).x))
		keel_path.append(Vector3(
			here.x, here.y - FASCIA_DEPTH * 0.5 - KEEL_DEPTH * 0.5, here.z))
		var built: Array = Geo.beam_section(
			maxf(half * KEEL_INSET, 0.05), KEEL_DEPTH, 0.09, 3)
		keel_profiles.append(built[0])
		keel_normals.append(built[1])

	var keel := MeshInstance3D.new()
	keel.name = "Keel"
	keel.mesh = Geo.sweep_profiles(keel_path, keel_profiles, keel_normals, true)
	keel.material_override = _palette.structure()
	root.add_child(keel)


func _build_splitter(root: Node3D) -> void:
	## The moulded island between the two feed spouts.
	##
	## The envelope that guarantees a floor under every racer also merges the
	## chute's two spouts and the wedge between them into one surface, and
	## that surface is then the largest pale area in the frame - which is the
	## exact complaint the V1.1 report ends on, made worse. The island puts
	## the wedge back as a raised moulded form: the support underneath is
	## untouched, and the eye sees two channels either side of a nose instead
	## of one apron.
	##
	## Its outline is the course's own, read the way the envelope is read:
	## where a sampled height has two clear spans, the gap between them is
	## the wedge.
	var bounds := _section_bounds("chute")
	if bounds == Vector2.ZERO:
		return
	var steps := maxi(2, int((bounds.y - bounds.x) / CHANNEL_STEP))
	var raw: Array = []
	for step in steps + 1:
		var y := bounds.x + float(step) * (bounds.y - bounds.x) / float(steps)
		var spans := _clear_spans("chute", y)
		if spans.size() < 2:
			continue
		var left: Vector2 = spans[0]
		var right: Vector2 = spans[spans.size() - 1]
		if right.x - left.y < 40.0:
			continue
		raw.append(Vector3(left.y - 6.0, right.x + 6.0, y))
	if raw.size() < 3:
		return
	var samples := _smooth(raw)

	var path: Array = []
	var profiles: Array = []
	var normals: Array = []
	for entry in samples:
		var sample: Vector3 = entry
		var centre := (sample.x + sample.y) * 0.5
		var half := maxf(to_units((sample.y - sample.x) * 0.5), 0.10)
		path.append(Vector3(
			to_units(centre - _course_width * 0.5),
			deck_height(centre, sample.z) + 0.02,
			to_units(sample.z)))
		# A dome rather than a channel: the same builder with the wall height
		# negated, so the island carries the fillet radius everything else on
		# the machine carries.
		var built: Array = Geo.channel_section(
			half, 0.02, -minf(half * 0.62, 0.42), minf(half * 0.40, 0.16),
			CHANNEL_ROUNDS)
		profiles.append(built[0])
		normals.append(built[1])

	var island := MeshInstance3D.new()
	island.name = "Splitter"
	island.mesh = Geo.sweep_profiles(path, profiles, normals, true)
	island.material_override = _palette.shell()
	root.add_child(island)

	var crest := MeshInstance3D.new()
	crest.name = "SplitterCrest"
	var line: Array = []
	for entry in path:
		var here: Vector3 = entry
		line.append(Vector3(here.x, here.y - 0.30, here.z))
	crest.mesh = Geo.tube(line, 0.05, 8)
	crest.material_override = _palette.underlight()
	crest.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	root.add_child(crest)


func _build_channel_accent(root: Node3D, path: Array, sections: Array,
		section: String) -> void:
	## A lit strip let into the outside of each wall.
	##
	## Colour on the component itself rather than only in the air around it,
	## and warm below the bowl and cool above it - the same ramp the zone
	## lights carry, so a paused frame has the gradient even where no
	## practical reaches. It runs on the *outside* of the wall, where it draws
	## the component's silhouette without putting light on the surface a
	## marble is read against.
	var warm := section == "bridge" or section == "finish" or section == "throat"
	for raw_side in [-1.0, 1.0]:
		var side: float = raw_side
		var line: Array = []
		for index in path.size():
			var profile: Array = sections[index]
			var half := 0.0
			for raw in profile:
				half = maxf(half, absf((raw as Vector2).x))
			var centre: Vector3 = path[index]
			line.append(Vector3(
				centre.x + side * (half + 0.012),
				centre.y - CHANNEL_DROP * 0.42,
				centre.z))
		var strip := MeshInstance3D.new()
		strip.name = "Accent%s" % ("R" if side > 0.0 else "L")
		strip.mesh = Geo.tube(line, 0.036, 8)
		strip.material_override = (
			_palette.underlight() if warm else _palette.light_ring(false))
		strip.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		root.add_child(strip)


func _build_rails(root: Node3D, path: Array, sections: Array) -> void:
	## An acrylic bar along the top of each wall.
	##
	## Round stock rather than a square strip, and translucent rather than
	## painted: it is the one place on a channel where the light can pass
	## through the component, and a lit edge running the length of a curve is
	## most of what makes the curve read at phone size.
	for side in [-1.0, 1.0]:
		var line: Array = []
		for index in path.size():
			var section: Array = sections[index]
			var half := 0.0
			for raw in section:
				half = maxf(half, absf((raw as Vector2).x))
			var centre: Vector3 = path[index]
			line.append(Vector3(
				centre.x, centre.y, centre.z))
			var last: int = line.size() - 1
			line[last] = Vector3(
				centre.x + side * (half - RAIL_INSET),
				centre.y + RAIL_LIFT,
				centre.z)
		var bar := MeshInstance3D.new()
		bar.name = "Rail%s" % ("R" if side > 0.0 else "L")
		bar.mesh = Geo.tube(line, RAIL_RADIUS, 10)
		bar.material_override = _palette.acrylic_rim()
		bar.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		root.add_child(bar)


func _build_channel_supports(root: Node3D, path: Array, sections: Array,
		section: String) -> void:
	## Rounded legs under a raised component, with warm hardware at the joint.
	##
	## The brief asks for elegant supports and a visible underside. A post is
	## also the cheapest depth cue there is: a component with air and a shadow
	## under it is an object, and the same component lying on a floor is a
	## marking. Only the stretches that are actually in the air get them.
	if section != "bridge" and section != "finish":
		return
	var spacing := maxi(6, int(path.size() / 4))
	for index in range(spacing / 2, path.size(), spacing):
		var here: Vector3 = path[index]
		var section_points: Array = sections[index]
		var half := 0.0
		for raw in section_points:
			half = maxf(half, absf((raw as Vector2).x))

		var top := here.y - CHANNEL_DROP
		var leg := MeshInstance3D.new()
		leg.name = "Leg%d" % index
		leg.mesh = Geo.tube([
			Vector3(here.x, top, here.z),
			Vector3(here.x, ROOM_FLOOR_Y + 0.35, here.z),
		], LEG_RADIUS, 12)
		leg.material_override = _palette.structure(true)
		root.add_child(leg)

		var collar := MeshInstance3D.new()
		collar.name = "Collar%d" % index
		collar.mesh = Geo.rounded_disc(LEG_RADIUS * 2.1, 0.16, 0.05, 24, 3)
		collar.material_override = _palette.hardware()
		collar.position = Vector3(here.x, top - 0.10, here.z)
		root.add_child(collar)

		var foot := MeshInstance3D.new()
		foot.name = "Foot%d" % index
		foot.mesh = Geo.rounded_disc(0.46, 0.20, 0.08, 28, 3)
		foot.material_override = _palette.structure()
		foot.position = Vector3(here.x, ROOM_FLOOR_Y + 0.32, here.z)
		root.add_child(foot)

		for side in [-1.0, 1.0]:
			var brace := MeshInstance3D.new()
			brace.name = "Brace%d%s" % [index, "R" if side > 0.0 else "L"]
			brace.mesh = Geo.tube([
				Vector3(here.x + side * (half - 0.06), here.y - 0.08, here.z),
				Vector3(here.x, top - 1.30, here.z),
			], 0.055, 8)
			brace.material_override = _palette.structure(true)
			brace.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			root.add_child(brace)


# --- the bowl -------------------------------------------------------------

func _bowl_centre() -> Vector3:
	return Vector3(
		to_units(_bowl_cx - _course_width * 0.5), 0.0, to_units(_bowl_cy))


func _build_bowl() -> void:
	## The hero object, in five layers.
	##
	## Outward from the marbles: a pearl running surface, a filleted rim, an
	## aqua acrylic wall standing on that rim, a lit ring under it, and a dark
	## cradle outside everything with warm hardware on it. That layering is
	## the brief's, and each layer is a different material class - moulded,
	## metal, transparent, emissive, metal - so the vessel reads as assembled
	## from parts rather than turned from one billet.
	##
	## The running surface is generated from `bowl_surface_y` at every vertex,
	## exactly as the neon bowl is, which is what guarantees a marble rests on
	## it rather than in it however the physics behaves.
	var root := Node3D.new()
	root.name = "Bowl"
	add_child(root)

	var centre := _bowl_centre()
	var radius := to_units(_bowl_r)
	var drain := to_units(_drain_half)

	# The running surface, from the drain out to the flange.
	var points: Array = []
	var normals: Array = []
	for step in BOWL_RINGS + 1:
		var rho := lerpf(drain / radius, FLANGE_OUTER, float(step) / float(BOWL_RINGS))
		points.append(Vector2(rho * radius, bowl_surface_y(rho)))
	normals = Geo.profile_normals(points, false)
	var basin := MeshInstance3D.new()
	basin.name = "Basin"
	basin.mesh = Geo.lathe(points, normals, BOWL_SEGMENTS)
	basin.material_override = _palette.bowl_surface()
	basin.position = centre
	root.add_child(basin)

	_build_basin_underside(root, centre, radius, drain)
	_build_basin_band(root, centre, radius)
	_build_bowl_rim(root, centre, radius)
	_build_bowl_glass(root, centre, radius)
	_build_bowl_ring(root, centre, radius)
	_build_bowl_cradle(root, centre, radius)
	_build_drain(root, centre, drain)
	_build_bowl_lights(root, centre, radius)


func _build_basin_underside(root: Node3D, centre: Vector3, radius: float,
		drain: float) -> void:
	## The outside of the vessel: a dark moulded shell under the pearl basin.
	##
	## Without it the running surface is a single-sided lathe, and every lens
	## low enough to see the bowl from outside - which is every bowl hero
	## there is - sees the *back* of the surface the marbles run on. It
	## renders as a huge unshaded white curve, which is why the vessel read as
	## a bathtub rather than as a component with a wall thickness.
	##
	## Offset below the running surface by the wall's own thickness, so the
	## two are a moulded part with a gap between its faces rather than one
	## infinitely thin sheet, and dark, because the brief's layering puts a
	## dark support under the pearl and because a pale bowl on a pale stand on
	## a pale feed is the monochrome frame this whole revision is escaping.
	var points: Array = []
	for step in BOWL_RINGS + 1:
		var rho := lerpf(
			drain / radius, FLANGE_OUTER, float(step) / float(BOWL_RINGS))
		points.append(Vector2(rho * radius, bowl_surface_y(rho) - BOWL_WALL))
	var under := MeshInstance3D.new()
	under.name = "BasinUnderside"
	under.mesh = Geo.lathe(
		points, Geo.profile_normals(points, true), BOWL_SEGMENTS)
	under.material_override = _palette.structure(true)
	under.position = centre
	root.add_child(under)

	# The lip that closes the two faces at the flange.
	var edge: Array = [
		Vector2(radius * FLANGE_OUTER, bowl_surface_y(FLANGE_OUTER)),
		Vector2(radius * FLANGE_OUTER,
			bowl_surface_y(FLANGE_OUTER) - BOWL_WALL),
	]
	var band := MeshInstance3D.new()
	band.name = "BasinEdge"
	band.mesh = Geo.lathe(
		edge, Geo.profile_normals(edge, true), BOWL_SEGMENTS)
	band.material_override = _palette.hardware()
	band.position = centre
	root.add_child(band)


func _build_basin_band(root: Node3D, centre: Vector3, radius: float) -> void:
	## A concentric moulded step around the basin, and a warm ring below it.
	##
	## The vessel is the largest single surface in every hero frame and, with
	## one material across the whole lathe, the largest *blank* one - a hero
	## object whose middle sixty percent has nothing on it. A moulded bowl has
	## a step in it: a tooling line where the wall's radius changes, which on
	## a real part is where the draft angle changes and in a render is a
	## continuous highlight running all the way round.
	##
	## Two of them, one cool high on the wall and one warm low, so the basin
	## carries the machine's own two accents where the marbles are read
	## against it, and the step nearest the drain is the warm one - the same
	## ramp everything else on the machine follows.
	for entry in [
			{"rho": 0.72, "warm": false, "width": 0.055},
			{"rho": 0.44, "warm": true, "width": 0.042}]:
		var rho: float = entry["rho"]
		var warm: bool = entry["warm"]
		var width: float = entry["width"]
		var points: Array = []
		for step in 11:
			var a := float(step) / 10.0 * PI
			points.append(Vector2(
				rho * radius + width * sin(a),
				bowl_surface_y(rho) + 0.02 + width * 0.72 * cos(a)))
		var band := MeshInstance3D.new()
		band.name = "BasinBand%d" % int(rho * 100.0)
		band.mesh = Geo.lathe(points, Geo.profile_normals(points, true), 88)
		band.material_override = _palette.light_ring(warm)
		band.position = centre
		band.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		root.add_child(band)


func _build_bowl_rim(root: Node3D, centre: Vector3, radius: float) -> void:
	## A filleted lip the acrylic stands on, and the clamps around it.
	var lip := H_RIM + RIM_RISE
	var points: Array = [
		Vector2(radius * FLANGE_OUTER, H_RIM),
		Vector2(radius * (FLANGE_OUTER + 0.02), H_RIM + RIM_RISE * 0.45),
		Vector2(radius * (FLANGE_OUTER + 0.055), lip),
		Vector2(radius * (FLANGE_OUTER + 0.09), H_RIM + RIM_RISE * 0.45),
		Vector2(radius * (FLANGE_OUTER + 0.10), H_RIM - RIM_THICKNESS),
		Vector2(radius * (FLANGE_OUTER + 0.02), H_RIM - RIM_THICKNESS - 0.06),
	]
	var rim := MeshInstance3D.new()
	rim.name = "Rim"
	rim.mesh = Geo.lathe(points, Geo.profile_normals(points, true), BOWL_SEGMENTS)
	rim.material_override = _palette.hardware()
	rim.position = centre
	root.add_child(rim)

	# Warm clamps around the lip. Small, machined, and the first place a
	# viewer's eye finds warm metal on the hero object.
	for index in RIM_CLAMPS:
		var angle := TAU * float(index) / float(RIM_CLAMPS)
		var at := radius * (FLANGE_OUTER + 0.06)
		var clamp_node := MeshInstance3D.new()
		clamp_node.name = "Clamp%d" % index
		clamp_node.mesh = Geo.rounded_box(
			Vector3(0.20, 0.16, 0.34), 0.055, 3)
		clamp_node.material_override = _palette.hardware()
		clamp_node.position = centre + Vector3(
			at * cos(angle), H_RIM - 0.02, at * sin(angle))
		clamp_node.rotation.y = -angle
		root.add_child(clamp_node)


func _build_bowl_glass(root: Node3D, centre: Vector3, radius: float) -> void:
	## The acrylic wall standing on the rim, open towards the lens.
	##
	## The brief asks for the acrylic to be unmistakable at phone size and in
	## the same breath asks not to put translucent geometry between the camera
	## and every racer. Both, by leaving the near quarter open: the wall is
	## unbroken across the far three quarters where it is silhouetted against
	## the backdrop and takes a Fresnel edge all the way round, and it is
	## simply absent where it would otherwise sit in front of the field.
	##
	## The rim bar at its top is a solid, slightly emissive part rather than
	## more glass, because a transparent edge one pixel wide at phone scale is
	## no edge at all. That bar is what survives the downscale.
	var near := atan2(-1.0, 0.0)          # the point of the disc nearest the lens
	var gap := deg_to_rad(GLASS_GAP_HALF)
	var from_angle := near + gap
	var to_angle := near + TAU - gap

	var points: Array = []
	for step in GLASS_ROUNDS + 1:
		var t := float(step) / float(GLASS_ROUNDS)
		# Flared: the wall leans outward as it rises, which is what turns a
		# cylinder into a vessel and gives the Fresnel somewhere to run.
		var rho := FLANGE_OUTER + 0.055 + GLASS_FLARE * t * t
		points.append(Vector2(radius * rho, H_RIM + RIM_RISE + GLASS_RISE * t))
	var wall := MeshInstance3D.new()
	wall.name = "Acrylic"
	wall.mesh = Geo.lathe(
		points, Geo.profile_normals(points, true), 72, from_angle, to_angle)
	wall.material_override = _palette.acrylic(0.33)
	wall.position = centre
	wall.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	root.add_child(wall)

	var top: Vector2 = points[points.size() - 1]
	var bar_points: Array = []
	for step in 25:
		var angle := lerpf(from_angle, to_angle, float(step) / 24.0)
		bar_points.append(centre + Vector3(
			top.x * cos(angle), top.y, top.x * sin(angle)))
	var bar := MeshInstance3D.new()
	bar.name = "AcrylicRim"
	bar.mesh = Geo.tube(bar_points, 0.062, 10)
	bar.material_override = _palette.acrylic_rim()
	bar.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	root.add_child(bar)

	# Mullions at the two open ends, so the wall terminates in a moulded post
	# rather than in a cut edge.
	for angle in [from_angle, to_angle]:
		var post := MeshInstance3D.new()
		post.name = "Mullion%d" % int(rad_to_deg(angle))
		post.mesh = Geo.tube([
			centre + Vector3(
				(points[0] as Vector2).x * cos(angle),
				(points[0] as Vector2).y, (points[0] as Vector2).x * sin(angle)),
			centre + Vector3(top.x * cos(angle), top.y, top.x * sin(angle)),
		], 0.058, 10)
		post.material_override = _palette.hardware()
		root.add_child(post)


func _build_bowl_ring(root: Node3D, centre: Vector3, radius: float) -> void:
	## The coloured light ring under the rim: the bowl's zone colour.
	var points: Array = []
	for step in 15:
		var t := float(step) / 14.0 * PI
		points.append(Vector2(
			radius * RING_RHO + 0.27 * sin(t),
			H_RIM - RING_DROP + 0.34 * cos(t)))
	var ring := MeshInstance3D.new()
	ring.name = "LightRing"
	ring.mesh = Geo.lathe(points, Geo.profile_normals(points, true), 80)
	ring.material_override = _palette.light_ring(false)
	ring.position = centre
	ring.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	root.add_child(ring)


func _build_bowl_cradle(root: Node3D, centre: Vector3, radius: float) -> void:
	## The dark support outside everything, and the warm lamps on it.
	var hoop_points: Array = []
	for step in 33:
		var angle := TAU * float(step) / 32.0
		hoop_points.append(centre + Vector3(
			radius * CRADLE_RHO * cos(angle),
			H_RIM - CRADLE_DROP,
			radius * CRADLE_RHO * sin(angle)))
	var hoop := MeshInstance3D.new()
	hoop.name = "CradleHoop"
	hoop.mesh = Geo.tube(hoop_points, 0.13, 12)
	hoop.material_override = _palette.cradle()
	root.add_child(hoop)

	for index in CRADLE_LEGS:
		var angle := TAU * float(index) / float(CRADLE_LEGS) + PI / float(CRADLE_LEGS)
		var at := radius * CRADLE_RHO
		var top := centre + Vector3(
			at * cos(angle), H_RIM - CRADLE_DROP, at * sin(angle))

		var arm := MeshInstance3D.new()
		arm.name = "CradleArm%d" % index
		arm.mesh = Geo.tube([
			top,
			centre + Vector3(
				radius * (FLANGE_OUTER + 0.02) * cos(angle),
				H_RIM - RIM_THICKNESS - 0.04,
				radius * (FLANGE_OUTER + 0.02) * sin(angle)),
		], 0.075, 10)
		arm.material_override = _palette.cradle()
		root.add_child(arm)

		var leg := MeshInstance3D.new()
		leg.name = "CradleLeg%d" % index
		leg.mesh = Geo.tube([
			top,
			centre + Vector3(
				at * 1.16 * cos(angle), ROOM_FLOOR_Y + 0.35, at * 1.16 * sin(angle)),
		], 0.115, 12)
		leg.material_override = _palette.structure()
		root.add_child(leg)

		var lamp := MeshInstance3D.new()
		lamp.name = "CradleLamp%d" % index
		lamp.mesh = Geo.rounded_disc(0.15, 0.10, 0.04, 20, 3)
		lamp.material_override = _palette.underlight()
		lamp.position = top + Vector3(0.0, -0.14, 0.0)
		lamp.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		root.add_child(lamp)


func _build_drain(root: Node3D, centre: Vector3, drain: float) -> void:
	## The hole the field leaves through, as a moulded collar over a well.
	var points: Array = [
		Vector2(drain * 0.92, bowl_surface_y(0.0) + 0.02),
		Vector2(drain, bowl_surface_y(0.0) - 0.02),
		Vector2(drain, bowl_surface_y(0.0) - DRAIN_WELL_DEPTH),
	]
	var well := MeshInstance3D.new()
	well.name = "DrainWell"
	well.mesh = Geo.lathe(points, Geo.profile_normals(points, false), 64)
	well.material_override = _palette.structure()
	well.position = centre
	root.add_child(well)

	var collar_points: Array = []
	for step in 13:
		var t := float(step) / 12.0 * PI
		collar_points.append(Vector2(
			drain * 1.03 + 0.085 * sin(t),
			bowl_surface_y(0.0) + 0.085 * cos(t)))
	var collar := MeshInstance3D.new()
	collar.name = "DrainCollar"
	collar.mesh = Geo.lathe(
		collar_points, Geo.profile_normals(collar_points, true), 64)
	collar.material_override = _palette.light_ring(true)
	collar.position = centre
	collar.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	root.add_child(collar)


func _build_bowl_lights(root: Node3D, centre: Vector3, radius: float) -> void:
	## Two practicals: warm under the cradle, cool inside the vessel.
	var under := OmniLight3D.new()
	under.name = "BowlUnderLight"
	under.light_color = _palette.color("accent_warm")
	under.light_energy = 3.20
	under.omni_range = radius * 3.2
	under.omni_attenuation = 1.4
	under.shadow_enabled = false
	under.position = centre + Vector3(0.0, H_RIM - CRADLE_DROP - 0.30, 0.0)
	root.add_child(under)

	var inside := OmniLight3D.new()
	inside.name = "BowlFillLight"
	inside.light_color = _palette.color("accent_cool")
	inside.light_energy = 3.40
	inside.omni_range = radius * 2.6
	inside.omni_attenuation = 1.7
	inside.shadow_enabled = false
	inside.position = centre + Vector3(0.0, H_RIM + GLASS_RISE * 0.6, 0.0)
	root.add_child(inside)


# --- the start platform ---------------------------------------------------

func _build_start_platform() -> void:
	## A raised display platform: the racers are on show before they run.
	##
	## The brief asks for the marbles to look like collectible pieces sitting
	## inside a toy, so the platform is a display case rather than a launch
	## apron - a rounded pearl shell with a recessed bay, acrylic guards down
	## both sides, a warm-lit fascia and a sign over it.
	var root := Node3D.new()
	root.name = "StartPlatform"
	add_child(root)

	var left := to_units(_platform_left - PLATFORM_OVERHANG - _course_width * 0.5)
	var right := to_units(_platform_right + PLATFORM_OVERHANG - _course_width * 0.5)
	var back := to_units(_platform_top - PLATFORM_OVERHANG)
	var front := to_units(_gate_y)
	var width := right - left
	var depth := front - back
	var mid_x := (left + right) * 0.5
	var mid_z := (back + front) * 0.5

	var body := MeshInstance3D.new()
	body.name = "Shell"
	body.mesh = Geo.rounded_box(
		Vector3(width, PLATFORM_THICKNESS, depth), PLATFORM_FILLET, 5)
	# Dark, with the pearl bay let into it. The first pass made the whole
	# block cream and it became the largest pale surface in the establishing
	# frame - which is the complaint the V1.1 report closes on, reproduced.
	body.material_override = _palette.structure()
	body.position = Vector3(mid_x, H_START - PLATFORM_THICKNESS * 0.5, mid_z)
	root.add_child(body)

	# The bay the racers sit in: a shallower rounded box let into the shell,
	# in the running surface's own material so the platform reads as a case
	# with a floor rather than as a solid block.
	var bay := MeshInstance3D.new()
	bay.name = "Bay"
	bay.mesh = Geo.rounded_box(
		Vector3(width - 0.60, BAY_RECESS * 2.0, depth - 0.44), 0.09, 4)
	bay.material_override = _palette.track()
	bay.position = Vector3(mid_x, H_START - BAY_RECESS, mid_z)
	root.add_child(bay)

	var lip := MeshInstance3D.new()
	lip.name = "BayLip"
	lip.mesh = Geo.rounded_box(
		Vector3(width - 0.34, 0.10, depth - 0.20), 0.045, 3)
	lip.material_override = _palette.hardware()
	lip.position = Vector3(mid_x, H_START - BAY_RECESS - 0.05, mid_z)
	root.add_child(lip)

	# Acrylic guards down both sides. Side walls rather than a front pane, so
	# nothing translucent sits between the lens and the field.
	for side in [-1.0, 1.0]:
		var guard := MeshInstance3D.new()
		guard.name = "Guard%s" % ("R" if side > 0.0 else "L")
		guard.mesh = Geo.rounded_box(
			Vector3(0.10, GUARD_HEIGHT, depth - 0.30), 0.045, 3)
		guard.material_override = _palette.acrylic(0.26)
		guard.position = Vector3(
			mid_x + side * (width * 0.5 - 0.16),
			H_START + GUARD_HEIGHT * 0.5 - BAY_RECESS, mid_z)
		guard.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		root.add_child(guard)

		var cap := MeshInstance3D.new()
		cap.name = "GuardCap%s" % ("R" if side > 0.0 else "L")
		cap.mesh = Geo.tube([
			Vector3(mid_x + side * (width * 0.5 - 0.16),
				H_START + GUARD_HEIGHT - BAY_RECESS, back + 0.20),
			Vector3(mid_x + side * (width * 0.5 - 0.16),
				H_START + GUARD_HEIGHT - BAY_RECESS, front - 0.10),
		], 0.05, 10)
		cap.material_override = _palette.acrylic_rim()
		cap.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		root.add_child(cap)

	# The fascia: a rounded warm-lit beam under the front lip. The machine's
	# face, and the brief's "rounded front fascia".
	var fascia := MeshInstance3D.new()
	fascia.name = "Fascia"
	fascia.mesh = Geo.rounded_box(
		Vector3(width - 0.20, FASCIA_HEIGHT, 0.30), 0.11, 4)
	fascia.material_override = _palette.structure(true)
	fascia.position = Vector3(
		mid_x, H_START - PLATFORM_THICKNESS - FASCIA_HEIGHT * 0.35, front - 0.14)
	root.add_child(fascia)

	var strip := MeshInstance3D.new()
	strip.name = "FasciaLight"
	strip.mesh = Geo.rounded_box(
		Vector3(width - 0.80, 0.09, 0.10), 0.035, 3)
	strip.material_override = _palette.underlight()
	strip.position = Vector3(
		mid_x, H_START - PLATFORM_THICKNESS - FASCIA_HEIGHT * 0.35, front - 0.30)
	strip.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	root.add_child(strip)

	# Four rounded legs, so the platform is standing rather than floating.
	for raw_sx in [-1.0, 1.0]:
		for raw_sz in [-1.0, 1.0]:
			var sx: float = raw_sx
			var sz: float = raw_sz
			var leg := MeshInstance3D.new()
			leg.name = "Leg%d%d" % [int(sx), int(sz)]
			var x: float = mid_x + sx * (width * 0.5 - 0.44)
			var z: float = mid_z + sz * (depth * 0.5 - 0.44)
			leg.mesh = Geo.tube([
				Vector3(x, H_START - PLATFORM_THICKNESS, z),
				Vector3(x, ROOM_FLOOR_Y + 0.35, z),
			], LEG_RADIUS, 12)
			leg.material_override = _palette.structure()
			root.add_child(leg)

	_build_start_gate(root, left, right, front)
	_build_start_sign(root, mid_x, back, width)


func _build_start_gate(root: Node3D, left: float, right: float,
		front: float) -> void:
	## The release: two rounded blades that drop clear as the floor is removed.
	var housing := MeshInstance3D.new()
	housing.name = "GateHousing"
	housing.mesh = Geo.rounded_box(
		Vector3(right - left, 0.26, 0.26), 0.10, 4)
	housing.material_override = _palette.structure(true)
	housing.position = Vector3((left + right) * 0.5, H_START + 0.30, front)
	root.add_child(housing)

	var half := (right - left) * 0.5
	for side in [-1.0, 1.0]:
		var blade := Node3D.new()
		blade.name = "GateBlade%s" % ("R" if side > 0.0 else "L")
		blade.position = Vector3(
			(left + right) * 0.5 + side * half * 0.5, H_START + 0.06, front)
		root.add_child(blade)

		var panel := MeshInstance3D.new()
		panel.name = "Panel"
		panel.mesh = Geo.rounded_box(
			Vector3(half * 0.98, GATE_HEIGHT, 0.11), 0.048, 3)
		panel.material_override = _palette.accent(true)
		blade.add_child(panel)

		_shutter_leaves.append(blade)
		_shutter_home.append(blade.position.y)


func _build_start_sign(root: Node3D, mid_x: float, back: float,
		width: float) -> void:
	## A rounded sign on two posts. The title card of the machine.
	for raw_side in [-1.0, 1.0]:
		var side: float = raw_side
		var post := MeshInstance3D.new()
		post.name = "SignPost%s" % ("R" if side > 0.0 else "L")
		var x: float = mid_x + side * (SIGN_SIZE.x * 0.5 - 0.10)
		post.mesh = Geo.tube([
			Vector3(x, H_START + 0.05, back + 0.30),
			Vector3(x, H_START + SIGN_RISE, back + 0.30),
		], 0.075, 10)
		post.material_override = _palette.hardware()
		root.add_child(post)

	var board := MeshInstance3D.new()
	board.name = "SignBoard"
	board.mesh = Geo.rounded_box(SIGN_SIZE, 0.16, 5)
	board.material_override = _palette.shell()
	board.position = Vector3(mid_x, H_START + SIGN_RISE, back + 0.30)
	root.add_child(board)

	var face := MeshInstance3D.new()
	face.name = "SignFace"
	face.mesh = Geo.rounded_box(
		Vector3(SIGN_SIZE.x - 0.28, SIGN_SIZE.y - 0.20, 0.08), 0.06, 4)
	face.material_override = _palette.sign(true)
	face.position = Vector3(mid_x, H_START + SIGN_RISE, back + 0.16)
	face.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	root.add_child(face)

	var label := Label3D.new()
	label.name = "SignText"
	label.text = "START"
	label.font_size = 150
	label.pixel_size = 0.0034
	label.shaded = false
	label.double_sided = false
	label.alpha_cut = Label3D.ALPHA_CUT_DISCARD
	label.modulate = Color(0.06, 0.10, 0.14)
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	label.position = Vector3(mid_x, H_START + SIGN_RISE, back + 0.10)
	label.render_priority = 3
	root.add_child(label)


# --- the mechanical toy element -------------------------------------------

func _build_element() -> void:
	## One rotating distributor, in a rounded casing with a warm hub.
	##
	## The brief asks for exactly one moving machine part, to establish the
	## visual vocabulary for machinery: rounded casing, warm mechanical
	## accent, visible centre hub, satisfying silhouette. It is decorative -
	## nothing races through it - because a frozen replay cannot be changed by
	## a new obstacle and this phase is not allowed to add one.
	var root := Node3D.new()
	root.name = "Distributor"
	add_child(root)

	var z := to_units(ELEMENT_Z)
	var y := deck_height(_bowl_cx, ELEMENT_Z) + 0.55
	var base := Vector3(ELEMENT_OFFSET, y, z)

	var casing := MeshInstance3D.new()
	casing.name = "Casing"
	casing.mesh = Geo.rounded_disc(
		ELEMENT_RADIUS, ELEMENT_CASING, 0.11, 56, 4)
	casing.material_override = _palette.shell()
	casing.position = base
	root.add_child(casing)

	var ring := MeshInstance3D.new()
	ring.name = "CasingRing"
	var hoop: Array = []
	for step in 41:
		var angle := TAU * float(step) / 40.0
		hoop.append(base + Vector3(
			ELEMENT_RADIUS * 0.96 * cos(angle),
			ELEMENT_CASING * 0.5,
			ELEMENT_RADIUS * 0.96 * sin(angle)))
	ring.mesh = Geo.tube(hoop, 0.055, 10)
	ring.material_override = _palette.light_ring(true)
	ring.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	root.add_child(ring)

	# The rotor: the one node in this scene whose transform is a function of
	# the playhead and not of the replay's contents.
	_element = Node3D.new()
	_element.name = "Rotor"
	_element.position = base + Vector3(0.0, ELEMENT_CASING * 0.55, 0.0)
	root.add_child(_element)

	for index in ELEMENT_BLADES:
		var angle := TAU * float(index) / float(ELEMENT_BLADES)
		var blade := MeshInstance3D.new()
		blade.name = "Blade%d" % index
		blade.mesh = Geo.rounded_box(
			Vector3(0.20, 0.14, ELEMENT_RADIUS * 1.30), 0.062, 4)
		blade.material_override = _palette.accent(false)
		blade.position = Vector3(
			ELEMENT_RADIUS * 0.44 * sin(angle), 0.0,
			ELEMENT_RADIUS * 0.44 * cos(angle))
		blade.rotation.y = angle
		_element.add_child(blade)

	var hub := MeshInstance3D.new()
	hub.name = "Hub"
	hub.mesh = Geo.rounded_disc(ELEMENT_HUB, 0.22, 0.07, 32, 4)
	hub.material_override = _palette.hardware()
	_element.add_child(hub)

	var column := MeshInstance3D.new()
	column.name = "Column"
	column.mesh = Geo.tube([
		base + Vector3(0.0, -ELEMENT_CASING * 0.5, 0.0),
		Vector3(base.x, ROOM_FLOOR_Y + 0.35, base.z),
	], 0.16, 12)
	column.material_override = _palette.structure()
	root.add_child(column)

	var foot := MeshInstance3D.new()
	foot.name = "Foot"
	foot.mesh = Geo.rounded_disc(0.50, 0.22, 0.09, 28, 3)
	foot.material_override = _palette.structure(true)
	foot.position = Vector3(base.x, ROOM_FLOOR_Y + 0.33, base.z)
	root.add_child(foot)


func _update_element(playhead: float) -> void:
	## A pure function of the playhead, exactly as the gate is.
	if _element == null:
		return
	_element.rotation.y = TAU * ELEMENT_RPS * (playhead / 60.0)


# --- the room -------------------------------------------------------------

func _build_room() -> void:
	## A sweep, two ranks of soft pylons, and a floor. Nothing else.
	##
	## The first pass built a hall - two ranks of pylons close in, a wall of
	## panels, arches over the machine - and every one of those turned into a
	## dark bar crossing the subject. The brief asks explicitly not to model a
	## room and for a small number of large forms, and this is the reading of
	## that which actually photographs: a product sweep behind the machine,
	## far enough back to be a gradient rather than an object, with two ranks
	## of rounded pylons for parallax and a floor for the supports to stand
	## on and cast onto.
	##
	## Everything is pushed much further out than it was. A pylon nine units
	## from a bowl four and a half across is beside the bowl; the same pylon
	## at fourteen is behind it, which is the difference between clutter and
	## depth.
	var root := Node3D.new()
	root.name = "Room"
	add_child(root)

	var top := to_units(_course_top) - 16.0
	var bottom := to_units(_course_bottom) + 18.0

	var floor_node := MeshInstance3D.new()
	floor_node.name = "Floor"
	floor_node.mesh = Geo.rounded_box(
		Vector3(FLOOR_SIZE, 0.8, bottom - top), 0.35, 3)
	floor_node.material_override = _palette.floor_material()
	floor_node.position = Vector3(0.0, ROOM_FLOOR_Y - 0.4, (top + bottom) * 0.5)
	root.add_child(floor_node)

	_build_sweep(root, top, bottom)
	_build_rank(root, "Near", PYLON_NEAR_X, PYLON_NEAR, PYLON_NEAR_SPACING,
		top, bottom, 0)
	_build_rank(root, "Mid", PYLON_MID_X, PYLON_MID, PYLON_MID_SPACING,
		top, bottom, 1)
	_build_room_panels(root, top, bottom)


func _build_room_panels(root: Node3D, top: float, bottom: float) -> void:
	## Large soft panels on the sweep: the room's own light.
	##
	## The brief asks for a background that still feels alive, and a graded
	## dark surface on its own does not - it reads as a photographic backdrop,
	## which is correct for a product shot and wrong for a playroom. Four
	## panels a side, very large, very dim, alternating cool and warm, put
	## light *in* the room rather than only on the machine. They are far
	## enough back to be soft shapes and they never compete: each is under a
	## fifth of the emission of anything on the machine itself.
	##
	## They also carry the zone ramp into the background - cool behind the
	## platform, warm behind the track - so a paused frame's environment is
	## the same temperature as the module in front of it.
	var count := 5
	for step in count:
		var t := float(step) / float(count - 1)
		var z := lerpf(top + 14.0, bottom - 14.0, t)
		var warm := t > 0.5
		for raw_side in [-1.0, 1.0]:
			var side: float = raw_side
			var panel := MeshInstance3D.new()
			panel.name = "RoomPanel%d%s" % [step, "R" if side > 0.0 else "L"]
			# Very large and very far, so they are a wash on the room rather
			# than objects in it. At the size and distance the first pass used
			# they read as coloured cards hanging in mid-air, which is worse
			# than no room light at all.
			panel.mesh = Geo.rounded_box(
				Vector3(0.5, 20.0, 13.0), 2.0, 4)
			panel.material_override = _palette.room_light(warm)
			panel.position = Vector3(
				side * (PYLON_MID_X + 9.0), ROOM_FLOOR_Y + 11.0, z)
			panel.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			root.add_child(panel)


func _build_sweep(root: Node3D, top: float, bottom: float) -> void:
	## The backdrop: one large curved surface, well behind everything.
	##
	## A product sweep rather than a wall of panels. Its whole job is to give
	## the machine something to be silhouetted against that is neither black
	## nor flat - the V1.1 measurement found one quantised colour covering a
	## fifth of the frame - and a single curved surface under a raking key
	## does that on its own, because a curve lit from one side is a gradient
	## by construction.
	var points: Array = []
	for step in 17:
		var t := float(step) / 16.0
		var angle := lerpf(PI * 0.06, PI * 0.94, t)
		points.append(Vector2(
			SWEEP_RADIUS * sin(angle),
			ROOM_FLOOR_Y - 1.0 + SWEEP_HEIGHT * (1.0 - cos(angle)) * 0.5))
	var normals := Geo.profile_normals(points, false)

	var path: Array = []
	var profiles: Array = []
	var frames: Array = []
	var steps := 10
	for step in steps + 1:
		var z := lerpf(top, bottom, float(step) / float(steps))
		path.append(Vector3(0.0, 0.0, z))
		profiles.append(points)
		frames.append(normals)
	var sweep := MeshInstance3D.new()
	sweep.name = "Sweep"
	sweep.mesh = Geo.sweep_profiles(path, profiles, frames, false)
	sweep.material_override = _palette.room(2)
	sweep.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	root.add_child(sweep)


func _build_rank(root: Node3D, tag: String, at_x: float, size: Vector3,
		spacing: float, top: float, bottom: float, distance: int) -> void:
	## One rank of rounded pylons, either side, at a fixed pitch.
	var material := _palette.room(distance)
	var index := 0
	var z := top
	while z < bottom:
		for raw_side in [-1.0, 1.0]:
			var side: float = raw_side
			var pylon := MeshInstance3D.new()
			pylon.name = "Pylon%s%d%s" % [tag, index, "R" if side > 0.0 else "L"]
			pylon.mesh = Geo.rounded_box(size, minf(size.x, size.z) * 0.46, 4)
			pylon.material_override = material
			# Stepped on a fixed cycle so the rank has a profile rather than a
			# picket fence. Deterministic by index: nothing here may randomise.
			var rise: float = [0.0, 1.9, 0.8, 2.7][index % 4]
			pylon.position = Vector3(
				side * at_x, ROOM_FLOOR_Y + size.y * 0.5 - 1.4 + rise, z)
			root.add_child(pylon)
		index += 1
		z += spacing


# --- racers ---------------------------------------------------------------

func _build_racers() -> void:
	## Candy marbles, drawn large, with nothing stuck to them.
	##
	## No number plate. The V1.1 measurement puts a racer's number at about
	## five pixels of cap height at phone scale, which is half the legibility
	## floor - so the plate costs a marble's silhouette and buys nothing. The
	## brief also asks for a plain marble to be made beautiful before any
	## identity treatment is tried, and this is that marble.
	var root := Node3D.new()
	root.name = "Racers"
	add_child(root)

	for index in _racer_meta.size():
		var meta: Dictionary = _racer_meta[index]
		var radius := to_units(float(meta.get("radius", 30.0))) * MARBLE_SCALE

		var pivot := Node3D.new()
		pivot.name = "Racer%d" % int(meta.get("id", index))
		root.add_child(pivot)

		var mesh := SphereMesh.new()
		mesh.radius = radius
		mesh.height = radius * 2.0
		mesh.radial_segments = MARBLE_SEGMENTS
		mesh.rings = MARBLE_RINGS

		var sphere := MeshInstance3D.new()
		sphere.name = "Body"
		sphere.mesh = mesh
		sphere.material_override = _palette.marble(_palette.marble_color(index))
		pivot.add_child(sphere)

		_racer_nodes.append(pivot)
		_racer_spheres.append(sphere)
		_racer_radius.append(radius)


func _update_racers(current: Array, upcoming: Array, blend: float) -> void:
	for index in _racer_nodes.size():
		if index >= current.size():
			continue
		var now: Dictionary = current[index]
		var soon: Dictionary = upcoming[index] if index < upcoming.size() else now
		var pivot := _racer_nodes[index]

		if bool(now.get("retired", false)):
			pivot.visible = false
			continue
		pivot.visible = true

		var x := lerpf(float(now.get("x", 0.0)), float(soon.get("x", 0.0)), blend)
		var y := lerpf(float(now.get("y", 0.0)), float(soon.get("y", 0.0)), blend)
		var spin := lerp_angle(
			deg_to_rad(float(now.get("rotation_degrees", 0.0))),
			deg_to_rad(float(soon.get("rotation_degrees", 0.0))),
			blend)

		pivot.position = to_world(x, y, _racer_radius[index])
		_racer_spheres[index].rotation.y = -spin


func _update_gate(tick: float) -> void:
	if _shutter_leaves.is_empty() or _gate_tick < 0.0:
		return
	var window := SHUTTER_SECONDS * _physics_hz
	var progress := clampf((tick - (_gate_tick - window)) / window, 0.0, 1.0)
	var travel := progress * progress * GATE_HEIGHT * SHUTTER_TRAVEL
	for index in _shutter_leaves.size():
		var blade := _shutter_leaves[index]
		blade.position.y = _shutter_home[index] - travel
		blade.visible = progress < 1.0
