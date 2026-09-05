extends Node3D

## The visual lab's hero scene: four authored modules on one tower, one rig,
## one camera, no replay.
##
## This scene shares nothing with `race_scene.gd`, `neon_scene.gd` or
## `toy_scene.gd`. It does not load a replay, does not read the course, does
## not know what a racer is and cannot affect any of them. That isolation is
## the point: every previous art attempt had to accept whatever geometry the
## simulation's course inferred, and the ceiling those attempts hit was the
## ceiling of inferred geometry. Here the machine is *designed*, and the only
## question being asked is whether a designed machine can reach the reference.
##
## ## The layout, and why it is shaped this way
##
## Four modules on a vertical run of about eighteen units, with the support
## structure standing *behind* them rather than through them:
##
##     16.4  START PLATFORM   eight bays, canopy, lit sign
##             |  feed chute, swinging left
##     11.3  HERO BOWL        dish, machined rim, aqua guard, cradle
##             |  the S, swinging right
##      2.5  COLLECTOR        stepped drum, five blades, gold tray
##
## The masts sit at x = +/-3.9, z = -1.9 - outboard of every module's radius
## and behind its centre - so no column ever passes through a running surface.
## That constraint is what forced the back-frame design, and the back frame is
## also what the reference actually has: look at its alternative-angle panel
## and the dark lattice is behind the track, never inside it.
##
## The two chutes swing to opposite sides. That is composition, not physics: a
## single S reads as a squiggle, and two curves mirroring each other around a
## central bowl read as a machine with a plan.
##
## ## What the camera is for
##
## `--lab-shot` selects a lens. The hero shot frames the whole run at a fixed
## vertical extent and varies only the field of view, so the five-way lens
## sweep the brief asks for compares *compression*, not size - the machine is
## the same height in all five frames and only its perspective changes.

const Palette := preload("res://assets/marble_machine/lab_palette.gd")
const Forms := preload("res://assets/marble_machine/lab_forms.gd")
const Tower := preload("res://assets/marble_machine/support_tower/support_tower.gd")
const StartPlatform := preload("res://assets/marble_machine/start_platform/start_platform.gd")
const HeroBowl := preload("res://assets/marble_machine/hero_bowl/hero_bowl.gd")
const SCurve := preload("res://assets/marble_machine/s_curve/s_curve.gd")
const Collector := preload("res://assets/marble_machine/collector/collector.gd")
const Backdrop := preload("res://assets/marble_machine/backdrop/backdrop.gd")

# --- the layout -----------------------------------------------------------

const TOWER_TOP := 17.7
const START_Y := 16.4
const BOWL_Y := 11.3
const COLLECTOR_Y := 2.5
const LEVELS := [3.3, 7.2, 10.1, 12.9, 15.6]

const MARBLE_RADIUS := 0.30

# The feed chute: start platform to bowl, swinging left.
const FEED_CONTROLS := [
	Vector3(-1.95, 16.20, 1.05),
	Vector3(-2.85, 15.70, 1.85),
	Vector3(-3.30, 14.85, 2.35),
	Vector3(-3.30, 13.90, 1.70),
	Vector3(-2.85, 13.25, 0.95),
	Vector3(-2.10, 12.95, 0.25),
]

# The S: bowl drain to collector tray, swinging right and hooking back.
const S_CONTROLS := [
	Vector3(0.00, 9.55, 0.30),
	Vector3(1.10, 9.05, 1.45),
	Vector3(2.45, 8.15, 2.35),
	Vector3(2.75, 7.00, 3.20),
	Vector3(1.40, 6.05, 3.75),
	Vector3(-0.60, 5.35, 3.55),
	Vector3(-2.10, 4.60, 2.85),
	Vector3(-2.80, 4.20, 1.75),
	Vector3(-2.35, 3.80, 0.85),
]

