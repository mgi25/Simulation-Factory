extends RefCounted

## The descending S: a moulded channel, guarded, lit and hung off the tower.
##
## The brief's requirement is that this looks like a part that could physically
## come in a box, and the failure mode it names - "sampled/ribbon appearance" -
## has a specific cause. A ribbon is what you get when a track is one surface.
## A moulded channel is five, stacked in section:
##
##     silver top lip        <- catches the key, draws the edge
##     acrylic side guard    <- transparent, stands proud of the wall
##     pearl channel         <- the running surface and its walls
##     gold fascia           <- the warm band under the lip
##     graphite keel         <- the dark structural spine
##
## Every one of those is a separate sweep along the same spline, offset in the
## path's own frame so they can never drift apart. Seen from the hero camera
## the stack is perhaps twelve pixels deep, and those twelve pixels are the
## difference between a drawn line and an extruded component. The style-lock
## track had three of the five and no transparent element at all.
##
## ## Why a spline and not an arc chain
##
## An arc chain has a curvature step at every joint, and a glossy channel
## shows a curvature step as a kink in its highlight. Catmull-Rom through
## authored controls is continuous, so the highlight runs the length of the
## track unbroken - which is exactly the shot the concept sells its S-curve
## bridge on.
##
## The module works in its parent's space: it is handed world-space controls
## because a track's whole job is to connect two other modules, and a local
## origin would only have to be undone.
##
## ## Two sets of dimensions
##
## `build(palette, controls)` draws the track the visual lab authored, at the
## constants below, and is what every existing caller gets. Handed a `spec` -
## the curve's `visual` block out of `marble3d/presentation.py` - it draws the
## same component at the dimensions of a simulated channel, along the exact
## centreline the collider was swept down.
##
## Two things change with a spec, and both are the physics' and not a taste
## call:
##
## **The channel is two and a half times wider.** The simulated half-width is
## 1.0 against the authored 0.40. Every one of the five layers, the neon and
## the hardware scales off that number the way it used to scale off
## `HALF_WIDTH`, and every detail size - fillets, tube stock, guard thickness,
## post section - is the authored number times `half_width / HALF_WIDTH`. That
## is what keeps the moulded-component read: a channel drawn two and a half
## times bigger, carrying the fillet it was drawn with at 0.40, is a channel
## with no fillet the eye can find - and an edge with no fillet band on it is
## the whole tell this asset exists to avoid.
##
## **The centreline is not resampled.** `path_for` smooths authored controls
## into a spline because authored controls are sparse and a spline is what
## makes them flow. The contract's 38 frames are not controls - they are the
## curve, at the solver's own tessellation, already inside its sagitta budget.
## Running them back through `smooth_path` would produce a different surface
## from the one the marbles are solved against, and the difference lands on
## the running surface where a hovering marble shows it.
##
## ## Banking
##
## The simulated curve rolls 27.7 degrees into its turn, because that is the
## angle at which a marble at the design speed needs no sideways force from
## the wall. Every sweep and every offset here therefore runs through the
## `_framed` variants in `toy_geometry` and `lab_forms`, carrying the up vector
## the solver used rather than world up. Without that the drawn floor is level
## where the solved floor is banked, and the marbles - placed by the solver -
## ride up the drawn wall and clip the drawn guard. With no spec the ups are
## world up at every sample, which is what the framed sweeps reduce to, so the
## authored track comes out exactly as before.

const Geometry := preload("res://scripts/toy_geometry.gd")
const Forms := preload("res://assets/marble_machine/lab_forms.gd")

const HALF_WIDTH := 0.40
const WALL_HEIGHT := 0.25
const SAMPLES := 14


