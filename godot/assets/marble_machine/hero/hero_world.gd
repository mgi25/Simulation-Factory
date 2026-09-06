extends RefCounted

## THE ENVIRONMENT - a dusk gorge, in four depth layers.
##
## The V2 world was the right idea built the wrong way. Its masses were faceted
## prisms with heavy per-facet jitter and flat shading, which is honest at four
## hundred units and reads as primitive low-poly blocks at eighty - and eighty
## is where the frame's dark shoulders actually live. The brief's note is exact:
## acceptable for distant silhouettes, too obvious as the primary backdrop.
##
## So the rock builder here is different in three ways.
##
## **Smooth normals.** Vertices carry averaged normals computed from their own
## neighbours, so light rolls across a mass instead of stopping at every facet
## edge. The silhouette is still irregular; the shading no longer announces the
## polygon count.
##
## **Two octaves of noise, not one jitter.** A broad octave shapes the macro
## form and a fine one roughens it. One octave of per-facet randomness gives
## crumpled foil; two octaves at different frequencies give a landform.
##
## **Value, not just fog.** Four rock materials from `#161D27` to `#425C76`,
## one per layer. Fog can only remove contrast, and a range that is merely
## faded reads as the same rock behind dirty glass. Distance has to be painted.
##
## ## The four layers
##
##     ~62u    NEAR CLIFF   the frame's dark shoulders, almost black
##     ~150u   MID CLIFF    the middle value, where the architecture lives
##     ~330u   FAR RIDGE    close to sky value, only a silhouette
##     ~620u   HAZE / SKY   cloud banks and the warm dusk band
##
## ## Camera arithmetic, because it decides every placement
##
## The hero lens is a 32-degree vertical field at 22 degrees of elevation,
## fitted to a 34-unit extent, which puts the camera about 60 units out and 36
## up. Two consequences:
##
## The frame's top edge is 6 degrees *below* horizontal, so at 200 units it is
## at y = 15 and at 400 units it is at y = -6. Anything placed on a notional
## horizon is above the shot. Everything distant is therefore sited low and
## checked against that line.
##
## A 9:16 frame at 32 degrees vertical is only about 18 degrees wide. Scenery
## has to sit near the view bearing (214 degrees, opposite the camera's 34) or
## it is simply not in the picture - and near crests packed shoulder to
## shoulder become one wall that occludes every layer behind them. The layout
## leaves a deliberate gap on the view bearing so the machine is read against
## light rather than against rock.

const Geometry := preload("res://scripts/toy_geometry.gd")
const Forms := preload("res://assets/marble_machine/lab_forms.gd")
const V2Forms := preload("res://assets/marble_machine/v2/v2_forms.gd")

# --- placement, and the one equation behind every number ------------------
#
# The hero lens looks *down* 21 degrees with a 32-degree vertical field, so the
# frame runs from 5 degrees below the camera's horizon at the top edge to 37
# degrees below at the bottom. Everything distant is placed by where its crest
# should sit in that band:
#
#     crest_y = 38.0 - d * tan(-elevation)
#
# with `d` the horizontal distance from the camera - about 61 units plus the
# mass's own radius from the machine.
#
# The mistake this replaces is worth recording, because it is not obvious. If
# every layer is given the same crest *height*, then each further layer sits
# lower in the frame than the one in front and the whole background collapses
# into a staircase falling away from the viewer - a cave, not a gorge. Distant
# terrain has to be **taller** to appear at the same angle. So the crest
# heights below rise with distance while the crest *angles* fall gently:
#
#     NEAR   d ~200   crest -7 deg    y = +13     the frame's dark shoulders
#     MID    d ~340   crest -10 deg   y = -22     seen through the gap
#     FAR    d ~530   crest -13 deg   y = -84     nearly haze value
#     BAND   d ~700   crest -14 deg   y = -136    warm light behind it all
#
# The near shoulders sit at bearing 213 +/- 23, which puts their inner edges
# about 5 degrees off the view axis against a 9.2-degree half-frame: a
# deliberate window on the view bearing, roughly a third of the frame's width,
# so the machine is read against light rather than against rock. Packed
# shoulder to shoulder they would be one wall, and one wall at two hundred
# units occludes every layer behind it.
#
# bearing, radius, height, base radius, seed
const NEAR_CLIFFS := [
	[190.0, 148.0, 130.0, 36.0, 3],
	[236.0, 154.0, 134.0, 37.0, 11],
	[166.0, 174.0, 128.0, 38.0, 19],
	[260.0, 180.0, 130.0, 38.0, 27],
	[140.0, 206.0, 124.0, 40.0, 35],
	[286.0, 210.0, 122.0, 40.0, 43],
	[108.0, 244.0, 118.0, 42.0, 51],
	[316.0, 240.0, 120.0, 42.0, 59],
]

