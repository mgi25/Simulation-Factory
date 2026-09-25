# P6C — the authoring session's adversarial pass

## What this is, and what it is not

A pass over the P6C diff against every attack the package brief names, run
**in the session that wrote the code**. It is not the independent review the
brief requires and it is not an attestation: nothing was written to
`docs/evidence/reviews/`. The independent review is requested in
`independent-review-request.md` and has to be a separate top-level session,
because no session may start another agent in Bootstrap Mode (constitution
rule 2). Until that review returns PASS, P6C is not ready for production
integration.

Every item below was checked by running something - a test, the full suite,
the real-history replay - not by reading.

## What it found, and what was done

| # | found by | finding | resolution |
|---|---|---|---|
| A1 | full suite at `304cd3e` | `company/experience` imported `company.integration` to build P6B's graph; the gate is read by no other Company OS subsystem (`test_no_other_company_os_subsystem_imports_the_gate`) | P6C-3: the graph is supplied by the caller; `graph_state` built / not_supplied / failed; per-item `checked`; the runner always graph-checks with its own P6B map |
| A2 | full suite at `304cd3e` | the runner held the string constant `"merge"` (in its authority-key set), which `test_the_runner_holds_no_merge_deploy_or_publish_capability` forbids | P6C-3: the bare key dropped on both sides (`authorizes_merge` stays); item-key whitelists added to the reader, which is stronger than any blacklist |
| A3 | first real-history replay | 16 of 34 decisions abstained `incompatible_only`, most on `review_capability`, which splits all history at the 2026-09-21 review-separation policy change | P6C-3: `review_capability` is no longer a gate (the architecture part is `specialist_domain`); risk becomes one-sided. The before-state is kept in `replay-first-rule/` because the rule changed after seeing it |
| A4 | adversarial pass | an episode file edited on disk - projection changed, identity untouched - still decoded and could be served; pointer digests protect canonical records, not the projection | P6C-4: retrieval re-derives every candidate from its canonical records; a difference is `invalid` (`test_an_edited_episode_is_not_served_as_precedent`) |
| A5 | adversarial pass | a directory write scope containing owned subtrees was governed by no capsule, so could share none | P6C-4: `governing_scope` |
| A6 | adversarial pass | could experience files in the primary ranking move the runner's economy downshift? | no - it reads only failure-guided compiled spans; pinned (`test_experience_cannot_move_the_adaptive_model_gate`) |
| A7 | first replay | one capture `conflict` on real data | not a defect: one receipt was ingested into two state directories (`e2e-pilot`, `e2e-pilot-2`) whose validation recorded different reasons (one clone lacked a remote ref), so two canonical histories claim one attempt; the store kept the first and refused the second |
| A8 | full suite at `16d5a39` | `test_the_review_is_adjudicated_against_the_tree_the_work_happened_in` saw two reviews | environmental: the chunk ran ~5h52m wall-clock against 4m26s before (machine suspended mid-run) and a stage retry followed; the test passes in isolation, and the runner suite is re-run whole (see `full-suite-*.txt`) |

## The attack list, item by item

| attack | result |
|---|---|
| duplicated source of truth | projections are a verified cache (A4); CEO decisions joined at read time, not copied |
| outcome leakage | builder signature + AST name whitelist + disjoint field sets + whitelist check + recompute-from-work-order, all tested |
| post-hoc features | features come only from the work order and the attempt number |
| stale history as current | only `current` reaches precedents or warnings; stale/invalid are listed as history |
| whole-repo SHA | not used; unrelated change keeps `current` (tested) |
| stale scoped evidence accepted | residual R1: changed-file content is not anchored, by design |
| one episode, many ids | identity from canonical pointers; re-capture on a later day is idempotent (tested) |
| distinct attempts collapsing | packet attempt in the identity; correction-then-accept is two episodes of two classes (tested) |
| failure ranked as success | separate lists; a stronger failure is still only a warning (tested) |
| nearest match instead of abstain | rule-based floor, six abstention codes (tested per code) |
| opaque scoring | lexicographic key with named, reported components |
| text similarity as relevance | the query has no objective field; the retrieval module reads no `.objective` (tested) |
| read / write authority | section 9 of the README |
| suppressing required tests | tested on both sides |
| lowering risk / reasoning class | one-sided risk gate; model tier untouched (A6) |
| KnowledgeStore mutation | byte-compare of the records directory around capture and advice (tested) |
| estimated / counterfactual as observed | basis on every resource value; counterfactual refused in history; replay rows labelled |
| future leakage in replay | strict earlier-day rule, governance `before=`, per-decision base-commit views |
| import boundary | A1, A2; the runner imports no Company OS module; Company OS imports no runner module |
| missing/corrupt store as failure | exit 0 abstain on every internal error; runner absorbs every failure (tested) |
| overclaiming | no token or cost claim; README "What is not claimed" |
