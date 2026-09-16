extends Node3D

## Race #2, built from the collider the physics actually ran on.
##
## Race #1's renderer draws a *twin* of its course: `course_machine.gd` builds a
## visual copy from the same layout table the Python side transcribes, and
## `physics_layout.json` exists to check the two against each other. That is
## right for a course transcribed from a drawing, and it costs a validation
## module to keep honest.
##
## Race #2 has no drawing. `race2.export` writes out the very rings the
## `TrackRun` colliders were swept from, and this scene sweeps them into meshes.
## So a disagreement between what is simulated and what is photographed is not
## possible here rather than merely tested for, and adding a module to the
## course adds it to the film with no second edit.
##
## ## What is reused and what is new
##
## The world - sky, fog, the two-key light rig, the backdrop - is
## `course_world.gd` exactly as Race #1 calls it, at whatever environment
## profile is asked for. Nothing in `assets/marble_machine/environment/` is
## touched or extended: Race #2 is environment-independent by construction, and
## a contained stage will drop in through the same seam.
##
## The racers are `racer_visual.gd` and the palette is `lab_palette.gd`, both
## unchanged, so a Race #2 marble is the same object a Race #1 marble is.
##
## What is new is the course builder below, and the camera, which comes from a
## solved track in the same JSON shape `sloped.cameras` writes - including the
## cut-boundary correction, which is carried over verbatim because the defect it
## fixes is a property of the format and not of Race #1.
##
## Usage, after `--`:
##
##     --geometry=PATH      the course, from `race2.export.write_geometry`
##     --replay=PATH        the marble3d replay JSON
##     --cameras=PATH       the camera track JSON
##     --environment=ID     an environment profile; default is the shipped one
##     --contrast=v21       the readability pass; default on
##     --racers=meridian    racer appearance
##     --show=course|matte|all
##                          `course` hides the world and keeps its sky, for a
##                          geometry proof; `matte` hides the sky as well, for
##                          a coverage measurement

const Palette := preload("res://assets/marble_machine/lab_palette.gd")
const World := preload("res://assets/marble_machine/course/course_world.gd")
const EnvProfile := preload(
	"res://assets/marble_machine/environment/environment_profile.gd")
const EnvBuilder := preload(
	"res://assets/marble_machine/environment/environment_builder.gd")
const EnvWorld := preload(
	"res://assets/marble_machine/environment/environment_world.gd")
const RacerVisual := preload("res://assets/marble_machine/racers/racer_visual.gd")

const DEFAULT_CONTRAST := "v21"
## The world Race #2 is developed against: V26's shipped production
## environment, used unmodified as a test background. Nothing in this package
## polishes it or builds around a particular rock, and `--environment=` still
## overrides, which is what a contained stage will come through.
const DEFAULT_ENVIRONMENT := "aurora_valley_v26"
const DEFAULT_RACERS := "meridian"
const COURSE_LAYER := 1
const WORLD_LAYER := 2

var _palette
var _course_root: Node3D
var _camera: Camera3D
var _marbles: Array[Node3D] = []
var _actuators: Dictionary = {}
var _replay: Dictionary = {}
var _frame_times: PackedFloat32Array = PackedFloat32Array()
var _camera_track: Dictionary = {}
var _use_track := false
var _duration := 0.0
var _render_scale := 0.57
var _geometry: Dictionary = {}
var _contrast := DEFAULT_CONTRAST
var _racers := DEFAULT_RACERS