# --- the lenses -----------------------------------------------------------
#
# `aim` is the height the camera looks at, `extent` the vertical span the
# frame is fitted to. Distance is derived from those two and the field of
# view, so changing the lens never changes how much machine is in shot.
const SHOTS := {
	"hero": {"aim": 9.6, "extent": 19.4, "fov": 35.0, "elevation": 18.0, "azimuth": 33.0},
	"fov30": {"aim": 9.2, "extent": 20.4, "fov": 30.0, "elevation": 10.0, "azimuth": 32.0},
	"fov35": {"aim": 9.2, "extent": 20.4, "fov": 35.0, "elevation": 10.0, "azimuth": 32.0},
	"fov40": {"aim": 9.2, "extent": 20.4, "fov": 40.0, "elevation": 10.0, "azimuth": 32.0},
	"fov45": {"aim": 9.2, "extent": 20.4, "fov": 45.0, "elevation": 10.0, "azimuth": 32.0},
	"fov50": {"aim": 9.2, "extent": 20.4, "fov": 50.0, "elevation": 10.0, "azimuth": 32.0},
	"elev04": {"aim": 9.2, "extent": 20.4, "fov": 35.0, "elevation": 4.0, "azimuth": 32.0},
	"elev18": {"aim": 9.4, "extent": 20.4, "fov": 35.0, "elevation": 18.0, "azimuth": 32.0},
	"elev26": {"aim": 9.6, "extent": 20.8, "fov": 35.0, "elevation": 26.0, "azimuth": 32.0},
	"azi00": {"aim": 9.2, "extent": 20.4, "fov": 35.0, "elevation": 10.0, "azimuth": 0.0},
	"azi55": {"aim": 9.2, "extent": 20.4, "fov": 35.0, "elevation": 10.0, "azimuth": 55.0},
	# Product lenses: one module each, same rig, longer glass.
	"bowl": {"aim": 11.5, "extent": 9.4, "fov": 30.0, "elevation": 22.0, "azimuth": 38.0},
	"start": {"aim": 17.2, "extent": 5.6, "fov": 30.0, "elevation": 12.0, "azimuth": 30.0},
	"collector": {"aim": 3.3, "extent": 9.0, "fov": 30.0, "elevation": 26.0, "azimuth": 44.0},
	"upper": {"aim": 13.4, "extent": 12.0, "fov": 33.0, "elevation": 8.0, "azimuth": 34.0},
}

const DEFAULT_SHOT := "hero"

var _palette
var _camera: Camera3D
var _environment: Environment
var _rotor: Node3D
var _shot := DEFAULT_SHOT
var _variant := "tower"
var _no_glow := false
var _feed_path: Array = []
var _s_path: Array = []
var _travellers: Array = []
var _orbit := 0.0


func _ready() -> void:
	var options := _options()
	_variant = str(options.get("lab-variant", "tower"))
	_shot = str(options.get("lab-shot", DEFAULT_SHOT))
	_no_glow = str(options.get("lab-no-glow", "")) != ""
	if not SHOTS.has(_shot):
		push_error("lab_scene: unknown shot '%s'" % _shot)
		_shot = DEFAULT_SHOT

	_palette = Palette.new(_variant)

	_build_environment()
	_build_lights()
	_build_machine()
	_build_camera()
	set_time(0.0)


func _options() -> Dictionary:
	var options := {}
	for argument in OS.get_cmdline_user_args():
		var arg: String = argument
		if not arg.begins_with("--"):
			continue
		var split := arg.substr(2).split("=", true, 1)
		if split.size() == 2:
			options[split[0]] = split[1]
	return options


# --- environment ----------------------------------------------------------