const MID_CLIFFS := [
	[213.0, 272.0, 154.0, 50.0, 67],
	[204.0, 292.0, 152.0, 52.0, 73],
	[222.0, 300.0, 154.0, 52.0, 29],
	[196.0, 322.0, 150.0, 54.0, 37],
	[230.0, 330.0, 152.0, 54.0, 13],
	[186.0, 352.0, 148.0, 56.0, 45],
	[240.0, 360.0, 146.0, 56.0, 53],
	[172.0, 388.0, 144.0, 58.0, 5],
	[254.0, 396.0, 142.0, 58.0, 61],
	[156.0, 424.0, 140.0, 60.0, 91],
	[270.0, 432.0, 138.0, 60.0, 95],
	[138.0, 462.0, 136.0, 62.0, 99],
	[288.0, 470.0, 134.0, 62.0, 101],
]

const FAR_RIDGES := [
	[211.0, 466.0, 176.0, 92.0, 77],
	[228.0, 508.0, 180.0, 92.0, 83],
	[194.0, 516.0, 180.0, 92.0, 89],
	[246.0, 562.0, 186.0, 96.0, 97],
	[176.0, 574.0, 186.0, 96.0, 103],
	[214.0, 622.0, 196.0, 104.0, 109],
	[150.0, 644.0, 196.0, 98.0, 113],
	[272.0, 652.0, 198.0, 100.0, 127],
]

# Tall lit structures standing on the mid crests: bearing, radius, base y,
# height, width, seed. What says "inhabited" rather than "canyon". Sited on
# the crest line, in the mid rock's own value, so they read as distant
# buildings instead of as black cut-outs floating in the haze.
const STRUCTURES := [
	[203.5, 246.0, -54.0, 43.0, 5.2, 2],
	[206.5, 268.0, -56.0, 46.0, 5.6, 6],
	[204.5, 292.0, -58.0, 44.0, 5.4, 14],
	[220.0, 252.0, -54.0, 42.0, 5.0, 22],
	[217.0, 274.0, -56.0, 45.0, 5.4, 26],
	[219.5, 298.0, -59.0, 43.0, 5.2, 34],
]

const SPIRES_PER_CREST := 3

# The bearing the hero camera looks along, opposite its own azimuth of 22.
# Every table below is authored around 213 - the bearing of the first camera
# this world was built for - and offset here, so re-aiming the lens is one
# number rather than sixty. The offset exists because the sweep moved the hero
# azimuth from 33 to 22 and the whole gorge stayed pointing at the old one:
# the shoulders ended up outside the frame and the machine was left standing
# against open sky.
# Visual layer 2, matched by `WorldKey`'s cull mask below.
const WORLD_LAYER := 2

const AUTHORED_BEARING := 213.0
const VIEW_BEARING := 202.0
const BEARING_SHIFT := VIEW_BEARING - AUTHORED_BEARING


static func _polar(bearing_degrees: float, radius: float, y: float) -> Vector3:
	var angle := deg_to_rad(bearing_degrees + BEARING_SHIFT)
	return Vector3(sin(angle) * radius, y, cos(angle) * radius)


static func _hash01(seed_value: int) -> float:
	## A deterministic pseudo-random in [0,1). No RNG, no clock: two renders
	## of this world are byte-identical.
	var x := (seed_value * 1103515245 + 12345) & 0x7FFFFFFF
	x = (x ^ (x >> 13)) * 1274126177
	return float((x ^ (x >> 16)) & 0xFFFF) / 65536.0


static func _noise(seed_value: int, u: float, v: float) -> float:
	## Smoothly interpolated value noise on a small integer lattice.
	##
	## `u` wraps around the mass (it is an angle) and `v` runs up it. Cubic
	## smoothstep between lattice points, which is what turns the hash's
	## per-cell randomness into a continuous surface - the difference between
	## a landform and crumpled foil.
	var lattice := 8.0
	var x := u * lattice
	var y := v * lattice
	var x0 := int(floor(x))
	var y0 := int(floor(y))
	var fx: float = smoothstep(0.0, 1.0, x - float(x0))
	var fy: float = smoothstep(0.0, 1.0, y - float(y0))
	var wrap := int(lattice)
	var a := _hash01(seed_value * 7919 + posmod(x0, wrap) * 131 + y0 * 17)
	var b := _hash01(seed_value * 7919 + posmod(x0 + 1, wrap) * 131 + y0 * 17)
	var c := _hash01(seed_value * 7919 + posmod(x0, wrap) * 131 + (y0 + 1) * 17)
	var d := _hash01(seed_value * 7919 + posmod(x0 + 1, wrap) * 131
		+ (y0 + 1) * 17)
	return lerpf(lerpf(a, b, fx), lerpf(c, d, fx), fy)


