# P5-R3 — external engineering runner ownership

Branch `p5-runner-ownership-v1`, based on `p5-read-authority-v1` at
`d7944aaceb901eabf1d962ac77463f47836dc790`.

This milestone creates the narrowest legitimate ownership boundary for the
external engineering runner, and then reviews the P5-R2 runner-side changes
that were made before an owner existed.

## Addendum: the P5-R2 file count was reported as 8, and is 9

The P5-R2 session summary reported 8 changed files. The actual diff from
`adc8a95` to `d7944aa` contains **9**. The omitted file is
`tests/test_company_evidence_review.py`, with a one-line modification: it adds
`"tests/test_company_read_authority.py"` to the tuple that pins the engineering
capsule's exact declared scope.

The omission is recorded here as an addendum rather than by editing the earlier
report, following the rule in `docs/evidence/reviews/README.md`: a correction
carries its own provenance and the original bytes stay. The line itself is
correct — it is the evidence suite keeping its scope pin in step with the new
test file — so this corrects the *count*, not the change.

The nine files:

| File | Side |
|---|---|
| `company/engineering/intake.py` | Company OS |
| `company/engineering/transport.py` | Company OS |
| `company/engineering/work_order.py` | Company OS |
| `knowledge/company_os/capsules/seeds/company-engineering-execution.json` | Company OS |
| `tests/test_company_engineering_execution.py` | Company OS |
| `tests/test_company_evidence_review.py` | Company OS — **omitted from the P5-R2 report** |
| `tests/test_company_read_authority.py` | Company OS |
| `tools/engineering_runner/authorization.py` | runner — ungoverned |
| `tests/test_company_external_engineering_runner.py` | boundary — ungoverned |

## The blocker, reproduced

Before this milestone, no capsule owned `tools/engineering_runner`. Intake
derives a work order's scope from capsule ownership, so a runner objective had
two outcomes, both wrong, and the first is the worse one:

**1. Silent misroute.** An objective naming the *external engineering runner*,
with no scope ceiling, was **authorized** — onto the wrong subsystem. The token
"engineering" produces the path signal `company/engineering`, which matched
`company-engineering-execution`. The resulting work order authorized
`company/engineering` and listed `tools` as forbidden: the developer would have
been sent to the wrong tree with the right one out of bounds.

**2. DECISION REQUIRED.** The same objective with `scope_ceiling:
["tools/engineering_runner"]` stopped with *"the matched capsule(s)
company-engineering-execution declare no writable path inside the requested
ceiling"*.

## The architectural contract that had to survive

| Question | Answer, and what enforces it |
|---|---|
| Why does the runner live outside `company/**`? | `tools/` is a declared production root (`company/integration/sources.py`). Being production is what lets the runner hold a subprocess. |
| Which import direction is allowed? | Neither. The runner imports no `company`, `ai_platform`, `knowledge` or `intelligence` module — required check `architecture.production_does_not_import_company_os`. Company OS names the runner only in comments; it imports nothing from `tools`. |
| What enforces the separation? | That gate check, plus `tests/test_company_external_engineering_runner.py`, the only module in the repository that imports both halves. |
| What is the subsystem? | The 19 modules under `tools/engineering_runner/`. |

Both directions were re-verified over the source at this HEAD, and are now
asserted by `test_owning_the_runner_did_not_put_it_inside_the_import_boundary`.

## The ownership design

Capsule `company-external-engineering-runner`, `type: module`, 3956/4000 chars.

- **owns_paths**: `tools/engineering_runner` — exactly one directory.
- **may_write**: `tools/engineering_runner/**`.
- **may_read**: the runner tree, the five control-plane files it restates, its
  own milestone doc, and the capsule store.
- **must_not_modify**: `company/**`, `ai_platform/**`, `knowledge/**`,
  `intelligence/**`, `tools/youtube_fetch/**`, `sloped/**`.
- **dependencies**: none. The runner rests on no Company OS capsule, because it
  imports none.
- **tests**: the six suites whose primary subject is the runner.

### What is deliberately *not* owned

`tools/` holds about 130 production scripts beside the runner package, plus
`tools/youtube_fetch`. None of them is claimed. The claim is written as
`tools/engineering_runner`, never as `tools`, for the same reason the evidence
review surface is named exactly: `owns_paths` becomes `authorized_paths`
becomes a developer contract's `may_write`, so a claim one level up would hand a
runner work order write authority over the entire video production toolchain.
`test_no_capsule_owns_any_tools_path_but_the_external_runner` asserts the claim
by value and by owner.

