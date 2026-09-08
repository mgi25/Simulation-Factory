extends RefCounted

## THE STYLE SYSTEM for the sloped course: five independent visual axes.
##
## This file changes no geometry that a marble can touch. It retunes named
## palette surfaces, patches the `Environment`, re-masks the light rig and adds
## purely-scenic volumes beyond the massif. Every axis defaults to `base`, and
## `base` on every axis is a no-op, so an un-styled build renders exactly the
## frame `marble-sloped-course-lab` committed.
##
## ## Why five axes and not five styles
##
## A "style" is a set, and comparing two sets tells you which set you prefer
## and nothing about why. So track, guard, support, environment and finish are
## selected separately (`--track=pearl --guard=lit ...`) and each candidate
## sheet moves exactly one of them. That is the only way a sheet answers
## "pearl or silver" rather than "sheet 1 or sheet 3".
##
## The axes are genuinely separable because the palette now carries an alias
## per shared surface - `keel_graphite` for the track's belly against `strut`
## for the piers under it - added with identical base values for this purpose.
##
## ## The three faults every candidate here is answering
##
## Measured off the committed hero and section frames, not guessed:
##
## **Pearl clips.** `pearl_shell` is `#E8E6E0`, linear 0.79, under a key at
## energy 3.2 with `tonemap_exposure 0.82`. The product of those is far past
## the ACES shoulder, so every lit face of the channel resolves to the same
## white and the shell, the lip and the polished floor become one flat band.
## The track reads as a painted road. Premium pearl needs a *lower* albedo
## than the word "pearl" suggests - the gloss has to come from the clearcoat
## lobe, not from the albedo.
##
## **Metal hardware is invisible.** The palette's own docstring says a
## metallic surface has almost nothing to reflect in a dark scene, then spends
## `_metal` on the support caps and the track's rib blocks. At `metallic 1.0`
## they trade their albedo for a reflection of an unlit sky and come back
## dull olive. Warm accents have to be *moulded* with a metallic hint, not
## metal.
##
## **Warm light is on the wrong layer.** `course_terrain` puts the near ground
## on the world layer, so `WorldWarm` - the amber rake that is supposed to
## light the far ranges - hits the mountainside under the track at full energy
## and turns it tan. The environment axis gives the near ground a layer of its
## own so the distance can be warm while the ground the course stands on stays
## cool. That single split is what produces the warm/cool depth the target
## concept has.

const Geometry := preload("res://scripts/toy_geometry.gd")
const Forms := preload("res://assets/marble_machine/lab_forms.gd")
const Palette := preload("res://assets/marble_machine/lab_palette.gd")

# Visual layers. 1 is the product, as before. The environment axis moves the
# near ground off the world layer onto 4 so the two can be lit apart.
const PRODUCT_LAYER := 1
const WORLD_LAYER := 2
const GROUND_LAYER := 4

const AXES := ["track", "guard", "support", "env", "finish"]

# The locked direction, applied by `--style=lock`. Named rather than inlined
# so the report, the tool and the scene all quote the same four words.
const LOCK := {
	"track": "pearl", "guard": "cast", "support": "brass",
	"env": "valley", "finish": "gold",
}


static func options(given: Dictionary) -> Dictionary:
	## Resolve the five axes from command-line options.
	var out := {}
	for axis in AXES:
		out[axis] = "base"
	var style := str(given.get("style", ""))
	if style == "lock":
		for axis in AXES:
			out[axis] = str(LOCK[axis])
	for axis in AXES:
		if given.has(axis):
			out[axis] = str(given[axis])
	return out


static func label(opts: Dictionary) -> String:
	var parts: Array = []
	for axis in AXES:
		parts.append("%s=%s" % [axis, str(opts[axis])])
	return " ".join(parts)


static func styled(opts: Dictionary) -> bool:
	for axis in AXES:
		if str(opts[axis]) != "base":
			return true
	return false


# --- palette ---------------------------------------------------------------


static func apply(palette, opts: Dictionary) -> void:
	## Seed the palette's cache with every retuned surface, before anything
	## has asked for one. Order is irrelevant: no two axes touch the same key.
	_track(palette, str(opts["track"]))
	_guard(palette, str(opts["guard"]))
	_support(palette, str(opts["support"]))
	_env_materials(palette, str(opts["env"]))
	_finish(palette, str(opts["finish"]))


# --- B: track material -----------------------------------------------------
#
# Three candidates against the shipped channel. All three keep the six-feature
# section and the 1.88 clear width untouched - this axis is albedo, roughness
# and the two gloss lobes, nothing else.
#
#   pearl    warm pearl pulled off the clip point, cool silver running band,
#            deep keel. The value ladder the section was designed to have.
#   silver   the shell itself goes cool silver. Closer to the concept's
#            "Light Silver / Gray" swatch, and the risk is that it reads grey.
#   fascia   warm pearl, low gloss, near-black belly. Maximum underside
#            contrast, and the softest highlight of the three.


