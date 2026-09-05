extends Node3D

## Plays back a race replay exported by the Python simulation.
##
## The sibling of the battle path in `replay_viewer.gd`, and it keeps the same
## contract: Godot is presentation only. It runs no physics and no race rules.
## Every position, every arm angle, every rank and the whole result come out of
## the replay file, and the course is rebuilt from the geometry the replay
## carries rather than by importing anything that knows how a course is built.
##
## ## Two cameras, on purpose
##
## A race is shot on one of two instruments, chosen by `camera_mode`:
##
## `verification` is the orthographic top-down camera V0.2 shipped. One
## simulation pixel is one frame pixel everywhere in the frame, so
## `tools/verify_race_render.py` can take a racer's recorded position, subtract
## the camera track, and look at that exact pixel. It is the only mechanical
## proof that Godot draws the race Python simulated, and it is kept working
## for that reason alone.
##
## `production` is the perspective camera a finished Short is shot on. It has
## depth, which is the whole point and also exactly why it cannot be verified
## the same way: under perspective a racer's screen position depends on how
## high it is standing as well as where it is.
##
## Nothing else in this file changes between the two. The same course, the same
## racers, the same effects, driven by the same replay - only the lens differs,
## which is what makes a verification render evidence about the production one.
##
## ## Everything is a pure function of the replay tick
##
## The offline renderer seeks to `frame / fps` and draws; it never passes a
## delta and never waits on a clock. So nothing here may integrate, accumulate
## or randomise. Trails are rebuilt from replay history, effects are aged
## against the tick they were recorded on, and the camera's framing is computed
## from the frame in front of it. Two renders of one replay are byte-identical,
## and the pipeline checks.

const RaceMaterials := preload("res://scripts/race_materials.gd")
const RaceTrails := preload("res://scripts/race_trails.gd")
const RaceVFX := preload("res://scripts/race_vfx.gd")
const RaceHud := preload("res://scripts/race_hud.gd")

# The single place where logical simulation pixels become Godot world units.
# The same figure the battle scene uses.
const PIXELS_PER_UNIT := 100.0

# The frame, in simulation pixels. The camera track in the replay is the
# course y at the *top* of this window, so the two have to agree.
const VIEW_HEIGHT := 1920.0

const CAMERA_VERIFICATION := "verification"
const CAMERA_PRODUCTION := "production"

# --- the verification camera ---------------------------------------------

const VERIFY_SIZE := VIEW_HEIGHT / PIXELS_PER_UNIT
const VERIFY_HEIGHT := 40.0

# --- the production camera -----------------------------------------------

# Modest, because a wide lens on a portrait frame stretches the corners and
# makes a racer at the edge of the course read as the wrong shape.
const PROD_FOV := 40.0
# How far above the course the lens sits, in degrees off the horizontal.
#
# V0.3 shot at 74 degrees on the argument that a course six times longer than
# it is wide only gets its height back by looking down the length of it. The
# argument is sound and the picture it produced was still wrong: at 74 degrees
# a viewer sees the *plan* of the machine. Every vertical surface is edge-on,
# nothing occludes anything, and a frame paused at random is indistinguishable
# from a diagram - which is exactly the complaint the V0.4 brief opens with.
#
# The replacement was measured rather than argued: `tools/race_camera_test.py`
# renders the same five moments of the same race at 45, 50, 55, 60 and 74 and
# the frames are compared side by side. See `docs/race_v04.md` for what each
# one looks like. `--race-elevation=` overrides this at render time, which is
# how that sweep is produced and the only reason the constant is not simply
# edited between runs.
const PROD_ELEVATION_DEG := 52.0
# Clearance past the course wall at the *nearest* visible ground point, in
# world units. The near edge is the narrowest part of the view frustum where
# it meets the ground, so fitting the course there fits it everywhere.
const PROD_EDGE_MARGIN := 0.25
# How far ahead of the camera track the lens is aimed, in course pixels. The
# exported track frames the leading group at 42% of a 1920px window, so the
# leaders sit at `camera_y + 806`; aiming past them pushes the leaders below
# centre and fills the top of the frame with the course they are about to
# reach, which is the shot.
const PROD_AIM_LEAD := 820.0

# A gentle dolly. The camera pulls back when the field is strung out and
# closes in when it is tight, which reads as the race breathing. Computed
# from the replay frames rather than accumulated across draws, so it is a pure
# function of the playhead like everything else.
const PROD_SPREAD_WINDOW := 36        # frames averaged, ~0.6s
const PROD_SPREAD_FULL := 2600.0      # course px of spread that earns the full pull-back
const PROD_DOLLY_RANGE := 0.16        # fraction of the base distance
# The closing push-in. Once the winner is in, the lens creeps forward: a
# small, slow move that says "this is the end" without taking over.
const PROD_FINISH_PUSH := 0.10
const PROD_FINISH_SECONDS := 2.4

# --- course geometry, as drawn -------------------------------------------
#
# The visual mesh is allowed to be richer than the collision representation as
# long as it faithfully overlays it. Walls are the one place that matters: the
# simulation's boundary is a flat 80px box, and drawing it flat leaves the
# course reading as markings on a floor. Given real height it reads as a
# channel, which is what a perspective camera is for.
const WALL_HEIGHT := 2.30
const PEG_HEIGHT := 0.98
const GATE_HEIGHT := 0.80
const PAD_HEIGHT := 0.34
const SPINNER_HUB_HEIGHT := 0.86
const SPINNER_ARM_HEIGHT := 0.52

# What the measuring lens draws everything that is not a racer at.
#
# A racer's centre sits one radius up, at 0.30 units. Anything drawn taller
# than that and standing on the same spot wins the depth test straight down,
# and the instrument loses the racer it was pointing at: a rotor arm 0.52 tall
# hid racer 6 completely in five of thirty sampled frames of the V0.3
# reference replay, in every case while it was riding an arm. The heights are
# presentation - the solver's pieces are flat bars in a plane - so on this lens
# they are flattened to well under a racer, and nothing can stand in front of
# the thing being measured.
const MEASURED_HEIGHT := 0.16

# A travelling surface is a *beam*, and how deep a beam depends on how steep
# it is. This is the single change that stopped the course reading as markings
# on a floor: the simulation's pieces are all 26px-thick bars in a plane, and
# drawn at one height they are all the same flat slab. Read as machinery they
# are two different objects - a near-flat piece is a platform racers run along
# and wants a deck's thickness, a near-vertical piece is a wall of the machine
# and wants a wall's. The angle in the replay says which, so nothing here has
# to know what a funnel or a divider is: the bowl's walls come out tall
# because they are steep, and the shelves come out as decks because they lie
# flat.
const BEAM_HEIGHT := 0.62           # a flat platform
const BEAM_WALL_HEIGHT := 1.55      # a vertical face
# Below this a beam is not worth supporting; above it, it gets posts.
const STRUT_MIN_LENGTH := 2.2
const STRUT_SPACING := 2.4
const STRUT_WIDTH := 0.20
const STRUT_DROP := 1.5             # how far a post reaches below its beam

# The lit line down the length of a travelling surface.
const EDGE_INSET := 0.86
const EDGE_THICKNESS := 0.055
const EDGE_RISE := 0.012

# --- the deck ------------------------------------------------------------
#
# The authoritative physics is two-dimensional: every piece of this course
# lies in one plane, and the only reason the render has a vertical axis at all
# is that nothing in the simulation uses it. So it is spent on the one thing a
# flat course cannot show - that a marble machine is a stack of levels, and
# that a racer moving down the course is descending through it.
#
# The mapping is a single monotone function of course height, applied to
# *everything*: pieces, spinners, racers, trails, effects and the camera's aim
# all read their vertical offset from `_deck()`. That is what keeps it
# truthful. Two things at the same point on the course are at the same visual
# height, so a racer can never appear to pass through geometry it is really
# resting on, and because the function only ever decreases, visual descent and
# course progress mean the same thing.
#
# It is invisible to the verification camera, which is orthographic and points
# straight down: screen position there depends on X and Z only, so the
# measuring lens sees exactly the picture it saw before.
const DECK_TOTAL := 4.0             # units dropped from the first level to the last
# Course pixels a step is blended over. Wide enough that no racer visibly
# steps down, narrow enough that each level reads as a level.
const DECK_BLEND := 300.0
# How finely a long piece is cut up so it can follow the deck. A boundary wall
# runs the whole length of the course and has to descend with everything else.
const DECK_SEGMENT := 220.0

# Checkpoint markers. In V0.3 every progress plane got a lit bar the full
# width of the course, and the effect on a finished frame was the opposite of
# what was wanted: a dozen glowing horizontal lines across the track read as
# the diagram of a course rather than as a machine. Course progress is not
# something a viewer needs drawn; it is something they can see.
#
# So in production a checkpoint is marked at the edges only - two short lit
# studs let into the deck beside the track, which read as machine markings
# rather than as gates. The full bar survives on the measuring lens, where
# there is nobody to mislead and it is useful to see the ladder.
const CHECKPOINT_HEIGHT := 0.035
const CHECKPOINT_THICKNESS := 0.10
const CHECKPOINT_STUD_WIDTH := 0.55
const FINISH_BAR_HEIGHT := 0.09
const FINISH_BAR_THICKNESS := 0.24
const FINISH_POST_HEIGHT := 1.9
const FINISH_POST_WIDTH := 0.26

# Pinch gates. Where the course narrows to a fraction of its width, a plain
# line across the track undersells what is about to happen - the funnel throat
# is 126 pixels of a 1000-pixel course, and it is the moment the prototype is
# built around. Found by measurement rather than by name, so the split
# course's pass gets the same treatment without this file knowing either
# course exists.
const PINCH_FRACTION := 0.18        # clear width, as a share of the course
const PINCH_STEP := 40.0            # course pixels between samples
const PINCH_POST_HEIGHT := 1.25
const PINCH_POST_WIDTH := 0.17
const PINCH_POST_DEPTH := 0.30
const PINCH_RING_THICKNESS := 0.13

# A jump pad flares when it fires. The pad piece gets its own material rather
# than the shared one so a single pad can light up without every pad on the
# course lighting with it.
const PAD_FLARE := 4.5

# Section portals: a pair of lit posts where each named stretch of course
# begins. Cheap architecture that gives the run a beat, and it marks the
# funnel - the moment the prototype course is built around - without this
# file knowing what a funnel is.
const PORTAL_HEIGHT := 3.55
const PORTAL_WIDTH := 0.30
const PORTAL_DEPTH := 0.46
# Two posts, no lintel. A gantry with a beam across it looked like the right
# idea and produced the wrong picture - see `_build_section_portals`. The
# posts alone still mark the boundary, still give the frame something near the
# lens to sweep past, and cross nothing.
# The riser: the vertical face of the step down to the next level. Without it
# the deck change is a slope nobody can see; with it, the machine has floors.
# Drawn as two wings from the walls inwards rather than across the track, so
# it never stands between the lens and a racer.
const RISER_HEIGHT := 0.52
const RISER_DEPTH := 0.30
const RISER_SPAN := 0.62        # share of a half-width each wing covers

