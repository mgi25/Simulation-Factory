extends RefCounted

## The Neon Marble Machine palette: light track, dark structure, one accent.
##
## A separate palette from `race_materials.gd` rather than an extension of it,
## because the two are opposite. The V0.4 course is dark blue-grey metal with
## cyan piping and its racers are the only bright things in frame; this
## machine is *pale* - light silver decks standing on graphite structure - and
## its brightness budget is spent on the surfaces a racer rolls on.
##
## Three rules shape everything below.
##
## **The track is light and the structure is dark.** That single contrast is
## what makes a beam read as a beam: a pale top face against a graphite web
## and a graphite post, with a real shadow underneath. Reverse it and the
## machine turns back into markings on a floor, which is the whole failure
## the V1 brief opens with.
##
## **Nothing is emissive unless it is a light.** Edge strips, the start
## treatment, the drain collar and the bowl accents glow; deck, rails,
## structure and bowl shell do not. A machine where every object is lit has
## no shadows, and shadows are how a viewer sees shape.
##
## **The picture has to survive with bloom off.** Every material here is
## built to read from its albedo, its roughness and the key light. Exactly two
## strengths below clear the environment's glow threshold - the start
## treatment and the drain collar - so those two halo and nothing else does,
## which is what "no overwhelming bloom" means in practice.
##
## Materials are cached by key and shared. The machine is a few hundred
## meshes drawn from about fifteen materials.

# --- track ----------------------------------------------------------------

# The racing surface. Light silver with a faint warm bias so it does not read
# as blue-grey next to the cyan accents, and deliberately *not* white: pure
# white clips under ACES and takes the surface's shading with it, which is how
# a deck stops looking like a solid object.
const TRACK_TOP := Color(0.520, 0.542, 0.562)
# The same material one step down in value, for the flange and the wide aprons
# so a big pale area is not one flat tone.
const TRACK_TOP_DEEP := Color(0.290, 0.308, 0.332)
# The side and underside of a deck. Much darker: this is the part of a beam
# that tells a viewer the beam has thickness.
const TRACK_SIDE := Color(0.170, 0.183, 0.205)
const TRACK_WEB := Color(0.108, 0.118, 0.136)

# --- structure ------------------------------------------------------------

const GRAPHITE := Color(0.098, 0.107, 0.126)
const GRAPHITE_LIT := Color(0.150, 0.163, 0.188)
const GRAPHITE_FAR := Color(0.046, 0.052, 0.064)
const VOID_FLOOR := Color(0.017, 0.020, 0.027)

# --- rails ----------------------------------------------------------------

const RAIL_METAL := Color(0.560, 0.605, 0.650)

# --- accents --------------------------------------------------------------

# One cool accent and one warm-violet one, and no third. Cyan is the machine's
# own colour - edges, rails, the drain collar, the start. Violet is used twice
# and both are the room rather than the track: the light across the bowl's rim,
# and every third strip on the far wall. So the bowl is the one place on the
# *machine* that is not cyan, and the two accents never compete on a surface a
# racer touches.
const CYAN := Color(0.330, 0.815, 1.000)
const CYAN_PALE := Color(0.760, 0.945, 1.000)
const VIOLET := Color(0.560, 0.430, 0.980)

# --- bowl -----------------------------------------------------------------

const GLASS := Color(0.620, 0.780, 0.870)
const GLASS_ALPHA := 0.26
const BOWL_SHELL := Color(0.255, 0.285, 0.315)
const BOWL_DARK := Color(0.030, 0.036, 0.048)

# --- emission strengths ---------------------------------------------------
#
# The environment's glow threshold is 1.05. Everything below that is a lit
# surface; the two entries above it are the only things in the machine that
# are allowed to bloom.
const EMISSION_EDGE := 0.62
const EMISSION_START := 1.25        # over threshold: the start is the title card
const EMISSION_DRAIN := 1.15        # over threshold: the exit has to read as a hole
const EMISSION_BOWL := 0.55
const EMISSION_STRIP := 0.40

var _cache := {}


func _cached(key: String) -> StandardMaterial3D:
	return _cache.get(key)


func _put(key: String, material: StandardMaterial3D) -> StandardMaterial3D:
	_cache[key] = material
	return material


# --- builders -------------------------------------------------------------

func metal(color: Color, metallic: float, roughness: float,
		specular := 0.5) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.metallic = metallic
	material.metallic_specular = specular
	material.roughness = roughness
	return material


