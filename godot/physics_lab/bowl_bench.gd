extends SceneTree

## The bowl benchmark in Godot, with Jolt owning the physics.
##
## The cross-check for the other half of section 31 of the brief. PyBullet
## answers "can Python own 3D physics"; this answers "what would we gain by
## moving the authority downstream into Godot", which is a different question
## and a different architecture - physics would live below the replay it is
## supposed to produce.
##
## It is deliberately dumb. Everything that could differ between engines is
## decided in Python and handed over as data: the marble starts, the bowl as a
## flat triangle soup, every coefficient. Nothing here generates geometry,
## draws a random number, or reads a clock.
##
## ## The clock
##
## Physics steps are counted, never timed. `_physics_process` is called at
## `Engine.physics_ticks_per_second` whatever the machine is doing, and this
## quits after a fixed number of them, so a slow machine runs the same
## simulation as a fast one - the same contract `RaceSimulation.step` keeps in
## production. Nothing reads `delta` for anything but an assertion.
##
## ## Scale
##
## The world is built at `scale` times life size and reported at 1x, for the
## same reason the PyBullet prototype does it: a 3D engine's contact
## tolerances are tuned for objects about a metre across, and this benchmark's
## marble is 40 mm. Lengths, velocities and gravity scale together, which
## leaves time unchanged.

const REPORT_EVERY := 1200

var _spec: Dictionary
var _bench: Dictionary
var _scale := 25.0
var _dt := 1.0 / 240.0
var _stride := 4
var _max_ticks := 0
var _ticks := 0

var _bodies: Array[RigidBody3D] = []
var _states: Array[String] = []
var _alive: Array[bool] = []
var _last: Array[Dictionary] = []
var _frames: Array = []
var _events: Array = []
var _exit_count := 0
var _touching := {}
var _out_path := ""
var _failure := ""


func _initialize() -> void:
	var options := _options()
	var spec_path: String = options.get("spec", "")
	_out_path = options.get("out", "")
	if spec_path.is_empty() or _out_path.is_empty():
		push_error("bowl_bench: --spec and --out are both required")
		quit(2)
		return

	var text := FileAccess.get_file_as_string(spec_path)
	if text.is_empty():
		push_error("bowl_bench: cannot read %s" % spec_path)
		quit(2)
		return
	_spec = JSON.parse_string(text)
	if _spec == null:
		push_error("bowl_bench: %s is not JSON" % spec_path)
		quit(2)
		return

	_bench = _spec["benchmark"]
	_scale = float(_spec["scale"])
	_dt = 1.0 / float(_bench["physics_hz"])
	_stride = int(_bench["physics_hz"]) / int(_bench["sample_hz"])
	_max_ticks = int(round(float(_bench["duration_limit"]) * float(_bench["physics_hz"])))

	Engine.physics_ticks_per_second = int(_bench["physics_hz"])
	Engine.max_fps = 0
	Engine.time_scale = 1.0

	_build()
	root.add_child(Ticker.new(self))
	_sample_initial()


func _options() -> Dictionary:
	var parsed := {}
	for argument in OS.get_cmdline_user_args():
		var pair := argument.trim_prefix("--").split("=", true, 1)
		if pair.size() == 2:
			parsed[pair[0]] = pair[1]
	return parsed