func _ready() -> void:
	var options := _options()
	_contrast = str(options.get("contrast", DEFAULT_CONTRAST))
	_racers = str(options.get("racers", DEFAULT_RACERS))
	if not RacerVisual.APPEARANCES.has(_racers):
		push_error("race2_scene: unknown --racers=%s" % _racers)
		_racers = DEFAULT_RACERS

	# A course 48 layout units long puts far more world inside one cascade than
	# a tower does; at the default atlas the guard rails come back as sawteeth.
	# Same setting, same reason, as `course_scene.gd`.
	RenderingServer.directional_shadow_atlas_set_size(8192, false)
	RenderingServer.directional_soft_shadow_filter_set_quality(
		RenderingServer.SHADOW_QUALITY_SOFT_HIGH)

	var environment_id := str(options.get("environment", DEFAULT_ENVIRONMENT))
	if environment_id != "" and not EnvProfile.has(environment_id):
		push_error("race2_scene: unknown environment '%s'" % environment_id)
		environment_id = ""
	var profile: Dictionary = EnvProfile.resolve(environment_id, _contrast)
	_palette = Palette.new("tower", _contrast, str(options.get("machine", "")))
	# **The profile's surface overrides, which Race #2 had never applied.**
	# `course_scene.gd:176` has always done this and this scene never did,
	# which did not show while Race #2 only ever drew the backdrop: the
	# overrides name world surfaces, and Race #2 built none of them. It
	# shows the moment a stage is built, because a contained profile paints
	# the room through exactly this table - and V27.2 in particular *is* one
	# leaf of it, `hall_panel_dark.specular`, so without this call the merge
	# correction that names the edition is not in the picture at all.
	#
	# Before anything is built, because the palette caches what it hands
	# out. The outdoor control is unaffected and measurably so: the V26
	# chain resolves to no palette overrides, and the control frame is byte
	# for byte the one it rendered before this line existed.
	EnvBuilder.apply_palette(_palette, profile)

	var show := str(options.get("show", "all"))
	var world_env := WorldEnvironment.new()
	world_env.name = "WorldEnvironment"
	world_env.environment = World.build_environment(false, _contrast, profile)
	# **`matte` is `course` with the sky taken away too.**
	#
	# `--show=course` hides the world's geometry and leaves its background, which
	# is the right answer for a geometry proof and the wrong one for a coverage
	# measurement: against a drawn sky every pixel of the frame is drawn, so
	# "how much of this frame is the machine" comes back as 100% in both worlds.
	# Clearing the background to black makes the same render a silhouette, and a
	# pixel that is lit in the silhouette is a pixel of machine or racer - which
	# is a fact about the frame rather than an inference from its colour.
	#
	# Lighting, grade and fog are left exactly as the profile sets them, so the
	# silhouette is the machine as this world lights it and not a flat matte.
	if show == "matte":
		world_env.environment.background_mode = Environment.BG_COLOR
		world_env.environment.background_color = Color(0.0, 0.0, 0.0)
	add_child(world_env)
	World.build_lights(self, _contrast, profile)
	if show == "all":
		add_child(World.build(_palette, profile))

	_build_course(str(options.get("geometry", "")))
	# **After the course, not before it.** The stage is sited against the
	# racing line and the stations, and both are read out of the geometry
	# `_build_course` has just parsed. Race #1 orders it the same way for
	# the same reason: `course_machine.gd` builds its world after its
	# ground, because the terrain config is not finished until then.
	if show == "all":
		_build_stage(profile)
	if str(options.get("replay", "")) != "":
		_load_replay(str(options["replay"]))
	if str(options.get("cameras", "")) != "":
		_load_cameras(str(options["cameras"]))
	_build_camera()
	set_time(0.0)


func _options() -> Dictionary:
	var out := {}
	for argument in OS.get_cmdline_user_args():
		var text := str(argument)
		if not text.begins_with("--"):
			continue
		var body := text.substr(2)
		var split := body.find("=")
		if split < 0:
			out[body] = "1"
		else:
			out[body.substr(0, split)] = body.substr(split + 1)
	return out


