extends RefCounted

## The world the course is installed in: sky, atmosphere, distant ranges, keys.
##
## A sibling of `hero/hero_world.gd`, not an edit to it - that file's gorge is
## authored as a ring of masses around a single vertical subject, and a course
## that travels sixty units laterally and eighty in depth cannot be surrounded
## by anything. Here the near ground is a heightfield (`course_terrain.gd`) and
## this file supplies only what is beyond it: three ranges at 210, 380 and 600
## units, a warm dusk band behind them, and the light rig.
##
## ## Two keys, again
##
## The one finding from the tower build that transfers unchanged: a
## three-quarter front key makes moulded pearl read and flattens rock into
## paper, so the course gets its own key on cull mask 1 and the world gets a
## raking key on mask 2. `course_terrain` and everything in this file are put
## on layer 2; the track, the modules and the racers stay on layer 1.

const Geometry := preload("res://scripts/toy_geometry.gd")
const Forms := preload("res://assets/marble_machine/lab_forms.gd")
const HeroWorld := preload("res://assets/marble_machine/hero/hero_world.gd")

const WORLD_LAYER := 2

# bearing, radius, height, base radius, seed. Bearings are world bearings, and
# the camera looks along roughly 200, so the tall entries cluster there and the
# ring thins out toward the flanks where only a wide shot ever sees it.
const NEAR_RANGE := [
	[168.0, 214.0, 118.0, 46.0, 3], [188.0, 206.0, 126.0, 48.0, 11],
	[208.0, 210.0, 124.0, 48.0, 19], [228.0, 218.0, 120.0, 46.0, 27],
	[248.0, 232.0, 112.0, 44.0, 35], [140.0, 246.0, 110.0, 46.0, 43],
	[272.0, 250.0, 108.0, 44.0, 51], [112.0, 272.0, 104.0, 44.0, 59],
	[300.0, 276.0, 106.0, 44.0, 67], [ 84.0, 300.0, 100.0, 42.0, 75],
	[330.0, 304.0, 100.0, 42.0, 83], [ 20.0, 330.0,  96.0, 42.0, 91],
]

const MID_RANGE := [
	[160.0, 372.0, 144.0, 74.0, 5], [182.0, 358.0, 154.0, 78.0, 13],
	[202.0, 350.0, 158.0, 80.0, 21], [222.0, 362.0, 152.0, 78.0, 29],
	[242.0, 380.0, 142.0, 74.0, 37], [130.0, 404.0, 136.0, 72.0, 45],
	[268.0, 408.0, 134.0, 72.0, 53], [100.0, 436.0, 130.0, 70.0, 61],
	[298.0, 440.0, 130.0, 70.0, 69], [ 40.0, 470.0, 124.0, 68.0, 77],
	[336.0, 474.0, 124.0, 68.0, 85],
]

const FAR_RANGE := [
	[176.0, 596.0, 188.0, 116.0, 7], [200.0, 580.0, 198.0, 120.0, 15],
	[224.0, 600.0, 186.0, 116.0, 23], [150.0, 634.0, 174.0, 112.0, 31],
	[252.0, 640.0, 174.0, 112.0, 39], [120.0, 686.0, 166.0, 108.0, 47],
	[282.0, 690.0, 166.0, 108.0, 55], [ 60.0, 740.0, 158.0, 104.0, 63],
	[320.0, 744.0, 158.0, 104.0, 71],
]

# Distant lit architecture on the mid crests: what says inhabited rather than
# geological. Bearing, radius, base y, height, width, seed.
const STRUCTURES := [
	[196.0, 316.0, -46.0, 40.0, 5.0, 2], [204.0, 336.0, -50.0, 44.0, 5.4, 6],
	[212.0, 322.0, -47.0, 38.0, 4.8, 14], [190.0, 348.0, -52.0, 42.0, 5.2, 22],
	[219.0, 352.0, -53.0, 41.0, 5.0, 26], [178.0, 330.0, -48.0, 36.0, 4.6, 34],
]


static func _polar(bearing: float, radius: float, y: float) -> Vector3:
	var angle := deg_to_rad(bearing)
	return Vector3(sin(angle) * radius, y, cos(angle) * radius)


