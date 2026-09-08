extends Node3D

## The sloped-course lab scene. One layout, one world, one camera rig.
##
## A fourth lab, and an edit to none of the three before it: `hero_scene.gd`,
## `track_lab_scene.gd` and `lab_scene.gd` are untouched, so every proof already
## committed on the earlier branches still reproduces.
##
## ## Shots are derived, not typed
##
## A course is a route through a world, so the useful camera positions are
## *along* it. Every shot names a point on the route - a module anchor, or a
## fraction along a named run - and gives an elevation, a bearing relative to
## the track's own heading at that point, and a vertical extent. The rig then
## works out where to stand. That is what lets the same seven-shot table serve
## three structurally different layouts, and it is what stops a section camera
## quietly becoming another view of the whole course.

const Palette := preload("res://assets/marble_machine/lab_palette.gd")
const World := preload("res://assets/marble_machine/course/course_world.gd")
const Machine := preload("res://assets/marble_machine/course/course_machine.gd")
const Layout := preload("res://assets/marble_machine/course/course_layout.gd")
const Track := preload("res://assets/marble_machine/v2/v2_track.gd")
const V2Forms := preload("res://assets/marble_machine/v2/v2_forms.gd")
const Terrain := preload("res://assets/marble_machine/course/course_terrain.gd")

# at: ["node", name] or ["path", run, t]. `bearing` is measured from the
# track's own forward direction at the aim point - 0 looks up the course from
# in front of it, 90 is a side tracking position, 180 follows from behind.
static var SHOTS := {
	"hero": {"at": ["hero"], "extent": 0.0, "fov": 0.0, "elevation": 0.0,
		"bearing": 0.0},
	"phone": {"at": ["hero"], "extent": 0.0, "fov": 0.0, "elevation": 0.0,
		"bearing": 0.0},
	"start": {"at": ["node", "start"], "extent": 12.6, "fov": 34.0,
		"elevation": 18.0, "bearing": 26.0},
	"descent": {"at": ["path", "launch", 0.60], "extent": 14.0, "fov": 36.0,
		"elevation": 12.0, "bearing": 42.0},
	# Along the track, not across it. A side-on shot of a long straight shows
	# a line; a shot down its axis shows a road running away into the hill,
	# which is the only framing that makes "long" a fact rather than a claim.
	"long_track": {"at": ["path", "leg2", 0.34], "extent": 18.0, "fov": 36.0,
		"elevation": 10.0, "bearing": 16.0},
	"obstacle": {"at": ["node", "obstacle"], "extent": 9.5, "fov": 34.0,
		"elevation": 14.0, "bearing": 44.0},
	"split": {"at": ["node", "split"], "extent": 15.0, "fov": 34.0,
		"elevation": 17.0, "bearing": 24.0},
	"merge": {"at": ["node", "merge"], "extent": 14.0, "fov": 34.0,
		"elevation": 15.0, "bearing": 32.0},
	"final_run": {"at": ["path", "final", 0.46], "extent": 24.0, "fov": 36.0,
		"elevation": 13.0, "bearing": 40.0},
	"finish": {"at": ["node", "finish"], "extent": 24.0, "fov": 34.0,
		"elevation": 21.0, "bearing": 34.0},
}

