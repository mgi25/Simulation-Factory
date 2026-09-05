extends RefCounted

## The country experiment: a badge above a plain marble, not a flag wrapped
## round one.
##
## The V1 prototype tried the wrap and reported honestly that it fails. A flag
## is a rectangle and a marble is a sphere, so an equirectangular map pinches
## everything towards the poles; worse, a rolling sphere spends half its time
## showing the back of the pattern, so whatever survives the projection is
## visible half the time at best. Germany and Japan came through it - one
## motif, high contrast - and India and the USA went to mush.
##
## The brief rules the wrap out and asks for a badge instead, which is also
## what the concept sheet's own note suggests. So this file builds the two
## badge candidates it names and nothing else:
##
##     FLAG   a circular flag plate in a dark bezel, over a three-letter code
##     CODE   the three-letter code alone, on a plate in the country's colour
##
## Both ride *above* the marble on a billboard, which is the only place a
## label on a rolling sphere can live. The marble underneath keeps a single
## country-inspired hue - identity is supposed to come from the badge, and a
## body that carried the whole flag would be the thing the brief rules out
## wearing a different name.
##
## `tools/neon_proof.py --countries` renders the same instant three ways -
## numbers, flags, codes - so the comparison differs in exactly one thing, and
## writes each at full size and at phone size, because the question is not
## whether a flag is legible but whether it is legible on a phone.

# The five the brief names, in order, with the hue each marble's body takes.
#
# One hue per country rather than a scheme: these are the *marbles*, they have
# to stay separable from each other in a pile-up of sixteen, and five bodies
# each carrying two or three national colours would be five marbles nobody can
# tell apart at forty pixels.
const COUNTRIES := [
	{"code": "IND", "body": Color(0.960, 0.545, 0.145)},   # saffron
	{"code": "JPN", "body": Color(0.930, 0.930, 0.945)},   # white
	{"code": "BRA", "body": Color(0.115, 0.640, 0.290)},   # green
	{"code": "USA", "body": Color(0.145, 0.265, 0.640)},   # navy
	{"code": "GER", "body": Color(0.900, 0.740, 0.155)},   # gold
]

# The plate, in pixels. Generated rather than loaded: a PNG per country would
# be five binaries in the repository for an experiment whose whole output is a
# verdict, and a generated one cannot go missing.
const PLATE := 128

var _textures := {}


func country_count() -> int:
	return COUNTRIES.size()


func code_of(index: int) -> String:
	return str((COUNTRIES[index % COUNTRIES.size()] as Dictionary)["code"])


func body_of(index: int) -> Color:
	return (COUNTRIES[index % COUNTRIES.size()] as Dictionary)["body"]


func plate(index: int) -> ImageTexture:
	## One circular flag plate, as a texture with a transparent surround.
	var key := index % COUNTRIES.size()
	if _textures.has(key):
		return _textures[key]

	var image := Image.create(PLATE, PLATE, false, Image.FORMAT_RGBA8)
	image.fill(Color(0, 0, 0, 0))
	var centre := float(PLATE) * 0.5
	var radius := centre - 3.0
	for y in PLATE:
		for x in PLATE:
			var dx := float(x) + 0.5 - centre
			var dy := float(y) + 0.5 - centre
			var distance := sqrt(dx * dx + dy * dy)
			if distance > radius:
				continue
			# A dark bezel round the outside, so the plate has an edge against
			# a pale deck as well as against a dark room.
			if distance > radius - 9.0:
				image.set_pixel(x, y, Color(0.075, 0.085, 0.105, 1.0))
				continue
			image.set_pixel(x, y, _flag_pixel(key,
				(float(x) + 0.5) / float(PLATE),
				(float(y) + 0.5) / float(PLATE)))

	var texture := ImageTexture.create_from_image(image)
	_textures[key] = texture
	return texture


func _flag_pixel(key: int, u: float, v: float) -> Color:
	## The flag itself, drawn from a handful of shapes.
	##
	## Simplified on purpose and by the same rule each time: keep the bands and
	## the one motif, drop everything smaller than the plate can hold. The
	## point of the experiment is to find out whether even that survives at
	## badge size, and a faithful flag that is unreadable answers a different
	## question than a legible one that is not faithful.
	match key:
		0:  # India: three bands and the wheel, as a ring.
			var ring := Vector2(u - 0.5, v - 0.5).length()
			if v < 0.36:
				return Color(1.00, 0.60, 0.20)
			if v > 0.64:
				return Color(0.075, 0.53, 0.28)
			if ring > 0.085 and ring < 0.125:
				return Color(0.05, 0.15, 0.45)
			return Color(0.97, 0.97, 0.97)
		1:  # Japan
			if Vector2(u - 0.5, v - 0.5).length() < 0.24:
				return Color(0.85, 0.10, 0.16)
			return Color(0.97, 0.97, 0.97)
		2:  # Brazil: field, diamond, disc.
			if Vector2(u - 0.5, v - 0.5).length() < 0.17:
				return Color(0.10, 0.24, 0.55)
			if absf(u - 0.5) + absf(v - 0.5) < 0.40:
				return Color(1.00, 0.87, 0.10)
			return Color(0.05, 0.53, 0.25)
		3:  # USA: stripes and a plain canton.
			if u < 0.42 and v < 0.42:
				return Color(0.10, 0.20, 0.50)
			return Color(0.80, 0.12, 0.18) if int(v * 7.0) % 2 == 0 \
				else Color(0.97, 0.97, 0.97)
		_:  # Germany
			if v < 0.36:
				return Color(0.09, 0.09, 0.10)
			if v > 0.64:
				return Color(0.98, 0.80, 0.10)
			return Color(0.83, 0.11, 0.14)


func plate_plain(index: int) -> ImageTexture:
	## The code-only candidate's plate: the country's own colour, no flag.
	##
	## Same size and same bezel as the flag plate, so the two candidates differ
	## in the graphic and in nothing else. The text is drawn by a `Label3D` on
	## top rather than into the image, because a font rasterised at a hundred
	## and twenty-eight pixels and then scaled to forty is not what a viewer
	## would see in the shipped thing.
	var key := 100 + index % COUNTRIES.size()
	if _textures.has(key):
		return _textures[key]

	var body := body_of(index)
	var image := Image.create(PLATE, PLATE, false, Image.FORMAT_RGBA8)
	image.fill(Color(0, 0, 0, 0))
	var centre := float(PLATE) * 0.5
	var radius := centre - 3.0
	for y in PLATE:
		for x in PLATE:
			var dx := float(x) + 0.5 - centre
			var dy := float(y) + 0.5 - centre
			var distance := sqrt(dx * dx + dy * dy)
			if distance > radius:
				continue
			if distance > radius - 9.0:
				image.set_pixel(x, y, Color(0.075, 0.085, 0.105, 1.0))
			else:
				# Dark enough for white text to sit on it and light enough to
				# find against a pale deck. The first version used a fifth of
				# the body colour and the plates vanished into the bowl, which
				# would have made the comparison a comparison of one candidate.
				image.set_pixel(x, y, Color(body.r * 0.42, body.g * 0.42,
					body.b * 0.42, 1.0))

	var texture := ImageTexture.create_from_image(image)
	_textures[key] = texture
	return texture
