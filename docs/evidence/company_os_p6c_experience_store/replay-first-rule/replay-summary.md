# P6C offline replay - generated, do not edit

Rendered by `replay_harness.py` from `replay-results.json`, `replay-validity-today.json` and `replay-corpus.json`.

- sources: 21 state directories, 721 record files, 1778096 bytes
- capture: `{"captured": 24, "class:accepted": 17, "class:correction": 7, "refused:conflict": 1, "refused:no_job": 1, "refused:not_settled": 9, "refused:work_order_undecodable": 2}`
- episodes captured: 23
- repeat run produced the same replay fingerprint: **True**
- historical trees that could not be materialised or read: 0

## Leave-future-out replay

| measure | value |
|---|---|
| decisions | 34 |
| replayed | 34 |
| not_replayed | 0 |
| with_eligible_history | 32 |
| precedent_found | 10 |
| abstained | 24 |
| abstentions_by_code | {"incompatible_only": 16, "no_match": 8} |
| rows_with_file_suggestions | 0 |
| rows_where_a_suggested_file_was_changed | 0 |
| suggested_files_total | 0 |
| suggested_files_later_changed | 0 |
| changed_files_in_rows_with_suggestions | 0 |
| rows_with_warnings | 7 |
| rows_with_warnings_that_ended_as_corrections | 1 |
| candidates_excluded_by_reason | {"below_floor": 197, "incompatible": 156, "not_yet_settled": 401} |
| suggestions_refused_total | 17 |
| suggestions_refused_by_read_authority | 17 |
| same_day_episodes_excluded_total | 138 |
| advice_chars_max | 5211 |
| advice_chars_median | 748 |
| eligible_history_bytes_max | 572610 |
| latency_ms_median | 33.377 |
| latency_ms_max | 78.689 |

## Per decision

| decided | work order | attempt | eligible | status | top-1 | warnings | changed later | actual |
|---|---|---|---|---|---|---|---|---|
| 2026-09-18 | wo-ceo-2026-09-18-attempts-remaining-consumer | 1 | 0 | abstain (no_match) |  |  |  | accepted |
| 2026-09-18 | wo-ceo-2026-09-18-reviews-completed-repoexpl | 1 | 0 | abstain (no_match) |  |  |  | accepted |
| 2026-09-19 | wo-blocked-attempts-v3b-2 | 1 | 2 | precedent | wo-ceo-2026-09-18-attempts-remaining-consumer |  |  | accepted |
| 2026-09-19 | wo-req-ceo-page-attempts-remaining | 1 | 2 | abstain (incompatible_only) |  |  |  | accepted |
| 2026-09-19 | wo-req-repo-exploration-v2-blocked-count-2 | 1 | 2 | precedent | wo-ceo-2026-09-18-attempts-remaining-consumer |  |  | accepted |
| 2026-09-20 | wo-req-auth-migration-classifier-ambiguity | 1 | 5 | abstain (incompatible_only) |  |  |  | correction |
| 2026-09-20 | wo-req-auth-migration-classifier-ambiguity | 1 | 5 | abstain (incompatible_only) |  |  |  | correction |
| 2026-09-20 | wo-req-auth-migration-correction-01 | 1 | 5 | abstain (incompatible_only) |  |  |  | accepted |
| 2026-09-20 | wo-req-review-routing-probe | 1 | 5 | abstain (incompatible_only) |  |  |  | not_captured |
| 2026-09-20 | wo-wo-gate-architecture-subsystem_ownership_bounded | 1 | 5 | abstain (no_match) |  |  |  | accepted |
| 2026-09-21 | wo-capsule-ownership-semantic-review | 1 | 8 | precedent | wo-wo-gate-architecture-subsystem_ownership_bounded |  |  | accepted |
| 2026-09-21 | wo-delegation-planning-test-ownership | 1 | 8 | abstain (no_match) |  |  |  | accepted |
| 2026-09-21 | wo-delegation-planning-test-ownership-v2 | 1 | 8 | abstain (no_match) |  |  |  | accepted |
| 2026-09-21 | wo-token-efficiency-v4-p2-benchmark-contract-correction | 1 | 8 | abstain (incompatible_only) |  |  |  | accepted |
| 2026-09-21 | wo-token-efficiency-v4-p2-review-test-ownership-v2 | 1 | 8 | abstain (no_match) |  |  |  | correction |
| 2026-09-21 | wo-token-efficiency-v4-p3-benchmark-contract-correction | 1 | 8 | abstain (incompatible_only) |  |  |  | correction |
| 2026-09-21 | wo-token-efficiency-v4-p3c-benchmark-contract-correction | 1 | 8 | abstain (incompatible_only) |  |  |  | accepted |
| 2026-09-21 | wo-token-efficiency-v4-review-separation-yaml-dependency | 1 | 8 | abstain (incompatible_only) |  |  |  | accepted |
| 2026-09-23 | wo-p3c-vs-p5-benchmark-attestation | 1 | 16 | abstain (no_match) |  |  |  | not_captured |
| 2026-09-23 | wo-p3c-vs-p5-benchmark-attestation | 1 | 16 | abstain (no_match) |  |  |  | not_captured |
| 2026-09-23 | wo-p5-evidence-reviewability-correction | 1 | 16 | precedent | wo-capsule-ownership-semantic-review | wo-delegation-planning-test-ownership, wo-token-efficiency-v4-p2-review-test-ownership-v2 |  | not_captured |
| 2026-09-23 | wo-p5-evidence-reviewability-correction | 1 | 16 | precedent | wo-capsule-ownership-semantic-review | wo-delegation-planning-test-ownership, wo-token-efficiency-v4-p2-review-test-ownership-v2 |  | not_captured |
| 2026-09-23 | wo-p5-evidence-reviewability-v1 | 1 | 16 | abstain (incompatible_only) |  |  |  | correction |
| 2026-09-23 | wo-p5-evidence-reviewability-v1 | 1 | 16 | abstain (incompatible_only) |  |  |  | correction |
| 2026-09-23 | wo-req-token-efficiency-v4-p3c-control | 1 | 16 | precedent | wo-token-efficiency-v4-p2-benchmark-contract-correction | wo-token-efficiency-v4-p3-benchmark-contract-correction |  | accepted |
| 2026-09-23 | wo-req-token-efficiency-v4-p3c-control-b | 1 | 16 | precedent | wo-token-efficiency-v4-p2-benchmark-contract-correction | wo-token-efficiency-v4-p3-benchmark-contract-correction |  | accepted |
| 2026-09-23 | wo-req-token-efficiency-v4-p5-challenger | 1 | 16 | precedent | wo-token-efficiency-v4-p2-benchmark-contract-correction | wo-token-efficiency-v4-p3-benchmark-contract-correction |  | correction |
| 2026-09-23 | wo-req-token-efficiency-v4-p5-challenger-b | 1 | 16 | precedent | wo-token-efficiency-v4-p2-benchmark-contract-correction | wo-token-efficiency-v4-p3-benchmark-contract-correction |  | accepted |
| 2026-09-23 | wo-req-token-efficiency-v4-p5-challenger-c | 1 | 16 | precedent | wo-token-efficiency-v4-p2-benchmark-contract-correction | wo-token-efficiency-v4-p3-benchmark-contract-correction |  | accepted |
| 2026-09-24 | wo-p5-read-authority-correction-b | 1 | 22 | abstain (incompatible_only) |  |  |  | not_captured |
| 2026-09-24 | wo-p5-read-authority-evidence-suite | 1 | 22 | abstain (incompatible_only) |  |  |  | not_captured |
| 2026-09-24 | wo-p5-read-authority-fingerprint | 1 | 22 | abstain (incompatible_only) |  |  |  | not_captured |
| 2026-09-24 | wo-p5-read-authority-fingerprint-b | 1 | 22 | abstain (incompatible_only) |  |  |  | not_captured |
| 2026-09-24 | wo-p5-read-authority-v1 | 1 | 22 | abstain (incompatible_only) |  |  |  | correction |

