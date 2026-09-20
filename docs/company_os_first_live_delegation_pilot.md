# The first live-delegation pilot — stopped at Phase 1

**Classification: `OBJECTIVE_TO_WORK_PLANNING_GAP`**

**Spend: $0.00 of $6.00. No developer ran. No reviewer ran. The pilot was never
activated. Canonical delegation mode is still `shadow`.**

---

## OBJECTIVE

Improve the reliability or maintainability of the Company OS engineering system
by completing one genuinely useful, already-existing LOW-risk engineering
improvement — with the company identifying the specific work itself from real
repository evidence.

Authorized by MGI (CEO) on 2026-09-20 as an objective, not as a work order:
department `engineering`, risk ceiling `LOW`, budget USD $6.00, internal pilot
integration target only, one bounded correction, short expiry, no standing
grant.

## STATUS

Stopped at Phase 1, before any paid execution, exactly as the authorization
instructs.

## RESULT

Company OS does not have a genuine objective-to-work planning mechanism.

It has the rung — `objectives.py` models the ladder
`ceo_objective → program → department_goal → work_order → task`, stamps each
child with the parent's intent fingerprint, and refuses a child derived from an
intent the parent no longer has. That machinery is sound.

What it does not have is anything that **fills** the rung. Specifically:

1. **`decompose()` is a constructor, not a planner.** It computes only the
   level. The title, department, success metrics and evidence refs are all
   parameters. What the work *is* arrives from the caller.

2. **There is no backlog to inspect.** The capsule schema has `risks`,
   `failure_learnings` and `decisions` as prose for a human reader. It has no
   `backlog`, `deferred_followups` or `known_debt` field. Nothing in the
   repository is a machine-readable register of work worth doing.

3. **`evidence_refs` are citations, not evidence.** They are hardcoded document
   paths. No module opens them. Company OS cannot read a validation report and
   extract a candidate task from it.

4. **"Choose work" is not a modelled action.** All 35 members of `ActionType`
   are approve / change / stop verbs. The live pilot grants the CTO and the
   Engineering Manager seven actions, every one an approval, a correction
   request, or a stop. Planning cannot be delegated because planning is not an
   act the system can represent — and therefore cannot be recorded, bounded or
   audited.

5. **`org_intelligence` is the wrong instrument.** It asks whether the *company*
   is organized well. Its outputs are organizational change proposals over
   human-supplied evidence, stopping at `PROPOSED`. It never emits engineering
   work.

### The failure mode is worse than an absence

The objective was submitted verbatim to deterministic intake. Intake **did not
refuse it.** It returned `"outcome": "authorized"` — routed to the
`company-engineering-execution` capsule, scoped to `company/engineering`, risk
`low`, `consumer` profile, reasoning ceiling `D`, no specialist escalation. A
clean STANDARD-tier authorization for a request that names no work at all.

The persisted work order carries the CEO's objective verbatim as its own, and
its first acceptance criterion is *"The stated objective is implemented: …"*
followed by the objective. That criterion cannot be reviewed and cannot be
QA'd, because it never names a behaviour.

The derived plan then states the displacement outright. Step `locate-contract`:

> *"Identify the smallest contract that the objective is missing, and state it
> before implementing it"*

So Company OS does not decline to plan. **It bounds the scope correctly and
hands the planning decision to the paid developer session** — an unsupervised
worker choosing its own work against an unfalsifiable acceptance criterion,
with no management decision recorded anywhere.

The authorization anticipated that the *outer orchestration session* might
silently act as management. The real defect points the other way: the system
pushes planning **downward onto the worker**. The separation-of-duties
guarantee the pilot exists to demonstrate would have been void before the first
dollar was spent.

## WORK COMPLETED

No engineering work. The objective was not converted into a task, because the
system cannot do so and the authorization forbids the orchestration session
from doing it on the company's behalf.

## MANAGEMENT DECISIONS

None. No manager was asked to decide anything, because the decision the
objective required — *which work* — is not an action the system can put to a
manager.

## EXECUTIVE DECISIONS

None recorded. The COO and CTO seats are filled and active and hold ample
budget, but the only executive acts available to them are approvals of work
that already exists.

## CEO DECISIONS REQUIRED

One, and it is the Phase 1 deliverable rather than an exception: **authorize
building the objective-to-work planning capability** as the next Company OS
increment. It is not in the current envelope, which covers engineering
improvement work and not a new planning subsystem.

Sketch of what is missing, for that future authorization:

- a machine-readable candidate register — deferred follow-ups, reviewer
  advisories and recorded LOW-risk debt, declared by the capsule that owns the
  code, so the evidence is owned rather than scraped;
- a `plan_objective` / `select_work` action in `ActionType`, so the choice is a
  delegable, recordable, auditable act with a seat attached;
- a planning decision record analogous to `LivePilotDecisionRecord`, naming the
  executive, the evidence consulted, the candidates rejected and why;
- an intake refusal: a request whose acceptance criteria reduce to *"the stated
  objective is implemented"* should return DECISION REQUIRED, not
  `authorized`. This one is a defect in the current system regardless of
  whether the planning layer is ever built.

## EXCEPTIONS

None of the policy exception classes fired. Budget, risk, authority and
protected refs were never approached, because execution stopped before the
first paid step.

## TEST / QUALITY RESULT

Not reached. No code changed in any Company OS module, so no suite was affected.

## INTERNAL INTEGRATION RESULT

None. `company-os-v1-delegated-engineering-pilot-integration` was never created
and nothing was integrated anywhere.

## AI COST

**$0.00 actual against a $6.00 budget.** No provider session was started for a
developer or a reviewer role. The only model process was this outer
orchestration session, which is CEO-side scaffolding and not a Company OS
employee.

## TIME

One orchestration pass, 2026-09-20. All Phase 1 verification was reading and
deterministic CLI execution.

## FINAL OUTCOME

The pilot did not run, and it should not have. The result is the one Phase 1
names as valuable: the live-delegation machinery is ready and the layer above it
is not. Company OS can govern work; it cannot yet choose work. Until the rung
between an objective and a work order is a real capability with its own action,
its own evidence and its own decision record, a "live delegation pilot" driven
by an objective would either be planned by the orchestration session — which
the authorization forbids — or planned by the developer, which is what the
system actually does today and which defeats the pilot's purpose.

The recommended next increment is the planning capability itself, plus the
intake refusal that would have caught this in the first place.
