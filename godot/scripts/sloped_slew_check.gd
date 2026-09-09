extends SceneTree

## Prints `v2_track.slewed_bank` on a fixed input, so Python and GDScript can be
## compared as **numbers** rather than as source text.
##
## `tests/test_sloped_bank_slew.py` reads this and compares it against
## `sloped.track._slewed_bank`. It exists because the source-text comparison
## that came first is a weak guarantee - it passes whenever the two files happen
## to contain the same substrings, which is not the same as computing the same
## roll. Two trees carrying one table is only worth something if they agree, and
## the only way to know they agree is to run them both.
##
## One line per case: `[first, last, margin]|deg,deg,...`, six decimals. The
## `profile_scale` argument is 1.0, so the half width is `CHANNEL_HALF` and the
## Python side has to be passed the same.

const Track := preload("res://assets/marble_machine/v2/v2_track.gd")


func _init() -> void:
	# leg2's own shape, roughly: a hard roll coming off through zero on a 10%
	# fall, plus a sign flip, which is the case a magnitude limit gets wrong.
	var degrees: Array = [
		-20.68, -19.64, -16.69, -11.72, -5.70, -0.59, 1.89, 1.47,
		-0.31, -1.44, -0.91, 0.74, 2.29, 2.95, 2.68, 1.81,
	]
	var banks: Array = []
	for value in degrees:
		banks.append(deg_to_rad(float(value)))
	var path: Array = []
	for index in degrees.size():
		path.append(Vector3(0.0, -0.0674 * float(index), 0.0))

	for slew in [[1, 13, 1.0], [1, 13, 0.5], [0, 3, 1.0], []]:
		var out: Array = Track.slewed_bank(banks, path, slew, 1.0)
		var parts: Array = []
		for value in out:
			parts.append("%.6f" % rad_to_deg(float(value)))
		print("%s|%s" % [str(slew), ",".join(parts)])
	quit()
