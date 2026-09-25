# P6C independent review — request

**For:** a separate, top-level review session. Not the authoring session, and
not a subagent of it. The authoring session did not start this review: in
Bootstrap Mode no session may spawn another agent (constitution rule 2), so
the review has to be its own session.

**Subject:** branch `p6c-experience-store-v1`, frozen implementation
`16d5a39cc9d1230f82301850b9195322300b7fd1`, based on `origin/main`
`4fd5fafa92767a83afb966c9a2210fdb016fc28d`. Evidence commits after `16d5a39`
change only `docs/evidence/company_os_p6c_experience_store/`.

**Verdict to return:** `PASS`, `CHANGES_REQUIRED` or `FAIL`, with each
finding reproduced by a probe rather than argued from reading, and recorded as
an attestation under `docs/evidence/reviews/` (the surface
`company-evidence-review` owns).

## What P6C claims

1. An experience episode is an immutable index over canonical engineering
   records - pointers with byte digests plus small projections - captured
   deterministically from the records the loop already wrote.
2. Decision-time features come from the work order alone; outcomes,
   resources and governance never enter them.
3. Identity is derived from canonical pointers; identical content is
   idempotent; different content under one identity is refused.
4. Validity is scoped (capsule contracts, path governance, read-file
   structure), never a whole-repository commit; stale or invalid history is
   never offered as precedent.
5. Retrieval is structural, explainable, deterministic, and abstains when
   nothing is related enough; corrections are warnings, never success.
6. Learning never creates authority: the advisory carries no authority
   vocabulary, every suggestion is revalidated against the task's current
   read grant, and the runner revalidates again against its own envelope and
   P6B map; nothing that decides authority, requirements, routing or
   readiness reads the advisory.
7. The KnowledgeStore is never written.
8. Absent or corrupt experience degrades to "no advice", never to a failed job.

## The attack list (from the package brief) and where to aim

| attack | start here |
|---|---|
| duplicated source of truth | `company/experience/model.py` docstring table; `capture.rederivation_problems` |
| outcome leakage / post-hoc features | `model.decision_features` (signature), `assert_decision_time_only`, `verify_features` |
| stale history treated as current | `repository.evaluate_validity`; `retrieval.retrieve` (only `current` reaches precedents/warnings) |
| whole-repo SHA invalidating everything | `ScopeProvenance` (`repository_commit` informational only) |
| stale scoped evidence accepted | changed files are anchored by existence + governance only - **deliberate, see residual R1 in the README** |
| one episode, many ids / many attempts, one id | `ExperienceEpisode.identity`; capture over evidence-format re-submissions |
| failure ranked as success | `retrieval.retrieve` (separate lists), `capture.governed_class` (downgrade only) |
| nearest match instead of abstain | `retrieval._above_floor`, `ABSTENTION_CODES` |
| opaque scoring / text similarity | `Candidate.rank_key`; `ExperienceQuery` has no objective field |
| read / write authority from history | `advice.read_refusal`, `advice.AUTHORITY_KEYS`; `tools/engineering_runner/experience.py` (`parse`, whitelists, `revalidate`) |
| skipping required tests / lowering gate requirements | suggestions exclude required suites; `resolve_required_suites` has no experience input |
| lowering risk or reasoning class | `retrieval.incompatibilities` (one-sided risk); runner `_adaptive_developer_model` reads only compiled spans |
| KnowledgeStore mutation | `tests/test_company_experience_store.py::test_capture_and_advice_never_touch_the_knowledge_store` |
| estimated / counterfactual mixed with observed | `ResourceObservation`, `Measurement`, replay rows' `basis` |
| future leakage in replay | `replay.run_replay` (strict earlier-day rule, governance `before=`) |
| runner <-> Company OS import boundary | `company/experience` never imports `company.integration`; runner imports no Company OS module |
| missing/corrupt store as a hard failure | `__main__._suggest`; runner `_experience` |
| overclaiming savings | README "What is not claimed" |

## Commands

```
git fetch origin && git checkout 16d5a39
python -m pytest tests/test_company_experience_store.py tests/test_company_experience_retrieval.py -q
python -m pytest tests/test_company_external_engineering_runner.py tests/test_engineering_runner_execution_context.py -q
python -m pytest tests/test_external_engineering_runner.py -q -k "experience or adaptive_model_gate or advisory_carrying"
python -m company.integration required-suites --repo-root . --json        # expect 47, f5de72a66d79bb83
python docs/evidence/company_os_p6c_experience_store/replay_harness.py --projects <projects dir> --scratch <empty dir> --out <dir>
```

The replay reads the historical state directories under
`projects/project-archives/` and `projects/project-factory-company-state/`,
which are outside git; it copies them before reading and never writes into
them. Compare its `replay-results.json` with the committed one - the
`replay_fingerprint` excludes only wall-clock latency.
