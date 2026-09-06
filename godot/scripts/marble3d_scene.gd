extends Node3D

## The authored machine, playing a PyBullet replay.
##
## Godot draws and does nothing else. Every marble position, every rotation and
## every gate movement in this scene is read out of a replay that PyBullet
## finished computing before Godot started, and the machine the marbles move
## through is built from a presentation contract that the same Python run
## wrote. Nothing here integrates, steps, solves or guesses. Search this file
## for a physics class and you will not find one; that is the point of it.
##
## ## The two documents
##
## **The contract** (`marble3d/presentation.py`) says what the machine is: one
## entry per module, giving its origin, its orientation, its bounds, its
## sockets in world space, and a `visual` block of the dimensions its authored
## asset should be built at. The scene does not know that a bowl has a rim or
## how wide the channel is - it asks the contract and hands the answer to the
## asset.
##
## **The replay** says what happened: 60 dense frames a second, every marble in
## every frame, each with position, orientation, linear and angular velocity,
## the module it is in and whether it is still running. Retired marbles stay in
## the array with their pose frozen, so the frame is rectangular and a lookup
## never has to ask whether a marble still exists.
##
## The two are generated together and cross-checked in Python before a render
## is allowed to start, so this file can trust that the bowl it draws is the
## bowl the marbles were solved against.
##
## ## The clock
##
## `set_frame(index)` is a pure function of the output frame index. Nothing
## accumulates, nothing reads `delta`, nothing asks the engine what time it is.
## A render that crawls and a render that flies produce the same images - the
## same contract `lab_scene.gd` and `replay_viewer.gd` hold themselves to.
##
## ## Why the lighting rig is scaled and the geometry is not
##
## The authored assets are re-dimensioned from the contract, so their absolute
## sizes are the physics'. The *lighting* cannot be re-dimensioned that way: an
## omni with a range of 7 was placed against a bowl 2.52 across, and the same
## number against a bowl 16.875 across lights nothing. So the rig keeps its
## authored numbers and multiplies every distance by one factor, `_detail`,
## which is the ratio between the two bowls. One factor, applied in one place,
## rather than fifteen re-tuned constants.

const Palette := preload("res://assets/marble_machine/lab_palette.gd")
const Forms := preload("res://assets/marble_machine/lab_forms.gd")
const Geometry := preload("res://scripts/toy_geometry.gd")
const HeroBowl := preload("res://assets/marble_machine/hero_bowl/hero_bowl.gd")
const SCurve := preload("res://assets/marble_machine/s_curve/s_curve.gd")
const StartPlatform := preload(
	"res://assets/marble_machine/start_platform/start_platform.gd")

## The dish radius hero_bowl.gd was authored at. Everything in the lighting rig
## was placed against a bowl this size, so it is the denominator that turns an
## authored distance into one that suits the simulated machine.
const AUTHORED_DISH_RADIUS := 2.52

const MARBLE_SEGMENTS := 24

## How far above the curve the camera may stand, in degrees.
##
## Measured, not chosen. The curve spirals directly under the dish - it has to,
## because the drain feeds it - so the bowl is a ceiling over the module and
## the shot is caught between two failures. Too flat and the channel is
## edge-on: the near arc of the helix hides the far one and the marbles are
## behind their own guard rail. Too steep and the bowl's outer flank swings
## down across the lens and fills the frame with pearl.
##
## At thirty degrees, on the framing above, the camera ends up tucked *under*
## the bowl's outer overhang - about 16 wu out from the axis and 5 up, which is
## below the dish surface at that radius and outside everything that hangs
## under it. From there two arcs of the spiral read at once with marbles on
## both, which is what says the module is a descent rather than a bend.
##
## The first attempt derived this instead, capping the lens to stay under the
## bowl's *bounding box* - a solid 38-wide slab from -3.5 up, which is not the
## shape of a bowl. It gave two degrees and a photograph of a rail.
##
## It is a constant rather than a formula because it belongs to this bowl over
## this curve at this framing, and all three are placeholders that Track V2
## replaces. Re-measure it then; do not port the number.
const CURVE_ELEVATION := 30.0

var _palette
var _contract: Dictionary = {}
var _replay: Dictionary = {}
var _frames: Array = []
var _replay_fps := 60.0
var _output_fps := 60.0
var _detail := 1.0
var _marble_radius := 0.5