static func dimensions(spec: Dictionary) -> Dictionary:
	## The authored channel, or a simulated one, as one set of numbers.
	##
	## An empty spec reproduces the authored constants exactly, so a caller
	## that passes nothing gets the component it has always got.
	##
	## `hung` is not a dimension but it travels with them, because it is the
	## same question asked of the structure: an authored track hangs off the
	## lab's support tower, and a contract track has no tower to hang from.
	## See `_supports`.
	if spec.is_empty():
		return {
			"half_width": HALF_WIDTH,
			"wall_height": WALL_HEIGHT,
			"detail": 1.0,
			"hung": true,
		}
	var half_width: float = float(spec["half_width"])
	return {
		"half_width": half_width,
		"wall_height": float(spec["wall_height"]),
		"detail": half_width / HALF_WIDTH,
		"hung": false,
	}


static func path_for(controls: Array) -> Array:
	## The running centreline, at the density everything else is built on.
	return Forms.smooth_path(controls, SAMPLES)


static func centreline_path(spec: Dictionary) -> Array:
	## The simulated channel's frames as a path - not a spline through them.
	##
	## These are the exact positions the collider was swept along, in world
	## space. They are handed straight to the sweeps: see the header on why
	## smoothing them is the one thing that must not happen here.
	var out: Array = []
	for frame in spec.get("centreline", []):
		var at: Array = frame["position"]
		out.append(Vector3(at[0], at[1], at[2]))
	return out


static func centreline_ups(spec: Dictionary) -> Array:
	## The banked up at each frame, out of the contract's quaternions.
	##
	## The contract writes each frame as a quaternion whose +X is the flow
	## direction and whose +Y is the channel's own up, in the same (x, y, z, w)
	## component order and the same handedness Godot uses. So the up is
	## `q * Vector3.UP` and nothing is reordered or negated on the way in.
	##
	## Some of these arrive negated relative to their neighbours, which is what
	## composing rotations does and is not a fault in the contract: `q` and
	## `-q` name the same rotation and give the same vector here. It is only a
	## trap for code that interpolates between two quaternions, and nothing
	## does - the up is read at a sample and used at that sample.
	var out: Array = []
	for frame in spec.get("centreline", []):
		var q: Array = frame["rotation"]
		out.append((Quaternion(q[0], q[1], q[2], q[3]) * Vector3.UP).normalized())
	return out


static func build(palette, controls: Array, node_name := "SCurve",
		accent := "neon_cyan", spec := {}) -> Node3D:
	var root := Node3D.new()
	root.name = node_name
	var d := dimensions(spec)

	var path: Array
	var ups: Array
	if d["hung"]:
		path = path_for(controls)
		ups = Geometry.world_ups(path.size())
	else:
		path = centreline_path(spec)
		ups = centreline_ups(spec)

	_channel(root, palette, path, ups, d)
	_understructure(root, palette, path, ups, d)
	_guards(root, palette, path, ups, d)
	_neon(root, palette, path, ups, d, accent)
	_supports(root, palette, path, ups, d)

	return root


# --- the five layers ------------------------------------------------------

static func _channel(root: Node3D, palette, path: Array, ups: Array,
		d: Dictionary) -> void:
	## The pearl running surface, walls and outer flanks, as one solid.
	var hw: float = d["half_width"]
	var wall: float = d["wall_height"]
	var k: float = d["detail"]
	var section: Array = Geometry.channel_section(
		hw, 0.17 * k, wall, 0.10 * k, 4)
	root.add_child(Forms.mesh_node(
		Geometry.sweep_framed(path, ups, section[0], section[1], true),
		palette.get_material("track_silver"), "Channel"))

	# The silver lip along the top of each wall. Round stock, because a wall
	# that ends in a flat edge catches a one-pixel highlight and one in round
	# stock catches a band - the same argument the whole rounding toolkit
	# rests on, applied to the longest edge in the machine.
	for side in 2:
		var lateral: float = hw * (1.0 if side == 0 else -1.0)
		var lip_path := Forms.offset_path_framed(path, ups, lateral, wall)
		root.add_child(Forms.mesh_node(
			Geometry.tube_framed(lip_path, ups, 0.042 * k, 8),
			palette.get_material("pearl_lip"), "TopLip%d" % side, false))