static func _mass_point(height: float, base_radius: float, seed_value: int,
		u: float, v: float, taper_amount := 0.78) -> Vector3:
	## One point on a rock mass, as a function of angle `u` and height `v`.
	##
	## Radius is a tapering profile times two octaves of noise; height carries
	## a small independent displacement so ledges are not all level. Written
	## as a pure function so the normal can be found by sampling neighbours
	## rather than by accumulating face normals.
	var angle := TAU * u
	# `taper_amount` is the single most important number in the environment.
	# At 0.78 a mass is a cone, and a cone at two hundred units puts only its
	# foot in a frame whose top edge is five degrees below the horizon - which
	# is exactly why the first gorge read as a scatter of small hills. A gorge
	# *wall* keeps most of its width to the crest, so 0.34 is what the cliffs
	# use and the steeper value is left to the spires.
	var taper: float = 1.0 - taper_amount * pow(v, 1.45)
	# Three octaves. One gives crumpled foil, two give a landform, and the
	# third is what puts gullies and buttresses on a face that would
	# otherwise be a smooth shoulder - which is the whole difference between
	# a cliff and a dune at the distance these are read from.
	var broad: float = 0.70 + 0.60 * _noise(seed_value, u, v * 0.35)
	var fine: float = 0.84 + 0.32 * _noise(seed_value * 3 + 1, u * 2.6, v * 1.7)
	var grain: float = 0.90 + 0.20 * _noise(seed_value * 11 + 5, u * 6.2,
		v * 3.8)
	# Strata. A horizontal ripple in the radius, phase-shifted around the
	# mass by the broad octave so the bands are not perfect rings. This is
	# the cheapest thing in the file and the one that most makes a smooth
	# shoulder read as *rock*: sedimentary ledges catch the key along their
	# tops and shadow under their lips, and a cliff without them is a dune.
	var strata: float = 1.0 + 0.045 * sin(v * 23.0
		+ 5.0 * _noise(seed_value * 17 + 9, u * 1.3, 0.5))
	var radius: float = base_radius * taper * broad * fine * grain * strata
	var lift: float = height * (v + 0.10 * (
		_noise(seed_value * 5 + 2, u * 1.4, v * 0.8) - 0.5))
	return Vector3(cos(angle) * radius, lift, sin(angle) * radius)


static func smooth_mass(height: float, base_radius: float, seed_value: int,
		facets := 26, tiers := 14, taper_amount := 0.78) -> ArrayMesh:
	## A cliff mass with averaged normals and two octaves of relief.
	##
	## Normals come from the analytic surface: sample the neighbours in `u`
	## and `v` and cross their differences. That gives a genuinely smooth
	## shading field, so the same mesh reads as rolling stone at sixty units
	## and still holds a broken outline at four hundred.
	var surface := SurfaceTool.new()
	surface.begin(Mesh.PRIMITIVE_TRIANGLES)
	var du := 1.0 / float(facets)
	var dv := 1.0 / float(tiers)

	var points: Array = []
	var normals: Array = []
	for tier in tiers + 1:
		var v: float = float(tier) * dv
		var ring: Array = []
		var ring_normals: Array = []
		for facet in facets:
			var u: float = float(facet) * du
			var here := _mass_point(height, base_radius, seed_value, u, v,
				taper_amount)
			var along := _mass_point(height, base_radius, seed_value,
				u + du * 0.5, v, taper_amount) - _mass_point(height,
				base_radius, seed_value, u - du * 0.5, v, taper_amount)
			var up := _mass_point(height, base_radius, seed_value, u,
				minf(v + dv * 0.5, 1.0), taper_amount) - _mass_point(height,
				base_radius, seed_value, u, maxf(v - dv * 0.5, 0.0),
				taper_amount)
			var normal := up.cross(along)
			if normal.length_squared() < 1.0e-10:
				normal = Vector3(here.x, 0.0, here.z)
			if normal.length_squared() < 1.0e-10:
				normal = Vector3.UP
			ring.append(here)
			ring_normals.append(normal.normalized())
		points.append(ring)
		normals.append(ring_normals)

	for tier in tiers:
		var lower: Array = points[tier]
		var upper: Array = points[tier + 1]
		var lower_n: Array = normals[tier]
		var upper_n: Array = normals[tier + 1]
		for facet in facets:
			var next := (facet + 1) % facets
			Geometry.quad_smooth_auto(surface,
				[lower[facet], upper[facet], upper[next], lower[next]],
				[lower_n[facet], upper_n[facet], upper_n[next], lower_n[next]])

	# Close the crown with a fan so the mass has a top rather than a hole.
	var crown: Array = points[tiers]
	var crown_n: Array = normals[tiers]
	var peak := Vector3(0.0, height * 1.03, 0.0)
	for facet in facets:
		var next := (facet + 1) % facets
		Geometry.quad_smooth_auto(surface,
			[crown[facet], peak, peak, crown[next]],
			[crown_n[facet], Vector3.UP, Vector3.UP, crown_n[next]])

	var mesh := ArrayMesh.new()
	surface.commit(mesh)
	return mesh


