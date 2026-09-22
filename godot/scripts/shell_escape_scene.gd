extends Node2D

## Category 3 Test #2 visual consumer.
##
## This scene has no body, collider, integration step, random source, force or
## response law.  It reads the Phase 1 flights, shell records, panel_states and
## events.  Each rendered frame is a pure function of the requested timestamp.

const EXPECTED_DOCUMENT_VERSION := "category3-test2-shell-escape-playback/1.0.0"
const EXPECTED_SCHEMA_VERSION := "category3-test2-shell-escape/1.0.0"
const EXPECTED_CONFIG_DIGEST := "7da0cbc80d5958260b65417c1ac94fac2285471aaf8adc4f093b27e3445afb3e"

# Mirrored in satisfying/shell_visual.py and checked by tests.
const ARENA_WIDTH_FRACTION := 0.720
const ARENA_CENTRE_X_FRACTION := 0.410
const ARENA_CENTRE_Y_FRACTION := 0.500
const BALL_DRAW_SCALE := 1.90
const TRAIL_SECONDS := 0.080
const TRAIL_SAMPLES := 10
const RELEASE_SECONDS := 0.120
const END_HOLD_SECONDS := 0.630
const NEAR_MISS_FEEDBACK_SECONDS := 0.130
const BREAK_FEEDBACK_SECONDS := 0.180

const BACKGROUND := Color("071019")
const PANEL_COLOURS := [
	Color("57d8e8"), Color("62bcd6"), Color("7babc7"),
	Color("879dbb"), Color("9a91ac"), Color("b08b9e")]
const PANEL_WIDTHS := [6.0, 8.0, 7.0, 9.0, 8.0, 11.0]
const OPENING_COLOUR := Color("77f1ff")
const DAMAGE_COLOUR := Color("ffbd54")
const HEAVY_DAMAGE_COLOUR := Color("ff714e")
const BALL_COLOUR := Color("fff7c7")
const BALL_CORE := Color("ffffff")

var hook_text := "CAN THE BALL ESCAPE?"
var _document := {}
var _width := 1080
var _height := 1920
var _scale := 1.0
var _render_time := 0.0
var _duration := 0.0
var _configured := false


func configure(document: Dictionary, width: int, height: int) -> void:
	_document = document
	_width = width
	_height = height
	_duration = float(_document["summary"]["duration"])
	var outer_radius := float(_document["shells"][-1]["radius"])
	_scale = float(_width) * ARENA_WIDTH_FRACTION / (2.0 * outer_radius)
	_configured = true
	queue_redraw()


func validate_document() -> String:
	if str(_document.get("document_version", "")) != EXPECTED_DOCUMENT_VERSION:
		return "unexpected playback document version"
	if str(_document.get("schema_version", "")) != EXPECTED_SCHEMA_VERSION:
		return "unexpected event schema version"
	if str(_document.get("config_digest", "")) != EXPECTED_CONFIG_DIGEST:
		return "unexpected frozen config digest"
	if int(_document.get("arena", {}).get("shell_count", -1)) != 6:
		return "visual proof requires six canonical shells"
	var events: Array = _document.get("events", [])
	if events.is_empty() or str(events[-1].get("kind", "")) != "escape":
		return "candidate has no canonical terminal escape"
	var previous := -INF
	for event in events:
		var at := float(event["t"])
		if at < previous:
			return "canonical event order changed"
		previous = at
	return ""


func playback_duration() -> float:
	return _duration


func render_duration() -> float:
	return _duration + RELEASE_SECONDS + END_HOLD_SECONDS


func world_to_pixel_scale() -> float:
	return _scale


func set_render_time(value: float) -> void:
	_render_time = clampf(value, 0.0, render_duration())
	queue_redraw()


func playback_time() -> float:
	return minf(_render_time, _duration + RELEASE_SECONDS)


func _project(point: Vector2) -> Vector2:
	return Vector2(
		float(_width) * ARENA_CENTRE_X_FRACTION + point.x * _scale,
		float(_height) * ARENA_CENTRE_Y_FRACTION - point.y * _scale)


