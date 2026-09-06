extends RefCounted

## The mixing bowl: the machine's primary landmark.
##
## Everything the eye reads as one moulded component - the dish, its rim, the
## running dish, rim, outer flank and underside - is a single lathe of a single
## closed profile, so the highlight that runs round the rim is continuous and
## the part reads as manufactured rather than assembled from rings.
##
## What makes it look like a product rather than a bowl primitive:
##
## **A thick rim with a top face.** A dish that ends in an edge is a plate. A
## dish that ends in a machined band with a flat top, a gold insert and a
## bolt ring is a component.
##
## **A guard that stands off the rim.** The acrylic wall does not sit on the
## rim, it sits *outboard* of it on its own shoulder, so there is a shadow gap
## between the two and the guard reads as a separate part.
##
## **A drain that is a hole.** A dark aperture with a gold collar around it,
## with the underside of the shell visible through the rim gap. The concept's
## bowl drains; a disc with a dark circle painted on it does not.
##
## Local origin is the rim top face, centred, so a caller positions the bowl by
## the height it wants the rim at and never has to know the depth.
##
## ## Two sets of dimensions
##
## `build(palette)` draws the bowl the visual lab authored, at the constants
## below, and is what every existing caller gets. `build(palette, spec)` draws
## the same bowl at the dimensions of a simulated one, handed over by
## `marble3d/presentation.py`.
##
## The two differ by more than a scale factor, which is why the spec is a
## dictionary of real dimensions rather than a multiplier:
##
## * **The dish outer edge is `outer_radius`, not `inner_radius`.** The
##   collider is an open surface of revolution with no wall on it at all.
##   Nothing stops a marble at the rim radius; what contains the run is the
##   dish continuing to climb out to its maximum radius. Drawing the dish only
##   as far as the rim would put marbles on a slope that was not there.
##
## * **The dish curve is a power law, not the authored cosine.** The two agree
##   at the drain and at the rim and disagree by about two marble radii in
##   between, which is the whole difference between a marble touching the
##   surface and floating above it.
##
## Detail - fillet sizes, hoop stock, bolt diameters, guard height, mullion
## section - is *not* re-derived. It is the authored number times
## `detail_scale`, so the component keeps the proportions it was drawn with.

const Geometry := preload("res://scripts/toy_geometry.gd")
const Forms := preload("res://assets/marble_machine/lab_forms.gd")

const INNER_RADIUS := 2.52
const DEPTH := 1.02
const DRAIN_RADIUS := 0.56
const SHELL := 0.19
const RIM_OUTER := 2.98


static func dimensions(spec: Dictionary) -> Dictionary:
	## The authored bowl, or a simulated one, as one set of numbers.
	##
	## An empty spec reproduces the authored constants exactly, so a caller
	## that passes nothing gets the mesh it has always got.
	if spec.is_empty():
		return {
			"dish_radius": INNER_RADIUS,
			"depth": DEPTH,
			"drain_radius": DRAIN_RADIUS,
			"shell": SHELL,
			"rim_outer": RIM_OUTER,
			"detail": 1.0,
			"power": 0.0,
			"rounds": 16,
		}
	var outer: float = float(spec["outer_radius"])
	var detail: float = float(spec["detail_scale"])
	return {
		"dish_radius": outer,
		# Depth of the dish at its outer edge, which is where the local
		# origin sits.
		"depth": float(spec["outer_depth"]),
		"drain_radius": float(spec["drain_radius"]),
		"shell": SHELL * detail,
		"rim_outer": RIM_OUTER * detail,
		"detail": detail,
		# Non-zero switches the profile from the authored cosine to the
		# solver's power law.
		"power": float(spec["profile_power"]),
		"reference_radius": float(spec["inner_radius"]),
		"reference_depth": float(spec["depth"]),
		"rounds": 28,
	}


static func drain_local(spec := {}) -> Vector3:
	## Where the track picks up: the centre of the aperture, at its underside.
	var d := dimensions(spec)
	return Vector3(0.0, -d["depth"] - d["shell"], 0.0)


