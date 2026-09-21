extends Node3D

## Category 3, Test #1 — HIT EVERY TILE TO ESCAPE. The presentation layer.
##
## **This scene has no physics.** It loads a playback document written by
## `satisfying.tile_playback` and evaluates it. There is no `RigidBody`, no
## `move_and_slide`, no integration and no `delta` anywhere in this file: the
## ball's position at time `t` is `p + v*dt - 0.5*g*dt^2` on the flight that
## was already in progress at `t`, which is a closed form the Python solver
## computed the coefficients for. Two consequences, and they are the reason the
## scene is written this way:
##
## * **The frame rate cannot change the run.** Render at 24, 30, 60 or 1000 fps
##   and each frame samples the same curve at a different instant. There is no
##   accumulated error to differ.
## * **A rendering bug cannot become a physics bug.** The worst this file can do
##   is draw the right run wrongly, which a still will show.
##
## `tile_escape_render.gd` drives it, and an `--audit=1` pass makes the claim
## checkable rather than merely stated: the scene records the frame on which it
## first drew each tile lit and the ball position it computed, and Python
## compares both against the canonical document.
##
## ## Why 3D with an orthographic camera, and not 2D
##
## The brief rules out the reference channel's thin concentric rings and asks
## for "slight physical depth". A `Line2D` cannot have depth; an extruded 3D
## tile can. But a perspective camera would make the projection non-linear, and
## then "the arena occupies 86% of the frame width" stops being a number Python
## can predict and check.
##
## So: orthographic, straight down -Z, `KEEP_WIDTH`. World-to-pixel is then an
## exact scalar, `viewport_width / camera.size`, and
## `satisfying.tile_readability` predicts every pixel measurement from the
## playback document alone. The depth comes from the tile mesh instead - each
## tile is a **chamfered slab**, a large back rectangle and a smaller front one
## joined by four sloped rim faces. Straight-on orthographic sees all four rims,
## a directional light gives each a different shade, and the tile reads as a
## raised physical block rather than as a painted line. A plain `BoxMesh` would
## not: its sides are exactly parallel to the view direction and invisible.
##
## ## Inactive against activated
##
## The one thing that must survive a phone screen, motion, and 50 of 51 tiles
## lit. Three separate channels carry it, so losing one still leaves two:
##
## 1. **Luminance.** Inactive tiles are near the background; activated ones are
##    bright. Measured, not asserted - `tile_readability.still_report` reads the
##    rendered PNG back.
## 2. **Hue.** Inactive is cold slate, activated is amber. Opposite sides of the
##    wheel, so the difference survives a greyscale or colour-blind check.
## 3. **Emission and glow.** An activated tile emits and blooms; an inactive one
##    is lit only by the scene. That is the channel that reads at thumbnail size
##    when the tile is four pixels tall.
##
## ## Hit feedback, and the duplicate problem
##
## A new activation pulses hard: emission spikes and the slab recoils outward,
## decaying over `NEW_HIT_PULSE_SECONDS`. A repeat hit on an already-lit tile
## gets a **different and much smaller** response - a brief brightness tap, no
## recoil at all, `DUP_HIT_PULSE_SCALE` of the magnitude and a third of the
## duration. The brief asks that a duplicate not falsely imply progress, and
## with roughly two duplicates per activation at this operating point a
## duplicate that looked like an activation would make the progress reading
## noise. The two responses are deliberately different in *kind* (brightness
## only, against brightness plus motion) and not merely in degree.

const HOOK_DEFAULT := "HIT EVERY TILE TO ESCAPE"

# --- Composition -----------------------------------------------------------
# The arena's width as a fraction of the frame's. A 17-gon is nearly circular,
# so in a 9:16 frame it occupies a square band across the middle and leaves
# about a quarter of the height clear above and below - which is where the hook
# and the counter go. 0.86 rather than the Phase 1 renderer's 0.88 because the
# chamfered slab is thicker than a drawn line and needs the extra margin.
const ARENA_WIDTH_FRACTION := 0.86
const HOOK_TOP_FRACTION := 0.075
const COUNTER_TOP_FRACTION := 0.815
const DEBUG_TOP_FRACTION := 0.905
const SAFE_MARGIN_FRACTION := 0.05