var _camera: Camera3D
var _shots: Dictionary = {}
var _cuts: Array = []
var _marbles: Array = []
var _gates: Array = []
var _debug := false
var _no_glow := false


# --- construction ---------------------------------------------------------

func configure(contract: Dictionary, replay: Dictionary, options: Dictionary) -> void:
	## Everything the scene needs, before it enters the tree.
	_contract = contract
	_replay = replay
	_frames = replay.get("frames", [])
	_replay_fps = float(replay.get("replay_fps", 60))
	_output_fps = float(options.get("fps", 60.0))
	_debug = bool(options.get("debug", false))
	_no_glow = bool(options.get("no_glow", false))
	_marble_radius = float(contract.get("marble_radius", 0.5))
	_palette = Palette.new(str(options.get("variant", "tower")))
	_detail = _bowl_visual().get("detail_scale", 1.0)


func build() -> void:
	_build_environment()
	_build_lights()
	_build_machine()
	_build_marbles()
	_build_shots()
	_build_camera()
	if _debug:
		_build_debug()
	set_frame(0)


func _module(module_id: String) -> Dictionary:
	for entry in _contract.get("modules", []):
		if str(entry.get("id", "")) == module_id:
			return entry
	return {}


func _bowl_visual() -> Dictionary:
	return _module("bowl").get("visual", {})


static func _v3(values) -> Vector3:
	return Vector3(float(values[0]), float(values[1]), float(values[2]))


static func _quat(values) -> Quaternion:
	## The contract's quaternions are XYZW, which is the order this constructor
	## takes. PyBullet and Godot are both right-handed with +Y up, so there is
	## no conversion here beyond reading the components in order.
	return Quaternion(
		float(values[0]), float(values[1]), float(values[2]), float(values[3]))


static func _placement(entry: Dictionary) -> Transform3D:
	return Transform3D(Basis(_quat(entry["orientation"])), _v3(entry["origin"]))


# --- the machine ----------------------------------------------------------

func _build_machine() -> void:
	## One authored asset per simulated module, at the contract's dimensions.
	##
	## The support tower the visual lab hangs its machine off is deliberately
	## not built. It was drawn to carry a machine laid out differently from
	## this one, so its masts would stand in places nothing needs holding up -
	## and two of them crossed the bowl's action area even in the lab, which
	## the visual review called out. Leaving it out is the smallest change that
	## clears the sightline; putting it back means re-authoring where its legs
	## land, which is a set-dressing job and not this one.
	var machine := Node3D.new()
	machine.name = "Machine"
	add_child(machine)

	for entry in _contract.get("modules", []):
		var asset := str(entry.get("visual_asset", ""))
		var visual: Dictionary = entry.get("visual", {})
		var placed := _placement(entry)
		var holder := Node3D.new()
		holder.name = "Module_%s" % str(entry.get("id", "?"))
		holder.transform = placed
		machine.add_child(holder)

		match asset:
			"hero_bowl":
				var bowl: Node3D = HeroBowl.build(_palette, visual)
				# The asset's local origin is the outer edge of its dish and
				# the module's origin is the dish floor, so the bowl is lifted
				# by the one number that reconciles them.
				bowl.position = Vector3(0.0, float(visual["outer_depth"]), 0.0)
				holder.add_child(bowl)
			"s_curve":
				# The centreline in the contract is already in world space, so
				# the channel is added to the machine rather than to the
				# module holder - placing it twice would move it twice.
				var curve: Node3D = SCurve.build(
					_palette, [], "SCurve", "neon_cyan", visual)
				machine.add_child(curve)
			"start_platform":
				# World space, like the curve: the chute is swept along the
				# contract's centreline and its stations sit on the contract's
				# bay positions, both of which are already placed. Adding it
				# to the holder would apply the module transform a second time.
				var start: Node3D = StartPlatform.build(_palette, visual)
				machine.add_child(start)
				_collect_gates(start, entry)
			_:
				push_error("no authored asset named %s" % asset)


func _collect_gates(holder: Node3D, entry: Dictionary) -> void:
	## Find the actuator nodes the scene has to drive, once, at build time.
	##
	## Looked up by name rather than by index because an asset is free to add
	## detail children; what it is not free to do is rename the part the
	## contract says moves.
	for actuator in entry.get("actuators", []):
		var node := holder.find_child(str(actuator.get("name", "")).capitalize(),
			true, false)
		if node == null:
			node = holder.find_child(str(actuator.get("name", "")), true, false)
		if node is Node3D:
			_gates.append({"node": node, "actuator": actuator, "holder": holder})