static func dish_profile(d: Dictionary) -> Array:
	## The running surface, drain-first, in the (radius, height) plane.
	##
	## Height is measured down from the dish's outer edge, because that is
	## where this asset's origin is; the solver measures the same surface up
	## from the drain floor. The two are the same curve read from opposite
	## ends.
	if d["power"] <= 0.0:
		return Forms.bowl_profile(
			d["dish_radius"], d["depth"], d["drain_radius"], int(d["rounds"]))

	var points: Array = []
	var rounds := int(d["rounds"])
	var reference_radius: float = d["reference_radius"]
	var reference_depth: float = d["reference_depth"]
	var power: float = d["power"]
	var edge: float = d["depth"]
	for step in range(rounds + 1):
		var t := float(step) / float(rounds)
		var radius: float = lerpf(d["drain_radius"], d["dish_radius"], t)
		# The solver's surface: height above the floor is
		# reference_depth * (r / reference_radius) ^ power.
		var above_floor: float = reference_depth * pow(radius / reference_radius, power)
		points.append(Vector2(radius, above_floor - edge))
	return points


static func build(palette, spec := {}) -> Node3D:
	var root := Node3D.new()
	root.name = "HeroBowl"
	var d := dimensions(spec)

	_shell(root, palette, d)
	_rim_hardware(root, palette, d)
	_guard(root, palette, d)
	_drain(root, palette, d)
	_cradle(root, palette, d)

	return root


# --- the body -------------------------------------------------------------

static func _shell(root: Node3D, palette, d: Dictionary) -> void:
	## Dish, rim, flank and underside as one closed lathe.
	##
	## The profile is read drain-first and anticlockwise in the (radius,
	## height) plane, which is why it asks `profile_normals` for the *inward*
	## family: traversed that way the running surface's normal comes out
	## pointing up into the bowl and the underside's comes out pointing down,
	## which is what they physically are.
	var dish: Array = dish_profile(d)
	var inner: float = d["dish_radius"]
	var rim_outer: float = d["rim_outer"]
	var shell: float = d["shell"]
	var k: float = d["detail"]

	var profile: Array = dish.duplicate()
	# Up and over the rim: a short inner round, a flat machined top face, and
	# a shoulder the guard will stand on.
	profile.append_array([
		Vector2(inner + 0.06 * k, 0.03 * k),
		Vector2(inner + 0.13 * k, 0.11 * k),
		Vector2(inner + 0.22 * k, 0.17 * k),
		Vector2(inner + 0.34 * k, 0.19 * k),
		Vector2(rim_outer - 0.10 * k, 0.19 * k),
		Vector2(rim_outer - 0.02 * k, 0.14 * k),
		Vector2(rim_outer, 0.04 * k),
		Vector2(rim_outer, -0.20 * k),
		Vector2(rim_outer - 0.06 * k, -0.33 * k),
		Vector2(rim_outer - 0.22 * k, -0.40 * k),
	])
	# The underside: the dish again, thinner and lower. Same curve, so the
	# component has an even wall - the thing an eye reads as moulded.
	for index in range(dish.size() - 1, -1, -1):
		var point: Vector2 = dish[index]
		profile.append(Vector2(maxf(point.x - 0.05 * k, 0.0), point.y - shell))
	profile.append(dish[0])

	var body := Forms.mesh_node(
		Geometry.lathe(profile, Geometry.profile_normals(profile, false), 72),
		palette.get_material("pearl_shell"), "Shell")
	root.add_child(body)

	# A brighter inset ring on the running surface, where the field circulates.
	# One value step, not a stripe: it gives the dish an interior landmark so
	# the eye can read its curvature instead of a single flat gradient.
	#
	# The authored bowl keeps the authored numbers, so this asset draws exactly
	# what it always drew when nobody passes a spec. A simulated bowl samples
	# the inset off the dish curve instead, because on a power-law surface the
	# authored fractions of the depth land well clear of it and the inset would
	# float above the thing it is meant to be inset into.
	var lane: Array
	if d["power"] <= 0.0:
		lane = [
			Vector2(inner * 0.52, -d["depth"] * 0.44),
			Vector2(inner * 0.60, -d["depth"] * 0.36),
			Vector2(inner * 0.60, -d["depth"] * 0.36),
			Vector2(inner * 0.86, -d["depth"] * 0.13),
		]
	else:
		lane = [
			_on_dish(dish, 0.52),
			_on_dish(dish, 0.60),
			_on_dish(dish, 0.60),
			_on_dish(dish, 0.86),
		]
	var lane_node := Forms.mesh_node(
		Geometry.lathe(lane, Geometry.profile_normals(lane, false), 72),
		palette.get_material("pearl_shade"), "LaneInset", false)
	lane_node.position = Vector3(0.0, 0.006 * k, 0.0)
	root.add_child(lane_node)


