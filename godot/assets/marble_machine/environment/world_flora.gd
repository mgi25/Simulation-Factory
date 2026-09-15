extends RefCounted

## THE VEGETATION KIT: five stylised plants, built from tiers rather than
## from one cone.
##
## V25's tree is `smooth_mass(top, stem, salt, 8, 5, 0.93)` - one mass with
## eight facets driven to a near-cone - and V25's own argument for it is that
## at 270 pixels a modelled branch structure is four dark pixels either way,
## so a silhouette is the correct amount of tree.
##
## That argument is half right and the half it gets wrong is the expensive
## half. A silhouette *is* all a viewer reads at phone size. But 188 copies of
## **one** silhouette, and that silhouette a cone, is what the review saw and
## called spikes: in the finish frames they line up along the crest as a row of
## identical dark teal triangles, which is the single most legible piece of
## procedural repetition in the film.
##
## The fix is not detail. It is **variety in the silhouette** at the same
## triangle cost:
##
##   * a conifer built from three or four **stacked tiers** has a stepped
##     outline rather than a straight one, and a stepped outline reads as a
##     tree at any size a cone reads as a spike
##   * tiers of **different widths and drops** mean two trees from the same
##     generator have different outlines
##   * a **trunk** below the lowest tier is eight triangles and is the
##     difference between a tree and a shape
##   * a **lean** and an off-centre crown break the file's own worst habit,
##     which is bilateral symmetry about a vertical axis
##
## Five entries: two conifers, a hero, a shrub and a ground clump. A cluster
## in `environment_world._trees` is composed from these rather than filled
## with one of them.
##
## ## Cost
##
## A `conifer` is 3 tiers x 7 facets x 2 triangles, plus a 5-triangle cap per
## tier and an 8-triangle trunk: **65 triangles**, against V25's cone at
## 8 x 5 x 2 + 8 = **88**. Cheaper, again, and for the same reason as the rock
## kit: the quality was in where the edges are.

## ## V25.2: why three tiers were still a triangle
##
## V25.1 was right that the fix is variety in the silhouette rather than
## detail, and the finish frame says it did not go far enough. Every tier is a
## **cone on a circular-ish plan with its apex on the axis**, so a stack of
## them is a taller cone: the outline is still two straight lines meeting at a
## point, which is the one silhouette the review keeps calling a spike. At
## finish distance the three tiers are three shallow notches on an otherwise
## perfect triangle.
##
## Three options fix that, and like the rock kit's they all default to off, so
## a profile that does not name them grows V25.1's plant exactly:
##
##     bough     the apex comes off the axis, so a tier leans one way
##               rather than closing over its own centre. Two boughs in
##               different directions up one tree is the end of bilateral
##               symmetry.
##     ragged    the skirt height varies per facet, so the lower edge of a
##               tier is a broken line of drooping tips rather than a rim.
##     aspect    a per-plant width-to-height jitter, so two conifers from one
##               generator are not the same tree at two scales.
##
## And one new kind. `snag` is a dead standing stem with two stub tiers near
## the top: the cheapest thing in the kit at about 30 triangles and the most
## distinct silhouette in it, because it is the only plant here that is mostly
## vertical line. It is in the kit but in no cluster unless a profile names it
## in `trees.roles` - a composition is data, not a constant.

const Geometry := preload("res://scripts/toy_geometry.gd")
const Forms := preload("res://assets/marble_machine/lab_forms.gd")


## `tiers` is how many crown cones; `spread` the widest tier's radius as a
## fraction of height; `drop` how much of the height the crown occupies;
## `trunk` the bare stem below it, also as a fraction of height.
const KINDS := {
	# The workhorse. Three tiers, a visible stem, a broad base tier.
	"conifer": {
		"tiers": 3, "facets": 7, "spread": 0.26, "drop": 0.80,
		"trunk": 0.17, "lean": 0.05, "shrink": 0.66, "overlap": 0.30,
		"material": "conifer_deep",
	},
	# The narrow one, for a cluster's back row: taller for its width, more
	# tiers, a tighter step.
	"spruce": {
		"tiers": 4, "facets": 7, "spread": 0.21, "drop": 0.84,
		"trunk": 0.13, "lean": 0.07, "shrink": 0.74, "overlap": 0.34,
		"material": "conifer_dark",
	},
	# **One hero silhouette per cluster.** The tallest form, the longest bare
	# trunk, a wide lowest tier and a deliberate lean. This is the tree a
	# viewer actually looks at; the others are the group it stands in.
	# The first build made this the *widest* form as well as the tallest, and
	# the probe sheet called it what it was: a parasol. A hero tree is taller
	# than its neighbours, not fatter - `spread` comes down while `drop` and
	# `trunk` go up, so what distinguishes it is a long bare stem under a
	# narrow crown, which is what an emergent conifer looks like.
	"hero": {
		"tiers": 4, "facets": 8, "spread": 0.23, "drop": 0.80,
		"trunk": 0.22, "lean": 0.10, "shrink": 0.68, "overlap": 0.34,
		"crown_off": 0.10, "material": "conifer_deep",
	},
	# Low, wide, no trunk: two or three lumps that break a bare slope without
	# adding a vertical.
	"shrub": {
		"tiers": 2, "facets": 6, "spread": 0.62, "drop": 1.0,
		"trunk": 0.0, "lean": 0.13, "shrink": 0.72, "overlap": 0.52,
		"squash": 0.42, "material": "world_shrub",
	},
	# Ground cover: one squashed lump, for the foot of a cluster and for the
	# lee of a ledge. The cheapest thing in the world at 12 triangles.
	"tuft": {
		"tiers": 1, "facets": 6, "spread": 0.9, "drop": 1.0,
		"trunk": 0.0, "lean": 0.18, "shrink": 1.0, "overlap": 0.0,
		"squash": 0.3, "material": "world_shrub",
	},
	# **The third silhouette, and the one that is not a triangle.** A dead
	# standing stem: two thirds bare trunk, two small stub tiers at the top,
	# a strong lean. A stand of conifers with one snag in it reads as a place
	# with a history; a stand of conifers with one more conifer in it reads as
	# a stand of conifers.
	"snag": {
		"tiers": 2, "facets": 6, "spread": 0.15, "drop": 0.36,
		"trunk": 0.66, "lean": 0.16, "shrink": 0.62, "overlap": 0.18,
		"stem_width": 0.42, "material": "conifer_dark",
	},
}


