"""Deterministic, no-model-call tests for the Benchmark C2 navigation providers.

These only prove the providers behave correctly and stay bounded; they never
invoke Sonnet/Claude. Ctags coverage runs unconditionally (the winget install
is locatable via CtagsProvider.locate_ctags_binary()). Tree-sitter's success
path is skipped when the isolated benchmark venv's packages are not on the
current interpreter (see docs/company_os_ai_resource_benchmark_c2_gdscript.md
for how to run this file under that venv to exercise it fully); the
unavailable-graceful-degradation path is always exercised.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from company.efficiency.providers import CodeIntelligenceQuery, CodeQueryKind
from tools.benchmark_c2.ctags_provider import CtagsProvider, locate_ctags_binary
from tools.benchmark_c2.treesitter_provider import MAX_BODY_CHARS, TreeSitterProvider
from tools.benchmark_c2.types import ProviderTelemetry

REPO_ROOT = Path(__file__).resolve().parents[1]


# --- Ctags -------------------------------------------------------------


def test_ctags_binary_is_locatable():
    assert locate_ctags_binary() is not None


@pytest.fixture(scope="module")
def ctags_index():
    provider = CtagsProvider(REPO_ROOT)
    assert provider.available, "ctags must be locatable for this suite to be meaningful"
    stats = provider.build_index()
    return provider, stats


def test_ctags_index_is_nonempty_and_bounded_build(ctags_index):
    _provider, stats = ctags_index
    assert stats.files_indexed > 0
    assert stats.tag_count > 0
    assert stats.build_time_ms < 5000


def test_ctags_definition_lookup_finds_known_symbol(ctags_index):
    provider, _stats = ctags_index
    result = provider.find_definition("_options")
    assert result.available
    assert result.matches
    assert any(m.file.endswith("course_scene.gd") for m in result.matches)
    assert all(m.start_line > 0 for m in result.matches)


def test_ctags_missing_symbol_is_clean_not_an_error(ctags_index):
    provider, _stats = ctags_index
    result = provider.find_definition("this_symbol_does_not_exist_xyz")
    assert result.available
    assert result.matches == ()
    assert result.reason


def test_ctags_output_ceiling_never_dumps_full_index(ctags_index):
    provider, stats = ctags_index
    result = provider.find_definition("_options")
    assert result.result_chars < stats.index_bytes


def test_ctags_query_kind_symbols_via_protocol(ctags_index):
    provider, _stats = ctags_index
    request = CodeIntelligenceQuery(CodeQueryKind.SYMBOLS, "_options")
    result = provider.query(request)
    assert result.available
    assert result.references
    assert result.provider == "ctags"


def test_ctags_query_kind_callers_is_honestly_unavailable(ctags_index):
    provider, _stats = ctags_index
    request = CodeIntelligenceQuery(CodeQueryKind.CALLERS, "_options")
    result = provider.query(request)
    assert result.available is False
    assert "reference" in result.reason or "caller" in result.reason


def test_ctags_provider_is_read_only(ctags_index, tmp_path):
    provider, _stats = ctags_index
    target = REPO_ROOT / "godot" / "scripts" / "course_scene.gd"
    before = target.read_bytes()
    provider.find_definition("_options")
    provider.symbols_in_file("godot/scripts/course_scene.gd")
    assert target.read_bytes() == before


def test_ctags_disabled_when_binary_missing(monkeypatch):
    monkeypatch.setenv("CTAGS_BIN", str(REPO_ROOT / "nonexistent_ctags_binary.exe"))
    monkeypatch.setattr("shutil.which", lambda name: None)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    provider = CtagsProvider(REPO_ROOT, ctags_bin=None)
    assert provider.available is False
    request = CodeIntelligenceQuery(CodeQueryKind.SYMBOLS, "_options")
    result = provider.query(request)
    assert result.available is False


def test_ctags_telemetry_records_each_call():
    telemetry = ProviderTelemetry()
    provider = CtagsProvider(REPO_ROOT, telemetry=telemetry)
    provider.build_index()
    provider.find_definition("_options")
    provider.find_definition("this_symbol_does_not_exist_xyz")
    assert telemetry.query_count == 2
    assert telemetry.error_count == 0


# --- tree-sitter ---------------------------------------------------------


def test_treesitter_unavailable_is_reported_cleanly_not_raised():
    provider = TreeSitterProvider(REPO_ROOT)
    request = CodeIntelligenceQuery(CodeQueryKind.SYMBOLS, "_options")
    result = provider.query(request)
    if provider.available:
        pytest.skip("tree-sitter-gdscript is installed on this interpreter")
    assert result.available is False
    assert "tree-sitter-gdscript" in result.reason


@pytest.fixture(scope="module")
def treesitter_index():
    provider = TreeSitterProvider(REPO_ROOT)
    if not provider.available:
        pytest.skip(
            "tree-sitter-gdscript not installed on this interpreter; "
            "run under the isolated benchmark venv to exercise this path"
        )
    stats = provider.build_index()
    return provider, stats


def test_treesitter_index_is_nonempty_and_bounded_build(treesitter_index):
    _provider, stats = treesitter_index
    assert stats.files_parsed > 0
    assert stats.parse_failures == 0
    assert stats.symbol_count > 0


def test_treesitter_definition_lookup_returns_span_and_body(treesitter_index):
    provider, _stats = treesitter_index
    result = provider.find_definition("_options", with_body=True)
    assert result.matches
    match = next(m for m in result.matches if m.file.endswith("course_scene.gd"))
    assert match.end_line is not None and match.end_line >= match.start_line
    assert match.body
    assert len(match.body) <= MAX_BODY_CHARS


def test_treesitter_missing_symbol_is_clean_not_an_error(treesitter_index):
    provider, _stats = treesitter_index
    result = provider.find_definition("this_symbol_does_not_exist_xyz")
    assert result.matches == ()
    assert result.reason


def test_treesitter_query_kind_dependencies_is_honestly_unavailable(treesitter_index):
    provider, _stats = treesitter_index
    request = CodeIntelligenceQuery(CodeQueryKind.DEPENDENCIES, "_options")
    result = provider.query(request)
    assert result.available is False


def test_treesitter_provider_is_read_only(treesitter_index):
    provider, _stats = treesitter_index
    target = REPO_ROOT / "godot" / "scripts" / "course_scene.gd"
    before = target.read_bytes()
    provider.find_definition("_options", with_body=True)
    assert target.read_bytes() == before


def test_treesitter_telemetry_records_each_call(treesitter_index):
    provider, _stats = treesitter_index
    telemetry = ProviderTelemetry()
    provider.telemetry = telemetry
    provider.find_definition("_options")
    provider.symbols_in_file("godot/scripts/course_scene.gd")
    assert telemetry.query_count == 2


# --- shared: no candidate sees another candidate's data ------------------


def test_providers_are_isolated_instances():
    ctags = CtagsProvider(REPO_ROOT)
    treesitter = TreeSitterProvider(REPO_ROOT)
    assert ctags.telemetry is not treesitter.telemetry
    assert ctags.name != treesitter.name