static func _on_dish(dish: Array, fraction: float) -> Vector2:
	## The dish point at a fraction of the outer radius, by linear search.
	var target: float = dish[dish.size() - 1].x * fraction
	for index in range(dish.size() - 1):
		var a: Vector2 = dish[index]
		var b: Vector2 = dish[index + 1]
		if target >= a.x and target <= b.x and b.x > a.x:
			var t: float = (target - a.x) / (b.x - a.x)
			return a.lerp(b, t)
	return dish[dish.size() - 1]


# --- rim ------------------------------------------------------------------

static func _rim_hardware(root: Node3D, palette, d: Dictionary) -> void:
	## The machined band, its gold insert, and the light under the flank.
	var inner: float = d["dish_radius"]
	var rim_outer: float = d["rim_outer"]
	var k: float = d["detail"]

	var insert_radius := inner + 0.40 * k
	var insert := Forms.mesh_node(
		Forms.hoop(insert_radius, 0.055 * k, 64, 10),
		palette.get_material("gold"), "RimInsert", false)
	insert.position = Vector3(0.0, 0.205 * k, 0.0)
	root.add_child(insert)

	var cap := Forms.mesh_node(
		Forms.hoop(rim_outer - 0.03 * k, 0.05 * k, 64, 10),
		palette.get_material("pearl_lip"), "RimCap", false)
	cap.position = Vector3(0.0, 0.16 * k, 0.0)
	root.add_child(cap)

	# The practical. Tucked under the flank so the *bowl* is lit by it and the
	# lamp itself is a thin line - a visible bulb reads as a prop, a visible
	# wash reads as a product.
	var glow_key := "neon_cyan" if palette.variant == "spine" else "neon_violet"
	var glow := Forms.mesh_node(
		Forms.hoop(rim_outer + 0.015 * k, 0.042 * k, 64, 8),
		palette.get_material(glow_key), "RimGlow", false)
	glow.position = Vector3(0.0, -0.12 * k, 0.0)
	root.add_child(glow)

	var bolt_count := 24 if palette.variant == "deck" else 16
	Forms.bolt_ring(root, palette.get_material("chrome"), bolt_count,
		insert_radius + 0.16 * k, 0.20 * k, 0.055 * k, 0.045 * k)

	# Four clamps holding the guard down onto its shoulder.
	var clamp_mesh := Geometry.rounded_box(
		Vector3(0.22, 0.13, 0.34) * k, 0.05 * k, 3)
	var seats: Array = Forms.ring_positions(4, rim_outer - 0.30 * k, PI * 0.25)
	for index in seats.size():
		var at: Vector3 = seats[index]
		var clamp := Forms.mesh_node(clamp_mesh, palette.get_material("silver"),
			"GuardClamp%d" % index, false)
		clamp.position = at + Vector3(0.0, 0.22 * k, 0.0)
		clamp.rotation.y = -atan2(at.z, at.x)
		root.add_child(clamp)


# --- guard ----------------------------------------------------------------

static func _guard(root: Node3D, palette, d: Dictionary) -> void:
	## The aqua acrylic wall, standing outboard of the rim on its shoulder.
	var rim_outer: float = d["rim_outer"]
	var k: float = d["detail"]
	var height: float = 1.42
	match palette.variant:
		"deck":
			height = 1.00
		"spine":
			height = 1.24
	height *= k

	var base_radius := rim_outer - 0.16 * k
	var wall: Array = [
		Vector2(base_radius, 0.20 * k),
		Vector2(base_radius + 0.04 * k, 0.34 * k),
		Vector2(base_radius + 0.14 * k, height * 0.55),
		Vector2(base_radius + 0.30 * k, height * 0.90),
		Vector2(base_radius + 0.38 * k, height),
	]
	var key := "acrylic_aqua_deep" if palette.variant == "deck" else "acrylic_aqua"
	var glass := Forms.mesh_node(
		Geometry.lathe(wall, Geometry.profile_normals(wall, true), 72),
		palette.get_material(key), "GuardWall", false)
	root.add_child(glass)

	# The top edge, in near-clear stock. A cast panel always has a thicker,
	# lighter edge than its face, and without it the wall's silhouette
	# dissolves against a dark backdrop.
	var edge := Forms.mesh_node(
		Forms.hoop(base_radius + 0.38 * k, 0.05 * k, 64, 10),
		palette.get_material("acrylic_clear"), "GuardEdge", false)
	edge.position = Vector3(0.0, height, 0.0)
	root.add_child(edge)

	# Vertical mullions: six thin silver posts up the wall. They are what give
	# the transparent surface something to shade against, and they read as the
	# frame of a guard rather than as decoration.
	var mullion := Geometry.rounded_box(
		Vector3(0.07 * k, height - 0.18 * k, 0.10 * k), 0.025 * k, 3)
	for index in 6:
		var angle := TAU * float(index) / 6.0 + PI * 0.08
		var post := Forms.mesh_node(mullion, palette.get_material("silver"),
			"Mullion%d" % index, false)
		var radius: float = base_radius + 0.22 * k
		post.position = Vector3(cos(angle) * radius,
			0.20 * k + (height - 0.18 * k) * 0.5, sin(angle) * radius)
		post.rotation.y = -angle
		root.add_child(post)


