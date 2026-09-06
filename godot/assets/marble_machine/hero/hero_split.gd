extends RefCounted

## STAGE 5 - THE SPLIT CHOICE.
##
## Two routes to the same finish, and the frame's second hero. The channels
## themselves are `v2_track` runs - the same moulding as the S, at 0.80 scale -
## so what this file builds is everything that makes the two runs read as a
## *decision* rather than as one track drawn twice:
##
##     the splitter nose      a gold chevron under a lit divider
##     LEFT  - COOL           blue shell, cyan lights, clean arch supports
##     RIGHT - WARM           orange shell, amber lights, spinners and cages
##     the hazard deck        a dark shelf of orange rotors behind the right
##
## ## Why the difference is albedo and not lighting
##
## The brief's test is that the choice be "immediately readable", and the
## acceptance frame is a phone. At 390 pixels wide the whole split is about
## seventy pixels across; an edge light differs from another edge light by two
## pixels of hue and nothing else survives. So the two branches differ in the
## colour of their *shells* - the largest lit area either route has - and in
## their silhouettes: the left is one long smooth sweep, the right hooks twice
## and carries furniture. Either difference alone would read; both together
## survive being shrunk.
##
## ## Left is safer, right is riskier, and the geometry says so
##
## No gameplay logic exists yet and none is claimed. But the visual language is
## not arbitrary: the left run is longer in arc and gentler in curvature, and
## the right is shorter, tighter and obstructed. If a physics pass later makes
## the left slightly slower and the right faster-but-riskier, the art already
## says that. If it does not, the art is what changes.

const Geometry := preload("res://scripts/toy_geometry.gd")
const Forms := preload("res://assets/marble_machine/lab_forms.gd")
const V2Forms := preload("res://assets/marble_machine/v2/v2_forms.gd")
const Layout := preload("res://assets/marble_machine/hero/hero_layout.gd")

const BRANCH_SCALE := 0.80

# The two runs, as option dictionaries for `v2_track.build`. Everything that
# differs between the routes is in this table and nowhere else.
const LEFT_OPTIONS := {
	"edge_stock": 0.062,
	"bank_gain": 2.6, "bank_max": 24.0,
	"entry_flare": 0.22, "exit_flare": 0.16,
	"edge_light": "neon_blue", "samples": 116,
	"shell": "blue_machine", "floor": "running_blue",
	"keel": "blue_deep", "guard": "acrylic_blue",
	"scale": BRANCH_SCALE,
}

const RIGHT_OPTIONS := {
	"edge_stock": 0.062,
	"bank_gain": 3.4, "bank_max": 30.0,
	"entry_flare": 0.22, "exit_flare": 0.16,
	"edge_light": "lit_orange_line", "samples": 124,
	"shell": "orange_machine", "floor": "running_orange",
	"keel": "orange_deep", "guard": "acrylic_amber",
	"scale": BRANCH_SCALE,
}


