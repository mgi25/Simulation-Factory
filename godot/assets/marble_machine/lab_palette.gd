extends RefCounted

## The visual lab's material language: one palette, quoted in hex, shared by
## every authored module.
##
## A fourth palette in this project, and the first written for a machine that
## was *designed* rather than inferred from a course. It keeps the three rules
## the toy style-lock measured its way to, because those were correct and the
## thing that failed was elsewhere:
##
## **Nothing painted is metallic.** Metallic trades diffuse for environment
## reflection, and a machine photographed against a dark backdrop has almost
## no environment to reflect. Moulded surfaces are `metallic 0.0` and buy
## their gloss from `clearcoat`, a dielectric second lobe that costs no
## albedo. Metal is spent only where the eye should read metal: hardware,
## rims, hubs. Small, and on purpose.
##
## **Every neutral is tinted.** An achromatic grey is what untextured default
## albedo looks like. Pearl runs warm, silver runs cool, graphite runs blue.
##
## **Warmth is structural.** Collars, joints, fascias, hub housings and the
## whole finale zone are warm in every variant. A frame whose only warm pixels
## are marbles reads as a laboratory.
##
## ## What is new here
##
## Colours are written as `Color("#RRGGBB")` and never as floats. GDScript
## colour floats are sRGB, so `0.605` is not "sixty per cent bright" - it is
## linear 0.31, a shade under a grey card, and reading those floats as
## brightness is what turned an earlier machine grey. A hex string is the
## value that will actually be displayed, so the mistake cannot recur.
##
## ## The three art variants
##
## `tower`, `deck` and `spine` are not palette swaps. They change support
## design, proportion, trim language and detail density; the palette shifts
## with them only where the structure demands it. Selected at build time so
## one scene, one camera and one lighting rig produce all three.

const VARIANT_TOWER := "tower"
const VARIANT_DECK := "deck"
const VARIANT_SPINE := "spine"
const VARIANTS := [VARIANT_TOWER, VARIANT_DECK, VARIANT_SPINE]


# --- the palette, as displayed --------------------------------------------
#
# Primary: the moulded body of the machine.
const PEARL_LIP := "#F7F4EE"      # brightest edge: rim caps, top lips
const PEARL_TRACK := "#F2F1EC"    # running surfaces
const PEARL_SHELL := "#E8E6E0"    # module shells, housings
const PEARL_SHADE := "#CBC9C3"    # shell undersides, inner returns
const SILVER := "#C8CED5"         # cool trim, guard frames
const SILVER_DEEP := "#8E979F"    # recessed silver, section breaks

# Structure: dark, blue-leaning, never black.
const GRAPHITE := "#2A2E35"       # columns, brace stock
const GRAPHITE_DEEP := "#191C22"  # keels, undersides, chassis
const GRAPHITE_SOFT := "#3A3F48"  # lit faces of structure, deck plates

# Secondary: the transparent language.
const ACRYLIC_AQUA := "#7FE0E8"   # guards, canopies, bowl wall
const ACRYLIC_CLEAR := "#CFEDF2"  # near-clear panels, sign faces
const CHROME := "#C3C9D1"         # true metal, small

# Accent: localised, and each with a job.
const CYAN := "#54E6F7"           # start zone, edge strips
const VIOLET := "#9B6BFF"         # mixer zone
const ORANGE := "#F0813A"         # machinery, moving parts
const GOLD := "#E4AC3C"           # hardware, collars, finale
const GOLD_LIGHT := "#F3CE86"     # gold highlight, glow cores

# The field. Eight candy hues, separated by hue *and* by value so that no two
# collide when they touch - which, in a bowl, they always do.
const MARBLE_COLOURS := [
	"#E02532",  # candy red
	"#2062DE",  # cobalt
	"#18A94E",  # emerald
	"#F5C518",  # warm yellow
	"#F2701F",  # orange
	"#8E3FD4",  # purple
	"#18C6C6",  # turquoise
	"#F0559B",  # pink
]

var _cache: Dictionary = {}
var variant: String = VARIANT_TOWER


func _init(art_variant: String = VARIANT_TOWER) -> void:
	variant = art_variant if art_variant in VARIANTS else VARIANT_TOWER


# --- builders -------------------------------------------------------------

