"""P6C production integration - B1 probes on the merged tree.

Written by the P6C integration session; archived here, never in tests/. Every case
drives the real `EngineeringRunner.run_one -> _developer_stage -> _experience`
path; only the control plane's answer (or one seam) is scripted. The harness
comes from the repository's own runner suite so the no-advice comparison is
the same whole-stage equality the suite uses, but the cases, and the extra
assertions, are this session's.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.test_external_engineering_runner import (  # noqa: F401 - fixtures are used by name
    COMPLETED,
    WORK_ORDER,
    ExperiencedControlPlane,
    ScriptedBackend,
    _experience_block,
    _experience_payload,
    _in_scope_edit,
    _runner,
    _runs_as_without_advice,
    repository,
    without_advice,
)
from tools.engineering_runner import experience as experience_module
from tools.engineering_runner import runner as runner_module


def _run(repository: dict[str, Any], advice: Any) -> tuple[Any, ExperiencedControlPlane, ScriptedBackend]:
    control = ExperiencedControlPlane(repository["base"], states=["planning"], advice=advice)
    backend = ScriptedBackend(edit=_in_scope_edit)
    report = _runner(repository, backend, control).run_one(WORK_ORDER)
    return report, control, backend


def _explicit(report: Any, backend: ScriptedBackend, without_advice: dict[str, Any]) -> None:
    """The package's named requirements, asserted one by one on top of the whole-stage equality."""
    stage = Path(report.run_dir) / "developer-01"
    developer = [item for item in backend.launched if item.role == "developer"][0]
    assert "## Prior experience" not in developer.instructions
    context = json.loads((stage / "execution-context.json").read_text("utf-8"))
    assert not any("prior experience" in item["reason"].lower() for item in context["files"])
    assert context["files"] == without_advice["execution_context"]["files"]
    envelope = json.loads((stage / "authority.json").read_text("utf-8"))["envelope"]
    for key in ("may_read", "may_not_read", "may_write", "required_tests"):
        assert envelope.get(key) == without_advice["authority"]["envelope"].get(key), key
    assert developer.model == without_advice["session"]["model"]


def _nested_mapping(depth: int) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for _ in range(depth):
        value = {"n": value}
    return value


# 1. non-empty mapping as precedent `why`
def test_nonempty_mapping_why(repository, without_advice):
    precedent = _experience_payload()["precedents"][0]
    advice = _experience_payload(precedents=[{**precedent, "why": {"a": "b", "c": ["d"]}}])
    report, control, backend = _run(repository, advice)
    assert ("experience", WORK_ORDER) in control.calls
    record = _runs_as_without_advice(repository, backend, report, without_advice)
    assert "why must be a list of strings, not dict" in record["rejected"]
    _explicit(report, backend, without_advice)


# 2. malformed warning `lines` (three shapes)
@pytest.mark.parametrize(
    "lines, expect",
    [
        ({"k": "v"}, "lines must be a list of strings, not dict"),
        ("a bare string", "lines must be a list of strings, not str"),
        (["ok", 7], "lines[1] must be a string, not int"),
    ],
)
def test_malformed_warning_lines(repository, without_advice, lines, expect):
    warning = _experience_payload()["warnings"][0]
    report, _, backend = _run(repository, _experience_payload(warnings=[{**warning, "lines": lines}]))
    record = _runs_as_without_advice(repository, backend, report, without_advice)
    assert expect in record["rejected"], record["rejected"]
    _explicit(report, backend, without_advice)


