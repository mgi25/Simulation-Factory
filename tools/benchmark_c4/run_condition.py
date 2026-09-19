"""Benchmark C4: launch one independent `claude -p` official-run session for
one (task, condition) pair.

Adapted from tools/benchmark_c2's run_condition.py with one deliberate,
CEO-mandated change: this version NEVER uses --permission-mode
bypassPermissions or any dangerously-skip-permissions flag. Phase 7's
harness smoke test (see execution_policy.json) validated that
--permission-mode default plus explicit --allowedTools works non-
interactively via -p without hanging or silently broadening the tool
surface, so that is what every C4 official run uses instead.

Usage: run_condition.py <run_dir> <prompt_file> <output_jsonl> [--mcp-config PATH] [--extra-tool NAME]
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

RUNNER_REPO = Path(r"C:\Users\mgial\OneDrive\Documents\projects\wt-company-os-benchmark-c4")
sys.path.insert(0, str(RUNNER_REPO))

from tools.engineering_runner.redaction import child_environment  # noqa: E402

BASE_TOOLS = "Read,Grep,Glob,Bash"
DENY_BASE = "Edit,Write,TodoWrite,Task,Agent,WebSearch,WebFetch"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir")
    parser.add_argument("prompt_file")
    parser.add_argument("output_jsonl")
    parser.add_argument("--mcp-config", default=None, help="path to an MCP config JSON file, or omit for an empty ({\"mcpServers\":{}}) config")
    parser.add_argument("--extra-tool", default=None, help="fully-qualified mcp tool name to allow, e.g. mcp__treesitter_query__treesitter_query")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    prompt = Path(args.prompt_file).read_text(encoding="utf-8")

    allowed = BASE_TOOLS
    denied = DENY_BASE
    if args.extra_tool:
        allowed += "," + args.extra_tool

    claude_path = shutil.which("claude")
    if claude_path is None:
        raise SystemExit("claude CLI not found on PATH")
    launcher = ["cmd.exe", "/c", claude_path] if claude_path.lower().endswith((".cmd", ".bat")) else [claude_path]

    cmd = [
        *launcher, "-p", prompt,
        "--model", "claude-sonnet-5",
        "--output-format", "stream-json",
        "--verbose",
        "--no-session-persistence",
        "--setting-sources", "project,local",
        "--strict-mcp-config",
        "--mcp-config", args.mcp_config or '{"mcpServers":{}}',
        "--tools", BASE_TOOLS,
        "--allowedTools", allowed,
        "--disallowedTools", denied,
        "--permission-mode", "default",
    ]

    env = child_environment()
    env["CLAUDE_CODE_DISABLE_CLAUDE_MDS"] = "1"
    env["DISABLE_AUTOUPDATER"] = "1"
    env["DISABLE_UPDATES"] = "1"

    start = time.perf_counter()
    with open(args.output_jsonl, "w", encoding="utf-8") as out:
        proc = subprocess.run(
            cmd, cwd=str(run_dir), env=env,
            stdout=out, stderr=subprocess.STDOUT,
            timeout=3600,
        )
    wall_s = time.perf_counter() - start
    print(f"exit={proc.returncode} wall_s={wall_s:.2f}")
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
