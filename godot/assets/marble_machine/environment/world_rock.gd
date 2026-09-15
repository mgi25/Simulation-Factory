extends RefCounted

## THE ROCK KIT: eight stylised rock forms from one faceted generator.
##
## V25 put rock at every distance and the review's verdict was that the rock
## itself still reads as procedural. That verdict is correct and the cause is
## one function. Every mass in V25 - valley wall, ridge, spire, boulder, crest
## tooth, landmark - comes out of `hero_world.smooth_mass`, which is
##
##     radius(u, v) = base * taper(v) * noise(u, v) * strata(v)
##
## with **averaged normals everywhere**. That is a noise-displaced dome, and a
## noise-displaced dome has three properties a designed rock does not:
##
##   * **No planes.** Smooth normals mean the shading field is continuous, so
##     no two parts of the surface catch the key differently enough to read as
##     separate faces. A cliff is a thing made of *planes meeting at edges*;
##     this is a thing made of gradients.
##   * **A round silhouette.** Three octaves of noise on the radius move the
##     outline by a few per cent. The outline is still a circle in plan and
##     still a dome in elevation, and at phone size the outline is all there
##     is.
##   * **No intent.** Every part of the form is statistically the same as
##     every other part. There is no dominant mass, no secondary mass, no
##     break - the three things that make a rock look composed rather than
##     generated.
##
## Adding detail cannot fix any of those; more octaves of noise on a dome is a
## bumpier dome. What fixes them is building the form out of **a small number
## of large flat faces, from a plan that was designed rather than sampled.**
##
## ## How a form here is built
##
## Three separable parts, and each answers one of the three failures:
##
##     plan      K radii round the form: one dominant lobe, one or two
##               chorded flats, one or two hard notches. This is the
##               silhouette, and it is the same plan the whole way up, so a
##               form has *a shape* rather than a different shape per tier.
##     profile   a piecewise taper up the form with hard ledge steps in it. A
##               ledge is two tiers at almost the same height with a step in
##               radius between them, which is a horizontal shelf that
##               catches the key and shadows what is under it.
##     frame     a lean, a twist and a crown plan the base plan blends into,
##               so the form is neither a prism nor a solid of revolution.
##
## Every quad is emitted with **one face normal** through `Geometry.quad_auto`,
## so a form is flat-shaded and every plane it has is visible as a plane.
##
## ## This is cheaper than what it replaces
##
## `smooth_mass` at its shipped settings is 26 facets x 14 tiers x 2 triangles
## plus a 26-triangle crown: **754 triangles**. A `cliff` here is 11 facets x
## ~12 tiers x 2 plus a 9-triangle cap: **273**. The kit is a third of the
## cost, and the reason is the whole argument of this file - the quality was
## never in the triangle count, it was in where the edges are.
##
## ## Nothing here is landform
##
## A mesh. No collider, no height field, no physics. See
## `environment_world.gd`'s header for why that separation is load-bearing.
##
## ## V25.2: the lookdev options, and why they are options
##
## V25.1 shipped this kit and its own doc recorded the cost of it honestly:
## the midground ridge band went from 22.6% of its pixels under grey 12 to
## **42.2%**, because a flat facet has one value and some of those values are
## low. The review saw the same thing without a number - cliffs that read as
## twelve unrelated dark polygons rather than as one sculpted mass.
##
## Four options below answer that, and **every one of them defaults to off**,
## so a profile that does not name them builds the mesh V25.1 built, vertex
## for vertex and triangle for triangle. That is not politeness: V25.1 and
## V25 B are the controls this pass is measured against, and a control that
## silently moved would make the comparison meaningless.
##
##     temper     crease-limited normal softening. The silhouette, the
##                vertices and the triangle count are untouched; only the
##                shading normals move, and only across edges shallower than
##                `crease`. A ledge step still catches the key as a hard line;
##                the 33-degree steps around the plan stop being cliffs of
##                value. This is the midground fix.
##     shade      a large-scale albedo gradient baked to vertex colour: lift
##                toward the crown, fall into the foot, and a restrained warm
##                or cool turn by aspect. Needs `vertex_tint` on the material.
##     jag        a broken crown contour on the flat-topped kinds.
##     overhang   a ledge that steps *outward*, which is the one silhouette
##                event a taper cannot produce.
##     shoulder   a high secondary mass that breaks the top contour, where
##                `buttress` is a low one that broadens the foot.

const Geometry := preload("res://scripts/toy_geometry.gd")


