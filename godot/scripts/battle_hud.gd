extends CanvasLayer

## The overlay: competitor cards, timer, matchup intro and the result panel.
##
## Everything shown here comes from the replay - names, colours, powers,
## health, the winner - and every animation is timed in *replay ticks*, never
## wall-clock seconds, so the overlay stays in step with the battle underneath
## it however fast frames happen to arrive.
##
## The 9:16 frame is treated as three bands: a header holding the timer and the
## two cards, the arena itself, and a lower band that is deliberate empty space
## during the battle and becomes the result panel at the end.

const HUD_WIDTH := 1080.0
const HUD_HEIGHT := 1920.0

# --- header ---------------------------------------------------------------

const TIMER_RECT := Rect2(425.0, 24.0, 230.0, 80.0)
const TIMER_FONT := 58

const CARD_SIZE := Vector2(478.0, 168.0)
const CARD_TOP := 124.0
const CARD_LEFT_X := 42.0
const CARD_GAP := 20.0

const CARD_PAD := 22.0
const NAME_FONT := 38
const PILL_SIZE := Vector2(236.0, 48.0)
const PILL_FONT := 30
const BAR_RECT := Rect2(22.0, 82.0, 434.0, 24.0)
const HP_FONT := 32

# --- palette --------------------------------------------------------------

# One restrained slate accent for every piece of chrome. Competitor colour is
# reserved for the things that are actually a competitor.
const PANEL_FILL := Color(0.055, 0.062, 0.085, 0.80)
const PANEL_BORDER := Color(0.30, 0.33, 0.42, 0.75)
const TRACK_FILL := Color(0.10, 0.11, 0.145, 0.95)
const TEXT_COLOR := Color(0.90, 0.92, 0.96)
const MUTED_COLOR := Color(0.62, 0.65, 0.73)
const POWER_ACTIVE_COLOR := Color(1.0, 0.93, 0.62)

# --- timing, all in simulated seconds -------------------------------------

# The matchup card is gone well before the opening warmup ends, so it never
# overlaps the first power of the battle.
const INTRO_HOLD_SECONDS := 0.72
const INTRO_FADE_SECONDS := 0.28
# Long enough for the elimination ring to open and fade before the result
# panel covers that corner of the arena.
const RESULT_DELAY_SECONDS := 0.55
const RESULT_FADE_SECONDS := 0.45
# A hit brightens the victim's bar just long enough to be felt, not read.
const HIT_RESPONSE_SECONDS := 0.22

var _fighter_meta: Array = []
var _physics_hz := 120.0
var _limit_seconds := 35.0
var _final_tick := 0.0

var _root: Control
var _timer_label: Label
var _cards: Array[Panel] = []
var _card_styles: Array[StyleBoxFlat] = []
var _pills: Array[Panel] = []
var _pill_styles: Array[StyleBoxFlat] = []
var _pill_labels: Array[Label] = []
var _bar_fills: Array[ColorRect] = []
var _hp_labels: Array[Label] = []
var _colors: Array[Color] = []

var _intro: Control
var _result: Control

var _events: Array = []
var _cursor := 0
var _last_hit_tick: Array[float] = []


func configure(replay: Dictionary) -> void:
	_fighter_meta = replay.get("fighters", [])
	_physics_hz = maxf(1.0, float(replay.get("physics_hz", 120.0)))
	_limit_seconds = float(replay.get("limit_seconds", 35.0))
	var frames: Array = replay.get("frames", [])
	if not frames.is_empty():
		_final_tick = float((frames[-1] as Dictionary).get("tick", 0))

	for meta in _fighter_meta:
		_colors.append(_color_of(meta))
		_last_hit_tick.append(-1.0e9)

	_root = Control.new()
	_root.name = "HudRoot"
	_root.set_anchors_preset(Control.PRESET_FULL_RECT)
	_root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_root)

	_build_timer()
	_build_cards()
	_build_intro()
	_build_result(replay.get("result", {}))


func set_events(events: Array) -> void:
	_events = events
	_cursor = 0


func show_error(message: String) -> void:
	_root = Control.new()
	_root.set_anchors_preset(Control.PRESET_FULL_RECT)
	add_child(_root)
	_label(_root, message, 40, Color(1.0, 0.5, 0.5),
		Rect2(60.0, 820.0, HUD_WIDTH - 120.0, 320.0), HORIZONTAL_ALIGNMENT_CENTER)


# --- per-frame ------------------------------------------------------------

