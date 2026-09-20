# Activation: bounded routine engineering, canonical

Built from canonical `bdbe71b`. This is the pass that turns the mode on as a
*supported capability*. It does not start an objective.

## Curated delta

From `company-os-v1-bounded-engineering-autonomy` @ `e36ebf1`, runtime only:

**Included** — the 7 live-authority modules, `operating_mode.py`,
`objective_lifecycle.py`, `promotion.py`, `objective_report.py`,
`PilotBoundaryViolation`, the delegation CLI, the runner CLI hardening, the
candidate register with the preserved advisory, and three test files.

**Excluded** — every `docs/evidence/**` and `docs/validation/**` bundle
belonging to the historical pilots. Those are the record that the pilots
happened; copying them into canonical as runtime state would turn evidence into
configuration. They stay on their own branches.

**Not renamed** — `pilot*.py`. Recorded as debt below.

## What was added in this pass

Three things the previous branch did not have, each needed to turn the mode on
rather than merely demonstrate it:

1. **`ObjectiveContract.from_mapping`** — the CEO entrypoint's reader. Every
   field in `REQUIRED_CONTRACT_FIELDS` must be present and non-empty, and an
   unrecognised field is refused too, because a contract carrying a field
   nobody reads means its author believes something untrue about what was
   authorized. **Nothing is defaulted.** A missing risk ceiling that quietly
   became LOW would be authority nobody wrote down.
2. **Termination and revocation** — `may_activate` now takes `objective_state`
   and `revoked`. A terminal objective and a revoked contract both authorize
   nothing. This is checked in `may_activate` rather than left to the caller,
   because "the objective finished but the activation object is still lying
   around" is precisely the residual-authority bug this mode must not have.
3. **`python -m company.delegation objective-contract`** — read-only. It
   reports what a contract *would* authorize. It opens no objective, spends
   nothing, and activates nothing.

## The default, proved rather than asserted

    no contract                          -> no live authority
    contract(mode=shadow)                -> refused at construction if it names actions
    valid bounded contract, flag absent  -> no live authority
    valid bounded contract, flag present -> live, for that objective only
    expired / terminal / revoked         -> no live authority

`may_activate` defaults `enabled_modes` to shadow only. The CLI requires
`--enable-bounded-engineering`. `evaluate_live` requires an activation passed
by hand. **There is no configuration file, environment variable or global
switch** — each of those is a thing that can be left in the wrong state. Two
tests assert nobody has added one: no module hardcodes the bounded mode into an
`enabled_modes=` literal, and the one place the CLI can enable it is guarded by
the explicit flag with shadow as the else.

`company/delegation_policy.yaml` still reads `mode: shadow` and the shadow
probe still refuses any other value at construction.

## Activation matrix — 63 tests

All twenty required cases, plus the entrypoint:

| # | case | result |
|---|---|---|
| 1 | absent contract | no live authority |
| 2 | shadow contract | refused / no authority |
| 3 | valid bounded contract | live authority |
| 4 | expired contract | no authority |
| 5 | completed contract (all 6 terminal states) | no authority |
| 6 | malformed contract (all 12 required fields, unknown field, non-mapping) | refused |
| 7 | wrong department | refused |
| 8 | excessive risk | refused |
| 9 | spend outside the envelope | refused |
| 10 | reserved/forbidden action in contract | refused at construction |
| 11 | public deployment | refused, CEO required |
| 12 | publishing (staging release, production render) | refused, CEO required |
| 13 | canonical/main promotion (all protected refs) | refused |
| 14 | authority / organization change | refused, CEO required |
| 15 | ordinary engineering chain | internal, CEO absent |
| 16 | one bounded correction | internal |
| 17 | second correction | stop, CEO required |
| 18 | QA failure / control override | stop |
| 19 | architecture-review CTO conflict | escalate |
| 20 | no executable work | clean terminal report, `CEO ACTION REQUIRED: NONE` |

The chain in case 15 resolves: three management decisions at
`engineering_manager`, integration at `cto`, CEO required nowhere.

## Results

- `tests/test_company_bounded_engineering_activation.py` — 63 tests
- `tests/test_company_bounded_engineering_autonomy.py` — 72 tests
- Full Company OS suite — **2440 selected, 0 failed**, 36 suites
- Gate — **READY, 34/34 required, 0 blockers**

## Preserved advisory

`capsule-ownership-semantic-review` is OPEN in the candidate register.
`intelligence/__init__.py` is owned by `company-knowledge-capsules` for
test-constraint reasons rather than semantic ones. **Not fixed to make
activation cleaner.** It is not an activation blocker.

## Technical debt recorded

The validated live-authority runtime is still named `pilot*.py`. Renaming seven
modules and their tests is churn with real regression risk and no behavioural
benefit, and doing it during an activation would mean the thing being activated
is not the thing that was validated. It should be its own candidate before a
third capability builds on those names.

## Protection

`main` at `8b1022a`, untouched. Nothing deployed, nothing published. No
promotion path to canonical exists inside the mode.