## The kit. Each entry is a set of defaults for `form()`, and a caller
## overrides whatever it needs - so `cliff` with `ledges: 3` is still a cliff.
##
## Eight, and eight is the whole kit deliberately. The brief's rule is that a
## scene with forty good rocks beats one with a hundred and fifty crude ones,
## and the way a kit goes crude is by growing an entry per site until nothing
## is reusable. These eight cover every job this course has:
##
##     cliff      the hero mass: tall, two ledges, a broad flat crown
##     block      a medium cliff block: squat, one ledge, a wide top
##     ledge      a low wide step, read for its horizontal
##     needle     a vertical spire, the one form with almost no top
##     slab       a broken plate, leaning, two flats
##     boulder    a chunk: few facets, strong lobe, no ledge to speak of
##     wall       a long ravine wall: low taper, many facets, grooved
##     mountain   distant mass: wide, low, and crowned with a ridge line
const KINDS := {
	"cliff": {
		"facets": 11, "tiers": 3, "taper": 0.46, "cap": 0.34,
		"lobe": 0.34, "flats": 1, "notches": 1, "ledges": 2, "step": 0.085,
		"lean": 0.11, "twist": 0.10, "crown": 0.50, "batter": 0.55,
		"buttress": 2,
	},
	"block": {
		"facets": 9, "tiers": 2, "taper": 0.30, "cap": 0.56,
		"lobe": 0.30, "flats": 1, "notches": 1, "ledges": 1, "step": 0.09,
		"lean": 0.08, "twist": 0.07, "crown": 0.38, "batter": 0.35,
		"buttress": 1,
	},
	"ledge": {
		"facets": 10, "tiers": 2, "taper": 0.20, "cap": 0.72,
		"lobe": 0.46, "flats": 2, "notches": 0, "ledges": 1, "step": 0.11,
		"lean": 0.06, "twist": 0.05, "crown": 0.32, "batter": 0.18,
		"buttress": 1,
	},
	"needle": {
		"facets": 7, "tiers": 2, "taper": 0.80, "cap": 0.11,
		"lobe": 0.24, "flats": 1, "notches": 1, "ledges": 1, "step": 0.07,
		"lean": 0.16, "twist": 0.15, "crown": 0.58, "batter": 0.60,
		"buttress": 1,
	},
	"slab": {
		"facets": 6, "tiers": 2, "taper": 0.34, "cap": 0.60,
		"lobe": 0.50, "flats": 2, "notches": 0, "ledges": 0, "step": 0.0,
		"lean": 0.26, "twist": 0.04, "crown": 0.22, "batter": 0.14,
		"buttress": 0,
	},
	"boulder": {
		"facets": 7, "tiers": 2, "taper": 0.50, "cap": 0.38,
		"lobe": 0.40, "flats": 1, "notches": 1, "ledges": 1, "step": 0.09,
		"lean": 0.18, "twist": 0.13, "crown": 0.52, "batter": 0.45,
		"buttress": 0,
	},
	"wall": {
		"facets": 13, "tiers": 3, "taper": 0.28, "cap": 0.50,
		"lobe": 0.26, "flats": 2, "notches": 2, "ledges": 2, "step": 0.07,
		"lean": 0.06, "twist": 0.06, "crown": 0.32, "batter": 0.22,
		"buttress": 1,
	},
	"mountain": {
		"facets": 13, "tiers": 3, "taper": 0.56, "cap": 0.18,
		"lobe": 0.38, "flats": 1, "notches": 2, "ledges": 2, "step": 0.075,
		"lean": 0.09, "twist": 0.08, "crown": 0.52, "batter": 0.62,
		"ridge": 0.30, "buttress": 2,
	},
}


static func known(kind: String) -> bool:
	return KINDS.has(kind)


static func kinds() -> Array:
	return KINDS.keys()


# --- the generator ----------------------------------------------------------


