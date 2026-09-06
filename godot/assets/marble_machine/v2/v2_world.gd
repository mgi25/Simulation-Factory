extends RefCounted

## ENVIRONMENT V2 - the cliff-gorge arena the machine stands in.
##
## The prior lab put a beautiful machine in a black room, and a black room is
## why it read as a render rather than as a place. The reference's background is
## only about three stops under its subject and still resolves as rock, towers
## and haze; it is separated from the machine by *atmosphere*, not by darkness.
## Reproducing that is the single largest available gain in this branch, and it
## costs almost nothing in geometry.
##
## ## The layout is a ring, not a backdrop
##
## Masses are placed on bearings around the machine rather than as a flat wall
## behind it, because the hero camera's azimuth is still being chosen and a
## painted backdrop only works from the angle it was painted for. A ring also
## means the key and rim lights have something to graze at every bearing, so
## the machine is never silhouetted against empty sky on one side.
##
## Three depth layers, separated by value as well as by fog:
##
##     ~90u    gorge walls, the frame's dark shoulders
##     ~210u   the far range, lighter and bluer
##     ~440u   ridge lines, nearly sky value
##
## ## Why the frame is narrower than it looks
##
## The output is 1080x1920 with a vertical field of view around 34 degrees,
## which is a *nineteen degree* horizontal field. Anything meant to be seen
## beside the machine has to be far away or it falls outside the frame
## entirely. That is why the gorge walls sit at ninety units and not at fifteen,
## and why the only near geometry is the ledge under the plinth - which is
## foreground framing that cannot occlude anything, because it is below the
## whole machine.
##
## ## Budget
##
## Large silhouettes, simple meshes, fog and light. No terrain system, no
## scattered props, no city. Every mass is one faceted prism; the far ranges
## are flat-shaded and eleven-sided. The whole world is a small fraction of the
## machine's triangle count and it is meant to stay that way.

const Geometry := preload("res://scripts/toy_geometry.gd")
const Forms := preload("res://assets/marble_machine/lab_forms.gd")
const V2Forms := preload("res://assets/marble_machine/v2/v2_forms.gd")

# --- the layout, and the arithmetic behind it ----------------------------
#
# The hero camera sits about 37 units out at 20 degrees of elevation, which
# puts it near y = 22 looking *down*. Two consequences drive every number
# below.
#
# The frame is a narrow wedge. A 34-degree vertical field on a 9:16 frame is
# only about 20 degrees wide, so at distance almost nothing outside a
# ten-degree cone either side of the view bearing is in shot. Scenery meant to
# be seen has to sit near that bearing, not merely "behind".
#
# And the top of the frame is not sky. Looking down, the frame's upper edge is
# three degrees below the camera's own horizon, which at 110 units is y = 16.
# A wall whose crest clears that fills the frame to the top; one that stops
# just under it leaves the sliver of lit haze the reference concept has, and
# nothing else does that job.
#
# So the gorge is built as three crests at rising distance, each a little
# taller and a lot hazier than the one in front:
#
#     ~90u   near crests, tops near y=+9    the frame's dark shoulders
#     ~210u  the far range, tops near y=+13  seen through the gap between them
#     ~450u  ridge lines                     almost fog value, the last step
#
# The near crests are deliberately spaced so that a gap of about fifteen
# degrees falls on the view bearing. Packed shoulder to shoulder they made one
# continuous wall, and a continuous wall at ninety units occludes every other
# layer in the scene - which is exactly how a gorge turns into a cave. The gap
# is what lets the far range, the haze and the warm horizon band behind them
# appear directly behind the machine, and it is what the reference concept
# does too: its tower is read against light, not against rock.
#
# bearing (deg), radius, height, base radius, seed
const GORGE_WALLS := [
	[190.0, 84.0, 30.0, 24.0, 3],
	[242.0, 90.0, 32.0, 26.0, 11],
	[150.0, 102.0, 28.0, 26.0, 19],
	[284.0, 98.0, 26.0, 24.0, 27],
	[108.0, 120.0, 24.0, 26.0, 35],
	[318.0, 112.0, 25.0, 24.0, 43],
	[ 40.0, 128.0, 22.0, 28.0, 51],
]