# --- the contained stage ----------------------------------------------------
#
# **Race #2 had no near world at all before this.** `course_world.build` is the
# backdrop and only the backdrop - sky masses, cloud band, aurora - while the
# architecture a contained profile authors lives in that profile's `world`
# section, which until now only Race #1 ever built, from `course_machine.gd`.
# So `--environment=contained_hall_v272` on this scene used to deliver the
# hall's sky, fog, grade and lights over nothing at all: a contained profile
# erases the outdoor backdrop, and there was no code path to replace it.
#
# This is the seam the header at the top of this file promised, and only it.
# Four limits, each a decision rather than an omission:
#
# 1. **Only the stage keys are built** - `deck`, `shell`, `pylons`, `canopy`,
#    `bays`. The eleven terrain-anchored features (`patches`, `ridges`,
#    `scarps`, `boulders`, `ravine`...) are skipped, because every one of them
#    is sited against a heightfield and Race #2's course does not stand on one.
#    The consequence that matters for a comparison is the useful one: a profile
#    that authors no stage - `aurora_valley_v26`, the outdoor control - reaches
#    `world_cfg.is_empty()` and adds nothing, so the control renders exactly
#    the frames it rendered before this edit.
#
# 2. **Nothing in the profile is rewritten.** The hall's radii, courses,
#    heights, patterns, materials and lit strips are V27.2's, to the leaf.
#
# 3. **The room is placed, because the profile cannot place it.** The hall
#    carries absolute heights - a deck at y = -80, a wall footed at -100 -
#    which are the terrace and the basin under Race #1's finish, and Race #2's
#    course does not descend a mountainside. So the stage is translated by one
#    rigid lift, derived below from the two courses' own numbers, and every
#    authored dimension keeps the value it was measured at. A *scale* would be
#    a redesign of the hall and is not done here: that the room comes out too
#    large for this course is a result this branch reports, not one it fixes.
#
# 4. **The lens keep-out is the profile's, when the profile carries one for
#    this course.** V29 dropped it, and was right to for what it was doing: the
#    78 points a V27 contained profile carries are decimated *Race #1* camera
#    paths, and applying them here would cull segments at positions no Race #2
#    lens ever visits - a room with holes in it for reasons belonging to
#    another film. But an empty guide is not a fix either, it is a missing
#    constraint, and V30 puts architecture close enough to the lens for that to
#    matter. So a V30 profile carries Race #2's own decimated camera A path,
#    written by `tools/race2_v30_stage.py keepout`, and this scene passes it
#    through unchanged.
#
#    It stays **profile data rather than the loaded track**, which is the rule
#    `environment_world.build` states and gives its reason for: a world that
#    avoided whichever camera happened to be loaded would be a different world
#    in the delivery and in the matte, and the subtraction between them is the
#    measurement. A profile with no keep-out gets an empty guide, exactly as
#    before, so every pre-V30 profile builds what it built.
#
#    The list is plan positions and the stage lift is purely vertical, so the
#    points are valid in both frames and no transform is applied to them.


## The stage keys, from `environment_stage.STAGE_ORDER`. Named here rather than
## read from there so that this scene builds architecture and nothing else even
## if a later edition teaches `environment_stage.gd` a sixth feature.
const STAGE_KEYS := ["deck", "shell", "pylons", "canopy", "bays"]

## How far under the lowest point of the racing line the room's floor is laid.
## Small on purpose: the floor is the datum the architecture stands on, and the
## gap between it and the course is a void nothing in the profile fills.
const STAGE_FLOOR_CLEARANCE := 2.0