# --- racers ---------------------------------------------------------------

# The meridian ring that makes rotation visible. A uniform sphere spinning
# about its axis looks exactly like a sphere at rest, and the replay carries a
# real rotation that would otherwise be thrown away.
const BAND_THICKNESS := 0.055
const BAND_SCALE := 1.012

# The number plate. Held above the racer rather than painted on it, because a
# number wrapped round a rolling sphere is unreadable exactly when it matters.
const BADGE_RISE := 0.62
const BADGE_FONT_SIZE := 140
const BADGE_PIXEL_SIZE := 0.0026
const BADGE_OUTLINE := 30

# Impact squash. Presentation only: the physics has already happened and this
# changes nothing about it. The racer is compressed along the axis it was hit
# on and recovers with a small overshoot, which is what makes a collision feel
# like it had weight.
const SQUASH_MAX := 0.30

# --- environment ----------------------------------------------------------

const COURSE_FLOOR_DROP := 0.55
const COURSE_FLOOR_THICKNESS := 1.1
# Recessed rails down the deck, as fractions of a half-width from the centre.
const FLOOR_RAIL_X := [-0.72, -0.30, 0.30, 0.72]
const FLOOR_RAIL_SIZE := Vector2(0.30, 0.07)
const SIDE_STRUCTURE_GAP := 1.0       # units outside the course wall
const SIDE_STRUCTURE_WIDTH := 2.6
const SIDE_STRUCTURE_TOP := 3.4
const SIDE_STRUCTURE_BOTTOM := -3.6
const STRIP_HEIGHT := 0.10
const STRIP_DEPTH := 0.12
const DEEP_FLOOR_DROP := 8.0
const RIB_SPACING := 4.0              # world units between structural ribs
const RIB_SIZE := Vector3(0.40, 2.30, 0.55)
# A second rank of ribs, taller and nearer the lens than the first. Two ranks
# at different distances is the cheapest parallax there is: at a 50 degree
# elevation the near rank crosses the frame in half the time the far one
# takes, and that difference is the cue that tells a viewer the picture has
# depth rather than being a drawing of it.
const RIB_NEAR_SPACING := 7.0
const RIB_NEAR_SIZE := Vector3(0.5, 3.4, 0.7)
const RIB_NEAR_OFFSET := 0.55         # units further out than the far rank
# How far the room runs past each end of the course, in course pixels. The
# machine has to continue past the finish or the top of the frame is a void:
# at 52 degrees the lens sees a long way down the course, and when it runs out
# there is nothing behind it but the background colour. Carried far enough
# that the fog closes over it instead.
const ROOM_OVERRUN_TOP := 1400.0
const ROOM_OVERRUN_BOTTOM := 3200.0

# --- playback -------------------------------------------------------------

# How near a whole frame the playhead has to be to *be* that frame. Sample
# times are computed by dividing and multiplying, and floating point lands
# either side of the integer, so frame 123 can arrive as 122.99999999999999.
const PLAYHEAD_SNAP := 1.0e-6

var camera_mode := CAMERA_PRODUCTION

# True while the verification camera is fitted, and it turns off every piece
# of presentation in this file.
#
# That is not a shortcut, it is the point. `tools/verify_race_render.py` finds
# a racer by looking for its colour at the pixel the replay puts it at, and
# every one of the things that make the production render look expensive
# defeats that: a glossy sphere lit by a cyan kicker is not its own hue at the
# edges, a bloomed jump pad turns a whole neighbourhood of the frame white, an
# additive impact ring sits on top of the ball it happened to, and a squash
# moves the silhouette the measurement is taken from.
#
# The first version of this scene left them all on. Alignment went from a
# median of 0.7 pixels to 4.1, with a third of the racers unmeasurable
# because a pad flare had saturated the frame around them - and none of that
# was a placement error. The geometry was exactly right and could not be
# proven right, which is worse than either.
#
# So the measuring lens gets flat unshaded racers, no glow, no trails, no
# effects and no deformation. Same course, same transforms, same frames - only
# the presentation is gone, and what is left is the thing being measured.
#
# V0.4 extends that to anything *standing over* the track as well as anything
# drawn on it. A gantry post, a pinch gate and a finish post are all several
# times a racer's height and sit at the course edges, and straight down they
# cover the exact lane a racer running along the wall is in: racer 6 went
# unmeasurable in five of thirty sampled frames until they were switched off,
# every time while it was hugging the left-hand side. None of them exists in
# the simulation, so none of them may stand between the instrument and the
# thing it is measuring.
var _measuring := false

var _replay: Dictionary = {}
var _course: Dictionary = {}
var _frames: Array = []
var _racer_meta: Array = []

var _course_width := 1080.0
var _course_top := 0.0
var _course_bottom := 0.0

var _palette: RefCounted
var _camera: Camera3D
var _hud: CanvasLayer
var _trails: Node3D
var _vfx: Node3D

# Where each level of the machine begins, in course pixels, and how far the
# deck has dropped by then. Built once from the course's own sections, so a
# course this file has never seen gets its levels for free.
var _deck_steps: Array[float] = []
var _deck_drop := 0.0

var _prod_offset := Vector3.ZERO
var _prod_distance := 0.0
var _prod_elevation := PROD_ELEVATION_DEG
var _final_tick := 0.0
var _winner_tick := -1.0

var _racer_nodes: Array[Node3D] = []
var _racer_spheres: Array[MeshInstance3D] = []
var _racer_bands: Array[MeshInstance3D] = []
var _racer_live: Array[StandardMaterial3D] = []
var _racer_done: Array[StandardMaterial3D] = []
var _racer_radius: Array[float] = []
var _racer_colors: Array[Color] = []

# Pivots of the spinners, keyed by the replay's spinner id. Built once from
# the course; every frame writes a transform into them and nothing is ever
# created or freed while playing back.
var _spinner_pivots: Dictionary = {}
var _spinner_edges: Dictionary = {}
# Gate pieces, hidden the frame the countdown ends. Removal is a state in the
# replay, not something timed here.
var _gate_nodes: Array[Node3D] = []
var _gates_hidden := false

var _finish_gate: Node3D
var _finish_materials: Array[StandardMaterial3D] = []
var _finish_base_energy: Array[float] = []

# Jump pads, keyed by course piece id, each with its own material so it can
# flare on its own.
var _pad_materials: Dictionary = {}
var _pad_base_energy: Dictionary = {}

var _physics_hz := 120.0
var _ticks_per_frame := 2.0


func build(replay: Dictionary, mode := CAMERA_PRODUCTION) -> void:
	camera_mode = mode if mode == CAMERA_VERIFICATION else CAMERA_PRODUCTION
	_measuring = camera_mode == CAMERA_VERIFICATION
	_replay = replay
	_course = replay.get("course", {})
	_frames = replay.get("frames", [])
	_racer_meta = replay.get("racers", [])
	_course_width = maxf(1.0, float(_course.get("width", 1080.0)))
	_course_top = float(_course.get("top", 0.0))
	_course_bottom = float(_course.get("bottom", 6800.0))
	_physics_hz = maxf(1.0, float(replay.get("physics_hz", 120.0)))
	_ticks_per_frame = maxf(1.0, float(replay.get("ticks_per_frame", 2.0)))
	if not _frames.is_empty():
		_final_tick = float((_frames[-1] as Dictionary).get("tick", 0))
	_winner_tick = _find_winner_tick()

	_palette = RaceMaterials.new()
	_build_deck()

	_build_environment()
	_build_lights()
	_build_camera()
	_build_course_floor()
	_build_side_structures()
	_build_pieces()
	_build_checkpoints()
	_build_spinners()
	_build_racers()
	_build_trails()
	_build_vfx()
	_build_hud()


func present(tick: float) -> void:
	## Show the race as it stood at `tick`, in simulation ticks.
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

	# Effects first: the racers ask it what happened to them this tick.
	_vfx.update_to_tick(tick)
	_update_camera(frame, next_frame, blend, index, tick)
	_update_racers(frame.get("racers", []), next_frame.get("racers", []), blend, tick)
	_update_trails(index, blend, tick)
	_update_spinners(frame.get("spinners", []), next_frame.get("spinners", []), blend)
	_update_gates(frame)
	_update_pads(tick)
	_update_finish(tick)
	_hud.update_hud(frame, tick)


# --- coordinate conversion -----------------------------------------------

func to_world(sim_x: float, sim_y: float, height: float) -> Vector3:
	## Simulation x maps to world X, simulation y to world Z, Y is visual only.
	##
	## X is centred on the course so a camera can sit on the middle line and
	## only ever move along Z. Z is *not* centred: it is the course height
	## itself, which is what lets the camera track be read straight out of the
	## replay without an offset in between.
	return Vector3(
		(sim_x - _course_width * 0.5) / PIXELS_PER_UNIT,
		height + _deck(sim_y),
		sim_y / PIXELS_PER_UNIT)


func _deck(sim_y: float) -> float:
	## How far the machine has stepped down by this point on the course.
	##
	## Smoothstepped across each boundary rather than stepped at it, so a
	## racer crossing between two levels descends over a third of a second
	## instead of teleporting a metre downwards. Monotone by construction:
	## every term is non-increasing in `sim_y`, so visual height and course
	## progress can never disagree about which way is forward.
	if _deck_steps.is_empty():
		return 0.0
	var total := 0.0
	for boundary in _deck_steps:
		total += smoothstep(
			boundary - DECK_BLEND * 0.5, boundary + DECK_BLEND * 0.5, sim_y)
	return -_deck_drop * total


func _build_deck() -> void:
	## One level per named section of the course, and nothing hard-coded.
	var sections: Array = _course.get("sections", [])
	_deck_steps.clear()
	for raw in sections:
		var section: Dictionary = raw
		var top := float(section.get("top", 0.0))
		if top > _course_top + 1.0:
			_deck_steps.append(top)
	_deck_drop = 0.0 if _deck_steps.is_empty() \
		else DECK_TOTAL / float(_deck_steps.size())


func to_units(pixels: float) -> float:
	return pixels / PIXELS_PER_UNIT


# --- environment ----------------------------------------------------------