static func splitter(palette) -> Node3D:
	## The nose that divides the stream, at the top of the two branches.
	##
	## A wedge, a lit blade along its crest, and a pair of flared cheeks that
	## hand off to each channel's entry flare. It sits directly under the
	## collector's exit chute and it is the single object in the machine whose
	## whole job is to say "from here, two ways".
	var root := Node3D.new()
	root.name = "Splitter"
	root.position = Vector3(0.0, Layout.SPLIT_TOP_Y + 0.28, 0.34)

	var body := Forms.mesh_node(
		Geometry.rounded_box(Vector3(2.35, 0.62, 1.55), 0.22, 4),
		palette.get_material("pearl_shell"), "Body")
	body.position = Vector3(0.0, -0.24, 0.0)
	root.add_child(body)

	var under := Forms.mesh_node(
		Geometry.rounded_box(Vector3(2.05, 0.44, 1.30), 0.18, 4),
		palette.get_material("graphite"), "Under")
	under.position = Vector3(0.0, -0.66, 0.0)
	root.add_child(under)

	# The blade: a narrow vertical fin on the centreline, lit white, running
	# fore and aft. It is what a marble would actually strike, and it is the
	# thing that makes the decision look mechanical instead of painted on.
	var fin := Forms.mesh_node(
		Geometry.rounded_box(Vector3(0.13, 0.52, 1.42), 0.05, 3),
		palette.get_material("chrome"), "Fin")
	fin.position = Vector3(0.0, 0.16, 0.0)
	root.add_child(fin)

	var crest := Forms.mesh_node(
		Geometry.tube([Vector3(0.0, 0.44, -0.66), Vector3(0.0, 0.44, 0.66)],
			0.036, 8),
		palette.get_material("lit_white"), "Crest", false)
	root.add_child(crest)

	# One cheek per route, in that route's own colour. Two coloured wedges
	# meeting at a chrome fin is the whole idea of the module in one object.
	for entry in [[1.0, "orange_machine", "lit_orange_line", "R"],
			[-1.0, "blue_machine", "neon_blue", "L"]]:
		var side: float = entry[0]
		var cheek := Forms.mesh_node(
			Geometry.rounded_box(Vector3(0.86, 0.40, 1.24), 0.16, 3),
			palette.get_material(str(entry[1])), "Cheek%s" % str(entry[3]))
		cheek.position = Vector3(side * 0.70, -0.02, 0.0)
		cheek.rotation.z = -side * 0.20
		root.add_child(cheek)

		var lamp := Forms.mesh_node(
			Geometry.tube([
				Vector3(side * 1.10, 0.14, -0.54),
				Vector3(side * 1.10, 0.14, 0.54)], 0.030, 8),
			palette.get_material(str(entry[2])),
			"CheekLight%s" % str(entry[3]), false)
		root.add_child(lamp)

		var collar := Forms.mesh_node(
			Geometry.rounded_disc(0.20, 0.16, 0.06, 16, 3),
			palette.get_material("gold"), "Collar%s" % str(entry[3]), false)
		collar.position = Vector3(side * 1.12, -0.34, 0.0)
		collar.rotation.z = PI * 0.5
		root.add_child(collar)

	Forms.bolt_ring(root, palette.get_material("chrome"), 10, 0.90, -0.52,
		0.055, 0.05)
	return root


static func cool_furniture(palette, path: Array, banks: Array) -> Node3D:
	## The left route's fittings: clean arches, and nothing in the channel.
	##
	## The safer route is characterised by *absence*. Three slim arches carry
	## it, each one a smooth hoop passing under the keel and up the far side,
	## with a cyan light following the arch. No obstacle stands in it and no
	## cage crosses it, which is exactly what makes the other branch read as
	## the risky one without the other branch having to be told.
	var root := Node3D.new()
	root.name = "CoolFurniture"

	for t in [0.20, 0.50, 0.80]:
		var index: int = clampi(int(round(float(t) * float(path.size() - 1))),
			0, path.size() - 1)
		var frame: Basis = V2Forms.banked_basis(path, banks, index)
		var at: Vector3 = path[index]
		var pivot := Node3D.new()
		pivot.name = "Arch%d" % int(float(t) * 100.0)
		pivot.position = at + Vector3(0.0, -0.42, 0.0)
		pivot.rotation.y = atan2(frame.z.x, frame.z.z)
		root.add_child(pivot)

		var span := 1.42
		var arch: Array = []
		for step in 13:
			var u := float(step) / 12.0
			arch.append(Vector3(
				lerpf(-span, span, u), sin(u * PI) * 0.58 - 0.32, 0.0))
		pivot.add_child(Forms.mesh_node(
			Geometry.tube(arch, 0.075, 10),
			palette.get_material("silver"), "Hoop"))
		pivot.add_child(Forms.mesh_node(
			Geometry.tube(arch, 0.026, 8),
			palette.get_material("neon_blue"), "HoopLight", false))

		for side in [1.0, -1.0]:
			var shoe := Forms.mesh_node(
				Geometry.rounded_box(Vector3(0.28, 0.20, 0.36), 0.07, 3),
				palette.get_material("graphite_soft"),
				"Shoe%s" % ("R" if side > 0.0 else "L"))
			shoe.position = Vector3(side * span, -0.38, 0.0)
			pivot.add_child(shoe)
	return root


