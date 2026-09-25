"""The compiled execution context: one canonical repository-intelligence
section, bounded, deterministic, and built from an already-ranked file list.

Imports nothing from Company OS - same boundary as the other
`tools.engineering_runner` test files.
"""

from __future__ import annotations

from pathlib import Path

from tools.engineering_runner.execution_context import (
    MAX_BUNDLE_CHARS,
    MAX_COMPILED_SPAN_CHARS,
    MAX_COMPILED_SPANS,
    MAX_TEST_ANCHOR_EXCERPTS,
    MAX_TEST_ANCHORS,
    SEMANTIC_COMPILER_VERSION,
    build_execution_context,
    failure_symbol_hints,
    rank_primary_files,
    rank_task_spans,
    rank_test_anchors,
)
from tools.engineering_runner.repo_map import build_repo_map


def _write(root: Path, rel: str, content: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _sample_repo(root: Path) -> Path:
    _write(
        root,
        "company/widgets/spinner.py",
        '"""Spin a widget until it stops."""\n\n'
        "import os\n"
        "from company.widgets.errors import SpinError\n\n"
        "class Spinner:\n"
        "    def spin(self) -> None:\n"
        "        return None\n\n"
        "def start_spinner() -> Spinner:\n"
        "    return Spinner()\n",
    )
    _write(
        root,
        "company/widgets/errors.py",
        '"""Errors a widget can raise."""\n\n'
        "class SpinError(Exception):\n"
        "    pass\n",
    )
    _write(
        root,
        "tools/actuator/launcher.py",
        '"""Launch a process for a widget."""\n\n'
        "from company.widgets.errors import SpinError\n\n"
        "def main() -> int:\n"
        "    return 0\n",
    )
    _write(
        root,
        "tests/test_company_widgets_errors.py",
        "from company.widgets.errors import SpinError\n\n"
        "def test_spin_error_is_an_exception():\n"
        "    assert issubclass(SpinError, Exception)\n",
    )
    return root


def _pattern_repo(root: Path) -> Path:
    """A tiny repo shaped like the V2 blocked_attempts scenario: a class with
    two existing counter-like fields, a test file whose helper (`_config`)
    sits before the sibling tests that actually exercise each counter, plus
    one wholly unrelated test."""
    _write(
        root,
        "company/widgets/counter.py",
        '"""A widget counter with two existing fields."""\n\n'
        "class Counter:\n"
        "    def __init__(self) -> None:\n"
        "        self.spin_count = 0\n"
        "        self.stop_count = 0\n",
    )
    _write(
        root,
        "tests/test_widget_counter.py",
        "def _config():\n"
        "    return {}\n\n"
        "def test_spin_count_increments_on_spin():\n"
        "    counter = Counter()\n"
        "    counter.spin_count += 1\n"
        "    assert counter.spin_count == 1\n\n"
        "def test_stop_count_increments_on_stop():\n"
        "    counter = Counter()\n"
        "    counter.stop_count += 1\n"
        "    assert counter.stop_count == 1\n\n"
        "def test_unrelated_widget_behaviour():\n"
        "    assert True\n",
    )
    return root


def test_rank_test_anchors_ranks_the_relevant_sibling_above_the_helper(tmp_path: Path) -> None:
    repo = _pattern_repo(tmp_path)
    repo_map = build_repo_map(repo, roots=("company", "tools", "tests"))
    anchors = rank_test_anchors(
        repo_map,
        objective="add a launch_count field",
        acceptance_criteria=["follows the same pattern as spin_count"],
        test_paths=["tests/test_widget_counter.py"],
        repo_root=repo,
    )
    assert anchors
    assert anchors[0].qualified_name == "test_spin_count_increments_on_spin"
    # `_config` is a fixture, not a `test_`-prefixed symbol, so it is never a
    # candidate at all - the irrelevant-helper de-prioritization is structural.
    assert all(a.qualified_name != "_config" for a in anchors)


def test_rank_test_anchors_ranks_a_second_named_pattern_correctly(tmp_path: Path) -> None:
    repo = _pattern_repo(tmp_path)
    repo_map = build_repo_map(repo, roots=("company", "tools", "tests"))
    anchors = rank_test_anchors(
        repo_map,
        objective="add a launch_count field",
        acceptance_criteria=["follows the same pattern as stop_count"],
        test_paths=["tests/test_widget_counter.py"],
        repo_root=repo,
    )
    assert anchors
    assert anchors[0].qualified_name == "test_stop_count_increments_on_stop"


def test_rank_test_anchors_surfaces_two_bounded_anchors_for_two_patterns(tmp_path: Path) -> None:
    repo = _pattern_repo(tmp_path)
    repo_map = build_repo_map(repo, roots=("company", "tools", "tests"))
    anchors = rank_test_anchors(
        repo_map,
        objective="add a launch_count field",
        acceptance_criteria=[
            "follows the same pattern as spin_count and stop_count",
        ],
        test_paths=["tests/test_widget_counter.py"],
        repo_root=repo,
    )
    names = {a.qualified_name for a in anchors}
    assert names == {"test_spin_count_increments_on_spin", "test_stop_count_increments_on_stop"}
    assert len(anchors) <= MAX_TEST_ANCHORS


def test_rank_test_anchors_does_not_manufacture_a_match(tmp_path: Path) -> None:
    repo = _pattern_repo(tmp_path)
    repo_map = build_repo_map(repo, roots=("company", "tools", "tests"))
    anchors = rank_test_anchors(
        repo_map,
        objective="improve overall reliability",
        acceptance_criteria=["the change should be well tested and documented"],
        test_paths=["tests/test_widget_counter.py"],
        repo_root=repo,
    )
    assert anchors == ()


def test_rank_test_anchors_ignores_a_self_referential_filename_mention(tmp_path: Path) -> None:
    repo = _pattern_repo(tmp_path)
    repo_map = build_repo_map(repo, roots=("company", "tools", "tests"))
    anchors = rank_test_anchors(
        repo_map,
        objective="x",
        acceptance_criteria=[
            "a new test case in tests/test_widget_counter.py covers this",
        ],
        test_paths=["tests/test_widget_counter.py"],
        repo_root=repo,
    )
    assert anchors == ()


def test_rank_test_anchors_caps_excerpts_at_one(tmp_path: Path) -> None:
    repo = _pattern_repo(tmp_path)
    repo_map = build_repo_map(repo, roots=("company", "tools", "tests"))
    anchors = rank_test_anchors(
        repo_map,
        objective="add a launch_count field",
        acceptance_criteria=["follows the same pattern as spin_count and stop_count"],
        test_paths=["tests/test_widget_counter.py"],
        repo_root=repo,
    )
    assert len(anchors) == 2
    with_excerpt = [a for a in anchors if a.excerpt is not None]
    assert len(with_excerpt) == MAX_TEST_ANCHOR_EXCERPTS


def test_rank_test_anchors_is_deterministic(tmp_path: Path) -> None:
    repo = _pattern_repo(tmp_path)
    repo_map = build_repo_map(repo, roots=("company", "tools", "tests"))
    kwargs = dict(
        objective="add a launch_count field",
        acceptance_criteria=["follows the same pattern as spin_count and stop_count"],
        test_paths=["tests/test_widget_counter.py"],
        repo_root=repo,
    )
    first = rank_test_anchors(repo_map, **kwargs)
    second = rank_test_anchors(repo_map, **kwargs)
    assert first == second


def test_rank_test_anchors_with_no_repo_map_is_empty() -> None:
    assert rank_test_anchors(
        None, objective="x", acceptance_criteria=["y"], test_paths=["tests/test_a.py"]
    ) == ()


def test_build_execution_context_renders_test_anchors_within_budget(tmp_path: Path) -> None:
    repo = _pattern_repo(tmp_path)
    repo_map = build_repo_map(repo, roots=("company", "tools", "tests"))
    anchors = rank_test_anchors(
        repo_map,
        objective="add a launch_count field",
        acceptance_criteria=["follows the same pattern as spin_count and stop_count"],
        test_paths=["tests/test_widget_counter.py"],
        repo_root=repo,
    )
    bundle = build_execution_context(
        repo_map,
        primary=[("company/widgets/counter.py", "authorized")],
        test_anchors=anchors,
        repo_root=repo,
    )
    rendered = bundle.render()
    assert "test_spin_count_increments_on_spin" in rendered
    assert "test_stop_count_increments_on_stop" in rendered
    assert len(rendered) <= MAX_BUNDLE_CHARS
    assert bundle.truncated is False


def test_failure_symbol_hints_parse_pytest_node_ids_deterministically() -> None:
    hints = failure_symbol_hints(
        [
            (
                "FAILED tests/test_widget_counter.py::"
                "test_spin_count_increments_on_spin - assert 0 == 1\n"
                "FAILED tests/test_widget_counter.py::CounterCases::"
                "test_stop_count[param-1] - AssertionError"
            ),
            "unrelated diagnostic line",
        ]
    )
    assert hints == (
        ("tests/test_widget_counter.py", "test_spin_count_increments_on_spin"),
        ("tests/test_widget_counter.py", "CounterCases.test_stop_count"),
    )


def test_failure_symbol_hints_deduplicate_repeated_failures() -> None:
    detail = (
        "FAILED tests/test_widget_counter.py::test_spin_count_increments_on_spin\n"
        "FAILED tests/test_widget_counter.py::test_spin_count_increments_on_spin"
    )
    assert failure_symbol_hints([detail]) == (
        ("tests/test_widget_counter.py", "test_spin_count_increments_on_spin"),
    )


def test_preferred_failure_symbol_beats_generic_semantic_overlap(tmp_path: Path) -> None:
    repo = _pattern_repo(tmp_path)
    repo_map = build_repo_map(repo, roots=("company", "tools", "tests"))
    spans = rank_task_spans(
        repo_map,
        objective="improve widget reliability",
        acceptance_criteria=["keep counter behaviour correct"],
        paths=["tests/test_widget_counter.py"],
        repo_root=repo,
        preferred_symbols=[
            ("tests/test_widget_counter.py", "test_stop_count_increments_on_stop")
        ],
    )
    assert spans
    assert spans[0].qualified_name == "test_stop_count_increments_on_stop"
    assert spans[0].reason == "failing required test at the immutable task base"


def test_preferred_failure_symbol_preserves_complete_body_when_it_fits(
    tmp_path: Path,
) -> None:
    padding = "\n".join(
        f"    # deterministic context padding {index:02d} keeps this function long"
        for index in range(12)
    )
    _write(
        tmp_path,
        "tests/test_long_contract.py",
        (
            "def test_contract_has_two_stale_assertions():\n"
            "    authorized_paths = ('old.py',)\n"
            "    assert authorized_paths == ('old.py',)\n"
            f"{padding}\n"
            "    required_tests = ('old_test.py',)\n"
            "    assert required_tests == ('old_test.py',)\n"
        ),
    )
    repo_map = build_repo_map(tmp_path, roots=("tests",))
    spans = rank_task_spans(
        repo_map,
        objective="x",
        acceptance_criteria=[],
        paths=["tests/test_long_contract.py"],
        repo_root=tmp_path,
        preferred_symbols=[
            ("tests/test_long_contract.py", "test_contract_has_two_stale_assertions")
        ],
    )
    assert len(spans) == 1
    assert len(spans[0].text) > 600
    assert "assert authorized_paths" in spans[0].text
    assert "assert required_tests" in spans[0].text
    assert spans[0].end_line == repo_map.by_path(
        "tests/test_long_contract.py"
    ).symbol("test_contract_has_two_stale_assertions").end_line


def test_preferred_failure_symbols_share_a_tight_global_budget(tmp_path: Path) -> None:
    long_body = "\n".join(
        f"    # long deterministic line {index:02d} " + ("x" * 30)
        for index in range(18)
    )
    _write(
        tmp_path,
        "tests/test_long_contract.py",
        (
            "def test_first_failure():\n"
            f"{long_body}\n"
            "    assert False\n\n"
            "def test_second_failure():\n"
            f"{long_body}\n"
            "    assert False\n"
        ),
    )
    repo_map = build_repo_map(tmp_path, roots=("tests",))
    spans = rank_task_spans(
        repo_map,
        objective="x",
        acceptance_criteria=[],
        paths=["tests/test_long_contract.py"],
        repo_root=tmp_path,
        preferred_symbols=[
            ("tests/test_long_contract.py", "test_first_failure"),
            ("tests/test_long_contract.py", "test_second_failure"),
        ],
        max_total_chars=400,
    )
    assert [span.qualified_name for span in spans] == [
        "test_first_failure",
        "test_second_failure",
    ]
    assert sum(len(span.text) for span in spans) <= 400
    assert all(span.text for span in spans)


def test_preferred_failure_symbol_outside_eligible_paths_is_ignored(tmp_path: Path) -> None:
    repo = _pattern_repo(tmp_path)
    repo_map = build_repo_map(repo, roots=("company", "tools", "tests"))
    spans = rank_task_spans(
        repo_map,
        objective="improve widget reliability",
        acceptance_criteria=["keep counter behaviour correct"],
        paths=["company/widgets/counter.py"],
        repo_root=repo,
        preferred_symbols=[
            ("tests/test_widget_counter.py", "test_stop_count_increments_on_stop")
        ],
    )
    assert all(span.path == "company/widgets/counter.py" for span in spans)


def test_rank_task_spans_compiles_multiple_exact_matches_once(tmp_path: Path) -> None:
    repo = _pattern_repo(tmp_path)
    repo_map = build_repo_map(repo, roots=("company", "tools", "tests"))
    spans = rank_task_spans(
        repo_map,
        objective="add a launch_count field",
        acceptance_criteria=["follow spin_count and stop_count exactly"],
        paths=["tests/test_widget_counter.py"],
        repo_root=repo,
    )
    assert {span.qualified_name for span in spans} == {
        "test_spin_count_increments_on_spin",
        "test_stop_count_increments_on_stop",
    }
    assert len(spans) <= MAX_COMPILED_SPANS
    assert sum(len(span.text) for span in spans) <= MAX_COMPILED_SPAN_CHARS
    assert all(len(span.digest) == 16 for span in spans)
    assert "spin_count" in next(
        span.text for span in spans if "spin_count" in span.qualified_name
    )
    assert "stop_count" in next(
        span.text for span in spans if "stop_count" in span.qualified_name
    )


def test_rank_task_spans_is_deterministic_and_path_bounded(tmp_path: Path) -> None:
    repo = _pattern_repo(tmp_path)
    repo_map = build_repo_map(repo, roots=("company", "tools", "tests"))
    kwargs = dict(
        objective="add a launch_count field",
        acceptance_criteria=["follow spin_count"],
        paths=["tests/test_widget_counter.py"],
        repo_root=repo,
    )
    first = rank_task_spans(repo_map, **kwargs)
    second = rank_task_spans(repo_map, **kwargs)
    assert first == second
    assert first
    assert {span.path for span in first} == {"tests/test_widget_counter.py"}


def test_rank_task_spans_hard_caps_the_excerpt_budget(tmp_path: Path) -> None:
    repo = _pattern_repo(tmp_path)
    repo_map = build_repo_map(repo, roots=("company", "tools", "tests"))
    spans = rank_task_spans(
        repo_map,
        objective="launch_count",
        acceptance_criteria=["spin_count and stop_count"],
        paths=["tests/test_widget_counter.py"],
        repo_root=repo,
        max_total_chars=40,
    )
    assert sum(len(span.text) for span in spans) <= 40


def test_rank_task_spans_does_not_manufacture_context(tmp_path: Path) -> None:
    repo = _pattern_repo(tmp_path)
    repo_map = build_repo_map(repo, roots=("company", "tools", "tests"))
    assert rank_task_spans(
        repo_map,
        objective="improve reliability",
        acceptance_criteria=["be clear"],
        paths=["tests/test_widget_counter.py"],
        repo_root=repo,
    ) == ()


def test_compiled_context_is_fingerprinted_and_rendered_read_once(tmp_path: Path) -> None:
    repo = _pattern_repo(tmp_path)
    repo_map = build_repo_map(repo, roots=("company", "tools", "tests"))
    spans = rank_task_spans(
        repo_map,
        objective="add launch_count",
        acceptance_criteria=["follow spin_count and stop_count"],
        paths=["tests/test_widget_counter.py"],
        repo_root=repo,
    )
    bundle = build_execution_context(
        repo_map,
        primary=[("company/widgets/counter.py", "authorized")],
        compiled_spans=spans,
        repo_root=repo,
        include_excerpts=False,
    )
    rendered = bundle.render()
    data = bundle.to_dict()
    assert "Precompiled task spans (read-once semantic context)" in rendered
    assert "Do not broadly re-read" in rendered
    assert data["compiler_version"] == SEMANTIC_COMPILER_VERSION
    assert data["compiled_spans"]
    assert len(data["fingerprint"]) == 16
    assert data["fingerprint"] == bundle.fingerprint()
    assert bundle.files[0].excerpts == ()
    assert len(rendered) <= MAX_BUNDLE_CHARS


def test_preferred_failure_symbol_works_even_without_semantic_targets(tmp_path: Path) -> None:
    repo = _pattern_repo(tmp_path)
    repo_map = build_repo_map(repo, roots=("company", "tools", "tests"))
    spans = rank_task_spans(
        repo_map,
        objective="x",
        acceptance_criteria=[],
        paths=["tests/test_widget_counter.py"],
        repo_root=repo,
        preferred_symbols=[
            ("tests/test_widget_counter.py", "test_spin_count_increments_on_spin")
        ],
    )
    assert [span.qualified_name for span in spans] == [
        "test_spin_count_increments_on_spin"
    ]


def test_a_compiled_only_bundle_still_renders(tmp_path: Path) -> None:
    repo = _pattern_repo(tmp_path)
    repo_map = build_repo_map(repo, roots=("company", "tools", "tests"))
    spans = rank_task_spans(
        repo_map,
        objective="x",
        acceptance_criteria=[],
        paths=["tests/test_widget_counter.py"],
        repo_root=repo,
        preferred_symbols=[
            ("tests/test_widget_counter.py", "test_spin_count_increments_on_spin")
        ],
    )
    bundle = build_execution_context(repo_map, primary=[], compiled_spans=spans)
    rendered = bundle.render()
    assert "Precompiled task spans" in rendered
    assert "test_spin_count_increments_on_spin" in rendered


def test_compiled_context_fingerprint_changes_with_source_body(tmp_path: Path) -> None:
    repo = _pattern_repo(tmp_path)
    repo_map = build_repo_map(repo, roots=("company", "tools", "tests"))
    kwargs = dict(
        objective="launch_count",
        acceptance_criteria=["follow spin_count"],
        paths=["tests/test_widget_counter.py"],
        repo_root=repo,
    )
    first = rank_task_spans(repo_map, **kwargs)
    first_bundle = build_execution_context(repo_map, primary=[], compiled_spans=first)

    path = repo / "tests" / "test_widget_counter.py"
    path.write_text(path.read_text("utf-8").replace("== 1", "== 2", 1), encoding="utf-8")
    changed_map = build_repo_map(repo, roots=("company", "tools", "tests"))
    second = rank_task_spans(changed_map, **kwargs)
    second_bundle = build_execution_context(changed_map, primary=[], compiled_spans=second)

    assert first_bundle.fingerprint() != second_bundle.fingerprint()


def test_rank_primary_files_puts_authorized_paths_first(tmp_path: Path) -> None:
    repo = _sample_repo(tmp_path)
    repo_map = build_repo_map(repo, roots=("company", "tools", "tests"))
    ranked = rank_primary_files(
        repo_map,
        objective="fix the spinner",
        focus_paths=["company/widgets/errors.py"],
        limit=5,
    )
    assert ranked[0][0] == "company/widgets/errors.py"
    assert "authorizes" in ranked[0][1]


def test_rank_primary_files_fills_remaining_slots_from_the_objective(tmp_path: Path) -> None:
    repo = _sample_repo(tmp_path)
    repo_map = build_repo_map(repo, roots=("company", "tools", "tests"))
    ranked = rank_primary_files(
        repo_map, objective="spinner", focus_paths=[], limit=5
    )
    assert any(path == "company/widgets/spinner.py" for path, _ in ranked)


def test_rank_primary_files_deduplicates_a_path_in_both_sources(tmp_path: Path) -> None:
    repo = _sample_repo(tmp_path)
    repo_map = build_repo_map(repo, roots=("company", "tools", "tests"))
    ranked = rank_primary_files(
        repo_map,
        objective="spinner",
        focus_paths=["company/widgets/spinner.py"],
        limit=5,
    )
    paths = [path for path, _ in ranked]
    assert paths.count("company/widgets/spinner.py") == 1


def test_rank_primary_files_with_no_repo_map_is_empty() -> None:
    assert rank_primary_files(None, objective="x", focus_paths=["a.py"]) == ()


def test_build_execution_context_includes_symbols_dependents_and_tests(tmp_path: Path) -> None:
    repo = _sample_repo(tmp_path)
    repo_map = build_repo_map(repo, roots=("company", "tools", "tests"))
    bundle = build_execution_context(
        repo_map,
        primary=[("company/widgets/errors.py", "authorized")],
        repo_root=repo,
    )
    assert len(bundle.files) == 1
    file = bundle.files[0]
    assert file.path == "company/widgets/errors.py"
    assert any(s.qualified_name == "SpinError" for s in file.symbols)
    assert set(file.dependents) == {"company/widgets/spinner.py", "tools/actuator/launcher.py"}
    assert file.tests == ("tests/test_company_widgets_errors.py",)


def test_build_execution_context_includes_a_small_source_excerpt(tmp_path: Path) -> None:
    repo = _sample_repo(tmp_path)
    repo_map = build_repo_map(repo, roots=("company", "tools", "tests"))
    bundle = build_execution_context(
        repo_map,
        primary=[("company/widgets/errors.py", "authorized")],
        repo_root=repo,
        include_excerpts=True,
    )
    file = bundle.files[0]
    assert file.excerpts
    assert "class SpinError" in file.excerpts[0].text


def test_build_execution_context_skips_excerpts_when_disabled(tmp_path: Path) -> None:
    repo = _sample_repo(tmp_path)
    repo_map = build_repo_map(repo, roots=("company", "tools", "tests"))
    bundle = build_execution_context(
        repo_map,
        primary=[("company/widgets/errors.py", "authorized")],
        repo_root=repo,
        include_excerpts=False,
    )
    assert bundle.files[0].excerpts == ()


def test_build_execution_context_only_excerpts_the_first_n_files(tmp_path: Path) -> None:
    repo = _sample_repo(tmp_path)
    repo_map = build_repo_map(repo, roots=("company", "tools", "tests"))
    bundle = build_execution_context(
        repo_map,
        primary=[
            ("company/widgets/errors.py", "authorized"),
            ("company/widgets/spinner.py", "matched"),
        ],
        repo_root=repo,
    )
    assert bundle.files[0].excerpts
    assert bundle.files[1].excerpts == (), "only MAX_FILES_WITH_EXCERPTS gets a body excerpt"


def test_build_execution_context_respects_limit(tmp_path: Path) -> None:
    repo = _sample_repo(tmp_path)
    repo_map = build_repo_map(repo, roots=("company", "tools", "tests"))
    bundle = build_execution_context(
        repo_map,
        primary=[
            ("company/widgets/errors.py", "a"),
            ("company/widgets/spinner.py", "b"),
            ("tools/actuator/launcher.py", "c"),
        ],
        limit=2,
    )
    assert len(bundle.files) == 2


def test_build_execution_context_skips_an_unknown_path(tmp_path: Path) -> None:
    repo = _sample_repo(tmp_path)
    repo_map = build_repo_map(repo, roots=("company", "tools", "tests"))
    bundle = build_execution_context(
        repo_map, primary=[("company/widgets/does_not_exist.py", "guess")]
    )
    assert bundle.files == ()


def test_build_execution_context_with_no_repo_map_is_empty_not_raised() -> None:
    bundle = build_execution_context(None, primary=[("a.py", "x")])
    assert bundle.files == ()
    assert bundle.render() == ""


def test_context_refs_are_rendered_as_pointers_not_bodies(tmp_path: Path) -> None:
    bundle = build_execution_context(
        None,
        primary=[],
        context_refs=[
            {"kind": "file", "ref": "docs/x.md", "reason": "explains the rule", "span": [1, 20]},
            {"kind": "fact", "ref": "capsule-123", "reason": "prior finding"},
        ],
    )
    rendered = bundle.render()
    assert "docs/x.md#1-20" in rendered
    assert "explains the rule" in rendered
    assert "capsule-123" in rendered


def test_context_refs_ignores_a_malformed_entry() -> None:
    bundle = build_execution_context(None, primary=[], context_refs=[{"kind": "file"}, "not-a-mapping"])
    assert bundle.context_refs == ()


def test_render_is_bounded_by_the_size_budget(tmp_path: Path) -> None:
    repo = _sample_repo(tmp_path)
    # Give every file a huge docstring-free body so symbols alone do not
    # trigger truncation, then force a tiny budget to prove the hard cut.
    repo_map = build_repo_map(repo, roots=("company", "tools", "tests"))
    bundle = build_execution_context(
        repo_map,
        primary=[("company/widgets/errors.py", "x" * 500)],
        repo_root=repo,
        budget_chars=200,
    )
    rendered = bundle.render()
    assert len(rendered) <= 200
    assert bundle.truncated is True


def test_a_bundle_within_budget_is_not_marked_truncated(tmp_path: Path) -> None:
    repo = _sample_repo(tmp_path)
    repo_map = build_repo_map(repo, roots=("company", "tools", "tests"))
    bundle = build_execution_context(
        repo_map, primary=[("company/widgets/errors.py", "authorized")], repo_root=repo
    )
    assert bundle.truncated is False
    assert len(bundle.render()) < MAX_BUNDLE_CHARS


def test_an_empty_bundle_renders_to_an_empty_string() -> None:
    bundle = build_execution_context(None, primary=[])
    assert bundle.render() == ""


def test_to_dict_reports_rendered_chars_and_truncation(tmp_path: Path) -> None:
    repo = _sample_repo(tmp_path)
    repo_map = build_repo_map(repo, roots=("company", "tools", "tests"))
    bundle = build_execution_context(
        repo_map, primary=[("company/widgets/errors.py", "authorized")], repo_root=repo
    )
    data = bundle.to_dict()
    assert data["rendered_chars"] == len(bundle.render())
    assert data["truncated"] is False


# --- prior experience: parsed strictly, revalidated here, navigation only ------

import types

import pytest

from tools.engineering_runner.experience import (
    ADVICE_KIND,
    AUTHORITY_KEYS,
    ExperienceAdvice,
    ExperienceAdviceRejected,
    fingerprint,
    revalidate,
)

_WORK_ORDER = "wo-widgets"


def _advice(**changes) -> dict:
    payload = {
        "kind": ADVICE_KIND,
        "version": 1,
        "advisory_only": True,
        "work_order_id": _WORK_ORDER,
        "work_order_fingerprint": "0123456789abcdef",
        "attempt": 1,
        "as_of": "2026-09-25",
        "status": "precedent",
        "abstention": None,
        "precedents": [
            {
                "experience_id": "1111111111111111",
                "work_order_id": "wo-earlier",
                "outcome": "accepted: recorded accepted, review pass, gate ready",
                "why": ["1 changed file(s) inside this task's write scope: company/widgets/spinner.py"],
            }
        ],
        "warnings": [],
        "historical_only": [],
        "suggested_files": [
            {"path": "company/widgets/spinner.py", "reason": "changed by accepted precedent wo-earlier"},
            {"path": "tools/actuator/launcher.py", "reason": "read by accepted precedent wo-earlier"},
        ],
        "suggested_tests": [
            {"path": "tests/test_company_widgets_errors.py", "reason": "exercised by accepted precedent wo-earlier"}
        ],
        "refused": [],
        "resource_history": [],
        "measurement": {},
        "truncated": False,
    }
    payload.update(changes)
    payload.pop("fingerprint", None)
    payload["fingerprint"] = fingerprint(payload)
    return payload


def _envelope(**changes):
    values = dict(
        may_read=("company/widgets", "tests"),
        may_not_read=(),
        may_write=("company/widgets",),
        required_tests=(),
    )
    values.update(changes)
    return types.SimpleNamespace(**values)


def test_a_well_formed_advisory_parses() -> None:
    advice = ExperienceAdvice.parse(_advice(), work_order_id=_WORK_ORDER)
    assert advice.status == "precedent"
    assert [p[0] for p in advice.precedents] == ["wo-earlier"]
    assert [path for path, _ in advice.files] == ["company/widgets/spinner.py", "tools/actuator/launcher.py"]


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"kind": "something_else"}, "not a version-1"),
        ({"version": 2}, "not a version-1"),
        ({"advisory_only": False}, "advisory-only"),
        ({"approved_for_merge": True}, "undeclared field"),
        ({"work_order_id": "wo-other"}, "answers"),
        ({"status": "certain"}, "unknown status"),
        ({"suggested_files": [{"path": "../outside.py", "reason": "x"}]}, "unusable path"),
        ({"suggested_files": [{"path": f"company/widgets/f{i}.py", "reason": "x"} for i in range(6)]}, "at most 5"),
    ],
)
def test_an_advisory_that_is_not_what_it_claims_is_dropped_whole(changes, message) -> None:
    with pytest.raises(ExperienceAdviceRejected, match=message):
        ExperienceAdvice.parse(_advice(**changes), work_order_id=_WORK_ORDER)