# --- Tile geometry, in simulation world units ------------------------------
const TILE_RADIAL_THICKNESS := 0.62
const TILE_DEPTH := 0.55
const TILE_CHAMFER := 0.13
# The drawn gap at each end of a tile, as a fraction of its length. Cosmetic:
# the physics uses the whole segment, and a ball landing in a drawn gap
# activates the tile it geometrically hit. Named here, and not on the config,
# because it is the one place in Category 3 where what is drawn is not exactly
# what is simulated.
const TILE_GAP_FRACTION := 0.075

# --- Ball ------------------------------------------------------------------
# The ball is drawn larger than the collision radius. At 85 wu/s in a
# circumradius-10 arena the physical ball is 0.9 wu across and reads as 42 px
# in a 1080-wide frame - small enough to lose against a lit wall. The drawn
# radius is a presentation constant and the *collision* radius stays the
# config's, so nothing about the trajectory changes.
const BALL_DRAW_SCALE := 1.45
const BALL_DEPTH := 0.9

# --- Motion treatment ------------------------------------------------------
# The trail is a time window, not a frame count, so it looks the same at every
# frame rate - which is the whole reason a 30 fps render and a 60 fps one can
# be compared at all.
#
# The length was chosen against a measurement, not a preference. At 85 wu/s and
# 46.44 px/wu the ball travels 131.6 px between two frames at 30 fps and 65.8 px
# at 60, while its drawn diameter is only 60.6 px: consecutive frames do not
# overlap and the ball strobes. A trail closes that gap only if the streak it
# draws is longer than the step. Four lengths were rendered and compared in
# `output/category3_v3/trail/`:
#
#   0.00 s (none)   no direction cue at all, and a visible strobe
#   0.05 s / 197 px covers the 30 fps step nominally, but the trail fades
#                   quadratically, so the *visible* streak is about 130 px and
#                   only just reaches the previous frame's ball
#   0.09 s / 355 px a clean streak; visible length ~230 px, comfortably over
#                   the 30 fps step and 3.5x the 60 fps one
#   0.14 s / 553 px a comet that crosses half the arena and competes with the
#                   tiles for attention
#
# 0.09 s, therefore. `tile_readability.strobe_report` measures the result on
# the rendered frames rather than trusting this arithmetic.
const TRAIL_SECONDS := 0.09
# Samples are spaced so that consecutive ones overlap: at 85 wu/s the ball
# covers 7.65 wu in the trail window, and 34 samples put them 0.22 wu apart
# against a drawn ball radius of 0.65 wu. Overlap is what makes the trail a
# streak rather than a dotted line.
const TRAIL_SAMPLES := 34
const TRAIL_HEAD_WIDTH := 0.95
const TRAIL_TAIL_WIDTH := 0.20
const HALO_SCALE := 2.4

# --- Feedback timing -------------------------------------------------------
const NEW_HIT_PULSE_SECONDS := 0.30
const NEW_HIT_PUSH := 0.30
const DUP_HIT_PULSE_SECONDS := 0.10
const DUP_HIT_PULSE_SCALE := 0.22
const COMPLETION_PULSE_SECONDS := 0.9
const COMPLETION_HOLD_SECONDS := 2.0

# --- Colour ----------------------------------------------------------------
const BACKGROUND := Color(0.027, 0.031, 0.047)
const FLOOR_COLOUR := Color(0.043, 0.050, 0.070)
const TILE_INACTIVE := Color(0.105, 0.125, 0.170)
const TILE_INACTIVE_EMISSION := Color(0.035, 0.048, 0.075)
const TILE_ACTIVE := Color(1.0, 0.560, 0.180)
const TILE_ACTIVE_EMISSION := Color(1.0, 0.470, 0.110)
const TILE_COMPLETE_EMISSION := Color(1.0, 0.760, 0.330)
const BALL_COLOUR := Color(1.0, 1.0, 1.0)
const TRAIL_COLOUR := Color(0.45, 0.78, 1.0)
const TEXT_PRIMARY := Color(0.925, 0.941, 0.972)
const TEXT_DIM := Color(0.47, 0.51, 0.59)

