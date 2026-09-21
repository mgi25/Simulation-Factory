"""The deterministic repo map: what it can answer without a model session.

This file imports nothing from Company OS - `tools.engineering_runner` may
not, so neither may its tests (`architecture.production_tests_independent`).
Every fixture here is a small synthetic tree under `tmp_path`, not this
repository, so the tests stay fast and do not depend on this repository's own
Python surface changing shape later.
"""

from __future__ import annotations

from pathlib import Path

from tools.engineering_runner.repo_map import (
    ModuleMap,
    RepoMap,
    SymbolSpan,
    build_and_cache,
    build_repo_map,
    build_repo_map_cached,
    load_or_build,
    neighborhood,
    query,
)


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
        "    def spin(self) -> None: ...\n\n"
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
        "def main() -> int:\n"
        "    return 0\n",
    )
    _write(
        root,
        "tests/test_company_widgets_spinner.py",
        "from company.widgets.spinner import Spinner, start_spinner\n\n"
        "def test_start_spinner_spins():\n"
        "    assert start_spinner().spin() is None\n",
    )
    _write(
        root,
        "tests/test_company_widgets_errors.py",
        "from company.widgets.errors import SpinError\n\n"
        "def test_spin_error_is_an_exception():\n"
        "    assert issubclass(SpinError, Exception)\n",
    )
    return root


def test_build_repo_map_extracts_classes_functions_and_imports(tmp_path: Path) -> None:
    repo = _sample_repo(tmp_path)
    repo_map = build_repo_map(repo, roots=("company", "tools", "tests"))

    spinner = repo_map.by_path("company/widgets/spinner.py")
    assert spinner is not None
    assert spinner.classes == ("Spinner",)
    assert spinner.functions == ("start_spinner",)
    assert "os" in spinner.imports
    assert "company.widgets.errors" in spinner.imports
    assert spinner.doc == "Spin a widget until it stops."
    assert spinner.owner == "company/widgets"


def test_entry_points_are_flagged(tmp_path: Path) -> None:
    repo = _sample_repo(tmp_path)
    repo_map = build_repo_map(repo, roots=("company", "tools", "tests"))
    launcher = repo_map.by_path("tools/actuator/launcher.py")
    assert launcher is not None
    assert launcher.is_entry_point is True
    spinner = repo_map.by_path("company/widgets/spinner.py")
    assert spinner is not None
    assert spinner.is_entry_point is False


def test_reverse_test_index_resolves_real_imports_not_filenames(tmp_path: Path) -> None:
    """Both test files import `spinner`'s sibling module too - via the
    package - so the index must not assume one test file per module."""
    repo = _sample_repo(tmp_path)
    repo_map = build_repo_map(repo, roots=("company", "tools", "tests"))

    assert repo_map.tests_by_module["company/widgets/spinner.py"] == (
        "tests/test_company_widgets_spinner.py",
    )
    assert repo_map.tests_by_module["company/widgets/errors.py"] == (
        "tests/test_company_widgets_errors.py",
    )


def test_a_syntax_error_does_not_abort_the_whole_build(tmp_path: Path) -> None:
    repo = _sample_repo(tmp_path)
    _write(repo, "company/widgets/broken.py", "def broken(:\n    pass\n")
    repo_map = build_repo_map(repo, roots=("company", "tools", "tests"))
    broken = repo_map.by_path("company/widgets/broken.py")
    assert broken is not None
    assert broken.classes == ()
    assert broken.functions == ()


def test_build_is_deterministic(tmp_path: Path) -> None:
    repo = _sample_repo(tmp_path)
    first = build_repo_map(repo, roots=("company", "tools", "tests"))
    second = build_repo_map(repo, roots=("company", "tools", "tests"))
    assert first.to_json() == second.to_json()


def test_json_round_trip_preserves_everything(tmp_path: Path) -> None:
    repo = _sample_repo(tmp_path)
    original = build_repo_map(repo, roots=("company", "tools", "tests"))
    restored = RepoMap.from_json(original.to_json())
    assert restored.to_dict() == original.to_dict()


def test_query_ranks_a_path_match_over_a_docstring_match(tmp_path: Path) -> None:
    repo = _sample_repo(tmp_path)
    repo_map = build_repo_map(repo, roots=("company", "tools", "tests"))
    hits = query(repo_map, "spinner", limit=5)
    assert hits
    assert hits[0].path == "company/widgets/spinner.py"
    assert "Spinner" in hits[0].matched_symbols or "start_spinner" in hits[0].matched_symbols
    assert hits[0].tests == ("tests/test_company_widgets_spinner.py",)


def test_query_is_deterministic_and_bounded_by_limit(tmp_path: Path) -> None:
    repo = _sample_repo(tmp_path)
    repo_map = build_repo_map(repo, roots=("company", "tools", "tests"))
    first = query(repo_map, "widget error spin", limit=2)
    second = query(repo_map, "widget error spin", limit=2)
    assert first == second
    assert len(first) <= 2


