"""Benchmark C4 apparatus: single-tool MCP stdio server for the C2 (tree-sitter)
condition only. C4 has no Ctags condition, so this file only implements
`treesitter`, unlike the C2/C3 apparatus this is adapted from.

Usage: provider_server.py treesitter

Loads the pre-built cache (godot/ content is byte-identical to Benchmark
C2/C3's baseline -- verified in source_fingerprints.json -- so the existing
C:\\Users\\mgial\\.benchmark-c2\\mcp\\treesitter_cache.json is reused rather
than rebuilt) and exposes exactly one bounded, read-only tool: treesitter_query.
Never exposes ground truth, never writes anything.

TRACKED-COPY NOTE: this file is committed here for provenance and review.
The file Claude Code's MCP configs actually launch during live runs is the
untracked operational copy at C:\\Users\\mgial\\.benchmark-c4\\mcp\\provider_server.py
(outside every git repo, like all benchmark run/ground-truth state). The two
must be kept byte-identical.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

CACHE_DIR = Path(r"C:\Users\mgial\.benchmark-c2\mcp")
MAX_MATCHES = 20
MAX_RESULT_CHARS = 4000
MAX_BODY_CHARS = 4000

which = sys.argv[1] if len(sys.argv) > 1 else "treesitter"
REPO_ROOT = Path(r"C:\Users\mgial\OneDrive\Documents\projects\wt-company-os-benchmark-c4")

if which != "treesitter":
    raise SystemExit(f"unsupported provider {which!r}: C4 only implements treesitter")

cache = json.loads((CACHE_DIR / "treesitter_cache.json").read_text(encoding="utf-8"))
_source_cache: dict[str, list[str]] = {}
mcp = FastMCP("treesitter_query")


def _lines_of(rel_file: str) -> list[str]:
    if rel_file not in _source_cache:
        path = REPO_ROOT / rel_file
        _source_cache[rel_file] = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return _source_cache[rel_file]


def _compact(name: str, m: dict) -> str:
    span = f"{m['start_line']}-{m['end_line']}" if m.get("end_line") else str(m["start_line"])
    return f"{m['file']}:{span}:{m['kind']}:{name}"


@mcp.tool()
def treesitter_query(query_kind: str, value: str, with_body: bool = False) -> str:
    """Query the isolated tree-sitter-gdscript index.

    query_kind: "find_definition" (value = symbol name) or
    "symbols_in_file" (value = repo-relative file path).
    with_body: if true, include a bounded (<=4000 char) body extracted
    from the exact line span for each match (find_definition only).
    No cross-file caller/reference graph is available.
    """
    if query_kind == "find_definition":
        matches = cache["by_name"].get(value, [])
    elif query_kind == "symbols_in_file":
        matches = cache["by_file"].get(value, [])
        matches = [{**m, "file": value} for m in matches]
    else:
        return json.dumps({"available": False, "reason": f"unsupported query_kind {query_kind!r}"})
    truncated = len(matches) > MAX_MATCHES
    matches = matches[:MAX_MATCHES]
    results = []
    total_chars = 0
    for m in matches:
        name = value if query_kind == "find_definition" else m["name"]
        entry = {"compact": _compact(name, m)}
        if with_body and query_kind == "find_definition" and m.get("end_line"):
            lines = _lines_of(m["file"])
            body = "\n".join(lines[m["start_line"] - 1: m["end_line"]])
            body_truncated = len(body) > MAX_BODY_CHARS
            if body_truncated:
                body = body[:MAX_BODY_CHARS]
            entry["body"] = body
            entry["body_truncated"] = body_truncated
        total_chars += len(entry["compact"]) + len(entry.get("body", ""))
        if total_chars > MAX_RESULT_CHARS:
            truncated = True
            break
        results.append(entry)
    return json.dumps({
        "provider": "tree_sitter_gdscript", "available": True,
        "truncated": truncated, "match_count": len(results), "matches": results,
    })


if __name__ == "__main__":
    mcp.run()
