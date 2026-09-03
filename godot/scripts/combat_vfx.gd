extends Node3D

## Combat feedback: contact flashes, shockwave rings and camera shake.
##
## Every effect here is spawned by an event the Python simulation recorded and
## exported. Nothing is inferred: this script never compares health values,
## never decides who hit whom and never invents a moment of its own.
##
## Effects age in *replay time* - the tick the event carries against the tick
## the playhead is on - and never in wall-clock time. A slow frame therefore
## shows the same animation at the same point of the battle as a fast one,
## which is what will let a frame-by-frame render match live playback later.
##
## Geometry only: two built-in primitives scaled and faded. No particle
## system, because a particle system is the one thing here that would not be
## reproducible frame for frame.

const EVENT_POWER_ACTIVATE := "power_activate"
const EVENT_HIT := "hit"
const EVENT_ELIMINATION := "elimination"

# Effect lifetimes, in *simulated* seconds.
const HIT_SECONDS := 0.24
const ACTIVATE_SECONDS := 0.34
const ELIMINATION_SECONDS := 0.60

# The damage that earns the biggest reaction. Roughly a capped Rush ram; past
# it everything is clamped, so no single hit can take over the screen.
const MAGNITUDE_FULL := 40.0

# World-unit sizes. One unit is 100 simulation pixels and a fighter's radius
# is 0.50 to 0.65, or half again as much while Titan is active - so even the
# weakest ring is drawn wider than the largest fighter and cannot be swallowed
# by the sphere it landed on.
const HIT_RING_RADIUS := Vector2(0.78, 1.70)
const HIT_FLASH_RADIUS := Vector2(0.09, 0.22)
const ACTIVATE_RING_RADIUS := 1.30
const ELIMINATION_RING_RADIUS := 2.60
const ELIMINATION_FLASH_RADIUS := 0.42

# Rings start as a bright point and open outwards.
const RING_START_FRACTION := 0.18
# Just clear of the floor, so a ring is never z-fighting with it.
const RING_HEIGHT := 0.10
# Roughly a fighter's centre: where two spheres visibly meet.
const FLASH_HEIGHT := 0.42
const RING_INNER := 0.78

const HIT_RING_ALPHA := 1.0
const ACTIVATE_RING_ALPHA := 0.45
const ELIMINATION_RING_ALPHA := 1.0
const FLASH_ALPHA := 1.0
const FLASH_GROWTH := 0.70
# A spark is the hottest thing on screen: the owner's hue is still in it, but
# it is close enough to white to read as the point of contact rather than as
# another ball.
const FLASH_LIGHTEN := 0.72
# The spark is gone well before the ring finishes opening.
const FLASH_LIFE_FRACTION := 0.55
# Driven past 1.0 so the spark clears the environment's glow threshold and
# blooms. Written straight into the HDR buffer: no particle system, and the
# same value every time it is drawn.
const FLASH_OVERDRIVE := 2.4

# Camera shake: short, small and only for hits that meant something.
const SHAKE_SECONDS := 0.15
# Below a quarter of a full-strength hit the camera does not move at all, so
# a chip of clone damage never sets the whole arena wobbling.
const SHAKE_MIN_STRENGTH := 0.25
const SHAKE_MAX_UNITS := 0.075
const SHAKE_FREQUENCY := 42.0
const SHAKE_VERTICAL_RATIO := 0.6
# A wobble at a slightly different rate on the second axis, so the shake
# reads as a jolt rather than a diagonal slide.
const SHAKE_CROSS_RATE := 1.37

const NEUTRAL_COLOR := Color(0.95, 0.96, 1.0)

var _events: Array = []
var _cursor := 0
var _physics_hz := 120.0
var _fighter_colors: Array[Color] = []
var _to_world: Callable
var _camera: Camera3D
var _camera_base := Vector3.ZERO

var _ring_mesh: TorusMesh
var _flash_mesh: SphereMesh
# One entry per live effect: the node plus the replay ticks it lives between.
var _effects: Array[Dictionary] = []
var _shakes: Array[Dictionary] = []


