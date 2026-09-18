# Company OS — AI Resource Optimization Research + Benchmark Design

Research and benchmark-design milestone. No external tool is installed, no
production or Company OS runtime code is changed, no live A/B benchmark is
run. Everything below is read-only analysis of the committed lineage plus
current external research, per the brief's constraints.

Branch: `company-os-v1-resource-optimization-research`
Base: `origin/company-os-v1-bootstrap` @ `b84f8a75a2d4aaeefd88798f23bc5948e7d39195`
Worktree: `C:/Users/mgial/OneDrive/Documents/projects/wt-company-os-resource-optimization-research`
(sibling of the main clone; the active `v21-visual-contrast` worktree was not
touched).

`main` observed at `8b1022aec899c7fa72ca77f2a1441c4d1b4ff48f` (read-only, via
`git ls-tree`/`git show` against `origin/main`; no checkout). Both refs matched
the brief's expected values exactly at task start; nothing had advanced.

---

## 1. Current resource architecture

This audits what already exists, so no candidate below gets credit for
solving an already-solved problem. All file paths are on
`company-os-v1-bootstrap` @ `b84f8a7` unless stated otherwise.

| Capability | Present | Where |
|---|---|---|
| Model routing | yes | `company/engineering/intake.py::derive_routing` — reasoning-class classifier (A–F), four named routes to the strongest tier, none silent |
| Task/resource classification | yes | `ai_platform/resource_classes.py`; `company/efficiency/strategy.py::select_strategy` |
| Context narrowing | yes | `company/efficiency/profile.py` (`consumer`/`expanded` resource profiles); `ai_platform/context_manifest.py` reference-only manifests |
| Context reference limits | yes | `ai_platform/references.py`; profile-scoped `include_capsule_dependencies` toggle |
| ExecutionContextBundle | yes | `tools/engineering_runner/execution_context.py` — ranked files, symbol spans, dependents, test anchors, bounded excerpts, `MAX_BUNDLE_CHARS = 6000` (line 51) |
| Symbol spans | yes | `tools/engineering_runner/repo_map.py::ModuleMap.symbols` — qualified name/kind/start-end line, stdlib `ast` only |
| Reverse production dependencies | yes | `repo_map.py::RepoMap.production_dependents` (a real reverse index; an earlier version's docstring claimed one before it existed) |
| Test anchors | yes | `execution_context.py::TestPatternAnchor` (line 133) — deterministic identifier/token matching, no LLM, no embeddings; developer briefing only, never reviewer |
| Repo map | yes | `repo_map.py` — stdlib `ast` over `company/` + `tools/` + `tests/` only; 413 modules, 1.74 s build, 554,922-char JSON at V1's measurement; never handed whole to a session, queried for a ranked 2–5-hit slice |
| Stream-json exploration telemetry | yes | `tools/engineering_runner/exploration_telemetry.py`, `exploration_report.py` — requires `--verbose` under `--print --output-format stream-json`; V1's `--output-format json` launch mode could never expose this, permanently, for any session launched that way |
| Cache-read/cache-creation telemetry | PARTIAL | cache-read captured and cross-checked; cache-creation is captured for the session total but `cache_creation_input_tokens` was never captured per-segment (see [[ai-resource-efficiency-v2-telemetry-defect]]) |
| Cost telemetry | yes, RELIABLE | `backends.py::normalise_claude_usage` — session-total `modelUsage` cross-checked against `total_cost_usd`; disagreement is recorded and the larger figure is kept, never averaged away |
| Turn reliability | PARTIAL | `model_turns` reclassified `UNAVAILABLE → POST_SESSION_OBSERVABLE` in `company/efficiency/budget.py`; trustworthy only when the two usage segments agree, explicitly marked `unreliable_metrics` otherwise |
| File-read/search telemetry | PARTIAL | `repo_file_reads`/`repo_searches`/`repeated_file_reads` moved `UNAVAILABLE → POST_SESSION_OBSERVABLE` in `budget.py` (lines ~172–190) once `stream-json` was wired; not retroactive to sessions stored before that fix |
| Reviewer context narrowing | PARTIAL | test anchors are developer-only by design; reviewer bundle unchanged by V3B, deliberately |
| Output reduction | present, UNREACHABLE in production | `capture_tool_output`/`reduce_*` filters exist but have no production caller — the developer's tool output happens inside the external `claude` CLI subprocess, outside Company OS's own process |
| Minimalism instructions | yes, internal | briefing text and this project's own working style (smallest diff, reuse existing implementation, no speculative abstraction) — see §9 below for the Ponytail comparison |
| No-subagents enforcement | yes, doubly enforced | traced end-to-end org_registry → permissions.bootstrap_defaults → employee contract → ExecutionPolicy → packet → receipt → usage record (`test_the_no_subagent_rule_holds_at_every_link`); independently, `production.no_publishing_capability` forbids the process-spawning primitives a subagent would need regardless |
| Wall-clock ceiling | yes, LIVE_ENFORCEABLE | 1,800 s, runner terminates the child process; largest recorded live duration is 305.9 s, so never yet actually triggered live |
| Cost ceiling | yes, LIVE_ENFORCEABLE (with a bug fixed) | `--max-budget-usd` binds at turn boundaries, not mid-turn (a $0.0001 ceiling still overshot to $0.042 in the live probe); `backends._read` now reads the `error_*` subtype rather than trusting `is_error` alone |
| Retry ceiling | yes | consumer profile: 1 automatic developer attempt, 1 reviewer pass, no auto-continue after `changes_required`; exhaustion moves the job to `decision_required`, an existing lifecycle state |
| Code-intelligence provider seam | present, deliberately unwired | `company/efficiency/providers.py::CodeIntelligenceProvider` / `CodeQueryKind.LIKELY_FILES` (lines 114–159) — the stub's own docstring says the query kind "remain[s] unavailable until a real provider (for example Graphify) is installed." Used only by `benchmark.py` and tests, never by the live `emission.py` path. Wiring it to the new repo map was deliberately declined in V1 because zero `company/` modules import anything from `tools/`, and adding the first such edge to save one Protocol implementation was judged not worth a new cross-boundary dependency |

**Reading.** Every capability the brief asks to check for already exists, in
a form the committed evidence has already exercised on a live job at least
once, with one exception: the code-intelligence provider seam is real code
with zero live callers, built specifically to receive a tool like Graphify
without Company OS ever importing it directly. That seam is the correct
integration point if a candidate is ever adopted — not a new import into
`company/efficiency/emission.py`.

---

## 2. Historical measurements (the resource-use baseline)

Reproduced from committed evidence, not re-measured. Source documents:
`docs/company_os_consumer_resource_mode.md`,
`docs/company_os_repository_exploration_efficiency.md`,
`docs/company_os_repository_exploration_efficiency_v2.md`,
`docs/company_os_read_efficiency_v3b.md`,
`docs/company_os_v1_operational_readiness.md` §2. No number below was invented
for this milestone.

### A. Exact same-task comparisons

**Task 1 — `attempts-remaining` (identical objective, rerun at successive baselines):**

| | BEFORE (`01a1638`, opus) | AFTER-V2 (`5d73557`, opus) | Consumer Mode V1 (sonnet) |
|---|---:|---:|---:|
| authorized attempts | 3 | 3 | **1** |
| developer cost | $1.2719 | $1.7408 | $1.6406 |
| job cost (dev+reviewer) | $1.6317 | $2.0784 | $1.9362 |
| developer turns | 29 | — | 39 |
| developer cache-read | 1,347,797 | 2,226,932 | 1,835,390 |
| reviewer / gate | pass / ready | pass / ready | pass / ready |

The cheaper model did not do the same work more cheaply on this workload —
it took 39 turns / 11,020 output tokens against BEFORE's 29 / 5,821. **The
model-tier lever is weak here.**

**Task 2 — `blocked_attempts` (the strongest exact-task comparison in this
codebase, and the one the brief asks to feature):**

| | V2 (`783,941` cache-read baseline) | V3B (test anchors) |
|---|---:|---:|
| targeted pre-edit test reads | 10 | **4** (−60%) |
| developer cache-read | 783,941 | **568,012** (−27.5%) |
| developer turns | 26 | 19 |
| developer cost | $0.804993 | $0.635691 |
| reviewer cache-read | 47,922 | 46,535 (flat) |
| reviewer / gate | pass / ready | pass / ready |

**What actually caused the improvement, stated precisely (not "efficiency
tooling" in general):** V2's own report speculated its ten repeated reads of
one test file were the coding CLI's own edit-verification behavior. The real
stored `stream-json` transcript, re-parsed with range-aware telemetry, showed
`read_after_edit_count == 0` — none of the ten repeated reads followed an
edit. They were eight targeted, non-identical, strictly pre-edit reads
walking forward through the file hunting for a sibling counter test the work
order's acceptance criteria named only by pattern
(`docs/company_os_read_efficiency_v3a.md`). V3B's fix was narrow and
mechanical: `TestPatternAnchor` supplies the developer with the exact
qualified name of the sibling test pattern up front, in the briefing, so the
model's own first `Grep` call already contains the target identifier instead
of discovering it by walking the file. This is a **prompt/context-content**
fix, not a retrieval-architecture fix — it did not add a new tool, a new
index, or a new external dependency. That distinction matters directly for
whether Serena/Graphify/ast-grep would add anything here: they solve
"find the right file/symbol I don't know the name of," and this bottleneck
was "know the exact name and stop re-deriving it."

### B. Similar-task comparisons (same tier/risk/shape, different objective)

| | Consumer V1 (`attempts-remaining`) | Repo Exploration V1 (`reviews-completed`) | Repo Exploration V2 (`blocked-count`) |
|---|---:|---:|---:|
| developer cache-read | 1,835,390 | 990,324 (−46.0%) | 783,941 (−20.84% vs. V1) |
| developer turns | 39 | 27 | 26 |
| developer cost | $1.640637 | $1.083562 | $0.804993 |
| reviewer cache-read | — | 158,520 | 47,922 (−69.8% vs. V1) |
| total job cost | — | ~$1.457 | $1.018683 (−30.1% vs. V1) |

These three are genuinely different named objectives on the same
subsystem/shape/risk category, not reruns of one task — treated separately
from category A per the brief's instruction not to average categories
together. All three passed review and gate on the first attempt.

### C. Historical unmatched sessions

21 stored sessions across six runner-state roots: **average developer
cache-read 2,584,057; max 7,245,449.** This is the "broader stored-session
average" the operating-state stop-conditions reference as an outer bound —
not a controlled comparison, and not used as if it were one anywhere in this
report.

### RTK, measured live during this milestone (operator-level, not Company OS)

`rtk --version` → `0.43.0`, installed and active on this operator's machine
via the Claude Code Bash hook described in the user's own `RTK.md`. `rtk gain`
(global scope, this account, all projects, 38,615 recorded commands):

| Command class | Count | Tokens saved | Avg % |
|---|---:|---:|---:|
| `rtk read` | 3,636 | 14.5M | 11.4% |
| `rtk grep` | 9,333 | 5.0M | 24.4% |
| `rtk ls -la tests/` | 180 | 186.6K | 56.9% |
| `rtk git log -p --format...` | 1 | 132.0K | 99.8% |
| `rtk diff` | 9 | 109.4K | 99.1% |
| `rtk pytest -q ...` | 6+18 | 98.7K+89.1K | 86.9–88.2% |
| overall | 38,615 | **23.5M (63.8%)** | — |

**Reading, stated precisely per the brief's §8 instruction:** the two
largest absolute-token buckets are `read` (14.5M) and `grep` (5.0M) — over
19M of the 23.5M total. `git`/`pytest`/`diff` output together account for
under 500K, three orders of magnitude smaller, despite each showing a very
high *percentage* reduction on its own line. **RTK's own telemetry, at the
operator's own global scale, says its dominant value is file-read and
search-output compression, not shell/git/test-output compression** — this
matches, rather than contradicts, V3B's own finding that Company OS's
dominant developer cost on Company/Python work is now `Read`/`Grep` calls and
genuine implementation edits, not raw Bash text. `rtk discover` (this
project, this session) found 0 scannable prior sessions — inconclusive, not
a null result, and not used as evidence either way.

**RTK is not, and cannot currently be, a Company OS runtime dependency.**
`docs/company_os_read_efficiency_v3b.md`'s own "External tools" section
records it explicitly: *"RTK: not installed (governance boundary preserved:
the runner subprocess ran outside RTK's shell hook, since Company OS may not
run subprocesses at all and the runner is the one thing here that does)."*
The operator's interactive Claude Code session (this one) and the
`tools/engineering_runner`-spawned developer/reviewer sessions are different
processes with different shells; RTK's hook lives in the operator's shell
profile, not in the runner's `child_environment()`. Wiring RTK into the
runner's spawned CLI invocation is a small, mechanically distinct question
from whether the operator benefits from RTK personally — see §8 below.

---

## 3. Current bottleneck analysis

Classified `CURRENTLY MATERIAL` / `POSSIBLY MATERIAL` / `CURRENTLY SMALL` /
`NOT MEASURED`, each with the evidence behind the classification.

**A. Repository discovery cost (Company/Python side) — CURRENTLY SMALL.**
V3B's own conclusion: "discovery is now 5 reads total, 2 of them the file the
developer is about to edit anyway... any further efficiency gain here would
have to come from a different dimension... not from more repository
intelligence." `docs/company_os_v1_operational_readiness.md` §12 reached the
same conclusion independently and recommended no further tool experiments on
this task class. This is the one bottleneck category with the strongest,
most recent, most directly falsifying evidence against a new tool.

**B. Repository discovery cost (production/GDScript side) — NOT MEASURED.**
No Company OS job, dogfood or otherwise, has ever touched `race2/`, `sloped/`,
`marble3d/`, `godot/`, `engine/`, `modes/`, or `powers/` — all committed
evidence is from `company/`+`tools/engineering_runner/`+`tests/` work.
`repo_map.py` explicitly excludes the marble-race side of the repository by
design. There is no telemetry, matched job, or even an unmatched historical
session for this task class. This is the single largest genuine gap in the
evidence base, and it is exactly where Benchmarks B and C target.

**C. Local file navigation cost — POSSIBLY MATERIAL, language-dependent.**
On the Company/Python side, CURRENTLY SMALL per (A). On the production side,
§1 of the validation artifact
(`docs/validation/company_os_ai_resource_optimization/production_repo_measurement.md`)
found the single largest source file in the whole repository is GDScript
(`godot/scripts/neon_scene.gd`, 129,898 bytes) — larger than the largest
Python file (`sloped/stations.py`, 125,327 bytes / 2,617 lines) — and stdlib
`ast` cannot parse GDScript at all. Classified POSSIBLY MATERIAL rather than
CURRENTLY MATERIAL because no live session has ever actually had to navigate
either file; the cost is inferred from file size, not measured from a
session.

**D. Prompt/context cost — CURRENTLY SMALL, measured directly.**
`consumer-resource-mode-stop-condition`: a routine packet was 1,552 chars;
what its references pointed at was 16,985 chars before the
`include_capsule_dependencies` fix, 3,661 after. `ExecutionContextBundle` is
hard-capped at 6,000 chars. V3B's own developer bundle was 9,807 chars in the
live matched job. These are all small relative to the multi-hundred-thousand
cache-read totals, which come overwhelmingly from tool-call outputs
accumulating in the session transcript, not from the initial packet.

**E. Model reasoning cost (turns, output units, retries) — POSSIBLY MATERIAL,
partly unreliable to measure.** Turn counts are `POST_SESSION_OBSERVABLE`
and were found unreliable in 1 of 19 real sessions by a full 60×. Where
reliable, turns track discovery reads closely (V3B: 19 turns for 5 reads +
6 edits + 2 shell calls); the reasoning-cost line item is currently
indistinguishable from the discovery-cost line item in the one exact-task
comparison available. No dedicated measurement exists that isolates
"reasoning" from "discovery" or "editing."

**F. Shell/tool-output cost — CURRENTLY SMALL for Company OS jobs, PARTIALLY
MATERIAL for the operator's own interactive use.** RTK's own global telemetry
(§2 above) shows git/pytest/diff output is a small fraction of total savings
compared to read/grep. `CommandRunner.run` in `process.py` captures raw
subprocess output once per call (unchanged since V2); no measurement exists
of how large that captured text typically is for this repository's own
pytest/git invocations specifically, only RTK's aggregate figure across all
of this operator's other projects. Classified NOT MEASURED for
Simulation-Factory-specific shell output size, CURRENTLY SMALL by inference
from the aggregate.

**G. Cross-language navigation — CURRENTLY MATERIAL by construction, per (B)
and (C).** No Python-AST-based tool in this codebase's toolchain (the
internal `repo_map.py`, ast-grep's Python binding, SCIP's `scip-python`) can
say anything about the 81 `.gd` files on `main`. This is not a measurement of
usage frequency — it is a hard capability gap, evidenced by the tools' own
documented language coverage (§4).

