extends RefCounted

## V23: THE ENVIRONMENT AS A NAMED DIRECTION, applied over a finished scene.
##
## The sloped course's world is authored across three files - `course_world.gd`
## builds the sky, the atmosphere, the distant ranges and the light rig,
## `course_terrain.gd` builds the near ground, `course_dressing.gd` builds what
## stands on it - and every one of them is shared with the layout proof, the
## hero build, the track lab and the toy lab. A colour direction that edited
## any of them would change four films to photograph one.
##
## So nothing here edits them. `apply()` runs **after** the course scene has
## finished building and re-skins what it finds:
##
##     the Environment resource          replaced outright
##     the six named directional lights  recoloured and re-energised in place
##     the six zone practicals           recoloured in place
##     every world-layer material        retuned through the palette cache
##     the three distant ranges          lifted, scaled and thinned
##     the haze banks and the dusk band  lifted into frame and recoloured
##     new atmosphere and landmarks      added under `EnvExtras`
##
## The default is `""`, which applies nothing at all, so a render with no
## `--env=` flag is the V22.1 picture to the byte. That is the whole safety
## property of this file and `tests/test_sloped_v23_env.py` pins it.
##
## ## Why retuning the palette cache is safe, and where it is not
##
## `lab_palette.get_material` caches one `StandardMaterial3D` per key and
## `lab_forms.mesh_node` assigns it as a `material_override`. So mutating the
## cached instance for a key retints **every** mesh built from that key and
## nothing else - which is exactly the granularity a colour direction wants, as
## long as the key belongs to the world alone.
##
## `WORLD_KEYS` is that list, and it was checked rather than assumed. Three keys
## the dressing uses are *not* on it - `graphite`, `graphite_deep` and
## `lit_cyan_line_hero` - because the machine is built from them too, and
## retinting `lit_cyan_line_hero` to recolour six pylon beacons would recolour
## the start module's edge lighting with them. Those are done as node-level
## overrides on the dressing groups instead, which is more code and the only
## correct amount of it.
##
## ## What a direction may not touch
##
## No physics, no replay, no camera, no track geometry, no marble, no module, no
## support and no sign. A profile that wanted to move a pier would be describing
## a different course rather than a different evening. Everything this file adds
## goes under one node, `EnvExtras`, on the world's own light layer, and every
## added form is sited from the terrain config rather than from the racing line.

const Geometry := preload("res://scripts/toy_geometry.gd")
const Forms := preload("res://assets/marble_machine/lab_forms.gd")
const HeroWorld := preload("res://assets/marble_machine/hero/hero_world.gd")
const Terrain := preload("res://assets/marble_machine/course/course_terrain.gd")
const Profiles := preload("res://assets/marble_machine/course/course_env_profiles.gd")

const WORLD_LAYER := 2

## Every palette key that belongs to the world and to nothing else. A profile's
## `materials` block may name these and only these; `apply` pushes an error for
## anything else rather than silently recolouring a machine.
const WORLD_KEYS := [
	"slope_cliff", "slope_rock", "slope_earth", "slope_scree", "slope_moss",
	"slope_cap", "slope_boulder", "scrub_dark", "scrub_dry",
	"rock_soft_near", "rock_soft_mid", "rock_soft_far", "rock_soft_haze",
	"far_structure", "lit_far_window_hero", "lit_valley_hero",
	"cloud_bank", "lit_dusk_band",
]

## The six lights `course_world.build_lights` puts in the scene, by name.
const LIGHT_NAMES := ["Key", "WorldKey", "WorldFill", "WorldWarm", "Rim",
	"ValleyBounce"]

## The six zone practicals `course_scene._practicals` puts in the scene. The
## order is the order they are passed down the course, and it is the colour
## story the brief asks a direction to carry: cool at the top, orange where the
## choice is, gold at the end.
const PRACTICAL_ZONES := ["start", "mix", "obstacle", "split", "merge",
	"finish"]


static func names() -> PackedStringArray:
	var out := PackedStringArray()
	for key in Profiles.PROFILES:
		out.append(str(key))
	out.sort()
	return out


static func has_profile(name: String) -> bool:
	return Profiles.PROFILES.has(name)


static func profile(name: String) -> Dictionary:
	return Profiles.PROFILES.get(name, {})


static func title(name: String) -> String:
	return str(profile(name).get("title", name))


# --- the one entry point ----------------------------------------------------


