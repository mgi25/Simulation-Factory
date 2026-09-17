extends RefCounted
## The Race #2 channel's surface treatment: V31's control, three V31.1 variants
## and the segmentation mask that measures them.
##
## ## Why this is a module and not four lines in `race2_scene.gd`
##
## The channel is **one swept strip per run with one `material_override`**, and
## the deck and the rail are the same mesh. So a deck/rail treatment cannot be
## a second material on a second node without changing the geometry, which the
## V31.1 brief forbids outright. What it can be is a function of the strip's
## own `u`, which `race2_scene._strip_mesh` already writes: `u = column /
## (section_points - 1)`, walked from the west guard top, down the west wall,
## across the cradle and back up the east - `sloped.track.channel_profile`'s
## order, unchanged since Race #1.
##
## At Race #2's 21-point section that puts the cradle - the surface a marble
## actually rolls on - at **u 0.30 to 0.70**, and the lip, wall and guard top
## in the two 0.30-wide bands outside it. Those two numbers are the whole
## mechanism: a 1-D texture across `u` separates deck from rail inside one
## material, on one mesh, with the vertices untouched.
##
## ## What each variant is allowed to touch
##
## Only the channel's own `StandardMaterial3D`. Not the geometry, not the
## environment, not a light, not the grade. `channel(palette, "v31", "")`
## returns the palette's `track_silver` itself, so a render with no `--track=`
## is the V31 render - `tests/test_race2_v311_track.py` holds that by comparing
## every field of the two materials.

const DECK_FROM := 0.30
const DECK_TO := 0.70

## The segmentation classes, as flat unshaded colours. Chosen to be corners of
## the RGB cube, which buys two things a measurement wants: an MSAA edge blend
## is never nearer to a wrong corner than to a right one, and a corner survives
## any per-channel transfer curve the pipeline might apply, so the classifier
## needs no threshold that depends on the renderer agreeing about sRGB.
##
## Written as hex rather than as float triples because
## `tests/test_marble3d_integration.py::test_the_marble_machine_never_builds_a_colour_from_floats`
## is a rule about every authored colour under `assets/marble_machine`, and a
## diagnostic is not an exemption from a house rule. Nothing about the rendered
## classes changes: a cube corner is the same colour written either way.
const MASK_DECK := "#FF0000"
const MASK_RAIL := "#00FF00"
const MASK_STRUCTURE := "#0000FF"
const MASK_STATION := "#00FFFF"
const MASK_ACTUATOR := "#FF00FF"
const MASK_RACER := "#FFFF00"
const MASK_BACKGROUND := "#000000"

## `--track=bands`: the same diagnostic at the resolution of the section
## itself, with everything that is not channel painted out. The four bands are
## the four things `sloped.track.channel_profile` actually authors, read off the
## profile at Race #2's scale of 2.0:
##
##     crown  u 0.00-0.10   the top 0.05 of the guard, at across +-2.004
##     wall   u 0.10-0.25   the face, 0.53 down to -0.02
##     lip    u 0.25-0.30   the fillet into the cradle
##     cradle u 0.30-0.70   the running surface, 3.76 wide
##
## This mode exists because the deck/rail mask answered "which of the two is on
## screen" with "neither, it is all rail", and the design of a deck-versus-edge
## hierarchy depends entirely on *which* rail.
const BAND_CRADLE := "#FF0000"
const BAND_LIP := "#FF00FF"
const BAND_WALL := "#00FF00"
const BAND_CROWN := "#00FFFF"
const BAND_EDGES := [0.10, 0.25, 0.30]

## `--track=racers`: the per-racer diagnostic behind Part K's contrast guard.
##
## The first build of that guard clustered the racer pixels in `ab` with
## k-means, and it was an instrument bug of exactly the kind this project has
## hit before: on a sparse frame - 0.37% of the picture at the 6.80 s chase -
## eight clusters over three visible marbles split one racer into four and
## returned a "weakest separation" that swung from 16.7 to 8.6 between two
## variants whose racers are identically lit. So the racers are *labelled* by
## the renderer instead of inferred from the image: racer `i` of `n` is painted
## with red byte `round(255 * i / (n - 1))`, and the classifier reads the
## eight distinct red levels back in sorted order. That is exact and does not
## depend on the pipeline agreeing with anybody about a transfer curve: sorting
## survives any per-channel monotone function - which is also why the level can
## be a byte in a hex string rather than a float, and therefore why this obeys
## the same no-float-colours rule as everything else in this file.
const RACER_FLAG := "FF00"

