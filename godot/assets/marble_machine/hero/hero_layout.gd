extends RefCounted

## The seven-stage machine's dimensions, in one place.
##
## Every module reads its size and its height from here and nothing hard-codes
## a world coordinate anywhere else. That is not tidiness for its own sake: the
## thing that went wrong in every earlier pass was *proportion*, and proportion
## is only adjustable if it lives as a small table of numbers rather than as
## three hundred literals scattered through seven builders.
##
## ## The vertical budget, and where it came from
##
## The reference concept's hero column is about 1:3.5, width to height, and its
## seven stages do not share that height equally. Measured off the concept, as
## a fraction of the machine's own height, against what this layout spends:
##
##                   concept   here
##     START            8%      8.7%   small iconic landmark
##     BOWL            15%     14.0%   hero
##     S-BRIDGE        24%     21.8%   the long graceful connector
##     COLLECTOR       13%      9.3%   medium mechanical landmark
##     SPLIT           18%     17.4%   the second hero, and the gameplay
##     COMPRESSION     10%     11.5%   small dramatic connector
##     FINISH          12%     11.7%   the warm anchor
##
## Spent over 32 units of height against an 8.8-unit maximum width: 1:3.6, a
## touch leaner than the concept. Hierarchy is therefore built into the
## coordinates rather than applied afterwards, and the failure the brief names
## - "do not make every module enormous" - is not available as a mistake,
## because a module's height is its allocation.
##
## ## Every module gets clear air above and below it
##
## The first assembled build put the S-curve's last swing directly on the
## collector's rim and its first under the bowl's belly, and the result was one
## continuous white spiral in which neither disc could be found. The rule this
## layout now holds to is that a connector ends *outside* the plan radius of
## the module it feeds, at least half a marble-diameter clear of its guard, and
## approaching from behind, so it never crosses the action it delivers into.
## The gaps are small - under a unit - but they are the whole difference
## between seven modules and one ribbon.
##
## ## The marble is the ruler
##
## `MARBLE_RADIUS` is 0.285, unchanged from the V2 slice, and every clearance
## is quoted in multiples of it. The hero channel is 1.88 clear - three racers
## abreast - and the branches are the same moulding at 0.80 scale, which is
## 1.50 clear, or two racers abreast plus a margin. Nothing is sized in the
## abstract.

const MARBLE_RADIUS := 0.285
const MARBLE_DIAMETER := MARBLE_RADIUS * 2.0

# --- the seven levels -----------------------------------------------------
#
# Read down the machine. Every value is the module's own origin plane; a
# module's extent above and below that plane is the module's business.
const START_Y := 30.20
const START_Z := 0.30
const START_YAW := 0.10

const BOWL_Y := 25.00
const BOWL_RIM_RADIUS := 3.72
const BOWL_DISH_RADIUS := 3.14
const BOWL_DRAIN_RADIUS := 0.66
const BOWL_DEPTH := 1.20

const COLLECTOR_Y := 14.60
const COLLECTOR_RADIUS := 3.02

const SPLIT_TOP_Y := 12.50
const SPLIT_BOTTOM_Y := 5.05
const SPLIT_REACH := 4.35        # how far each branch swings off centre

const COMPRESSION_TOP_Y := 5.20
const COMPRESSION_BOTTOM_Y := 3.10

const FINISH_Y := 2.05
const FINISH_RADIUS := 4.18

const PLINTH_Y := -0.55

# --- the support frame ----------------------------------------------------
#
# Two slim outrigger towers and a central trunk, and no back wall. The V2.2
# slab did its job - the modules had something to be read against - and cost
# more than it earned: it closed the frame, and a closed frame has no depth in
# it. Here the reading-against is done by the trunk, which is narrow enough
# that the gorge shows past it at every level.
const TOWER_X := 3.34
const TOWER_Z := -8.80
const TOWER_HALF := 0.25
const TOWER_TOP := 31.40
const TOWER_BASE := 0.10

# The core runs the machine's whole height as a series of segments, one per
# gap between two modules, each stopping clear of the envelopes either side.
# Segmented rather than continuous for two reasons: a segment can be sized
# for the gap it fills, and it can be *absent* where a module is transparent -
# a core visible through the bowl's glass is a black post standing in the
# middle of the machine's first hero, which is exactly what the first build
# did. Read as [centre y, height, radius, z].
const CORE_SEGMENTS := [
	[27.55, 1.90, 1.06, -0.55],   # start chassis down to the bowl's mouth
	[21.30, 2.30, 1.34, -1.25],   # under the bowl: the biggest section
	[19.00, 2.40, 1.22, -1.25],
	[16.75, 2.20, 1.12, -1.25],   # down to the collector's guard
	[11.55, 2.10, 1.00, -1.55],   # behind the split, upper
	[ 9.15, 2.30, 0.92, -1.55],   # behind the split, lower
	[ 5.20, 2.60, 0.74, -1.35],   # behind the compression
]

