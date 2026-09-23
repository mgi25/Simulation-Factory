# P3C vs P5 — matched real-work benchmark

Date: 2026-09-23
Manifest: `benchmark_manifest.json`, sha256 `984ac2065c95b904b7b447375aa9a20c645b4b0f59eab5eb0a98462f09866280`,
frozen and committed at `2dc319b` **before** the first paid session.

## Verdict

**P5_WIN, scoped to provider cost per accepted READY result.**

P5 reduced whole-task provider cost by **46.47%** (mean $0.8723 → $0.4670) with
**no quality regression**. The direction held in both matched pairs and the arms'
cost ranges do not overlap.

It is **not** a win on token consumption. Every token dimension — cache read,
cache creation, output, turns, model wall time — has overlapping ranges across
the two arms, so this benchmark does **not** establish that P5 reduces or
increases token usage. P5 buys its saving by moving routine developer work to a
cheaper model, not by doing less work.

## What P5 changes, and what actually fired

P5 is a tight increment over the P3C baseline: 8 files, 640 insertions, two
mechanisms.

1. **Gated economy downshift.** Company OS may nominate a routine task as an
   economy candidate; the runner then owns the evidence that only exists at
   execution time and applies the downshift only if every check passes.
2. **Content-addressed repo-map cache** keyed on git blob identities.

The downshift **applied on all three P5 attempts, with zero vetoes**:

| field | value |
|---|---|
| candidate | `true` |
| requested downshift tier | `economy` |
| immutable-base diagnostic ran | yes |
| failing required tests at base | 5 |
| failure-symbol hints | 5 |
| failure-guided complete AST spans | 5 |
| runtime authority path count | 1 |
| required test count | 1 |
| veto reasons | *(none)* |
| downshift applied | `true` |
| final developer model | `haiku` → `claude-haiku-4-5-20251001` |
| model source | `adaptive:economy` |

No model was pinned on either arm. The reviewer stayed on `sonnet` at
`tier:standard` in every P5 run, so reviewer independence and strength were
never traded away.

The repo-map cache was observed working: the developer stage ran cold
(0/510 module hits) and the reviewer stage that followed hit 509/510.

## The two matched pairs

Both arms took immutable task base `287d690`, the same objective, acceptance
criteria, constraints, authority ceiling (`tests/test_company_engineering_execution.py`),
required test, `consumer` profile, `code_review` capability and a one-attempt
ceiling. The request files differ only in `request_id` and `authorized_branch`.

| run | arm | dev model | sessions | turns | cache read | cache create | output | cost USD | model wall s | e2e wall s |
|---|---|---|---|---|---|---|---|---|---|---|
| control 1 | P3C | sonnet | 2 | 20 | 363,600 | 45,964 | 9,107 | 0.69686 | 159.30 | 518.09 |
| challenger 1 | P5 | haiku | 2 | 54 | 1,565,335 | 64,083 | 18,815 | 0.63330 | 638.05 | 892.37 |
| control 2 | P3C | sonnet | 2 | 33 | 814,942 | 51,424 | 12,751 | 1.04782 | 364.53 | 661.10 |
| challenger 2 | P5 | haiku | 2 | 26 | 581,333 | 45,703 | 8,720 | 0.30069 | 204.96 | 494.19 |

Pair 1 cost: −9.12%. Pair 2 cost: −71.30%.

Pair 1 was worse for P5 on every token dimension; pair 2 was better for P5 on
every token dimension. That spread is the finding: run-to-run variation on this
task is larger than most of the differences between the two implementations.

## Pooled, with an honesty test

With two samples per arm a mean is a weak instrument, so each dimension also
gets a range-overlap test. Overlapping ranges mean the difference sits inside
run-to-run variation and this benchmark does not establish it.

