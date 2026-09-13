extends RefCounted

## A resolved `EnvironmentProfile`, turned into scene.
##
## Every number in here arrives as an argument. There is no default look in
## this file and no `if theme == ...` anywhere in it: the profile decides, and
## a profile that decides nothing is a bug in the profile rather than a shrug
## here. That is the property that makes a future theme a JSON file.
##
## The six builders map one to one onto what the old constants controlled:
##
##     environment()   sky, haze, grade, glow, screen-space passes
##     lights()        the six-light rig, by name
##     backdrop()      three mountain ranges, landmarks, dusk band, cloud banks
##     apply_palette() every environment surface override, in one call
##     terrain()       ground material keys and scatter passes, as cfg fields
##     zone_lamps()    the practical at each race moment
##
## `course_world.gd`, `course_terrain.gd`, `course_dressing.gd` and
## `course_scene.gd` call these and hold no environment values of their own.

const Geometry := preload("res://scripts/toy_geometry.gd")
const Forms := preload("res://assets/marble_machine/lab_forms.gd")
const HeroWorld := preload("res://assets/marble_machine/hero/hero_world.gd")
const Profile := preload(
	"res://assets/marble_machine/environment/environment_profile.gd")

const WORLD_LAYER := 2

## Fixed build order, so a profile that adds a light cannot reorder the rig.
const LIGHT_ORDER := ["Key", "WorldKey", "WorldFill", "WorldWarm", "Rim",
	"ValleyBounce"]

const TONEMAP := {
	"linear": Environment.TONE_MAPPER_LINEAR,
	"reinhard": Environment.TONE_MAPPER_REINHARDT,
	"filmic": Environment.TONE_MAPPER_FILMIC,
	"aces": Environment.TONE_MAPPER_ACES,
}

const GLOW_BLEND := {
	"additive": Environment.GLOW_BLEND_MODE_ADDITIVE,
	"screen": Environment.GLOW_BLEND_MODE_SCREEN,
	"softlight": Environment.GLOW_BLEND_MODE_SOFTLIGHT,
	"replace": Environment.GLOW_BLEND_MODE_REPLACE,
	"mix": Environment.GLOW_BLEND_MODE_MIX,
}


static func _polar(bearing: float, radius: float, y: float) -> Vector3:
	var angle := deg_to_rad(bearing)
	return Vector3(sin(angle) * radius, y, cos(angle) * radius)


# --- sky, haze and grade --------------------------------------------------


