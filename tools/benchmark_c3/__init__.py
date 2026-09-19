"""Benchmark C3 (Provider Utility, forced-use) — apparatus tooling and tests.

This package holds the C3 apparatus's own regression tests, which exercise
the real MCP provider_server.py process via the actual mcp.client library
(not a reimplementation of its query logic). It does not implement the
providers themselves -- those remain tools/benchmark_c2/ctags_provider.py
and tools/benchmark_c2/treesitter_provider.py, reused unchanged, since the
underlying godot/ source is unchanged between Benchmark C2 and C3.

Nothing here is imported by canonical Company OS runtime code or by
production Godot/Python code. It is read-only with respect to the
repository.
"""