var playback: Dictionary = {}
var hook_text := HOOK_DEFAULT
var trail_mode := "temporal"
## The trail window, in seconds. Settable so the render driver can put two
## lengths side by side; `TRAIL_SECONDS` is the default and the reason for it.
var trail_seconds := TRAIL_SECONDS
var show_counter := true
var show_debug := false

var _width := 1080
var _height := 1920
var _camera: Camera3D
var _tiles: Array[MeshInstance3D] = []
var _tile_materials: Array[StandardMaterial3D] = []
var _tile_home: Array[Vector3] = []
var _tile_normal: Array[Vector3] = []
var _ball: MeshInstance3D
var _halo: MeshInstance3D
var _trail: Array[MeshInstance3D] = []
var _trail_material: StandardMaterial3D
var _gradient: GradientTexture2D
var _hook_label: Label
var _counter_label: Label
var _debug_label: Label

var _flight_times: PackedFloat64Array = PackedFloat64Array()
var _activation_times: PackedFloat64Array = PackedFloat64Array()
var _last_new_hit: PackedFloat64Array = PackedFloat64Array()
var _last_dup_hit: PackedFloat64Array = PackedFloat64Array()
var _gravity := 0.0
var _total_tiles := 0
var _completion := -1.0
var _end_seconds := 0.0
var _pixels_per_unit := 1.0
var _time := 0.0


func configure(document: Dictionary, width: int, height: int) -> void:
	playback = document
	_width = width
	_height = height
	_gravity = float(document["config"]["gravity"])
	_total_tiles = int(document["total_tiles"])
	_completion = -1.0
	_end_seconds = float(document["end_seconds"])
	if document.get("completion_seconds") != null:
		_completion = float(document["completion_seconds"])

	_flight_times = PackedFloat64Array()
	for flight in document["flights"]:
		_flight_times.append(float(flight["t"]))
	_activation_times = PackedFloat64Array()
	for entry in document["activations"]:
		_activation_times.append(float(entry["t"]))

	_last_new_hit = PackedFloat64Array()
	_last_dup_hit = PackedFloat64Array()
	for _i in _total_tiles:
		_last_new_hit.append(-1.0e9)
		_last_dup_hit.append(-1.0e9)

	_build()


## The run's own length plus the completion hold. The renderer's clip mode uses
## it so the video is as long as the run was, and no longer.
func playback_duration() -> float:
	var end := float(playback.get("end_seconds", 0.0))
	if _completion >= 0.0:
		end = maxf(end, _completion)
	return end + COMPLETION_HOLD_SECONDS


func world_to_pixel_scale() -> float:
	return _pixels_per_unit


# ---------------------------------------------------------------------------
# Building
# ---------------------------------------------------------------------------


func _build() -> void:
	for child in get_children():
		child.queue_free()
	_tiles.clear()
	_tile_materials.clear()
	_tile_home.clear()
	_tile_normal.clear()
	_trail.clear()

	var arena: Dictionary = playback["arena"]
	var circumradius := float(arena["circumradius"])

	_build_environment()
	_build_camera(circumradius)
	_build_floor(arena)
	_build_tiles(arena)
	_build_ball()
	_build_overlay()


func _build_environment() -> void:
	var world := WorldEnvironment.new()
	var environment := Environment.new()
	environment.background_mode = Environment.BG_COLOR
	environment.background_color = BACKGROUND
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.ambient_light_color = Color(0.32, 0.40, 0.58)
	environment.ambient_light_energy = 0.55
	# Restrained glow, and the reason the activated/inactive difference reads at
	# thumbnail size: an emissive tile blooms a little past its own edge, an
	# inactive one does not bloom at all. The threshold sits above the inactive
	# tile's brightness on purpose, so the bloom is a *signal* and not a haze
	# over the whole frame.
	environment.glow_enabled = true
	environment.glow_intensity = 0.55
	environment.glow_strength = 1.0
	environment.glow_bloom = 0.10
	environment.glow_blend_mode = Environment.GLOW_BLEND_MODE_ADDITIVE
	environment.glow_hdr_threshold = 0.90
	world.environment = environment
	add_child(world)

	# One key from the upper left. Its only job is to shade the four chamfer
	# rims differently from the tile face, which is what makes a slab look
	# raised under an orthographic camera.
	var key := DirectionalLight3D.new()
	key.light_energy = 1.25
	key.light_color = Color(0.86, 0.91, 1.0)
	key.look_at_from_position(Vector3(-6.0, 9.0, 12.0), Vector3.ZERO, Vector3.UP)
	add_child(key)

	var fill := DirectionalLight3D.new()
	fill.light_energy = 0.35
	fill.light_color = Color(0.55, 0.68, 1.0)
	fill.look_at_from_position(Vector3(8.0, -6.0, 9.0), Vector3.ZERO, Vector3.UP)
	add_child(fill)


