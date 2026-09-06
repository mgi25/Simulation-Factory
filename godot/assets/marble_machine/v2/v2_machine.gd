extends RefCounted

## The three-module machine: START -> BOWL -> TRACK, on one spine.
##
## A vertical slice of a larger tower, not a finished course. The brief stops
## the composition here deliberately - three modules built properly are worth
## more as a direction lock than seven built approximately - but the slice is
## proportioned so it reads as *part* of something: the pylons run past the
## start and past the last track sample at both ends, the plinth is sized for a
## taller machine than this one, and the track exits the bottom of the frame
## still descending.
##
## ## The layout, and the reason for the two-chute plan
##
##     19.80  START POD        eight bays, sign, gate, chassis
##              │  funnel, then the feed chute swinging LEFT
##     12.60  BOWL             dish, rim, acrylic shell, cradle
##              │  the S, swinging RIGHT then hooking back LEFT
##      1.95   exit, still descending
##      0.00   plinth
##
## The two chutes swing to opposite sides for the same compositional reason the
## prior lab found: a single S reads as a squiggle, and two curves mirroring
## around a central bowl read as a machine with a plan. It also means the
## machine's silhouette breaks outboard twice at different heights, which is
## what stops a stack of discs reading as a column.
##
## ## Metadata
##
## `module_table()` is the contract this branch hands to marble-v1. It records
## every anchor a physics pass would need - entries, exits, the bowl centre and
## drain, the channel's clear width, the marble diameter the art was drawn for -
## and it is derived from the same constants the geometry is built from, so it
## cannot drift away from what was rendered.

const Forms := preload("res://assets/marble_machine/lab_forms.gd")
const V2Forms := preload("res://assets/marble_machine/v2/v2_forms.gd")
const Start := preload("res://assets/marble_machine/v2/v2_start.gd")
const Bowl := preload("res://assets/marble_machine/v2/v2_bowl.gd")
const Track := preload("res://assets/marble_machine/v2/v2_track.gd")
const Spine := preload("res://assets/marble_machine/v2/v2_spine.gd")

const MARBLE_RADIUS := 0.285

const START_Y := 19.80
const START_Z := 0.55
const START_YAW := 0.16
const BOWL_Y := 12.60
const PLINTH_Y := 0.10
const PYLON_TOP := 21.40
const PANEL_LEVELS := [3.0, 7.4, 11.6, 15.8, 19.4]

# The feed chute: the funnel throat, out to the left, back over the bowl rim.
const FEED_CONTROLS := [
	Vector3(0.15, 19.20, 1.80),
	Vector3(-1.10, 18.50, 2.60),
	Vector3(-2.40, 17.30, 2.70),
	Vector3(-3.00, 15.90, 1.85),
	Vector3(-2.85, 14.55, 0.65),
	Vector3(-2.00, 13.55, 0.00),
]

# The S: bowl drain, out to the right, down, and hooking back left.
const S_CONTROLS := [
	Vector3(0.00, 11.44, 0.10),
	Vector3(1.20, 10.90, 1.25),
	Vector3(2.55, 10.05, 1.70),
	Vector3(2.95, 8.90, 0.80),
	Vector3(2.35, 7.85, -0.50),
	Vector3(0.90, 7.15, -1.15),
	Vector3(-0.90, 6.65, -0.90),
	Vector3(-2.20, 5.95, 0.15),
	Vector3(-2.70, 4.95, 1.45),
	Vector3(-2.20, 3.95, 2.45),
	Vector3(-0.75, 3.25, 2.80),
	Vector3(0.95, 2.65, 2.35),
	Vector3(2.05, 2.10, 1.30),
]