static func apply(scene: Node3D, palette, name: String,
		terrain_cfg: Dictionary) -> Dictionary:
	## Re-skin a built course scene as one named direction.
	##
	## Returns a report of what it touched, which the render tool prints. A
	## profile that silently did nothing - a typo in a light name, a material
	## key that no longer exists - would be indistinguishable from a subtle one
	## in a still, so the counts are printed rather than trusted.
	if name.is_empty():
		return {"profile": "", "title": "V22.1 (unchanged)"}
	if not has_profile(name):
		push_error("course_env: unknown environment profile '%s'" % name)
		return {"profile": "", "title": "V22.1 (unchanged)"}

	var spec: Dictionary = profile(name)
	var report := {
		"profile": name,
		"title": str(spec.get("title", name)),
		"note": str(spec.get("note", "")),
	}
	report["environment"] = _apply_environment(scene, spec)
	report["lights"] = _apply_lights(scene, spec)
	report["practicals"] = _apply_practicals(scene, spec)
	report["materials"] = _apply_materials(palette, spec)
	report["ranges"] = _apply_ranges(scene, spec)
	report["haze"] = _apply_haze(scene, palette, spec)
	report["dressing"] = _apply_dressing(scene, palette, spec)
	report["features"] = _apply_features(scene, palette, spec, terrain_cfg)
	return report


# --- the environment resource -----------------------------------------------


static func _apply_environment(scene: Node3D, spec: Dictionary) -> int:
	## Rebuild the `Environment` in place, field by field.
	##
	## In place rather than replaced wholesale, because `course_world` sets
	## about forty properties and only a dozen of them are a colour direction's
	## business. SSAO, SSR, the glow level curve and the shadow settings carry
	## decisions from the V21 readability pass that no profile here has an
	## opinion about, and rebuilding the resource would silently drop them.
	var holder := scene.get_node_or_null("WorldEnvironment") as WorldEnvironment
	if holder == null or holder.environment == null:
		push_error("course_env: no WorldEnvironment to re-skin")
		return 0
	var env: Environment = holder.environment
	var touched := 0

	var sky_spec: Dictionary = spec.get("sky", {})
	var material := env.sky.sky_material if env.sky != null else null
	if material is ProceduralSkyMaterial and not sky_spec.is_empty():
		var sky: ProceduralSkyMaterial = material
		if sky_spec.has("top"):
			sky.sky_top_color = Color(str(sky_spec["top"]))
		if sky_spec.has("horizon"):
			sky.sky_horizon_color = Color(str(sky_spec["horizon"]))
		if sky_spec.has("curve"):
			sky.sky_curve = float(sky_spec["curve"])
		if sky_spec.has("ground_bottom"):
			sky.ground_bottom_color = Color(str(sky_spec["ground_bottom"]))
		if sky_spec.has("ground_horizon"):
			sky.ground_horizon_color = Color(str(sky_spec["ground_horizon"]))
		if sky_spec.has("ground_curve"):
			sky.ground_curve = float(sky_spec["ground_curve"])
		if sky_spec.has("sky_energy"):
			sky.sky_energy_multiplier = float(sky_spec["sky_energy"])
		# **The pale mass in the top of every preview frame, in all four
		# builds including the baseline.** `ProceduralSkyMaterial` draws a halo
		# for *every* `DirectionalLight3D` in the environment, and this scene
		# has six - a subject key, a world key, a world fill, a warm rake, a rim
		# and a valley bounce. `course_world` leaves `sun_angle_max` at 46
		# degrees, so each of the six paints a halo a quarter of the sky across,
		# and where several overlap the result is a soft blob with no edge that
		# reads as an enormous smeared sun.
		#
		# It cost two wrong diagnoses to find: the obvious suspects were the
		# haze banks, which had just been lifted into the sky, and then the
		# aurora curtains, which are cyan and in that part of the frame. Halving
		# the lift changed nothing and removing the curtains changed nothing,
		# and the giveaway was that the *baseline* has the same mass in the same
		# place in a different colour. It is not a V23 artefact at all; V23 only
		# made it visible by taking the tan wash off the sky that was hiding it.
		if sky_spec.has("sun_angle"):
			sky.sun_angle_max = float(sky_spec["sun_angle"])
		if sky_spec.has("sun_curve"):
			sky.sun_curve = float(sky_spec["sun_curve"])
		touched += sky_spec.size()

	var env_spec: Dictionary = spec.get("env", {})
	if env_spec.has("background_energy"):
		env.background_energy_multiplier = float(env_spec["background_energy"])
	if env_spec.has("ambient_energy"):
		env.ambient_light_energy = float(env_spec["ambient_energy"])
	if env_spec.has("exposure"):
		env.tonemap_exposure = float(env_spec["exposure"])
	if env_spec.has("white"):
		env.tonemap_white = float(env_spec["white"])
	if env_spec.has("contrast"):
		env.adjustment_contrast = float(env_spec["contrast"])
	if env_spec.has("saturation"):
		env.adjustment_saturation = float(env_spec["saturation"])
	if env_spec.has("brightness"):
		env.adjustment_brightness = float(env_spec["brightness"])
	touched += env_spec.size()

	var fog: Dictionary = spec.get("fog", {})
	if fog.has("colour"):
		env.fog_light_color = Color(str(fog["colour"]))
	if fog.has("energy"):
		env.fog_light_energy = float(fog["energy"])
	if fog.has("sun_scatter"):
		env.fog_sun_scatter = float(fog["sun_scatter"])
	if fog.has("density"):
		env.fog_density = float(fog["density"])
	if fog.has("sky_affect"):
		env.fog_sky_affect = float(fog["sky_affect"])
	if fog.has("aerial"):
		env.fog_aerial_perspective = float(fog["aerial"])
	if fog.has("height"):
		env.fog_height = float(fog["height"])
	if fog.has("height_density"):
		env.fog_height_density = float(fog["height_density"])
	touched += fog.size()

	var glow: Dictionary = spec.get("glow", {})
	if env.glow_enabled and not glow.is_empty():
		if glow.has("intensity"):
			env.glow_intensity = float(glow["intensity"])
		if glow.has("bloom"):
			env.glow_bloom = float(glow["bloom"])
		if glow.has("threshold"):
			env.glow_hdr_threshold = float(glow["threshold"])
		touched += glow.size()
	return touched