func _build_camera(circumradius: float) -> void:
	_camera = Camera3D.new()
	_camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	_camera.keep_aspect = Camera3D.KEEP_WIDTH
	# `size` under KEEP_WIDTH is the horizontal extent in world units, so the
	# arena's share of the frame width is exactly ARENA_WIDTH_FRACTION and the
	# pixel scale below is exact rather than fitted.
	_camera.size = (2.0 * circumradius) / ARENA_WIDTH_FRACTION
	_camera.near = 0.05
	_camera.far = 200.0
	# `look_at` needs the node in the tree; `look_at_from_position` does not, and
	# the camera is built before it is parented.
	_camera.look_at_from_position(Vector3(0.0, 0.0, 60.0), Vector3.ZERO, Vector3.UP)
	add_child(_camera)
	_pixels_per_unit = float(_width) / _camera.size


func _build_floor(arena: Dictionary) -> void:
	## The arena interior, one shade above the background. It says "the ball
	## lives in here" in frame one, before any tile has lit.
	var vertices := PackedVector3Array()
	var indices := PackedInt32Array()
	var points: Array = arena["vertices"]
	vertices.append(Vector3.ZERO)
	for point in points:
		vertices.append(Vector3(float(point[0]), float(point[1]), 0.0))
	for k in points.size():
		indices.append(0)
		indices.append(1 + k)
		indices.append(1 + ((k + 1) % points.size()))

	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_INDEX] = indices
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)

	var material := StandardMaterial3D.new()
	material.albedo_color = FLOOR_COLOUR
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	# A single flat unshaded polygon seen from one side. Which way its triangles
	# wind is not information anybody needs, and culling it is one more way for
	# the arena interior to silently vanish.
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	var instance := MeshInstance3D.new()
	instance.name = "Floor"
	instance.mesh = mesh
	instance.material_override = material
	instance.position = Vector3(0.0, 0.0, -0.4)
	add_child(instance)


func _chamfered_slab(length: float, thickness: float, depth: float, chamfer: float) -> ArrayMesh:
	## A slab whose front face is inset on all four sides, joined to the back by
	## four sloped rims.
	##
	## This is the whole reason the camera can stay orthographic. A `BoxMesh`
	## seen straight down its own axis shows one flat rectangle and no depth at
	## all - its side faces are exactly parallel to the view direction. The
	## rims here are not parallel to it, so a directional light gives the top,
	## bottom, left and right rims four different shades and the tile reads as a
	## raised block. Cheap, too: twelve triangles.
	var hl := length * 0.5
	var ht := thickness * 0.5
	var fl := maxf(0.02, hl - chamfer)
	var ft := maxf(0.02, ht - chamfer)

	var vertices := PackedVector3Array([
		Vector3(-hl, -ht, 0.0), Vector3(hl, -ht, 0.0),
		Vector3(hl, ht, 0.0), Vector3(-hl, ht, 0.0),
		Vector3(-fl, -ft, depth), Vector3(fl, -ft, depth),
		Vector3(fl, ft, depth), Vector3(-fl, ft, depth),
	])
	# **Clockwise**, seen from +Z. Godot's front face is the clockwise winding,
	# not the counter-clockwise one a lot of graphics writing assumes, and a
	# counter-clockwise slab is silently culled: the second render of this scene
	# showed the arena floor and not one of its fifty-one tiles.
	var indices := PackedInt32Array([
		6, 5, 4, 7, 6, 4,          # front face
		5, 1, 0, 4, 5, 0,          # bottom rim
		6, 2, 1, 5, 6, 1,          # right rim
		7, 3, 2, 6, 7, 2,          # top rim
		4, 0, 3, 7, 4, 3,          # left rim
	])

	var surface := SurfaceTool.new()
	surface.begin(Mesh.PRIMITIVE_TRIANGLES)
	# Smooth group -1 is flat shading. Averaged normals would blend each rim
	# into the face and into its neighbours, which is exactly the shading
	# difference the chamfer exists to create - a smoothed slab looks like a
	# painted line again.
	surface.set_smooth_group(-1)
	for index in indices:
		surface.add_vertex(vertices[index])
	surface.generate_normals()
	return surface.commit()


