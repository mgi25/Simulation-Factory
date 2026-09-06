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

# --- the profile. Authored at unit scale and multiplied by `PROFILE_SCALE`
# on the way out, so the whole cross-section can be resized against the rest
# of the machine without every one of its forty numbers being retyped - and
# without the shell, the floor, the keel, the guards, the beads and the light
# lines ever drifting apart from each other.
#
# The channel's own origin is the top of the floor at its centreline, so a
# marble's rest height is a single number.
const CHANNEL_HALF := 0.74     # authored half width between the inner walls
# V2.1: the finished channel's clear span, in world units. Three racers of
# 0.57 abreast plus working clearance - the V2 channel was 1.24, which is two
# marbles and change, and it read as undersized next to a bowl eleven marbles
# across. Everything else in the profile follows from this number, so the
# shell, floor, keel, guards, beads, light lines and joint straps all grow
# together and the section's proportions are untouched.
const HERO_CLEAR_WIDTH := 1.90
const PROFILE_SCALE := HERO_CLEAR_WIDTH / (CHANNEL_HALF * 2.0)
const FLOOR_Y := -0.100        # floor centre, below the section origin
const FLOOR_EDGE_Y := -0.055   # floor at the foot of the inner wall
const LIP_CROWN := 0.295       # top of the rolled lip
const SHELL_HALF := 1.060      # widest half width, at the shoulder
const BELLY_Y := -0.605        # underside of the pearl shell at the centreline
const KEEL_TOP := -0.500
const KEEL_BOTTOM := -0.980
const KEEL_HALF := 0.460
const GUARD_HEIGHT := 0.34

const SAMPLES := 132
const RIB_SPACING := 1.80


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
	## The dished running floor: flattest at the centre, rising to the walls.
	var t: float = clampf(absf(x) / (CHANNEL_HALF - 0.14), 0.0, 1.0)
	return lerpf(FLOOR_Y, FLOOR_EDGE_Y, t * t)


static func channel_section() -> Array:
	## The pearl body, authored as one half and mirrored.
	##
	## The walk starts at the belly centreline and ends at the floor
	## centreline, so `mirror_close` puts the only seam under the keel where
	## nothing sees it, and the floor's centre - where the marble runs and any
	## crease would show - lands in the middle of the list with a neighbour on
	## each side and a properly averaged normal.
	var half: Array = [
		# Underside, centre outwards.
		Vector2(0.000, BELLY_Y),
		Vector2(0.290, -0.590),
		Vector2(0.520, -0.545),
		Vector2(0.700, -0.470),
		Vector2(0.850, -0.360),
		Vector2(0.955, -0.230),
		Vector2(1.020, -0.090),
		# The shoulder: the widest point, and the shell's main highlight.
		Vector2(1.055, 0.040),
		Vector2(SHELL_HALF, 0.150),
		# The rolled lip, over the top and back down inside.
		Vector2(1.045, 0.225),
		Vector2(0.995, 0.278),
		Vector2(0.920, LIP_CROWN),
		Vector2(0.850, 0.268),
		Vector2(0.800, 0.210),
		# Inner wall, with a fillet into the floor.
		Vector2(0.775, 0.130),
		Vector2(0.760, 0.060),
		Vector2(0.735, 0.000),
		Vector2(0.685, -0.045),
	]
	for step in range(4, -1, -1):
		var x: float = (CHANNEL_HALF - 0.14) * float(step) / 4.0
		half.append(Vector2(x, _floor_y_at(x)))
	return _scaled(V2Forms.ensure_ccw(V2Forms.mirror_close(half)))


static func floor_section() -> Array:
	## A thin silver insert laid in the channel: the running surface proper.
	##
	## Separate geometry from the shell because they are different materials
	## in the brief's hierarchy, and because a silver floor inside a pearl
	## shell puts a value break exactly where the marble runs. That break is
	## what stops the whole track reading as one white stripe - the failure
	## the marble-v1 curve was called out for.
	var span := CHANNEL_HALF - 0.145
	var top: Array = []
	var bottom: Array = []
	var steps := 10
	for step in steps + 1:
		var x: float = lerpf(span, -span, float(step) / float(steps))
		top.append(Vector2(x, _floor_y_at(x) + 0.014))
		bottom.append(Vector2(-x, _floor_y_at(x) - 0.030))
	var points: Array = top
	points.append_array(bottom)
	points.append(top[0])
	return _scaled(V2Forms.ensure_ccw(points))