func position_at(t: float) -> Vector2:
	## Evaluate the canonical flight record.  This is interpolation of the
	## document, not an integration step and not a collision response.
	var flights: Array = _document["flights"]
	var lo := 0
	var hi := flights.size() - 1
	if t > float(flights[0]["t"]):
		while lo < hi:
			var mid := int((lo + hi + 1) / 2)
			if float(flights[mid]["t"]) <= t:
				lo = mid
			else:
				hi = mid - 1
	var flight: Dictionary = flights[lo]
	var dt := t - float(flight["t"])
	return Vector2(
		float(flight["p"][0]) + float(flight["v"][0]) * dt,
		float(flight["p"][1]) + float(flight["v"][1]) * dt)


func region_at(t: float) -> int:
	var region := 0
	for event in _document["events"]:
		if float(event["t"]) > t:
			break
		if str(event["kind"]) in ["shell_exit", "shell_entry"]:
			region = int(event["to_region"])
	return region


func _panel_broken_at(shell_id: int, panel_id: int, t: float) -> bool:
	for record in _document["panel_states"]:
		if int(record["shell_id"]) == shell_id and int(record["panel_id"]) == panel_id:
			return t >= float(record["t"])
	return false


func _damage_ratio_at(shell_id: int, panel_id: int, t: float) -> float:
	var cumulative := 0.0
	var threshold := float(_document["config"]["break_threshold"])
	for event in _document["events"]:
		if float(event["t"]) > t:
			break
		if str(event["kind"]) == "damage" \
				and int(event["shell_id"]) == shell_id \
				and int(event["panel_id"]) == panel_id:
			cumulative = float(event["cumulative"])
			threshold = float(event["threshold"])
	return cumulative / threshold if threshold > 0.0 else 0.0


func panel_visual_state(shell_id: int, panel_id: int, t: float) -> String:
	var shell: Dictionary = _document["shells"][shell_id]
	if panel_id in shell["open_slots"]:
		return "opening"
	if _panel_broken_at(shell_id, panel_id, t):
		return "broken"
	var ratio := _damage_ratio_at(shell_id, panel_id, t)
	if ratio >= 0.72:
		return "heavily_damaged"
	if ratio >= 0.35:
		return "damaged"
	return "healthy"


func _vertex(shell: Dictionary, index: int, t: float) -> Vector2:
	var angle := float(shell["theta0"]) + float(shell["omega"]) * t \
		+ float(index) * float(shell["slot_width"])
	var radius := float(shell["radius"])
	return Vector2(radius * cos(angle), radius * sin(angle))


func panel_segment(shell_id: int, panel_id: int, t: float) -> Array:
	var shell: Dictionary = _document["shells"][shell_id]
	return [_vertex(shell, panel_id, t), _vertex(shell, panel_id + 1, t)]


func evidence_moments() -> Array:
	var events: Array = _document["events"]
	var first_hit := _first_event_time(events, "collision", -1, 0.25)
	var near := _first_event_time(events, "near_miss", -1, first_hit)
	var broken := _first_event_time(events, "panel_break", -1, _duration * 0.4)
	var middle := _duration * 0.55
	var outer := _duration * 0.82
	for event in events:
		if str(event["kind"]) == "shell_exit" and int(event["to_region"]) >= 3:
			middle = float(event["t"])
			break
	for event in events:
		if int(event.get("shell_id", -1)) == 5 \
				and str(event["kind"]) in ["collision", "near_miss", "shell_exit"]:
			outer = float(event["t"])
			break
	return [
		["a_opening", 0.0],
		["b_first_shell", minf(_duration, first_hit + 0.025)],
		["c_near_miss", minf(_duration, near + 0.035)],
		["d_panel_break", minf(_duration, broken + 0.045)],
		["e_middle_progress", minf(_duration, middle + 0.080)],
		["f_outer_sequence", minf(_duration, outer + 0.060)],
		["g_final_escape", _duration + RELEASE_SECONDS],
	]


func _first_event_time(events: Array, kind: String, shell_id: int, fallback: float) -> float:
	for event in events:
		if str(event["kind"]) == kind \
				and (shell_id < 0 or int(event.get("shell_id", -1)) == shell_id):
			return float(event["t"])
	return fallback


func active_near_miss_count(t: float) -> int:
	var total := 0
	for event in _document["events"]:
		var age := t - float(event["t"])
		if str(event["kind"]) == "near_miss" \
				and age >= 0.0 and age <= NEAR_MISS_FEEDBACK_SECONDS:
			total += 1
	return total


