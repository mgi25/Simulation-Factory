extends RefCounted

## TRACK V2 - the signature marble channel.
##
## The one asset in this branch that has to survive being photographed on its
## own. Everything else can lean on the composition; a track cannot, because a
## track is mostly repetition and repetition is where "procedural" shows.
##
## ## The cross-section, and why it has six features
##
## Read across the channel in its own rolled frame:
##
##        acrylic guard        chrome bead
##             ╲                    │
##              ╲   ╭───────────────▼──╮   ← rolled pearl lip
##               ╲ ╱                    ╲
##     ───────────╳──────────────────────╲──   ← recessed light line
##                │   silver running floor │
##                ╲                       ╱   ← full-round pearl shell
##                 ╲_____________________╱
##                    ╲               ╱       ← graphite keel
##                     ╲_____________╱
##
## Six features rather than two because of what the brief calls the medium
## layer. A U with a lip is a gutter: two radii, one silhouette, and at any
## distance where the whole track is in frame it presents exactly one highlight
## band down its length. This section presents four - the shell's shoulder, the
## rolled lip, the chrome bead and the floor's own dish - and four bands running
## down a curve is what makes the eye read a moulded profile instead of a
## sampled ribbon.
##
## The keel is a separate sweep in graphite, narrower and hung below. It exists
## because the brief requires a visible underside, and because from the hero
## camera a track's belly is a large share of its screen area: a white shell
## with a white underside has no bottom and floats.
##
## ## Why the section is per-sample
##
## `width_curve` flares the channel at its throat and at its mouth and pinches
## it through the fast middle. A constant section is an extrusion, and an
## extrusion is exactly the "sampled ribbon" the brief bans. It also does real
## work: the entry accepts a spread of marbles leaving a drain and the exit
## hands them on close to single file.
##
## ## Banking
##
## `V2Forms.auto_bank` rolls the whole section into every turn. Real banking is
## a named V2 requirement, and it is also the only reason the running floor
## stays visible through a hard turn from a twenty-degree camera: unbanked, the
## outer wall rises into the sightline and the marble vanishes behind it.

const Geometry := preload("res://scripts/toy_geometry.gd")
const Forms := preload("res://assets/marble_machine/lab_forms.gd")
const V2Forms := preload("res://assets/marble_machine/v2/v2_forms.gd")

# --- the profile ----------------------------------------------------------
#
# V2.2. The V2.1 channel met its width requirement and lost the silhouette
# doing it: at 2.72 across with a 0.41 wall each side it read as a road, and
# the racer inside looked small against all that white shell. The usable width
# is the same requirement; everything wrapped around it is now half as thick.
#
#            acrylic guard (lower)      chrome bead
#                    ╲                       │
#                     ╲   ╭─────────────────▼╮   thin rolled lip
#     ────────────────╳───╯                   ╰───── recessed light line
#                      ╲   polished running U   ╱
#                       ╲_____________________╱   slim pearl trough
#                          ╲               ╱      graphite keel, deep
#                            ╲___________╱
#
# Three changes, all aimed at the same thing - less white, more racer:
#
# **The floor is a real U.** A circular cradle of radius `FLOOR_RADIUS` rather
# than a nearly flat pan with a dip in it. A marble sitting in a cradle is held
# by it and reads as *in* the track; one sitting on a flat floor reads as on
# top of it. It is also what lets the walls be short.
#
# **The wall is thin.** 0.19 from the channel edge to the outer shoulder,
# against 0.41 before. The lip still rolls and still carries a bead, but there
# is no longer a slab of shell either side of the running surface.
#
# **The underside is graphite, not pearl.** The pearl trough now stops at
# `TROUGH_BASE` and a deep keel hangs below it, so the bottom half of every
# section in frame is dark. That is most of the "flat white surface" the review
# called out: it was never the running surface, it was the belly.
const CHANNEL_HALF := 0.94     # authored half width between the inner walls
const HERO_CLEAR_WIDTH := 1.88 # three 0.57 racers abreast plus clearance
const PROFILE_SCALE := HERO_CLEAR_WIDTH / (CHANNEL_HALF * 2.0)

const FLOOR_RADIUS := 2.20     # the running cradle's radius
const FLOOR_Y := -0.260        # the cradle's lowest point
const LIP_CROWN := 0.302
const SHELL_HALF := 1.130      # widest half width, at the shoulder
const TROUGH_BASE := -0.350    # underside of the pearl trough at the centre
const KEEL_TOP := -0.280
const KEEL_BOTTOM := -0.980
const KEEL_HALF := 0.720
const GUARD_HEIGHT := 0.26

