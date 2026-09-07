extends RefCounted

## THE THREE COURSE LAYOUTS, as tables.
##
## Phase one of the sloped-course brief is a shape competition, not a materials
## competition, so all three layouts are described in exactly the same terms -
## a terrain config, a list of runs, a list of module anchors and a camera - and
## the blockout builder draws whichever it is handed. Nothing about the art
## direction differs between them; if one wins it is because its *shape* won.
##
##     A  CLIFF DESCENT     one long traverse across a mountain flank
##     B  ZIG-ZAG RACEWAY   switchback legs marching down a staircase of shelves
##     C  OPEN MOUNTAIN RUN a deep run straight at the viewer with a huge split
##
## ## What a run is
##
## A list of control points for `v2_track.build`, authored so that each run
## starts where the previous module hands off and ends where the next accepts.
## Read in order, the runs of a layout are one unbroken route from the start
## line to the finish - which is the brief's first selection criterion, and the
## only one that is checked by construction rather than by eye.
##
## ## Why the coordinate frame is what it is
##
## +Z is downhill and toward the camera; X is across the flank; the mountain
## falls away on +X into a gorge and rises on -X into a wall. Travel is
## therefore *always* +Z, whatever a layout does laterally, and a viewer who has
## learned the direction of travel in one shot has learned it for the whole
## course. That is worth more than any individual bend.

const MARBLE_RADIUS := 0.285
const HERO_SCALE := 1.0          # the full 1.88 clear channel
const BRANCH_SCALE := 0.82       # two abreast, for the split's two routes

const LAYOUTS := ["a", "b", "c"]


# --- A: CLIFF DESCENT -----------------------------------------------------
#
# One dominant diagonal. The course leaves a shoulder high on the left, crosses
# the whole flank to the right on a long descending arc, comes back across it
# on a technical curve, splits over the low shelf and the gorge mouth, and
# sprints out onto a promontory. Two lateral crossings, never a repeat.

const A_TERRAIN := {
	"top_y": 35.0, "z_top": -40.0, "grade": 0.56,
	"steps": [[-24.0, 3.6, 4.5], [-6.0, 5.2, 5.0], [14.0, 4.4, 5.0]],
	"left_at": 20.0, "left_span": 26.0, "left_rise": 15.0,
	"gorge_at": 6.0, "gorge_span": 26.0, "gorge_depth": 26.0,
	"crest_rise": 5.0, "crest_scale": 26.0,
	"centre_x": -2.0, "centre_z": -2.0,
	"edge_from": 62.0, "edge_to": 100.0, "edge_y": -78.0,
	"valley_below": -18.0, "cap_above": 34.0,
	"cut_depth": 3.0, "cut_inner": 3.4, "cut_reach": 9.0,
	"noise": 2.1, "cell": 2.2,
	"x_min": -88.0, "x_max": 88.0, "z_min": -104.0, "z_max": 96.0,
	"pads": [
		[-16.6, -32.6, 5.0, 6.0, 32.0],   # start shelf
		[12.6, -7.4, 4.6, 6.0, 16.8],     # obstacle terrace
		[-10.6, 8.2, 4.2, 6.0, 9.2],      # split promontory
		[8.4, 38.4, 8.0, 9.0, 0.6],       # finish plain
	],
}