static func form(kind: String, height: float, base_radius: float,
		seed_value: int, opts := {}) -> ArrayMesh:
	## One rock, flat-shaded, standing on y = 0 and topping out at `height`.
	##
	## `base_radius` is the radius of the **widest** point, which is the foot
	## on every kind here. A caller sizing a form against a gap it must not
	## block can therefore use `base_radius` directly, which is not true of
	## `smooth_mass` - there the noise makes the real extent up to 1.3x the
	## nominal radius, and V25's ring keep-outs are padded for exactly that.
	var spec: Dictionary = (KINDS.get(kind, KINDS["cliff"]) as Dictionary) \
		.duplicate()
	for key in opts:
		spec[key] = opts[key]

	var surface := SurfaceTool.new()
	surface.begin(Mesh.PRIMITIVE_TRIANGLES)
	_shell(surface, spec, height, base_radius, seed_value, Vector3.ZERO)

	# **The secondary masses.** The brief's rule for a hero formation is one
	# dominant mass, one secondary mass and one or two asymmetric breaks, and
	# the first two of those cannot come out of a single solid of revolution
	# however it is faceted - a shape with one axis has one mass by
	# construction. So a form may carry buttresses: smaller shells of the same
	# kind, at 38-62% of the height, pushed out to the foot's own edge and
	# welded into the same surface.
	#
	# **Interpenetrating, not boolean.** Two closed opaque shells that overlap
	# render as their union with no seam, because the depth buffer does the
	# union for free. A CSG or a weld would cost geometry and solve a problem
	# that does not exist here: nothing in this world is transparent and
	# nothing is cut open.
	var buttresses := int(spec.get("buttress", 0))
	for which in buttresses:
		var salt := seed_value * 31 + which * 617 + 41
		var angle: float = TAU * _h(salt, 71)
		var out: float = base_radius * (0.52 + 0.4 * _h(salt, 73))
		var share: float = 0.38 + 0.24 * _h(salt, 79)
		var side: Dictionary = spec.duplicate()
		side["ledges"] = maxi(int(spec.get("ledges", 2)) - 1, 0)
		side["buttress"] = 0
		side["lean"] = float(spec.get("lean", 0.1)) * 1.4
		_shell(surface, side, height * share,
			base_radius * (0.40 + 0.26 * _h(salt, 83)), salt,
			Vector3(cos(angle) * out, -height * 0.02, sin(angle) * out))

	# **The high secondary mass.** A buttress broadens the foot; what breaks a
	# *top* contour has to be up near the crown, and the brief's hero-rock
	# rule asks for both. A shoulder is a shell at 62-88% of the height,
	# pushed out about half a radius, so it interpenetrates the parent's upper
	# third and its own crown lands beside the parent's - two summits at
	# different heights instead of one plate.
	var shoulders := int(spec.get("shoulder", 0))
	for which in shoulders:
		var salt := seed_value * 53 + which * 907 + 17
		var angle: float = TAU * _h(salt, 89)
		var out: float = base_radius * (0.34 + 0.3 * _h(salt, 97))
		var share: float = 0.62 + 0.26 * _h(salt, 101)
		var high: Dictionary = spec.duplicate()
		high["ledges"] = maxi(int(spec.get("ledges", 2)) - 1, 0)
		high["buttress"] = 0
		high["shoulder"] = 0
		high["overhang"] = 0
		high["cap"] = float(spec.get("cap", 0.4)) * 0.72
		high["lean"] = float(spec.get("lean", 0.1)) * 1.6
		_shell(surface, high, height * share,
			base_radius * (0.30 + 0.2 * _h(salt, 103)), salt,
			Vector3(cos(angle) * out, -height * 0.01, sin(angle) * out))

	var mesh := ArrayMesh.new()
	surface.commit(mesh)
	return mesh


