extends RefCounted

## The premium-toy palette: bright moulded surfaces, warm hardware, candy marbles.
##
## A third palette beside `race_materials.gd` and `neon_materials.gd`, and the
## opposite of the second in almost every value. The neon palette's rules were
## "the track is light and the structure is dark", "nothing is emissive unless
## it is a light", "the picture has to survive with bloom off". Only the last
## of those survives here. The rest are replaced, because a measurement of
## what the neon direction actually renders says they are what makes it read
## as a factory.
##
## ## What the measurement said
##
## Three numbers decided this file, taken off the committed V1.1 heroes.
##
## **Warmth: 0.8-1.3% of frame against the concept reference's 18.8%.** Every
## warm pixel in a V1.1 frame is a marble. There is not one warm structural
## surface, warm bounce or warm practical in the machine. The concept sheet is
## 56% warm against 38% cool. A cyan-only palette over neutral grey is the
## Tron signature, and no amount of brightening escapes it.
##
## **Neutrality: 41-50% of lit pixels are achromatic** - channel spread under
## 10/255 - against the reference's 14.3%. Sampled deck values come back
## #A0A0A0, #989898, #686868: not silver, *untinted default albedo*. Every
## neutral in this file carries a tint, and the pearl family carries a warm
## one.
##
## **Value: `TRACK_TOP` renders as #9A9790.** Those GDScript floats are sRGB,
## so 0.605 is linear 0.310 - four fifths of a stop above an 18% grey card. A
## white toy plastic sits near linear 0.86. The track was a grey card. Every
## surface here is quoted with the hex it actually displays as, so that
## mistake cannot be made twice by reading the floats as brightness.
##
## ## The three rules that replace the neon ones
##
## **Nothing painted is metallic.** Metallic substitutes environment
## reflection for diffuse, and V1.1's environment is black - so a deck at
## metallic 0.28 threw away 28% of its light and got 1% back. Every moulded
## surface here is metallic 0.0 and buys its gloss from `clearcoat`, which is
## a dielectric second lobe and costs nothing in albedo. Metal is spent only
## where it is meant to read as metal: warm hardware, small and deliberate.
##
## **Every neutral is tinted, and the machine is warm-neutral.** Pearl,
## ivory, cream and silver-white all carry a channel spread; none is
## achromatic. That is the difference between "moulded composite" and
## "untextured default".
##
## **Warmth is structural, not decorative.** Hubs, clamps, brackets, joints,
## lamps and underlighting are warm in every variant, including the two whose
## primary accent is cool. A frame in which the only warm thing is a marble
## is the frame this file exists to stop.
##
## ## The three variants
##
## `a` pearl and aqua, `b` warm toy, `c` futuristic candy. Selected at render
## time by `--toy-variant`, so the comparison frames come out of one build of
## one scene from one replay and differ in the palette alone. The geometry,
## the camera, the lighting *rig* and the marbles are identical across all
## three: what changes is surface colour and accent, which is the only thing
## the comparison is asking about.
##
## Materials are cached by key and shared, as in the other two palettes.

const VARIANT_A := "a"
const VARIANT_B := "b"
const VARIANT_C := "c"
const VARIANTS := [VARIANT_A, VARIANT_B, VARIANT_C]

# --- the marbles ----------------------------------------------------------
#
# Shared across all three variants on purpose. The brief asks for candy red,
# cobalt, emerald, warm yellow, orange, purple, turquoise and pink; these are
# those, deepened and saturated past the simulation's own presentation colours
# so they hold their identity against a bright machine rather than a dark one.
#
# Every pair is separated by hue *and* by value, and the lowest saturation
# here is 0.72. The V1.1 field of sixteen contained three near-identical
# cyans at saturation 0.26; eight is the field this prototype is shot with
# and eight hues this far apart cannot collide.
const MARBLES: Array[Color] = [
	Color(0.906, 0.169, 0.220),   # candy red      #E72B38
	Color(0.129, 0.396, 0.898),   # cobalt blue    #2165E5
	Color(0.106, 0.757, 0.427),   # emerald green  #1BC16D
	Color(1.000, 0.749, 0.118),   # warm yellow    #FFBF1E
	Color(0.596, 0.243, 0.878),   # purple         #983EE0
	Color(1.000, 0.475, 0.098),   # orange         #FF7919
	Color(0.114, 0.831, 0.812),   # turquoise      #1DD4CF
	Color(1.000, 0.353, 0.647),   # pink           #FF5AA5
]