const A_RUNS := [
	{"name": "launch", "role": "descent", "scale": HERO_SCALE,
		"bank_gain": 3.0, "bank_max": 22.0, "controls": [
		Vector3(-16.60, 33.20, -32.40), Vector3(-15.40, 32.30, -30.40),
		Vector3(-12.80, 30.20, -28.40), Vector3(-9.00, 28.40, -27.20),
		Vector3(-5.20, 27.30, -26.50), Vector3(-3.20, 26.85, -26.00)]},
	{"name": "sweep_a", "role": "long", "scale": HERO_SCALE,
		"bank_gain": 3.4, "bank_max": 26.0, "controls": [
		Vector3(-1.60, 26.30, -25.40), Vector3(2.80, 24.90, -24.20),
		Vector3(7.60, 23.20, -21.80), Vector3(11.40, 21.50, -18.00),
		Vector3(13.60, 19.90, -13.40), Vector3(13.40, 18.60, -9.40),
		Vector3(12.80, 17.90, -7.60)]},
	{"name": "sweep_b", "role": "long", "scale": HERO_SCALE,
		"bank_gain": 3.6, "bank_max": 28.0, "controls": [
		Vector3(12.00, 17.20, -5.60), Vector3(8.60, 16.20, -2.60),
		Vector3(3.20, 14.90, -0.20), Vector3(-2.80, 13.70, 0.90),
		Vector3(-8.20, 12.50, 1.60), Vector3(-11.60, 11.50, 3.80),
		Vector3(-11.40, 10.80, 6.60), Vector3(-10.80, 10.45, 7.70)]},
	{"name": "blue", "role": "branch", "scale": BRANCH_SCALE,
		"bank_gain": 3.2, "bank_max": 26.0, "controls": [
		Vector3(-11.50, 10.05, 9.20), Vector3(-14.60, 9.10, 12.40),
		Vector3(-17.20, 7.90, 16.60), Vector3(-16.40, 6.60, 20.80),
		Vector3(-13.20, 5.70, 23.80), Vector3(-9.80, 5.15, 25.60),
		Vector3(-8.40, 4.95, 26.30)]},
	{"name": "orange", "role": "branch", "scale": BRANCH_SCALE,
		"bank_gain": 3.8, "bank_max": 30.0, "controls": [
		Vector3(-9.70, 10.05, 9.20), Vector3(-5.80, 9.30, 11.60),
		Vector3(-1.40, 8.20, 14.20), Vector3(0.60, 7.00, 17.80),
		Vector3(-1.80, 5.90, 21.60), Vector3(-6.00, 5.20, 24.60),
		Vector3(-8.00, 4.95, 26.30)]},
	{"name": "final", "role": "sprint", "scale": HERO_SCALE,
		"bank_gain": 2.6, "bank_max": 18.0, "controls": [
		Vector3(-8.20, 4.55, 27.60), Vector3(-5.40, 3.90, 30.20),
		Vector3(-1.40, 3.10, 33.00), Vector3(3.00, 2.45, 35.60),
		Vector3(6.20, 2.10, 37.20), Vector3(7.60, 1.95, 37.90)]},
]

const A_NODES := {
	"start": Vector3(-17.20, 33.40, -33.60),
	"mix": Vector3(-3.20, 26.85, -26.00),
	"obstacle": Vector3(12.80, 17.90, -7.60),
	"split": Vector3(-10.80, 10.45, 7.70),
	"merge": Vector3(-8.20, 4.90, 26.60),
	"finish": Vector3(8.40, 1.85, 38.60),
}

const A_HERO := {"aim": Vector3(-1.0, 16.0, 1.0), "fov": 30.0,
	"elevation": 14.0, "azimuth": 26.0}


# --- B: ZIG-ZAG RACEWAY - THE SELECTED COURSE ------------------------------
#
# Switchbacks down a terraced mountain flank. Four legs, each with a different
# curve character, an obstacle at the second hairpin, a choice thrown right
# across the terrain and a viaduct sprint into the finish.
#
#     START      a shelf under the crest, 8 bays abreast
#       |        the plunge: 25 degrees, the steepest thing on the course
#     LEG 1      long fast right-hander, wide radius, into a tight hairpin
#     LEG 2      the long race straight, a gentle S, hairpin at the wall
#     OBSTACLE   a spinner corridor on the second terrace
#     LEG 3      one long sweep to the choice
#     SPLIT      blue: the long smooth inside arc
#                orange: out over the gorge on trestles, two hooks, shorter
#     MERGE      both routes compress into one channel
#     FINAL      a short steep pitch, then a viaduct sprint over the valley
#     FINISH     a mesa arena ten units above the valley floor
#
# The terrain is authored *with* the course rather than under it. `grade` is
# set to the legs' own average descent, so a leg neither digs into the hill nor
# climbs off it, and each step falls at a hairpin - which is where a terrace
# edge belongs, because that is where the course reverses.

