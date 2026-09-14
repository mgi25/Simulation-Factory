extends SceneTree
## Dump what `racer_visual` actually paints, so Python can be held to it.
##
## `sloped/v24_spin.py` carries a twin of `racer_visual.coverage` - it has to,
## because the readability numbers in the report are computed in Python while
## the picture is painted in GDScript. Two implementations of one shape is two
## chances to be wrong, so this writes the GDScript's own answers at a fixed
## set of directions and `tests/test_sloped_v24_spin.py` compares them. If the
## band ever moves in one file and not the other, that test fails.
##
##     godot --headless --path godot --script res://scripts/racer_visual_check.gd \
##         -- --out=PATH

const RacerVisual := preload("res://assets/marble_machine/racers/racer_visual.gd")


func _init() -> void:
	var out := "coverage_dump.json"
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--out="):
			out = argument.substr(6)

	var rows: Array = []
	# The same Fibonacci set the Python side samples with, so the comparison is
	# of the shape and not of two different guesses at where to look.
	var count := 512
	for index in count:
		var offset := float(index) + 0.5
		var z: float = 1.0 - 2.0 * offset / float(count)
		var radius: float = sqrt(maxf(0.0, 1.0 - z * z))
		var theta: float = PI * (1.0 + sqrt(5.0)) * offset
		var point := Vector3(radius * cos(theta), radius * sin(theta), z)
		var row: Dictionary = {"p": [point.x, point.y, point.z]}
		for appearance in RacerVisual.APPEARANCES:
			row[appearance] = RacerVisual.coverage(appearance, point)
		rows.append(row)

	var payload := {
		"appearances": RacerVisual.APPEARANCES,
		"marker_tint": RacerVisual.MARKER_TINT,
		"texture": [RacerVisual.TEXTURE_WIDTH, RacerVisual.TEXTURE_HEIGHT],
		"samples": rows,
	}
	var handle := FileAccess.open(out, FileAccess.WRITE)
	if handle == null:
		push_error("racer_visual_check: cannot write %s" % out)
		quit(1)
		return
	handle.store_string(JSON.stringify(payload))
	handle.close()
	print("racer_visual: %d samples over %d appearances -> %s"
		% [rows.size(), RacerVisual.APPEARANCES.size(), out])
	quit(0)