# --- the light rig ----------------------------------------------------------


static func _apply_lights(scene: Node3D, spec: Dictionary) -> int:
	## Recolour and re-energise the six named directionals, in place.
	##
	## `rotation` is accepted but rarely given. A profile that re-aimed the
	## subject key would move every shadow on the machine, which is a change to
	## the product photograph rather than to the evening it was taken in - so
	## only the two world lights ever carry one, and only in elevation.
	var lights: Dictionary = spec.get("lights", {})
	var touched := 0
	for light_name in LIGHT_NAMES:
		if not lights.has(light_name):
			continue
		var node := scene.get_node_or_null(light_name) as DirectionalLight3D
		if node == null:
			push_error("course_env: no light named '%s'" % light_name)
			continue
		var entry: Dictionary = lights[light_name]
		if entry.has("colour"):
			node.light_color = Color(str(entry["colour"]))
		if entry.has("energy"):
			node.light_energy = float(entry["energy"])
		if entry.has("specular"):
			node.light_specular = float(entry["specular"])
		if entry.has("rotation"):
			node.rotation_degrees = entry["rotation"]
		touched += 1
	return touched


static func _apply_practicals(scene: Node3D, spec: Dictionary) -> int:
	## The six zone omnis: cyan at the start, violet at the mixer, orange at the
	## obstacle, white at the choice, gold at the merge and the finish.
	##
	## This is the brief's colour story and it already existed - `course_scene.
	## _practicals` has carried it since the layout proof. What a direction does
	## with it is decide how much of the frame's total light it is allowed to
	## be, which is why every entry here is an energy and a range rather than a
	## new hue.
	var practicals: Dictionary = spec.get("practicals", {})
	var touched := 0
	for zone in PRACTICAL_ZONES:
		if not practicals.has(zone):
			continue
		# `course_scene` names them with GDScript's `capitalize()`, so the node
		# for "obstacle" is "LampObstacle".
		var node := scene.get_node_or_null("Lamp%s" % zone.capitalize()) \
			as OmniLight3D
		if node == null:
			continue
		var entry: Dictionary = practicals[zone]
		if entry.has("colour"):
			node.light_color = Color(str(entry["colour"]))
		if entry.has("energy"):
			node.light_energy = float(entry["energy"])
		if entry.has("range"):
			node.omni_range = float(entry["range"])
		touched += 1
	return touched


# --- the palette ------------------------------------------------------------


static func _apply_materials(palette, spec: Dictionary) -> int:
	## Retune the cached world materials. See the class docstring for why this
	## is a safe granularity and where it stops being one.
	var materials: Dictionary = spec.get("materials", {})
	var touched := 0
	for key in materials:
		var name := str(key)
		if not WORLD_KEYS.has(name):
			push_error("course_env: '%s' is not a world-only material key; a "
				% name + "profile may not retint it")
			continue
		var material: StandardMaterial3D = palette.get_material(name)
		var entry: Dictionary = materials[key]
		if entry.has("albedo"):
			var tinted := Color(str(entry["albedo"]))
			tinted.a = material.albedo_color.a
			material.albedo_color = tinted
		if entry.has("roughness"):
			material.roughness = float(entry["roughness"])
		if entry.has("emission"):
			# An emissive surface keeps its own albedo relationship: the
			# builders set albedo to a darkened copy of the emission so the
			# surface does not also fake a diffuse response, and a profile that
			# set only the emission would leave the old hue on the unlit face.
			var glow := Color(str(entry["emission"]))
			material.emission = glow
			material.albedo_color = glow.darkened(0.40)
		if entry.has("energy"):
			material.emission_energy_multiplier = float(entry["energy"])
		touched += 1
	return touched