func _build_tiles(arena: Dictionary) -> void:
	var container := Node3D.new()
	container.name = "Tiles"
	add_child(container)

	for entry in arena["tiles"]:
		var start := Vector3(float(entry["start"][0]), float(entry["start"][1]), 0.0)
		var end := Vector3(float(entry["end"][0]), float(entry["end"][1]), 0.0)
		var normal := Vector3(
			float(entry["outward_normal"][0]), float(entry["outward_normal"][1]), 0.0)
		var full_length := start.distance_to(end)
		var drawn_length := full_length * (1.0 - 2.0 * TILE_GAP_FRACTION)

		var mesh := _chamfered_slab(
			drawn_length, TILE_RADIAL_THICKNESS, TILE_DEPTH, TILE_CHAMFER)
		var material := StandardMaterial3D.new()
		material.albedo_color = TILE_INACTIVE
		material.emission_enabled = true
		material.emission = TILE_INACTIVE_EMISSION
		material.emission_energy_multiplier = 1.0
		material.roughness = 0.55
		material.metallic = 0.10

		var instance := MeshInstance3D.new()
		instance.name = "Tile%02d" % int(entry["index"])
		instance.mesh = mesh
		instance.material_override = material
		# The slab sits just inside the wall line, centred on the tile, with its
		# long axis along the wall. `basis` is built from the wall direction so
		# a tile is never drawn at an angle the ball did not bounce off.
		var along := (end - start).normalized()
		var home := (start + end) * 0.5 - normal * (TILE_RADIAL_THICKNESS * 0.5)
		# `Basis(along, normal, +Z)` is **mirrored**, and that is not a cosmetic
		# detail: the arena's vertices run counter-clockwise, so for every side
		# `along.cross(normal)` points at -Z and the basis has determinant -1.
		# A mirrored basis reverses every triangle's winding, backface culling
		# then removes the whole slab, and the first render of this scene drew
		# an empty arena with a ball bouncing around inside nothing. Building
		# the second axis as `depth.cross(along)` makes the basis right-handed
		# by construction. The slab is symmetric across that axis, so the shape
		# is unchanged - only its handedness is.
		var depth := Vector3(0.0, 0.0, 1.0)
		instance.transform = Transform3D(
			Basis(along, depth.cross(along), depth), home)
		container.add_child(instance)

		_tiles.append(instance)
		_tile_materials.append(material)
		_tile_home.append(home)
		_tile_normal.append(normal)