func _build_environment() -> void:
	## A dark room with a little air in it.
	##
	## Everything expensive is off. No SDFGI, no screen-space reflections, no
	## volumetric fog: this renders 1080x1920 on a laptop GPU, and each of
	## those costs more than every light in the scene put together. What is
	## left - a flat ambient, depth fog and a tight glow - is enough, because
	## the depth in this picture comes from the geometry and the key light
	## rather than from the renderer.
	var environment := Environment.new()
	# The void stays black: what is drawn behind the course is a flat dark
	# colour, not the sky below.
	environment.background_mode = Environment.BG_COLOR
	environment.background_color = Color(0.014, 0.017, 0.026)

	# A sky that is never drawn, and is the single most important object in
	# this scene.
	#
	# Most of the course is metal, and a metal surface is almost entirely a
	# mirror: its albedo barely matters and what it shows is whatever the
	# environment gives it to reflect. With no reflection source every polished
	# ramp renders as a black hole with a specular streak on it - which is
	# exactly how the first version of this scene looked, and no amount of
	# lifting the albedo fixes it, because the albedo is not what is missing.
	#
	# So there is a sky. It is kept out of the background and used only as a
	# light and reflection probe: a cool gradient overhead, a warmer band at
	# the horizon for surfaces facing sideways, near-black underneath. It is
	# what puts a soft sheen down the length of every slick ramp.
	var sky_material := ProceduralSkyMaterial.new()
	sky_material.sky_top_color = Color(0.085, 0.125, 0.190)
	sky_material.sky_horizon_color = Color(0.150, 0.205, 0.290)
	sky_material.sky_curve = 0.18
	sky_material.ground_horizon_color = Color(0.070, 0.090, 0.130)
	sky_material.ground_bottom_color = Color(0.020, 0.024, 0.034)
	sky_material.ground_curve = 0.10
	# No sun disc: the key light is a light, and a bright disc in the
	# reflection would land as a hot spot somewhere nothing is shining from.
	sky_material.sun_angle_max = 0.0
	sky_material.energy_multiplier = 1.0

	var sky := Sky.new()
	sky.sky_material = sky_material
	sky.radiance_size = Sky.RADIANCE_SIZE_128
	# Fully recomputed rather than updated incrementally or reprojected from
	# the previous frame. The sky never changes, so the cost is paid once -
	# and anything that carried state between draws would make the first
	# frame of a render differ from the same frame rendered later.
	sky.process_mode = Sky.PROCESS_MODE_QUALITY
	environment.sky = sky

	environment.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	environment.ambient_light_sky_contribution = 1.0
	environment.ambient_light_energy = 1.20
	environment.reflected_light_source = Environment.REFLECTION_SOURCE_SKY

	# ACES for the picture, and nothing at all for the instrument.
	#
	# A tone curve is a deliberate distortion of colour, which is exactly what
	# a production frame wants and exactly what a measurement must not have.
	# Under ACES a flat unshaded racer does not reach the PNG as its own
	# colour - red (235, 72, 72) arrives as (239, 0, 21) - and
	# `verify_race_render.py` finds a racer by looking for its colour. Linear,
	# with the albedo converted out of sRGB where it is set, the pixel is the
	# number the replay carries.
	environment.tonemap_mode = Environment.TONE_MAPPER_LINEAR if _measuring 		else Environment.TONE_MAPPER_ACES
	environment.tonemap_white = 2.2
	environment.tonemap_exposure = 1.0

	# Depth fog. The cheapest depth cue there is, and the thing that stops the
	# far end of a 68-unit course reading as flat as the near end.
	environment.fog_enabled = not _measuring
	environment.fog_mode = Environment.FOG_MODE_DEPTH
	environment.fog_light_color = Color(0.055, 0.085, 0.130)
	environment.fog_light_energy = 1.0
	environment.fog_density = 0.0
	environment.fog_depth_begin = 22.0
	environment.fog_depth_end = 78.0
	environment.fog_depth_curve = 1.4
	environment.fog_sky_affect = 0.0

	# Glow, kept on a short leash. The threshold sits above every ordinary lit
	# surface, so only the things that are meant to bloom do: a pad, a spinner
	# edge, the finish, an impact. Turn this loose and the whole course hazes
	# over and the racers stop being the brightest thing in the frame.
	environment.glow_enabled = not _measuring
	environment.glow_intensity = 0.55
	environment.glow_strength = 1.0
	environment.glow_bloom = 0.02
	environment.glow_blend_mode = Environment.GLOW_BLEND_MODE_ADDITIVE
	environment.glow_hdr_threshold = 1.05
	environment.glow_hdr_scale = 2.0
	# Mid-sized levels only: level 1 is a tight halo that just sharpens
	# aliasing, and the widest levels are what turn glow into fog.
	environment.set_glow_level(1, 0.0)
	environment.set_glow_level(2, 0.6)
	environment.set_glow_level(3, 1.0)
	environment.set_glow_level(4, 0.7)
	environment.set_glow_level(5, 0.3)
	environment.set_glow_level(6, 0.0)

	# Contact darkening where geometry meets geometry. Moderate radius and a
	# short distance: this is here to seat a racer on a ramp, not to shade the
	# whole room.
	environment.ssao_enabled = not _measuring
	environment.ssao_radius = 0.55
	environment.ssao_intensity = 1.6
	environment.ssao_power = 1.5
	environment.ssao_detail = 0.5
	environment.ssao_light_affect = 0.12

	var world := WorldEnvironment.new()
	world.name = "WorldEnvironment"
	world.environment = environment
	add_child(world)


func _build_lights() -> void:
	## A key, a fill and a cold kicker.
	##
	## The key is angled across the course rather than down it. A light
	## straight overhead would put every shadow underneath the thing casting
	## it and the whole course would read as flat paint - which is precisely
	## what the V0.2 render looked like. Across the course, a ramp gets a lit
	## face and a dark face, a racer gets a shadow to sit on, and the picture
	## has a direction.
	var key := DirectionalLight3D.new()
	key.name = "KeyLight"
	key.light_color = Color(1.0, 0.96, 0.90)
	key.light_energy = 2.35
	key.light_specular = 1.0
	key.shadow_enabled = true
	key.directional_shadow_mode = DirectionalLight3D.SHADOW_PARALLEL_2_SPLITS
	# Only as far as the camera can see. A course is 68 units long and the
	# frame shows about 23 of them; a shadow range covering the whole course
	# would spend the same texels over three times the area.
	key.directional_shadow_max_distance = 62.0
	key.directional_shadow_split_1 = 0.16
	key.directional_shadow_blend_splits = true
	key.shadow_bias = 0.035
	key.shadow_normal_bias = 1.2
	key.shadow_opacity = 0.88
	key.rotation_degrees = Vector3(-52.0, 38.0, 0.0)
	add_child(key)

	var fill := DirectionalLight3D.new()
	fill.name = "FillLight"
	fill.light_color = Color(0.42, 0.62, 1.0)
	fill.light_energy = 0.85
	fill.light_specular = 0.25
	fill.shadow_enabled = false
	fill.rotation_degrees = Vector3(-24.0, -132.0, 0.0)
	add_child(fill)

	# A cold light almost along the camera axis, low and behind, purely to put
	# a bright edge on the far side of every sphere. It is what stops ten dark
	# balls merging into one shape in a pile-up.
	var kicker := DirectionalLight3D.new()
	kicker.name = "KickerLight"
	kicker.light_color = Color(0.55, 0.85, 1.0)
	kicker.light_energy = 0.85
	kicker.light_specular = 1.4
	kicker.shadow_enabled = false
	kicker.rotation_degrees = Vector3(-12.0, 186.0, 0.0)
	add_child(kicker)


func _build_course_floor() -> void:
	## The slab the course stands on, and what its shadows land on.
	var mesh := BoxMesh.new()
	mesh.size = Vector3(to_units(_course_width) + 0.6, COURSE_FLOOR_THICKNESS, 1.0)
	var rail_mesh := BoxMesh.new()

	# Cut into slabs so the floor descends with the machine standing on it.
	# One slab spanning the whole course would sit at one height and every
	# level but the middle one would float above it or be swallowed by it.
	var root := Node3D.new()
	root.name = "CourseFloor"
	add_child(root)

	var floor_top := _course_top - ROOM_OVERRUN_TOP
	var floor_bottom := _course_bottom + ROOM_OVERRUN_BOTTOM
	var slabs := maxi(1, int((floor_bottom - floor_top) / 400.0))
	var slab_span := (floor_bottom - floor_top) / float(slabs)
	mesh.size = Vector3(
		to_units(_course_width) + 0.6,
		COURSE_FLOOR_THICKNESS,
		to_units(slab_span) + 0.05)
	rail_mesh.size = Vector3(
		FLOOR_RAIL_SIZE.x, FLOOR_RAIL_SIZE.y, to_units(slab_span) + 0.05)
	for index in slabs:
		var y := floor_top + (float(index) + 0.5) * slab_span
		var node := MeshInstance3D.new()
		node.name = "Slab%d" % index
		node.mesh = mesh
		node.material_override = _palette.structure()
		node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		node.position = to_world(
			_course_width * 0.5, y,
			-COURSE_FLOOR_DROP - COURSE_FLOOR_THICKNESS * 0.5)
		root.add_child(node)

		if _measuring:
			continue
		# Rails let into the deck, running *along* the course rather than
		# across it. Along matters: anything drawn across the track reads as a
		# rung and puts the frame back in diagram territory, while a line down
		# the direction of travel is what a machined floor actually looks like
		# - and, moving under the lens at the deck's own rate, it is a third
		# distance for the eye to compare the walls and the near ribs against.
		for lane in FLOOR_RAIL_X:
			var rail := MeshInstance3D.new()
			rail.name = "Rail%d_%d" % [index, int(lane * 10.0)]
			rail.mesh = rail_mesh
			rail.material_override = _palette.structure(true)
			rail.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			rail.position = node.position + Vector3(
				lane * to_units(_course_width) * 0.5,
				COURSE_FLOOR_THICKNESS * 0.5 + FLOOR_RAIL_SIZE.y * 0.5, 0.0)
			root.add_child(rail)