const FAR_RANGE := [
	[214.0, 196.0, 24.0, 44.0, 5],
	[202.0, 232.0, 54.0, 50.0, 13],
	[228.0, 224.0, 52.0, 48.0, 21],
	[178.0, 180.0, 46.0, 44.0, 29],
	[252.0, 190.0, 48.0, 44.0, 37],
	[140.0, 226.0, 44.0, 46.0, 45],
	[292.0, 236.0, 46.0, 48.0, 53],
	[ 20.0, 264.0, 42.0, 50.0, 61],
]

# bearing, radius, length, height
const RIDGES := [
	[214.0, 430.0, 560.0, 40.0],
	[168.0, 470.0, 560.0, 32.0],
	[256.0, 458.0, 560.0, 36.0],
	[ 96.0, 500.0, 560.0, 26.0],
	[326.0, 486.0, 560.0, 30.0],
]

# Tall lit structures embedded in the gorge walls: bearing, radius, base y,
# height, width, seed. They are what says "inhabited" rather than "canyon",
# and they are placed on the near crests where the haze has not yet eaten
# their windows.
const STRUCTURES := [
	[210.0, 76.0, 4.0, 13.0, 2.2, 2],
	[218.0, 84.0, 3.0, 16.0, 2.6, 6],
	[188.0, 66.0, 2.0, 11.0, 1.9, 10],
	[238.0, 72.0, 5.0, 14.0, 2.3, 14],
	[204.0, 100.0, 1.0, 15.0, 2.6, 18],
	[228.0, 116.0, 0.0, 18.0, 3.0, 22],
	[196.0, 132.0, -2.0, 20.0, 3.4, 26],
]

# Spires per crest. They are generated from each wall's own entry rather than
# listed, because what matters is that every crest gets a broken edge, and
# hand-placing forty of them would be forty numbers that say nothing.
const SPIRES_PER_CREST := 6

static func _polar(bearing_degrees: float, radius: float, y: float) -> Vector3:
	var angle := deg_to_rad(bearing_degrees)
	return Vector3(sin(angle) * radius, y, cos(angle) * radius)


static func build_environment(no_glow: bool) -> Environment:
	## Deep blue dusk, warm at the horizon, tone-mapped like a product shot.
	##
	## The sky does two jobs. It is the picture behind the machine, and it is
	## the only thing a clearcoat lobe has to reflect - the prior lab's
	## graded sky was what gave its rounded edges their sheen, and this one is
	## brighter and warmer at the horizon so the sheen has a colour gradient
	## in it instead of one flat blue.
	var sky_material := ProceduralSkyMaterial.new()
	sky_material.sky_top_color = Color("#081226")
	sky_material.sky_horizon_color = Color("#3E657C")
	sky_material.sky_curve = 0.09
	sky_material.sky_energy_multiplier = 1.0
	sky_material.ground_bottom_color = Color("#152534")
	sky_material.ground_horizon_color = Color("#345168")
	sky_material.ground_curve = 0.40
	sky_material.sun_angle_max = 42.0
	sky_material.energy_multiplier = 1.0

	var sky := Sky.new()
	sky.sky_material = sky_material

	var env := Environment.new()
	env.background_mode = Environment.BG_SKY
	env.sky = sky
	env.background_energy_multiplier = 0.72
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.ambient_light_sky_contribution = 1.0
	env.ambient_light_energy = 0.30
	env.reflected_light_source = Environment.REFLECTION_SOURCE_SKY

	env.tonemap_mode = Environment.TONE_MAPPER_ACES
	env.tonemap_exposure = 0.77
	env.tonemap_white = 9.5

	# Atmosphere. The density is set so the gorge walls lose about a third of
	# their contrast and the far range most of it; `aerial_perspective` is
	# what makes that a *colour* shift toward the sky rather than a grey wash,
	# which is the difference between haze and dirty glass.
	env.fog_enabled = true
	env.fog_mode = Environment.FOG_MODE_DEPTH
	env.fog_light_color = Color("#25455C")
	env.fog_light_energy = 1.20
	env.fog_sun_scatter = 0.28
	env.fog_density = 0.0078
	env.fog_sky_affect = 0.18
	env.fog_aerial_perspective = 0.50
	env.fog_height = 2.0
	env.fog_height_density = 0.045

	env.ssao_enabled = true
	env.ssao_radius = 0.85
	env.ssao_intensity = 2.4
	env.ssao_power = 1.5
	env.ssao_light_affect = 0.12

	env.ssr_enabled = true
	env.ssr_max_steps = 48
	env.ssr_fade_in = 0.2
	env.ssr_fade_out = 2.0

	if not no_glow:
		env.glow_enabled = true
		env.glow_intensity = 1.05
		env.glow_bloom = 0.16
		# Threshold above one so a lit *surface* blooms and a white shell
		# never does. The marble-v1 curve clipped because its bloom started
		# below the pearl's own value and ate the shell's curvature with it.
		env.glow_hdr_threshold = 1.08
		env.glow_hdr_scale = 2.2
		env.glow_blend_mode = Environment.GLOW_BLEND_MODE_SOFTLIGHT
		for level in 7:
			env.set_glow_level(level, 0.0)
		env.set_glow_level(1, 0.3)
		env.set_glow_level(2, 0.65)
		env.set_glow_level(3, 0.85)
		env.set_glow_level(4, 0.45)

	env.adjustment_enabled = true
	env.adjustment_contrast = 1.14
	env.adjustment_saturation = 1.16
	env.adjustment_brightness = 1.0
	return env