static func build_environment(no_glow: bool) -> Environment:
	## Deep blue dusk, warm at the horizon, tone-mapped like a product shot.
	var sky_material := ProceduralSkyMaterial.new()
	sky_material.sky_top_color = Color("#030711")
	sky_material.sky_horizon_color = Color("#2A4658")
	sky_material.sky_curve = 0.11
	sky_material.sky_energy_multiplier = 1.0
	sky_material.ground_bottom_color = Color("#070D16")
	sky_material.ground_horizon_color = Color("#27404F")
	sky_material.ground_curve = 0.30
	sky_material.sun_angle_max = 44.0
	sky_material.energy_multiplier = 1.0

	var sky := Sky.new()
	sky.sky_material = sky_material

	var env := Environment.new()
	env.background_mode = Environment.BG_SKY
	env.sky = sky
	env.background_energy_multiplier = 0.44
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.ambient_light_sky_contribution = 1.0
	env.ambient_light_energy = 0.22
	env.reflected_light_source = Environment.REFLECTION_SOURCE_SKY

	env.tonemap_mode = Environment.TONE_MAPPER_ACES
	env.tonemap_exposure = 0.80
	env.tonemap_white = 14.0

	# Atmosphere. Density is set so the near cliffs lose a quarter of their
	# contrast, the mid cliffs half and the far ridges nearly all of it;
	# `aerial_perspective` makes that a shift toward the sky's colour rather
	# than a grey wash, which is the difference between haze and dirty glass.
	env.fog_enabled = true
	env.fog_mode = Environment.FOG_MODE_DEPTH
	env.fog_light_color = Color("#2C4C66")
	env.fog_light_energy = 0.80
	env.fog_sun_scatter = 0.32
	env.fog_density = 0.0026
	env.fog_sky_affect = 0.34
	env.fog_aerial_perspective = 0.70
	env.fog_height = -10.0
	env.fog_height_density = 0.030

	env.ssao_enabled = true
	env.ssao_radius = 0.85
	env.ssao_intensity = 2.3
	env.ssao_power = 1.5
	env.ssao_light_affect = 0.12

	env.ssr_enabled = true
	env.ssr_max_steps = 48
	env.ssr_fade_in = 0.2
	env.ssr_fade_out = 2.0

	if not no_glow:
		env.glow_enabled = true
		env.glow_intensity = 0.95
		env.glow_bloom = 0.19
		# Threshold above one so a lit *surface* blooms and a white shell
		# never does: bloom that starts below the pearl's own value eats the
		# shell's curvature, which is the brief's white-surface rule.
		env.glow_hdr_threshold = 1.35
		env.glow_hdr_scale = 2.2
		env.glow_blend_mode = Environment.GLOW_BLEND_MODE_SOFTLIGHT
		for level in 7:
			env.set_glow_level(level, 0.0)
		env.set_glow_level(1, 0.3)
		env.set_glow_level(2, 0.65)
		env.set_glow_level(3, 0.85)
		env.set_glow_level(4, 0.45)

	env.adjustment_enabled = true
	env.adjustment_contrast = 1.06
	env.adjustment_saturation = 1.16
	env.adjustment_brightness = 1.0
	return env