### The prior contract this reverses, and why

`tests/test_company_external_engineering_runner.py` previously asserted that no
capsule may claim anything under `tools/`, on the grounds that a claimed package
would be "inside the control plane's declared surface while living outside its
import boundary". The two halves of that sentence are separable, and separating
them is what this milestone does: `owns_paths` decides who reviews a change and
what a developer may write; the import boundary decides which packages may
import which. An unowned subsystem gets no bounded work order and therefore no
independent review — which is exactly how the P5-R2 change to
`authorization.py` reached this branch ungoverned.

That old assertion had never executed its own failure message: it referenced
`capsule.capsule_id`, which does not exist, and the `AttributeError` surfaced
only when the assertion first failed under this change.

### Ownership is not membership

The capsule is governed but deliberately **outside** the control plane's
dependency graph. Making it reachable from `company-os-control-plane` would
declare that the control plane rests on production — the coupling the required
import check exists to forbid. The exemption is a single named constant,
`company.dashboard.builder.EXTERNAL_CAPSULES`. Three required suites restate
it as a literal to keep their own import surface small, and all three are
pinned against the definition by
`test_the_external_capsule_exemption_is_stated_once_and_agrees`.

## Result

Intake now derives a clean bounded work order for a runner change when the
request names the capsule:

    capsule_hints: ["company-external-engineering-runner"]
    -> authorized: tools/engineering_runner + the six declared tests
    -> forbidden:  ai_platform, company, intelligence, knowledge, sloped,
                   tools/youtube_fetch

## Two findings recorded, not fixed

### 1. Co-selection collapses nested scopes, and fails closed silently

Intake unions `must_not_modify` across every selected capsule and subtracts only
the *exactly matching* authorized paths. When one selected capsule owns a path
nested inside another's prohibition, the ancestor stays forbidden, and
`PathScope` resolves forbidden-over-allowed — so the work order authorizes a
path it simultaneously forbids. Intake reports `authorized`; every changed path
is then refused at receipt validation, after a developer attempt has been spent.

A runner request that uses a path-shaped `subsystem_hint` instead of a capsule
hint co-selects `company-engineering-execution` and lands in exactly this state.

**This is pre-existing and repository-wide, not introduced here.** Across
capsule combinations of size 2–3, 509 already exhibited it before this capsule
existed — `ai-platform` declares `must_not_modify: company/**` while fourteen
capsules own paths under `company/`. The new capsule adds instances of the same
shape; it does not add the shape.

Fixing it means changing how intake reconciles nested scopes, which would alter
the derivation for hundreds of existing combinations. That is materially wider
than this milestone. **Recorded as the next bounded Company OS correctness item.**

### 2. No lifecycle state for authorized work that was never started

`ALLOWED_TRANSITIONS` permits `planning → {developing, decision_required,
blocked, failed}`. `closed` is **not reachable from `planning`**, and
`record_execution_stop` refuses from any state but `developing` or `reviewing`.

So an authorized, planned job that was never started and is later superseded can
only be recorded as `failed` — which mislabels never-attempted work — or parked
indefinitely in a non-terminal CEO state.

A `superseded` terminal state would touch the enum, the transition table,
`TERMINAL_STATES`, the runner's restatement of the state names (and therefore
the drift test across the boundary), the CLI and the dashboard. That is a
coordinated cross-boundary change, materially wider than this milestone.
**Recorded as a bounded Company OS correctness item.** No historical record was
altered and no never-attempted work was marked failed.

## P5 technical closure

| # | Item | State |
|---|---|---|
| 1 | Adaptive economy routing | in place |
| 2 | Matched benchmark | run; conclusion scoped to provider-equivalent monetary cost |
| 3 | Benchmark independent approval | PASS — `docs/evidence/reviews/p3c_vs_p5_matched_benchmark_attestation.md` |
| 4 | Evidence reviewability | closed at `adc8a95` |
| 5 | Read-authority propagation | closed at `d7944aa` |
| 6 | External-runner ownership | **closed here** |
| 7 | Independent review of the P5-R2 runner change | **PASS — closed here** |
| 8 | Canonical validation | green |
| 9 | Integration gate | 0 blockers |

The benchmark conclusion stays scoped: **P5 reduces provider-equivalent monetary
cost for the matched workload while preserving accepted quality.** It does not
establish token savings, and it does not establish subscription-quota savings.

No technical P5 blocker remains. The only outstanding action is the CEO
integration/merge decision, which this milestone does not take.
