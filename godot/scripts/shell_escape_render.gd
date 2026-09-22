extends Node

## Deterministic offline render driver for Category 3 Test #2 visual proof.
## The clock is output frame index / fps.  Godot never advances simulation.

const ShellEscapeScene := preload("res://scripts/shell_escape_scene.gd")
const DEFAULT_WIDTH := 1080
const DEFAULT_HEIGHT := 1920
const DEFAULT_FPS := 60.0
const WARMUP_DRAWS := 2

var _viewport: SubViewport
var _scene: Node2D
var _document := {}
var _out_dir := ""
var _playback_path := ""
var _width := DEFAULT_WIDTH
var _height := DEFAULT_HEIGHT
var _fps := DEFAULT_FPS


func _ready() -> void:
	var options := _parse_options()
	_out_dir = str(options.get("out-dir", ""))
	_playback_path = str(options.get("playback", ""))
	_width = int(options.get("width", DEFAULT_WIDTH))
	_height = int(options.get("height", DEFAULT_HEIGHT))
	_fps = maxf(1.0, float(options.get("fps", DEFAULT_FPS)))
	if _out_dir.is_empty() or _playback_path.is_empty():
		_fail("--playback and --out-dir are required")
		return
	if not _load_playback():
		return
	if DirAccess.make_dir_recursive_absolute(_out_dir) != OK \
			and not DirAccess.dir_exists_absolute(_out_dir):
		_fail("cannot create output directory")
		return
	_build_viewport()
	var error: String = _scene.validate_document()
	if not error.is_empty():
		_fail(error)
		return
	if str(options.get("audit", "0")) == "1":
		await _write_audit()
	elif str(options.get("clip", "0")) == "1":
		await _render_clip(options)
	else:
		await _render_stills(str(options.get("phone", "1")) != "0")


func _load_playback() -> bool:
	var file := FileAccess.open(_playback_path, FileAccess.READ)
	if file == null:
		_fail("cannot read playback: %s" % _playback_path)
		return false
	var parsed = JSON.parse_string(file.get_as_text())
	file.close()
	if typeof(parsed) != TYPE_DICTIONARY:
		_fail("playback is not a JSON object")
		return false
	_document = parsed
	return true


func _build_viewport() -> void:
	_viewport = SubViewport.new()
	_viewport.size = Vector2i(_width, _height)
	_viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	_viewport.transparent_bg = false
	_viewport.msaa_2d = Viewport.MSAA_2X
	add_child(_viewport)
	_scene = ShellEscapeScene.new()
	_viewport.add_child(_scene)
	_scene.configure(_document, _width, _height)
	print("playback seed %d  %.3fs  digest %s" % [
		int(_document["seed"]), _scene.playback_duration(),
		str(_document["digest"]).substr(0, 16)])
	print("arena %.3f px/wu  ball %.2f px" % [
		_scene.world_to_pixel_scale(),
		2.0 * float(_document["arena"]["ball_radius"]) * 1.90
			* _scene.world_to_pixel_scale()])


func _warm_up() -> void:
	_scene.set_render_time(0.0)
	for _index in WARMUP_DRAWS:
		await RenderingServer.frame_post_draw


func _render_stills(phone: bool) -> void:
	await _warm_up()
	for moment in _scene.evidence_moments():
		_scene.set_render_time(float(moment[1]))
		await RenderingServer.frame_post_draw
		await RenderingServer.frame_post_draw
		var image := _viewport.get_texture().get_image()
		if image.is_empty():
			_fail("empty render target")
			return
		var base := _out_dir.path_join(str(moment[0]) + ".png")
		if image.save_png(base) != OK:
			_fail("could not save %s" % base)
			return
		if phone:
			var phone_image := image.duplicate()
			phone_image.resize(360, 640, Image.INTERPOLATE_LANCZOS)
			if phone_image.save_png(_out_dir.path_join(str(moment[0]) + "_phone.png")) != OK:
				_fail("could not save phone still")
				return
		print("still %s  t=%.3f" % [moment[0], float(moment[1])])
	get_tree().quit(0)


func _render_clip(options: Dictionary) -> void:
	await _warm_up()
	var start := maxf(0.0, float(options.get("start", 0.0)))
	var end := minf(_scene.render_duration(),
		float(options.get("end", _scene.render_duration())))
	var first := int(ceil(start * _fps))
	var last := int(floor(end * _fps))
	for frame in range(first, last + 1):
		var t := float(frame) / _fps
		_scene.set_render_time(t)
		await RenderingServer.frame_post_draw
		var image := _viewport.get_texture().get_image()
		var path := _out_dir.path_join("frame_%06d.png" % (frame - first))
		if image.save_png(path) != OK:
			_fail("could not save frame %d" % frame)
			return
		if (frame - first) % 120 == 0:
			print("frame %d/%d" % [frame - first, last - first])
	get_tree().quit(0)


func _write_audit() -> void:
	var event_times := []
	var event_kinds := []
	for event in _document["events"]:
		event_times.append(float(event["t"]))
		event_kinds.append(str(event["kind"]))
	var samples := []
	var last := int(ceil((_scene.playback_duration() + 0.120) * _fps))
	for frame in range(0, last + 1, maxi(1, int(_fps))):
		var t := minf(float(frame) / _fps, _scene.playback_duration() + 0.120)
		var p: Vector2 = _scene.position_at(t)
		samples.append({"frame": frame, "t": t, "position": [p.x, p.y],
			"region": _scene.region_at(minf(t, _scene.playback_duration()))})
	var audit := {
		"format": "category3-shell-visual-audit/1.0.0",
		"seed": int(_document["seed"]),
		"digest": str(_document["digest"]),
		"schema_version": str(_document["schema_version"]),
		"config_digest": str(_document["config_digest"]),
		"fps": _fps,
		"frame": [_width, _height],
		"event_times": event_times,
		"event_kinds": event_kinds,
		"panel_states": _document["panel_states"],
		"samples": samples,
	}
	var file := FileAccess.open(_out_dir.path_join("audit.json"), FileAccess.WRITE)
	if file == null:
		_fail("cannot write audit")
		return
	file.store_string(JSON.stringify(audit, " "))
	file.store_string("\n")
	file.close()
	print("audit %d events, %d samples" % [event_times.size(), samples.size()])
	get_tree().quit(0)


func _parse_options() -> Dictionary:
	var out := {}
	for argument in OS.get_cmdline_user_args():
		if not argument.begins_with("--"):
			continue
		var body := argument.substr(2)
		var equal := body.find("=")
		if equal < 0:
			out[body] = "1"
		else:
			out[body.substr(0, equal)] = body.substr(equal + 1)
	return out


func _fail(message: String) -> void:
	push_error("shell_escape render failed: %s" % message)
	get_tree().quit(1)
