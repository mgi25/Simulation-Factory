extends Node

## A contact sheet of the world kit, rendered on its own.
##
## The kit is the part of V25.1 that a world render is the *slowest* way to
## judge: a boulder at thirty units is forty pixels tall, and a change to its
## plan that is obvious on a turntable is invisible in a race frame. So the
## forms are photographed here first - lit by the world rig, at the value the
## world paints them, against the world's own sky - and only wired into the
## course once they read.
##
## Not part of any deliverable and not in any profile. `tools/
## sloped_v251_kit.py` drives it.
##
##     --out=PATH           where to write the PNG
##     --rows=cliff,block   which kinds, one row each
##     --count=5            how many of each (different seeds)
##     --flora=1            draw the vegetation kit instead

const Palette := preload("res://assets/marble_machine/lab_palette.gd")
const Rock := preload("res://assets/marble_machine/environment/world_rock.gd")
const Flora := preload("res://assets/marble_machine/environment/world_flora.gd")
const Forms := preload("res://assets/marble_machine/lab_forms.gd")
const Builder := preload(
	"res://assets/marble_machine/environment/environment_builder.gd")
const Profiles := preload(
	"res://assets/marble_machine/environment/environment_profile.gd")

var _args := {}


func _ready() -> void:
	_args = _parse()
	var palette = Palette.new()
	palette.contrast = "v21"
	var root := Node3D.new()
	add_child(root)

	var env := WorldEnvironment.new()
	env.environment = _environment()
	root.add_child(env)
	_lights(root)

	var flora := bool(int(_args.get("flora", "0")))
	var rows: Array = str(_args.get("rows", "")).split(",", false)
	if rows.is_empty():
		rows = Flora.kinds() if flora else Rock.kinds()
	var count := int(_args.get("count", "5"))
	var pitch := float(_args.get("pitch", "13.0"))

	var tallest := 0.0
	for row in rows.size():
		for column in count:
			var seed_value := 101 + row * 977 + column * 131
			var node: Node3D
			var high := 0.0
			if flora:
				node = Flora.plant(str(rows[row]), 7.0, seed_value, palette, {})
				high = 7.0
			else:
				var mesh := Rock.form(str(rows[row]), 9.0, 3.4, seed_value)
				node = Forms.mesh_node(mesh,
					palette.get_material("world_cliff_face"),
					"%s%d" % [rows[row], column], false)
				high = 9.0
			tallest = maxf(tallest, high)
			node.position = Vector3(float(column) * pitch - float(count - 1)
				* pitch * 0.5, 0.0, float(row) * pitch
				- float(rows.size() - 1) * pitch * 0.5)
			_layer(node)
			root.add_child(node)

	# The ground: one large plate at the near-ground value, so a form is read
	# against the surface it will actually stand on.
	var ground := Forms.mesh_node(
		preload("res://scripts/toy_geometry.gd").rounded_box(
			Vector3(240.0, 2.0, 240.0), 0.4, 1),
		palette.get_material("slope_earth"), "Ground", false)
	ground.position.y = -1.0
	_layer(ground)
	root.add_child(ground)

	var camera := Camera3D.new()
	var span: float = maxf(float(count) * pitch, float(rows.size()) * pitch)
	var elevation := deg_to_rad(float(_args.get("elevation", "36.0")))
	var reach: float = span * 1.05 + tallest
	camera.position = Vector3(0.0, sin(elevation) * reach + tallest * 0.3,
		cos(elevation) * reach)
	camera.fov = 44.0
	root.add_child(camera)
	camera.look_at(Vector3(0.0, tallest * 0.34, 0.0), Vector3.UP)
	camera.make_current()

	await RenderingServer.frame_post_draw
	await RenderingServer.frame_post_draw
	var shot := get_viewport().get_texture().get_image()
	shot.save_png(str(_args.get("out", "kit.png")))
	get_tree().quit()


func _layer(node: Node) -> void:
	if node is VisualInstance3D:
		(node as VisualInstance3D).layers = 2
	for child in node.get_children():
		_layer(child)


func _environment() -> Environment:
	var profile := Profiles.resolve("aurora_valley_v25b", "v21")
	return Builder.environment(profile, false)


func _lights(root: Node3D) -> void:
	var profile := Profiles.resolve("aurora_valley_v25b", "v21")
	Builder.lights(root, profile)


func _parse() -> Dictionary:
	var out := {}
	for one in OS.get_cmdline_user_args():
		var text := str(one)
		if not text.begins_with("--"):
			continue
		var body := text.substr(2)
		var split := body.find("=")
		if split < 0:
			out[body] = "1"
		else:
			out[body.substr(0, split)] = body.substr(split + 1)
	return out
