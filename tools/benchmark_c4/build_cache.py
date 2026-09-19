"""Benchmark C4 apparatus: (re)build the tree-sitter provider cache.

C4 does not need a fresh build: godot/ on this branch is byte-identical to
the content Benchmark C2 already indexed (verified in
docs/validation/company_os_ai_resource_benchmark_c4/source_fingerprints.json),
so the existing C:\\Users\\mgial\\.benchmark-c2\\mcp\\treesitter_cache.json is
reused as-is by tools/benchmark_c4/provider_server.py. This script is
committed so the cache can be reproduced/reconfirmed independently rather
than trusted blindly, and to keep provenance for how it was originally
built. Running it against this checkout (against REPO_ROOT below) should
reproduce byte-for-byte the same by_name/by_file symbol data as the existing
cache (module-independent fields like _orchestration_wall_ms will differ).

Usage: build_cache.py treesitter   (writes to CACHE_DIR/treesitter_cache_reconfirm.json,
deliberately NOT overwriting the cache actually in use, to avoid any chance
of a mid-benchmark apparatus change)
"""
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(r"C:\Users\mgial\OneDrive\Documents\projects\wt-company-os-benchmark-c4")
CACHE_DIR = Path(r"C:\Users\mgial\.benchmark-c4\mcp")

sys.path.insert(0, str(REPO_ROOT))


def build_treesitter_cache() -> dict:
    from tools.benchmark_c2.treesitter_provider import TreeSitterProvider

    provider = TreeSitterProvider(REPO_ROOT)
    if not provider.available:
        raise RuntimeError(f"tree-sitter-gdscript unavailable: {provider.unavailable_reason}")
    stats = provider.build_index()
    cache = {
        "provider": "tree_sitter_gdscript",
        "stats": {
            "files_parsed": stats.files_parsed,
            "parse_failures": stats.parse_failures,
            "parse_time_ms": stats.parse_time_ms,
            "symbol_count": stats.symbol_count,
            "source_bytes_parsed": stats.source_bytes_parsed,
        },
        "by_name": {
            name: [
                {
                    "file": m.file.replace("\\", "/"), "kind": m.kind,
                    "start_line": m.start_line, "end_line": m.end_line,
                }
                for m in matches
            ]
            for name, matches in provider._symbols_by_name.items()
        },
        "by_file": {
            file.replace("\\", "/"): [
                {"name": m.name, "kind": m.kind, "start_line": m.start_line, "end_line": m.end_line}
                for m in matches
            ]
            for file, matches in provider._symbols_by_file.items()
        },
        "bodies": {},
    }
    return cache


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "treesitter"
    if which != "treesitter":
        raise SystemExit("C4 only implements treesitter (no Ctags condition)")
    start = time.perf_counter()
    data = build_treesitter_cache()
    out = CACHE_DIR / "treesitter_cache_reconfirm.json"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    wall_ms = (time.perf_counter() - start) * 1000
    data["_orchestration_wall_ms"] = round(wall_ms, 3)
    out.write_text(json.dumps(data), encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size} bytes), wall {wall_ms:.1f}ms, stats={data['stats']}")