# --- the distant world ------------------------------------------------------


static func _apply_ranges(scene: Node3D, spec: Dictionary) -> Dictionary:
	## Lift, scale and thin the three distant ranges.
	##
	## **Lift is the important one and it is a fix, not a taste.** `course_world`
	## puts the near range's base at y = -78 with masses 118 units tall, so its
	## crest sits at y = +40; the terrain above the start reaches +45 and the
	## camera stands near +30 looking down a few degrees. From most cameras on
	## this course the first of the three ranges was entirely behind the hill it
	## was built to stand behind, which is why the backdrop has always read as
	## one silhouette however carefully the three were valued.
	##
	## `thin` removes every nth mass. A ridge of twelve masses at 210 units
	## reads as a crowd; four large ones read as buttes, which is the silhouette
	## a display backdrop wants and the opposite of what an alpine valley does.
	##
	## ## `lift` and `stretch` are not the same lever, and only one of them works
	##
	## The two camera families on this course point opposite ways. The preview's
	## reverse dolly is tilted **up** at the crest above the start; every race
	## section shot is tilted **down** at the channel. So lifting a range far
	## enough to reach into the top of a merge frame stands it in the middle of
	## the preview's sky, and lowering it far enough to clear the preview's sky
	## takes it out of every race frame. There is no value of `lift` that serves
	## both, and the first three builds of this lab each found one end of that
	## and broke the other.
	##
	## `stretch` is the lever that does serve both, because a mountain that is
	## *taller* has its crest higher and its foot in the same place. It scales Y
	## alone, about the mass's own origin, which `course_world` has already put
	## on the range's ground line - so a stretched range appears over the
	## shoulder of the massif in a race frame without rising off the horizon in
	## a preview one.
	var ranges: Dictionary = spec.get("ranges", {})
	var world := scene.get_node_or_null("World")
	var report := {}
	if world == null:
		return report
	for group_name in ranges:
		var group := world.get_node_or_null(str(group_name)) as Node3D
		if group == null:
			push_error("course_env: no range group '%s'" % str(group_name))
			continue
		var entry: Dictionary = ranges[group_name]
		group.position.y += float(entry.get("lift", 0.0))
		var factor := float(entry.get("scale", 1.0))
		var stretch := float(entry.get("stretch", 1.0))
		var thin := int(entry.get("thin", 0))
		var kept := 0
		var dropped := 0
		var children := group.get_children()
		for index in children.size():
			var mass := children[index] as Node3D
			if mass == null:
				continue
			if thin > 1 and index % thin == 0:
				group.remove_child(mass)
				mass.queue_free()
				dropped += 1
				continue
			if not is_equal_approx(factor, 1.0) or not is_equal_approx(stretch, 1.0):
				# `hero_world.smooth_mass` builds a mass from y = 0 upward and
				# `course_world._range` sits its origin on the range's base
				# line, so scaling about the node's own origin keeps the foot
				# where it was and moves only the crest. That is the whole
				# reason `stretch` exists and is not the same lever as `lift`.
				mass.scale = Vector3(factor, factor * stretch, factor)
			kept += 1
		report[str(group_name)] = {"kept": kept, "dropped": dropped}
	return report