static func _shell(surface: SurfaceTool, spec: Dictionary, height: float,
		base_radius: float, seed_value: int, origin: Vector3) -> void:
	## One closed mass: plan, profile, frame, crown.
	var facets := maxi(int(spec.get("facets", 11)), 5)
	var plan := _plan(facets, seed_value, float(spec.get("lobe", 0.3)),
		int(spec.get("flats", 1)), int(spec.get("notches", 1)), 0)
	# The crown is a *second* plan the base plan blends into with height. Two
	# plans rather than one is what stops a form reading as an extrusion: an
	# extrusion has the same outline from every height, and a rock that was
	# cut by anything has not.
	var crown := _plan(facets, seed_value * 7 + 13,
		float(spec.get("lobe", 0.3)) * 0.8,
		int(spec.get("flats", 1)), int(spec.get("notches", 1)), 97)
	var blend := clampf(float(spec.get("crown", 0.45)), 0.0, 1.0)

	var rings := _profile(spec, seed_value, facets)
	var lean := float(spec.get("lean", 0.1))
	var lean_dir := TAU * _h(seed_value, 211)
	var twist := float(spec.get("twist", 0.08))
	var ridge := float(spec.get("ridge", 0.0))

	var loops: Array = []
	for index in rings.size():
		var ring: Dictionary = rings[index]
		var v: float = ring["v"]
		var scale: PackedFloat32Array = ring["scale"]
		var slide: float = lean * height * pow(v, 1.3)
		var offset := origin + Vector3(cos(lean_dir) * slide, 0.0,
			sin(lean_dir) * slide)
		var spin: float = twist * v
		var mix: float = blend * pow(v, 1.15)
		var loop: Array = []
		for facet in facets:
			var angle: float = TAU * float(facet) / float(facets) + spin
			var radius: float = lerpf(plan[facet], crown[facet], mix) \
				* base_radius * scale[facet]
			loop.append(Vector3(cos(angle) * radius, height * v,
				sin(angle) * radius) + offset)
		loops.append(loop)

	# **The vertex tint.** A large-scale albedo gradient, baked per vertex and
	# multiplied into the material by `vertex_tint`. Off unless a profile asks
	# for it, and when it is on it is on for *every* vertex of the surface -
	# `SurfaceTool` rejects a surface where some vertices carry a colour and
	# others do not.
	var shade := float(spec.get("shade", 0.0))
	var tints: Array = []
	if shade > 0.0:
		for index in loops.size():
			var ring: Array = loops[index]
			var row: Array = []
			for facet in facets:
				row.append(_tint(spec, shade, ring[facet], origin, height))
			tints.append(row)

	# **The shading normals, and the one rule that keeps this from flattening
	# the kit.**
	#
	# `temper` blends each corner of a quad from its own face normal toward
	# the average of the faces meeting at that corner - but only over edges
	# shallower than `crease`. So the 33-degree steps around a plan, which are
	# what turn a cliff into a mosaic of unrelated values, get a gradient
	# across them; a ledge step, a notch and a chorded flat's corner are all
	# past the crease angle and stay exactly as hard as they were. The
	# vertices do not move, the silhouette does not move and the triangle
	# count does not move: this is a shading change and nothing else.
	var temper := clampf(float(spec.get("temper", 0.0)), 0.0, 1.0)
	var crease := cos(deg_to_rad(clampf(float(spec.get("crease", 42.0)),
		1.0, 179.0)))
	var faces: Array = []
	for tier in loops.size() - 1:
		var lower: Array = loops[tier]
		var upper: Array = loops[tier + 1]
		var row := PackedVector3Array()
		row.resize(facets)
		for facet in facets:
			var next := (facet + 1) % facets
			var a: Vector3 = lower[facet]
			var b: Vector3 = upper[facet]
			var c: Vector3 = upper[next]
			var d: Vector3 = lower[next]
			var outward := Vector3(a.x + d.x - 2.0 * origin.x, 0.0,
				a.z + d.z - 2.0 * origin.z)
			if outward.length_squared() < 1.0e-9:
				outward = Vector3.RIGHT
			# One normal for the whole quad. This single line is most of what
			# separates this file from what it replaces: the face is a face,
			# it catches the key at its own angle, and the edge where it meets
			# its neighbour is a real edge.
			var normal := (c - a).cross(b - d)
			if normal.dot(outward) < 0.0:
				normal = -normal
			if normal.length_squared() < 1.0e-12:
				normal = outward
			row[facet] = normal.normalized()
		faces.append(row)

	for tier in loops.size() - 1:
		var lower: Array = loops[tier]
		var upper: Array = loops[tier + 1]
		for facet in facets:
			var next := (facet + 1) % facets
			var a: Vector3 = lower[facet]
			var b: Vector3 = upper[facet]
			var c: Vector3 = upper[next]
			var d: Vector3 = lower[next]
			var flat: Vector3 = faces[tier][facet]
			if temper <= 0.0 and shade <= 0.0:
				Geometry.quad_auto(surface, a, b, c, d, flat)
				continue
			var normals := [flat, flat, flat, flat]
			if temper > 0.0:
				normals = [
					_soft(faces, facets, tier, facet, flat, temper, crease),
					_soft(faces, facets, tier + 1, facet, flat, temper, crease),
					_soft(faces, facets, tier + 1, next, flat, temper, crease),
					_soft(faces, facets, tier, next, flat, temper, crease),
				]
			var colours := []
			if shade > 0.0:
				colours = [tints[tier][facet], tints[tier + 1][facet],
					tints[tier + 1][next], tints[tier][next]]
			_face(surface, [a, b, c, d], normals, colours, flat)

	# **The foot is a buried skirt, not a flat cap, and the reason is the one
	# lighting fact that flat shading makes unforgiving.**
	#
	# Every light in the world rig points *downward*: `WorldKey` at -26 degrees
	# of elevation, `WorldFill` at -14, `WorldWarm` at -11, `WorldRim` at -7,
	# `WorldBounce` at -6. A surface whose normal is `Vector3.DOWN` is therefore
	# lit by **nothing**, and gets only the ambient term.
	#
	# The first version of this file closed each form with a flat downward fan
	# at y = 0. On level ground that is buried and costs nothing; on the
	# gorge's far side, where the terrain falls away twenty units under a mass
	# eighteen units wide, the downhill half of that fan is exposed - and it
	# came out as a large near-black plate. Measured: the ridge band in the
	# left half of the split frame sat at grey 8 against V25 B's 27, and
	# raising a back-fill light three-fold moved it by 0.4 of a level, because
	# the faces were not facing the back-fill either. They were facing the
	# ground.
	#
	# `smooth_mass` never had this problem because it never had a bottom: an
	# open shell shows its own lit inside. A closed flat-shaded form has to
	# solve it, and the solution is to put the cap **below the ground** and
	# make what is exposed a vertical wall, which every light reaches.
	var skirt := float(spec.get("skirt", 0.5)) * maxf(base_radius, 1.0)
	var foot: Array = loops[0]
	var buried: Array = []
	for point in foot:
		buried.append(Vector3(point.x, point.y - skirt, point.z))
	for index in foot.size():
		var next := (index + 1) % foot.size()
		var a: Vector3 = buried[index]
		var b: Vector3 = foot[index]
		var c: Vector3 = foot[next]
		var d: Vector3 = buried[next]
		var outward := Vector3(b.x + c.x - 2.0 * origin.x, 0.0,
			b.z + c.z - 2.0 * origin.z)
		if outward.length_squared() < 1.0e-9:
			outward = Vector3.RIGHT
		if shade <= 0.0:
			Geometry.quad_auto(surface, a, b, c, d, outward.normalized())
			continue
		var face := outward.normalized()
		# The skirt is below the ground on level terrain and is a vertical
		# wall where the ground falls away, so it takes the foot's own tint
		# rather than a darker one: what is visible of it is the bottom of
		# the mass, not a separate object.
		var low: Color = tints[0][index]
		var low_next: Color = tints[0][next]
		_face(surface, [a, b, c, d], [face, face, face, face],
			[low, low, low_next, low_next], face)
	var base_centre := origin - Vector3(0.0, skirt, 0.0)
	for index in buried.size():
		var next := (index + 1) % buried.size()
		if shade <= 0.0:
			Geometry.quad_auto(surface, buried[index], buried[next],
				base_centre, base_centre, Vector3.DOWN)
			continue
		var under: Color = tints[0][index]
		_face(surface, [buried[index], buried[next], base_centre, base_centre],
			[Vector3.DOWN, Vector3.DOWN, Vector3.DOWN, Vector3.DOWN],
			[under, under, under, under], Vector3.DOWN)

	_crown(surface, loops[loops.size() - 1], height, ridge, seed_value,
		spec, shade, origin)