func _build_side_structures() -> void:
	## The room the course runs through.
	##
	## Two long walls just outside the track with a lit strip along the top of
	## each, and a rank of ribs between them and the camera. Cheap on purpose:
	## the walls are one box each, the ribs are one MultiMesh, and together
	## they do the whole job of making the course a place rather than a shape
	## on a black background. They also give the perspective camera something
	## to run past, which is most of what sells speed.
	var room_top := _course_top - ROOM_OVERRUN_TOP
	var room_bottom := _course_bottom + ROOM_OVERRUN_BOTTOM
	var length := to_units(room_bottom - room_top)
	var centre_z := (room_top + room_bottom) * 0.5
	var offset := to_units(_course_width) * 0.5 + SIDE_STRUCTURE_GAP
	var height := SIDE_STRUCTURE_TOP - SIDE_STRUCTURE_BOTTOM

	var root := Node3D.new()
	root.name = "Environment"
	add_child(root)

	# Cut into runs, so the room descends with the machine inside it. A
	# single wall the length of the course would cross every level and the
	# whole point of the deck - that there are levels - would be lost behind
	# one continuous horizontal line down the side of the frame.
	var runs := maxi(1, int((room_bottom - room_top) / 500.0))
	var run_span := (room_bottom - room_top) / float(runs)
	var wall := BoxMesh.new()
	wall.size = Vector3(SIDE_STRUCTURE_WIDTH, height, to_units(run_span) + 0.05)
	var strip := BoxMesh.new()
	strip.size = Vector3(STRIP_DEPTH, STRIP_HEIGHT, to_units(run_span) + 0.05)

	for side in [-1.0, 1.0]:
		for index in runs:
			var y := room_top + (float(index) + 0.5) * run_span
			var drop := _deck(y)
			var node := MeshInstance3D.new()
			node.name = "SideWall%d_%d" % [int(side), index]
			node.mesh = wall
			node.material_override = _palette.structure()
			node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			node.position = Vector3(
				side * (offset + SIDE_STRUCTURE_WIDTH * 0.5),
				drop + SIDE_STRUCTURE_BOTTOM + height * 0.5,
				to_units(y))
			root.add_child(node)

			var lit := MeshInstance3D.new()
			lit.name = "SideStrip%d_%d" % [int(side), index]
			lit.mesh = strip
			lit.material_override = _palette.light_strip()
			lit.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			lit.position = Vector3(
				side * (offset + STRIP_DEPTH * 0.5),
				drop + SIDE_STRUCTURE_TOP - 0.35,
				to_units(y))
			root.add_child(lit)

	_build_ribs(root, offset, length, centre_z)
	_build_near_ribs(root, offset)
	_build_deep_floor(root, length, centre_z)


func _build_ribs(root: Node3D, offset: float, length: float, centre_z: float) -> void:
	## Structural ribs down both walls, as one MultiMesh.
	##
	## Two hundred separate boxes would be two hundred draw calls for scenery
	## nobody looks at directly. As instances of one mesh they are one, and
	## they are what makes the camera's forward motion legible - a rank of
	## regular objects sweeping past reads as speed in a way that a smooth
	## wall never does.
	var count := int(length / RIB_SPACING)
	if count < 2:
		return

	var mesh := BoxMesh.new()
	mesh.size = RIB_SIZE

	var multi := MultiMesh.new()
	multi.transform_format = MultiMesh.TRANSFORM_3D
	multi.mesh = mesh
	multi.instance_count = count * 2

	var start := to_units(centre_z) - length * 0.5
	for index in count:
		var z := start + float(index) * RIB_SPACING
		var drop := _deck(z * PIXELS_PER_UNIT)
		for side_index in 2:
			var side := -1.0 if side_index == 0 else 1.0
			multi.set_instance_transform(
				index * 2 + side_index,
				Transform3D(Basis(), Vector3(
					side * (offset - RIB_SIZE.x * 0.5),
					drop + SIDE_STRUCTURE_TOP - 2.1,
					z)))

	var node := MultiMeshInstance3D.new()
	node.name = "Ribs"
	node.multimesh = multi
	node.material_override = _palette.structure(true)
	node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	root.add_child(node)


func _build_near_ribs(root: Node3D, offset: float) -> void:
	## A second rank of ribs, taller and further out than the first.
	##
	## This exists for one reason and it is worth stating plainly: parallax.
	## A tilted lens moving down a course sweeps near geometry across the
	## frame far faster than distant geometry, and a viewer reads that
	## difference as depth without ever thinking about it. One rank of ribs
	## gives a rate; two ranks at different distances give a *comparison*,
	## which is the actual cue. They are placed outside the course walls and
	## well above the racing surface, so nothing they do can hide a racer.
	if _measuring:
		return
	var span := (_course_bottom + ROOM_OVERRUN_BOTTOM) 		- (_course_top - ROOM_OVERRUN_TOP)
	var count := int(to_units(span) / RIB_NEAR_SPACING)
	if count < 2:
		return

	var mesh := BoxMesh.new()
	mesh.size = RIB_NEAR_SIZE

	var multi := MultiMesh.new()
	multi.transform_format = MultiMesh.TRANSFORM_3D
	multi.mesh = mesh
	multi.instance_count = count * 2

	for index in count:
		var z := to_units(_course_top - ROOM_OVERRUN_TOP) 			+ float(index) * RIB_NEAR_SPACING
		var drop := _deck(z * PIXELS_PER_UNIT)
		for side_index in 2:
			var side := -1.0 if side_index == 0 else 1.0
			multi.set_instance_transform(
				index * 2 + side_index,
				Transform3D(Basis(), Vector3(
					side * (offset + RIB_NEAR_OFFSET + RIB_NEAR_SIZE.x * 0.5),
					drop + SIDE_STRUCTURE_TOP - 1.0,
					z)))

	var node := MultiMeshInstance3D.new()
	node.name = "NearRibs"
	node.multimesh = multi
	node.material_override = _palette.structure()
	node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	root.add_child(node)


func _build_deep_floor(root: Node3D, length: float, centre_z: float) -> void:
	## A floor a long way below, so the gap either side of the course reads as
	## a drop into a dark building rather than as the edge of the world.
	var mesh := BoxMesh.new()
	mesh.size = Vector3(60.0, 0.5, length)

	var node := MeshInstance3D.new()
	node.name = "DeepFloor"
	node.mesh = mesh
	node.material_override = _palette.floor_deep()
	node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	node.position = Vector3(
		0.0, -DEEP_FLOOR_DROP - DECK_TOTAL * 0.5, to_units(centre_z))
	root.add_child(node)


# --- cameras --------------------------------------------------------------

func _build_camera() -> void:
	_camera = Camera3D.new()
	_camera.name = "Camera3D"
	_camera.near = 0.15
	if camera_mode == CAMERA_VERIFICATION:
		_build_verification_camera()
	else:
		_build_production_camera()
	add_child(_camera)


func _build_verification_camera() -> void:
	## Orthographic, straight down, framing exactly 1080x1920 course pixels.
	##
	## `size` is the vertical extent in world units because the aspect is kept
	## on height, so 19.2 units of course fill the 1920 pixel frame and the
	## 10.8 units of width fall out of the 9:16 aspect exactly. One simulation
	## pixel is one frame pixel, everywhere in the frame - which is the whole
	## reason this projection exists and why it is worth keeping after the
	## production camera arrived.
	_camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	_camera.keep_aspect = Camera3D.KEEP_HEIGHT
	_camera.size = VERIFY_SIZE
	_camera.far = VERIFY_HEIGHT * 3.0
	# Looking down -Y with screen-up along -Z, so up the frame is up the
	# course. Set as a rotation rather than with look_at, which has no way to
	# express "up" for a straight-down view.
	_camera.rotation_degrees = Vector3(-90.0, 0.0, 0.0)
	_camera.position = Vector3(0.0, VERIFY_HEIGHT, 0.0)


func _build_production_camera() -> void:
	## Elevated perspective, looking down the course.
	##
	## The distance is derived rather than dialled in, because the thing that
	## must not happen is the course running out of frame sideways. Under a
	## tilted lens the *nearest* visible ground point is where the frustum is
	## narrowest against the ground, so if the course fits across there it
	## fits everywhere:
	##
	##     span      = 2 D tan(fov/2) / sin(e)      ground covered, along Z
	##     near      = D - (span/2) cos(e)          view distance to the near edge
	##               = D (1 - tan(fov/2) / tan(e))
	##     half_wide = near * tan(h)                half the frame's width there
	##
	## Setting `half_wide` to half the course plus a margin and solving for D
	## gives the framing below. Aiming is then the only thing that changes per
	## frame: the camera holds a fixed offset from the point it looks at, and
	## that point runs down the course on the exported track.
	_camera.projection = Camera3D.PROJECTION_PERSPECTIVE
	_camera.keep_aspect = Camera3D.KEEP_HEIGHT
	_camera.fov = PROD_FOV
	_camera.far = 260.0
	_prod_elevation = _elevation_argument()

	var viewport_width := float(ProjectSettings.get_setting(
		"display/window/size/viewport_width", 1080))
	var viewport_height := float(ProjectSettings.get_setting(
		"display/window/size/viewport_height", 1920))
	var half_v := deg_to_rad(PROD_FOV * 0.5)
	var half_h := atan(tan(half_v) * viewport_width / viewport_height)
	var elevation := deg_to_rad(_prod_elevation)

	var needed := to_units(_course_width) * 0.5 + PROD_EDGE_MARGIN
	var shrink := 1.0 - tan(half_v) / tan(elevation)
	_prod_distance = needed / maxf(0.05, tan(half_h) * shrink)
	_prod_offset = Vector3(
		0.0,
		_prod_distance * sin(elevation),
		-_prod_distance * cos(elevation))


func _update_camera(frame: Dictionary, next_frame: Dictionary, blend: float,
		index: int, tick: float) -> void:
	var top := lerpf(
		float(frame.get("camera_y", 0.0)),
		float(next_frame.get("camera_y", 0.0)),
		blend)

	if camera_mode == CAMERA_VERIFICATION:
		# Nothing is allowed to move this camera but the exported track - not
		# a dolly, and not a shake. It is a measuring instrument.
		_camera.position = Vector3(
			0.0, VERIFY_HEIGHT, to_units(top + VIEW_HEIGHT * 0.5))
		return

	# The aim point rides the deck, so a camera looking at the machine keeps
	# looking at the machine as it steps down rather than gradually pointing
	# over the top of it.
	var aim_y := top + PROD_AIM_LEAD
	var aim := Vector3(0.0, _deck(aim_y), to_units(aim_y))
	var dolly := 1.0 + _spread_pull(index) - _finish_push(tick)
	_camera.position = aim + _prod_offset * dolly
	_camera.look_at(aim, Vector3.UP)
	# Applied after the aim, so a jolt moves the lens without re-pointing it.
	_camera.position += _vfx.camera_shake(tick)


func _elevation_argument() -> float:
	## `--race-elevation=50` shoots this render at fifty degrees.
	##
	## A render-time override rather than an edit to the constant, because the
	## whole point of the sweep is that the five candidate frames come out of
	## one build of one scene from one replay: anything else and the thing
	## being compared is not only the lens.
	for argument in OS.get_cmdline_user_args():
		var arg: String = argument
		if arg.begins_with("--race-elevation="):
			var value := arg.substr(17).to_float()
			if value >= 20.0 and value <= 89.0:
				return value
	return PROD_ELEVATION_DEG


func _spread_pull(index: int) -> float:
	## How far to pull back, from how strung out the field is.
	##
	## Averaged over the last half-second of *replay frames* rather than eased
	## across draws, so it is a pure function of the playhead: seeking
	## anywhere gives the same framing, and two renders agree.
	if _frames.is_empty():
		return 0.0
	var first := maxi(0, index - PROD_SPREAD_WINDOW + 1)
	var total := 0.0
	var samples := 0
	for at in range(first, index + 1):
		total += _frame_spread(_frames[at])
		samples += 1
	if samples == 0:
		return 0.0
	var spread := total / float(samples)
	return clampf(spread / PROD_SPREAD_FULL, 0.0, 1.0) * PROD_DOLLY_RANGE