# --- drain ----------------------------------------------------------------

static func _drain(root: Node3D, palette, d: Dictionary) -> void:
	## A real aperture: a dark throat, a gold collar, a lit inner edge.
	var drain: float = d["drain_radius"]
	var depth: float = d["depth"]
	var k: float = d["detail"]

	var throat: Array = [
		Vector2(drain + 0.09 * k, -depth + 0.10 * k),
		Vector2(drain, -depth - 0.02 * k),
		Vector2(drain - 0.04 * k, -depth - 0.34 * k),
		Vector2(drain - 0.04 * k, -depth - 0.78 * k),
	]
	root.add_child(Forms.mesh_node(
		Geometry.lathe(throat, Geometry.profile_normals(throat, true), 40),
		palette.get_material("graphite_deep"), "DrainThroat"))

	var collar := Forms.mesh_node(
		Forms.hoop(drain + 0.10 * k, 0.062 * k, 44, 10),
		palette.get_material("gold"), "DrainCollar", false)
	collar.position = Vector3(0.0, -depth + 0.10 * k, 0.0)
	root.add_child(collar)

	var lit := Forms.mesh_node(
		Forms.hoop(drain + 0.20 * k, 0.032 * k, 44, 6),
		palette.get_material("neon_cyan"), "DrainLight", false)
	lit.position = Vector3(0.0, -depth + 0.145 * k, 0.0)
	root.add_child(lit)


# --- cradle ---------------------------------------------------------------

static func _cradle(root: Node3D, palette, d: Dictionary) -> void:
	## What holds the bowl up, and it must look like it could.
	var rim_outer: float = d["rim_outer"]
	var depth: float = d["depth"]
	var drain: float = d["drain_radius"]
	var k: float = d["detail"]

	var arm_count := 4
	var reach := rim_outer - 0.26 * k
	var phase := PI * 0.25
	match palette.variant:
		"deck":
			arm_count = 8
			phase = 0.0
		"spine":
			arm_count = 3
			phase = PI * 0.5

	var hoop_radius := reach * 0.72
	var hub := Forms.mesh_node(
		Forms.hoop(hoop_radius, 0.10 * k, 48, 8),
		palette.get_material("graphite"), "CradleHoop")
	hub.position = Vector3(0.0, -depth - 0.36 * k, 0.0)
	root.add_child(hub)

	var boss := Forms.mesh_node(
		Geometry.rounded_disc(drain + 0.42 * k, 0.26 * k, 0.09 * k, 32, 3),
		palette.get_material("graphite_soft"), "CradleBoss")
	boss.position = Vector3(0.0, -depth - 0.30 * k, 0.0)
	root.add_child(boss)

	for index in arm_count:
		var angle := phase + TAU * float(index) / float(arm_count)
		var outer := Vector3(cos(angle) * reach, -0.34 * k, sin(angle) * reach)
		var mid := Vector3(cos(angle) * reach * 0.92, -depth * 0.62 - 0.30 * k,
			sin(angle) * reach * 0.92)
		var inner := Vector3(cos(angle) * hoop_radius, -depth - 0.36 * k,
			sin(angle) * hoop_radius)
		var arm_path := Forms.smooth_path([outer, mid, inner], 8)
		root.add_child(Forms.mesh_node(
			Geometry.tube(arm_path, 0.085 * k, 8),
			palette.get_material("graphite"), "CradleArm%d" % index))

		var pad := Forms.mesh_node(
			Geometry.rounded_box(Vector3(0.34, 0.13, 0.26) * k, 0.05 * k, 3),
			palette.get_material("gold"), "CradlePad%d" % index, false)
		pad.position = outer + Vector3(0.0, 0.02 * k, 0.0)
		pad.rotation.y = -angle
		root.add_child(pad)