static func _track(palette, name: String) -> void:
	match name:
		"base":
			return
		"pearl":
			# Albedo down about a third from #E8E6E0 so the lit shoulder lands
			# near white instead of on it, roughness up so the highlight is a
			# band rather than a line, clearcoat down to match.
			palette.override("pearl_shell",
				palette.make_moulded("#D8D4CB", 0.30, 0.72, 0.085))
			palette.override("pearl_shade",
				palette.make_moulded("#B4B0A7", 0.36, 0.50, 0.13))
			palette.override("pearl_lip_v2",
				palette.make_moulded("#EDE9DF", 0.22, 0.85, 0.055))
			# The running band. Two full steps below the shell, cool against
			# its warmth, and with the clearcoat lobe cut from 1.0 to 0.45 -
			# that second lobe on a wide sky-facing cradle was the actual
			# source of the white stripe, not the metallic term.
			palette.override("running_polished",
				_part_metal(palette, "#7F8B99", 0.24, 0.45, 0.58, 0.68))
			palette.override("running_blue",
				_part_metal(palette, "#7CA4C6", 0.22, 0.45, 0.52, 0.70))
			palette.override("running_orange",
				_part_metal(palette, "#C08F6E", 0.22, 0.45, 0.52, 0.70))
			palette.override("running_warm",
				_part_metal(palette, "#93856B", 0.22, 0.45, 0.55, 0.70))
			palette.override("keel_graphite",
				palette.make_moulded("#191D24", 0.48, 0.30, 0.18))
		"silver":
			palette.override("pearl_shell",
				palette.make_moulded("#C6CED7", 0.26, 0.85, 0.055))
			palette.override("pearl_shade",
				palette.make_moulded("#9DA6B0", 0.34, 0.55, 0.12))
			palette.override("pearl_lip_v2",
				palette.make_moulded("#DFE6EE", 0.20, 0.92, 0.045))
			palette.override("running_polished",
				_part_metal(palette, "#6E7C8C", 0.22, 0.50, 0.65, 0.72))
			palette.override("running_blue",
				_part_metal(palette, "#6F97BC", 0.22, 0.50, 0.58, 0.70))
			palette.override("running_orange",
				_part_metal(palette, "#B4876A", 0.22, 0.50, 0.58, 0.70))
			palette.override("running_warm",
				_part_metal(palette, "#8A8069", 0.22, 0.50, 0.60, 0.70))
			palette.override("keel_graphite",
				palette.make_moulded("#171B22", 0.46, 0.34, 0.17))
		"fascia":
			palette.override("pearl_shell",
				palette.make_moulded("#DED7C8", 0.33, 0.60, 0.11))
			palette.override("pearl_shade",
				palette.make_moulded("#B5AC99", 0.38, 0.45, 0.15))
			palette.override("pearl_lip_v2",
				palette.make_moulded("#F0EADC", 0.24, 0.78, 0.06))
			palette.override("running_polished",
				_part_metal(palette, "#8C929A", 0.30, 0.20, 0.45, 0.60))
			palette.override("running_blue",
				_part_metal(palette, "#8AABC6", 0.28, 0.20, 0.42, 0.60))
			palette.override("running_orange",
				_part_metal(palette, "#C4977B", 0.28, 0.20, 0.42, 0.60))
			palette.override("running_warm",
				_part_metal(palette, "#9C9078", 0.28, 0.20, 0.45, 0.60))
			palette.override("keel_graphite",
				palette.make_moulded("#0E1116", 0.55, 0.22, 0.20))
		_:
			push_error("course_style: unknown track '%s'" % name)


static func _part_metal(palette, hex: String, roughness: float,
		clearcoat: float, metallic: float,
		specular: float) -> StandardMaterial3D:
	## A running surface: partly metallic so it darkens where it sees nothing
	## and flares where it sees a light, with the clearcoat lobe kept small.
	var material: StandardMaterial3D = palette.make_moulded(
		hex, roughness, clearcoat, 0.05)
	material.metallic = metallic
	material.metallic_specular = specular
	return material


# --- C: guard system -------------------------------------------------------
#
# The shipped guard is `#7FE0E8` at alpha 0.115 with a 0.30 rim on a wall
# 0.26 units tall. At the hero distance that is under two pixels of a
# twelve-per-cent tint and it disappears completely; the target concept's
# aqua rails are one of the four things that read at a glance. Geometry is
# untouched, so all three candidates buy their presence optically.
#
#   tint    more pigment and a stronger frosted edge. Cheapest, and it holds
#           its colour in a still.
#   lit     moderate tint plus a low self-emission, so the rail survives
#           being resized to phone width. The trick every neon reference uses.
#   glass   heavy tint, low rim: thick cast glass rather than a lit rail.


static func _guard(palette, name: String) -> void:
	if name == "base":
		return
	# hue, alpha, rim, emission energy - per candidate, per branch identity.
	var recipe := {}
	match name:
		"tint":
			recipe = {"alpha": 0.30, "rim": 0.44, "glow": 0.0,
				"backlight": 0.55}
		"lit":
			recipe = {"alpha": 0.22, "rim": 0.36, "glow": 0.55,
				"backlight": 0.60}
		"glass":
			recipe = {"alpha": 0.40, "rim": 0.26, "glow": 0.0,
				"backlight": 0.45}
		"cast":
			# The pick, and a combination rather than a fifth idea. `glass`
			# gave the strongest aqua and the best thickness read; `lit` was
			# the only one that survived being resized to phone width,
			# because emission does not average away and a tint does. So:
			# most of glass's pigment, a rim between the two, and enough
			# self-emission to keep the rail on a 390-pixel frame.
			recipe = {"alpha": 0.34, "rim": 0.32, "glow": 0.40,
				"backlight": 0.50}
		_:
			push_error("course_style: unknown guard '%s'" % name)
			return
	# The four guard identities: the neutral rail, the two route colours and
	# the finale's. All four move together - a split whose blue rail is cast
	# glass and whose amber rail is a lit strip reads as two products.
	var hues := {
		"acrylic_guard": "#63D2E0",
		"acrylic_blue": "#5AB6F2",
		"acrylic_amber": "#F2A254",
		"acrylic_gold": "#F4CE7C",
		"acrylic_bowl": "#63D2E0",
	}
	for key in hues:
		var hex := str(hues[key])
		var material: StandardMaterial3D = palette.make_acrylic(
			hex, float(recipe["alpha"]), float(recipe["rim"]), 0.03,
			float(recipe["backlight"]))
		var glow: float = float(recipe["glow"])
		if glow > 0.0:
			# A guard that emits a little is still a guard: the emission is a
			# fraction of a lit strip's, so the rail glows along its length
			# and does not become a light source in its own right.
			material.emission_enabled = true
			material.emission = Color(hex)
			material.emission_energy_multiplier = glow
		palette.override(key, material)


