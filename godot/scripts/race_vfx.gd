extends Node3D

## Race feedback: impact sparks, jump pulses, finish bursts and camera jolts.
##
## The race counterpart of `combat_vfx.gd`, and it keeps that file's two
## rules, which are the reason either of them can exist at all.
##
## **Nothing is inferred.** Every effect here is spawned by an event the Python
## simulation recorded and exported. This script never compares positions,
## never decides that two racers touched, and never invents a moment. If the
## replay does not say a collision happened, no collision is drawn - and the
## effect appears at the coordinates the *event* carries, not at wherever the
## racers involved have since got to.
##
## **Everything ages in replay time.** An effect knows the tick it was recorded
## on and the tick the playhead is on, and nothing else. No delta, no wall
## clock, no particle system - geometry scaled and faded by a function of two
## integers. A frame rendered in five milliseconds and the same frame rendered
## in five hundred are the same picture.
##
## The magnitudes are measured rather than chosen. The simulation only records
## a collision above 620 px/s, and across three full races those run from 620
## to about 1250 with a median near 730 - so 620 is the floor here and the
## full reaction is held back for 980, which leaves the ordinary bump looking
## like an ordinary bump.

const EVENT_COLLISION := "collision"
const EVENT_JUMP := "jump"
const EVENT_FINISH := "finish"
const EVENT_WINNER := "winner"
const EVENT_RETIRED := "retired"
const EVENT_RECOVERY := "recovery"

# --- impact scaling -------------------------------------------------------
#
# The closing speed the simulation refuses to record below, and the speed that
# earns the whole reaction. Anything past the top is clamped, so no single
# collision can take over the frame.
const IMPACT_FLOOR := 620.0
const IMPACT_FULL := 980.0

# Effect lifetimes, in *simulated* seconds.
const IMPACT_SECONDS := 0.30
const JUMP_SECONDS := 0.42
const FINISH_SECONDS := 0.55
const WINNER_SECONDS := 1.10
const RETIRE_SECONDS := 0.60

# World-unit sizes, and the scale that matters is the racer: a radius of 0.30.
#
# Every number here came down for V0.4, and the reason is a rule rather than a
# preference. An effect exists to say *something happened to that racer*, and
# the moment it is large enough to cover the racer it has stopped saying that
# and started hiding the thing it was pointing at. So the tiers are set
# against the ball:
#
#     ordinary contact   ring peaks at  1.5 racer radii   - a highlight
#     hard contact       ring peaks at  3.7 racer radii   - unmissable
#     the win            ring peaks at  8.0 racer radii   - once, at the end
#
# V0.3 ran at 2.1 / 5.2 / 10.7. On a 1080-wide frame a 5.2-radius ring is 310
# pixels of additive white across a third of the course, several times a
# second in a pile-up, and it was routinely the brightest thing in a shot
# where the brightest thing should be a racer. `tests/test_race_visuals.py`
# holds the ratios so they cannot drift back up.
const IMPACT_RING := Vector2(0.45, 1.10)
const IMPACT_FLASH := Vector2(0.065, 0.17)
const JUMP_RING := 0.70
const JUMP_FLASH := 0.16
const FINISH_RING := 0.95
const WINNER_RING := 2.40
const WINNER_FLASH := 0.40
const RETIRE_RING := 0.70

# Rings start as a bright point and open outwards.
const RING_START_FRACTION := 0.16
const RING_INNER := 0.80
# Above the course, not on it. Ramps stand 0.30 units tall, pegs 0.62 and
# spinner hubs 0.72, so a ring laid just clear of the floor would be hidden
# behind the very geometry the collision happened against - which is where
# collisions mostly happen. Lifted to a racer's own centre height it reads as
# a flash around the ball rather than a decal under the track.
const RING_HEIGHT := 0.66
# Roughly where two spheres visibly meet.
const FLASH_HEIGHT := 0.06