static func _understructure(root: Node3D, palette, path: Array, ups: Array,
		d: Dictionary) -> void:
	## Warm fascia over dark keel: the 1:5 structure-to-track value split the
	## concept builds every one of its beams from.
	var hw: float = d["half_width"]
	var k: float = d["detail"]

	var fascia_section: Array = Geometry.beam_section(
		hw - 0.05 * k, 0.20 * k, 0.06 * k, 3)
	var fascia_path := Forms.offset_path_framed(path, ups, 0.0, -0.28 * k)
	root.add_child(Forms.mesh_node(
		Geometry.sweep_framed(fascia_path, ups,
			fascia_section[0], fascia_section[1], true),
		palette.get_material("gold"), "Fascia", false))

	var keel_section: Array = Geometry.beam_section(
		hw - 0.19 * k, 0.30 * k, 0.09 * k, 3)
	var keel_path := Forms.offset_path_framed(path, ups, 0.0, -0.53 * k)
	root.add_child(Forms.mesh_node(
		Geometry.sweep_framed(keel_path, ups,
			keel_section[0], keel_section[1], true),
		palette.get_material("graphite_deep"), "Keel"))

	# The underlight, tucked in the shadow between fascia and keel.
	root.add_child(Forms.mesh_node(
		Geometry.tube_framed(
			Forms.offset_path_framed(path, ups, 0.0, -0.41 * k), ups,
			0.030 * k, 6),
		palette.get_material("lit_cyan_soft"), "UnderLight", false))


static func _guards(root: Node3D, palette, path: Array, ups: Array,
		d: Dictionary) -> void:
	## Acrylic standing proud of the channel walls, on its own shoulder.
	var hw: float = d["half_width"]
	var wall: float = d["wall_height"]
	var k: float = d["detail"]
	var hung: bool = d["hung"]

	var height: float = 0.40 * k
	if palette.variant == "deck":
		height = 0.32 * k
	var guard_section: Array = Geometry.beam_section(
		0.035 * k, height, 0.014 * k, 2)
	var key := "acrylic_aqua_deep" if palette.variant == "deck" else "acrylic_aqua"

	for side in 2:
		var lateral: float = (hw + 0.045 * k) * (1.0 if side == 0 else -1.0)
		var guard_path := Forms.offset_path_framed(path, ups, lateral,
			wall + height * 0.5 - 0.06 * k)
		root.add_child(Forms.mesh_node(
			Geometry.sweep_framed(guard_path, ups,
				guard_section[0], guard_section[1], true),
			palette.get_material(key), "Guard%d" % side, false))

		# A clear cap on the guard's top edge, for the same reason the bowl's
		# guard has one: cast acrylic has a bright edge, and without it the
		# panel has no silhouette against a dark background.
		root.add_child(Forms.mesh_node(
			Geometry.tube_framed(
				Forms.offset_path_framed(path, ups, lateral,
					wall + height - 0.06 * k),
				ups, 0.026 * k, 6),
			palette.get_material("acrylic_clear"), "GuardCap%d" % side, false))

	# Guard posts at intervals, alternating sides: the medium-scale rhythm
	# along a length of track that would otherwise be one smooth extrusion.
	var post := Geometry.rounded_box(
		Vector3(0.07 * k, height + 0.30 * k, 0.11 * k), 0.025 * k, 3)
	var post_paths := [
		Forms.offset_path_framed(path, ups, hw + 0.05 * k, 0.0),
		Forms.offset_path_framed(path, ups, -(hw + 0.05 * k), 0.0),
	]
	var lift: float = (height + 0.30 * k) * 0.5 - 0.14 * k
	var count := 7
	for index in count:
		var t := (float(index) + 0.5) / float(count)
		var at: Vector3 = Forms.sample_at(post_paths[index % 2], t)
		var node := Forms.mesh_node(post, palette.get_material("silver_deep"),
			"GuardPost%d" % index, false)
		if hung:
			node.position = at + Vector3(0.0, lift, 0.0)
		else:
			# On banked track the post has to stand square to the channel it
			# is bolted to. An upright post on a 27.7 degree bank leans away
			# from its own guard by a third of its height, which reads as a
			# part that missed its mounting face.
			var frame := Forms.sample_basis(path, ups, t)
			node.transform = Transform3D(frame, at + frame.y * lift)
		root.add_child(node)