# --- PRESENTATION CAMERA CANDIDATES --------------------------------------
#
# Candidates, not cuts. The final replay does not exist yet - the physics
# session still owns the start mechanism, the orange transition and the seed -
# so timing a cut list now would be timing it against a race that is going to
# change. What CAN be settled now, and what this table settles, is the shot
# LANGUAGE: where a camera stands for each kind of section, how high, how far
# round from the direction of travel, and how much of the course is in frame.
# A later pass picks moments; it does not have to rediscover angles.
#
# Nine sections from the brief, plus two frames that exist to photograph the
# work of this branch rather than the race: `environment` looks out across the
# valley so the haze, the ranges and the warm accents are actually in shot,
# and `track_materials` stands close enough to one length of channel to read
# the pearl against the silver.
#
# `candidate` keeps them out of `physics_layout.json`. The physics dump
# records the course's own cameras and must not gain eleven entries because a
# presentation branch was authored; these are published to
# `docs/validation/presentation_polish/cameras.json` instead.
#
# ## Two rules the numbers come from
#
# **A shot's `t` lands on a pack.** The display field puts marbles at fixed
# phases along each run, so an arbitrary `t` frames empty channel - which is
# the brief's first camera failure and it is entirely avoidable. The packs sit
# at 0.06, 0.40 and 0.68 (plus 0.96 on the sprint), so every candidate's `t`
# is within a few hundredths of one of those.
#
# **Elevation is bought against the guard.** The acrylic wall's top arris
# stands 0.23 above a racer's crown, so a side-on camera below about 27
# degrees sees the centre and near lanes through the acrylic rather than over
# it. That is acceptable at alpha 0.150 and it is measured rather than
# assumed - `_camera_report` writes the per-shot count into cameras.json - but
# it is why the hairpin and the split are the two highest candidates at 33 and
# 30 degrees, and why the two follow shots - the first descent at 11 and the
# final sprint at 162 degrees of bearing - are deliberately near-axial, where a
# guard is edge-on and occludes nothing at all whatever the elevation is.
const CANDIDATES := {
	"environment": {
		"at": ["path", "leg3", 0.40], "extent": 62.0, "fov": 42.0,
		"elevation": 9.0, "bearing": 118.0, "candidate": true,
		"style": "environment plate - out across the valley",
		"notes": "Looks off the flank rather than along it, so the layered"
			+ " haze, the three ranges, the warm outposts and the valley"
			+ " platforms are all in frame. The course crosses the lower"
			+ " third; it is the subject of the branch, not of this frame.",
	},
	"track_materials": {
		"at": ["path", "leg2", 0.40], "extent": 8.6, "fov": 30.0,
		"elevation": 22.0, "bearing": 52.0, "candidate": true,
		"style": "material plate - one length of channel, close",
		"notes": "Close enough that the pearl shoulder, the rolled lip, the"
			+ " chrome bead, the silver running insert and the graphite keel"
			+ " are five separable surfaces. Aimed at a pack rather than at a"
			+ " round number, because a material plate with no racer on it"
			+ " does not show the one thing the running surface is for.",
	},
	"start_event": {
		"at": ["node", "start"], "extent": 17.4, "fov": 34.0,
		"elevation": 20.0, "bearing": 30.0, "candidate": true,
		"style": "close three-quarter event view",
		"notes": "Extent up from the committed 12.6, which cropped both the"
			+ " sign and the outer bays at phone size. Non-geometric only:"
			+ " the start mechanism is the physics session's and nothing here"
			+ " touches it.",
	},
	"first_descent": {
		"at": ["path", "launch", 0.62], "extent": 13.0, "fov": 36.0,
		"elevation": 11.0, "bearing": 26.0, "candidate": true,
		"style": "low follow, from behind",
		"notes": "Low and in FRONT, looking back up the plunge, which is the"
			+ " reverse of what a follow shot usually means and is what the"
			+ " terrain forces. On this run behind means uphill: at bearing"
			+ " 158 the camera stood inside the hill and the ground crossed"
			+ " every sightline. Reversed to 26 the same low elevation reads"
			+ " the 32-degree plunge against the sky and the field comes at"
			+ " the lens. Near-axial, so the guards are edge-on.",
	},
	"fast_turn": {
		"at": ["path", "leg1", 0.60], "extent": 17.0, "fov": 36.0,
		"elevation": 24.0, "bearing": 70.0, "candidate": true,
		"style": "outside tracking",
		"notes": "On the outside of leg 1's long right-hander, where the"
			+ " bank rolls the running surface toward the lens. The rig picks"
			+ " the open side against the terrain, which on this leg is the"
			+ " gorge side and is also the correct one artistically.",
	},
	"hairpin": {
		"at": ["path", "leg2", 0.64], "extent": 19.0, "fov": 34.0,
		"elevation": 33.0, "bearing": 30.0, "candidate": true,
		"style": "high three-quarter",
		"notes": "Leg 2's hairpin against the rock wall. High enough that"
			+ " the reversal is legible as a shape and that the centre and"
			+ " far lanes clear the near guard rather than reading through"
			+ " it.",
	},
	"long_straight": {
		"at": ["path", "leg2", 0.36], "extent": 16.0, "fov": 36.0,
		"elevation": 11.0, "bearing": 22.0, "candidate": true,
		"style": "side follow, angled off square",
		"notes": "The brief asks for a side follow; the sloped-course pass"
			+ " found that square side-on makes a straight read as a line;"
			+ " and this frame settled the argument in favour of the second."
			+ " A side bearing was tried at 66, 48 and 42 and each one put"
			+ " the channel across the top third of a portrait frame with"
			+ " the rest of it hillside. At 22 the run recedes down the"
			+ " frame instead and carries five racers strung out along it,"
			+ " which is what makes 'long' a fact. It is still a follow -"
			+ " the camera is off the axis and ahead of the pack - it is"
			+ " just not square to it.",
	},
	"obstacle_action": {
		"at": ["path", "leg3", 0.05], "extent": 17.0, "fov": 34.0,
		"elevation": 22.0, "bearing": 48.0, "candidate": true,
		"style": "tight action, above the gantry",
		"notes": "Aimed at leg 3's entry rather than at the obstacle anchor,"
			+ " which is where the pack actually is, and raised to 22"
			+ " degrees, because at the committed 14 the spinner gantry's"
			+ " own legs crossed the channel and the racers behind them were"
			+ " read through two guard walls and a support. The extent is 17"
			+ " for a reason worth remembering: the frame is portrait and the"
			+ " camera keeps height, so `extent` is the VERTICAL span and the"
			+ " horizontal one is only 0.5625 of it. At 12 this shot framed"
			+ " under seven units across and lost the machinery off the"
			+ " left edge while reporting no occlusion at all.",
	},
	"split_wide": {
		"at": ["pair", "blue", 0.46, "orange", 0.46], "extent": 48.0,
		"fov": 38.0, "elevation": 30.0, "bearing": 6.0, "candidate": true,
		"style": "wide elevated, both branches",
		"notes": "Aimed at the midpoint of the two branches at matching"
			+ " progress, not at the split module. The committed shot aimed"
			+ " at the module with an extent of 15 and the branches diverge"
			+ " by 36 units, so neither route was in frame - the single"
			+ " worst framing failure on the course. Bearing 6 looks back up"
			+ " at the fork from below, which is the only station from which"
			+ " a choice reads as a choice.",
	},
	"final_sprint": {
		"at": ["path", "final", 0.64], "extent": 15.0, "fov": 36.0,
		"elevation": 20.0, "bearing": 162.0, "candidate": true,
		"style": "low forward tracking",
		"notes": "On the viaduct, behind the pack and nearly on the axis, so"
			+ " the girders and the valley run away underneath. Started at 8"
			+ " degrees on the brief's 'low forward tracking' and came up to"
			+ " 20: from under the deck the nearest trestle filled a third of"
			+ " the frame and the pack was a row of dots above it. Near-axial"
			+ " at 162, so the guards stay edge-on and the elevation costs"
			+ " nothing in occlusion.",
	},
	"finish_push": {
		"at": ["node", "finish"], "extent": 18.0, "fov": 34.0,
		"elevation": 16.0, "bearing": 42.0, "candidate": true,
		"style": "warm dramatic push-in",
		"notes": "Extent down from 24 and elevation down from 21: the"
			+ " committed frame read as a board seen from above with an empty"
			+ " deck. Lower and tighter puts the gantry sign against the sky"
			+ " and the arriving pack in the mouth. Paired with a sprint pack"
			+ " at phase 0.96 so there is something to finish.",
	},
}

# The motion proof's cut list. `shot` reuses a still's lens and animates the
# orbit and dolly across the cut; `follow` walks the aim along a named run and
# carries the camera with it. Explicitly not an orbit of the whole course - the
# brief's own rule, and the right one: a course this long has to be *travelled*
# by the camera or its length is a claim rather than an experience.
const SEQUENCE := [
	{"shot": "hero", "seconds": 0.9, "orbit": [-3.0, 3.0],
		"dolly": [0.05, -0.02]},
	{"shot": "start", "seconds": 1.2, "orbit": [-9.0, 5.0],
		"dolly": [0.12, -0.05]},
	{"follow": "leg1", "seconds": 1.5, "t": [0.16, 0.68], "extent": 11.5,
		"fov": 36.0, "elevation": 15.0, "bearing": 164.0},
	{"follow": "leg2", "seconds": 1.2, "t": [0.18, 0.70], "extent": 15.0,
		"fov": 34.0, "elevation": 17.0, "bearing": 74.0},
	{"shot": "obstacle", "seconds": 0.9, "orbit": [-11.0, 6.0],
		"dolly": [0.07, -0.03]},
	{"shot": "split", "seconds": 1.0, "orbit": [9.0, -9.0],
		"dolly": [0.06, -0.06]},
	{"shot": "finish", "seconds": 1.3, "orbit": [-13.0, 6.0],
		"dolly": [0.16, -0.07]},
]

# The camera proof's cut list, and it is a proof of the CAMERAS rather than a
# cut of a race. Eight seconds over six of the candidates, each held just long
# enough to see the move settle - what it is for is watching the pearl take a
# highlight as the lens swings, watching a guard's arris catch and lose the
# key, and watching the environment hold together across a cut. It cannot be
# the final race video: there is no race in it, the marbles are a display
# field moving at a constant rate, and the physics session has not frozen the
# start, the orange transition or the seed.
const POLISH_SEQUENCE := [
	{"shot": "start_event", "seconds": 1.2, "orbit": [-8.0, 5.0],
		"dolly": [0.10, -0.04]},
	{"shot": "first_descent", "seconds": 1.3, "orbit": [6.0, -6.0],
		"dolly": [0.12, -0.05]},
	{"shot": "fast_turn", "seconds": 1.3, "orbit": [-10.0, 6.0],
		"dolly": [0.08, -0.05]},
	{"shot": "obstacle_action", "seconds": 1.1, "orbit": [-9.0, 6.0],
		"dolly": [0.07, -0.03]},
	{"shot": "split_wide", "seconds": 1.6, "orbit": [8.0, -8.0],
		"dolly": [0.06, -0.06]},
	{"shot": "finish_push", "seconds": 1.5, "orbit": [-11.0, 5.0],
		"dolly": [0.18, -0.08]},
]

