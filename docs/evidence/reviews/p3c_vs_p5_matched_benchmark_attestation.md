# Independent review — P3C vs P5 matched real-work benchmark

**Verdict: PASS**, for the scoped claim below and for no wider one.

| | |
|---|---|
| Record reviewed | `docs/evidence/project_factory_repository_architecture_v1/p3c_vs_p5_matched_benchmark/` |
| Evidence branch HEAD reviewed | `19dbdb35836323015465784176ef6bf4b92ae0a3` |
| Manifest digest read | `984ac2065c95b904b7b447375aa9a20c645b4b0f59eab5eb0a98462f09866280` |
| Manifest digest recomputed | identical |
| Reviewed on | 2026-09-23 |
| Reviewer | `software_review_engineer` |
| Work order | `wo-p3c-vs-p5-benchmark-attestation` |
| Benchmark rerun | none — no model session of either arm was spent |

This attestation is the review the benchmark record itself reports it could not
obtain. Its section *Independent review — attempted, structurally blocked*
records that intake returned `decision_required` because no capsule owned any
`docs/` path, and concludes: "this benchmark is NOT approved and claims no
approval. It is a request to be read." That blocker is now closed, by a capsule
that owns the attestation surface this file sits in and owns no evidence record,
so the record under review remained outside every authorized path while it was
being reviewed.

## The claim this review adjudicates

> P5 reduces provider-equivalent monetary cost for this matched task while
> preserving accepted quality.

**Supported.** The evidence establishes it for this task, on this environment,
at n = 2 per arm, and establishes nothing beyond it.

## What was verified, and how

Every headline number was re-derived from the raw accounting files by a code
path written for this review, not by rerunning the record's own verifier. The
derivation and its output are reproducible from the five files under
`accounting/`.

| Claim in `RESULT.md` | Recomputed | Agrees |
|---|---|---|
| whole-task cost −46.47% ($0.8723 → $0.4670) | −46.47% | yes |
| cost ranges do not overlap | challenger `[0.30069, 0.63330]`, control `[0.69686, 1.04782]` | yes |
| developer cost −69.33% | −69.33%, ranges disjoint | yes |
| reviewer cost +9.11%, not established | +9.11%, ranges overlap | yes |
| as-spent parity −0.07% including the void | −0.07% | yes |
| 10 distinct provider sessions, none double counted, none omitted | 10 distinct session UUIDs; per-arm session counts equal the claimed `paid_sessions` | yes |
| developer + reviewer sum to the whole-task total | exact on all five arms, to floating-point identity | yes |
| cache read, cache creation, output, turns: not established | all four ranges overlap | yes |

**Matched-fields proof.** `request_control.json` and `request_challenger.json`
were compared field by field. They differ in exactly two fields, `request_id`
and `authorized_branch`, as the manifest asserts. All five intake records derive
the same capsule, the same single authorized path, the same required test, the
same reasoning-class ceiling `D` and the same `consumer` profile, so the task
contract is genuinely matched and not merely described as matched.

**Adaptive routing.** The downshift is recorded as `applied: true` with
`veto_reasons: []` on all three P5 attempts, and the control arm carries no
routing record at all, which is consistent with the manifest's statement that
the economy tier exists only on P5. The developer ran `haiku` on every P5
attempt and `sonnet` on every control attempt; the reviewer ran `sonnet` on all
five. `doctor_*.json` shows `reviewer_model: ""`, corroborating that no model
was pinned by the operator.

**The void attempt.** Reported in full, in its own document and its own
accounting file, and included in the as-spent total. Its exclusion from the
matched comparison is reasoned rather than asserted: its reviewer brief carried
the rejected receipt outcome, and its reviewer cost is $0.5738, the highest
reviewer figure anywhere in the record, which is direct evidence that the
reviewer stage was in fact confounded.

**Post-freeze modification.** The disclosed redaction was checked against git.
The manifest blob is byte-identical at the freeze commit `2dc319b` and at the
evidence HEAD, so its recorded sha256 still holds. The two `raw/doctor_*.json`
captures differ by exactly ten lines, all of them operator-absolute paths
replaced by placeholders. No measured value changed. The disclosure is accurate.

**Semantic equivalence.** Verified against the commits rather than the prose.
Both controls produced blob `f6bddace`, byte-identical. One P5 run differs from
the control by a single comment word. The other is the superset discussed below.