func _frame_spread(frame: Dictionary) -> float:
	## The course distance between the leading racer and the last one racing.
	var lowest := INF
	var highest := -INF
	for raw in frame.get("racers", []):
		var racer: Dictionary = raw
		if bool(racer.get("retired", false)) or bool(racer.get("finished", false)):
			continue
		var y := float(racer.get("y", 0.0))
		lowest = minf(lowest, y)
		highest = maxf(highest, y)
	if lowest > highest:
		return 0.0
	return highest - lowest


func _finish_push(tick: float) -> float:
	## A slow creep forward once the race has been won.
	if _winner_tick < 0.0 or tick < _winner_tick:
		return 0.0
	var seconds := (tick - _winner_tick) / _physics_hz
	var progress := clampf(seconds / PROD_FINISH_SECONDS, 0.0, 1.0)
	# Ease out: it arrives and settles rather than drifting on.
	return (1.0 - pow(1.0 - progress, 2.0)) * PROD_FINISH_PUSH


func _find_winner_tick() -> float:
	for raw in _replay.get("events", []):
		var event: Dictionary = raw
		if str(event.get("type", "")) == "winner":
			return float(event.get("tick", 0))
	return -1.0


# --- the course -----------------------------------------------------------

func _build_pieces() -> void:
	## Course geometry, rebuilt from the replay and nothing else.
	##
	## The viewer does not know how this course was generated and must not:
	## the replay gives it every box and every circle with a role and a
	## physical material attached, and a course it has never seen draws
	## correctly for free.
	var pieces: Array = _course.get("pieces", [])
	if pieces.is_empty():
		return

	var root := Node3D.new()
	root.name = "Course"
	add_child(root)

	for raw in pieces:
		var spec: Dictionary = raw
		var role := str(spec.get("role", "ramp"))
		var physical := str(spec.get("material", "track"))

		if str(spec.get("type", "")) == "circle":
			_build_peg(root, spec, role, physical)
		else:
			_build_box(root, spec, role, physical)

	_build_section_portals(root)


func _build_peg(root: Node3D, spec: Dictionary, role: String,
		physical: String) -> void:
	## A post standing on the deck, not a disc lying on it.
	##
	## Three parts, because that is what makes a cylinder read as a machined
	## object rather than as a circle: a flared base that seats it in the
	## deck, a shaft, and a lit cap. The cap is also the only part of a peg a
	## racer ever touches at speed, so lighting it says something true.
	var radius := to_units(float(spec.get("radius", 0.0)))
	var x := float(spec.get("x", 0.0))
	var y := float(spec.get("y", 0.0))

	var pivot := Node3D.new()
	pivot.name = "Peg%d" % int(spec.get("id", 0))
	pivot.position = to_world(x, y, 0.0)
	root.add_child(pivot)

	# The flare is wider than the peg the solver used, so it is presentation
	# and it is left off the measuring lens. Straight down, a base at 1.22x
	# the radius covers ground the collision shape does not - and it covered
	# enough of a racer standing beside one that the alignment check could no
	# longer find it.
	if not _measuring:
		var base := CylinderMesh.new()
		base.top_radius = radius * 1.02
		base.bottom_radius = radius * 1.22
		base.height = PEG_HEIGHT * 0.22
		base.radial_segments = 20
		var base_node := MeshInstance3D.new()
		base_node.name = "Base"
		base_node.mesh = base
		base_node.material_override = _palette.structure()
		base_node.position = Vector3(0.0, PEG_HEIGHT * 0.11, 0.0)
		pivot.add_child(base_node)

	var height := MEASURED_HEIGHT if _measuring else PEG_HEIGHT
	var mesh := CylinderMesh.new()
	mesh.top_radius = radius
	mesh.bottom_radius = radius if _measuring else radius * 1.02
	mesh.height = height
	mesh.radial_segments = 20
	var node := MeshInstance3D.new()
	node.name = "Shaft"
	node.mesh = mesh
	node.material_override = _palette.surface(role, physical)
	node.position = Vector3(0.0, height * 0.5, 0.0)
	pivot.add_child(node)

	if _measuring:
		return
	var cap := CylinderMesh.new()
	cap.top_radius = radius * 0.72
	cap.bottom_radius = radius * 0.94
	cap.height = PEG_HEIGHT * 0.13
	cap.radial_segments = 20
	var cap_node := MeshInstance3D.new()
	cap_node.name = "Cap"
	cap_node.mesh = cap
	cap_node.material_override = _palette.edge(physical)
	cap_node.position = Vector3(0.0, PEG_HEIGHT * 1.02, 0.0)
	cap_node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	pivot.add_child(cap_node)


func _build_box(root: Node3D, spec: Dictionary, role: String,
		physical: String) -> void:
	## One solid piece, cut into as many segments as the deck needs.
	##
	## The simulation's piece is a single rotated bar. Drawn as one mesh it
	## can only sit at one height, and a bar that runs a thousand pixels down
	## the course would either float above the level below it or sink into the
	## one above. So a piece is cut along its own length into segments short
	## enough that each can take the deck height at its own midpoint and tilt
	## to meet its neighbours. A short piece is one segment and this costs
	## nothing; a boundary wall is thirty and follows the machine down.
	##
	## Nothing about the collision shape changes. The union of the segments is
	## the bar the solver used, to within the tilt - which is a fraction of a
	## degree except where the deck is actually stepping.
	var length := float(spec.get("width", 0.0))
	var thickness := float(spec.get("height", 0.0))
	var angle := deg_to_rad(float(spec.get("rotation_degrees", 0.0)))
	var centre_x := float(spec.get("x", 0.0))
	var centre_y := float(spec.get("y", 0.0))
	var height := _box_height(role, angle)
	var piece_id := int(spec.get("id", 0))

	var pivot := Node3D.new()
	pivot.name = "Piece%d" % piece_id
	root.add_child(pivot)

	# How much course the piece spans vertically decides how finely it is cut.
	var span := absf(sin(angle)) * length
	var cuts := maxi(1, int(ceil(span / DECK_SEGMENT)))
	var step := length / float(cuts)
	var material: StandardMaterial3D = _palette.surface(role, physical)
	if role == "jump_pad":
		# Its own material, not the shared one: a pad has to be able to flare
		# on the tick it launches somebody without dragging every other pad on
		# the course up with it.
		material = material.duplicate()
		_pad_materials[piece_id] = material
		_pad_base_energy[piece_id] = material.emission_energy_multiplier

	for index in cuts:
		var offset := (float(index) + 0.5) * step - length * 0.5
		var seg_x := centre_x + offset * cos(angle)
		var seg_y := centre_y + offset * sin(angle)
		var half := step * 0.5
		var back_y := seg_y - half * sin(angle)
		var front_y := seg_y + half * sin(angle)
		# The deck at each end of this segment. Tilting to join them is what
		# keeps a cut piece a continuous surface rather than a staircase.
		var rise := _deck(front_y) - _deck(back_y)
		var seg_length := to_units(step)

		var seat := Node3D.new()
		seat.name = "Seg%d" % index
		seat.position = to_world(seg_x, seg_y, 0.0)
		# Simulation y becomes world Z, which mirrors the plane, so a rotation
		# that turns one way in simulation coordinates turns the other way
		# here. Negating it is what puts a ramp where the replay says it is.
		seat.rotation_degrees = Vector3(0.0, -rad_to_deg(angle), 0.0)
		pivot.add_child(seat)

		var tilt := Node3D.new()
		tilt.name = "Tilt"
		# About local Z, after the yaw, so the beam's own length axis rises to
		# meet the deck instead of the whole piece leaning sideways.
		tilt.rotation = Vector3(0.0, 0.0, atan2(rise, maxf(seg_length, 0.001)))
		seat.add_child(tilt)

		var slab := BoxMesh.new()
		slab.size = Vector3(seg_length, height, to_units(thickness))
		var body := MeshInstance3D.new()
		body.name = "Body"
		body.mesh = slab
		body.material_override = material
		# Hung below the deck line rather than standing on it: a racer runs
		# along the *top* of a simulation bar, so the top of the drawn beam is
		# where the bar is and all of the depth is underneath, where it cannot
		# lift a racer off its surface.
		body.position = Vector3(0.0, -height * 0.5, 0.0)
		tilt.add_child(body)

		if role == "jump_pad" or role == "gate" or _measuring:
			continue
		_build_beam_edge(tilt, seg_length, to_units(thickness), height)

	if role == "gate":
		_gate_nodes.append(pivot)
		return
	if role == "jump_pad" or _measuring:
		return
	_build_struts(pivot, spec, angle, length, height)


func _build_beam_edge(tilt: Node3D, seg_length: float, depth: float,
		height: float) -> void:
	## A lit line along the top of the beam and a dark web down its side.
	##
	## The lit line is the racing surface, which is the one part of a piece a
	## viewer has to be able to read instantly. The web is what stops a deep
	## beam looking like a solid block: a machine is built out of members with
	## faces, and one darker inset face down the length of each is enough to
	## say so.
	var strip := BoxMesh.new()
	strip.size = Vector3(seg_length * EDGE_INSET, EDGE_THICKNESS, depth * 0.34)
	var edge := MeshInstance3D.new()
	edge.name = "Edge"
	edge.mesh = strip
	edge.material_override = _palette.edge("track")
	edge.position = Vector3(0.0, EDGE_RISE, 0.0)
	edge.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	tilt.add_child(edge)

	if height < BEAM_HEIGHT * 0.9:
		return
	var web := BoxMesh.new()
	web.size = Vector3(seg_length * 0.94, height * 0.46, depth * 1.06)
	var web_node := MeshInstance3D.new()
	web_node.name = "Web"
	web_node.mesh = web
	web_node.material_override = _palette.structure(true)
	web_node.position = Vector3(0.0, -height * 0.56, 0.0)
	web_node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	tilt.add_child(web_node)