# --- D: support system -----------------------------------------------------
#
# The piers read as a picket fence of near-black hairlines with dull olive
# caps. Two separate causes: `strut` at `#2A2E35` has no lit-face value at
# all against dark ground, and `strut_accent` is `_metal` - which in this
# scene reflects an unlit sky and loses its colour. Every candidate below
# raises the graphite one step and replaces the metal accent with a moulded
# one carrying a metallic hint.
#
#   brass   graphite with warm brass caps. The concept's own hardware colour.
#   copper  cooler graphite, hotter copper accent. More contrast, more risk
#           of looking rusty.
#   mono    two-tone graphite and no warm accent at all, as the control for
#           "not too busy".


static func _structural(palette, hex: String,
		roughness: float) -> StandardMaterial3D:
	## A structural member: matte, no clearcoat, and *low specular*.
	##
	## The third attempt at this, and the first that worked. A pier is a
	## vertical cylinder and the rim light rakes in from nine degrees above
	## the horizontal with `light_specular 1.5`, so it lays a bright stripe
	## down every leg's full length. Raising roughness made that worse rather
	## than better - a broader lobe spreads the stripe across more of the
	## cylinder - and dropping the clearcoat only removed the second, thinner
	## one on top of it.
	##
	## `metallic_specular` is the dielectric F0 scale in Godot 4 and applies
	## to non-metals, so it is the one dial that turns the stripe down without
	## touching a light every other surface in the frame depends on. At 0.12
	## a graphite member reads as graphite; the rim keeps its full strength on
	## the pearl channel, which is what it is there for.
	var material: StandardMaterial3D = palette.make_moulded(hex, roughness,
		0.0)
	material.clearcoat_enabled = false
	material.metallic_specular = 0.12
	return material


static func _support(palette, name: String) -> void:
	## Every candidate here is rough and barely lacquered, and that is the
	## finding rather than a taste. A support is a long thin cylinder, and a
	## clearcoat lobe on one - under a rim light carrying `light_specular
	## 1.5` for the pearl channel's benefit - returns a single bright streak
	## running its whole length. The first pass kept the palette's graphite
	## gloss and every pier came back reading as a polished steel tube, on
	## all three candidates equally. Graphite is a matte structural finish.
	match name:
		"base":
			return
		"brass":
			palette.override("strut",
				_structural(palette, "#333A44", 0.58))
			palette.override("strut_deep",
				_structural(palette, "#181C23", 0.66))
			palette.override("strut_accent", _warm_metal(palette, "#C89A4C"))
			palette.override("gold", _warm_metal(palette, "#D2A455"))
			palette.override("gold_dark", _warm_metal(palette, "#A87F2E"))
			palette.override("graphite_soft",
				_structural(palette, "#353C46", 0.46))
		"copper":
			palette.override("strut",
				_structural(palette, "#2B323C", 0.60))
			palette.override("strut_deep",
				_structural(palette, "#14181E", 0.68))
			palette.override("strut_accent", _warm_metal(palette, "#BE7A42"))
			palette.override("gold", _warm_metal(palette, "#C98A4A"))
			palette.override("gold_dark", _warm_metal(palette, "#9C6430"))
			palette.override("graphite_soft",
				_structural(palette, "#2E353F", 0.48))
		"mono":
			palette.override("strut",
				_structural(palette, "#394252", 0.58))
			palette.override("strut_deep",
				_structural(palette, "#171B22", 0.66))
			palette.override("strut_accent",
				_structural(palette, "#5B677A", 0.42))
			palette.override("gold",
				_structural(palette, "#6B7788", 0.40))
			palette.override("graphite_soft",
				_structural(palette, "#2F3743", 0.48))
		_:
			push_error("course_style: unknown support '%s'" % name)


static func _warm_metal(palette, hex: String) -> StandardMaterial3D:
	## Warm hardware that keeps its colour in an unlit scene.
	##
	## Moulded, with a third of a metallic term for specular life. A full
	## `metallic 1.0` gold has no diffuse response, and in a scene whose
	## reflection source is a nearly black dusk sky it renders as dark olive -
	## which is what every gold cap and rib block on the committed frames is.
	var material: StandardMaterial3D = palette.make_moulded(hex, 0.22, 0.9, 0.04)
	material.metallic = 0.34
	material.metallic_specular = 0.78
	return material


static func mast_stock(opts: Dictionary) -> float:
	## Column radius for the trackside lamp masts.
	##
	## 0.10 is a hairline at the hero distance: the column vanishes and its
	## foot block is left reading as a dark box hanging on a wire, which is
	## the single most debug-looking detail in the committed section frames.
	## A mast is a member; it gets member stock.
	return 0.10 if str(opts.get("support", "base")) == "base" else 0.145


static func mast_foot(opts: Dictionary) -> float:
	## Footing size for the trackside lamp masts.
	##
	## Held at the base value while the column thickens, which is the whole
	## correction: the box-on-a-wire read comes from the *ratio* between the
	## two, so scaling the footing off the column preserves it exactly.
	return 0.62


# --- E: environment --------------------------------------------------------
#
# The one axis that is not only materials. Three things move together, because
# separating them produces frames nobody would choose:
#
#   the light rig     the near ground gets its own layer, so the amber dusk
#                     rake reaches the distance without tanning the
#                     mountainside; the cyan rim is masked to the product
#                     instead of teal-rimming every boulder on the hill.
#   the atmosphere    a cooler, denser, height-pooled haze and a warmer sky
#                     horizon, so distance separates by temperature as well
#                     as by value.
#   scenic volumes    a warm dusk band that clears the far range instead of
#                     hiding behind it, and lit settlement on the near
#                     crests. Beyond the massif, and touched by nothing.
#
#   depth    the layer split, the haze and the sky. No new geometry.
#   valley   depth, plus the scenic volumes and a darker near ground.
#   warm     depth with a warm-dominant dusk, as the counter-proposal.