## Every treatment this branch can render, control first.
const VARIANTS := ["v31", "A", "B", "C", "mask", "bands", "racers"]

## How much of the strip is drawn. `front` is V32; `both` is V32.1's fix. See
## `faces` for the measurement that says why this field exists at all.
const FACE_MODES := ["front", "both", "inside"]

## **Variant B's gain profile, and why it is shaped the way it is.**
##
## The band measurement in `docs/race2_v311_track_visibility.md` section 2 is
## what these five numbers answer. On the delivered picture the channel's four
## bands render at L* 24-48 (cradle), 57-74 (lip), 80-92 (wall face) and 85-90
## (crown) - fifty points of range inside one material - and the two that are
## actually on screen, the wall face and the crown, are **1.6 L* apart**. So
## the ribbon has no edge: the road and its rail are the same value, and a
## surface with one value across it reads as a line rather than as a plane.
##
## The profile below is a kerb, described in light:
##
## - `CRADLE_GAIN` lifts the running surface, the darkest band and the one the
##   brief calls the deck. It is on screen for a fraction of a percent of the
##   frame, so this is worth little - and it costs nothing, and it is what makes
##   the opening frame read as a road.
## - `LIP_GAIN` **darkens** the band just outside the cradle's edge, which is
##   the section's one real corner - 53.7 degrees, against under 8 everywhere
##   else. A concave corner is the one place in a real moulding that is
##   genuinely darker, so this is the shadow line at the foot of the rail, and
##   it is the cue that separates road from rail at phone size. It is not paint
##   because it is not on a flat part of the section; see `break_gain` for the
##   rule that says so and the test that holds it.
## - `WALL_BASE_GAIN` to `WALL_TOP_GAIN` is a gradient **up the face**, which is
##   the part that survives being resampled to 270 px wide. A crown highlight
##   alone is four pixels on the delivery frame and one on the phone; a gradient
##   over the whole face is the thickness cue at any size.
## - `CROWN_GAIN` puts the brighter silver on the top edge, where the brief's
##   Part C asks for it.
const CRADLE_GAIN := 1.35
const LIP_GAIN := 0.55
const WALL_BASE_GAIN := 0.70
const WALL_TOP_GAIN := 1.14
const CROWN_GAIN := 1.34


static func known(variant: String) -> bool:
	return variant.is_empty() or VARIANTS.has(variant)


static func is_mask(variant: String) -> bool:
	return variant == "mask" or variant == "bands" or variant == "racers"


static func racer_class(index: int, count: int) -> StandardMaterial3D:
	## Racer `index` of `count`, as a flat class the classifier can sort.
	##
	## The red byte is the label and the green byte is the "this is a racer"
	## flag. Eight racers land on 0, 36, 73, 109, 146, 182, 219 and 255, which
	## is nineteen apart at the closest - far more than anything downstream of a
	## flat unshaded surface can blur them by.
	var level := int(round(255.0 * float(index)
		/ maxf(float(count) - 1.0, 1.0)))
	return flat("#%02X%s" % [level, RACER_FLAG])


static func faces(material: StandardMaterial3D, mode: String) -> StandardMaterial3D:
	## **The pass's root cause, as one field.**
	##
	## The channel is an open strip of single-sided triangles, and
	## `race2_scene._strip_mesh` winds it so that the side Godot draws is the
	## **outside of the shell**: the underside of the cradle and the outer face
	## of each guard. So the running surface is not hidden behind the near rail,
	## as V31.1 and the V32.1 brief both assumed - it is *backfacing to every
	## camera above the track*, and no amount of lowering a guard can reveal a
	## polygon the rasteriser discards before depth is ever considered.
	##
	## Measured, `--track=bands` on the shipped picture against the same frame
	## with this set to `both`:
	##
	##     t       deck, front only     deck, both
	##     3.20          0.000%           2.070%
	##     8.40          0.001%          44.542%
	##     15.40         0.000%          10.851%
	##
	## `CULL_DISABLED` is the whole fix. It moves no vertex, so the collider is
	## untouched by construction; it changes no colour, roughness, clearcoat or
	## texture, so V31.1's Variant B material is field-for-field what it was;
	## and Godot's own shader flips `NORMAL` on a back-facing fragment when a
	## material is double-sided, so the running surface is lit as the surface it
	## is rather than as the underside of one.
	##
	## `front` is the default and is V32's render exactly.
	if mode == "both":
		material.cull_mode = BaseMaterial3D.CULL_DISABLED
	elif mode == "inside":
		# The cut-away: only the channel's inner surface, with the shell's
		# outside discarded. It reveals the same deck `both` does and, because
		# the underside of the strip is never drawn, it leaves the upper frame
		# the dark room it was - which is where V32's payoff card lives.
		material.cull_mode = BaseMaterial3D.CULL_FRONT
	return material