const DEFAULT_SHOT := "hero"

# `v2_track`'s guard strip, in profile units, for the occlusion test. Quoted
# here rather than imported because `v2_track` exposes the section as points
# and not as named edges, and reaching into that file to add accessors would
# be an edit to an asset four other branches' committed proofs render from.
const GUARD_X := 1.030
const GUARD_BASE := 0.280
const GUARD_TOP := 0.540

var _palette
var _camera: Camera3D
var _shot := DEFAULT_SHOT
var _layout := "a"
var _no_glow := false
var _course: Node3D
var _table: Dictionary
var _travellers: Array = []
var _orbit := 0.0
var _dolly := 0.0
var _fitted: Dictionary = {}
var _sequenced := false
var _action: Array = []
var _pier_cache: Array = []
var _camera_target := Vector3.ZERO
var _polish_cut := false


func _ready() -> void:
	var options := _options()
	_layout = str(options.get("layout", "a"))
	_shot = str(options.get("shot", DEFAULT_SHOT))
	_no_glow = str(options.get("no-glow", "")) != ""
	_sequenced = str(options.get("sequence", "")) != ""
	# `--sequence=polish` runs the candidate proof; any other truthy value
	# keeps the sloped-course cut list, so that clip still reproduces.
	_polish_cut = str(options.get("sequence", "")) == "polish"
	if not SHOTS.has(_shot):
		push_error("course_scene: unknown shot '%s'" % _shot)
		_shot = DEFAULT_SHOT

	# Shadow quality set here rather than in `project.godot`, so the earlier
	# labs' committed frames keep reproducing byte for byte from this branch.
	# A course a hundred and eighty units long puts far more world inside one
	# cascade than a tower did, and at the default atlas the terrace lips came
	# back as a row of sawteeth across the mountainside.
	RenderingServer.directional_shadow_atlas_set_size(8192, false)
	RenderingServer.directional_soft_shadow_filter_set_quality(
		RenderingServer.SHADOW_QUALITY_SOFT_HIGH)

	for name in CANDIDATES:
		SHOTS[name] = CANDIDATES[name]

	_palette = Palette.new("tower")
	_table = Layout.table(_layout)

	var world_env := WorldEnvironment.new()
	world_env.name = "WorldEnvironment"
	world_env.environment = World.build_environment(_no_glow)
	add_child(world_env)

	World.build_lights(self)
	add_child(World.build(_palette))

	_course = Machine.build(_palette, _layout, {
		"detail": str(options.get("detail", "block")),
	})
	# Adopt the terrain config the ground was actually built from.
	#
	# Without this the camera rig queries a copy that never received the
	# bench index, so `Terrain.height` reports the un-cut hill - which is
	# `cut_depth` too high everywhere the track runs, and the track is
	# exactly where every camera is looking. Two things were reading it: the
	# bearing probe that decides which side of a leg is the open one, and the
	# occlusion walk in `_terrain_blocks`. The occlusion walk is what found
	# it, by reporting three candidate cameras as one hundred per cent
	# blocked by ground while their rendered frames were clear - a figure too
	# round to be geometry.
	_table["terrain"] = _course.get_meta("terrain_cfg")
	add_child(_course)
	_practicals()
	_collect_travellers()
	_report()

	_build_camera()
	set_time(0.0)
	if str(options.get("dump-physics", "")) != "":
		_dump_physics(str(options["dump-physics"]))
	if str(options.get("dump-cameras", "")) != "":
		_dump_cameras(str(options["dump-cameras"]))


func _options() -> Dictionary:
	var options := {}
	for argument in OS.get_cmdline_user_args():
		var arg: String = argument
		if not arg.begins_with("--"):
			continue
		var split := arg.substr(2).split("=", true, 1)
		if split.size() == 2:
			options[split[0]] = split[1]
	return options


func _report() -> void:
	var metrics: Dictionary = _course.get_meta("metrics")
	print("layout %s: %s" % [_layout, str(_table["title"])])
	print("  length %.1f  drop %.1f  span x %.1f z %.1f  grade %.1f deg" % [
		metrics["length"], metrics["drop"], metrics["span_x"],
		metrics["span_z"], metrics["mean_grade_deg"]])
	print("  start->finish %.1f  clearance %.2f..%.2f  buried piers %d" % [
		metrics["start_to_finish"], metrics["min_clearance"],
		metrics["max_clearance"], metrics["buried_piers"]])


func _practicals() -> void:
	## One warm or cool omni at each race moment, following the colour story.
	var nodes: Dictionary = _table["nodes"]
	var lamps := [
		["start", "#6BE9FF", 2.6, 9.0, 2.2],
		["mix", "#A379FF", 2.6, 8.0, 1.8],
		["obstacle", "#FF9A48", 3.0, 9.5, 2.4],
		["split", "#EAF7FF", 2.4, 9.0, 2.6],
		["merge", "#FFC168", 2.8, 9.0, 2.0],
		["finish", "#FFC46A", 3.4, 14.0, 2.6],
	]
	for entry in lamps:
		var name := str(entry[0])
		if not nodes.has(name):
			continue
		var lamp := OmniLight3D.new()
		lamp.name = "Lamp%s" % name.capitalize()
		lamp.position = (nodes[name] as Vector3) + Vector3(0.0,
			float(entry[4]), 0.0)
		lamp.light_color = Color(str(entry[1]))
		lamp.light_energy = float(entry[2])
		lamp.omni_range = float(entry[3])
		lamp.omni_attenuation = 1.5
		lamp.shadow_enabled = false
		add_child(lamp)


func _collect_travellers() -> void:
	var field := _course.get_node_or_null("Field")
	if field == null:
		return
	for entry in _course.get_meta("travellers"):
		var record: Dictionary = entry
		var node: Node3D = field.get_node_or_null(str(record["node"]))
		if node == null:
			continue
		var run := str(record["run"])
		_travellers.append({
			"node": node,
			"path": _course.get_meta("%s_path" % run),
			"banks": _course.get_meta("%s_banks" % run),
			"scale": float(_course.get_meta("%s_scale" % run)),
			"lane": float(record["lane"]),
			"phase": float(record["phase"]),
		})


# --- camera ---------------------------------------------------------------