# --- the palettes ---------------------------------------------------------
#
# Every entry is quoted with the hex it displays as, because these floats are
# sRGB and reading them as brightness is exactly the mistake the neon palette
# made. Anything below about 0.75 here is a mid-tone, not a light one.

const PALETTES := {
	# A - Pearl + Aqua. The coolest of the three and still far warmer than
	# V1.1: pearl decks with a warm bias, aqua acrylic, cyan primary accent
	# and gold hardware carrying the warmth on its own.
	"a": {
		"track": Color(0.859, 0.839, 0.796),          # #DBD6CB pearl ivory
		"track_panel": Color(0.855, 0.835, 0.788),    # #DAD5C9
		"track_side": Color(0.741, 0.718, 0.667),     # #BDB7AA
		"shell": Color(0.643, 0.620, 0.573),          # #A49E92 moulded flank
		"structure": Color(0.180, 0.196, 0.235),      # #2E323C graphite
		"structure_lit": Color(0.267, 0.290, 0.341),  # #444A57
		"cradle": Color(0.137, 0.149, 0.180),         # #23262E
		"acrylic": Color(0.435, 0.898, 0.910),        # #6FE5E8 aqua
		"acrylic_rim": Color(0.804, 0.980, 1.000),    # #CDFAFF
		"bowl_surface": Color(0.898, 0.886, 0.855),   # #E5E2DA pearl basin
		"accent_cool": Color(0.310, 0.831, 0.914),    # #4FD4E9
		"accent_warm": Color(1.000, 0.698, 0.302),    # #FFB24D gold
		"hardware": Color(0.878, 0.678, 0.365),       # #E0AD5D warm metal
		"sky_top": Color(0.243, 0.298, 0.376),        # #3E4C60
		"sky_horizon": Color(0.400, 0.463, 0.541),    # #66768A
		"ground": Color(0.118, 0.133, 0.165),         # #1E222A
		"backdrop": Color(0.153, 0.180, 0.231),       # #272E3B
		"floor": Color(0.145, 0.161, 0.196),          # #252932
	},
	# B - Warm Toy. Cream decks, near-clear acrylic, and the machine's primary
	# accent is the warm one with blue kept as the secondary. The closest of
	# the three to the reference's own gold finish-arena warmth.
	"b": {
		"track": Color(0.886, 0.847, 0.776),          # #E2D8C6 cream
		"track_panel": Color(0.898, 0.851, 0.769),    # #E5D9C4
		"track_side": Color(0.784, 0.733, 0.647),     # #C8BBA5
		"shell": Color(0.678, 0.627, 0.549),          # #ADA08C
		"structure": Color(0.192, 0.184, 0.204),      # #312F34 warm graphite
		"structure_lit": Color(0.286, 0.271, 0.294),  # #49454B
		"cradle": Color(0.145, 0.137, 0.157),         # #252328
		"acrylic": Color(0.529, 0.878, 0.902),        # #87E0E6 light aqua
		"acrylic_rim": Color(0.949, 0.988, 1.000),    # #F2FCFF
		"bowl_surface": Color(0.910, 0.886, 0.839),   # #E8E2D6
		"accent_cool": Color(0.353, 0.659, 0.878),    # #5AA8E0 secondary
		"accent_warm": Color(1.000, 0.604, 0.235),    # #FF9A3C orange
		"hardware": Color(1.000, 0.788, 0.420),       # #FFC96B gold
		"sky_top": Color(0.239, 0.267, 0.337),        # #3D4456
		"sky_horizon": Color(0.427, 0.451, 0.514),    # #6D7383
		"ground": Color(0.106, 0.118, 0.145),         # #1B1E25
		"backdrop": Color(0.145, 0.165, 0.216),       # #252A37
		"floor": Color(0.133, 0.149, 0.188),          # #222630
	},
	# C - Futuristic Candy. Silver-white surfaces, aqua glass, violet and cyan
	# accents over warm yellow hardware. The most saturated of the three.
	"c": {
		"track": Color(0.871, 0.882, 0.898),          # #DEE1E5 silver-white
		"track_panel": Color(0.867, 0.882, 0.906),    # #DDE1E7
		"track_side": Color(0.741, 0.761, 0.800),     # #BDC2CC
		"shell": Color(0.616, 0.639, 0.690),          # #9DA3B0
		"structure": Color(0.169, 0.188, 0.235),      # #2B303C cool graphite
		"structure_lit": Color(0.251, 0.275, 0.333),  # #404655
		"cradle": Color(0.125, 0.141, 0.176),         # #20242D
		"acrylic": Color(0.400, 0.812, 0.925),        # #66CFEC aqua glass
		"acrylic_rim": Color(0.784, 0.961, 1.000),    # #C8F5FF
		"bowl_surface": Color(0.902, 0.914, 0.933),   # #E6E9EE
		"accent_cool": Color(0.275, 0.847, 0.961),    # #46D8F5 cyan
		"accent_violet": Color(0.604, 0.420, 1.000),  # #9A6BFF
		"accent_warm": Color(1.000, 0.824, 0.290),    # #FFD24A warm yellow
		"hardware": Color(0.949, 0.780, 0.396),       # #F2C765
		"sky_top": Color(0.239, 0.278, 0.376),        # #3D4760
		"sky_horizon": Color(0.396, 0.435, 0.545),    # #656F8B
		"ground": Color(0.114, 0.129, 0.169),         # #1D212B
		"backdrop": Color(0.145, 0.165, 0.231),       # #252A3B
		"floor": Color(0.141, 0.157, 0.204),          # #242834
	},
}

