extends SceneTree

const G := preload("res://scripts/toy_geometry.gd")

func _report(label: String, mesh: ArrayMesh) -> void:
	var total := 0
	for s in mesh.get_surface_count():
		total += mesh.surface_get_array_len(s)
	var aabb := mesh.get_aabb()
	print("%-18s surfaces=%d verts=%d aabb=%s size=%s" % [
		label, mesh.get_surface_count(), total, str(aabb.position.round()),
		str(aabb.size)])

func _initialize() -> void:
	_report("rounded_box", G.rounded_box(Vector3(2.0, 0.5, 3.0), 0.16, 4))
	_report("rounded_disc", G.rounded_disc(1.0, 0.3, 0.08, 32, 3))
	var pts := [Vector2(0.2, 0.0), Vector2(0.8, 0.4), Vector2(1.0, 1.0)]
	_report("lathe", G.lathe(pts, G.profile_normals(pts), 32))
	var path := G.arc_path(Vector3.ZERO, 3.0, 0.0, PI * 0.6, 0.0, -1.2, 20)
	var sec: Array = G.channel_section(0.7, 0.28, 0.34, 0.10, 3)
	_report("swept channel", G.sweep(path, sec[0], sec[1], true))
	_report("tube", G.tube(path, 0.07, 10))
	print("section points=%d" % (sec[0] as Array).size())
	quit()