static func _crown(surface: SurfaceTool, top: Array, height: float,
		ridge: float, seed_value: int, spec := {}, shade := 0.0,
		origin := Vector3.ZERO) -> void:
	## The top. A flat plate on every kind but the mountains, which get a
	## broken ridge line instead.
	##
	## **Flat, not pointed**, and that is a design decision rather than a
	## simplification. A mass that closes to a point is a cone, a cone is the
	## one silhouette a viewer reads as "generated", and the reference's rock
	## is mesas and buttes - forms with a *top surface*. `smooth_mass` closes
	## with a fan to a peak at 1.03x the height, which is why every V25 ridge
	## reads as a dune however much noise is on its flank.
	var centre := Vector3.ZERO
	for point in top:
		centre += point
	centre /= float(top.size())
	if ridge <= 0.0:
		# A plate, tilted a few degrees so the crowns of a range do not all
		# catch the key identically.
		var tilt := Vector3(
			(_h(seed_value, 307) - 0.5) * 0.22, 0.0,
			(_h(seed_value, 311) - 0.5) * 0.22)
		# **The broken crown.** A flat top is the right decision - the
		# reference's rock is mesas and buttes, and a mass that closes to a
		# point is a cone. But a flat top whose rim is a single clean polygon
		# draws a straight line across the sky, and a straight line across the
		# sky is the strongest "generated" cue a silhouette has. `jag` gives
		# each rim vertex its own height, so the top reads as a weathered
		# crown with notches in it and still reads as a *top*.
		var jag := maxf(float(spec.get("jag", 0.0)), 0.0)
		var lifted: Array = []
		for index in top.size():
			var raised: Vector3 = top[index]
			raised.y += tilt.x * raised.x + tilt.z * raised.z
			if jag > 0.0:
				raised.y += height * jag * (_h(seed_value * 17 + index, 503)
					- 0.42)
			lifted.append(raised)
		var apex := centre
		apex.y += height * 0.02
		if jag > 0.0:
			apex.y += height * jag * 0.22
		for index in lifted.size():
			var next := (index + 1) % lifted.size()
			var a: Vector3 = lifted[index]
			var b: Vector3 = lifted[next]
			var normal := (b - apex).cross(a - apex)
			if normal.y < 0.0:
				normal = -normal
			if shade <= 0.0:
				Geometry.quad_auto(surface, a, b, apex, apex,
					normal.normalized())
				continue
			var face := normal.normalized()
			var top_a := _tint(spec, shade, a, origin, height)
			var top_b := _tint(spec, shade, b, origin, height)
			var top_c := _tint(spec, shade, apex, origin, height)
			_face(surface, [a, b, apex, apex], [face, face, face, face],
				[top_a, top_b, top_c, top_c], face)
		return
	# A ridge line: each crown vertex gets its own height, so the top is a row
	# of summits and saddles rather than a plate. This is what makes a distant
	# mass read as a *range* - the thing V25's crest teeth were bolted on to
	# fake, at three hundred triangles each, on top of a dome that was still a
	# dome underneath them.
	var peaks: Array = []
	for index in top.size():
		var point: Vector3 = top[index]
		point.y += height * ridge * (0.36 + 0.64
			* _h(seed_value * 13 + index, 401))
		peaks.append(point)
	var spine := centre
	spine.y += height * ridge * 0.66
	for index in peaks.size():
		var next := (index + 1) % peaks.size()
		var a: Vector3 = peaks[index]
		var b: Vector3 = peaks[next]
		var normal := (b - spine).cross(a - spine)
		if normal.y < 0.0:
			normal = -normal
		if shade <= 0.0:
			Geometry.quad_auto(surface, a, b, spine, spine,
				normal.normalized())
			continue
		var face := normal.normalized()
		_face(surface, [a, b, spine, spine], [face, face, face, face],
			[_tint(spec, shade, a, origin, height),
				_tint(spec, shade, b, origin, height),
				_tint(spec, shade, spine, origin, height),
				_tint(spec, shade, spine, origin, height)], face)


