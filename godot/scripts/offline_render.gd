extends Node

## Offline frame renderer: one replay in, a numbered PNG sequence out.
##
## This is the production path. It renders the *same* scene the interactive
## viewer plays - same camera, arena, fighters, HUD, VFX - into an offscreen
## SubViewport sized exactly 1080x1920, so the picture owes nothing to the
## monitor, the window, the desktop refresh rate or how fast the GPU happens
## to be. The window this process opens is incidental and never captured.
##
## The clock is the output frame index and nothing else. Frame `i` is the
## battle at `i / fps` seconds, computed from the index rather than
## accumulated from deltas, so a render that crawls at 5 frames a second and
## one that flies at 200 produce byte-identical images. Nothing here reads
## `delta`, sleeps, or waits on wall-clock time.

const ViewerScene := preload("res://scenes/ReplayViewer.tscn")

const DEFAULT_WIDTH := 1080
const DEFAULT_HEIGHT := 1920
const DEFAULT_FPS := 60.0

# Draws thrown away before frame zero is captured, so the first *kept* frame
# is never a half-built scene or a still-warming pipeline. A fixed count, not
# a wait: every run discards exactly the same number, which is what keeps two
# renders of one replay identical.
const WARMUP_DRAWS := 8

# Frames between progress lines. Purely console noise; it changes nothing
# about what is rendered.
const PROGRESS_EVERY := 120

var _viewport: SubViewport
var _viewer: Node3D

var _out_dir := ""
var _frame_count := 0
# When set, only these output frame indices are written, and they are named
# `still_%06d.png` rather than `frame_%06d.png`. It is how a camera sweep is
# produced without rendering the whole race five times: the scene, the replay
# and the clock are identical, and only the handful of moments being compared
# are kept.
var _stills: Array[int] = []
var _fps := DEFAULT_FPS
var _width := DEFAULT_WIDTH
var _height := DEFAULT_HEIGHT


func _ready() -> void:
	var options := _parse_options()

	_out_dir = str(options.get("out-dir", ""))
	_frame_count = int(options.get("frames", 0))
	_fps = maxf(1.0, float(options.get("fps", DEFAULT_FPS)))
	_width = int(options.get("width", DEFAULT_WIDTH))
	_height = int(options.get("height", DEFAULT_HEIGHT))
	for part in str(options.get("stills", "")).split(",", false):
		if part.strip_edges().is_valid_int():
			_stills.append(int(part.strip_edges()))

	if _out_dir.is_empty():
		_fail("--out-dir is required")
		return
	if _frame_count <= 0:
		_fail("--frames must be a positive count")
		return
	if _width <= 0 or _height <= 0:
		_fail("--width and --height must be positive")
		return
	if DirAccess.make_dir_recursive_absolute(_out_dir) != OK \
			and not DirAccess.dir_exists_absolute(_out_dir):
		_fail("cannot create output directory: %s" % _out_dir)
		return

	# Nothing about this render should be paced by the desktop. Real time is
	# not a clock here, it is only a cost.
	Engine.max_fps = 0
	DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)

	_build_viewport()
	if not _viewer.is_loaded():
		_fail("replay could not be loaded (see the error above)")
		return

	print("offline render: %dx%d @ %.0f fps, %d frames -> %s" % [
		_width, _height, _fps, _frame_count, _out_dir])
	_render_all()


