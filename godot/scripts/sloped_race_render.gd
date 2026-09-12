extends Node

## Offline renderer for the real sloped race. Stills, or every frame of a clip.
##
## A sibling of `course_render.gd` and a change to neither it nor
## `offline_render.gd`: the layout proof's frames stay reproducible and the
## bowl machine's replay renderer stays untouched. Only the scene it drives
## differs, and only in that the marbles come from a replay and the camera from
## a solved track.
##
## What it keeps from the production renderer is the part that matters: an
## offscreen `SubViewport` at the true output resolution, a fixed warm-up count,
## and a clock that is the *output frame index* rather than wall time. A render
## that crawls and one that flies produce identical images, which is the only
## reason a two-thousand-frame clip can be trusted to match a still.
##
## Usage, after `--`:
##
##     --out-dir=DIR        required
##     --replay=PATH        the marble3d replay JSON
##     --cameras=PATH       the camera track JSON
##     --stills=a,b,c       one frame per named cut, at the cut's midpoint
##     --at=1.5,2.0,...     one frame per **output** second named, for a sheet
##     --clip=1             every frame from 0 to the replay's own duration
##     --fps=60             output rate; 60 matches the replay's sampling
##     --width= --height=   default 1080x1920
##     --start= --end=      seconds, to render part of a clip
##     --dump-terrain=PATH  write a grid of ground heights and exit
##     --layout=b --detail=hero

const RaceScene := preload("res://scripts/sloped_race_scene.gd")

const DEFAULT_WIDTH := 1080
const DEFAULT_HEIGHT := 1920
const DEFAULT_FPS := 60.0
const WARMUP_DRAWS := 14
const PROGRESS_EVERY := 60

var _viewport: SubViewport
var _scene: Node3D
var _out_dir := ""
var _stills: Array = []
var _at: Array = []
var _clip := false
var _fps := DEFAULT_FPS
var _width := DEFAULT_WIDTH
var _height := DEFAULT_HEIGHT
var _from := 0.0
var _to := -1.0


func _ready() -> void:
	var options := _parse_options()
	_out_dir = str(options.get("out-dir", ""))
	_clip = str(options.get("clip", "")) != ""
	_fps = maxf(1.0, float(options.get("fps", DEFAULT_FPS)))
	_width = int(options.get("width", DEFAULT_WIDTH))
	_height = int(options.get("height", DEFAULT_HEIGHT))
	_from = float(options.get("start", 0.0))
	_to = float(options.get("end", -1.0))
	for part in str(options.get("stills", "")).split(",", false):
		var name := part.strip_edges()
		if not name.is_empty():
			_stills.append(name)
	for part in str(options.get("at", "")).split(",", false):
		var when := part.strip_edges()
		if not when.is_empty():
			_at.append(when.to_float())

	if _out_dir.is_empty():
		_fail("--out-dir is required")
		return
	if _stills.is_empty() and _at.is_empty() and not _clip \
			and str(options.get("dump-terrain", "")) == "":
		_fail("give one of --stills=NAME,... --at=SECONDS,... or --clip=1")
		return
	if DirAccess.make_dir_recursive_absolute(_out_dir) != OK \
			and not DirAccess.dir_exists_absolute(_out_dir):
		_fail("cannot create output directory: %s" % _out_dir)
		return

	Engine.max_fps = 0
	DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)

	_build_viewport()
	var dump := str(options.get("dump-terrain", ""))
	if dump != "":
		_scene.dump_terrain(dump)
		get_tree().quit(0)
		return
	if _clip:
		await _render_clip()
	elif not _at.is_empty():
		await _render_at()
	else:
		await _render_stills()


func _build_viewport() -> void:
	_viewport = SubViewport.new()
	_viewport.name = "RenderTarget"
	_viewport.size = Vector2i(_width, _height)
	_viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	_viewport.transparent_bg = false
	# The project setting only reaches the root viewport, so the offline target
	# has to be told or the race frames would alias where a preview does not.
	_viewport.msaa_3d = int(ProjectSettings.get_setting(
		"rendering/anti_aliasing/quality/msaa_3d", Viewport.MSAA_DISABLED))
	_viewport.own_world_3d = true
	_viewport.handle_input_locally = false
	add_child(_viewport)

	_scene = RaceScene.new()
	_scene.name = "SlopedRace"
	_viewport.add_child(_scene)