static func _env_materials(palette, name: String) -> void:
	if name == "base":
		return
	# The distant ranges. Pushed cooler and further apart in value, because
	# the whole job of three rings at 210, 380 and 600 units is to be three
	# distinguishable distances.
	palette.override("rock_soft_near", palette.make_matte("#141B26", 0.96))
	palette.override("rock_soft_mid", palette.make_matte("#22344B", 0.96))
	palette.override("rock_soft_far", palette.make_matte("#3B5877", 0.97))
	palette.override("rock_soft_haze", palette.make_matte("#54748F", 0.98))
	palette.override("cloud_bank", palette.make_matte("#2C4A68", 0.98))
	palette.override("far_structure", palette.make_matte("#41556E", 0.95))

	if name == "valley":
		# The near ground goes down, not up. The track is the brightest thing
		# in the frame and it needs something to be bright *against*; at the
		# shipped values the mountainside and the pearl channel are close
		# enough in the shadows that the silhouette softens.
		palette.override("slope_cliff", palette.make_matte("#1A222C", 0.95))
		palette.override("slope_rock", palette.make_matte("#232C38", 0.94))
		palette.override("slope_earth", palette.make_matte("#333B4C", 0.93))
		palette.override("slope_scree", palette.make_matte("#2A3445", 0.94))
		palette.override("slope_cap", palette.make_matte("#28323E", 0.94))
		palette.override("slope_moss", palette.make_matte("#27352D", 0.95))
		palette.override("slope_boulder", palette.make_matte("#1E2732", 0.94))
	if name == "warm":
		# The counter-proposal: warmth in the ground itself rather than only
		# in the light on it.
		palette.override("slope_cliff", palette.make_matte("#1F212A", 0.95))
		palette.override("slope_rock", palette.make_matte("#2A2A31", 0.94))
		palette.override("slope_earth", palette.make_matte("#3B3742", 0.93))
		palette.override("slope_cap", palette.make_matte("#2F2E38", 0.94))
	# 0.85, not 2.6. A dusk band subtends a fifth of the frame's height, and
	# a large area at line energy is a blown patch: the first pass put a
	# peach slab across the sky brighter than the finish arena.
	palette.override("lit_dusk_band", palette.make_emissive("#D98F5C", 0.85, 0.42))
	palette.override("lit_far_window_hero",
		palette.make_emissive("#FFD39A", 2.4, 0.30))

	# The zone colours, retuned down. This belongs to the environment axis
	# and not to the track's, because an emissive line's *correct* energy is
	# a function of the tonemap and the glow threshold - both of which are
	# set here - and of nothing on the track at all.
	#
	# At energy 8 to 10 every rail's core is far past the ACES shoulder, so
	# the line renders white and its hue survives only in the bloom halo.
	# That is why the committed hero frame has a cyan start, a violet mixer
	# and an orange choice and reads as three white lines with coloured fog
	# around them: the colour journey was authored correctly and then burnt
	# off. Halved, each rail keeps its own hue in its own pixels.
	palette.override("lit_cyan_line_hero", palette.make_emissive(
		Palette.CYAN, 5.2, 0.10))
	palette.override("neon_violet_hero", palette.make_emissive(
		Palette.VIOLET, 6.0, 0.06))
	palette.override("lit_violet_ring_hero", palette.make_emissive(
		Palette.VIOLET, 5.6, 0.10))
	palette.override("neon_blue", palette.make_emissive("#3FA8FF", 5.2, 0.08))
	palette.override("lit_orange_line", palette.make_emissive(
		Palette.ORANGE, 5.0, 0.06))
	palette.override("lit_gold_line", palette.make_emissive(
		Palette.GOLD_LIGHT, 4.6, 0.14))
	# Vegetation: darker and less olive. Lit by the near-ground warm rake,
	# `scrub_dark` came back as bright moss chips lying on a blue hillside.
	palette.override("scrub_dark", palette.make_matte("#16221C", 0.96))
	palette.override("scrub_dry", palette.make_matte("#1F2018", 0.95))
	palette.override("lit_valley_hero",
		palette.make_emissive("#FFA255", 5.5, 0.26))