func _aim_of(spec: Dictionary) -> Dictionary:
	## Resolve a shot's `at` clause to a world point and a forward direction.
	var at: Array = spec["at"]
	var kind := str(at[0])
	if kind == "hero":
		var hero: Dictionary = _table["hero"]
		var fitted := _hero_fit()
		return {"point": fitted["aim"], "forward": Vector3(0.0, 0.0, 1.0),
			"distance": float(fitted["distance"]), "fov": float(hero["fov"]),
			"elevation": float(hero["elevation"]),
			"azimuth": float(hero["azimuth"])}

	var point := Vector3.ZERO
	var forward := Vector3(0.0, 0.0, 1.0)
	if kind == "pair":
		# The midpoint of two runs at matching progress, and the average of
		# their headings. The one primitive the section table was missing: a
		# split is the only race moment whose subject is not ON a run, and
		# aiming at either branch or at the module between them frames one
		# route and half of nothing.
		var first: Array = _course.get_meta("%s_path" % str(at[1]))
		var second: Array = _course.get_meta("%s_path" % str(at[3]))
		var a := _sample_at(first, float(at[2]))
		var b := _sample_at(second, float(at[4]))
		point = (a + b) * 0.5
		forward = (_heading_on(first, float(at[2]))
			+ _heading_on(second, float(at[4]))).normalized()
	elif kind == "node":
		var nodes: Dictionary = _table["nodes"]
		point = nodes[str(at[1])]
		forward = _heading_near(point)
	else:
		var run := str(at[1]) if kind == "path" else _longest_run()
		var t: float = float(at[2]) if kind == "path" else float(at[1])
		var path: Array = _course.get_meta("%s_path" % run)
		point = _sample_at(path, t)
		forward = _heading_on(path, t)
	# Which way a bearing swings is decided by the ground, not by its sign.
	#
	# A side-on bearing of seventy-eight degrees is a tracking shot on one
	# layout and a camera buried in the mountain on the next, because "the
	# track's left" is uphill on a leg running one way and downhill on the leg
	# running back. So both candidates are tested against the terrain and the
	# one standing over lower ground wins. That is also the correct answer
	# artistically - the open side is the side with the view.
	var bearing: float = deg_to_rad(float(spec["bearing"]))
	var side := Vector3(forward.z, 0.0, -forward.x).normalized()
	var flat := Vector3(forward.x, 0.0, forward.z).normalized()
	var probe := 9.0
	var cfg: Dictionary = _table["terrain"]
	var left := point + side * probe
	var right := point - side * probe
	if Terrain.height(left.x, left.z, cfg) > Terrain.height(right.x, right.z, cfg):
		side = -side
	var direction := flat * cos(bearing) + side * sin(bearing)
	var fov: float = float(spec["fov"])
	var half := tan(deg_to_rad(fov) * 0.5)
	var distance: float = (float(spec["extent"]) * 0.5) / half
	return {"point": point, "forward": direction, "distance": distance,
		"fov": fov, "elevation": float(spec["elevation"]), "azimuth": NAN}


func _sample_at(path: Array, t: float) -> Vector3:
	var at: float = clampf(t, 0.0, 1.0) * float(path.size() - 1)
	var index: int = clampi(int(round(at)), 0, path.size() - 1)
	return path[index]


func _heading_on(path: Array, t: float) -> Vector3:
	var index: int = clampi(int(round(clampf(t, 0.0, 1.0)
		* float(path.size() - 1))), 1, path.size() - 2)
	var delta: Vector3 = (path[index + 1] as Vector3) - (path[index - 1] as Vector3)
	delta.y = 0.0
	if delta.length_squared() < 1.0e-8:
		return Vector3(0.0, 0.0, 1.0)
	return delta.normalized()


func _heading_near(point: Vector3) -> Vector3:
	## The direction of travel at the nearest sample of any run.
	var best := 1.0e9
	var heading := Vector3(0.0, 0.0, 1.0)
	for entry in _table["runs"]:
		var run := str((entry as Dictionary)["name"])
		var path: Array = _course.get_meta("%s_path" % run)
		for index in path.size():
			var distance: float = (path[index] as Vector3).distance_to(point)
			if distance < best:
				best = distance
				heading = _heading_on(path,
					float(index) / float(maxi(path.size() - 1, 1)))
	return heading


func _longest_run() -> String:
	var best := ""
	var longest := -1.0
	for entry in _table["runs"]:
		var spec: Dictionary = entry
		if str(spec["role"]) != "long":
			continue
		var path: Array = _course.get_meta("%s_path" % str(spec["name"]))
		var length: float = V2Forms.path_length(path)
		if length > longest:
			longest = length
			best = str(spec["name"])
	return best


## The establishing lens is solved, not typed.
##
## A course is a hundred and fifty units long and forty deep, so the distance
## that frames it depends on the *shape* of the layout as much as on its size -
## and three layouts with the same bounding box can need distances twenty per
## cent apart. Typing an extent per layout means every camera change is a
## re-measure, and the first study did exactly that and cropped all three.
##
## So the rig binary-searches the smallest distance at which every centreline
## sample and every module anchor falls inside the frame with `HERO_MARGIN` to
## spare, then shifts the aim to the middle of what it found and solves again.
## Two passes is enough; the second only ever moves it by a fraction.
const HERO_MARGIN := 0.09


func _course_points() -> Array:
	var points: Array = []
	for entry in _table["runs"]:
		var run := str((entry as Dictionary)["name"])
		points.append_array(_course.get_meta("%s_path" % run))
	for key in (_table["nodes"] as Dictionary):
		points.append((_table["nodes"] as Dictionary)[key])
	return points


func _aspect() -> float:
	var viewport := get_viewport()
	if viewport == null:
		return 0.5625
	var size := viewport.get_visible_rect().size
	if size.y <= 0.0:
		return 0.5625
	return size.x / size.y


func _direction(elevation: float, azimuth: float) -> Vector3:
	var e := deg_to_rad(elevation)
	var a := deg_to_rad(azimuth)
	return Vector3(sin(a) * cos(e), sin(e), cos(a) * cos(e))


func _fits(points: Array, camera_at: Vector3, target: Vector3,
		tan_h: float, tan_v: float) -> bool:
	var back := (camera_at - target).normalized()
	var right := Vector3.UP.cross(back)
	if right.length_squared() < 1.0e-8:
		right = Vector3.RIGHT
	right = right.normalized()
	var up := back.cross(right).normalized()
	for point in points:
		var v: Vector3 = (point as Vector3) - camera_at
		var depth := -v.dot(back)
		if depth < 0.5:
			return false
		if absf(v.dot(right)) > depth * tan_h:
			return false
		if absf(v.dot(up)) > depth * tan_v:
			return false
	return true