## Every captured episode, judged against today's checkout

counts: `{"current": 4, "stale": 19}`

| work order | attempt | class | validity | first reason |
|---|---|---|---|---|
| wo-ceo-2026-09-18-attempts-remaining-consumer | 1 | accepted | stale | capsule company-engineering-execution contract changed since capture |
| wo-ceo-2026-09-18-reviews-completed-repoexpl | 1 | accepted | stale | capsule company-engineering-execution contract changed since capture |
| wo-blocked-attempts-v3b-2 | 1 | accepted | stale | capsule company-engineering-execution contract changed since capture |
| wo-req-ceo-page-attempts-remaining | 1 | accepted | stale | capsule company-engineering-execution contract changed since capture |
| wo-req-repo-exploration-v2-blocked-count-2 | 1 | accepted | stale | capsule company-engineering-execution contract changed since capture |
| wo-req-auth-migration-classifier-ambiguity | 1 | correction | stale | capsule company-engineering-execution contract changed since capture |
| wo-req-auth-migration-correction-01 | 1 | accepted | stale | capsule company-engineering-execution contract changed since capture |
| wo-wo-gate-architecture-subsystem_ownership_bounded | 1 | accepted | current |  |
| wo-capsule-ownership-semantic-review | 1 | accepted | current |  |
| wo-delegation-planning-test-ownership | 1 | accepted | current |  |
| wo-delegation-planning-test-ownership-v2 | 1 | accepted | current |  |
| wo-token-efficiency-v4-p2-benchmark-contract-correction | 1 | accepted | stale | capsule company-engineering-execution contract changed since capture |
| wo-token-efficiency-v4-p2-review-test-ownership-v2 | 1 | correction | stale | capsule company-engineering-execution contract changed since capture |
| wo-token-efficiency-v4-p3-benchmark-contract-correction | 1 | correction | stale | capsule company-engineering-execution contract changed since capture |
| wo-token-efficiency-v4-p3c-benchmark-contract-correction | 1 | accepted | stale | capsule company-engineering-execution contract changed since capture |
| wo-token-efficiency-v4-review-separation-yaml-dependency | 1 | accepted | stale | capsule company-engineering-execution contract changed since capture |
| wo-p5-evidence-reviewability-v1 | 1 | correction | stale | docs/evidence/reviews/README.md is governed by company-evidence-review (was nothing) |
| wo-req-token-efficiency-v4-p3c-control | 1 | accepted | stale | capsule company-engineering-execution contract changed since capture |
| wo-req-token-efficiency-v4-p3c-control-b | 1 | accepted | stale | capsule company-engineering-execution contract changed since capture |
| wo-req-token-efficiency-v4-p5-challenger | 1 | correction | stale | capsule company-engineering-execution contract changed since capture |
| wo-req-token-efficiency-v4-p5-challenger-b | 1 | accepted | stale | capsule company-engineering-execution contract changed since capture |
| wo-req-token-efficiency-v4-p5-challenger-c | 1 | accepted | stale | capsule company-engineering-execution contract changed since capture |
| wo-p5-read-authority-v1 | 1 | correction | stale | capsule company-engineering-execution contract changed since capture |
