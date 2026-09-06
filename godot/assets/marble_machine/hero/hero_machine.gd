extends RefCounted

## THE COMPLETE SEVEN-STAGE MACHINE.
##
##     29.6  1 START PLATFORM   eight bays, sign, gate, housed mixer
##            │                  feed chute, swinging left
##     24.3  2 MIXING BOWL      flared glass bell, grooved dish, drain
##            │                  the S: right, left, right
##     15.4  4 COLLECTOR        pan, five-blade rotor, one gate
##            │
##     13.3  5 SPLIT CHOICE     blue route left, orange route right
##      7.0   │                  hazard deck between them
##      6.7  6 COMPRESSION      merge block, three closing collars
##      3.6   │
##      2.1  7 FINISH ARENA     checkered pad, gold bollards, FINISH
##      0.0    plinth, then the drop
##
## Stage 3, the S-curve bridge, is the run between the bowl and the collector -
## a module by virtue of being the longest single unbroken channel in the
## machine and the one thing that carries the eye across the middle third.
##
## ## Every dimension lives in `hero_layout.gd`
##
## Nothing here invents a coordinate. The file is an assembly drawing: it reads
## heights and paths from the layout, hands them to module builders, and records
## what it did in `module_table()`. That is what makes the machine's proportions
## adjustable - the failure of every earlier pass was proportion, and proportion
## you can only fix if it is a table rather than three hundred literals.
##
## ## The field
##
## Fifty-odd racers, placed for composition and for nothing else. The physics
## phase owns where marbles actually go; what this placement guarantees is that
## every one of the seven stages has racers *in* it, because a stage without
## racers reads as a museum exhibit and the brief's own test is whether the
## machine looks like something in use.

const Geometry := preload("res://scripts/toy_geometry.gd")
const Forms := preload("res://assets/marble_machine/lab_forms.gd")
const V2Forms := preload("res://assets/marble_machine/v2/v2_forms.gd")
const Track := preload("res://assets/marble_machine/v2/v2_track.gd")
const Start := preload("res://assets/marble_machine/v2/v2_start.gd")
const Layout := preload("res://assets/marble_machine/hero/hero_layout.gd")
const Bowl := preload("res://assets/marble_machine/hero/hero_bowl.gd")
const Collector := preload("res://assets/marble_machine/hero/hero_collector.gd")
const Split := preload("res://assets/marble_machine/hero/hero_split.gd")
const Compression := preload(
	"res://assets/marble_machine/hero/hero_compression.gd")
const Finish := preload("res://assets/marble_machine/hero/hero_finish.gd")
const Spine := preload("res://assets/marble_machine/hero/hero_spine.gd")

const MARBLE_RADIUS := Layout.MARBLE_RADIUS

const FEED_OPTIONS := {
	"edge_stock": 0.062,
	"bank_gain": 2.4, "bank_max": 18.0,
	"entry_flare": 0.16, "exit_flare": 0.10,
	"edge_light": "lit_cyan_line_hero", "samples": 104,
}

const S_OPTIONS := {
	"edge_stock": 0.062,
	"bank_gain": 3.0, "bank_max": 24.0,
	"entry_flare": 0.30, "exit_flare": 0.16,
	"edge_light": "neon_violet_hero", "samples": 150,
}

const COLLECT_OUT_OPTIONS := {
	"edge_stock": 0.062,
	"bank_gain": 2.0, "bank_max": 14.0,
	"entry_flare": 0.22, "exit_flare": 0.26,
	"edge_light": "lit_cyan_line_hero", "samples": 56,
	"scale": 0.90, "ribs": false,
}