func _build() -> void:
	var world := root.world_3d
	var space := world.space
	PhysicsServer3D.area_set_param(
		space, PhysicsServer3D.AREA_PARAM_GRAVITY,
		float(_bench["gravity"]) * _scale
	)
	PhysicsServer3D.area_set_param(
		space, PhysicsServer3D.AREA_PARAM_GRAVITY_VECTOR, Vector3(0, -1, 0)
	)

	# The bowl, as the exact triangle soup PyBullet was given. Handed over
	# flattened rather than rebuilt here, because "the same bowl" has to be a
	# fact about the data and not a claim about two implementations agreeing.
	var flat: Array = _spec["mesh"]
	var faces := PackedVector3Array()
	faces.resize(flat.size() / 3)
	for index in range(faces.size()):
		faces[index] = Vector3(
			float(flat[index * 3]) * _scale,
			float(flat[index * 3 + 1]) * _scale,
			float(flat[index * 3 + 2]) * _scale
		)
	var shape := ConcavePolygonShape3D.new()
	shape.set_faces(faces)

	var bowl := StaticBody3D.new()
	var bowl_collider := CollisionShape3D.new()
	bowl_collider.shape = shape
	bowl.add_child(bowl_collider)
	var bowl_material := PhysicsMaterial.new()
	# Jolt combines friction as sqrt(a*b), so the bowl carries whatever makes
	# the product come out at the benchmark's marble-on-bowl figure while the
	# marble carries the marble-on-marble one directly.
	bowl_material.friction = float(_spec["bowl_friction"])
	bowl_material.bounce = float(_bench["surface_restitution"])
	bowl.physics_material_override = bowl_material
	root.add_child(bowl)

	var marble_material := PhysicsMaterial.new()
	marble_material.friction = float(_bench["friction"])
	marble_material.bounce = float(_bench["restitution"])

	var radius := float(_bench["marble_radius"]) * _scale
	for start in _spec["starts"]:
		var body := RigidBody3D.new()
		body.mass = float(_spec["scaled_mass"])
		body.physics_material_override = marble_material
		body.continuous_cd = true
		body.can_sleep = false
		body.custom_integrator = false
		body.linear_damp_mode = RigidBody3D.DAMP_MODE_REPLACE
		body.angular_damp_mode = RigidBody3D.DAMP_MODE_REPLACE
		body.linear_damp = float(_spec["damping"])
		body.angular_damp = float(_spec["damping"])
		body.contact_monitor = true
		body.max_contacts_reported = 16

		var sphere := SphereShape3D.new()
		sphere.radius = radius
		var collider := CollisionShape3D.new()
		collider.shape = sphere
		body.add_child(collider)
		# Placed BEFORE it enters the tree. A RigidBody3D that is added first
		# and moved afterwards hands its transform to the physics server as a
		# deferred state change, so `global_position` still reads as the origin
		# until the first step has run - and frame zero of the recording came
		# out with all eight marbles stacked at the centre of the bowl, which
		# the analysis duly reported as a full-diameter overlap and a 0.8 J
		# jump in energy.
		body.transform.origin = _vector(start["position"]) * _scale
		root.add_child(body)

		body.linear_velocity = _vector(start["velocity"]) * _scale
		# Spin is v/r and both scale together, so it carries across untouched.
		body.angular_velocity = _vector(start["spin"])

		_bodies.append(body)
		_states.append("surface")
		_alive.append(true)
		_last.append({})


static func _vector(values: Array) -> Vector3:
	return Vector3(float(values[0]), float(values[1]), float(values[2]))


func physics_tick() -> void:
	_ticks += 1
	var now := _ticks * _dt

	var contacts := {}
	for index in range(_bodies.size()):
		if not _alive[index]:
			continue
		var body := _bodies[index]
		var touching_bowl := false
		for other in body.get_colliding_bodies():
			if other is StaticBody3D:
				touching_bowl = true
				continue
			var other_index := _bodies.find(other)
			if other_index < 0 or other_index == index:
				continue
			var pair := "%d-%d" % [mini(index, other_index), maxi(index, other_index)]
			contacts[pair] = [mini(index, other_index), maxi(index, other_index)]
		_states[index] = "surface" if touching_bowl else "free"

	for pair in contacts:
		if _touching.has(pair):
			continue
		var ids: Array = contacts[pair]
		var first: RigidBody3D = _bodies[ids[0]]
		var second: RigidBody3D = _bodies[ids[1]]
		var separation := (second.global_position - first.global_position)
		var normal := separation.normalized() if separation.length() > 0.0 else Vector3.UP
		_events.append({
			"time": now,
			"kind": "collision",
			"a": ids[0],
			"b": ids[1],
			"closing_speed": absf(
				(second.linear_velocity - first.linear_velocity).dot(normal)
			) / _scale,
			"position": _out(first.global_position.lerp(second.global_position, 0.5)),
		})
	_touching = contacts

	var exit_y := float(_bench["drain_exit_y"]) * _scale
	var max_radius := float(_bench["surface_max_radius"]) * _scale
	for index in range(_bodies.size()):
		if not _alive[index]:
			continue
		var body := _bodies[index]
		var position := body.global_position
		if not (is_finite(position.x) and is_finite(position.y) and is_finite(position.z)):
			_failure = "marble %d left the real numbers" % index
			_alive[index] = false
			continue
		var kind := ""
		if position.y <= exit_y:
			kind = "drained"
		elif Vector2(position.x, position.z).length() > max_radius:
			kind = "escaped"
		if kind.is_empty():
			continue
		_last[index] = _snapshot(index)
		_exit_count += 1
		_states[index] = kind
		_alive[index] = false
		_events.append({
			"time": now, "kind": kind, "id": index,
			"order": _exit_count, "position": _out(position),
		})
		body.queue_free()

	if _ticks % _stride == 0:
		_sample()
	if _ticks % REPORT_EVERY == 0:
		print("bowl_bench: tick %d / %d" % [_ticks, _max_ticks])

	if _ticks >= _max_ticks or not _alive.has(true) or not _failure.is_empty():
		_finish()


