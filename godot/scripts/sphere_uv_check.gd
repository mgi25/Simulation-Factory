extends SceneTree
## Proof that `racer_visual`'s UV assumption is the engine's, not a guess.
##
## Every racer marker is painted into a texture by inverting Godot's
## `SphereMesh` UV layout: given a texel, `racer_visual.direction()` says which
## point of the ball it lands on, and the marker is a function of that point.
## If a Godot release ever changed that layout, the bands would silently become
## the wrong shape - a great circle would stop being a great circle - and the
## render would still succeed. So the mapping is checked against the mesh the
## engine actually builds rather than trusted.
##
##     godot --headless --path godot --script res://scripts/sphere_uv_check.gd

const RacerVisual := preload("res://assets/marble_machine/racers/racer_visual.gd")

const TOLERANCE := 1.0e-5


func _init() -> void:
	var sphere := SphereMesh.new()
	sphere.radius = 1.0
	sphere.height = 2.0
	sphere.radial_segments = 24
	sphere.rings = 12
	var arrays := sphere.get_mesh_arrays()
	var points: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var uvs: PackedVector2Array = arrays[Mesh.ARRAY_TEX_UV]

	var worst := 0.0
	for index in points.size():
		var uv := uvs[index]
		var offset: float = RacerVisual.direction(uv.x, uv.y).distance_to(
			points[index])
		worst = maxf(worst, offset)
	print("sphere uv: %d vertices, worst offset %.9f" % [points.size(), worst])
	if worst > TOLERANCE:
		push_error("sphere_uv_check: racer_visual.direction() no longer "
			+ "matches SphereMesh (worst offset %.9f)" % worst)
		quit(1)
		return

	# The marker is a function of a *direction*, so it has no preferred pixel
	# and no preferred frame. Spot-check that the band really is a great
	# circle: every point on it is perpendicular to the band normal.
	var on_band := 0
	var off_plane := 0.0
	for step in 4000:
		var u := float(step % 80) / 80.0
		var v := (float(step / 80) + 0.5) / 50.0
		var point: Vector3 = RacerVisual.direction(u, v)
		if RacerVisual.coverage("ribbon", point) > 0.99:
			on_band += 1
			off_plane = maxf(off_plane, absf(
				point.dot(RacerVisual.RIBBON_NORMAL.normalized())))
	print("ribbon: %d sampled points, all within %.4f of the plane (limit %.4f)"
		% [on_band, off_plane, RacerVisual.BAND_HALF])
	if on_band == 0 or off_plane > RacerVisual.BAND_HALF:
		push_error("sphere_uv_check: the ribbon is not a great circle")
		quit(1)
		return

	# And the appearance the films shipped really is empty.
	for step in 500:
		var point: Vector3 = RacerVisual.direction(
			float(step % 25) / 25.0, (float(step / 25) + 0.5) / 20.0)
		if RacerVisual.coverage("solid", point) != 0.0:
			push_error("sphere_uv_check: solid is not featureless")
			quit(1)
			return
	print("solid: featureless, as shipped")
	quit(0)