const IMPACT_RING_ALPHA := 0.72
const JUMP_RING_ALPHA := 0.62
const FINISH_RING_ALPHA := 0.68
const FLASH_ALPHA := 1.0
const FLASH_GROWTH := 0.65
const FLASH_LIFE_FRACTION := 0.5
# A spark is the hottest thing on screen: the racer's hue is still in it, but
# close enough to white to read as the point of contact rather than as another
# ball. Driven past 1.0 so it clears the environment's glow threshold and
# blooms - written straight into the HDR buffer, the same value every time.
const FLASH_LIGHTEN := 0.70
const FLASH_OVERDRIVE := 1.7

# --- squash ---------------------------------------------------------------
#
# Presentation only. The physics has already happened; this is the racer
# reacting to it visually and it changes nothing about where the racer goes.
const SQUASH_SECONDS := 0.24
# Below this the collision was not worth a visible deformation, and squashing
# on every recorded bump would leave the field permanently wobbling.
const SQUASH_MIN_STRENGTH := 0.10

# --- jump boost -----------------------------------------------------------

const BOOST_SECONDS := 0.55
# How long the pad itself stays lit after it fires. Shorter than the boost the
# racer carries away, so the pad reads as having discharged into the racer.
const PAD_PULSE_SECONDS := 0.40

# --- camera ---------------------------------------------------------------
#
# Short, small, and only for collisions that meant something. A camera that
# moves on every contact is a camera nobody can follow a racer through.
const SHAKE_SECONDS := 0.16
const SHAKE_MIN_STRENGTH := 0.45
const SHAKE_MAX_UNITS := 0.040
const SHAKE_FREQUENCY := 46.0
const SHAKE_CROSS_RATE := 1.41
const SHAKE_VERTICAL_RATIO := 0.55
const WINNER_SHAKE := 0.9

const NEUTRAL_COLOR := Color(0.95, 0.96, 1.0)

var _events: Array = []
var _silent := false
var _cursor := 0
var _last_tick := -1.0
var _physics_hz := 120.0
var _colors: Array[Color] = []
var _to_world: Callable

var _ring_mesh: TorusMesh
var _flash_mesh: SphereMesh

# One entry per live effect: the node plus the replay ticks it lives between.
var _effects: Array[Dictionary] = []
var _shakes: Array[Dictionary] = []
# Per-racer reaction records, kept as plain data rather than as nodes because
# the racers read them back rather than this file drawing them.
var _squashes: Array[Dictionary] = []
var _boosts: Array[Dictionary] = []
# Which jump pad fired, and when. Keyed by the course piece id the event
# names, so the pad that actually launched a racer is the one that lights up
# rather than every pad on the course.
var _pad_pulses: Dictionary = {}


func configure(colors: Array[Color], physics_hz: float,
		to_world: Callable) -> void:
	_colors = colors
	_physics_hz = maxf(1.0, physics_hz)
	_to_world = to_world

	_ring_mesh = TorusMesh.new()
	_ring_mesh.inner_radius = RING_INNER
	_ring_mesh.outer_radius = 1.0
	_ring_mesh.rings = 44
	_ring_mesh.ring_segments = 6

	_flash_mesh = SphereMesh.new()
	_flash_mesh.radius = 1.0
	_flash_mesh.height = 2.0
	_flash_mesh.radial_segments = 14
	_flash_mesh.rings = 7


func set_silent(silent: bool) -> void:
	## Track the events, draw nothing.
	##
	## The verification camera measures where racers are, and an additive ring
	## sitting on top of a ball is the one thing guaranteed to be exactly
	## where the measurement is taken. The squash and boost records are still
	## kept, so the rest of the scene behaves identically either way.
	_silent = silent


func set_events(events: Array) -> void:
	## The stream arrives in tick order; playback normally only walks forward.
	_events = events
	_cursor = 0
	_last_tick = -1.0


func update_to_tick(tick: float) -> void:
	# Seeking backwards is not something the offline renderer ever does, but
	# the interactive viewer restarts races - and an event cursor that only
	# counts up would silently show nothing for the whole of the second run.
	if tick < _last_tick:
		_rewind()
	_last_tick = tick
	_spawn_due(tick)
	_age(tick)


