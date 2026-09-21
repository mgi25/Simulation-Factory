extends Node

## Offline renderer for Category 3, Test #1. Stills, a clip, or an audit.
##
## A sibling of `race2_render.gd` and a change to none of it. What it keeps is
## the part that matters: an offscreen `SubViewport` at the true output
## resolution, a fixed warm-up count, and a clock that is the **output frame
## index** rather than wall time. A render that crawls and one that flies
## produce identical images, which is the only reason a nine-hundred-frame clip
## can be trusted to match a still taken from the middle of it.
##
## What it adds is `--audit=1`. The scene walks every frame exactly as a clip
## would, saves no PNG, and writes down the frame on which it first drew each
## tile lit plus the ball position it computed at every frame. Python compares
## that against the canonical playback document, and "rendering did not change
## the physics" stops being an architectural assurance and becomes a diff.
##
## Usage, after `--`:
##
##     --playback=PATH      required; from `satisfying.tile_playback`
##     --out-dir=DIR        required
##     --stills=1           the five progress stills
##     --clip=1             every frame from 0 to the run's own end
##     --audit=1            walk every frame, save no image, write the audit
##     --fps=60             output rate
##     --width= --height=   default 1080x1920
##     --start= --end=      seconds, to render part of a clip
##     --hook=TEXT          the hook line; empty draws none
##     --climax=1           play the document's completion sequence, and index
##                          the clip by render time rather than simulation time
##     --climax-stills=1    the six named stills of the ending
##     --trail=temporal|halo|none
##     --trail-seconds=0.14  the trail window; a time, so it is fps-independent
##     --counter=1 --debug=0

const TileEscapeScene := preload("res://scripts/tile_escape_scene.gd")
const DEFAULT_WIDTH := 1080
const DEFAULT_HEIGHT := 1920
const DEFAULT_FPS := 60.0
const WARMUP_DRAWS := 14
const PROGRESS_EVERY := 120

# The progress fractions the first three stills are taken at. Fractions of the
# **tile count**, not of the clock, so "90% of the arena is lit" means the same
# thing in a 26-second run and a 38-second one. The last two stills are
# absolute instead - 50 of 51, and completion - and `_still_moments` builds
# all five.
const STILL_PROGRESS := [0.5, 0.9]

