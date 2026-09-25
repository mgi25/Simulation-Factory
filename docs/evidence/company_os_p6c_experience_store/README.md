# P6C — Experience Store: evidence

Branch `p6c-experience-store-v1`, from `origin/main`
`4fd5fafa92767a83afb966c9a2210fdb016fc28d`. Implementation frozen at
`16d5a39cc9d1230f82301850b9195322300b7fd1`; later commits touch only this
directory.

| commit | what |
|---|---|
| `de13127` | P6C-1: `company/experience` - episodes, store, capture, scoped validity, retrieval, advice, replay, CLI; capsule `company-experience-store` |
| `304cd3e` | P6C-2: the external runner consumes the advisory as navigation only |
| `e1e7583` | P6C-3: never import the gate; one-sided risk; item whitelists in the reader (found by the full suite and the first replay) |
| `16d5a39` | P6C-4: serve an episode only while its records still derive it (found by the authoring session's adversarial pass) |

Every number below the "Measured" heading comes from a generated file in this
directory. Nothing measured is typed into this README.

## 1. What already existed, and what P6C adds

Inventory of canonical facts before P6C (all under one caller-supplied state
directory, all append-only via `company.runtime.state_paths`):

| fact | canonical record | writer |
|---|---|---|
| work-order identity, objective, write/read scope, forbidden paths, required tests, capabilities, risk, reasoning ceiling, specialist domain, profile, attempts, capsule context refs | `EngineeringWorkOrder` (`engineering/work_orders/`) | intake |
| task classification, routing, context manifest | `SessionPacket` (`execution/packets/`) - reasoning class, employee, context refs, context fingerprint | `prepare_developer_session` |
| authority | `ExecutionAuthoritySnapshot` (`execution/authorities/`) | adapter |
| context expansion | requests/decisions (`execution/context_expansions/`) | adapter |
| files changed, tests run, context refs used, provider/model/usage testimony | `SessionReceipt` (`execution/receipts/`) | adapter |
| validated outcome, context sources, expansion counts | `ResourceUsageRecord` (`resource_usage/`) | `finalise_attempt` |
| capabilities/capsules selected, files selected/read, tokens with `MeasurementSource`, cost, model, provider | `EfficiencyRecord` (`execution/efficiency/`) | `emit_execution_efficiency` |
| review outcome, findings, unanswered criteria | `EngineeringReview` + `ReviewerAttestation` (`engineering/reviews/`, `attestations/`) | `record_review` |
| gate outcome | `GateVerdict` (`engineering/gate_verdicts/`) | `record_gate` |
| lifecycle, attempts, corrections, **links between all of the above** | `EngineeringJob` transitions' `evidence_refs` (`engineering/jobs/`) | orchestrator |
| CEO decision | `CEODecision` (`engineering/decisions/`) | `record_decision` |
| handoffs | `HandoffArtifact` | `finalise_attempt` |
| curated learnings | `knowledge/company_os/records/` | a person, explicitly |

What did **not** exist: any index across work orders, any notion of a
settled attempt as a unit, any decision-time/outcome split, any scoped
record of the repository state an attempt depended on, and any retrieval.

## 2. The semantic boundary

**An experience episode = one settled developer attempt, indexed.** It is a
join over the records above, not a copy of them:

| episode section | source | copied because a pointer is insufficient |
|---|---|---|
| `evidence` | pointers + byte digests | (is the pointer) |
| `features` | work order | frozen decision-time snapshot; retrieval and training rows may read only this; recomputable while the work order decodes (`verify_features`) |
| `action` | packet | what went out, not a re-plan |
| `outcome` | receipt, usage record, review, gate, expansions, job | five records joined into one comparable shape |
| `resources` | efficiency record + receipt usage, each value with its basis | one shape with explicit basis; `None` stays `None` |
| `provenance` | capsule store + files at capture | **cannot be recomputed later at all** - it describes a repository that has since moved |

Not copied: the CEO decision (joined at read time, `capture.governance_facts`),
the objective text (unused by retrieval; the pointer suffices), transcripts,
review prose beyond one 200-character line per finding.

A projection is only served while the canonical records still derive it
(`capture.rederivation_problems`, P6C-4): it is a verified cache, not a
second source of truth. The one exception - a record today's decoder refuses -
is covered by the pointer digests proving those bytes are the ones captured.

Two historical work orders in this repository no longer decode under the
current `EngineeringWorkOrder` (pre-profile `max_developer_attempts: 3`
against the consumer ceiling of 1). That is why the snapshot exists, and why
capture refuses them (`work_order_undecodable`) rather than guessing.

## 3. Schema and identity

`company/experience/model.py`. Versions: episode 1, features 1, action 1,
outcome 1.

- `experience_id = fingerprint{schema, work_order_id, work_order_fingerprint,
  packet_fingerprint, packet_attempt, receipt_fingerprint}` - canonical
  pointers only. Same attempt from any machine, any day, any copy of the
  state directory: same id. Different packet attempt: different id.
- `content_fingerprint()` excludes `provenance` and `source` (when/where it
  was indexed). The store keeps the first capture; identical content is
  idempotent; different content is `ExperienceConflict`, nothing written.
- One `O_EXCL` file per identity: `<state>/experience/episodes/<id>/000001.json`
  via `state_paths.create_json_bytes_at_sequence`. No update, no delete, no
  database.

An evidence-format re-submission (a receipt refused for its report shape that
did not move the job) is part of the same developer attempt: capture counts it
and joins the receipt that *did* move the job, named by the job's own
`developing -> testing` transition together with its usage record. That
transition-linked join is exact; pairing usage records by position is what
carried-forward finding 5 warns about, and it is not used.

## 4. Decision time and outcome

`decision_features(order, *, attempt)` receives the work order and an integer
and nothing else. `tests/test_company_experience_store.py` asserts its
signature, that the only names its body reaches are those two and local
plumbing, that `DECISION_TIME_FIELDS` and `OUTCOME_FIELDS` are disjoint, that
`assert_decision_time_only` refuses any non-declared key (a whitelist), and
that stored features recompute exactly from the work order.

Capsule ownership and import-graph neighbourhood are **query-time signals**,
computed for both sides from today's repository, never stored as features:
computing them at capture would carry the outcome of any attempt that changed
them.

`training.training_row` is the shape a future decision model would read:
`inputs.features` (checked) and `labels` (action, outcome, resources, classes).
No model field is filled; `recommendation.recorded` is `false` because no
recommender existed when any historical attempt was decided.

## 5. Observed, estimated, counterfactual

`EvidenceBasis`: `observed`, `estimated`, `counterfactual`, `unavailable`
(maps the existing `MeasurementSource`). `ObservedOutcome` has no basis field
because it can hold only observations. `ResourceObservation` refuses
`counterfactual` in history, `observed` without a value, `unavailable` with
one. Counterfactual values appear only in `Measurement`s in analysis output -
every replay suggestion is one.

## 6. Settledness and precedent classes

Settled = the job has left the attempt's cycle (`planning`,
`ready_for_approval`, `decision_required`, `blocked`, `closed`, `failed`).
`testing`/`reviewing`/`gate` are waits and are refused `not_settled`.