# --- emission strengths ---------------------------------------------------
#
# Every one of these is below the environment's glow threshold, and that is
# the point. The brief asks for a version with no bloom that is still
# attractive, so this palette is built to have nothing that *needs* bloom: a
# light ring reads because it is brighter than the pearl beside it, not
# because the post-process smears it. `--toy-no-glow` renders the same frame
# with glow off and the two should differ only in seasoning.
#
# The neon palette's two above-threshold entries produced, when the numbers
# were actually run, a 0.15% and a 0.30% additive halo - bloom that was
# claimed in a docstring and invisible in the frame. Nothing here pretends.
const EMISSION_RING := 1.05
const EMISSION_LAMP := 0.85
const EMISSION_SIGN := 0.62
const EMISSION_UNDER := 0.78
const EMISSION_RIM := 0.30

# --- material character ---------------------------------------------------
#
# The toy look, as four numbers. `clearcoat` is the whole trick: a second
# specular lobe over an unlit-by-metal diffuse, which is physically what a
# moulded part with a lacquer on it is, and visually what separates a
# collectible from a machined plate. V1.1 used it on exactly two materials.
const TOY_ROUGHNESS := 0.38
const TOY_CLEARCOAT := 0.86
const TOY_CLEARCOAT_ROUGHNESS := 0.070
const MARBLE_ROUGHNESS := 0.12

var variant := VARIANT_B
var _colors: Dictionary = {}
var _cache := {}


func _init(which := VARIANT_B) -> void:
	variant = which if PALETTES.has(which) else VARIANT_B
	_colors = PALETTES[variant]


func color(key: String) -> Color:
	## One palette entry, with a loud fallback rather than a silent black.
	##
	## Variant C carries `accent_violet` and the other two do not; asking for
	## it under A returns A's cool accent rather than nothing, which is what
	## lets one scene build all three without branching at every call site.
	if _colors.has(key):
		return _colors[key]
	if key == "accent_violet":
		return _colors.get("accent_cool", Color.MAGENTA)
	return Color.MAGENTA


func marble_color(index: int) -> Color:
	return MARBLES[index % MARBLES.size()]


func _cached(key: String) -> StandardMaterial3D:
	return _cache.get(key)


func _put(key: String, material: StandardMaterial3D) -> StandardMaterial3D:
	_cache[key] = material
	return material


# --- builders -------------------------------------------------------------

func moulded(albedo: Color, roughness := TOY_ROUGHNESS,
		clearcoat := TOY_CLEARCOAT) -> StandardMaterial3D:
	## The default surface of this machine: painted, glossy, not metal.
	var material := StandardMaterial3D.new()
	material.albedo_color = albedo
	material.metallic = 0.0
	material.metallic_specular = 0.5
	material.roughness = roughness
	material.clearcoat_enabled = clearcoat > 0.0
	material.clearcoat = clearcoat
	material.clearcoat_roughness = TOY_CLEARCOAT_ROUGHNESS
	return material


func metal(albedo: Color, metallic: float, roughness: float) -> StandardMaterial3D:
	## Real metal, spent only where metal is meant to read.
	var material := StandardMaterial3D.new()
	material.albedo_color = albedo
	material.metallic = metallic
	material.metallic_specular = 0.5
	material.roughness = roughness
	return material


func glowing(albedo: Color, energy: float,
		emission: Color = Color.BLACK) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = albedo
	material.metallic = 0.0
	material.roughness = 0.30
	material.emission_enabled = true
	material.emission = albedo if emission == Color.BLACK else emission
	material.emission_energy_multiplier = energy
	return material


# --- track and shell ------------------------------------------------------

