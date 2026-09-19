# Company OS V1 — Operating State Record

Authoritative current operating-state record. This is not a re-review; the
full evidence and reasoning behind the classification below live in
`docs/company_os_v1_operational_readiness.md` (725 lines, unchanged) and are
not duplicated here.

Branch: `company-os-v1-state-c-activation`
Base: `company-os-v1-routine-eligibility-guard` @
`ebde58246b5b1eff268c89a5ebf7d837814f8f6e`
Plus (cherry-picked, documentation-only): the operational-readiness review
commit, `c8796ad9dae968081141f338e0ebc2ead19380b3`.

## Current operating state

**ROUTINE AUTONOMOUS ENGINEERING WITH CEO APPROVAL GATE**

State C is ACTIVE for eligible routine engineering only.

## Eligible work (State C scope)

Work qualifies for State C only if ALL of the following hold:

- LOW or MEDIUM risk
- reversible
- bounded authorized paths
- acceptance criteria available
- required tests available
- no CEO-reserved action
- no credential handling
- no explicit specialist domain
- no explicit reasoning escalation
- no security-sensitive redesign
- no governance-policy change
- no architecture rewrite
- no concurrency-critical redesign
- no breaking migration/schema/storage-format/wire-protocol/API-contract
  change
- STANDARD-tier classification

Anything outside this list is not eligible for State C and requires a
different, explicitly authorized route.

## What State C authorizes

CEO/operator submits an eligible work order
→ deterministic intake/routing
→ bounded execution context
→ one STANDARD developer session
→ required tests
→ one independent reviewer
→ integration gate
→ decision packet
→ STOP at `ready_for_approval` / `decision_required` / `blocked` / `failed`

## What State C does NOT authorize

- Company OS inventing work for itself
- automatic merge
- automatic deployment
- automatic publishing
- automatic release/tag creation
- automatic approval
- unlimited retries
- subagents
- silent strongest-tier escalation
- authority widening
- specialist/high-risk work
- Company OS integration into `main`

CEO/operator approval before merge remains mandatory.

**State C activation is an operator/CEO policy decision. It does not alter
the technical merge/deploy/publish boundaries** — those boundaries are
identical between state B and state C (readiness review §4, §7); only the
per-job authorization step changes.

## Stop / fallback conditions

State C automatically falls back to CONTROLLED ROUTINE DOGFOOD (state B) —
and to PAUSED if the trigger indicates the technical boundary itself may be
compromised — on any of the following (reproduced from readiness review
§15, not materially rewritten):

1. Any authority violation actually occurs — a receipt reporting a change
   outside `may_write`, a protected-digest drift, or a HEAD found off the
   authorized branch. Fall back to PAUSED.
2. An automatic retry occurs when the consumer profile said none. Fall back
   to PAUSED.
3. The strongest tier is selected for a routine job without one of the four
   named routes (readiness review §4) being recorded on the work order.
   Fall back to B and re-audit `derive_routing`.
4. A routine job's developer cache-read or cost materially exceeds the
   measured historical range (568,012–1,913,995 cache-read units,
   $0.64–$1.94 job cost; broader stored-session average 2,584,057) without a
   scope explanation on the work order. Fall back to B.
5. Telemetry is marked unreliable on a routine job. Fall back to B until the
   specific disagreement is understood; do not average through it.
6. Two consecutive routine jobs require manual recovery (a checkpoint was
   needed, a lease had to be reclaimed, a receipt was rejected for a reason
   other than a clean scope refusal). Fall back to B.
7. Reviewer and gate disagree in a way the current lifecycle states cannot
   represent (i.e., neither `ready_for_approval`, `decision_required`, nor
   `blocked` describes the outcome). Fall back to PAUSED.
8. The canonical branch's ancestry diverges unexpectedly (a force-push, a
   rewrite, or a commit on `company-os-v1-bootstrap` that
   `git merge-base --is-ancestor` would not predict). Fall back to PAUSED
   immediately.
9. Protected governance changes outside an authorized work order. Fall back
   to PAUSED.
10. GitHub branch protection is still absent 30 days after the readiness
    review is accepted. Not an immediate trigger, but a standing condition —
    its continued absence should be revisited rather than forgotten once
    operation begins.

## Status

- Activated: 2026-09-19
- First real autonomous job run: not yet — this milestone activates State C
  but does not consume it. The first State-C job is a separate, subsequent
  decision.
- `main` integration: not authorized by this record.