func _build_stage(profile: Dictionary) -> void:
	if _geometry.is_empty():
		return
	var authored: Dictionary = EnvBuilder.world(profile)
	var world_cfg := {}
	for key in STAGE_KEYS:
		if authored.get(key, null) is Dictionary:
			world_cfg[key] = authored[key]
	if world_cfg.is_empty():
		return
	# Not a build key - `environment_world.BUILD_ORDER` has no entry for it -
	# so this adds a guide rather than a feature. See note 4 in the header.
	if authored.get("keepout", null) is Array:
		world_cfg["keepout"] = authored["keepout"]

	var centreline := _centreline()
	if centreline.is_empty():
		push_warning("race2_scene: no centreline; stage not built")
		return
	var floor_y := INF
	var low := Vector2(INF, INF)
	var high := Vector2(-INF, -INF)
	for entry in centreline:
		var point: Vector3 = entry
		floor_y = minf(floor_y, point.y)
		low = Vector2(minf(low.x, point.x), minf(low.y, point.z))
		high = Vector2(maxf(high.x, point.x), maxf(high.y, point.z))
	var centre := (low + high) * 0.5

	# **The datum is the highest deck surface, not the lowest.** A deck ring
	# refuses to build if its top would stand above the ground it is meant to
	# lie under - `environment_stage._deck` tests exactly that, and it is right
	# to, because a plate floating over a hillside is the artefact the test
	# exists to catch. On a flat floor that test becomes a constraint on where
	# the floor goes: put the ground at the top of the tallest ring and every
	# ring passes; put it one unit lower and the upper terrace silently
	# disappears.
	var datum := _stage_datum(world_cfg)
	var lift := (floor_y - STAGE_FLOOR_CLEARANCE) - datum

	var stage := Node3D.new()
	stage.name = "Stage"
	stage.position = Vector3(0.0, lift, 0.0)
	add_child(stage)

	# Sited in the stage's own frame: the racing line and the station anchors
	# come down by exactly the lift the node goes up by, so a form kept clear
	# of the course is kept clear of the course.
	var local: Array = []
	for entry in centreline:
		var point: Vector3 = entry
		local.append(Vector3(point.x, point.y - lift, point.z))
	var anchors := _station_nodes()
	var nodes := {}
	for key in anchors:
		var anchor: Vector3 = anchors[key]
		nodes[key] = Vector3(anchor.x, anchor.y - lift, anchor.z)

	var cfg := _flat_ground(centre, datum)
	var census: Dictionary = EnvWorld.build(stage, _palette, cfg, local, nodes,
		world_cfg)
	World.assign_layer(stage)
	stage.set_meta("stage_census", census)
	stage.set_meta("stage_lift", lift)

	# Printed, because a feature that built nothing is indistinguishable from a
	# subtle one in a still - `environment_world.build` says exactly that - and
	# on this course one of them does build nothing.
	var parts := PackedStringArray()
	for key in census:
		parts.append("%s %d" % [key, int(census[key])])
	print("stage: %s lift %.2f floor %.2f datum %.2f centre (%.2f, %.2f)"
		% [str(profile.get("id", "?")), lift, floor_y, datum, centre.x,
			centre.y])
	print("stage: census %s" % ", ".join(parts))
	var bays: Dictionary = world_cfg.get("bays", {})
	for key in (bays.get("sites", {}) as Dictionary):
		var site: Dictionary = (bays["sites"] as Dictionary)[key]
		var wanted := str(site.get("node", key))
		if not nodes.has(wanted):
			print("stage: bay '%s' wants node '%s', which this course has not"
				% [str(key), wanted])


func _stage_datum(world_cfg: Dictionary) -> float:
	## The height of the room's floor, in the profile's own frame.
	##
	## The top of the highest deck surface: what the architecture stands on and
	## what the ring test measures against. A stage with no deck falls back to
	## the highest wall foot, the only other absolute a shell carries.
	##
	## **Plates count, and the highest plate wins.** A V30 floor is a plate
	## field rather than a ring, and a datum that only knew about rings would
	## put a plate-floored stage at the shell's foot instead - which is
	## typically twenty units lower, so the room would sink and the course
	## would hang in the air above its own floor. `terrace` only ever steps a
	## plate *down* from `y`, so `y` plus half the thickness is the top of the
	## field whatever the terracing does.
	var deck: Dictionary = world_cfg.get("deck", {})
	var datum := -INF
	for entry in (deck.get("rings", []) as Array):
		var ring: Dictionary = entry
		datum = maxf(datum, float(ring.get("y", -20.0))
			+ float(ring.get("thickness", 3.0)) * 0.5)
	for entry in (deck.get("plates", []) as Array):
		var field: Dictionary = entry
		var cell: Array = field.get("cell", [18.0, 2.4, 18.0])
		var thickness := float(field.get("thickness",
			float(cell[1]) if cell.size() > 2 else 2.4))
		datum = maxf(datum, float(field.get("y", -3.0)) + thickness * 0.5)
	if datum > -INF:
		return datum
	var shell: Dictionary = world_cfg.get("shell", {})
	for entry in (shell.get("bands", []) as Array):
		var band: Dictionary = entry
		datum = maxf(datum, float(band.get("foot", -40.0)))
	return datum if datum > -INF else 0.0


func _flat_ground(centre: Vector2, level: float) -> Dictionary:
	## A terrain config whose `height()` is one number everywhere.
	##
	## `environment_stage.gd` asks `course_terrain.height()` where the ground is
	## under a pad, a pylon and a bay. Race #1 answers with its mountainside;
	## Race #2 has no ground at all, so the answer is the floor of the room.
	## Every term of that surface is switched off explicitly rather than left at
	## a default, because a default here is a slope nobody authored.
	return {
		"centre_x": centre.x,
		"centre_z": centre.y,
		"z_top": 0.0,
		"top_y": level,
		"grade": 0.0,
		"crest_rise": 0.0,
		"crest_scale": 1.0,
		"steps": [],
		"left_at": 0.0,
		"left_span": 1.0,
		"left_rise": 0.0,
		"gorge_at": 0.0,
		"gorge_span": 1.0,
		"gorge_depth": 0.0,
		"noise": 0.0,
		# The edge fade lerps toward `edge_y` past `edge_from`. With the two
		# heights equal it is an identity wherever it fires, so the floor stays
		# flat out to whatever radius the shell is authored at.
		"edge_from": 1.0e9,
		"edge_to": 1.0e9 + 1.0,
		"edge_y": level,
		"pads": [],
	}