func track() -> StandardMaterial3D:
	var found := _cached("track")
	if found:
		return found
	# Rougher than the shell and less clearcoat: this is the surface a marble
	# runs on, and a mirror-finish channel would take a highlight straight
	# down its length and compete with the marbles for the eye.
	return _put("track", moulded(color("track"), 0.44, 0.62))


func track_panel() -> StandardMaterial3D:
	var found := _cached("track_panel")
	if found:
		return found
	return _put("track_panel", moulded(color("track_panel"), 0.46, 0.55))


func track_side() -> StandardMaterial3D:
	var found := _cached("track_side")
	if found:
		return found
	return _put("track_side", moulded(color("track_side"), 0.40))


func shell() -> StandardMaterial3D:
	## The outer flank and underside of a moulded component.
	##
	## Deliberately only two steps below the running surface, not eight. In
	## the neon palette a deck's side was #2B2D31 against a #9A9790 top, and
	## that eight-stop cliff is what made every beam read as a pale strip
	## floating on a black web. A moulded part's flank is the *same plastic*
	## seen at a different angle.
	var found := _cached("shell")
	if found:
		return found
	return _put("shell", moulded(color("shell"), 0.36))


# --- structure ------------------------------------------------------------

func structure(lit := false) -> StandardMaterial3D:
	var key := "structure:lit" if lit else "structure"
	var found := _cached(key)
	if found:
		return found
	# A little metallic, because these are the parts that are meant to look
	# like metal - but only a little, because the environment they would
	# mirror is a soft dome rather than a studio and too much would flatten
	# them into it.
	var material := metal(
		color("structure_lit") if lit else color("structure"), 0.22, 0.46)
	return _put(key, material)


func cradle() -> StandardMaterial3D:
	var found := _cached("cradle")
	if found:
		return found
	return _put("cradle", metal(color("cradle"), 0.30, 0.38))


func hardware() -> StandardMaterial3D:
	## Warm metal: hubs, clamps, brackets, joints, the mechanical element.
	##
	## The one place metallic is spent freely. It is a small fraction of the
	## frame and it is the fraction that has to say "machined": brass and
	## anodised gold under a bright dome give a long warm sheen that no
	## painted surface can, and it is where most of this palette's warmth
	## lives in the two variants whose accent is cool.
	var found := _cached("hardware")
	if found:
		return found
	return _put("hardware", metal(color("hardware"), 0.82, 0.26))


func rail() -> StandardMaterial3D:
	var found := _cached("rail")
	if found:
		return found
	return _put("rail", metal(Color(0.855, 0.867, 0.886), 0.70, 0.22))


# --- acrylic --------------------------------------------------------------

func acrylic(alpha := 0.20) -> StandardMaterial3D:
	## The transparent wall, and the brief's "unmistakable at phone size".
	##
	## Three things make acrylic read rather than merely be transparent: a
	## strong rim so the silhouette draws itself at grazing angles, a very low
	## roughness so it takes a hard specular from the key, and enough tint in
	## the body that the surface has a colour of its own. Culling is disabled
	## so the far wall is seen through the near one, which is what gives the
	## vessel thickness.
	var key := "acrylic:%.3f" % alpha
	var found := _cached(key)
	if found:
		return found
	var material := StandardMaterial3D.new()
	var tint := color("acrylic")
	material.albedo_color = Color(tint.r, tint.g, tint.b, alpha)
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	material.blend_mode = BaseMaterial3D.BLEND_MODE_MIX
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	material.metallic = 0.0
	material.metallic_specular = 0.85
	material.roughness = 0.04
	material.clearcoat_enabled = true
	material.clearcoat = 1.0
	material.clearcoat_roughness = 0.01
	material.rim_enabled = true
	material.rim = 1.0
	material.rim_tint = 0.20
	material.shadow_to_opacity = false
	material.disable_receive_shadows = true
	return _put(key, material)


func acrylic_rim() -> StandardMaterial3D:
	## The moulded edge of an acrylic part: solid, bright, and the thing that
	## actually survives a downscale to phone size.
	var found := _cached("acrylic_rim")
	if found:
		return found
	var material := moulded(color("acrylic_rim"), 0.06, 1.0)
	material.emission_enabled = true
	material.emission = color("acrylic_rim")
	material.emission_energy_multiplier = EMISSION_RIM
	return _put("acrylic_rim", material)


# --- the bowl -------------------------------------------------------------

func bowl_surface() -> StandardMaterial3D:
	## The running surface inside the vessel. The brightest large area in the
	## frame, and the thing the marbles are read against.
	var found := _cached("bowl_surface")
	if found:
		return found
	return _put("bowl_surface", moulded(color("bowl_surface"), 0.32, 0.80))