static func guard_section(side: float) -> Array:
	## One acrylic wall, standing on a lip: a thin blade with a rounded head.
	var base := 0.255
	var inner := 0.806 * side
	var outer := 0.862 * side
	var mid := (inner + outer) * 0.5
	return _scaled(V2Forms.ensure_ccw([
		Vector2(inner, base),
		Vector2(outer, base),
		Vector2(outer, base + GUARD_HEIGHT - 0.09),
		Vector2(mid + (outer - mid) * 0.72, base + GUARD_HEIGHT - 0.02),
		Vector2(mid, base + GUARD_HEIGHT),
		Vector2(mid + (inner - mid) * 0.72, base + GUARD_HEIGHT - 0.02),
		Vector2(inner, base + GUARD_HEIGHT - 0.09),
		Vector2(inner, base),
	]))


static func keel_section() -> Array:
	## The graphite belly: a narrow tapered spine hung under the shell.
	return _scaled(V2Forms.ensure_ccw([
		Vector2(KEEL_HALF, KEEL_TOP),
		Vector2(KEEL_HALF * 0.95, KEEL_BOTTOM + 0.24),
		Vector2(KEEL_HALF * 0.72, KEEL_BOTTOM + 0.07),
		Vector2(KEEL_HALF * 0.34, KEEL_BOTTOM),
		Vector2(-KEEL_HALF * 0.34, KEEL_BOTTOM),
		Vector2(-KEEL_HALF * 0.72, KEEL_BOTTOM + 0.07),
		Vector2(-KEEL_HALF * 0.95, KEEL_BOTTOM + 0.24),
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
		palette.get_material("track_floor_v2"), "RunningSurface", false))

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
				+ frame.x * 0.920 * PROFILE_SCALE * factor * side
				+ frame.y * (LIP_CROWN + 0.022) * PROFILE_SCALE)
			light.append(path[index]
				+ frame.x * 1.105 * PROFILE_SCALE * factor * side
				+ frame.y * 0.168 * PROFILE_SCALE)
		root.add_child(Forms.mesh_node(
			Geometry.tube(bead, 0.030 * PROFILE_SCALE, 8),
			palette.get_material("chrome"), "Bead%s" % suffix, false))
		root.add_child(Forms.mesh_node(
			Geometry.tube(light, 0.058 * PROFILE_SCALE, 8),
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
	var strap := Geometry.rounded_box(
		Vector3(1.84 * PROFILE_SCALE, 0.46 * PROFILE_SCALE, 0.19), 0.10, 3)
	var block := Geometry.rounded_box(
		Vector3(0.36 * PROFILE_SCALE, 0.18, 0.23), 0.06, 3)
	var ribs := Node3D.new()
	ribs.name = "Ribs"
	root.add_child(ribs)

	for step in count:
		var t := (float(step) + 0.5) / float(count)
		var index: int = clampi(int(round(t * float(path.size() - 1))),
			0, path.size() - 1)
		var frame: Basis = V2Forms.banked_basis(path, banks, index)
		var factor: float = float(widths[index])
		var centre: Vector3 = path[index] + frame.y * -0.50 * PROFILE_SCALE

		var node := Forms.mesh_node(strap, palette.get_material("graphite_soft"),
			"Rib%d" % step)
		node.transform = Transform3D(
			Basis(frame.x * factor, frame.y, frame.z), centre)
		ribs.add_child(node)

		var cap := Forms.mesh_node(block, palette.get_material("gold"),
			"RibBlock%d" % step, false)
		cap.transform = Transform3D(Basis(frame.x, frame.y, frame.z),
			centre + frame.y * -0.28)
		ribs.add_child(cap)


static func running_point(path: Array, banks: Array, t: float,
		marble_radius: float) -> Vector3:
	## Where a marble of `marble_radius` rests on the floor at fraction `t`.
	var at: float = clampf(t, 0.0, 1.0) * float(path.size() - 1)
	var index: int = clampi(int(round(at)), 0, path.size() - 1)
	var frame: Basis = V2Forms.banked_basis(path, banks, index)
	return Forms.sample_at(path, t) + frame.y * (marble_radius + floor_offset())