func _build_struts(pivot: Node3D, spec: Dictionary, angle: float,
		length: float, height: float) -> void:
	## Posts under a platform, so it stands on something.
	##
	## Only under pieces that are flat enough to read as platforms - a wall
	## does not need legs - and only if they are long enough for a post to be
	## more than clutter. Cheap, and the single most effective depth cue in
	## the frame after the deck itself: a slab with air and a shadow beneath
	## it is unmistakably an object, where the same slab flat on a floor is a
	## marking.
	if absf(sin(angle)) > 0.55:
		return
	var units := to_units(length)
	if units < STRUT_MIN_LENGTH:
		return
	var count := maxi(2, int(units / STRUT_SPACING))
	var centre_x := float(spec.get("x", 0.0))
	var centre_y := float(spec.get("y", 0.0))
	var mesh := BoxMesh.new()
	mesh.size = Vector3(STRUT_WIDTH, STRUT_DROP, STRUT_WIDTH)

	for index in count:
		var t := (float(index) + 0.5) / float(count)
		var offset := (t - 0.5) * length
		var post := MeshInstance3D.new()
		post.name = "Strut%d" % index
		post.mesh = mesh
		post.material_override = _palette.structure()
		post.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		post.position = to_world(
			centre_x + offset * cos(angle),
			centre_y + offset * sin(angle),
			-height - STRUT_DROP * 0.5)
		pivot.add_child(post)


func _box_height(role: String, angle: float) -> float:
	## How deep to draw a piece, from how steep the simulation made it.
	##
	## The replay has no idea what a wall is - every piece is a bar with an
	## angle - so the angle is what decides. A near-vertical bar is a face of
	## the machine and is drawn as one; a near-flat bar is something racers
	## run along and is drawn as a deck. Nothing here needs to know that this
	## particular course has a bowl in it, which is why the prototype and the
	## split course get the same treatment for free.
	if _measuring:
		return MEASURED_HEIGHT
	match role:
		"wall":
			return WALL_HEIGHT
		"gate":
			return GATE_HEIGHT
		"jump_pad":
			return PAD_HEIGHT
	return lerpf(BEAM_HEIGHT, BEAM_WALL_HEIGHT, absf(sin(angle)))


func _build_section_portals(root: Node3D) -> void:
	## A gantry and a riser wherever the machine steps down a level.
	##
	## Course sections are exported, so this needs no idea what a bowl or a
	## carousel is - it builds a doorway wherever the course says one stretch
	## ends and the next begins, and those are exactly the heights `_deck()`
	## steps at. The two together are what turn a run down a slope into a
	## descent through a building:
	##
	## The **riser** is the vertical face of the step. It is the piece of
	## geometry that makes the level change legible instead of merely present
	## - without it the deck drops smoothly and reads as a camera drift.
	##
	## The **gantry** is a pair of posts and a beam across the top of them.
	## It stands well above the racing surface so it never hides anybody, and
	## because it is close to the lens and the course behind it is not, it is
	## where most of the frame's parallax comes from: the beam sweeps over the
	## top of the picture while the course slides under it at a quite
	## different rate, which is the cue that says this is a space.
	var sections: Array = _course.get("sections", [])
	if sections.size() < 2 or _measuring:
		return

	var half := to_units(_course_width) * 0.5
	var post_mesh := BoxMesh.new()
	post_mesh.size = Vector3(PORTAL_WIDTH, PORTAL_HEIGHT, PORTAL_DEPTH)

	for index in sections.size():
		var section: Dictionary = sections[index]
		var top := float(section.get("top", 0.0))
		# The first section starts at the top of the course, where a gantry
		# would only frame the ceiling.
		if top <= _course_top + 1.0:
			continue

		var zone := _zone_material(index)
		var pivot := Node3D.new()
		pivot.name = "Portal_%s" % str(section.get("name", "?"))
		pivot.position = to_world(_course_width * 0.5, top, 0.0)
		root.add_child(pivot)

		if not _measuring:
			# The step face, in two wings with the middle left open.
			#
			# A step across the whole width was the first thing tried and it
			# was wrong twice over. It read as a rung - nine of them down the
			# frame, which is the schematic look this render exists to get
			# away from - and, worse, it stood between the lens and the track
			# behind it: a racer arriving at a boundary spent half a second
			# hidden behind the edge of the floor it was about to run onto.
			# Open in the middle, it says "the machine steps down here"
			# without ever crossing the racing line.
			var riser := BoxMesh.new()
			riser.size = Vector3(half * RISER_SPAN, RISER_HEIGHT, RISER_DEPTH)
			for side in [-1.0, 1.0]:
				var face := MeshInstance3D.new()
				face.name = "Riser%d" % int(side)
				face.mesh = riser
				face.material_override = _palette.structure(true)
				face.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
				face.position = Vector3(
					side * (half - half * RISER_SPAN * 0.5),
					-RISER_HEIGHT * 0.5, 0.0)
				pivot.add_child(face)

		for side in [-1.0, 1.0]:
			var post := MeshInstance3D.new()
			post.name = "Post%d" % int(side)
			post.mesh = post_mesh
			post.material_override = _palette.structure()
			post.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			post.position = Vector3(
				side * (half - PORTAL_WIDTH * 0.5), PORTAL_HEIGHT * 0.5, 0.0)
			pivot.add_child(post)

			if _measuring:
				continue
			# The zone light, on the post rather than on a cross-beam.
			#
			# V0.3 hung a lit bar over the track at every section and the
			# finished frame read as a course diagram: a dozen horizontal
			# lines is what a plan view looks like, whatever lens drew it. A
			# vertical light on a vertical post says the same thing - a new
			# stretch starts here, and it is this colour - and adds no line
			# across the picture at all.
			var strip := BoxMesh.new()
			strip.size = Vector3(
				PORTAL_WIDTH * 0.42, PORTAL_HEIGHT * 0.62, PORTAL_DEPTH * 0.5)
			var lit := MeshInstance3D.new()
			lit.name = "Strip%d" % int(side)
			lit.mesh = strip
			lit.material_override = _zone_material(index)
			lit.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			lit.position = Vector3(
				side * (half - PORTAL_WIDTH * 1.05),
				PORTAL_HEIGHT * 0.52, 0.0)
			pivot.add_child(lit)


func _zone_material(index: int) -> StandardMaterial3D:
	## The colour of one level of the machine.
	##
	## Deliberately a two-colour ramp rather than a rainbow: cool at the top
	## of the course, warm at the bottom, and nothing in between that a viewer
	## would read as a separate idea. It says only "you are further along",
	## which is the one thing the environment is allowed to say.
	var sections: Array = _course.get("sections", [])
	var span := maxf(1.0, float(sections.size() - 1))
	return _palette.light_strip(float(index) / span > 0.55)


func _build_checkpoints() -> void:
	## A lit bar across the track at every progress plane.
	##
	## Read straight out of the exported progress graph, including the
	## corridor a branch plane exists across - so on the split course the two
	## paths are marked separately and at their own widths, and a viewer can
	## see the fork is a fork. The finish gets a gate instead of a bar.
	var checkpoints: Array = _course.get("checkpoints", [])
	if checkpoints.is_empty():
		return

	var finish: Dictionary = _course.get("finish", {})
	var finish_index := int(finish.get("index", -1))

	var root := Node3D.new()
	root.name = "Checkpoints"
	add_child(root)

	for raw in checkpoints:
		var node: Dictionary = raw
		if int(node.get("index", -1)) == finish_index:
			continue
		var left := 0.0 if node.get("x_min") == null else float(node.get("x_min"))
		var right := _course_width if node.get("x_max") == null \
			else float(node.get("x_max"))
		var span := maxf(0.1, to_units(right - left))

		var y := float(node.get("y", 0.0))
		if _measuring:
			# The measuring lens keeps the full bar: there is nobody to
			# mislead, and seeing the ladder is useful when checking one.
			var mesh := BoxMesh.new()
			mesh.size = Vector3(span, CHECKPOINT_HEIGHT, CHECKPOINT_THICKNESS)
			var bar := MeshInstance3D.new()
			bar.name = "Checkpoint%d" % int(node.get("index", 0))
			bar.mesh = mesh
			bar.material_override = _palette.checkpoint_bar(false)
			bar.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			bar.position = to_world((left + right) * 0.5, y, CHECKPOINT_HEIGHT * 0.5)
			root.add_child(bar)
			continue

		# Production gets two short studs let into the deck at the edges of
		# the plane instead. The V0.3 render drew a dozen lit lines the full
		# width of the track and the frame read as a diagram of a course
		# rather than a machine - progress is something a viewer can see, not
		# something that has to be drawn across the floor.
		var stud := BoxMesh.new()
		stud.size = Vector3(
			CHECKPOINT_STUD_WIDTH, CHECKPOINT_HEIGHT, CHECKPOINT_THICKNESS)
		for side in [-1.0, 1.0]:
			var mark := MeshInstance3D.new()
			mark.name = "Checkpoint%d_%d" % [int(node.get("index", 0)), int(side)]
			mark.mesh = stud
			mark.material_override = _palette.checkpoint_bar(false)
			mark.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			var edge_x := left if side < 0.0 else right
			var inset := CHECKPOINT_STUD_WIDTH * PIXELS_PER_UNIT * 0.5
			mark.position = to_world(
				edge_x - side * inset, y, CHECKPOINT_HEIGHT * 0.5)
			root.add_child(mark)

	_build_finish_gate(root, finish)
	_build_pinch_gates(root)


func _build_pinch_gates(root: Node3D) -> void:
	"""A lit ring wherever the course narrows to a fraction of its width.

	The funnel throat is the moment the prototype course is built around and
	the pass is the moment the split course is: both are a hole a racer has to
	get through, and both looked like any other stretch of track. A plain line
	across the course at the nearest checkpoint would not do it, because
	neither hole has a checkpoint on it - the throat sits eighty pixels above
	`funnel_exit`.

	So the course is measured instead of asked. Sampling the clear width every
	forty pixels finds each stretch where the track closes to under a third of
	its width, and a gate goes at the narrowest point of each. Nothing here
	knows what a funnel is, which is why the split course's pass gets one too.
	"""
	var width := _course_width
	var threshold := width * PINCH_FRACTION
	var samples := int((_course_bottom - _course_top) / PINCH_STEP)
	if samples < 2 or _measuring:
		return

	var best_y := 0.0
	var best_clear := INF
	var inside := false

	for step in samples + 1:
		var y := _course_top + float(step) * PINCH_STEP
		var clear := _clear_width(y, 0.0, width)
		# A plane with no gap at all is the ceiling or the floor of the
		# course, not a passage through it.
		if clear > 0.0 and clear < threshold:
			# Inside a narrow stretch: remember the tightest point of it.
			if not inside or clear < best_clear:
				best_y = y
				best_clear = clear
			inside = true
			continue
		if inside:
			_build_pinch_gate(root, best_y, best_clear)
			inside = false
			best_clear = INF
	if inside:
		_build_pinch_gate(root, best_y, best_clear)