const SAMPLES := 132
const RIB_SPACING := 1.70


static func clear_width() -> float:
	## The finished channel's clear span, for the module table.
	return HERO_CLEAR_WIDTH


static func floor_offset() -> float:
	## Where a marble's contact point sits, relative to the section origin.
	return FLOOR_Y * PROFILE_SCALE


static func _scaled(points: Array) -> Array:
	var out: Array = []
	for point in points:
		out.append((point as Vector2) * PROFILE_SCALE)
	return out


static func _floor_y_at(x: float) -> float:
	## The running cradle: a circular arc, not a dished pan.
	var span: float = clampf(absf(x), 0.0, CHANNEL_HALF)
	var rise := FLOOR_RADIUS - sqrt(maxf(
		FLOOR_RADIUS * FLOOR_RADIUS - span * span, 0.0))
	return FLOOR_Y + rise


static func channel_section() -> Array:
	## The pearl trough, authored as one half and mirrored.
	##
	## The walk starts at the trough's underside centreline and ends at the
	## cradle's centreline, so `mirror_close` puts the only seam underneath
	## where the keel covers it, and the point the marble actually runs on
	## lands mid-list with a neighbour either side and a properly averaged
	## normal.
	var half: Array = [
		# Underside of the trough, centre outwards. Shallow: the keel below
		# does the deep work, so this only has to close the section.
		Vector2(0.000, TROUGH_BASE),
		Vector2(0.450, -0.340),
		Vector2(0.780, -0.300),
		Vector2(0.980, -0.220),
		Vector2(1.080, -0.100),
		Vector2(1.115, 0.030),
		# The shoulder: the widest point, and the shell's main highlight.
		Vector2(SHELL_HALF, 0.160),
		# A thin rolled lip, over the top and back down inside.
		Vector2(1.115, 0.250),
		Vector2(1.075, 0.298),
		Vector2(1.030, LIP_CROWN),
		Vector2(1.000, 0.265),
		Vector2(0.985, 0.180),
		Vector2(0.970, 0.080),
		Vector2(0.950, -0.010),
	]
	# The cradle, wall foot to centreline.
	for step in range(4, -1, -1):
		var x: float = CHANNEL_HALF * float(step) / 4.0
		half.append(Vector2(x, _floor_y_at(x)))
	return _scaled(V2Forms.ensure_ccw(V2Forms.mirror_close(half)))


static func floor_section() -> Array:
	## The polished running insert laid in the cradle.
	##
	## Separate geometry from the trough because they are different materials,
	## and because a metal surface inside a pearl shell puts a hard value and
	## specular break exactly where the racer runs. That break is what stops a
	## track reading as one white stripe.
	var span := CHANNEL_HALF - 0.03
	var top: Array = []
	var bottom: Array = []
	var steps := 12
	for step in steps + 1:
		var x: float = lerpf(span, -span, float(step) / float(steps))
		top.append(Vector2(x, _floor_y_at(x) + 0.014))
		bottom.append(Vector2(-x, _floor_y_at(x) - 0.026))
	var points: Array = top
	points.append_array(bottom)
	points.append(top[0])
	return _scaled(V2Forms.ensure_ccw(points))


static func guard_section(side: float) -> Array:
	## One acrylic wall, standing on the lip: lower than V2.1's, and thinner.
	##
	## A guard is a safety rail, not a windscreen. At 0.44 it stood as tall as
	## the trough was deep and boxed the racer in from every camera above the
	## horizontal; at 0.26 it reads as trim on the lip and the marble stays the
	## tallest thing in the channel.
	var base := 0.280
	var inner := 1.002 * side
	var outer := 1.058 * side
	var mid := (inner + outer) * 0.5
	return _scaled(V2Forms.ensure_ccw([
		Vector2(inner, base),
		Vector2(outer, base),
		Vector2(outer, base + GUARD_HEIGHT - 0.07),
		Vector2(mid + (outer - mid) * 0.72, base + GUARD_HEIGHT - 0.015),
		Vector2(mid, base + GUARD_HEIGHT),
		Vector2(mid + (inner - mid) * 0.72, base + GUARD_HEIGHT - 0.015),
		Vector2(inner, base + GUARD_HEIGHT - 0.07),
		Vector2(inner, base),
	]))


