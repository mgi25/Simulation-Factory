"""Phase 4: each P6C invariant, the tests that pin it, and their outcome in the merged-tree run."""

import json
import sys
import xml.etree.ElementTree as ET

SP = sys.argv[1]
S, R, X, C = (
    "tests.test_company_experience_store",
    "tests.test_company_experience_retrieval",
    "tests.test_external_engineering_runner",
    "tests.test_engineering_runner_execution_context",
)
INVARIANTS = {
    "1 episodes index canonical records, not a second source of truth": [
        (S, "test_capture_follows_the_jobs_own_links_not_positions"),
        (S, "test_the_identity_is_derived_from_canonical_pointers_only"),
        (S, "test_a_changed_canonical_record_leaves_the_episode_unresolved"),
        (R, "test_an_edited_episode_is_not_served_as_precedent"),
    ],
    "2 decision-time features separate from outcome": [
        (S, "test_decision_time_and_outcome_fields_are_disjoint"),
        (S, "test_the_feature_builder_cannot_see_an_outcome"),
        (S, "test_an_outcome_smuggled_into_features_is_refused"),
        (S, "test_stored_features_recompute_exactly_from_the_work_order"),
        (R, "test_the_future_is_invisible_to_a_decision"),
    ],
    "3 observed / estimated / counterfactual provenance explicit": [
        (S, "test_history_refuses_a_counterfactual_measurement"),
        (S, "test_a_gap_cannot_be_written_as_a_measurement_or_a_guess_as_an_observation"),
        (S, "test_counterfactual_values_live_only_in_labelled_measurements"),
        (S, "test_missing_usage_telemetry_stays_unavailable_and_never_becomes_zero"),
        (S, "test_reported_provider_usage_is_observed_with_its_values"),
    ],
    "4 identical capture is idempotent": [(S, "test_duplicate_ingestion_resolves_to_the_same_identity")],
    "5 conflicting duplicate refuses overwrite": [
        (S, "test_a_conflicting_duplicate_is_refused_and_the_stored_episode_kept"),
        (S, "test_the_store_is_append_only_with_no_update_or_delete"),
        (S, "test_a_stored_id_that_disagrees_with_its_content_is_refused"),
    ],
    "6 stale history is not current precedent": [
        (R, "test_only_stale_experience_abstains_and_is_listed_as_history"),
        (S, "test_a_capsule_contract_change_makes_relevant_experience_stale"),
        (S, "test_a_governance_move_on_an_anchored_path_is_stale"),
        (S, "test_a_removed_path_or_retired_capsule_invalidates"),
        (S, "test_no_capsule_store_means_invalid_not_current"),
    ],
    "7 retrieval deterministic and explainable": [
        (R, "test_retrieval_and_advice_are_deterministic"),
        (R, "test_a_related_accepted_episode_is_precedent_and_says_why"),
        (R, "test_ties_break_by_recency_then_by_id"),
        (S, "test_scan_order_is_deterministic"),
        (R, "test_the_replay_is_leave_future_out_labelled_and_repeatable"),
    ],
    "8 weak / incompatible history abstains": [
        (R, "test_an_empty_store_abstains_with_no_history"),
        (R, "test_an_unrelated_task_abstains"),
        (R, "test_the_same_words_in_another_subsystem_abstain"),
        (R, "test_the_same_subsystem_under_a_different_risk_is_incompatible"),
        (R, "test_every_routing_input_must_match"),
        (R, "test_every_abstention_code_is_declared"),
    ],
    "9 corrections / failures are warnings, never success precedent": [
        (R, "test_only_failed_experience_never_becomes_success_precedent"),
        (R, "test_a_failure_with_stronger_signals_is_still_only_a_warning"),
        (S, "test_a_rejected_attempt_is_a_correction_and_never_accepted"),
        (S, "test_a_ceo_approval_keeps_accepted_and_never_promotes_a_correction"),
        (S, "test_a_ceo_rejection_downgrades_an_accepted_episode_without_rewriting_it"),
    ],
    "10 KnowledgeStore not mutated automatically": [
        (S, "test_capture_and_advice_never_touch_the_knowledge_store"),
        (S, "test_no_experience_module_can_write_a_knowledge_record"),
    ],
    "11 experience grants no authority": [
        (R, "test_history_cannot_expand_the_read_scope"),
        (R, "test_an_empty_read_scope_grants_nothing_whatever_history_says"),
        (R, "test_the_advice_carries_no_authority_vocabulary_at_any_depth"),
        (R, "test_an_injected_authority_field_is_refused_wherever_it_hides"),
        (R, "test_a_risk_class_cannot_be_lowered_by_precedent"),
        (R, "test_the_gate_and_the_engineering_loop_never_read_experience"),
        (X, "test_an_advisory_carrying_authority_is_dropped_whole"),
        (X, "test_experience_cannot_move_the_adaptive_model_gate"),
        (X, "test_prior_experience_reaches_the_briefing_as_navigation_only"),
    ],
    "12 missing / corrupt advice degrades to no advice": [
        (R, "test_a_broken_experience_store_degrades_to_no_precedent"),
        (R, "test_a_corrupt_episode_is_skipped_and_counted"),
        (S, "test_a_corrupt_record_costs_one_episode_and_never_the_scan"),
        (X, "test_a_failing_experience_call_changes_nothing"),
        (X, "test_a_malformed_advisory_runs_the_job_exactly_as_without_advice"),
        (X, "test_an_unforeseen_parser_or_revalidation_exception_is_absorbed"),
        (X, "test_a_failed_experience_write_is_no_advice_not_a_failed_run"),
        (X, "test_process_level_control_is_never_absorbed_as_missing_advice"),
        (C, "test_a_precedent_why_that_is_not_a_list_of_strings_is_refused"),
        (C, "test_warning_lines_that_are_not_a_list_of_strings_are_refused"),
    ],
    "13 current P6B graph / current authority revalidate historical suggestions": [
        (R, "test_revalidation_against_this_repositorys_own_p6b_graph"),
        (R, "test_a_test_that_no_longer_reaches_the_task_is_refused"),
        (R, "test_a_file_missing_from_the_current_graph_is_refused"),
        (R, "test_a_supplied_graph_that_fails_to_build_refuses_everything"),
        (R, "test_a_deleted_file_is_refused_even_when_history_used_it"),
        (R, "test_an_unauthorized_historical_file_is_refused"),
    ],
    "14 experience cannot reduce current required suites": [
        (R, "test_history_cannot_skip_or_replace_a_required_suite"),
        (R, "test_the_gate_and_the_engineering_loop_never_read_experience"),
    ],
}

outcomes: dict[tuple[str, str], list[str]] = {}
for case in ET.parse(f"{SP}/runs/merge/req.xml").getroot().iter("testcase"):
    base = case.get("name").split("[")[0]
    status = "failed" if (case.find("failure") is not None or case.find("error") is not None) else "skipped" if case.find("skipped") is not None else "passed"
    outcomes.setdefault((case.get("classname"), base), []).append(status)

report, ok = {}, True
for invariant, tests in INVARIANTS.items():
    rows = []
    for mod, name in tests:
        got = outcomes.get((mod, name))
        verdict = "NOT FOUND" if not got else ("passed" if set(got) == {"passed"} else "/".join(sorted(set(got))))
        ok &= verdict == "passed"
        rows.append({"test": f"{mod.replace('.', '/')}.py::{name}", "cases": len(got or []), "result": verdict})
    report[invariant] = {"holds": all(r["result"] == "passed" for r in rows), "tests": rows}
    print(("PASS " if report[invariant]["holds"] else "FAIL ") + invariant, sum(r["cases"] for r in rows), "cases")
json.dump(report, open(f"{SP}/ev/experience-invariants-merged-tree.json", "w", newline="\n"), indent=1)
sys.exit(0 if ok else 1)