func _build_environment() -> void:
	## Dark, but never black, and tone-mapped like a product photograph.
	##
	## The sky is the part that matters. A clearcoat lobe has nothing to
	## reflect in a black room, so every glossy surface in the style-lock
	## render was carrying its highlight from three direct lights and nothing
	## else. A dim graded sky costs no shadow work and returns a faint sheen
	## along every rounded edge in the machine - which is the difference
	## between "rendered" and "photographed".
	var sky_material := ProceduralSkyMaterial.new()
	sky_material.sky_top_color = Color("#0C1822")
	sky_material.sky_horizon_color = Color("#193544")
	sky_material.sky_curve = 0.14
	sky_material.ground_bottom_color = Color("#0C1219")
	sky_material.ground_horizon_color = Color("#193544")
	sky_material.sun_angle_max = 30.0
	sky_material.energy_multiplier = 1.0

	var sky := Sky.new()
	sky.sky_material = sky_material

	_environment = Environment.new()
	_environment.background_mode = Environment.BG_SKY
	_environment.sky = sky
	_environment.background_energy_multiplier = 0.62
	_environment.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	_environment.ambient_light_sky_contribution = 1.0
	_environment.ambient_light_energy = 0.25
	_environment.reflected_light_source = Environment.REFLECTION_SOURCE_SKY

	_environment.tonemap_mode = Environment.TONE_MAPPER_ACES
	_environment.tonemap_exposure = 1.0
	_environment.tonemap_white = 6.0

	# Depth haze. The reference's background sits three or four stops under
	# its subject and gets there through atmosphere, not through a darker
	# paint - which is why its distant shapes still read as shapes.
	_environment.fog_enabled = true
	_environment.fog_light_color = Color("#173340")
	_environment.fog_light_energy = 0.8
	_environment.fog_density = 0.017
	_environment.fog_sky_affect = 0.25
	_environment.fog_aerial_perspective = 0.45

	_environment.ssao_enabled = true
	_environment.ssao_radius = 0.9
	_environment.ssao_intensity = 2.6
	_environment.ssao_power = 1.4
	_environment.ssao_light_affect = 0.15

	_environment.ssr_enabled = true
	_environment.ssr_max_steps = 48
	_environment.ssr_fade_in = 0.2
	_environment.ssr_fade_out = 2.0

	if not _no_glow:
		_environment.glow_enabled = true
		_environment.glow_intensity = 0.95
		_environment.glow_bloom = 0.18
		_environment.glow_hdr_threshold = 0.92
		_environment.glow_hdr_scale = 2.0
		_environment.glow_blend_mode = Environment.GLOW_BLEND_MODE_SOFTLIGHT
		for level in 7:
			_environment.set_glow_level(level, 0.0)
		_environment.set_glow_level(1, 0.35)
		_environment.set_glow_level(2, 0.7)
		_environment.set_glow_level(3, 0.9)
		_environment.set_glow_level(4, 0.5)

	_environment.adjustment_enabled = true
	_environment.adjustment_contrast = 1.16
	_environment.adjustment_saturation = 1.14
	_environment.adjustment_brightness = 1.0

	var world := WorldEnvironment.new()
	world.name = "WorldEnvironment"
	world.environment = _environment
	add_child(world)


func _build_lights() -> void:
	## Product photography: one hard key, one cool rim, one warm bounce, and
	## three practicals that belong to the machine rather than to the studio.
	##
	## The style-lock rig failed the brief's contrast test by being *only*
	## soft: it had no source hard enough to throw a readable shadow, so the
	## machine had no darks and the frame flattened. The key here is a single
	## directional with a tight shadow, and the fill is deliberately half a
	## stop weaker than it wants to be.
	var key := DirectionalLight3D.new()
	key.name = "Key"
	key.light_color = Color("#FFF3E2")
	key.light_energy = 3.0
	key.light_specular = 1.0
	key.shadow_enabled = true
	key.directional_shadow_mode = DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS
	key.directional_shadow_max_distance = 70.0
	key.directional_shadow_blend_splits = true
	key.shadow_bias = 0.035
	key.shadow_normal_bias = 1.2
	key.rotation_degrees = Vector3(-46.0, -38.0, 0.0)
	add_child(key)

	var rim := DirectionalLight3D.new()
	rim.name = "Rim"
	rim.light_color = Color("#8FD9FF")
	rim.light_energy = 1.9
	rim.light_specular = 1.4
	rim.shadow_enabled = false
	rim.rotation_degrees = Vector3(-12.0, 158.0, 0.0)
	add_child(rim)

	var fill := DirectionalLight3D.new()
	fill.name = "Fill"
	fill.light_color = Color("#FFD2AC")
	fill.light_energy = 0.40
	fill.light_specular = 0.2
	fill.shadow_enabled = false
	fill.rotation_degrees = Vector3(18.0, 44.0, 0.0)
	add_child(fill)

	_practical("StartPractical", Vector3(0.0, START_Y + 1.5, 1.6),
		Color("#5FE6FF"), 3.6, 7.0)
	_practical("BowlPractical", Vector3(0.0, BOWL_Y + 0.9, 0.0),
		Color("#9E7CFF"), 2.0, 8.0)
	_practical("CollectorWarm", Vector3(0.0, COLLECTOR_Y + 0.75, 0.0),
		Color("#FFB35C"), 4.6, 9.5)
	_practical("CollectorRim", Vector3(0.0, COLLECTOR_Y + 2.4, 2.2),
		Color("#FFC98A"), 2.2, 8.5)
	_practical("MixerViolet", Vector3(-1.2, BOWL_Y - 1.6, 1.5),
		Color("#9A6CFF"), 2.6, 7.5)
	_practical("BaseWarm", Vector3(0.0, 1.3, 1.8),
		Color("#FFA451"), 3.6, 8.5)
	_practical("BowlTop", Vector3(0.6, BOWL_Y + 3.1, 1.4),
		Color("#EAF4FF"), 1.5, 6.0)


