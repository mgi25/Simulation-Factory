# AI Resource Optimization Lab — Benchmark C2: Repeated GDScript Efficiency Validation

Status: **Checkpoint C (freeze T1/T2/T3 + the 3×3 matrix) complete.**
Checkpoint D (live benchmark) has not run. This document will grow a
section per checkpoint; it does not yet contain conclusions about which
candidate wins — that is Checkpoint D's job.

**Deliberate omission in this section**: the actual T1/T2/T3 answers
(which symbols, which line spans, which files are required vs. distractor)
are not written anywhere in this document or anywhere else in this git
working tree. See "Ground-truth isolation" below for why and where they
live instead.

## Checkpoint A summary (evidence audit, prior session)

`company-os-resource-lab-benchmark-c` (`d2a01dc`), `c1-ctags` (`40a8a59`)
and `c2-treesitter` (`f8314f2`) were audited read-only, found free of vendor
files, venvs, generated indexes, credentials and unexpected binaries, and
pushed to origin for reproducibility. `c1-ctags` and `c2-treesitter` are
byte-identical trees to the C0 fix commit `d82fdde` — same 2-line
`godot/scripts/course_scene.gd` fix, independently found by each candidate.

## Checkpoint B — C2 lab construction

### Baseline

- `origin/main` = `8b1022aec899c7fa72ca77f2a1441c4d1b4ff48f` — unchanged since
  Benchmark C; no refresh required.
- `origin/company-os-v1-bootstrap` = `b84f8a75a2d4aaeefd88798f23bc5948e7d39195`
  — authoritative Company OS baseline (the remote-tracking ref, not the
  local `company-os-v1-bootstrap` branch, which sits ahead at `01a1638` and
  was intentionally left untouched).
- Clean unified baseline: `f2116a5fdaf0f5150753b36cb525f94e1c62b1f2`, the
  merge commit with parents `8b1022a` (production `main`) and `b84f8a7`
  (canonical Company OS). It predates the C0 benchmark fix (`d82fdde`), so
  C2 branches from it directly rather than from `d2a01dc` — no BC-1 code
  change is replayed into the C2 baseline.
- C2 branch: `company-os-resource-lab-benchmark-c2`, created at `f2116a5`
  (HEAD unchanged after setup — all Checkpoint B work is currently
  uncommitted-then-committed on top in a single setup commit; see below).

### Workspace safety

All cross-branch inspection of `company-os-resource-lab-benchmark-c`,
`c1-ctags` and `c2-treesitter` used only `git show` / `git diff` / `git log`
/ `git ls-tree` / `git merge-base` / `git rev-parse` — no `checkout`,
`switch`, `restore`, `reset`, `cherry-pick` or `merge` touched the shared
clone. The shared `v21-visual-contrast` worktree was verified unchanged
before and after this checkpoint (branch, HEAD, and clean status all
identical). All mutable C2 work happened in a dedicated worktree:

```
C:/Users/mgial/OneDrive/Documents/projects/wt-company-os-benchmark-c2
  branch: company-os-resource-lab-benchmark-c2
  created from: f2116a5 (git worktree add ../wt-company-os-benchmark-c2 -b company-os-resource-lab-benchmark-c2 f2116a5)
```

### Baseline validation

Confirmed in the dedicated worktree before adding any tooling:

- `godot/scripts/course_scene.gd` does **not** contain the BC-1 two-line
  fix — this is the genuine pre-fix baseline.
- No Ctags-generated index, tree-sitter cache, venv, or candidate-provider
  production wiring present anywhere in the tree.
- No production module (`race2/`, `sloped/`, `godot/`, `tools/race2*.py`)
  imports `company.*` — dependency direction unchanged from Benchmark C's
  own finding ("production and Company OS touch disjoint file sets").

Focused deterministic smoke suite (not the full 5,451-test suite, per the
brief — `f2116a5` was already validated during Benchmark C with a recorded
18-failed/4,993-passed/440-skipped fingerprint, all 18 pre-classified):