# --- what the racers read back --------------------------------------------

func squash_for(racer_id: int, tick: float) -> Dictionary:
	## How hard this racer is currently reacting to being hit, and where from.
	##
	## Returns the strongest live impact rather than summing them: two hits in
	## the same tenth of a second are one moment, and adding them would fold a
	## racer flat.
	var best := {"amount": 0.0, "at": Vector3.ZERO}
	if racer_id < 0 or racer_id >= _squashes.size():
		return best
	for record in _squashes[racer_id].get("hits", []):
		var progress := (tick - float(record["start"])) / float(record["ticks"])
		if progress < 0.0 or progress >= 1.0:
			continue
		# Compress hard, release with a small overshoot, settle. A linear
		# release reads as the racer deflating.
		var shape := sin(progress * PI) * (1.0 - progress * 0.35)
		var amount := float(record["strength"]) * shape
		if amount > float(best["amount"]):
			best = {"amount": amount, "at": record["at"]}
	return best


func speed_boost_for(racer_id: int, tick: float) -> float:
	## Whether this racer has just been launched, and how recently.
	if racer_id < 0 or racer_id >= _boosts.size():
		return 0.0
	var best := 0.0
	for record in _boosts[racer_id].get("kicks", []):
		var progress := (tick - float(record["start"])) / float(record["ticks"])
		if progress < 0.0 or progress >= 1.0:
			continue
		best = maxf(best, pow(1.0 - progress, 1.4))
	return best


func pad_pulse_for(piece_id: int, tick: float) -> float:
	## How brightly one jump pad is currently lit, from 0 to 1.
	##
	## A pad is a piece of course, so it is the course that draws it - this
	## only says which one went off and how long ago. Read back rather than
	## pushed, for the same reason the squash is: the thing that owns the
	## material should be the thing that writes to it.
	var records: Array = _pad_pulses.get(piece_id, [])
	var best := 0.0
	for record in records:
		var progress := (tick - float(record["start"])) / float(record["ticks"])
		if progress < 0.0 or progress >= 1.0:
			continue
		# A hard flash that falls away fast: a pad fires, it does not glow.
		best = maxf(best, pow(1.0 - progress, 2.2))
	return best


func camera_shake(tick: float) -> Vector3:
	## A decaying oscillation of replay time. Returned rather than applied,
	## because the race camera moves every frame and something that wrote to
	## it directly would be fighting the camera track.
	var offset := Vector3.ZERO
	for shake in _shakes:
		var age := (tick - float(shake["start"])) / _physics_hz
		if age < 0.0 or age >= SHAKE_SECONDS:
			continue
		var decay := 1.0 - age / SHAKE_SECONDS
		var amount := float(shake["amount"]) * decay * decay
		offset.x += sin(age * SHAKE_FREQUENCY) * amount
		offset.y += cos(age * SHAKE_FREQUENCY * SHAKE_CROSS_RATE) * amount \
			* SHAKE_VERTICAL_RATIO
	return offset


func live_effect_count() -> int:
	return _effects.size()


# --- spawning -------------------------------------------------------------

func _rewind() -> void:
	_cursor = 0
	for effect in _effects:
		(effect["node"] as Node).queue_free()
	_effects.clear()
	_shakes.clear()
	_squashes.clear()
	_boosts.clear()
	_pad_pulses.clear()


func _ensure_records() -> void:
	while _squashes.size() < _colors.size():
		_squashes.append({"hits": []})
	while _boosts.size() < _colors.size():
		_boosts.append({"kicks": []})


func _spawn_due(tick: float) -> void:
	_ensure_records()
	while _cursor < _events.size():
		var event: Dictionary = _events[_cursor]
		if float(event.get("tick", 0)) > tick:
			return
		_cursor += 1
		_spawn(event, tick)