func _practical(node_name: String, at: Vector3, colour: Color, energy: float,
		range_units: float) -> void:
	## A lamp that belongs to the machine. Shadows off: a practical's job is
	## to wash a local surface, and shadow-casting omnis at this count cost
	## more than the picture gains.
	if energy <= 0.0:
		return
	var lamp := OmniLight3D.new()
	lamp.name = node_name
	lamp.position = at
	lamp.light_color = colour
	lamp.light_energy = energy
	lamp.omni_range = range_units
	lamp.omni_attenuation = 1.6
	lamp.shadow_enabled = false
	add_child(lamp)


# --- the machine ----------------------------------------------------------

func _build_machine() -> void:
	add_child(Backdrop.build(_palette))

	var machine := Node3D.new()
	machine.name = "Machine"
	add_child(machine)

	machine.add_child(Tower.build(_palette, LEVELS, TOWER_TOP))

	var collector := Collector.build(_palette)
	collector.position = Vector3(0.0, COLLECTOR_Y, 0.0)
	machine.add_child(collector)
	_rotor = collector.get_node_or_null("Rotor")

	var bowl := HeroBowl.build(_palette)
	bowl.position = Vector3(0.0, BOWL_Y, 0.0)
	machine.add_child(bowl)

	var platform := StartPlatform.build(_palette)
	platform.position = Vector3(0.0, START_Y, 0.55)
	platform.rotation.y = 0.30
	machine.add_child(platform)

	_feed_path = SCurve.path_for(FEED_CONTROLS)
	_s_path = SCurve.path_for(S_CONTROLS)
	machine.add_child(SCurve.build(_palette, FEED_CONTROLS, "FeedChute", "neon_cyan"))
	machine.add_child(SCurve.build(_palette, S_CONTROLS, "SCurve", "neon_violet"))

	_build_marbles(machine, platform)