# 3/4. unexpected RuntimeError from parse / from revalidate
@pytest.mark.parametrize("seam", ["parse", "revalidate"])
def test_unexpected_runtime_error(repository, without_advice, monkeypatch, seam):
    def boom(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError(f"integration probe: {seam} blew up")

    if seam == "parse":
        monkeypatch.setattr(runner_module.ExperienceAdvice, "parse", staticmethod(boom))
    else:
        monkeypatch.setattr(runner_module, "revalidate", boom)
    report, _, backend = _run(repository, _experience_payload())
    record = _runs_as_without_advice(repository, backend, report, without_advice)
    assert record["rejected"] == f"RuntimeError: integration probe: {seam} blew up"
    _explicit(report, backend, without_advice)


# 5a. forced RecursionError at the parse seam
def test_forced_recursion_error_at_parse(repository, without_advice, monkeypatch):
    def deep(*args: Any, **kwargs: Any) -> Any:
        raise RecursionError("maximum recursion depth exceeded (forced by integration probe)")

    monkeypatch.setattr(runner_module.ExperienceAdvice, "parse", staticmethod(deep))
    report, _, backend = _run(repository, _experience_payload())
    record = _runs_as_without_advice(repository, backend, report, without_advice)
    assert record["rejected"].startswith("RecursionError: ")
    _explicit(report, backend, without_advice)


# 5b. forced RecursionError at the real recursion site, inside the real parse
def test_forced_recursion_error_inside_real_parse(repository, without_advice, monkeypatch):
    calls: list[int] = []

    def deep(value: Any, where: str = "advice") -> tuple[str, ...]:
        calls.append(1)
        raise RecursionError("maximum recursion depth exceeded (at _authority_keys, forced)")

    monkeypatch.setattr(experience_module, "_authority_keys", deep)
    report, _, backend = _run(repository, _experience_payload())
    assert calls, "the real parse reached the authority scan"
    record = _runs_as_without_advice(repository, backend, report, without_advice)
    assert record["rejected"].startswith("RecursionError: ")
    _explicit(report, backend, without_advice)


# 5c. a genuinely deep payload, nested just past the recursion limit, built
#     without the suite's depth (+500) so construction stays inside budget.
def test_genuine_recursion_just_past_the_limit(repository, without_advice):
    depth = sys.getrecursionlimit() + 50
    advice = _experience_payload(measurement={"trace": _nested_mapping(depth)})
    assert json.loads(json.dumps(advice)) == advice  # the courier would deliver it
    with pytest.raises(RecursionError):
        experience_module._authority_keys(advice)  # the real scan cannot walk it
    report, _, backend = _run(repository, advice)
    record = _runs_as_without_advice(repository, backend, report, without_advice)
    assert record["rejected"].startswith("RecursionError: "), record["rejected"]
    _explicit(report, backend, without_advice)


# 6/7. OSError writing either experience artifact
@pytest.mark.parametrize("artifact", ["experience-advice.json", "experience.json"])
def test_oserror_writing_artifact(repository, without_advice, monkeypatch, artifact):
    real = runner_module.write_json
    seen: list[str] = []

    def write_json(path: Path, payload: Any) -> Path:
        if Path(path).name == artifact:
            seen.append(artifact)
            raise PermissionError(13, "integration probe: access denied", str(path))
        return real(path, payload)

    monkeypatch.setattr(runner_module, "write_json", write_json)
    report, _, backend = _run(repository, _experience_payload())
    assert seen == [artifact]
    record = _runs_as_without_advice(repository, backend, report, without_advice)
    assert record["rejected"].startswith("PermissionError: ")
    _explicit(report, backend, without_advice)


# 8. real process-level control still propagates
@pytest.mark.parametrize("control_exc", [KeyboardInterrupt, SystemExit, GeneratorExit])
@pytest.mark.parametrize("seam", ["parse", "revalidate", "write"])
def test_process_control_propagates(repository, monkeypatch, control_exc, seam):
    def stop(*args: Any, **kwargs: Any) -> Any:
        raise control_exc()

    if seam == "parse":
        monkeypatch.setattr(runner_module.ExperienceAdvice, "parse", staticmethod(stop))
    elif seam == "revalidate":
        monkeypatch.setattr(runner_module, "revalidate", stop)
    else:
        real = runner_module.write_json

        def write_json(path: Path, payload: Any) -> Path:
            if Path(path).name == "experience-advice.json":
                stop()
            return real(path, payload)

        monkeypatch.setattr(runner_module, "write_json", write_json)
    control = ExperiencedControlPlane(repository["base"], states=["planning"], advice=_experience_payload())
    backend = ScriptedBackend(edit=_in_scope_edit)
    with pytest.raises(control_exc):
        _runner(repository, backend, control).run_one(WORK_ORDER)
    assert [item for item in backend.launched if item.role == "developer"] == []


# Control: well-formed advice still reaches the brief (the probes are not vacuous)
def test_wellformed_advice_still_used(repository):
    report, _, backend = _run(repository, _experience_payload())
    assert report.outcome == COMPLETED, report.reason
    developer = [item for item in backend.launched if item.role == "developer"][0]
    assert "wo-earlier" in _experience_block(developer.instructions)
    assert (Path(report.run_dir) / "developer-01" / "experience.json").exists()
