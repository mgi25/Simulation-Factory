# Job C — not executed

Same reason as `job_b/NOT_EXECUTED.md`: the batch stopped after Job A's legitimate
`decision_required` outcome, per the CEO's batch rules (A -> B -> C, proceed only if the
previous job reached `ready_for_approval` with no systemic blocker).

Job C (`req-finance-usage-observation-dedup`, capsule `company-finance`) was selected and
passed dry deterministic-intake validation before execution began, but no real work
order, packet, or runner session was ever created for it. Nothing in this directory
should be read as execution evidence.
