extends Node

## Offline renderer for a marble3d replay played through the authored machine.
##
## A sibling of `lab_render.gd` and `offline_render.gd` rather than a change to
## either. The lab renderer points a camera at a scene with no simulation
## behind it; the production one plays a 2D pymunk race through
## `ReplayViewer.tscn`. This one plays a true-3D PyBullet replay through
## `marble3d_scene.gd`, and it needs both of the documents that neither of the
## others takes: the replay and the presentation contract.
##
## What it keeps from both is the part that matters. An offscreen `SubViewport`
## at the true output resolution, a fixed warm-up count, and a clock that is
## the output frame index and never the wall clock. A render that crawls and
## one that flies produce identical images, because `set_frame(i)` is a pure
## function of `i` and nothing in the scene accumulates.
##
## Usage, after `--`:
##
##     --replay=PATH          required, a marble3d replay
##     --contract=PATH        required, its presentation contract
##     --out-dir=DIR          required
##     --frames=N             how many output frames to write
##     --start-frame=I        the first output frame index, default 0
##     --fps=F                output rate, default 60
##     --width= --height=     output size, default 1080x1920
##     --shots=a:0,b:120,...  which lens takes over at which output frame
##     --debug=1              draw module bounds, origins and sockets
##     --no-glow=1            bloom off, for a control frame

const MachineScene := preload("res://scripts/marble3d_scene.gd")

const DEFAULT_WIDTH := 1080
const DEFAULT_HEIGHT := 1920
const DEFAULT_FPS := 60.0
const REPLAY_FORMAT := "marble3d"
const CONTRACT_VERSION := 1
const WARMUP_DRAWS := 12
const PROGRESS_EVERY := 60

var _viewport: SubViewport
var _scene: Node3D
var _out_dir := ""
var _frames := 0
var _start_frame := 0
var _fps := DEFAULT_FPS
var _width := DEFAULT_WIDTH
var _height := DEFAULT_HEIGHT


func _ready() -> void:
	var options := _parse_options()
	_out_dir = str(options.get("out-dir", ""))
	_frames = int(options.get("frames", 0))
	_start_frame = int(options.get("start-frame", 0))
	_fps = maxf(1.0, float(options.get("fps", DEFAULT_FPS)))
	_width = int(options.get("width", DEFAULT_WIDTH))
	_height = int(options.get("height", DEFAULT_HEIGHT))

	var replay_path := str(options.get("replay", ""))
	var contract_path := str(options.get("contract", ""))
	if replay_path.is_empty() or contract_path.is_empty():
		_fail("--replay and --contract are both required")
		return
	if _out_dir.is_empty():
		_fail("--out-dir is required")
		return
	if _frames <= 0:
		_fail("--frames must be positive")
		return

	var replay := _load_json(replay_path)
	if replay.is_empty():
		return
	var contract := _load_json(contract_path)
	if contract.is_empty():
		return

	# Refuse anything that is not the document this scene understands, rather
	# than drawing a plausible-looking machine out of the wrong numbers. The
	# race and battle replays share a directory with these and are a different
	# contract entirely.
	if str(replay.get("format", "")) != REPLAY_FORMAT:
		_fail("replay %s is format '%s', not '%s'" % [
			replay_path, replay.get("format", ""), REPLAY_FORMAT])
		return
	if int(contract.get("contract_version", -1)) != CONTRACT_VERSION:
		_fail("contract %s is version %s, this renderer speaks %d" % [
			contract_path, contract.get("contract_version", "?"), CONTRACT_VERSION])
		return

	if DirAccess.make_dir_recursive_absolute(_out_dir) != OK \
			and not DirAccess.dir_exists_absolute(_out_dir):
		_fail("cannot create output directory: %s" % _out_dir)
		return

	Engine.max_fps = 0
	DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)

	_build_viewport(contract, replay, options)
	await _render_clip()


func _load_json(path: String) -> Dictionary:
	var text := FileAccess.get_file_as_string(path)
	if text.is_empty():
		_fail("cannot read %s" % path)
		return {}
	var parsed = JSON.parse_string(text)
	if typeof(parsed) != TYPE_DICTIONARY:
		_fail("%s is not a JSON object" % path)
		return {}
	return parsed