func _moulded(hex: String, roughness: float, clearcoat: float,
		clearcoat_roughness := 0.06) -> StandardMaterial3D:
	## A painted, moulded surface. Never metallic; gloss from clearcoat.
	var material := StandardMaterial3D.new()
	material.albedo_color = Color(hex)
	material.metallic = 0.0
	material.roughness = roughness
	material.clearcoat_enabled = true
	material.clearcoat = clearcoat
	material.clearcoat_roughness = clearcoat_roughness
	return material

func _matte(hex: String, roughness: float) -> StandardMaterial3D:
	## Unpainted, unlacquered surface: rock, cloud, far terrain.
	##
	## No clearcoat. A cliff with a gloss lobe on it picks up the key as a
	## sheen and immediately reads as wet plastic at distance, which is the
	## fastest way to lose a background's believability.
	var material := StandardMaterial3D.new()
	material.albedo_color = Color(hex)
	material.metallic = 0.0
	material.roughness = roughness
	return material


func _metal(hex: String, roughness: float, specular := 0.6) -> StandardMaterial3D:
	## Real metal, for hardware only.
	var material := StandardMaterial3D.new()
	material.albedo_color = Color(hex)
	material.metallic = 1.0
	material.metallic_specular = specular
	material.roughness = roughness
	return material


func _acrylic(hex: String, alpha: float, roughness := 0.04) -> StandardMaterial3D:
	## A cast transparent guard: thick, tinted, glossy, lit from both sides.
	##
	## `cull_mode` is disabled because a guard is a shell and the camera sees
	## its inside wall through its outside one; `backlight` is what stops the
	## far wall going black when the key is on the near one, and it is the
	## single value that separates cast acrylic from tinted glass.
	var material := StandardMaterial3D.new()
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	material.albedo_color = Color(hex, alpha)
	material.metallic = 0.0
	material.roughness = roughness
	material.clearcoat_enabled = true
	material.clearcoat = 1.0
	material.clearcoat_roughness = 0.02
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	material.backlight_enabled = true
	material.backlight = Color(hex).darkened(0.55)
	material.rim_enabled = true
	material.rim = 0.9
	material.rim_tint = 0.3
	return material


func _acrylic_soft(hex: String, alpha: float, rim: float) -> StandardMaterial3D:
	## Cast acrylic without the frosted edge: for large guards and shells.
	##
	## The stock `_acrylic` rim term is a face-on brightening, which sells a
	## small canopy and turns a large wall into frosted milk. These carry the
	## cast-plastic read on wall thickness and backlight instead.
	var material := _acrylic(hex, alpha, 0.03)
	material.rim = rim
	material.rim_tint = 0.15
	material.backlight = Color(hex).darkened(0.7)
	return material


func _emissive(hex: String, energy: float, albedo_darken := 0.0) -> StandardMaterial3D:
	## A lit strip or lamp face. Emission carries it; albedo stays low so the
	## surface does not also fake a diffuse response it is not receiving.
	var material := StandardMaterial3D.new()
	material.albedo_color = Color(hex).darkened(albedo_darken)
	material.metallic = 0.0
	material.roughness = 0.35
	material.emission_enabled = true
	material.emission = Color(hex)
	material.emission_energy_multiplier = energy
	material.shading_mode = BaseMaterial3D.SHADING_MODE_PER_PIXEL
	return material


func _veil(hex: String, alpha: float) -> StandardMaterial3D:
	## A layer of haze, as translucent geometry rather than as opaque cloud.
	##
	## The first environment banked its distance with opaque slabs, and an
	## opaque mass at four hundred units is another range, not a veil in front
	## of one - so the cloud banks read as slate shapes hanging in the sky. A
	## low alpha with no cull and no depth write lets the range behind show
	## through at exactly the strength the alpha says, which is what stacks
	## distance into layers rather than into silhouettes.
	var material := StandardMaterial3D.new()
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	material.albedo_color = Color(hex, alpha)
	material.metallic = 0.0
	material.roughness = 0.99
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	material.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_DISABLED
	material.backlight_enabled = true
	material.backlight = Color(hex).lightened(0.18)
	return material

# --- the named surfaces ---------------------------------------------------

func get_material(key: String) -> StandardMaterial3D:
	if _cache.has(key):
		return _cache[key]
	var material := _build(key)
	_cache[key] = material
	return material