# --- marbles --------------------------------------------------------------

func _build_marbles() -> void:
	## One sphere per marble in the replay, in the eight candy hues.
	##
	## Each carries a thin interior ribbon in a lighter tint of its own hue.
	## A plain gloss sphere is very nearly rotation-invariant on screen: it can
	## be spinning at fifty radians a second and read as sliding. The ribbon is
	## what makes rolling legible, and it is the feature a candy marble
	## actually has rather than a badge stuck on to carry information.
	var field := Node3D.new()
	field.name = "Marbles"
	add_child(field)

	var sphere := SphereMesh.new()
	sphere.radius = _marble_radius
	sphere.height = _marble_radius * 2.0
	sphere.radial_segments = MARBLE_SEGMENTS
	sphere.rings = MARBLE_SEGMENTS / 2

	var ribbon := _ribbon_mesh()

	_marbles.clear()
	for info in _replay.get("marbles", []):
		var index := int(info.get("id", 0))
		var node := Forms.mesh_node(sphere, _palette.marble(index),
			"Marble%d" % index)
		var inner := Forms.mesh_node(ribbon, _palette.marble_core(index),
			"Ribbon%d" % index, false)
		node.add_child(inner)
		field.add_child(node)
		_marbles.append(node)


func _ribbon_mesh() -> ArrayMesh:
	## A flattened lens through the middle of the marble, just inside its skin.
	var lens: Array = []
	var rounds := 12
	var reach: float = _marble_radius * 0.82
	var thickness: float = _marble_radius * 0.22
	for step in range(rounds + 1):
		var t := float(step) / float(rounds)
		lens.append(Vector2(reach * sin(t * PI), thickness * cos(t * PI)))
	return Geometry.lathe(lens, Geometry.profile_normals(lens, true), 20)


# --- the clock ------------------------------------------------------------

func set_frame(index: int) -> void:
	## Everything that moves, as a pure function of the output frame index.
	##
	## The replay is sampled at 60 fps and the render is too, so at the default
	## rate this is an exact lookup and no marble is ever drawn anywhere the
	## solver did not put it. The interpolating branch exists for a render at
	## some other rate and is deliberately a plain lerp/slerp between two
	## recorded frames rather than anything that could be called a trajectory.
	if _frames.is_empty():
		return
	var position_in_replay: float = float(index) * _replay_fps / _output_fps
	var low := int(floor(position_in_replay))
	var last: int = _frames.size() - 1
	if low >= last:
		_apply_frame(_frames[last], _frames[last], 0.0)
	else:
		var blend: float = position_in_replay - float(low)
		if is_zero_approx(blend):
			_apply_frame(_frames[low], _frames[low], 0.0)
		else:
			_apply_frame(_frames[low], _frames[low + 1], blend)

	_apply_actuators(float(index) / _output_fps)
	_place_camera(index)


func _apply_frame(frame: Dictionary, next: Dictionary, blend: float) -> void:
	var records: Array = frame.get("marbles", [])
	var following: Array = next.get("marbles", [])
	for slot in records.size():
		if slot >= _marbles.size():
			break
		var record: Dictionary = records[slot]
		var node: Node3D = _marbles[slot]
		var at := _v3(record["p"])
		var spin := _quat(record["q"])
		if blend > 0.0 and slot < following.size():
			var ahead: Dictionary = following[slot]
			at = at.lerp(_v3(ahead["p"]), blend)
			spin = spin.slerp(_quat(ahead["q"]), blend)
		node.transform = Transform3D(Basis(spin), at)


func _apply_actuators(seconds: float) -> void:
	## The gate, from the contract's own release schedule.
	##
	## Driven from the actuator description rather than from a per-frame
	## actuator sample because the replay writes the gate's position without
	## its rotation, and a box drawn at the recorded position with no rotation
	## lies across a chute that is itself turned a long way off axis.
	for gate in _gates:
		var actuator: Dictionary = gate["actuator"]
		var release := float(actuator.get("release_time", 0.0))
		var duration := maxf(float(actuator.get("duration", 0.0)), 1e-6)
		var travelled := clampf((seconds - release) / duration, 0.0, 1.0)
		var rest: Dictionary = actuator["rest"]
		var world := Transform3D(
			Basis(_quat(rest["rotation"])),
			_v3(rest["position"]) + _v3(actuator["travel"]) * travelled)
		var holder: Node3D = gate["holder"]
		var node: Node3D = gate["node"]
		node.global_transform = world if node.is_inside_tree() \
			else holder.transform.affine_inverse() * world


