"""The research package that should exist before a significant video is made.

Section 12 of the brief. This phase builds the data model, the validation and
the store slot - nothing here is wired to production, and nothing in production
imports it. Connecting a dossier to a render is a later phase with its own gate.

## The two fields that make it an experiment rather than a plan

`ExperimentDefinition` requires `variables_changed` and `variables_locked`, and
refuses any variable that appears in both. Constitution rule 9 asks for isolated
variables and a statement of what was changed and what was held; a plan that
lists "camera, pacing, lighting, colour" as changed and nothing as locked has
not designed an experiment, it has described a rewrite. The overlap check is
the cheap half and it catches the common real mistake: a variable copied into
both lists while the plan was being edited.

`predicted_observation` is required for the same reason `Hypothesis` requires
it in the knowledge store - a prediction written after the render is not a
prediction.

## Kill conditions

`kill_conditions` is required and non-empty. The expensive failure in a video
pipeline is not a bad idea; it is a bad idea nobody agreed in advance to stop.
The field is retained verbatim through the dossier's life - there is no
transition in this module that edits or clears it, because a kill condition
that can be quietly dropped when it starts to bite is not a kill condition.

## Superiority targets, again

A video dossier carries its own `SuperiorityTarget`s (at least one). They are
the same type the opportunity uses, so a target that was `unknown_pending_
measurement` at the opportunity stage can be carried forward as `measured` once
somebody measured it, without a second vocabulary for the same idea.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import Enum
from typing import Any, ClassVar

from ai_platform.serde import as_date, as_tuple
from intelligence.research.common import (
    Complexity,
    Evidence,
    ResearchConfidence,
    assert_nonempty,
    assert_research_id,
    assert_slug,
    assert_slugs,
    assert_text,
    assert_texts,
    evidence_tuple,
)
from intelligence.research.errors import ResearchError
from intelligence.research.opportunity import SuperiorityTarget


class DossierStatus(Enum):
    """Where the research package is, not where the video is."""

    DRAFT = "draft"
    READY_FOR_PRODUCTION = "ready_for_production"
    IN_PRODUCTION = "in_production"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


@dataclass(frozen=True)
class ExperimentDefinition:
    """One question, one prediction, and an honest list of what moved."""

    question: str
    predicted_observation: str
    method: str
    variables_changed: tuple[str, ...]
    variables_locked: tuple[str, ...]

    def __post_init__(self) -> None:
        assert_text(self.question, "experiment question")
        assert_text(
            self.predicted_observation,
            "experiment predicted_observation (what we expect to see if the hypothesis holds)",
        )
        assert_text(self.method, "experiment method (how the result will be judged)")
        object.__setattr__(
            self, "variables_changed", assert_slugs(self.variables_changed, "variables_changed")
        )
        object.__setattr__(
            self, "variables_locked", assert_slugs(self.variables_locked, "variables_locked")
        )
        assert_nonempty(
            self.variables_changed,
            "variables_changed",
            "an experiment that changed nothing is a re-render (constitution rule 9)",
        )
        assert_nonempty(
            self.variables_locked,
            "variables_locked",
            "name what is held constant, or the result cannot be attributed to anything",
        )
        overlap = sorted(set(self.variables_changed) & set(self.variables_locked))
        if overlap:
            raise ResearchError(
                f"variable(s) {', '.join(overlap)} are listed as both changed and locked. "
                "A variable is one or the other; the result means nothing otherwise."
            )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExperimentDefinition:
        return cls(
            question=data["question"],
            predicted_observation=data["predicted_observation"],
            method=data["method"],
            variables_changed=as_tuple(data.get("variables_changed")),
            variables_locked=as_tuple(data.get("variables_locked")),
        )


@dataclass(frozen=True)
class VideoPlan:
    """Seven answers about the video itself, all required.

    Hook, commitment, middle rhythm and payoff are the viewer's experience;
    visual, camera and audio are how it is delivered. Splitting them into a
    separate object from the dossier keeps the plan reviewable on its own - the
    creative director reads this, not the whole file.
    """

    hook: str
    viewer_commitment: str
    middle_rhythm: str
    payoff: str
    visual: str
    camera: str
    audio: str

    FIELDS: ClassVar[tuple[str, ...]] = (
        "hook",
        "viewer_commitment",
        "middle_rhythm",
        "payoff",
        "visual",
        "camera",
        "audio",
    )

    def __post_init__(self) -> None:
        for field in self.FIELDS:
            assert_text(getattr(self, field), f"video plan {field}")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VideoPlan:
        return cls(**{field: data[field] for field in cls.FIELDS})


@dataclass(frozen=True)
class VideoIntelligenceDossier:
    """Everything known and intended about one video, before it is made."""

    kind: ClassVar[str] = "video_dossier"

    id: str
    video_id: str
    format_family: str
    objective: str
    author: str
    created: dt.date
    known_weakness: str
    hypothesis: str
    plan: VideoPlan
    experiment: ExperimentDefinition
    superiority_targets: tuple[SuperiorityTarget, ...]
    kill_conditions: tuple[str, ...]
    confidence: ResearchConfidence
    cost_estimate: Complexity = Complexity.UNKNOWN
    cost_basis: str = ""
    risks: tuple[str, ...] = ()
    previous_findings: tuple[Evidence, ...] = ()
    reference_case_ids: tuple[str, ...] = ()
    opportunity_ids: tuple[str, ...] = ()
    status: DossierStatus = DossierStatus.DRAFT
    notes: str = ""

    def __post_init__(self) -> None:
        assert_research_id(self.id, "video_dossier")
        assert_slug(self.video_id, "video_id")
        assert_slug(self.format_family, "format_family")
        assert_text(self.objective, "dossier objective (the business or audience goal)")
        assert_text(self.author, "dossier author")
        assert_text(
            self.known_weakness,
            "known_weakness (what the last one got wrong, or 'none known, because ...')",
        )
        assert_text(self.hypothesis, "dossier hypothesis")
        if not isinstance(self.created, dt.date):
            raise ResearchError("a video dossier must record the date it was written")

        object.__setattr__(
            self, "kill_conditions", assert_texts(self.kill_conditions, "kill_conditions")
        )
        object.__setattr__(self, "risks", assert_texts(self.risks, "risks"))
        object.__setattr__(
            self, "previous_findings", evidence_tuple(self.previous_findings)
        )
        assert_nonempty(
            self.kill_conditions,
            "kill_conditions",
            "state in advance what would stop this video; a kill condition agreed "
            "afterwards has never stopped anything",
        )
        assert_nonempty(
            self.superiority_targets,
            "superiority_targets",
            "state at least one dimension this must beat; 'make it better' is not an "
            "acceptance criterion (company/constitution.md)",
        )

        dimensions = [t.dimension for t in self.superiority_targets]
        if len(set(dimensions)) != len(dimensions):
            raise ResearchError(
                f"video_dossier {self.id!r}: two superiority targets claim the same dimension"
            )

        for field, kind in (
            ("reference_case_ids", "reference_case"),
            ("opportunity_ids", "opportunity"),
        ):
            ids = as_tuple(getattr(self, field))
            for value in ids:
                assert_research_id(value, kind)
            if len(set(ids)) != len(ids):
                raise ResearchError(f"video_dossier {self.id!r}: duplicate id in {field}")
            object.__setattr__(self, field, ids)

        if self.cost_estimate is not Complexity.UNKNOWN and not self.cost_basis.strip():
            raise ResearchError(
                f"video_dossier {self.id!r}: cost_estimate {self.cost_estimate.value!r} "
                "without a cost_basis. An estimate nobody can check is a number."
            )
        if self.status is DossierStatus.READY_FOR_PRODUCTION and not self.experiment.variables_locked:
            raise ResearchError(
                f"video_dossier {self.id!r}: cannot be ready for production with nothing "
                "locked"
            )

    @property
    def changed_and_locked(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        return self.experiment.variables_changed, self.experiment.variables_locked

    @property
    def unmeasured_targets(self) -> tuple[SuperiorityTarget, ...]:
        from intelligence.research.opportunity import TargetStatus

        return tuple(
            t
            for t in self.superiority_targets
            if t.status is TargetStatus.UNKNOWN_PENDING_MEASUREMENT
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VideoIntelligenceDossier:
        return cls(
            id=data["id"],
            video_id=data["video_id"],
            format_family=data["format_family"],
            objective=data["objective"],
            author=data["author"],
            created=as_date(data["created"], "created"),
            known_weakness=data["known_weakness"],
            hypothesis=data["hypothesis"],
            plan=VideoPlan.from_dict(data["plan"]),
            experiment=ExperimentDefinition.from_dict(data["experiment"]),
            superiority_targets=tuple(
                SuperiorityTarget.from_dict(t) for t in data.get("superiority_targets", ())
            ),
            kill_conditions=as_tuple(data.get("kill_conditions")),
            confidence=ResearchConfidence.from_dict(data["confidence"]),
            cost_estimate=Complexity(data.get("cost_estimate", "unknown")),
            cost_basis=data.get("cost_basis", ""),
            risks=as_tuple(data.get("risks")),
            previous_findings=evidence_tuple(data.get("previous_findings")),
            reference_case_ids=as_tuple(data.get("reference_case_ids")),
            opportunity_ids=as_tuple(data.get("opportunity_ids")),
            status=DossierStatus(data.get("status", "draft")),
            notes=data.get("notes", ""),
        )
