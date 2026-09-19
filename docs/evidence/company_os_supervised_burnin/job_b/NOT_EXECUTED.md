# Job B — not executed

The supervised burn-in's batch rule requires stopping immediately if a job produces a
legitimate non-`READY` result, and forbids proceeding to the next job when that happens.

Job A reached `decision_required` (reviewer verdict `changes_required`, adjudicated
`changes_required`) rather than `ready_for_approval`. That is a legitimate engineering
outcome, not an infrastructure defect, and it is a stop condition under the batch rules
the CEO set for this burn-in.

Job B (`req-engineering-test-section-numbering`, capsule `company-engineering-execution`)
was selected and passed dry deterministic-intake validation before execution began (see
the parent `company_os_supervised_burnin.md` report), but no real work order, packet, or
runner session was ever created for it. It was never submitted to
`python -m company.engineering request`, so it holds no work order id, no packet, no
authority grant, and no telemetry. Nothing in this directory should be read as execution
evidence.