static func build(palette) -> Node3D:
	var root := Node3D.new()
	root.name = "World"

	_layer(root, palette, NEAR_CLIFFS, "rock_soft_near", -117.0, "NearCliffs",
		44, 22, 0.30, "rock_ledge_hero")
	_layer(root, palette, MID_CLIFFS, "rock_soft_mid", -174.0, "MidCliffs",
		32, 16, 0.36, "rock_soft_near")
	_layer(root, palette, FAR_RIDGES, "rock_soft_far", -244.0, "FarRidges",
		24, 12, 0.42, "rock_soft_mid")
	_layer(root, palette, FAR_RIDGES, "rock_soft_haze", -258.0, "HazeRidges",
		20, 10, 0.46, "rock_soft_far")
	_spires(root, palette)
	_scrub(root, palette)
	_structures(root, palette)
	_dusk_band(root, palette)
	_clouds(root, palette)
	_ledge(root, palette)
	_valley_lights(root, palette)
	_assign_layer(root)
	return root


static func _assign_layer(node: Node) -> void:
	## Put every environment mesh on visual layer 2.
	##
	## What this buys is the one thing a single sun cannot give: the gorge and
	## the machine want *different* key directions. A three-quarter front key
	## is what makes a moulded pearl shell read, and it is also what flattens
	## a cliff into a paper cut-out, because a large smooth mass lit from the
	## direction it faces has no gradient across it at all. Two directionals
	## with complementary cull masks is the standard answer - a product key on
	## the subject, a raking key on the background - and it costs one extra
	## light and one integer per mesh.
	if node is VisualInstance3D:
		(node as VisualInstance3D).layers = WORLD_LAYER
	for child in node.get_children():
		_assign_layer(child)


static func _layer(root: Node3D, palette, entries: Array, material_key: String,
		base_y: float, group_name: String, facets: int, tiers: int,
		taper_amount := 0.78, alternate_key := "") -> void:
	var group := Node3D.new()
	group.name = group_name
	root.add_child(group)
	var material = palette.get_material(material_key)
	var alternate = palette.get_material(
		alternate_key if alternate_key != "" else material_key)
	for index in entries.size():
		var entry: Array = entries[index]
		# Alternating between the layer's own value and the one a step
		# darker, so adjacent masses read as separate objects where they
		# overlap rather than merging into one silhouette.
		var shade = material if index % 2 == 0 else alternate
		var node := Forms.mesh_node(
			smooth_mass(float(entry[2]), float(entry[3]), int(entry[4]),
				facets, tiers, taper_amount),
			shade, "Mass%d" % index, false)
		var radius: float = float(entry[1])
		if group_name == "HazeRidges":
			radius *= 1.62
		node.position = _polar(float(entry[0]) + (7.0
			if group_name == "HazeRidges" else 0.0), radius, base_y)
		node.rotation.y = float(entry[4]) * 0.37
		group.add_child(node)


static func _spires(root: Node3D, palette) -> void:
	## Rock teeth along the near and mid crest lines.
	##
	## A smooth mass reads as stone but its outline is still a soft dome, and
	## a soft dome at any distance reads as a hill rather than as a gorge
	## wall. Five thin masses per crest, sited by arithmetic on the crest's own
	## seed, break that outline for almost no triangles.
	var group := Node3D.new()
	group.name = "Spires"
	root.add_child(group)

	for which in [[NEAR_CLIFFS, -117.0, "rock_soft_near", 0.88],
			[MID_CLIFFS, -174.0, "rock_soft_mid", 0.90]]:
		var walls: Array = which[0]
		var base_y: float = which[1]
		var material = palette.get_material(str(which[2]))
		var crest: float = which[3]
		for index in walls.size():
			var entry: Array = walls[index]
			var bearing := float(entry[0])
			var radius := float(entry[1])
			var height := float(entry[2])
			var spread := float(entry[3])
			var seed_value := int(entry[4])
			for step in SPIRES_PER_CREST:
				var jitter := _hash01(seed_value * 13 + step * 29)
				var swing := _hash01(seed_value * 7 + step * 11) - 0.5
				var offset := float(step) / float(SPIRES_PER_CREST) - 0.45
				var spire_height: float = height * (0.09 + 0.13 * jitter)
				var node := Forms.mesh_node(
					smooth_mass(spire_height,
						spread * (0.15 + 0.14 * jitter),
						seed_value * 31 + step, 14, 8, 0.50),
					material, "Spire%d_%d" % [index, step], false)
				node.position = _polar(
					bearing + offset * spread * 42.0 / maxf(radius, 1.0),
					radius + swing * spread * 0.6,
					base_y + height * (crest + 0.14 * swing))
				node.rotation.y = float(seed_value + step) * 0.53
				group.add_child(node)


