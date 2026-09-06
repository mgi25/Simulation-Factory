extends Node3D

## The track visual lab's scene: the V2 machine in the V2 world, one rig.
##
## Isolated from everything that races. It loads no replay, imports nothing from
## `race` or `engine`, and is unreachable from `ReplayViewer.tscn` or
## `OfflineRender.tscn`. It is also separate from `lab_scene.gd`, which stays
## exactly as it was so the prior lab's frames remain reproducible - this is a
## second lab, not an edit to the first.
##
## ## What the shots are for
##
## `hero*` frame the whole machine at a fixed vertical extent so an elevation
## sweep compares *angle* and nothing else; `start`, `bowl` and `track` are
## product lenses on one module each; `phone` is the hero at review scale.
## Distance is always derived from the extent and the field of view, never
## typed in, so no comparison is secretly a crop.

const Palette := preload("res://assets/marble_machine/lab_palette.gd")
const World := preload("res://assets/marble_machine/v2/v2_world.gd")
const Machine := preload("res://assets/marble_machine/v2/v2_machine.gd")
const Track := preload("res://assets/marble_machine/v2/v2_track.gd")
const Forms := preload("res://assets/marble_machine/lab_forms.gd")

const SHOTS := {
	# aim: the height the lens looks at. extent: the vertical span it fits.
	"hero": {"aim": 10.9, "extent": 28.6, "fov": 34.0, "elevation": 22.0, "azimuth": 34.0},
	"phone": {"aim": 10.9, "extent": 28.6, "fov": 34.0, "elevation": 22.0, "azimuth": 34.0},

	"e16": {"aim": 10.9, "extent": 28.6, "fov": 34.0, "elevation": 16.0, "azimuth": 34.0},
	"e20": {"aim": 10.9, "extent": 28.6, "fov": 34.0, "elevation": 20.0, "azimuth": 34.0},
	"e24": {"aim": 11.0, "extent": 28.8, "fov": 34.0, "elevation": 24.0, "azimuth": 34.0},
	"e28": {"aim": 11.1, "extent": 29.0, "fov": 34.0, "elevation": 28.0, "azimuth": 34.0},

	"a18": {"aim": 10.9, "extent": 28.6, "fov": 34.0, "elevation": 20.0, "azimuth": 18.0},
	"a34": {"aim": 10.9, "extent": 28.6, "fov": 34.0, "elevation": 20.0, "azimuth": 34.0},
	"a50": {"aim": 10.9, "extent": 28.6, "fov": 34.0, "elevation": 20.0, "azimuth": 50.0},
	"a66": {"aim": 10.9, "extent": 28.6, "fov": 34.0, "elevation": 20.0, "azimuth": 66.0},

	"f30": {"aim": 10.9, "extent": 28.6, "fov": 30.0, "elevation": 20.0, "azimuth": 34.0},
	"f40": {"aim": 10.9, "extent": 28.6, "fov": 40.0, "elevation": 20.0, "azimuth": 34.0},

	# Product lenses.
	"start": {"aim": 18.7, "extent": 13.0, "fov": 30.0, "elevation": 23.0, "azimuth": 35.0},
	"bowl": {"aim": 12.2, "extent": 12.4, "fov": 30.0, "elevation": 27.0, "azimuth": 40.0},
	"track": {"aim": 6.4, "extent": 12.6, "fov": 32.0, "elevation": 17.0, "azimuth": 58.0},
	"upper": {"aim": 16.2, "extent": 12.0, "fov": 33.0, "elevation": 14.0, "azimuth": 30.0},
}

const DEFAULT_SHOT := "hero"

var _palette
var _camera: Camera3D
var _shot := DEFAULT_SHOT
var _no_glow := false
var _machine: Node3D
var _orbit := 0.0
var _travellers: Array = []


func _ready() -> void:
	var options := _options()
	_shot = str(options.get("shot", DEFAULT_SHOT))
	_no_glow = str(options.get("no-glow", "")) != ""
	if not SHOTS.has(_shot):
		push_error("track_lab_scene: unknown shot '%s'" % _shot)
		_shot = DEFAULT_SHOT

	_palette = Palette.new("tower")

	var world_env := WorldEnvironment.new()
	world_env.name = "WorldEnvironment"
	world_env.environment = World.build_environment(_no_glow)
	add_child(world_env)

	World.build_lights(self)
	add_child(World.build(_palette))
	_practicals()

	_machine = Machine.build(_palette)
	add_child(_machine)

	if str(options.get("dump-modules", "")) != "":
		_dump_modules(str(options["dump-modules"]))

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