# --- camera ---------------------------------------------------------------

func _build_shots() -> void:
	## Three lenses, aimed from the contract rather than from typed-in numbers.
	##
	## The visual lab's hero framing - 35 degrees, 18 up, 33 round - is a rig
	## of angles plus a vertical extent to fit, and angles do not care how big
	## the machine is. So the angles carry over unchanged and only the target
	## and the extent are recomputed here, which is why these shots look like
	## the approved stills of a machine five times smaller.
	var bowl := _module("bowl")
	var bowl_visual: Dictionary = bowl.get("visual", {})
	var bowl_anchors: Dictionary = bowl.get("anchors", {})
	var bowl_centre := _v3(bowl_anchors["centre"])
	var outer: float = float(bowl_visual["outer_radius"])
	var outer_depth: float = float(bowl_visual["outer_depth"])

	var start := _module("start")
	var bays: Array = start.get("visual", {}).get("bays", [])
	var bay_centre := bowl_centre
	var queue_span := 0.0
	if not bays.is_empty():
		var total := Vector3.ZERO
		for bay in bays:
			total += _v3(bay["position"])
		bay_centre = total / float(bays.size())
		queue_span = (_v3(bays[0]["position"]) - _v3(bays[-1]["position"])).length()
	# Where the chute hands over. The establishing shot looks down the queue at
	# it, so the release has somewhere to go inside the frame.
	var start_exit := bay_centre
	var exit_socket: Dictionary = start.get("sockets", {}).get("exit", {})
	if exit_socket.has("position"):
		start_exit = _v3(exit_socket["position"])

	var curve := _module("curve")
	var curve_low := _v3(curve["bounds"][0])
	var curve_high := _v3(curve["bounds"][1])
	var curve_centre := (curve_low + curve_high) * 0.5
	# Aimed down the spiral toward the way out, and tighter than the module.
	#
	# The whole 270 degrees will not go in one frame from anywhere a camera can
	# stand: the helix is roofed by the dish that feeds it, and from outside it
	# the near arc covers the far one. Framing all of it produces a picture of
	# the near arc. So the shot gives up on the module and takes the part with
	# the run in it - the descent into the exit - at a little over half the
	# module's diagonal.
	var curve_exit := _v3(curve["sockets"]["exit"]["position"])
	var curve_target := curve_centre.lerp(curve_exit, 0.40)
	var curve_extent: float = (curve_high - curve_low).length() * 0.55

	_shots = {
		# The establishing lens: the loaded queue and the gate it is waiting
		# behind, with the chute running away toward the bowl.
		#
		# Not the whole machine. The first cut of this framed the chute and the
		# bowl together, which is thirty-two units of diagonal, and at that
		# extent eight one-unit marbles are eight pixels in the corner of a
		# frame whose subject is an empty dish. This shot is 0.6 seconds long
		# and it has one job - that there are eight marbles, that they are held,
		# and that they are let go - so it is framed on the thing that does it.
		# The bowl is still in shot, behind and below, because the chute points
		# at it.
		"start": {
			"target": bay_centre.lerp(start_exit, 0.30),
			"extent": maxf(queue_span * 1.85, 4.0 * _marble_radius),
			"fov": 35.0, "elevation": 16.0, "azimuth": 33.0,
		},
		# The bowl. Higher than the hero angle on purpose: at 18 degrees the
		# far rim cuts across the running surface and the dish reads as a
		# disc. At 30 the near rim, the whole interior and the drain are all
		# in frame at once, which is the only way the orbit reads as a marble
		# going round a bowl rather than round a circle.
		"bowl": {
			"target": bowl_centre + Vector3(0.0, outer_depth * 0.30, 0.0),
			"extent": outer * 2.35,
			"fov": 35.0, "elevation": 30.0, "azimuth": 33.0,
		},
		# The curve. Framed on the descent into the exit rather than on the
		# module, and pitched by CURVE_ELEVATION, which the bowl decides.
		"curve": {
			"target": curve_target,
			"extent": curve_extent,
			"fov": 35.0, "elevation": CURVE_ELEVATION, "azimuth": 33.0,
		},
	}