func configure(fighter_colors: Array[Color], camera: Camera3D, physics_hz: float,
		to_world: Callable) -> void:
	_fighter_colors = fighter_colors
	_camera = camera
	_camera_base = camera.position if camera != null else Vector3.ZERO
	_physics_hz = maxf(1.0, physics_hz)
	_to_world = to_world

	_ring_mesh = TorusMesh.new()
	_ring_mesh.inner_radius = RING_INNER
	_ring_mesh.outer_radius = 1.0
	_ring_mesh.rings = 48
	_ring_mesh.ring_segments = 8

	_flash_mesh = SphereMesh.new()
	_flash_mesh.radius = 1.0
	_flash_mesh.height = 2.0
	_flash_mesh.radial_segments = 16
	_flash_mesh.rings = 8


func set_events(events: Array) -> void:
	## The stream arrives already in tick order; playback only walks forward.
	_events = events
	_cursor = 0


func update_to_tick(tick: float) -> void:
	_spawn_due(tick)
	_age(tick)
	_apply_shake(tick)


## --- spawning ------------------------------------------------------------

func _spawn_due(tick: float) -> void:
	while _cursor < _events.size():
		var event: Dictionary = _events[_cursor]
		if float(event.get("tick", 0)) > tick:
			return
		_cursor += 1
		_spawn(event, tick)


func _spawn(event: Dictionary, tick: float) -> void:
	var start := float(event.get("tick", 0))
	var kind := str(event.get("type", ""))
	var position: Vector3 = _to_world.call(
		float(event.get("x", 0.0)), float(event.get("y", 0.0)), RING_HEIGHT)

	match kind:
		EVENT_HIT:
			var strength := _strength(event)
			var color := _source_color(event)
			_add_ring(position, color, start, tick, HIT_SECONDS,
				lerpf(HIT_RING_RADIUS.x, HIT_RING_RADIUS.y, strength),
				HIT_RING_ALPHA)
			_add_flash(position, color, start, tick, HIT_SECONDS,
				lerpf(HIT_FLASH_RADIUS.x, HIT_FLASH_RADIUS.y, strength))
			_add_shake(start, strength)
		EVENT_POWER_ACTIVATE:
			_add_ring(position, _source_color(event), start, tick,
				ACTIVATE_SECONDS, ACTIVATE_RING_RADIUS, ACTIVATE_RING_ALPHA)
		EVENT_ELIMINATION:
			# The target's colour, not the killer's: this is that fighter
			# going out, and the HUD already says whose bar emptied.
			var color := _color_for(event.get("target_id"))
			_add_ring(position, color, start, tick, ELIMINATION_SECONDS,
				ELIMINATION_RING_RADIUS, ELIMINATION_RING_ALPHA)
			_add_flash(position, color, start, tick, ELIMINATION_SECONDS,
				ELIMINATION_FLASH_RADIUS)
			_add_shake(start, 1.0)


func _add_ring(position: Vector3, color: Color, start: float, now: float,
		seconds: float, radius: float, alpha: float) -> void:
	var node := _make_node(_ring_mesh, color, alpha)
	if node == null:
		return
	node.position = position
	_register(node, start, now, seconds, {
		"from": radius * RING_START_FRACTION,
		"to": radius,
		"alpha": alpha,
	})


func _add_flash(position: Vector3, color: Color, start: float, now: float,
		seconds: float, radius: float) -> void:
	var hot := color.lightened(FLASH_LIGHTEN) * FLASH_OVERDRIVE
	var node := _make_node(_flash_mesh, hot, FLASH_ALPHA)
	if node == null:
		return
	# Lifted to about fighter-centre height so the flash sits on the contact
	# between two spheres rather than at their feet.
	node.position = position + Vector3(0.0, FLASH_HEIGHT, 0.0)
	_register(node, start, now, seconds * FLASH_LIFE_FRACTION, {
		"from": radius,
		"to": radius * (1.0 + FLASH_GROWTH),
		"alpha": FLASH_ALPHA,
	})