static func environment(profile: Dictionary, no_glow := false) -> Environment:
	var sky_cfg: Dictionary = profile.get("sky", {})
	var sky_material := ProceduralSkyMaterial.new()
	sky_material.sky_top_color = Color(str(sky_cfg.get("top", "#000000")))
	sky_material.sky_horizon_color = Color(str(sky_cfg.get("horizon", "#888888")))
	sky_material.sky_curve = float(sky_cfg.get("curve", 0.15))
	sky_material.sky_energy_multiplier = float(sky_cfg.get("sky_energy", 1.0))
	sky_material.ground_bottom_color = Color(
		str(sky_cfg.get("ground_bottom", "#000000")))
	sky_material.ground_horizon_color = Color(
		str(sky_cfg.get("ground_horizon", "#444444")))
	sky_material.ground_curve = float(sky_cfg.get("ground_curve", 0.28))
	sky_material.sun_angle_max = float(sky_cfg.get("sun_angle_max", 46.0))
	sky_material.energy_multiplier = float(sky_cfg.get("energy", 1.0))

	var sky := Sky.new()
	sky.sky_material = sky_material

	var env := Environment.new()
	env.background_mode = Environment.BG_SKY
	env.sky = sky

	var grade: Dictionary = profile.get("grade", {})
	env.background_energy_multiplier = float(grade.get("background_energy", 1.0))
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.ambient_light_sky_contribution = float(
		grade.get("ambient_sky_contribution", 1.0))
	env.ambient_light_energy = float(grade.get("ambient_energy", 0.4))
	env.reflected_light_source = Environment.REFLECTION_SOURCE_SKY
	env.tonemap_mode = TONEMAP.get(str(grade.get("tonemap", "aces")),
		Environment.TONE_MAPPER_ACES)
	env.tonemap_exposure = float(grade.get("exposure", 1.0))
	env.tonemap_white = float(grade.get("white", 6.0))

	var fog: Dictionary = profile.get("fog", {})
	env.fog_enabled = bool(fog.get("enabled", false))
	if env.fog_enabled:
		env.fog_mode = Environment.FOG_MODE_DEPTH
		env.fog_light_color = Color(str(fog.get("colour", "#888888")))
		env.fog_light_energy = float(fog.get("energy", 1.0))
		env.fog_sun_scatter = float(fog.get("sun_scatter", 0.0))
		env.fog_density = float(fog.get("density", 0.001))
		env.fog_sky_affect = float(fog.get("sky_affect", 0.0))
		env.fog_aerial_perspective = float(fog.get("aerial_perspective", 0.0))
		env.fog_height = float(fog.get("height", 0.0))
		env.fog_height_density = float(fog.get("height_density", 0.0))

	var ssao: Dictionary = profile.get("ssao", {})
	env.ssao_enabled = bool(ssao.get("enabled", false))
	if env.ssao_enabled:
		env.ssao_radius = float(ssao.get("radius", 1.0))
		env.ssao_intensity = float(ssao.get("intensity", 2.0))
		env.ssao_power = float(ssao.get("power", 1.5))
		env.ssao_light_affect = float(ssao.get("light_affect", 0.0))

	var ssr: Dictionary = profile.get("ssr", {})
	env.ssr_enabled = bool(ssr.get("enabled", false))
	if env.ssr_enabled:
		env.ssr_max_steps = int(ssr.get("max_steps", 44))
		env.ssr_fade_in = float(ssr.get("fade_in", 0.2))
		env.ssr_fade_out = float(ssr.get("fade_out", 2.0))

	# `--no-glow` is the caller's, not the profile's: it is a render-cost
	# switch the proof tools use, and a theme has no business overruling it.
	var glow: Dictionary = profile.get("glow", {})
	env.glow_enabled = bool(glow.get("enabled", false)) and not no_glow
	if env.glow_enabled:
		env.glow_intensity = float(glow.get("intensity", 1.0))
		env.glow_bloom = float(glow.get("bloom", 0.0))
		env.glow_hdr_threshold = float(glow.get("hdr_threshold", 1.0))
		env.glow_hdr_scale = float(glow.get("hdr_scale", 2.0))
		env.glow_blend_mode = GLOW_BLEND.get(str(glow.get("blend", "softlight")),
			Environment.GLOW_BLEND_MODE_SOFTLIGHT)
		var levels: Array = glow.get("levels", [])
		for level in 7:
			env.set_glow_level(level,
				float(levels[level]) if level < levels.size() else 0.0)

	env.adjustment_enabled = true
	env.adjustment_contrast = float(grade.get("contrast", 1.0))
	env.adjustment_saturation = float(grade.get("saturation", 1.0))
	env.adjustment_brightness = float(grade.get("brightness", 1.0))
	return env


# --- the light rig --------------------------------------------------------


static func lights(parent: Node3D, profile: Dictionary) -> void:
	var table: Dictionary = profile.get("lights", {})
	var order: Array = LIGHT_ORDER.duplicate()
	for name in table:
		if not name in order:
			order.append(name)
	for name in order:
		if not table.has(name):
			continue
		var spec: Dictionary = table[name]
		# A light dialled to zero is removed rather than added dark, so a
		# profile can retire one without leaving a node for the next reader
		# to wonder about.
		if is_zero_approx(float(spec.get("energy", 0.0))):
			continue
		var light := DirectionalLight3D.new()
		light.name = str(name)
		light.light_cull_mask = int(spec.get("cull_mask", 0xFFFFFFFF))
		light.light_color = Color(str(spec.get("colour", "#FFFFFF")))
		light.light_energy = float(spec["energy"])
		light.light_specular = float(spec.get("specular", 1.0))
		var rotation: Array = spec.get("rotation", [0.0, 0.0, 0.0])
		light.rotation_degrees = Vector3(float(rotation[0]),
			float(rotation[1]), float(rotation[2]))
		var shadow: Dictionary = spec.get("shadow", {})
		light.shadow_enabled = bool(shadow.get("enabled", false))
		if light.shadow_enabled:
			light.directional_shadow_mode = \
				DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS
			light.directional_shadow_max_distance = float(
				shadow.get("max_distance", 100.0))
			var splits: Array = shadow.get("splits", [0.1, 0.2, 0.5])
			light.directional_shadow_split_1 = float(splits[0])
			light.directional_shadow_split_2 = float(splits[1])
			light.directional_shadow_split_3 = float(splits[2])
			light.directional_shadow_blend_splits = bool(
				shadow.get("blend_splits", true))
			light.shadow_bias = float(shadow.get("bias", 0.03))
			light.shadow_normal_bias = float(shadow.get("normal_bias", 1.0))
		parent.add_child(light)


