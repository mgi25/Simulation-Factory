extends RefCounted
## One racer's visible body, built so that **real** rotation becomes readable.
##
## The problem this solves is not a physics problem. `sloped_race_scene.gd`
## already sets `node.quaternion` from the replay every frame, and the replay
## already records what PyBullet did: in the mixer the eight marbles turn at a
## median 0.7-5.5 rad/s and peak near 26 rad/s, and on the descent they pass 90
## rad/s. None of it is visible, because the body drawn is a uniformly coloured
## sphere and a uniformly coloured sphere is invariant under every rotation.
## The marble is not sliding. It is spinning, and the picture cannot say so.
##
## So the fix is a *surface* fix and nothing else. Nothing here reads velocity,
## nothing here holds a clock, and nothing here can turn: the marker is baked
## into the albedo map of the racer's own material, which lives in the mesh's
## local UV space and is therefore carried by the node's transform exactly. If
## the replay quaternion stops changing, the marker stops. There is no path by
## which this file could invent a spin the solver did not produce.
##
## **The map is a multiplier, not a repaint.** Godot multiplies `albedo_color`
## by `albedo_texture`, so a map that is white leaves the shipped racer colour
## bit-for-bit as it was. Every appearance here is white everywhere except on
## the marker, which means the body hue, saturation and value of all eight
## racers are untouched and only the marker region is tinted. `solid` builds no
## texture at all and is therefore the shipped appearance itself, not a
## reconstruction of it.
##
## **The marker is greyscale, so all eight racers share one texture.** A grey
## multiplier darkens without moving hue, which is both what a swirl inside a
## candy marble looks like and the reason this costs one 512x256 image for the
## whole field rather than eight. Node count, mesh count and material count are
## all exactly what the plain sphere cost.
##
## Future country skins are the same mechanism with the base colour moved into
## the map: set `albedo_color` to white, bake the flag into the image, and the
## flag inherits the replay quaternion for free because the flag is the
## surface. That is why the marker is a texture rather than child geometry.

const APPEARANCES := ["solid", "ribbon", "crescent", "meridian"]

## Where the marker sits on the body, in the marble's own frame.
##
## The normals are deliberately not axis-aligned. A marble is dropped with an
## identity orientation, so a band whose normal is local +Y would start as a
## horizontal line on every racer in the bay - eight identical marbles wearing
## the same stripe at the same angle, which reads as decoration applied to the
## picture rather than as a property of each ball.
const RIBBON_NORMAL := Vector3(0.44, 0.84, 0.31)
const MERIDIAN_NORMAL := Vector3(-0.52, 0.30, 0.80)
const CRESCENT_AXIS := Vector3(0.36, 0.58, -0.73)

## Band half-width as |dot(p, n)|, i.e. the sine of the half-angle.
const BAND_HALF := 0.085          # ~4.9 deg either side of the great circle
const MERIDIAN_HALF := 0.055      # the second, quieter line
const MERIDIAN_TILT := 0.62       # cos of the small circle's polar angle

## The crescent: a cap with a second, offset cap bitten out of it.
const CRESCENT_COS := 0.80        # cap reaches ~37 deg from its axis
const CRESCENT_BITE := Vector3(0.10, 0.66, -0.74)
const CRESCENT_BITE_COS := 0.855

## How dark the marker is, as a multiplier on the racer's own colour.
##
## 0.52 is the shallowest value that still reads at 270x480 and the deepest
## that still reads as the marble's own colour rather than as a black mark
## drawn on it. It is a multiplier, so it is the same *ratio* on all eight
## bodies and cannot push any of them to a different hue.
const MARKER_TINT := 0.52

## The soft edge, in the same |dot| units as the widths above.
##
## A hard edge on a ten-pixel ball crawls: the band's boundary lands on a
## different pixel each frame and the eye reads the shimmer rather than the
## turn. The ramp is about one texel at 512 wide and costs nothing.
const EDGE_SOFT := 0.016

const TEXTURE_WIDTH := 512
const TEXTURE_HEIGHT := 256

static var _skins: Dictionary = {}


static func direction(u: float, v: float) -> Vector3:
	## The point on the unit sphere that Godot's `SphereMesh` gives this UV.
	##
	## Verified against the engine rather than assumed - see
	## `scripts/sphere_uv_check.gd`, which fails if a Godot release ever moves
	## the convention out from under the maps built here.
	return Vector3(sin(TAU * u) * sin(PI * v), cos(PI * v),
		cos(TAU * u) * sin(PI * v))