static func warm_furniture(palette, path: Array, banks: Array) -> Node3D:
	## The right route's fittings: cages over the channel, and gold ratchets.
	##
	## Where the left route is carried by arches that stay clear of it, the
	## right route is *held down* by three cage frames that pass over the top
	## of the channel. Same structural job, opposite read - and from any
	## camera the warm branch is the one with things across it.
	var root := Node3D.new()
	root.name = "WarmFurniture"

	for t in [0.18, 0.46, 0.74]:
		var index: int = clampi(int(round(float(t) * float(path.size() - 1))),
			0, path.size() - 1)
		var frame: Basis = V2Forms.banked_basis(path, banks, index)
		var at: Vector3 = path[index]
		var pivot := Node3D.new()
		pivot.name = "Cage%d" % int(float(t) * 100.0)
		pivot.position = at
		pivot.rotation.y = atan2(frame.z.x, frame.z.z)
		root.add_child(pivot)

		for side in [1.0, -1.0]:
			var post := Forms.mesh_node(
				Geometry.rounded_box(Vector3(0.17, 1.30, 0.22), 0.06, 3),
				palette.get_material("graphite"),
				"Post%s" % ("R" if side > 0.0 else "L"))
			post.position = Vector3(side * 1.05, -0.10, 0.0)
			pivot.add_child(post)

		var lintel := Forms.mesh_node(
			Geometry.rounded_box(Vector3(2.36, 0.20, 0.26), 0.08, 3),
			palette.get_material("orange_machine"), "Lintel")
		lintel.position = Vector3(0.0, 0.50, 0.0)
		pivot.add_child(lintel)

		var strip := Forms.mesh_node(
			Geometry.tube([Vector3(-1.02, 0.40, 0.12), Vector3(1.02, 0.40, 0.12)],
				0.030, 8),
			palette.get_material("lit_orange_line"), "LintelLight", false)
		pivot.add_child(strip)

		var ratchet := Forms.mesh_node(
			Geometry.rounded_disc(0.24, 0.16, 0.06, 14, 3),
			palette.get_material("gold"), "Ratchet")
		ratchet.position = Vector3(1.05, 0.50, 0.0)
		ratchet.rotation.z = PI * 0.5
		pivot.add_child(ratchet)
	return root


static func hazard_deck(palette) -> Node3D:
	## The spinner field between and behind the two branches.
	##
	## The reference concept's choice zone is not two tracks on empty air -
	## there is a dark deck between them carrying a scatter of small orange
	## rotors, and that deck is most of what makes the zone read as *the
	## dangerous part of the machine*. Nine spinners on two shelves: enough to
	## be a field, few enough that each one is still an object at phone size.
	##
	## They sit at z = -1.5, behind both channels' centrelines, so nothing
	## here ever crosses a racer's sightline.
	var root := Node3D.new()
	root.name = "HazardDeck"

	var shelves := [
		[10.80, 2.70, 0.00, 5],
		[8.70, 2.30, 0.00, 4],
	]
	for shelf_index in shelves.size():
		var shelf: Array = shelves[shelf_index]
		var y: float = shelf[0]
		var half: float = shelf[1]
		var offset: float = shelf[2]
		var count: int = shelf[3]

		var deck := Forms.mesh_node(
			Geometry.rounded_box(Vector3(half * 2.0, 0.20, 1.05), 0.08, 3),
			palette.get_material("graphite_deep"), "Deck%d" % shelf_index)
		deck.position = Vector3(offset, y, -1.55)
		root.add_child(deck)

		var edge := Forms.mesh_node(
			Geometry.rounded_box(Vector3(half * 2.0 + 0.14, 0.07, 1.16),
				0.03, 2),
			palette.get_material("gold"), "DeckEdge%d" % shelf_index, false)
		edge.position = Vector3(offset, y - 0.12, -1.55)
		root.add_child(edge)

		for index in count:
			var t: float = (float(index) + 0.5) / float(count)
			var x: float = offset + lerpf(-half + 0.34, half - 0.34, t)
			var lift: float = 0.42 + 0.16 * float((shelf_index + index) % 3)
			root.add_child(_spinner(palette,
				Vector3(x, y + lift, -1.50),
				float(index) * 0.7 + float(shelf_index) * 0.3,
				"Spinner%d_%d" % [shelf_index, index]))
	return root