| class | when | may be |
|---|---|---|
| `accepted` | recorded accepted, review pass, gate ready, parked ready/closed, no failing test | precedent |
| `correction` | any observed negative verdict; or accepted and later rejected / sent back by the CEO or moved off readiness | a warning, never scored as success |
| `incomplete` | anything else (no receipt, no review, stopped session) | history only |

Governance only ever downgrades.

## 7. Scoped staleness

`repository.evaluate_validity`: `current` / `stale` / `invalid`.

- capsule contract digest over the governing fields (not prose) - changed: stale;
  gone or no longer in force: invalid;
- path governance (which in-force capsules own or declare each anchored path) -
  moved: stale;
- structure (top-level names + imports) of files the attempt read without
  changing - moved: stale; body/comment edits: not;
- anchored path gone, canonical record changed or missing, projection not
  re-deriving, capsule store unreadable: invalid.

`repository_commit` is recorded and used for nothing: a whole-repository
anchor would make every episode stale on any unrelated commit.

## 8. Retrieval, ranking, abstention

`company/experience/retrieval.py`. The objective text is never read.

- **Gates** (incompatible, never scored): precedent risk below the task's
  (one-sided); reasoning-class ceiling differs; specialist domain differs.
- **Floor**: accepted precedent must share a governing capsule and have
  changed a file the task may write now; a correction must share a capsule and
  a writable target or required suite.