func emissive(color: Color, energy: float, body := Color.BLACK,
		roughness := 0.35) -> StandardMaterial3D:
	## A lit surface: dark body, bright emission, so the light reads as coming
	## out of the piece rather than as a pale piece catching the key.
	var base := body if body != Color.BLACK else color.darkened(0.75)
	var material := metal(base, 0.0, roughness, 0.30)
	material.emission_enabled = true
	material.emission = color
	material.emission_energy_multiplier = energy
	return material


# --- the machine ----------------------------------------------------------

func track_top(deep := false) -> StandardMaterial3D:
	## The surface a racer rolls on.
	##
	## Lightly metallic and fairly smooth, which on a pale albedo gives a
	## broad soft highlight rather than a mirror - a machined composite deck
	## rather than polished steel. Smoother than this and the deck becomes a
	## sheet of light with no shading left; rougher and it goes chalky.
	var key := "track:%s" % ("deep" if deep else "top")
	var cached := _cached(key)
	if cached != null:
		return cached
	var color := TRACK_TOP_DEEP if deep else TRACK_TOP
	return _put(key, metal(color, 0.28, 0.295, 0.62))


func track_side() -> StandardMaterial3D:
	## The face of a deck's thickness. Dark, so the depth is legible.
	var cached := _cached("track_side")
	if cached != null:
		return cached
	return _put("track_side", metal(TRACK_SIDE, 0.42, 0.46, 0.45))


func track_web() -> StandardMaterial3D:
	## The recessed rib under a deck. Darker again than the side face.
	var cached := _cached("track_web")
	if cached != null:
		return cached
	return _put("track_web", metal(TRACK_WEB, 0.35, 0.62, 0.35))


func rail() -> StandardMaterial3D:
	## A rail is the one polished thing on the track. Silver and near-mirror,
	## so a highlight runs along it and traces the curve of the channel -
	## which is most of how a viewer reads an S-bend as a bend.
	var cached := _cached("rail")
	if cached != null:
		return cached
	return _put("rail", metal(RAIL_METAL, 0.88, 0.175, 0.85))


func edge_light() -> StandardMaterial3D:
	## The thin lit line let into the top of a rail. Cyan, on every rail on the
	## machine - a second edge colour would be a second thing for a viewer to
	## interpret, and an edge means the same thing everywhere.
	var cached := _cached("edge")
	if cached != null:
		return cached
	return _put("edge", emissive(CYAN, EMISSION_EDGE, CYAN.darkened(0.86), 0.28))


func structure(far := false, lit := false) -> StandardMaterial3D:
	## Graphite. Three values: near, near-and-catching-light, and far.
	##
	## `lit` is not emissive - it is the same gunmetal a step lighter, for the
	## members that face the key light. It exists because a support frame all
	## at one value reads as a silhouette, and a silhouette has no depth.
	var key := "structure:%s" % ("far" if far else ("lit" if lit else "near"))
	var cached := _cached(key)
	if cached != null:
		return cached
	if far:
		return _put(key, metal(GRAPHITE_FAR, 0.28, 0.74, 0.28))
	if lit:
		return _put(key, metal(GRAPHITE_LIT, 0.58, 0.44, 0.44))
	return _put(key, metal(GRAPHITE, 0.55, 0.52, 0.40))


func void_floor() -> StandardMaterial3D:
	var cached := _cached("void_floor")
	if cached != null:
		return cached
	return _put("void_floor", metal(VOID_FLOOR, 0.08, 0.92, 0.18))


func strip(warm := false) -> StandardMaterial3D:
	## A machine light on a wall or a column, well below glow threshold.
	var key := "strip:%s" % ("warm" if warm else "cool")
	var cached := _cached(key)
	if cached != null:
		return cached
	var color := VIOLET if warm else CYAN
	return _put(key, emissive(color, EMISSION_STRIP, color.darkened(0.90), 0.34))


# --- the bowl -------------------------------------------------------------

func bowl_surface() -> StandardMaterial3D:
	## The bowl's inner face: the same composite as the track, one step
	## smoother so the curvature carries a highlight that slides across it.
	##
	## Opaque, and that is a decision rather than an omission. A translucent
	## racing surface loses the contact shadow under every marble and loses
	## the terminator across the curve, and those two are what prove the bowl
	## is a bowl. The glass is on the *outside* of it, where it can be seen
	## from the side and from underneath without costing readability.
	var cached := _cached("bowl_surface")
	if cached != null:
		return cached
	var material := metal(TRACK_TOP, 0.24, 0.335, 0.62)
	material.clearcoat_enabled = true
	material.clearcoat = 0.22
	material.clearcoat_roughness = 0.14
	return _put("bowl_surface", material)