## On "nothing else is broadened"

The record raises this concern against itself and resolves it more harshly than
the evidence requires. Its account is that P5 challenger 1 produced a strict
superset of the control's change, 22 insertions against 13, and that "the
controls proved those extra edits unnecessary", recording it as variability in
the economy-tier developer's output discipline.

Inspecting the two extra edits directly:

1. an added assertion that `tests/test_company_review_separation.py` appears in
   `usage.untouched_paths`, immediately beside the existing assertion for the
   first test file;
2. a fixture `scope` tuple extended to include that same second test file.

Both are inside the one authorized path. Neither substitutes a containment,
subset, unordered or partial assertion for an exact one, so acceptance criterion
3 is not touched. Both are consequences of the very change the objective names —
the capsule now declaring a second semantic test — so they fall inside criterion
2's "expectations that change because" clause rather than outside it.

"The controls proved those extra edits unnecessary" is not what the controls
proved. They proved the suite is green without them. A defensible reading is
that the P5 run was more complete and the controls under-updated.

This does not change the verdict, and it is recorded here rather than as a
required correction to the frozen record: a record that judges itself more
strictly than its evidence demands does not overclaim, and overclaiming is what
this review exists to catch. **No correction to the frozen bytes is required.**

## What this review does **not** find established

These are recorded as explicitly as the finding, because the record's own
limitations section asks that they be:

- **Token efficiency: NOT ESTABLISHED.** Cache read, cache creation, output and
  turns all have overlapping ranges. P5's means are *higher* on all four. The
  record states this plainly — "It is not a win on token consumption" and "P5
  buys its saving by moving routine developer work to a cheaper model, not by
  doing less work" — and that statement is correct.
- **Subscription-plan quota: NOT MEASURED.** Cost here is provider-equivalent
  USD. The provider publishes no conversion to plan-usage percentage, and the
  record marks it `UNAVAILABLE`. Since P5 spends more tokens for less money, a
  quota that tracks tokens rather than dollars would not receive this saving.
  Nothing in the record claims otherwise.
- **Universal model superiority: NOT CLAIMED and NOT SUPPORTED.** One task, one
  reasoning class, one profile, n = 2 per arm.
- **Reviewer-stage effect: NOT ESTABLISHED.** Ranges overlap heavily.
- **Deterministic wall-time improvement: NOT CAUSALLY ATTRIBUTED.** The record
  separates the observation from the attribution and marks the repo-map cache's
  timing contribution `UNAVAILABLE`.

## Findings

| id | severity | finding |
|---|---|---|
| `f-verdict-omits-the-as-spent-figure` | advisory | The Verdict section leads with −46.47% and "no quality regression" and does not point to the as-spent parity or the disclosed superset. Both are fully disclosed further down, each under its own heading, so this is a reading-order concern rather than a concealment. A cross-reference in the Verdict would close it. |
| `f-exclusion-criterion-is-one-sided-by-construction` | advisory | The headline comparison excludes a paid P5 attempt and excludes no control attempt, because only P5 met the external fault. The manifest's own accounting rule says failed sessions count, and the as-spent table honours it, so the record is internally consistent — but the headline is conditional on an exclusion that could only ever have applied to one arm. |
| `f-run-numbering-conflicts-across-artifacts` | advisory | `RESULT.md` calls the accepted P5 runs "challenger 1" and "challenger 2", while `review/deterministic_verification.txt` uses "challenger1" for the voided attempt and `comparison/pooled_comparison.json` uses `challenger2`/`challenger3` for the accepted ones. Same words, different runs, one record. |
| `f-n-equals-2` | advisory | Range separation with two points per arm is a heuristic, not a significance test. The record says so in its first limitation, and the cost mechanism is independently known, which is why the direction is credible anyway. |
| `f-controls-proved-unnecessary-overstated` | advisory | See the section above. Self-penalizing rather than self-serving. |

No finding is `changes_required` and none is `blocking`.

## Scope of this attestation

It covers the frozen record listed above at evidence HEAD `19dbdb35`, and the
arithmetic, accounting completeness, matched-pair construction, routing
evidence, quality equivalence, exclusion rules, variance disclosure and claim
scope within it. It does not re-run the benchmark, does not extend to any other
task or environment, and is not an authorization to merge or integrate P5.