static func channel(palette, variant: String, probe: String,
		face_mode: String = "front") -> StandardMaterial3D:
	## The material the runs render with.
	##
	## `palette.get_material("track_silver")` is cached and shared, so every
	## variant works on a duplicate: a variant that mutated the cache would
	## repaint the collector tray and the S-curve channel in Race #1 too.
	var base: StandardMaterial3D = palette.get_material("track_silver")
	if variant.is_empty() or variant == "v31":
		if probe.is_empty() and face_mode != "both":
			return base
		return faces(_probed(base.duplicate(), probe), face_mode)
	# **`racers` paints the channel out, and that is a bug fix.** The first
	# build let it fall through to the deck/rail mask, whose rail is pure green
	# - which is also racer 0's class colour, because racer 0 is painted
	# `#00FF00`. Every rail pixel in the film joined racer 0, and the
	# weakest-separation guard came back as a flat 0.00 dE for all four
	# candidates: a guard that could not fail.
	if variant == "racers":
		return faces(flat(MASK_BACKGROUND), face_mode)
	if is_mask(variant):
		# The probe reaches the segmentation too, which the first build did not
		# allow. It has to: the only probe that matters to a *coverage* measure
		# is `cull`, and asking "is the deck behind something or facing away?"
		# is a question about the mask, not about the picture.
		var masked := _mask_channel(variant == "bands")
		if not probe.is_empty():
			_probed(masked, probe)
		return faces(masked, face_mode)
	var material: StandardMaterial3D = base.duplicate()
	match variant:
		"A":
			_pearl(material)
		"B":
			_pearl(material)
			material.albedo_texture = _deck_break()
			material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR
			material.texture_repeat = false
		"C":
			_pearl(material)
			_solid(material)
	if not probe.is_empty():
		_probed(material, probe)
	return faces(material, face_mode)


# --- the three variants -----------------------------------------------------


static func _pearl(material: StandardMaterial3D) -> void:
	## **Variant A, and the base the other two are built on.**
	##
	## The brief expected to have to *lift* the deck. The measurement says the
	## opposite about the band that is actually on screen, and A is what the
	## measurement asks for:
	##
	## 1. **Settle the value.** The visible band renders at L* 82 against a room
	##    at L* 17 and racers at L* 34-72 - the track is the brightest object in
	##    the frame, 28 points above the racers, which is the hierarchy upside
	##    down. `#BEC1C4` lands it near L* 75: a light grey rather than a white,
	##    still 58 points clear of the room, and off the part of the ACES
	##    shoulder that was flattening it.
	## 2. **Neutral in the render, which is not the same as neutral in the
	##    albedo.** This is the finding that cost the most to learn and the one
	##    to carry forward. `#D2D8DE` is 210/216/222 - twelve points of blue
	##    over red - and it renders at R-B = **+0.7**, dead neutral. The room
	##    adds about 12 bytes of red-minus-blue to whatever is put in front of
	##    it: `WorldWarm` is `#FFC694` and the bay practicals are warmer still.
	##    So the albedo's coolness is *load-bearing*, and taking it out - the
	##    brief's Part D, read literally - overshot to R-B = +11.7, a visibly
	##    warm track in a cool room. `#BEC1C4` keeps six points of the coolness
	##    and lands the render at about +4: Part D's "neutral or slightly
	##    warm-neutral", measured where Part D says to measure it.
	## 3. **Roughness and clearcoat moved, with no illusions about what they
	##    buy.** Section 3's probe is blunt: `specular` is byte-identical at
	##    0.50, 0.20 and 0.00, and `clearcoat = 0` moves the band 0.7 L*. This
	##    room returns no specular - sky `#0C0B0A`, key `specular 0.14`, every
	##    other light 0.0 - so the channel is a diffuse surface whatever its
	##    gloss says. 0.42 and a narrowed 0.55/0.10 clearcoat are kept because
	##    they drop the hard white streak the 0.04 lobe lays across a banked
	##    pan, which is a real defect, and not because they change the value.
	material.albedo_color = Color("#BEC1C4")
	material.roughness = 0.42
	material.clearcoat = 0.55
	material.clearcoat_roughness = 0.10


