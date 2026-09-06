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


# --- B: ZIG-ZAG RACEWAY ---------------------------------------------------
#
# Switchbacks down a staircase of shelves. Four long legs alternating across
# the flank, each with its own hairpin, the obstacle sitting mid-leg and the
# split taken at the end of the third. The longest of the three by a wide
# margin, and the one whose legs are most obviously *straights*.

const B_TERRAIN := {
	"top_y": 35.6, "z_top": -38.0, "grade": 0.40,
	"steps": [[-27.0, 3.0, 4.0], [-17.0, 3.4, 4.0], [-6.0, 3.6, 4.0],
		[6.0, 3.8, 4.5], [19.0, 3.6, 4.5]],
	"left_at": 20.0, "left_span": 26.0, "left_rise": 15.0,
	"gorge_at": 19.0, "gorge_span": 24.0, "gorge_depth": 24.0,
	"crest_rise": 5.0, "crest_scale": 24.0,
	"centre_x": 0.0, "centre_z": -4.0,
	"edge_from": 62.0, "edge_to": 100.0, "edge_y": -78.0,
	"valley_below": -14.0, "cap_above": 34.0,
	"cut_depth": 3.0, "cut_inner": 3.4, "cut_reach": 9.0,
	"noise": 1.9, "cell": 2.2,
	"x_min": -88.0, "x_max": 88.0, "z_min": -104.0, "z_max": 96.0,
	"pads": [
		[-15.6, -30.4, 4.6, 6.0, 32.2],
		[-1.0, -14.8, 4.4, 6.0, 20.4],
		[14.2, 4.8, 4.4, 6.0, 10.4],
		[4.6, 32.0, 7.5, 9.0, 0.4],
	],
}

const B_RUNS := [
	{"name": "launch", "role": "descent", "scale": HERO_SCALE,
		"bank_gain": 3.0, "bank_max": 22.0, "controls": [
		Vector3(-15.40, 33.20, -30.00), Vector3(-13.00, 32.20, -29.20),
		Vector3(-9.00, 31.00, -28.60), Vector3(-4.60, 30.10, -28.20),
		Vector3(-2.00, 29.70, -28.00)]},
	{"name": "leg1", "role": "long", "scale": HERO_SCALE,
		"bank_gain": 3.2, "bank_max": 24.0, "controls": [
		Vector3(0.60, 29.30, -27.80), Vector3(5.60, 28.30, -27.10),
		Vector3(10.60, 27.10, -25.80), Vector3(14.20, 25.90, -23.60),
		Vector3(15.60, 25.00, -21.20), Vector3(15.20, 24.20, -18.60),
		Vector3(12.80, 23.55, -16.80), Vector3(9.60, 23.20, -16.10)]},
	{"name": "leg2", "role": "long", "scale": HERO_SCALE,
		"bank_gain": 3.2, "bank_max": 24.0, "controls": [
		Vector3(6.00, 22.70, -15.60), Vector3(0.00, 21.70, -14.90),
		Vector3(-6.00, 20.70, -13.70), Vector3(-11.60, 19.70, -11.90),
		Vector3(-14.80, 18.90, -9.60), Vector3(-15.40, 18.10, -6.80),
		Vector3(-13.40, 17.40, -4.80), Vector3(-10.00, 16.95, -4.00)]},
	{"name": "leg3", "role": "long", "scale": HERO_SCALE,
		"bank_gain": 3.4, "bank_max": 26.0, "controls": [
		Vector3(-6.20, 16.40, -3.40), Vector3(0.40, 15.20, -2.20),
		Vector3(6.80, 13.90, -0.40), Vector3(12.00, 12.60, 2.20),
		Vector3(13.80, 11.90, 4.20), Vector3(14.20, 11.55, 5.40)]},
	{"name": "blue", "role": "branch", "scale": BRANCH_SCALE,
		"bank_gain": 3.2, "bank_max": 26.0, "controls": [
		Vector3(13.80, 11.15, 6.60), Vector3(12.40, 10.00, 10.00),
		Vector3(8.20, 8.60, 13.20), Vector3(2.40, 7.50, 15.20),
		Vector3(-2.40, 6.85, 15.90), Vector3(-4.40, 6.55, 15.80)]},
	{"name": "orange", "role": "branch", "scale": BRANCH_SCALE,
		"bank_gain": 3.9, "bank_max": 30.0, "controls": [
		Vector3(14.80, 11.15, 6.60), Vector3(16.60, 9.80, 10.20),
		Vector3(14.00, 8.00, 14.80), Vector3(8.00, 6.90, 17.80),
		Vector3(1.00, 6.50, 17.90), Vector3(-3.00, 6.60, 16.30),
		Vector3(-4.60, 6.55, 15.80)]},
	{"name": "final", "role": "sprint", "scale": HERO_SCALE,
		"bank_gain": 2.6, "bank_max": 18.0, "controls": [
		Vector3(-4.40, 6.15, 17.00), Vector3(-2.20, 4.90, 21.00),
		Vector3(0.60, 3.60, 25.00), Vector3(3.00, 2.60, 28.60),
		Vector3(4.00, 2.20, 30.60)]},
]

const B_NODES := {
	"start": Vector3(-16.00, 33.40, -31.20),
	"mix": Vector3(-2.00, 29.70, -28.00),
	"obstacle": Vector3(-1.00, 21.70, -14.90),
	"split": Vector3(14.20, 11.55, 5.40),
	"merge": Vector3(-4.50, 6.50, 15.80),
	"finish": Vector3(4.70, 2.05, 31.80),
}

const B_HERO := {"aim": Vector3(0.0, 17.0, -1.0), "fov": 30.0,
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