static func build(palette) -> Node3D:
	var root := Node3D.new()
	root.name = "MachineV2"

	root.add_child(Spine.backwall(palette, PLINTH_Y + 0.60, PYLON_TOP - 0.5,
		PANEL_LEVELS))
	root.add_child(Spine.build(palette, PLINTH_Y + 0.70, PYLON_TOP,
		PANEL_LEVELS))
	root.add_child(Spine.plinth(palette, PLINTH_Y))
	root.add_child(Spine.deck(palette, Vector3(0.0, 15.95, -2.65), 3.0, 3,
		"UpperDeck"))
	root.add_child(Spine.deck(palette, Vector3(0.0, 11.75, -2.65), 3.4, 11,
		"MidDeck"))
	root.add_child(Spine.deck(palette, Vector3(0.0, 7.55, -2.65), 3.6, 7,
		"LowerDeck"))

	# Yokes: three, all behind the modules, tying the pylons together.
	for entry in [[3.70, "YokeLow"], [9.60, "YokeMid"], [17.70, "YokeHigh"]]:
		root.add_child(Spine.yoke(palette, float(entry[0]), str(entry[1])))

	var bowl := Bowl.build(palette)
	bowl.name = "Bowl"
	bowl.position = Vector3(0.0, BOWL_Y, 0.0)
	root.add_child(bowl)

	var start := Start.build(palette)
	start.name = "Start"
	start.position = Vector3(0.0, START_Y, START_Z)
	start.rotation.y = START_YAW
	root.add_child(start)

	var sill := Start.build_sill(palette)
	sill.position = Vector3(0.0, START_Y, START_Z)
	sill.rotation.y = START_YAW
	root.add_child(sill)

	# The big entry flare is the start-to-bowl transition: the channel opens
	# to the full width of the start tray at its mouth and closes to single
	# file within two units, so eight lanes become one stream inside a part
	# that is visibly the same component as the rest of the track.
	var feed := Track.build(palette, FEED_CONTROLS, "FeedChute", {
		"bank_gain": 2.6, "bank_max": 20.0,
		"entry_flare": 0.80, "exit_flare": 0.10,
		"edge_light": "lit_cyan_line", "samples": 112,
	})
	root.add_child(feed)

	var main = Track.build(palette, S_CONTROLS, "SCurve", {
		"bank_gain": 3.4, "bank_max": 27.0,
		"entry_flare": 0.30, "exit_flare": 0.18,
		"edge_light": "neon_violet",
	})
	root.add_child(main)

	_brackets(root, palette, feed, main)
	_marbles(root, palette, feed, main)

	root.set_meta("feed_path", feed.get_meta("path"))
	root.set_meta("feed_banks", feed.get_meta("banks"))
	root.set_meta("s_path", main.get_meta("path"))
	root.set_meta("s_banks", main.get_meta("banks"))
	return root


static func _brackets(root: Node3D, palette, feed: Node3D,
		main: Node3D) -> void:
	## The few large brackets that carry the modules off the pylons.
	##
	## Six in total for the whole machine. Each one lands on a panel break, so
	## structure meets structure at a designed joint rather than wherever the
	## module happened to be.
	root.add_child(Spine.cantilever(palette, 1.0, 19.40,
		Vector3(1.45, 19.30, -0.65), "StartBracketR"))
	root.add_child(Spine.cantilever(palette, -1.0, 19.40,
		Vector3(-1.45, 19.30, -0.65), "StartBracketL"))
	root.add_child(Spine.cantilever(palette, 1.0, 11.60,
		Vector3(1.45, 11.70, -1.00), "BowlBracketR"))
	root.add_child(Spine.cantilever(palette, -1.0, 11.60,
		Vector3(-1.45, 11.70, -1.00), "BowlBracketL"))

	# Two saddles where the S passes closest to a pylon, so the track is
	# visibly carried rather than floating past its own supports.
	var path: Array = main.get_meta("path")
	var banks: Array = main.get_meta("banks")
	for entry in [[0.44, "SaddleUpper"], [0.72, "SaddleLower"]]:
		var t := float(entry[0])
		var index: int = clampi(int(round(t * float(path.size() - 1))),
			0, path.size() - 1)
		var frame: Basis = V2Forms.banked_basis(path, banks, index)
		var at: Vector3 = path[index] + frame.y * -1.15
		root.add_child(Spine.saddle(palette, at,
			atan2(frame.z.x, frame.z.z), str(entry[1])))
		root.add_child(Spine.cantilever(palette,
			1.0 if at.x > 0.0 else -1.0, at.y + 0.55,
			at + Vector3(0.0, 0.10, 0.0), "%sArm" % str(entry[1])))