static func build(palette) -> Node3D:
	## Every piece of the world that is not the machine.
	var root := Node3D.new()
	root.name = "World"

	_gorge(root, palette)
	_spires(root, palette)
	_far_range(root, palette)
	_ridges(root, palette)
	_structures(root, palette)
	_clouds(root, palette)
	_ledge(root, palette)
	_valley_lights(root, palette)
	_sun_pocket(root, palette)
	return root


static func _sun_pocket(root: Node3D, palette) -> void:
	## The warm band low in the haze, behind the crests.
	##
	## Fog only subtracts contrast; something has to put light back into the
	## background or the gorge reads as a cave. Two large soft masses in a
	## warm tone, partly occluded by the near crest, give the frame a
	## direction to be lit from and the machine a warm edge to sit against.
	var group := Node3D.new()
	group.name = "SunPocket"
	root.add_child(group)
	# Sited above the far range's crest line rather than behind it. Placed
	# low they were simply occluded, which is the whole reason the background
	# was reading as a cave: there was a sun in the scene and nothing that
	# could see it.
	var layout := [
		[214.0, 262.0, -8.0, 240.0, 26.0, "lit_horizon"],
		[194.0, 292.0, -10.0, 200.0, 20.0, "lit_horizon"],
		[236.0, 280.0, -9.0, 210.0, 22.0, "lit_horizon_cool"],
		[214.0, 232.0, -24.0, 180.0, 12.0, "lit_horizon"],
	]
	for index in layout.size():
		var entry: Array = layout[index]
		var node := Forms.mesh_node(
			Geometry.rounded_box(
				Vector3(float(entry[3]), float(entry[4]), 6.0),
				float(entry[4]) * 0.46, 3),
			palette.get_material(str(entry[5])), "Pocket%d" % index, false)
		node.position = _polar(float(entry[0]), float(entry[1]), float(entry[2]))
		node.rotation.y = -deg_to_rad(float(entry[0]))
		group.add_child(node)
	return


static func _gorge(root: Node3D, palette) -> void:
	## The dark shoulders of the frame: the gorge the machine is built into.
	var group := Node3D.new()
	group.name = "Gorge"
	root.add_child(group)
	var material = palette.get_material("rock_near")
	for index in GORGE_WALLS.size():
		var entry: Array = GORGE_WALLS[index]
		var node := Forms.mesh_node(
			V2Forms.rock_mass(float(entry[2]), float(entry[3]), int(entry[4]),
				15, 8),
			material, "Wall%d" % index, false)
		node.position = _polar(float(entry[0]), float(entry[1]), -22.0)
		node.rotation.y = float(entry[4]) * 0.37
		group.add_child(node)