func _build(key: String) -> StandardMaterial3D:
	match key:
		# Moulded body.
		"pearl_lip":
			return _moulded(PEARL_LIP, 0.16, 1.0, 0.03)
		"pearl_track":
			return _moulded(PEARL_TRACK, 0.19, 0.95, 0.04)
		"pearl_shell":
			return _moulded(PEARL_SHELL, 0.26, 0.8, 0.07)
		"pearl_shade":
			return _moulded(PEARL_SHADE, 0.34, 0.55, 0.12)
		"silver":
			return _moulded(SILVER, 0.24, 0.85, 0.05)
		"track_silver":
			return _moulded("#D2D8DE", 0.20, 0.95, 0.04)
		"silver_deep":
			return _moulded(SILVER_DEEP, 0.38, 0.5, 0.12)

		# Structure.
		"graphite":
			return _moulded(GRAPHITE, 0.42, 0.45, 0.14)
		"graphite_deep":
			return _moulded(GRAPHITE_DEEP, 0.52, 0.3, 0.2)
		"graphite_soft":
			return _moulded(GRAPHITE_SOFT, 0.38, 0.5, 0.12)

		# Metal hardware.
		"chrome":
			return _metal(CHROME, 0.14, 0.75)
		"gold":
			return _metal(GOLD, 0.17, 0.85)
		"gold_bright":
			return _metal(GOLD_LIGHT, 0.16, 0.8)
		"orange_machine":
			return _moulded(ORANGE, 0.28, 0.9, 0.05)

		# Transparent.
		"acrylic_aqua":
			return _acrylic(ACRYLIC_AQUA, 0.125)
		"acrylic_aqua_deep":
			return _acrylic(ACRYLIC_AQUA, 0.26)
		"acrylic_clear":
			return _acrylic(ACRYLIC_CLEAR, 0.13)
		# V2 guards. The stock acrylic carries a strong rim term, which reads
		# as frosting when a wall is large and seen face on - beautiful on a
		# small canopy, milk on a bowl. These two drop the rim and lean on
		# thickness and backlight for the cast-plastic read instead.
		"acrylic_guard":
			return _acrylic_soft(ACRYLIC_AQUA, 0.115, 0.30)
		"acrylic_bowl":
			return _acrylic_soft(ACRYLIC_AQUA, 0.175, 0.38)

		# Lit.
		"lit_cyan":
			return _emissive(CYAN, 3.4, 0.45)
		"neon_cyan":
			return _emissive(CYAN, 8.5, 0.22)
		"neon_violet":
			return _emissive(VIOLET, 8.0, 0.22)
		"neon_orange":
			return _emissive(ORANGE, 9.0, 0.20)
		"neon_gold":
			return _emissive(GOLD_LIGHT, 4.5, 0.25)
		"lit_cyan_soft":
			return _emissive(CYAN, 0.85, 0.62)
		"lit_violet":
			return _emissive(VIOLET, 2.8, 0.45)
		"lit_orange":
			return _emissive(ORANGE, 2.6, 0.4)
		"lit_gold":
			return _emissive(GOLD_LIGHT, 3.0, 0.35)
		"lit_white":
			return _emissive("#EAF7FF", 2.2, 0.4)
		"lit_sign":
			return _emissive(CYAN, 1.15, 0.30)
		"lit_window":
			return _emissive("#FFD9A0", 1.4, 0.6)

		# Backdrop.
		"backdrop_near":
			return _moulded("#1E242C", 0.85, 0.0)
		"backdrop_mid":
			return _moulded("#191F27", 0.9, 0.0)
		"backdrop_far":
			return _moulded("#151A22", 0.95, 0.0)

		# V2 environment. Rock is matte, blue-leaning and *lit* - the cliff
		# gorge only reads as depth if each layer is a different value, so
		# the three are separated by lightness rather than by fog alone.
		"rock_near":
			return _matte("#121821", 0.94)
		"rock_mid":
			return _matte("#1D2B3A", 0.95)
		"rock_far":
			return _matte("#2C4055", 0.96)
		"rock_ledge":
			return _matte("#10161D", 0.92)
		"cloud_bank":
			return _matte("#26405A", 0.98)
		"lit_valley":
			return _emissive("#FF9C4A", 4.0, 0.30)
		# Read through three hundred units of haze, so its energy is set for
		# what survives rather than for what it emits.
		"lit_horizon":
			return _emissive("#C87F4C", 2.0, 0.42)
		"lit_horizon_cool":
			return _emissive("#5A87A8", 1.5, 0.42)
		"lit_far_window":
			return _emissive("#FFCE93", 2.6, 0.30)
		"lit_cyan_line":
			return _emissive(CYAN, 8.5, 0.28)
		"lit_violet_ring":
			return _emissive(VIOLET, 7.5, 0.28)
		"track_floor":
			return _moulded("#C6CDD5", 0.24, 0.9, 0.05)
		# V2 only. The two keys above are what the earlier visual lab renders
		# with, so its committed proofs stay reproducible; these carry the
		# tuning this branch needed without reaching back into them.
		"pearl_lip_v2":
			# A broader, dimmer clearcoat lobe: the start pod's top lip was the
			# one surface in the frame that clipped.
			return _moulded(PEARL_LIP, 0.21, 0.85, 0.06)
		"track_floor_v2":
			# Darker than the shell it sits inside, which is the whole point of
			# having a separate running surface at all.
			return _moulded("#AEB8C3", 0.26, 0.9, 0.05)
		# V2.2 running surfaces. Part metal rather than painted: a dielectric
		# gloss returns one bright specular and stays whatever value its
		# albedo is, which is how both the track floor and the bowl dish kept
		# reading as white paint. A partly metallic surface trades diffuse for
		# reflection, so it darkens where it sees nothing and flares where it
		# sees a light - which is what "polished" actually looks like, and it
		# is what makes a candy-coloured racer pop off it.
		"running_polished":
			var track_metal := _moulded("#AEBAC6", 0.17, 1.0, 0.03)
			track_metal.metallic = 0.55
			track_metal.metallic_specular = 0.7
			return track_metal
		"dish_polished":
			var dish_metal := _moulded("#7D8A99", 0.20, 1.0, 0.04)
			dish_metal.metallic = 0.62
			dish_metal.metallic_specular = 0.65
			return dish_metal
		"pan_polished":
			# The collector's floor. Half the metallic of the bowl's dish: a
			# pan seen almost from above reflects mostly sky, and at 0.62
			# metallic that made it a dark blue mirror with white bars lying
			# on it instead of a silver surface with a rotor over it.
			var pan_metal := _moulded("#8E9AA8", 0.20, 1.0, 0.04)
			pan_metal.metallic = 0.32
			pan_metal.metallic_specular = 0.68
			return pan_metal
		"dish_floor":
			# Rougher and far less lacquered than a track floor. A bowl is a
			# wide smooth surface facing the key, and a clearcoat lobe on it
			# returns one enormous blown highlight that erases the dish. The
			# broad, dim specular of a rougher surface keeps the curvature.
			return _moulded("#B0BAC6", 0.44, 0.28, 0.22)
		"sign_face":
			return _emissive(CYAN, 0.62, 0.34)
		"pearl_soft":
			return _moulded("#DFDDD7", 0.30, 0.7, 0.09)

		# --- HERO retunes of shared keys ----------------------------------
		#
		# Seven surfaces the hero build wanted at a different setting from
		# the one the V2 lab shipped with. They live here as `_hero` keys
		# rather than as edits to the originals, because the earlier lab's
		# committed proofs have to keep reproducing from any later branch -
		# the same rule the `_v2` keys above were added under.
		"lit_cyan_line_hero":
			return _emissive(CYAN, 10.0, 0.24)
		"neon_violet_hero":
			return _emissive(VIOLET, 10.0, 0.20)
		"lit_violet_ring_hero":
			return _emissive(VIOLET, 9.5, 0.24)
		"rock_ledge_hero":
			return _matte("#080C12", 0.94)
		"lit_valley_hero":
			return _emissive("#FF9C4A", 6.5, 0.24)
		"lit_far_window_hero":
			return _emissive("#FFCE93", 1.9, 0.36)
		"lit_horizon_cool_hero":
			return _emissive("#5A87A8", 1.6, 0.42)

		# --- HERO build ---------------------------------------------------
		#
		# Additive only, like the `_v2` keys above: everything the seven-stage
		# machine needs that the three-module slice never had. The zone story
		# runs cyan at the top, violet through the mixer, silver and graphite
		# through the middle, cyan *against* orange at the choice, and gold at
		# the bottom - so the frame has a temperature gradient down its own
		# height rather than one colour repeated seven times.
		"pearl_warm":
			# The finale's shell. The same moulding, half a step warmer, so
			# the bottom of the tower is made of the same product as the top
			# and still reads as being lit by something golden.
			return _moulded("#F2ECDF", 0.22, 0.9, 0.05)
		"pearl_warm_shade":
			return _moulded("#D2C8B4", 0.34, 0.55, 0.12)
		"running_warm":
			# The finish arena's floor: the polished running surface, pushed
			# warm and darkened, so gold hardware reads against it.
			var warm_run := _moulded("#9C8F76", 0.19, 1.0, 0.03)
			warm_run.metallic = 0.55
			warm_run.metallic_specular = 0.7
			return warm_run
		# The two branch identities. Painted bodies, not tints on pearl: the
		# split has to be readable as a *decision* at phone size, and two
		# shells that differ only in their edge lights are not.
		"blue_machine":
			return _moulded("#2E8FD8", 0.24, 0.95, 0.04)
		"blue_deep":
			return _moulded("#1C5C93", 0.32, 0.7, 0.08)
		"orange_deep":
			return _moulded("#B8500F", 0.32, 0.7, 0.08)
		"running_blue":
			var blue_run := _moulded("#9FC8E4", 0.18, 1.0, 0.03)
			blue_run.metallic = 0.5
			blue_run.metallic_specular = 0.7
			return blue_run
		"running_orange":
			var orange_run := _moulded("#D9B49A", 0.18, 1.0, 0.03)
			orange_run.metallic = 0.5
			orange_run.metallic_specular = 0.7
			return orange_run
		"acrylic_blue":
			return _acrylic_soft("#63B8F0", 0.135, 0.32)
		"acrylic_amber":
			return _acrylic_soft("#F0A659", 0.135, 0.32)
		"acrylic_gold":
			return _acrylic_soft("#F2CE7E", 0.14, 0.34)
		"neon_blue":
			return _emissive("#3FA8FF", 8.5, 0.22)
		"lit_blue":
			return _emissive("#3FA8FF", 2.8, 0.42)
		"lit_orange_line":
			return _emissive(ORANGE, 8.0, 0.26)
		"lit_gold_line":
			return _emissive(GOLD_LIGHT, 7.0, 0.26)
		"lit_gold_wash":
			# The finale's own practical, as a surface. Lower energy than a
			# neon line because it is read over a large area, and a large
			# area at line energy is a blown patch.
			return _emissive("#FFC868", 1.5, 0.44)
		"gold_dark":
			return _metal("#A97C23", 0.24, 0.8)
		# The finish floor motif. Two moulded tiles rather than a texture: at
		# this scale a checker is geometry, and geometry keeps its contrast
		# when the whole arena is under a warm wash.
		"checker_light":
			return _moulded("#DED8CA", 0.24, 0.85, 0.06)
		"checker_dark":
			return _moulded("#14171C", 0.36, 0.55, 0.14)
		# Environment, second pass. Rock that is smooth-shaded and lower in
		# contrast than the V2 set, because the faceted blocks were reading as
		# primitives rather than as distance.
		"rock_soft_near":
			return _matte("#141C27", 0.96)
		"rock_soft_mid":
			return _matte("#243449", 0.96)
		"rock_soft_far":
			return _matte("#3B5471", 0.97)
		"far_structure":
			# Distant architecture, one value above the rock it stands on.
			# In the layer's own colour a building at two hundred units is
			# indistinguishable from the crest behind it, and the whole point
			# of putting one there is that it reads as built rather than
			# geological.
			return _matte("#44566C", 0.95)
		"rock_soft_haze":
			return _matte("#4E6C88", 0.98)
		"lit_dusk_band":
			return _emissive("#D89A63", 1.9, 0.42)

		# --- SLOPED COURSE ------------------------------------------------
		#
		# Additive, like every block above it. The near ground of the sloped
		# course is a heightfield rather than a backdrop ring, which is a
		# different job from anything the tower needed: it is *under* the
		# subject, it fills a third of the frame, and it has to carry a
		# readable landform at ten units as well as at two hundred.
		#
		# So the four values are separated by warmth as much as by lightness.
		# A mountainside where every plane is the same blue-grey reads as one
		# extruded mass however well it is modelled; a warm shelf against a
		# cool cliff face reads as two kinds of ground. The warm ones are also
		# where the course's own supports land, so the frame's warmest large
		# area sits directly under its whitest object.
		"slope_cliff":
			return _matte("#1C242D", 0.95)
		"slope_rock":
			return _matte("#232B34", 0.94)
		"slope_earth":
			return _matte("#33394A", 0.93)
		"slope_scree":
			return _matte("#2C3646", 0.94)
		"slope_moss":
			return _matte("#2A3830", 0.95)
		"slope_cap":
			return _matte("#28323D", 0.94)
		# Scattered cover. Both darker than any ground value, because a bush
		# or a boulder is a shadow at every distance this course is read at,
		# and anything lighter reads as debris lying on the hill.
		"scrub_dark":
			return _matte("#1B2A22", 0.96)
		"scrub_dry":
			return _matte("#2A2A20", 0.95)
		"slope_boulder":
			return _matte("#212A36", 0.94)

		# --- PRESENTATION POLISH ------------------------------------------
		#
		# Additive, like every block above it, and for the same reason: the
		# sloped course's committed proofs render from the keys above and have
		# to keep rendering from them. Nothing here is an edit; every key is a
		# `_polish` sibling that `course_machine` and `course_dressing` opt
		# into.
		#
		# ## The running surface was never the problem. The lobe was.
		#
		# `running_polished` is a bright albedo under a clearcoat of roughness
		# 0.03. A lobe that tight returns almost all of its energy into a
		# two-pixel band, and with the environment's glow threshold at 1.16
		# that band is over the knee down the whole length of a straight - so
		# a hundred units of channel came back as one white stripe with no
		# curvature in it. Widening the lobe and dropping the albedo half a
		# step is the whole fix: the same surface, the same metallic read, and
		# a highlight that falls off across the cradle instead of clipping.
		#
		# ## Pearl against silver, not white against white
		#
		# The shell and the running floor were separated in albedo already and
		# both were clipping, which erases any separation there is. Held below
		# the knee the pair reads as the two materials they are: a warm pearl
		# moulding with a cool silver insert laid in it.
		"shell_pearl_polish":
			return _moulded("#E4E0D6", 0.29, 0.72, 0.10)
		"shell_pearl_warm_polish":
			return _moulded("#EDE6D6", 0.26, 0.78, 0.09)
		"running_pearl_polish":
			var run_pearl := _moulded("#97A6B6", 0.23, 1.0, 0.09)
			run_pearl.metallic = 0.58
			run_pearl.metallic_specular = 0.72
			return run_pearl
		"running_warm_polish":
			var run_warm := _moulded("#8C806A", 0.23, 1.0, 0.09)
			run_warm.metallic = 0.56
			run_warm.metallic_specular = 0.72
			return run_warm
		"running_blue_polish":
			var run_blue := _moulded("#8AAFC9", 0.23, 1.0, 0.09)
			run_blue.metallic = 0.54
			run_blue.metallic_specular = 0.72
			return run_blue
		"running_orange_polish":
			var run_orange := _moulded("#C39C81", 0.23, 1.0, 0.09)
			run_orange.metallic = 0.54
			run_orange.metallic_specular = 0.72
			return run_orange

		# ## The guard has to be seen and not looked through
		#
		# At alpha 0.115 with the rim dropped to 0.30 the acrylic wall was
		# invisible in every section frame: a safety rail that cannot be seen
		# is not read as transparent, it is read as absent, and the channel
		# lost the one feature that says the run is enclosed. The fix is edge
		# light, not body density - a cast wall is visible because its top
		# arris catches the key - so the rim goes back up and the alpha only
		# moves a third of a step.
		#
		# ## How much of a racer a guard is actually in front of
		#
		# Measured against `v2_track`, because the intuition here is wrong and
		# it matters for every camera on the course. In profile units the
		# guard spans y 0.28 to 0.54 at |x| 1.03, and a 0.285 racer sitting in
		# the cradle has its centre at y 0.025 and its crown at y 0.31. So the
		# guard's top arris stands 0.23 ABOVE the top of a racer: the wall is
		# taller than the thing it is protecting, and a racer is never seen
		# over it from a side-on camera unless the camera is very high.
		#
		# Clear-over-the-near-guard elevation, by lane, side-on:
		#
		#     far lane      18.2 degrees
		#     centre lane   26.6 degrees
		#     near lane     46.4 degrees
		#
		# Every section camera on this course sits between 8 and 30 degrees,
		# so in practice a racer in the near half of the channel is always
		# seen THROUGH the acrylic and not over it. That is the whole reason
		# the alpha is a trade rather than a free improvement, and it is why
		# it stops at 0.150: at that value a racer behind one wall loses
		# about a seventh of its value and picks up a slight aqua cast, which
		# reads as glass in front of it. Anything heavier starts reading as
		# a racer painted the wrong colour.
		#
		# The consequence for the physics session is the useful one: the
		# guard must not get TALLER. At 0.26 it is already over the racer,
		# and every degree it grows is a degree of camera elevation the whole
		# shot list has to buy back.
		"acrylic_guard_polish":
			var guard := _acrylic_soft(ACRYLIC_AQUA, 0.150, 0.52)
			guard.rim_tint = 0.24
			guard.roughness = 0.025
			return guard
		"acrylic_violet_polish":
			var violet_guard := _acrylic_soft("#A9B8F0", 0.150, 0.52)
			violet_guard.rim_tint = 0.24
			violet_guard.roughness = 0.025
			return violet_guard
		"acrylic_blue_polish":
			var blue_guard := _acrylic_soft("#63B8F0", 0.150, 0.50)
			blue_guard.rim_tint = 0.24
			blue_guard.roughness = 0.025
			return blue_guard
		"acrylic_amber_polish":
			var amber_guard := _acrylic_soft("#F0A659", 0.150, 0.50)
			amber_guard.rim_tint = 0.24
			amber_guard.roughness = 0.025
			return amber_guard
		"acrylic_gold_polish":
			var gold_guard := _acrylic_soft("#F2CE7E", 0.155, 0.52)
			gold_guard.rim_tint = 0.24
			gold_guard.roughness = 0.025
			return gold_guard

		# ## Seven edge lights, one per zone, all below the bloom knee
		#
		# The hero keys run at energy 7 to 10, which is over the glow
		# threshold across the whole strip rather than at its core, so the
		# lines bloomed into the shell beside them and took the pearl with
		# them. At six the tube is still the brightest thing in its own
		# neighbourhood and the bloom stays a halo on it.
		#
		# The zone order is the journey, read along the course rather than
		# down a tower: cyan off the line, aqua through the first leg, a
		# neutral violet through the middle, full violet on the approach to
		# the choice, the two route identities at the choice, gold to the
		# flag. Seven hues over two hundred and thirty units means a frame's
		# edge lights say roughly how far through the race it is.
		"lit_cyan_line_polish":
			return _emissive(CYAN, 6.2, 0.26)
		"lit_aqua_line_polish":
			return _emissive("#7FE8E4", 6.0, 0.26)
		"lit_violet_cool_polish":
			return _emissive("#B4A8F5", 5.8, 0.26)
		"lit_violet_line_polish":
			return _emissive(VIOLET, 6.0, 0.24)
		"lit_blue_line_polish":
			return _emissive("#3FA8FF", 6.0, 0.24)
		"lit_orange_line_polish":
			return _emissive(ORANGE, 5.6, 0.28)
		"lit_gold_line_polish":
			return _emissive(GOLD_LIGHT, 5.4, 0.28)

		# --- environment: rock that has a silhouette ----------------------
		#
		# The ground values are deliberately NOT touched. Three nearly-equal
		# rock surfaces is what the sloped-course pass measured its way to,
		# because a band boundary on a heightfield is assigned per quad and a
		# value jump either side of it is a staircase at cell resolution - the
		# most visible edge on the mountain. Reintroducing separation in the
		# ground material would undo that finding.
		#
		# So the silhouette is bought with geometry instead. These are the
		# values for the crag masses and strata benches that stand on the
		# steep ground: one step darker than the flank they rise out of, and
		# one lit face value that catches the raking world key, so a crag has
		# a bright plane and a dark one rather than a single flat tone.
		# All three within a step of the flank they stand in, and one of them
		# LIGHTER than it. The first pass made them darker on the theory that
		# had held for boulders - "a boulder lighter than the hillside reads
		# as a sheet of paper lying on it" - and on a crag it inverts, for a
		# reason worth writing down: a boulder is sited on a shelf, which is
		# in shadow, and a crag is sited on a steep face, which is what the
		# key is raking. A value darker than a LIT plane is not a rock on it,
		# it is a hole in it, and the first crag pass came back as black
		# rectangles lying on the mountainside.
		#
		# So the value carries nothing and the form carries everything: a lit
		# plane a step above the flank, a body at the flank's own value, and
		# an underside a step below it. Which is what a rock outcrop is.
		# Within half a step of the flank, and that is the point. At #36434F
		# the lit face was a pale patch and the outcrops competed with the
		# track for attention; the form was already doing the work by then,
		# so the value only has to stay out of its way.
		"crag_shadow":
			return _matte("#1C2530", 0.95)
		"crag_rock":
			return _matte("#232C36", 0.94)
		"crag_face":
			return _matte("#2C3742", 0.93)
		# Vegetation as masses rather than as pebbles. `scrub_dark` is correct
		# for a bush read at ten units and vanishes at sixty; a canopy value
		# a step lighter and a shade greener is what makes a stand of scrub
		# read as cover on a hillside at a hundred.
		# Darker and less saturated than the first pass. At #24352B a stand
		# came back as a bright olive blob against cool rock - "subtle" is
		# the brief's own word for this, and a value that reads as a distinct
		# hue rather than as a dark mass is competing with the track. Cover
		# on a hillside at dusk is nearly black with a green bias, and the
		# bias is all that needs to survive.
		"foliage_canopy":
			return _matte("#1B2620", 0.95)
		"foliage_deep":
			return _matte("#121A16", 0.96)
		"foliage_dry":
			return _matte("#31301F", 0.95)
		# Layered haze. Three alphas at three distances: what turns the flat
		# grey wall behind the finish into air with depth in it.
		"haze_near_polish":
			return _veil("#5C6E86", 0.19)
		"haze_mid_polish":
			return _veil("#6E7F97", 0.24)
		"haze_far_polish":
			return _veil("#8695AC", 0.30)
		# Warm architecture. The concept's environment is inhabited and warm
		# behind its machine; ours had six cool slab towers at three hundred
		# units, which is too far to read as anything but crest. These are for
		# accents at sixty to a hundred and forty - close enough to have a
		# silhouette and far enough to stay subordinate to the race.
		"warm_structure":
			return _matte("#4A4034", 0.94)
		"warm_structure_deep":
			return _matte("#302921", 0.95)
		"lit_far_warm_polish":
			return _emissive("#FFB570", 2.4, 0.32)
		"lit_ridge_warm_polish":
			return _emissive("#FF9A52", 3.0, 0.30)
		"lit_valley_warm_polish":
			return _emissive("#FF8C3C", 5.0, 0.28)
		# The support family's plate value. A trestle built entirely from tube
		# stock reads as loose sticks whatever the stock radius is, because a
		# bundle of cylinders has no flat to catch a highlight. One plate
		# value against the tube graphite is what makes the same frame read
		# as fabricated.
		"graphite_plate_polish":
			return _moulded("#31373F", 0.40, 0.48, 0.13)
	push_error("lab_palette: unknown material key '%s'" % key)
	return _moulded("#FF00FF", 0.5, 0.0)


func marble(index: int) -> StandardMaterial3D:
	## One racer. Deep clearcoat over a saturated body: the candy read.
	var key := "marble_%d" % (index % MARBLE_COLOURS.size())
	if _cache.has(key):
		return _cache[key]
	var material := StandardMaterial3D.new()
	material.albedo_color = Color(MARBLE_COLOURS[index % MARBLE_COLOURS.size()])
	material.metallic = 0.0
	material.roughness = 0.08
	material.clearcoat_enabled = true
	material.clearcoat = 1.0
	material.clearcoat_roughness = 0.02
	material.rim_enabled = true
	material.rim = 0.22
	material.rim_tint = 0.85
	_cache[key] = material
	return material