# Where the towers are tied together. Chosen to fall *between* modules, never
# across one, so a brace is never the thing in front of the action.
const YOKE_LEVELS := [4.30, 13.60, 26.10]

# --- the channels ---------------------------------------------------------
#
# The paths every marble runs on, as control points for `v2_track.build`.
# Authored as one continuous descent: each run starts where the previous
# module hands off and ends where the next one accepts, so the eye can follow
# a single unbroken route from the start line to the finish.

# START throat -> BOWL dish. Short, swinging left, so the machine's silhouette
# breaks outboard immediately under the widest thing at the top.
const FEED_CONTROLS := [
	Vector3(0.30, 28.30, 2.30),
	Vector3(-0.75, 27.70, 2.60),
	Vector3(-2.10, 26.80, 2.40),
	Vector3(-2.95, 25.90, 1.55),
	Vector3(-2.85, 25.35, 0.70),
	Vector3(-2.30, 25.05, 0.20),
]

# BOWL drain -> COLLECTOR pan. The S, and the longest single unbroken run in
# the machine: out right, back left, out right, and finally in from behind at
# bearing 208 so the pan and its rotor stay unoccluded from the hero camera.
const S_CONTROLS := [
	Vector3(0.00, 23.80, 0.00),
	Vector3(1.40, 23.00, 1.45),
	Vector3(2.95, 22.05, 1.45),
	Vector3(3.45, 20.95, 0.05),
	Vector3(2.50, 19.90, -1.35),
	Vector3(0.55, 19.30, -1.85),
	Vector3(-1.50, 18.90, -1.35),
	Vector3(-3.10, 18.20, 0.10),
	Vector3(-3.55, 17.25, 1.55),
	Vector3(-3.35, 16.70, 0.35),
	Vector3(-2.60, 16.40, -1.15),
]

# COLLECTOR gate (bearing 20) -> the split gate. Down the machine's right.
const COLLECT_OUT_CONTROLS := [
	Vector3(2.90, 14.35, 1.06),
	Vector3(2.45, 13.85, 1.35),
	Vector3(1.60, 13.30, 1.20),
	Vector3(0.70, 12.85, 0.70),
	Vector3(0.10, 12.62, 0.34),
]

# The two branches. LEFT is the cool route: broad, smooth, one long sweep.
# RIGHT is the warm route: tighter, and it hooks twice.
const LEFT_CONTROLS := [
	Vector3(-0.42, 12.30, 0.42),
	Vector3(-1.85, 11.65, 1.15),
	Vector3(-3.30, 10.65, 1.20),
	Vector3(-4.30, 9.35, 0.45),
	Vector3(-4.35, 8.15, -0.35),
	Vector3(-3.70, 7.15, -0.55),
	Vector3(-2.70, 6.45, -0.05),
	Vector3(-1.55, 5.85, 0.38),
	Vector3(-0.62, 5.32, 0.56),
	Vector3(-0.26, 5.06, 0.58),
]

const RIGHT_CONTROLS := [
	Vector3(0.42, 12.30, 0.42),
	Vector3(1.85, 11.60, 1.15),
	Vector3(3.35, 10.55, 1.20),
	Vector3(4.25, 9.20, 0.45),
	Vector3(4.05, 8.05, -0.40),
	Vector3(3.20, 7.30, -0.40),
	Vector3(2.55, 6.55, 0.10),
	Vector3(1.50, 5.90, 0.42),
	Vector3(0.62, 5.32, 0.56),
	Vector3(0.26, 5.06, 0.58),
]

# The compression is one run, not three: the two coloured branches above
# arrive at the junction as themselves, and a single narrowing channel takes
# the field from there into the arena.
const DROP_CONTROLS := [
	Vector3(0.00, 4.66, 0.58),
	Vector3(0.02, 4.15, 0.88),
	Vector3(0.18, 3.66, 1.42),
	Vector3(0.58, 3.28, 2.06),
	Vector3(1.22, 3.04, 2.62),
]


static func machine_height() -> float:
	return TOWER_TOP - PLINTH_Y