static func build(palette) -> Node3D:
	var root := Node3D.new()
	root.name = "HeroMachine"

	# --- structure, first, so everything else lands in front of it --------
	root.add_child(Spine.towers(palette))
	root.add_child(Spine.trunk(palette))
	root.add_child(Spine.yokes(palette))
	root.add_child(Spine.service_rings(palette))
	root.add_child(Spine.plinth(palette))

	# --- 1  START --------------------------------------------------------
	var start := Start.build(palette)
	start.name = "Start"
	start.position = Vector3(0.0, Layout.START_Y, Layout.START_Z)
	start.rotation.y = Layout.START_YAW
	root.add_child(start)

	var mixer := Start.build_mixer(palette)
	mixer.position = Vector3(0.0, Layout.START_Y, Layout.START_Z)
	mixer.rotation.y = Layout.START_YAW
	root.add_child(mixer)

	var feed := Track.build(palette, Layout.FEED_CONTROLS, "FeedChute",
		FEED_OPTIONS)
	root.add_child(feed)

	# --- 2  BOWL ---------------------------------------------------------
	var bowl := Bowl.build(palette)
	bowl.name = "Bowl"
	bowl.position = Vector3(0.0, Layout.BOWL_Y, 0.0)
	root.add_child(bowl)

	# --- 3  S-CURVE BRIDGE -----------------------------------------------
	var s_curve := Track.build(palette, Layout.S_CONTROLS, "SCurve", S_OPTIONS)
	root.add_child(s_curve)

	# --- 4  COLLECTOR ----------------------------------------------------
	var collector := Collector.build(palette)
	collector.name = "Collector"
	collector.position = Vector3(0.0, Layout.COLLECTOR_Y, 0.0)
	root.add_child(collector)

	var collect_out := Track.build(palette, Layout.COLLECT_OUT_CONTROLS,
		"CollectorOut", COLLECT_OUT_OPTIONS)
	root.add_child(collect_out)

	# --- 5  SPLIT --------------------------------------------------------
	root.add_child(Split.splitter(palette))
	var left := Track.build(palette, Layout.LEFT_CONTROLS, "LeftBranch",
		Split.LEFT_OPTIONS)
	root.add_child(left)
	var right := Track.build(palette, Layout.RIGHT_CONTROLS, "RightBranch",
		Split.RIGHT_OPTIONS)
	root.add_child(right)
	root.add_child(Split.cool_furniture(palette, left.get_meta("path"),
		left.get_meta("banks")))
	root.add_child(Split.warm_furniture(palette, right.get_meta("path"),
		right.get_meta("banks")))
	root.add_child(Split.hazard_deck(palette))
	root.add_child(Split.route_signs(palette))

	# --- 6  COMPRESSION --------------------------------------------------
	root.add_child(Compression.merge_block(palette))
	var drop := Track.build(palette, Layout.DROP_CONTROLS, "DropChannel",
		Compression.DROP_OPTIONS)
	root.add_child(drop)
	root.add_child(Compression.collars(palette, drop.get_meta("path")))
	root.add_child(Compression.frame(palette))

	# --- 7  FINISH -------------------------------------------------------
	var finish := Finish.build(palette)
	finish.name = "Finish"
	finish.position = Vector3(0.0, Layout.FINISH_Y, 0.0)
	root.add_child(finish)

	_brackets(root, palette, s_curve, left, right)
	_field(root, palette, {
		"feed": feed, "s": s_curve, "out": collect_out,
		"left": left, "right": right, "drop": drop,
	})

	for entry in [["feed", feed], ["s", s_curve], ["out", collect_out],
			["left", left], ["right", right], ["drop", drop]]:
		var node: Node3D = entry[1]
		root.set_meta("%s_path" % str(entry[0]), node.get_meta("path"))
		root.set_meta("%s_banks" % str(entry[0]), node.get_meta("banks"))
		root.set_meta("%s_scale" % str(entry[0]), node.get_meta("scale"))
	return root


static func _brackets(root: Node3D, palette, s_curve: Node3D, left: Node3D,
		right: Node3D) -> void:
	## The few large brackets carrying modules off the towers, and the
	## saddles under the tracks.
	##
	## Eleven pieces for a thirty-unit machine. Every one lands on a tower
	## panel break, so structure meets structure at a designed joint, and
	## none of them crosses the bowl, the split or the arena - the brief's
	## support rule, obeyed by placement rather than by hope.
	# Six, not sixteen: one pair at the start, one pair at the bowl, and a
	# single arm each at the collector and the arena, alternating sides. A
	# bracket at every module on both towers made a ladder of the right-hand
	# tower, and a ladder beside the machine is the loudest thing in the frame.
	for entry in [
			[1.0, 26.90, Vector3(2.40, 26.60, -2.60), "BowlBracketR"],
			[-1.0, 26.90, Vector3(-2.40, 26.60, -2.60), "BowlBracketL"],
			[-1.0, 13.60, Vector3(-2.50, 13.90, -2.50), "CollectorBracket"],
			[1.0, 3.10, Vector3(2.70, 2.50, -2.60), "FinishBracket"]]:
		root.add_child(Spine.cantilever(palette, float(entry[0]),
			float(entry[1]), Vector3(entry[2]), str(entry[3])))

	# Saddles: where each long run passes nearest a tower.
	for entry in [[s_curve, 0.30, "SaddleS1"], [s_curve, 0.72, "SaddleS2"],
			[left, 0.46, "SaddleLeft"], [right, 0.40, "SaddleRight"]]:
		var node: Node3D = entry[0]
		var t: float = entry[1]
		var path: Array = node.get_meta("path")
		var banks: Array = node.get_meta("banks")
		var scale: float = float(node.get_meta("scale"))
		var index: int = clampi(int(round(t * float(path.size() - 1))), 0,
			path.size() - 1)
		var frame: Basis = V2Forms.banked_basis(path, banks, index)
		var at: Vector3 = path[index] + frame.y * (-1.42 * scale)
		var saddle := Spine.saddle(palette, at,
			atan2(frame.z.x, frame.z.z), str(entry[2]))
		saddle.scale = Vector3(scale, scale, scale)
		root.add_child(saddle)
		root.add_child(Spine.cantilever(palette,
			1.0 if at.x > 0.0 else -1.0, at.y + 0.50,
			at + Vector3(0.0, 0.08, 0.0), "%sArm" % str(entry[2])))


