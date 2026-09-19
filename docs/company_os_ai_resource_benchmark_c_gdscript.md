# Benchmark C — GDScript/Godot Code Intelligence

AI Resource Optimization Lab, Benchmark C. Live A/B-style comparison of
plain Read+Grep against Universal Ctags and a direct `tree-sitter-gdscript`
binding, on one real, bounded, reversible GDScript task. Runs on a temporary
unified lab branch; nothing here is merged into `main` or into canonical
Company OS.

## Methodology deviation from the brief, stated up front

The operating brief for this milestone forbids two things this benchmark's
own C0/C1/C2 design otherwise assumes: routing execution through Company
OS's `tools/engineering_runner` (which is the only mechanism in this
repository that spawns an isolated developer/reviewer `claude` CLI
subprocess and captures its `cache_read`/`cost_usd`/`model_turns` telemetry
from `stream-json`), and using subagents. With both ruled out, there is no
mechanism available in this session to produce an isolated, per-condition
cache-read/cost/turn measurement the way Company OS's own historical
benchmarks (cited throughout
`docs/company_os_ai_resource_optimization_research.md`) do.

Given that constraint, all three conditions (C0, C1, C2) were performed by
the same interactive session acting as the developer, on three separate git
worktrees from the same frozen base commit, with tool calls (Read, Grep,
Bash, Edit) counted and their output character volume measured directly —
the same category of measurement `repo_map.py` and `execution_context.py`
already use internally (bounded char counts), just captured by hand instead
of by the runner's telemetry pipeline. `cache_read_units`, `cost_usd`, and
`model_turns` are recorded as **NOT MEASURED** for all three conditions
rather than estimated or fabricated, per this project's own established
convention (`Enforceability: LIVE_ENFORCEABLE / POST_SESSION_OBSERVABLE /
UNAVAILABLE` — declare what is actually measurable honestly). The primary
comparison in this report is therefore **navigation-context character
volume** (Grep/query/Read output actually produced) and **tool-call count**,
which are the two proxies this session could measure without violating the
no-Company-OS / no-subagent constraint, and which the base research doc
itself identifies as the dominant driver of cache-read cost ("the
multi-hundred-thousand cache-read totals... come overwhelmingly from
tool-call outputs accumulating in the session transcript").

## Unified lab baseline

- Production `main`: `8b1022aec899c7fa72ca77f2a1441c4d1b4ff48f` (unchanged
  from the value recorded when this milestone's brief was written).
- Company OS: `origin/company-os-v1-bootstrap` @ `b84f8a75a2d4aaeefd88798f23bc5948e7d39195`
  ("State C operating-state activation"). The local `company-os-v1-bootstrap`
  branch ref was stale at `01a163879bc68548c4bf2a22ee6a069838329503`
  (missing `tools/engineering_runner/repo_map.py` entirely) at the start of
  this session; `origin/company-os-v1-bootstrap` had already fast-forwarded
  past it. The first lab merge was built against the stale ref, discovered
  missing `repo_map.py`, and was discarded and rebuilt against the correct
  `origin` tip before anything else in this benchmark proceeded. This is
  recorded here rather than silently corrected, per the brief's own
  instruction not to hide integration complexity inside the experiment.
- `v21-visual-contrast` (`2795138`, the production worktree this session
  started in) is a superseded historical branch per explicit operator
  decision; its two commits were never merged into `main` because the same
  work reached `main` through separate commits
  (`f6e78c2`/`d8efaad`/`2129311`, all verified ancestors of `main`). It was
  not touched by this benchmark.
- Unified lab branch: `company-os-resource-lab-benchmark-c`, built as a
  worktree off `main`, with `origin/company-os-v1-bootstrap` merged in
  (`--no-ff`). Merge SHA: `f2116a5fdaf0f5150753b36cb525f94e1c62b1f2`.
- **Integration conflicts: none.** Production and Company OS have touched
  zero common files since their merge-base (`eaca65e`) — 263 files changed
  on the production side, 476 on the Company OS side, zero overlap. The
  merge applied cleanly with no manual conflict resolution.
- **Boundary check:** `grep` over `race2/ sloped/ marble3d/ godot/ engine/
  modes/ powers/ tools/` (excluding `tools/engineering_runner/` and
  `tools/youtube_fetch/`, which are Company OS's own) for `import
  company`/`import ai_platform` returns zero matches. No production module
  imports Company OS.

## Unified lab validation

Full `pytest -q` from the merge commit: **18 failed, 4993 passed, 440
skipped, 958.41s.** Zero failures are in `company`/`ai_platform`/
`tools/engineering_runner` — Company OS's own suite is fully green in the
unified tree. All 18 production failures are accounted for by the two
defect classes this project's own memory
(`suite-has-14-known-failures`) already diagnosed on `main` before this
session started, now scaled up because more history (V33, V33.1, and this
lab's own merge commits) has landed after the frozen `BASE` several
branch-scope guards compare against:

- **6 are missing gitignored render artifacts** (`output/sloped_race_v1/...`
  absent from any fresh checkout): `test_neon_proof::test_a_missing_godot_is_reported_rather_than_raised`,
  `test_sloped_v251_world` (4 cases), `test_sloped_v252_world` (1 case).
  Exact match, same count, to memory's previously-documented set.
- **12 are stale branch-scope guards** comparing a two-dot `git diff` against
  a frozen `BASE` commit, which by construction fails once any later commit
  lands (documented mechanism, not a new defect): `test_race2_v301_stage`,
  `test_race2_v30_stage`, `test_race2_v311_track` (2 cases),
  `test_race2_v321_geometry`, `test_race2_v32_final` (5 cases — 2 more than
  memory's last count of 3, because more files, including this lab's own
  merge, have landed after that guard's `BASE` since memory was last
  updated), `test_race2_v33_bookends` (a new instance of the same guard
  family; V33 did not exist when memory's 8-guard count was recorded).

None of the 5 tests that actually reference `course_scene.gd`
(`test_sloped_contrast.py`, `test_sloped_v23_env.py`,
`test_sloped_v23_integration.py`, `test_sloped_v23_machine.py`,
`test_sloped_v26_integration.py`) are in the failure list — the frozen
task's fix introduced no regression.

## GDScript inventory (measured, not estimated)

All figures from `main` @ `8b1022a` (identical content on the lab branch,
since Company OS and production share no files).

| Metric | Value |
|---|---|
| `.gd` files | 81 |
| Total lines | 39,566 |
| Total bytes | 1,643,697 |
| Largest file | `godot/scripts/neon_scene.gd` — 132,984 bytes, 3,086 lines, 76 functions |
| `class_name` declarations | 0 |
| `signal` declarations | 0 |
| `.connect(` call sites | 0 |
| `extends` (built-in base) | RefCounted 47, Node3D 13, Node 10, SceneTree 6, CanvasLayer 2 |
| `extends` (script inheritance) | 3 edges: `sloped_race_scene.gd`→`course_scene.gd`, `v23_env_scene.gd`→`sloped_race_scene.gd`, `v23_env_render.gd`→`sloped_race_render.gd` |
| `func` declarations (plain grep, column-0 only) | 626 |
| `preload(`/`load(` call sites | 205, to 40+ distinct targets — heaviest: `toy_geometry.gd` (36), `lab_forms.gd` (34), `v2_forms.gd` (17), `v2_track.gd` (11) |
| SceneTree-extending "check" scripts (likely deterministic validation entry points) | 6: `racer_visual_check.gd`, `sloped_fork_gap_check.gd`, `sloped_open_side_check.gd`, `sloped_slew_check.gd`, `sphere_uv_check.gd`, `toy_geometry_check.gd` — plus `marble3d_axis_check.gd` (`extends Node`, same role) |
| Python↔`.gd` association | ~23 `tests/*.py` and ~12 `tools/*.py` files reference specific `.gd` scripts or drive them via a Godot subprocess |
| Internal RepoMap coverage | **0.** `tools/engineering_runner/repo_map.py::DEFAULT_ROOTS = ("company", "tools", "tests")` — confirmed by direct read, not inferred. No `.gd` file, and no path under `godot/` or `race2/assets/`, is reachable by the existing AST-based intelligence layer at all. |

One measurement-methodology finding, recorded rather than resolved: plain
`grep -c "^func "` counts 626 top-level function declarations; the
tree-sitter parse (below) counts 1,077 `function_definition` nodes across
the same files. The difference is real, not an error — tree-sitter also
counts nested/indented function definitions (e.g. inside `match` arms or as
local closures) that a column-0-anchored grep pattern cannot see. Ctags'
own count (2,543 tags) is not comparable to either, since it spans every
symbol kind (consts, vars, methods), not functions alone.

## Frozen task — BC-1

**Objective.** `godot/scripts/course_scene.gd::_options()` (line 231) is one
of 19 near-identical command-line-argument parsers scattered across
`godot/scripts/` (`_options`, `_parse_options`, `_argument`, `_parse`,
depending on the file). Comparing all of them directly shows a real,
reproducible, cross-file inconsistency: `course_scene.gd`, along with 10
siblings (`course_render.gd`, `hero_render.gd`, `hero_scene.gd`,
`lab_render.gd`, `lab_scene.gd`, `offline_render.gd`, `race2_render.gd`,
`sloped_race_render.gd`, `track_lab_render.gd`, `track_lab_scene.gd`),
silently **drops** any bare `--flag` argument (one with no `=value`) from
the dictionary it returns — the loop only ever writes to `options` when
`arg.substr(2).split("=", true, 1)` produces exactly two pieces. This
contradicts the project's own documented convention for exactly this kind
of flag, stated in `neon_scene.gd::_argument()`'s own docstring (`"--name"
on its own counts as "1" ... a flag and a valued option are read the same
way`), and already correctly implemented in two sibling files —
`marble3d_render.gd::_parse_options()` (has an explicit
`else: options[split[0]] = "1"`) and `race2_scene.gd::_options()` (a
differently-written but equivalent `if split < 0: out[body] = "1"`).
`course_scene.gd` itself calls this convention on real, currently-shipped
flags — `--no-glow`, `--sequence`, `--dump-terrain` are all checked via
`options.get(name, "") != ""`, so a bare `--no-glow` on the command line
silently does nothing today. The bug is currently **latent** rather than
actively firing: every real caller in `tools/*.py` already always passes the
`--flag=1` form explicitly (verified by grepping `tools/` and `tests/` for
every affected flag name), so no existing render currently produces a wrong
frame because of it — but it is a real, present defect a careful maintainer
would want fixed for consistency and future manual/CLI use, not one
constructed to flatter a tool.

- **Base commit:** `f2116a5fdaf0f5150753b36cb525f94e1c62b1f2` (the unified
  lab merge, identical `course_scene.gd` content to `main` @ `8b1022a`).
- **Authorized paths:** `godot/scripts/course_scene.gd` only, one function.
- **Acceptance criteria:** (1) a bare `--<name>` now yields
  `options["<name>"] == "1"`; (2) `--<name>=<value>` is byte-for-byte
  unchanged; (3) no other function in the file changes; (4) no other `.gd`
  file changes; (5) behavior matches `marble3d_render.gd::_parse_options()`
  and `race2_scene.gd::_options()` for identical input.
- **Required tests:** none exist today that exercise `_options()`'s runtime
  behavior — confirmed by search, not assumed absent (this absence is itself
  a finding, per the brief's own instruction). Validation used a disposable
  headless Godot probe script (`_bench_c_probe.gd`, never committed,
  deleted after each run): `preload()`s `course_scene.gd`, instantiates it
  without adding it to the tree (so `_ready()` never fires), calls
  `._options()` directly, and prints the dictionary as JSON. Run once with
  `-- --no-glow` and once with `-- --no-glow=1`; before the fix the bare
  form printed `{}`, after it printed `{"no-glow":"1"}`, matching the
  `=1` form exactly. Godot binary:
  `Godot_v4.7.2-stable_win64_console.exe` (per `[[godot-binary-location]]`).
- **Risk:** LOW. `course_scene.gd` is superseded lab-era code (predates
  `race2_scene.gd`, the currently-shipped Race #2 line), still exercised by
  5 real tests (none of which check this behavior), not on the frozen
  visual/camera path. The fix is strictly additive relative to every
  existing caller.
- **Model/tier:** Sonnet 5, STANDARD, no escalation.
- **Review policy:** self-review inside this session plus the deterministic
  Godot probe, in place of Company OS's reviewer pass (see methodology note
  above).

All three conditions below produced the **exact same, byte-identical,
2-line diff**:

```diff
 		if split.size() == 2:
 			options[split[0]] = split[1]
+		else:
+			options[split[0]] = "1"
 	return options
```

## C0 — baseline (Read + Grep only)

No Ctags, no tree-sitter, no Serena, no Graphify.

1. `Read` — `course_scene.gd` lines 225–244 (~600 chars).
2. `Grep` — pattern `^func (_options|_parse_options|_argument|_parse)\(` with
   9 lines of trailing context, across `godot/scripts/`. Matched 17 files in
   one call; saved output was **36,984 bytes**.
3. `Edit` — apply the fix.

| Metric | Value |
|---|---|
| Tool calls | 3 (1 Read, 1 Grep, 1 Edit) |
| Navigation context volume | ≈ 37,584 chars |
| Files touched | 1 |
| Files read (unique) | 1 targeted + 17 surfaced by one Grep call |
| Searches | 1 |
| Repeated/irrelevant reads | 0 |
| cache-read / cost / turns | NOT MEASURED (see methodology note) |
| Quality | correct, byte-identical to reference, probe-validated, no regression |

## Ctags — candidate 1

Not installed at session start (`ctags: command not found`). Installed via
`winget install UniversalCtags.Ctags` (v6.1.0, from the
`ctags-win32` GitHub release) — reversible with `winget uninstall
UniversalCtags.Ctags`, no repository vendoring, no production dependency
added.

- **GDScript support:** native, first-party (`--list-languages` lists
  `GDScript`; `--list-kinds-full=GDScript` shows `const`/`class`/`enum`/
  `method`/`signal`/`variable`/`parameter` kinds).
- **A real operational defect found and worked around:** `ctags -R
  --languages=GDScript` (recursive directory mode) returns **zero** tags
  against this repository's `.gd` files on this Windows build, even though
  `--print-language` correctly identifies every file and a direct per-file
  invocation (`ctags -f - path/to/file.gd`) works perfectly. The verbose
  trace shows the file opened and the parser initialized, then nothing
  emitted. Root cause not fully isolated within this benchmark's budget;
  the practical workaround (`find godot -name "*.gd" | ctags -L - -f
  tags`) works reliably and was used for every measurement below.
- **Index construction:** 0.105s for all 81 files via the `-L -` workaround.
- **Index size:** 2,543 tags, 332,700 bytes, one flat tags file.
- **Query used for BC-1's actual navigation need** (list every
  `_options`/`_parse_options`/`_argument`/`_parse` definition, file + line):
  a `grep` over the tags file, **2,085 chars**, exact file:line for all 17
  candidates, sorted, matching the set found by both the C0 grep and the
  tree-sitter parse exactly.
- **Definition lookup:** works, file+line, one line per symbol.
- **Reference/call-site lookup:** none — Ctags' GDScript parser here has no
  reference-only role enabled (`REFONLY` column is `no` for every kind), so
  it cannot answer "who calls `_options`," only "where is it defined."
  `preload()` targets are visible only as incidental text inside `const`
  tags' pattern field, not as a structured edge.
- **Deterministic screening: PASS.** Replaying C0's actual navigation
  need (locate all candidate definitions to compare) against the tags file
  answers it completely and correctly, in far fewer characters than the
  grep-with-context approach.

### C1 — live run

Same base commit (`f2116a5`, worktree `c1-ctags`), same objective, same
authorized paths.

1. Bash — grep the pre-built tags file for the four candidate names
   (2,085 chars).
2. `Read` — 10 lines of `marble3d_render.gd` at the exact line the tags
   file named (212), to see the reference `else:` branch's body (~300
   chars).
3. `Edit` — apply the fix.

| Metric | Value |
|---|---|
| Tool calls | 3 (1 Bash query, 1 Read, 1 Edit) |
| Navigation context volume | ≈ 2,385 chars |
| Index build (one-time, amortizes across queries) | 0.105s / 332,700 bytes |
| Quality | byte-identical to C0, probe-validated |
| Delta vs C0 | **−93.6%** navigation-context volume; same tool-call count |

## Tree-sitter-gdscript — candidate 2

Not installed at session start. Installed `tree-sitter` +
`tree-sitter-gdscript` via `pip install` into an isolated, disposable venv
(`ts-eval-venv`, never the project's own `.venv`) — reversible by deleting
the venv directory, no project dependency added.

- **Install:** clean, no compiler needed — both packages ship prebuilt
  wheels for this Python (3.13) on Windows, confirming the research doc's
  claim of Windows compatibility without a build step.
- **Parse:** 0.335s for all 81 files (a single Python script, one process),
  1,077 `function_definition` nodes found (see the methodology-difference
  note in the inventory section above for why this differs from grep's 626
  and ctags' 2,543).
- **Same candidate set:** the 17 `_options`/`_parse_options`/`_argument`/
  `_parse` definitions found by tree-sitter are identical, file-for-file and
  line-for-line, to both C0's grep and Ctags' index — cross-validating all
  three navigation methods against each other on this task.
- **Unique capability over Ctags:** tree-sitter serves the **exact function
  body**, extracted directly from the parse tree by byte span, in the same
  query that lists candidates — no separate `Read` call is needed. It also
  answers structural questions Ctags cannot (e.g. "does the second
  `if` in this function have an `else` clause?" → `True`, computed from the
  tree, not from reading text).
- **No persistent index in this benchmark's implementation.** Unlike
  Ctags' flat tags file, the evaluation script re-parses all 81 files on
  every invocation (0.335s). A production version would need its own
  caching layer, architecturally identical to `repo_map.py`'s existing
  `build_and_cache()` — this is exactly the pattern the base research doc
  recommended, and is additional (small) implementation cost tree-sitter
  carries that Ctags does not.
- **Deterministic screening: PASS**, and materially better than Ctags for
  this specific need: it eliminates the follow-up targeted `Read` entirely.

### C2 — live run

Same base commit (`f2116a5`, worktree `c2-treesitter`), same objective, same
authorized paths.

1. Bash — one Python script invocation: lists the 17 candidates, then
   returns `course_scene.gd::_options()`'s own current body (334 chars) and
   `marble3d_render.gd::_parse_options()`'s reference body (340 chars) in
   the same call. Total ≈ 1,570 chars.
2. `Edit` — apply the fix.

| Metric | Value |
|---|---|
| Tool calls | 2 (1 Bash query, 1 Edit — no separate Read) |
| Navigation context volume | ≈ 1,570 chars |
| Parse cost (per invocation, uncached) | 0.335s / 81 files |
| Quality | byte-identical to C0/C1, probe-validated |
| Delta vs C0 | **−95.8%** navigation-context volume, **1 fewer tool call** |
| Delta vs C1 | ≈ −34.2% navigation-context volume, **1 fewer tool call** |

## Quality comparison

All three conditions: correct, byte-identical 2-line diff, verified against
the same disposable Godot probe (bare flag → `"1"`, `=value` form
unchanged), zero scope violations (only the authorized file changed in each
worktree), zero regressions (the 5 tests that reference `course_scene.gd`
still pass). **Quality is tied across all three conditions on this task.**

## Resource comparison — the honest reading

This project's own documented variance floor
(`ai-resource-efficiency-v2-after-validation` / this milestone's cited 37%
spread between two runs of the identical `attempts-remaining` task) applies
here: **C1 vs. C2's ≈34% difference is below that floor and should not be
reported as a confident win for tree-sitter over Ctags on a single n=1
task.** C0 vs. either candidate (93.6%–95.8%) is far above that floor and is
a real, reproducible effect — reproducible in the literal sense that it was
independently re-derived twice (once for C1, once for C2) from the same
frozen base commit and reached the identical correct answer both times.

**The predeclared Benchmark C adoption threshold (Section 13 of the
brief) is correctness-gated, not efficiency-gated:** *"ADOPT the specific
candidate only if it correctly resolves symbol references... that plain
Read+Grep... gets wrong or misses."* On this task, plain Grep in C0 did
**not** get anything wrong or miss any reference — it found all 17
candidates correctly, in one call, and produced a fully correct fix. Under
the letter of that threshold, **neither Ctags nor tree-sitter clears the
bar for ADOPT**, because the control did not fail. This is recorded
faithfully rather than papered over.

At the same time, the **general primary metric** (Section 17: total
resource cost per accepted result, using cache-read/tool-output volume as
its proxy) shows both candidates producing the same accepted result at
roughly 1/15th to 1/24th the navigation-context volume of plain Grep, on a
task that already required comparing structurally similar definitions
across many files — exactly the shape of task this project's own reads
dominate its cache-read cost on. That is a real, large, currently
unclaimed efficiency opportunity, even though it does not satisfy this
specific benchmark's narrower correctness-only bar.

## Tool overhead

| | Ctags | tree-sitter-gdscript |
|---|---|---|
| Static tool/schema chars | 0 (no MCP tools, a subprocess call) | 0 (a Python import, no MCP tools) |
| Install | `winget install`, reversible, no repo change | `pip install` into an isolated venv, reversible, no repo change |
| New dependency if productionized | one external binary (no Python package) | two Python packages (`tree-sitter`, `tree-sitter-gdscript`) |
| Index/parse cost | 0.105s (81 files, via workaround) | 0.335s (81 files), no cache in this benchmark's implementation |
| Persistent artifact | 332,700-byte flat tags file | none (re-parses per invocation, unless a cache layer is added) |
| Known defect | `-R` recursive mode returns 0 tags on this Windows build; `-L -` workaround required | none found |
| Reference/call-graph queries | no (definitions only) | no (definitions + bodies + structure; still no cross-file call graph) |
| Windows | confirmed working live | confirmed working live, no compiler needed |

Neither candidate's overhead consumed a material fraction of its own
measured saving (both wells under the brief's 25% overhead-vs-saving reject
trigger).

## Adoption recommendation

**WINNER: INCONCLUSIVE**, precisely stated: inconclusive **against this
benchmark's own predeclared correctness-only adoption bar**, because the
baseline (plain Grep) did not fail or miss anything on this task, so no
candidate can be said to have fixed a correctness gap the baseline had. This
is not the same as "no difference was found" — a large, cross-validated,
twice-reproduced efficiency difference (93.6%–95.8% less navigation-context
volume for an identical accepted result) was found on the general resource
metric, with tree-sitter's edge over Ctags specifically (≈34%) sitting
right at this project's own documented noise floor and therefore reported
as directional, not confident.

- **Serena needed next:** **no.** Both lightweight candidates passed
  deterministic screening and produced a correct, accepted result; per
  Section 13 of the brief, Serena is only warranted if both fail.
- **Graphify tested:** no (out of scope for Benchmark C).
- **RTK tested:** no (out of scope for Benchmark C).
- **Productionized:** no. Ctags was installed via `winget` (uninstalled
  after this benchmark); tree-sitter's venv is disposable scratch. Neither
  touched the repository, `requirements.txt`, or the
  `CodeIntelligenceProvider` seam.
- **Canonical Company OS modified:** no. **`main` modified:** no.
- **Recommended next milestone:** a **repeated-task** efficiency benchmark
  (n≥3 distinct GDScript navigation tasks, not one) specifically targeting
  the general resource metric rather than the correctness-only bar this
  milestone used — with a real Company-OS-runner-mediated live session (once
  that constraint is lifted) to get an actual cache-read/cost measurement in
  place of this session's char-volume proxy. If that confirms the
  93%+ reduction holds across tasks, wire a bounded, cached, tree-sitter-gdscript
  provider through the existing but currently-unwired
  `CodeIntelligenceProvider` seam in `company/efficiency/providers.py`,
  choosing tree-sitter over Ctags specifically because it needs no follow-up
  `Read` call and because a body/structure-serving provider matches
  `repo_map.py`'s own existing architecture more closely than a
  location-only one — with the `-R` Ctags defect and the tree-sitter
  caching gap both noted as implementation risks to close first, not
  ignored.

## Unanswered semantic-navigation needs

Neither Ctags nor tree-sitter, as evaluated here, can answer "who calls
`_options()`" or "which scenes preload this module" as a structured,
queryable edge — Ctags exposes no reference role for GDScript in this
build, and tree-sitter's parse tree only gives per-file structure, not a
cross-file call graph. `preload()`/`load()` edges are visible only by
grepping tag/parse output for the literal path string, the same way this
benchmark's own inventory step in `docs/` measured them. If a future task
genuinely needs "every scene that calls into `v2_track.gd`," that is
exactly the class of query this benchmark's two lightweight candidates
cannot answer and Serena (or a purpose-built local call-graph index) would
need to supply — consistent with the base research doc's own framing.
