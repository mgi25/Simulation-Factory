extends RefCounted

## THE THREE V23 ENVIRONMENT DIRECTIONS, as data.
##
## Split from `course_env.gd` so that the code which applies a direction and
## the directions themselves can be read separately: this file is a set of art
## decisions with no logic in it, and that one is a set of mechanisms with no
## taste in it.
##
## Three worlds, not three grades. Each entry below is a complete description
## of an evening - what the sky is made of, how far you can see through it,
## what colour the rock is, where the light comes from, and what stands in the
## distance - and they are meant to be told apart from across a room.
##
## Every block is optional. A profile that omits `ranges` leaves the distant
## masses exactly where `course_world` put them; one that omits `materials`
## leaves the rock the colour it was. Omission is how a direction says "V22.1
## was already right about this part", and two of the three say it about
## something.
##
## ## What every one of them is answering
##
## The V22.1 frame that these were designed against has three faults, and they
## were measured rather than felt. `tools/sloped_v23_env.py measure` prints
## them for any render:
##
## * **The sky is the brightest thing in the picture.** Over the eight race
##   moments the sky band is a warm tan around luma 0.72 while the pearl track
##   it is behind sits at 0.66. A white machine against a lighter background
##   has no silhouette, and at the fork and the finish it has none.
## * **There is no aerial perspective.** `course_world` builds three ranges at
##   210, 380 and 600 units and puts fourteen haze banks between them; all
##   fourteen sit below y = -96 and are under the horizon from every camera on
##   this course, and the three ranges are within four points of luma of each
##   other. The backdrop is one silhouette.
## * **The warm half of the palette is spent on the sky.** The concept's warm
##   accents are the choice zone and the finish. In V22.1 they compete with a
##   tan horizon that covers a third of the frame.
##
## Each direction answers all three. They disagree about what to do next.

# --- A ----------------------------------------------------------------------