const CONTRAST_V21 := "v21"


static func build_environment(no_glow: bool, contrast := "") -> Environment:
	## Dusk, tuned for a scene four times the tower's depth.
	##
	## The tower's fog density was set so a cliff at two hundred units lost half
	## its contrast. Here the *subject itself* is a hundred and thirty units
	## long, and at that density the finish would have been hazed away from a
	## camera looking at the start. Density is halved and the height term
	## carries the difference, which is also more honest: haze pools in a
	## valley, it does not fill a mountainside evenly.
	var sky_material := ProceduralSkyMaterial.new()
	sky_material.sky_top_color = Color("#040A16")
	# The horizon carries the warmth. A dusk whose only warm pixels are the
	# lamps on the subject reads as night, and the concept's frame is warm
	# behind its machine as well as on it.
	sky_material.sky_horizon_color = Color("#6A5C63")
	sky_material.sky_curve = 0.16
	sky_material.sky_energy_multiplier = 1.0
	sky_material.ground_bottom_color = Color("#080F19")
	sky_material.ground_horizon_color = Color("#4A4048")
	sky_material.ground_curve = 0.28
	sky_material.sun_angle_max = 46.0
	sky_material.energy_multiplier = 1.0

	var sky := Sky.new()
	sky.sky_material = sky_material

	var env := Environment.new()
	env.background_mode = Environment.BG_SKY
	env.sky = sky
	env.background_energy_multiplier = 0.78
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.ambient_light_sky_contribution = 1.0
	env.ambient_light_energy = 0.42
	env.reflected_light_source = Environment.REFLECTION_SOURCE_SKY

	env.tonemap_mode = Environment.TONE_MAPPER_ACES
	env.tonemap_exposure = 0.82
	env.tonemap_white = 14.0

	# V21. Sky ambient reaches every upward-facing plane in the picture, and
	# the widest upward-facing planes here are the track floor and the terrain
	# - so it is the term that was adding the last of the pearl's clip and
	# most of the mountainside's wash. Down a sixth, with the sky's own
	# contribution to the background left alone so the dusk does not change.
	if contrast == CONTRAST_V21:
		env.ambient_light_energy = 0.35

	env.fog_enabled = true
	env.fog_mode = Environment.FOG_MODE_DEPTH
	env.fog_light_color = Color("#5E5A6E")
	env.fog_light_energy = 0.85
	env.fog_sun_scatter = 0.52
	env.fog_density = 0.0016
	env.fog_sky_affect = 0.30
	env.fog_aerial_perspective = 0.72
	env.fog_height = -14.0
	env.fog_height_density = 0.022

	env.ssao_enabled = true
	env.ssao_radius = 0.90
	env.ssao_intensity = 2.1
	env.ssao_power = 1.5
	env.ssao_light_affect = 0.12
	if contrast == CONTRAST_V21:
		# Local form, which is the half of "the track is flat" that lowering
		# its value does not fix. A tighter radius reads the rib spacing, the
		# guard root and the gap under a marble rather than the whole channel
		# as one cavity, and `light_affect` is what lets the occlusion survive
		# on a surface the key is pointed straight at - at 0.12 the lit face
		# of the track, which is most of it, had no occlusion at all.
		env.ssao_radius = 0.70
		env.ssao_intensity = 2.7
		env.ssao_light_affect = 0.22

	env.ssr_enabled = true
	env.ssr_max_steps = 44
	env.ssr_fade_in = 0.2
	env.ssr_fade_out = 2.0

	if not no_glow:
		env.glow_enabled = true
		env.glow_intensity = 1.10
		env.glow_bloom = 0.26
		env.glow_hdr_threshold = 1.16
		env.glow_hdr_scale = 2.2
		# V21. At 1.16 the threshold sits *below* what a lit pearl surface
		# renders at, so the track itself was being bloomed - which is what
		# turned the running channel into a light source with a course
		# somewhere inside it, and it is why the white ribbon has no edge. The
		# practicals and the edge lights are all well above 1.34 and keep
		# their halo; the moulding stops having one.
		if contrast == CONTRAST_V21:
			env.glow_intensity = 0.95
			env.glow_bloom = 0.19
			env.glow_hdr_threshold = 1.34
		env.glow_blend_mode = Environment.GLOW_BLEND_MODE_SOFTLIGHT
		for level in 7:
			env.set_glow_level(level, 0.0)
		env.set_glow_level(1, 0.3)
		env.set_glow_level(2, 0.65)
		env.set_glow_level(3, 0.85)
		env.set_glow_level(4, 0.45)

	env.adjustment_enabled = true
	env.adjustment_contrast = 1.06
	env.adjustment_saturation = 1.20
	env.adjustment_brightness = 1.0
	if contrast == CONTRAST_V21:
		# A grade contrast above 1 is a gain around mid grey, so it pushes the
		# top of the range further into the clip it is supposed to be shaping.
		# Flat, with the separation bought back as saturation - which costs
		# the pearl nothing, because pearl has almost no chroma to amplify,
		# and pays the racers directly.
		env.adjustment_contrast = 1.0
		env.adjustment_saturation = 1.26
		# Depth. Half the work the mountainside was doing to read as distance
		# was being done by value alone, and the value range just came down;
		# a little more aerial perspective puts it back where a lens would.
		env.fog_density = 0.0019
		env.fog_aerial_perspective = 0.80
	return env