static func _spires(root: Node3D, palette) -> void:
	## Rock teeth along every crest line.
	##
	## A faceted prism at eighty units still reads as a smooth hill, because
	## its facets are broader than the haze's own gradient across it. What
	## makes a crest read as rock is a *broken silhouette*, and the cheapest
	## honest way to break one is to stand a scatter of tall thin masses on
	## it. Six per crest, placed by arithmetic on the crest's own seed, so the
	## result is dense, varied and byte-identical between renders.
	var group := Node3D.new()
	group.name = "Spires"
	root.add_child(group)

	for which in [[GORGE_WALLS, -22.0, "rock_near"], [FAR_RANGE, -37.0, "rock_mid"]]:
		var walls: Array = which[0]
		var base_y: float = which[1]
		var material = palette.get_material(str(which[2]))
		for index in walls.size():
			var entry: Array = walls[index]
			var bearing := float(entry[0])
			var radius := float(entry[1])
			var height := float(entry[2])
			var spread := float(entry[3])
			var seed_value := int(entry[4])
			for step in SPIRES_PER_CREST:
				var jitter := float((seed_value * 13 + step * 29) % 17) / 17.0
				var swing := float((seed_value * 7 + step * 11) % 13) / 13.0 - 0.5
				var offset := (float(step) / float(SPIRES_PER_CREST) - 0.45)
				var spire_height: float = height * (0.16 + 0.30 * jitter)
				var node := Forms.mesh_node(
					V2Forms.rock_mass(spire_height, spread * (0.07 + 0.09 * jitter),
						seed_value * 31 + step, 7, 4),
					material, "Spire%d_%d_%d" % [seed_value, index, step], false)
				node.position = _polar(
					bearing + offset * spread * 44.0 / maxf(radius, 1.0),
					radius + swing * spread * 0.55,
					base_y + height * (0.72 + 0.20 * swing))
				node.rotation.y = float(seed_value + step) * 0.53
				group.add_child(node)


static func _far_range(root: Node3D, palette) -> void:
	## The second layer. Lighter and bluer, so depth is carried by value and
	## not by fog alone - fog can only take contrast away, and a range that is
	## merely faded reads as the same rock behind glass.
	var group := Node3D.new()
	group.name = "FarRange"
	root.add_child(group)
	var material = palette.get_material("rock_mid")
	for index in FAR_RANGE.size():
		var entry: Array = FAR_RANGE[index]
		var node := Forms.mesh_node(
			V2Forms.rock_mass(float(entry[2]), float(entry[3]), int(entry[4]),
				13, 6),
			material, "Range%d" % index, false)
		node.position = _polar(float(entry[0]), float(entry[1]), -37.0)
		node.rotation.y = float(entry[4]) * 0.53
		group.add_child(node)


static func _ridges(root: Node3D, palette) -> void:
	var group := Node3D.new()
	group.name = "Ridges"
	root.add_child(group)
	var material = palette.get_material("rock_far")
	for index in RIDGES.size():
		var entry: Array = RIDGES[index]
		var node := Forms.mesh_node(
			V2Forms.ridge_wall(float(entry[2]), float(entry[3]), 26.0,
				index * 9 + 3, 13),
			material, "Ridge%d" % index, false)
		node.position = _polar(float(entry[0]), float(entry[1]), -66.0)
		node.rotation.y = -deg_to_rad(float(entry[0]))
		group.add_child(node)