func bowl_glass() -> StandardMaterial3D:
	## The acrylic outer shell. Thin, cool, and barely there.
	var cached := _cached("bowl_glass")
	if cached != null:
		return cached
	var material := StandardMaterial3D.new()
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	material.albedo_color = Color(GLASS.r, GLASS.g, GLASS.b, GLASS_ALPHA)
	material.metallic = 0.0
	material.metallic_specular = 0.9
	material.roughness = 0.04
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	# No shadow: a 15%-opacity shell casting a solid shadow would put a dark
	# disc across the machine underneath it.
	material.rim_enabled = true
	material.rim = 0.85
	material.rim_tint = 0.1
	return _put("bowl_glass", material)


func bowl_shell() -> StandardMaterial3D:
	## The metallic support shell under the bowl. Brushed, mid-value, so the
	## bowl reads as a machined vessel sitting in a cradle.
	var cached := _cached("bowl_shell")
	if cached != null:
		return cached
	return _put("bowl_shell", metal(BOWL_SHELL, 0.82, 0.30, 0.70))


func bowl_dark() -> StandardMaterial3D:
	## Inside the drain. Almost black, barely reflective: the hole has to be
	## the darkest thing in the frame or it stops being a hole.
	var cached := _cached("bowl_dark")
	if cached != null:
		return cached
	return _put("bowl_dark", metal(BOWL_DARK, 0.05, 0.88, 0.15))


func drain_collar() -> StandardMaterial3D:
	var cached := _cached("drain_collar")
	if cached != null:
		return cached
	return _put("drain_collar",
		emissive(CYAN_PALE, EMISSION_DRAIN, CYAN.darkened(0.82), 0.24))


func start_light() -> StandardMaterial3D:
	## The start treatment: the one cyan-white thing bright enough to bloom.
	var cached := _cached("start_light")
	if cached != null:
		return cached
	return _put("start_light",
		emissive(CYAN_PALE, EMISSION_START, CYAN.darkened(0.78), 0.22))


func bowl_accent() -> StandardMaterial3D:
	## The ring let into the bowl's lip.
	var cached := _cached("bowl_accent")
	if cached != null:
		return cached
	return _put("bowl_accent",
		emissive(CYAN, EMISSION_BOWL, CYAN.darkened(0.86), 0.26))


# --- racers ---------------------------------------------------------------

func racer(color: Color) -> StandardMaterial3D:
	## A premium glossy marble.
	##
	## The look is a saturated body under a clear coat, which is what a real
	## glass or lacquered marble is: the body carries the hue and the coat
	## carries a small, hard, white highlight that does not take the hue with
	## it. Metallic is kept low for exactly that reason - a metallic sphere
	## tints its own highlight and stops reading as glossy plastic.
	##
	## There is no emission at all, and that is the difference from the V0.4
	## racer. An emissive sphere is bright everywhere, so it has no terminator
	## and no shading, and at Shorts scale it flattens to a coloured disc. The
	## rim light is what keeps sixteen of them separable in a pile-up instead,
	## and it costs no shading to have.
	var key := "racer:%d" % color.to_rgba32()
	var cached := _cached(key)
	if cached != null:
		return cached
	var material := metal(color, 0.12, 0.115, 0.95)
	material.clearcoat_enabled = true
	material.clearcoat = 0.85
	material.clearcoat_roughness = 0.035
	material.rim_enabled = true
	material.rim = 0.55
	material.rim_tint = 0.25
	return _put(key, material)


func racer_textured(texture: Texture2D, key: String) -> StandardMaterial3D:
	## A marble whose body is a generated pattern rather than a flat colour.
	##
	## Only the country experiment uses this. Same coat, same rim, same
	## roughness as `racer()` - the comparison still is meant to isolate the
	## *pattern*, so nothing else about the material is allowed to differ.
	var cache_key := "racer_tex:%s" % key
	var cached := _cached(cache_key)
	if cached != null:
		return cached
	var material := metal(Color.WHITE, 0.12, 0.115, 0.95)
	material.albedo_texture = texture
	material.clearcoat_enabled = true
	material.clearcoat = 0.85
	material.clearcoat_roughness = 0.035
	material.rim_enabled = true
	material.rim = 0.55
	material.rim_tint = 0.25
	return _put(cache_key, material)