def test_query_with_no_recognisable_token_returns_nothing(tmp_path: Path) -> None:
    repo = _sample_repo(tmp_path)
    repo_map = build_repo_map(repo, roots=("company", "tools", "tests"))
    assert query(repo_map, "zzzznotpresentanywhere", limit=5) == ()


def test_content_addressed_cache_reuses_an_exact_tree_snapshot(tmp_path: Path) -> None:
    repo = _sample_repo(tmp_path)
    cache = tmp_path / "runner-cache"

    first, cold = build_repo_map_cached(
        repo, cache, roots=("company", "tools", "tests")
    )
    second, warm = build_repo_map_cached(
        repo, cache, roots=("company", "tools", "tests")
    )

    assert first.to_dict() == second.to_dict()
    assert cold.snapshot_hit is False
    assert cold.module_hits == 0
    assert cold.module_misses == cold.module_count
    assert warm.snapshot_hit is True
    assert warm.module_hits == warm.module_count
    assert warm.module_misses == 0
    assert warm.tree_fingerprint == cold.tree_fingerprint


def test_content_addressed_cache_reparses_only_a_changed_module(tmp_path: Path) -> None:
    repo = _sample_repo(tmp_path)
    cache = tmp_path / "runner-cache"

    first, cold = build_repo_map_cached(
        repo, cache, roots=("company", "tools", "tests")
    )
    _write(
        repo,
        "company/widgets/spinner.py",
        '"""Spin a widget until it stops."""\n\n'
        "import os\n"
        "from company.widgets.errors import SpinError\n\n"
        "class Spinner:\n"
        "    def spin(self) -> None: ...\n"
        "    def stop(self) -> None: ...\n\n"
        "def start_spinner() -> Spinner:\n"
        "    return Spinner()\n",
    )

    second, changed = build_repo_map_cached(
        repo, cache, roots=("company", "tools", "tests")
    )

    assert changed.snapshot_hit is False
    assert changed.tree_fingerprint != cold.tree_fingerprint
    assert changed.module_count == cold.module_count
    assert changed.module_misses == 1
    assert changed.module_hits == changed.module_count - 1
    spinner = second.by_path("company/widgets/spinner.py")
    assert spinner is not None
    assert spinner.symbol("Spinner.stop") is not None
    assert second.to_dict() == build_repo_map(
        repo, roots=("company", "tools", "tests")
    ).to_dict()
    assert first.to_dict() != second.to_dict()


def test_content_addressed_cache_recovers_from_a_corrupt_latest_manifest(
    tmp_path: Path,
) -> None:
    repo = _sample_repo(tmp_path)
    cache = tmp_path / "runner-cache"

    expected, _cold = build_repo_map_cached(
        repo, cache, roots=("company", "tools", "tests")
    )

    for snapshot in (cache / "snapshots").glob("*.json"):
        snapshot.unlink()

    latest = cache / "latest.json"
    assert latest.is_file()
    latest.write_text("{not json", encoding="utf-8")

    recovered, evidence = build_repo_map_cached(
        repo, cache, roots=("company", "tools", "tests")
    )

    assert recovered.to_dict() == expected.to_dict()
    assert evidence.snapshot_hit is False
    assert evidence.invalid_entries == 1
    assert evidence.module_misses == evidence.module_count
    assert evidence.module_hits == 0


def test_content_addressed_cache_never_reuses_a_snapshot_after_source_change(
    tmp_path: Path,
) -> None:
    repo = _sample_repo(tmp_path)
    cache = tmp_path / "runner-cache"

    _original, cold = build_repo_map_cached(
        repo, cache, roots=("company", "tools", "tests")
    )
    _write(repo, "company/widgets/errors.py", "class NewError(Exception):\n    pass\n")

    changed, evidence = build_repo_map_cached(
        repo, cache, roots=("company", "tools", "tests")
    )

    assert evidence.snapshot_hit is False
    assert evidence.tree_fingerprint != cold.tree_fingerprint
    errors = changed.by_path("company/widgets/errors.py")
    assert errors is not None
    assert errors.classes == ("NewError",)


def test_build_and_cache_then_load_or_build_reads_the_cache(tmp_path: Path) -> None:
    repo = _sample_repo(tmp_path)
    cache = tmp_path / ".cache" / "repo_map.json"
    written = build_and_cache(repo, cache, roots=("company", "tools", "tests"))
    assert cache.is_file()

    loaded = load_or_build(repo, cache, roots=("company", "tools", "tests"))
    assert loaded.to_dict() == written.to_dict()