**H. Knowledge rediscovery — CURRENTLY SMALL, by design.** `knowledge/company_os/`
(five record types, decision ledger) exists specifically to make repeated
architecture facts a lookup rather than a re-read; this project's own memory
system (outside Company OS, at the operator level) serves the same role for
this specific line of work, and this milestone itself drew directly on 11
prior memory records instead of re-deriving them (§2 above).

**I. Review cost — CURRENTLY SMALL, with one real reduction already
measured.** Reviewer cache-read fell 69.8% from Repo-Exploration-V1 to V2
(158,520 → 47,922) as a side effect of the general context-narrowing work,
then stayed flat (47,922 → 46,535) through V3B, which deliberately did not
touch the reviewer briefing. "Reviewer cost" and "developer discovery cost"
have already diverged as separate, separately-measured line items.

**Tool/environment startup overhead — NOT MEASURED for any candidate,
because none is installed.** This is addressed as pure vendor-documentation
research in §4/§7, not as a measurement.

---

## 4. Candidate research

For each candidate: problem claimed, architecture, language support, license,
local/offline capability, whether it needs an LLM/embeddings/paid API/
subagents, and what Company OS capability it would duplicate vs. add. URLs
and research date (2026-09-19) recorded per candidate.

### 1. Serena (oraios/serena)

