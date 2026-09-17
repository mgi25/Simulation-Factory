extends RefCounted

## The Race #2 bookends: a start stand and a finish stand, from a spec.
##
## `race2.bookends` writes the spec and this file instantiates it. The split is
## the same one `environment_stage.gd` makes with a profile, and for the same
## reason: the shapes are a design decision that wants to be measured in Python
## - against the replay, against the camera track - and the instantiation is
## engine work with no decisions in it.
##
## **Nothing here is a collider.** A bookend is scenery over a locked
## simulation; see the module docstring on the Python side. Every node this
## builds is a `MeshInstance3D` and there is no `StaticBody3D` in the file.
##
## ## Units and parenting
##
## The spec is in layout units, which are Godot world units, so the root this
## returns is parented at the *scene* root and never under `Course` (which is
## scaled by `render_scale` to convert simulation units). Passing this node to
## the scaled parent would shrink a stand by 0.57 and is the one mistake the
## seam can make; `race2_scene.gd` adds it beside `Stage`, not beside `Course`.
##
## ## The motion group
##
## A stand may carry one moving group - the start's gate. It is a `Node3D` with
## the parts under it and the animation on the parent's transform, so the parts
## themselves are authored in the same frame as everything else and a frame of
## the animation is one vector add. `set_time` is called from the scene's own
## `set_time`, after the replay is placed, and is a pure function of seconds:
## the same second gives the same pose whether the clip is rendered forwards,
## backwards or one still at a time, which is what makes the gate deterministic
## in the sense `tests/test_race2_v33_bookends.py` asserts.

const COURSE_LAYER := 1


static func build(palette, spec: Dictionary) -> Node3D:
	var root := Node3D.new()
	root.name = "Bookends"
	if spec.is_empty():
		return root
	var stands: Array = spec.get("stands", [])
	var built := 0
	var moving := 0
	for entry in stands:
		var stand: Dictionary = entry
		var node := Node3D.new()
		node.name = "Stand_%s" % str(stand.get("id", "?"))
		root.add_child(node)
		var statics := Node3D.new()
		statics.name = "Static"
		node.add_child(statics)
		for part_entry in (stand.get("static", []) as Array):
			var made := _part(palette, part_entry)
			if made != null:
				statics.add_child(made)
				built += 1
		var motion: Dictionary = stand.get("motion", {})
		var parts: Array = motion.get("parts", [])
		if parts.is_empty():
			continue
		var group := Node3D.new()
		group.name = "Motion"
		# The animation is read back off the node, so a caller that only has
		# the tree can still pose it. Meta rather than script variables because
		# this class is a builder and holds no state between calls.
		group.set_meta("kind", str(motion.get("kind", "none")))
		group.set_meta("axis", _vec(motion.get("axis", [0.0, 1.0, 0.0])))
		group.set_meta("travel", float(motion.get("travel", 0.0)))
		group.set_meta("starts", float(motion.get("starts", 0.0)))
		group.set_meta("duration", float(motion.get("duration", 0.0)))
		group.set_meta("ease", str(motion.get("ease", "linear")))
		node.add_child(group)
		for part_entry in parts:
			var made := _part(palette, part_entry)
			if made != null:
				group.add_child(made)
				built += 1
		moving += 1
	print("bookends: %d stands, %d parts, %d moving groups" % [
		stands.size(), built, moving])
	return root


static func set_time(root: Node3D, seconds: float) -> void:
	## Pose every moving group. Safe to call with no bookends built.
	if root == null:
		return
	for stand in root.get_children():
		for child in stand.get_children():
			if child.name != "Motion":
				continue
			var group := child as Node3D
			var travel: float = group.get_meta("travel", 0.0)
			var starts: float = group.get_meta("starts", 0.0)
			var duration: float = group.get_meta("duration", 0.0)
			var axis: Vector3 = group.get_meta("axis", Vector3.UP)
			var phase := 0.0
			if duration > 1.0e-6:
				phase = clampf((seconds - starts) / duration, 0.0, 1.0)
			elif seconds >= starts:
				phase = 1.0
			if str(group.get_meta("ease", "linear")) == "smoothstep":
				phase = phase * phase * (3.0 - 2.0 * phase)
			group.position = axis * (travel * phase)