func _recentre(points: Array, camera_at: Vector3, target: Vector3) -> Vector3:
	var back := (camera_at - target).normalized()
	var right := Vector3.UP.cross(back).normalized()
	var up := back.cross(right).normalized()
	var lo := Vector2(1.0e9, 1.0e9)
	var hi := -lo
	for point in points:
		var v: Vector3 = (point as Vector3) - camera_at
		var depth := maxf(-v.dot(back), 0.5)
		var angular := Vector2(v.dot(right) / depth, v.dot(up) / depth)
		lo = Vector2(minf(lo.x, angular.x), minf(lo.y, angular.y))
		hi = Vector2(maxf(hi.x, angular.x), maxf(hi.y, angular.y))
	var mid := (lo + hi) * 0.5
	var reach := camera_at.distance_to(target)
	return target + right * mid.x * reach + up * mid.y * reach


func _hero_fit() -> Dictionary:
	if not _fitted.is_empty():
		return _fitted
	var hero: Dictionary = _table["hero"]
	var points := _course_points()
	var direction := _direction(float(hero["elevation"]),
		float(hero["azimuth"]))
	var tan_v := tan(deg_to_rad(float(hero["fov"])) * 0.5) * (1.0 - HERO_MARGIN)
	var tan_h := tan_v * _aspect()

	var target: Vector3 = hero["aim"]
	var distance := 100.0
	for _pass in 2:
		var lo := 6.0
		var hi := 3000.0
		for _step in 34:
			var mid := (lo + hi) * 0.5
			if _fits(points, target + direction * mid, target, tan_h, tan_v):
				hi = mid
			else:
				lo = mid
		distance = hi
		target = _recentre(points, target + direction * distance, target)
	_fitted = {"aim": target, "distance": distance}
	print("  hero lens: fov %.0f  elevation %.0f  azimuth %.0f  distance %.1f"
		% [float(hero["fov"]), float(hero["elevation"]),
			float(hero["azimuth"]), distance])
	return _fitted


func _build_camera() -> void:
	_camera = Camera3D.new()
	_camera.name = "CourseCamera"
	_camera.keep_aspect = Camera3D.KEEP_HEIGHT
	_camera.near = 0.15
	_camera.far = 2400.0
	add_child(_camera)
	_camera.current = true
	_place_camera(0.0, 0.0)


func _place_camera(orbit_offset: float, dolly: float) -> void:
	var spec: Dictionary = SHOTS[_shot]
	var aim := _aim_of(spec)
	var fov: float = float(aim["fov"])
	var elevation := deg_to_rad(float(aim["elevation"]))
	var distance: float = float(aim["distance"]) * (1.0 + dolly)
	var target: Vector3 = aim["point"]

	var direction: Vector3
	if not is_nan(float(aim["azimuth"])):
		var azimuth := deg_to_rad(float(aim["azimuth"]) + orbit_offset)
		direction = Vector3(sin(azimuth) * cos(elevation), sin(elevation),
			cos(azimuth) * cos(elevation))
	else:
		var flat: Vector3 = aim["forward"]
		var spun := flat.rotated(Vector3.UP, deg_to_rad(orbit_offset))
		direction = (spun * cos(elevation) + Vector3.UP * sin(elevation))
		direction = direction.normalized()

	_camera.fov = fov
	_camera.position = target + direction * distance
	_camera.look_at(target, Vector3.UP)
	_camera_target = target


func set_time(seconds: float) -> void:
	## Display motion only. Constant rate along each run; no physics implied.
	for entry in _travellers:
		var node: Node3D = entry["node"]
		var path: Array = entry["path"]
		var banks: Array = entry["banks"]
		var scale: float = float(entry["scale"])
		var t: float = fposmod(float(entry["phase"]) + seconds * 0.085, 1.0)
		var centre := Track.running_point(path, banks, t,
			Layout.MARBLE_RADIUS, scale)
		var index: int = clampi(int(round(t * float(path.size() - 1))), 0,
			path.size() - 1)
		var frame: Basis = V2Forms.banked_basis(path, banks, index)
		node.position = centre + frame.x * float(entry["lane"]) * scale

	if _sequenced:
		_place_sequence(seconds)
	else:
		_orbit = sin(seconds * 0.32) * 4.0
		_dolly = -0.03 * (1.0 - cos(seconds * 0.28))
		_place_camera(_orbit, _dolly)


func _place_sequence(seconds: float) -> void:
	## The camera for one instant of the cut list.
	var cuts: Array = POLISH_SEQUENCE if _polish_cut else SEQUENCE
	var total := 0.0
	for entry in cuts:
		total += float((entry as Dictionary)["seconds"])
	var clock: float = fposmod(seconds, maxf(total, 0.001))
	var cursor := 0.0
	for entry in cuts:
		var cut: Dictionary = entry
		var length: float = float(cut["seconds"])
		if clock > cursor + length and cut != cuts[cuts.size() - 1]:
			cursor += length
			continue
		var t: float = clampf((clock - cursor) / maxf(length, 0.001), 0.0, 1.0)
		# Eased across the cut, so a move settles rather than stopping dead.
		var eased := smoothstep(0.0, 1.0, t)
		if cut.has("follow"):
			var span: Array = cut["t"]
			_shot = "_follow"
			SHOTS["_follow"] = {
				"at": ["path", str(cut["follow"]),
					lerpf(float(span[0]), float(span[1]), eased)],
				"extent": float(cut["extent"]), "fov": float(cut["fov"]),
				"elevation": float(cut["elevation"]),
				"bearing": float(cut["bearing"]),
			}
			_place_camera(0.0, 0.0)
			return
		var orbit: Array = cut["orbit"]
		var dolly: Array = cut["dolly"]
		_shot = str(cut["shot"])
		_place_camera(lerpf(float(orbit[0]), float(orbit[1]), eased),
			lerpf(float(dolly[0]), float(dolly[1]), eased))
		return



# --- camera candidate verification ---------------------------------------


func _progress_table() -> Dictionary:
	## Cumulative course fraction at the start and end of every run.
	##
	## The two branches share one window rather than following each other:
	## they are alternatives, so a racer on either is at the same point in the
	## race, and a progress number that ran blue then orange would say the
	## choice takes twice as long as it does.
	var lengths: Dictionary = {}
	var trunk := 0.0
	var branch := 0.0
	for entry in _table["runs"]:
		var spec: Dictionary = entry
		var name := str(spec["name"])
		var length: float = V2Forms.path_length(
			_course.get_meta("%s_path" % name))
		lengths[name] = length
		if str(spec["role"]) == "branch":
			branch = maxf(branch, length)
		else:
			trunk += length
	var total: float = trunk + branch
	var out: Dictionary = {}
	var cursor := 0.0
	var branch_from := -1.0
	for entry in _table["runs"]:
		var spec: Dictionary = entry
		var name := str(spec["name"])
		var length: float = float(lengths[name])
		if str(spec["role"]) == "branch":
			if branch_from < 0.0:
				branch_from = cursor
			out[name] = [branch_from / total, (branch_from + branch) / total]
			continue
		if branch_from >= 0.0 and cursor < branch_from + branch:
			cursor = branch_from + branch
		out[name] = [cursor / total, (cursor + length) / total]
		cursor += length
	return out