func _draw() -> void:
	if not _configured:
		return
	draw_rect(Rect2(0, 0, _width, _height), BACKGROUND)
	_draw_background_field()
	var t := playback_time()
	_draw_shells(t)
	_draw_break_feedback(t)
	_draw_trail_and_ball(t)
	_draw_near_miss_feedback(t)
	_draw_hook()
	if _render_time > _duration:
		_draw_escape_confirmation()


func _draw_background_field() -> void:
	var centre := _project(Vector2.ZERO)
	var outer_px := float(_document["shells"][-1]["radius"]) * _scale
	for index in range(5, 0, -1):
		var alpha := 0.010 + float(index) * 0.006
		draw_circle(centre, outer_px * float(index) / 5.0,
			Color(0.10, 0.30, 0.38, alpha))


func _draw_shells(t: float) -> void:
	var current_region := region_at(minf(t, _duration))
	for shell_value in _document["shells"]:
		var shell: Dictionary = shell_value
		var shell_id := int(shell["shell_id"])
		var count := int(shell["panel_count"])
		var base: Color = PANEL_COLOURS[shell_id]
		var passed_alpha := 0.38 if shell_id < current_region else 0.92
		var width: float = PANEL_WIDTHS[shell_id] * float(_width) / 1080.0
		for panel_id in range(count):
			var state := panel_visual_state(shell_id, panel_id, t)
			if state == "opening":
				continue
			var segment := panel_segment(shell_id, panel_id, t)
			var a := _project(segment[0])
			var b := _project(segment[1])
			if state == "broken":
				_draw_broken_remnant(a, b, base, width)
				continue
			var colour := base
			colour.a = passed_alpha
			if state == "damaged":
				colour = DAMAGE_COLOUR
				colour.a = passed_alpha
			elif state == "heavily_damaged":
				colour = HEAVY_DAMAGE_COLOUR
				colour.a = passed_alpha
			draw_line(a, b, Color(0.0, 0.02, 0.04, 0.90), width + 5.0, true)
			draw_line(a, b, colour, width, true)
			draw_line(a, b, Color(0.85, 0.98, 1.0, 0.22 * passed_alpha),
				maxf(1.0, width * 0.22), true)
			var post_radius := maxf(2.4, width * 0.52)
			draw_circle(a, post_radius, colour)
			draw_circle(b, post_radius, colour)
			if state != "healthy":
				_draw_damage_marks(a, b, state)
		_draw_opening_markers(shell, t, width)


func _draw_opening_markers(shell: Dictionary, t: float, panel_width: float) -> void:
	for opening_value in shell["openings"]:
		var opening: Dictionary = opening_value
		var first := int(opening["first_slot"])
		var last := first + int(opening["slot_count"])
		var a_world := _vertex(shell, first, t)
		var b_world := _vertex(shell, last, t)
		for world_value in [a_world, b_world]:
			var world: Vector2 = world_value
			var p: Vector2 = _project(world)
			var radial: Vector2 = world.normalized()
			var outward := Vector2(radial.x, -radial.y)
			draw_circle(p, maxf(3.0, panel_width * 0.68), Color(0.16, 0.72, 0.82, 0.26))
			draw_circle(p, maxf(1.7, panel_width * 0.30), OPENING_COLOUR)
			draw_line(p + outward * 4.0, p + outward * (8.0 + panel_width * 0.35),
				Color(OPENING_COLOUR, 0.62), maxf(1.0, panel_width * 0.18), true)


func _draw_damage_marks(a: Vector2, b: Vector2, state: String) -> void:
	var along := (b - a).normalized()
	var normal := Vector2(-along.y, along.x)
	var marks := 3 if state == "heavily_damaged" else 1
	for index in range(marks):
		var fraction := 0.38 + 0.12 * float(index)
		var centre := a.lerp(b, fraction)
		draw_line(centre - normal * 4.0 - along * 2.0,
			centre + normal * 4.0 + along * 2.0,
			Color("381414"), 1.7, true)


func _draw_broken_remnant(a: Vector2, b: Vector2, base: Color, width: float) -> void:
	var stub := (b - a) * 0.12
	var remnant := Color(base, 0.42)
	draw_line(a, a + stub, remnant, maxf(2.0, width * 0.60), true)
	draw_line(b, b - stub, remnant, maxf(2.0, width * 0.60), true)
	draw_circle(a, maxf(2.0, width * 0.38), Color(HEAVY_DAMAGE_COLOUR, 0.55))
	draw_circle(b, maxf(2.0, width * 0.38), Color(HEAVY_DAMAGE_COLOUR, 0.55))