Symbol-level code retrieval/editing via Language Server Protocol, shipped as
an MCP server (also a JetBrains plugin). Claims 40+ languages including
GDScript, Python, C#, Rust, TypeScript. GDScript support depends on a running
Godot editor's own LSP server — this machine has Godot 4.7.2 at
`C:\Users\mgial\Downloads\Godot_v4.7.2-stable_win64.exe\...` (per
[[godot-binary-location]]), not on PATH, so the dependency is satisfiable but
requires launching and keeping alive a Godot editor process, which is a new
kind of long-lived process this project's tooling does not currently manage.
License: SolidLSP (LSP layer) MIT, the Serena application itself GPL-3.0-or-
later — a distribution combining both is GPL as a whole. Fully local; no
telemetry to Oraios servers documented. Registers 20+ tools by default
(duplicating Read/Grep/Glob/Edit), but ships `context`/`mode` configuration
(`no-onboarding`, `no-memories`) specifically to strip that down, and the
brief's own §7 minimal-configuration ask (`find_symbol`,
`get_symbols_overview`, `find_referencing_symbols`, `find_implementations`)
is directly supported by that mechanism, not merely aspirational. Onboarding
itself is documented as expensive ("reads a lot of content... consider
switching conversations after") and skippable. No embeddings, no vector
store, no internal LLM call, no subagents. Windows support: yes (Python
package + language servers, cross-platform by design). Version 1.5.1 as of
2026-05-18, 24,351 GitHub stars, active.
Unique capability: cross-language symbol-level navigation via a real
language server, specifically including GDScript — the one language this
repository's internal tooling has zero coverage for.
Duplicates: `find_symbol`/`get_symbols_overview` overlap Grep/Read for
Python, where V1/V3B already found discovery is CURRENTLY SMALL.
Sources: [oraios/serena](https://github.com/oraios/serena),
[Serena memories/onboarding docs](https://oraios.github.io/serena/02-usage/045_memories.html),
[Serena license](https://github.com/oraios/serena/blob/main/LICENSE).

### 2. Graphify (Graphify-Labs/graphify)

Deterministic local AST-based knowledge graph over a codebase (plus optional
LLM-assisted extraction for docs/PDFs, off by default with `--code-only`).
"Pass 1/2" (graph build, code-only) requires no API key, no embeddings, no
vector store — every answer is an explicit graph path with file:line
citations. Ships a PreToolUse hook + CLAUDE.md directive for Claude Code
integration, and a related "code-review-graph" component exposing ~25 MCP
tools (`whoCalls`, `blastRadius`, `deadExports`, `neighborhood`,
`references`), allow-listable down to a working set of ~8. Incremental
updates: re-extracts only the changed subgraph, ~0.8s for 3 changed files.
License: MIT/Apache-2.0, free for commercial use, no account required for
the code-only path. Windows support not separately confirmed in vendor docs;
treat as unverified until probed. GDScript support not documented — the
project's own marketing centers on JS/TS/Python-ecosystem codebases;
absence of a specific claim is itself evidence against assuming coverage.
Unique capability over the internal `repo_map.py`: multi-hop call-graph
queries (`whoCalls`, `blastRadius`) — the internal map has single-hop reverse
production-dependents only, no transitive call graph.
Duplicates: `repo_map.py`'s symbol spans and reverse-dependents for the one-
hop case, where V1/V2 already measured this at small absolute cost
(1.74s build, single-digit-KB queries).
Sources: [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify),
[Graphify pricing](https://graphify.com/pricing),
[code-review-graph via dev.to writeup](https://dev.to/mir_mursalin_ankur/graphify-code-review-graph-build-a-self-updating-knowledge-graph-for-claude-code-and-other-ai-j1m).

### 3. RTK (Rust Token Killer)

Already researched live, not from vendor docs — see §2. Installed at the
operator level (v0.43.0), hooked transparently into this Claude Code
session's own Bash tool calls per the user's global `RTK.md`/`CLAUDE.md`.
Zero cost, zero embeddings, zero LLM, no subagents — it is a local,
deterministic output-filtering proxy for shell commands. Windows: confirmed
working live, right now, in this exact session. Not installed inside Company
OS's runner-spawned child processes, deliberately, because the runner is the
one thing in this repository permitted to spawn subprocesses at all and its
`child_environment()` is a governance-relevant allowlist, not an ordinary
shell profile.
Unique capability: output-size reduction on `read`/`grep`/`git`/`pytest`
invocations, largest on `read`/`grep` specifically per its own global
telemetry.
Duplicates: nothing in Company OS today — `capture_tool_output`'s reduce
filters exist but have no production caller (§1), so RTK would be additive,
not redundant, *if* it were wired into the runner's child process, which is
a distinct question from the operator already benefiting from it personally.
Sources: this session's own `rtk --version` / `rtk gain` output; user's
`RTK.md`.

### 4. Ponytail (DietrichGebert/ponytail)

Not a code tool — a skill/prompt pack (a decision ladder: YAGNI → codebase
reuse → stdlib → native platform → installed deps → one-liner → minimal
implementation) distributed as Claude Code/Codex/Copilot/Gemini skill files.
MIT license. No indexing, no dependency, no runtime footprint at all — it is
markdown instructions injected into the session, comparable in mechanism to
this project's own working-style guidance already present in this
conversation's system instructions ("don't add features... reuse existing
implementation... smallest coherent diff... no speculative abstractions").
Claims 54% average code-volume reduction, up to 94%, from the vendor's own
benchmark — not independently reproduced here.
Unique capability over internal minimalism instructions: none identified.
The seven-step ladder is a more explicit, more granular restatement of rules
this project's session instructions and Company OS's own review culture
already encode; no distinct behavior was found in the public description
that these instructions do not already ask for.
Sources: [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail),
[JetBrains AI blog review](https://blog.jetbrains.com/ai/2026/07/ponytail-skill-claude-tested/).

### 5. Repomix (yamadashy/repomix)

Packs a repository into a single AI-friendly file; separately, exposes
`repomix --token-count-tree N` to show only files/directories at or above N
tokens, and a secret-scanner (Secretlint) on output. MIT-family license,
npm-distributed, cross-platform (Node.js). No LLM, no embeddings, runs fully
offline for the packing/counting features (an MCP-server mode exists for
letting an agent fetch a packed remote repo, which is a different, heavier
use the brief already rules out). This is the "offline diagnostic" role the
brief asks to evaluate it as, not a per-session context tool.
Unique capability: `--token-count-tree` is a ready-made version of the
"internal token-count utility" the brief asks to compare it against; building
one internally (`wc -c` per file grouped by directory, weighted by an
approximate chars-per-token constant) would take under an hour and add no
new dependency, at the cost of being less precise about actual tokenizer
boundaries than Repomix's own counting.
Sources: [yamadashy/repomix](https://github.com/yamadashy/repomix),
[repomix.com guide](https://repomix.com/guide/).

### 6. Aider repository-map ideas (not adopting Aider itself)

Aider's repo-map: tree-sitter parses every file into a dependency graph
(files as nodes, symbol references as edges), then personalized PageRank
ranks symbols, biased toward files already in the current chat (50x weight),
explicitly-mentioned identifiers (10x), and well-named long identifiers
(10x); the result is compressed to a configurable token budget (default
1,024 tokens). MIT license (Aider itself); the technique is a well-documented
algorithm, not a proprietary black box.
Company OS's own `repo_map.py::query()` already does deterministic, bounded,
budgeted file selection — but by a simpler token/path-weighting scheme, and
V2's own dogfood found a real defect in it: two unrelated test files scored
identically to the actual target file at this repository's real 593-file
scale, because a test file routinely repeats its subject's name and the
weighting could not distinguish that. V2's fix was to cap the *guessed*
portion of the file list (`max_query_fill=2`) rather than fix the ranking
itself — a mitigation, not a resolution, by the milestone's own account.
Unique capability: a PageRank-style relevance signal would rank the
*actually-referenced* file above a same-named-but-unrelated test file using
the dependency graph's structure, not string overlap — directly addressing
V2's own documented false-positive, without adopting Aider, an LLM call, or
a new external dependency (a pure-Python PageRank over the existing reverse-
dependency graph is a small, deterministic addition to `repo_map.py`).
Sources: [aider.chat repomap post](https://aider.chat/2023/10/22/repomap.html),
[PageRank ranking explainer](https://anishgandhi.com/aider-pagerank-codebase-ranking/).

### 7. Structural/semantic search comparison

| | Python (this repo, `company`/`tools`/`tests`) | GDScript (this repo, `race2`/`sloped`/`godot`/etc.) |
|---|---|---|
| stdlib `ast` (current) | native, in production, 2.07s full-repo parse, 0 errors | not applicable — no GDScript grammar |
| ast-grep | native, built-in Python language support | **not built-in**; community `@ast-grep/lang-gdscript` package and an open, unmerged PR (`ast-grep/langs#195`) exist, requiring a compiled dynamic library and `sgconfig.yml` custom-language registration — meaningfully higher integration complexity than for Python |
| Universal Ctags | works (token-based parser, same family as its Python one) | **native, dedicated parser** (`ctags-lang-gdscript`, documented in the project's own manual, adjusted from the Python parser for GDScript's differences) — the only candidate here with an *official*, first-party GDScript parser, not a community add-on |
| tree-sitter (direct grammar, no ast-grep/Serena wrapper) | works via `py-tree-sitter` | grammar exists and is actively maintained (`tree-sitter-gdscript`, multiple maintained forks, v6.1.0 seen) — usable as a direct Python-binding replacement for `repo_map.py`'s stdlib-`ast` approach, extended to `.gd` files in the same architectural style already used for Python |
| Serena (LSP) | works, but this repo's own evidence says Python discovery is CURRENTLY SMALL already | works, but requires a live Godot editor process for the language server |
| SCIP | `scip-python` exists | **no GDScript indexer exists in the SCIP ecosystem** — ruled out entirely for this repo's GDScript half |

**The smallest sufficient code-intelligence layer for GDScript, by this
comparison, is not obviously Serena.** Universal Ctags (native GDScript
parser, no MCP server, no LSP, no persistent process, single small binary,
decades of Windows support) or a direct `tree-sitter-gdscript` binding
(matching `repo_map.py`'s own existing architecture, extended to a second
language) both plausibly answer "what symbols exist in this 130KB `.gd`
file and where" without adding a language-server-managing MCP layer. Serena
adds cross-reference/call-graph queries neither of those two provides for
GDScript; whether that specific capability is needed is exactly what
Benchmark C is designed to find out, not something this research can decide
from documentation alone.
Sources: [ast-grep language list](https://ast-grep.github.io/reference/languages.html),
[ast-grep custom language support](https://ast-grep.github.io/advanced/custom-language.html),
[ast-grep/langs#195 GDScript PR](https://github.com/ast-grep/langs/pull/195),
[Universal Ctags GDScript parser docs](https://docs.ctags.io/en/latest/man/ctags-lang-gdscript.7.html),
[tree-sitter-gdscript (PrestonKnopp)](https://github.com/PrestonKnopp/tree-sitter-gdscript),
[SCIP indexer list](https://sourcegraph.com/blog/announcing-scip).

### 11th candidate discovered during research: direct `tree-sitter-gdscript` binding

Not on the brief's list of ten. Surfaced by researching candidate 7 above.
A small, local, deterministic Python module (`py-tree-sitter` +
`tree-sitter-gdscript` grammar) that extends `repo_map.py`'s existing
stdlib-`ast` pattern to `.gd` files — same output shape (`ModuleMap`-style
symbol spans), same "query for a ranked slice, never hand the whole map to a
session" discipline, no MCP server, no LSP process, no Godot editor
dependency. This is architecturally the closest match to what this
repository already does for Python, extended by one language, and is
recorded here as a candidate specifically because it may make Serena's
GDScript LSP dependency (a live Godot editor process) unnecessary for the
symbol-lookup and reference-lookup use cases, while still leaving call-graph/
blast-radius queries (Serena's or Graphify's actual unique value) unanswered.

---

## 5. Candidate-vs-bottleneck matrix

| Candidate | Bottleneck addressed | Current severity of that bottleneck | Verdict basis |
|---|---|---|---|
| Serena | C (local file nav, GDScript), G (cross-language nav) | POSSIBLY MATERIAL / CURRENTLY MATERIAL by construction | targets a real, unmeasured gap |
| Graphify | B (production discovery), multi-hop query the internal map lacks | NOT MEASURED | targets an unmeasured gap, but no confirmed GDScript coverage |
| RTK | F (shell/tool-output cost) | CURRENTLY SMALL for Company OS jobs (own telemetry says so) | targets a bottleneck its own evidence says is not dominant here |
| Ponytail | D/E-adjacent (reasoning/output minimalism) | already addressed internally | no measured gap; internal instructions already cover the described behavior |
| ast-grep | A/G (structural search) | CURRENTLY SMALL for Python, HIGH integration cost for GDScript | Python side already solved; GDScript side not built-in |
| Repomix | Tool-overhead diagnostic (I. startup/measurement), not a live bottleneck | diagnostic use only | correctly scoped as offline-only by the brief |
| Aider ranking idea | A (a documented real ranking defect in `repo_map.py::query()`) | POSSIBLY MATERIAL — mitigated, not resolved, per V2's own account | a specific, evidenced defect exists to fix |
| Universal Ctags | C/G (GDScript symbol lookup) | POSSIBLY MATERIAL | smallest-footprint native option for the identified gap |
| tree-sitter-gdscript direct | C/G (GDScript symbol lookup) | POSSIBLY MATERIAL | architecturally consistent internal extension |
| SCIP | none available | not applicable | no GDScript indexer exists |

---

## 6. Constraint compatibility matrix

| Candidate | No subagents | No paid API required | Deterministic-first | Bounded context | Local/offline | Windows | Python | GDScript | Prod. independent of Company OS |
|---|---|---|---|---|---|---|---|---|---|
| Serena (code-only mode) | yes | yes | no — LSP, not deterministic parsing | yes, via minimal tool subset | yes | yes | yes | yes (needs Godot editor process) | yes, external MCP server |
| Graphify (`--code-only`) | yes | yes | yes | yes, ranked/incremental | yes | unverified | yes | unverified/unclaimed | yes |
| RTK | yes | yes | yes | n/a (output filter) | yes | yes (confirmed live) | n/a | n/a | yes, operator-level shell hook |
| Ponytail | yes | yes | n/a (prompt text) | n/a | yes | yes | n/a | n/a | yes, a skill file |
| ast-grep | yes | yes | yes | yes | yes | yes | yes | community-only, unmerged | yes |
| Repomix | yes | yes (diagnostic mode) | yes | yes (that's its purpose) | yes | yes | n/a | n/a | yes |
| Aider ranking idea (internal impl.) | yes | yes | yes | yes | yes | yes | yes | n/a (Python-side idea) | it would live in `tools/`, same as `repo_map.py` |
| Universal Ctags | yes | yes | yes | yes | yes | yes (long history) | yes | yes, native | yes |
| tree-sitter-gdscript direct | yes | yes | yes | yes | yes | yes | n/a | yes | yes, would live in `tools/` |
| SCIP | yes | yes | yes | yes | yes | yes | yes (`scip-python`) | **no** | n/a |

**INELIGIBLE FOR CURRENT RUNTIME, in full or in part:**

- **Serena's full default mode** (20+ tools, onboarding, memory tools) —
  ineligible as shipped; its **minimal mode** (`find_symbol`,
  `get_symbols_overview`, `find_referencing_symbols`,
  `find_implementations`, `no-onboarding`, `no-memories`) is not ineligible,
  it is a distinct configuration that must be the one actually tested (§7).
- **Serena's GDScript path specifically** requires a long-lived Godot editor
  process — not disqualifying, since Godot is already present on this
  machine, but it is a new category of managed process this project's
  tooling does not have today, and should be named as such rather than
  assumed away.
- **Graphify's Pass 3** (LLM-assisted doc/PDF semantic extraction) requires a
  paid API key — ineligible; **Pass 1/2 (`--code-only`)** requires none and
  is the only mode in scope.
- **SCIP** is ineligible for the GDScript half of this repository not because
  of a runtime constraint but because no indexer for GDScript exists at all,
  full stop.

---

## 7. Tool-overhead analysis

No candidate is installed, so no live measurement of index-build time, tool-
schema prompt chars, or refresh cost exists for this repository specifically.
Vendor-documented figures, recorded as vendor claims, not verified numbers:

| Candidate | Static tool/schema overhead | Index/startup | Refresh | Persistent service required |
|---|---|---|---|---|
| Serena, default | 20+ MCP tool descriptions on every prompt | onboarding reads "a lot of content," documented as expensive | LSP-server-dependent | yes — MCP server + one language server per active language |
| Serena, minimal mode | 4 tool descriptions (per brief's own proposed subset) | skippable (`no-onboarding`) | LSP-server-dependent | yes, same |
| Graphify, code-only | not documented; PreToolUse hook adds one hook invocation per tool call | not documented for this repo's scale | ~0.8s for 3 changed files (vendor claim) | no persistent server for `--code-only`; graph is a local artifact |
| Universal Ctags | none — output is a flat tags file, no MCP tools at all | fast, single-pass; not benchmarked on this repo | full re-tag, not incremental, but cheap at this repo's scale (81 `.gd` files) | no |
| tree-sitter-gdscript direct | none — same shape as `repo_map.py`, queried not exposed as raw tools | comparable to `repo_map.py`'s 1.74s for 413 Python modules; untested on 81 `.gd` files | incremental re-parse of changed files only, same pattern as `repo_map.py` | no |
| RTK | none — a Bash-hook output filter, not an MCP tool | none | n/a | no — a per-command hook, not a service |
| Repomix | none if used only as an offline CLI diagnostic | one-time pack per invocation | manual, on demand | no |
| Ponytail | skill text adds to system-prompt chars once, comparable to any skill | none | none | no |

**Reading.** The two lowest-overhead options for the one genuinely unmeasured
gap (GDScript navigation) are Universal Ctags and the direct
tree-sitter-gdscript binding — both add zero MCP tool-schema overhead and no
persistent service. Serena's minimal-mode configuration is a meaningfully
different overhead profile from its default, and any test of Serena must use
the minimal configuration or the overhead comparison is not fair to Company
OS's existing lean toolset.

---

## 8. Language/platform coverage — summary table

| Candidate | Python | GDScript | Windows |
|---|---|---|---|
| Serena | yes (LSP) | yes, needs Godot editor process | yes |
| Graphify | yes | unclaimed | unverified |
| RTK | n/a (shell layer) | n/a | yes, confirmed live |
| Ponytail | n/a (prompt skill) | n/a | yes |
| ast-grep | yes, built-in | community-only, unmerged | yes |
| Repomix | yes (any text file) | yes (any text file) | yes |
| Universal Ctags | yes | yes, native parser | yes |
| tree-sitter-gdscript direct | n/a (Python-side is already stdlib ast) | yes | yes |
| SCIP | yes (`scip-python`) | no | n/a |

---

## 9. Ponytail vs. internal minimalism — direct comparison

Ponytail's seven-step ladder (YAGNI → codebase reuse → stdlib → native
platform → installed deps → one-liner → minimal implementation) was compared
against this project's own working instructions already in force for every
session on this repository: "don't add features, refactor, or introduce
abstractions beyond what the task requires... reuse existing implementation,
smallest surface, existing dependency/stdlib preference... no speculative
abstractions/config/fallbacks." No behavior in Ponytail's public description
was found that is not already covered by an existing instruction at
comparable or finer granularity (the ladder's five middle steps map directly
onto "prefer existing dependency/stdlib," and step 1/7 map onto "don't design
for hypothetical future requirements" and "smallest coherent diff").
**Recommendation: DO NOT ADD PACKAGE — INTERNAL PRINCIPLE ALREADY ABSORBED.**
No A/B is designed for it; the brief's own instruction is to skip the A/B
when no measurable-behavior gap is found, and none was.

---

## 10. Repomix / token diagnostics — recommendation

Repomix's `--token-count-tree` is evaluated exclusively as an **offline
diagnostic**, per the brief's explicit instruction not to propose sending a
packed repository into every session. It would answer, in one command,
questions this research had to answer by hand with `git ls-tree`/`awk`
(§ production measurement artifact): which directories are token-heaviest,
where growth is concentrated, which files are outliers. An internal
equivalent (byte-count grouped by directory, already demonstrated as
sufficient for this milestone's own measurements) costs nothing to keep
using and adds no dependency; Repomix would be strictly more convenient
(actual tokenizer-aware counts, not a byte-size proxy) at the cost of one new
npm-distributed dependency for a task that is run rarely, not per-session.
**Recommendation: DIAGNOSTIC ONLY, if adopted at all — install locally on
the operator's machine for occasional audits, never as a Company OS or
runner dependency, and only if the byte-count proxy already used in this
milestone's own measurement artifact proves insufficiently precise in
practice.**

---

## 11. Proposed benchmark suite

None of these are run in this milestone. Each is designed to be startable
without further design work.

### Benchmark A — Company/Python

**Purpose:** confirm (not merely assume) that the existing internal RepoMap
remains sufficient on this task class, since V3B/operational-readiness §12
already concluded no further tool experiment is needed here. Expected result
is a DEFER/no-material-difference outcome — this benchmark exists to check
that expectation, not to manufacture a win.
- Frozen base commit: `company-os-v1-bootstrap` @ `b84f8a7` (this milestone's
  own base, so it stays reproducible even as the canonical branch advances).
- Objective: one bounded, genuinely-unimplemented counter/field addition on
  `company/engineering/`, of the same shape as `blocked_attempts` — grep for
  candidates before selecting one, per this project's own established
  practice.
- Acceptance criteria: mirrors an existing counter's test shape (5 criteria,
  as `blocked_attempts` had).
- Authorized paths: one production file + its one test file, narrowly scoped
  (`scope_ceiling` set explicitly, per V3B's own corrective precedent for its
  first, over-broad submission).
- Required tests: the relevant `tests/test_company_engineering_*.py` file.
- Model/tier: sonnet, STANDARD (the only reachable tier under State C's
  eligibility list).
- Reasoning effort: default for the runner; no escalation flag set.
- Context budget: consumer profile, `MAX_BUNDLE_CHARS = 6000`, unchanged.
- Cost ceiling: $3.00 (the stop-condition's own named approach-threshold).
- Retry count: 1 developer attempt, 1 reviewer pass (consumer profile).
- Reviewer policy: unchanged, no anchors, per V3B's own deliberate choice.
- Measurable expected behavior: developer cache-read within
  568,012–990,324 (the V3B–V1 historical range for this exact task shape);
  a candidate is only interesting here if it moves *outside* that range.

### Benchmark B — Production Python / multi-file

**Purpose:** the first-ever measurement of dependency/reference navigation
across the marble-race Python side, which `repo_map.py` excludes entirely
today.
- Frozen base commit: `origin/main` @ `8b1022a` (production lives on `main`,
  not on the Company OS lineage).
- Objective candidate: a bounded, real, reference-navigation-heavy task —
  e.g., "find every caller of a named function in `sloped/` and add one
  guard-clause consistently" — chosen so success requires finding call sites
  across files, not just editing one known file, which is exactly the
  capability `repo_map.py`'s `production_dependents` index has never been
  asked to do outside `company/`+`tools/`.
- Acceptance criteria: every actual call site updated, none missed, none in
  an unrelated file touched.
- Authorized paths: the specific files touched, named after a read-only scan
  identifies them — not a blanket grant to the directory.
- Required tests: whichever existing test file(s) cover the touched module;
  a new one only if none exists and the task needs it.
- Model/tier: sonnet, STANDARD, same profile as A for comparability.
- Context budget/cost ceiling/retry policy: identical to A, so the only
  variable that changes between A and B is the task class, not the policy.
- Measurable expected behavior: no fixed prior range exists (this task class
  has never been run); record the first number as the new baseline rather
  than judging it against an invented threshold.

### Benchmark C — GDScript/Godot

**Purpose:** the task class this whole research milestone exists to justify
— genuinely unmeasured, genuinely uncovered by internal tooling (§3.B/C/G).
- Frozen base commit: `origin/main` @ `8b1022a`.
- Objective candidate: a bounded, real GDScript change in one of the large
  files identified in the production measurement artifact (e.g.
  `godot/scripts/neon_scene.gd` or a smaller, less risky sibling script),
  scoped to something revertible and non-visual (a naming/constant fix, a
  small guard clause) rather than anything touching the locked visual/camera
  work this project's other memory records treat as frozen.
- Acceptance criteria: the specific symbol/behavior changes as specified;
  no other `.gd` file's behavior changes.
- Authorized paths: the one `.gd` file (+ a matching test if a GDScript test
  harness exists for it; if none does, that absence is itself a finding to
  record, not a task blocker to route around).
- Required tests: whatever this repository's actual GDScript test/CI story
  is — to be confirmed at benchmark-start time, since this research did not
  find one; do not assume one exists.
- Model/tier: sonnet, STANDARD.
- Context budget/cost ceiling/retry policy: identical to A/B.
- Measurable expected behavior: first-ever baseline for this task class,
  same treatment as B.
- **This is the one benchmark class where a candidate tool is expected to
  plausibly change the outcome**, per §4's finding that no internal tool
  covers GDScript at all.

### Benchmark D — Test/output-heavy

**Purpose:** measure shell/test-output compression and reviewer efficiency
specifically, isolating it from discovery cost (which A–C already measure).
- Frozen base commit: `company-os-v1-bootstrap` @ `b84f8a7` (or `main` @
  `8b1022a` if the chosen task is production-side — either is valid since
  the point is the output volume, not the subsystem).
- Objective candidate: a task whose required-test suite is large/verbose by
  itself (e.g. a change requiring `tests/test_soundtrack.py`, 56,869 bytes,
  identified in the production measurement) or a Company OS task requiring
  the 11-suite gate run, whose output volume was never itself measured, only
  its pass/fail outcome.
- Acceptance criteria: as for the underlying task; the metric of interest is
  captured/raw shell-output character counts, not just pass/fail.
- Authorized paths / required tests / model / context / cost / retry:
  identical framework to A.
- Measurable expected behavior: this is the one benchmark specifically
  positioned to test RTK's actual claimed strength (shell/test output
  reduction) against Company OS's own current unmeasured baseline for this
  repository's specific pytest/git output sizes — something RTK's own
  telemetry (§2) is aggregated across other projects and does not answer for
  Simulation Factory specifically.

**Benchmark E (large-file local navigation) is justified by the production
measurement** (`stations.py` at 2,617 lines, `neon_scene.gd` at 129,898
bytes) but is folded into Benchmark C's file choice rather than run
separately, to keep the total live-session count small per §19's own
instruction — a dedicated Benchmark E is not proposed as a fifth live class.

---

## 12. Metrics

Captured per the brief's four categories (QUALITY, RESOURCE, EXPLORATION,
SHELL, TOOL OVERHEAD, MAINTENANCE) using fields that already exist in this
repository's telemetry, named exactly as they appear in code, so the harness
does not need new instrumentation beyond what §1 already lists as present:

- QUALITY: `ReviewerAttestation` verdict, gate `READY`/`BLOCKED`, required
  test pass/fail counts, `unresolved_reviewer_findings`, first-attempt
  acceptance (`max_developer_attempts` consumed == 1), `PathRules.violations`
  count (scope violations).
- RESOURCE: developer/reviewer `cache_read_units` (cross-checked, per
  [[ai-resource-efficiency-v2-telemetry-defect]]'s rule — never trust a
  single segment silently), `cache_creation_input_tokens` (currently
  UNAVAILABLE per-segment, record as such rather than guessing),
  `output_units`, `model_turns` (marked `unreliable` when segments disagree,
  never silently averaged), `cost_usd` (RELIABLE), wall time, instruction
  chars, `ExecutionContextBundle` char count against `MAX_BUNDLE_CHARS`.
- EXPLORATION: `repo_file_reads`, `repo_searches`, `repeated_file_reads`,
  `read_after_edit_count` (V3A's own diagnostic field — distinguishes
  verification re-reads from discovery re-reads), all `POST_SESSION_OBSERVABLE`
  and only available for sessions launched with `--verbose stream-json`.
- SHELL: `CommandResult.stdout` raw length pre-/post- any reduction filter
  (none currently applied in production — see §1's "output reduction"
  row — so pre==post today; a benchmark introducing RTK or a reduction
  filter is the first time these two numbers would ever differ).
- TOOL OVERHEAD: static MCP/tool schema character count (measurable directly
  from whatever MCP config a benchmark run uses — zero today, since nothing
  is installed), index build/refresh time (candidate-reported or measured
  fresh, never assumed from vendor marketing).
- MAINTENANCE: dependencies added (`git show <sha>:requirements.txt` diff,
  the same mechanism [[external-runner-hardening-stop-condition]] already
  built for the `dependencies_added` fix), persistent services required
  (yes/no per §6/§7), config files added, platform restrictions.

**Primary metric: TOTAL RESOURCE COST PER ACCEPTED RESULT** — job cost
(developer + reviewer) divided by 1 only if `ready_for_approval` was reached
on the first attempt with 0 scope violations; a job that reaches
`decision_required` or `blocked` does not produce an "accepted result" and
is recorded as a failure for this metric, not averaged in at a discounted
weight.

---

## 13. Adoption thresholds

Predeclared per candidate/bottleneck, not chosen after seeing a result.

- **Benchmark A (Company/Python):** ADOPT nothing unless developer
  cache-read falls **below 568,012** (below V3B's own already-improved
  number, not merely below V2's). Given §3.A's own conclusion that discovery
  is already at 5 reads including the 2 files about to be edited anyway, the
  predeclared expectation is DEFER, and this benchmark is run to confirm
  that, not to find a win.
- **Benchmark B (production Python):** no prior baseline exists, so no
  percentage threshold is predeclarable. ADOPT only if a candidate correctly
  finds 100% of real call sites that a manual `grep -rn` pass (recorded
  alongside the live run for comparison, at zero extra cost) also finds, in
  fewer total tool calls; a candidate that finds *fewer* call sites than a
  plain grep, however fast, is a correctness regression and is REJECTed
  regardless of speed.
- **Benchmark C (GDScript):** ADOPT the specific candidate only if it
  correctly resolves symbol references in a `.gd` file that plain
  Read+Grep, exercised in a control run on the same task, gets wrong or
  misses — GDScript's lack of any internal semantic tool today means the
  bar is "materially more correct than blind text search," not a percentage
  cache-read reduction. A candidate that matches plain Read+Grep's
  correctness at higher tool overhead is DEFERRED, not adopted, even if it
  "works."
- **Benchmark D (shell/output):** ADOPT only if raw-vs-reduced shell output
  differs by more than the aggregate RTK figure already suggests is
  plausible for this workload class (over 50%, per §2's git/pytest-specific
  lines, not the 63.8% *overall* figure that is dominated by read/grep) AND
  the reduction does not remove information the reviewer or gate actually
  needed (verified by re-running the gate against the reduced output and
  confirming an identical verdict).
- **General REJECT trigger, all benchmarks:** any increase in retries, any
  scope/authority-boundary violation, any telemetry disagreement introduced
  by the candidate's own instrumentation, or context/tool-schema overhead
  consuming more than 25% of the measured saving.
- **General DEFER trigger, all benchmarks:** result within the variance
  already documented between two runs of the *same* task on the *same*
  tooling (a 37% cost spread was measured between BEFORE and Consumer-V1's
  own developer sessions on the identical `attempts-remaining` objective) —
  i.e., an effect smaller than ~37% on a single n=1 run is not distinguishable
  from noise already proven to exist in this workload, and must not be
  reported as a win.

---

## 14. Recommended test order

| Candidate | Assignment | Reason |
|---|---|---|
| Universal Ctags (GDScript) | **TEST FIRST** | native GDScript parser, zero MCP overhead, no persistent process, cheapest possible probe of whether *any* symbol-level GDScript tool beats plain Read+Grep on Benchmark C |
| tree-sitter-gdscript direct binding | **TEST FIRST** (alongside Ctags, not instead of — both are cheap enough to run as a paired diagnostic before committing to Benchmark C's live session) | architecturally consistent with the existing `repo_map.py` pattern; if it performs comparably to Ctags, it is the one that fits this codebase's existing style |
| Serena, minimal config | **TEST LATER** | real unique value (cross-reference/call-graph queries neither Ctags nor raw tree-sitter gives), but higher overhead (a managed Godot-editor LSP process) — worth testing only after Ctags/tree-sitter establish whether basic symbol lookup alone already clears the Benchmark C bar |
| internal PageRank-style ranking enhancement (Aider idea) | **TEST LATER** | targets a real, specific, already-documented defect in `repo_map.py::query()`, but on the Company/Python side where §3.A says discovery is already CURRENTLY SMALL — worth doing as a correctness fix regardless of A/B outcome, but not urgent |
| Graphify, code-only mode | **TEST LATER** | targets Benchmark B's genuinely unmeasured multi-hop navigation gap, but GDScript coverage and Windows support are both unverified — verify those two facts directly (a 10-minute install-and-probe) before committing a full live session to it |
| Repomix | **DIAGNOSTIC ONLY** | explicitly scoped as an offline audit tool, never a per-session dependency |
| RTK, wired into the runner's child process | **DIAGNOSTIC ONLY, then TEST LATER if Benchmark D shows a real gap** | its own telemetry says its Company-OS-relevant value (shell/test output) is proportionally small; Benchmark D exists specifically to check that inference against this repository's own numbers before spending on it |
| Ponytail | **REJECT CURRENT MODE** | no measurable behavior gap versus existing instructions found |
| ast-grep | **DEFER** | Python side already solved; GDScript side requires an unmerged community package — not worth the integration cost until Ctags/tree-sitter are shown insufficient |
| SCIP | **REJECT CURRENT MODE** | no GDScript indexer exists; no unique value over `scip-python`, which this repo's own stdlib-`ast` approach already covers for Python at lower overhead |

---

## 15. Estimated benchmark cost

Using the measured per-job cost range already established (§2: $0.64–$1.94
job cost for a routine Company/Python job; no prior figure exists for
production-Python or GDScript jobs, so the same range is used as a planning
estimate, not a proven one):

- Benchmark A (confirm-no-regression run): 1 developer session + 1 reviewer
  pass = 1 live session pair, ~$1.00–$2.00.
- Benchmark B (baseline-only, no candidate yet): 1 session pair, ~$1.00–$2.50
  (larger context, more files, unproven — budget the high end).
- Benchmark C (baseline, plain Read+Grep control): 1 session pair,
  ~$1.00–$2.50.
- Benchmark C (candidate run — whichever of Ctags/tree-sitter/Serena is
  tested first per §14): 1 additional developer session (reviewer policy
  unchanged, so reuse the same reviewer cost estimate), ~$0.50–$1.50.
- Benchmark D (baseline + one candidate): 1 session pair each, ~$1.00–$2.00
  per side.
- Deterministic-only phases requiring no model calls at all: the Ctags/
  tree-sitter-gdscript diagnostic probes in §14 (parse the repo, measure
  symbol counts and index time — no LLM session needed for this part),
  Repomix's token-count-tree run, and re-verifying the ast-grep/GDScript
  package's actual install complexity by attempting the install once,
  read-only, in a disposable location.

**Total estimated live sessions: 5–7 developer sessions, 4–5 reviewer
passes.** **Estimated maximum total benchmark spend: $12–$20** across all
four benchmark classes plus one candidate test on the one class most likely
to show a real difference (C). **Approximate runtime:** each session pair
historically completes in 150–310 seconds server-side, plus gate-suite time
(~100s for 11 required suites on the Company OS side; unknown for a
production-side/GDScript gate equivalent, since none has ever run — this
itself should be measured on the very first production/GDScript benchmark
run, not assumed). This is deliberately the smallest experiment set that
covers all four required task classes plus the one candidate the evidence
most supports testing (Ctags/tree-sitter on GDScript) — not a campaign.

---

## 16. Relation to the Master Development Plan

The winning architecture pattern this research points toward — deterministic,
local, queried-not-dumped, bounded by an explicit character ceiling, built
as a `tools/`-side actuator that Company OS references through an unwired
Protocol seam rather than imports directly (§1's `CodeIntelligenceProvider`)
— is already the shape every future department (Research, Engineering,
Video Intelligence, Analytics, HR/workforce, Corporate Self-Improvement,
Technology Radar) would need for:

- **dormant zero-cost roles:** a department with no active work order costs
  nothing, because context is reference-only and assembled per-job, not
  held resident (§1, `ai_platform/context_manifest.py`).
- **minimum relevant context:** the `ExecutionContextBundle` ceiling pattern
  (bounded chars, ranked/queried, never a whole-repository dump) generalizes
  to any department's own knowledge base the same way it already generalizes
  from Company-OS-Python to (proposed) GDScript.
- **deterministic-first processing:** every capability in §1 that works today
  is deterministic (stdlib AST, string/token matching, byte-digests); the
  one non-deterministic layer (the LLM developer/reviewer session itself) is
  bracketed by deterministic gates on both sides. Any new department should
  follow the same shape — deterministic classification and retrieval feeding
  a bounded LLM session, not the reverse.
- **retrieval before reasoning:** `TestPatternAnchor`'s whole value (§2,
  Task 2) was supplying an exact identifier before the reasoning step needed
  to guess one — the same pattern (compact, named, exact) is the template
  for any department's "brief" format going forward.
- **compact handoffs:** `checkpoint.json`'s deliberate exclusion of the full
  conversation, carrying only work order/git position/failing
  tests/unresolved findings/context refs, is the existing template for a
  cross-department handoff artifact.
- **token/resource telemetry:** the `Enforceability` typing
  (`LIVE_ENFORCEABLE`/`POST_SESSION_OBSERVABLE`/`UNAVAILABLE`) is a reusable
  pattern for any new department's own resource dimensions — declare what is
  actually measurable honestly, rather than inventing a number.

No department implementation is begun here. This section only confirms the
substrate's shape scales without redesign — the two currently-missing pieces
for that scaling are language coverage beyond Python (§4, §14's GDScript
test order) and multi-hop/call-graph queries beyond the internal map's
single-hop reverse index (Graphify's specific claimed unique value, still
unverified for this repository).

---

## 17. What should NOT be tested or installed right now

- **Graphify, Serena, RTK, Ponytail, ast-grep, Repomix, SCIP, Tree-sitter
  extensions, Ctags, embedding databases, vector databases** — none
  installed or vendored in this milestone, per the brief's explicit
  instruction. This includes not running `npm install`/`pip install`/`cargo
  install` even in a disposable scratch location for anything beyond a
  read-only version/capability probe, which was not done in this milestone
  (all candidate facts above come from vendor documentation and this
  session's own already-installed RTK, not from a fresh install).
- **Ponytail** — REJECT CURRENT MODE outright; no benchmark designed.
- **SCIP** for the GDScript half of this repository — no indexer exists;
  not a runtime-constraint rejection, a capability-absence one.
- **ast-grep for GDScript** until Universal Ctags and the direct
  tree-sitter-gdscript binding are tried first and shown insufficient — its
  GDScript path is an unmerged community package, the highest integration
  cost of any candidate evaluated.
- **RTK inside the Company OS runner's child process** until Benchmark D
  actually measures this repository's own git/pytest output volume — its
  own aggregate telemetry (§2) says this is probably not where the value is,
  and wiring it into the governance-relevant `child_environment()` allowlist
  is not a change to make speculatively.
- **A combined "winning stack" test** (Serena + Graphify + RTK together, or
  any multi-candidate combination) before at least one individual winner
  exists on at least one benchmark class, per the brief's §17 one-variable-
  at-a-time rule.
- **Any of this inside Company OS's runtime code, `company/`, or
  `ai_platform/`** — the one wiring point that exists (`providers.py`'s
  `CodeIntelligenceProvider` seam) stays unwired until a candidate actually
  wins a benchmark.

---

## Decision table

| Candidate | Unique value | Measured bottleneck addressed | Current evidence | Expected test | Runtime constraints | Research verdict |
|---|---|---|---|---|---|---|
| Serena | symbol-level cross-reference/call-graph nav via real LSP, incl. GDScript | C, G (GDScript nav) | none live; GDScript file-size evidence only | Benchmark C, minimal-tool config, after Ctags/tree-sitter | needs a managed Godot-editor process for `.gd`; GPL-3.0 as distributed | TEST LATER |
| Graphify | multi-hop call-graph/blast-radius query the internal map lacks | B (production multi-file nav) | none live; internal map's single-hop limit is documented | Benchmark B, `--code-only` mode, after verifying Windows/GDScript facts directly | Pass 3 (LLM) ineligible; Pass 1/2 eligible | TEST LATER |
| RTK | shell/test-output compression | F (shell/tool-output cost) | own global telemetry says value concentrates in read/grep, not shell text, for this operator's aggregate workload | Benchmark D, as a diagnostic first | already present at operator level; ineligible as a Company-OS-runtime dependency without a deliberate `child_environment()` change | DIAGNOSTIC ONLY, then TEST LATER only if D shows a real gap |
| Ponytail | code-volume minimalism | none found beyond existing instructions | vendor benchmark only, not reproduced | none designed | fully eligible, trivially | REJECT CURRENT MODE |
| ast-grep | structural search/rewrite | A (Python, already CURRENTLY SMALL); G (GDScript, unmerged community support) | V1's own 2.07s full-repo `ast.parse` finding already rejected it for Python | none for Python; DEFER for GDScript pending Ctags/tree-sitter result | eligible, but GDScript integration complexity is highest of any candidate | DEFER |
| Repomix | token-count-tree diagnostic | tool-overhead/audit category only | this milestone's own byte-count measurement stands in for it | none — diagnostic use only | eligible | DIAGNOSTIC ONLY |
| Aider-style ranking improvement | PageRank-based file relevance, fixing a documented `repo_map.py::query()` false-positive | A (a specific, already-evidenced defect) | V2's own dogfood found the defect; V2's own fix was a mitigation, not a resolution | internal implementation + Benchmark A as regression check | eligible, no new dependency (pure-Python addition) | TEST LATER |
| Tree-sitter/Ctags (GDScript) | native/near-native GDScript symbol parsing, zero MCP overhead | C, G (GDScript nav) | file-size evidence only; no live session | Benchmark C, first, as the cheapest possible probe | fully eligible on all constraints | TEST FIRST |
| SCIP | none for this repo | none reachable | no GDScript indexer exists | none | ineligible by capability absence, not policy | REJECT CURRENT MODE |
| direct tree-sitter-gdscript binding (discovered, not on original list) | same as Ctags, architecturally consistent with existing `repo_map.py` | C, G | file-size evidence only | Benchmark C, paired with Ctags | fully eligible | TEST FIRST |

---

## Validation

- `git status`/`git diff` in the primary worktree (`v21-visual-contrast`)
  was not touched by this session — no command in this milestone ran inside
  that path.
- `company-os-v1-bootstrap` was read from `origin/company-os-v1-bootstrap`
  only, never checked out for editing; this branch's worktree started at
  that exact commit and no file under `company/`, `ai_platform/`, or
  `tools/` was modified — only `docs/` was added.
- `main` was read via `git ls-tree`/`git show` against `origin/main` only;
  no checkout, no working-tree change.
- No `pip install`, `npm install`, `cargo install`, or vendored package was
  run in this milestone. The one already-installed external tool used
  (`rtk`) pre-existed this session, at the operator level, per the user's
  own global configuration — it was queried (`--version`, `gain`,
  `discover`), never installed or reconfigured.
- Only `docs/company_os_ai_resource_optimization_research.md` and
  `docs/validation/company_os_ai_resource_optimization/production_repo_measurement.md`
  were added. No other file differs from the base commit.