func _action_points() -> Array:
	## Every running-surface point and every display racer, with provenance.
	##
	## The running surface rather than the centreline: a camera has to see
	## where a marble actually sits, and the cradle floor is a quarter of a
	## unit below the path and inside two guard walls.
	if not _action.is_empty():
		return _action
	var progress := _progress_table()
	for entry in _table["runs"]:
		var spec: Dictionary = entry
		var name := str(spec["name"])
		var path: Array = _course.get_meta("%s_path" % name)
		var banks: Array = _course.get_meta("%s_banks" % name)
		var scale: float = float(_course.get_meta("%s_scale" % name))
		var window: Array = progress[name]
		for index in path.size():
			var t := float(index) / float(maxi(path.size() - 1, 1))
			_action.append({
				"at": Track.running_point(path, banks, t,
					Layout.MARBLE_RADIUS, scale),
				"run": name, "t": t, "racer": false, "lane": 0.0,
				"scale": scale, "index": index,
				"progress": lerpf(float(window[0]), float(window[1]), t),
			})
	for entry in _travellers:
		var record: Dictionary = entry
		var node: Node3D = record["node"]
		var name := ""
		for spec in _table["runs"]:
			if _course.get_meta("%s_path" % str((spec as Dictionary)["name"])) \
					== record["path"]:
				name = str((spec as Dictionary)["name"])
				break
		var phase: float = float(record["phase"])
		var window: Array = progress.get(name, [0.0, 1.0])
		_action.append({
			"at": node.position, "run": name, "t": phase, "racer": true,
			"lane": float(record["lane"]), "scale": float(record["scale"]),
			"index": clampi(int(round(phase * float(
				(record["path"] as Array).size() - 1))), 0,
				(record["path"] as Array).size() - 1),
			"progress": lerpf(float(window[0]), float(window[1]), phase),
		})
	return _action


func _piers() -> Array:
	## Every support, as a vertical capsule: axis, radius, top, bottom.
	##
	## Read off the built scene rather than recomputed, so what is tested for
	## occlusion is what was photographed. The radius is the pier's own child
	## bounds projected onto the ground plane, which for a splayed trestle is
	## its foot spread and for a plinth is its box - both conservative in the
	## right direction, because a support that is reported as blocking and is
	## not costs a camera nudge, and one that blocks and is not reported costs
	## a reshoot after the physics is frozen.
	if not _pier_cache.is_empty():
		return _pier_cache
	for child in _course.get_children():
		if not str(child.name).begins_with("Support"):
			continue
		for entry in child.get_children():
			var pier: Node3D = entry
			var radius := 0.0
			var top := -1.0e9
			var bottom := 1.0e9
			var stack: Array = [pier]
			while not stack.is_empty():
				var node: Node = stack.pop_back()
				for grandchild in node.get_children():
					stack.append(grandchild)
				if not (node is VisualInstance3D):
					continue
				var box: AABB = (node as VisualInstance3D).get_aabb()
				var world := (node as Node3D).global_transform
				for corner in 8:
					var point: Vector3 = world * box.get_endpoint(corner)
					var local := point - pier.global_position
					radius = maxf(radius, Vector2(local.x, local.z).length())
					top = maxf(top, point.y)
					bottom = minf(bottom, point.y)
			if top < bottom:
				continue
			_pier_cache.append({"at": pier.global_position, "radius": radius,
				"top": top, "bottom": bottom, "name": str(pier.name)})
	return _pier_cache


func _terrain_blocks(from: Vector3, to: Vector3) -> bool:
	## Does the ground stand in front of `to`, seen from `from`?
	##
	## Walked rather than solved, because `height` is four octaves of value
	## noise plus a bench cut and has no closed form. Forty-eight steps over a
	## sightline of at most a hundred units is a sample every two units, which
	## is under the terrain's own cell size of 1.3 and so cannot step over a
	## ridge. The near end is skipped: a camera standing on the hill is
	## legitimately below the ground at its own feet.
	var cfg: Dictionary = _table["terrain"]
	var steps := 48
	for step in range(4, steps):
		var t := float(step) / float(steps)
		var probe: Vector3 = from.lerp(to, t)
		# A margin, so that grazing the bench lip a metre short of the target
		# is not reported as an occlusion. Below this the check fires on the
		# cut face the track itself sits in.
		if Terrain.height(probe.x, probe.z, cfg) > probe.y + 0.45:
			return true
	return false


func _support_blocks(from: Vector3, to: Vector3) -> String:
	## The name of the first support standing in the sightline, or "".
	var direction := to - from
	var span := direction.length()
	if span < 0.001:
		return ""
	direction /= span
	for entry in _piers():
		var pier: Dictionary = entry
		var axis: Vector3 = pier["at"]
		# Closest approach in plan, then a height test at that station: a
		# capsule test rather than a sphere, because a trestle is twelve
		# units tall and a sphere around it would swallow the whole frame.
		var to_axis := Vector2(axis.x - from.x, axis.z - from.z)
		var flat := Vector2(direction.x, direction.z)
		var flat_len := flat.length()
		if flat_len < 0.001:
			continue
		var along: float = to_axis.dot(flat / flat_len)
		if along <= 0.4 or along >= span * flat_len - 0.4:
			continue
		var reach: float = (to_axis - (flat / flat_len) * along).length()
		if reach > float(pier["radius"]):
			continue
		var at: Vector3 = from + direction * (along / flat_len)
		if at.y < float(pier["bottom"]) or at.y > float(pier["top"]):
			continue
		return str(pier["name"])
	return ""


func _through_guard(from: Vector3, record: Dictionary) -> bool:
	## Is this racer seen through an acrylic wall rather than over one?
	##
	## The wall is a thin vertical strip in the section's own rolled frame -
	## |x| at `GUARD_X`, y from `GUARD_BASE` to `GUARD_TOP` - so the test is
	## done in that frame: take the sightline into section coordinates at the
	## racer's own station and ask whether it crosses either strip. Working in
	## world space would need the swept guard mesh, whose bounding box is the
	## whole run.
	var path: Array = _course.get_meta("%s_path" % str(record["run"]))
	var banks: Array = _course.get_meta("%s_banks" % str(record["run"]))
	var index: int = int(record["index"])
	var frame: Basis = V2Forms.banked_basis(path, banks, index)
	var origin: Vector3 = path[index]
	var scale: float = float(record["scale"])
	var eye := Vector3(
		(from - origin).dot(frame.x), (from - origin).dot(frame.y),
		(from - origin).dot(frame.z))
	var target := Vector3(float(record["lane"]) * scale,
		(Layout.MARBLE_RADIUS + Track.floor_offset() * scale), 0.0)
	for side in [1.0, -1.0]:
		var wall: float = side * GUARD_X * scale
		# Only a wall the sightline actually passes through: same side as the
		# eye and between it and the racer.
		if (eye.x - wall) * (target.x - wall) >= 0.0:
			continue
		var t: float = (wall - eye.x) / (target.x - eye.x)
		var y: float = lerpf(eye.y, target.y, t)
		if y >= GUARD_BASE * scale and y <= GUARD_TOP * scale:
			return true
	return false