const B_TERRAIN := {
	"top_y": 39.6, "z_top": -34.0, "grade": 0.45,
	"steps": [[-30.0, 5.2, 4.4], [-13.0, 2.2, 5.0], [1.5, 2.4, 5.0],
		[16.0, 2.2, 5.4], [32.0, 2.8, 6.0]],
	"left_at": 20.0, "left_span": 26.0, "left_rise": 17.0,
	"gorge_at": 15.0, "gorge_span": 24.0, "gorge_depth": 28.0,
	"crest_rise": 5.5, "crest_scale": 24.0,
	"centre_x": 1.0, "centre_z": 6.0,
	"edge_from": 58.0, "edge_to": 94.0, "edge_y": -82.0,
	"valley_below": -60.0, "cap_above": 34.0,
	"cut_depth": 2.8, "cut_inner": 3.2, "cut_reach": 8.0,
	# Cell 1.3 over a tighter footprint rather than 1.75 over a wider one.
	# Beyond about eighty units the massif has already faded to the valley
	# floor and the distant ranges carry the horizon, so the extra area was
	# buying nothing while the near ground - which fills a third of every
	# section shot - was reading as smooth clay.
	"noise": 2.3, "cell": 1.3,
	"x_min": -80.0, "x_max": 80.0, "z_min": -90.0, "z_max": 108.0,
	"pads": [
		[-19.4, -38.9, 6.6, 7.0, 37.2],   # start shelf
		[-8.6, 3.2, 5.0, 6.0, 16.4],      # obstacle terrace
		[6.0, 18.0, 4.6, 6.0, 9.8],       # choice promontory
		[24.2, 46.2, 11.0, 12.5, -2.4],   # finish mesa
	],
}

const B_RUNS := [
	{"name": "launch", "role": "descent", "scale": HERO_SCALE,
		"bank_gain": 2.6, "bank_max": 18.0, "controls": [
		Vector3(-17.00, 37.90, -33.60), Vector3(-16.20, 37.10, -32.30),
		Vector3(-14.80, 35.40, -31.00), Vector3(-12.40, 33.40, -29.80),
		Vector3(-9.40, 32.20, -29.00), Vector3(-6.80, 31.60, -28.50)]},
	{"name": "leg1", "role": "long", "scale": HERO_SCALE,
		"bank_gain": 3.6, "bank_max": 28.0, "controls": [
		Vector3(-6.80, 31.60, -28.50), Vector3(0.60, 30.20, -27.40),
		Vector3(6.20, 29.00, -26.20), Vector3(11.60, 27.60, -24.40),
		Vector3(16.00, 26.20, -21.80), Vector3(18.60, 24.90, -18.80),
		Vector3(18.80, 24.00, -16.00), Vector3(17.00, 23.50, -13.80),
		Vector3(14.00, 23.20, -12.60), Vector3(11.20, 23.15, -12.40)]},
	{"name": "leg2", "role": "long", "scale": HERO_SCALE,
		"bank_gain": 3.0, "bank_max": 22.0, "controls": [
		Vector3(11.20, 23.15, -12.40), Vector3(3.80, 22.20, -11.40),
		Vector3(-1.80, 21.20, -10.20), Vector3(-7.40, 20.20, -8.60),
		Vector3(-12.60, 19.40, -6.20), Vector3(-16.20, 18.60, -3.00),
		Vector3(-16.80, 17.90, 0.40), Vector3(-14.40, 17.50, 2.40),
		Vector3(-11.40, 17.20, 2.90), Vector3(-9.00, 17.05, 3.16),
		Vector3(-6.40, 16.90, 3.50)]},
	{"name": "leg3", "role": "long", "scale": HERO_SCALE,
		"bank_gain": 3.4, "bank_max": 26.0, "controls": [
		Vector3(-6.40, 16.90, 3.50), Vector3(-0.60, 16.00, 4.60),
		Vector3(5.40, 15.00, 6.20), Vector3(10.60, 13.90, 8.60),
		Vector3(13.60, 12.70, 11.80), Vector3(13.20, 11.70, 14.80),
		Vector3(10.40, 11.00, 16.80), Vector3(7.40, 10.70, 17.60),
		Vector3(6.00, 10.60, 17.80)]},
	{"name": "blue", "role": "branch", "scale": BRANCH_SCALE,
		"bank_gain": 3.0, "bank_max": 24.0, "controls": [
		Vector3(5.20, 10.40, 18.55), Vector3(-0.80, 9.30, 21.40),
		Vector3(-6.80, 8.50, 23.40), Vector3(-12.40, 7.60, 25.40),
		Vector3(-15.20, 6.70, 28.60), Vector3(-13.40, 5.90, 31.80),
		Vector3(-9.60, 5.40, 33.80), Vector3(-6.00, 5.18, 34.60),
		Vector3(-3.20, 5.00, 35.40), Vector3(-1.10, 4.90, 36.05)]},
	# The three tail heights marked below were 5.20, 5.18 and 5.00 as first
	# authored. Four control points inside half a unit of each other over
	# fourteen units of travel make a Catmull-Rom overshoot, and orange was the
	# only run of the nine that climbed: ten uphill samples, 86 to 95. A marble
	# arriving at orange[102] with 10 wu/s crawled the flat and stopped at
	# orange[114], which is where every orange-bound marble died.
	#
	# The fall from control 5 to control 9 is now spread linearly in horizontal
	# arc length, which makes the tail monotone at -0.049 - blue's own tail
	# grade. Every x and z is untouched, so the silhouette is unchanged; three
	# heights move, by at most 0.145. Kept in step with `sloped/layout.py`,
	# which is the physics' copy of this table.
	{"name": "orange", "role": "branch", "scale": BRANCH_SCALE,
		"bank_gain": 4.0, "bank_max": 32.0, "controls": [
		Vector3(6.90, 10.40, 18.55), Vector3(13.00, 9.20, 21.00),
		Vector3(18.40, 8.20, 23.60), Vector3(21.00, 7.20, 27.00),
		Vector3(19.40, 6.30, 30.60), Vector3(15.00, 5.60, 33.20),
		Vector3(10.00, 5.3456, 34.60), Vector3(5.60, 5.1300, 34.70),
		Vector3(3.20, 5.0069, 35.45), Vector3(1.10, 4.90, 36.05)]},
	{"name": "final", "role": "sprint", "scale": HERO_SCALE,
		"bank_gain": 2.2, "bank_max": 14.0, "controls": [
		Vector3(0.00, 4.85, 36.40), Vector3(2.60, 4.15, 37.60),
		Vector3(5.80, 3.30, 39.00), Vector3(9.20, 2.55, 40.40),
		Vector3(12.60, 1.95, 41.70), Vector3(15.80, 1.45, 42.90),
		Vector3(18.40, 1.12, 43.90), Vector3(19.80, 1.02, 44.40)]},
]