func _draw_trail_and_ball(t: float) -> void:
	for index in range(TRAIL_SAMPLES, 0, -1):
		var age := TRAIL_SECONDS * float(index) / float(TRAIL_SAMPLES)
		var sample_t := maxf(0.0, t - age)
		var p := _project(position_at(sample_t))
		var fraction := 1.0 - age / TRAIL_SECONDS
		var radius := float(_document["arena"]["ball_radius"]) * BALL_DRAW_SCALE \
			* _scale * (0.34 + 0.30 * fraction)
		draw_circle(p, radius, Color(0.90, 0.94, 0.66, 0.025 + 0.10 * fraction))
	var centre := _project(position_at(t))
	var ball_radius := float(_document["arena"]["ball_radius"]) * BALL_DRAW_SCALE * _scale
	draw_circle(centre, ball_radius * 1.90, Color(1.0, 0.88, 0.30, 0.055))
	draw_circle(centre, ball_radius * 1.35, Color(1.0, 0.92, 0.48, 0.15))
	draw_circle(centre, ball_radius, BALL_COLOUR)
	draw_circle(centre - Vector2(ball_radius * 0.22, ball_radius * 0.25),
		ball_radius * 0.42, BALL_CORE)


func _draw_near_miss_feedback(t: float) -> void:
	for event in _document["events"]:
		if str(event["kind"]) != "near_miss":
			continue
		var age := t - float(event["t"])
		if age < 0.0 or age > NEAR_MISS_FEEDBACK_SECONDS:
			continue
		var strength := 1.0 - age / NEAR_MISS_FEEDBACK_SECONDS
		var p := _project(Vector2(float(event["ball_position"][0]),
			float(event["ball_position"][1])))
		draw_circle(p, 5.0 + 13.0 * strength,
			Color(1.0, 0.44, 0.18, 0.10 + 0.20 * strength))
		for ray in range(4):
			var angle := float(ray) * PI * 0.5 + float(event["shell_id"]) * 0.31
			var direction := Vector2(cos(angle), sin(angle))
			draw_line(p + direction * 4.0, p + direction * (6.0 + 8.0 * strength),
				Color(1.0, 0.78, 0.42, 0.85 * strength), 1.5, true)


func _draw_break_feedback(t: float) -> void:
	for event in _document["events"]:
		if str(event["kind"]) != "panel_break":
			continue
		var age := t - float(event["t"])
		if age < 0.0 or age > BREAK_FEEDBACK_SECONDS:
			continue
		var strength := 1.0 - age / BREAK_FEEDBACK_SECONDS
		var p := _project(Vector2(float(event["position"][0]), float(event["position"][1])))
		draw_arc(p, 8.0 + 22.0 * (1.0 - strength), 0.0, TAU, 24,
			Color(1.0, 0.34, 0.18, 0.72 * strength), 2.0, true)


func _draw_hook() -> void:
	var text := "ESCAPED" if _render_time > _duration + 0.03 else hook_text
	var font := ThemeDB.fallback_font
	var size := int(round(62.0 * float(_width) / 1080.0))
	var text_size := font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, size)
	var x := float(_width) * ARENA_CENTRE_X_FRACTION - text_size.x * 0.5
	var y := float(_height) * 0.118
	var colour := Color("9ff6ff") if text == "ESCAPED" else Color("eefbff")
	draw_string(font, Vector2(x + 2.0, y + 3.0), text,
		HORIZONTAL_ALIGNMENT_LEFT, -1, size, Color(0.0, 0.0, 0.0, 0.82))
	draw_string(font, Vector2(x, y), text,
		HORIZONTAL_ALIGNMENT_LEFT, -1, size, colour)


func _draw_escape_confirmation() -> void:
	var event: Dictionary = _document["events"][-1]
	var point := _project(Vector2(float(event["position"][0]), float(event["position"][1])))
	var age := minf(1.0, (_render_time - _duration) / 0.35)
	draw_arc(point, 16.0 + 30.0 * age, 0.0, TAU, 36,
		Color(0.45, 0.96, 1.0, 0.55 * (1.0 - age)), 2.2, true)
