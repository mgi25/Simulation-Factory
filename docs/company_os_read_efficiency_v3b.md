# Execution Efficiency V3B: acceptance-criteria test anchors

## Baseline

baseline branch: `company-os-v1-read-efficiency-v3a`
baseline SHA: `ba851fa735786e45dd4e16adfcb29614a492914b`
new branch: `company-os-v1-read-efficiency-v3b`
new SHA (mechanism commit): `9e6c604988bddf7b42a10d1a990e2110d48fb187`
pushed: yes
merged: no

Preconditions verified before any work: `company-os-v1-read-efficiency-v3a` exists
on `origin` and local/remote HEAD match at `ba851fa7`; the worktree checked out
from it was clean; the V3A commit (routing precision fix + read-pattern
diagnosis) is present in `git log`; `blocked_attempts` does not appear anywhere
in `company/engineering/lifecycle.py`.

## Exact task match

The original V2 CEO request was recovered in full from
`company-os-repo-exploration-v2-state/engineering/requests/req-repo-exploration-v2-blocked-count-2-3a11340a4aed/000002.json`
(the actual `CEORequest` record, not just the compiled work order), so nothing
here was reconstructed by guesswork.

same V2 objective: yes, verbatim - "For one engineering job, tell me how many
developer attempts were BLOCKED for an authority-scope violation, so a CEO
page can show that count alongside developer attempts and reviewer passes."
same V2 acceptance criteria: yes, all 5, verbatim.
same authorized path shape: yes - `company/engineering/lifecycle.py` +
`tests/test_company_engineering_execution.py` allowed; the same forbidden set.
same risk/reversible: yes - `risk: medium`, `reversible: true` (recovered from
the original request record, not invented).
same tier: yes - `consumer` profile, `standard` tier, `sonnet`, one developer
attempt, one reviewer pass, no specialist domain, no escalation - confirmed by
`derive_routing()` returning `EscalationReason.NONE` and `specialist_domain=""`
before the live run.

**Differences from V2's work order, and why:** new `request_id`
(`req-blocked-attempts-v3b-2`), new `work_order_id`
(`wo-blocked-attempts-v3b-2`), new `authorized_branch`
(`eng-blocked-attempts-v3b`), and `base_commit` is V3B's own mechanism commit
rather than V2's. A first submission (`wo-blocked-attempts-v3b`, superseded)
omitted `scope_ceiling` and so authorized the whole `company/engineering`
directory instead of the exact V2 scope; it was left unactioned once the
narrower, request-matching resubmission was authorized - the same corrective
pattern V2 itself used for its own mis-scoped first attempt
(`req-repo-exploration-v2-blocked-attempts`).

## Test anchor mechanism

matching mechanism: `TestPatternAnchor` in
`tools/engineering_runner/execution_context.py`, wired into the developer
briefing only (`briefs.py::_developer_execution_context`), never the reviewer.
ranking mechanism: deterministic identifier/token matching - no LLM, no
embeddings. Two identifier shapes count as an "exact identifier phrase"
(snake_case and PascalCase); a phrase match scores 5x a plain meaningful-token
overlap. A self-reference filter strips the test file's own stem (and its
constituent words) from the match targets, so a criterion that merely names
the test file to change does not manufacture a match against every candidate
in it.
max anchors: 2 (`MAX_TEST_ANCHORS`).
excerpt policy: at most 1 anchor carries a source excerpt (`MAX_TEST_ANCHOR_EXCERPTS`),
bounded by the existing `MAX_EXCERPT_LINES` (25) / `MAX_EXCERPT_CHARS` (600) -
no new, looser budget.
added context chars: 1,161 (the "Existing test(s) matching..." section).
bundle total chars (developer): 4,493 (budget ceiling unchanged at 6,000).
truncated: no.

anchors supplied in the matched job:
anchor 1: `tests/test_company_engineering_execution.py::test_every_record_round_trips_through_its_own_decoder`
  (#1630-1642) - "acceptance criteria names: engineeringjob, from_mapping"
anchor 2: `tests/test_company_engineering_execution.py::test_the_correction_loop_is_bounded_by_the_work_order`
  (#1172-1237) - "acceptance criteria names: developer_attempts"

Both are the correct sibling tests for the two counter-pattern criteria - not
`_config`, `_index`, `_fake_repo` or `_validation` (structurally excluded, since
only `test_`-prefixed symbols are candidates at all), and not an
unrelated-but-superficially-similar round-trip test on a different class
(`ProtectedSurface`), which an earlier version of the ranking picked until the
self-reference filter and PascalCase phrase matching were added - see
`rank_test_anchors` in `execution_context.py` and its tests in
`tests/test_engineering_runner_execution_context.py`.

## Context cost

| | developer | reviewer |
|---|---:|---:|
| V2 execution-context chars | 3,330 | 1,729 |
| V3B execution-context chars | 4,493 | 1,345 |
| V3B test-anchor chars (subset of the above) | 1,161 | 0 (anchors are developer-only) |
| V2 total instruction chars | 9,807 | 10,158 |
| V3B total instruction chars | 11,069 | 11,326 |
| bundle ceiling reached | no | no |
| truncated | no | no |

The developer bundle grew by the anchor section's own size (+1,163 chars,
matching the +1,161 measured anchor section plus rounding); the reviewer
bundle is smaller than V2's, consistent with an unrelated variable (diff
size), not the anchor mechanism, since anchors were never added to the
reviewer briefing at all.