func _render_stills() -> void:
	## One frame per named cut, at that cut's own midpoint, from one build.
	##
	## Rebuilding between stills would let the terrain scatter re-seed between
	## frames that are meant to be comparable; and taking them from the cut's
	## midpoint rather than from a typed time means a still is a frame of the
	## clip rather than a picture near it.
	var started := Time.get_ticks_usec()
	_scene.set_time(0.0)
	for _i in WARMUP_DRAWS:
		await RenderingServer.frame_post_draw

	for name in _stills:
		var when: float = _scene.cut_midpoint(str(name))
		_scene.set_time(when)
		# Two draws per still: screen-space reflection and ambient occlusion
		# both carry history, and one draw after a camera cut resolves them
		# against the previous frame's depth.
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
		print("  still %s at %.2fs -> %s" % [name, when, path])

	_report(started, _stills.size())
	get_tree().quit(0)


func _render_at() -> void:
	## One frame per named **output** second, from one build.
	##
	## Its own mode rather than a clip with a narrow window, because a contact
	## sheet wants eleven moments spread over three and a half seconds and a
	## clip would render the two hundred frames between them to get there. The
	## clock is the same one `_render_clip` walks, so a frame taken here is the
	## frame the video will have at that second and not a picture near it.
	var started := Time.get_ticks_usec()
	_scene.set_time(_at[0])
	for _i in WARMUP_DRAWS:
		await RenderingServer.frame_post_draw

	for when in _at:
		var seconds: float = when
		_scene.set_time(seconds)
		# Two draws, for the same reason `_render_stills` takes two: screen
		# space reflection and ambient occlusion carry history across a cut.
		await RenderingServer.frame_post_draw
		await RenderingServer.frame_post_draw

		var image := _viewport.get_texture().get_image()
		if image == null:
			_fail("frame at %.3f: the render target produced no image" % seconds)
			return
		var path := _out_dir.path_join("at_%07.3f.png" % seconds)
		if image.save_png(path) != OK:
			_fail("frame at %.3f: could not write %s" % [seconds, path])
			return
		print("  out %.3f s -> replay %.3f s -> %s" % [
			seconds, _scene.replay_at(seconds), path])

	_report(started, _at.size())
	get_tree().quit(0)


func _render_clip() -> void:
	## Every output frame, in order, over the replay's own duration.
	##
	## The duration is the replay's, not a chosen one. Section 40: no frame is
	## dropped and nothing is sped up, so the clip is as long as the race was.
	var started := Time.get_ticks_usec()
	var duration: float = _scene.replay_duration()
	if _to > 0.0:
		duration = minf(duration, _to)
	if duration <= 0.0:
		_fail("the replay has no duration to render")
		return
	var first := int(round(_from * _fps))
	var last := int(round(duration * _fps))
	_scene.set_time(_from)
	for _i in WARMUP_DRAWS:
		await RenderingServer.frame_post_draw
	_report_triangles()

	for index in range(first, last + 1):
		_scene.set_time(float(index) / _fps)
		await RenderingServer.frame_post_draw

		var image := _viewport.get_texture().get_image()
		if image == null:
			_fail("frame %d: the render target produced no image" % index)
			return
		if image.save_png(_out_dir.path_join("frame_%06d.png" % index)) != OK:
			_fail("frame %d: could not write the image" % index)
			return
		if index > first and (index - first) % PROGRESS_EVERY == 0:
			var elapsed := float(Time.get_ticks_usec() - started) / 1_000_000.0
			print("  frame %d/%d  %.1f fps" % [
				index - first, last - first, float(index - first) / maxf(elapsed, 0.001)])

	_report(started, last - first + 1)
	get_tree().quit(0)


func _report_triangles() -> void:
	var total := 0
	var meshes := 0
	var stack: Array = [_scene]
	while not stack.is_empty():
		var node: Node = stack.pop_back()
		for child in node.get_children():
			stack.append(child)
		if node is MeshInstance3D and (node as MeshInstance3D).mesh != null:
			var mesh: Mesh = (node as MeshInstance3D).mesh
			meshes += 1
			for surface in mesh.get_surface_count():
				var arrays: Array = mesh.surface_get_arrays(surface)
				if arrays.is_empty():
					continue
				var indices = arrays[Mesh.ARRAY_INDEX]
				if indices is PackedInt32Array and indices.size() > 0:
					total += indices.size() / 3
					continue
				var vertices = arrays[Mesh.ARRAY_VERTEX]
				if vertices is PackedVector3Array:
					total += vertices.size() / 3
	print("scene: %d mesh instances, ~%d triangles" % [meshes, total])


func _report(started: int, count: int) -> void:
	var elapsed := float(Time.get_ticks_usec() - started) / 1_000_000.0
	print("rendered %d frames in %.1fs  (%.0f ms/frame)" % [
		count, elapsed, 1000.0 * elapsed / float(maxi(count, 1))])
	print("adapter: %s" % RenderingServer.get_video_adapter_name())


func _fail(message: String) -> void:
	push_error("sloped race render failed: %s" % message)
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