func _build_ball() -> void:
	var radius := float(playback["config"]["ball_radius"]) * BALL_DRAW_SCALE

	if trail_mode == "temporal":
		_trail_material = StandardMaterial3D.new()
		_trail_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		_trail_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		_trail_material.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
		_trail_material.albedo_color = TRAIL_COLOUR
		_trail_material.billboard_mode = BaseMaterial3D.BILLBOARD_ENABLED
		_trail_material.vertex_color_use_as_albedo = true
		var container := Node3D.new()
		container.name = "Trail"
		add_child(container)
		for i in TRAIL_SAMPLES:
			var quad := QuadMesh.new()
			quad.size = Vector2(2.0 * radius, 2.0 * radius)
			var node := MeshInstance3D.new()
			node.mesh = quad
			# Each sample owns its material so its alpha can differ; sharing one
			# would make the whole trail a single opacity and defeat the point.
			var sample_material: StandardMaterial3D = _trail_material.duplicate()
			sample_material.albedo_texture = _radial_gradient()
			node.material_override = sample_material
			node.visible = false
			container.add_child(node)
			_trail.append(node)

	if trail_mode != "none":
		var halo_mesh := QuadMesh.new()
		halo_mesh.size = Vector2(radius * 2.0 * HALO_SCALE, radius * 2.0 * HALO_SCALE)
		var halo_material := StandardMaterial3D.new()
		halo_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		halo_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		halo_material.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
		halo_material.albedo_color = Color(0.55, 0.78, 1.0, 0.20)
		halo_material.billboard_mode = BaseMaterial3D.BILLBOARD_ENABLED
		halo_material.albedo_texture = _radial_gradient()
		_halo = MeshInstance3D.new()
		_halo.name = "Halo"
		_halo.mesh = halo_mesh
		_halo.material_override = halo_material
		add_child(_halo)

	var sphere := SphereMesh.new()
	sphere.radius = radius
	sphere.height = radius * 2.0
	sphere.radial_segments = 32
	sphere.rings = 16
	var ball_material := StandardMaterial3D.new()
	ball_material.albedo_color = BALL_COLOUR
	ball_material.emission_enabled = true
	ball_material.emission = Color(0.80, 0.90, 1.0)
	ball_material.emission_energy_multiplier = 1.6
	ball_material.roughness = 0.25
	_ball = MeshInstance3D.new()
	_ball.name = "Ball"
	_ball.mesh = sphere
	_ball.material_override = ball_material
	_ball.position = Vector3(0.0, 0.0, BALL_DEPTH)
	add_child(_ball)


func _radial_gradient() -> GradientTexture2D:
	## Built once and shared. An earlier draft called this from `_apply_ball`,
	## so every frame allocated thirty-four 128x128 gradient textures: a 3,697
	## frame audit made 125,000 of them, ran twenty-eight seconds instead of
	## one, and took the engine down with a stack overflow during shutdown
	## *after* it had written a perfectly good audit file. The texture does not
	## depend on time, so there was never a reason to rebuild it.
	if _gradient != null:
		return _gradient
	var gradient := Gradient.new()
	gradient.set_color(0, Color(1.0, 1.0, 1.0, 1.0))
	gradient.set_color(1, Color(1.0, 1.0, 1.0, 0.0))
	var texture := GradientTexture2D.new()
	texture.gradient = gradient
	texture.fill = GradientTexture2D.FILL_RADIAL
	texture.fill_from = Vector2(0.5, 0.5)
	texture.fill_to = Vector2(1.0, 0.5)
	texture.width = 128
	texture.height = 128
	_gradient = texture
	return texture


func _label(size: int, colour: Color, top: float, letter_spacing: int = 0) -> Label:
	var label := Label.new()
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	label.vertical_alignment = VERTICAL_ALIGNMENT_TOP
	label.add_theme_font_size_override("font_size", size)
	label.add_theme_color_override("font_color", colour)
	if letter_spacing != 0:
		label.add_theme_constant_override("line_spacing", letter_spacing)
	label.set_anchors_preset(Control.PRESET_TOP_WIDE)
	label.offset_top = top
	label.offset_bottom = top + float(size) * 2.2
	# The safe margin keeps text off the edge where a phone's rounded corners
	# and a platform's own UI live.
	label.offset_left = float(_width) * SAFE_MARGIN_FRACTION
	label.offset_right = -float(_width) * SAFE_MARGIN_FRACTION
	return label


func _build_overlay() -> void:
	var layer := CanvasLayer.new()
	layer.name = "Overlay"
	add_child(layer)

	var root := Control.new()
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	layer.add_child(root)

	# The hook sits above the arena, in the band a near-circular arena leaves
	# empty in a 9:16 frame. No background panel: at this size the type is
	# already well clear of the arena's top vertex, and a panel would be the
	# busiest object in a frame whose whole argument is restraint.
	_hook_label = _label(int(float(_height) * 0.0305), TEXT_PRIMARY,
		float(_height) * HOOK_TOP_FRACTION)
	_hook_label.text = hook_text
	root.add_child(_hook_label)

	_counter_label = _label(int(float(_height) * 0.058), TEXT_PRIMARY,
		float(_height) * COUNTER_TOP_FRACTION)
	_counter_label.visible = show_counter
	root.add_child(_counter_label)

	_debug_label = _label(int(float(_height) * 0.019), TEXT_DIM,
		float(_height) * DEBUG_TOP_FRACTION)
	_debug_label.visible = show_debug
	root.add_child(_debug_label)


