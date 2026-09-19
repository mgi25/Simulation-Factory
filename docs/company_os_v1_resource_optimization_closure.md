# Company OS — GDScript Navigation-Provider Research: Closure

Status: **CLOSED.** This document is the final decision record for the
lightweight code-navigation-provider research line (Benchmarks C2 → C3 →
C4). No further benchmarking in this line is scheduled. Company OS
development returns to normal (non-research) work after this record.

## Original problem

Company OS's own engineering-runner sessions, and this research program's
earlier "AI resource optimization research" milestone, identified that
Company/Python code exploration was already efficient (no additional
tooling indicated), but **GDScript structural navigation** — finding a
function's definition, span, and callers inside the marble-race production
codebase (`godot/`) — was a plausible gap: built-in `Read`/`Grep`/`Glob`/
`Bash` have no symbol index, so answering "where is X defined, and what
does it look like" over a large `.gd` file means guessing a grep pattern
and paging through source by hand. Two lightweight, external, read-only
candidates were identified as worth testing before considering anything
heavier (Serena): **Ctags** (a mature, generic tag indexer) and
**tree-sitter-gdscript** (a structural parser with body-level extraction).

The question this research line existed to answer: *should either
candidate be added to Company OS's read-only navigation toolset for
GDScript work, given real measurement rather than intuition?*

## Benchmark C2 — first live attempt (inconclusive)

Three tasks (T1–T3) were run under three conditions (C0 baseline, C1
Ctags, C2 tree-sitter). **Provider utility was inconclusive because
provider use was largely absent**: the model was free to choose whether to
call the provider tool at all, and in most runs it simply didn't — Grep
and Read were faster to reach for. A benchmark that never exercises the
thing it's testing cannot answer the question. This directly motivated
C3's design: force provider use via an explicit per-condition directive.

## Benchmark C3 — forced-use, inconclusive by its own frozen rule

Branch `company-os-resource-lab-benchmark-c3` @
`dffee0ca375da745b8536c7f75272ba4d964d05e`.

Two tasks (A, B), three conditions (C0, C1 Ctags, C2 tree-sitter), a
directive requiring at least one provider call before falling back to
built-ins. Results, all CORRECT:

| Task | Ctags Δ context_load | tree-sitter Δ context_load |
|---|---|---|
| A (large-file structural localization) | −38.7% | −64.9% |
| B (same-name multi-definition comparison) | +1.372% | +1.128% |

Both candidates cleared the noise floor decisively on Task A and regressed
(marginally) on Task B. C3's own frozen `mixed_result_handling` rule
requires a contingency Task C before any conclusion can be drawn when one
task passes and the other fails for the same candidate — and the
pre-drafted Task C turned out to require cross-file caller/reference
resolution that **neither Ctags nor tree-sitter supports for GDScript**
(confirmed live, not assumed). Redesigning Task C after seeing A/B results
would have been a post-hoc change to the experiment, so it was not
attempted. **C3 closed INCONCLUSIVE.** Neither candidate was productionized
or rejected; Ctags and Serena were deferred pending resolution of
lightweight-provider utility.

## Benchmark C4 — candidate prioritization, valid mechanical result

Frozen experiment commit `2784973dd21908b997862f31d2fbcd500ec1a723`;
apparatus-only pre-run fix `472ae5b948d3ca562aa3142e8cf905e765a945b5`
(a PowerShell 5.1 stderr-handling bug in the runner script, caught and
fixed before any official session launched — no official run was ever
attempted against the broken version); closure commit `d021e83`. Branch
`company-os-resource-lab-benchmark-c4`.

C4 narrowed scope deliberately: **tree-sitter only** (Ctags deferred, not
re-tested — C4 is candidate prioritization, not a retroactive C3 re-run),
**two conditions only** (C0, C2 — no contingency task, no mixed-result
handling; the decision rule is applied mechanically to whatever the six
runs produce), and **three new tasks**, none reused from C2 or C3,
deliberately including one task designed to be easy for built-ins (a
control against the possibility that a provider only ever looks good
because every benchmark task is hand-picked to favor it).

Six runs, all procedurally valid (`claude-code 2.1.70`, `permission_mode:
default`, no bypass flag anywhere, zero contamination, provider invoked as
the *first* tool call and genuinely relevant in every C2 run), all CORRECT
with identical classification between conditions on every task (no
regression):

| Task | C0 context_load_tokens | C2 context_load_tokens | Δ |
|---|---|---|---|
| 1 — structural localization (1070-line file) | 139,218 | 96,872 | −30.4% |
| 2 — multi-definition comparison (5 files) | 42,682 | 43,726 | +2.45% |
| 3 — grep-friendly control | 51,808 | 40,751 | −21.3% |

- **BASE_TOTAL** = 233,708. **TREE_TOTAL** = 181,349.
- **Aggregate reduction** = −22.4%. **Required threshold** = −30%.
- Per-task regression guardrail (≤15%): **PASS** (worst case was Task 2's
  +2.45%, well inside the bound).
