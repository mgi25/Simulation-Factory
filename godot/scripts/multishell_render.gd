extends Node

## Offline renderer for the Category 3 Test #2 redesign, visual Phase 2A.
##
## A sibling of `tile_escape_render.gd` and a change to none of it. What it
## keeps is the part that matters: an offscreen `SubViewport` at the true
## output resolution, a fixed warm-up count, and a clock that is the **output
## frame index** rather than wall time. A render that crawls and one that flies
## produce identical images, which is the only reason a still taken from the
## middle of a seven-hundred-frame clip can be trusted to match it.
##
## `--audit=1` walks every frame, saves no PNG, and writes down the ball
## positions and panel states the scene computed. Python diffs that against the
## canonical document, and "the renderer did not change the simulation" stops
## being an architectural assurance and becomes a number.
##
## Usage, after `--`:
##
##     --playback=PATH      required; from `satisfying.multishell_playback`
##     --out-dir=DIR        required
##     --stills=1           the nine event-centred stills
##     --clip=1             every frame of the run plus the ending
##     --audit=1            walk every frame, save no image, write the audit
##     --moments=JSON       the still times, from `multishell_visual`
##     --fps=30             output rate
##     --width= --height=   default 1080x1920
##     --frontier-width=    override the frame fraction (A/B/C sweep only)
##     --start= --end=      seconds, to render part of a clip
##     --fixed=1            the control: pin the framing to the whole arena
##     --release=0.55       the escapee's run-on past the document's end
##     --hold=0.40          the freeze after it
##     --debug=0

const MultishellScene := preload("res://scripts/multishell_scene.gd")
const DEFAULT_WIDTH := 1080
const DEFAULT_HEIGHT := 1920
const DEFAULT_FPS := 30.0
const WARMUP_DRAWS := 14
const PROGRESS_EVERY := 120

var _viewport: SubViewport
var _scene: Node3D
var _out_dir := ""
var _playback_path := ""
var _moments_path := ""
var _stills := false
var _clip := false
var _audit := false
var _fps := DEFAULT_FPS
var _width := DEFAULT_WIDTH
var _height := DEFAULT_HEIGHT
var _from := 0.0
var _to := -1.0
var _document := {}


func _ready() -> void:
	var options := _parse_options()
	_out_dir = str(options.get("out-dir", ""))
	_playback_path = str(options.get("playback", ""))
	_moments_path = str(options.get("moments", ""))
	_stills = str(options.get("stills", "")) == "1"
	_clip = str(options.get("clip", "")) == "1"
	_audit = str(options.get("audit", "")) == "1"
	_fps = maxf(1.0, float(options.get("fps", DEFAULT_FPS)))
	_width = int(options.get("width", DEFAULT_WIDTH))
	_height = int(options.get("height", DEFAULT_HEIGHT))
	_from = float(options.get("start", 0.0))
	_to = float(options.get("end", -1.0))

	if _out_dir.is_empty():
		_fail("--out-dir is required")
		return
	if _playback_path.is_empty():
		_fail("--playback is required")
		return
	if not (_stills or _clip or _audit):
		_fail("give one of --stills=1 --clip=1 --audit=1")
		return
	if DirAccess.make_dir_recursive_absolute(_out_dir) != OK \
			and not DirAccess.dir_exists_absolute(_out_dir):
		_fail("cannot create output directory: %s" % _out_dir)
		return
	if not _load_playback():
		return

	Engine.max_fps = 0
	DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
	_build_viewport(options)

	var reason: String = _scene.validate_document()
	if reason != "":
		_fail("refusing to render: %s" % reason)
		return

	if _audit:
		await _render_audit()
	elif _stills:
		await _render_stills()
	else:
		await _render_clip()


func _parse_options() -> Dictionary:
	var options := {}
	for argument in OS.get_cmdline_user_args():
		var text := str(argument)
		if not text.begins_with("--"):
			continue
		var body := text.substr(2)
		var split := body.find("=")
		if split < 0:
			options[body] = "1"
		else:
			options[body.substr(0, split)] = body.substr(split + 1)
	return options


func _load_playback() -> bool:
	var file := FileAccess.open(_playback_path, FileAccess.READ)
	if file == null:
		_fail("cannot read playback: %s" % _playback_path)
		return false
	var parsed = JSON.parse_string(file.get_as_text())
	file.close()
	if typeof(parsed) != TYPE_DICTIONARY:
		_fail("playback is not a JSON object: %s" % _playback_path)
		return false
	_document = parsed
	print("playback: seed %d  %.2f s  %d balls  %d events  digest %s" % [
		int(_document["seed"]),
		float(_document["summary"]["duration"]),
		int(_document["balls"].size()),
		int(_document["events"].size()),
		str(_document["digest"]).substr(0, 16)])
	return true