func _centreline() -> Array:
	## Every run's path, concatenated, in layout units.
	##
	## The same samples `race2.spine` measures its arc length along, and the
	## same concatenation Race #1 hands its world builder. In layout units
	## because the profile is: the geometry is written in simulation units, and
	## `_render_scale` is the factor between the two.
	var out: Array = []
	for entry in _geometry.get("runs", []):
		var run: Dictionary = entry
		for sample in (run.get("path", []) as Array):
			var point: Array = sample
			out.append(Vector3(float(point[0]), float(point[1]),
				float(point[2])) * _render_scale)
	return out


func _station_nodes() -> Dictionary:
	## Each module's centre, by id, in layout units.
	##
	## The anchors a profile's `bays` sites name. Race #1's are `start`,
	## `split`, `obstacle`, `merge` and `finish`; Race #2's are its stations -
	## `studs`, `drum`, `sweep`, `pair`, `last` - plus `start` and `runout`. The
	## two sets share exactly one name, and a site naming any of the others is
	## skipped by `environment_stage._bays` rather than guessed at.
	var out := {}
	for entry in _geometry.get("modules", []):
		var module: Dictionary = entry
		var lowest := Vector3(INF, INF, INF)
		var highest := Vector3(-INF, -INF, -INF)
		var seen := false
		for mesh_entry in (module.get("meshes", []) as Array):
			var mesh: Dictionary = mesh_entry
			# `v` is flat - x, y, z, x, y, z - exactly as `_indexed_mesh`
			# reads it a few functions down. Strided rather than reshaped:
			# two readers of one array that disagree about its shape is the
			# bug this comment exists to stop coming back.
			var flat: Array = mesh.get("v", [])
			var index := 0
			while index + 2 < flat.size():
				var point := Vector3(float(flat[index]), float(flat[index + 1]),
					float(flat[index + 2]))
				lowest = Vector3(minf(lowest.x, point.x),
					minf(lowest.y, point.y), minf(lowest.z, point.z))
				highest = Vector3(maxf(highest.x, point.x),
					maxf(highest.y, point.y), maxf(highest.z, point.z))
				seen = true
				index += 3
		if seen:
			out[str(module.get("id", ""))] = (lowest + highest) * 0.5 \
				* _render_scale
	return out


# --- the course -----------------------------------------------------------