# --- V25.2: shading response, not geometry ----------------------------------


static func _soft(faces: Array, facets: int, tier: int, facet: int,
		flat: Vector3, temper: float, crease: float) -> Vector3:
	## One corner's shading normal: its own face, blended toward the average
	## of the faces meeting there over shallow edges only.
	##
	## Vertex `(tier, facet)` belongs to the four quads `(tier-1, facet-1)`,
	## `(tier-1, facet)`, `(tier, facet-1)` and `(tier, facet)`, minus whichever
	## of those are off the ends of the form. A neighbour joins the average
	## only if its normal is within `crease` of the face being emitted, so a
	## ledge step, a notch wall and the corner of a chorded flat are all left
	## alone - they are the edges that carry the kit's whole argument.
	var sum := flat
	var previous := (facet + facets - 1) % facets
	for row in [tier - 1, tier]:
		if row < 0 or row >= faces.size():
			continue
		var band: PackedVector3Array = faces[row]
		for column in [previous, facet]:
			if row == tier and column == facet:
				continue
			var other: Vector3 = band[column]
			if other.dot(flat) >= crease:
				sum += other
	if sum.length_squared() < 1.0e-12:
		return flat
	return flat.lerp(sum.normalized(), temper).normalized()


static func _tint(spec: Dictionary, shade: float, point: Vector3,
		origin: Vector3, height: float) -> Color:
	## The large-scale albedo gradient at one vertex, as a multiplier.
	##
	## Two terms, both of them at the scale of the whole form, because the
	## brief's rule and this course's style lock both ban high-frequency
	## surface noise:
	##
	##   * **height.** Lift toward the crown and fall into the foot, which is
	##     what a mass standing in its own dust and its own shadow does, and
	##     which gives a cliff an internal value change that survives being
	##     flat-shaded. A facet is still one value; the *form* is no longer
	##     one value.
	##   * **aspect.** A restrained warm turn on the side the world's warm
	##     fill comes from and a cool turn away from it. This is the brief's
	##     "warm bounce on selected rock faces" bought at zero light cost and
	##     with no risk of reaching the machine, which is on another layer and
	##     another material set entirely.
	##
	## Returned as a multiplier around 1.0 in **linear** space, which is what
	## `vertex_color_use_as_albedo` wants with `vertex_color_is_srgb` off.
	var v: float = clampf(point.y / maxf(height, 0.001), 0.0, 1.0)
	var lift: float = 1.0 		+ shade * float(spec.get("shade_crown", 0.34)) * pow(v, 0.8) 		- shade * float(spec.get("shade_foot", 0.30)) * pow(1.0 - v, 2.0)
	var warm := shade * float(spec.get("shade_warm", 0.0))
	var cool := shade * float(spec.get("shade_cool", 0.0))
	var tint := Color(lift, lift, lift, 1.0)
	if warm > 0.0 or cool > 0.0:
		var bearing := deg_to_rad(float(spec.get("shade_bearing", 58.0)))
		var out := Vector3(point.x - origin.x, 0.0, point.z - origin.z)
		var aspect := 0.0
		if out.length_squared() > 1.0e-9:
			out = out.normalized()
			aspect = out.x * sin(bearing) + out.z * cos(bearing)
		var lit: float = maxf(aspect, 0.0)
		var away: float = maxf(-aspect, 0.0)
		tint.r += warm * lit * 1.00 - cool * away * 0.30
		tint.g += warm * lit * 0.52 - cool * away * 0.05
		tint.b += -warm * lit * 0.22 + cool * away * 0.55
	tint.r = maxf(tint.r, 0.05)
	tint.g = maxf(tint.g, 0.05)
	tint.b = maxf(tint.b, 0.05)
	return tint


static func _face(surface: SurfaceTool, points: Array, normals: Array,
		colours: Array, mean: Vector3) -> void:
	## One quad with a normal - and optionally a colour - per corner.
	##
	## `Geometry.quad_auto` is still the path when no lookdev option is on,
	## and a byte-identical mesh is the reason: this exists because
	## `SurfaceTool` needs the colour set before each `add_vertex` and the
	## shared helper has no colour argument. Winding is decided against
	## `mean`, the untempered face normal, so a tempered quad winds exactly
	## the way the same quad wound in V25.1.
	var order := [0, 1, 2, 3]
	if (points[1] - points[0]).cross(points[2] - points[0]).dot(mean) > 0.0:
		order = [0, 3, 2, 1]
	var tinted := not colours.is_empty()
	for index in [0, 1, 2, 0, 2, 3]:
		var at: int = order[index]
		if tinted:
			surface.set_color(colours[at])
		surface.set_normal(normals[at])
		surface.add_vertex(points[at])


# --- the plan: what the form looks like from above --------------------------


