extends RefCounted

## Stylised country marbles, generated in code. The comparison experiment only.
##
## Part 15 of the V1 brief asks one question and only one: does country
## identity make the marbles more appealing than plain colour? So this is
## built to answer that and not to become the racer system. There are five
## countries, they are drawn procedurally into a small image each, and
## nothing outside `--neon-countries` ever loads them.
##
## They are *flag-inspired materials*, not flags. A rectangular flag PNG
## stretched over a sphere is the thing the brief explicitly rules out, and it
## deserves to be: the equirectangular map compresses everything towards the
## poles, so a wrapped flag arrives as a smear with a pinched top and bottom.
## What survives that projection is bands of latitude and a motif sitting on
## the equator - which is, conveniently, exactly what a designed marble looks
## like. So each of these is the flag reduced to those two ingredients:
##
##     India      three latitude bands, a fine navy ring on the equator
##     Japan      white body, one clean red disc
##     Brazil     green body, a yellow lozenge, a blue disc inside it
##     USA        red and white latitude bands, a navy field with stars
##     Germany    three latitude bands
##
## Everything is a pure function of the country index: no randomness, no
## files, no imports. Two runs generate the same five images.

# Wide enough that a band edge is clean on a marble filling a couple of
# hundred pixels, small enough that generating five of them in GDScript is
# not something anybody notices.
const WIDTH := 384
const HEIGHT := 192

const NAMES: Array[String] = ["india", "japan", "brazil", "usa", "germany"]

# --- palettes -------------------------------------------------------------

const SAFFRON := Color(0.965, 0.545, 0.100)
const INDIA_GREEN := Color(0.075, 0.533, 0.278)
const NAVY := Color(0.024, 0.145, 0.478)
const OFF_WHITE := Color(0.965, 0.965, 0.960)
const JAPAN_RED := Color(0.737, 0.098, 0.208)
const BRAZIL_GREEN := Color(0.086, 0.541, 0.239)
const BRAZIL_YELLOW := Color(0.996, 0.855, 0.153)
const BRAZIL_BLUE := Color(0.024, 0.169, 0.478)
const USA_RED := Color(0.698, 0.132, 0.203)
const GERMAN_BLACK := Color(0.070, 0.070, 0.074)
const GERMAN_RED := Color(0.867, 0.106, 0.141)
const GERMAN_GOLD := Color(1.000, 0.808, 0.000)

var _textures: Dictionary = {}


func country_count() -> int:
	return NAMES.size()


func name_of(index: int) -> String:
	return NAMES[index % NAMES.size()]


func texture(index: int) -> Texture2D:
	var key := name_of(index)
	if _textures.has(key):
		return _textures[key]
	var image := Image.create(WIDTH, HEIGHT, false, Image.FORMAT_RGBA8)
	for y in HEIGHT:
		var v := (float(y) + 0.5) / float(HEIGHT)
		for x in WIDTH:
			var u := (float(x) + 0.5) / float(WIDTH)
			image.set_pixel(x, y, _sample(key, u, v))
	var made := ImageTexture.create_from_image(image)
	_textures[key] = made
	return made


func _sample(key: String, u: float, v: float) -> Color:
	match key:
		"india":
			return _india(u, v)
		"japan":
			return _japan(u, v)
		"brazil":
			return _brazil(u, v)
		"usa":
			return _usa(u, v)
	return _germany(u, v)


# --- the five -------------------------------------------------------------

func _bands(v: float, colors: Array) -> Color:
	var index := int(clampf(v * float(colors.size()), 0.0, float(colors.size() - 1)))
	return colors[index]


func _disc(u: float, v: float, centre_u: float, radius: float) -> float:
	## Distance from a point on the equator, corrected for the projection.
	##
	## Longitude is compressed by cos(latitude), so a disc measured in raw uv
	## comes out as an oval. Scaling the u difference by the same factor is
	## what makes a red circle on a Japanese marble round.
	var latitude := (v - 0.5) * PI
	var du := absf(u - centre_u)
	du = minf(du, 1.0 - du) * cos(latitude)
	var dv := (v - 0.5) * 0.5
	return sqrt(du * du + dv * dv) / maxf(radius, 0.001)


func _india(u: float, v: float) -> Color:
	var base := _bands(v, [SAFFRON, OFF_WHITE, INDIA_GREEN])
	var ring := _disc(u, v, 0.5, 0.115)
	# A ring rather than a filled disc: the emblem is a wheel, and at marble
	# scale an outline reads as one where twenty-four spokes read as a blob.
	if ring < 1.0 and ring > 0.74:
		return NAVY
	if ring < 0.18:
		return NAVY
	return base


func _japan(u: float, v: float) -> Color:
	if _disc(u, v, 0.5, 0.30) < 1.0:
		return JAPAN_RED
	return OFF_WHITE


func _brazil(u: float, v: float) -> Color:
	# A lozenge, measured the same corrected way as a disc so it stays a
	# diamond rather than a kite.
	var latitude := (v - 0.5) * PI
	var du := absf(u - 0.5)
	du = minf(du, 1.0 - du) * cos(latitude) / 0.40
	var dv := absf(v - 0.5) / 0.34
	if du + dv < 1.0:
		if _disc(u, v, 0.5, 0.145) < 1.0:
			return BRAZIL_BLUE
		return BRAZIL_YELLOW
	return BRAZIL_GREEN


func _usa(u: float, v: float) -> Color:
	var stripe := _bands(v, [
		USA_RED, OFF_WHITE, USA_RED, OFF_WHITE, USA_RED, OFF_WHITE, USA_RED])
	# The canton, on one face only, with a lattice of stars punched out of it.
	var latitude := (v - 0.5) * PI
	var du := absf(u - 0.30)
	du = minf(du, 1.0 - du) * cos(latitude)
	if du < 0.115 and v > 0.24 and v < 0.50:
		var star_u := fmod(u * 26.0, 1.0)
		var star_v := fmod(v * 16.0, 1.0)
		if absf(star_u - 0.5) + absf(star_v - 0.5) < 0.30:
			return OFF_WHITE
		return NAVY
	return stripe


func _germany(u: float, v: float) -> Color:
	return _bands(v, [GERMAN_BLACK, GERMAN_RED, GERMAN_GOLD])
