# Company OS experience store

Operational episode history for engineering: every settled developer attempt,
indexed from the canonical records the engineering loop already wrote, so a
later task can be told what similar work did - and abstain when nothing is
similar enough.

```
settled attempt ──capture──► episode (pointers + small projections)
current work order ──query──► accepted precedent | correction warnings | abstain
retrieval + current authority + current P6B graph ──advise──► bounded advisory JSON
```

| module | holds |
|---|---|
| `model` | the episode: decision-time features, chosen action, observed outcome, resources with basis, scoped provenance, derived identity |
| `store` | one `O_EXCL` file per identity; identical content idempotent, different content refused |
| `capture` | attempt cycles read off the job's own transition links; settledness; refusal codes; governance joined at read time |
| `repository` | the current repository view; capsule-contract, governance and structure anchors; CURRENT / STALE / INVALID |
| `retrieval` | compatibility gates, a rule-based support floor, a lexicographic rank with named components, abstention codes |
| `advice` | the one artifact this package emits: bounded, fingerprinted, advisory-only, authority vocabulary refused |
| `training` | the row shape a future decision model would read, with the decision-time check applied |
| `replay` | chronological leave-future-out replay over real state directories |

```
python -m company.experience capture --state-dir S --repo-root R
python -m company.experience suggest --work-order WO --state-dir S --repo-root R
python -m company.experience list    --state-dir S
python -m company.experience show    --experience-id ID --state-dir S
```

## The four lines that matter

1. **An episode is an index, not a copy.** Canonical records stay where they
   were written; an episode points at them with byte digests and carries only
   the projections retrieval needs.
2. **Features are decision-time only.** They come from the work order and the
   attempt number, through a function that cannot see an outcome.
3. **Learning never creates authority.** The advisory carries no authority
   vocabulary, every suggestion is re-checked against the task's current read
   grant and P6B's current graph, and nothing that decides authority,
   requirements or readiness imports this package.
4. **No precedent beats false precedent.** Incompatible, stale, failure-only
   and weak matches abstain, with a reason.

## Experience is not knowledge

`knowledge.company_os` holds curated claims - facts, hypotheses, decisions,
experiment and failure learnings - each a deliberate semantic act. This
package holds what happened. It never writes a knowledge record, and an
episode never becomes a Fact, a Decision or a FailureLearning by being stored.
Promoting a pattern seen here into knowledge is a separate, explicit act by
someone accountable for the claim.

Evidence: `docs/evidence/company_os_p6c_experience_store/`.