@pytest.mark.parametrize("key", ["may_write", "may_read", "required_tests", "risk", "reasoning_class", "approve"])
def test_authority_vocabulary_anywhere_in_an_advisory_is_refused(key: str) -> None:
    assert key in AUTHORITY_KEYS
    files = [{"path": "company/widgets/spinner.py", "reason": "x", key: ["company"]}]
    with pytest.raises(ExperienceAdviceRejected, match="authority vocabulary"):
        ExperienceAdvice.parse(_advice(suggested_files=files), work_order_id=_WORK_ORDER)


def test_a_tampered_advisory_fails_its_fingerprint() -> None:
    payload = _advice()
    payload["suggested_files"][0]["path"] = "company/widgets/errors.py"
    with pytest.raises(ExperienceAdviceRejected, match="fingerprint"):
        ExperienceAdvice.parse(payload, work_order_id=_WORK_ORDER)


def test_revalidation_keeps_only_what_this_envelope_may_read(tmp_path: Path) -> None:
    repo_map = build_repo_map(_sample_repo(tmp_path))
    advice = ExperienceAdvice.parse(_advice(), work_order_id=_WORK_ORDER)
    result = revalidate(advice, _envelope(), repo_map)
    assert [path for path, _ in result.files] == ["company/widgets/spinner.py"]
    assert ("file:tools/actuator/launcher.py", "outside this work order's read authority") in result.refused
    assert [path for path, _ in result.tests] == ["tests/test_company_widgets_errors.py"]