func light_ring(warm := false) -> StandardMaterial3D:
	var key := "ring:warm" if warm else "ring:cool"
	var found := _cached(key)
	if found:
		return found
	var tint := color("accent_warm") if warm else color("accent_cool")
	return _put(key, glowing(tint, EMISSION_RING))


func underlight() -> StandardMaterial3D:
	## Warm, and under everything. The cheapest structural warmth there is:
	## it lands on the cradle, the supports and the floor, which are the three
	## places a cool-accent variant would otherwise have none.
	var found := _cached("underlight")
	if found:
		return found
	return _put("underlight", glowing(color("accent_warm"), EMISSION_UNDER))


func lamp() -> StandardMaterial3D:
	var found := _cached("lamp")
	if found:
		return found
	return _put("lamp", glowing(color("hardware"), EMISSION_LAMP))


func sign(cool := true) -> StandardMaterial3D:
	var key := "sign:cool" if cool else "sign:warm"
	var found := _cached(key)
	if found:
		return found
	var tint := color("accent_cool") if cool else color("accent_warm")
	return _put(key, glowing(tint, EMISSION_SIGN))


func accent(warm := false) -> StandardMaterial3D:
	## A painted accent stripe: colour without light, for zone identity.
	var key := "accent:warm" if warm else "accent:cool"
	var found := _cached(key)
	if found:
		return found
	var tint := color("accent_warm") if warm else color("accent_cool")
	return _put(key, moulded(tint, 0.28, 0.95))


func violet() -> StandardMaterial3D:
	var found := _cached("violet")
	if found:
		return found
	return _put("violet", glowing(color("accent_violet"), EMISSION_RING))


# --- the room -------------------------------------------------------------

func room(distance: int) -> StandardMaterial3D:
	## Background structure at three distances.
	##
	## All three are far brighter than the neon room's, and none is near
	## black. The measurement that forced this: one quantised colour covered
	## 21% of the V1.1 bridge hero and the top two covered 41%, against a
	## 2.65% maximum for any single colour in the concept reference. A
	## background is allowed to be dark; it is not allowed to be one value.
	var key := "room:%d" % distance
	var found := _cached(key)
	if found:
		return found
	var base := color("backdrop")
	var shade: float = [1.0, 0.82, 0.68][clampi(distance, 0, 2)]
	return _put(key, moulded(
		Color(base.r * shade, base.g * shade, base.b * shade), 0.62, 0.20))


func room_light(warm := false) -> StandardMaterial3D:
	## A very dim, very large soft panel in the room.
	##
	## An order of magnitude below anything on the machine, because the whole
	## point is that it is *behind* the subject. A background light that
	## competes for the eye is the neon direction's failure, not its fix.
	var key := "room_light:warm" if warm else "room_light:cool"
	var found := _cached(key)
	if found:
		return found
	var tint := color("accent_warm") if warm else color("accent_cool")
	var soft := Color(
		lerpf(tint.r, 0.5, 0.55), lerpf(tint.g, 0.5, 0.55),
		lerpf(tint.b, 0.5, 0.55))
	return _put(key, glowing(soft, 0.20))


func floor_material() -> StandardMaterial3D:
	var found := _cached("floor")
	if found:
		return found
	# Matte, and no clearcoat at all. A hall floor with a sheen on it mirrors
	# the machine standing on it, and a bright object with a bright copy of
	# itself underneath has no ground - the eye reads the pair as one shape
	# floating.
	return _put("floor", moulded(color("floor"), 0.92, 0.0))


# --- racers ---------------------------------------------------------------

func marble(body: Color) -> StandardMaterial3D:
	## A candy collectible: saturated body, hard clearcoat, no emission.
	##
	## No emission is the whole of it. A glowing sphere has no terminator, and
	## the terminator is what makes a sphere a sphere - the brief asks for a
	## visible shadow side and a subtle rim, which is a lit ball, not a lamp.
	## The rim is small and untinted so it reads as the dome behind the marble
	## catching its edge rather than as an outline drawn round it.
	var key := "marble:%d" % body.to_rgba32()
	var found := _cached(key)
	if found:
		return found
	var material := StandardMaterial3D.new()
	material.albedo_color = body
	material.metallic = 0.0
	material.metallic_specular = 0.62
	material.roughness = MARBLE_ROUGHNESS
	material.clearcoat_enabled = true
	material.clearcoat = 1.0
	material.clearcoat_roughness = 0.02
	material.rim_enabled = true
	material.rim = 0.42
	material.rim_tint = 0.55
	return _put(key, material)