static func keel_section() -> Array:
	## The graphite underside. Wide at the top and deep, because it is now the
	## whole bottom half of the track rather than a spine tucked under it.
	return _scaled(V2Forms.ensure_ccw([
		Vector2(KEEL_HALF, KEEL_TOP),
		Vector2(KEEL_HALF * 0.92, KEEL_BOTTOM + 0.46),
		Vector2(KEEL_HALF * 0.70, KEEL_BOTTOM + 0.20),
		Vector2(KEEL_HALF * 0.36, KEEL_BOTTOM + 0.04),
		Vector2(0.0, KEEL_BOTTOM),
		Vector2(-KEEL_HALF * 0.36, KEEL_BOTTOM + 0.04),
		Vector2(-KEEL_HALF * 0.70, KEEL_BOTTOM + 0.20),
		Vector2(-KEEL_HALF * 0.92, KEEL_BOTTOM + 0.46),
		Vector2(-KEEL_HALF, KEEL_TOP),
		Vector2(KEEL_HALF, KEEL_TOP),
	]))


static func width_curve(count: int, entry_flare: float,
		exit_flare: float) -> Array:
	## Lateral scale per sample: flared at the throat, pinched, flared out.
	var out: Array = []
	for index in count:
		var t := float(index) / float(maxi(count - 1, 1))
		# The flare collapses on a steep curve rather than a gentle one. A
		# gentle taper over a fifth of the run is a wing; a steep one is a
		# mouth, and a mouth is what a component that swallows eight lanes
		# should look like.
		var entry: float = entry_flare * pow(clampf(1.0 - t / 0.16, 0.0, 1.0), 2.5)
		var leaving: float = exit_flare * pow(
			clampf((t - 0.84) / 0.16, 0.0, 1.0), 2.2)
		var waist := -0.055 * sin(clampf((t - 0.18) / 0.62, 0.0, 1.0) * PI)
		out.append(1.0 + entry + leaving + waist)
	return out


static func build(palette, controls: Array, node_name: String,
		options: Dictionary = {}) -> Node3D:
	## One run of signature channel through `controls`.
	##
	## `options`: `bank_gain`, `bank_max`, `entry_flare`, `exit_flare`,
	## `edge_light` (a palette key), `ribs`, `samples`.
	var root := Node3D.new()
	root.name = node_name

	var samples := int(options.get("samples", SAMPLES))
	var path: Array = V2Forms.resample(Forms.smooth_path(controls, 26), samples)
	var banks: Array = V2Forms.auto_bank(path,
		float(options.get("bank_gain", 3.2)),
		float(options.get("bank_max", 26.0)))
	root.set_meta("path", path)
	root.set_meta("banks", banks)

	var widths := width_curve(path.size(),
		float(options.get("entry_flare", 0.14)),
		float(options.get("exit_flare", 0.09)))
	root.set_meta("widths", widths)

	var body := channel_section()
	var body_set: Array = V2Forms.scaled_sections(
		body, V2Forms.section_normals(body), path.size(), widths)
	root.add_child(Forms.mesh_node(
		V2Forms.banked_sweep(path, body_set[0], body_set[1], banks),
		palette.get_material("pearl_shell"), "Shell"))

	var floor_pts := floor_section()
	var floor_set: Array = V2Forms.scaled_sections(
		floor_pts, V2Forms.section_normals(floor_pts), path.size(), widths)
	root.add_child(Forms.mesh_node(
		V2Forms.banked_sweep(path, floor_set[0], floor_set[1], banks),
		palette.get_material("running_polished"), "RunningSurface", false))

	var keel := keel_section()
	var keel_set: Array = V2Forms.scaled_sections(
		keel, V2Forms.section_normals(keel), path.size(), widths)
	root.add_child(Forms.mesh_node(
		V2Forms.banked_sweep(path, keel_set[0], keel_set[1], banks),
		palette.get_material("graphite"), "Keel"))

	for side in [1.0, -1.0]:
		var guard := guard_section(side)
		var guard_set: Array = V2Forms.scaled_sections(
			guard, V2Forms.section_normals(guard), path.size(), widths)
		root.add_child(Forms.mesh_node(
			V2Forms.banked_sweep(path, guard_set[0], guard_set[1], banks),
			palette.get_material("acrylic_guard"),
			"Guard%s" % ("L" if side > 0.0 else "R"), false))

	_edge_details(root, palette, path, banks, widths,
		str(options.get("edge_light", "lit_cyan_line")))
	if bool(options.get("ribs", true)):
		_ribs(root, palette, path, banks, widths)
	return root