static func _scrub(root: Node3D, palette) -> void:
	## Dark clusters along the crest lines.
	##
	## A gorge wall read at a hundred and fifty units is mostly silhouette and
	## value, and a mass with a clean smooth outline reads as cut paper no
	## matter how well shaded its face is. What breaks that is a *fringe*: a
	## scatter of small dark forms sitting on the crest, catching almost no
	## key and biting irregular notches out of the skyline. Eight per crest at
	## a twentieth of the crest's own size, placed by arithmetic on its seed,
	## so this is dense, varied and byte-identical between renders.
	var group := Node3D.new()
	group.name = "Scrub"
	root.add_child(group)

	for which in [[NEAR_CLIFFS, -117.0, "rock_ledge_hero", 0.90],
			[MID_CLIFFS, -174.0, "rock_soft_near", 0.92]]:
		var walls: Array = which[0]
		var base_y: float = which[1]
		var material = palette.get_material(str(which[2]))
		var crest: float = which[3]
		for index in walls.size():
			var entry: Array = walls[index]
			var bearing := float(entry[0])
			var radius := float(entry[1])
			var height := float(entry[2])
			var spread := float(entry[3])
			var seed_value := int(entry[4])
			for step in 8:
				var jitter := _hash01(seed_value * 23 + step * 41)
				var swing := _hash01(seed_value * 19 + step * 7) - 0.5
				var lift := _hash01(seed_value * 5 + step * 13) - 0.5
				var offset := float(step) / 8.0 - 0.45
				var clump: float = spread * (0.035 + 0.045 * jitter)
				var node := Forms.mesh_node(
					smooth_mass(clump * 2.4, clump, seed_value * 53 + step,
						10, 6, 0.52),
					material, "Scrub%d_%d" % [index, step], false)
				node.position = _polar(
					bearing + offset * spread * 46.0 / maxf(radius, 1.0),
					radius + swing * spread * 0.75,
					base_y + height * (crest + 0.11 * lift))
				node.rotation.y = float(seed_value * 3 + step) * 0.71
				group.add_child(node)


static func _structures(root: Node3D, palette) -> void:
	## Distant architecture: tapered slabs with lit window bands and beacons.
	##
	## Abstract on purpose. At a hundred and fifty units a detailed building
	## and a correctly proportioned slab are the same pixels, and the slab
	## does not tempt anyone into modelling a city.
	var group := Node3D.new()
	group.name = "Structures"
	root.add_child(group)
	var shell = palette.get_material("far_structure")
	var window = palette.get_material("lit_far_window_hero")
	var warm = palette.get_material("lit_valley_hero")

	for index in STRUCTURES.size():
		var entry: Array = STRUCTURES[index]
		var bearing := float(entry[0])
		var height := float(entry[3])
		var width := float(entry[4])
		var pivot := Node3D.new()
		pivot.name = "Structure%d" % index
		pivot.position = _polar(bearing, float(entry[1]), float(entry[2]))
		pivot.rotation.y = -deg_to_rad(bearing + BEARING_SHIFT)
		group.add_child(pivot)

		var body := Forms.mesh_node(
			Geometry.rounded_box(Vector3(width, height, width * 0.8),
				width * 0.14, 2), shell, "Body", false)
		body.position = Vector3(0.0, height * 0.5, 0.0)
		pivot.add_child(body)

		var cap := Forms.mesh_node(
			Geometry.rounded_box(Vector3(width * 1.5, height * 0.08,
				width * 1.2), width * 0.12, 2), shell, "Cap", false)
		cap.position = Vector3(0.0, height * 0.95, 0.0)
		pivot.add_child(cap)

		var mast := Forms.mesh_node(
			Geometry.tube([Vector3.ZERO, Vector3(0.0, height * 0.28, 0.0)],
				width * 0.05, 6), shell, "Mast", false)
		mast.position = Vector3(0.0, height, 0.0)
		pivot.add_child(mast)

		var beacon := Forms.mesh_node(
			Geometry.rounded_disc(width * 0.07, width * 0.07, width * 0.03,
				8, 2), warm, "Beacon", false)
		beacon.position = Vector3(0.0, height * 1.29, 0.0)
		pivot.add_child(beacon)

		for row in 6:
			var y: float = height * (0.18 + 0.125 * float(row))
			var band := Forms.mesh_node(
				Geometry.rounded_box(
					Vector3(width * 0.96, height * 0.020, width * 0.80),
					width * 0.008, 1),
				window, "Band%d" % row, false)
			band.position = Vector3(0.0, y, 0.0)
			pivot.add_child(band)

		var sill := Forms.mesh_node(
			Geometry.rounded_box(
				Vector3(width * 1.3, height * 0.011, width * 0.10),
				width * 0.005, 1), warm, "Sill", false)
		sill.position = Vector3(0.0, height * 0.04, width * 0.45)
		pivot.add_child(sill)