## **AURORA VALLEY** - a premium stylised natural world at cold dusk.
##
## The sky stops being the brightest thing in the frame and becomes a deep
## indigo with a cold teal band on the horizon; the haze thickens and pools, so
## the gorge and every terrace below the track fill with mist and the machine is
## read *through* air. The distant ranges are re-valued into four clean steps of
## aerial perspective and lifted until their crests clear the near massif, which
## is the single change that turns the backdrop from one silhouette into four.
##
## The whole warm half of the palette is then spent in one place: the finish.
## There is exactly one gold pocket in this world and the race ends in it.
const AURORA := {
	"title": "Aurora Valley",
	"note": "cold alpine dusk, layered mist, one gold pocket at the finish",
	"sky": {
		"top": "#050A1E", "horizon": "#1E4C6E", "curve": 0.10,
		"ground_bottom": "#03060E", "ground_horizon": "#14283C",
		"ground_curve": 0.22, "sky_energy": 1.0,
		# Six directional lights, six sun halos. See `course_env` on
		# `sun_angle`: at the inherited 46 degrees they merge into a pale mass
		# across the top of every wide frame. A compact disc is what a cold dusk
		# has, and it also puts the warm point of the sky where the finish is.
		"sun_angle": 3.0, "sun_curve": 0.12,
	},
	"env": {
		"background_energy": 0.52, "ambient_energy": 0.30,
		# Trimmed twice against the clip measure rather than by eye. V21 is this
		# project's readability gate and it exists because V20 ran 5.5% of every
		# frame flat at the top of the range; a direction that looks richer by
		# spending exposure is undoing it.
		"exposure": 0.81, "white": 12.0,
		"contrast": 1.04, "saturation": 1.30, "brightness": 1.0,
	},
	# **The fog colour is what a distant object converges to, so in a dark
	# world it has to be dark.** This is the second half of the aerial
	# perspective correction and it is the half that actually mattered. The
	# rock albedo barely reaches the camera at two hundred units - by then
	# `fog_aerial_perspective` has blended almost all of it away - so the
	# colour of the far ranges is `fog_light_color` and nothing else. At
	# the inherited pale slate and 0.95 energy every mountain in the
	# distance came back a pale lavender wash *brighter than the sky it
	# stood in*, whatever its albedo: blacking the four rock keys out
	# entirely changed the frame not at all, which is how this was found.
	#
	# `fog_sky_affect` is raised with it. It is how much the sky itself is
	# fogged, and leaving it low while the fog is dark puts a dark haze in
	# front of a sky that is not in it - the horizon line goes hard.
	"fog": {
		"colour": "#1D3D5C", "energy": 0.60, "sun_scatter": 0.24,
		"density": 0.0034, "sky_affect": 0.38, "aerial": 0.92,
		"height": -26.0, "height_density": 0.055,
	},
	# Threshold above what a lit pearl surface renders at, which is the V21
	# finding and it survives a darker world: a dark sky makes a bloomed track
	# look better and read worse, and 1.22 put the moulding back inside the
	# glow. The practicals and the edge lights are all well clear of 1.30.
	"glow": {"intensity": 1.10, "bloom": 0.22, "threshold": 1.30},
	"lights": {
		# The machine keeps its product key. A direction that dims the subject
		# to make the world look moody has solved the wrong problem.
		"Key": {"colour": "#FFF0DC", "energy": 2.85},
		"WorldKey": {"colour": "#BFE0FF", "energy": 2.00},
		"WorldFill": {"colour": "#4478B4", "energy": 0.78},
		# V22.1's warm raking light is most of what made the mountainside tan.
		# Here it is an alpenglow rather than a key: a third of the energy, and
		# aimed higher so it catches crests and not flanks.
		"WorldWarm": {"colour": "#FFAE62", "energy": 0.90,
			"rotation": Vector3(-14.0, 52.0, 0.0)},
		# Less light, more of it specular - V21's own trade, and a cold world
		# needs it harder. At energy 2.0 the cool rim was arriving as diffuse on
		# every pearl drum in the course and the machine came back cyan rather
		# than white with a cyan edge.
		"Rim": {"colour": "#6FE7FF", "energy": 1.65, "specular": 2.55},
		"ValleyBounce": {"colour": "#3D86B8", "energy": 0.55},
	},
	"practicals": {
		"start": {"colour": "#6BE9FF", "energy": 3.0, "range": 10.0},
		"mix": {"colour": "#9E7BFF", "energy": 3.0, "range": 9.0},
		"obstacle": {"colour": "#FF8A38", "energy": 3.4, "range": 10.5},
		# **The choice zone goes orange.** The brief puts warm energy where the
		# decision is, and `split` is the fork - the one node on this course a
		# marble chooses at. V22.1 lights it white, which is the one colour that
		# says nothing, and in a cold world it says less than nothing.
		"split": {"colour": "#FF9A4E", "energy": 3.2, "range": 10.5},
		"merge": {"colour": "#FFC168", "energy": 3.0, "range": 9.5},
		"finish": {"colour": "#FFC46A", "energy": 4.2, "range": 18.0},
	},
	"materials": {
		# Four steps of cool recession. The point is not that they are blue; it
		# is that no two of them are the same value, which is what the V22.1 set
		# failed at and why its three ranges read as one mass.
		# **Aerial perspective converges on the SKY, and this sky is dark.**
		# The first build stepped these four toward a light blue-grey, which
		# is the daylight convention and is what everyone draws from memory:
		# distant hills are paler than near ones. It is paler *because the
		# air between is lit*, and what the haze actually does is pull every
		# surface toward the colour of the sky behind it. Under a deep indigo
		# dusk that means distant rock gets DARKER, not lighter - and at the
		# first values the far range came back a vivid cyan mass floating
		# above the mountain, brighter than the sky it was supposed to be
		# receding into and the largest object in the top of every wide
		# frame. These four now step toward this profile's own horizon.
		"rock_soft_near": {"albedo": "#141F32"},
		"rock_soft_mid": {"albedo": "#1A2C42"},
		"rock_soft_far": {"albedo": "#1F3852"},
		"rock_soft_haze": {"albedo": "#244460"},
		# Lifted a step off the floor after the first proof. A cool ground can
		# be dark and still be ground; at the first values the near hillside fell
		# below the sky it was silhouetted against and the machine stopped being
		# installed in anything.
		"slope_cliff": {"albedo": "#1A2637"},
		"slope_rock": {"albedo": "#243245"},
		"slope_earth": {"albedo": "#354765"},
		"slope_scree": {"albedo": "#2D3E5C"},
		"slope_cap": {"albedo": "#28374E"},
		"slope_boulder": {"albedo": "#1C2738"},
		"scrub_dark": {"albedo": "#16251F"},
		"scrub_dry": {"albedo": "#1E2A2A"},
		"cloud_bank": {"albedo": "#2E5A80"},
		"far_structure": {"albedo": "#4C6B8C"},
		# The horizon band stops being a sunset and becomes the cold glow off a
		# snowfield, which is what lets the finish keep the only warm light.
		"lit_dusk_band": {"emission": "#5FA8D8", "energy": 1.20},
		"lit_valley_hero": {"emission": "#FFA451", "energy": 4.20},
		"lit_far_window_hero": {"emission": "#BFE6FF", "energy": 1.90},
	},
	"ranges": {
		# Lift, so a crest clears the massif's shoulder. The near range's top
		# sat at y = +40 and the ground above the start reaches +45: from most
		# cameras on this course the first range was behind the hill it was
		# supposed to stand behind.
		# Halved from the first build. Enough to clear the massif shoulder,
		# which was the fault; more than that stands a mountain in the sky.
		"NearRange": {"lift": 16.0, "stretch": 1.30},
		"MidRange": {"lift": 26.0, "scale": 1.10, "stretch": 1.55},
		"FarRange": {"lift": 36.0, "scale": 1.18, "stretch": 1.70},
	},
	"haze": {
		# `course_world._clouds` puts its fourteen banks between y = -96 and
		# -138 at radius 430 to 670. A camera on this course sits near y = 30
		# and looks down a few degrees, so every one of them has always been
		# below the horizon and out of frame. Lifted to straddle the ranges they
		# become the thing that separates them.
		"lift": 66.0, "scale": Vector3(1.2, 0.45, 1.3), "extra_banks": 8,
		# **Alpha is per bank and the stack is meant to accumulate.** At 0.26 a
		# single slab was legible as a slab - a pale lozenge with a rounded end,
		# sitting in the sky above the start in all three directions. A bank has
		# to be below the threshold where its own silhouette reads, and the way
		# to get a visible layer out of that is more of them, not stronger ones.
		"colour": "#7FA8C8", "alpha": 0.07,
	},
	"mist": {"colour": "#A8C6DE", "alpha": 0.075, "decks": 6, "top": -28.0,
		"step": 10.0, "offset": 38.0, "reach": 30.0},
	"dusk_band": {"lift": 68.0},
	"beacon": {"colour": "#7FF0FF", "energy": 6.0},
	"valley_glow": {"colour": "#FFA451", "energy": 4.2},
	"features": ["gorge_mist", "ridge_cards", "aurora"],
}

