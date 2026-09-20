# Executable work, and the discovery that was unreachable behind it

The previous end-to-end pilot ended at `NO_EXECUTABLE_WORK_CANDIDATE` having
spent nothing. That was the right answer, reached by the wrong route, and this
change fixes the route.

## The defect

Planning counted **eligible** candidates. Eligibility answers "may the company
choose this?" — status, department, capsule ownership, risk, budget, evidence,
falsifiable criteria. It does not answer "would anything come of choosing it?".

Those turned out to be different questions. Deterministic eligibility left
exactly one candidate, `reserved-screening-negation-blindness`. Planning took
the one-candidate rung — arithmetic, no model — and selected it. Normal intake
then refused the work order derived from it: the candidate is a defect *in*
credential screening, its title contains the word `credential`, and
`screen_credentials()` matches that word anywhere in an objective. The defect
blocked the authorization of its own fix.

Bounded discovery existed for exactly this situation. It was unreachable,
because the condition guarding it read:

    eligible == 0   ->   discovery may run

So the company could hold work it was allowed to choose and could not start,
and the one mechanism for finding different work sat behind a door that only
opens when the register is empty.

## The change

    executable == 0   ->   discovery may run

where **executable** means: passes deterministic eligibility, derives a bounded
`WorkOrderProposal`, *and* normal engineering intake authorizes that proposal.

`company/delegation/viability.py` answers that per candidate by deriving the
work order and dry-running `assess_request` — the real one, with the real
permissions and the real repository root. Nothing is written, no job is opened,
no attempt is consumed. The cost is milliseconds per candidate against a
developer session that costs real money and, in the pilot that motivated this,
was about to be spent on a work order that could never have been authorized.

Three things it does not do:

- **It does not weaken intake.** A candidate intake refuses is refused here.
- **It does not rewrite candidates.** No retry with different wording, no scope
  trimming, no risk downgrade.
- **It does not decide.** It produces verdicts; planning reads them.

## What the CEO can now see

`PlanningRunRecord` carries `viability_assessed`, `executable_candidate_ids`
and `not_executable`, so the record answers the question the previous pilot
could not: *why did management not choose the candidate that looked eligible?*

The record refuses three contradictions outright: results recorded without the
assessed flag; an executable id that was never eligible (viability narrows, it
cannot widen); and a SELECTED run naming a candidate viability refused.

A run given no viability check keeps the older behaviour and records
`viability_assessed: false`, so an unchecked run cannot be mistaken for one
that checked and found everything workable.

## A second discovery reader

Discovery had one deterministic reader: capsule staleness. Every capsule in
this repository rechecks in 2027, so that reader honestly returns nothing —
which is how the previous run reached discovery and still found no work. A
mechanism that is only reachable when it has nothing to say is not much of a
fallback.

`gate_advisory_proposals` reads the production integration gate's own
**committed** readiness report and turns a failing **advisory** check into a
candidate. Advisory findings are precisely known problems nobody has been asked
to fix. It reads one JSON file the caller names, walks no trees and opens no
prose, and it refuses two things deliberately:

- **A failing required check produces nothing.** That is a blocker, and routing
  a blocker into the work register would let the company schedule around
  something meant to stop it.
- **A finding it cannot scope produces nothing.** `_ADVISORY_WORK` maps a check
  id to a write scope and acceptance criteria; a finding absent from that table
  is for a person to read, not to hand a developer a write scope for.

The report must be a committed file, because `validate_proposal` requires
evidence that exists as something a reviewer can open. A report built in memory
during planning is not that.

## What was not done

The CEO forbade four escapes and none was taken:

- `reserved-screening-negation-blindness` was **not** excepted. It is still
  refused by intake, and a test pins that.
- `screen_credentials()` and reserved-action screening were **not** weakened.
- The candidate was **not** reworded.
- `tools/` was **not** given a capsule. `runner-blocked-attempt-repo-dir` still
  fails `capsule_owned`, and a test pins that too.

## Evidence

- `tests/test_company_executable_work_planning.py` — 23 tests across the nine
  required cases.
- `docs/validation/company_os_executable_work_planning/` — suite evidence and
  the gate report: 2145 selected, 0 failed, READY 34/34, no blockers.
