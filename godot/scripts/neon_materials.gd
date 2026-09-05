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

# The racing surface. Light silver, and warm rather than cool: V1's was a
# blue-grey a hair darker, and against cyan accents on a graphite machine that
# read as the same grey as the structure lit a little harder. Warming it past
# neutral - red above green above blue - is what separates track from frame
# without adding a colour to the palette, and lifting it a step is what stops
# the machine reading as one value.
#
# Still deliberately *not* white: pure white clips under ACES and takes the
# surface's shading with it, which is how a deck stops looking like a solid.
const TRACK_TOP := Color(0.605, 0.592, 0.566)
# One step down in value, for the flange and the bevel along a deck's edge.
const TRACK_TOP_DEEP := Color(0.352, 0.342, 0.326)
# A much smaller step, for the panel inlaid down the middle of a deck.
#
# The panel used the deep value in V1, where every deck was wide enough that
# it read as an inlay. On a launch channel a unit and three quarters across it
# read as a dark stripe with the track either side of it, which turns a light
# silver deck into a dark one with pale edges - the opposite of the brief's
# palette. One step is enough to break a flat surface; three is a different
# material.
const TRACK_PANEL := Color(0.512, 0.500, 0.478)
# The side and underside of a deck. Much darker: this is the part of a beam
# that tells a viewer the beam has thickness.
const TRACK_SIDE := Color(0.168, 0.176, 0.194)
const TRACK_WEB := Color(0.100, 0.108, 0.124)

# --- structure ------------------------------------------------------------

const GRAPHITE := Color(0.126, 0.136, 0.158)
# The members that face the key. Lifted well clear of the base graphite,
# because V1's cradle, legs and braces all fell within a few hundredths of
# each other and the whole support frame read as one silhouette - and a
# silhouette has no depth. The brief asks for the machinery holding the bowl
# to be obvious; this is most of how that is bought.
const GRAPHITE_LIT := Color(0.205, 0.218, 0.244)
# The room. Also lifted, and for the opposite reason: at V1's value the
# columns and gantries were inside a few percent of the background and the
# frame was mostly empty black. They are still the darkest structure in the
# picture - they just exist now.
const GRAPHITE_FAR := Color(0.082, 0.092, 0.113)
const GRAPHITE_DIM := Color(0.055, 0.062, 0.078)
# The nearest rank, between the lens and the machine. A step above the far
# ranks so a paused frame has three distances in it rather than two.
const GRAPHITE_NEAR := Color(0.132, 0.143, 0.166)
const VOID_FLOOR := Color(0.079, 0.086, 0.101)

# --- rails ----------------------------------------------------------------

const RAIL_METAL := Color(0.655, 0.672, 0.700)

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
# The tall outer wall is thinner in body and much stronger at its edges than
# the shell under the vessel. That is what acrylic looks like and it is also
# what keeps it free: the body is where the racers are seen through, so it has
# to cost as little as possible, and the Fresnel that draws the silhouette
# happens at grazing angles where there is nothing behind it to obscure.
const GLASS_WALL_ALPHA := 0.155
const BOWL_SHELL := Color(0.290, 0.312, 0.338)
const BOWL_DARK := Color(0.030, 0.036, 0.048)

# --- emission strengths ---------------------------------------------------
#
# The environment's glow threshold is 1.05. Everything below that is a lit
# surface; the two entries above it are the only things in the machine that
# are allowed to bloom.
const EMISSION_EDGE := 0.54
const EMISSION_START := 1.12        # over threshold: the start is the title card
const EMISSION_DRAIN := 1.15        # over threshold: the exit has to read as a hole
const EMISSION_BOWL := 0.55
const EMISSION_STRIP := 0.40
# Under the bowl, and under threshold on purpose. The brief asks for
# underlighting that leaves the track's shading visible and the marbles
# dominant; a strip that bloomed would do neither.
const EMISSION_UNDER := 0.85
const EMISSION_GLASS_RIM := 0.34

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

func track_panel() -> StandardMaterial3D:
	## The inlay down the middle of a deck. One step below the running
	## surface, and the same finish, so it reads as a recess in one material
	## rather than as a second material.
	var cached := _cached("track_panel")
	if cached != null:
		return cached
	return _put("track_panel", metal(TRACK_PANEL, 0.28, 0.315, 0.60))


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
		return _put(key, metal(GRAPHITE_FAR, 0.30, 0.70, 0.30))
	if lit:
		return _put(key, metal(GRAPHITE_LIT, 0.58, 0.42, 0.48))
	return _put(key, metal(GRAPHITE, 0.55, 0.52, 0.40))