static func tune_environment(env: Environment, name: String) -> void:
	## Sky, haze and tonemap, patched on top of `course_world`'s dusk.
	if name == "base":
		return
	var sky_material: ProceduralSkyMaterial = (env.sky.sky_material
		as ProceduralSkyMaterial)
	# A dusk sky with one warm value at the horizon and one near-black at the
	# top is a gradient with nothing in the middle. Three named colours and a
	# flatter curve put the transition where a camera pitched fifteen degrees
	# down actually sees it.
	sky_material.sky_top_color = Color("#071426")
	sky_material.sky_horizon_color = Color("#5F5560" if name != "warm"
		else "#8A6250")
	# 0.42, not 0.16. A low curve spreads the horizon colour over most of
	# the dome, and with a warm horizon that fills the top of every portrait
	# frame with flat orange. High, the warmth is a band at the skyline with
	# deep dusk blue above it - which is what a dusk actually looks like and
	# what leaves the frame's warmest pixels down at the finish arena.
	sky_material.sky_curve = 0.42
	# A 46-degree disk is a wash across a third of the sky; at 21 it is a
	# dusk sun with a glow around it, which is what puts a warm gradient
	# behind the ridge line without any geometry in front of it.
	sky_material.sun_angle_max = 11.0
	sky_material.sun_curve = 0.22
	sky_material.energy_multiplier = 1.0
	sky_material.ground_bottom_color = Color("#070D18")
	# The sky's *ground* half, and it matters more than the dome does. Every
	# camera on this course is pitched down, and `fog_aerial_perspective`
	# blends this colour into the fog over anything far away - so the pale
	# region filling the upper third of the finish frame is largely this
	# swatch, seen through 1400 units of haze.
	sky_material.ground_horizon_color = Color("#2A2632")
	env.background_energy_multiplier = 0.92

	env.ambient_light_energy = 0.46
	env.tonemap_exposure = 0.86 if name != "warm" else 0.88

	# Haze. Density stays low - the finish must not be hazed away from a
	# camera at the start - and the height term carries the separation, which
	# is also what haze does: it pools in a valley rather than filling a
	# mountainside evenly. The colour is the important change: `#5E5A6E` is a
	# desaturated mauve, and a mauve haze over a blue mountain is the whole
	# muddy cast on the committed frames.
	# Dark, and that is the point. Aerial perspective blends a distant
	# surface toward the fog's own lit colour, and the terrain fades to a
	# valley floor at y -82 that runs to the horizon - so at 0.62 energy and
	# 0.80 aerial the upper third of every low camera's frame is that floor
	# washed to pale grey. It is the "empty pale sheet" behind the finish
	# arena on the committed frames, and it is not the sky: at elevation 21
	# with a 34-degree lens there is no sky in that shot at all.
	env.fog_light_color = Color("#2F4A66" if name != "warm"
		else "#5A4A54")
	env.fog_light_energy = 0.30
	# 0.14, against the 0.52 this branch inherited. `fog_sun_scatter` adds
	# every directional light's colour into the fog along the view ray, and
	# this rig has six of them at energies 1.2 to 2.7 - so the term is
	# multiplied six times over. That, and not the fog colour or the sky, is
	# why the far valley floor renders as a bright pale sheet however dark
	# the fog is set: at 1400 units the fog is 93% opaque and almost all of
	# what it carries is scattered key light.
	env.fog_sun_scatter = 0.14
	env.fog_density = 0.0019
	# The near-camera haze wall was the worst artefact in the finish frame:
	# at 0.30 sky affect the sky behind a close-up subject resolves to one
	# flat pale sheet and half the picture is empty grey.
	env.fog_sky_affect = 0.22
	env.fog_aerial_perspective = 0.62
	env.fog_height = -26.0
	env.fog_height_density = 0.030

	env.adjustment_contrast = 1.10
	env.adjustment_saturation = 1.26 if name != "warm" else 1.20
	if env.glow_enabled:
		# The edge lights run at emission energy 8 to 10 and the glow
		# threshold is 1.16, so every rail is deep into bloom and the bloom
		# is what washes the pearl beside it. Lifting the threshold keeps the
		# lines glowing and takes the halo off the shell.
		env.glow_hdr_threshold = 1.55
		env.glow_intensity = 0.95
		env.glow_bloom = 0.20


static func tune_lights(parent: Node3D, name: String) -> void:
	## Re-mask and retune the rig `course_world.build_lights` installed.
	if name == "base":
		return
	var both := WORLD_LAYER | GROUND_LAYER

	var key := parent.get_node_or_null("Key") as DirectionalLight3D
	if key != null:
		# The product key comes down from 3.2. It is the reason pearl clips,
		# and every candidate on the track axis is compensating for it with
		# albedo; taking a little out of the light lets the albedo stay where
		# a moulded shell belongs.
		key.light_energy = 2.7
		key.light_color = Color("#FFF1DE")

	var world_key := parent.get_node_or_null("WorldKey") as DirectionalLight3D
	if world_key != null:
		world_key.light_cull_mask = both
		world_key.light_energy = 2.6

	var world_fill := parent.get_node_or_null("WorldFill") as DirectionalLight3D
	if world_fill != null:
		world_fill.light_cull_mask = both
		world_fill.light_color = Color("#5F8CBA")
		world_fill.light_energy = 1.18

	# The split that makes the frame. The amber rake keeps its full energy on
	# the distance, where it is the warm half of the dusk, and the near ground
	# gets a separate, much weaker one - so the mountainside under the track
	# stays cool rock instead of turning tan camouflage.
	var world_warm := parent.get_node_or_null("WorldWarm") as DirectionalLight3D
	if world_warm != null:
		world_warm.light_cull_mask = WORLD_LAYER
		world_warm.light_energy = 2.6 if name != "warm" else 3.4
		world_warm.light_color = Color("#FF9A4A")

	var ground_warm := DirectionalLight3D.new()
	ground_warm.name = "GroundWarm"
	ground_warm.light_cull_mask = GROUND_LAYER
	ground_warm.light_color = Color("#E08C58")
	ground_warm.light_energy = 0.85 if name != "warm" else 1.7
	ground_warm.light_specular = 0.0
	ground_warm.shadow_enabled = false
	ground_warm.rotation_degrees = Vector3(-8.0, 52.0, 0.0)
	parent.add_child(ground_warm)

	# The rim had no cull mask, so a cyan light with specular 1.5 was rimming
	# every boulder and terrace lip on the mountain - which is why the scatter
	# in the finish frame reads as teal litter lying on the ground. A rim
	# light belongs to the subject.
	var rim := parent.get_node_or_null("Rim") as DirectionalLight3D
	if rim != null:
		rim.light_cull_mask = PRODUCT_LAYER
		rim.light_energy = 2.5

	var bounce := parent.get_node_or_null("ValleyBounce") as DirectionalLight3D
	if bounce != null:
		bounce.light_cull_mask = PRODUCT_LAYER | GROUND_LAYER
		bounce.light_energy = 1.05

	# One sun, and it is not any of the lights above.
	#
	# A `ProceduralSkyMaterial` draws a sun disk for every directional light
	# whose `sky_mode` includes the sky, and this rig has six - so the sky
	# was carrying six overlapping glows, all of them behind the camera. The
	# warm rake has to come from +X +Z or it lights only the uphill faces
	# this course's cameras never see, which means the sun that *should* be
	# in frame cannot be the same light.
	#
	# So every functional light is demoted to `LIGHT_ONLY` and one
	# `SKY_ONLY` light is aimed at bearing 202 - the bearing the hero and
	# every section camera look along - three degrees above the horizon. It
	# contributes no lighting at all; it exists to put a dusk where the
	# camera is pointing. Seamless, infinitely far, and free.
	for name_of in ["Key", "WorldKey", "WorldFill", "WorldWarm", "Rim",
			"ValleyBounce", "GroundWarm"]:
		var light := parent.get_node_or_null(name_of) as DirectionalLight3D
		if light != null:
			light.sky_mode = DirectionalLight3D.SKY_MODE_LIGHT_ONLY

	var sun := DirectionalLight3D.new()
	sun.name = "DuskSun"
	sun.sky_mode = DirectionalLight3D.SKY_MODE_SKY_ONLY
	sun.light_color = Color("#F2A97C" if name != "warm" else "#FF9A54")
	sun.light_energy = 1.15
	sun.shadow_enabled = false
	# Yaw is the sun's own bearing and pitch is minus its elevation: a
	# directional light points along local -Z, so the disk lands opposite the
	# forward vector.
	sun.rotation_degrees = Vector3(-3.5, 202.0, 0.0)
	parent.add_child(sun)