- **Rank**: lexicographic on writable targets, shared required suites,
  P6B import links (when a graph is supplied), shared capsules; then recency;
  then id. Each component is reported with its members.
- **Abstain**: `no_history`, `experience_unavailable`, `no_match`,
  `incompatible_only`, `stale_only`, `correction_only`.

## 9. Learning never creates authority - the proof

| cannot | enforced by | test |
|---|---|---|
| add a read path | every file/test suggestion must pass today's read grant (`advice.read_refusal`), then the runner's envelope (`experience.revalidate`) | `test_an_unauthorized_historical_file_is_refused`, `test_history_cannot_expand_the_read_scope`, `test_an_empty_read_scope_grants_nothing_whatever_history_says`, `test_revalidation_keeps_only_what_this_envelope_may_read`, `test_a_denied_read_outranks_history` |
| add a write path | no write vocabulary in the advisory; the runner never gives it to `authorization.py` | `test_the_advice_carries_no_authority_vocabulary_at_any_depth`, `test_prior_experience_reaches_the_briefing_as_navigation_only` (envelope unchanged) |
| smuggle authority in any field | `AUTHORITY_KEYS` walk on both sides + item-key whitelists in the reader | `test_an_injected_authority_field_is_refused_wherever_it_hides[*]`, `test_authority_vocabulary_anywhere_in_an_advisory_is_refused[*]`, `test_an_advisory_carrying_authority_is_dropped_whole` |
| skip or replace a required suite | suggestions exclude required suites; no field can remove one | `test_history_cannot_skip_or_replace_a_required_suite`, `test_a_required_test_is_never_offered_and_an_unreaching_test_is_refused` |
| shrink gate requirements | the gate never reads experience | `test_the_gate_and_the_engineering_loop_never_read_experience` |
| lower risk / reasoning class | one-sided risk gate; the runner's model downshift reads only compiled spans | `test_a_risk_class_cannot_be_lowered_by_precedent`, `test_experience_cannot_move_the_adaptive_model_gate` |
| bypass review separation or the gate | nothing in `engineering`, `integration`, `runtime`, `efficiency`, `dashboard`, `delegation` imports it | `test_nothing_else_in_company_os_depends_on_the_experience_store` |

## 10. The real execution path

```
runner developer stage
  -> python -m company.experience suggest --work-order WO --state-dir S --repo-root R
       captures every settled attempt in S (idempotent), retrieves, revalidates, emits the advisory
  -> ExperienceAdvice.parse (strict)  -> revalidate(envelope, repo_map)
  -> surviving files rank after authorized paths, before text-query guesses
  -> bounded "Prior experience" block in the developer instructions
  -> experience-advice.json, experience.json, resources.json["experience"] in the stage dir
```

Any failure on that path is recorded and the stage runs exactly as before
(`test_a_failing_experience_call_changes_nothing`). `--no-experience-advice`
switches it off.

The import-graph check: `company/experience` may not import the gate that
owns P6B's graph (P6C-3), so `suggest` leaves that check to the consumer and
says so per item (`checked`); the runner always performs it with its own P6B
map built from the task worktree. A caller that supplies a graph
(`RepositoryView(graph_builder=...)`) gets it performed in Company OS; the
replay harness does.

## 11. Experience is not knowledge

The experience store holds operational history; the knowledge store holds
curated semantic claims. No experience module imports a knowledge writer; no
capture or advisory run changes a byte under `knowledge/company_os/records/`;
an episode never becomes a Fact, Decision or FailureLearning by being stored.

## 12. Resources and ContextCache

`ResourceUsageRecord` is **referenced, not migrated** (finding 5 stays open):
capture reaches it through the job's own link instead of by position, which
closes the one place P6C needed a stable join, without a schema migration.
`ContextCache` is untouched (finding 6 stays open): same-task reread avoidance
and cross-task precedent are different problems.

## Measured

Generated files:

- `replay-summary.md` - rendered tables; `replay-results.json` - every row;
  `replay-validity-today.json` - every captured episode against today's
  checkout; `replay-corpus.json` - digests of every input record file.