static func _edge_details(root: Node3D, palette, path: Array, banks: Array,
		widths: Array, light_key: String) -> void:
	## Chrome bead on each lip crown, lit line sunk into each shoulder.
	##
	## The light is a tube of emissive stock half-buried in the shell rather
	## than a bright face painted on it. A half-buried source lights the
	## surface around itself and keeps its own pixel count small, which is how
	## the reference's edge lines stay thin down a full-height tower instead
	## of blooming out into the white body.
	for side in [1.0, -1.0]:
		var suffix := "L" if side > 0.0 else "R"
		var bead: Array = []
		var light: Array = []
		for index in path.size():
			var factor: float = float(widths[index])
			var frame: Basis = V2Forms.banked_basis(path, banks, index)
			bead.append(path[index]
				+ frame.x * 1.030 * PROFILE_SCALE * factor * side
				+ frame.y * (LIP_CROWN + 0.018) * PROFILE_SCALE)
			light.append(path[index]
				+ frame.x * 1.148 * PROFILE_SCALE * factor * side
				+ frame.y * 0.128 * PROFILE_SCALE)
		root.add_child(Forms.mesh_node(
			Geometry.tube(bead, 0.026 * PROFILE_SCALE, 8),
			palette.get_material("chrome"), "Bead%s" % suffix, false))
		root.add_child(Forms.mesh_node(
			Geometry.tube(light, 0.044 * PROFILE_SCALE, 8),
			palette.get_material(light_key), "EdgeLight%s" % suffix, false))


static func _ribs(root: Node3D, palette, path: Array, banks: Array,
		widths: Array) -> void:
	## Transverse joints under the channel, at a fixed arc-length interval.
	##
	## The mechanical seam language: a graphite strap wrapping the underside
	## with a gold block on its keel, which is the collar-over-a-joint idea
	## applied along a length instead of at a point. They make the track read
	## as assembled from moulded sections rather than pulled in one piece, and
	## they give the belly something to catch a highlight on.
	var total: float = V2Forms.path_length(path)
	var count: int = maxi(int(total / RIB_SPACING), 2)
	# Sized and sited to hug the belly rather than to cross the widest part
	# of the shell: a strap as wide as the shoulder sticks out as two black
	# tabs and reads as a fin, which is the opposite of a joint.
	# Sited in the keel, not at the shoulder. At shoulder height the strap
	# passed straight through the running cradle - the trough is only 0.35
	# deep now, so there is no longer room for a band across its waist.
	var strap := Geometry.rounded_box(
		Vector3(1.70 * PROFILE_SCALE, 0.28 * PROFILE_SCALE, 0.17), 0.08, 3)
	var block := Geometry.rounded_box(
		Vector3(0.40 * PROFILE_SCALE, 0.20, 0.24), 0.07, 3)
	var ribs := Node3D.new()
	ribs.name = "Ribs"
	root.add_child(ribs)

	for step in count:
		var t := (float(step) + 0.5) / float(count)
		var index: int = clampi(int(round(t * float(path.size() - 1))),
			0, path.size() - 1)
		var frame: Basis = V2Forms.banked_basis(path, banks, index)
		var factor: float = float(widths[index])
		var centre: Vector3 = path[index] + frame.y * -0.54 * PROFILE_SCALE

		var node := Forms.mesh_node(strap, palette.get_material("graphite_soft"),
			"Rib%d" % step)
		node.transform = Transform3D(
			Basis(frame.x * factor, frame.y, frame.z), centre)
		ribs.add_child(node)

		var cap := Forms.mesh_node(block, palette.get_material("gold"),
			"RibBlock%d" % step, false)
		cap.transform = Transform3D(Basis(frame.x, frame.y, frame.z),
			centre + frame.y * -0.34)
		ribs.add_child(cap)


static func running_point(path: Array, banks: Array, t: float,
		marble_radius: float) -> Vector3:
	## Where a marble of `marble_radius` rests on the floor at fraction `t`.
	var at: float = clampf(t, 0.0, 1.0) * float(path.size() - 1)
	var index: int = clampi(int(round(at)), 0, path.size() - 1)
	var frame: Basis = V2Forms.banked_basis(path, banks, index)
	return Forms.sample_at(path, t) + frame.y * (marble_radius + floor_offset())
