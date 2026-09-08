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


static func build_environment(no_glow: bool) -> Environment:
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
	# A dusk band, not a mauve wash. At #6A5C63 over a curve of 0.16 the
	# warm term was spread over the whole lower sky, and since the sky is
	# also the only ambient source that put a desaturated pink on every
	# upward face of the mountain - which is most of what read as tan. The
	# same warmth over a curve of 0.11 is a band at the horizon: warmer
	# where it shows and gone by forty degrees up.
	# Thinner and more saturated still. A wide desaturated warm band is a
	# muddy brown wash across the top of any frame that looks even slightly
	# up, and it reads as haze rather than as dusk. Narrow it and the same
	# hue becomes a light source with a direction.
	sky_material.sky_horizon_color = Color("#85604D")
	sky_material.sky_curve = 0.08
	sky_material.sky_energy_multiplier = 1.0
	sky_material.ground_bottom_color = Color("#080F19")
	sky_material.ground_horizon_color = Color("#41393B")
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

	env.fog_enabled = true
	env.fog_mode = Environment.FOG_MODE_DEPTH
	# Half a step warm. The fog is the largest single area in the two frames
	# that look out over the valley - the finish and the environment plate -
	# and at #5E5A6E that area is a cool grey, which is the one thing the
	# warm end of the journey cannot afford behind it.
	env.fog_light_color = Color("#6B6070")
	env.fog_light_energy = 0.85
	env.fog_sun_scatter = 0.52
	# Down a fifth. With `fog_depth_begin` now holding the subject clear, the
	# density is free to be set for what it is actually doing - reading
	# distance across the valley - and 0.0016 was thick enough to erase the
	# valley platforms and the far crests behind the finish into one flat
	# sheet.
	env.fog_density = 0.0013
	env.fog_sky_affect = 0.30
	# Aerial perspective is what makes haze take the *sky's* colour rather
	# than one flat grey, and it is the difference between three ranges at
	# three distances and a wall behind the finish.
	env.fog_aerial_perspective = 0.88
	# Depth fog with a floor under it. The sloped-course pass noted the real
	# tension here and could only trade one side against the other: at a
	# density that hazed a cliff at two hundred units, a camera at the start
	# also hazed the finish a hundred and thirty units away. `fog_depth_begin`
	# resolves it rather than trading it - nothing inside fifty-two units is
	# fogged at all, so the whole subject stays crisp from any camera on it,
	# and everything past the massif's own shoulder still recedes.
	env.fog_depth_begin = 52.0
	env.fog_depth_end = 900.0
	env.fog_depth_curve = 0.72
	env.fog_height = -12.0
	# Thicker than the depth term, and low. Haze pools in a valley; it does
	# not fill a mountainside evenly - and a gorge whose bottom is lost in
	# haze has a depth, where a gorge whose bottom is merely dark has a floor.
	env.fog_height_density = 0.034

	env.ssao_enabled = true
	env.ssao_radius = 0.90
	env.ssao_intensity = 2.1
	env.ssao_power = 1.5
	env.ssao_light_affect = 0.12

	env.ssr_enabled = true
	env.ssr_max_steps = 44
	env.ssr_fade_in = 0.2
	env.ssr_fade_out = 2.0

	if not no_glow:
		env.glow_enabled = true
		env.glow_intensity = 0.92
		env.glow_bloom = 0.22
		# 1.16 is under the pearl. A moulded white shell lit by a 3.2-energy
		# key returns well over 1.16 across its whole shoulder, so the bloom
		# was not haloing the edge lights - it was washing the entire running
		# surface, which is the single largest cause of the blown-out white
		# road. At 1.48 only the emissive stock and the chrome bead clear the
		# knee, which is what a halo is supposed to be for.
		env.glow_hdr_threshold = 1.48
		env.glow_hdr_scale = 2.2
		env.glow_blend_mode = Environment.GLOW_BLEND_MODE_SOFTLIGHT
		for level in 7:
			env.set_glow_level(level, 0.0)
		env.set_glow_level(1, 0.3)
		env.set_glow_level(2, 0.65)
		env.set_glow_level(3, 0.85)
		env.set_glow_level(4, 0.45)

	env.adjustment_enabled = true
	env.adjustment_contrast = 1.10
	env.adjustment_saturation = 1.16
	env.adjustment_brightness = 1.0
	return env