static func _apply_haze(scene: Node3D, palette, spec: Dictionary) -> int:
	## Lift the haze banks into frame, and add more of them.
	##
	## `course_world._clouds` builds fourteen slabs between y = -96 and -138 at
	## radius 430 to 670. A camera on this course sits near y = 30 and is aimed
	## a few degrees below horizontal, so the highest of them subtends about six
	## degrees *below* the frame's centre line and none of the fourteen has ever
	## appeared in a delivered frame. They are the layering the world file was
	## written to provide, and lifting them is the cheapest depth in the render.
	##
	## The extra banks are sited between the ranges rather than beyond them, on
	## the same polar convention, so a bank always has a mass behind it and a
	## mass in front of it. That is what a haze layer has to do to read as one.
	var haze: Dictionary = spec.get("haze", {})
	var world := scene.get_node_or_null("World")
	if world == null or haze.is_empty():
		return 0
	var group := world.get_node_or_null("Clouds") as Node3D
	if group == null:
		return 0
	var lift := float(haze.get("lift", 0.0))
	group.position.y += lift
	var scale_by: Vector3 = haze.get("scale", Vector3.ONE)

	# **A lifted bank has to stop being a lit solid or it is a cloud, not
	# haze.** `lab_palette`'s `cloud_bank` is `_matte`, which is the right
	# choice for a slab under the horizon that only ever contributes a dark
	# value - and the wrong one the moment the slab is raised into the sky,
	# where the raking world key and the warm alpenglow both reach it and turn
	# it into a bright painted blob with a hard rounded edge. That is exactly
	# what the first lift produced, in every direction, in the top left of the
	# start frame.
	#
	# So the banks get their own material here: unshaded, so no light reaches
	# them; alpha, so the range behind shows through; and depth-write off, so
	# two overlapping banks accumulate instead of clipping each other.
	var tint := Color(str(haze.get("colour", "#8FAEC8")))
	var vapour := StandardMaterial3D.new()
	vapour.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	vapour.albedo_color = Color(tint.r, tint.g, tint.b,
		float(haze.get("alpha", 0.30)))
	vapour.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	vapour.cull_mode = BaseMaterial3D.CULL_DISABLED
	vapour.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_DISABLED

	for child in group.get_children():
		var slab := child as MeshInstance3D
		if slab != null:
			slab.scale = scale_by
			slab.material_override = vapour

	var extra := int(haze.get("extra_banks", 0))
	for index in extra:
		# Radii chosen to interleave with the three ranges at 210-330, 350-470
		# and 580-740: a bank at 270 sits between the near masses, one at 500
		# between near and mid, one at 660 between mid and far.
		var radius: float = [390.0, 545.0, 700.0][index % 3]
		var bearing: float = 122.0 + float(index) * 23.0
		# Wide and thin. A haze layer is read by its horizontal extent and by
		# how little of it there is vertically; the world file's 190x13x26 slab
		# was authored to be seen edge-on from below and is a lozenge when it is
		# seen from the side.
		var slab := Forms.mesh_node(
			Geometry.rounded_box(Vector3(340.0, 9.0, 44.0), 4.2, 2),
			vapour, "ExtraBank%d" % index, false)
		slab.position = _polar(bearing, radius,
			-96.0 + lift - 9.0 * float(index % 4))
		slab.rotation.y = deg_to_rad(-bearing)
		slab.scale = scale_by
		group.add_child(slab)

	var band := world.get_node_or_null("DuskBand") as Node3D
	var band_spec: Dictionary = spec.get("dusk_band", {})
	if band != null and band_spec.has("lift"):
		# The same fault as the haze banks and it is worse: the warm horizon
		# slabs sit at y = -78 at radius 880, six degrees under the horizon from
		# every camera the film uses. The band that the V20 notes call "where
		# the light comes from" has never been in a frame.
		band.position.y += float(band_spec["lift"])
	_layer(world)
	return extra + 1


static func _apply_dressing(scene: Node3D, palette, spec: Dictionary) -> int:
	## The two dressing accents a direction owns, as node-level overrides.
	##
	## The pylon beacons are built from `lit_cyan_line_hero` and the valley
	## platform glows from `lit_valley_hero`. The second is a world-only key and
	## a profile retints it through the palette; the first is **not** - the same
	## material lights the start module's edge strips - so the beacons are
	## overridden one node at a time with a material this file owns.
	var beacon: Dictionary = spec.get("beacon", {})
	if beacon.is_empty():
		return 0
	var course := scene.get_node_or_null("Course")
	if course == null:
		# `course_scene` adds the machine without renaming it, so find it by
		# the group the dressing builds rather than by a guessed node name.
		course = scene
	var pylons := course.find_child("Pylons", true, false)
	if pylons == null:
		return 0
	var lit := StandardMaterial3D.new()
	lit.albedo_color = Color(str(beacon.get("colour", "#7FF0FF"))).darkened(0.40)
	lit.metallic = 0.0
	lit.roughness = 0.35
	lit.emission_enabled = true
	lit.emission = Color(str(beacon.get("colour", "#7FF0FF")))
	lit.emission_energy_multiplier = float(beacon.get("energy", 6.0))
	lit.shading_mode = BaseMaterial3D.SHADING_MODE_PER_PIXEL
	var touched := 0
	for mast in pylons.get_children():
		var head := mast.get_node_or_null("Beacon") as MeshInstance3D
		if head != null:
			head.material_override = lit
			touched += 1
	return touched


# --- what a direction adds --------------------------------------------------