func _build_pinch_gate(root: Node3D, y: float, clear: float) -> void:
	## Two lit posts either side of the gap, and a ring joining them.
	var centre := _gap_centre(y, clear)
	var half_gap := maxf(to_units(clear) * 0.5, PINCH_POST_WIDTH)

	var post_mesh := BoxMesh.new()
	post_mesh.size = Vector3(
		PINCH_POST_WIDTH, PINCH_POST_HEIGHT, PINCH_POST_DEPTH)
	for side in [-1.0, 1.0]:
		var post := MeshInstance3D.new()
		post.name = "PinchPost%d_%d" % [int(y), int(side)]
		post.mesh = post_mesh
		post.material_override = _palette.light_strip()
		post.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		post.position = to_world(centre, y, PINCH_POST_HEIGHT * 0.5)
		post.position.x += side * (half_gap + PINCH_POST_WIDTH * 0.6)
		root.add_child(post)

	# A bar across the top, so the two posts read as one gate rather than as
	# two unrelated lights.
	var span := half_gap * 2.0 + PINCH_POST_WIDTH * 2.2
	var lintel := BoxMesh.new()
	lintel.size = Vector3(span, PINCH_RING_THICKNESS, PINCH_POST_DEPTH * 0.8)
	var bar := MeshInstance3D.new()
	bar.name = "PinchLintel%d" % int(y)
	bar.mesh = lintel
	bar.material_override = _palette.light_strip()
	bar.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	bar.position = to_world(centre, y, PINCH_POST_HEIGHT)
	root.add_child(bar)


func _gap_centre(y: float, clear: float) -> float:
	## Where the widest gap at this height actually sits.
	##
	## A throat is rarely centred on the course - the split course's pass is at
	## x 800 of 1080 - so a gate drawn on the centre line would stand in the
	## middle of a wall.
	var blocked := _blocked_spans(y)
	if blocked.is_empty():
		return _course_width * 0.5
	var cursor := 0.0
	var best_start := 0.0
	var best_width := -1.0
	for span in blocked:
		if span.x > cursor and span.x - cursor > best_width:
			best_width = span.x - cursor
			best_start = cursor
		cursor = maxf(cursor, span.y)
	if _course_width - cursor > best_width:
		best_start = cursor
		best_width = _course_width - cursor
	return best_start + best_width * 0.5


func _blocked_spans(y: float) -> Array:
	## Every piece the plane at `y` cuts through, projected onto the x axis.
	##
	## A conservative measure: a steeply angled ramp occupies more of the axis
	## than it really blocks, because this takes the axis-aligned extent of a
	## rotated box. It only has to tell a throat from open track, and there the
	## difference is a factor of eight.
	var blocked: Array = []
	for raw in _course.get("pieces", []):
		var spec: Dictionary = raw
		var role := str(spec.get("role", ""))
		# The gate is removed the moment the race starts, so it is not a
		# pinch - it is the start line. Pegs are not walls either: a racer
		# goes round them and between them, and counting them would call
		# every row of plinko a throat.
		if role == "gate" or role == "peg":
			continue
		var piece_y := float(spec.get("y", 0.0))
		var half_x := 0.0
		var half_y := 0.0
		if str(spec.get("type", "")) == "circle":
			half_x = float(spec.get("radius", 0.0))
			half_y = half_x
		else:
			var half_w := float(spec.get("width", 0.0)) * 0.5
			var half_h := float(spec.get("height", 0.0)) * 0.5
			var angle := deg_to_rad(float(spec.get("rotation_degrees", 0.0)))
			half_x = absf(half_w * cos(angle)) + absf(half_h * sin(angle))
			half_y = absf(half_w * sin(angle)) + absf(half_h * cos(angle))
		if absf(y - piece_y) > half_y:
			continue
		var piece_x := float(spec.get("x", 0.0))
		blocked.append(Vector2(piece_x - half_x, piece_x + half_x))
	blocked.sort_custom(func(a, b): return a.x < b.x)
	return blocked


func _clear_width(y: float, left: float, right: float) -> float:
	## The widest gap a racer could pass through at this height.
	var blocked := _blocked_spans(y)
	if blocked.is_empty():
		return right - left

	var widest := 0.0
	var cursor := left
	for span in blocked:
		if span.x > cursor:
			widest = maxf(widest, span.x - cursor)
		cursor = maxf(cursor, span.y)
	return maxf(widest, right - cursor)


func _build_finish_gate(root: Node3D, finish: Dictionary) -> void:
	## The one place on the course a viewer must understand without text.
	if finish.is_empty():
		return

	var y := float(finish.get("y", 0.0))
	var half := to_units(_course_width) * 0.5

	_finish_gate = Node3D.new()
	_finish_gate.name = "FinishGate"
	_finish_gate.position = to_world(_course_width * 0.5, y, 0.0)
	root.add_child(_finish_gate)

	var bar_mesh := BoxMesh.new()
	bar_mesh.size = Vector3(half * 2.0, FINISH_BAR_HEIGHT, FINISH_BAR_THICKNESS)
	var bar := MeshInstance3D.new()
	bar.name = "Bar"
	bar.mesh = bar_mesh
	bar.material_override = _palette.checkpoint_bar(true)
	bar.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	bar.position = Vector3(0.0, FINISH_BAR_HEIGHT * 0.5, 0.0)
	_finish_gate.add_child(bar)
	_finish_materials.append(bar.material_override)

	if _measuring:
		return
	var post_mesh := BoxMesh.new()
	post_mesh.size = Vector3(FINISH_POST_WIDTH, FINISH_POST_HEIGHT, FINISH_POST_WIDTH)
	for side in [-1.0, 1.0]:
		var post := MeshInstance3D.new()
		post.name = "Post%d" % int(side)
		post.mesh = post_mesh
		post.material_override = _palette.checkpoint_bar(true)
		post.position = Vector3(
			side * (half - FINISH_POST_WIDTH * 0.5),
			FINISH_POST_HEIGHT * 0.5, 0.0)
		_finish_gate.add_child(post)
		_finish_materials.append(post.material_override)

	for material in _finish_materials:
		_finish_base_energy.append(material.emission_energy_multiplier)


func _build_spinners() -> void:
	## A hub and its arms on one pivot, exactly as the simulation builds them.
	##
	## The arms are placed at their rest angles and never touched again: every
	## frame writes one rotation into the pivot, taken from what the
	## simulation actually did. Nothing here integrates an angular speed, so
	## playback cannot drift away from the race it is showing.
	var spinners: Array = _course.get("spinners", [])
	if spinners.is_empty():
		return

	var root := Node3D.new()
	root.name = "Spinners"
	add_child(root)

	var body_material: StandardMaterial3D = _palette.spinner_body()
	var edge_material: StandardMaterial3D = _palette.spinner_edge()

	for raw in spinners:
		var spec: Dictionary = raw
		var pivot := Node3D.new()
		pivot.name = "Spinner%d" % int(spec.get("id", 0))
		pivot.position = to_world(
			float(spec.get("x", 0.0)), float(spec.get("y", 0.0)), 0.0)
		root.add_child(pivot)

		var hub_height := MEASURED_HEIGHT if _measuring else SPINNER_HUB_HEIGHT
		var arm_height := MEASURED_HEIGHT if _measuring else SPINNER_ARM_HEIGHT
		var hub_radius := to_units(float(spec.get("hub_radius", 0.0)))
		var hub := CylinderMesh.new()
		hub.top_radius = hub_radius if _measuring else hub_radius * 0.82
		hub.bottom_radius = hub_radius
		hub.height = hub_height
		hub.radial_segments = 24
		var hub_node := MeshInstance3D.new()
		hub_node.name = "Hub"
		hub_node.mesh = hub
		hub_node.material_override = body_material
		hub_node.position = Vector3(0.0, hub_height * 0.5, 0.0)
		pivot.add_child(hub_node)

		# A lit collar around the hub, so the axis of rotation is obvious even
		# when an arm is pointing straight at the camera.
		if not _measuring:
			_build_collar(pivot, hub_radius, hub_height, edge_material)
		var arm_count := maxi(1, int(spec.get("arm_count", 1)))
		var arm_length := to_units(float(spec.get("arm_length", 0.0)))
		var arm_thickness := to_units(float(spec.get("arm_thickness", 0.0)))
		var distance := hub_radius + arm_length * 0.5
		var step := 360.0 / float(arm_count)

		for index in arm_count:
			# The rest angle in *simulation* degrees. The same mirror applies
			# to a child's placement as to the pivot's rotation, so the offset
			# is computed with simulation trigonometry and the box is then
			# turned by the negated angle to lie along it.
			var angle := deg_to_rad(float(index) * step)
			var arm_node := Node3D.new()
			arm_node.name = "Arm%d" % index
			arm_node.position = Vector3(
				distance * cos(angle), 0.0, distance * sin(angle))
			arm_node.rotation_degrees = Vector3(0.0, -float(index) * step, 0.0)
			pivot.add_child(arm_node)

			var arm := BoxMesh.new()
			arm.size = Vector3(arm_length, arm_height, arm_thickness)
			var body := MeshInstance3D.new()
			body.name = "Body"
			body.mesh = arm
			body.material_override = body_material
			body.position = Vector3(0.0, arm_height * 0.5, 0.0)
			arm_node.add_child(body)

			if _measuring:
				continue

			# The lit tip. A spinner is the one piece of course that can pick
			# a racer up and put it somewhere else, and the end of the arm is
			# the part that does it - so that is the part that glows.
			var tip := BoxMesh.new()
			tip.size = Vector3(
				arm_length * 0.26, arm_height * 1.06, arm_thickness * 1.08)
			var tip_node := MeshInstance3D.new()
			tip_node.name = "Tip"
			tip_node.mesh = tip
			tip_node.material_override = edge_material
			tip_node.position = Vector3(
				arm_length * 0.37, arm_height * 0.53, 0.0)
			tip_node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			arm_node.add_child(tip_node)

		_spinner_pivots[int(spec.get("id", 0))] = pivot


# --- racers ---------------------------------------------------------------

func _build_collar(pivot: Node3D, hub_radius: float, hub_height: float,
		edge_material: StandardMaterial3D) -> void:
	## A lit collar around a hub, so the axis of rotation is obvious even when
	## an arm points straight at the camera.
	var collar := TorusMesh.new()
	collar.inner_radius = hub_radius * 0.92
	collar.outer_radius = hub_radius * 1.16
	collar.rings = 28
	collar.ring_segments = 6
	var node := MeshInstance3D.new()
	node.name = "Collar"
	node.mesh = collar
	node.material_override = edge_material
	node.position = Vector3(0.0, hub_height * 0.86, 0.0)
	node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	pivot.add_child(node)