const B_NODES := {
	"start": Vector3(-18.60, 38.55, -37.20),
	"mix": Vector3(-5.60, 31.45, -28.35),
	"obstacle": Vector3(-9.00, 17.05, 3.16),
	"split": Vector3(6.00, 10.50, 18.00),
	"merge": Vector3(0.00, 4.88, 36.10),
	"finish": Vector3(24.20, 0.70, 46.20),
}

const B_HERO := {"aim": Vector3(1.0, 18.0, 6.0), "fov": 30.0,
	"elevation": 15.0, "azimuth": 22.0}


# --- C: OPEN MOUNTAIN RUN -------------------------------------------------
#
# Depth rather than width. The course comes almost straight at the viewer down
# a long open slope, crosses a gorge on an elevated span, and then throws its
# two branches an enormous distance apart across the low ground before pulling
# them back together for a straight finish.

const C_TERRAIN := {
	"top_y": 37.0, "z_top": -42.0, "grade": 0.44,
	"steps": [[-20.0, 4.0, 5.0], [2.0, 6.5, 5.5], [24.0, 4.5, 5.5]],
	"left_at": 22.0, "left_span": 26.0, "left_rise": 16.0,
	"gorge_at": 22.0, "gorge_span": 24.0, "gorge_depth": 24.0,
	"crest_rise": 5.0, "crest_scale": 26.0,
	"centre_x": 0.0, "centre_z": 4.0,
	"edge_from": 62.0, "edge_to": 100.0, "edge_y": -78.0,
	"valley_below": -16.0, "cap_above": 36.0,
	"cut_depth": 3.0, "cut_inner": 3.4, "cut_reach": 9.0,
	"noise": 2.0, "cell": 2.2,
	"x_min": -88.0, "x_max": 88.0, "z_min": -108.0, "z_max": 116.0,
	"pads": [
		[-2.0, -34.0, 5.0, 6.5, 33.4],
		[5.4, 14.6, 4.6, 6.0, 14.6],
		[-1.0, 23.2, 4.2, 6.0, 11.4],
		[0.6, 50.6, 8.5, 10.0, 0.2],
	],
}