def test_a_denied_read_outranks_history(tmp_path: Path) -> None:
    repo_map = build_repo_map(_sample_repo(tmp_path))
    advice = ExperienceAdvice.parse(_advice(), work_order_id=_WORK_ORDER)
    result = revalidate(advice, _envelope(may_not_read=("company/widgets/spinner.py",)), repo_map)
    assert result.files == ()
    assert ("file:company/widgets/spinner.py", "forbidden to read by this work order") in result.refused


def test_an_empty_read_grant_admits_nothing(tmp_path: Path) -> None:
    repo_map = build_repo_map(_sample_repo(tmp_path))
    advice = ExperienceAdvice.parse(_advice(), work_order_id=_WORK_ORDER)
    result = revalidate(advice, _envelope(may_read=()), repo_map)
    assert result.files == () and result.tests == ()


def test_without_a_map_nothing_is_passed_on() -> None:
    advice = ExperienceAdvice.parse(_advice(), work_order_id=_WORK_ORDER)
    result = revalidate(advice, _envelope(), None)
    assert result.files == () and result.tests == ()
    assert {reason for _, reason in result.refused} <= {
        "no repository map to check it against",
        "outside this work order's read authority",
    }


def test_a_required_test_is_never_offered_and_an_unreaching_test_is_refused(tmp_path: Path) -> None:
    repo_map = build_repo_map(_sample_repo(tmp_path))
    advice = ExperienceAdvice.parse(_advice(), work_order_id=_WORK_ORDER)
    required = revalidate(advice, _envelope(required_tests=("tests/test_company_widgets_errors.py",)), repo_map)
    assert required.tests == ()
    elsewhere = revalidate(advice, _envelope(may_write=("company/widgets/spinner.py",)), repo_map)
    assert elsewhere.tests == ()
    assert (
        "test:tests/test_company_widgets_errors.py",
        "does not statically reach a path this work order may change",
    ) in elsewhere.refused