static func _band(point: Vector3, normal: Vector3, half: float) -> float:
	## 1.0 on the great circle perpendicular to `normal`, 0.0 off the band.
	var distance: float = absf(point.dot(normal.normalized()))
	return 1.0 - smoothstep(half, half + EDGE_SOFT, distance)


static func _ring(point: Vector3, normal: Vector3, tilt: float,
		half: float) -> float:
	## The same, for a *small* circle at `tilt` = cos of its polar angle.
	var distance: float = absf(point.dot(normal.normalized()) - tilt)
	return 1.0 - smoothstep(half, half + EDGE_SOFT, distance)


static func _cap(point: Vector3, axis: Vector3, reach: float) -> float:
	## 1.0 inside the spherical cap about `axis`, 0.0 outside it.
	return smoothstep(reach - EDGE_SOFT, reach + EDGE_SOFT,
		point.dot(axis.normalized()))


static func coverage(appearance: String, point: Vector3) -> float:
	## How much marker is at this point of the body, in 0..1.
	##
	## One pure function of a direction in the marble's own frame. It is the
	## whole of the appearance: there is no second term anywhere that depends
	## on time, on the frame index, or on any part of the replay.
	match appearance:
		"solid":
			return 0.0
		"ribbon":
			# One thin great circle. Honest about its own limit: a marble
			# turning exactly about RIBBON_NORMAL moves this band nowhere.
			return _band(point, RIBBON_NORMAL, BAND_HALF)
		"crescent":
			# A cap with a bite out of it, so the mark has a direction as well
			# as a position and a roll about its own axis still shows.
			return clampf(_cap(point, CRESCENT_AXIS, CRESCENT_COS)
				- _cap(point, CRESCENT_BITE, CRESCENT_BITE_COS), 0.0, 1.0)
		"meridian":
			# A great circle plus a small circle about a second axis. No
			# rotation leaves both of them stationary, which is what makes
			# this the one that never goes quiet.
			return clampf(_band(point, RIBBON_NORMAL, BAND_HALF)
				+ _ring(point, MERIDIAN_NORMAL, MERIDIAN_TILT, MERIDIAN_HALF),
				0.0, 1.0)
	push_error("racer_visual: unknown appearance '%s'" % appearance)
	return 0.0


static func skin_image(appearance: String) -> Image:
	## The multiplier map: white off the marker, MARKER_TINT on it.
	var image := Image.create(TEXTURE_WIDTH, TEXTURE_HEIGHT, true,
		Image.FORMAT_RGB8)
	for y in TEXTURE_HEIGHT:
		# Texel centres, so the top row is the pole's neighbourhood rather
		# than the pole itself and the map has no degenerate first row.
		var v: float = (float(y) + 0.5) / float(TEXTURE_HEIGHT)
		for x in TEXTURE_WIDTH:
			var u: float = (float(x) + 0.5) / float(TEXTURE_WIDTH)
			var amount := coverage(appearance, direction(u, v))
			var level: float = lerpf(1.0, MARKER_TINT, amount)
			image.set_pixel(x, y, Color(level, level, level))
	return image


static func skin(appearance: String) -> ImageTexture:
	## One texture for the whole field, built once and shared by all eight.
	if appearance == "solid":
		return null
	if _skins.has(appearance):
		return _skins[appearance]
	var image := skin_image(appearance)
	image.generate_mipmaps()
	var texture := ImageTexture.create_from_image(image)
	_skins[appearance] = texture
	return texture


static func material(base: StandardMaterial3D,
		appearance: String) -> StandardMaterial3D:
	## The racer's shipped material, with the marker map on it and nothing else.
	##
	## `solid` returns the palette's own material object untouched, so the
	## default appearance is not merely equal to the shipped one - it *is* the
	## shipped one, and no future edit here can drift it.
	if appearance == "solid":
		return base
	var skinned: StandardMaterial3D = base.duplicate()
	skinned.albedo_texture = skin(appearance)
	# Anisotropic, because a rolling marble presents most of its band at a
	# grazing angle and trilinear alone turns the far side of it into mush.
	skinned.texture_filter = \
		BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC
	return skinned


static func mesh(radius: float) -> SphereMesh:
	## Exactly the body `sloped_race_scene.gd` has always drawn.
	var sphere := SphereMesh.new()
	sphere.radius = radius
	sphere.height = radius * 2.0
	sphere.radial_segments = 32
	sphere.rings = 16
	return sphere


static func build(base: StandardMaterial3D, radius: float, node_name: String,
		appearance: String) -> MeshInstance3D:
	## One racer: one mesh, one material, no children.
	var node := MeshInstance3D.new()
	node.name = node_name
	node.mesh = mesh(radius)
	node.material_override = material(base, appearance)
	node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	return node
