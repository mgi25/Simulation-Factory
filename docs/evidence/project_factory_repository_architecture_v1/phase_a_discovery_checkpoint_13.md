# Phase A Discovery Checkpoint 13 — P2 benchmark intake selection conflict

Date: 2026-09-21

## Event

The first Token Efficiency V4 P2 matched benchmark request was valid JSON and reached deterministic Company OS intake, but intake refused before persisting a work order.

Observed refusal:

`the plan proposes writing outside the work order's authorized scope ... knowledge/company_os/capsules/seeds/company-engineering-execution.json is covered by forbidden rule knowledge`

Exit code: 2.

No model session was launched and no benchmark work order was persisted.

## Cause

The request's objective text included broad selection terms including `authority` and `runtime`.

Engineering intake selects up to three capsules from:

- subsystem/path signals;
- objective-derived capability tokens;
- explicit capsule hints.

The explicit `company-knowledge-capsules` hint does not mean "select only this capsule". The broader objective vocabulary allowed an additional capsule match whose `must_not_modify` surface included `knowledge/**`.

The resulting plan therefore contained an honest contradiction:

- the work-order ceiling allowed the exact capsule seed file;
- a selected capsule also forbade the broader `knowledge` surface.

Planning refused rather than choosing which authority to ignore.

## Decision

Do not weaken path-scope or planner enforcement.

Preserve the rejected benchmark request as evidence and issue V2 with:

- the same validated P2 base;
- the same two-file scope ceiling;
- the same acceptance criteria and constraints;
- a narrower objective sentence that describes only the metadata/test-list change and avoids unrelated authority/runtime selection terms;
- a fresh request id, worker branch and work-order id.

V2 request:

`req-token-efficiency-v4-p2-review-test-ownership-v2`

Before opening it in the real Repository Architecture state, run the full request/open-job path against a fresh temporary state directory. This deterministic dry run must show the intended capsule selection, exact two-file writable scope, consumer profile and no plan-scope conflict.

No canonical merge, model invocation, deployment or publishing is authorized.