| dimension | control mean | challenger mean | mean change | ranges overlap | verdict |
|---|---|---|---|---|---|
| paid sessions | 2.00 | 2.00 | 0.00% | yes | not established |
| turns | 26.50 | 40.00 | +50.94% | yes | **not established** |
| input units | 28 | 258 | +821.43% | no | established (economically trivial) |
| cache read | 589,271 | 1,073,334 | +82.15% | yes | **not established** |
| cache creation | 48,694 | 54,893 | +12.73% | yes | **not established** |
| output | 10,929 | 13,768 | +25.97% | yes | **not established** |
| **provider cost USD** | **0.8723** | **0.4670** | **−46.47%** | **no** | **ESTABLISHED** |
| model wall s | 261.92 | 421.50 | +60.93% | yes | **not established** |
| end-to-end wall s | 589.59 | 693.28 | +17.59% | yes | **not established** |
| deterministic s | 258.63 | 218.39 | −15.56% | no | established, but see below |

Cost is the only economically meaningful dimension that separates the arms, and
it separates cleanly: the most expensive P5 run ($0.6333) is cheaper than the
cheapest P3C run ($0.6969). The mechanism is known and causal — Haiku's per-token
price against Sonnet's — so the direction is credible despite n=2.

The deterministic difference is **observed but not causally attributed to P5**.
Its dominant component is gate-suite pytest time (control 170.99 s / 184.51 s,
challenger 128.55 s / 157.77 s), which neither P5 mechanism touches. The
repo-map cache's own wall-time contribution is not separately instrumented:
**UNAVAILABLE**.

### Stage split, pooled

| stage | control mean cost | challenger mean cost | change |
|---|---|---|---|
| developer | $0.61806 | $0.18956 | −69.33% |
| reviewer | $0.25428 | $0.27743 | +9.11% |

The developer saving is where the win lives, and it is **established**: the
ranges do not overlap either (control $0.4447–$0.7914, challenger
$0.1236–$0.2555). The reviewer moved +9.11% on the mean, but its ranges overlap
heavily (control $0.2522–$0.2564, challenger $0.1771–$0.3778), so **no reviewer
effect is established** — P5 neither saved nor cost money at the reviewer.

## Quality — the challenger earned its result

Both P5 accepted runs satisfied every gate:

- acceptance criteria satisfied, zero unanswered;
- exactly one changed file, inside the one authorized path;
- no protected, production, runtime, runner, capsule or governance file touched;
- no subagent — `Task` is in `--disallowedTools` and absent from `--tools`, and
  `execution.no_subagent_runtime_lock` is a required gate check that passed;
- required deterministic validation green (207 passed), runner-owned;
- independent reviewer PASS, zero findings;
- deterministic review adjudication PASS;
- canonical integration gate READY, 11/11 required suites green, zero blockers;
- one developer attempt, no hidden correction;
- remote SHA verified; no merge.

**Semantic equivalence.** Both P3C controls produced the *byte-identical* file
(blob `f6bddac`). P5 challenger 2 produced a file differing from the control by
exactly one comment word — "the test files" against "the two test files".
Semantically identical.