static func known(kind: String) -> bool:
	return KINDS.has(kind)


static func kinds() -> Array:
	return KINDS.keys()


static func plant(kind: String, height: float, seed_value: int, palette,
		opts := {}) -> Node3D:
	## One plant, as a node whose origin is the foot.
	##
	## Returned as a node rather than as a mesh because a tiered conifer is
	## several meshes sharing one material, and merging them into one surface
	## would cost a `SurfaceTool` commit per tree rather than a shared mesh
	## resource per *kind and size*. The meshes here are generated per plant
	## because each one differs; what is shared is the material, which is what
	## the draw-call count actually turns on.
	var spec: Dictionary = (KINDS.get(kind, KINDS["conifer"]) as Dictionary) \
		.duplicate()
	for key in opts:
		spec[key] = opts[key]

	var node := Node3D.new()
	node.name = "Plant"
	var facets := maxi(int(spec.get("facets", 7)), 5)
	var tiers := maxi(int(spec.get("tiers", 3)), 1)
	var spread := float(spec.get("spread", 0.3)) * height
	var drop := clampf(float(spec.get("drop", 0.78)), 0.1, 1.0)
	var trunk := clampf(float(spec.get("trunk", 0.18)), 0.0, 0.7)
	var shrink := clampf(float(spec.get("shrink", 0.66)), 0.2, 0.98)
	var overlap := clampf(float(spec.get("overlap", 0.3)), 0.0, 0.8)
	var squash := float(spec.get("squash", 1.0))
	var offset := float(spec.get("crown_off", 0.0))
	var key := str(spec.get("material", "conifer_deep"))
	var material = palette.get_material(key)

	# **The per-plant aspect jitter.** Two plants of one kind differed only in
	# height and in the per-tier radius noise, which at phone size is two
	# copies of the same tree. This puts a real width-to-height spread on the
	# kind itself: `aspect` 0.3 means a plant is between 15% narrower and 15%
	# wider for its height than the kind's nominal.
	var aspect := float(spec.get("aspect", 0.0))
	if aspect > 0.0:
		spread *= 1.0 + aspect * (_h(seed_value, 41) - 0.5)

	var base := height * trunk
	if trunk > 0.01:
		# A stem. Four-sided and untapered: at this size it is two or three
		# pixels wide and its only job is to hold the crown off the ground,
		# which is the cue that separates a tree from a bush.
		var girth := spread * float(spec.get("stem_width", 0.15))
		var stem := Forms.mesh_node(
			Geometry.rounded_box(Vector3(girth, base * 1.06, girth),
				spread * 0.04, 1),
			palette.get_material(str(spec.get("stem", key))), "Stem", false)
		stem.position.y = base * 0.53
		node.add_child(stem)

	# The crown, tier by tier from the bottom up. Each tier is a cone whose
	# base overlaps the top of the one below, so the outline steps in rather
	# than stepping *out* - which is what a fir does and what a stack of
	# separated discs does not.
	var span := height * drop
	var step := span / (float(tiers) - (float(tiers) - 1.0) * overlap)
	var lean := float(spec.get("lean", 0.05))
	var lean_dir := TAU * _h(seed_value, 3)
	for tier in tiers:
		var scale: float = pow(shrink, float(tier))
		var radius: float = spread * scale * (0.86 + 0.28 * _h(
			seed_value * 5 + tier, 11))
		var tall: float = step * (1.0 + overlap) * (0.82 + 0.36 * _h(
			seed_value * 7 + tier, 13)) * squash
		var foot: float = base + step * float(tier) * (1.0 - overlap * 0.0)
		var slide: float = lean * height * (float(tier) / float(maxi(tiers, 1)))
		# **The lean grows with height, and that is what stops the tip being a
		# spike.** A uniform `bough` leans every tier the same amount, which
		# is a leaning cone - still one straight outline. Scaling it up the
		# plant puts the largest offset on the topmost tier, whose apex is the
		# only point on a conifer a viewer reads as *the* point.
		var reach: float = float(spec.get("bough", 0.0))
		if reach > 0.0 and tiers > 1:
			reach *= 0.55 + 0.9 * float(tier) / float(tiers - 1)
		var mesh := _tier(radius, tall, facets, seed_value * 11 + tier * 3,
			reach, float(spec.get("ragged", 0.0)))
		var cone := Forms.mesh_node(mesh, material, "Tier%d" % tier, false)
		cone.position = Vector3(
			cos(lean_dir) * slide + cos(lean_dir) * spread * offset
				* float(tier) / float(maxi(tiers, 1)),
			foot,
			sin(lean_dir) * slide + sin(lean_dir) * spread * offset
				* float(tier) / float(maxi(tiers, 1)))
		cone.rotation.y = _h(seed_value * 13 + tier, 17) * TAU
		node.add_child(cone)
	return node