def test_the_rendered_advice_is_bounded_and_says_it_changes_nothing(tmp_path: Path) -> None:
    repo_map = build_repo_map(_sample_repo(tmp_path))
    advice = ExperienceAdvice.parse(_advice(), work_order_id=_WORK_ORDER)
    text = revalidate(advice, _envelope(), repo_map).render()
    assert "Prior experience" in text and "wo-earlier" in text
    assert "nothing in this section changes them" in text
    assert "tools/actuator/launcher.py" not in text
    assert len(text) <= 1800
    quiet = ExperienceAdvice.parse(
        _advice(
            status="abstain",
            abstention={"code": "no_match", "detail": "x"},
            precedents=[],
            suggested_files=[],
            suggested_tests=[],
        ),
        work_order_id=_WORK_ORDER,
    )
    assert revalidate(quiet, _envelope(), repo_map).render() == ""


def test_experience_files_rank_after_authorized_paths_and_before_guesses(tmp_path: Path) -> None:
    repo_map = build_repo_map(_sample_repo(tmp_path))
    ranked = rank_primary_files(
        repo_map,
        objective="spin the widget faster",
        focus_paths=("company/widgets/errors.py",),
        experience_paths=(
            ("company/widgets/spinner.py", "prior experience: changed by accepted precedent"),
            ("company/widgets/missing.py", "prior experience: gone"),
        ),
    )
    assert ranked[0] == ("company/widgets/errors.py", "a path this work order authorizes changing")
    assert ranked[1] == ("company/widgets/spinner.py", "prior experience: changed by accepted precedent")
    assert all(path != "company/widgets/missing.py" for path, _ in ranked)
    assert len(ranked) == 2, "experience filled the budget a guess would have used"
    plain = rank_primary_files(repo_map, objective="spin the widget faster", focus_paths=("company/widgets/errors.py",))
    assert plain[0] == ranked[0]