static func build_lights(parent: Node3D, contrast := "") -> void:
	## Product key on the course, raking key on the world, rim, warm bounce.
	##
	## V21 moves four energies and nothing else: no light is added, removed,
	## recoloured or re-aimed, so every shadow in the picture falls exactly
	## where it fell in V20. What changes is the ratio between the subject key
	## and the two lights that were washing the hill out from under it.
	var v21 := contrast == CONTRAST_V21
	var key := DirectionalLight3D.new()
	key.name = "Key"
	key.light_cull_mask = 1
	key.light_color = Color("#FFF2E2")
	# The course key at 3.2 over a 0.89-linear pearl is three and a half times
	# what the curve can hold. Down to 2.7, which is where the moulding's own
	# form comes back; the racers lose the same fraction and were never near
	# the clip, so the gap between a marble and the track it sits on widens.
	key.light_energy = 2.7 if v21 else 3.2
	key.light_specular = 1.0
	key.shadow_enabled = true
	key.directional_shadow_mode = DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS
	key.directional_shadow_max_distance = 110.0
	key.directional_shadow_split_1 = 0.05
	key.directional_shadow_split_2 = 0.16
	key.directional_shadow_split_3 = 0.44
	key.directional_shadow_blend_splits = true
	key.shadow_bias = 0.035
	key.shadow_normal_bias = 1.2
	key.rotation_degrees = Vector3(-44.0, -34.0, 0.0)
	parent.add_child(key)

	var world_key := DirectionalLight3D.new()
	world_key.name = "WorldKey"
	world_key.light_cull_mask = WORLD_LAYER
	world_key.light_color = Color("#DFEBFF")
	# The terrain fills a third of a section frame. Its key comes down by the
	# same fraction as the course's, so the two keep their V20 relationship
	# and the hill does not brighten relative to the track it carries.
	world_key.light_energy = 2.45 if v21 else 2.9
	world_key.light_specular = 0.2
	world_key.shadow_enabled = true
	world_key.directional_shadow_mode = \
		DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS
	world_key.directional_shadow_max_distance = 300.0
	world_key.directional_shadow_split_1 = 0.07
	world_key.directional_shadow_split_2 = 0.22
	world_key.directional_shadow_split_3 = 0.52
	world_key.directional_shadow_blend_splits = true
	world_key.shadow_bias = 0.045
	world_key.shadow_normal_bias = 1.1
	world_key.rotation_degrees = Vector3(-26.0, -78.0, 0.0)
	parent.add_child(world_key)

	# A cool fill for the world only, from behind the camera and barely above
	# the horizontal. A mountainside lit by one raking key has a lit face and a
	# black one, and the black one is half the frame; this is what keeps the
	# shadowed flank readable without softening the relief the key is there to
	# create.
	var world_fill := DirectionalLight3D.new()
	world_fill.name = "WorldFill"
	world_fill.light_cull_mask = WORLD_LAYER
	world_fill.light_color = Color("#6E9AC4")
	# The one light that only ever *reduces* contrast. Two thirds of it is
	# enough to keep the shadowed flank readable, and the third that goes is
	# most of what made the near ground read as a pale lavender wash under a
	# white track.
	world_fill.light_energy = 0.68 if v21 else 0.95
	world_fill.light_specular = 0.0
	world_fill.shadow_enabled = false
	world_fill.rotation_degrees = Vector3(-14.0, 26.0, 0.0)
	parent.add_child(world_fill)

	# The warm half of the dusk, on the world only and raking in from the same
	# bearing as the sky's warm horizon. One light, and it is what turns a
	# uniformly blue mountainside into a lit one - the concept's environment is
	# warm behind its machine as well as in front of it, and no amount of warm
	# paint on the subject substitutes for that.
	var world_warm := DirectionalLight3D.new()
	world_warm.name = "WorldWarm"
	world_warm.light_cull_mask = WORLD_LAYER
	world_warm.light_color = Color("#FF9C46")
	world_warm.light_energy = 2.3
	world_warm.light_specular = 0.1
	world_warm.shadow_enabled = false
	# From +X and +Z: the camera's own side of the hill, and the opposite side
	# from the cool key. Aimed the other way it lit only the uphill faces,
	# which this camera never sees, and the mountainside stayed uniformly blue.
	world_warm.rotation_degrees = Vector3(-8.0, 52.0, 0.0)
	parent.add_child(world_warm)

	var rim := DirectionalLight3D.new()
	rim.name = "Rim"
	rim.light_color = Color("#8ED6FF")
	# The rim is on no cull mask, so it reaches the racers and the course
	# alike - and it was reaching them in the wrong proportion. On a pearl
	# drum at roughness 0.34 almost all of it arrives as diffuse, which is a
	# second key on the frame's largest pale surfaces; on a marble at
	# roughness 0.08 under a full clearcoat almost all of it arrives as
	# specular, which is the cool edge that lifts a candy sphere off whatever
	# is behind it. So V21 trades the one for the other: less light, more of
	# it specular. The marbles keep their backlight and the shells stop being
	# lit twice.
	rim.light_energy = 1.75 if v21 else 2.3
	rim.light_specular = 2.1 if v21 else 1.5
	rim.shadow_enabled = false
	rim.rotation_degrees = Vector3(-9.0, 162.0, 0.0)
	parent.add_child(rim)

	var bounce := DirectionalLight3D.new()
	bounce.name = "ValleyBounce"
	bounce.light_color = Color("#FFB06A")
	# The warm bounce off the valley, which is almost pure diffuse fill on the
	# course and so lands hardest on exactly the wide pale surfaces this pass
	# is trying to get back under the clip.
	bounce.light_energy = 0.85 if v21 else 1.15
	bounce.light_specular = 0.25
	bounce.rotation_degrees = Vector3(36.0, 54.0, 0.0)
	bounce.shadow_enabled = false
	parent.add_child(bounce)