func _spawn(event: Dictionary, tick: float) -> void:
	var kind := str(event.get("type", ""))
	if event.get("x") == null or event.get("y") == null:
		# Countdown, start and complete carry no position. They belong to the
		# overlay, not to the course.
		return

	var start := float(event.get("tick", 0))
	var at: Vector3 = _to_world.call(
		float(event.get("x", 0.0)), float(event.get("y", 0.0)), RING_HEIGHT)
	var color := _color_for(event.get("racer_id"))

	match kind:
		EVENT_COLLISION:
			_spawn_impact(event, at, color, start, tick)
		EVENT_JUMP:
			_spawn_jump(event, at, color, start, tick)
		EVENT_FINISH:
			_add_ring(at, color, start, tick, FINISH_SECONDS, FINISH_RING,
				FINISH_RING_ALPHA)
		EVENT_WINNER:
			_add_ring(at, color, start, tick, WINNER_SECONDS, WINNER_RING, 1.0)
			_add_flash(at, color, start, tick, WINNER_SECONDS, WINNER_FLASH)
			_add_shake(start, WINNER_SHAKE)
		EVENT_RETIRED:
			# A retired racer is taken out of the world, and a ball that
			# simply vanished would read as a bug rather than as a rescue
			# that failed.
			_add_ring(at, color, start, tick, RETIRE_SECONDS, RETIRE_RING, 0.7)
		EVENT_RECOVERY:
			_add_ring(at, color, start, tick, RETIRE_SECONDS, RETIRE_RING * 0.7,
				0.45)


func _spawn_impact(event: Dictionary, at: Vector3, color: Color, start: float,
		tick: float) -> void:
	var strength := _impact_strength(event)
	_add_ring(at, color, start, tick, IMPACT_SECONDS,
		lerpf(IMPACT_RING.x, IMPACT_RING.y, strength), IMPACT_RING_ALPHA)
	_add_flash(at, color, start, tick, IMPACT_SECONDS,
		lerpf(IMPACT_FLASH.x, IMPACT_FLASH.y, strength))
	_add_shake(start, strength)

	# Both racers react, not just the one the event is filed under. `detail`
	# carries the other one's id, which is the only place that pairing exists.
	_add_squash(event.get("racer_id"), at, start, strength)
	_add_squash(_other_racer(event), at, start, strength)


func _spawn_jump(event: Dictionary, at: Vector3, color: Color, start: float,
		tick: float) -> void:
	## A pad firing. Bright, brief, and a boost the trail picks up.
	##
	## Every jump in a measured race carries almost the same impulse - 283 to
	## 317 across three races - so this deliberately does not scale on
	## magnitude. A pad either fired or it did not.
	_add_ring(at, NEUTRAL_COLOR.lerp(color, 0.35), start, tick, JUMP_SECONDS,
		JUMP_RING, JUMP_RING_ALPHA)
	_add_flash(at, color, start, tick, JUMP_SECONDS, JUMP_FLASH)
	_add_boost(event.get("racer_id"), start)
	# `detail` carries the piece id of the pad that fired. It is the only
	# place that pairing exists, and without it the course would have to
	# guess which of its pads a launch came from.
	_add_pad_pulse(event.get("detail"), start)


# --- effect construction --------------------------------------------------

func _add_ring(at: Vector3, color: Color, start: float, now: float,
		seconds: float, radius: float, alpha: float) -> void:
	var node := _make_node(_ring_mesh, color, alpha)
	if node == null:
		return
	node.position = at
	_register(node, start, now, seconds, {
		"from": radius * RING_START_FRACTION,
		"to": radius,
		"alpha": alpha,
	})


func _add_flash(at: Vector3, color: Color, start: float, now: float,
		seconds: float, radius: float) -> void:
	var hot := color.lightened(FLASH_LIGHTEN) * FLASH_OVERDRIVE
	var node := _make_node(_flash_mesh, hot, FLASH_ALPHA)
	if node == null:
		return
	node.position = at + Vector3(0.0, FLASH_HEIGHT, 0.0)
	_register(node, start, now, seconds * FLASH_LIFE_FRACTION, {
		"from": radius,
		"to": radius * (1.0 + FLASH_GROWTH),
		"alpha": FLASH_ALPHA,
	})


