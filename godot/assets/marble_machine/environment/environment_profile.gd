extends RefCounted

## THE ENVIRONMENT PROFILE: one named description of everything that is not
## the machine.
##
## Before this file the world was six sets of constants in four scripts -
## `course_world.gd` held the sky, the fog, the grade, the light rig and three
## mountain ranges; `course_terrain.gd` held the ground materials and the
## boulder values; `course_dressing.gd` held the lamps, the scrub, the pylons
## and the valley; `course_scene.gd` held the zone practicals. Changing the
## direction meant editing all four, and *keeping* two directions meant
## branching them.
##
## A profile is that same set of numbers as data, in one JSON file, under one
## id. `resolve()` hands back a single dictionary; `environment_builder.gd`
## turns it into the scene. Nothing about the machine, the track, the physics
## or the camera rig is in here or reachable from here.
##
## ## Profiles inherit
##
## `alpine_neon.json` is the root: it is the shipped V20/V21 look transcribed
## field for field, and it is the only file that has to be complete. Every
## other profile names it in `extends` and carries deltas, so a new theme is
## thirty lines rather than three hundred. Merging is deep, and a JSON `null`
## **erases** the inherited key - that is how `canyon_dusk` drops the twelve
## authored alpine masses and takes the generated mesa ring instead.
##
## ## The contrast pass is an overlay, not a fork
##
## V21's readability retune was a set of overrides applied inside an `if` in
## `course_world.gd`. Here it is `contrast.v21` inside the profile, merged on
## top after inheritance. So it stays a named, reviewable pass, it composes
## with any profile, and `--contrast=` still selects it.
##
## ## GEOMETRY IS NOT THEME
##
## The one rule this file enforces rather than documents. `course_terrain.gd`'s
## height function decides where every support pier stops, and `sloped/
## terrain.py` is an exact port of it that every production camera is solved
## against. A profile that moved the grade, the terraces, the gorge or the
## noise would silently invalidate both. So `validate()` rejects any profile
## carrying a terrain *shape* field, and the terrain section can name materials
## and scatter densities and nothing else. A theme repaints the mountain; it
## does not move it. Changing the landform is a layout change, and it belongs
## in `course_layout.gd` where the camera port can be re-verified against it.

const ROOT := "res://assets/marble_machine/environment/profiles"

## Terrain keys a profile may never set. These are the arguments to
## `course_terrain.height`, and `sloped/terrain.py` mirrors every one of them.
const SHAPE_FIELDS := [
	"top_y", "z_top", "grade", "steps", "left_at", "left_span", "left_rise",
	"gorge_at", "gorge_span", "gorge_depth", "crest_rise", "crest_scale",
	"centre_x", "centre_z", "edge_from", "edge_to", "edge_y", "noise", "pads",
	"cut_depth", "cut_inner", "cut_reach", "cut_index",
	"x_min", "x_max", "z_min", "z_max", "cell",
]

const SECTIONS := [
	"id", "title", "family", "summary", "extends",
	"sky", "grade", "fog", "ssao", "ssr", "glow", "lights", "backdrop",
	"terrain", "dressing", "zones", "ravine", "accent", "palette", "contrast",
	# V25. The near world - what a race camera can actually see that is not
	# the machine, the sky or a distant range. Built by
	# `environment_world.gd`; absent from every profile shipped before V25,
	# and absent means nothing is built.
	"world",
]

const TERRAIN_SECTIONS := ["surfaces", "scatter"]

const DEFAULT_ID := "alpine_neon"

static var _cache: Dictionary = {}


static func index() -> Dictionary:
	var parsed = _read("%s/index.json" % ROOT)
	if typeof(parsed) != TYPE_DICTIONARY:
		push_error("environment_profile: profiles/index.json is unreadable")
		return {"default": DEFAULT_ID, "profiles": [DEFAULT_ID]}
	return parsed