func _build_course(path: String) -> void:
	## Every run and every station, swept from the exported rings.
	if path.is_empty():
		push_error("race2_scene: --geometry= is required")
		return
	var text := FileAccess.get_file_as_string(path)
	if text.is_empty():
		push_error("race2_scene: cannot read geometry %s" % path)
		return
	var parsed = JSON.parse_string(text)
	if typeof(parsed) != TYPE_DICTIONARY:
		push_error("race2_scene: %s is not a course" % path)
		return
	_geometry = parsed
	_render_scale = float((_geometry.get("units", {}) as Dictionary).get(
		"render_scale", 0.57))

	# **One scaled node for the whole course, marbles included.** The geometry
	# and the replay are both in simulation units and the camera track is in
	# layout units; a uniform scale on one parent converts positions and radii
	# together, so there is no second multiply anywhere to forget.
	_course_root = Node3D.new()
	_course_root.name = "Course"
	_course_root.scale = Vector3(_render_scale, _render_scale, _render_scale)
	add_child(_course_root)

	var channel: StandardMaterial3D = _palette.get_material("track_silver")
	var structure: StandardMaterial3D = _palette.get_material("graphite")
	var hazard: StandardMaterial3D = _palette.get_material("hazard_machine")

	var runs: Array = _geometry.get("runs", [])
	var triangles := 0
	for entry in runs:
		var run: Dictionary = entry
		var node := MeshInstance3D.new()
		node.name = "Run_%s" % str(run["name"])
		node.mesh = _strip_mesh(run["rings"], int(run["section_points"]))
		node.material_override = channel
		node.layers = COURSE_LAYER
		node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
		_course_root.add_child(node)
		triangles += node.mesh.surface_get_arrays(0)[Mesh.ARRAY_INDEX].size() / 3

	for entry in _geometry.get("modules", []):
		var module: Dictionary = entry
		var holder := Node3D.new()
		holder.name = "Module_%s" % str(module["id"])
		_course_root.add_child(holder)
		var material := hazard if bool(module.get("station", false)) else structure
		for mesh_entry in module.get("meshes", []):
			var node := MeshInstance3D.new()
			node.name = "Shell"
			node.mesh = _indexed_mesh(mesh_entry)
			node.material_override = material
			node.layers = COURSE_LAYER
			holder.add_child(node)
			triangles += node.mesh.surface_get_arrays(0)[Mesh.ARRAY_INDEX].size() / 3

	# The moving parts. One box per actuator, posed from the replay every frame.
	var moving := Node3D.new()
	moving.name = "Actuators"
	_course_root.add_child(moving)
	for entry in _geometry.get("actuators", []):
		var record: Dictionary = entry
		var half: Array = record["half_extents"]
		var node := MeshInstance3D.new()
		node.name = str(record["key"])
		var box := BoxMesh.new()
		box.size = Vector3(float(half[0]), float(half[1]), float(half[2])) * 2.0
		node.mesh = box
		# A station's blades are hazard-coloured; the start's floor panels are
		# structure. Both are actuators, and colouring every actuator as a
		# hazard put an orange slab across the whole of the first shot.
		node.material_override = hazard if _is_station(str(record["module"])) else structure
		node.layers = COURSE_LAYER
		moving.add_child(node)
		_actuators[str(record["key"])] = node
		triangles += 12

	print("race2: %d runs, %d modules, %d actuators, %d triangles" % [
		runs.size(), (_geometry.get("modules", []) as Array).size(),
		_actuators.size(), triangles])


func _is_station(module_id: String) -> bool:
	for entry in _geometry.get("modules", []):
		var module: Dictionary = entry
		if str(module["id"]) == module_id:
			return bool(module.get("station", false))
	return false


func _strip_mesh(rings: Array, width: int) -> ArrayMesh:
	## A ring sweep, with the same winding `sloped.track.sweep_rings` uses.
	var vertices := PackedVector3Array()
	var indices := PackedInt32Array()
	var uvs := PackedVector2Array()
	var count := rings.size()
	for row in count:
		var ring: Array = rings[row]
		for column in width:
			vertices.append(Vector3(float(ring[column * 3]),
				float(ring[column * 3 + 1]), float(ring[column * 3 + 2])))
			uvs.append(Vector2(float(column) / float(maxi(width - 1, 1)),
				float(row) / float(maxi(count - 1, 1)) * 8.0))
	for row in count - 1:
		var base := row * width
		var above := base + width
		for column in width - 1:
			indices.append_array([base + column, above + column, base + column + 1])
			indices.append_array([base + column + 1, above + column, above + column + 1])
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_TEX_UV] = uvs
	arrays[Mesh.ARRAY_INDEX] = indices
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	# Generated rather than exported: the collider has no normals to export and
	# a per-face normal on a swept channel reads as facets at every sample.
	var tool := SurfaceTool.new()
	tool.create_from(mesh, 0)
	tool.generate_normals()
	return tool.commit()


func _indexed_mesh(entry: Dictionary) -> ArrayMesh:
	var raw: Array = entry["v"]
	var vertices := PackedVector3Array()
	for index in range(0, raw.size(), 3):
		vertices.append(Vector3(float(raw[index]), float(raw[index + 1]),
			float(raw[index + 2])))
	var indices := PackedInt32Array()
	for value in entry["i"]:
		indices.append(int(value))
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_INDEX] = indices
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	var tool := SurfaceTool.new()
	tool.create_from(mesh, 0)
	tool.generate_normals()
	return tool.commit()


# --- the replay -----------------------------------------------------------