static func _apply_features(scene: Node3D, palette, spec: Dictionary,
		cfg: Dictionary) -> PackedStringArray:
	## Everything a direction builds that V22.1 has no node for.
	##
	## All of it under one parent, all of it on the world's light layer, and all
	## of it sited from the terrain config. Nothing here is placed near the
	## racing line: the brief asks for landmarks and for controlled clutter, and
	## the way to have both is to put every added form beyond the gorge lip or
	## below the valley floor, where a section camera sees it as background and
	## never as an obstruction.
	var built := PackedStringArray()
	var features: Array = spec.get("features", [])
	if features.is_empty():
		return built
	var extras := Node3D.new()
	extras.name = "EnvExtras"
	scene.add_child(extras)
	var mist: Dictionary = spec.get("mist", {})
	for entry in features:
		var feature := str(entry)
		match feature:
			"gorge_mist":
				_gorge_mist(extras, cfg, mist, 1.0)
			"gorge_haze_soft":
				_gorge_mist(extras, cfg, mist, 0.45)
			"ridge_cards":
				_ridge_cards(extras, palette, cfg, false)
			"mesa_plinths":
				_ridge_cards(extras, palette, cfg, true)
			"aurora":
				_aurora(extras, palette)
			"crest_lines":
				_crest_lines(extras, palette)
			"valley_grid":
				_valley_grid(extras, palette, cfg)
			_:
				push_error("course_env: unknown feature '%s'" % feature)
				continue
		built.append(feature)
	_layer(extras)
	return built


static func _gorge_mist(root: Node3D, cfg: Dictionary, spec: Dictionary,
		weight: float) -> void:
	## Flat mist shelves stacked down the gorge, on the open side of the course.
	##
	## The reason is a fact about the layout rather than about taste:
	## `course_layout.B_TERRAIN` drops the ground by `gorge_depth` over
	## `gorge_span` starting at x = +15, and the racing line runs along the lip
	## of it for most of its length. Half of every section shot is therefore open
	## air, and open air with nothing in it is a hole rather than a drop - which
	## is what the V22.1 branch and merge frames show.
	##
	## Stacked shelves turn that hole into a measured distance. They are drawn
	## rather than fogged because depth fog is a function of distance from the
	## camera and cannot put a *near* edge on a drop that is thirty units below
	## the lens and eight units away from it.
	##
	## ## The one thing that has to be got right, and it is not the colour
	##
	## **A horizontal deck seen from above is not mist, it is a floor.** Every
	## camera on this course looks down between fifteen and forty degrees, so a
	## slab wide enough to span the gorge presents almost its whole area to the
	## lens - and the first build of this feature put six of them from y = -6
	## downward at up to 225 units across, which came out as a pale sheet lying
	## over the lower half of the frame with the course sitting on it.
	##
	## The three numbers that fix it are all in the profile, so a direction tunes
	## them rather than this file:
	##
	##     `top` and `step` keep the highest deck well below the racing line, so
	##         a section camera sees it past the guard rather than under the
	##         track;
	##     `offset` pushes every deck out past the gorge lip in +X, so the near
	##         edge of the stack is beyond the course rather than under it;
	##     `alpha` is per-deck and small - the stack is meant to accumulate, and
	##         any single deck that reads on its own is too strong.
	var group := Node3D.new()
	group.name = "GorgeMist"
	root.add_child(group)
	var tint: Color = Color(str(spec.get("colour", "#9EBCD6")))
	var mist := StandardMaterial3D.new()
	mist.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	mist.albedo_color = Color(tint.r, tint.g, tint.b,
		float(spec.get("alpha", 0.055)) * weight)
	mist.metallic = 0.0
	mist.roughness = 1.0
	mist.cull_mode = BaseMaterial3D.CULL_DISABLED
	mist.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	# A deck that wrote depth would clip the boulders and the supports behind it
	# into hard silhouettes; unsorted alpha over an unshaded plane is the trick.
	mist.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_DISABLED

	var gorge_at: float = float(cfg.get("gorge_at", 15.0))
	var centre_z: float = float(cfg.get("centre_z", 6.0))
	var decks := int(spec.get("decks", 5))
	var top: float = float(spec.get("top", -26.0))
	var step: float = float(spec.get("step", 11.0))
	var offset: float = float(spec.get("offset", 40.0))
	var reach: float = float(spec.get("reach", 30.0))
	for index in decks:
		var y: float = top - step * float(index)
		var span: float = reach + 9.0 * float(index)
		var slab := Forms.mesh_node(
			Geometry.rounded_box(Vector3(span * 1.7, 0.5, span * 2.1),
				span * 0.38, 2),
			mist, "Shelf%d" % index, false)
		slab.position = Vector3(gorge_at + offset + 7.0 * float(index), y,
			centre_z + 6.0 * float(index % 3))
		group.add_child(slab)