static func ids() -> Array:
	var listed: Array = index().get("profiles", [])
	var out: Array = []
	for entry in listed:
		out.append(str(entry))
	return out


static func default_id() -> String:
	return str(index().get("default", DEFAULT_ID))


static func has(id: String) -> bool:
	return id in ids()


static func _read(path: String):
	var text := FileAccess.get_file_as_string(path)
	if text.is_empty():
		return null
	return JSON.parse_string(text)


static func _load(id: String) -> Dictionary:
	## One profile file, unmerged, with its `extends` chain still to follow.
	if _cache.has(id):
		return _cache[id]
	var parsed = _read("%s/%s.json" % [ROOT, id])
	if typeof(parsed) != TYPE_DICTIONARY:
		push_error("environment_profile: no profile '%s'" % id)
		return {}
	_cache[id] = parsed
	return parsed


static func merge(base: Dictionary, over: Dictionary) -> Dictionary:
	## Deep merge. A dictionary recurses, anything else replaces, and `null`
	## erases - which is the only way a child can *remove* an inherited list
	## rather than shadow it with an empty one that still reads as authored.
	var out := base.duplicate(true)
	for key in over:
		var value = over[key]
		if value == null:
			out.erase(key)
			continue
		if value is Dictionary and out.get(key) is Dictionary:
			out[key] = merge(out[key], value)
		elif value is Dictionary or value is Array:
			out[key] = value.duplicate(true)
		else:
			out[key] = value
	return out


static func resolve(id := "", contrast := "") -> Dictionary:
	## The finished profile: inheritance chain, then the contrast overlay,
	## then the accent dial. This is the only thing the builder ever sees.
	var wanted := id if id != "" else default_id()
	var chain: Array = []
	var cursor := wanted
	var guard := 0
	while cursor != "":
		var step := _load(cursor)
		if step.is_empty():
			break
		chain.push_front(step)
		var parent = step.get("extends", null)
		cursor = "" if parent == null else str(parent)
		guard += 1
		if guard > 16:
			push_error("environment_profile: '%s' has a cyclic extends" % wanted)
			break

	var profile: Dictionary = {}
	for step in chain:
		profile = merge(profile, step)
	# The child's identity survives its parent's, which inheritance would
	# otherwise overwrite - `merge` has no idea these three fields are not
	# theme values.
	var own := _load(wanted)
	for field in ["id", "title", "family", "summary"]:
		if own.has(field):
			profile[field] = own[field]
	profile["extends"] = own.get("extends", null)

	if contrast != "":
		var passes: Dictionary = profile.get("contrast", {})
		if passes.has(contrast):
			profile = merge(profile, passes[contrast])
		profile["contrast_pass"] = contrast
	else:
		profile["contrast_pass"] = ""
	profile.erase("contrast")
	_apply_accent(profile)
	return profile


static func _apply_accent(profile: Dictionary) -> void:
	## One dial over the profile's own lit values.
	##
	## Deliberately not a global emissive multiplier: it reaches the zone
	## practicals, the course spill and any emissive surface the profile
	## itself overrides, and it reaches nothing it cannot see a base value
	## for. A dial that silently scaled materials it had never been shown
	## would make two profiles with the same numbers render differently.
	var gain: float = float((profile.get("accent", {}) as Dictionary)
		.get("intensity", 1.0))
	if is_equal_approx(gain, 1.0):
		return
	var zones: Dictionary = profile.get("zones", {})
	for name in zones:
		var zone: Dictionary = zones[name]
		zone["energy"] = float(zone.get("energy", 1.0)) * gain
	var practicals: Dictionary = (profile.get("dressing", {}) as Dictionary) \
		.get("practicals", {})
	for slot in ["spill", "under"]:
		if practicals.has(slot):
			var lamp: Dictionary = practicals[slot]
			lamp["energy"] = float(lamp.get("energy", 1.0)) * gain
	var palette: Dictionary = profile.get("palette", {})
	for key in palette:
		var spec: Dictionary = palette[key]
		if spec.has("energy"):
			spec["energy"] = float(spec["energy"]) * gain


