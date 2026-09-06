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
			return _acrylic_soft(ACRYLIC_AQUA, 0.095, 0.24)

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
			return _emissive("#FFB668", 11.0, 0.20)
		"lit_horizon_cool":
			return _emissive("#8FC4E8", 7.0, 0.25)
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