```
python -m pytest tests/test_sloped_guards.py tests/test_company_runtime.py \
  tests/test_company_integration_gate.py tests/test_company_efficiency.py \
  tests/test_engineering_runner_repo_map.py tests/test_engineering_runner_execution_context.py
  -> 230 passed

python -m pytest tests/test_sloped_race.py \
  tests/test_engineering_runner_exploration_telemetry.py \
  tests/test_engineering_runner_exploration_report.py
  -> 65 passed
```

Total: **295/295 passed, 0 failed** across Company OS
architecture/runtime/efficiency/runner/integration-gate coverage and
representative production (Sloped/Godot) + telemetry coverage. This is
consistent with, not contradictory to, the historical 18-failure fingerprint
— those 18 failures live in files outside this focused set (branch-DAG
"no locked file moved" guards that only fail once multiple version branches
are unified, and one pre-existing `neon_scene` Godot-absence test).

### The code-intelligence seam

`company/efficiency/providers.py` already defines the exact seam this
milestone needs, unused for real symbol lookup:

```python
class CodeIntelligenceProvider(Protocol):
    name: str
    def query(self, request: CodeIntelligenceQuery) -> CodeIntelligenceResult: ...
```

`CodeQueryKind` enumerates `SYMBOLS`, `CALLERS`, `DEPENDENCIES`, `PATH`,
`LIKELY_FILES`. The only existing implementation,
`ReferenceRepositoryProvider`, only implements `LIKELY_FILES` (validating
caller-supplied candidate paths against the filesystem) and explicitly
returns `available=False` with reason `"the reference provider has no
symbol graph; inject a code-intelligence provider"` for every other kind.
`GRAPHIFY_STATUS` in the same file documents that this seam was designed
for a future Graphify injection that has never happened
(`"not installed; repository reference provider remains active"`). This
confirms the milestone's premise directly from the code: the seam exists,
compiles, and is exercised by `company/efficiency/benchmark.py`'s
deterministic Company/Python fixtures, but has never been asked to do real
GDScript symbol/definition/reference work.

Both new Benchmark C2 providers implement this exact Protocol (`name` +
`query()`) so they are structurally interchangeable with a real future
Graphify-backed provider, without touching `providers.py`, `benchmark.py`,
or any canonical runtime file.

### Ctags — isolated

- **Version**: Universal Ctags 6.1.0(v6.1.0) — matches the version proven in
  Benchmark C exactly.
