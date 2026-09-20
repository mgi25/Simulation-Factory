# CEO objective and operating envelope — as authorized

Recorded verbatim from the CEO authorization of 2026-09-20. This file is the
CEO layer's own input to the pilot. Nothing below was chosen by Company OS or
by the outer orchestration session.

## Objective

    objective_id   obj-first-live-delegation-2026-09-20
    title          Improve the reliability or maintainability of the Company OS
                   engineering system by completing ONE genuinely useful,
                   already-existing LOW-risk engineering improvement.
    constraint     The company must identify the specific work itself from real
                   repository evidence. Do NOT invent a benchmark task.
    set_by         MGI (CEO, external human)
    set_on         2026-09-20

## Envelope as authorized

| Field | Value |
|---|---|
| department | `engineering` |
| risk ceiling | `LOW` |
| budget | USD $6.00 total (developer + reviewer + one bounded correction) |
| integration target | `company-os-v1-delegated-engineering-pilot-integration` |
| protected refs | `main`, `master`, `company-os-v1-bootstrap` |
| max corrections | 1 |
| expiry | short-lived, sufficient for one run |
| authorized_by | MGI |

Allowed action classes: `approve_work_order`, `approve_code_change`,
`approve_review_outcome`, `approve_test_progression`,
`request_bounded_correction`, `stop_work_on_invalid_premise`,
`approve_integration_merge`.

Reserved / forbidden: main and bootstrap modification, public deployment,
publishing, staging release, authority expansion, permissions or
delegation-policy changes, organization restructuring, hiring, security or
governance or major architecture redesign, credentials, secrets, schema or
storage or protocol migration, destructive operations, self-modification of the
objective, additional unrelated work orders. Unknown actions fail closed.

## Envelope instantiation status

**Not instantiated.** `PilotEnvelope` and `PilotActivation` were deliberately
NOT constructed. Phase 1 of the authorization orders a stop before paid
developer or reviewer execution when no genuine objective-to-work planning
mechanism exists, and that stop precedes Phase 4 activation. Creating an
activation token for a run that cannot legitimately proceed would leave a live
grant in the evidence bundle with nothing behind it.

No `PilotActivation` was created. No activation ID exists. The pilot remains
unactivated and canonical delegation mode remains `shadow`.