- `replay-first-rule/` - the first replay, before P6C-3 changed the
  compatibility rule; kept because the change was made after seeing it.
- `validation-summary.json` - every validation headline (full-suite
  classification, focused suites, required-suite set, both gate verdicts),
  derived from the archived files below by `verify_evidence.py --write`.
- `required-suites.json` (derived on the branch), `suite-evidence-branch.json`
  and `suite-evidence-post-merge-modelled.json` (the 47 required suites, from
  JUnit), `gate-report-branch.json` and `gate-report-post-merge-modelled.json`,
  `full-suite-per-file-16d5a39.json`, `runner-suite-rerun-16d5a39.json`,
  `full-suite-failures-16d5a39.txt`, `full-suite-failures-304cd3e.txt`,
  `baseline-failures-main.txt`, `full-suite-run.txt`.

`python docs/evidence/company_os_p6c_experience_store/verify_evidence.py
[--projects <dir>]` recomputes every replay and validation number from these
files (and, with `--projects`, re-digests the historical inputs) and exits
non-zero on any disagreement.

The gate result on the branch is **BLOCKED** and that is the real result: the
three `test_this_branch_changed_no_race_fight_or_v30_code` research guards
refuse any branch that touches `tools/` until it is `main`. The modelled
post-merge result - a scratch clone with `origin/main` repointed at `16d5a39`,
which is what a fast-forward merge would make it - is supporting evidence
only, not production proof.

The chunked full run at `16d5a39` was suspended mid-way (about six hours of
wall clock against eighteen minutes for the same chunks at `304cd3e`), and one
runner test saw a retried stage; the runner suite was re-run whole at the same
SHA and passed. Both results are archived.

Replay method: every historical developer attempt in 21 state directories
(snapshot-copied, never written), queried in decision order with only
episodes settled **strictly before** its decision day, each episode anchored
at its own base commit and each query judged against its own base commit,
governance joined as of the decision day. Run twice; the replay fingerprint
(excluding latency) must match.

### What is not claimed

No provider-token or monetary saving: no paid session ran, and every replay
suggestion is counterfactual. Not model accuracy. The corpus is small and
clustered - most history concerns one capsule, and five decisions are re-runs
of one matched benchmark task, which is why top-1 file overlap is high where
precedent exists. The historical work orders predate read authority, so the
fail-closed read rule refused every historical file suggestion: the replay
measures retrieval and abstention, not suggestion usefulness in a session.

## Residual findings (P6C)

- **R1.** A changed file is anchored by existence and governance, not content:
  its content legitimately differs before and after integration and capture
  cannot tell which side it is on. A precedent whose changed file was later
  rewritten in place stays `current`; its suggestions are still revalidated
  item by item, and no historical content is ever replayed.
- **R2.** Settled includes `ready_for_approval`; a later CEO decision is joined
  at read time and only downgrades. A replay without the decision's date
  would over-count accepted precedent; the replay passes `before=`.
- **R3.** Warnings render historical review summaries into a developer
  prompt, framed as history and cut to 240 characters. Same trust level as the
  runner's existing prior-findings block; not sanitised beyond that.
- **R4.** Runner-era token counts are carried with the basis the efficiency
  record recorded (`provider_reported`), although the runner telemetry
  defect (session-total cost, final-segment tokens) is known.
- **R5.** Chronology is by day. Same-day precedent is excluded even when it
  probably settled first.
- **R6.** An attempt that edits a capsule's own contract reads as stale once
  that edit is integrated.

## Carried-forward correctness register

1. nested capsule co-selection / forbidden-over-authorized conflict - open
2. no explicitly named superseded workflow state - open
3. external-runner import-guard breadth - open (P6C added a runner module and
   kept the text guard's strings out of it; the guard itself is unchanged)
4. gate reports not archived automatically - open
5. ResourceUsageRecord not migrated to ExecutionEvidence - open; P6C avoids
   the positional join by reading the job's own link, no migration
6. ContextCache not wired into build_execution_context - open
7. compressed transient/synthesized artefacts may not be recoverable - open
8. third-party test dependency declarations not globally enforced - open
9. dependency closure cutoff does not report truncation - open
10. unused DependencyRelation enum members - open
11. satisfying/ outside gate-scanned/governed roots - open

None is claimed closed.
