"""P6C production integration - experience never moves authority (merged tree).

Written by the P6C integration session; archived here, never in tests/.
"""

from __future__ import annotations

import dataclasses
import json
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
    _normalised,
    _runner,
    without_advice,
    repository,
)
from tools.engineering_runner.experience import AUTHORITY_KEYS, ExperienceAdvice, ExperienceAdviceRejected

# The package's list, by the key a producer would have to use to say it.
PACKAGE_AUTHORITY = {
    "may_read": "may_read",
    "may_not_read": "may_not_read",
    "may_write": "may_write",
    "required_tests": "required_tests",
    "reasoning class": "reasoning_class",
    "risk": "risk",
    "specialist domain": "employee",
    "merge authority": "authorizes_merge",
    "deploy authority": "deploy",
    "publish authority": "publish",
    "readiness": "readiness",
    "model-tier gate": "resource_profile",
}


@pytest.mark.parametrize("label", sorted(PACKAGE_AUTHORITY))
@pytest.mark.parametrize("where", ["top-nested", "suggestion", "measurement-deep"])
def test_every_listed_authority_key_is_refused_at_any_depth(label, where):
    key = PACKAGE_AUTHORITY[label]
    assert key in AUTHORITY_KEYS, key
    if where == "top-nested":
        payload = _experience_payload(resource_history=[{key: "x"}])
    elif where == "suggestion":
        payload = _experience_payload(suggested_files=[{"path": "tests/test_subject.py", "reason": "r", key: "x"}])
    else:
        payload = _experience_payload(measurement={"a": [{"b": {key: ["subject"]}}]})
    with pytest.raises(ExperienceAdviceRejected):
        ExperienceAdvice.parse(payload, work_order_id=WORK_ORDER)


def test_the_parsed_advice_has_no_field_that_could_carry_authority():
    assert [f.name for f in dataclasses.fields(ExperienceAdvice)] == [
        "work_order_id", "fingerprint", "status", "abstention", "precedents", "warnings", "files", "tests",
    ]


def test_unlisted_words_ride_nowhere(repository, without_advice):
    """Words outside the vocabulary (model tier, domain, merge) in an unread field:
    accepted by the parser, and nothing about the run moves."""
    advice = _experience_payload(measurement={"model_tier": "strongest", "specialist_domain": "all", "merge": True})
    control = ExperiencedControlPlane(repository["base"], states=["planning"], advice=advice)
    backend = ScriptedBackend(edit=_in_scope_edit)
    report = _runner(repository, backend, control).run_one(WORK_ORDER)
    assert report.outcome == COMPLETED, report.reason
    _same_authority(repository, report, backend, without_advice, expect_block=True)


def test_wellformed_advice_moves_no_authority(repository, without_advice):
    control = ExperiencedControlPlane(repository["base"], states=["planning"], advice=_experience_payload())
    backend = ScriptedBackend(edit=_in_scope_edit)
    report = _runner(repository, backend, control).run_one(WORK_ORDER)
    assert report.outcome == COMPLETED, report.reason
    _same_authority(repository, report, backend, without_advice, expect_block=True)


def _same_authority(repository: dict[str, Any], report: Any, backend: ScriptedBackend, without_advice: dict[str, Any], *, expect_block: bool) -> None:
    stage = Path(report.run_dir) / "developer-01"
    developer = [item for item in backend.launched if item.role == "developer"][0]
    assert bool(_experience_block(developer.instructions)) is expect_block
    envelope = _normalised(json.loads((stage / "authority.json").read_text("utf-8")), repository)
    assert envelope["envelope"] == without_advice["authority"]["envelope"]
    for name in ("model", "allowed_tools", "disallowed_tools", "read_only", "timeout_s", "max_cost"):
        assert _normalised(getattr(developer, name), repository) == without_advice["session"][name], name
    resources = _normalised(json.loads((stage / "resources.json").read_text("utf-8")), repository)
    assert resources["adaptive_model_routing"] == without_advice["resources"]["adaptive_model_routing"]
    assert report.final_state == without_advice["final_state"] == "ready_for_approval"
    assert [s.stage for s in report.stages] == without_advice["stages"]