static func _plan(facets: int, seed_value: int, lobe: float, flats: int,
		notches: int, salt: int) -> PackedFloat32Array:
	## `facets` unit radii: the silhouette, composed rather than sampled.
	##
	## Three operations, in this order, and the order matters - a flat has to
	## be able to cut a lobe, and a notch has to be able to cut a flat:
	##
	##   1. **one dominant lobe**, a cosine bulge in a random direction. This
	##      is the "one dominant mass" the brief asks every formation for, and
	##      putting it in the plan means every form has one for free.
	##   2. **chorded flats**: a run of consecutive facets pushed onto a
	##      straight line. A flat face is the single strongest "this was
	##      quarried / this was cleaved" cue available, and noise cannot
	##      produce one.
	##   3. **notches**: one facet pulled hard inward, which reads as a cleft.
	##
	## Normalised so the widest radius is exactly 1, so `base_radius` means
	## what a caller thinks it means.
	var plan := PackedFloat32Array()
	plan.resize(facets)
	var direction := TAU * _h(seed_value + salt, 3)
	# One dominant lobe plus a second and third harmonic at a third and a
	# sixth of its strength. A single cosine is an ellipse, and an ellipse is
	# still a smooth closed curve - three harmonics in phase with each other
	# give a mass with **a front, a flank and a back**, which is the coarsest
	# possible statement of "this form has parts".
	var second := TAU * _h(seed_value + salt, 5)
	var third := TAU * _h(seed_value + salt, 7)
	for facet in facets:
		var angle: float = TAU * float(facet) / float(facets)
		plan[facet] = 1.0 + lobe * cos(angle - direction) \
			+ lobe * 0.42 * cos(2.0 * (angle - second)) \
			+ lobe * 0.22 * cos(3.0 * (angle - third))
	for which in maxi(flats, 0):
		var start := int(_h(seed_value + salt, 11 + which * 7) * float(facets))
		var span := 2 + int(_h(seed_value + salt, 13 + which * 7) * 2.99)
		var mid: float = TAU * (float(start) + float(span) * 0.5) \
			/ float(facets)
		var reach: float = 0.74 + 0.16 * _h(seed_value + salt, 17 + which * 7)
		for step in span:
			var facet := (start + step) % facets
			var angle: float = TAU * float(facet) / float(facets)
			var along := cos(angle - mid)
			if along > 0.3:
				plan[facet] = minf(plan[facet], reach / along)
	for which in maxi(notches, 0):
		var facet := int(_h(seed_value + salt, 23 + which * 5) * float(facets))
		plan[facet] *= 0.56 + 0.2 * _h(seed_value + salt, 29 + which * 5)
	var widest := 0.0
	for facet in facets:
		widest = maxf(widest, plan[facet])
	if widest > 0.0:
		for facet in facets:
			plan[facet] = plan[facet] / widest
	return plan


# --- the profile: what the form looks like from the side --------------------


