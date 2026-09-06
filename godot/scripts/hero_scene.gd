extends Node3D

## The final hero build's scene: the seven-stage machine, in the dusk gorge.
##
## Isolated from everything that races, like the two labs before it. It loads no
## replay, imports nothing from `race` or `engine`, and is unreachable from
## `ReplayViewer.tscn` or `OfflineRender.tscn`. `track_lab_scene.gd` is left
## exactly as it is so the V2.2 proofs stay reproducible - this is a third lab,
## not an edit to the second.
##
## ## Shots
##
## `hero` and `phone` frame the whole machine at one vertical extent, so an
## elevation or azimuth sweep compares *angle* and nothing else. The seven
## module lenses are design inspection shots and are framed for the module
## rather than for the picture. Distance is always derived from the extent and
## the field of view, never typed in, so no comparison is secretly a crop.
##
## ## The practicals
##
## One lamp group per zone, sited where that zone's own lit geometry is, so the
## emissive strips appear to cast the light they imply. The set is a gradient
## down the machine: cyan at the start, violet through the bowl and collector,
## blue against orange at the split, gold from the compression down. That
## gradient is the brief's colour story, and it is carried by *lights* as much
## as by paint - a warm module under a cool lamp is still a cool module.

const Palette := preload("res://assets/marble_machine/lab_palette.gd")
const World := preload("res://assets/marble_machine/hero/hero_world.gd")
const Machine := preload("res://assets/marble_machine/hero/hero_machine.gd")
const Layout := preload("res://assets/marble_machine/hero/hero_layout.gd")
const Track := preload("res://assets/marble_machine/v2/v2_track.gd")

const SHOTS := {
	# aim: the height the lens looks at. extent: the vertical span it fits.
	"hero": {"aim": 15.75, "extent": 36.4, "fov": 32.0, "elevation": 18.0,
		"azimuth": 22.0},
	"phone": {"aim": 15.75, "extent": 36.4, "fov": 32.0, "elevation": 18.0,
		"azimuth": 22.0},

	# Elevation sweep, all at the hero azimuth.
	"e13": {"aim": 15.75, "extent": 36.4, "fov": 32.0, "elevation": 13.0,
		"azimuth": 22.0},
	"e16": {"aim": 15.75, "extent": 36.4, "fov": 32.0, "elevation": 16.0,
		"azimuth": 22.0},
	"e18": {"aim": 15.75, "extent": 36.4, "fov": 32.0, "elevation": 18.0,
		"azimuth": 22.0},
	"e21": {"aim": 15.75, "extent": 36.4, "fov": 32.0, "elevation": 21.0,
		"azimuth": 22.0},
	"e24": {"aim": 15.85, "extent": 36.8, "fov": 32.0, "elevation": 24.0,
		"azimuth": 33.0},
	"e27": {"aim": 15.95, "extent": 37.2, "fov": 32.0, "elevation": 27.0,
		"azimuth": 33.0},

	# Azimuth sweep.
	"a14": {"aim": 15.75, "extent": 36.4, "fov": 32.0, "elevation": 18.0,
		"azimuth": 14.0},
	"a20": {"aim": 15.75, "extent": 36.4, "fov": 32.0, "elevation": 18.0,
		"azimuth": 20.0},
	"a26": {"aim": 15.75, "extent": 36.4, "fov": 32.0, "elevation": 18.0,
		"azimuth": 26.0},
	"a33": {"aim": 15.75, "extent": 36.4, "fov": 32.0, "elevation": 18.0,
		"azimuth": 33.0},
	"a40": {"aim": 15.75, "extent": 36.4, "fov": 32.0, "elevation": 18.0,
		"azimuth": 40.0},
	"a47": {"aim": 15.75, "extent": 36.4, "fov": 32.0, "elevation": 18.0,
		"azimuth": 47.0},

	# Lens sweep. A long lens flattens the tower and a short one throws the
	# start away from the finish; the brief's 28-38 band is worth testing.
	"f28": {"aim": 15.75, "extent": 36.4, "fov": 28.0, "elevation": 18.0,
		"azimuth": 22.0},
	"f35": {"aim": 15.75, "extent": 36.4, "fov": 35.0, "elevation": 18.0,
		"azimuth": 22.0},
	"f38": {"aim": 15.75, "extent": 36.4, "fov": 38.0, "elevation": 18.0,
		"azimuth": 22.0},

	# The seven module lenses. Design inspection shots, framed for the module
	# rather than for the picture: each one is aimed at its own origin plane,
	# fitted to its own extent with a sixth of that again as margin, and given
	# the elevation and bearing from which that module's *mechanism* is
	# legible - high and near-frontal for the two dishes, low and oblique for
	# the channels, square-on for the choice.
	"start": {"aim": 30.20, "extent": 8.6, "fov": 30.0,
		"elevation": 19.0, "azimuth": 30.0},
	"bowl": {"aim": 24.35, "extent": 9.2, "fov": 30.0,
		"elevation": 28.0, "azimuth": 36.0},
	"s_bridge": {"aim": 20.10, "extent": 12.6, "fov": 32.0,
		"elevation": 16.0, "azimuth": 46.0},
	"collector": {"aim": 14.10, "extent": 7.2, "fov": 30.0,
		"elevation": 30.0, "azimuth": 28.0},
	"split": {"aim": 8.75, "extent": 12.6, "fov": 32.0,
		"elevation": 13.0, "azimuth": 16.0},
	"compression": {"aim": 4.80, "extent": 7.0, "fov": 30.0,
		"elevation": 17.0, "azimuth": 28.0},
	"finish": {"aim": 2.05, "extent": 9.6, "fov": 30.0,
		"elevation": 25.0, "azimuth": 40.0},
}

