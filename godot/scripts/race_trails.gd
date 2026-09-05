extends Node3D

## Speed trails, rebuilt every frame from the racer's own replay history.
##
## There is no particle system here and there could not be. A particle system
## integrates: it emits on a timer, ages its particles against a delta, and
## seeds them from a random stream. The offline renderer never passes a delta
## and draws each frame exactly once at an exact replay instant, so a particle
## trail would look different every render and the pipeline's byte-identical
## check would fail on the first comparison. It would also be *guessing* where
## the racer had been.
##
## The replay already knows. Frame N-18 through frame N holds eighteen
## positions the racer actually occupied, so the trail is not simulated, it is
## drawn: a ribbon threaded through recorded history, rebuilt from scratch on
## every frame. Seek anywhere and it is correct immediately, with no warm-up
## and nothing to catch up.
##
## The ribbon is one `ImmediateMesh` per racer, about forty vertices each,
## rebuilt per frame. That is nothing next to a course - and it means a trail
## can be shaped by anything in the replay, which is how speed drives its
## length and a jump pad brightens it.

# How far back the ribbon can reach, in replay frames. Eighteen frames is
# 0.3 seconds; at the speed cap that is about 225 course pixels, or three and
# a half racer diameters. Longer starts to hide the course behind it.
const MAX_FRAMES := 18

# Speed thresholds, in course pixels per second, taken from measured races
# rather than chosen. The cap is 750 and the median racer sample sits near
# 400, so a trail that started at zero would be on almost all the time and
# would stop meaning anything. Starting at 330 leaves roughly half of all
# samples with no trail at all, and full length is reserved for the top fifth.
const SPEED_MIN := 330.0
const SPEED_FULL := 700.0

# The head is a little narrower than the racer, so the ball stays the widest
# thing and the trail reads as coming out from behind it.
const HEAD_WIDTH := 0.78
# How much of the ribbon's length the fade covers. Below 1.0 the tail is
# still faintly visible where it ends, which reads as a cut.
const FADE_POWER := 1.7
const MAX_ALPHA := 0.62
# A jump pad's kick brightens and lengthens the trail for a moment, so a
# launch reads as a launch rather than as the racer simply moving.
const BOOST_ALPHA := 0.5
const BOOST_LENGTH := 0.45

var _colors: Array[Color] = []
var _radius: Array[float] = []
var _frames: Array = []
var _to_world: Callable

var _meshes: Array[ImmediateMesh] = []
var _nodes: Array[MeshInstance3D] = []


func configure(colors: Array[Color], radius: Array[float], frames: Array,
		to_world: Callable) -> void:
	_colors = colors
	_radius = radius
	_frames = frames
	_to_world = to_world

	for index in _colors.size():
		var mesh := ImmediateMesh.new()
		var node := MeshInstance3D.new()
		node.name = "Trail%d" % index
		node.mesh = mesh
		node.material_override = _make_material()
		node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		node.visible = false
		add_child(node)
		_meshes.append(mesh)
		_nodes.append(node)


func _make_material() -> StandardMaterial3D:
	## Additive light with no depth write.
	##
	## Additive because a trail is a smear of the racer's own light, not an
	## object - it should brighten what is behind it and never darken it. No
	## depth write so ten overlapping ribbons in a pile-up cannot sort against
	## each other and flicker; depth *test* stays on, so a trail is still
	## hidden by a ramp it has passed behind.
	var material := StandardMaterial3D.new()
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	material.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
	material.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_DISABLED
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	material.vertex_color_use_as_albedo = true
	material.albedo_color = Color.WHITE
	return material


func update_to_frame(index: int, blend: float, vfx: Node) -> void:
	## Redraw every trail for the frame the playhead is on.
	if _frames.is_empty():
		return
	var frame: Dictionary = _frames[index]
	var racers: Array = frame.get("racers", [])
	var next_index := mini(index + 1, _frames.size() - 1)
	var upcoming: Array = (_frames[next_index] as Dictionary).get("racers", [])
	var tick := float(frame.get("tick", 0))

	for racer_index in _nodes.size():
		if racer_index >= racers.size():
			continue
		var now: Dictionary = racers[racer_index]
		var boost := 0.0
		if vfx != null:
			boost = float(vfx.speed_boost_for(racer_index, tick))
		_draw_trail(racer_index, index, blend, now, upcoming, boost)