static func _dusk_band(root: Node3D, palette) -> void:
	## The warm light behind the gorge, as five separated masses.
	##
	## Fog only subtracts contrast; something has to put light back into the
	## background or a gorge reads as a cave. A continuous glowing band across
	## the frame is the failure mode - it becomes a bright empty region and
	## flattens the whole upper third. Five masses at different bearings and
	## depths read as distant settlement instead: the same warmth, spent on
	## points rather than on a wash.
	var group := Node3D.new()
	group.name = "DuskBand"
	root.add_child(group)
	var layout := [
		[211.0, 700.0, -96.0, 250.0, 9.0, "lit_dusk_band"],
		[224.0, 756.0, -104.0, 200.0, 8.0, "lit_dusk_band"],
		[198.0, 774.0, -108.0, 190.0, 7.5, "lit_horizon_cool_hero"],
		[236.0, 728.0, -100.0, 160.0, 7.0, "lit_dusk_band"],
		[213.0, 640.0, -86.0, 150.0, 6.5, "lit_horizon_cool_hero"],
		[203.0, 616.0, -80.0, 130.0, 6.0, "lit_dusk_band"],
	]
	for index in layout.size():
		var entry: Array = layout[index]
		var node := Forms.mesh_node(
			Geometry.rounded_box(
				Vector3(float(entry[3]), float(entry[4]), 7.0),
				float(entry[4]) * 0.46, 3),
			palette.get_material(str(entry[5])), "Pocket%d" % index, false)
		node.position = _polar(float(entry[0]), float(entry[1]),
			float(entry[2]))
		node.rotation.y = -deg_to_rad(float(entry[0]) + BEARING_SHIFT)
		group.add_child(node)


static func _clouds(root: Node3D, palette) -> void:
	## Cloud banks at the horizon: wide, thin, and only ever silhouette.
	var group := Node3D.new()
	group.name = "Clouds"
	root.add_child(group)
	var material = palette.get_material("cloud_bank")
	var layout := [
		[212.0, 1020.0, -172.0, 700.0, 26.0],
		[176.0, 1120.0, -186.0, 660.0, 20.0],
		[248.0, 1090.0, -180.0, 680.0, 23.0],
		[206.0, 930.0, -158.0, 600.0, 16.0],
	]
	for index in layout.size():
		var entry: Array = layout[index]
		var node := Forms.mesh_node(
			Geometry.rounded_box(
				Vector3(float(entry[3]), float(entry[4]), 8.0),
				float(entry[4]) * 0.48, 3),
			material, "Cloud%d" % index, false)
		node.position = _polar(float(entry[0]), float(entry[1]),
			float(entry[2]))
		node.rotation.y = -deg_to_rad(float(entry[0]) + BEARING_SHIFT)
		group.add_child(node)


static func _ledge(root: Node3D, palette) -> void:
	## The rock shelf the machine is bolted to, and the drop beyond it.
	##
	## A tower needs something under it that is not tower, and the drop is
	## what gives the frame its bottom. Cut short so the void stays visible:
	## depth *below* the machine is as much of the scale read as height above
	## the valley.
	var group := Node3D.new()
	group.name = "Ledge"
	root.add_child(group)

	var shelf := Forms.mesh_node(
		smooth_mass(11.0, 9.2, 61, 24, 11, 0.30),
		palette.get_material("rock_ledge_hero"), "Shelf", false)
	shelf.position = Vector3(-0.8, -11.4, -1.8)
	shelf.scale = Vector3(1.05, 0.62, 1.0)
	group.add_child(shelf)

	var buttress := Forms.mesh_node(
		smooth_mass(46.0, 7.6, 83, 20, 13, 0.24),
		palette.get_material("rock_ledge_hero"), "Buttress", false)
	buttress.position = Vector3(-1.8, -56.0, -5.0)
	group.add_child(buttress)

	# Foreground framing: a spur at the bottom of the frame, below every
	# running surface, so it adds depth without occluding anything.
	var spur := Forms.mesh_node(
		smooth_mass(13.0, 8.4, 97, 22, 10, 0.34),
		palette.get_material("rock_ledge_hero"), "Spur", false)
	spur.position = Vector3(11.5, -24.0, 15.5)
	spur.scale = Vector3(1.3, 0.55, 1.0)
	group.add_child(spur)


