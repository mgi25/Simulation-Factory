"""The compiled execution context: one canonical repository-intelligence
section, bounded, deterministic, and built from an already-ranked file list.

Imports nothing from Company OS - same boundary as the other
`tools.engineering_runner` test files.
"""

from __future__ import annotations

from pathlib import Path

from tools.engineering_runner.execution_context import (
    MAX_BUNDLE_CHARS,
    MAX_TEST_ANCHOR_EXCERPTS,
    MAX_TEST_ANCHORS,
    build_execution_context,
    rank_primary_files,
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