func _load_replay(path: String) -> void:
	var text := FileAccess.get_file_as_string(path)
	if text.is_empty():
		push_error("race2_scene: cannot read replay %s" % path)
		return
	var parsed = JSON.parse_string(text)
	if typeof(parsed) != TYPE_DICTIONARY:
		push_error("race2_scene: %s is not a replay" % path)
		return
	_replay = parsed
	var frames: Array = _replay.get("frames", [])
	_frame_times = PackedFloat32Array()
	for frame in frames:
		_frame_times.append(float((frame as Dictionary)["t"]))
	_duration = _frame_times[_frame_times.size() - 1] if _frame_times.size() > 0 else 0.0

	var radius := 0.5
	var marbles: Array = _replay.get("marbles", [])
	if marbles.size() > 0:
		radius = float((marbles[0] as Dictionary).get("radius", 0.5))
	for index in marbles.size():
		var info: Dictionary = marbles[index]
		var node := RacerVisual.build(_palette.marble(int(info["id"])), radius,
			"Racer%d" % int(info["id"]), _racers)
		node.layers = COURSE_LAYER
		_course_root.add_child(node)
		_marbles.append(node)
	print("race2: %d frames, %.2f s, %d racers" % [
		frames.size(), _duration, _marbles.size()])


func _load_cameras(path: String) -> void:
	var text := FileAccess.get_file_as_string(path)
	if text.is_empty():
		push_error("race2_scene: cannot read camera track %s" % path)
		return
	var parsed = JSON.parse_string(text)
	if typeof(parsed) != TYPE_DICTIONARY:
		push_error("race2_scene: %s is not a camera track" % path)
		return
	_camera_track = parsed
	_use_track = true
	var cuts: Array = _camera_track.get("cuts", [])
	var names := PackedStringArray()
	for cut in cuts:
		var record: Dictionary = cut
		names.append("%s[%s] %.2f-%.2f" % [str(record["name"]),
			str(record.get("mode", "")), float(record["from"]), float(record["to"])])
	print("cameras: %d cuts  %s" % [cuts.size(), ", ".join(names)])


func _build_camera() -> void:
	_camera = Camera3D.new()
	_camera.name = "Camera"
	_camera.fov = 36.0
	_camera.near = 0.2
	_camera.far = 900.0
	_camera.current = true
	add_child(_camera)


func replay_duration() -> float:
	return _duration


func cut_names() -> PackedStringArray:
	var out := PackedStringArray()
	for cut in _camera_track.get("cuts", []):
		out.append(str((cut as Dictionary)["name"]))
	return out


func cut_starts() -> PackedFloat32Array:
	## When each cut begins, in seconds. Used by the clip renderer.
	##
	## **A hard cut needs two draws, not one.** Screen-space reflection and
	## ambient occlusion carry history, and the first draw after the camera
	## jumps resolves them against the previous frame's depth - which on the
	## `sprint` to `payoff` boundary of seed 8 produced a frame byte-identical
	## to the one before it, out of 1150. The stills path already takes two
	## draws for exactly this reason; the clip path takes one, because taking
	## two everywhere would double a five-minute render to remove a defect that
	## exists on eleven frames.
	var out := PackedFloat32Array()
	for cut in _camera_track.get("cuts", []):
		out.append(float((cut as Dictionary)["from"]))
	return out


func cut_midpoint(name: String) -> float:
	for cut in _camera_track.get("cuts", []):
		var record: Dictionary = cut
		if str(record["name"]) == name:
			return 0.5 * (float(record["from"]) + float(record["to"]))
	return 0.0


func set_time(seconds: float) -> void:
	if _replay.is_empty():
		return
	var frames: Array = _replay["frames"]
	var pair := _frame_pair(seconds)
	var low: Dictionary = frames[int(pair[0])]
	var high: Dictionary = frames[int(pair[1])]
	var blend: float = float(pair[2])

	var low_marbles: Array = low["marbles"]
	var high_marbles: Array = high["marbles"]
	for index in _marbles.size():
		if index >= low_marbles.size():
			break
		var a: Dictionary = low_marbles[index]
		var b: Dictionary = high_marbles[index] if index < high_marbles.size() else a
		var node: Node3D = _marbles[index]
		node.position = _vec(a["p"]).lerp(_vec(b["p"]), blend)
		node.quaternion = _quat(a["q"]).slerp(_quat(b["q"]), blend)

	_place_actuators(low, high, blend)
	if _use_track:
		_place_from_track(seconds)