static func build(palette) -> Node3D:
	var root := Node3D.new()
	root.name = "World"
	_range(root, palette, NEAR_RANGE, -78.0, "NearRange", 30, 15, 0.34,
		"rock_soft_near", "rock_soft_mid")
	_range(root, palette, MID_RANGE, -132.0, "MidRange", 26, 13, 0.38,
		"rock_soft_mid", "rock_soft_far")
	_range(root, palette, FAR_RANGE, -186.0, "FarRange", 22, 11, 0.42,
		"rock_soft_far", "rock_soft_haze")
	_structures(root, palette)
	_dusk_band(root, palette)
	_clouds(root, palette)
	assign_layer(root)
	return root


static func assign_layer(node: Node) -> void:
	if node is VisualInstance3D:
		(node as VisualInstance3D).layers = WORLD_LAYER
	for child in node.get_children():
		assign_layer(child)


static func _range(root: Node3D, palette, entries: Array, base_y: float,
		group_name: String, facets: int, tiers: int, taper: float,
		material_key: String, alternate_key: String) -> void:
	var group := Node3D.new()
	group.name = group_name
	root.add_child(group)
	for index in entries.size():
		var entry: Array = entries[index]
		var shade = palette.get_material(
			material_key if index % 2 == 0 else alternate_key)
		var node := Forms.mesh_node(
			HeroWorld.smooth_mass(float(entry[2]), float(entry[3]),
				int(entry[4]), facets, tiers, taper),
			shade, "Mass%d" % index, false)
		node.position = _polar(float(entry[0]), float(entry[1]), base_y)
		node.rotation.y = float(entry[4]) * 0.41
		group.add_child(node)