static func to_ground_layer(node: Node) -> void:
	## Move the near ground onto its own visual layer.
	if node is VisualInstance3D:
		(node as VisualInstance3D).layers = GROUND_LAYER
	for child in node.get_children():
		to_ground_layer(child)


static func world_extras(world: Node3D, palette, name: String) -> void:
	## Scenic volumes beyond the massif: a visible dusk band and settlement.
	if name != "valley":
		return
	_push_near_range(world)
	_ridge_line(world, palette)
	_settlement(world, palette)
	# `course_world`'s warm horizon is nine lit slabs at radius 880. Raised
	# until they cleared the far range they read as exactly what they are -
	# rounded-rectangle billboards with visible seams between them, brighter
	# than the finish arena. A horizon is infinite and a slab is not, so the
	# warmth moved into the sky material and its sun (`tune_lights`), and
	# these are switched off rather than retuned.
	var band := world.get_node_or_null("DuskBand")
	if band != null:
		band.visible = false
	# The cloud banks go with it, and for the same reason. Fourteen
	# 190x13x26 boxes at radius 430 to 670 are seen almost edge-on from a
	# camera pitched fifteen degrees down, so each one renders as a thin
	# plate with a razor-straight top edge hanging in the sky. Cropping the
	# top of the hero frame and enlarging it, those plates - not the ranges,
	# and not the terrain - are every hard geometric edge above the skyline.
	# Depth fog with a height term does the same job with no silhouette.
	var clouds := world.get_node_or_null("Clouds")
	if clouds != null:
		clouds.visible = false
	for child in world.get_children():
		if str(child.name) in ["Settlement", "RidgeLine"]:
			_to_world_layer(child)


static func _push_near_range(world: Node3D) -> void:
	## Move `course_world`'s nearest ring out to where its facet count works.
	##
	## Those masses are authored at radius 206 to 330 with a base radius of
	## 46 and thirty facets. The hero camera stands at radius 175 on the
	## opposite bearing, which puts the closest of them barely forty units
	## behind the massif - and a thirty-facet mass at forty units is a set of
	## flat plates with straight edges across the top of the frame. They are
	## the only hard geometric edges in the committed hero frame.
	##
	## Pushed out by a third, the same silhouette subtends a quarter less and
	## its facets fall below the resolution that gives them away. Nothing is
	## re-modelled and nothing is deleted; `_ridge_line` then fills the band
	## they vacated with masses authored for that distance.
	var group := world.get_node_or_null("NearRange")
	if group == null:
		return
	for child in group.get_children():
		var node: Node3D = child
		node.position = Vector3(node.position.x * 1.36, node.position.y - 9.0,
			node.position.z * 1.36)


