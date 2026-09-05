extends Node

## Offline renderer for the visual lab. Stills or a short clip, no replay.
##
## A sibling of `offline_render.gd`, not a change to it. The production path
## renders `ReplayViewer.tscn` against an exported replay and is verified by
## `verify_race_render.py`; nothing in this file touches it, imports it, or is
## reachable from it. The lab needs a renderer that can point a camera at a
## scene with no simulation behind it, and forcing that through a replay-shaped
## interface would mean inventing a fake replay to satisfy a contract the art
## question does not have.
##
## What it keeps from the production renderer is the part that matters: an
## offscreen `SubViewport` at the true output resolution, a fixed warm-up
## count, and a clock that is the output frame index rather than wall time. A
## render that crawls and one that flies produce identical images.
##
## Usage, after `--`:
##
##     --out-dir=DIR          required
##     --shots=a,b,c          render one still per named shot
##     --frames=N --fps=F     render a clip instead
##     --width= --height=     output size, default 1080x1920
##     --lab-variant=NAME     tower | deck | spine
##     --lab-shot=NAME        the lens for a clip
##     --lab-no-glow=1        bloom off, for the control frame

const LabScene := preload("res://scripts/lab_scene.gd")

const DEFAULT_WIDTH := 1080
const DEFAULT_HEIGHT := 1920
const DEFAULT_FPS := 60.0
const WARMUP_DRAWS := 12
const PROGRESS_EVERY := 60

var _viewport: SubViewport
var _scene: Node3D
var _out_dir := ""
var _shots: Array = []
var _frames := 0
var _fps := DEFAULT_FPS
var _width := DEFAULT_WIDTH
var _height := DEFAULT_HEIGHT


func _ready() -> void:
	var options := _parse_options()
	_out_dir = str(options.get("out-dir", ""))
	_frames = int(options.get("frames", 0))
	_fps = maxf(1.0, float(options.get("fps", DEFAULT_FPS)))
	_width = int(options.get("width", DEFAULT_WIDTH))
	_height = int(options.get("height", DEFAULT_HEIGHT))
	for part in str(options.get("shots", "")).split(",", false):
		var name := part.strip_edges()
		if not name.is_empty():
			_shots.append(name)

	if _out_dir.is_empty():
		_fail("--out-dir is required")
		return
	if _shots.is_empty() and _frames <= 0:
		_fail("give either --shots=NAME,... or --frames=N")
		return
	if DirAccess.make_dir_recursive_absolute(_out_dir) != OK \
			and not DirAccess.dir_exists_absolute(_out_dir):
		_fail("cannot create output directory: %s" % _out_dir)
		return

	Engine.max_fps = 0
	DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)

	_build_viewport()
	if _shots.is_empty():
		await _render_clip()
	else:
		await _render_stills()


func _build_viewport() -> void:
	_viewport = SubViewport.new()
	_viewport.name = "RenderTarget"
	_viewport.size = Vector2i(_width, _height)
	_viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	_viewport.transparent_bg = false
	# The project setting only reaches the root viewport, so the offline
	# target has to be told or lab frames would alias where a preview does not.
	_viewport.msaa_3d = int(ProjectSettings.get_setting(
		"rendering/anti_aliasing/quality/msaa_3d", Viewport.MSAA_DISABLED))
	_viewport.own_world_3d = true
	_viewport.handle_input_locally = false
	add_child(_viewport)

	_scene = LabScene.new()
	_scene.name = "LabScene"
	_viewport.add_child(_scene)


func _render_stills() -> void:
	## One frame per named lens, all from one build of one scene.
	##
	## Rebuilding between shots would let geometry drift between the frames
	## being compared, which is exactly what a lens comparison must not do.
	var started := Time.get_ticks_usec()
	_scene.set_time(0.0)
	for _i in WARMUP_DRAWS:
		await RenderingServer.frame_post_draw

	for name in _shots:
		_scene.set_shot(str(name))
		# Two draws per shot: screen-space reflection and ambient occlusion
		# both carry history, and a single draw after a camera cut renders
		# them against the previous frame's depth.
		await RenderingServer.frame_post_draw
		await RenderingServer.frame_post_draw

		var image := _viewport.get_texture().get_image()
		if image == null:
			_fail("shot %s: the render target produced no image" % name)
			return
		var path := _out_dir.path_join("%s.png" % name)
		if image.save_png(path) != OK:
			_fail("shot %s: could not write %s" % [name, path])
			return
		print("  shot %s -> %s" % [name, path])

	_report(started, _shots.size())
	get_tree().quit(0)


func _render_clip() -> void:
	## Every frame of a short motion proof, in order.
	var started := Time.get_ticks_usec()
	_scene.set_time(0.0)
	for _i in WARMUP_DRAWS:
		await RenderingServer.frame_post_draw

	for index in _frames:
		_scene.set_time(float(index) / _fps)
		await RenderingServer.frame_post_draw

		var image := _viewport.get_texture().get_image()
		if image == null:
			_fail("frame %d: the render target produced no image" % index)
			return
		if image.save_png(_out_dir.path_join("frame_%06d.png" % index)) != OK:
			_fail("frame %d: could not write the image" % index)
			return
		if index > 0 and index % PROGRESS_EVERY == 0:
			var elapsed := float(Time.get_ticks_usec() - started) / 1_000_000.0
			print("  frame %d/%d  %.1f fps" % [
				index, _frames, float(index) / maxf(elapsed, 0.001)])

	_report(started, _frames)
	get_tree().quit(0)


func _report(started: int, count: int) -> void:
	var elapsed := float(Time.get_ticks_usec() - started) / 1_000_000.0
	print("rendered %d frames in %.1fs  (%.0f ms/frame)" % [
		count, elapsed, 1000.0 * elapsed / float(maxi(count, 1))])
	print("adapter: %s" % RenderingServer.get_video_adapter_name())


func _fail(message: String) -> void:
	push_error("lab render failed: %s" % message)
	get_tree().quit(1)


func _parse_options() -> Dictionary:
	var options := {}
	for argument in OS.get_cmdline_user_args():
		var arg: String = argument
		if not arg.begins_with("--"):
			continue
		var split := arg.substr(2).split("=", true, 1)
		if split.size() == 2:
			options[split[0]] = split[1]
	return options