func _frame_pair(seconds: float) -> Array:
	var count := _frame_times.size()
	if count == 0:
		return [0, 0, 0.0]
	var fps := float(_replay.get("replay_fps", 60))
	var at: float = clampf(seconds, 0.0, _duration) * fps
	var low: int = clampi(int(floor(at)), 0, count - 1)
	var high: int = clampi(low + 1, 0, count - 1)
	var span: float = _frame_times[high] - _frame_times[low]
	var blend := 0.0
	if span > 1.0e-9:
		blend = clampf((clampf(seconds, 0.0, _duration) - _frame_times[low]) / span,
			0.0, 1.0)
	return [low, high, blend]


func _place_actuators(low: Dictionary, high: Dictionary, blend: float) -> void:
	## Every moving part, at the pose the physics had it at.
	##
	## Interpolated the same way a marble is, and for the same reason: the
	## output rate need not equal the replay rate, and a blade that snapped
	## between replay frames would strobe in a still taken between two.
	var a: Dictionary = low.get("actuators", {})
	var b: Dictionary = high.get("actuators", {})
	for key in _actuators:
		if not a.has(key):
			continue
		var node: Node3D = _actuators[key]
		# The replay writes an actuator pose as {"p": [...], "q": [...]},
		# not as a two-element array. A marble sample is the same shape.
		var first: Dictionary = a[key]
		var second: Dictionary = b[key] if b.has(key) else first
		node.position = _vec(first["p"]).lerp(_vec(second["p"]), blend)
		node.quaternion = _quat(first["q"]).slerp(_quat(second["q"]), blend)


func _vec(raw) -> Vector3:
	var values: Array = raw
	return Vector3(float(values[0]), float(values[1]), float(values[2]))


func _quat(raw) -> Quaternion:
	var values: Array = raw
	return Quaternion(float(values[0]), float(values[1]), float(values[2]),
		float(values[3])).normalized()


func _place_from_track(seconds: float) -> void:
	## The camera for one instant of the solved sequence.
	##
	## Carried over from `sloped_race_scene.gd` including the step-back at a cut
	## boundary, because the defect it fixes belongs to the format rather than
	## to Race #1: `to` is written to six places and the clock is `frame / fps`
	## at full precision, so at a boundary the search can fall through into the
	## next cut by a fraction of a microsecond and draw the frame after the
	## wanted one - which duplicates a frame and doubles the camera step across
	## the join.
	var cuts: Array = _camera_track.get("cuts", [])
	if cuts.is_empty():
		return
	var fps := float(_camera_track.get("fps", 60))
	var half := 0.5 / maxf(fps, 1.0)
	var index: int = cuts.size() - 1
	for i in range(cuts.size()):
		if seconds <= float((cuts[i] as Dictionary)["to"]):
			index = i
			break
	while index > 0:
		var previous: Array = (cuts[index] as Dictionary)["frames"]
		if previous.is_empty() or seconds >= float((previous[0] as Array)[0]) - half:
			break
		index -= 1
	var rows: Array = (cuts[index] as Dictionary)["frames"]
	if rows.is_empty():
		return
	var first := float((rows[0] as Array)[0])
	var at: float = (clampf(seconds, first, float((rows[rows.size() - 1] as Array)[0]))
		- first) * fps
	var low: int = clampi(int(floor(at)), 0, rows.size() - 1)
	var high: int = clampi(low + 1, 0, rows.size() - 1)
	var a: Array = rows[low]
	var b: Array = rows[high]
	var blend: float = clampf(at - float(low), 0.0, 1.0)

	var position := Vector3(float(a[1]), float(a[2]), float(a[3])).lerp(
		Vector3(float(b[1]), float(b[2]), float(b[3])), blend)
	var aim := Vector3(float(a[4]), float(a[5]), float(a[6])).lerp(
		Vector3(float(b[4]), float(b[5]), float(b[6])), blend)
	_camera.fov = lerpf(float(a[7]), float(b[7]), blend)
	_camera.position = position
	if position.distance_to(aim) > 1.0e-4:
		_camera.look_at(aim, Vector3.UP)