## Deterministic validation (before the live run)

Focused suite (`tests/test_engineering_runner_execution_context.py`): 26
passed, including all of: a `developer_attempts` criterion ranking above `_config`
(structurally, since `_config` is never a `test_`-prefixed candidate); a
`stop_count`/`spin_count`-style pattern ranking correctly in a synthetic repo;
two named patterns surfacing two bounded anchors; unrelated acceptance prose
producing no anchor; a self-referential filename mention producing no anchor;
deterministic repeat calls returning identical results; excerpt cap at exactly
1 of N anchors; and the full `build_execution_context` bundle, with anchors
included, staying under `MAX_BUNDLE_CHARS`.

Full suite: **4,632 passed, 6 failed, 337 skipped**. All 6 failures are the
project's known pre-existing gap - missing gitignored render artefacts
(`neon_proof`, `sloped_v251_world` x4, `sloped_v252_world` x1) - none in
`company/`, `tools/engineering_runner/` or this milestone's test scope. Zero
new regressions.

## V2 read behavior (recovered from the original runner-state evidence)

total reads: 12
unique files: 2
targeted test reads before first test edit: 10
full/implicit reads: 2
greps before first test edit: 1 (a single grep across `developer_attempts|
reviews_completed|blocked_attempts`, run *before* the first read)
cache-read: 783,941
turns: 26
cost: $0.804993

## V3B read behavior (the live matched job, `wo-blocked-attempts-v3b-2`)

total reads: 5
unique files: 2
targeted test reads before first test edit: 4
full/implicit reads: 1
greps before first test edit: 1 (`developer_attempts|reviews_completed|
test_the_correction` - the grep query itself names the qualified test symbol
the anchor supplied)
cache-read: 568,012
turns: 19
cost: $0.635691

primary threshold: <= 5 targeted pre-edit test reads
threshold met: **yes** - 4, a 60% reduction from V2's 10 (exceeds the
declared 50% target).

resource guardrail: <= 900,000 cache-read
guardrail met: **yes** - 568,012 (also under the aspirational 700,000; delta
against 783,941 is -215,929, or -27.5%).

## Event sequence comparison

| | V2 | V3B |
|---|---|---|
| first production-file read | `company/engineering/lifecycle.py` | `company/engineering/lifecycle.py` |
| first test-file read | order 3 | order 4 |
| targeted test-file reads before first test edit | 10 (orders 4,6-13) | 4 (orders 4,5,12,13) |
| grep calls before first test-file edit | 1 | 1 |
| test anchors supplied | none (V2 predates this mechanism) | 2 |
| first test-file edit order | after order 13 | order 14 |

## Behavior classification

**A: the model used the supplied test anchor and navigated directly.**
Observable evidence, not inference about motive: the developer's one `Grep`
call (order 3) queried `developer_attempts|reviews_completed|
test_the_correction` - the third alternation is the exact qualified-name
prefix of anchor 2 (`test_the_correction_loop_is_bounded_by_the_work_order`),
a string that appears nowhere in the work order's own objective or acceptance
criteria text, only in the supplied anchor. The session still read the test
file directly afterward (4 targeted reads, not blind trust in the excerpt) -
consistent with section 5's design intent that the anchor accelerate
navigation, not replace reading.

## Quality

required tests: pass (`tests/test_company_engineering_execution.py`, 129/129
after the change, per the developer's own receipt and the gate's suite run)
full suite: gate ran its required 11 suites, all green (`11/11 required
suites green; gate says ready at cc78d0efcdef`)
review: pass, 2 advisory findings (no ceiling guard on `blocked_attempts` -
explicitly noted as consistent with `reviews_completed`'s own lack of one; the
CEO dashboard builder not updated - explicitly out of this work order's scope)
gate: READY, 0 blockers
automatic retry: none - one developer attempt, one reviewer pass, as the
`consumer` profile requires

reviewer cache-read: 46,535 (V2: 158,520 pre-V1-fix / 47,922 at V2's own
matched job - V3B is in the same range, confirming the reviewer was not
broadened by this milestone)
reviewer turns: 6
reviewer cost: $0.195453

## External tools

Graphify: not installed
RTK: not installed (governance boundary preserved: the runner subprocess ran
outside RTK's shell hook, since Company OS may not run subprocesses at all
and the runner is the one thing here that does)
Serena: not installed
Ponytail: not installed
ast-grep: not installed

## Consumer viability

**SUPPORTED.** The test-anchor mechanism closed the local-scan gap V3A
diagnosed (ten repeated reads of one already-known-relevant file, hunting for
a sibling pattern) without widening scope, without blocking reads, and
without exceeding the existing context and resource ceilings.

recommendation: **KEEP TEST ANCHORS.**

next measured bottleneck: the developer's now-dominant cost is genuinely
implementation work (4 `Edit` calls to `lifecycle.py`, 1 to the test file,
2 `Bash` calls to run the suite) rather than discovery - discovery is now 5
reads total, 2 of them the file the developer is about to edit anyway. Any
further efficiency gain here would have to come from a different dimension
(e.g. reviewer context, or the developer's own edit/verification loop), not
from more repository intelligence.

## Verdict

**EXECUTION EFFICIENCY V3B: PASS**
