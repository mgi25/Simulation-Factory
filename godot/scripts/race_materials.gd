extends RefCounted

## The race's material system: one palette, built once, shared by every piece.
##
## Two rules shape everything here.
##
## **The racers own the colour.** Ten saturated hues have to stay the most
## colourful things on screen, so the course is built almost entirely from one
## dark blue-grey metal and one restrained cyan accent. Where a piece needs its
## own identity - a jump pad, the finish - it earns a hue, and nothing else
## gets one. A course where every obstacle is a different colour is a course
## where the racers are just ten more coloured things.
##
## **Behaviour should be legible from appearance.** The simulation gives every
## surface one of three materials, and they behave very differently: TRACK
## grips, SLICK slides, BOUNCY throws. A viewer who watches a few races should
## come to read a polished pale surface as "they will slide here" without ever
## being told. So the physical material picks the finish - roughness, metallic,
## how much the edge accent glows - and the role picks the hue.
##
## Materials are cached by key and shared across every piece that wants them.
## A course has ~70 pieces; allocating a StandardMaterial3D per piece would be
## seventy copies of six materials.

# --- the palette ----------------------------------------------------------

# Structure. Dark, faintly blue, and metallic enough to catch the key light
# along an edge - which is what stops a dark course reading as a hole.
#
# Lifted for V0.4, and the reason is the geometry rather than taste. Under the
# V0.3 top-down camera every structural surface faced the lens and a value
# this low read as "dark metal". With real volumes and a 52 degree lens, half
# of every beam, post and rib faces away from the key, and at 0.055 those
# faces resolved to black: the machine had shape and none of it was visible.
const STRUCTURE := Color(0.105, 0.122, 0.152)
const WALL := Color(0.105, 0.120, 0.158)

# Track surface. Three finishes of one colour, so the differences read as
# *surface* rather than as different objects.
const TRACK_BODY := Color(0.185, 0.205, 0.250)
const SLICK_BODY := Color(0.235, 0.270, 0.335)
const BOUNCY_BODY := Color(0.105, 0.150, 0.185)

# The one accent colour the architecture is allowed. Everything structural
# that lights up, lights up in this.
const ACCENT := Color(0.30, 0.78, 0.95)
const ACCENT_WARM := Color(1.00, 0.80, 0.38)

# The pieces that earn their own hue, because a viewer has to tell at a glance
# what will happen when a racer touches one.
const PEG_BODY := Color(0.115, 0.190, 0.255)
const PEG_GLOW := Color(0.42, 0.86, 1.00)
const PAD_BODY := Color(0.085, 0.180, 0.130)
const PAD_GLOW := Color(0.36, 1.00, 0.62)
const GATE_BODY := Color(0.230, 0.075, 0.090)
const GATE_GLOW := Color(1.00, 0.34, 0.34)
const SPINNER_BODY := Color(0.135, 0.120, 0.105)
const SPINNER_GLOW := Color(1.00, 0.62, 0.22)
const FINISH_GLOW := Color(1.00, 0.86, 0.42)

# Environment.
const STRUCTURE_FAR := Color(0.058, 0.068, 0.090)
const FLOOR_DEEP := Color(0.018, 0.022, 0.032)

# --- emission strengths ---------------------------------------------------
#
# Everything here sits against the environment's glow threshold. An accent
# under it is simply a lit surface; one over it blooms. Only the things a
# viewer must not miss are allowed over.
const EMISSION_EDGE := 0.55        # the thin line along a track edge
const EMISSION_PEG := 0.85
const EMISSION_PAD := 1.35         # over threshold: a pad is an event
const EMISSION_GATE := 0.70
const EMISSION_SPINNER := 1.10     # over threshold: a spinner is a hazard
const EMISSION_CHECKPOINT := 0.45
const EMISSION_FINISH := 1.45      # the brightest static thing on the course
const EMISSION_STRIP := 0.70

var _cache := {}


func _cached(name: String) -> StandardMaterial3D:
	## Materials are shared, not copied. A course has around seventy pieces
	## drawn from six materials; one StandardMaterial3D each would be sixty
	## duplicates of the same shader state.
	return _cache.get(name)


func _put(name: String, material: StandardMaterial3D) -> StandardMaterial3D:
	_cache[name] = material
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
		roughness := 0.4) -> StandardMaterial3D:
	## A lit surface. The body colour is kept dark and the emission carries
	## the brightness, so the accent reads as light coming *out* of the piece
	## rather than as a pale piece catching the key light.
	var base := body if body != Color.BLACK else color.darkened(0.72)
	var material := metal(base, 0.0, roughness, 0.35)
	material.emission_enabled = true
	material.emission = color
	material.emission_energy_multiplier = energy
	return material