static func _tier(radius: float, height: float, facets: int,
		seed_value: int, bough := 0.0, ragged := 0.0) -> ArrayMesh:
	## One crown tier: a flat-shaded cone on an irregular plan.
	##
	## The plan is jittered per facet by up to a quarter of the radius, which
	## at any distance is the difference between an outline that is a straight
	## line and one that has a bite out of it. Flat-shaded, like the rock, so
	## the lit side and the shadow side of a tier are two values rather than a
	## gradient - a tree that shades smoothly reads as a plastic cone.
	var surface := SurfaceTool.new()
	surface.begin(Mesh.PRIMITIVE_TRIANGLES)
	var plan: Array = []
	for facet in facets:
		plan.append(radius * (0.76 + 0.34 * _h(seed_value + facet * 31, 23)))
	# **The apex comes off the axis.** A cone with its point over its centre
	# is bilaterally symmetric from every direction, and a stack of them is a
	# triangle. Leaning the apex by up to `bough` radii turns the tier into a
	# bough: one flank is long and shallow, the other short and steep, and
	# because the lean direction is hashed per tier the tiers of one tree lean
	# different ways.
	#
	# **Named `bough` rather than `tilt` for the reason `floor_lift` is not
	# `lift`:** `alpine_neon` already uses `tilt` for an aurora curtain angle.
	# The two are read by different builders out of different sections and
	# could not collide, and one name for two meanings is still a trap.
	var slew := TAU * _h(seed_value, 37)
	var peak := Vector3(cos(slew) * radius * bough, height,
		sin(slew) * radius * bough)
	var base: float = -height * 0.1
	var hub := Vector3(0.0, base, 0.0)
	var skirts := PackedFloat32Array()
	skirts.resize(facets)
	for facet in facets:
		# `ragged` drops alternating facets of the rim. A tier whose lower
		# edge is a broken line of tips reads as branches; a tier whose lower
		# edge is a clean rim reads as a lampshade.
		skirts[facet] = base - height * ragged 			* _h(seed_value + facet * 43, 47)
	for facet in facets:
		var next := (facet + 1) % facets
		var a := Vector3(cos(TAU * float(facet) / float(facets)) * plan[facet],
			skirts[facet], sin(TAU * float(facet) / float(facets)) * plan[facet])
		var b := Vector3(cos(TAU * float(next) / float(facets)) * plan[next],
			skirts[next], sin(TAU * float(next) / float(facets)) * plan[next])
		var normal := (b - peak).cross(a - peak)
		if normal.dot(a + b) < 0.0:
			normal = -normal
		Geometry.quad_auto(surface, a, b, peak, peak, normal.normalized())
		# The underside, so a tier seen from below or in silhouette against
		# the sky is not an open shell.
		Geometry.quad_auto(surface, a, b, hub, hub, Vector3.DOWN)
	var mesh := ArrayMesh.new()
	surface.commit(mesh)
	return mesh


## How a cluster is composed, as `[kind, share]`. Read by
## `environment_world._trees`: a cluster takes its first plant from the head of
## this list and the rest by rotating through it, so every cluster gets exactly
## one hero and a mix behind it.
##
## **The composition is the placement fix.** V25 scattered `per_cluster`
## identical trees on a disc, and an even scatter of one silhouette is what
## reads as procedural however few of them there are. A dominant form with a
## group behind it is what a stand of trees looks like from the air.
const CLUSTER := ["hero", "conifer", "spruce", "conifer", "shrub", "spruce",
	"tuft", "conifer"]


static func _h(seed_value: int, salt: int) -> float:
	var x := ((seed_value * 1103515245) + salt * 12345 + 7) & 0x7FFFFFFF
	x = (x ^ (x >> 13)) * 1274126177
	return float((x ^ (x >> 16)) & 0xFFFF) / 65536.0
