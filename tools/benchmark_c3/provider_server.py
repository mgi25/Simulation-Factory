"""Benchmark C3 apparatus: single-tool MCP stdio server for one condition.

Usage: provider_server.py ctags|treesitter

Loads the pre-built cache (see build_cache.py) and exposes exactly one
bounded, read-only tool: ctags_query or treesitter_query. Never exposes the
other provider, never exposes the answer key (it has no access to it -- the
cache contains only symbol/kind/file/line data derived from the real
godot/ source, the same thing Read/Grep could find), and never writes
anything.

This is the Benchmark C3 apparatus-amendment copy of Benchmark C2's
provider_server.py. It fixes one defect, discovered live during official
C3 Task A/C1 (session 69867a18-32cd-49f6-be40-3b0c4ea6564b): the Ctags
symbols_in_file branch discarded each match's real symbol name and
substituted the queried file path instead, making every returned entry's
name identical and useless for disambiguation. See
docs/validation/company_os_ai_resource_benchmark_c3/apparatus_amendment_ctags_symbols_in_file.json
for the full defect record. No other behavior changes; find_definition
(both providers) and treesitter's symbols_in_file were already correct
and are unchanged.

TRACKED-COPY NOTE: this file is committed here for provenance and so
tools/benchmark_c3/test_provider_server.py has something checked-in to
point at in CI/review. The file that Claude Code's MCP configs actually
launch during live runs is the untracked operational copy at
C:\\Users\\mgial\\.benchmark-c3\\mcp\\provider_server.py (outside every git
repo, like all benchmark run/ground-truth state). The two must be kept
byte-identical; this apparatus-amendment commit updates both together.
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

which = sys.argv[1] if len(sys.argv) > 1 else "ctags"
REPO_ROOT = Path(r"C:\Users\mgial\OneDrive\Documents\projects\wt-company-os-benchmark-c3")

if which == "ctags":
    cache = json.loads((CACHE_DIR / "ctags_cache.json").read_text(encoding="utf-8"))
    mcp = FastMCP("ctags_query")

    def _compact(name: str, m: dict) -> str:
        return f"{m['file']}:{m['start_line']}:{m['kind']}:{name}"

    @mcp.tool()
    def ctags_query(query_kind: str, value: str) -> str:
        """Query the isolated Universal Ctags GDScript index.

        query_kind: "find_definition" (value = symbol name) or
        "symbols_in_file" (value = repo-relative file path).
        Returns definitions with file+line only -- Ctags has no
        caller/reference graph for GDScript.
        """
        if query_kind == "find_definition":
            matches = cache["by_name"].get(value, [])
        elif query_kind == "symbols_in_file":
            matches = [
                {"file": value, "kind": e["kind"], "start_line": e["start_line"], "name": e["name"]}
                for e in cache["by_file"].get(value, [])
            ]
        else:
            return json.dumps({"available": False, "reason": f"unsupported query_kind {query_kind!r}"})
        truncated = len(matches) > MAX_MATCHES
        matches = matches[:MAX_MATCHES]
        # Apparatus fix (Benchmark C3): symbols_in_file matches now carry their
        # own real name (m["name"]), not the queried file path (`value`). The
        # prior version passed `value` here, making every entry's compacted
        # name identical to the file path -- confirmed live in session
        # 69867a18-32cd-49f6-be40-3b0c4ea6564b (Task A/C1).
        lines = [_compact(m["name"] if query_kind == "symbols_in_file" else m.get("name", value), m) for m in matches]
        # For find_definition, `name` isn't in each match dict (it's the key); use `value`.
        if query_kind == "find_definition":
            lines = [_compact(value, m) for m in matches]
        chars = sum(len(l) for l in lines)
        if chars > MAX_RESULT_CHARS:
            kept, running = [], 0
            for l in lines:
                running += len(l)
                if running > MAX_RESULT_CHARS:
                    truncated = True
                    break
                kept.append(l)
            lines = kept
        return json.dumps({
            "provider": "ctags", "available": True, "truncated": truncated,
            "match_count": len(lines), "matches": lines,
        })

elif which == "treesitter":
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

else:
    raise SystemExit(f"unknown provider {which!r}")

if __name__ == "__main__":
    mcp.run()