# ---------------------------------------------------------------------------
# Evaluating the playback. No integration anywhere below this line.
# ---------------------------------------------------------------------------


func _flight_index_at(t: float) -> int:
	var lo := 0
	var hi := _flight_times.size() - 1
	while lo < hi:
		var mid := (lo + hi + 1) / 2
		if _flight_times[mid] <= t:
			lo = mid
		else:
			hi = mid - 1
	return lo


## The ball at time `t`, in **doubles**.
##
## Separate from `position_at` because a `Vector2` stores 32-bit components in
## a standard Godot build, and rounding the playback to float32 costs about
## 5e-7 world units. That is a ten-thousandth of a pixel and nobody could see
## it - but it is also a hundred times the tolerance the playback audit exists
## to enforce, and an audit that had to allow 5e-7 could no longer tell "the
## renderer replayed the document" from "the renderer computed something very
## close to it". GDScript's own `float` is a double, so evaluating here and
## narrowing only at the point of drawing keeps the audit exact.
func position_pair(raw: float) -> Array:
	# Clamped to the run's end, exactly as `tile_playback.position_at` does.
	# The document defines the trajectory on [0, end_seconds]; past that the
	# last flight would carry the ball straight through the wall, and during
	# the completion hold that is several arena widths off frame.
	var t := minf(raw, _end_seconds)
	var flight: Dictionary = playback["flights"][_flight_index_at(t)]
	var dt := maxf(0.0, t - float(flight["t"]))
	var px := float(flight["p"][0])
	var py := float(flight["p"][1])
	var vx := float(flight["v"][0])
	var vy := float(flight["v"][1])
	return [
		px + vx * dt,
		py + vy * dt - 0.5 * _gravity * dt * dt,
	]


func position_at(raw: float) -> Vector2:
	var pair := position_pair(raw)
	return Vector2(pair[0], pair[1])


func activated_count_at(t: float) -> int:
	var lo := 0
	var hi := _activation_times.size()
	while lo < hi:
		var mid := (lo + hi) / 2
		if _activation_times[mid] <= t:
			lo = mid + 1
		else:
			hi = mid
	return lo


## Set the world to simulation time `t`. Every frame of every render goes
## through here and nothing else advances state, which is what makes the
## rendered frame a pure function of `t`.
func set_time(t: float) -> void:
	_time = t
	_apply_hits(t)
	_apply_tiles(t)
	_apply_ball(t)
	_apply_overlay(t)


func _apply_hits(t: float) -> void:
	## The most recent new hit and the most recent duplicate hit on each tile,
	## at or before `t`.
	##
	## Recomputed from the collision list every frame rather than carried
	## forward, so a still taken at 20 s is identical whether it was reached by
	## rendering 1,200 frames or by jumping straight there. A scene that
	## accumulated this would give a clip and a still different pictures of the
	## same instant, which is the class of bug this whole architecture exists to
	## make impossible.
	for i in _total_tiles:
		_last_new_hit[i] = -1.0e9
		_last_dup_hit[i] = -1.0e9
	for hit in playback["collisions"]:
		var when := float(hit["t"])
		if when > t:
			break
		var index := int(hit["tile"])
		if bool(hit["new"]):
			_last_new_hit[index] = when
		else:
			_last_dup_hit[index] = when