static func _marbles(root: Node3D, palette, feed: Node3D,
		main: Node3D) -> void:
	## The field, placed for composition: eight on the line, six in the bowl,
	## four spread down the two chutes.
	##
	## Nothing here says anything about how a real field would distribute -
	## the physics phase owns that - but every module needs racers in it or
	## the machine reads as a museum piece rather than as something in use,
	## and the eight on the line are the brief's own "grand start" test.
	var sphere := SphereMesh.new()
	sphere.radius = MARBLE_RADIUS
	sphere.height = MARBLE_RADIUS * 2.0
	sphere.radial_segments = 28
	sphere.rings = 14

	var field := Node3D.new()
	field.name = "Field"
	root.add_child(field)

	var colour := 0
	var yaw := START_YAW
	for at in Start.bay_positions(MARBLE_RADIUS):
		var local: Vector3 = at
		var node := Forms.mesh_node(sphere, palette.marble(colour),
			"LineMarble%d" % colour)
		node.position = Vector3(START_Y * 0.0, START_Y, START_Z) + Vector3(
			local.x * cos(yaw) + local.z * sin(yaw), local.y,
			-local.x * sin(yaw) + local.z * cos(yaw))
		field.add_child(node)
		colour += 1

	# The bowl: six circulating, at radii and bearings that avoid the cradle
	# arms so every one of them is against the silver dish.
	for pair in [[2.42, 0.30], [1.95, 1.20], [2.62, -0.55], [1.35, -1.75],
			[1.80, 2.45], [2.20, -2.55], [2.55, 1.85], [1.55, 0.85],
			[2.30, 2.95], [1.15, -0.35]]:
		var radius: float = pair[0]
		var bearing: float = pair[1]
		# The dish's own profile, so a racer rests on the surface it is
		# drawn against rather than hovering over it.
		var t: float = clampf(
			(radius - Bowl.DRAIN_RADIUS) / (Bowl.DISH_RADIUS - Bowl.DRAIN_RADIUS),
			0.0, 1.0)
		var drop: float = -Bowl.DISH_DEPTH * (0.5 + 0.5 * cos(t * PI))
		var node := Forms.mesh_node(sphere, palette.marble(colour),
			"BowlMarble%d" % colour)
		node.position = Vector3(cos(bearing) * radius,
			BOWL_Y + drop + MARBLE_RADIUS * 0.94, sin(bearing) * radius)
		field.add_child(node)
		colour += 1

	for entry in [[feed, 0.30], [feed, 0.68], [main, 0.16], [main, 0.44],
			[main, 0.72], [main, 0.93]]:
		var chute: Node3D = entry[0]
		var t: float = entry[1]
		var node := Forms.mesh_node(sphere, palette.marble(colour),
			"ChuteMarble%d" % colour)
		node.position = Track.running_point(chute.get_meta("path"),
			chute.get_meta("banks"), t, MARBLE_RADIUS)
		field.add_child(node)
		colour += 1


static func module_table() -> Dictionary:
	## Anchors and dimensions marble-v1 will need to adapt physics to this art.
	##
	## World space, in the same units the scene is built in. Every value is
	## read from the constants the geometry uses, so a change to the layout
	## moves the recorded anchor with it.
	var feed_entry := Vector3(FEED_CONTROLS[0])
	var feed_exit := Vector3(FEED_CONTROLS[FEED_CONTROLS.size() - 1])
	var s_entry := Vector3(S_CONTROLS[0])
	var s_exit := Vector3(S_CONTROLS[S_CONTROLS.size() - 1])
	return {
		"marble_diameter": MARBLE_RADIUS * 2.0,
		"modules": {
			"start_v2": {
				"origin": Vector3(0.0, START_Y, START_Z),
				"yaw": START_YAW,
				"bays": Start.BAYS,
				"bay_pitch": Start.BAY_PITCH,
				"bay_floor_local_y": Start.TRAY_TOP,
				"entry_anchor": Vector3(0.0, START_Y + 0.30, START_Z - 1.0),
				"exit_anchor": feed_entry,
				"bounds": AABB(
					Vector3(-3.4, START_Y - 2.5, START_Z - 2.0),
					Vector3(6.8, 5.2, 5.6)),
				"preferred_camera": "start",
				"action_clearance": {
					"shape": "box",
					"centre": Vector3(0.0, START_Y + 0.5, START_Z + 0.9),
					"size": Vector3(6.6, 1.8, 3.4),
				},
			},
			"bowl_v2": {
				"origin": Vector3(0.0, BOWL_Y, 0.0),
				"rim_radius": Bowl.RIM_RADIUS,
				"dish_radius": Bowl.DISH_RADIUS,
				"dish_depth": Bowl.DISH_DEPTH,
				"drain_radius": Bowl.DRAIN_RADIUS,
				"centre": Vector3(0.0, BOWL_Y, 0.0),
				"drain": Vector3(0.0, BOWL_Y - Bowl.DISH_DEPTH, 0.0),
				"entry_anchor": feed_exit,
				"exit_anchor": s_entry,
				"bounds": AABB(
					Vector3(-4.6, BOWL_Y - 3.2, -4.6),
					Vector3(9.2, 5.2, 9.2)),
				"preferred_camera": "bowl",
				"action_clearance": Bowl.action_clearance(),
			},
			"track_v2_feed": {
				"controls": FEED_CONTROLS,
				"entry_anchor": feed_entry,
				"exit_anchor": feed_exit,
				"channel_clear_width": Track.clear_width(),
				"floor_offset": Track.floor_offset(),
				"preferred_camera": "track",
			},
			"track_v2_s": {
				"controls": S_CONTROLS,
				"entry_anchor": s_entry,
				"exit_anchor": s_exit,
				"channel_clear_width": Track.clear_width(),
				"floor_offset": Track.floor_offset(),
				"bank_max_degrees": 27.0,
				"preferred_camera": "track",
			},
		},
		"spine": {
			"pylon_x": Spine.PYLON_X,
			"pylon_z": Spine.PYLON_Z,
			"panel_levels": PANEL_LEVELS,
			"plinth_y": PLINTH_Y,
			"top_y": PYLON_TOP,
		},
	}