# --- B ----------------------------------------------------------------------

## **COLLECTOR CANYON** - the machine as a product on a display plinth.
##
## The direction that deliberately refuses the night. A collector piece is
## photographed against a seamless backdrop under a controlled key, not at dusk
## in a valley - so the sky here is a cyclorama rather than a sky (a long,
## low-saturation gradient, `sky_curve` three times the others'), the haze is
## thin so shapes stay clean, and the glow is the *lowest* of the three because
## a lit object is not a lamp.
##
## The warm/cool contrast is inverted against Aurora and that is the whole idea:
## the backdrop is cool and neutral, the canyon is warm putty, and the machine
## sits between them as the only white in the frame. Nothing in this world emits
## except the machine and a handful of far windows.
const COLLECTOR := {
	"title": "Collector Canyon",
	"note": "warm stylised canyon on a cool seamless backdrop, product-lit",
	"sky": {
		"top": "#101A2B", "horizon": "#3E4C62", "curve": 0.30,
		"ground_bottom": "#0B1220", "ground_horizon": "#2A3345",
		"ground_curve": 0.45, "sky_energy": 1.0,
		# A cyclorama has no sun in it at all. This is the one direction that
		# turns the halo off outright, which is also what makes its backdrop read
		# as a lit backdrop rather than as weather.
		"sun_angle": 0.4, "sun_curve": 0.05,
	},
	"env": {
		"background_energy": 0.60, "ambient_energy": 0.40,
		"exposure": 0.86, "white": 11.0,
		"contrast": 1.02, "saturation": 1.34, "brightness": 1.0,
	},
	# Mid-value fog for a mid-value backdrop: this is the one direction whose
	# sky was never dark, so the distance converges on a neutral slate and the
	# correction is small. See Aurora's fog block for the rule.
	"fog": {
		"colour": "#5A6478", "energy": 0.74, "sun_scatter": 0.22,
		"density": 0.0021, "sky_affect": 0.30, "aerial": 0.70,
		"height": -24.0, "height_density": 0.030,
	},
	"glow": {"intensity": 0.85, "bloom": 0.16, "threshold": 1.40},
	"lights": {
		"Key": {"colour": "#FFF6EC", "energy": 3.10},
		# The one direction whose *world* key is warm. A canyon lit cool and a
		# machine lit warm is a diorama with two evenings in it; this way the
		# ground and the product agree and the backdrop is the only cool thing.
		"WorldKey": {"colour": "#F2E6D2", "energy": 2.60},
		"WorldFill": {"colour": "#7E9BC6", "energy": 0.85},
		"WorldWarm": {"colour": "#FF9A50", "energy": 1.50},
		"Rim": {"colour": "#A8DCFF", "energy": 1.90, "specular": 2.20},
		"ValleyBounce": {"colour": "#FFC089", "energy": 1.00},
	},
	"practicals": {
		"start": {"colour": "#7FE9FF", "energy": 2.8, "range": 9.5},
		"mix": {"colour": "#A98AFF", "energy": 2.6, "range": 8.5},
		"obstacle": {"colour": "#FF9A48", "energy": 3.2, "range": 10.0},
		"split": {"colour": "#EAF7FF", "energy": 2.4, "range": 9.0},
		"merge": {"colour": "#FFC97E", "energy": 2.8, "range": 9.0},
		"finish": {"colour": "#FFD089", "energy": 4.0, "range": 17.0},
	},
	"materials": {
		# Warm *stone*, not terracotta. The first build read as a Mars canyon,
		# and the fault was chroma rather than value: at a red-leaning hue the
		# ground competed directly with the orange machinery and with the gold
		# finish, which are the two things in this world that are allowed to be
		# warm. Rotated toward a greige and the same value ladder reads as rock
		# the machine is standing on.
		# Warm near, cool far: these step off the canyon's own hue and onto the
		# backdrop's, which is what puts the distance behind the seamless rather
		# than in front of it. Same rule as Aurora's - converge on the sky - and
		# because this sky is a mid grey-blue the steps are nearly flat in value
		# and carry almost all of their recession in chroma.
		"rock_soft_near": {"albedo": "#463D3A"},
		"rock_soft_mid": {"albedo": "#4C4A4E"},
		"rock_soft_far": {"albedo": "#47505F"},
		"rock_soft_haze": {"albedo": "#44536B"},
		# The canyon. Warm, light enough to read as a material rather than as an
		# absence, and separated from the machine by hue instead of by value -
		# which is what keeps a white track legible over it without having to
		# make the ground black.
		"slope_cliff": {"albedo": "#38322E"},
		"slope_rock": {"albedo": "#4A423A"},
		"slope_earth": {"albedo": "#63594B"},
		"slope_scree": {"albedo": "#564C42"},
		"slope_cap": {"albedo": "#443C36"},
		"slope_boulder": {"albedo": "#2F2A26"},
		"scrub_dark": {"albedo": "#2A2A22"},
		"scrub_dry": {"albedo": "#3A3428"},
		"cloud_bank": {"albedo": "#76706C"},
		"far_structure": {"albedo": "#89837C"},
		"lit_dusk_band": {"emission": "#E8B584", "energy": 1.50},
		"lit_valley_hero": {"emission": "#FFB268", "energy": 3.40},
		"lit_far_window_hero": {"emission": "#FFE2BC", "energy": 1.50},
	},
	"ranges": {
		# Fewer, larger, cleaner. `thin` drops every third mass, which is what
		# turns a crowded ridge into three or four readable buttes - the
		# silhouette a display backdrop wants.
		"NearRange": {"lift": 18.0, "scale": 1.16, "thin": 3, "stretch": 1.25},
		"MidRange": {"lift": 30.0, "scale": 1.24, "thin": 3, "stretch": 1.45},
		"FarRange": {"lift": 40.0, "scale": 1.28, "stretch": 1.60},
	},
	"haze": {"lift": 62.0, "scale": Vector3(1.4, 0.45, 1.3), "extra_banks": 8,
		"colour": "#9AA0AC", "alpha": 0.06},
	"mist": {"colour": "#C8BBB2", "alpha": 0.055, "decks": 4, "top": -30.0,
		"step": 12.0, "offset": 44.0, "reach": 28.0},
	"dusk_band": {"lift": 64.0},
	"beacon": {"colour": "#BFE9FF", "energy": 3.6},
	"valley_glow": {"colour": "#FFB268", "energy": 3.4},
	"features": ["mesa_plinths", "gorge_haze_soft"],
}

