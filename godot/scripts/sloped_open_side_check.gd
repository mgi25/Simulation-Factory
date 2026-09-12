extends SceneTree

## Prints `v2_track.wall_factor` on the windows the course actually ships, so
## Python and GDScript can be compared as **numbers** rather than as source text.
##
## `tests/test_sloped_open_side.py` reads this and compares it against
## `sloped.track.TrackRun.wall_factor`. The reason it exists is
## `godot/scripts/sloped_slew_check.gd`'s: a source-text comparison passes
## whenever two files happen to contain the same substrings, which is not the
## same as computing the same wall. Two trees carrying one rule is only worth
## something if they agree, and the only way to know they agree is to run both.
##
## One line per case: `[side, a, b, c, d(, floor)]|f,f,...`, six decimals, over
## a fixed sample count.

const Track := preload("res://assets/marble_machine/v2/v2_track.gd")

const COUNT := 24


func _init() -> void:
	# The four shapes the course uses: both rails over a window (the sprint and
	# the merge lead), one rail with the fork's own crest as its floor (leg3),
	# one rail at the bare floor (orange's lead), and a window that runs off
	# the end of the run (blue's tail).
	var cases: Array = [
		[0.0, -1, 0, 12, 14],
		[1.0, 9, 11, 18, 20, 0.12],
		[-1.0, 3, 5, 9, 11],
		[0.0, 17, 19, 23, 24],
	]
	for case in cases:
		var out: Array = Track.wall_factor(COUNT, case)
		var parts: Array = []
		for value in out:
			parts.append("%.6f" % float(value))
		print("%s|%s" % [str(case), ",".join(parts)])
	quit()