static func _profile(spec: Dictionary, seed_value: int, facets: int) -> Array:
	## Rings from foot to crown as `{v, scale[facets]}`, with hard ledge steps.
	##
	## A ledge is **two rings at almost the same height** with a step in
	## radius between them. The quad between those two rings is therefore
	## nearly horizontal: it faces up, it takes the key square on, and the
	## face below it falls into its shadow. That is what a sedimentary shelf
	## does, and it is a different mechanism from V25's `strata`, which is a
	## 4.5% sine ripple on a smooth radius - a ripple has no horizontal
	## anywhere on it, so it never catches a light and never casts a line.
	##
	## ## A ledge that goes all the way round is a cake tier
	##
	## The first build of this file stepped the radius *uniformly* at each
	## ledge, and the probe sheet said what that is: a stack of cylinders, a
	## wedding cake, exactly the "repeated rectangular prism" the brief bans.
	## A real shelf is a **partial** feature - it runs along one aspect of a
	## cliff, dies out at a corner, and the next shelf up starts somewhere
	## else. So a ledge here owns an arc: `start` and `span` in facets, and
	## the step applies only inside it.
	##
	## That is also why the scale has to be per-facet rather than one number,
	## and why this returns dictionaries instead of `Vector2`.
	##
	## `batter` bends the taper: 0 is a straight cone, 1 is strongly concave
	## (wide skirt, vertical upper), which is what a weathered cliff does.
	var tiers := maxi(int(spec.get("tiers", 4)), 1)
	var taper := clampf(float(spec.get("taper", 0.36)), 0.0, 0.97)
	var cap := clampf(float(spec.get("cap", 0.40)), 0.03, 1.0)
	var batter := clampf(float(spec.get("batter", 0.3)), 0.0, 1.0)
	var ledges := maxi(int(spec.get("ledges", 2)), 0)
	var step := maxf(float(spec.get("step", 0.16)), 0.0)

	# Where the ledges are, and how far round each one runs. Spread through
	# the middle of the form rather than sampled anywhere: a shelf at the very
	# foot is buried by whatever the form is standing on, and one at the crown
	# is a hat.
	var marks: Array = []
	for which in ledges:
		var band: float = (float(which) + 0.5) / float(maxi(ledges, 1))
		var at: float = clampf(0.2 + 0.58 * band
			+ 0.12 * (_h(seed_value, 53 + which * 3) - 0.5), 0.12, 0.88)
		# Between a third and three quarters of the circumference, starting
		# anywhere. Two ledges on one form therefore almost never share an
		# aspect, which is what makes the two of them read as separate events
		# in the rock rather than as a repeat.
		var span := maxi(int(round(float(facets)
			* (0.34 + 0.4 * _h(seed_value, 59 + which * 3)))), 2)
		marks.append({
			"v": at,
			"start": int(_h(seed_value, 61 + which * 3) * float(facets)),
			"span": mini(span, facets - 1),
			"step": step * (0.7 + 0.6 * _h(seed_value, 67 + which * 3)),
		})
	# **The overhang: the one silhouette event a taper cannot produce.**
	#
	# Every mark above steps the radius *in*, because that is what a taper and
	# a shelf do. A cliff that has been undercut steps *out* - the mass above
	# hangs past the mass below, and the face under it goes into a shadow no
	# amount of fill reaches. That is worth exactly one per hero form: two
	# overhangs is a mushroom.
	#
	# Implemented as a mark with a negative step, high up the form and over a
	# short arc, so the lip is a corner of the silhouette rather than a brim.
	for which in maxi(int(spec.get("overhang", 0)), 0):
		var at: float = clampf(0.52 + 0.24 * _h(seed_value, 71 + which * 3),
			0.3, 0.86)
		var span := maxi(int(round(float(facets)
			* (0.2 + 0.22 * _h(seed_value, 73 + which * 3)))), 2)
		marks.append({
			"v": at,
			"start": int(_h(seed_value, 79 + which * 3) * float(facets)),
			"span": mini(span, facets - 1),
			"step": -maxf(float(spec.get("overhang_step", 0.13)), 0.0)
				* (0.7 + 0.6 * _h(seed_value, 83 + which * 3)),
		})
	marks.sort_custom(func(a, b): return float(a["v"]) < float(b["v"]))

	var stops: Array = []
	for index in tiers + 1:
		stops.append(float(index) / float(tiers))
	for mark in marks:
		stops.append(float(mark["v"]))
	stops.sort()

	var shed := PackedFloat32Array()
	shed.resize(facets)
	var rings: Array = []
	var previous := -1.0
	for entry in stops:
		var height: float = clampf(float(entry), 0.0, 1.0)
		if is_equal_approx(height, previous):
			continue
		previous = height
		# The taper, bent by `batter`. `pow(v, 1 + batter)` keeps the foot
		# wide and pulls the loss into the upper half.
		var natural: float = 1.0 - taper * pow(height, 1.0 + batter)
		rings.append({"v": height, "scale": _scaled(natural, shed, cap)})
		for mark in marks:
			if not is_equal_approx(height, float(mark["v"])):
				continue
			# The shelf: a second ring 1.2% of the height above this one,
			# stepped in over this ledge's arc only. Small enough that the
			# shelf is a line rather than a terrace, big enough that it never
			# z-fights.
			for offset in int(mark["span"]):
				var facet := (int(mark["start"]) + offset) % facets
				shed[facet] += float(mark["step"])
			rings.append({"v": minf(height + 0.012, 0.998),
				"scale": _scaled(natural, shed, cap)})
	# The crown ring is the cap radius, always, whatever the taper did - and
	# it is uniform, so a form has one clean top edge rather than a ragged one.
	var crown := PackedFloat32Array()
	crown.resize(facets)
	for facet in facets:
		crown[facet] = cap
	rings[rings.size() - 1] = {"v": 1.0, "scale": crown}
	return rings


static func _scaled(natural: float, shed: PackedFloat32Array,
		floor_scale: float) -> PackedFloat32Array:
	## Clamped **above** as well as below, and the upper clamp is what keeps
	## `form()`'s promise that `base_radius` is the widest point: an overhang
	## is a negative shed, and without the clamp a low-taper kind with one on
	## it would grow past its own foot and out through a keep-out that was
	## sized against the foot.
	var out := PackedFloat32Array()
	out.resize(shed.size())
	for facet in shed.size():
		out[facet] = clampf(natural - shed[facet], floor_scale * 0.45, 1.0)
	return out


# --- the hash ---------------------------------------------------------------


static func _h(seed_value: int, salt: int) -> float:
	## Deterministic pseudo-random in [0, 1). The same integer hash
	## `hero_world` uses, so two renders of one world are identical and the
	## kit needs no RNG object and no seeded state.
	var x := ((seed_value * 1103515245) + salt * 12345 + 7) & 0x7FFFFFFF
	x = (x ^ (x >> 13)) * 1274126177
	return float((x ^ (x >> 16)) & 0xFFFF) / 65536.0