func _build_marbles(machine: Node3D, platform: Node3D) -> void:
	## Ten racers, spread along the whole run so the eye is led down it.
	##
	## Placement is composition, not simulation. Four wait in the bays, two
	## are on each chute, one sits in the bowl and one in the collector, so
	## every module has a racer in it and the frame reads as a machine in use.
	## Nothing here says anything about how a real field would distribute -
	## the physics phase owns that question and this scene does not answer it.
	var sphere := SphereMesh.new()
	sphere.radius = MARBLE_RADIUS
	sphere.height = MARBLE_RADIUS * 2.0
	sphere.radial_segments = 32
	sphere.rings = 16

	var field := Node3D.new()
	field.name = "Field"
	machine.add_child(field)

	var colour_index := 0
	var slots: Array = StartPlatform.marble_slots()
	for index in [0, 2, 4, 6]:
		var at: Vector3 = slots[index]
		var node := Forms.mesh_node(sphere, _palette.marble(colour_index),
			"BayMarble%d" % index)
		node.position = platform.position + Vector3(
			at.x * cos(platform.rotation.y) + at.z * sin(platform.rotation.y),
			at.y - MARBLE_RADIUS + MARBLE_RADIUS,
			-at.x * sin(platform.rotation.y) + at.z * cos(platform.rotation.y))
		field.add_child(node)
		colour_index += 1

	# Bowl: two on the running surface, at different radii and bearings.
	for pair in [[1.62, -0.14, 2.35], [2.08, 0.14, -0.55], [1.95, 0.06, 1.05], [1.28, -0.34, -1.85]]:
		var radius: float = pair[0]
		var lift: float = pair[1]
		var bearing: float = pair[2]
		var node := Forms.mesh_node(sphere, _palette.marble(colour_index),
			"BowlMarble%d" % colour_index)
		node.position = Vector3(cos(bearing) * radius,
			BOWL_Y + lift + MARBLE_RADIUS * 0.55, sin(bearing) * radius)
		field.add_child(node)
		colour_index += 1

	# Collector: one settled on the gold inlay.
	var settled := Forms.mesh_node(sphere, _palette.marble(colour_index),
		"CollectorMarble")
	settled.position = Vector3(cos(-1.15) * 1.94, COLLECTOR_Y + 0.11,
		sin(-1.15) * 1.94)
	field.add_child(settled)
	colour_index += 1

	# The three travellers, one on the feed chute and two on the S. These are
	# the only marbles a motion proof moves.
	_travellers.clear()
	for entry in [[0, 0.42], [1, 0.38]]:
		var which: int = entry[0]
		var t: float = entry[1]
		var node := Forms.mesh_node(sphere, _palette.marble(colour_index),
			"Traveller%d" % colour_index)
		field.add_child(node)
		_travellers.append({"node": node, "path": which, "phase": t})
		colour_index += 1


# --- camera ---------------------------------------------------------------

func _build_camera() -> void:
	_camera = Camera3D.new()
	_camera.name = "HeroCamera"
	_camera.keep_aspect = Camera3D.KEEP_HEIGHT
	_camera.near = 0.15
	_camera.far = 400.0
	add_child(_camera)
	_camera.current = true
	_place_camera(0.0)


func _place_camera(orbit_offset: float) -> void:
	## Fit the shot's vertical extent exactly, whatever the lens.
	##
	## Distance falls out of the extent and the field of view rather than
	## being typed in, which is the only way a five-way lens comparison says
	## anything: if distance were fixed, a longer lens would just be a crop.
	var shot: Dictionary = SHOTS[_shot]
	var fov := float(shot["fov"])
	var extent := float(shot["extent"])
	var aim := float(shot["aim"])
	var elevation := deg_to_rad(float(shot["elevation"]))
	var azimuth := deg_to_rad(float(shot["azimuth"]) + orbit_offset)

	var distance := (extent * 0.5) / tan(deg_to_rad(fov) * 0.5)
	var target := Vector3(0.0, aim, 0.0)
	var direction := Vector3(
		sin(azimuth) * cos(elevation), sin(elevation), cos(azimuth) * cos(elevation))

	_camera.fov = fov
	_camera.position = target + direction * distance
	_camera.look_at(target, Vector3.UP)


# --- the clock ------------------------------------------------------------

func set_time(seconds: float) -> void:
	## Everything that moves, as a pure function of the output frame's time.
	##
	## Nothing accumulates and nothing reads `delta`, so a render that crawls
	## and one that flies produce identical frames - the same contract the
	## production offline renderer holds itself to.
	if _rotor != null:
		_rotor.rotation.y = seconds * 0.55

	for entry in _travellers:
		var path: Array = _feed_path if int(entry["path"]) == 0 else _s_path
		var t: float = fposmod(float(entry["phase"]) + seconds * 0.11, 1.0)
		var node: Node3D = entry["node"]
		node.position = Forms.sample_at(path, t) + Vector3(0.0, MARBLE_RADIUS, 0.0)

	_orbit = sin(seconds * 0.42) * 5.0
	_place_camera(_orbit)


func shot_names() -> Array:
	return SHOTS.keys()


func set_shot(name: String) -> void:
	if SHOTS.has(name):
		_shot = name
		_place_camera(_orbit)