static func _valley_lights(root: Node3D, palette) -> void:
	## Warm points down in the haze: the read that there is a world below.
	var group := Node3D.new()
	group.name = "ValleyLights"
	root.add_child(group)
	var material = palette.get_material("lit_valley_hero")
	var layout := [
		[205.0, 202.0, -18.0, 0.50],
		[206.5, 224.0, -22.0, 0.55],
		[203.5, 240.0, -26.0, 0.55],
		[205.5, 268.0, -30.0, 0.65],
		[204.5, 300.0, -36.0, 0.75],
		[219.5, 206.0, -19.0, 0.50],
		[218.0, 228.0, -23.0, 0.55],
		[221.0, 244.0, -27.0, 0.55],
		[219.0, 272.0, -31.0, 0.65],
		[220.5, 304.0, -37.0, 0.75],
	]
	for index in layout.size():
		var entry: Array = layout[index]
		var node := Forms.mesh_node(
			Geometry.rounded_disc(float(entry[3]), float(entry[3]) * 0.5,
				float(entry[3]) * 0.24, 10, 2),
			material, "Glow%d" % index, false)
		node.position = _polar(float(entry[0]), float(entry[1]),
			float(entry[2]))
		group.add_child(node)


static func build_lights(parent: Node3D) -> void:
	## Four directionals: two keys, a rim and a bounce.
	##
	## `Key` lights the machine only (cull mask 1). It is a three-quarter
	## front key at 46 degrees of elevation, which is what makes a moulded
	## pearl shell show its curvature and a clearcoat lobe fire.
	##
	## `WorldKey` lights the gorge only (cull mask 2, matching `WORLD_LAYER`).
	## It rakes in from the machine's left at a low 34 degrees, so the cliffs'
	## windward faces take the light, their leeward faces fall away, and the
	## modelled gullies cast into each other. Aiming one sun to do both jobs
	## was the whole reason the environment kept reading as flat card: the
	## bearing that flatters a shell is the bearing that flattens a wall.
	##
	## The rim and the bounce are shared. The bounce is aimed *upward*: in a
	## gorge at dusk the ground below the subject is the warmest thing in the
	## scene, and lighting the machine's undersides from below is what stops
	## its graphite going to black.
	var key := DirectionalLight3D.new()
	key.name = "Key"
	key.light_cull_mask = 1
	key.light_color = Color("#FFF2E2")
	key.light_energy = 3.3
	key.light_specular = 1.0
	key.shadow_enabled = true
	key.directional_shadow_mode = DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS
	key.directional_shadow_max_distance = 80.0
	key.directional_shadow_blend_splits = true
	key.shadow_bias = 0.03
	key.shadow_normal_bias = 1.1
	key.rotation_degrees = Vector3(-46.0, -30.0, 0.0)
	parent.add_child(key)

	var world_key := DirectionalLight3D.new()
	world_key.name = "WorldKey"
	world_key.light_cull_mask = WORLD_LAYER
	world_key.light_color = Color("#E4EEFF")
	world_key.light_energy = 2.0
	world_key.light_specular = 0.2
	world_key.shadow_enabled = true
	world_key.directional_shadow_mode = \
		DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS
	world_key.directional_shadow_max_distance = 460.0
	world_key.directional_shadow_split_1 = 0.06
	world_key.directional_shadow_split_2 = 0.18
	world_key.directional_shadow_split_3 = 0.48
	world_key.directional_shadow_blend_splits = true
	world_key.shadow_bias = 0.06
	world_key.shadow_normal_bias = 1.6
	world_key.rotation_degrees = Vector3(-30.0, -74.0, 0.0)
	parent.add_child(world_key)

	var rim := DirectionalLight3D.new()
	rim.name = "Rim"
	rim.light_color = Color("#8ED6FF")
	rim.light_energy = 2.4
	rim.light_specular = 1.5
	rim.shadow_enabled = false
	rim.rotation_degrees = Vector3(-8.0, 158.0, 0.0)
	parent.add_child(rim)

	var bounce := DirectionalLight3D.new()
	bounce.name = "ValleyBounce"
	bounce.light_color = Color("#FFB06A")
	bounce.light_energy = 1.2
	bounce.light_specular = 0.25
	bounce.rotation_degrees = Vector3(38.0, 52.0, 0.0)
	bounce.shadow_enabled = false
	parent.add_child(bounce)