static func _ridge_line(world: Node3D, palette) -> void:
	## The near silhouette layer, authored for the distance it stands at.
	##
	## The frame needs one dark ridge between the mountainside the course is
	## on and the first lit range behind it - that read is what makes a gorge
	## a gorge rather than a hill with mountains behind it. Facet and tier
	## counts are half again what the distant ranges use, because this is the
	## only ring a camera ever sees from close enough to count them.
	var group := Node3D.new()
	group.name = "RidgeLine"
	world.add_child(group)
	var HeroWorld = load("res://assets/marble_machine/hero/hero_world.gd")
	# bearing, radius, height, base radius, seed
	# Heights sized against the *massif*, not against the other ranges. The
	# course sits on a flank whose crest reaches y 62 at 90 units out, and a
	# camera below that crest sees over it by barely a degree - so every one
	# of `course_world`'s three rings, authored to top out between y -28 and
	# y +48, has always been hidden behind the hill the course is on. That is
	# why the sky above the skyline is empty in every frame this branch
	# inherited. A ridge that reads has to stand taller than the hill in
	# front of it.
	# Two numbers do all the work, and both were arrived at by measurement.
	#
	# *Height* sets where the crest lands in frame. The hero lens is solved
	# to fit the course with a 9% margin, which leaves only a few degrees of
	# sky above the massif - so a ridge whose top reaches the camera's own
	# elevation sits exactly on the frame's top edge and there is no sky at
	# all. Three degrees below it is the whole usable range.
	#
	# *Base radius* sets whether the ring reads as peaks or as a wall. At 72
	# each mass subtends 22 degrees against an 18-degree spacing and the
	# eight of them merge into one silhouette; at 53 they subtend 16 and the
	# gaps between them are where the dusk shows through.
	var entries := [
		[132.0, 320.0, 137.0, 50.0, 173], [150.0, 304.0, 143.0, 53.0, 101],
		[168.0, 294.0, 146.0, 54.0, 113], [186.0, 288.0, 148.0, 54.0, 127],
		[204.0, 290.0, 146.0, 53.0, 139], [222.0, 298.0, 143.0, 52.0, 151],
		[240.0, 310.0, 139.0, 51.0, 163], [258.0, 328.0, 135.0, 50.0, 181],
	]
	for index in entries.size():
		var entry: Array = entries[index]
		var shade = palette.get_material(
			"rock_soft_near" if index % 3 else "slope_cliff")
		var node := Forms.mesh_node(
			HeroWorld.smooth_mass(float(entry[2]), float(entry[3]),
				int(entry[4]), 46, 23, 0.36),
			shade, "Ridge%d" % index, false)
		node.position = _polar(float(entry[0]), float(entry[1]), -86.0)
		node.rotation.y = float(entry[4]) * 0.37
		group.add_child(node)


static func _to_world_layer(node: Node) -> void:
	if node is VisualInstance3D:
		(node as VisualInstance3D).layers = WORLD_LAYER
	for child in node.get_children():
		_to_world_layer(child)


static func _polar(bearing: float, radius: float, y: float) -> Vector3:
	var angle := deg_to_rad(bearing)
	return Vector3(sin(angle) * radius, y, cos(angle) * radius)



static func _settlement(world: Node3D, palette) -> void:
	## Lit habitation on the near crests and down in the valley.
	##
	## `course_world.STRUCTURES` stands at radius 320 with its roofline near
	## y -6, and the near range in front of it reaches y +40; so it has never
	## once been visible. These clusters sit on the *near* range's own flanks,
	## on the camera side of each mass, which is the only band of distance
	## this course's cameras all see.
	var group := Node3D.new()
	world.add_child(group)
	group.name = "Settlement"
	var shell = palette.get_material("far_structure")
	var lit = palette.get_material("lit_far_window_hero")
	var ember = palette.get_material("lit_valley_hero")

	# bearing, radius, y, blocks. Bearings kept inside the arc the hero and
	# section cameras look along, so nothing is built where nothing looks.
	var clusters := [
		[172.0, 188.0, -2.0, 4], [192.0, 176.0, 6.0, 5],
		[210.0, 182.0, 2.0, 5], [228.0, 192.0, -4.0, 4],
		[246.0, 206.0, -10.0, 3], [160.0, 214.0, -14.0, 3],
	]
	for index in clusters.size():
		var entry: Array = clusters[index]
		var origin := _polar(float(entry[0]), float(entry[1]),
			float(entry[2]))
		var cluster := Node3D.new()
		cluster.name = "Town%d" % index
		cluster.position = origin
		cluster.rotation.y = deg_to_rad(-float(entry[0]))
		group.add_child(cluster)
		for block in int(entry[3]):
			var t := float(block) - float(int(entry[3])) * 0.5
			var height: float = 7.0 + 3.4 * float((block + index) % 3)
			var width: float = 4.4 + 1.2 * float(block % 2)
			var body := Forms.mesh_node(
				Geometry.rounded_box(Vector3(width, height, width * 0.8),
					width * 0.14, 2), shell, "Block%d" % block, false)
			body.position = Vector3(t * 7.2, height * 0.5 - 1.5,
				2.2 * float((block % 3) - 1))
			cluster.add_child(body)
			var band := Forms.mesh_node(
				Geometry.rounded_box(Vector3(width * 1.04, 1.5,
					width * 0.84), 0.4, 2), lit, "Lit%d" % block, false)
			band.position = body.position + Vector3(0.0, height * 0.22, 0.0)
			cluster.add_child(band)
		# One ember at the foot of each cluster: the warm point-source that
		# says the settlement is inhabited rather than modelled.
		var pool := Forms.mesh_node(
			Geometry.rounded_box(Vector3(13.0, 1.1, 7.0), 3.0, 2),
			ember, "Ember", false)
		pool.position = Vector3(0.0, -2.2, 4.0)
		cluster.add_child(pool)



static func _finish(palette, name: String) -> void:
	match name:
		"base":
			return
		"gold":
			palette.override("lit_gold_wash",
				palette.make_emissive("#FFC062", 2.4, 0.36))
			palette.override("lit_gold_line",
				palette.make_emissive("#FFD98C", 8.0, 0.24))
			# `sign_face` is deliberately NOT touched here. It reads as the
			# finish arena's sign and it is not: `course_finish` lights its
			# own face with `lit_gold_wash`, and the only user of
			# `sign_face` in the whole course is the START gantry
			# (`course_modules.start`). Warming it turned the start sign
			# gold, which inverts the one thing the zone story is for.
			# The checker is two moulded tiles rather than a texture, so its
			# contrast is a material decision. Under a gold wash the shipped
			# pair converge; the light tile goes warmer and the dark one goes
			# nearly black so the motif survives the wash.
			palette.override("checker_light",
				palette.make_moulded("#EDE2CB", 0.22, 0.88, 0.055))
			palette.override("checker_dark",
				palette.make_moulded("#0D1014", 0.34, 0.58, 0.13))
			palette.override("pearl_warm",
				palette.make_moulded("#D6CDB8", 0.31, 0.70, 0.08))
			palette.override("pearl_warm_shade",
				palette.make_moulded("#ADA189", 0.38, 0.44, 0.15))
		"contrast":
			palette.override("lit_gold_wash",
				palette.make_emissive("#FFC569", 2.0, 0.40))
			palette.override("lit_gold_line",
				palette.make_emissive("#FFD98C", 8.0, 0.24))
			palette.override("checker_light",
				palette.make_moulded("#E6E7E2", 0.22, 0.88, 0.055))
			palette.override("checker_dark",
				palette.make_moulded("#0D1014", 0.34, 0.58, 0.13))
			palette.override("pearl_warm",
				palette.make_moulded("#D8DAD6", 0.28, 0.80, 0.06))
			palette.override("pearl_warm_shade",
				palette.make_moulded("#A8ADAE", 0.36, 0.50, 0.13))
		_:
			push_error("course_style: unknown finish '%s'" % name)