static func build_lights(parent: Node3D) -> void:
	## Product key on the course, raking key on the world, rim, warm bounce.
	var key := DirectionalLight3D.new()
	key.name = "Key"
	key.light_cull_mask = 1
	key.light_color = Color("#FFF2E2")
	# 3.2 put the pearl shoulder over the tonemap knee on its own, before any
	# bloom: a hundred units of straight came back as one white stripe with
	# no curvature in it. The moulding needs the key to model it, not to
	# saturate it, and 2.65 is where the shoulder highlight still separates
	# from the lip highlight.
	key.light_energy = 2.65
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
	world_key.light_energy = 3.15
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
	# Four degrees flatter. The terrain carries its landform in lighting
	# rather than in material - that was the sloped-course pass's own
	# conclusion after the material bands failed - so the rake angle IS
	# the terrain shading, and at -22 a crag has a lit plane and a dark
	# one where at -26 it had a lit top and a grey side.
	world_key.rotation_degrees = Vector3(-22.0, -78.0, 0.0)
	parent.add_child(world_key)

	# A cool fill for the world only, from behind the camera and barely above
	# the horizontal. A mountainside lit by one raking key has a lit face and a
	# black one, and the black one is half the frame; this is what keeps the
	# shadowed flank readable without softening the relief the key is there to
	# create.
	var world_fill := DirectionalLight3D.new()
	world_fill.name = "WorldFill"
	world_fill.light_cull_mask = WORLD_LAYER
	world_fill.light_color = Color("#6892C4")
	# 0.95 was set against a warm key at 2.3. With that key down to a rim
	# the fill is most of what the shadowed half of the mountain gets, and
	# the shadowed half is well over a third of every section frame.
	world_fill.light_energy = 1.55
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
	# Halved, and raking. This light was right in principle and wrong in
	# strength: a 2.3-energy #FF9C46 aimed eight degrees below the horizontal
	# lands on the broad camera-facing planes of the flank, not just on its
	# edges, and a broad plane taking a saturated orange at that energy comes
	# back tan. The sloped-course pass diagnosed the same symptom as a
	# light-mask fault and fixed a real one; this is the second cause, and it
	# is an exposure fault.
	#
	# A warm light on an environment should be a rim, not a fill. At 1.3 from
	# five degrees below the horizontal it catches ridge lines, crag arrises
	# and the tops of the terrace lips and leaves the fields to the cool key -
	# which is what the concept's warmth actually is. The warmth the frame
	# loses here comes back as *local* accents in `course_dressing`, where it
	# is attached to something that could plausibly be emitting it.
	world_warm.light_color = Color("#FFB273")
	world_warm.light_energy = 1.50
	world_warm.light_specular = 0.1
	world_warm.shadow_enabled = false
	# From +X and +Z: the camera's own side of the hill, and the opposite side
	# from the cool key. Aimed the other way it lit only the uphill faces,
	# which this camera never sees, and the mountainside stayed uniformly blue.
	world_warm.rotation_degrees = Vector3(-5.0, 52.0, 0.0)
	parent.add_child(world_warm)

	var rim := DirectionalLight3D.new()
	rim.name = "Rim"
	rim.light_color = Color("#8ED6FF")
	rim.light_energy = 2.1
	rim.light_specular = 1.15
	rim.shadow_enabled = false
	rim.rotation_degrees = Vector3(-9.0, 162.0, 0.0)
	parent.add_child(rim)

	var bounce := DirectionalLight3D.new()
	bounce.name = "ValleyBounce"
	bounce.light_color = Color("#FFB06A")
	bounce.light_energy = 1.35
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
	_haze(root, palette)
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
	# Warm and cool alternating. Six cool slabs on a cool crest under a cool
	# key is one silhouette with lights on it; the same six with every other
	# one warm reads as a settlement, because a settlement is lit by more
	# than one thing.
	var cool_shell = palette.get_material("far_structure")
	var warm_shell = palette.get_material("warm_structure")
	var cool_lit = palette.get_material("lit_far_window_hero")
	var warm_lit = palette.get_material("lit_far_warm_polish")
	for index in STRUCTURES.size():
		var warm := index % 2 == 1
		var shell = warm_shell if warm else cool_shell
		var lit = warm_lit if warm else cool_lit
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
		var at := _polar(bearing, 880.0, -78.0)
		# `look_at` requires the node to be inside the tree and prints
		# "Node not inside tree" and does nothing when it is not - which is
		# what was happening here, silently, for the whole of the
		# sloped-course pass: `group` is not added to the scene until
		# `build` returns, so every one of these nine slabs kept its default
		# orientation and seven of the nine were edge-on to the camera.
		#
		# That is most of why the dusk was reading as a flat mauve wash
		# rather than as a lit horizon: the geometry that was supposed to
		# carry the warm band was almost entirely invisible. The positional
		# form of the same call works outside the tree.
		slab.look_at_from_position(at, Vector3(0.0, -78.0, 0.0), Vector3.UP)
		group.add_child(slab)


