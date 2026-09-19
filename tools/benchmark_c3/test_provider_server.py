"""Regression tests for the Benchmark C3 apparatus's provider_server.py.

These tests exercise the ACTUAL MCP stdio server process via the real
mcp.client library (mcp.client.stdio.stdio_client + mcp.ClientSession),
the same client machinery a real MCP-speaking agent uses -- not a
reimplementation of the server's query logic. This is deliberate: an
earlier hand-written simulation of ctags_query's symbols_in_file branch
did not reproduce a real defect (it discarded each match's own name and
substituted the queried file path), which was only caught when a live
Claude Code session actually called the real server
(session 69867a18-32cd-49f6-be40-3b0c4ea6564b, Benchmark C3 Task A/C1).
These tests exist so that defect class cannot recur silently.

Run with: python -m pytest tools/benchmark_c3/test_provider_server.py -v
(No pytest-asyncio dependency -- each test drives its own asyncio.run.)
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

PYTHON = r"C:\Users\mgial\.benchmark-c2\tsvenv\Scripts\python.exe"
SERVER = r"C:\Users\mgial\.benchmark-c3\mcp\provider_server.py"
TARGET_FILE = "godot/assets/marble_machine/environment/environment_world.gd"


async def _call(which: str, tool_name: str, **arguments) -> dict:
    params = StdioServerParameters(command=PYTHON, args=[SERVER, which])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            text = result.content[0].text
            outer = json.loads(text)
            # provider_server.py tools return a JSON string as their payload;
            # FastMCP additionally wraps it under {"result": "<that string>"}
            # in some transports -- unwrap once more if present.
            if isinstance(outer, dict) and "result" in outer and isinstance(outer["result"], str):
                return json.loads(outer["result"])
            return outer


def run(coro):
    return asyncio.run(coro)


# --- Ctags -------------------------------------------------------------

def test_ctags_symbols_in_file_names_are_not_the_file_path():
    payload = run(_call("ctags", "ctags_query", query_kind="symbols_in_file", value=TARGET_FILE))
    assert payload["available"] is True
    assert payload["match_count"] > 0
    for entry in payload["matches"]:
        # entry format: "file:line:kind:name"
        name = entry.rsplit(":", 1)[-1]
        assert name != TARGET_FILE, f"regression: entry name fell back to the file path: {entry!r}"
        assert "/" not in name, f"regression: entry name looks like a path, not a symbol: {entry!r}"


def test_ctags_find_definition_sited():
    payload = run(_call("ctags", "ctags_query", query_kind="find_definition", value="_sited"))
    assert payload["available"] is True
    matches = payload["matches"]
    assert any(TARGET_FILE in m and ":249:" in m and m.endswith(":_sited") for m in matches), matches
    for m in matches:
        assert m.endswith(":_sited"), f"find_definition('_sited') returned a mis-named entry: {m!r}"


def test_ctags_find_definition_action_clearance():
    payload = run(_call("ctags", "ctags_query", query_kind="find_definition", value="action_clearance"))
    assert payload["available"] is True
    assert payload["match_count"] == 4
    files = {m.split(":")[0] for m in payload["matches"]}
    assert files == {
        "godot/assets/marble_machine/hero/hero_bowl.gd",
        "godot/assets/marble_machine/hero/hero_collector.gd",
        "godot/assets/marble_machine/hero/hero_finish.gd",
        "godot/assets/marble_machine/v2/v2_bowl.gd",
    }
    for m in payload["matches"]:
        assert m.endswith(":action_clearance"), m


def test_ctags_bounds_and_json_validity():
    payload = run(_call("ctags", "ctags_query", query_kind="symbols_in_file", value=TARGET_FILE))
    assert isinstance(payload, dict)
    assert payload["truncated"] is True  # 38 real symbols, MAX_MATCHES=20
    assert payload["match_count"] <= 20


# --- tree-sitter ---------------------------------------------------------

def test_treesitter_symbols_in_file_names_correct():
    payload = run(_call("treesitter", "treesitter_query", query_kind="symbols_in_file", value=TARGET_FILE))
    assert payload["available"] is True
    compacts = [m["compact"] for m in payload["matches"]]
    assert any(c.endswith(":_track_gap") for c in compacts), compacts
    assert any(c.endswith(":_clear") for c in compacts), compacts
    assert any(c.endswith(":_sited") for c in compacts), compacts
    for c in compacts:
        name = c.rsplit(":", 1)[-1]
        assert name != TARGET_FILE, f"regression: tree-sitter also substituted the file path: {c!r}"


def test_treesitter_find_definition_sited_with_body():
    payload = run(_call("treesitter", "treesitter_query", query_kind="find_definition", value="_sited", with_body=True))
    assert payload["available"] is True
    target = [m for m in payload["matches"] if TARGET_FILE in m["compact"]]
    assert len(target) == 1, payload["matches"]
    entry = target[0]
    assert entry["compact"].split(":")[1] == "249-256"
    assert "body" in entry and entry["body"], "expected a non-empty body"
    assert "Both constraints at once" in entry["body"]


def test_treesitter_find_definition_action_clearance_with_body():
    payload = run(_call("treesitter", "treesitter_query", query_kind="find_definition", value="action_clearance", with_body=True))
    assert payload["available"] is True
    assert payload["match_count"] == 4
    bodies = [m["body"] for m in payload["matches"]]
    assert all(b.strip().startswith("static func action_clearance()") for b in bodies)
    # hero_bowl.gd and v2_bowl.gd share an identical formula; v2_bowl.gd carries
    # one extra doc-comment line the other three lack.
    doc_comment_count = sum("volume that must stay clear of structure" in b for b in bodies)
    assert doc_comment_count == 1


def test_treesitter_bounds_and_json_validity():
    payload = run(_call("treesitter", "treesitter_query", query_kind="symbols_in_file", value=TARGET_FILE))
    assert isinstance(payload, dict)
    assert payload["truncated"] is True
    assert payload["match_count"] <= 20


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