const DEFAULT_SHOT := "hero"

var _palette
var _camera: Camera3D
var _shot := DEFAULT_SHOT
var _no_glow := false
var _machine: Node3D
var _orbit := 0.0
var _dolly := 0.0
var _travellers: Array = []
var _rotor: Node3D
var _wheels: Array = []


func _ready() -> void:
	var options := _options()
	_shot = str(options.get("shot", DEFAULT_SHOT))
	_no_glow = str(options.get("no-glow", "")) != ""
	if not SHOTS.has(_shot):
		push_error("hero_scene: unknown shot '%s'" % _shot)
		_shot = DEFAULT_SHOT

	_palette = Palette.new("tower")

	var world_env := WorldEnvironment.new()
	world_env.name = "WorldEnvironment"
	world_env.environment = World.build_environment(_no_glow)
	add_child(world_env)

	World.build_lights(self)
	add_child(World.build(_palette))

	_machine = Machine.build(_palette)
	add_child(_machine)
	_practicals()
	_collect_moving_parts()

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
	## Shadows off throughout: a practical's job is to wash a local surface,
	## and shadow-casting omnis at this count cost far more than the picture
	## gains. Their colours are the zone story, read top to bottom.
	var lamps := [
		# Start - cyan and white.
		["StartCyan", Vector3(0.0, Layout.START_Y + 0.9, Layout.START_Z + 1.6),
			"#6BE9FF", 1.3, 5.2],
		["SignGlow", Vector3(0.0, Layout.START_Y + 1.9, Layout.START_Z - 1.4),
			"#8FF0FF", 1.1, 3.8],
		["StartUnder", Vector3(0.0, Layout.START_Y - 2.2, Layout.START_Z + 1.9),
			"#54E6F7", 1.6, 4.4],
		# Bowl - violet from under the dish, cool white over the rim.
		["BowlViolet", Vector3(0.0, Layout.BOWL_Y - 1.5, 0.0),
			"#A379FF", 2.8, 6.4],
		["BowlTop", Vector3(1.5, Layout.BOWL_Y + 3.0, 2.7),
			"#E4F1FF", 1.9, 8.0],
		["BowlFar", Vector3(-1.9, Layout.BOWL_Y + 2.2, -2.1),
			"#CFE6FF", 2.4, 6.8],
		# S-bridge - violet, following its edge light.
		["SUpper", Vector3(2.7, 21.4, 0.5), "#9B6BFF", 2.1, 6.4],
		["SMid", Vector3(0.2, 19.4, -1.0), "#9B6BFF", 1.8, 5.6],
		["SLower", Vector3(-2.8, 17.4, 0.6), "#9B6BFF", 2.0, 6.0],
		# Collector - violet over the pan, orange in the drum.
		["PanViolet", Vector3(0.0, Layout.COLLECTOR_Y + 1.6, 1.2),
			"#B08CFF", 2.4, 6.2],
		["DrumWarm", Vector3(0.0, Layout.COLLECTOR_Y - 1.4, 1.0),
			"#FF9A48", 2.0, 4.6],
		# Split - the two identities, one lamp each, well separated in x.
		["SplitCool", Vector3(-3.4, 9.9, 0.9), "#4FB4FF", 3.2, 7.4],
		["SplitWarm", Vector3(3.4, 9.7, 0.6), "#FF8A3C", 3.2, 7.4],
		["SplitGate", Vector3(0.0, Layout.SPLIT_TOP_Y + 0.4, 1.2),
			"#EAF7FF", 1.8, 3.6],
		["HazardWarm", Vector3(0.4, 9.9, -1.3), "#FF7C2E", 1.8, 4.4],
		# Compression - the handover to gold.
		["Compress", Vector3(0.0, 5.4, 1.2), "#FFC168", 3.2, 5.6],
		# Finish - the frame's warm anchor, and the brightest practical set.
		["ArenaCore", Vector3(0.0, Layout.FINISH_Y + 1.2, 0.0),
			"#FFC46A", 1.7, 7.6],
		["ArenaFront", Vector3(0.9, Layout.FINISH_Y + 1.5, 2.8),
			"#FFB253", 1.4, 7.0],
		["ArenaBack", Vector3(-1.6, Layout.FINISH_Y + 1.3, -2.6),
			"#FFA451", 1.8, 6.4],
		["ArenaRise", Vector3(1.2, Layout.FINISH_Y + 3.8, 1.0),
			"#FFB870", 2.0, 7.0],
		["PlinthWarm", Vector3(0.0, Layout.PLINTH_Y + 0.9, 1.4),
			"#FF9A45", 2.4, 5.6],
		# One cool fill behind the tower so the graphite never goes to black.
		["SpineFill", Vector3(0.0, 19.0, -4.6), "#5FC8E8", 2.2, 13.0],
		["SpineFillLow", Vector3(0.0, 8.0, -4.2), "#5FC8E8", 1.8, 10.0],
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
	_camera.far = 1400.0
	add_child(_camera)
	_camera.current = true
	_place_camera(0.0, 0.0)


func _place_camera(orbit_offset: float, dolly: float) -> void:
	var shot: Dictionary = SHOTS[_shot]
	var fov := float(shot["fov"])
	var extent := float(shot["extent"]) * (1.0 + dolly)
	var elevation := deg_to_rad(float(shot["elevation"]))
	var azimuth := deg_to_rad(float(shot["azimuth"]) + orbit_offset)

	var distance := (extent * 0.5) / tan(deg_to_rad(fov) * 0.5)
	var target := Vector3(0.0, float(shot["aim"]), 0.0)
	var direction := Vector3(
		sin(azimuth) * cos(elevation), sin(elevation),
		cos(azimuth) * cos(elevation))

	_camera.fov = fov
	_camera.position = target + direction * distance
	_camera.look_at(target, Vector3.UP)


func _collect_moving_parts() -> void:
	## Bind every animated node to what drives it, once.
	if _machine == null:
		return
	var field := _machine.get_node_or_null("Field")
	if field != null:
		for entry in _machine.get_meta("travellers"):
			var record: Dictionary = entry
			var node: Node3D = field.get_node_or_null(str(record["node"]))
			if node == null:
				continue
			var run: String = str(record["run"])
			_travellers.append({
				"node": node,
				"path": _machine.get_meta("%s_path" % run),
				"banks": _machine.get_meta("%s_banks" % run),
				"scale": float(_machine.get_meta("%s_scale" % run)),
				"phase": float(record["phase"]),
			})

	var collector := _machine.get_node_or_null("Collector")
	if collector != null:
		_rotor = collector.get_node_or_null("Rotor")

	var hazard := _machine.get_node_or_null("HazardDeck")
	if hazard != null:
		for child in hazard.get_children():
			var wheel := (child as Node3D).get_node_or_null("Wheel")
			if wheel != null:
				_wheels.append({"node": wheel,
					"phase": float((child as Node3D).get_meta("spin_phase", 0.0))})


func set_time(seconds: float) -> void:
	## Everything that moves, as a pure function of the output frame's time.
	##
	## No physics and none implied. The travellers slide along their own runs
	## at a constant rate so the clip shows the *route*; the rotor and the
	## spinners turn so the machine reads as powered. A racer that overtakes
	## another here means nothing.
	for entry in _travellers:
		var node: Node3D = entry["node"]
		var t: float = fposmod(float(entry["phase"]) + seconds * 0.105, 1.0)
		node.position = Track.running_point(entry["path"], entry["banks"], t,
			Layout.MARBLE_RADIUS, float(entry["scale"]))
	if _rotor != null:
		_rotor.rotation.y = seconds * 0.34
	for entry in _wheels:
		var wheel: Node3D = entry["node"]
		wheel.rotation.y = float(entry["phase"]) + seconds * 1.15

	_orbit = sin(seconds * 0.36) * 5.0
	_dolly = -0.035 * (1.0 - cos(seconds * 0.30))
	_place_camera(_orbit, _dolly)


func _dump_modules(path: String) -> void:
	var table := Machine.module_table()
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		push_error("hero_scene: cannot write %s" % path)
		return
	file.store_string(JSON.stringify(_jsonable(table), "  "))
	file.close()
	print("  modules -> %s" % path)


func _jsonable(value):
	if value is Dictionary:
		var out := {}
		for key in value:
			out[str(key)] = _jsonable(value[key])
		return out
	if value is Array:
		var list: Array = []
		for item in value:
			list.append(_jsonable(item))
		return list
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
		_place_camera(_orbit, _dolly)