func _build_viewport() -> void:
	## An offscreen target at the true production resolution.
	##
	## A SubViewport's size is its own business: it is not the window, not the
	## screen and not clamped by either, which is the whole reason a portrait
	## 1080x1920 frame can be produced on a landscape 1920x1080 laptop.
	_viewport = SubViewport.new()
	_viewport.name = "RenderTarget"
	_viewport.size = Vector2i(_width, _height)
	_viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	# Opaque frames: the sky fills every pixel the arena does not.
	_viewport.transparent_bg = false
	# The project setting only ever reaches the root viewport, so the offline
	# target has to be told, or production frames would be aliased where the
	# preview is not.
	_viewport.msaa_3d = int(ProjectSettings.get_setting(
		"rendering/anti_aliasing/quality/msaa_3d", Viewport.MSAA_DISABLED))
	# Its own 3D world, so the viewer's WorldEnvironment and lights apply here
	# and nowhere else.
	_viewport.own_world_3d = true
	_viewport.handle_input_locally = false
	add_child(_viewport)

	_viewer = ViewerScene.instantiate()
	# Set before the node enters the tree: the viewer must never advance a
	# clock of its own.
	_viewer.offline_mode = true
	_viewport.add_child(_viewer)


func _render_all() -> void:
	## Render every frame of the production timeline, in order.
	##
	## One output frame per drawn frame, with the scene moved to the exact
	## replay instant before the draw and the finished image read back after
	## it. The loop never runs ahead of the renderer and never falls behind
	## it, so there is exactly one image per intended frame - no drops from a
	## slow frame, no duplicates from a fast one.
	var started := Time.get_ticks_usec()

	_viewer.seek_to_seconds(0.0)
	for _i in WARMUP_DRAWS:
		await RenderingServer.frame_post_draw

	var wanted: Array = _stills if not _stills.is_empty() else range(_frame_count)
	for index in wanted:
		_viewer.seek_to_seconds(float(index) / _fps)
		await RenderingServer.frame_post_draw

		var image := _viewport.get_texture().get_image()
		if image == null:
			_fail("frame %d: the render target produced no image" % index)
			return
		if image.get_width() != _width or image.get_height() != _height:
			_fail("frame %d: rendered %dx%d, expected %dx%d" % [
				index, image.get_width(), image.get_height(), _width, _height])
			return

		var prefix := "still" if not _stills.is_empty() else "frame"
		var path := _out_dir.path_join("%s_%06d.png" % [prefix, index])
		var error := image.save_png(path)
		if error != OK:
			_fail("frame %d: could not write %s (error %d)" % [index, path, error])
			return

		if index > 0 and index % PROGRESS_EVERY == 0 and _stills.is_empty():
			_report_progress(index, started)

	_report_done(started)
	get_tree().quit(0)


func _report_progress(index: int, started: int) -> void:
	var elapsed := float(Time.get_ticks_usec() - started) / 1_000_000.0
	print("  frame %d/%d  %.1f%%  %.1f fps  %.1f ms/frame" % [
		index, _frame_count, 100.0 * float(index) / float(_frame_count),
		float(index) / maxf(elapsed, 0.001),
		1000.0 * elapsed / float(index)])


func _report_done(started: int) -> void:
	## Wall-clock cost only. It says nothing about what was rendered, which is
	## why it is printed rather than written into the deterministic metadata.
	var elapsed := float(Time.get_ticks_usec() - started) / 1_000_000.0
	print("rendered %d frames in %.1fs  (%.1f frames/sec, %.1f ms/frame)" % [
		_frame_count, elapsed,
		float(_frame_count) / maxf(elapsed, 0.001),
		1000.0 * elapsed / float(_frame_count)])
	print("adapter: %s" % RenderingServer.get_video_adapter_name())


func _fail(message: String) -> void:
	## An incomplete render is a failed render: say so, and exit non-zero.
	push_error("offline render failed: %s" % message)
	get_tree().quit(1)


func _parse_options() -> Dictionary:
	## `--key=value` pairs from the user arguments after `--`.
	##
	## `--replay=` is deliberately left in place rather than consumed: the
	## viewer reads it itself, exactly as it does during interactive playback.
	var options := {}
	for argument in OS.get_cmdline_user_args():
		var arg: String = argument
		if not arg.begins_with("--"):
			continue
		var split := arg.substr(2).split("=", true, 1)
		if split.size() == 2:
			options[split[0]] = split[1]
	return options