func unshaded(color: Color, alpha: float, additive := true) -> StandardMaterial3D:
	## For effects: no lighting, no shadow, written straight into the buffer.
	var material := StandardMaterial3D.new()
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	if additive:
		material.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
	material.albedo_color = Color(color.r, color.g, color.b, alpha)
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	return material


# --- the course palette, by role and physical material --------------------

func surface(role: String, physical: String) -> StandardMaterial3D:
	## The body of a course piece.
	##
	## `role` says what the piece is for and `physical` says how it behaves.
	## Role wins where the two disagree, because a jump pad has to look like a
	## jump pad whatever surface it is made of.
	var name := "surface:%s:%s" % [role, physical]
	var cached := _cached(name)
	if cached != null:
		return cached

	var material: StandardMaterial3D
	match role:
		"wall":
			material = metal(WALL, 0.40, 0.60, 0.45)
		"peg":
			material = emissive(PEG_GLOW, EMISSION_PEG, PEG_BODY, 0.30)
		"jump_pad":
			material = emissive(PAD_GLOW, EMISSION_PAD, PAD_BODY, 0.24)
		"gate":
			material = emissive(GATE_GLOW, EMISSION_GATE, GATE_BODY, 0.42)
		_:
			material = _track_surface(physical)
	return _put(name, material)


func _track_surface(physical: String) -> StandardMaterial3D:
	## The three finishes a racer has to be able to tell apart.
	match physical:
		"slick":
			# Polished and near-mirror. The clearest signal on the course:
			# a bright reflected highlight sliding along a ramp reads as
			# "nothing grips here" before a viewer could name why.
			return metal(SLICK_BODY, 0.70, 0.16, 0.80)
		"bouncy":
			# Softer and slightly lit, so a bumper reads as sprung rather
			# than solid.
			var material := metal(BOUNCY_BODY, 0.15, 0.55, 0.40)
			material.emission_enabled = true
			material.emission = ACCENT
			material.emission_energy_multiplier = 0.16
			return material
	# TRACK: honest brushed metal. Most of the course is this, so it is the
	# surface everything else is read against.
	return metal(TRACK_BODY, 0.35, 0.44, 0.45)


func edge(physical: String) -> StandardMaterial3D:
	## The thin lit line along the length of a travelling surface.
	##
	## It does two jobs at once: it gives a dark ramp a readable silhouette
	## against a dark floor, and it is where the surface type is stated most
	## clearly - a slick ramp's edge is brighter and cooler than a track one's.
	var name := "edge:%s" % physical
	var cached := _cached(name)
	if cached != null:
		return cached

	var energy := EMISSION_EDGE
	var color := ACCENT
	if physical == "slick":
		energy = EMISSION_EDGE * 1.7
	elif physical == "bouncy":
		color = PEG_GLOW
		energy = EMISSION_EDGE * 1.3
	return _put(name, emissive(color, energy, ACCENT.darkened(0.86), 0.35))


func spinner_body() -> StandardMaterial3D:
	var cached := _cached("spinner_body")
	if cached != null:
		return cached
	return _put("spinner_body", metal(SPINNER_BODY, 0.80, 0.34, 0.60))


func spinner_edge() -> StandardMaterial3D:
	var cached := _cached("spinner_edge")
	if cached != null:
		return cached
	return _put("spinner_edge",
		emissive(SPINNER_GLOW, EMISSION_SPINNER, SPINNER_BODY, 0.28))


func checkpoint_bar(is_finish: bool) -> StandardMaterial3D:
	var name := "checkpoint:%s" % ("finish" if is_finish else "plain")
	var cached := _cached(name)
	if cached != null:
		return cached
	if is_finish:
		return _put(name, emissive(FINISH_GLOW, EMISSION_FINISH,
			FINISH_GLOW.darkened(0.80), 0.22))
	return _put(name, emissive(ACCENT, EMISSION_CHECKPOINT,
		ACCENT.darkened(0.88), 0.40))


func structure(far := false) -> StandardMaterial3D:
	var name := "structure:%s" % ("far" if far else "near")
	var cached := _cached(name)
	if cached != null:
		return cached
	if far:
		return _put(name, metal(STRUCTURE_FAR, 0.30, 0.78, 0.30))
	return _put(name, metal(STRUCTURE, 0.45, 0.70, 0.38))