static func _neon(root: Node3D, palette, path: Array, ups: Array,
		d: Dictionary, accent: String) -> void:
	## The zone light: a rope of neon down both flanks, outboard of the wall.
	##
	## This is the reference's signature and the thing every earlier prototype
	## left out. Its track is not a light-coloured surface with a glow pass
	## over it - it is a dark-mounted channel with a *lit edge* running the
	## whole length, and the eye follows that edge from module to module. A
	## soft strip tucked under the fascia cannot do that job: it has to sit on
	## the silhouette, at an emission high enough to cross the bloom threshold
	## on its own.
	##
	## The accent is per-chute, so the run reads as zones - cyan at the top,
	## violet through the mixer, warm at the finish - which is the concept's
	## own colour plan and the reason its tower does not read as monochrome.
	var hw: float = d["half_width"]
	var wall: float = d["wall_height"]
	var k: float = d["detail"]
	for side in 2:
		var lateral: float = (hw + 0.085 * k) * (1.0 if side == 0 else -1.0)
		root.add_child(Forms.mesh_node(
			Geometry.tube_framed(
				Forms.offset_path_framed(path, ups, lateral, wall - 0.10 * k),
				ups, 0.048 * k, 8),
			palette.get_material(accent), "Neon%d" % side, false))


static func _supports(root: Node3D, palette, path: Array, ups: Array,
		d: Dictionary) -> void:
	## Where the track is held. Three brackets, each a collar, a leg and a tie.
	##
	## ## Why the contract build keeps only the collar
	##
	## The leg and the tie below reach toward a point derived from the lab's
	## support tower - `at * 0.14` is a pull back toward the tower's axis at
	## the origin - and the integrated machine has no tower. `marble3d_scene`
	## deliberately does not build one: it was drawn to carry a differently
	## laid out machine, and two of its masts crossed the bowl's action area
	## even in the lab.
	##
	## There is also nowhere for a leg to go. The curve runs directly under the
	## bowl for most of its length, so a strut long enough to reach anything
	## would come out through the dish; and below the curve there is nothing at
	## all, because the curve's own exit is the bottom of the machine. A strut
	## ending in mid-air is worse than no strut - it is the one detail that
	## tells the eye the machine is a drawing.
	##
	## So the contract build keeps the collar and drops the leg and the tie. A
	## collar is a band clamped round the keel: it is attached to the thing it
	## wraps and therefore cannot float, and it was doing most of the work
	## anyway, since a joint with a collar over it reads as a fitting while a
	## bare leg meeting a track reads as a mistake.
	var k: float = d["detail"]
	var hung: bool = d["hung"]
	var count := 3
	for index in count:
		var t := (float(index) + 0.6) / float(count + 0.4)
		var at := Forms.sample_at(path, t)

		if not hung:
			var frame := Forms.sample_basis(path, ups, t)
			var band := Forms.mesh_node(Forms.collar(0.30 * k, 0.16 * k),
				palette.get_material("gold"), "SupportCollar%d" % index, false)
			band.transform = Transform3D(frame, at - frame.y * (0.55 * k))
			root.add_child(band)
			continue

		var anchor := Vector3(at.x * 0.14, at.y - 2.15, at.z * 0.14 - 0.55)

		var collar := Forms.mesh_node(Forms.collar(0.30, 0.16),
			palette.get_material("gold"), "SupportCollar%d" % index, false)
		collar.position = at + Vector3(0.0, -0.55, 0.0)
		root.add_child(collar)

		root.add_child(Forms.mesh_node(
			Forms.brace(at + Vector3(0.0, -0.55, 0.0), anchor, 0.075, 8),
			palette.get_material("graphite"), "SupportLeg%d" % index))

		root.add_child(Forms.mesh_node(
			Forms.brace(at + Vector3(0.0, -0.30, 0.0),
				anchor.lerp(at, 0.30) + Vector3(0.0, 0.55, 0.0), 0.038, 6),
			palette.get_material("chrome"), "SupportTie%d" % index))
