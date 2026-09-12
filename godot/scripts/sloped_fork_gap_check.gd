extends SceneTree

## Measures the **built** guard rail at the fork, so "the wall is open" is a
## number rather than a look at a picture.
##
## Section 19 of the V1.15 brief asks for a proof that the intended wall is
## absent, that its neighbours are not, and that nothing is drawn across the
## path the physics lets a marble take. A still shows all three to a person; it
## shows none of them to a test. So this sweeps leg3's east rail exactly as
## `v2_track.build` sweeps it - once with the fork's window and once without -
## reads the **vertices of the resulting mesh**, and reports how far the highest
## of them stands above the run's own centreline at each sample.
##
## One line per sample: `sample,open_height,closed_height`, six decimals, in
## profile units. `tests/test_sloped_open_side.py` reads it.

const Track := preload("res://assets/marble_machine/v2/v2_track.gd")
const Forms := preload("res://assets/marble_machine/v2/v2_forms.gd")
const Layout := preload("res://assets/marble_machine/course/course_layout.gd")
const Machine := preload("res://assets/marble_machine/course/course_machine.gd")

# Either side of the fork window, wide enough that the shoulders of the ease are
# in frame as well as its floor.
const FIRST := 74
const LAST := 99


func _init() -> void:
	var spec: Dictionary = {}
	for entry in Layout.table("b")["runs"]:
		if str((entry as Dictionary)["name"]) == "leg3":
			spec = entry
	if spec.is_empty():
		printerr("leg3 is not in layout b")
		quit(1)
		return

	var window: Array = Machine.OPEN_SIDES["leg3"]
	var open_heights := _rail_heights(spec, window)
	var shut_heights := _rail_heights(spec, [])
	for index in range(FIRST, LAST + 1):
		print("%d,%.6f,%.6f" % [index, open_heights[index], shut_heights[index]])
	quit()


func _rail_heights(spec: Dictionary, window: Array) -> Dictionary:
	## Per sample, the tallest east-rail vertex above the run's centreline.
	##
	## Built through `Track.build`, not through the section maths, so what is
	## measured is the mesh a camera sees. The node is freed before returning;
	## the palette is the render's own, because a material cannot change a
	## vertex and a headless build has no reason to load one.
	var palette: Object = _palette()
	var run: Node3D = Track.build(palette, spec["controls"], "Leg3", {
		"scale": float(spec["scale"]),
		"bank_gain": float(spec["bank_gain"]),
		"bank_max": float(spec["bank_max"]),
		"samples": 118,
		"bank_slew": Machine.BANK_SLEWS.get("leg3", []),
		"open_side": window,
		"ribs": false,
	})
	var path: Array = run.get_meta("path")
	var banks: Array = run.get_meta("banks")
	var out: Dictionary = {}
	for node in run.get_children():
		if not (node is MeshInstance3D) or str(node.name) != "GuardL":
			continue
		var mesh: ArrayMesh = (node as MeshInstance3D).mesh
		for surface in mesh.get_surface_count():
			var arrays: Array = mesh.surface_get_arrays(surface)
			for point in (arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array):
				var index := _nearest(path, point)
				# In the run's **own banked frame**, not in world y. leg3 rolls
				# 26 degrees here, so a rail that has collapsed to nothing still
				# stands 0.44 above the centreline in world height purely from
				# its lateral offset - which reads as a wall that is still
				# there. The first run of this check reported exactly that.
				var frame: Basis = Forms.banked_basis(path, banks, index)
				var offset: Vector3 = point - (path[index] as Vector3)
				var height: float = offset.dot(frame.y)
				if not out.has(index) or height > float(out[index]):
					out[index] = height
	run.free()
	for index in path.size():
		if not out.has(index):
			out[index] = -1.0
	return out


func _nearest(path: Array, point: Vector3) -> int:
	var best := 0
	var closest := 1.0e12
	for index in path.size():
		var distance: float = (path[index] as Vector3).distance_squared_to(point)
		if distance < closest:
			closest = distance
			best = index
	return best


func _palette() -> Object:
	var script: Script = load("res://assets/marble_machine/lab_palette.gd")
	return script.new()