static func _structures(root: Node3D, palette) -> void:
	## Slab towers with lit window bands, standing on the mid crests.
	var group := Node3D.new()
	group.name = "Structures"
	root.add_child(group)
	var shell = palette.get_material("far_structure")
	var lit = palette.get_material("lit_far_window_hero")
	for index in STRUCTURES.size():
		var entry: Array = STRUCTURES[index]
		var height: float = float(entry[3])
		var width: float = float(entry[4])
		var tower := Node3D.new()
		tower.name = "Tower%d" % index
		tower.position = _polar(float(entry[0]), float(entry[1]),
			float(entry[2]))
		group.add_child(tower)
		var body := Forms.mesh_node(
			Geometry.rounded_box(Vector3(width, height, width * 0.8),
				width * 0.16, 2), shell, "Body", false)
		body.position.y = height * 0.5
		tower.add_child(body)
		for band in 4:
			var strip := Forms.mesh_node(
				Geometry.rounded_box(Vector3(width * 1.03, 0.9,
					width * 0.83), 0.3, 2), lit, "Band%d" % band, false)
			strip.position.y = height * (0.28 + 0.17 * float(band))
			tower.add_child(strip)


static func _dusk_band(root: Node3D, palette) -> void:
	## The warm horizon behind the far range: where the light comes from.
	var group := Node3D.new()
	group.name = "DuskBand"
	root.add_child(group)
	for index in 9:
		var bearing: float = 160.0 + float(index) * 10.0
		var slab := Forms.mesh_node(
			Geometry.rounded_box(Vector3(150.0, 30.0, 8.0), 8.0, 2),
			palette.get_material("lit_dusk_band"), "Band%d" % index, false)
		slab.position = _polar(bearing, 880.0, -78.0)
		# **Turned to face the origin by a yaw, not by `look_at`.**
		#
		# `look_at` reads the node's *global* transform, and every node here is
		# still detached: `build` makes `root` with `Node3D.new()` and returns
		# it, so nothing in this file is in the tree when it is posed. Godot
		# printed an error for each of these nine slabs and left them all at
		# the identity - facing bearing 0 - which is why the warm horizon band
		# has been edge-on over most of its arc since before V21.
		#
		# The yaw is exact rather than an approximation of what `look_at` meant.
		# `_polar(b, r, y)` puts the slab at `(sin b * r, y, cos b * r)` and the
		# target is `(0, y, 0)`, so the aim is horizontal and `look_at` would
		# have pointed -Z at `(-sin b, 0, -cos b)`. A yaw of `b` about Y sends
		# +Z to `(sin b, 0, cos b)`, which is the same orientation, and it needs
		# no tree. `_clouds` below has posed its slabs this way all along.
		slab.rotation.y = deg_to_rad(bearing)
		group.add_child(slab)


static func _clouds(root: Node3D, palette) -> void:
	## Two banks of haze between the ranges, so distance has layers in it.
	var group := Node3D.new()
	group.name = "Clouds"
	root.add_child(group)
	var bank = palette.get_material("cloud_bank")
	for index in 14:
		var bearing: float = 96.0 + float(index) * 17.0
		var radius: float = 430.0 + 120.0 * float(index % 3)
		var slab := Forms.mesh_node(
			Geometry.rounded_box(Vector3(190.0, 13.0, 26.0), 12.0, 2),
			bank, "Bank%d" % index, false)
		slab.position = _polar(bearing, radius,
			-96.0 - 14.0 * float(index % 4))
		slab.rotation.y = deg_to_rad(-bearing)
		group.add_child(slab)