static func gate_phase(spec: Dictionary, seconds: float) -> float:
	## The same curve, for a test that wants it without an engine.
	for entry in (spec.get("stands", []) as Array):
		var stand: Dictionary = entry
		var motion: Dictionary = stand.get("motion", {})
		if str(motion.get("kind", "none")) != "slide":
			continue
		var starts := float(motion.get("starts", 0.0))
		var duration := float(motion.get("duration", 0.0))
		var phase := 0.0
		if duration > 1.0e-6:
			phase = clampf((seconds - starts) / duration, 0.0, 1.0)
		elif seconds >= starts:
			phase = 1.0
		if str(motion.get("ease", "linear")) == "smoothstep":
			phase = phase * phase * (3.0 - 2.0 * phase)
		return phase
	return 0.0


static func _part(palette, entry) -> MeshInstance3D:
	var part: Dictionary = entry
	var kind := str(part.get("kind", ""))
	var node := MeshInstance3D.new()
	node.name = str(part.get("name", kind))
	node.layers = COURSE_LAYER
	# A part may declare `"shadow": false` - the back board and the portal do,
	# because they stand between the room's key and the bays. See
	# `race2.bookends._no_shadow` for the arithmetic; the flag is read here
	# rather than inferred from a name so the decision stays on the Python
	# side with the measurement that produced it.
	node.cast_shadow = (GeometryInstance3D.SHADOW_CASTING_SETTING_ON
		if bool(part.get("shadow", true))
		else GeometryInstance3D.SHADOW_CASTING_SETTING_OFF)
	if kind == "box":
		var half: Array = part.get("half", [1.0, 1.0, 1.0])
		var box := BoxMesh.new()
		box.size = Vector3(float(half[0]), float(half[1]), float(half[2])) * 2.0
		node.mesh = box
		node.transform = Transform3D(
			Basis(_vec(part.get("along", [1.0, 0.0, 0.0])),
				_vec(part.get("up", [0.0, 1.0, 0.0])),
				_vec(part.get("across", [0.0, 0.0, 1.0]))),
			_vec(part.get("centre", [0.0, 0.0, 0.0])))
	elif kind == "cylinder":
		var a := _vec(part.get("from", [0.0, 0.0, 0.0]))
		var b := _vec(part.get("to", [0.0, 1.0, 0.0]))
		var span := b - a
		var length := span.length()
		if length < 1.0e-6:
			return null
		var cylinder := CylinderMesh.new()
		cylinder.top_radius = float(part.get("radius", 0.1))
		cylinder.bottom_radius = cylinder.top_radius
		cylinder.height = length
		cylinder.radial_segments = 12
		cylinder.rings = 1
		node.mesh = cylinder
		# `CylinderMesh` runs along local Y, so the basis is built from the
		# span and any perpendicular; the mesh is a surface of revolution about
		# that axis, so which perpendicular is chosen cannot be visible.
		var up := span / length
		var seed_axis := Vector3.RIGHT if absf(up.dot(Vector3.RIGHT)) < 0.9 \
			else Vector3.FORWARD
		var right := seed_axis.cross(up).normalized()
		var forward := up.cross(right).normalized()
		node.transform = Transform3D(Basis(right, up, forward), a + span * 0.5)
	else:
		push_error("race2_bookends: unknown part kind '%s'" % kind)
		return null
	var key := str(part.get("material", ""))
	var material: StandardMaterial3D = palette.get_material(key)
	if material == null:
		push_error("race2_bookends: no material '%s'" % key)
		return null
	node.material_override = material
	return node


static func _vec(raw) -> Vector3:
	var values: Array = raw
	if values.size() < 3:
		return Vector3.ZERO
	return Vector3(float(values[0]), float(values[1]), float(values[2]))