func _build_viewport(options: Dictionary) -> void:
	_viewport = SubViewport.new()
	_viewport.name = "RenderTarget"
	_viewport.size = Vector2i(_width, _height)
	_viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	_viewport.transparent_bg = false
	# The project setting only reaches the root viewport, so the offline target
	# has to be told or these frames would alias where a preview does not.
	_viewport.msaa_3d = int(ProjectSettings.get_setting(
		"rendering/anti_aliasing/quality/msaa_3d", Viewport.MSAA_DISABLED))
	_viewport.own_world_3d = true
	_viewport.handle_input_locally = false
	add_child(_viewport)

	_scene = MultishellScene.new()
	_scene.name = "Multishell"
	if options.has("release"):
		_scene.release_seconds = maxf(0.0, float(options["release"]))
	if options.has("hold"):
		_scene.hold_seconds = maxf(0.0, float(options["hold"]))
	if options.has("panel-depth"):
		var parts: PackedStringArray = str(options["panel-depth"]).split(",")
		var ramp := []
		for part in parts:
			ramp.append(float(part))
		_scene.set_panel_depth(ramp)
	if options.has("frontier-width"):
		_scene.set_frontier_width(float(options["frontier-width"]))
	_scene.fixed_framing = str(options.get("fixed", "0")) == "1"
	_scene.show_debug = str(options.get("debug", "0")) == "1"
	_viewport.add_child(_scene)
	_scene.configure(_document, _width, _height)
	print("arena: %.2f px per world unit at the opening, %.1f px ball, view radius %.2f" % [
		_scene.world_to_pixel_scale(),
		2.0 * float(_document["config"]["ball_radius"])
			* _scene.BALL_DRAW_SCALE * _scene.world_to_pixel_scale(),
		_scene.view_radius()])
	print("framing: %d canonical frontier advances, render %.2f s" % [
		_scene.frame_mark_count(), _scene.render_duration()])


func _moments() -> Array:
	## The still times come from `satisfying.multishell_visual.event_moments`,
	## written to a JSON file by the CLI. They are canonical event times plus a
	## stated offset, so a still of "a panel breaking" is a still of a panel
	## breaking and not of whatever was on screen at a round number of seconds.
	if _moments_path.is_empty():
		return []
	var file := FileAccess.open(_moments_path, FileAccess.READ)
	if file == null:
		return []
	var parsed = JSON.parse_string(file.get_as_text())
	file.close()
	if typeof(parsed) != TYPE_ARRAY:
		return []
	return parsed


func _render_stills() -> void:
	var started := Time.get_ticks_usec()
	var moments := _moments()
	if moments.is_empty():
		_fail("--stills needs --moments=PATH")
		return

	_scene.set_render_time(0.0)
	for _i in WARMUP_DRAWS:
		await RenderingServer.frame_post_draw

	for entry in moments:
		var name := str(entry["name"])
		var when := float(entry["t"])
		_scene.set_render_time(when)
		# Two draws per still: glow carries history across a jump in time, and
		# one draw after a discontinuity resolves it against the previous
		# frame's buffer.
		await RenderingServer.frame_post_draw
		await RenderingServer.frame_post_draw
		var image := _viewport.get_texture().get_image()
		if image == null:
			_fail("still %s: the render target produced no image" % name)
			return
		var path := _out_dir.path_join("%s.png" % name)
		if image.save_png(path) != OK:
			_fail("still %s: could not write %s" % [name, path])
			return
		print("  still %s at %.2fs  %d balls -> %s" % [
			name, when, _scene.population_at(minf(when, _scene.playback_duration())),
			path])

	_report(started, moments.size())
	get_tree().quit(0)


func _render_clip() -> void:
	var started := Time.get_ticks_usec()
	var duration: float = _scene.render_duration()
	if _to > 0.0:
		duration = minf(duration, _to)
	if duration <= 0.0:
		_fail("the playback has no duration to render")
		return
	var first := int(round(_from * _fps))
	var last := int(round(duration * _fps))

	_scene.set_render_time(_from)
	for _i in WARMUP_DRAWS:
		await RenderingServer.frame_post_draw

	for index in range(first, last + 1):
		# The clock is the output frame index, never accumulated wall time.
		_scene.set_render_time(float(index) / _fps)
		await RenderingServer.frame_post_draw
		var image := _viewport.get_texture().get_image()
		if image == null:
			_fail("frame %d: the render target produced no image" % index)
			return
		var path := _out_dir.path_join("frame_%05d.png" % index)
		if image.save_png(path) != OK:
			_fail("frame %d: could not write %s" % [index, path])
			return
		if index % PROGRESS_EVERY == 0:
			print("  frame %d/%d" % [index, last])

	_report(started, last - first + 1)
	get_tree().quit(0)


func _render_audit() -> void:
	## Walk every frame the clip would walk, compute what the clip would
	## compute, save nothing. What comes out is the scene's own arithmetic, for
	## Python to compare against the document it was built from.
	var started := Time.get_ticks_usec()
	var duration: float = _scene.playback_duration()
	var last := int(round(duration * _fps))
	var rows := []
	for index in range(0, last + 1):
		var t := float(index) / _fps
		_scene.set_render_time(t)
		var state: Dictionary = _scene.audit_state()
		state["frame"] = index
		rows.append(state)
	var payload := {
		"seed": int(_document["seed"]),
		"digest": str(_document["digest"]),
		"fps": _fps,
		"frames": rows.size(),
		"rows": rows,
	}
	var path := _out_dir.path_join("audit_%.0f.json" % _fps)
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		_fail("cannot write audit: %s" % path)
		return
	file.store_string(JSON.stringify(payload))
	file.close()
	print("audit: %d frames -> %s" % [rows.size(), path])
	_report(started, rows.size())
	get_tree().quit(0)


func _report(started_usec: int, count: int) -> void:
	var elapsed := float(Time.get_ticks_usec() - started_usec) / 1000000.0
	print("rendered %d in %.1fs (%.2f s each)" % [
		count, elapsed, elapsed / maxf(1.0, float(count))])


func _fail(message: String) -> void:
	printerr("multishell_render: %s" % message)
	get_tree().quit(1)