const C_RUNS := [
	{"name": "launch", "role": "descent", "scale": HERO_SCALE,
		"bank_gain": 3.0, "bank_max": 22.0, "controls": [
		Vector3(-2.20, 33.60, -32.40), Vector3(-3.60, 31.60, -29.80),
		Vector3(-6.20, 29.60, -27.00), Vector3(-8.00, 28.30, -24.40),
		Vector3(-8.60, 27.75, -22.60)]},
	{"name": "slope", "role": "long", "scale": HERO_SCALE,
		"bank_gain": 3.0, "bank_max": 22.0, "controls": [
		Vector3(-8.80, 27.20, -21.00), Vector3(-8.20, 25.20, -16.00),
		Vector3(-6.20, 23.20, -11.00), Vector3(-3.20, 21.40, -6.00),
		Vector3(0.00, 20.00, -1.50), Vector3(1.60, 19.40, 1.00)]},
	{"name": "span", "role": "long", "scale": HERO_SCALE,
		"bank_gain": 2.6, "bank_max": 18.0, "controls": [
		Vector3(2.60, 19.00, 2.60), Vector3(4.20, 18.20, 6.00),
		Vector3(5.60, 17.20, 9.60), Vector3(6.00, 16.40, 13.00),
		Vector3(5.60, 15.95, 14.60)]},
	{"name": "approach", "role": "long", "scale": HERO_SCALE,
		"bank_gain": 3.2, "bank_max": 24.0, "controls": [
		Vector3(4.80, 15.40, 16.40), Vector3(2.60, 14.20, 19.40),
		Vector3(0.00, 13.10, 21.80), Vector3(-1.00, 12.55, 23.20)]},
	{"name": "blue", "role": "branch", "scale": BRANCH_SCALE,
		"bank_gain": 3.2, "bank_max": 26.0, "controls": [
		Vector3(-2.00, 12.15, 24.40), Vector3(-8.00, 10.50, 27.20),
		Vector3(-14.60, 8.40, 29.80), Vector3(-18.00, 6.40, 33.60),
		Vector3(-15.00, 4.90, 37.60), Vector3(-9.00, 4.10, 39.80),
		Vector3(-4.00, 3.85, 41.00)]},
	{"name": "orange", "role": "branch", "scale": BRANCH_SCALE,
		"bank_gain": 3.8, "bank_max": 30.0, "controls": [
		Vector3(0.00, 12.15, 24.40), Vector3(6.00, 10.30, 26.80),
		Vector3(12.60, 8.20, 29.60), Vector3(16.00, 6.20, 33.80),
		Vector3(13.00, 4.70, 37.80), Vector3(7.00, 4.00, 40.00),
		Vector3(2.40, 3.85, 41.00)]},
	{"name": "final", "role": "sprint", "scale": HERO_SCALE,
		"bank_gain": 2.4, "bank_max": 16.0, "controls": [
		Vector3(-0.60, 3.50, 42.20), Vector3(0.00, 2.60, 45.60),
		Vector3(0.40, 1.90, 48.60), Vector3(0.60, 1.60, 50.00)]},
]

const C_NODES := {
	"start": Vector3(-2.00, 34.00, -33.80),
	"mix": Vector3(-8.60, 27.75, -22.60),
	"obstacle": Vector3(5.60, 15.95, 14.60),
	"split": Vector3(-1.00, 12.55, 23.20),
	"merge": Vector3(-0.80, 3.80, 41.40),
	"finish": Vector3(0.60, 1.50, 51.00),
}

const C_HERO := {"aim": Vector3(-1.0, 16.0, 6.0), "fov": 30.0,
	"elevation": 15.0, "azimuth": 18.0}


static func table(key: String) -> Dictionary:
	## One layout, as a fresh mutable copy.
	##
	## The terrain config is deep-copied because the builder writes the bench
	## index back into it, and a GDScript `const` Dictionary is read-only. The
	## copy is also what keeps two builds in one process independent.
	match key:
		"a":
			return {"terrain": A_TERRAIN.duplicate(true), "runs": A_RUNS,
				"nodes": A_NODES, "hero": A_HERO, "title": "A  CLIFF DESCENT"}
		"b":
			return {"terrain": B_TERRAIN.duplicate(true), "runs": B_RUNS,
				"nodes": B_NODES, "hero": B_HERO,
				"title": "B  ZIG-ZAG RACEWAY"}
		"c":
			return {"terrain": C_TERRAIN.duplicate(true), "runs": C_RUNS,
				"nodes": C_NODES, "hero": C_HERO,
				"title": "C  OPEN MOUNTAIN RUN"}
	push_error("course_layout: unknown layout '%s'" % key)
	return table("a")