func _make_node(mesh: Mesh, color: Color, alpha: float) -> MeshInstance3D:
	if _silent:
		return null
	var material := StandardMaterial3D.new()
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	material.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
	material.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_DISABLED
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
	# Shaped straight away, so a frame is never drawn at unit scale before
	# the first ageing pass reaches it.
	_shape(effect, now)


func _add_squash(raw: Variant, at: Vector3, start: float,
		strength: float) -> void:
	if raw == null or strength < SQUASH_MIN_STRENGTH:
		return
	var index := int(raw)
	if index < 0 or index >= _squashes.size():
		return
	_squashes[index]["hits"].append({
		"start": start,
		"ticks": maxf(1.0, SQUASH_SECONDS * _physics_hz),
		"strength": strength,
		"at": at,
	})


func _add_boost(raw: Variant, start: float) -> void:
	if raw == null:
		return
	var index := int(raw)
	if index < 0 or index >= _boosts.size():
		return
	_boosts[index]["kicks"].append({
		"start": start,
		"ticks": maxf(1.0, BOOST_SECONDS * _physics_hz),
	})


func _add_pad_pulse(raw: Variant, start: float) -> void:
	if raw == null:
		return
	var text := str(raw)
	if not text.is_valid_int():
		return
	var piece_id := int(text)
	if not _pad_pulses.has(piece_id):
		_pad_pulses[piece_id] = []
	_pad_pulses[piece_id].append({
		"start": start,
		"ticks": maxf(1.0, PAD_PULSE_SECONDS * _physics_hz),
	})


func _add_shake(start: float, strength: float) -> void:
	if strength <= SHAKE_MIN_STRENGTH:
		return
	var scaled := (strength - SHAKE_MIN_STRENGTH) / (1.0 - SHAKE_MIN_STRENGTH)
	_shakes.append({"start": start, "amount": scaled * SHAKE_MAX_UNITS})


# --- ageing and cleanup ---------------------------------------------------

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

	# Reaction records are plain data and cheap to hold, but a long race would
	# otherwise accumulate every collision it ever had.
	_forget_spent(tick)


func _forget_spent(tick: float) -> void:
	for record in _squashes:
		record["hits"] = _live(record["hits"], tick)
	for record in _boosts:
		record["kicks"] = _live(record["kicks"], tick)
	for piece_id in _pad_pulses.keys():
		_pad_pulses[piece_id] = _live(_pad_pulses[piece_id], tick)
	var shakes: Array[Dictionary] = []
	for shake in _shakes:
		if (tick - float(shake["start"])) / _physics_hz < SHAKE_SECONDS:
			shakes.append(shake)
	_shakes = shakes


func _live(records: Array, tick: float) -> Array:
	var survivors: Array = []
	for record in records:
		if tick - float(record["start"]) < float(record["ticks"]):
			survivors.append(record)
	return survivors


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


# --- event helpers --------------------------------------------------------

func _impact_strength(event: Dictionary) -> float:
	## Where this collision sits between "the softest the simulation bothers
	## to record" and "as hard as it gets".
	var value: Variant = event.get("value")
	if value == null:
		return 0.0
	return clampf(
		(float(value) - IMPACT_FLOOR) / (IMPACT_FULL - IMPACT_FLOOR), 0.0, 1.0)


func _other_racer(event: Dictionary) -> Variant:
	## A collision names one racer in `racer_id` and the other in `detail`.
	var detail: Variant = event.get("detail")
	if detail == null:
		return null
	var text := str(detail)
	return int(text) if text.is_valid_int() else null


func _color_for(raw: Variant) -> Color:
	if raw == null:
		return NEUTRAL_COLOR
	var index := int(raw)
	if index < 0 or index >= _colors.size():
		return NEUTRAL_COLOR
	return _colors[index]