static func _ridge_cards(root: Node3D, palette, cfg: Dictionary,
		rounded: bool) -> void:
	## A fourth range, in the gap the world file leaves empty.
	##
	## The near terrain fades to the valley floor by a radius of 94 units and
	## the nearest distant mass stands at 210. Between them is eighty units of
	## nothing, and it is the band a viewer reads as "how big is this" - the one
	## place a mid-ground silhouette can sit and be unambiguously *between* the
	## machine and the mountains.
	##
	## `rounded` is the Collector variant: fewer, wider, smoother masses with a
	## flatter taper, which read as display plinths rather than as crags.
	var group := Node3D.new()
	group.name = "MesaPlinths" if rounded else "RidgeCards"
	root.add_child(group)
	var key := "rock_soft_mid" if rounded else "rock_soft_near"
	var shade = palette.get_material(key)
	var alternate = palette.get_material("rock_soft_far" if rounded
		else "rock_soft_mid")
	var sites := [
		[150.0, 126.0, 52.0, 30.0, 101], [176.0, 118.0, 60.0, 34.0, 109],
		[200.0, 132.0, 56.0, 32.0, 117], [224.0, 122.0, 62.0, 35.0, 125],
		[248.0, 140.0, 50.0, 29.0, 133], [128.0, 152.0, 46.0, 27.0, 141],
		[272.0, 158.0, 44.0, 26.0, 149],
	]
	var facets := 22 if rounded else 28
	var tiers := 9 if rounded else 14
	var taper := 0.52 if rounded else 0.32
	for index in sites.size():
		var site: Array = sites[index]
		var height := float(site[2]) * (1.25 if rounded else 1.0)
		var base := float(site[3]) * (1.5 if rounded else 1.0)
		var node := Forms.mesh_node(
			HeroWorld.smooth_mass(height, base, int(site[4]), facets, tiers,
				taper),
			shade if index % 2 == 0 else alternate,
			"Ridge%d" % index, false)
		# Base y chosen so a card's foot is under the terrain's own edge height
		# of -82: a mid-ground mass has to *emerge* from behind the massif, not
		# stand on top of it.
		node.position = _polar(float(site[0]), float(site[1]), -88.0)
		node.rotation.y = float(site[4]) * 0.37
		group.add_child(node)


static func _aurora(root: Node3D, palette) -> void:
	## Cold light in the upper sky, behind the ranges and above them.
	##
	## Aurora Valley's one piece of environmental emission, and it is sited by a
	## rule the brief states: cyan and violet belong to the *upper* areas of the
	## frame. Putting them at bearing 200 and high above the far range means the
	## only shots that see them are the ones whose camera is tilted up - the
	## course preview's opening and the wide descents - which are exactly the
	## frames that had nothing but flat sky in their top third.
	##
	## ## Curtains, not bands, and the first build proved why
	##
	## This began as fifteen horizontal slabs 210 units wide and 62 tall, three
	## tiers of five, at radius 720 to 800. Each one was faint; together they
	## tiled the whole upper sky into a solid pale cyan ceiling with a scalloped
	## edge where the rounded boxes met, and it was the worst artefact in the
	## lab - a *painted* sky sitting over the mountain in every preview frame.
	## Worse, it was diagnosed twice as something else, because the obvious
	## suspect for a pale mass in the sky is the haze banks that had just been
	## lifted into it; halving their lift changed the frame not at all, which is
	## what finally pointed here.
	##
	## Two things fix it and both are about *shape*. An aurora is a set of tall
	## narrow ribbons with gaps between them, so the slabs are turned ninety
	## degrees - 26 wide and 150 tall rather than 210 by 62 - and there are nine
	## rather than fifteen, spread over 120 degrees of bearing so that no two
	## overlap from any camera on the course. A ribbon that is mostly gap cannot
	## become a ceiling however many of them there are.
	##
	## The second is that `emission` survives an albedo alpha of zero: in the
	## unshaded path the emission term is added after the alpha the blend uses,
	## so the first build's "invisible albedo, faint emission" was in fact a
	## fully opaque glow. The alpha here is real and the emission is low.
	var group := Node3D.new()
	group.name = "Aurora"
	root.add_child(group)
	var tiers := [["#4FE3FF", 150.0, 0.34], ["#8C7CFF", 178.0, 0.24]]
	for tier in tiers.size():
		var entry: Array = tiers[tier]
		var glow := StandardMaterial3D.new()
		glow.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		glow.albedo_color = Color(str(entry[0]), 0.30)
		glow.metallic = 0.0
		glow.roughness = 1.0
		glow.cull_mode = BaseMaterial3D.CULL_DISABLED
		glow.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		glow.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_DISABLED
		glow.emission_enabled = true
		glow.emission = Color(str(entry[0]))
		glow.emission_energy_multiplier = float(entry[2])
		for index in 5 - tier:
			var bearing: float = 148.0 + float(index) * 27.0 + float(tier) * 13.0
			var curtain := Forms.mesh_node(
				Geometry.rounded_box(Vector3(26.0, 150.0, 5.0), 11.0, 2),
				glow, "Curtain%d_%d" % [tier, index], false)
			curtain.position = _polar(bearing, 780.0 + 50.0 * float(tier),
				float(entry[1]) + 26.0 * float(index % 3))
			curtain.rotation.y = deg_to_rad(bearing)
			curtain.rotation.z = (float(index) - 2.0) * 0.09
			group.add_child(curtain)


