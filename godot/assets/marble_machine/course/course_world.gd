extends RefCounted

## The world the course is installed in: sky, atmosphere, distant ranges, keys.
##
## **The numbers moved.** Everything this file used to hold as constants - the
## dusk sky, the fog, the ACES grade, the glow curve, the six-light rig, three
## mountain ranges, the lit structures, the horizon band and the cloud banks -
## is now `environment/profiles/alpine_neon.json`, transcribed field for field,
## and the V21 readability pass is the `contrast.v21` overlay inside it. What
## is left here is the seam: `course_scene.gd` still calls `World.build_*`, and
## those calls now resolve an `EnvironmentProfile` and hand it to
## `environment_builder.gd`.
##
## Keeping the seam rather than deleting it is deliberate. Four scenes and a
## dozen proof tools reach the world through these three functions, and a
## profile system whose first act is to break every caller is not a framework.
##
## ## Two keys, still
##
## The one finding from the tower build that transfers unchanged, and the
## reason the rig is keyed by name rather than by index: a three-quarter front
## key makes moulded pearl read and flattens rock into paper, so the course
## gets `Key` on cull mask 1 and the world gets `WorldKey` on mask 2.
## `course_terrain` and everything the builder makes are put on layer 2; the
## track, the modules and the racers stay on layer 1. A profile can recolour
## and re-aim those lights. It cannot renumber the masks out from under that
## split, because each mask sits in the profile beside the light it belongs to,
## so a theme that moves one moves the other in the same file.

const Profile := preload(
	"res://assets/marble_machine/environment/environment_profile.gd")
const Builder := preload(
	"res://assets/marble_machine/environment/environment_builder.gd")

const WORLD_LAYER := 2

const CONTRAST_V21 := "v21"


static func profile(contrast := "", id := "") -> Dictionary:
	## The resolved profile a caller that has not resolved one already gets.
	return Profile.resolve(id, contrast)


static func _resolved(given: Dictionary, contrast: String) -> Dictionary:
	return given if not given.is_empty() else profile(contrast)


static func build_environment(no_glow: bool, contrast := "",
		given: Dictionary = {}) -> Environment:
	return Builder.environment(_resolved(given, contrast), no_glow)


static func build_lights(parent: Node3D, contrast := "",
		given: Dictionary = {}) -> void:
	Builder.lights(parent, _resolved(given, contrast))


static func build(palette, given: Dictionary = {}) -> Node3D:
	return Builder.backdrop(palette, _resolved(given, ""))


static func assign_layer(node: Node) -> void:
	Builder.assign_layer(node)