func set_cuts(cuts: Array) -> void:
	## When each shot takes over, as output frame indices.
	_cuts = cuts


func is_cut_frame(index: int) -> bool:
	## Whether this frame is the first of a new shot.
	##
	## The renderer asks so it can draw the frame twice and throw the first
	## away: screen-space reflection and ambient occlusion both carry a frame
	## of history, and the first frame after a camera jump would otherwise
	## shade its reflections against the previous shot's depth buffer.
	for cut in _cuts:
		if int(cut.get("frame", -1)) == index:
			return true
	return false


func shot_at(index: int) -> String:
	var chosen := "bowl"
	for cut in _cuts:
		if index >= int(cut.get("frame", 0)):
			chosen = str(cut.get("shot", chosen))
	return chosen


func _build_camera() -> void:
	_camera = Camera3D.new()
	_camera.name = "MachineCamera"
	_camera.keep_aspect = Camera3D.KEEP_HEIGHT
	_camera.near = 0.15 * _detail
	_camera.far = 400.0 * _detail
	add_child(_camera)
	_camera.current = true


func _place_camera(index: int) -> void:
	## Fit the shot's vertical extent exactly, whatever the lens.
	var name := shot_at(index)
	if not _shots.has(name):
		name = "bowl"
	var shot: Dictionary = _shots[name]
	var fov := float(shot["fov"])
	var extent := float(shot["extent"])
	var target: Vector3 = shot["target"]
	var elevation := deg_to_rad(float(shot["elevation"]))
	var azimuth := deg_to_rad(float(shot["azimuth"]))

	var distance := (extent * 0.5) / tan(deg_to_rad(fov) * 0.5)
	var direction := Vector3(
		sin(azimuth) * cos(elevation), sin(elevation), cos(azimuth) * cos(elevation))

	_camera.fov = fov
	_camera.position = target + direction * distance
	_camera.look_at(target, Vector3.UP)


# --- light and air --------------------------------------------------------

func _build_environment() -> void:
	## The visual lab's environment, with the distances it measures in scaled.
	##
	## Tonemap, palette, glow curve and colour grade are the art direction and
	## are copied exactly. Fog density and ambient-occlusion radius are not art
	## - they are lengths, and a density tuned against a machine 20 units tall
	## makes one 33 units deep disappear.
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

	var environment := Environment.new()
	environment.background_mode = Environment.BG_SKY
	environment.sky = sky
	environment.background_energy_multiplier = 0.62
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	environment.ambient_light_sky_contribution = 1.0
	environment.ambient_light_energy = 0.25
	environment.reflected_light_source = Environment.REFLECTION_SOURCE_SKY

	environment.tonemap_mode = Environment.TONE_MAPPER_ACES
	# The visual review found the white track approaching clipped white. ACES
	# with a white point of 6 and a contrast lift of 1.16 was tuned against a
	# machine lit by seven practicals at close range; the same rig over a
	# machine five times bigger puts more of the pearl surface near the top of
	# the curve at once. Half a stop down and a slightly higher white point
	# keeps the highlight roll-off inside the curve, which is where the dish's
	# curvature and the marble speculars live.
	#
	# Exposure alone did not finish the job. The dish is the largest, flattest,
	# palest surface in the machine and it faces the key directly, so it clips
	# before anything else does and it clips over an area big enough to take the
	# drain and the marble shadows with it. Three things came down together:
	# the pearl albedos (from `marble-visual-polish`, which dropped the running
	# surfaces from #F2F1EC to #D2D0C7 and roughened them), the key rig below,
	# and this. Rendering the bowl shot across a small grid of the last two put
	# the answer at about two-thirds of the authored light with a third of a
	# stop off the exposure: at that setting the dish holds its profile, the
	# gold drain collar reads as gold, and the candy marbles have something to
	# be bright against.
	environment.tonemap_exposure = 0.78
	environment.tonemap_white = 7.5

	environment.fog_enabled = true
	environment.fog_light_color = Color("#173340")
	environment.fog_light_energy = 0.8
	environment.fog_density = 0.017 / _detail
	environment.fog_sky_affect = 0.25
	environment.fog_aerial_perspective = 0.45

	environment.ssao_enabled = true
	environment.ssao_radius = 0.9 * _detail
	environment.ssao_intensity = 2.6
	environment.ssao_power = 1.4
	environment.ssao_light_affect = 0.15

	environment.ssr_enabled = true
	environment.ssr_max_steps = 48
	environment.ssr_fade_in = 0.2
	environment.ssr_fade_out = 2.0 * _detail

	if not _no_glow:
		environment.glow_enabled = true
		environment.glow_intensity = 0.95
		environment.glow_bloom = 0.18
		environment.glow_hdr_threshold = 0.92
		environment.glow_hdr_scale = 2.0
		environment.glow_blend_mode = Environment.GLOW_BLEND_MODE_SOFTLIGHT
		for level in 7:
			environment.set_glow_level(level, 0.0)
		environment.set_glow_level(1, 0.35)
		environment.set_glow_level(2, 0.7)
		environment.set_glow_level(3, 0.9)
		environment.set_glow_level(4, 0.5)

	environment.adjustment_enabled = true
	environment.adjustment_contrast = 1.16
	environment.adjustment_saturation = 1.14

	var holder := WorldEnvironment.new()
	holder.name = "WorldEnvironment"
	holder.environment = environment
	add_child(holder)