func _draw_trail(racer_index: int, index: int, blend: float, now: Dictionary,
		upcoming: Array, boost: float) -> void:
	var mesh := _meshes[racer_index]
	var node := _nodes[racer_index]
	mesh.clear_surfaces()

	if bool(now.get("retired", false)) or bool(now.get("finished", false)):
		node.visible = false
		return

	# How much trail this racer has earned, from the speed the simulation
	# recorded for it on this frame.
	var speed := float(now.get("speed", 0.0))
	var strength := clampf(
		(speed - SPEED_MIN) / maxf(1.0, SPEED_FULL - SPEED_MIN), 0.0, 1.0)
	strength = minf(1.0, strength + boost * BOOST_LENGTH)
	if strength <= 0.001:
		node.visible = false
		return

	var span := int(round(strength * float(MAX_FRAMES)))
	if span < 2:
		node.visible = false
		return

	var points := _history(racer_index, index, blend, now, upcoming, span)
	if points.size() < 2:
		node.visible = false
		return

	var color := _colors[racer_index]
	var width := _radius[racer_index] * HEAD_WIDTH
	var alpha := MAX_ALPHA * strength * (1.0 + boost * BOOST_ALPHA)

	mesh.surface_begin(Mesh.PRIMITIVE_TRIANGLE_STRIP)
	for step in points.size():
		var point: Vector3 = points[step]
		# `step` 0 is the head, at the racer; the last is the oldest sample.
		var along := float(step) / float(points.size() - 1)
		var taper := 1.0 - along
		var fade := pow(taper, FADE_POWER)

		# The ribbon is widened across the direction of travel, in the ground
		# plane, so it lies flat under the racer rather than standing up.
		var direction := _direction(points, step)
		var side := Vector3(-direction.z, 0.0, direction.x).normalized() \
			* width * maxf(0.06, taper)

		var tint := Color(color.r, color.g, color.b, alpha * fade)
		mesh.surface_set_color(tint)
		mesh.surface_add_vertex(point - side)
		mesh.surface_set_color(tint)
		mesh.surface_add_vertex(point + side)
	mesh.surface_end()

	node.material_override.albedo_color = Color.WHITE
	node.visible = true


func _direction(points: Array, step: int) -> Vector3:
	## The travel direction at one point of the ribbon, in the ground plane.
	var ahead: Vector3 = points[maxi(0, step - 1)]
	var behind: Vector3 = points[mini(points.size() - 1, step + 1)]
	var delta := ahead - behind
	delta.y = 0.0
	if delta.length_squared() < 1.0e-8:
		return Vector3.FORWARD
	return delta.normalized()


func _history(racer_index: int, index: int, blend: float, now: Dictionary,
		upcoming: Array, span: int) -> Array:
	## Where this racer has been, newest first.
	##
	## The head is the interpolated position the racer is actually being drawn
	## at, so the trail is attached to the ball rather than trailing a frame
	## behind it. Everything after that is recorded history, read straight out
	## of the replay.
	var points: Array = []
	var height := _radius[racer_index]

	var head_x := float(now.get("x", 0.0))
	var head_y := float(now.get("y", 0.0))
	if racer_index < upcoming.size() and blend > 0.0:
		var soon: Dictionary = upcoming[racer_index]
		head_x = lerpf(head_x, float(soon.get("x", head_x)), blend)
		head_y = lerpf(head_y, float(soon.get("y", head_y)), blend)
	points.append(_to_world.call(head_x, head_y, height))

	for back in range(1, span + 1):
		var at := index - back
		if at < 0:
			break
		var past: Array = (_frames[at] as Dictionary).get("racers", [])
		if racer_index >= past.size():
			break
		var sample: Dictionary = past[racer_index]
		# A racer that was recovered has been teleported, and joining the two
		# sides of that jump would draw a stripe across the course.
		if int(sample.get("recoveries", 0)) != int(now.get("recoveries", 0)):
			break
		points.append(_to_world.call(
			float(sample.get("x", 0.0)), float(sample.get("y", 0.0)), height))
	return points