var _viewport: SubViewport
var _scene: Node3D
var _out_dir := ""
var _playback_path := ""
var _stills := false
var _clip := false
var _audit := false
var _climax := false
var _climax_stills := false
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
	_stills = str(options.get("stills", "")) == "1"
	_clip = str(options.get("clip", "")) == "1"
	_audit = str(options.get("audit", "")) == "1"
	_climax_stills = str(options.get("climax-stills", "")) == "1"
	# `--climax-stills` implies `--climax`: the six stills are render instants
	# on the ending's timeline, and a still task that left this false addressed
	# the scene in *simulation* time instead. Four of the six then fell past the
	# run's end, the ball evaluated its escape flight at a render clock and left
	# the frame, and the gate was already open in the confirmation still. One
	# flag, settled here rather than tested at each use.
	_climax = str(options.get("climax", "")) == "1" or _climax_stills
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
	if not (_stills or _clip or _audit or _climax_stills):
		_fail("give one of --stills=1 --clip=1 --audit=1 --climax-stills=1")
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
	if (_climax or _climax_stills) and not _scene.has_completion():
		# Refusing is the point. A document without a completion block renders
		# perfectly well as the Phase 3 prototype ending, so a silent fallback
		# would hand back a plausible video of the wrong thing.
		_fail("--climax needs a playback document with a completion block; "
			+ "export it with `python -m satisfying.tile_phase4_cli export`")
		return
	if _audit:
		await _render_audit()
	elif _climax_stills:
		await _render_climax_stills()
	elif _clip:
		await _render_clip()
	else:
		await _render_stills()


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
	if str(_document.get("kind", "")) != "category3_tile_escape_playback":
		_fail("not a tile-escape playback document: %s" % _playback_path)
		return false
	# The format check is the renderer's half of the contract in
	# `satisfying/tile_playback.py`: a document with a field this build does not
	# know about renders a plausible wrong video, which is worse than an error.
	if int(_document.get("format", -1)) != 1:
		_fail("playback format %s, this renderer reads 1" % _document.get("format"))
		return false
	print("playback: seed %d  %d/%d tiles  %.3f s  digest %s" % [
		int(_document["seed"]), int(_document["activated_tiles"]),
		int(_document["total_tiles"]),
		float(_document["completion_seconds"]) if _document.get("completion_seconds") != null
			else float(_document["end_seconds"]),
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

	_scene = TileEscapeScene.new()
	_scene.name = "TileEscape"
	_scene.hook_text = str(options.get("hook", "HIT EVERY TILE TO ESCAPE"))
	_scene.climax_enabled = _climax or _climax_stills
	_scene.trail_mode = str(options.get("trail", "temporal"))
	if options.has("trail-seconds"):
		_scene.trail_seconds = maxf(0.0, float(options["trail-seconds"]))
	_scene.show_counter = str(options.get("counter", "1")) != "0"
	_scene.show_debug = str(options.get("debug", "0")) == "1"
	_viewport.add_child(_scene)
	_scene.configure(_document, _width, _height)
	print("arena: %d tiles, %.2f px per world unit, ball %.1f px across" % [
		int(_document["total_tiles"]), _scene.world_to_pixel_scale(),
		2.0 * float(_document["config"]["ball_radius"]) * _scene.world_to_pixel_scale()])


func _still_moments() -> Array:
	## The five instants, named, from the run's own activation times.
	var activations: Array = _document["activations"]
	var total := int(_document["total_tiles"])
	var moments := []
	moments.append(["a_open", minf(0.30, float(_document["end_seconds"]))])
	for fraction in STILL_PROGRESS:
		var nth := int(round(fraction * float(total)))
		nth = clampi(nth, 1, activations.size())
		moments.append(["b_half" if fraction == 0.5 else "c_late",
			float(activations[nth - 1]["t"])])
	if activations.size() >= 2:
		# 50 of 51: the instant the penultimate tile lights, which is the state
		# the whole ending is about. Half a second after it, so the activation
		# pulse has decayed and the still shows the *steady* reading of one
		# remaining dark tile rather than a frame mid-flash.
		# Half a second after the penultimate tile, but never inside the last
		# one: a run whose final tile arrives quickly would otherwise have its
		# "50 of 51" still show 51 of 51, which is the one frame in the set
		# that has to show what it says.
		var penultimate := float(activations[activations.size() - 2]["t"])
		var final_tile := float(activations[activations.size() - 1]["t"])
		moments.append(["d_penultimate",
			minf(penultimate + 0.5, final_tile - 0.05)])
	if _document.get("completion_seconds") != null:
		moments.append(["e_complete",
			float(_document["completion_seconds"]) + 0.6])
	return moments


func _render_stills() -> void:
	var started := Time.get_ticks_usec()
	_scene.set_time(0.0)
	for _i in WARMUP_DRAWS:
		await RenderingServer.frame_post_draw

	var moments := _still_moments()
	for entry in moments:
		var name: String = entry[0]
		var when: float = entry[1]
		_scene.set_time(when)
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
		print("  still %s at %.2fs  %d/%d lit -> %s" % [
			name, when, _scene.activated_count_at(when),
			int(_document["total_tiles"]), path])

	_report(started, moments.size())
	get_tree().quit(0)


func _render_clip() -> void:
	var started := Time.get_ticks_usec()
	# With the ending on, the clip is as long as the *ending* says and every
	# frame is a render instant; without it, it is the Phase 3 run length and
	# every frame is a simulation instant. One `if`, and it is the only place
	# in this file that knows the difference.
	var duration: float = _scene.render_duration() if _climax else _scene.playback_duration()
	if _to > 0.0:
		duration = minf(duration, _to)
	if duration <= 0.0:
		_fail("the playback has no duration to render")
		return
	var first := int(round(_from * _fps))
	var last := int(round(duration * _fps))
	_set_clock(_from)
	for _i in WARMUP_DRAWS:
		await RenderingServer.frame_post_draw

	for index in range(first, last + 1):
		# The clock is the output frame index, never an accumulated delta.
		_set_clock(float(index) / _fps)
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


func _set_clock(t: float) -> void:
	if _climax:
		_scene.set_render_time(t)
	else:
		_scene.set_time(t)


func _climax_moments() -> Array:
	## The six stills the brief names, from the ending's own timeline.
	##
	## Taken at render instants, not simulation ones - four of the six sit
	## inside a hold, where simulation time does not move and only the render
	## clock distinguishes "the arena is answering" from "the gate is opening".
	var block: Dictionary = _document["completion"]
	var timing: Dictionary = block["timing"]
	var route: Dictionary = block["route"]
	var final_at := float(block["final_seconds"])
	var release := float(timing["release_at_seconds"])
	var gate_open_at := float(timing["gate_open_at_seconds"])
	var gate_open := float(timing["gate_open_seconds"])
	var escape_render: float = float(route["exit_seconds"]) / float(timing["escape_rate"])
	return [
		# One frame before the final activation, at the output rate: the last
		# instant with a dark tile in the arena.
		["a_before_final", final_at - 1.0 / _fps],
		["b_final_hit", final_at],
		["c_confirmation", final_at + float(timing["impact_hold_seconds"])
			+ 0.5 * (gate_open_at - float(timing["impact_hold_seconds"]))],
		["d_unlock", final_at + gate_open_at + gate_open],
		# Mid-escape: the ball between the opening and the frame edge.
		["e_escape", final_at + release + 0.55 * escape_render],
		["f_end", float(block["total_render_seconds"]) - 0.02],
	]


func _render_climax_stills() -> void:
	var started := Time.get_ticks_usec()
	_set_clock(0.0)
	for _i in WARMUP_DRAWS:
		await RenderingServer.frame_post_draw

	var moments := _climax_moments()
	for entry in moments:
		var name: String = entry[0]
		var when: float = entry[1]
		_set_clock(when)
		await RenderingServer.frame_post_draw
		await RenderingServer.frame_post_draw
		var image := _viewport.get_texture().get_image()
		if image == null:
			_fail("climax still %s: the render target produced no image" % name)
			return
		var path := _out_dir.path_join("%s.png" % name)
		if image.save_png(path) != OK:
			_fail("climax still %s: could not write %s" % [name, path])
			return
		print("  still %s at r=%.3fs sim=%.3fs  state %s  %d/%d lit -> %s" % [
			name, when, _scene.sim_time_at(when), _scene.climax_state_at(when),
			_scene.activated_count_at(_scene.sim_time_at(when)),
			int(_document["total_tiles"]), path])

	_report(started, moments.size())
	get_tree().quit(0)


func _render_audit() -> void:
	## Walk every frame, save nothing, and write down what the scene showed.
	##
	## No PNG and no `frame_post_draw` await: the audit asks what the scene
	## *computed*, and the scene's state is a pure function of `set_time`, so a
	## draw would cost minutes and add nothing. That is itself the claim being
	## tested - if a frame had to be drawn for the state to be right, the scene
	## would be carrying rendering state into playback, and this pass would not
	## agree with the canonical document.
	var started := Time.get_ticks_usec()
	var duration: float = _scene.playback_duration()
	var last := int(round(duration * _fps))
	var total := int(_document["total_tiles"])

	var first_lit_frame := {}
	# Three flat arrays rather than one array of four-element arrays. A
	# 60 fps audit of the longest run in the cast is 3,576 frames, and
	# `JSON.stringify` over 3,576 nested `Array` variants overflowed the stack
	# and killed the process with 0xC00000FD. Packed arrays serialise as flat
	# lists of numbers and cost nothing to walk.
	var sample_t := PackedFloat64Array()
	var sample_x := PackedFloat64Array()
	var sample_y := PackedFloat64Array()
	var sample_count := PackedInt32Array()
	var previous := 0
	for index in range(0, last + 1):
		_scene.set_time(float(index) / _fps)
		var state: Dictionary = _scene.audit_state()
		var count := int(state["activated"])
		if count != previous:
			for tile in state["lit"]:
				# Keyed by the string form on both sides. Testing `has(tile)`
				# against a dictionary keyed by `str(tile)` never matches, so
				# every lit tile was rewritten on every change and all fifty-one
				# ended up recorded as first lit on the final frame.
				var key := str(tile)
				if not first_lit_frame.has(key):
					first_lit_frame[key] = index
			previous = count
		sample_t.append(float(state["t"]))
		sample_x.append(float(state["ball"][0]))
		sample_y.append(float(state["ball"][1]))
		sample_count.append(count)

	var payload := {
		"kind": "category3_tile_escape_audit",
		"seed": int(_document["seed"]),
		"digest": str(_document["digest"]),
		"fps": _fps,
		"width": _width,
		"height": _height,
		"frames": last + 1,
		"pixels_per_unit": _scene.world_to_pixel_scale(),
		"final_activated": previous,
		"total_tiles": total,
		"first_lit_frame": first_lit_frame,
		"sample_t": sample_t,
		"sample_x": sample_x,
		"sample_y": sample_y,
		"sample_count": sample_count,
	}
	var path := _out_dir.path_join("audit_%dfps.json" % int(_fps))
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		_fail("cannot write the audit: %s" % path)
		return
	file.store_string(JSON.stringify(payload))
	file.close()
	# `%g` is not a GDScript format specifier - it raises "unsupported format
	# character", and Godot then exits non-zero even though the audit was
	# already on disk, so the driver reported a failure for a file that was
	# written correctly.
	print("audit: %d frames at %.0f fps, %d/%d lit -> %s" % [
		last + 1, _fps, previous, total, path])
	_report(started, last + 1)
	get_tree().quit(0)


func _report(started: int, count: int) -> void:
	var elapsed := float(Time.get_ticks_usec() - started) / 1_000_000.0
	print("rendered %d frames in %.1fs  (%.0f ms/frame)" % [
		count, elapsed, 1000.0 * elapsed / float(maxi(count, 1))])
	print("adapter: %s" % RenderingServer.get_video_adapter_name())


func _fail(message: String) -> void:
	push_error("tile_escape render failed: %s" % message)
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
