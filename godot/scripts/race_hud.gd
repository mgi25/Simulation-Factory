extends CanvasLayer

## The race overlay: the clock, the top three, the countdown and the result.
##
## The counterpart of `battle_hud.gd`, and it keeps that file's rule: everything
## shown here comes out of the replay, and every animation is timed in replay
## ticks rather than wall-clock seconds, so the overlay stays in step with the
## race underneath it however fast frames happen to arrive. A Tween or an
## AnimationPlayer would advance on engine frame time and two renders of one
## replay would stop matching, so there are none.
##
## ## Where things are allowed to be
##
## A Short is not watched full-frame. YouTube draws its own chrome over the
## video: a status and navigation band across the top, a channel/title/sound
## block across the bottom, and a column of action buttons up the right. Google
## publishes the reserved regions as percentages - top 10%, bottom 25%, right
## 10% - which on 1080x1920 is 192px, 480px and 108px. Widening the rail to
## 156px for safety leaves the rectangle every important thing here sits in:
##
##     SAFE = x 48..924, y 192..1440
##
## The V0.2 overlay predates that measurement and lost badly to it. Its clock
## sat at y 24..100 - entirely inside the top band. Its first standings row sat
## at y 116..170, so on a phone the race leader was the one competitor a viewer
## could not see. Worst of all, the winner panel sat at y 1560..1750, which is
## underneath the channel and title row: the payoff frame of the whole Short
## was the frame the platform covered.
##
## ## And how big
##
## A 1080-wide frame is watched at roughly 400 logical pixels on a phone, so
## source pixels divide by about 2.7 to reach what the eye gets. Sixteen
## device-independent pixels is the usual comfortable floor for text, which is
## 44 source pixels here; anything meant to be read in a glance wants 54. The
## V0.2 standings ran at 36 - about 13dp, below the floor, and softened further
## by YouTube's re-encode.
##
## Anything moved here has to move in `tools/verify_race_render.py` too. That
## tool skips racers hidden behind the overlay, and a rect it does not know
## about becomes a racer it reports as missing.

const HUD_WIDTH := 1080.0
const HUD_HEIGHT := 1920.0

# --- the safe rectangle ---------------------------------------------------

const SAFE_LEFT := 48.0
const SAFE_TOP := 192.0
const SAFE_RIGHT := 924.0
const SAFE_BOTTOM := 1440.0

# --- the top-left column --------------------------------------------------
#
# A column rather than a band across the frame, because under the production
# camera the top of the picture is the *distant* course near the vanishing
# point - upcoming track with almost no racers on it - while a full-width band
# would still cut across the one part of the frame that is always busy.
#
# Every position is a whole number. Godot's glyph rasteriser is deterministic
# for a fixed size and position, and a fractional y can round differently
# between two runs and cost the pipeline its byte-identical renders.
const CLOCK_RECT := Rect2(48.0, 200.0, 220.0, 68.0)
const CLOCK_FONT := 52

const STANDINGS_LEFT := 48.0
const STANDINGS_TOP := 284.0
const STANDINGS_SIZE := Vector2(300.0, 56.0)
const STANDINGS_GAP := 8.0
const STANDINGS_FONT := 44
const STANDINGS_SHOWN := 3

# --- the countdown --------------------------------------------------------
#
# Centred on 540 rather than on the safe rectangle's optical centre of 486:
# the numeral is on screen for three seconds, it sits well above the action
# rail, and the course is symmetric about 540, so an off-centre digit would
# read as a mistake rather than as a margin.
const COUNTDOWN_RECT := Rect2(0.0, 646.0, HUD_WIDTH, 340.0)
const COUNTDOWN_FONT := 300

# --- the result -----------------------------------------------------------
#
# Optically centred: x 90..882 puts the middle at 486, which is the centre of
# the space a viewer can actually see once the action rail is accounted for.
# The bottom edge clears the safe floor by 24px.
const RESULT_RECT := Rect2(90.0, 1148.0, 792.0, 268.0)
const RESULT_FONT := 86
const RESULT_SUB_FONT := 48
const RESULT_RULE_HEIGHT := 8.0

# --- palette --------------------------------------------------------------
#
# Deliberately thin. The V0.2 panels were an 80%-opaque near-black over a
# near-black course, which reads as a hole cut in the frame. At 0.52 the track
# shows through and the text still carries, because the text has its own
# outline and shadow to separate it.
const PANEL_FILL := Color(0.045, 0.055, 0.075, 0.52)
const PANEL_BORDER := Color(0.30, 0.36, 0.46, 0.55)
const TEXT_COLOR := Color(0.93, 0.95, 0.99)
const MUTED_COLOR := Color(0.66, 0.72, 0.82)
const ACCENT_WIDTH := 6

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
var _clock_label: Label
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

	_build_clock()
	_build_standings()
	_build_countdown()
	_build_result(replay.get("result", {}))


func show_error(message: String) -> void:
	_root = Control.new()
	_root.set_anchors_preset(Control.PRESET_FULL_RECT)
	add_child(_root)
	_label(_root, message, 48, Color(1.0, 0.5, 0.5),
		Rect2(SAFE_LEFT, 820.0, SAFE_RIGHT - SAFE_LEFT, 320.0),
		HORIZONTAL_ALIGNMENT_CENTER)


# --- per-frame ------------------------------------------------------------

