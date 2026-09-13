extends "res://scripts/sloped_race_render.gd"

const EnvScene := preload("res://scripts/v23_env_scene.gd")

## The V23 lab's renderer: `sloped_race_render.gd` with one line changed.
##
## Every mode, every flag, the warm-up count, the two-draw still and the
## output-frame clock are the parent's and are inherited rather than copied - so
## a lab clip and a production clip are the same renderer, and a difference
## between two frames of them is a difference in the scene rather than in how
## the frame was taken.
##
## The one line is which scene goes in the viewport. `_build_viewport` is
## overridden whole because the parent's version is where the scene is made; the
## body below is identical to it except for the class it instances.
##
## Usage, after `--`: everything `sloped_race_render` takes, plus `--env=NAME`,
## which the scene reads for itself.


func _build_viewport() -> void:
	_viewport = SubViewport.new()
	_viewport.name = "RenderTarget"
	_viewport.size = Vector2i(_width, _height)
	_viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	_viewport.transparent_bg = false
	_viewport.msaa_3d = int(ProjectSettings.get_setting(
		"rendering/anti_aliasing/quality/msaa_3d", Viewport.MSAA_DISABLED))
	_viewport.own_world_3d = true
	_viewport.handle_input_locally = false
	add_child(_viewport)

	_scene = EnvScene.new()
	_scene.name = "SlopedRace"
	_viewport.add_child(_scene)