**One observed quality variability, disclosed.** P5 challenger 1 produced a
strict *superset* of the control's change: the same six on-target assertion
updates plus two more — a new `untouched_paths` assertion and a local `scope`
tuple in a test fixture (22 insertions against the control's 13). The
independent reviewer passed it with zero findings and all 207 tests were green,
so it is not a defect. But the controls proved those extra edits unnecessary,
and acceptance criterion 2 says "nothing else is broadened". The economy-tier
developer's *minimality* varied run to run; the standard-tier developer's did
not (both controls byte-identical). This is a real, disclosed difference in
output discipline, not a gate failure.

## The void attempt — reported, not concealed

The first P5 challenger attempt spent **$0.80952** (2 paid sessions, 61 turns,
1,650,055 cache read, 69,944 cache creation, 19,537 output) and ended
`decision_required` without reaching the gate.

Cause: GitHub returned `Internal Server Error` on `git push`
(request id `F0B9:206277:AF8472:C7A220:6AB38621`, 2026-09-23T07:56:19Z). The
completion protocol requires a verified remote SHA, so the receipt was rejected
and deterministic review adjudicated `changes_required` on the single finding
`attempt-not-accepted`. The independent reviewer had itself attested **pass**
with no substantive findings.

This is an external infrastructure fault, not a P5 defect: the control arm
pushed successfully four minutes earlier and the evidence branch pushed
successfully six minutes later.

It is **excluded from the matched comparison** for a specific reason: the
reviewer's brief carried the rejected receipt outcome, which confounds the
reviewer stage. It is **included in the P5 as-spent total**:

| | total spend | accepted READY results | cost per accepted result |
|---|---|---|---|
| P3C, 2 attempts | $1.74468 | 2 | $0.87234 |
| P5, 3 attempts incl. void | $1.74350 | 2 | $0.87175 |

As-spent parity (−0.07%) is a coincidence of one external outage, not a
property of P5. Both figures are reported; neither is the headline.

## Limitations

1. **n = 2 per arm.** Only the cost dimension separates the arms cleanly. Every
   token dimension is inside run-to-run variation. Control cost varied 50%
   between its two runs; challenger cost varied 111%.
2. **Cost is API-equivalent USD, not subscription-plan impact.** The V4 protocol
   already records that the provider publishes no conversion from this field to
   Team-plan usage percentage. P5 spends *more tokens for less money*. If plan
   quota tracks tokens rather than dollars, the −46.47% saving may not transfer.
   Measuring that requires operator-observed plan percentage and was not
   observable here: **UNAVAILABLE**.
3. **The repo-map cache's wall-time contribution is not isolated.** It was
   observed reusing 509/510 modules, but no timing attribution is claimed.
4. **`--output-format stream-json` telemetry only.** Per-session file-read and
   search counts are recorded, but the two arms' exploration counters are not
   compared here because the developer models differ, which makes per-tool
   counts a model property rather than an implementation property.
5. **The two arms' branch names differ by two characters**, an unavoidable
   consequence of giving each run a distinct identity. The effect on token
   counts is far below the observed variance.
6. **One idle orphaned pytest process** (PID 10724, from a dead session two days
   earlier) was resident throughout. It had consumed 74 CPU-seconds in 37.8
   hours and had no children, so it was blocked rather than running, and it
   affected both arms identically. It was left untouched.
7. **Post-freeze modification, disclosed.** After the freeze commit, the two
   `raw/doctor_*.json` captures were rewritten to replace operator-absolute
   paths with `<projects>` / `<home>` placeholders. No measured value changed
   and the pre-redaction content remains in git history at `2dc319b`.
   `benchmark_manifest.json` itself was never modified; its sha256 still holds.

## Branches produced

All pushed, none merged. None may be deleted — they are the benchmark controls.

- `eng-token-efficiency-v4-p3c-control` → `889aaa9`
- `eng-token-efficiency-v4-p5-challenger-b` → `63e76c0`
- `eng-token-efficiency-v4-p3c-control-b` → `eb8b8cf`
- `eng-token-efficiency-v4-p5-challenger-c` → `30e6bbf`
- `eng-token-efficiency-v4-p5-challenger` → local only; its push is the one
  GitHub rejected with a 500.

## Recommended next work package

**Decide whether the economy tier is worth its output-discipline cost, using
plan-quota evidence rather than API-equivalent USD.**

The open question is no longer whether the P5 gate works — it fired correctly
three times out of three with zero vetoes and never touched the reviewer. It is
whether a −46% API-equivalent-dollar saving survives translation into whatever
the subscription plan actually meters, given that P5 consumes *more* tokens to
get there. That needs operator-observed plan percentage before and after a run,
which no runner telemetry can supply.

A secondary, smaller item: the economy developer broadened the change beyond the
authorized minimum in one of two accepted runs, while the standard developer was
byte-identical in both. If the economy tier is kept, the acceptance criterion
"nothing else is broadened" deserves a deterministic check rather than relying
on reviewer judgement.