# --- what is beyond the near ground ---------------------------------------


static func backdrop(palette, profile: Dictionary) -> Node3D:
	var root := Node3D.new()
	root.name = "World"
	var cfg: Dictionary = profile.get("backdrop", {})
	_range(root, palette, cfg.get("near_range", {}), "NearRange")
	_range(root, palette, cfg.get("mid_range", {}), "MidRange")
	_range(root, palette, cfg.get("far_range", {}), "FarRange")
	_landmarks(root, palette, cfg.get("structures", {}))
	_band(root, palette, cfg.get("dusk_band", {}))
	_clouds(root, palette, cfg.get("clouds", {}))
	assign_layer(root)
	return root


static func assign_layer(node: Node) -> void:
	if node is VisualInstance3D:
		(node as VisualInstance3D).layers = WORLD_LAYER
	for child in node.get_children():
		assign_layer(child)


static func _range(root: Node3D, palette, layer: Dictionary,
		group_name: String) -> void:
	var entries: Array = Profile.masses_of(layer)
	if entries.is_empty():
		return
	var group := Node3D.new()
	group.name = group_name
	root.add_child(group)
	var materials: Array = layer.get("materials", ["rock_soft_near"])
	var facets := int(layer.get("facets", 26))
	var tiers := int(layer.get("tiers", 13))
	var taper := float(layer.get("taper", 0.38))
	var base_y := float(layer.get("base_y", -100.0))
	for index in entries.size():
		var entry: Array = entries[index]
		var shade = palette.get_material(str(
			materials[index % materials.size()]))
		var node := Forms.mesh_node(
			HeroWorld.smooth_mass(float(entry[2]), float(entry[3]),
				int(entry[4]), facets, tiers, taper),
			shade, "Mass%d" % index, false)
		node.position = _polar(float(entry[0]), float(entry[1]), base_y)
		node.rotation.y = float(entry[4]) * 0.41
		group.add_child(node)


static func _landmarks(root: Node3D, palette, cfg: Dictionary) -> void:
	## Lit architecture on the crests: what says inhabited rather than
	## geological, and the profile's whole landmark set.
	var sites: Array = cfg.get("sites", [])
	if sites.is_empty():
		return
	var group := Node3D.new()
	group.name = "Structures"
	root.add_child(group)
	var shell = palette.get_material(str(cfg.get("shell", "far_structure")))
	var lit = palette.get_material(str(cfg.get("lit", "lit_far_window_hero")))
	var bands := int(cfg.get("bands", 4))
	var band_from := float(cfg.get("band_from", 0.28))
	var band_step := float(cfg.get("band_step", 0.17))
	for index in sites.size():
		var entry: Array = sites[index]
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
		for band in bands:
			var strip := Forms.mesh_node(
				Geometry.rounded_box(Vector3(width * 1.03, 0.9,
					width * 0.83), 0.3, 2), lit, "Band%d" % band, false)
			strip.position.y = height * (band_from + band_step * float(band))
			tower.add_child(strip)


static func _band(root: Node3D, palette, cfg: Dictionary) -> void:
	## The warm horizon behind the far range: where the light comes from.
	var count := int(cfg.get("count", 0))
	if count <= 0:
		return
	var group := Node3D.new()
	group.name = "DuskBand"
	root.add_child(group)
	var size: Array = cfg.get("size", [150.0, 30.0, 8.0])
	var shade = palette.get_material(str(cfg.get("material", "lit_dusk_band")))
	for index in count:
		var bearing: float = float(cfg.get("bearing_from", 160.0)) \
			+ float(cfg.get("bearing_step", 10.0)) * float(index)
		var slab := Forms.mesh_node(
			Geometry.rounded_box(Vector3(float(size[0]), float(size[1]),
				float(size[2])), float(cfg.get("round", 8.0)), 2),
			shade, "Band%d" % index, false)
		slab.position = _polar(bearing, float(cfg.get("radius", 880.0)),
			float(cfg.get("base_y", -78.0)))
		# Posed by yaw, not `look_at`: nothing here is in the tree yet, and
		# `look_at` reads a global transform. See the note this replaces in
		# `course_world.gd` - nine slabs sat at the identity for two versions.
		slab.rotation.y = deg_to_rad(bearing)
		group.add_child(slab)


