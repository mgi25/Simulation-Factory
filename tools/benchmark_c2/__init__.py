"""Benchmark C2 (AI Resource Optimization Lab) — isolated GDScript navigation providers.

Everything under this package exists only to run the Ctags / tree-sitter-gdscript
navigation benchmark. Nothing here is imported by canonical Company OS runtime
code or by production Godot/Python code, and nothing here is wired into
``company.efficiency.providers``. It is read-only with respect to the
repository: providers here index or parse tracked source files but never
write to them.
"""