static func _solid(material: StandardMaterial3D) -> void:
	## **Variant C: the brief's Part E hypothesis, built and rendered.**
	##
	## Part E asks whether the deck is dark because of its specular, its
	## reflection or its metallic response, and says not to assume albedo is the
	## only problem. C is that question as a film: A's value with the gloss
	## chain taken to the matte end - roughness 0.75, the dielectric F0 down to
	## 0.25, the clearcoat off.
	##
	## It is kept even though the probe already answered the question, because a
	## candidate that shows the trade turning over is worth more than a third
	## good one - the same reason V31 kept RC. The measured answer is in section
	## 6: C differs from A by under two L* and is *flatter* than A, because
	## roughness on a diffuse-only surface takes modulation away rather than
	## adding it. The reflection response is not a lever in this room.
	material.roughness = 0.75
	material.metallic_specular = 0.25
	material.clearcoat = 0.0
	material.clearcoat_enabled = false


static func _deck_break() -> ImageTexture:
	## **Variant B: the deck/rail value break, as a gradient across `u`.**
	##
	## Not a stripe and not a painted line - the brief rules both out, and both
	## would need an edge somewhere a marble can run over. This is a value
	## hierarchy: the cradle a little under the material's albedo, the guard top
	## a little over, and a wide smoothstep between them that lands on the wall
	## face, where the section is already turning away. A viewer reads "the
	## floor is one value and the rail is a brighter one", and there is no line
	## anywhere to read as paint.
	##
	## `FORMAT_RGBF` on purpose: a float texture is unambiguously linear, so the
	## gain is a gain and not a gain composed with whatever transfer curve a
	## byte texture would have been decoded through. 256 wide by 1 tall, so `v`
	## - which the strip tiles eight times along the run - samples the same row
	## whatever it is, and nothing repeats along the course.
	var image := Image.create(256, 1, false, Image.FORMAT_RGBF)
	for x in 256:
		var gain := break_gain((float(x) + 0.5) / 256.0)
		image.set_pixel(x, 0, Color(gain, gain, gain))
	return ImageTexture.create_from_image(image)


static func break_gain(u: float) -> float:
	## The multiplier variant B applies to the albedo at one `u`.
	##
	## Knots and smoothsteps. **The section has exactly one corner**, and that
	## is worth stating because the first draft of this profile assumed four:
	## walking `race2.track.capped_profile(2.0)` and measuring the turn at every
	## point gives 53.7 degrees at the cradle edge (u 0.30 and 0.70) and under
	## 8 degrees everywhere else. The lip is not a fillet and the crown is not a
	## bevel - the guard is one smooth curve from the running surface to its top.
	##
	## So "not a painted stripe" is two rules rather than one, and
	## `test_variant_b_break_is_a_ramp_and_not_a_stripe` checks both: a ramp is
	## allowed to be steep **only** where it sits on that one corner, and
	## everywhere else it has to be gentle enough that a whole delivery pixel
	## sees under three L* of change. The cradle-to-lip drop is the steep one
	## and it is centred on u 0.30; the long climb up the face is the gentle
	## one, and it is a form gradient rather than an edge.
	##
	## Pure, and reachable from the tests on purpose:
	## `test_variant_b_break_is_a_ramp_and_not_a_stripe` asserts the cradle and
	## crown plateaus are flat, the curve is symmetric about the centreline, and
	## no step between neighbouring texels exceeds 0.01 - which is what "no
	## visible stripe" means as a number.
	var side: float = minf(u, 1.0 - u)   # 0 at a guard top, 0.5 mid-deck
	var knots := [
		[0.50, CRADLE_GAIN], [0.33, CRADLE_GAIN],   # the running surface
		[0.27, LIP_GAIN],                           # the fillet: a shadow line
		[0.24, WALL_BASE_GAIN],                     # the foot of the rail
		[0.10, WALL_TOP_GAIN],                      # up the face: the thickness
		[0.055, CROWN_GAIN], [0.00, CROWN_GAIN],    # the crown, brighter silver
	]
	for index in knots.size() - 1:
		var hi: Array = knots[index]
		var lo: Array = knots[index + 1]
		if side <= float(hi[0]) and side >= float(lo[0]):
			var t: float = (float(hi[0]) - side) / (float(hi[0]) - float(lo[0]))
			t = t * t * (3.0 - 2.0 * t)  # smoothstep: no derivative step either
			return float(hi[1]) + (float(lo[1]) - float(hi[1])) * t
	return CROWN_GAIN