# --- C ----------------------------------------------------------------------

## **GRAPHITE GRID** - a dark world the machine is the only light in.
##
## The brief's third direction taken as far as readability allows. The ground
## goes to near-black graphite, the sky nearly to black, and the only bright
## things left in the frame are the track, the marbles, the practicals and a
## short list of environmental lights that are all the same two colours. What it
## buys is silhouette: every edge of the machine has a dark field behind it,
## which is the one thing neither of the other two can promise in every shot.
##
## The risk it runs is the opposite of Collector's. A black world flatters a
## glowing object and starves a moulded one, and this course is mostly moulded
## pearl - so the glow threshold comes *down* here rather than up, and the
## practicals do more of the lighting than the key does.
const GRAPHITE := {
	"title": "Graphite Grid",
	"note": "near-black valley, graphic silhouettes, restrained cyan sci-fi",
	"sky": {
		"top": "#01030A", "horizon": "#0B2436", "curve": 0.08,
		"ground_bottom": "#000205", "ground_horizon": "#071520",
		"ground_curve": 0.18, "sky_energy": 1.0,
		"sun_angle": 1.6, "sun_curve": 0.08,
	},
	"env": {
		"background_energy": 0.38, "ambient_energy": 0.26,
		# 0.92 was the first build and it cost 3.9% of the worst frame flat at
		# the top of the range - nearly the V20 regression the whole V21 pass
		# exists to have removed. A dark world does not need more exposure; it
		# needs the bright things in it to stay inside the curve.
		"exposure": 0.81, "white": 10.0,
		"contrast": 1.08, "saturation": 1.22, "brightness": 1.0,
	},
	# The darkest fog of the three, for the darkest sky of the three. Same
	# rule as Aurora's: a distant mass converges on this colour, so this colour
	# is what "the far mountains" are.
	"fog": {
		"colour": "#10293A", "energy": 0.72, "sun_scatter": 0.18,
		"density": 0.0042, "sky_affect": 0.28, "aerial": 1.00,
		"height": -30.0, "height_density": 0.070,
	},
	# **The single worst number in the first build of this lab.** At threshold
	# 1.10 the bloom starts below what a lit pearl surface renders at, so the
	# track itself was the light source and the white ribbon had no edge -
	# which is exactly the V20 defect V21 was written to remove, reintroduced
	# in the name of a glowing machine. The machine still glows here; what
	# glows is the practicals and the edge strips, which is what "glowing
	# machine" meant in the concept.
	"glow": {"intensity": 1.10, "bloom": 0.20, "threshold": 1.34},
	"lights": {
		"Key": {"colour": "#EAF4FF", "energy": 2.50},
		# Dark is not the same as absent, and the first build confused them: at
		# 1.35 and 0.45 the hillside fell below the sky and the machine floated.
		# The backdrop is still the darkest of the three directions by twelve
		# points of L*; it is now a backdrop rather than a hole.
		"WorldKey": {"colour": "#7FB6E0", "energy": 1.85},
		"WorldFill": {"colour": "#24507A", "energy": 0.72},
		# Down from 0.70. The warm rake was the only light reaching the lifted
		# haze banks, and against a near-black sky it painted a magenta smear
		# across the top of the start frame.
		"WorldWarm": {"colour": "#FF7A3A", "energy": 0.38,
			"rotation": Vector3(-12.0, 52.0, 0.0)},
		"Rim": {"colour": "#59E8FF", "energy": 1.90, "specular": 2.80},
		"ValleyBounce": {"colour": "#2A6E96", "energy": 0.55},
	},
	"practicals": {
		# Each about a sixth under the first build. The zone practicals are the
		# whole of "the machine is the only light in this world", so they are the
		# last thing this direction should give up - but at the first energies
		# they were putting 1.4% of the obstacle frame flat white, and a blown
		# pool of light is not a lit machine.
		"start": {"colour": "#5CF0FF", "energy": 3.4, "range": 10.0},
		"mix": {"colour": "#A24CFF", "energy": 3.1, "range": 9.0},
		"obstacle": {"colour": "#FF7A28", "energy": 3.7, "range": 11.0},
		"split": {"colour": "#FF8A34", "energy": 2.9, "range": 10.0},
		"merge": {"colour": "#FFB43C", "energy": 3.1, "range": 10.0},
		"finish": {"colour": "#FFC64F", "energy": 4.5, "range": 20.0},
	},
	"materials": {
		# Raised a whole step after the first proof measured seven moments out
		# of eleven whose backdrop was a featureless wall. Graphite is meant to
		# be the darkest of the three, not the emptiest: these are still four to
		# six points of L* under Aurora's and the silhouette is untouched.
		# The same correction as Aurora's, and in the darkest sky of the three
		# the steps are the smallest: four values inside eight points of L*,
		# every one of them converging on a near-black horizon. Distance here is
		# carried by the haze banks and the crest lines rather than by the rock.
		"rock_soft_near": {"albedo": "#0C1621"},
		"rock_soft_mid": {"albedo": "#0F1E2B"},
		"rock_soft_far": {"albedo": "#122634"},
		"rock_soft_haze": {"albedo": "#152E3E"},
		"slope_cliff": {"albedo": "#0E141F"},
		"slope_rock": {"albedo": "#141C29"},
		"slope_earth": {"albedo": "#1C2739"},
		"slope_scree": {"albedo": "#17202F"},
		"slope_cap": {"albedo": "#111A27"},
		"slope_boulder": {"albedo": "#0C121C"},
		"scrub_dark": {"albedo": "#0B1512"},
		"scrub_dry": {"albedo": "#101410"},
		"cloud_bank": {"albedo": "#1E4058"},
		"far_structure": {"albedo": "#2C465C"},
		"lit_dusk_band": {"emission": "#2FB8D8", "energy": 2.60},
		# The valley platforms stop being industry at dusk and become a lit
		# floor a long way down, which is the cheapest depth cue this course
		# has: the gorge is open air in half its shots.
		"lit_valley_hero": {"emission": "#35E0FF", "energy": 4.60},
		"lit_far_window_hero": {"emission": "#7FE8FF", "energy": 2.40},
	},
	"ranges": {
		"NearRange": {"lift": 20.0, "stretch": 1.35},
		"MidRange": {"lift": 32.0, "scale": 1.12, "stretch": 1.60},
		"FarRange": {"lift": 44.0, "scale": 1.20, "stretch": 1.75},
	},
	"haze": {"lift": 70.0, "scale": Vector3(1.4, 0.5, 1.6), "extra_banks": 12,
		"colour": "#3E7292", "alpha": 0.08},
	"mist": {"colour": "#7FC4E0", "alpha": 0.065, "decks": 6, "top": -30.0,
		"step": 10.0, "offset": 38.0, "reach": 32.0},
	"dusk_band": {"lift": 72.0},
	"beacon": {"colour": "#5CF0FF", "energy": 8.0},
	"valley_glow": {"colour": "#35E0FF", "energy": 4.6},
	"features": ["gorge_mist", "ridge_cards", "crest_lines", "valley_grid"],
}

const PROFILES := {
	"aurora": AURORA,
	"collector": COLLECTOR,
	"graphite": GRAPHITE,
}
