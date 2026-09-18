# Company OS V1 — routine eligibility guard

## Gap found by the operational-readiness review

The review recommended operating state **C — routine autonomous engineering
with CEO approval gate**, with one runtime eligibility gap: a breaking
migration/schema/storage-format/wire-protocol change was only escalated out of
routine `STANDARD`-tier execution when the CEO's objective happened to use one
of the existing specialist trigger words (`schema change`, `protocol change`,
`breaking change`, `migrate`, `migration`). State C should not depend on the
CEO phrasing a dangerous change using a lucky trigger word.

## The fix

`company/engineering/intake.py`'s `SPECIALIST_TRIGGERS["architecture"]` table
gained a dedicated set of phrases naming breaking structural changes:

- `migrate the`, `database migration`, `schema migration`
- `storage-format migration`, `storage format migration`
- `serialization-format migration`, `serialization format migration`,
  `replace the serialization format`
- `wire protocol`, `wire-protocol`
- `backward-incompatible`, `breaks compatibility`

A hit routes the request to the existing `architecture` specialist domain, the
same one that already handles rewrites and re-architecture. No new domain, no
new eligibility engine: `derive_routing` still produces the one
`specialist_domain` value that `assess_request` and, downstream,
`ai_platform.resource_classes.classify` both read. A non-empty
`specialist_domain` already keeps `classify` off the `small_reasoning_floor`
(routine class C) rule and onto `specialist_reasoning` (class D) — that
enforcement point was not touched, because the review's gap was in what fed
it, not in how it was read.

The two previous bare triggers, `migrate` and `migration`, were removed. They
were the exact "incidental wording" problem: `migrate`/`migration` alone also
matched harmless mentions such as "show migration status on a dashboard."
Every replacement phrase pairs the noun with what makes it *breaking*, so a
routine mention of schema/protocol/migration/format stays routine.

`request.notes` continues to play no part in routing (the V3A correction), and
the bare noun `governance` remains non-triggering — both are covered by
existing tests and neither was touched.

## False-positive protection

Confirmed to stay routine: "Document the current schema," "Display protocol
status on the CEO page," "Add tests for the existing serialization format,"
"Show migration status on a dashboard," "Add schema information to a report,"
"Rename a field in documentation," and a routine objective whose *notes*
mention a past schema migration.

## Tests

`tests/test_company_engineering_execution.py`, new section 13b:

- 6 routine objectives assert `specialist_domain == ""` and cite
  `"routine implementation"` in the recorded reason.
- 1 test pins that a breaking-change phrase inside `notes` does not route.
- 6 objectives (the ones the operational-readiness review named) assert
  `specialist_domain == "architecture"`.
- 4 objectives spanning security/governance/concurrency/older-architecture
  triggers pin that the new table left the rest of specialist routing
  untouched.
- explicit `specialist_domain`, explicit `escalate_reasoning`, and HIGH/CRITICAL
  `risk` are each re-asserted authoritative over a breaking-change or
  routine-looking objective.
- one test drives `ai_platform.resource_classes.classify` directly with
  `derive_routing`'s own output, on both a routine and a breaking request, to
  demonstrate the class C / class D split end to end through the one existing
  enforcement path — not a second eligibility check.

Every assertion above checks the recorded derivation/reason string, not only
the resulting domain, per the milestone's requirement.

## State-C eligibility

With this change, a job reaches routine `STANDARD`-tier eligibility only when
all of the pre-existing conditions still hold (LOW/MEDIUM risk, reversible,
bounded scope, acceptance criteria and required tests available, no
CEO-reserved action, no credential handling, no explicit escalation) **and**
now, deterministically, no breaking migration/schema/storage-format/protocol/
API-contract change — closing the one gap the operational-readiness review
named. The operating state itself was not changed by this milestone; it
remains whatever the CEO/operator has set.
