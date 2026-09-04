extends CanvasLayer

## The race overlay: the clock, the top three, the countdown and the result.
##
## The counterpart of `battle_hud.gd`, and it keeps the same rule: everything
## shown here comes out of the replay, and every animation is timed in replay
## ticks rather than wall-clock seconds, so the overlay stays in step with the
## race underneath it however fast frames happen to arrive.
##
## It is deliberately smaller than the battle overlay. A duel has two
## competitors with health bars and powers to explain; a race has ten
## identical balls, and what a viewer needs is who is winning and how long it
## has been going. Anything more would be covering the course, which on a
## portrait frame is the whole picture.

const HUD_WIDTH := 1080.0
const HUD_HEIGHT := 1920.0

const TIMER_RECT := Rect2(425.0, 24.0, 230.0, 76.0)
const TIMER_FONT := 54

const STANDINGS_TOP := 116.0
const STANDINGS_LEFT := 42.0
const STANDINGS_SIZE := Vector2(380.0, 54.0)
const STANDINGS_GAP := 8.0
const STANDINGS_FONT := 36
const STANDINGS_SHOWN := 3

const COUNTDOWN_RECT := Rect2(0.0, 700.0, HUD_WIDTH, 320.0)
const COUNTDOWN_FONT := 260

const RESULT_RECT := Rect2(112.0, 1560.0, 856.0, 190.0)
const RESULT_FONT := 78
const RESULT_SUB_FONT := 40

const PANEL_FILL := Color(0.055, 0.062, 0.085, 0.80)
const PANEL_BORDER := Color(0.30, 0.33, 0.42, 0.75)
const TEXT_COLOR := Color(0.90, 0.92, 0.96)
const MUTED_COLOR := Color(0.62, 0.65, 0.73)

# The result panel waits for the last finisher to settle and then fades in.
# The same figures the battle overlay uses, so a race and a duel end with the
# same rhythm and the production post-roll fits both.
const RESULT_DELAY_SECONDS := 0.55
const RESULT_FADE_SECONDS := 0.45

var _racer_meta: Array = []
var _colors: Array[Color] = []
var _names: Array[String] = []
var _physics_hz := 120.0
var _final_tick := 0.0

var _root: Control
var _timer_label: Label
var _standing_panels: Array[Panel] = []
var _standing_styles: Array[StyleBoxFlat] = []
var _standing_labels: Array[Label] = []
var _countdown: Label
var _result: Control


func configure(replay: Dictionary) -> void:
	_racer_meta = replay.get("racers", [])
	_physics_hz = maxf(1.0, float(replay.get("physics_hz", 120.0)))
	var frames: Array = replay.get("frames", [])
	if not frames.is_empty():
		_final_tick = float((frames[-1] as Dictionary).get("tick", 0))

	for meta in _racer_meta:
		_colors.append(_color_of(meta))
		_names.append(str((meta as Dictionary).get("name", "?")))

	_root = Control.new()
	_root.name = "HudRoot"
	_root.set_anchors_preset(Control.PRESET_FULL_RECT)
	_root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_root)

	_build_timer()
	_build_standings()
	_build_countdown()
	_build_result(replay.get("result", {}))


func show_error(message: String) -> void:
	_root = Control.new()
	_root.set_anchors_preset(Control.PRESET_FULL_RECT)
	add_child(_root)
	_label(_root, message, 40, Color(1.0, 0.5, 0.5),
		Rect2(60.0, 820.0, HUD_WIDTH - 120.0, 320.0), HORIZONTAL_ALIGNMENT_CENTER)


# --- per-frame ------------------------------------------------------------

func update_hud(frame: Dictionary, tick: float) -> void:
	var race_time := float(frame.get("race_time", 0.0))
	_update_timer(race_time)
	_update_countdown(race_time)
	_update_standings(frame.get("racers", []))
	_update_result(tick)


func _update_timer(race_time: float) -> void:
	# Held at zero through the countdown: a clock that counted up from minus
	# three would be reporting the wait rather than the race.
	_timer_label.text = "%.1f" % maxf(0.0, race_time)


func _update_countdown(race_time: float) -> void:
	if race_time >= 0.0:
		_countdown.visible = false
		return
	_countdown.visible = true
	_countdown.text = str(int(ceil(-race_time - 1.0e-9)))


func _update_standings(racers: Array) -> void:
	## The top three by the rank the simulation assigned.
	##
	## Rank is read, never recomputed. Ranking a race is the one piece of
	## logic that has to follow the course rather than the canvas - on a
	## branching course two racers at the same height are not level - and it
	## belongs in one place, which is Python.
	var order: Array = []
	for raw in racers:
		var racer: Dictionary = raw
		if bool(racer.get("retired", false)):
			continue
		order.append(racer)
	order.sort_custom(func(a, b): return int(a.get("rank", 99)) < int(b.get("rank", 99)))

	for slot in _standing_panels.size():
		if slot >= order.size():
			_standing_panels[slot].visible = false
			continue
		var racer: Dictionary = order[slot]
		var id := int(racer.get("id", -1))
		if id < 0 or id >= _names.size():
			_standing_panels[slot].visible = false
			continue
		_standing_panels[slot].visible = true
		_standing_styles[slot].border_color = _colors[id]
		_standing_labels[slot].text = "%d  %s" % [slot + 1, _names[id]]
		_standing_labels[slot].label_settings.font_color = _colors[id]