- **Installation**: `winget install --id UniversalCtags.Ctags --version
  6.1.0`. Per-user install under
  `%LOCALAPPDATA%\Microsoft\WinGet\Packages\UniversalCtags.Ctags_...\`,
  reversible via `winget uninstall UniversalCtags.Ctags`. Not vendored into
  the repo; not a production or Company OS dependency.
- **Recursive-mode finding reproduced**: `ctags -R godot/` still produces
  only pseudo-tag header lines (0 real tags) in this environment. The
  working invocation from Benchmark C is confirmed and reused: build an
  explicit file list with `find`/`Path.glob`, then
  `ctags -f <tags> -L <filelist> --languages=GDScript --fields=+n`.
- **GDScript files indexed**: 81 (`godot/**/*.gd`)
- **Tag count**: 2,543
- **Build time**: 66.5 ms (measured via `CtagsProvider.build_index()`,
  `subprocess.run` + parse; a raw shell `time ctags ...` on the same
  invocation measured ~82 ms wall)
- **Index size**: 332,604 bytes (with `--fields=+n`; the tags file is never
  committed to git — written to the OS temp directory, rebuilt per session)
- **Definition lookup**: file + line number confirmed correct — e.g.
  `_options` resolves to `godot/scripts/course_scene.gd:231`, matching
  tree-sitter's independently-derived start line exactly.
- **Reference/caller capability**: none. `ctags --list-kinds-full=GDScript`
  shows every kind (`const`, `class`, `enumerator`, `enum`, `local`,
  `method`, `signal`, `variable`, `parameter`) with `REFONLY=no` — there is
  no caller/reference role for GDScript in this ctags build. The provider
  reports `CALLERS`/`DEPENDENCIES`/`PATH` queries as honestly unavailable
  rather than emulating them.
- **Output ceiling**: 20 matches per query, 4,000 chars per query result
  (`MAX_MATCHES` / `MAX_RESULT_CHARS` in `tools/benchmark_c2/ctags_provider.py`),
  truncation flagged on the result rather than silently dropped.
- **Query latency**: sub-millisecond to low-single-digit ms per
  `readtags`-equivalent in-memory lookup once indexed (index parsed once
  into two dicts; query is a dict lookup, not a subprocess call).

### Tree-sitter-gdscript — isolated

- **Version**: `tree-sitter-gdscript` 6.1.0 (grammar by
  `prestonknopp/tree-sitter-gdscript`, MIT license), Python binding
  `tree-sitter` 0.23.2. Matches the grammar family/revision identified
  during Benchmark C's research phase.
- **Installation**: dedicated venv **outside the repository tree** at
  `C:\Users\mgial\.benchmark-c2\tsvenv` (`python -m venv`, then
  `pip install tree-sitter==0.23.2 tree-sitter-gdscript==6.1.0`). Not
  committed; not referenced by any production or Company OS requirements
  file. `tools/benchmark_c2/treesitter_provider.py` imports both packages
  inside a guarded `try/except ImportError` block so importing the module
  elsewhere never requires them to be installed.
- **Windows compatibility**: confirmed — installs and runs directly via
  `pip` on Windows/Python 3.13 with no build step (prebuilt wheel).
- **GDScript files parsed**: 81 (same `godot/**/*.gd` set as Ctags)
- **Parse failures**: 0
- **Parse/index time**: 214.0 ms for all 81 files (1,643,697 source bytes)
  — slower than Ctags' 66.5 ms, consistent with tree-sitter doing a full
  AST parse per file versus Ctags' single-pass tag scan.
- **Symbol extraction coverage**: 2,582 symbols (functions, classes,
  variables, consts, signals, enums), walked to depth 2 (top-level and one
  level of nesting, e.g. methods inside a class) — intentionally bounded,
  not a full-tree dump.
- **Body/span extraction**: yes — this is tree-sitter's differentiator.
  `node.start_point` / `node.end_point` give an exact line range;
  `_options` in `course_scene.gd` resolves to lines 231–240 (matching
  Ctags' independently-derived start line of 231 exactly), with a bounded
  288-character body. Ctags has no equivalent — it only reports a start
  line and a search pattern, never an end line.
- **Inheritance / preload / load extraction**: not implemented in this
  provider. The grammar exposes `extends_statement` and would support it,
  but Checkpoint B only builds what the frozen T1/T2/T3 tasks (Checkpoint
  C) will actually need — building unused capability now would be
  premature.
- **Relationship support**: none across files. Same-file structural
  nesting only (depth-limited walk). `CALLERS`/`DEPENDENCIES` queries are
  reported unavailable via the same honest-unavailable pattern as Ctags,
  never emulated.
- **Output ceiling**: 20 matches per query, 4,000 chars per query result,
  4,000 chars per extracted body (`MAX_MATCHES` / `MAX_RESULT_CHARS` /
  `MAX_BODY_CHARS` in `tools/benchmark_c2/treesitter_provider.py`).
- **Query latency**: in-memory dict lookup after indexing, same order of
  magnitude as Ctags' lookup.

### Provider tooling added

All under the dedicated C2 worktree, benchmark-only, none imported by
canonical runtime:

- `tools/benchmark_c2/__init__.py` — package docstring stating isolation.
- `tools/benchmark_c2/types.py` — `SymbolMatch`, `ProviderQueryResult`,
  `ProviderCallRecord`, `ProviderTelemetry` (provider-side telemetry only;
  deliberately separate from the runner's real model-usage telemetry).
- `tools/benchmark_c2/ctags_provider.py` — `CtagsProvider`
  (`CodeIntelligenceProvider`-compatible), `locate_ctags_binary()`
  (env var → `PATH` → winget glob, never vendored).
- `tools/benchmark_c2/treesitter_provider.py` — `TreeSitterProvider`
  (`CodeIntelligenceProvider`-compatible), guarded lazy import.
- `tests/test_benchmark_c2_providers.py` — 18 deterministic tests, no model
  calls.

**Files changed**: 5 new files, all under `tools/benchmark_c2/` and
`tests/`. **No production GDScript, no production Python outside
`tests/`, no canonical Company OS runtime file, no dependency manifest**
was modified. `git status` in the dedicated worktree shows exactly these 5
paths as the only change from `f2116a5`.

### Deterministic provider tests

```
python -m pytest tests/test_benchmark_c2_providers.py
  (system Python, no tree-sitter installed) -> 12 passed, 6 skipped