static func _haze(root: Node3D, palette) -> void:
	## Four layers of translucent air, at four distances.
	##
	## Replaces two banks of opaque slab. An opaque mass at four hundred units
	## is another range - it has an edge, it occludes, and the eye files it
	## with the mountains rather than with the sky - so the previous banks
	## added shapes where they were meant to add distance. These are veils:
	## alpha only, no depth write, and each one takes a value from the
	## `haze_*_polish` ramp so that a range seen through two of them is
	## measurably paler than the same range seen through one.
	##
	## The near layer at 190 is the one that was missing. The massif's own
	## shoulder fades out at about ninety units and the near range starts at
	## two hundred and six, and with nothing between them the two read as one
	## continuous ground - which is why the hero frame had a horizon and no
	## middle distance.
	var group := Node3D.new()
	group.name = "Haze"
	root.add_child(group)
	# radius, base y, count, span x, span y, material, y stagger
	var layers := [
		[190.0, -66.0, 11, 150.0, 22.0, "haze_near_polish", 9.0],
		[330.0, -88.0, 11, 210.0, 30.0, "haze_mid_polish", 13.0],
		[500.0, -104.0, 9, 280.0, 38.0, "haze_mid_polish", 16.0],
		[760.0, -116.0, 9, 380.0, 46.0, "haze_far_polish", 19.0],
	]
	for tier in layers.size():
		var layer: Array = layers[tier]
		var radius: float = float(layer[0])
		var count: int = int(layer[2])
		var veil = palette.get_material(str(layer[5]))
		for index in count:
			# Spread over the camera's own arc rather than the full circle:
			# every camera on this course looks along roughly 200 degrees, and
			# a veil behind the camera costs the same to draw as one in front.
			var bearing: float = 96.0 + 208.0 * float(index) / float(count - 1)
			var slab := Forms.mesh_node(
				Geometry.rounded_box(Vector3(float(layer[3]),
					float(layer[4]), 6.0), float(layer[4]) * 0.45, 2),
				veil, "Veil%d_%d" % [tier, index], false)
			var at := _polar(bearing,
				radius + 26.0 * float((index + tier) % 3),
				float(layer[1]) + float(layer[6])
					* float((index * 2 + tier) % 3))
			# Positional, for the reason spelled out in `_dusk_band`: these
			# are oriented before they join the tree, and the plain
			# `look_at` would have left every veil axis-aligned.
			slab.look_at_from_position(at, Vector3(0.0, float(layer[1]), 0.0),
				Vector3.UP)
			group.add_child(slab)