func room(depth := 0) -> StandardMaterial3D:
	## The chamber the machine stands in, at three distances.
	##
	## 0 is the near rank, between the lens and the machine; 1 is the far
	## ranks and the towers; 2 is the back wall behind everything. The brief
	## asks a paused frame to contain a foreground, a midground and a
	## background, and three values a viewer can tell apart is what makes the
	## difference between three distances and one dark mass.
	var key := "room:%d" % depth
	var cached := _cached(key)
	if cached != null:
		return cached
	if depth <= 0:
		return _put(key, metal(GRAPHITE_NEAR, 0.42, 0.56, 0.36))
	if depth == 1:
		return _put(key, metal(GRAPHITE_FAR, 0.30, 0.70, 0.30))
	return _put(key, metal(GRAPHITE_DIM, 0.16, 0.86, 0.20))


func void_floor() -> StandardMaterial3D:
	## The floor of the hall, nineteen units under the deck.
	##
	## Lifted well above V1's near-black, and that is a deliberate reversal.
	## V1 reasoned that a dark void keeps the machine the subject; what it
	## actually produced was a frame that is mostly nothing, and plant standing
	## on an invisible floor reads as boxes floating in space. A floor a viewer
	## can see is a floor that can take a shadow, and the shadows the machine
	## throws onto it are worth more than the contrast the darkness bought.
	var cached := _cached("void_floor")
	if cached != null:
		return cached
	return _put("void_floor", metal(VOID_FLOOR, 0.10, 0.88, 0.20))


func strip(warm := false, dim := false) -> StandardMaterial3D:
	## A machine light on a tower or a floor run, well below glow threshold.
	##
	## `dim` is a third of the energy, for the runs on the floor. They are the
	## longest continuous lines in the picture and the first version had them
	## at full strength: two bright dashed rules crossing a dark frame, which
	## is the most attention-grabbing shape there is and belonged to nothing.
	var key := "strip:%s:%s" % [
		"warm" if warm else "cool", "dim" if dim else "full"]
	var cached := _cached(key)
	if cached != null:
		return cached
	var color := VIOLET if warm else CYAN
	var energy := EMISSION_STRIP * (0.30 if dim else 1.0)
	return _put(key, emissive(color, energy, color.darkened(0.92), 0.34))


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


func under_light(warm := false) -> StandardMaterial3D:
	## The lit strip beneath the bowl's cradle. Cyan on the drain side, violet
	## opposite it, and both kept under the environment's glow threshold: the
	## brief wants the underlighting to describe the machinery, not to become
	## the brightest thing in the picture.
	var key := "under:%s" % ("warm" if warm else "cool")
	var cached := _cached(key)
	if cached != null:
		return cached
	var color := VIOLET if warm else CYAN
	return _put(key, emissive(color, EMISSION_UNDER, color.darkened(0.88), 0.30))


func glass_rim() -> StandardMaterial3D:
	## The cap on top of the acrylic wall. Just bright enough to draw the
	## silhouette of a transparent object, which is the one thing a
	## transparent object cannot do for itself.
	var cached := _cached("glass_rim")
	if cached != null:
		return cached
	return _put("glass_rim",
		emissive(CYAN, EMISSION_GLASS_RIM, CYAN.darkened(0.90), 0.24))


func bowl_wall_glass() -> StandardMaterial3D:
	## The tall acrylic wall standing on the bowl's rim.
	##
	## The V1 shell was underneath the vessel, where at a fifty-two degree
	## lens there is almost none of it in view - the report said so and it was
	## the honest reading. This is the other half of the reference's bowl and
	## the half that reads: a flared wall rising *above* the rim, seen against
	## the dark room, with the racers below and inside it.
	##
	## Two things keep it from costing readability. It is broken by a wide
	## opening on the side the lens is on, so nothing is seen through glass
	## that could be seen without it; and its body is far thinner than the
	## shell's while its rim is far stronger, so what a viewer reads is an
	## edge rather than a film.
	var cached := _cached("bowl_wall_glass")
	if cached != null:
		return cached
	var material := StandardMaterial3D.new()
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	material.albedo_color = Color(GLASS.r, GLASS.g, GLASS.b, GLASS_WALL_ALPHA)
	material.metallic = 0.0
	material.metallic_specular = 0.95
	material.roughness = 0.03
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	material.rim_enabled = true
	material.rim = 1.0
	material.rim_tint = 0.05
	# No shadow: a fifteen percent wall casting a solid one would put a dark
	# ring across the machine underneath it.
	return _put("bowl_wall_glass", material)


func throat_glass() -> StandardMaterial3D:
	## The window let into the far half of the bowl's floor.
	##
	## Nothing ever stands on that half - a racer past the drain plane is in
	## the throat, below - so it costs no racing surface, and it is the only
	## place the lens can see the throat from at all. Darker and clearer than
	## the wall: it is being looked *through* on purpose.
	var cached := _cached("throat_glass")
	if cached != null:
		return cached
	var material := StandardMaterial3D.new()
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	material.albedo_color = Color(0.400, 0.560, 0.660, 0.215)
	material.metallic = 0.0
	material.metallic_specular = 0.85
	material.roughness = 0.05
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	material.rim_enabled = true
	material.rim = 0.70
	material.rim_tint = 0.10
	return _put("throat_glass", material)


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