# --- the diagnostic ---------------------------------------------------------


static func band_colour(u: float, banded: bool) -> String:
	## Which class one `u` belongs to, in either diagnostic. Pure, and the
	## tests read it rather than a rendered frame.
	var side: float = minf(u, 1.0 - u)
	if not banded:
		return MASK_DECK if side > DECK_FROM else MASK_RAIL
	if side >= BAND_EDGES[2]:
		return BAND_CRADLE
	if side >= BAND_EDGES[1]:
		return BAND_LIP
	if side >= BAND_EDGES[0]:
		return BAND_WALL
	return BAND_CROWN


static func _mask_channel(banded: bool) -> StandardMaterial3D:
	## Deck red, rail green, on one mesh, by the same `u` the variants use.
	##
	## Nearest filtering and a 20-texel texture put the class boundary exactly
	## on the section point that is the cradle's edge: texel `i` covers `u` in
	## [i/20, (i+1)/20), so texels 6 to 13 are exactly u 0.30 to 0.70. The band
	## edges at 0.10 and 0.25 land on texel boundaries for the same reason.
	var image := Image.create(20, 1, false, Image.FORMAT_RGBF)
	for x in 20:
		var u := (float(x) + 0.5) / 20.0
		image.set_pixel(x, 0, Color(band_colour(u, banded)))
	var material := flat("#FFFFFF")
	material.albedo_texture = ImageTexture.create_from_image(image)
	material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	material.texture_repeat = false
	return material


static func flat(hex: String) -> StandardMaterial3D:
	## One segmentation class: unshaded, unfogged, unlit, unshadowed.
	##
	## `disable_fog` is the field that makes this a measurement rather than a
	## picture. The contained profile runs 0.0016 of density with aerial
	## perspective at 0.30, and without this every class would arrive at the
	## film plane blended toward `#231F1A` by an amount that depends on how far
	## away it is - which is precisely the variable a coverage measure must not
	## have.
	var material := StandardMaterial3D.new()
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.albedo_color = Color(hex)
	material.disable_fog = true
	material.disable_receive_shadows = true
	return material


# --- Part E's probe ---------------------------------------------------------


static func _probed(material: StandardMaterial3D, probe: String) -> StandardMaterial3D:
	## `--track-probe=roughness=0.5` - one field at a time, over any variant.
	##
	## Part E asks for albedo, roughness, metallic and specular to be moved
	## separately and the cause documented. A scan that had to edit this file
	## between runs would be a scan whose runs were not comparable, which is the
	## argument `race2.track.WALL_CAP` already makes for its own env override.
	for part in probe.split(",", false):
		var text: String = str(part).strip_edges()
		var split := text.find("=")
		if split < 0:
			continue
		var key := text.substr(0, split).strip_edges()
		var value := text.substr(split + 1).strip_edges()
		match key:
			"albedo":
				material.albedo_color = Color(value)
			"roughness":
				material.roughness = value.to_float()
			"metallic":
				material.metallic = value.to_float()
			"specular":
				material.metallic_specular = value.to_float()
			"clearcoat":
				material.clearcoat = value.to_float()
				material.clearcoat_enabled = material.clearcoat > 0.0
			"clearcoat_roughness":
				material.clearcoat_roughness = value.to_float()
			_:
				push_error("race2_track_surface: unknown probe field '%s'" % key)
	return material
