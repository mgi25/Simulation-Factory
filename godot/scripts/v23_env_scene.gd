extends "res://scripts/sloped_race_scene.gd"

const Env := preload("res://assets/marble_machine/course/course_env.gd")

## THE V23 ENVIRONMENT LAB, over the locked V22.1 race.
##
## A subclass of the production race scene and an edit to nothing. The course is
## the course that shipped, the replay is the locked `race_5432`, the camera
## comes from the same solved track, the start contract is the same file and the
## edit map is the same edit map - so a frame taken here at output second 13.6 is
## the frame V22.1 delivers at 13.6, photographed in a different evening.
##
## All this file does is call `course_env.apply` after the parent has finished
## building, and print what it changed.
##
## ## Why a subclass rather than a flag through `course_scene`
##
## `course_scene.gd` is the parent of the layout proof, the hero build and this
## race, and its `_ready` is the one place the palette, the world, the light rig
## and the machine are all in scope. Threading an `--env=` through it would be
## four lines and would put a V23 decision inside a file that three earlier labs
## are photographed from. A subclass reaches exactly the same objects - the
## parent leaves `_palette`, `_table` and every named node in the tree - and
## reaches them from the one file that has a V23 opinion.
##
## The parent is therefore byte-identical on this branch, which is the property
## `tests/test_sloped_v23_env.py` checks: a render with no `--env=` flag is the
## V22.1 picture, and a render with one is the same geometry under a new sky.
##
## Usage, after `--`: everything `sloped_race_scene` takes, plus
##
##     --env=NAME    one of `course_env.names()`; empty is V22.1 unchanged


func _ready() -> void:
	super()
	var options := _options()
	var name := str(options.get("env", ""))
	if name.is_empty():
		print("env: no profile, V22.1 unchanged")
		return
	# `_table["terrain"]` rather than the machine's own copy. The two differ by
	# the bench index, which `course_machine.build` writes into its copy on the
	# way past - and nothing a profile sites needs it: every added form stands
	# beyond the gorge lip or below the valley floor, and both of those come
	# from the layout constants rather than from the racing line.
	var report := Env.apply(self, _palette, name, _table["terrain"])
	if str(report.get("profile", "")).is_empty():
		return
	print("env: %s - %s" % [report["title"], report.get("note", "")])
	print("    %d environment fields, %d lights, %d practicals, %d materials"
		% [int(report.get("environment", 0)), int(report.get("lights", 0)),
			int(report.get("practicals", 0)), int(report.get("materials", 0))])
	var ranges: Dictionary = report.get("ranges", {})
	for group in ranges:
		var row: Dictionary = ranges[group]
		print("    range %-10s %d kept, %d dropped"
			% [str(group), int(row["kept"]), int(row["dropped"])])
	print("    %d haze changes, %d beacons, features: %s"
		% [int(report.get("haze", 0)), int(report.get("dressing", 0)),
			", ".join(report.get("features", PackedStringArray()))])