def test_load_or_build_recovers_from_a_corrupt_cache(tmp_path: Path) -> None:
    repo = _sample_repo(tmp_path)
    cache = tmp_path / ".cache" / "repo_map.json"
    cache.parent.mkdir(parents=True)
    cache.write_text("{not json", encoding="utf-8")

    recovered = load_or_build(repo, cache, roots=("company", "tools", "tests"))
    assert recovered.by_path("company/widgets/spinner.py") is not None
    assert cache.read_text(encoding="utf-8") != "{not json"


def test_symbol_spans_cover_classes_methods_and_functions(tmp_path: Path) -> None:
    repo = _sample_repo(tmp_path)
    repo_map = build_repo_map(repo, roots=("company", "tools", "tests"))
    spinner = repo_map.by_path("company/widgets/spinner.py")
    assert spinner is not None
    names = {s.qualified_name: s for s in spinner.symbols}
    assert set(names) == {"Spinner", "Spinner.spin", "start_spinner"}
    assert names["Spinner"].kind == "class"
    assert names["Spinner.spin"].kind == "method"
    assert names["start_spinner"].kind == "function"
    # Line 6 is `class Spinner:`, line 7 is its one method.
    assert names["Spinner"].start_line == 6
    assert names["Spinner.spin"].start_line == 7
    assert spinner.symbol("Spinner.spin") is names["Spinner.spin"]
    assert spinner.symbol("does-not-exist") is None


def test_reverse_production_index_resolves_real_imports(tmp_path: Path) -> None:
    """`spinner.py` imports `errors.py` directly - a production dependency,
    not a test one - so `errors.py` must show `spinner.py` as a dependent."""
    repo = _sample_repo(tmp_path)
    repo_map = build_repo_map(repo, roots=("company", "tools", "tests"))
    assert repo_map.production_dependents["company/widgets/errors.py"] == (
        "company/widgets/spinner.py",
    )
    assert "company/widgets/spinner.py" not in repo_map.production_dependents


def test_reverse_production_index_excludes_self_imports(tmp_path: Path) -> None:
    repo = _sample_repo(tmp_path)
    repo_map = build_repo_map(repo, roots=("company", "tools", "tests"))
    for path, dependents in repo_map.production_dependents.items():
        assert path not in dependents


def test_neighborhood_bundles_symbols_dependents_and_tests(tmp_path: Path) -> None:
    repo = _sample_repo(tmp_path)
    repo_map = build_repo_map(repo, roots=("company", "tools", "tests"))
    hood = neighborhood(repo_map, "company/widgets/errors.py")
    assert hood.found is True
    assert hood.path == "company/widgets/errors.py"
    assert any(s.qualified_name == "SpinError" for s in hood.symbols)
    assert hood.dependents == ("company/widgets/spinner.py",)
    assert hood.tests == ("tests/test_company_widgets_errors.py",)


def test_neighborhood_reports_entry_points_among_dependents(tmp_path: Path) -> None:
    repo = _sample_repo(tmp_path)
    _write(
        repo,
        "tools/actuator/launcher.py",
        '"""Launch a process for a widget."""\n\n'
        "from company.widgets.errors import SpinError\n\n"
        "def main() -> int:\n"
        "    return 0\n",
    )
    repo_map = build_repo_map(repo, roots=("company", "tools", "tests"))
    hood = neighborhood(repo_map, "company/widgets/errors.py")
    assert "tools/actuator/launcher.py" in hood.dependents
    assert hood.entry_points == ("tools/actuator/launcher.py",)


def test_neighborhood_of_an_unknown_path_reports_not_found(tmp_path: Path) -> None:
    repo = _sample_repo(tmp_path)
    repo_map = build_repo_map(repo, roots=("company", "tools", "tests"))
    hood = neighborhood(repo_map, "company/widgets/does_not_exist.py")
    assert hood.found is False
    assert hood.symbols == ()
    assert hood.dependents == ()


def test_neighborhood_is_bounded_by_its_limits(tmp_path: Path) -> None:
    repo = _sample_repo(tmp_path)
    repo_map = build_repo_map(repo, roots=("company", "tools", "tests"))
    hood = neighborhood(repo_map, "company/widgets/spinner.py", symbol_limit=1)
    assert len(hood.symbols) == 1


def test_symbol_span_to_dict_and_from_dict_round_trip() -> None:
    span = SymbolSpan(qualified_name="Spinner.spin", kind="method", start_line=6, end_line=6)
    assert SymbolSpan.from_dict(span.to_dict()) == span


def test_module_map_to_dict_and_from_dict_round_trip() -> None:
    module = ModuleMap(
        path="company/widgets/spinner.py",
        owner="company/widgets",
        classes=("Spinner",),
        functions=("start_spinner",),
        imports=("os",),
        doc="Spin a widget until it stops.",
        lines=8,
        is_entry_point=False,
    )
    assert ModuleMap.from_dict(module.to_dict()) == module