func update_hud(tick: float, healths: Array, powered: Array) -> void:
	_consume_events(tick)
	for i in _cards.size():
		var health: float = healths[i] if i < healths.size() else 0.0
		var is_powered: bool = powered[i] if i < powered.size() else false
		_update_card(i, tick, health, is_powered)
	_update_timer(tick)
	_update_intro(tick)
	_update_result(tick)


func _consume_events(tick: float) -> void:
	## Only hits are of interest here; the world-space effects handle the rest.
	while _cursor < _events.size():
		var event: Dictionary = _events[_cursor]
		if float(event.get("tick", 0)) > tick:
			return
		_cursor += 1
		if str(event.get("type", "")) != "hit":
			continue
		var target: Variant = event.get("target_id")
		if target != null and int(target) < _last_hit_tick.size():
			_last_hit_tick[int(target)] = float(event.get("tick", 0))


func _update_card(index: int, tick: float, health: float, powered: bool) -> void:
	var meta: Dictionary = _fighter_meta[index]
	var max_health := maxf(1.0, float(meta.get("max_health", 100.0)))
	var fraction := clampf(health / max_health, 0.0, 1.0)
	var color := _colors[index]

	# A hit lifts the bar and the card edge briefly. Replay time, so it lands
	# on the same frame of the battle every run.
	var since := (tick - _last_hit_tick[index]) / _physics_hz
	var response := 0.0
	if since >= 0.0 and since < HIT_RESPONSE_SECONDS:
		response = 1.0 - since / HIT_RESPONSE_SECONDS

	_bar_fills[index].size = Vector2(BAR_RECT.size.x * fraction, BAR_RECT.size.y)
	_bar_fills[index].color = color.lightened(0.55 * response)
	_hp_labels[index].text = "%d HP" % int(round(health))

	var edge: StyleBoxFlat = _card_styles[index]
	edge.border_color = PANEL_BORDER.lerp(color, 0.35 + 0.55 * response)
	edge.border_width_left = 5 if response > 0.0 else 4

	var pill: StyleBoxFlat = _pill_styles[index]
	if powered:
		pill.bg_color = Color(color.r, color.g, color.b, 0.30)
		pill.border_color = POWER_ACTIVE_COLOR
		_pill_labels[index].label_settings.font_color = POWER_ACTIVE_COLOR
		_pill_labels[index].text = "%s  ACTIVE" % str(meta.get("power", "")).to_upper()
	else:
		pill.bg_color = Color(0.10, 0.11, 0.15, 0.85)
		pill.border_color = PANEL_BORDER
		_pill_labels[index].label_settings.font_color = MUTED_COLOR
		_pill_labels[index].text = str(meta.get("power", "")).to_upper()


func _update_timer(tick: float) -> void:
	var remaining := maxf(0.0, _limit_seconds - minf(tick, _final_tick) / _physics_hz)
	_timer_label.text = "%.1f" % remaining


func _update_intro(tick: float) -> void:
	var seconds := tick / _physics_hz
	var alpha := 1.0
	if seconds > INTRO_HOLD_SECONDS:
		alpha = 1.0 - (seconds - INTRO_HOLD_SECONDS) / INTRO_FADE_SECONDS
	_intro.modulate.a = clampf(alpha, 0.0, 1.0)
	_intro.visible = _intro.modulate.a > 0.002


func _update_result(tick: float) -> void:
	var age := (tick - _final_tick) / _physics_hz - RESULT_DELAY_SECONDS
	var alpha := clampf(age / RESULT_FADE_SECONDS, 0.0, 1.0)
	_result.modulate.a = alpha
	_result.visible = alpha > 0.002
	# Rises the last few pixels as it fades in, so it arrives rather than
	# simply appearing.
	_result.position.y = (1.0 - alpha) * 26.0


# --- construction ---------------------------------------------------------

func _build_timer() -> void:
	var panel := _panel(_root, TIMER_RECT, PANEL_FILL, PANEL_BORDER, 2, 10)
	_timer_label = _label(panel, "0.0", TIMER_FONT, TEXT_COLOR,
		Rect2(0.0, 0.0, TIMER_RECT.size.x, TIMER_RECT.size.y),
		HORIZONTAL_ALIGNMENT_CENTER)