- Operational-overhead guardrail (turns, navigation characters ≤ +25%
  over baseline): **PASS** — tree-sitter used *fewer* turns (12 vs 20
  aggregate) and *fewer* navigation characters (−11.6%) than baseline, not
  more.
- No apparatus defect touched an official result.

Every criterion in the frozen decision rule passed **except aggregate
savings**, which is the one criterion the rule allows no exception for.

## Final operational policy

1. **Default GDScript/repository navigation remains native**: `Read`,
   `Grep`, `Glob`, `Bash`. No change to how any Company OS or production
   session navigates code.
2. **tree-sitter is NOT productionized.** C4 was a valid, complete,
   mechanically-applied experiment; its answer is no.
3. **Ctags is NOT productionized**, but this is **deferred, not rejected**
   — C4 did not re-evaluate it (C4 was tree-sitter-only by design), so no
   valid current evidence exists to reject it outright. C3's own evidence
   for Ctags (−38.7% / +1.372%, structurally identical shape to
   tree-sitter's C3 numbers) was itself inconclusive under C3's rule.
4. **Serena remains deferred.** It is not tested unless future real
   production evidence demonstrates a recurring navigation/semantic
   problem that built-ins cannot handle efficiently enough — a materially
   higher bar than "a benchmark task exists for it."
5. **No further navigation-provider benchmark (no C5) starts without a new
   CEO request.** See the backlog document for the specific reopening
   triggers.

## Why tree-sitter was not adopted despite showing benefits on some workloads

**"Do not productionize" does not mean tree-sitter is technically bad.**
On the task shape it's actually suited for — locating and inspecting
implementation in a large, unfamiliar file — it delivered a real, honest
−30% to −65% reduction across two independent benchmarks (C3 Task A, C4
Task 1), with correct answers both times. The problem is not the tool; it
is that **the precommitted bar was an aggregate 30% reduction across a
representative task mix, not a best-case reduction on the tasks it's
naturally good at**, and a representative mix necessarily includes tasks
where a provider adds a real (if small) tax — C4's Task 2 needed one
provider call regardless of how many files were being compared, which
turned out to cost slightly more than a single well-aimed Grep for a
distinctive symbol name already would have. Adding a new runtime
dependency (an isolated Python venv, an MCP server process, a cache-build
step) to every Company OS and production session's tool surface is real,
permanent operational complexity — a second thing to keep working,
version, and reason about — and the frozen threshold exists precisely so
that complexity is only added when the aggregate benefit clearly justifies
it. −22.4% is a real, measured, positive number. It is not the number the
threshold asked for.

## Why additional benchmarking is not currently cost-effective

Three independent, honestly-run benchmarks (C2, C3, C4) have now measured
this question from three angles — unforced use, forced use with a mixed
task set, and forced use with a task set deliberately including an
easy-for-baseline control — at real API cost across 6+6+6 = 18 live
sessions in total. C4's result is not ambiguous or borderline in the way
C2 and C3's were: every non-aggregate criterion passed cleanly, and the
one criterion that failed did so by a specific, quantified margin (−22.4%
vs a −30% requirement) on a task mix that was itself designed not to favor
either candidate. Running a C5 without a materially different premise
(different task population, a different provider, or new production
evidence that the current task mix under-samples a workload GDScript
navigation actually faces) would very likely reproduce the same aggregate
shortfall at further real cost, for a question that already has a valid
answer. The backlog document below names the specific conditions under
which that premise could change.

## Ctags / tree-sitter / Serena status (at closure)

| Candidate | Status | Why |
|---|---|---|
| Ctags | **DEFERRED** (not rejected) | C4 did not evaluate it; C3's own evidence for it was inconclusive under C3's rule |
| tree-sitter | **NOT PRODUCTIONIZED** | C4 valid result: −22.4% aggregate vs required −30% |
| Serena | **DEFERRED** | Never tested in this research line (explicitly out of scope for C2/C3/C4); no current evidence a lighter-weight option can't handle the workload |

## Exact relevant branch/commit references

- `company-os-resource-lab-benchmark-c2` — first live attempt, inconclusive (provider use largely absent)
- `company-os-resource-lab-benchmark-c3` @ `dffee0ca375da745b8536c7f75272ba4d964d05e` — forced-use, closed INCONCLUSIVE (frozen contingency Task C invalid)
- `company-os-resource-lab-benchmark-c4`:
  - `2784973dd21908b997862f31d2fbcd500ec1a723` — frozen experiment (tasks, prompts, ground truth, decision rule, harness)
  - `472ae5b948d3ca562aa3142e8cf905e765a945b5` — apparatus-only pre-run fix (no official run affected)
  - `d021e83` — closure, final result `DO_NOT_PRODUCTIONIZE_TREE_SITTER`
- None of the above are merged into `main` or into `company-os-v1-bootstrap`. Production behavior is unchanged throughout this entire research line.
