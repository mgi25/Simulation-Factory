# The discovery end-to-end pilot

**Classification: `END_TO_END_DELEGATION_SUCCESS`. USD 3.27 of 6.00.**

The company was given one objective, found that none of its known work could
be started, went looking for different legitimate work, found some, and
completed it — developer, independent reviewer, Engineering Manager,
deterministic QA, CTO, internal integration — without asking the CEO anything.

---

## Objective

> Improve the reliability, maintainability, or operating efficiency of the
> Company OS by completing ONE genuinely useful engineering improvement chosen
> by the company itself.

Engineering, MEDIUM ceiling, USD 6.00. One developer, one reviewer, one
bounded correction if needed. No standing grant.

## Known work considered

Seven candidates. Six failed eligibility — two completed, three blocked or out
of department, and `runner-blocked-attempt-repo-dir` failing `capsule_owned`
because nothing owns `tools/`. One passed: the credential-screening candidate.

Run over known work alone, planning returned:

> 1 candidate(s) passed eligibility and none can be worked on
> (`reserved-screening-negation-blindness`: not executable at intake — the
> objective names credential material: credential)

That is the change this pilot rests on. Previously planning counted *eligible*
candidates, selected that one, and only discovered at intake that it could not
be authorized. Now viability is checked first, the record says which candidate
and why, and **discovery becomes reachable** — the condition moved from
`eligible == 0` to `executable == 0`.

The credential candidate was not excepted, not reworded, and
`screen_credentials()` was not weakened. `tools/` was not given a capsule.

## Discovery

Bounded, deterministic, no model. Two readers over authorized surfaces: capsule
staleness (every capsule rechecks in 2027, so it honestly returned nothing) and
the production integration gate's own **committed** readiness report.

The gate had been reporting `architecture.subsystem_ownership_bounded` as
failing — advisory, so it blocked nothing and nobody had been asked to fix it.
Seven Company OS modules were claimed by no capsule. One candidate proposed,
zero rejected, passing all thirteen proposal checks.

Planning then had 2 eligible and 1 executable, so the choice was arithmetic:
**no executive planning session was opened and planning cost USD 0.00.**
Neither the orchestration session nor the developer chose the task.

## Work selected

`gate-architecture-subsystem_ownership_bounded` — *Declare capsule ownership
for the modules no capsule claims*. LOW risk, write scope
`knowledge/company_os/capsules/seeds`, review capability `code_review`.

Normal intake: **AUTHORIZED**.

## Execution

| stage | who | result |
|---|---|---|
| developer | `software_implementation_engineer` (sonnet, standard tier) | commit `020de294`, 3 files, all in scope |
| review | `software_review_engineer` | **pass**, one advisory finding |
| QA | deterministic | **11/11 required suites green** |
| `approve_code_change` | `engineering_manager` | approved |
| `approve_test_progression` | `engineering_manager` | approved |
| `approve_review_outcome` | `engineering_manager` | approved |
| `approve_integration_merge` | `cto` | approved |

No correction was needed — the review passed on the first attempt, so the one
bounded correction the envelope allowed went unused. **The CEO was asked
nothing.**

The acceptance criterion is met and checkable: the gate now reports
*"all 243 Company OS modules are claimed by a capsule"*.

## Internal integration

`eng-capsule-ownership` @ `020de294` → `company-os-v1-delegated-engineering-pilot-integration`.

`main`, `master` and `company-os-v1-bootstrap` are untouched and remain in
`PROTECTED_REFS`. Nothing was deployed and nothing was published.

## The reviewer's advisory finding

Worth the CEO's attention because it is honest rather than convenient:

> `intelligence/__init__.py` is assigned to `company-knowledge-capsules` for
> test-constraint reasons, not semantic ones; the natural owners
> (`company-research-intelligence`, `company-research-operations`) have
> exact-equality assertions that bar additions.

The gate check passes and every module is claimed, but one assignment is
structural rather than meaningful. That is a real follow-up, and it is recorded
here rather than smoothed over. It is not urgent and nothing was done about it.

## Spend

| | |
|---|---|
| planning | USD 0.00 (no model) |
| discovery | USD 0.00 (deterministic) |
| developer | USD 2.6300 — sonnet, 63 turns, 634 s |
| reviewer | USD 0.6437 — sonnet, 24 turns, 153 s |
| **total** | **USD 3.2737 of 6.00** |

Model selection came from the normal resource strategy (`tier:standard`), not
an override.

## End state

- Canonical `company-os-v1-bootstrap` at `bdbe71b`, `mode: shadow`, no pilot
  module. Untouched by this pilot.
- `main` at `8b1022a`. Untouched.
- Live delegation remains pilot-only, activated for this one objective.
- No general autonomy. No second objective.