# --- validation -----------------------------------------------------------


static func validate(profile: Dictionary) -> Array:
	## Every complaint, as strings. Empty means the profile is usable.
	var problems: Array = []
	for field in ["id", "title", "summary"]:
		if str(profile.get(field, "")).is_empty():
			problems.append("missing %s" % field)
	for key in profile:
		var name := str(key)
		if name in SECTIONS or name == "contrast_pass":
			continue
		problems.append("unknown section '%s'" % name)

	var terrain: Dictionary = profile.get("terrain", {})
	for key in terrain:
		var name := str(key)
		if name in SHAPE_FIELDS:
			problems.append(
				"terrain.%s is landform, not theme - see GEOMETRY IS NOT THEME"
					% name)
		elif not name in TERRAIN_SECTIONS:
			problems.append("unknown terrain key '%s'" % name)

	for pass_name in (profile.get("contrast", {}) as Dictionary):
		var overlay: Dictionary = profile["contrast"][pass_name]
		if overlay.has("terrain"):
			for key in (overlay["terrain"] as Dictionary):
				if str(key) in SHAPE_FIELDS:
					problems.append(
						"contrast.%s.terrain.%s is landform, not theme"
							% [pass_name, key])

	var lights: Dictionary = profile.get("lights", {})
	for name in lights:
		var light: Dictionary = lights[name]
		if float(light.get("energy", 0.0)) < 0.0:
			problems.append("lights.%s.energy is negative" % name)
	return problems


static func describe(profile: Dictionary) -> String:
	var backdrop: Dictionary = profile.get("backdrop", {})
	var counted := 0
	for layer in ["near_range", "ridge_range", "mid_range", "far_range"]:
		counted += masses_of(backdrop.get(layer, {})).size()
	var scatter: Array = (profile.get("terrain", {}) as Dictionary) \
		.get("scatter", [])
	var rocks := 0
	for entry in scatter:
		rocks += int((entry as Dictionary).get("count", 0))
	return "%s (%s): %d backdrop masses, %d scattered rocks, accent %.2f" % [
		str(profile.get("title", "?")), str(profile.get("family", "?")),
		counted, rocks,
		float((profile.get("accent", {}) as Dictionary).get("intensity", 1.0)),
	]


# --- the mass ring generator ----------------------------------------------


static func masses_of(layer: Dictionary) -> Array:
	## A backdrop layer's masses, authored or generated.
	##
	## Authored wins, because the alpine ranges were placed by eye against a
	## specific camera and no generator reproduces that. A theme that has no
	## such study sets `masses: null` and a `ring`, and gets a deterministic
	## arc with the same five columns, so the builder never learns which it is.
	if layer.get("masses") is Array:
		return layer["masses"]
	var ring = layer.get("ring")
	if not (ring is Dictionary):
		return []
	var spec: Dictionary = ring
	var out: Array = []
	var count := int(spec.get("count", 0))
	for index in count:
		var bearing: float = float(spec.get("bearing_from", 0.0)) \
			+ float(spec.get("bearing_step", 0.0)) * float(index)
		var radius: float = float(spec.get("radius", 200.0)) \
			+ float(spec.get("radius_step", 0.0)) \
			* float(index % maxi(int(spec.get("radius_cycle", 1)), 1))
		var height: float = float(spec.get("height", 100.0)) \
			+ float(spec.get("height_step", 0.0)) \
			* float(index % maxi(int(spec.get("height_cycle", 1)), 1))
		var base: float = float(spec.get("base", 40.0)) \
			+ float(spec.get("base_step", 0.0)) \
			* float(index % maxi(int(spec.get("base_cycle", 1)), 1))
		var seed := int(spec.get("seed_from", 1)) \
			+ int(spec.get("seed_step", 8)) * index
		out.append([fposmod(bearing, 360.0), radius, height, base, seed])
	return out