func floor_deep() -> StandardMaterial3D:
	var cached := _cached("floor_deep")
	if cached != null:
		return cached
	return _put("floor_deep", metal(FLOOR_DEEP, 0.10, 0.92, 0.20))


func light_strip(warm := false) -> StandardMaterial3D:
	var name := "strip:%s" % ("warm" if warm else "cool")
	var cached := _cached(name)
	if cached != null:
		return cached
	var color := ACCENT_WARM if warm else ACCENT
	return _put(name, emissive(color, EMISSION_STRIP, color.darkened(0.85), 0.30))


func racer(color: Color, finished: bool) -> StandardMaterial3D:
	## A competitor.
	##
	## Glossy and lightly metallic so the sphere carries a real highlight and
	## a real terminator - which is the whole difference between a ball and a
	## coloured circle. The emission is deliberately low: enough that the hue
	## survives a dark environment and reads at Shorts scale, far too little
	## to wash the shading out. Past about 0.4 the highlight disappears and
	## the racer goes back to being a disc.
	var name := "racer:%d:%s" % [color.to_rgba32(), "done" if finished else "live"]
	var cached := _cached(name)
	if cached != null:
		return cached

	if finished:
		# Still recognisably itself, but out of the contest: darker, duller,
		# and no longer glowing.
		return _put(name, metal(color.darkened(0.55), 0.25, 0.62, 0.35))

	var material := metal(color, 0.28, 0.22, 0.85)
	material.emission_enabled = true
	material.emission = color
	material.emission_energy_multiplier = 0.30
	# A hot edge where the sphere turns away from the light. On a dark course
	# this is what separates one racer from another in a pile-up.
	material.rim_enabled = true
	material.rim = 0.65
	material.rim_tint = 0.35
	return _put(name, material)


func racer_flat(color: Color) -> StandardMaterial3D:
	"""A racer as pure albedo, for the measuring lens.

	Unshaded, so no light can reach it: not the key, not the fill, and above
	all not the cold kicker whose specular turns the edge of every sphere
	cyan. The pixel a check looks at is then exactly the colour the replay
	names, which is the only property the verification camera needs a racer
	to have.

	"Exactly" was not true for two releases, and unshaded was never what was
	standing in the way. The *tone curve* was: ACES is applied to the whole
	frame, unshaded surfaces included, and it lifted racer 7's
	(72, 226, 224) to (157, 230, 228) in the PNG. The hue survived - which is
	why the check worked at all - but cyan drifted far enough that
	`verify_race_render.py` lost that racer whenever a neighbour covered part
	of it, in four of thirty sampled frames of the V0.3 reference replay.

	The fix is in `race_scene.gd`, which gives the measuring lens a linear
	tone mapper: a tone curve is a deliberate distortion of colour, which is
	exactly what a production frame wants and exactly what a measurement must
	not have. With it, every racer reaches the file as the number the replay
	carries, and this material can be what it says it is.
	"""
	var name := "racer_flat:%d" % color.to_rgba32()
	var cached := _cached(name)
	if cached != null:
		return cached
	var material := StandardMaterial3D.new()
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.albedo_color = color
	return _put(name, material)


func racer_band(color: Color) -> StandardMaterial3D:
	## The meridian ring that makes rotation visible.
	##
	## A uniform sphere spinning about its axis is indistinguishable from a
	## sphere at rest, and the replay carries a real rotation that would
	## otherwise be thrown away. Pale rather than white so it reads as part of
	## the racer rather than as a separate object stuck to it.
	var name := "band:%d" % color.to_rgba32()
	var cached := _cached(name)
	if cached != null:
		return cached
	var material := metal(color.lightened(0.62), 0.10, 0.30, 0.70)
	material.emission_enabled = true
	material.emission = color.lightened(0.45)
	material.emission_energy_multiplier = 0.22
	return _put(name, material)


func badge() -> StandardMaterial3D:
	## The disc a racer's number sits on. Dark and unlit, so the number reads
	## against it whatever the racer is doing.
	var cached := _cached("badge")
	if cached != null:
		return cached
	var material := StandardMaterial3D.new()
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.albedo_color = Color(0.03, 0.035, 0.05, 0.82)
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	material.billboard_mode = BaseMaterial3D.BILLBOARD_ENABLED
	material.billboard_keep_scale = true
	return _put("badge", material)