func _apply_tiles(t: float) -> void:
	var complete_at := _completion
	var completing := complete_at >= 0.0 and t >= complete_at
	var completion_pulse := 0.0
	if completing:
		completion_pulse = maxf(0.0,
			1.0 - (t - complete_at) / COMPLETION_PULSE_SECONDS)

	for i in _total_tiles:
		var material := _tile_materials[i]
		var lit := _last_new_hit[i] > -1.0e8
		var push := 0.0

		if lit:
			var since_new := t - _last_new_hit[i]
			# A decaying pulse, strongest at the instant of contact. `1 - x^2`
			# rather than a linear ramp so the tile is still visibly brighter a
			# tenth of a second later, which is about when the eye arrives.
			var pulse := 0.0
			if since_new < NEW_HIT_PULSE_SECONDS:
				var x := since_new / NEW_HIT_PULSE_SECONDS
				pulse = 1.0 - x * x
			# The duplicate response: brightness only, never a push, and capped
			# well under the new-hit pulse.
			var dup := 0.0
			var since_dup := t - _last_dup_hit[i]
			if _last_dup_hit[i] > -1.0e8 and since_dup < DUP_HIT_PULSE_SECONDS:
				var y := since_dup / DUP_HIT_PULSE_SECONDS
				dup = DUP_HIT_PULSE_SCALE * (1.0 - y * y)

			material.albedo_color = TILE_ACTIVE
			var emission := TILE_ACTIVE_EMISSION
			var energy := 1.35 + 2.6 * pulse + 1.1 * dup
			if completing:
				emission = TILE_ACTIVE_EMISSION.lerp(
					TILE_COMPLETE_EMISSION, completion_pulse)
				energy += 1.8 * completion_pulse
			material.emission = emission
			material.emission_energy_multiplier = energy
			push = NEW_HIT_PUSH * pulse
		else:
			material.albedo_color = TILE_INACTIVE
			material.emission = TILE_INACTIVE_EMISSION
			material.emission_energy_multiplier = 1.0

		# Outward, along the wall's own normal: the ball is travelling outward
		# when it arrives, so the tile recoiling away from the arena centre is
		# the direction the impact actually had. Inward would read as the wall
		# reaching for the ball.
		_tiles[i].position = _tile_home[i] + _tile_normal[i] * push


func _apply_ball(t: float) -> void:
	var here := position_at(t)
	_ball.position = Vector3(here.x, here.y, BALL_DEPTH)
	if _halo != null:
		_halo.position = Vector3(here.x, here.y, BALL_DEPTH - 0.05)

	if trail_mode != "temporal":
		return
	for i in _trail.size():
		# Sample backwards along the *canonical* path, so the trail bends at a
		# wall exactly where the ball did. A straight streak behind the ball
		# would draw a line through the wall on the frame after a bounce.
		var age := trail_seconds * float(i + 1) / float(_trail.size())
		var node := _trail[i]
		if t - age < 0.0:
			node.visible = false
			continue
		var fade := 1.0 - float(i) / float(_trail.size())
		var at := position_at(t - age)
		node.visible = true
		node.position = Vector3(at.x, at.y, BALL_DEPTH - 0.02)
		var width: float = TRAIL_TAIL_WIDTH + (TRAIL_HEAD_WIDTH - TRAIL_TAIL_WIDTH) * fade
		node.scale = Vector3(width, width, 1.0)
		# Only the alpha changes per frame. The texture was assigned at build
		# time and the mesh size is fixed; `scale` carries the taper.
		var material: StandardMaterial3D = node.material_override
		material.albedo_color = Color(
			TRAIL_COLOUR.r, TRAIL_COLOUR.g, TRAIL_COLOUR.b, 0.42 * fade * fade)


func _apply_overlay(t: float) -> void:
	var count := activated_count_at(t)
	if _counter_label != null:
		_counter_label.text = "%d / %d" % [count, _total_tiles]
		var colour := TEXT_PRIMARY
		if count >= _total_tiles:
			colour = TILE_ACTIVE
		elif count >= _total_tiles - 1:
			# One tile left. The counter is the only thing in the frame that
			# says so in words, and it changes colour a beat before the arena
			# does.
			colour = Color(1.0, 0.82, 0.55)
		_counter_label.add_theme_color_override("font_color", colour)
	if _debug_label != null and show_debug:
		_debug_label.text = "seed %d   t=%.2fs   %d collisions" % [
			int(playback["seed"]), t, int(playback["collisions"].size())]


## What the scene drew, for the audit. Reported rather than recomputed, so a
## disagreement between this and the canonical document is a real disagreement.
func audit_state() -> Dictionary:
	var lit: Array[int] = []
	for i in _total_tiles:
		if _last_new_hit[i] > -1.0e8:
			lit.append(i)
	var here := position_pair(_time)
	return {
		"t": _time,
		"activated": lit.size(),
		"lit": lit,
		"ball": here,
	}
