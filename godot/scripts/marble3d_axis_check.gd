extends Node

## Proves that Godot agrees with PyBullet about which way round the world is.
##
## `marble3d/presentation.py` claims the conversion between the two engines is
## the identity: both are right-handed, both are +Y up, and both store a
## quaternion as (x, y, z, w). That claim is the reason there is no axis swap
## anywhere in the render path, and it is exactly the kind of claim that is
## never noticed to be wrong until a marble orbits the bowl the wrong way and
## somebody spends a day looking at the solver.
##
## So Python writes a set of golden vectors - a rotation and a point, with the
## rotated point it computed itself - and this script rotates the same points
## with Godot's own `Quaternion` and writes down what it got. A test compares
## the two files. The cases are chosen to fail loudly rather than subtly: a
## 120-degree turn about the diagonal cycles the axes, so reading the
## components in the wrong order sends a point somewhere obviously wrong, and
## the last case is the real placement of the start chute, which is not
## axis-aligned and so catches a composition done in the other order.
##
## Usage, after `--`:
##
##     --golden=PATH   the vectors Python produced
##     --out=PATH      where to write what Godot got

func _ready() -> void:
	var options := _parse_options()
	var golden_path := str(options.get("golden", ""))
	var out_path := str(options.get("out", ""))
	if golden_path.is_empty() or out_path.is_empty():
		_fail("--golden and --out are both required")
		return

	var text := FileAccess.get_file_as_string(golden_path)
	if text.is_empty():
		_fail("cannot read %s" % golden_path)
		return
	var golden = JSON.parse_string(text)
	if typeof(golden) != TYPE_DICTIONARY:
		_fail("%s is not a JSON object" % golden_path)
		return

	var results: Array = []
	for case in golden.get("cases", []):
		var q: Array = case["quaternion"]
		var p: Array = case["point"]
		var rotation := Quaternion(
			float(q[0]), float(q[1]), float(q[2]), float(q[3]))
		var point := Vector3(float(p[0]), float(p[1]), float(p[2]))

		# Three ways of applying the same rotation, because the render path
		# uses all three: the quaternion directly on a vector, a Basis built
		# from it (which is what a Transform3D carries), and the basis's own
		# axis accessors, which is how a socket's flow and up are read.
		var direct := rotation * point
		var basis := Basis(rotation)
		var through_basis := basis * point
		var through_transform := Transform3D(basis, Vector3.ZERO) * point

		results.append({
			"name": str(case.get("name", "?")),
			"rotated": [direct.x, direct.y, direct.z],
			"rotated_basis": [through_basis.x, through_basis.y, through_basis.z],
			"rotated_transform": [
				through_transform.x, through_transform.y, through_transform.z],
			"basis_x": [basis.x.x, basis.x.y, basis.x.z],
			"basis_y": [basis.y.x, basis.y.y, basis.y.z],
			"basis_z": [basis.z.x, basis.z.y, basis.z.z],
		})

	var payload := {
		"engine": "godot",
		"version": Engine.get_version_info().get("string", "unknown"),
		# Written out so the test can assert on them rather than trusting the
		# prose in the contract's docstring.
		"up": [Vector3.UP.x, Vector3.UP.y, Vector3.UP.z],
		"handedness_cross_x_y": _cross_components(Vector3.RIGHT, Vector3.UP),
		"cases": results,
	}

	var handle := FileAccess.open(out_path, FileAccess.WRITE)
	if handle == null:
		_fail("cannot write %s" % out_path)
		return
	handle.store_string(JSON.stringify(payload, "  "))
	handle.close()
	print("axis check wrote %d cases to %s" % [results.size(), out_path])
	get_tree().quit(0)


func _cross_components(a: Vector3, b: Vector3) -> Array:
	## +X cross +Y. In a right-handed frame this is +Z.
	var c := a.cross(b)
	return [c.x, c.y, c.z]


func _fail(message: String) -> void:
	push_error("marble3d axis check failed: %s" % message)
	get_tree().quit(1)


func _parse_options() -> Dictionary:
	var options := {}
	for argument in OS.get_cmdline_user_args():
		var arg: String = argument
		if not arg.begins_with("--"):
			continue
		var split := arg.substr(2).split("=", true, 1)
		if split.size() == 2:
			options[split[0]] = split[1]
		else:
			options[split[0]] = "1"
	return options