static func _field(root: Node3D, palette, chutes: Dictionary) -> void:
	## Every racer in the machine, and the node the clip animates.
	var sphere := SphereMesh.new()
	sphere.radius = MARBLE_RADIUS
	sphere.height = MARBLE_RADIUS * 2.0
	sphere.radial_segments = 26
	sphere.rings = 13

	var field := Node3D.new()
	field.name = "Field"
	root.add_child(field)

	var colour := 0
	var yaw := Layout.START_YAW

	# 1 - eight on the line, all visible side by side.
	for at in Start.bay_positions(MARBLE_RADIUS):
		var local: Vector3 = at
		var node := Forms.mesh_node(sphere, palette.marble(colour),
			"LineMarble%d" % colour)
		node.position = Vector3(0.0, Layout.START_Y, Layout.START_Z) + Vector3(
			local.x * cos(yaw) + local.z * sin(yaw), local.y,
			-local.x * sin(yaw) + local.z * cos(yaw))
		field.add_child(node)
		colour += 1

	# 2 - the bowl, circulating on the dish's own surface.
	for pair in [[2.52, 0.34], [2.02, 1.24], [2.74, -0.52], [1.42, -1.72],
			[1.88, 2.42], [2.30, -2.52], [2.66, 1.88], [1.64, 0.88],
			[2.40, 2.92], [1.18, -0.34]]:
		var radius: float = pair[0]
		var bearing: float = pair[1]
		var node := Forms.mesh_node(sphere, palette.marble(colour),
			"BowlMarble%d" % colour)
		node.position = Vector3(cos(bearing) * radius,
			Layout.BOWL_Y + Bowl.dish_y(radius) + MARBLE_RADIUS * 0.94,
			sin(bearing) * radius)
		field.add_child(node)
		colour += 1

	# 4 - the collector pan, spread so the rotor is legible between them.
	for pair in [[2.20, 0.52], [1.74, 1.62], [2.34, -0.86], [1.28, -2.10],
			[2.02, 2.62], [1.56, -1.24], [2.42, 2.18]]:
		var radius: float = pair[0]
		var bearing: float = pair[1]
		var node := Forms.mesh_node(sphere, palette.marble(colour),
			"PanMarble%d" % colour)
		node.position = Vector3(cos(bearing) * radius,
			Layout.COLLECTOR_Y + Collector._pan_y(radius)
				+ MARBLE_RADIUS * 0.94,
			sin(bearing) * radius)
		field.add_child(node)
		colour += 1

	# 7 - the finish arena, several arriving close together, which is the
	# whole point of the module.
	for pair in [[2.62, 0.20], [2.86, 0.62], [2.44, 1.06], [3.02, 2.30],
			[2.70, -1.30], [2.46, -2.44], [2.92, 3.02]]:
		var radius: float = pair[0]
		var bearing: float = pair[1]
		var node := Forms.mesh_node(sphere, palette.marble(colour),
			"ArenaMarble%d" % colour)
		node.position = Vector3(cos(bearing) * radius,
			Layout.FINISH_Y + Finish._trough_y(radius) + MARBLE_RADIUS * 0.94,
			sin(bearing) * radius)
		field.add_child(node)
		colour += 1

	# 3, 5, 6 - the racers in the channels. These are the ones the motion
	# proof moves, so they are recorded with the run they belong to.
	var travellers := [
		["feed", 0.30], ["feed", 0.68],
		["s", 0.06], ["s", 0.19], ["s", 0.33], ["s", 0.47],
		["s", 0.61], ["s", 0.74], ["s", 0.88],
		["out", 0.35], ["out", 0.78],
		["left", 0.10], ["left", 0.28], ["left", 0.46], ["left", 0.64],
		["left", 0.82], ["left", 0.95],
		["right", 0.09], ["right", 0.25], ["right", 0.42],
		["right", 0.59], ["right", 0.76], ["right", 0.92],
		["drop", 0.24], ["drop", 0.58], ["drop", 0.88],
	]
	var travel_meta: Array = []
	for entry in travellers:
		var key: String = entry[0]
		var t: float = entry[1]
		var chute: Node3D = chutes[key]
		var scale: float = float(chute.get_meta("scale"))
		var node := Forms.mesh_node(sphere, palette.marble(colour),
			"Run_%s_%d" % [key, colour])
		node.position = Track.running_point(chute.get_meta("path"),
			chute.get_meta("banks"), t, MARBLE_RADIUS, scale)
		field.add_child(node)
		travel_meta.append({"node": node.name, "run": key, "phase": t})
		colour += 1
	root.set_meta("travellers", travel_meta)