func _in_frame(point: Vector3) -> bool:
	var tan_v := tan(deg_to_rad(_camera.fov) * 0.5)
	var tan_h := tan_v * _aspect()
	var back := (_camera.position - _camera_target).normalized()
	var right := Vector3.UP.cross(back)
	if right.length_squared() < 1.0e-8:
		right = Vector3.RIGHT
	right = right.normalized()
	var up := back.cross(right).normalized()
	var v := point - _camera.position
	var depth := -v.dot(back)
	if depth < 0.2:
		return false
	return absf(v.dot(right)) <= depth * tan_h \
		and absf(v.dot(up)) <= depth * tan_v


func _camera_report(name: String) -> Dictionary:
	## One candidate, placed and then measured against the brief's own rules.
	var spec: Dictionary = SHOTS[name]
	_shot = name
	_place_camera(0.0, 0.0)
	var aim := _aim_of(spec)
	var focus: Vector3 = aim["point"]
	# The region a shot is about: everything within three quarters of the
	# framed extent of the aim point. Wider than that and a wide establishing
	# lens would be judged on track it is not asking anyone to look at.
	var reach: float = maxf(float(spec["extent"]) * 0.75, 6.0)

	var considered := 0
	var visible := 0
	var terrain_hits := 0
	var support_hits: Dictionary = {}
	var racers := 0
	var racers_visible := 0
	var racers_through_guard := 0
	var lo := 2.0
	var hi := -1.0
	for entry in _action_points():
		var record: Dictionary = entry
		var at: Vector3 = record["at"]
		if at.distance_to(focus) > reach:
			continue
		if not _in_frame(at):
			continue
		considered += 1
		lo = minf(lo, float(record["progress"]))
		hi = maxf(hi, float(record["progress"]))
		var blocked := false
		if _terrain_blocks(_camera.position, at):
			terrain_hits += 1
			blocked = true
		var pier := _support_blocks(_camera.position, at)
		if pier != "":
			support_hits[pier] = int(support_hits.get(pier, 0)) + 1
			blocked = true
		if not blocked:
			visible += 1
		if not bool(record["racer"]):
			continue
		racers += 1
		if not blocked:
			racers_visible += 1
		if _through_guard(_camera.position, record):
			racers_through_guard += 1

	var occlusions: Array = []
	if terrain_hits > 0:
		occlusions.append("terrain crosses %d of %d action samples"
			% [terrain_hits, considered])
	for pier in support_hits:
		occlusions.append("support %s crosses %d samples"
			% [str(pier), int(support_hits[pier])])
	if racers_through_guard > 0:
		occlusions.append("%d of %d racers read through an acrylic wall"
			% [racers_through_guard, racers])
	if racers == 0:
		occlusions.append("NO RACER IN FRAME - the shot is empty track")
	return {
		"name": name,
		"style": str(spec.get("style", "")),
		"position": _camera.position,
		"aim": focus,
		"fov": _camera.fov,
		"elevation_deg": float(spec["elevation"]),
		"bearing_deg": float(spec["bearing"]),
		"framed_extent": float(spec["extent"]),
		"target_region": {"centre": focus, "radius": reach,
			"at": spec["at"]},
		"progress_range": [snappedf(lo, 0.001), snappedf(hi, 0.001)]
			if hi >= lo else [],
		"action_samples_in_frame": considered,
		"action_samples_clear": visible,
		"racers_in_frame": racers,
		"racers_clear": racers_visible,
		"racers_through_guard": racers_through_guard,
		"known_occlusions": occlusions,
		"notes": str(spec.get("notes", "")),
	}


func _dump_cameras(path: String) -> void:
	## The camera-candidate file, with every clearance claim measured.
	##
	## Deliberately not a camera director. There is no interpolation, no cut
	## list and no selection logic here: this writes down where eleven cameras
	## stand and what each one can and cannot see, and a later pass that owns
	## the finished replay decides which of them to use and for how long.
	var records: Array = []
	var was := _shot
	for name in CANDIDATES.keys():
		records.append(_camera_report(str(name)))
	_shot = was
	_place_camera(0.0, 0.0)

	var empty: Array = []
	var occluded: Array = []
	for entry in records:
		var record: Dictionary = entry
		if int(record["racers_in_frame"]) == 0:
			empty.append(str(record["name"]))
		if int(record["action_samples_clear"]) \
				< int(record["action_samples_in_frame"]):
			occluded.append(str(record["name"]))

	var table := {
		"branch": "marble-sloped-presentation-polish",
		"layout": _layout,
		"status": "CANDIDATES, NOT CUTS. No timing, no selection, no final"
			+ " replay. Positions, lenses and bearings only, verified against"
			+ " the built scene.",
		"physics": "UNTOUCHED. This file changes no route, no collider, no"
			+ " module anchor and no metadata. Camera positions are the only"
			+ " thing in it that moved.",
		"verification": "Every clearance number is measured, not asserted."
			+ " Terrain occlusion is walked against course_terrain.height at"
			+ " 48 samples per sightline; support occlusion is a capsule test"
			+ " against the built piers' own bounds; guard occlusion is a"
			+ " strip crossing in the section's rolled frame.",
		"guard_geometry": {
			"note": "The acrylic wall's top arris stands 0.23 above a"
				+ " racer's crown, so a side-on camera below the elevations"
				+ " here sees a racer THROUGH the acrylic, not over it.",
			"clear_over_guard_deg": {"far_lane": 18.2, "centre_lane": 26.6,
				"near_lane": 46.4},
			"guard_top_above_marble_crown": 0.23,
		},
		"marble": {"radius": Layout.MARBLE_RADIUS},
		"empty_shots": empty,
		"shots_with_occlusion": occluded,
		"cameras": records,
	}
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		push_error("course_scene: cannot write %s" % path)
		return
	file.store_string(JSON.stringify(_jsonable(table), "  "))
	file.close()
	print("  cameras -> %s" % path)
	print("  candidates %d  empty %d  with occlusion %d" % [
		records.size(), empty.size(), occluded.size()])
	for entry in records:
		var record: Dictionary = entry
		print("    %-16s racers %d/%d  clear %d/%d  %s" % [
			str(record["name"]), int(record["racers_clear"]),
			int(record["racers_in_frame"]),
			int(record["action_samples_clear"]),
			int(record["action_samples_in_frame"]),
			"; ".join(record["known_occlusions"])])

# --- physics metadata -----------------------------------------------------


