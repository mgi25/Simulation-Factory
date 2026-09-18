"""The compiled execution context: one canonical repository-intelligence
section, bounded, deterministic, and built from an already-ranked file list.

Imports nothing from Company OS - same boundary as the other
`tools.engineering_runner` test files.
"""

from __future__ import annotations

from pathlib import Path

from tools.engineering_runner.execution_context import (
    MAX_BUNDLE_CHARS,
    build_execution_context,
    rank_primary_files,
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