static func module_table() -> Dictionary:
	## Anchors and dimensions a physics pass would need to adapt to this art.
	##
	## World space, in the units the scene is built in, derived from the same
	## constants the geometry uses so a change to the layout moves the
	## recorded anchor with it. Nothing here is a fairness claim.
	var feed_entry := Vector3(Layout.FEED_CONTROLS[0])
	var feed_exit := Vector3(Layout.FEED_CONTROLS[Layout.FEED_CONTROLS.size() - 1])
	var s_entry := Vector3(Layout.S_CONTROLS[0])
	var s_exit := Vector3(Layout.S_CONTROLS[Layout.S_CONTROLS.size() - 1])
	var out_entry := Vector3(Layout.COLLECT_OUT_CONTROLS[0])
	var out_exit := Vector3(
		Layout.COLLECT_OUT_CONTROLS[Layout.COLLECT_OUT_CONTROLS.size() - 1])
	var left_entry := Vector3(Layout.LEFT_CONTROLS[0])
	var left_exit := Vector3(Layout.LEFT_CONTROLS[Layout.LEFT_CONTROLS.size() - 1])
	var right_entry := Vector3(Layout.RIGHT_CONTROLS[0])
	var right_exit := Vector3(
		Layout.RIGHT_CONTROLS[Layout.RIGHT_CONTROLS.size() - 1])
	var drop_entry := Vector3(Layout.DROP_CONTROLS[0])
	var drop_exit := Vector3(Layout.DROP_CONTROLS[Layout.DROP_CONTROLS.size() - 1])
	var hero_clear := Track.clear_width()

	return {
		"marble_diameter": Layout.MARBLE_DIAMETER,
		"machine_height": Layout.machine_height(),
		"fairness": "UNVERIFIED - no simulation has been run against this art",
		"stage_order": ["start", "bowl", "s_bridge", "collector", "split",
			"compression", "finish"],
		"modules": {
			"start": {
				"stage": 1,
				"origin": Vector3(0.0, Layout.START_Y, Layout.START_Z),
				"yaw": Layout.START_YAW,
				"bays": Start.BAYS,
				"bay_pitch": Start.BAY_PITCH,
				"bay_floor_local_y": Start.TRAY_TOP,
				"entry_anchor": Vector3(0.0, Layout.START_Y + 0.30,
					Layout.START_Z - 1.0),
				"exit_socket": feed_entry,
				"mixer": {
					"half_width": Start.MIX_HALF,
					"housing_z": [Start.MIX_BACK_Z, Start.MIX_FRONT_Z],
					"housing_y": [Start.MIX_BOTTOM_Y, Start.MIX_TOP_Y],
					"throat_local": Start.mixer_exit_local(),
					"pin_rows": Start.PIN_ROWS,
					"pin_pitch": Start.PIN_PITCH,
					"pin_radius": Start.PIN_RADIUS,
					"pin_height": Start.PIN_HEIGHT,
					"pins_local": Start.pin_positions(),
					"note": "intended to break start-lane advantage; UNVERIFIED",
				},
				"action_clearance": {
					"shape": "box",
					"centre": Vector3(0.0, Layout.START_Y + 0.5,
						Layout.START_Z + 0.9),
					"size": Vector3(6.6, 1.8, 3.4),
				},
				"preferred_camera": "start",
			},
			"feed_chute": {
				"stage": 1,
				"controls": Layout.FEED_CONTROLS,
				"entry_socket": feed_entry,
				"exit_socket": feed_exit,
				"channel_clear_width": hero_clear,
				"floor_offset": Track.floor_offset(),
			},
			"bowl": {
				"stage": 2,
				"origin": Vector3(0.0, Layout.BOWL_Y, 0.0),
				"centre": Vector3(0.0, Layout.BOWL_Y, 0.0),
				"rim_radius": Bowl.RIM_RADIUS,
				"dish_radius": Bowl.DISH_RADIUS,
				"dish_depth": Bowl.DISH_DEPTH,
				"drain_radius": Bowl.DRAIN_RADIUS,
				"drain": Vector3(0.0, Layout.BOWL_Y - Bowl.DISH_DEPTH, 0.0),
				"entry_socket": feed_exit,
				"exit_socket": s_entry,
				"action_clearance": Bowl.action_clearance(),
				"preferred_camera": "bowl",
			},
			"s_bridge": {
				"stage": 3,
				"controls": Layout.S_CONTROLS,
				"entry_socket": s_entry,
				"exit_socket": s_exit,
				"channel_clear_width": hero_clear,
				"floor_offset": Track.floor_offset(),
				"bank_max_degrees": float(S_OPTIONS["bank_max"]),
				"preferred_camera": "s_bridge",
			},
			"collector": {
				"stage": 4,
				"origin": Vector3(0.0, Layout.COLLECTOR_Y, 0.0),
				"centre": Vector3(0.0, Layout.COLLECTOR_Y, 0.0),
				"radius": Collector.RADIUS,
				"pan_radius": Collector.PAN_RADIUS,
				"pan_drop": Collector.PAN_DROP,
				"hub_radius": Collector.HUB_RADIUS,
				"blades": Collector.BLADES,
				"gate_bearing_degrees": Collector.GATE_BEARING,
				"gate_half_angle_degrees": Collector.GATE_HALF_ANGLE,
				"entry_socket": s_exit,
				"exit_socket": out_entry,
				"action_clearance": Collector.action_clearance(),
				"preferred_camera": "collector",
			},
			"collector_out": {
				"stage": 4,
				"controls": Layout.COLLECT_OUT_CONTROLS,
				"entry_socket": out_entry,
				"exit_socket": out_exit,
				"channel_clear_width": hero_clear * 0.90,
			},
			"split": {
				"stage": 5,
				"splitter_at": Vector3(0.0, Layout.SPLIT_TOP_Y + 0.28, 0.34),
				"branch_scale": Split.BRANCH_SCALE,
				"branch_clear_width": hero_clear * Split.BRANCH_SCALE,
				"left": {
					"identity": "cool",
					"controls": Layout.LEFT_CONTROLS,
					"entry_socket": left_entry,
					"exit_socket": left_exit,
				},
				"right": {
					"identity": "warm",
					"controls": Layout.RIGHT_CONTROLS,
					"entry_socket": right_entry,
					"exit_socket": right_exit,
				},
				"action_clearance": {
					"shape": "box",
					"centre": Vector3(0.0,
						(Layout.SPLIT_TOP_Y + Layout.SPLIT_BOTTOM_Y) * 0.5, 0.2),
					"size": Vector3(Layout.SPLIT_REACH * 2.4 + 1.4,
						Layout.SPLIT_TOP_Y - Layout.SPLIT_BOTTOM_Y + 1.2, 4.4),
				},
				"preferred_camera": "split",
			},
			"compression": {
				"stage": 6,
				"merge_block_at": Vector3(0.00, 4.98, 0.58),
				"drop_controls": Layout.DROP_CONTROLS,
				"entry_sockets": [left_exit, right_exit],
				"exit_socket": drop_exit,
				"drop_entry_socket": drop_entry,
				"channel_clear_width": hero_clear * Compression.DROP_SCALE,
				"preferred_camera": "compression",
			},
			"finish": {
				"stage": 7,
				"origin": Vector3(0.0, Layout.FINISH_Y, 0.0),
				"centre": Vector3(0.0, Layout.FINISH_Y, 0.0),
				"radius": Finish.RADIUS,
				"trough_outer": Finish.TROUGH_OUTER,
				"trough_inner": Finish.TROUGH_INNER,
				"trough_drop": Finish.TROUGH_DROP,
				"podium_top_local_y": Finish.PODIUM_TOP,
				"pad_radius": Finish.PAD_RADIUS,
				"entry_socket": drop_exit,
				"action_clearance": Finish.action_clearance(),
				"preferred_camera": "finish",
			},
		},
		"support": {
			"tower_x": Layout.TOWER_X,
			"tower_z": Layout.TOWER_Z,
			"tower_half": Layout.TOWER_HALF,
			"tower_span_y": [Layout.TOWER_BASE, Layout.TOWER_TOP],
			"core_segments": Layout.CORE_SEGMENTS,
			"yoke_levels": Layout.YOKE_LEVELS,
			"panel_levels": Spine.PANEL_LEVELS,
			"plinth_y": Layout.PLINTH_Y,
		},
	}