func _practicals() -> void:
	## The lamps that belong to the machine rather than to the studio.
	##
	## One per zone, sited where that zone's own lit geometry is, so the
	## emissive strips actually appear to cast the light they imply. Shadows
	## off: a practical's job is to wash a local surface, and shadow-casting
	## omnis at this count cost more than the picture gains.
	var lamps := [
		["StartCyan", Vector3(0.0, Machine.START_Y + 0.9, Machine.START_Z + 1.5),
			"#6BE9FF", 1.9, 5.0],
		["SignGlow", Vector3(0.0, Machine.START_Y + 1.9, Machine.START_Z - 1.5),
			"#8FF0FF", 1.6, 3.6],
		["BowlViolet", Vector3(0.0, Machine.BOWL_Y - 1.3, 0.0),
			"#A379FF", 2.4, 6.0],
		["BowlTop", Vector3(1.4, Machine.BOWL_Y + 2.9, 2.6),
			"#E4F1FF", 2.5, 7.5],
		["BowlFar", Vector3(-1.8, Machine.BOWL_Y + 2.2, -2.0),
			"#CFE6FF", 2.4, 6.5],
		["TrackViolet", Vector3(2.6, 8.4, 0.8), "#9B6BFF", 2.0, 6.0],
		["BaseWarm", Vector3(0.0, Machine.PLINTH_Y + 1.3, 1.4),
			"#FFA451", 7.0, 9.5],
		["BaseWarmBack", Vector3(-1.5, Machine.PLINTH_Y + 1.0, -2.0),
			"#FF9040", 4.4, 8.0],
		["BaseRise", Vector3(1.4, Machine.PLINTH_Y + 3.4, 1.0),
			"#FFB870", 3.0, 7.5],
		["SpineFill", Vector3(0.0, 9.5, -3.9), "#5FC8E8", 2.0, 9.0],
	]
	for entry in lamps:
		var lamp := OmniLight3D.new()
		lamp.name = str(entry[0])
		lamp.position = entry[1]
		lamp.light_color = Color(str(entry[2]))
		lamp.light_energy = float(entry[3])
		lamp.omni_range = float(entry[4])
		lamp.omni_attenuation = 1.5
		lamp.shadow_enabled = false
		add_child(lamp)


func _build_camera() -> void:
	_camera = Camera3D.new()
	_camera.name = "HeroCamera"
	_camera.keep_aspect = Camera3D.KEEP_HEIGHT
	_camera.near = 0.15
	_camera.far = 900.0
	add_child(_camera)
	_camera.current = true
	_place_camera(0.0)


func _place_camera(orbit_offset: float) -> void:
	var shot: Dictionary = SHOTS[_shot]
	var fov := float(shot["fov"])
	var extent := float(shot["extent"])
	var elevation := deg_to_rad(float(shot["elevation"]))
	var azimuth := deg_to_rad(float(shot["azimuth"]) + orbit_offset)

	var distance := (extent * 0.5) / tan(deg_to_rad(fov) * 0.5)
	var target := Vector3(0.0, float(shot["aim"]), 0.0)
	var direction := Vector3(
		sin(azimuth) * cos(elevation), sin(elevation), cos(azimuth) * cos(elevation))

	_camera.fov = fov
	_camera.position = target + direction * distance
	_camera.look_at(target, Vector3.UP)


func set_time(seconds: float) -> void:
	## Everything that moves, as a pure function of the output frame's time.
	if _travellers.is_empty() and _machine != null:
		_collect_travellers()
	for entry in _travellers:
		var node: Node3D = entry["node"]
		var t: float = fposmod(float(entry["phase"]) + seconds * 0.115, 1.0)
		node.position = Track.running_point(entry["path"], entry["banks"], t,
			Machine.MARBLE_RADIUS)
	_orbit = sin(seconds * 0.40) * 4.5
	_place_camera(_orbit)


func _collect_travellers() -> void:
	## The chute marbles, bound to the path they were placed on.
	var field := _machine.get_node_or_null("Field")
	if field == null:
		return
	var feed_path: Array = _machine.get_meta("feed_path")
	var feed_banks: Array = _machine.get_meta("feed_banks")
	var s_path: Array = _machine.get_meta("s_path")
	var s_banks: Array = _machine.get_meta("s_banks")
	var phases := [
		[feed_path, feed_banks, 0.34], [feed_path, feed_banks, 0.72],
		[s_path, s_banks, 0.10], [s_path, s_banks, 0.28],
		[s_path, s_banks, 0.46], [s_path, s_banks, 0.63],
		[s_path, s_banks, 0.79], [s_path, s_banks, 0.94],
	]
	var index := 0
	for child in field.get_children():
		if not str(child.name).begins_with("ChuteMarble"):
			continue
		if index >= phases.size():
			break
		_travellers.append({
			"node": child, "path": phases[index][0],
			"banks": phases[index][1], "phase": phases[index][2]})
		index += 1


func _dump_modules(path: String) -> void:
	## Write the module anchor table beside the renders, as JSON.
	var table := Machine.module_table()
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		push_error("track_lab_scene: cannot write %s" % path)
		return
	file.store_string(JSON.stringify(_jsonable(table), "  "))
	file.close()
	print("  modules -> %s" % path)


func _jsonable(value):
	## Vectors and AABBs as plain numbers, so the table survives JSON.
	if value is Dictionary:
		var out := {}
		for key in value:
			out[str(key)] = _jsonable(value[key])
		return out
	if value is Array:
		var out: Array = []
		for item in value:
			out.append(_jsonable(item))
		return out
	if value is Vector3:
		return [snappedf(value.x, 0.001), snappedf(value.y, 0.001),
			snappedf(value.z, 0.001)]
	if value is AABB:
		return {"position": _jsonable(value.position),
			"size": _jsonable(value.size)}
	if value is float:
		return snappedf(value, 0.0001)
	return value


func shot_names() -> Array:
	return SHOTS.keys()


func set_shot(name: String) -> void:
	if SHOTS.has(name):
		_shot = name
		_place_camera(_orbit)