func _build_cards() -> void:
	for i in _fighter_meta.size():
		var meta: Dictionary = _fighter_meta[i]
		var color := _colors[i]
		var x := CARD_LEFT_X + float(i) * (CARD_SIZE.x + CARD_GAP)
		var card := _panel(_root, Rect2(x, CARD_TOP, CARD_SIZE.x, CARD_SIZE.y),
			PANEL_FILL, PANEL_BORDER.lerp(color, 0.35), 2, 12)
		# A thicker stripe on the leading edge in the fighter's colour: the
		# card is identifiable before a single word has been read.
		var style: StyleBoxFlat = card.get_theme_stylebox("panel")
		style.border_width_left = 4
		_cards.append(card)
		_card_styles.append(style)

		_label(card, str(meta.get("name", "?")), NAME_FONT, color,
			Rect2(CARD_PAD, 14.0, 200.0, 50.0), HORIZONTAL_ALIGNMENT_LEFT)

		var pill_x := CARD_SIZE.x - CARD_PAD - PILL_SIZE.x
		var pill := _panel(card, Rect2(pill_x, 16.0, PILL_SIZE.x, PILL_SIZE.y),
			Color(0.10, 0.11, 0.15, 0.85), PANEL_BORDER, 2, 24)
		_pills.append(pill)
		_pill_styles.append(pill.get_theme_stylebox("panel"))
		_pill_labels.append(_label(pill, "", PILL_FONT, MUTED_COLOR,
			Rect2(0.0, 0.0, PILL_SIZE.x, PILL_SIZE.y), HORIZONTAL_ALIGNMENT_CENTER))

		var track := ColorRect.new()
		track.color = TRACK_FILL
		track.position = BAR_RECT.position
		track.size = BAR_RECT.size
		card.add_child(track)

		var fill := ColorRect.new()
		fill.color = color
		fill.position = BAR_RECT.position
		fill.size = BAR_RECT.size
		card.add_child(fill)
		_bar_fills.append(fill)

		_hp_labels.append(_label(card, "", HP_FONT, TEXT_COLOR,
			Rect2(CARD_PAD, 114.0, CARD_SIZE.x - CARD_PAD * 2.0, 42.0),
			HORIZONTAL_ALIGNMENT_RIGHT))


func _build_intro() -> void:
	## Sits over the arena, not over the cards, and is gone before the first
	## power fires.
	_intro = Control.new()
	_intro.name = "Intro"
	_intro.set_anchors_preset(Control.PRESET_FULL_RECT)
	_intro.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_root.add_child(_intro)

	var rows := [560.0, 1080.0]
	for i in _fighter_meta.size():
		var meta: Dictionary = _fighter_meta[i]
		var y: float = rows[i] if i < rows.size() else 560.0 + 520.0 * i
		_label(_intro, str(meta.get("power", "")).to_upper(), 128, _colors[i],
			Rect2(0.0, y, HUD_WIDTH, 150.0), HORIZONTAL_ALIGNMENT_CENTER)
		_label(_intro, str(meta.get("name", "?")), 46, TEXT_COLOR,
			Rect2(0.0, y + 148.0, HUD_WIDTH, 60.0), HORIZONTAL_ALIGNMENT_CENTER)

	_label(_intro, "VS", 62, MUTED_COLOR,
		Rect2(0.0, 880.0, HUD_WIDTH, 90.0), HORIZONTAL_ALIGNMENT_CENTER)


func _build_result(result: Dictionary) -> void:
	## Lives in the lower band, which is otherwise deliberate empty space.
	_result = Control.new()
	_result.name = "Result"
	_result.set_anchors_preset(Control.PRESET_FULL_RECT)
	_result.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_root.add_child(_result)

	var winner := _winner_meta(result)
	var accent := TEXT_COLOR if winner.is_empty() else _color_of(winner)
	var panel := _panel(_result, Rect2(112.0, 1648.0, 856.0, 196.0),
		Color(0.045, 0.05, 0.07, 0.94), accent, 2, 18)
	# A heavy rule in the winner's colour along the top: the result is read
	# before a word of it has been.
	var style: StyleBoxFlat = panel.get_theme_stylebox("panel")
	style.border_width_top = 7

	if winner.is_empty():
		_label(panel, "DRAW", 92, TEXT_COLOR,
			Rect2(0.0, 44.0, 856.0, 110.0), HORIZONTAL_ALIGNMENT_CENTER)
		return

	_label(panel, "%s WINS" % str(winner.get("name", "?")).to_upper(), 86, accent,
		Rect2(0.0, 28.0, 856.0, 104.0), HORIZONTAL_ALIGNMENT_CENTER)
	_label(panel, str(winner.get("power", "")).to_upper(), 42,
		TEXT_COLOR.darkened(0.18),
		Rect2(0.0, 126.0, 856.0, 56.0), HORIZONTAL_ALIGNMENT_CENTER)


func _winner_meta(result: Dictionary) -> Dictionary:
	var winner_id: Variant = result.get("winner_id")
	if bool(result.get("is_draw", false)) or winner_id == null:
		return {}
	for meta in _fighter_meta:
		if int((meta as Dictionary).get("id", -1)) == int(winner_id):
			return meta
	return {}


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
