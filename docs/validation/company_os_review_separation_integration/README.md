# Curated canonical integration: review separation, the classifier fix, and the authority audit

Built from canonical `92b308c` (shadow). Nothing here makes canonical capable
of live delegated execution, and nothing here rewrites the historical pilot.

## What was integrated, and why each piece earned it

Four things, each production-worthy independently of any pilot runtime.

1. **The independent engineering reviewer** — `software_review_engineer`
   holding `code_review`, a new `engineering_reviewer` worker seat, and the
   capability-registry entry. From `e334c49`.
2. **Ordinary-review routing** — intake asks for `code_review` on work the
   routing did not call architectural, and for `software_architecture` on work
   it did. The choice is made in intake, where the specialist domain is known;
   the dataclass default stays `software_architecture` so a hand-built order
   still asks the architect.
3. **The runner's `--no-push` preflight** — refused before a session starts
   rather than after it is paid for. The first end-to-end pilot lost USD 0.86
   to this exact configuration.
4. **`WorkOrderProposal.authorized_branch` and `.base_commit`** — taken from
   `19a606a` as a file-scoped change to `company/delegation/planning.py` only.
   None of that commit's seven pilot modules, its pilot tests or its design doc
   came across.
5. **The auth/migration classifier fix** — `_QUOTED_IDENT` in
   `company/engineering/intake.py`, in its corrected form from the historical
   pilot's correction branch, with both of its tests. Integrated under an
   explicit CEO exception; see "provenance" below.

## What was deliberately left out

`PilotActivation`, `evaluate_live`, `LivePilotDecisionRecord`, `PilotEnvelope`,
`PilotBoundaryViolation`, `pilot_correction`, `pilot_integration`,
`pilot_record`, `pilot_report`, `pilot_simulation`, the pilot CLI commands, the
pilot design doc and the pilot tests. Verified absent: no `pilot*.py` exists
under `company/delegation/`, and no runtime module references any pilot symbol.
`company/delegation_policy.yaml` still reads `mode: shadow`.

## The management-authority audit

The review-separation branch's `future_job_simulation.json` recorded `cto` as
the actor for all four of `approve_code_change`, `approve_test_progression`,
`approve_review_outcome` and `approve_integration_merge`. That reads as the
Engineering Manager being bypassed. It was not. Two separate causes, traced:

**The simulation filed every request as the manager.** The test passed
`requesting_seat="engineering_manager"` for all four actions.
`company/delegation/authority.py` refuses self-approval, so the manager was
skipped by construction on the three decisions it owns and each fell through to
the CTO. Only the integration actor was asserted, so the other three went
unnoticed into the evidence file. **This was the defect, and it was in the
simulation, not in the policy.**

**The manager's ceiling is `low`, on purpose.** At MEDIUM risk the manager
returns `risk_above_ceiling` and the CTO decides, against a CTO carrying
`medium`. That grant is explicit in the policy with the rationale "routine
low-risk engineering work". It was **not** widened. An ordinary routine job is
LOW and stops at the manager.

Fixed by filing each request from the seat that actually raises it and
asserting every actor rather than only the last. The corrected
`future_job_simulation.json` now records four management decisions taken by
`engineering_manager` and integration by `cto`, with the CEO required nowhere.

Four tests pin it:
`test_a_future_job_completes_without_the_ceo`,
`test_the_manager_does_not_decide_its_own_request`,
`test_medium_risk_routine_work_escalates_to_the_cto_by_design`,
`test_architecture_review_still_disqualifies_the_cto_from_integration`.

The architecture case is unchanged and was not weakened: architecture work
still routes its review to `chief_architect`, the CTO is still disqualified
from integrating work its own employee reviewed, and that chain still reaches
the CEO.

## Provenance of the classifier fix

`auth-migration-classifier-ambiguity` is marked COMPLETED in
`company/delegation/candidate_seeds.json`. Its implementation came from the
historical end-to-end delegation pilot: developer, independent review, one
bounded correction authorized by the Engineering Manager, second review PASS,
deterministic required suites 11/11 green. The pilot did not fail technically.
It stopped at integration because integration authority correctly escalated,
and its classification stands unchanged as
`END_TO_END_DELEGATION_ESCALATED_CORRECTLY`. The CEO later authorized curated
canonical integration of that specific completed change as an exception, which
is why no paid developer or reviewer session was re-run.

Two tests pinned the seed register's open-candidate set and broke when that
candidate closed. Both now build the register they need by appending a reopened
version of the candidate — the register is append-only and the latest version
of an id wins — so they test the mechanism rather than this week's backlog.

## Evidence

- `suite_evidence.json` — 32 Company OS suites, 2122 selected, 0 failed.
- `gate_report.txt` — READY, 34/34 required, 0 blockers. The 4 advisory
  findings are the pre-existing ones and are unchanged from the baseline.
- `docs/evidence/company_os_review_separation/future_job_simulation.json` —
  the corrected authority distribution.