C:\Users\mgial\.benchmark-c2\tsvenv\Scripts\python.exe -m pytest tests/test_benchmark_c2_providers.py
  (isolated venv, both providers available) -> 17 passed, 1 skipped
```

The complementary skip pattern is intentional: the "tree-sitter reports
itself unavailable" test skips itself when tree-sitter *is* installed, and
vice versa for the success-path tests. Together the two runs exercise
every case in the checkpoint's required list: provider disabled, Ctags
query, tree-sitter query, output ceiling, truncation-on-oversized-result
path (exercised by construction — `MAX_RESULT_CHARS`/`MAX_MATCHES` are
enforced unconditionally in `_to_result`), missing symbol, invalid/missing
binary handling, provider isolation (`test_providers_are_isolated_instances`),
read-only behavior (before/after byte-identical source file checks), and
telemetry event generation. No test invoked Sonnet/Claude or any other
model.

### C0/C1/C2 isolation, preserved

Nothing built in this checkpoint wires either provider into the runner's
default path. `ReferenceRepositoryProvider` remains the only provider
`company/efficiency/benchmark.py` uses. A C0 developer session run against
this worktree today would see exactly current normal Read/Grep navigation,
with neither candidate provider available to it — the architecture keeps
C0/C1/C2 as an opt-in choice made by whatever harness Checkpoint D builds,
not a runtime default.

### Limitations carried into Checkpoint C

- Neither provider gives a real cross-file caller/reference graph. Any T2
  ("cross-file relationship") task frozen in Checkpoint C must be
  answerable from same-file structure, `extends`/`preload` text matching,
  or explicit candidate-path validation — not a true call graph. This
  matches Benchmark C's own prior conclusion and is not a regression.
- Tree-sitter's body/span capability is real and measured; whether it
  matters for the specific T1/T2/T3 tasks (not yet frozen) is a Checkpoint
  C/D question, not decided here.
- Ctags' 66.5 ms and tree-sitter's 214.0 ms build times are both far below
  any plausible per-task wall budget; this checkpoint makes no claim about
  which is faster in a way that matters, only that both are measured.

### Confirmation

**No live AI/model sessions ran during Checkpoint B.** Every measurement
above came from local, deterministic subprocess/parse calls against the
repository's own tracked files.

## Checkpoint C — freeze T1/T2/T3 + the 3×3 matrix

Machine-readable frozen definitions live under
`docs/validation/company_os_ai_resource_benchmark_c2/`:
`tasks.json` (questions, common instructions, output schema, per-condition
tool policy, model configuration), `experiment.json` (scoring rules,
resource-metric schema, run order, index policy, stop conditions, decision
rule, Serena trigger), and `ground_truth_fingerprint.json` (a hash, not the
answer key itself — see below). This section is the narrative companion;
it does not repeat the actual answers either.

### Source freeze

All nine Checkpoint D runs must see byte-identical `godot/` content. This
is the same clean unified baseline `f2116a5` Checkpoint B validated —
`git diff --stat f2116a5 HEAD -- godot/` is empty, so the Checkpoint B
tooling commit on top changes nothing under `godot/`. Every ground-truth
file's git blob SHA-1 and SHA-256 are recorded in the (external) ground
truth file, so a mismatch at Checkpoint D start is immediately detectable
without revealing what the hash is protecting.

### Task design

Three fresh tasks (none reusing BC-1's `course_scene.gd::_options` fix),
each in a different file/relationship shape:

- **T1 — large-file local navigation**, in `godot/scripts/neon_scene.gd`
  (3,086 lines, the largest GDScript file in the repository, confirmed via
  `wc -c godot/scripts/*.gd`). Asks for the exact symbol behind one
  concrete, observable behavior, described without naming the symbol.
  Contains a naturally-occurring in-task distractor: a same-named function
  exists in a different scene file (confirmed via both providers' own
  query output during design — Ctags and tree-sitter both returned two
  matches for the target symbol name, one per file), so selecting the
  wrong file's version is a real, checkable failure mode, not a
  hypothetical one.
- **T2 — multi-file production path**, tracing one shared command-line
  convention across two independent scene files that each implement it
  separately (confirmed via `Grep` across `godot/scripts/` during design:
  exactly two files match). Neither file is named in the frozen question.
  Contains a same-file distractor: a sibling camera-building path in one
  of the two files that is reached from the same dispatcher function but
  explicitly does not consume the traced value (its own source comment
  says so).
  This does not require true cross-file caller/reference intelligence —
  neither provider has it (Checkpoint B). It measures whether compact
  definition/body lookup reduces the manual search a multi-file task still
  requires, exactly as instructed.
- **T3 — structural change-surface discovery**, in
  `godot/assets/marble_machine/lab_palette.gd`, a file eleven other
  GDScript files across `godot/scripts/` and
  `godot/assets/marble_machine/` reference (confirmed via `Grep` for its
  preload/load path). Asks which exact symbols in that one file would
  need to change to add one new capability, which symbols in the same file
  are already generic enough to need no change, and which of the eleven
  referencing files are genuine-but-irrelevant distractors for that
  specific question. This is the task instrumented to measure irrelevant
  navigation, per the milestone's own emphasis.

  **Honest caveat found during the leak-check below**: two pre-existing,
  already-committed production docs (`docs/sloped_race_v23.md`,
  `docs/sloped_race_v23_machine_colour.md`, both inherited from the
  unified baseline, written long before this benchmark) name
  `lab_palette.MACHINE_PASSES` directly while describing the existing
  three color passes. This is real, ambient repository documentation, not
  a benchmark-design leak — it is equally reachable by C0, C1, and C2
  through the same ordinary `Grep`/`Read` every condition has, so it does
  not bias the comparison between conditions. It may make T3's core
  mechanism easier to find for all three conditions than the source-only
  reading in this section implies, which is a fact about this task's
  real-world difficulty worth carrying into Checkpoint D's interpretation,
  not a reason to redesign the task now (Checkpoint C freezes tasks before
  seeing condition-specific performance, not before seeing the repository
  itself).

All three were designed by manually navigating the repository with
Read/Grep-equivalent tools only — the same toolset C0 gets — which is
itself a lightweight proof that C0 can theoretically solve each task
without any candidate provider.

### Ground-truth isolation

The actual answer key (required symbols, exact line spans, distractor
lists, and the reasoning connecting them) is stored at
`C:\Users\mgial\.benchmark-c2\ground_truth\c2_ground_truth.json` — a path
outside every git repository on this machine, in the same location family
as the isolated tree-sitter venv. It is never committed. Only its SHA-256
and byte length are committed, in `ground_truth_fingerprint.json`, so
tampering after freezing is detectable without the fingerprint itself
revealing anything.

**Why not just commit it and deny the path to developer sessions?**
Because denial is a configuration a future harness change could get wrong
silently, while a file that is not present at all cannot be leaked by a
policy bug. `tasks.json` also declares an explicit `universal_denials`
entry for `docs/validation/company_os_ai_resource_benchmark_c2/` and the
external ground-truth directory as defense in depth, but the primary
control is that the answer key is physically outside the checkout
Checkpoint D's sessions will ever see.

**Proof, deterministic, no model calls:**
- `git grep` across every committed file in this branch for the six most
  distinctive ground-truth symbol names returns zero matches outside the
  actual GDScript source files themselves (verified during this
  checkpoint) — i.e. no separate document packages the answer conveniently
  for a shortcut search.
- `tasks.json`, `experiment.json`, and `ground_truth_fingerprint.json` were
  each grepped for those same symbol names after being written; zero
  matches.
- The external ground-truth file's directory
  (`C:\Users\mgial\.benchmark-c2\`) is a sibling of the git repository
  root, not a descendant of it — a session whose working directory is a
  runner-managed worktree under `worktree_root/<branch>` has no path
  relationship to it at all.

### Model, condition, and tool policy freeze

Recorded in full in `tasks.json`. Summary: model = `sonnet`
(`tools/engineering_runner/resources.py`'s own `DEFAULT_TIER_MODELS[STANDARD]`
alias, which resolves to Claude Sonnet 5 in this account), STANDARD tier,
default effort, exactly one developer attempt per condition with no
automatic retry, the existing runner's own `developer_timeout_s` (3,600s)
as the wall ceiling, and the existing `DEFAULT_DEVELOPER_TOOLS` /
`DEFAULT_DISALLOWED_TOOLS` as C0's unmodified tool policy (so C0 is not
handicapped relative to a normal session). C1 adds exactly one bounded
tool wrapping `CtagsProvider`; C2 adds exactly one bounded tool wrapping
`TreeSitterProvider`; neither removes anything from C0, and neither
condition can reach the other's tool. All three ceilings and the tool
lists come from values already established in this repository's runner
config or Checkpoint B's own measurements — nothing here is an invented
number.

### Scoring, telemetry, run order, index policy, stop conditions, decision rule

All frozen in `experiment.json`, structurally: CORRECT/PARTIAL/WRONG rules
that reference ground-truth field names (required files/symbols,
distractors, tolerance) without restating their values; the full
model/navigation/provider telemetry schema from the milestone brief,
carrying forward two known, already-documented telemetry limitations
([[ai-resource-efficiency-v2-telemetry-defect]] and
[[repository-exploration-efficiency-v2-stop-condition]]'s `--verbose`
requirement) so Checkpoint D does not have to rediscover them mid-run; a
balanced run order (`T1: C0→C1→C2`, `T2: C1→C2→C0`, `T3: C2→C0→C1`); an
index policy that rebuilds each provider's index once per condition (not
per task) and reports that cost separately from per-task model resource
use; nine stop conditions; a decision rule anchored to Benchmark C's own
~37% noise-floor finding; and a Serena trigger that requires a demonstrated,
recurring capability gap rather than a feature-list comparison.

### Validation performed (no model calls)

- Every ground-truth file confirmed to exist and match its recorded git
  blob hash at `HEAD` (== `f2116a5` for these paths).
- Every ground-truth symbol confirmed locatable by name via both
  `CtagsProvider.find_definition()` and `TreeSitterProvider.find_definition()`,
  with tree-sitter's independently-derived line spans matching the manual
  reading exactly, and both providers' start lines agreeing with each
  other exactly.
- Every call-site/consumer relationship in the ground truth was read
  directly from source, not inferred.
- Every distractor's classification is backed by a specific, checkable
  reason (a same-named symbol in a different file; a sibling function
  whose own comment disclaims the traced behavior; a real reference that
  is an adoption site rather than part of the capability's change surface).
- Ground-truth isolation proven per the "Ground-truth isolation" section
  above.

### Confirmation

**No live AI/model sessions ran during Checkpoint C.** All task design and
validation used the same Read/Grep-equivalent navigation C0 will get, plus
the two providers' own deterministic query methods already validated in
Checkpoint B.