func _make_node(mesh: Mesh, color: Color, alpha: float) -> MeshInstance3D:
	var material := StandardMaterial3D.new()
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	material.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
	material.albedo_color = Color(color.r, color.g, color.b, alpha)

	var node := MeshInstance3D.new()
	node.mesh = mesh
	node.material_override = material
	node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(node)
	return node


func _register(node: MeshInstance3D, start: float, now: float, seconds: float,
		shape: Dictionary) -> void:
	var effect := shape.duplicate()
	effect["node"] = node
	effect["start"] = start
	effect["ticks"] = maxf(1.0, seconds * _physics_hz)
	_effects.append(effect)
	# Placed correctly straight away, so a frame is never drawn at unit scale
	# before the first age pass reaches it.
	_shape(effect, now)


## --- ageing and cleanup --------------------------------------------------

func _age(tick: float) -> void:
	var survivors: Array[Dictionary] = []
	for effect in _effects:
		var progress := (tick - float(effect["start"])) / float(effect["ticks"])
		if progress >= 1.0 or progress < 0.0:
			(effect["node"] as Node).queue_free()
			continue
		_shape(effect, tick)
		survivors.append(effect)
	_effects = survivors


func _shape(effect: Dictionary, tick: float) -> void:
	var progress := clampf(
		(tick - float(effect["start"])) / float(effect["ticks"]), 0.0, 1.0)
	# Fast out of the gate, easing as it opens: a shockwave, not a balloon.
	var eased := 1.0 - pow(1.0 - progress, 3.0)
	var radius: float = lerpf(float(effect["from"]), float(effect["to"]), eased)
	var fade := pow(1.0 - progress, 1.6)

	var node: MeshInstance3D = effect["node"]
	node.scale = Vector3.ONE * radius

	var material: StandardMaterial3D = node.material_override
	var color := material.albedo_color
	material.albedo_color = Color(color.r, color.g, color.b,
		float(effect["alpha"]) * fade)


func clear_effects() -> void:
	for effect in _effects:
		(effect["node"] as Node).queue_free()
	_effects.clear()
	_shakes.clear()


func live_effect_count() -> int:
	return _effects.size()


## --- camera --------------------------------------------------------------

func _add_shake(start: float, strength: float) -> void:
	## Only a hit with some weight behind it moves the camera at all.
	if strength <= SHAKE_MIN_STRENGTH:
		return
	var scaled := (strength - SHAKE_MIN_STRENGTH) / (1.0 - SHAKE_MIN_STRENGTH)
	_shakes.append({"start": start, "amount": scaled * SHAKE_MAX_UNITS})


func _apply_shake(tick: float) -> void:
	if _camera == null:
		return

	var offset := Vector3.ZERO
	var survivors: Array[Dictionary] = []
	for shake in _shakes:
		var age := (tick - float(shake["start"])) / _physics_hz
		if age < 0.0 or age >= SHAKE_SECONDS:
			continue
		survivors.append(shake)
		# Deterministic: a fixed decaying oscillation of replay time, with no
		# random offset anywhere.
		var decay := 1.0 - age / SHAKE_SECONDS
		var amount := float(shake["amount"]) * decay * decay
		offset.x += sin(age * SHAKE_FREQUENCY) * amount
		offset.y += cos(age * SHAKE_FREQUENCY * SHAKE_CROSS_RATE) * amount \
			* SHAKE_VERTICAL_RATIO
	_shakes = survivors

	# Always rebuilt from the base transform, so nothing accumulates and an
	# empty shake list restores the framing exactly.
	_camera.position = _camera_base + offset


## --- event helpers -------------------------------------------------------

func _strength(event: Dictionary) -> float:
	## Where this hit sits between "barely grazed" and "as hard as it gets".
	var magnitude: Variant = event.get("magnitude")
	if magnitude == null:
		return 0.0
	return clampf(float(magnitude) / MAGNITUDE_FULL, 0.0, 1.0)


func _source_color(event: Dictionary) -> Color:
	return _color_for(event.get("source_id"))


func _color_for(raw: Variant) -> Color:
	if raw == null:
		return NEUTRAL_COLOR
	var index := int(raw)
	if index < 0 or index >= _fighter_colors.size():
		return NEUTRAL_COLOR
	return _fighter_colors[index]