static func _structures(root: Node3D, palette) -> void:
	## Futuristic silhouettes embedded in the walls, with lit windows.
	##
	## Deliberately abstract: a tapered slab, a cap, a mast and a band of
	## small warm faces. At this distance a detailed building and a slab with
	## the right proportion are the same pixels, and the slab does not tempt
	## anyone into modelling a city.
	var group := Node3D.new()
	group.name = "Structures"
	root.add_child(group)
	var shell = palette.get_material("rock_ledge")
	var window = palette.get_material("lit_far_window")
	var warm = palette.get_material("lit_valley")

	for index in STRUCTURES.size():
		var entry: Array = STRUCTURES[index]
		var bearing := float(entry[0])
		var height := float(entry[3])
		var width := float(entry[4])
		var seed_value := int(entry[5])
		var pivot := Node3D.new()
		pivot.name = "Structure%d" % index
		pivot.position = _polar(bearing, float(entry[1]), float(entry[2]))
		pivot.rotation.y = -deg_to_rad(bearing)
		group.add_child(pivot)

		var body := Forms.mesh_node(
			Geometry.rounded_box(Vector3(width, height, width * 0.8),
				width * 0.14, 2),
			shell, "Body", false)
		body.position = Vector3(0.0, height * 0.5, 0.0)
		pivot.add_child(body)

		var cap := Forms.mesh_node(
			Geometry.rounded_box(Vector3(width * 1.5, height * 0.09,
				width * 1.2), width * 0.12, 2), shell, "Cap", false)
		cap.position = Vector3(0.0, height * 0.94, 0.0)
		pivot.add_child(cap)

		var mast := Forms.mesh_node(
			Geometry.tube([Vector3.ZERO, Vector3(0.0, height * 0.3, 0.0)],
				width * 0.05, 6), shell, "Mast", false)
		mast.position = Vector3(0.0, height, 0.0)
		pivot.add_child(mast)

		var beacon := Forms.mesh_node(
			Geometry.rounded_disc(width * 0.07, width * 0.07, width * 0.03, 8, 2),
			warm, "Beacon", false)
		beacon.position = Vector3(0.0, height * 1.30, 0.0)
		pivot.add_child(beacon)

		# Window bands: regular, so they read as one lit texture rather than
		# as a scattering of dots. They sit slightly proud of the body so the
		# haze between here and the camera does not simply erase them.
		for row in 6:
			var y: float = height * (0.16 + 0.135 * float(row))
			var band := Forms.mesh_node(
				Geometry.rounded_box(
					Vector3(width * 0.92, height * 0.026, width * 0.76),
					width * 0.012, 1),
				window, "Band%d_%d" % [seed_value, row], false)
			band.position = Vector3(0.0, y, 0.0)
			pivot.add_child(band)

		# A lit sill along the foot: the warm line that says the structure
		# stands on something and is in use. A disc was tried here and read
		# as a lamp lying on the cliff - at this distance a horizontal
		# emissive plane has no context to be a floor.
		var sill := Forms.mesh_node(
			Geometry.rounded_box(
				Vector3(width * 1.25, height * 0.012, width * 0.10),
				width * 0.006, 1),
			warm, "Sill", false)
		sill.position = Vector3(0.0, height * 0.045, width * 0.44)
		pivot.add_child(sill)


static func _clouds(root: Node3D, palette) -> void:
	## Three cloud banks at the horizon: wide, thin, and only ever silhouette.
	var group := Node3D.new()
	group.name = "Clouds"
	root.add_child(group)
	var material = palette.get_material("cloud_bank")
	var layout := [
		[212.0, 560.0, -34.0, 460.0, 20.0],
		[178.0, 610.0, -30.0, 420.0, 15.0],
		[248.0, 590.0, -40.0, 440.0, 17.0],
	]
	for index in layout.size():
		var entry: Array = layout[index]
		var node := Forms.mesh_node(
			Geometry.rounded_box(
				Vector3(float(entry[3]), float(entry[4]), 8.0),
				float(entry[4]) * 0.48, 3),
			material, "Cloud%d" % index, false)
		node.position = _polar(float(entry[0]), float(entry[1]), float(entry[2]))
		node.rotation.y = -deg_to_rad(float(entry[0]))
		group.add_child(node)