static func _crest_lines(root: Node3D, palette) -> void:
	## A thin lit edge along the mid crests: the graphic direction's one
	## sci-fi signature.
	##
	## Restrained on purpose. The brief asks for "subtle sci-fi environmental
	## accents, restrained neon, not cluttered", and a dark world will take any
	## amount of neon before it looks full - which is the trap. One line per
	## crest, at an energy that survives three hundred units of haze and does
	## nothing at thirty, keeps the accent in the background where it belongs.
	var group := Node3D.new()
	group.name = "CrestLines"
	root.add_child(group)
	var lit := StandardMaterial3D.new()
	lit.albedo_color = Color("#2FB8D8").darkened(0.55)
	lit.metallic = 0.0
	lit.roughness = 0.4
	lit.emission_enabled = true
	lit.emission = Color("#5FE4FF")
	lit.emission_energy_multiplier = 2.4
	lit.shading_mode = BaseMaterial3D.SHADING_MODE_PER_PIXEL
	for index in 9:
		var bearing: float = 140.0 + float(index) * 19.0
		var radius: float = 300.0 + 70.0 * float(index % 3)
		var bar := Forms.mesh_node(
			Geometry.rounded_box(Vector3(78.0, 1.6, 2.0), 0.7, 2),
			lit, "Crest%d" % index, false)
		bar.position = _polar(bearing, radius, -14.0 + 16.0 * float(index % 4))
		bar.rotation.y = deg_to_rad(bearing)
		bar.rotation.z = (float(index % 3) - 1.0) * 0.06
		group.add_child(bar)


static func _valley_grid(root: Node3D, palette, cfg: Dictionary) -> void:
	## A lit floor a long way down the gorge.
	##
	## `course_dressing._valley` already puts seven platforms on the valley
	## floor for exactly this reason, and in the V22.1 frames they are three
	## warm specks. This is the same idea at the scale the drop actually is: a
	## sparse orthogonal grid of thin emissive bars far below the track, which
	## reads as a floor rather than as scattered lights and therefore gives the
	## fall a measurable bottom.
	var group := Node3D.new()
	group.name = "ValleyGrid"
	root.add_child(group)
	var lit := StandardMaterial3D.new()
	lit.albedo_color = Color("#0A1C24")
	lit.metallic = 0.0
	lit.roughness = 0.5
	lit.emission_enabled = true
	lit.emission = Color("#35E0FF")
	lit.emission_energy_multiplier = 3.0
	lit.shading_mode = BaseMaterial3D.SHADING_MODE_PER_PIXEL
	var centre_x: float = float(cfg.get("centre_x", 0.0)) + 40.0
	var centre_z: float = float(cfg.get("centre_z", 0.0)) + 6.0
	var floor_y: float = float(cfg.get("edge_y", -82.0)) + 2.0
	for index in 7:
		var offset: float = (float(index) - 3.0) * 17.0
		group.add_child(Forms.placed(Forms.mesh_node(
			Geometry.rounded_box(Vector3(116.0, 0.5, 1.1), 0.2, 2),
			lit, "Along%d" % index, false),
			Vector3(centre_x, floor_y, centre_z + offset)))
		group.add_child(Forms.placed(Forms.mesh_node(
			Geometry.rounded_box(Vector3(1.1, 0.5, 116.0), 0.2, 2),
			lit, "Across%d" % index, false),
			Vector3(centre_x + offset, floor_y, centre_z)))


# --- shared -----------------------------------------------------------------


static func _polar(bearing: float, radius: float, y: float) -> Vector3:
	## `course_world._polar`, which is not a static this file can reach.
	var angle := deg_to_rad(bearing)
	return Vector3(sin(angle) * radius, y, cos(angle) * radius)


static func _layer(node: Node) -> void:
	## Everything this file touches or builds belongs to the world, which is
	## lit by the raking key on cull mask 2 and not by the product key on mask
	## 1. A mist deck on layer 1 would take the machine's warm key full in the
	## face and read as a tan sheet across the gorge.
	if node is VisualInstance3D:
		(node as VisualInstance3D).layers = WORLD_LAYER
	for child in node.get_children():
		_layer(child)