func update_hud(frame: Dictionary, tick: float) -> void:
	var race_time := float(frame.get("race_time", 0.0))
	_update_clock(race_time)
	_update_countdown(race_time)
	_update_standings(frame.get("racers", []))
	_update_result(tick)


func _update_clock(race_time: float) -> void:
	# Held at zero through the countdown: a clock counting up from minus three
	# would be reporting the wait rather than the race.
	_clock_label.text = "%.1f" % maxf(0.0, race_time)


func _update_countdown(race_time: float) -> void:
	if race_time >= 0.0:
		_countdown.visible = false
		return
	_countdown.visible = true
	_countdown.text = str(int(ceil(-race_time - 1.0e-9)))


func _update_standings(racers: Array) -> void:
	## The top three by the rank the simulation assigned.
	##
	## Rank is read, never recomputed. Ranking a race is the one piece of logic
	## that has to follow the course rather than the canvas - on a branching
	## course two racers at the same height are not level - and it belongs in
	## one place, which is Python.
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
		_standing_labels[slot].text = "%d   %s" % [slot + 1, _names[id]]
		_standing_labels[slot].label_settings.font_color = _colors[id].lightened(0.25)


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

func _build_clock() -> void:
	var panel := _panel(_root, CLOCK_RECT, PANEL_FILL, PANEL_BORDER, 0, 10)
	var style: StyleBoxFlat = panel.get_theme_stylebox("panel")
	style.border_width_left = ACCENT_WIDTH
	style.border_color = Color(0.30, 0.78, 0.95, 0.85)
	_clock_label = _label(panel, "0.0", CLOCK_FONT, TEXT_COLOR,
		Rect2(20.0, 0.0, CLOCK_RECT.size.x - 40.0, CLOCK_RECT.size.y),
		HORIZONTAL_ALIGNMENT_CENTER)


func _build_standings() -> void:
	for slot in STANDINGS_SHOWN:
		var top := STANDINGS_TOP + float(slot) * (STANDINGS_SIZE.y + STANDINGS_GAP)
		var rect := Rect2(STANDINGS_LEFT, top, STANDINGS_SIZE.x, STANDINGS_SIZE.y)
		var panel := _panel(_root, rect, PANEL_FILL, PANEL_BORDER, 0, 8)
		var style: StyleBoxFlat = panel.get_theme_stylebox("panel")
		# The competitor's colour, as a stripe rather than as a fill: it says
		# who the row is about without adding another coloured shape to a
		# frame whose colour belongs to the racers.
		style.border_width_left = ACCENT_WIDTH

		var label := _label(panel, "", STANDINGS_FONT, TEXT_COLOR,
			Rect2(22.0, 0.0, STANDINGS_SIZE.x - 34.0, STANDINGS_SIZE.y),
			HORIZONTAL_ALIGNMENT_LEFT)
		label.clip_text = true

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
	var winner_name := _names[id] if id >= 0 and id < _names.size() else "?"

	_result = Control.new()
	_result.name = "Result"
	_result.position = RESULT_RECT.position
	_result.size = RESULT_RECT.size
	_result.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_result.visible = false
	_root.add_child(_result)

	# A rule in the winner's colour instead of a filled card. The finish is
	# the shot; a solid panel across it would cover the thing it is announcing.
	var rule := ColorRect.new()
	rule.name = "Rule"
	rule.color = accent
	rule.position = Vector2.ZERO
	rule.size = Vector2(RESULT_RECT.size.x, RESULT_RULE_HEIGHT)
	rule.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_result.add_child(rule)

	var headline := _label(_result, "%s WINS" % winner_name.to_upper(),
		RESULT_FONT, accent.lightened(0.2),
		Rect2(0.0, 26.0, RESULT_RECT.size.x, 112.0), HORIZONTAL_ALIGNMENT_CENTER)
	# A longer name would run off the end silently - Label does not shrink.
	headline.clip_text = true

	var winner_time: Variant = result.get("winner_time")
	var subtitle := "" if winner_time == null else "%.2f s" % float(winner_time)
	_label(_result, subtitle, RESULT_SUB_FONT, MUTED_COLOR,
		Rect2(0.0, 152.0, RESULT_RECT.size.x, 70.0), HORIZONTAL_ALIGNMENT_CENTER)


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
	# Scaled rather than fixed. A flat six pixels is 17% of the em at font 36 -
	# enough to close the counters of a, e and o once YouTube has re-encoded
	# the frame - and 2% at font 300, where it may as well not be there.
	settings.outline_size = int(clampf(round(float(font_size) / 9.0), 4.0, 18.0))
	settings.outline_color = Color(0.0, 0.0, 0.0, 0.85)
	# A soft drop shadow underneath. Over a dark course an outline alone only
	# separates the glyph from itself; a shadow separates it from the picture.
	settings.shadow_size = maxi(4, font_size / 8)
	settings.shadow_color = Color(0.0, 0.0, 0.0, 0.55)
	settings.shadow_offset = Vector2(0.0, 3.0)
	label.label_settings = settings

	parent.add_child(label)
	return label


func _color_of(meta: Dictionary) -> Color:
	var raw: Variant = meta.get("color", [])
	if raw is Array and (raw as Array).size() >= 3:
		var rgb: Array = raw
		return Color8(int(rgb[0]), int(rgb[1]), int(rgb[2]))
	return Color.WHITE