func _build_lights() -> void:
	## The lab's three-point rig, unchanged, plus practicals placed on anchors.
	##
	## Directional lights carry no distance, so the key, rim and fill are the
	## authored ones exactly. The practicals are lamps at positions, and both
	## the positions and the ranges have to come from the machine that is
	## actually there - so they are hung off the contract's anchors rather than
	## off the lab's storey heights.
	var key := DirectionalLight3D.new()
	key.name = "Key"
	key.light_color = Color("#FFF3E2")
	key.light_energy = 2.04
	key.light_specular = 1.0
	key.rotation_degrees = Vector3(-46.0, -38.0, 0.0)
	key.shadow_enabled = true
	key.directional_shadow_mode = DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS
	key.directional_shadow_max_distance = 70.0 * _detail
	key.directional_shadow_blend_splits = true
	key.shadow_bias = 0.035 * _detail
	key.shadow_normal_bias = 1.2
	add_child(key)

	var rim := DirectionalLight3D.new()
	rim.name = "Rim"
	rim.light_color = Color("#8FD9FF")
	rim.light_energy = 1.29
	rim.light_specular = 1.4
	rim.rotation_degrees = Vector3(-12.0, 158.0, 0.0)
	rim.shadow_enabled = false
	add_child(rim)

	var fill := DirectionalLight3D.new()
	fill.name = "Fill"
	fill.light_color = Color("#FFD2AC")
	fill.light_energy = 0.27
	fill.light_specular = 0.2
	fill.rotation_degrees = Vector3(18.0, 44.0, 0.0)
	fill.shadow_enabled = false
	add_child(fill)

	var bowl := _module("bowl")
	var bowl_centre := _v3(bowl.get("anchors", {})["centre"])
	var bowl_visual: Dictionary = bowl.get("visual", {})
	var outer: float = float(bowl_visual["outer_radius"])
	var outer_depth: float = float(bowl_visual["outer_depth"])

	var start_exit := _v3(_module("start")["sockets"]["exit"]["position"])
	var curve_entry := _v3(_module("curve")["sockets"]["entry"]["position"])
	var curve_exit := _v3(_module("curve")["sockets"]["exit"]["position"])

	# Violet over the bowl, the lab's mixer colour, high enough to rake the
	# whole dish rather than blow out the middle of it.
	_practical("BowlPractical", bowl_centre + Vector3(0.0, outer_depth + 0.9 * _detail, 0.0),
		"#9E7CFF", 2.0, 8.0 * _detail)
	# A second violet off-axis, so the dish has a gradient across it and does
	# not read as a lit disc.
	_practical("MixerViolet",
		bowl_centre + Vector3(-outer * 0.42, outer_depth * 0.55, outer * 0.36),
		"#9A6CFF", 2.6, 7.5 * _detail)
	# Cool at the top of the chute, which is the lab's start colour.
	_practical("StartPractical", start_exit + Vector3(0.0, 2.4 * _detail, 0.0),
		"#5FE6FF", 3.6, 7.0 * _detail)
	# Cool white just inside the rim, to put an edge on the marbles as they
	# come round the near side.
	_practical("BowlTop",
		bowl_centre + Vector3(outer * 0.20, outer_depth + 3.1 * 0.5 * _detail, outer * 0.30),
		"#EAF4FF", 1.5, 6.0 * _detail)
	# Warm inside the curve. The lab put its warm light in the finale zone and
	# the finale is not in this clip, so the warmth moves to the lowest thing
	# there is - which is also what keeps the bottom of the frame from going
	# to a single cold value.
	#
	# Hung on the helix's own axis at half its drop, rather than under the
	# track. Under the track was the authored position and it is wrong here for
	# a reason worth writing down: this channel banks *inward*, so its running
	# surface faces the axis of the spiral, and it is roofed by the bowl. A lamp
	# below it lights the keel - the one face of the module the camera never
	# sees into - and leaves the channel the marbles are actually in unlit. On
	# the axis, one lamp reaches the inside of all 270 degrees of it.
	# The axis is the middle of the module's own bounds, not its origin. A
	# curve module's origin is its *entry* - the arc turns away from it with a
	# 7 wu radius - so hanging the lamp off the origin buries it in the track
	# at the top of the spiral, which is where the first attempt at this put it.
	var curve_anchors: Dictionary = _module("curve").get("anchors", {})
	var curve_bounds_low := _v3(_module("curve")["bounds"][0])
	var curve_bounds_high := _v3(_module("curve")["bounds"][1])
	var curve_axis := (curve_bounds_low + curve_bounds_high) * 0.5
	_practical("CurveWarm", curve_axis, "#FFB35C", 5.2,
		2.2 * float(curve_anchors.get("radius", 7.0)))
	_practical("CurveRim", curve_exit + Vector3(0.0, 2.2 * _detail, 0.0),
		"#FFC98A", 2.2, 8.5 * _detail)