static func _clouds(root: Node3D, palette, cfg: Dictionary) -> void:
	## Banks of haze between the ranges, so distance has layers in it.
	var count := int(cfg.get("count", 0))
	if count <= 0:
		return
	var group := Node3D.new()
	group.name = "Clouds"
	root.add_child(group)
	var size: Array = cfg.get("size", [190.0, 13.0, 26.0])
	var bank = palette.get_material(str(cfg.get("material", "cloud_bank")))
	var radius_cycle := maxi(int(cfg.get("radius_cycle", 3)), 1)
	var drop_cycle := maxi(int(cfg.get("drop_cycle", 4)), 1)
	for index in count:
		var bearing: float = float(cfg.get("bearing_from", 96.0)) \
			+ float(cfg.get("bearing_step", 17.0)) * float(index)
		var radius: float = float(cfg.get("radius", 430.0)) \
			+ float(cfg.get("radius_step", 120.0)) * float(index % radius_cycle)
		var slab := Forms.mesh_node(
			Geometry.rounded_box(Vector3(float(size[0]), float(size[1]),
				float(size[2])), float(cfg.get("round", 12.0)), 2),
			bank, "Bank%d" % index, false)
		slab.position = _polar(bearing, radius,
			float(cfg.get("base_y", -96.0))
				- float(cfg.get("drop_step", 14.0)) * float(index % drop_cycle))
		slab.rotation.y = deg_to_rad(-bearing)
		group.add_child(slab)


# --- what the rest of the course asks for ---------------------------------


static func apply_palette(surfaces, profile: Dictionary) -> void:
	## Install the profile's surface overrides on a built palette.
	##
	## Overrides rather than a second material table, because `lab_palette.gd`
	## holds decisions a theme has no opinion about - the acrylic backlight,
	## the running surfaces' metallic - and a theme that rebuilt those
	## materials would silently drop them.
	surfaces.apply_environment(profile.get("palette", {}))


static func terrain(profile: Dictionary) -> Dictionary:
	## The ground's theme fields, shaped for `course_layout`'s terrain table.
	##
	## Material keys and scatter passes only. The landform stays where the
	## camera port can see it - see GEOMETRY IS NOT THEME in
	## `environment_profile.gd`.
	var cfg: Dictionary = profile.get("terrain", {})
	var surfaces: Dictionary = cfg.get("surfaces", {})
	var out := {}
	if surfaces.has("shelf"):
		out["shelf_material"] = str(surfaces["shelf"])
	if surfaces.has("flank"):
		out["flank_material"] = str(surfaces["flank"])
	if surfaces.has("cliff"):
		out["cliff_material"] = str(surfaces["cliff"])
	if surfaces.has("high"):
		out["high_material"] = str(surfaces["high"])
	out["scatter"] = cfg.get("scatter", []).duplicate(true)
	return out


static func dressing(profile: Dictionary) -> Dictionary:
	return (profile.get("dressing", {}) as Dictionary).duplicate(true)


static func zone_lamps(profile: Dictionary) -> Array:
	## One omni at each race moment, as `[name, colour, energy, range, lift]`.
	##
	## Ordered by the zone table rather than by dictionary chance, so two
	## profiles with the same zones build the same rig in the same order.
	var zones: Dictionary = profile.get("zones", {})
	var out: Array = []
	for name in zones:
		var zone: Dictionary = zones[name]
		if is_zero_approx(float(zone.get("energy", 0.0))):
			continue
		out.append([str(name), str(zone.get("colour", "#FFFFFF")),
			float(zone.get("energy", 1.0)), float(zone.get("range", 9.0)),
			float(zone.get("lift", 2.0))])
	return out