func _build_racers() -> void:
	var root := Node3D.new()
	root.name = "Racers"
	add_child(root)

	for meta in _racer_meta:
		var radius := to_units(float(meta.get("radius", 30.0)))
		var color := _color_of(meta)
		var racer_id := int(meta.get("id", 0))

		# The pivot carries position and the squash; the sphere inside it
		# carries the roll. Separating them is what lets a racer be squashed
		# along the axis it was hit on while still rolling about its own.
		var pivot := Node3D.new()
		pivot.name = "Racer%d" % racer_id
		root.add_child(pivot)

		var mesh := SphereMesh.new()
		mesh.radius = radius
		mesh.height = radius * 2.0
		mesh.radial_segments = 40
		mesh.rings = 20

		var live: StandardMaterial3D = _palette.racer(color, false)
		var done: StandardMaterial3D = _palette.racer(color, true)
		if _measuring:
			live = _palette.racer_flat(color)
			done = live

		var sphere := MeshInstance3D.new()
		sphere.name = "Body"
		sphere.mesh = mesh
		sphere.material_override = live
		pivot.add_child(sphere)

		# A meridian ring: a torus lying in the plane the sphere spins
		# through, so it sweeps as the racer rolls. Without it a spinning
		# sphere and a still one are the same picture.
		var band := TorusMesh.new()
		band.inner_radius = radius * BAND_SCALE - BAND_THICKNESS
		band.outer_radius = radius * BAND_SCALE
		band.rings = 32
		band.ring_segments = 8
		var band_node := MeshInstance3D.new()
		band_node.name = "Band"
		band_node.mesh = band
		band_node.material_override = _palette.racer_band(color)
		band_node.rotation_degrees = Vector3(90.0, 0.0, 0.0)
		band_node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		band_node.visible = not _measuring
		sphere.add_child(band_node)

		# Both would bias the silhouette the alignment check measures: the
		# band is a paler stripe across the ball, the number floats over it.
		if not _measuring:
			_build_badge(pivot, racer_id, color, radius)

		_racer_nodes.append(pivot)
		_racer_spheres.append(sphere)
		_racer_bands.append(band_node)
		_racer_live.append(live)
		_racer_done.append(done)
		_racer_radius.append(radius)
		_racer_colors.append(color)


func _build_badge(pivot: Node3D, racer_id: int, color: Color,
		radius: float) -> void:
	## The racer's number, on a disc above it.
	##
	## Above rather than on: a number painted on a rolling sphere spends most
	## of its time on the far side, and the moment a viewer wants to read it
	## is the moment a racer is in a pile-up. Billboarded and fixed-size, so
	## it stays square to the camera and the same size wherever it is on a
	## perspective frame - a number that shrinks with distance is a number
	## nobody reads.
	var badge := Node3D.new()
	badge.name = "Badge"
	badge.position = Vector3(0.0, radius + BADGE_RISE, 0.0)
	pivot.add_child(badge)

	var label := Label3D.new()
	label.name = "Number"
	label.text = str(racer_id + 1)
	label.font_size = BADGE_FONT_SIZE
	label.pixel_size = BADGE_PIXEL_SIZE
	label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	label.shaded = false
	label.double_sided = true
	label.alpha_cut = Label3D.ALPHA_CUT_DISCARD
	# The number is the racer's own colour against a heavy black outline,
	# which is what makes it legible over a bright pad, a dark ramp or another
	# racer without needing a plate behind it. An earlier version put the text
	# at the centre of a small sphere; the sphere won the depth test and the
	# numbers were never seen at all.
	label.modulate = color.lightened(0.45)
	label.outline_modulate = Color(0.0, 0.0, 0.0, 0.9)
	label.outline_size = BADGE_OUTLINE
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	label.render_priority = 2
	label.outline_render_priority = 1
	badge.add_child(label)


func _update_racers(current: Array, upcoming: Array, blend: float,
		tick: float) -> void:
	for index in _racer_nodes.size():
		if index >= current.size():
			continue
		var now: Dictionary = current[index]
		var soon: Dictionary = upcoming[index] if index < upcoming.size() else now
		var pivot := _racer_nodes[index]

		# A retired racer was taken out of the simulation's space, so it is
		# taken out of the picture too rather than left lying on the course.
		if bool(now.get("retired", false)):
			pivot.visible = false
			continue
		pivot.visible = true

		# Interpolation is cosmetic: the replay data is never modified.
		var x := lerpf(float(now.get("x", 0.0)), float(soon.get("x", 0.0)), blend)
		var y := lerpf(float(now.get("y", 0.0)), float(soon.get("y", 0.0)), blend)
		var spin := lerp_angle(
			deg_to_rad(float(now.get("rotation_degrees", 0.0))),
			deg_to_rad(float(soon.get("rotation_degrees", 0.0))),
			blend)

		var radius := _racer_radius[index]
		pivot.position = to_world(x, y, radius)

		var sphere := _racer_spheres[index]
		# A racer rolls about the axis out of the simulation plane, which is
		# world Y, and the plane is mirrored - so the angle is negated here
		# exactly as a ramp's is.
		sphere.rotation.y = -spin

		var finished := bool(now.get("finished", false))
		sphere.material_override = _racer_done[index] if finished \
			else _racer_live[index]

		if not _measuring:
			_apply_squash(pivot, index, tick)


func _apply_squash(pivot: Node3D, index: int, tick: float) -> void:
	## Compress the racer along the axis it was hit on, and let it back out.
	##
	## Scale on the pivot, not the sphere, because the sphere is carrying the
	## roll - and a squash applied after a rotation would shear rather than
	## flatten. Nothing here touches position: the racer stays exactly where
	## the replay put it, and only its shape reacts.
	var hit: Dictionary = _vfx.squash_for(index, tick)
	var amount := float(hit.get("amount", 0.0))
	if amount <= 0.0:
		pivot.basis = Basis()
		return

	# The axis is taken from where the collision was recorded to where the
	# racer is now, so the ball flattens against the thing that hit it and
	# keeps doing so as it is pushed away.
	var axis: Vector3 = pivot.position - (hit.get("at", pivot.position) as Vector3)
	axis.y = 0.0
	var squash := 1.0 - amount * SQUASH_MAX
	var stretch := 1.0 / sqrt(maxf(0.05, squash))

	# Build a frame with the impact axis as local X, scale that axis down and
	# the other two up, and put the frame back. Volume stays roughly constant,
	# which is what makes it read as a compression rather than a shrink.
	var forward := axis.normalized()
	if forward.length_squared() < 0.5:
		forward = Vector3.FORWARD
	var up := Vector3.UP
	if absf(forward.dot(up)) > 0.95:
		up = Vector3.RIGHT
	var side := up.cross(forward).normalized()
	var lifted := forward.cross(side).normalized()

	var frame := Basis(forward, lifted, side)
	pivot.basis = frame * Basis.from_scale(
		Vector3(squash, stretch, stretch)) * frame.inverse()


# --- trails, spinners, gates, finish --------------------------------------

func _build_trails() -> void:
	_trails = RaceTrails.new()
	_trails.name = "Trails"
	add_child(_trails)
	_trails.configure(_racer_colors, _racer_radius, _frames, Callable(self, "to_world"))


func _update_trails(index: int, blend: float, tick: float) -> void:
	if _measuring:
		return
	_trails.update_to_frame(index, blend, _vfx)


func _build_vfx() -> void:
	_vfx = RaceVFX.new()
	_vfx.name = "VFXRoot"
	add_child(_vfx)
	_vfx.configure(_racer_colors, _physics_hz, Callable(self, "to_world"))
	# Under the measuring lens the effects still track the events - the racers
	# ask the same object how hard they were hit - but nothing is drawn.
	_vfx.set_silent(_measuring)
	_vfx.set_events(_replay.get("events", []))


func _update_spinners(current: Array, upcoming: Array, blend: float) -> void:
	## Move the spinners purely from what the replay recorded.
	##
	## No motion is computed here: the viewer never reads angular speed or
	## start angle, only the transform Python actually had. The angle is
	## blended the short way round so an arm crossing 359 to 1 degree keeps
	## turning forwards instead of unwinding almost a full circle.
	if _spinner_pivots.is_empty():
		return

	var next_by_id := {}
	for raw in upcoming:
		var soon: Dictionary = raw
		next_by_id[int(soon.get("id", -1))] = soon

	for raw in current:
		var now: Dictionary = raw
		var id := int(now.get("id", -1))
		var pivot: Node3D = _spinner_pivots.get(id)
		if pivot == null:
			continue

		var x := float(now.get("x", 0.0))
		var y := float(now.get("y", 0.0))
		var angle := deg_to_rad(float(now.get("rotation_degrees", 0.0)))
		if next_by_id.has(id):
			var soon: Dictionary = next_by_id[id]
			x = lerpf(x, float(soon.get("x", x)), blend)
			y = lerpf(y, float(soon.get("y", y)), blend)
			angle = lerp_angle(
				angle, deg_to_rad(float(soon.get("rotation_degrees", 0.0))), blend)

		pivot.position = to_world(x, y, 0.0)
		pivot.rotation.y = -angle


func _update_gates(frame: Dictionary) -> void:
	## The gate is removed from the simulation, not moved, so it is a state
	## rather than a transform: the frame says whether it is still there.
	var open := bool(frame.get("gates_open", false))
	if open == _gates_hidden:
		return
	_gates_hidden = open
	for node in _gate_nodes:
		node.visible = not open


func _update_pads(tick: float) -> void:
	## A jump pad flares on the tick it launches a racer.
	##
	## Which pad fired comes out of the replay - the jump event names the
	## piece - so nothing here works out who touched what. A pad that never
	## fires never brightens, which is what makes the flare mean something.
	if _measuring:
		return
	for piece_id in _pad_materials.keys():
		var pulse: float = _vfx.pad_pulse_for(piece_id, tick)
		var material: StandardMaterial3D = _pad_materials[piece_id]
		material.emission_energy_multiplier = \
			float(_pad_base_energy[piece_id]) * (1.0 + pulse * PAD_FLARE)


func _update_finish(tick: float) -> void:
	## The finish line answers when it is crossed.
	##
	## One brightening, driven from the winner event's tick, so the moment a
	## viewer is watching for is marked on the course itself rather than only
	## in the overlay. The gate keeps a raised glow afterwards - the race is
	## over and the line is the subject.
	if _measuring or _finish_materials.is_empty() or _winner_tick < 0.0:
		return
	var seconds := (tick - _winner_tick) / _physics_hz
	var pulse := 0.0
	if seconds >= 0.0:
		# A hard flash that decays into a steady lift.
		pulse = 2.6 * exp(-seconds * 4.5) + 0.55 * clampf(seconds / 0.4, 0.0, 1.0)
	for index in _finish_materials.size():
		_finish_materials[index].emission_energy_multiplier = \
			_finish_base_energy[index] * (1.0 + pulse)


func _build_hud() -> void:
	_hud = RaceHud.new()
	_hud.name = "RaceHUD"
	add_child(_hud)
	_hud.configure(_replay)


func _color_of(meta: Dictionary) -> Color:
	var raw: Variant = meta.get("color", [])
	if raw is Array and (raw as Array).size() >= 3:
		var rgb: Array = raw
		return Color8(int(rgb[0]), int(rgb[1]), int(rgb[2]))
	return Color.WHITE