func _dump_physics(path: String) -> void:
	## Everything a PyBullet pass would need, and nothing it would not.
	##
	## Written from the *built* scene rather than from the layout table, so it
	## records the geometry that was actually photographed - the resampled
	## centrelines, the solved bank angles, the module yaws the placer worked
	## out - and cannot drift from it. Read it as a description of a shape, not
	## as a set of colliders: no collider in this branch exists.
	var metrics: Dictionary = _course.get_meta("metrics")
	var terrain: Dictionary = (_table["terrain"] as Dictionary).duplicate()
	terrain.erase("cut_index")

	var runs: Array = []
	for entry in _table["runs"]:
		var spec: Dictionary = entry
		var name := str(spec["name"])
		var path_points: Array = _course.get_meta("%s_path" % name)
		var banks: Array = _course.get_meta("%s_banks" % name)
		var scale: float = float(_course.get_meta("%s_scale" % name))
		runs.append({
			"name": name,
			"role": str(spec["role"]),
			"profile_scale": scale,
			"clear_width": Track.clear_width() * scale,
			"floor_offset": Track.floor_offset() * scale,
			"origin": path_points[0],
			"entry_socket": {"at": path_points[0],
				"heading_deg": rad_to_deg(_heading_on(path_points, 0.0).angle_to(
					Vector3(0.0, 0.0, 1.0)))},
			"exit_socket": {"at": path_points[path_points.size() - 1],
				"heading_deg": rad_to_deg(_heading_on(path_points,
					1.0).angle_to(Vector3(0.0, 0.0, 1.0)))},
			"length": V2Forms.path_length(path_points),
			"drop": float((path_points[0] as Vector3).y)
				- float((path_points[path_points.size() - 1] as Vector3).y),
			"slope_deg": _slope_profile(path_points),
			"bank_max_deg": _bank_extreme(banks),
			"bounds": _bounds(path_points, 1.13 * scale, 0.98 * scale, 0.32),
			"centreline": _thinned(path_points, 26),
		})

	var modules: Array = []
	var nodes: Dictionary = _table["nodes"]
	var course_modules := _course.get_node_or_null("Modules")
	if course_modules != null:
		for child in course_modules.get_children():
			var node: Node3D = child
			var key := node.name.to_lower()
			modules.append({
				"name": node.name,
				"origin": node.position,
				"yaw_deg": rad_to_deg(node.rotation.y),
				"anchor": nodes.get(key, node.position),
				"action_clearance": _module_clearance(node.name),
			})

	var cameras: Array = []
	var was := _shot
	for name in SHOTS.keys():
		if str(name).begins_with("_"):
			continue
		# The presentation candidates are published to their own file. This
		# dump describes the course, and it must not gain eleven camera
		# entries because an art branch was authored on top of it.
		if bool((SHOTS[name] as Dictionary).get("candidate", false)):
			continue
		_shot = str(name)
		_place_camera(0.0, 0.0)
		cameras.append({
			"name": str(name),
			"position": _camera.position,
			"aim": _aim_of(SHOTS[name])["point"],
			"fov": _camera.fov,
		})
	_shot = was
	_place_camera(0.0, 0.0)

	var table := {
		"branch": "marble-sloped-course-lab",
		"layout": _layout,
		"title": str(_table["title"]),
		"fairness": "UNVERIFIED. Nothing in this branch simulates. The start"
			+ " grid, the mixer pin rows and the two branch lengths are"
			+ " shapes, not proofs, and no lane-bias claim may be made from"
			+ " them until a PyBullet pass measures one.",
		"physics": "NOT ATTACHED. No collider, no solver, no seed. Every"
			+ " number here describes photographed geometry.",
		"marble": {"radius": Layout.MARBLE_RADIUS,
			"diameter": Layout.MARBLE_RADIUS * 2.0},
		"course": metrics,
		"terrain": terrain,
		"runs": runs,
		"modules": modules,
		"cameras": cameras,
	}
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		push_error("course_scene: cannot write %s" % path)
		return
	file.store_string(JSON.stringify(_jsonable(table), "  "))
	file.close()
	print("  physics -> %s" % path)


func _slope_profile(path: Array) -> Dictionary:
	## Gradient over the first, middle and last third of a run.
	var out := {}
	var names := ["entry", "middle", "exit"]
	for third in 3:
		var a: int = int(float(third) * float(path.size() - 1) / 3.0)
		var b: int = int(float(third + 1) * float(path.size() - 1) / 3.0)
		var run := 0.0
		for index in range(a, b):
			run += Vector2((path[index + 1] as Vector3).x
				- (path[index] as Vector3).x,
				(path[index + 1] as Vector3).z
				- (path[index] as Vector3).z).length()
		var fall: float = float((path[a] as Vector3).y) 			- float((path[b] as Vector3).y)
		out[names[third]] = rad_to_deg(atan(fall / maxf(run, 0.001)))
	return out


func _bank_extreme(banks: Array) -> float:
	var most := 0.0
	for value in banks:
		most = maxf(most, absf(float(value)))
	return rad_to_deg(most)


func _bounds(path: Array, half: float, below: float, above: float) -> Dictionary:
	var lo := Vector3(1.0e9, 1.0e9, 1.0e9)
	var hi := -lo
	for point in path:
		var p: Vector3 = point
		lo = Vector3(minf(lo.x, p.x - half), minf(lo.y, p.y - below),
			minf(lo.z, p.z - half))
		hi = Vector3(maxf(hi.x, p.x + half), maxf(hi.y, p.y + above),
			maxf(hi.z, p.z + half))
	return {"min": lo, "max": hi}


func _thinned(path: Array, count: int) -> Array:
	var out: Array = []
	for step in count:
		var index: int = clampi(int(round(float(step)
			* float(path.size() - 1) / float(count - 1))), 0, path.size() - 1)
		out.append(path[index])
	return out


func _module_clearance(name: String) -> Dictionary:
	## The volume each module needs kept free above the running surface.
	match name:
		"Start":
			return {"above": 1.10, "lateral": 3.30,
				"note": "eight bays at 0.63 pitch, gate bar at +0.26"}
		"Mixer":
			return {"above": 0.90, "lateral": 1.60,
				"note": "two staggered pin rows behind the window"}
		"Obstacle":
			return {"above": 1.70, "lateral": 1.80,
				"note": "three spinners, hub at +1.46, blade tips reach -0.05"}
		"Split":
			return {"above": 2.60, "lateral": 3.60,
				"note": "wedge nose on the centreline, portals at +/-2.05"}
		"Merge":
			return {"above": 1.20, "lateral": 2.60,
				"note": "two inlets at +/-1.10, one exit"}
		"Finish":
			return {"above": 4.20, "lateral": 6.30,
				"note": "deck 12.6 by 9.8, eight catch lanes at 1.32 pitch"}
	return {"above": 1.0, "lateral": 2.0, "note": ""}


func _jsonable(value):
	if value is Dictionary:
		var out := {}
		for key in value:
			out[str(key)] = _jsonable(value[key])
		return out
	if value is Array:
		var list: Array = []
		for item in value:
			list.append(_jsonable(item))
		return list
	if value is Vector3:
		return [snappedf(value.x, 0.001), snappedf(value.y, 0.001),
			snappedf(value.z, 0.001)]
	if value is float:
		return snappedf(value, 0.0001)
	return value


func shot_names() -> Array:
	return SHOTS.keys()


func set_shot(name: String) -> void:
	if SHOTS.has(name):
		_shot = name
		_place_camera(_orbit, _dolly)