# --- A: the palette, as a document -----------------------------------------
#
# The named swatches the brief asks for, grouped by the zone each one serves
# and in the order a viewer meets them travelling the course. This table is
# what `--dump-style` writes and what the swatch sheet draws, so the sheet
# cannot drift from what the renderer actually used: both read the resolved
# material out of the live palette rather than a hex quoted twice.

const SWATCHES := [
	["START ZONE", [
		["start shell", "pearl_shell"],
		["start lip", "pearl_lip_v2"],
		["start rail", "acrylic_guard"],
		["start edge light", "lit_cyan_line_hero"],
		["start practical", "lit_cyan"],
	]],
	["UPPER TRACK", [
		["channel shell", "pearl_shell"],
		["running surface", "running_polished"],
		["keel / underside", "keel_graphite"],
		["lip bead", "chrome"],
		["edge light", "lit_cyan_line_hero"],
	]],
	["BOWL / MIX ZONE", [
		["dish", "dish_polished"],
		["bowl wall", "acrylic_bowl"],
		["mixer shell", "pearl_shade"],
		["mixer light", "neon_violet_hero"],
		["mixer ring", "lit_violet_ring_hero"],
	]],
	["MID SUPPORTS", [
		["pier stock", "strut"],
		["tie / diagonal", "strut_deep"],
		["bearing cap", "strut_accent"],
		["rib strap", "graphite_soft"],
		["rib block", "gold"],
	]],
	["SPLIT - BLUE ROUTE", [
		["blue shell", "blue_machine"],
		["blue running", "running_blue"],
		["blue rail", "acrylic_blue"],
		["blue edge light", "neon_blue"],
	]],
	["SPLIT - ORANGE ROUTE", [
		["orange shell", "orange_machine"],
		["orange running", "running_orange"],
		["orange rail", "acrylic_amber"],
		["orange edge light", "lit_orange_line"],
	]],
	["FINISH ZONE", [
		["arena shell", "pearl_warm"],
		["arena running", "running_warm"],
		["gold wash", "lit_gold_wash"],
		["gold line", "lit_gold_line"],
		["checker light", "checker_light"],
		["checker dark", "checker_dark"],
		["finish hardware", "gold_dark"],
	]],
	["ENVIRONMENT ROCK", [
		["cliff face", "slope_cliff"],
		["flank", "slope_rock"],
		["shelf", "slope_earth"],
		["crest cap", "slope_cap"],
		["boulder", "slope_boulder"],
		["scrub", "scrub_dark"],
	]],
	["DISTANCE", [
		["near range", "rock_soft_near"],
		["mid range", "rock_soft_mid"],
		["far range", "rock_soft_far"],
		["haze bank", "cloud_bank"],
		["far structure", "far_structure"],
	]],
	["ACCENT + WARM LIGHT", [
		["cyan accent", "lit_cyan_line_hero"],
		["violet accent", "neon_violet_hero"],
		["orange accent", "lit_orange_line"],
		["gold accent", "lit_gold_line"],
		["dusk band", "lit_dusk_band"],
		["valley ember", "lit_valley_hero"],
		["far window", "lit_far_window_hero"],
	]],
]


static func dump(palette, opts: Dictionary) -> Dictionary:
	## Every swatch, resolved through the live palette.
	var groups: Array = []
	for entry in SWATCHES:
		var swatches: Array = []
		for pair in entry[1]:
			var key := str((pair as Array)[1])
			var material: StandardMaterial3D = palette.get_material(key)
			var albedo := material.albedo_color
			var record := {
				"name": str((pair as Array)[0]),
				"key": key,
				"albedo": "#%02X%02X%02X" % [
					int(round(albedo.r8)), int(round(albedo.g8)),
					int(round(albedo.b8))],
				"alpha": snappedf(albedo.a, 0.001),
				"roughness": snappedf(material.roughness, 0.001),
				"metallic": snappedf(material.metallic, 0.001),
			}
			if material.clearcoat_enabled:
				record["clearcoat"] = snappedf(material.clearcoat, 0.001)
			if material.emission_enabled:
				var emission := material.emission
				record["emission"] = "#%02X%02X%02X" % [
					int(round(emission.r8)), int(round(emission.g8)),
					int(round(emission.b8))]
				record["emission_energy"] = snappedf(
					material.emission_energy_multiplier, 0.01)
			if material.transparency != BaseMaterial3D.TRANSPARENCY_DISABLED:
				record["transparent"] = true
				record["rim"] = snappedf(material.rim, 0.001)
			swatches.append(record)
		groups.append({"zone": str(entry[0]), "swatches": swatches})
	var marbles: Array = []
	for index in 8:
		marbles.append("#%02X%02X%02X" % [
			int(round(palette.marble(index).albedo_color.r8)),
			int(round(palette.marble(index).albedo_color.g8)),
			int(round(palette.marble(index).albedo_color.b8))])
	return {"style": opts, "groups": groups, "field": marbles}