func _practical(node_name: String, at: Vector3, hex: String, energy: float,
		reach: float) -> void:
	if energy <= 0.0:
		return
	var lamp := OmniLight3D.new()
	lamp.name = node_name
	lamp.position = at
	lamp.light_color = Color(hex)
	lamp.light_energy = energy
	lamp.omni_range = reach
	lamp.omni_attenuation = 1.6
	lamp.shadow_enabled = false
	add_child(lamp)


# --- debug ----------------------------------------------------------------

func _build_debug() -> void:
	## Module bounds, sockets and origins, drawn as wire.
	##
	## Never reachable from a production render: the renderer only builds this
	## when --debug is passed, and the driver never passes it for the delivered
	## clip. It exists because "the marble is where the contract says" is a
	## claim that is much easier to check with the boxes drawn than by reading
	## coordinates out of a log.
	var overlay := Node3D.new()
	overlay.name = "Debug"
	add_child(overlay)

	for entry in _contract.get("modules", []):
		var low := _v3(entry["bounds"][0])
		var high := _v3(entry["bounds"][1])
		overlay.add_child(_wire_box((low + high) * 0.5, high - low,
			Color("#54E6F7"), "Bounds_%s" % entry["id"]))

		var origin := _marker(_v3(entry["origin"]), 0.55 * _detail,
			Color("#F5C518"), "Origin_%s" % entry["id"])
		overlay.add_child(origin)

		for socket_name in entry.get("sockets", {}):
			var socket: Dictionary = entry["sockets"][socket_name]
			var tint := Color("#18C6C6") if str(socket["kind"]) == "guided" \
				else Color("#F0559B")
			overlay.add_child(_marker(_v3(socket["position"]), 0.45 * _detail,
				tint, "Socket_%s_%s" % [entry["id"], socket_name]))


func _wire_box(centre: Vector3, size: Vector3, tint: Color, node_name: String) -> MeshInstance3D:
	var mesh := BoxMesh.new()
	mesh.size = size
	var material := StandardMaterial3D.new()
	material.albedo_color = Color(tint.r, tint.g, tint.b, 0.10)
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	var node := MeshInstance3D.new()
	node.name = node_name
	node.mesh = mesh
	node.material_override = material
	node.position = centre
	return node


func _marker(at: Vector3, radius: float, tint: Color, node_name: String) -> MeshInstance3D:
	var mesh := SphereMesh.new()
	mesh.radius = radius
	mesh.height = radius * 2.0
	mesh.radial_segments = 10
	mesh.rings = 5
	var material := StandardMaterial3D.new()
	material.albedo_color = tint
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	var node := MeshInstance3D.new()
	node.name = node_name
	node.mesh = mesh
	node.material_override = material
	node.position = at
	return node