static func _spinner(palette, at: Vector3, phase: float,
		node_name: String) -> Node3D:
	## One obstacle rotor: a post, a gold hub, six short orange blades.
	##
	## Small - 0.62 across against a 0.57 racer - because an obstacle that
	## dwarfs the thing it obstructs reads as scenery. Registered as a
	## `spin_phase` on the node so the motion proof can turn them.
	var root := Node3D.new()
	root.name = node_name
	root.position = at

	var post := Forms.mesh_node(
		Geometry.rounded_box(Vector3(0.11, 0.62, 0.11), 0.04, 3),
		palette.get_material("graphite"), "Post")
	post.position = Vector3(0.0, -0.34, 0.0)
	root.add_child(post)

	var wheel := Node3D.new()
	wheel.name = "Wheel"
	wheel.rotation.y = phase
	root.add_child(wheel)

	var hub := Forms.mesh_node(
		Geometry.rounded_disc(0.11, 0.13, 0.045, 14, 3),
		palette.get_material("gold"), "Hub")
	wheel.add_child(hub)

	for index in 6:
		var bearing := TAU * float(index) / 6.0
		var blade := Forms.mesh_node(
			Geometry.rounded_box(Vector3(0.22, 0.055, 0.10), 0.022, 2),
			palette.get_material("orange_machine"), "Blade%d" % index)
		blade.position = Vector3(cos(bearing) * 0.22, 0.0, sin(bearing) * 0.22)
		blade.rotation.y = -bearing
		wheel.add_child(blade)

	var lamp := Forms.mesh_node(
		Geometry.rounded_disc(0.055, 0.05, 0.02, 10, 2),
		palette.get_material("neon_orange"), "Lamp", false)
	lamp.position = Vector3(0.0, 0.10, 0.0)
	wheel.add_child(lamp)
	root.set_meta("spin_phase", phase)
	return root


static func route_signs(palette) -> Node3D:
	## Two small illuminated route markers, one per branch.
	##
	## Not text - at hero distance a word this size is four pixels of mush.
	## A blue disc with a smooth chevron and an amber disc with a jagged one,
	## carried on short gold posts off the splitter's shoulders. They read as
	## signage by their shape and their placement, which is all a sign at this
	## scale is ever going to do.
	var root := Node3D.new()
	root.name = "RouteSigns"

	for entry in [[-1.0, "neon_blue", "acrylic_blue", "L", 0.0],
			[1.0, "neon_orange", "acrylic_amber", "R", 1.0]]:
		var side: float = entry[0]
		var jagged: float = entry[4]
		var pivot := Node3D.new()
		pivot.name = "Sign%s" % str(entry[3])
		pivot.position = Vector3(side * 1.90, Layout.SPLIT_TOP_Y - 0.30, 0.55)
		pivot.rotation.y = -side * 0.42
		root.add_child(pivot)

		pivot.add_child(Forms.mesh_node(
			Geometry.tube([Vector3(0.0, -0.62, 0.0), Vector3(0.0, 0.0, 0.0)],
				0.055, 8),
			palette.get_material("gold"), "Post"))

		var face := Forms.mesh_node(
			Geometry.rounded_disc(0.40, 0.09, 0.035, 22, 3),
			palette.get_material(str(entry[2])), "Face", false)
		face.rotation.x = PI * 0.5
		pivot.add_child(face)

		var ring := Forms.mesh_node(
			Forms.hoop(0.40, 0.035, 24, 8),
			palette.get_material(str(entry[1])), "Ring", false)
		ring.rotation.x = PI * 0.5
		pivot.add_child(ring)

		# The chevron: two bars meeting at a point, and the jagged one gets a
		# sharper included angle plus a third bar. Shape is the whole message.
		for step in 2:
			var lift: float = -0.10 + 0.20 * float(step)
			var bar := Forms.mesh_node(
				Geometry.rounded_box(
					Vector3(0.30, 0.055, 0.05), 0.02, 2),
				palette.get_material(str(entry[1])),
				"Chevron%d" % step, false)
			bar.position = Vector3(0.0, lift, 0.06)
			bar.rotation.z = (0.55 + jagged * 0.45) * (1.0 if step == 0 else -1.0)
			pivot.add_child(bar)
	return root