func _out(vector: Vector3) -> Array:
	return [vector.x / _scale, vector.y / _scale, vector.z / _scale]


func _snapshot(index: int) -> Dictionary:
	var body := _bodies[index]
	var quaternion := body.global_transform.basis.get_rotation_quaternion()
	return {
		"id": index,
		"position": _out(body.global_position),
		"velocity": _out(body.linear_velocity),
		"orientation": [quaternion.x, quaternion.y, quaternion.z, quaternion.w],
		"spin": [body.angular_velocity.x, body.angular_velocity.y, body.angular_velocity.z],
		"state": _states[index],
	}


func _sample_initial() -> void:
	## Frame zero comes from the run spec, not from the engine.
	##
	## A RigidBody3D reports `global_position` through the physics server, and
	## the server has not been stepped yet when this runs, so it answers with
	## the origin however the node transform was set - which put all eight
	## marbles on top of each other in frame zero and had the analysis report a
	## full-diameter overlap and a 0.8 J jump in energy on the second frame.
	##
	## Reading the spec here is not a workaround for that; it is the correct
	## thing independently. Frame zero *is* the initial condition, and the
	## initial condition is the spec.
	var marbles := []
	for index in range(_spec["starts"].size()):
		var start: Dictionary = _spec["starts"][index]
		marbles.append({
			"id": index,
			"position": start["position"],
			"velocity": start["velocity"],
			"orientation": [0.0, 0.0, 0.0, 1.0],
			"spin": start["spin"],
			"state": "surface",
		})
	_frames.append({"time": 0.0, "marbles": marbles})


func _sample() -> void:
	var marbles := []
	for index in range(_bodies.size()):
		var marble: Dictionary
		if _alive[index]:
			marble = _snapshot(index)
		else:
			marble = _last[index].duplicate(true)
			marble["velocity"] = [0.0, 0.0, 0.0]
			marble["spin"] = [0.0, 0.0, 0.0]
		marble["state"] = _states[index]
		marbles.append(marble)
	_frames.append({"time": _ticks * _dt, "marbles": marbles})


func _finish() -> void:
	var drained := 0
	var escaped := 0
	for state in _states:
		if state == "drained":
			drained += 1
		elif state == "escaped":
			escaped += 1
	var payload := {
		"ticks": _ticks,
		"sim_seconds": _ticks * _dt,
		"failure": _failure,
		"engine": "godot-jolt",
		"godot_version": Engine.get_version_info()["string"],
		"physics_engine": ProjectSettings.get_setting("physics/3d/physics_engine"),
		"drained": drained,
		"escaped": escaped,
		"still_going": _alive.count(true),
		"frames": _frames,
		"events": _events,
	}
	var handle := FileAccess.open(_out_path, FileAccess.WRITE)
	if handle == null:
		push_error("bowl_bench: cannot write %s" % _out_path)
		quit(3)
		return
	handle.store_string(JSON.stringify(payload))
	handle.close()
	print("bowl_bench: %d ticks, %d drained, %d escaped -> %s" % [
		_ticks, drained, escaped, _out_path])
	quit(0)


## The only reason this exists: `_physics_process` is a Node callback and a
## SceneTree is not a Node. One child, forwarding one call.
class Ticker extends Node:
	var _owner: SceneTree

	func _init(owner: SceneTree) -> void:
		_owner = owner

	func _physics_process(_delta: float) -> void:
		_owner.call("physics_tick")