static func _ledge(root: Node3D, palette) -> void:
	## The rock shelf the machine is bolted to, and the drop beyond it.
	##
	## This answers the marble-v1 complaint that the machine floats. A tower
	## needs something under it that is *not* tower, and the cheapest honest
	## answer is a piece of the cliff it was built on, cut off short so the
	## void below stays visible.
	var group := Node3D.new()
	group.name = "Ledge"
	root.add_child(group)

	var shelf := Forms.mesh_node(
		V2Forms.rock_mass(7.0, 11.5, 61, 13, 4),
		palette.get_material("rock_ledge"), "Shelf", false)
	shelf.position = Vector3(-1.2, -7.2, -2.2)
	shelf.scale = Vector3(1.0, 0.62, 1.0)
	group.add_child(shelf)

	var buttress := Forms.mesh_node(
		V2Forms.rock_mass(22.0, 9.0, 83, 11, 5),
		palette.get_material("rock_ledge"), "Buttress", false)
	buttress.position = Vector3(-2.6, -28.0, -6.0)
	group.add_child(buttress)

	# Foreground framing: a spur of rock at the bottom of the frame, below
	# every running surface, so it can add depth without occluding anything.
	var spur := Forms.mesh_node(
		V2Forms.rock_mass(9.0, 8.0, 97, 11, 4),
		palette.get_material("rock_near"), "Spur", false)
	spur.position = Vector3(9.5, -15.0, 13.5)
	spur.scale = Vector3(1.3, 0.55, 1.0)
	group.add_child(spur)


static func _valley_lights(root: Node3D, palette) -> void:
	## Warm points down in the haze: the read that there is a world below.
	var group := Node3D.new()
	group.name = "ValleyLights"
	root.add_child(group)
	var material = palette.get_material("lit_valley")
	var layout := [
		[190.0, 92.0, -14.0, 1.6],
		[196.0, 104.0, -16.0, 1.8],
		[242.0, 96.0, -13.0, 1.5],
		[236.0, 110.0, -15.0, 1.7],
		[150.0, 112.0, -17.0, 2.0],
		[284.0, 106.0, -14.0, 1.8],
		[204.0, 168.0, -22.0, 2.8],
		[230.0, 182.0, -24.0, 3.0],
		[176.0, 156.0, -20.0, 2.4],
	]
	for index in layout.size():
		var entry: Array = layout[index]
		var node := Forms.mesh_node(
			Geometry.rounded_disc(float(entry[3]), float(entry[3]) * 0.5,
				float(entry[3]) * 0.24, 10, 2),
			material, "Glow%d" % index, false)
		node.position = _polar(float(entry[0]), float(entry[1]), float(entry[2]))
		group.add_child(node)


static func build_lights(parent: Node3D) -> void:
	## The rig: a cool key from over the gorge wall, a hard cool rim from
	## behind, and a warm bounce up out of the valley.
	##
	## Three directionals rather than a dome, because the brief asks for deep
	## readable shadows and an environment-only rig gives none. The warm
	## bounce is aimed *upward*: in a gorge at dusk the ground below the
	## subject is the warmest thing in the scene, and lighting the machine's
	## undersides from below is what stops its graphite going to black.
	var key := DirectionalLight3D.new()
	key.name = "Key"
	key.light_color = Color("#FFF0DC")
	key.light_energy = 3.2
	key.light_specular = 1.0
	key.shadow_enabled = true
	key.directional_shadow_mode = DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS
	key.directional_shadow_max_distance = 90.0
	key.directional_shadow_blend_splits = true
	key.shadow_bias = 0.03
	key.shadow_normal_bias = 1.1
	key.rotation_degrees = Vector3(-46.0, -30.0, 0.0)
	parent.add_child(key)

	var rim := DirectionalLight3D.new()
	rim.name = "Rim"
	rim.light_color = Color("#8ED6FF")
	rim.light_energy = 1.7
	rim.light_specular = 1.5
	rim.shadow_enabled = false
	rim.rotation_degrees = Vector3(-8.0, 162.0, 0.0)
	parent.add_child(rim)

	var bounce := DirectionalLight3D.new()
	bounce.name = "ValleyBounce"
	bounce.light_color = Color("#FFB06A")
	bounce.light_energy = 1.15
	bounce.light_specular = 0.25
	bounce.shadow_enabled = false
	bounce.rotation_degrees = Vector3(38.0, 58.0, 0.0)
	parent.add_child(bounce)