func _build_viewport(contract: Dictionary, replay: Dictionary,
		options: Dictionary) -> void:
	_viewport = SubViewport.new()
	_viewport.name = "RenderTarget"
	_viewport.size = Vector2i(_width, _height)
	_viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	_viewport.transparent_bg = false
	# The project setting only reaches the root viewport, so the offline
	# target has to be told or these frames would alias where a preview does
	# not.
	_viewport.msaa_3d = int(ProjectSettings.get_setting(
		"rendering/anti_aliasing/quality/msaa_3d", Viewport.MSAA_DISABLED))
	_viewport.own_world_3d = true
	_viewport.handle_input_locally = false
	add_child(_viewport)

	_scene = MachineScene.new()
	_scene.name = "MarbleMachine"
	_scene.configure(contract, replay, {
		"fps": _fps,
		"debug": str(options.get("debug", "")) != "",
		"no_glow": str(options.get("no-glow", "")) != "",
	})
	_viewport.add_child(_scene)
	_scene.set_cuts(_parse_shots(str(options.get("shots", ""))))
	_scene.build()


func _parse_shots(spec: String) -> Array:
	## "start:0,bowl:180,curve:400" as a list of cuts, in frame order.
	var cuts: Array = []
	for part in spec.split(",", false):
		var pair := str(part).strip_edges().split(":", true, 1)
		if pair.size() != 2:
			continue
		cuts.append({"shot": pair[0].strip_edges(), "frame": int(pair[1])})
	cuts.sort_custom(func(a, b): return int(a["frame"]) < int(b["frame"]))
	if cuts.is_empty():
		cuts.append({"shot": "bowl", "frame": 0})
	return cuts


func _render_clip() -> void:
	## Every output frame, in order, each drawn from its own index.
	var started := Time.get_ticks_usec()
	_scene.set_frame(_start_frame)
	for _i in WARMUP_DRAWS:
		await RenderingServer.frame_post_draw

	for offset in _frames:
		var index: int = _start_frame + offset
		_scene.set_frame(index)
		await RenderingServer.frame_post_draw
		# A second draw on a cut. Screen-space reflection and ambient
		# occlusion both carry a frame of history, so the first frame of a new
		# shot would otherwise shade against the outgoing shot's depth buffer -
		# a visible smear on exactly the frame a viewer is most likely to
		# freeze on.
		if _scene.is_cut_frame(index):
			await RenderingServer.frame_post_draw

		var image := _viewport.get_texture().get_image()
		if image == null:
			_fail("frame %d: the render target produced no image" % index)
			return
		if image.get_width() != _width or image.get_height() != _height:
			_fail("frame %d: rendered %dx%d, expected %dx%d" % [
				index, image.get_width(), image.get_height(), _width, _height])
			return
		if image.save_png(_out_dir.path_join("frame_%06d.png" % index)) != OK:
			_fail("frame %d: could not write the image" % index)
			return
		if offset > 0 and offset % PROGRESS_EVERY == 0:
			var elapsed := float(Time.get_ticks_usec() - started) / 1_000_000.0
			print("  frame %d/%d  %.1f fps" % [
				offset, _frames, float(offset) / maxf(elapsed, 0.001)])

	_report(started, _frames)
	get_tree().quit(0)


func _report(started: int, count: int) -> void:
	## Timings are printed and never written into a render's metadata: they are
	## the one thing about a deterministic render that legitimately differs
	## between two runs of it.
	var elapsed := float(Time.get_ticks_usec() - started) / 1_000_000.0
	print("rendered %d frames in %.1fs  (%.0f ms/frame)" % [
		count, elapsed, 1000.0 * elapsed / float(maxi(count, 1))])
	print("adapter: %s" % RenderingServer.get_video_adapter_name())


func _fail(message: String) -> void:
	push_error("marble3d render failed: %s" % message)
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
		else:
			options[split[0]] = "1"
	return options