func _update_result(tick: float) -> void:
	if _result == null:
		return
	var seconds := (tick - _final_tick) / _physics_hz - RESULT_DELAY_SECONDS
	if seconds <= 0.0:
		_result.visible = false
		return
	_result.visible = true
	_result.modulate.a = clampf(seconds / RESULT_FADE_SECONDS, 0.0, 1.0)


# --- builders -------------------------------------------------------------

func _build_timer() -> void:
	var panel := _panel(_root, TIMER_RECT, PANEL_FILL, PANEL_BORDER, 2, 10)
	_timer_label = _label(panel, "0.0", TIMER_FONT, TEXT_COLOR,
		Rect2(0.0, 0.0, TIMER_RECT.size.x, TIMER_RECT.size.y),
		HORIZONTAL_ALIGNMENT_CENTER)


func _build_standings() -> void:
	for slot in STANDINGS_SHOWN:
		var top := STANDINGS_TOP + float(slot) * (STANDINGS_SIZE.y + STANDINGS_GAP)
		var style := StyleBoxFlat.new()
		style.bg_color = PANEL_FILL
		style.border_color = PANEL_BORDER
		style.set_border_width_all(0)
		style.border_width_left = 6
		style.set_corner_radius_all(8)

		var panel := Panel.new()
		panel.add_theme_stylebox_override("panel", style)
		panel.position = Vector2(STANDINGS_LEFT, top)
		panel.size = STANDINGS_SIZE
		panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
		_root.add_child(panel)

		var label := _label(panel, "", STANDINGS_FONT, TEXT_COLOR,
			Rect2(20.0, 0.0, STANDINGS_SIZE.x - 32.0, STANDINGS_SIZE.y),
			HORIZONTAL_ALIGNMENT_LEFT)

		_standing_panels.append(panel)
		_standing_styles.append(style)
		_standing_labels.append(label)


func _build_countdown() -> void:
	_countdown = _label(_root, "", COUNTDOWN_FONT, TEXT_COLOR, COUNTDOWN_RECT,
		HORIZONTAL_ALIGNMENT_CENTER)
	_countdown.visible = false


func _build_result(result: Dictionary) -> void:
	var winner_id: Variant = result.get("winner_id")
	if winner_id == null:
		return
	var id := int(winner_id)
	var accent := _colors[id] if id >= 0 and id < _colors.size() else TEXT_COLOR
	var name := _names[id] if id >= 0 and id < _names.size() else "?"

	_result = Control.new()
	_result.name = "Result"
	_result.position = RESULT_RECT.position
	_result.size = RESULT_RECT.size
	_result.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_result.visible = false
	_root.add_child(_result)

	_panel(_result, Rect2(0.0, 0.0, RESULT_RECT.size.x, RESULT_RECT.size.y),
		PANEL_FILL, accent.darkened(0.25), 3, 16)
	_label(_result, "%s WINS" % name.to_upper(), RESULT_FONT, accent,
		Rect2(0.0, 22.0, RESULT_RECT.size.x, 96.0), HORIZONTAL_ALIGNMENT_CENTER)

	var winner_time: Variant = result.get("winner_time")
	var subtitle := "" if winner_time == null else "%.2fs" % float(winner_time)
	_label(_result, subtitle, RESULT_SUB_FONT, MUTED_COLOR,
		Rect2(0.0, 118.0, RESULT_RECT.size.x, 52.0), HORIZONTAL_ALIGNMENT_CENTER)


# --- small builders -------------------------------------------------------

func _panel(parent: Control, rect: Rect2, fill: Color, border: Color,
		border_width: int, radius: int) -> Panel:
	var style := StyleBoxFlat.new()
	style.bg_color = fill
	style.border_color = border
	style.set_border_width_all(border_width)
	style.set_corner_radius_all(radius)

	var panel := Panel.new()
	panel.add_theme_stylebox_override("panel", style)
	panel.position = rect.position
	panel.size = rect.size
	panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
	parent.add_child(panel)
	return panel


func _label(parent: Control, text: String, font_size: int, color: Color,
		rect: Rect2, alignment: int) -> Label:
	var label := Label.new()
	label.text = text
	label.position = rect.position
	label.size = rect.size
	label.horizontal_alignment = alignment
	label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	label.mouse_filter = Control.MOUSE_FILTER_IGNORE

	# Built-in Godot font only - no external font assets.
	var settings := LabelSettings.new()
	settings.font_size = font_size
	settings.font_color = color
	settings.outline_size = 6
	settings.outline_color = Color(0.0, 0.0, 0.0, 0.7)
	label.label_settings = settings

	parent.add_child(label)
	return label


func _color_of(meta: Dictionary) -> Color:
	var raw: Variant = meta.get("color", [])
	if raw is Array and (raw as Array).size() >= 3:
		var rgb: Array = raw
		return Color8(int(rgb[0]), int(rgb[1]), int(rgb[2]))
	return Color.WHITE
