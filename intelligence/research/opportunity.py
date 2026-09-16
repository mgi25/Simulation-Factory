"""An opportunity: what we could make, why we believe it, and how it beats what exists.

## A video idea is not a format opportunity

Section 5 of the brief asks for the distinction and this module makes it a type
error to blur it. `FormatClass` has three values, and two of them require a
`FormatFamily`:

    SINGLE_VIDEO       one video. May not carry a family - if it has a reusable
                       core loop and a variation space, it was not a single
                       video and the classification is wrong.
    FORMAT_EXTENSION   a new variable inside a family we already run.
    NEW_FORMAT_FAMILY  a new reusable loop.

`FormatFamily` demands the five things that make a family a family: a reusable
core loop, the dimensions that vary between episodes, the variation space, the
systems and assets that get reused, and the audience question that survives
from one episode to the next. "Marble race but in a volcano" fills none of them
in, which is the useful outcome.

## Superiority targets can say "I do not know"

Section 6, and the honest part is `TargetStatus`:

    MEASURED                      we measured the reference. Requires a
                                  `Measurement`, which requires evidence.
    QUALITATIVE                   a described intent, no number claimed. May
                                  not carry a reference measurement - a
                                  qualitative target with a number attached is
                                  a measured one that skipped the evidence.
    UNKNOWN_PENDING_MEASUREMENT   we know the dimension matters and have not
                                  measured it. Requires a `measurement_plan`
                                  and refuses a reference number.

The third status is the one that makes the other two trustworthy. Without it,
every unmeasured dimension either gets dropped or gets a plausible number, and
the plausible number is indistinguishable from a real one a month later.

## Stage is set by people

`OpportunityStage.PROTOTYPE_RECOMMENDED` requires `reviewed_by`, `reviewed_on`
and at least one superiority target. Nothing in `scoring.py` returns a stage,
and no function in this package promotes a dossier on its own - the brief says
do not automatically approve prototypes, and the way to guarantee that is for
approval to have no code path at all.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import Enum
from typing import Any, ClassVar

from ai_platform.serde import as_date, as_opt_date, as_tuple
from intelligence.research.common import (
    Complexity,
    Evidence,
    Measurement,
    ResearchConfidence,
    assert_nonempty,
    assert_research_id,
    assert_slug,
    assert_slugs,
    assert_text,
    assert_texts,
    evidence_tuple,
    opt_measurement,
)
from intelligence.research.errors import ResearchError

KNOWN_SUPERIORITY_DIMENSIONS: tuple[str, ...] = (
    "hook_clarity",
    "event_density",
    "mobile_readability",
    "camera_continuity",
    "visual_depth",
    "original_mechanics",
    "payoff_clarity",
    "audio_feedback",
    "repeatability",
    "production_efficiency",
)
"""The ten the brief names. Open tags allowed; this fixes the spelling."""


class FormatClass(Enum):
    SINGLE_VIDEO = "single_video"
    FORMAT_EXTENSION = "format_extension"
    NEW_FORMAT_FAMILY = "new_format_family"


FAMILY_REQUIRED: frozenset[FormatClass] = frozenset(
    {FormatClass.FORMAT_EXTENSION, FormatClass.NEW_FORMAT_FAMILY}
)


class OpportunityStage(Enum):
    DISCOVERED = "discovered"
    RESEARCHING = "researching"
    CANDIDATE = "candidate"
    PROTOTYPE_RECOMMENDED = "prototype_recommended"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class TargetStatus(Enum):
    MEASURED = "measured"
    QUALITATIVE = "qualitative"
    UNKNOWN_PENDING_MEASUREMENT = "unknown_pending_measurement"


@dataclass(frozen=True)
class FormatFamily:
    """What makes a thing repeatable, in the five fields that answer it."""

    family_id: str
    reusable_core_loop: str
    variable_dimensions: tuple[str, ...]
    variation_space: str
    audience_question: str
    differentiation: str
    reusable_systems: tuple[str, ...] = ()
    estimated_episodes: int | None = None

    def __post_init__(self) -> None:
        assert_slug(self.family_id, "family_id")
        assert_text(self.reusable_core_loop, "reusable_core_loop")
        assert_text(self.variation_space, "variation_space")
        assert_text(self.audience_question, "family audience_question")
        assert_text(self.differentiation, "family differentiation")
        object.__setattr__(
            self,
            "variable_dimensions",
            assert_texts(self.variable_dimensions, "variable_dimensions"),
        )
        object.__setattr__(
            self, "reusable_systems", assert_texts(self.reusable_systems, "reusable_systems")
        )
        assert_nonempty(
            self.variable_dimensions,
            "variable_dimensions",
            "name what changes between episodes, or there is one episode and no family",
        )
        if self.estimated_episodes is not None:
            if isinstance(self.estimated_episodes, bool) or not isinstance(
                self.estimated_episodes, int
            ):
                raise ResearchError(
                    f"estimated_episodes must be a whole number or None, got "
                    f"{self.estimated_episodes!r}"
                )
            if self.estimated_episodes < 2:
                raise ResearchError(
                    f"estimated_episodes {self.estimated_episodes} does not describe a "
                    "family. Classify the opportunity as single_video instead."
                )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FormatFamily:
        return cls(
            family_id=data["family_id"],
            reusable_core_loop=data["reusable_core_loop"],
            variable_dimensions=as_tuple(data.get("variable_dimensions")),
            variation_space=data["variation_space"],
            audience_question=data["audience_question"],
            differentiation=data["differentiation"],
            reusable_systems=as_tuple(data.get("reusable_systems")),
            estimated_episodes=data.get("estimated_episodes"),
        )


@dataclass(frozen=True)
class SuperiorityTarget:
    """One dimension in which our work must beat the reference, and its status.

    The constitution says "make it better" is not an acceptance criterion. This
    is the record that replaces it: a named dimension, what exceeding it means
    here, and an honest statement of whether anyone has actually measured the
    reference yet.
    """

    dimension: str
    intent: str
    status: TargetStatus
    reference_observation: Measurement | None = None
    our_target: Measurement | None = None
    measurement_plan: str = ""
    evidence: tuple[Evidence, ...] = ()
    note: str = ""

    def __post_init__(self) -> None:
        assert_slug(self.dimension, "superiority dimension")
        assert_text(self.intent, "superiority intent (what exceeding it means here)")
        object.__setattr__(self, "evidence", evidence_tuple(self.evidence))

        if self.status is TargetStatus.MEASURED:
            if self.reference_observation is None:
                raise ResearchError(
                    f"superiority target {self.dimension!r} is marked measured but carries "
                    "no reference_observation. Attach the Measurement, or mark it "
                    "unknown_pending_measurement."
                )
        else:
            if self.reference_observation is not None:
                raise ResearchError(
                    f"superiority target {self.dimension!r} is {self.status.value!r} yet "
                    "carries a reference_observation. A number about the reference makes "
                    "it measured; set the status that matches the evidence."
                )
            if self.status is TargetStatus.UNKNOWN_PENDING_MEASUREMENT and not self.measurement_plan.strip():
                raise ResearchError(
                    f"superiority target {self.dimension!r} is pending measurement but "
                    "names no measurement_plan. Say how it would be measured, or the "
                    "dimension will stay unknown forever."
                )

    @property
    def is_novel_dimension(self) -> bool:
        return self.dimension not in KNOWN_SUPERIORITY_DIMENSIONS

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SuperiorityTarget:
        return cls(
            dimension=data["dimension"],
            intent=data["intent"],
            status=TargetStatus(data["status"]),
            reference_observation=opt_measurement(data.get("reference_observation")),
            our_target=opt_measurement(data.get("our_target")),
            measurement_plan=data.get("measurement_plan", ""),
            evidence=evidence_tuple(data.get("evidence")),
            note=data.get("note", ""),
        )


@dataclass(frozen=True)
class OpportunityDossier:
    """What we could make, the evidence for it, and the shape of doing it well.

    `evidence` is required and non-empty: the brief's "which evidence supports
    it?" is the difference between an opportunity and an idea, and a dossier
    that cannot cite anything has not left the idea stage. `limitations` is
    required for the same reason from the other side - what this dossier does
    not establish is part of what it says.
    """

    kind: ClassVar[str] = "opportunity"

    id: str
    title: str
    statement: str
    author: str
    created: dt.date
    format_class: FormatClass
    viewer_question: str
    core_entertainment_loop: str
    channel_fit: str
    originality_path: str
    repeatability: str
    differentiation: str
    production_complexity: Complexity
    complexity_basis: str
    evidence: tuple[Evidence, ...]
    limitations: tuple[str, ...]
    confidence: ResearchConfidence
    family: FormatFamily | None = None
    source_ids: tuple[str, ...] = ()
    reference_case_ids: tuple[str, ...] = ()
    superiority_targets: tuple[SuperiorityTarget, ...] = ()
    technical_risks: tuple[str, ...] = ()
    content_risks: tuple[str, ...] = ()
    monetization_reuse: str = ""
    stage: OpportunityStage = OpportunityStage.DISCOVERED
    next_recommended_stage: OpportunityStage | None = None
    reviewed_by: str = ""
    reviewed_on: dt.date | None = None
    review_note: str = ""
    tags: tuple[str, ...] = ()
    notes: str = ""

    _PROSE: ClassVar[tuple[str, ...]] = (
        "title",
        "statement",
        "author",
        "viewer_question",
        "core_entertainment_loop",
        "channel_fit",
        "originality_path",
        "repeatability",
        "differentiation",
        "complexity_basis",
    )

    def __post_init__(self) -> None:
        assert_research_id(self.id, "opportunity")
        for field in self._PROSE:
            assert_text(getattr(self, field), f"opportunity {field}")
        if not isinstance(self.created, dt.date):
            raise ResearchError("an opportunity dossier must record the date it was written")

        object.__setattr__(self, "evidence", evidence_tuple(self.evidence))
        object.__setattr__(self, "limitations", assert_texts(self.limitations, "limitations"))
        object.__setattr__(
            self, "technical_risks", assert_texts(self.technical_risks, "technical_risks")
        )
        object.__setattr__(self, "content_risks", assert_texts(self.content_risks, "content_risks"))
        object.__setattr__(self, "tags", assert_slugs(self.tags, "opportunity tag"))

        assert_nonempty(
            self.evidence,
            "evidence",
            "an opportunity nobody can cite anything for is an idea (constitution rule 7)",
        )
        assert_nonempty(
            self.limitations,
            "limitations",
            "state what this dossier does not establish, or its confidence is unreadable",
        )

        for field, kind in (("source_ids", "source"), ("reference_case_ids", "reference_case")):
            ids = as_tuple(getattr(self, field))
            for value in ids:
                assert_research_id(value, kind)
            if len(set(ids)) != len(ids):
                raise ResearchError(f"opportunity {self.id!r}: duplicate id in {field}")
            object.__setattr__(self, field, ids)

        dimensions = [t.dimension for t in self.superiority_targets]
        if len(set(dimensions)) != len(dimensions):
            raise ResearchError(
                f"opportunity {self.id!r}: two superiority targets claim the same "
                "dimension. Merge them - the later one silently wins otherwise."
            )

        if self.format_class in FAMILY_REQUIRED and self.family is None:
            raise ResearchError(
                f"opportunity {self.id!r} is classified {self.format_class.value!r} but "
                "describes no FormatFamily. A repeatable format states its reusable loop, "
                "its variable dimensions and its variation space, or it is a single video."
            )
        if self.format_class is FormatClass.SINGLE_VIDEO and self.family is not None:
            raise ResearchError(
                f"opportunity {self.id!r} is classified single_video yet carries a "
                "FormatFamily. If it has a reusable loop and a variation space, classify "
                "it as format_extension or new_format_family."
            )

        if self.stage is OpportunityStage.PROTOTYPE_RECOMMENDED:
            if not self.reviewed_by.strip() or self.reviewed_on is None:
                raise ResearchError(
                    f"opportunity {self.id!r}: a prototype recommendation must name the "
                    "reviewer and the date. No code path sets this stage on its own."
                )
            if not self.superiority_targets:
                raise ResearchError(
                    f"opportunity {self.id!r}: recommending a prototype with no superiority "
                    "target leaves 'make it better' as the acceptance criterion, which the "
                    "constitution rejects."
                )
        if self.reviewed_on is not None and self.reviewed_on < self.created:
            raise ResearchError(
                f"opportunity {self.id!r}: reviewed_on {self.reviewed_on} predates "
                f"created {self.created}"
            )

    @property
    def measured_targets(self) -> tuple[SuperiorityTarget, ...]:
        return tuple(t for t in self.superiority_targets if t.status is TargetStatus.MEASURED)

    @property
    def pending_measurement(self) -> tuple[SuperiorityTarget, ...]:
        """Targets whose reference is admittedly unmeasured - the honest backlog."""
        return tuple(
            t
            for t in self.superiority_targets
            if t.status is TargetStatus.UNKNOWN_PENDING_MEASUREMENT
        )

    @property
    def is_repeatable_format(self) -> bool:
        return self.format_class in FAMILY_REQUIRED

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OpportunityDossier:
        raw_next = data.get("next_recommended_stage")
        return cls(
            id=data["id"],
            title=data["title"],
            statement=data["statement"],
            author=data["author"],
            created=as_date(data["created"], "created"),
            format_class=FormatClass(data["format_class"]),
            viewer_question=data["viewer_question"],
            core_entertainment_loop=data["core_entertainment_loop"],
            channel_fit=data["channel_fit"],
            originality_path=data["originality_path"],
            repeatability=data["repeatability"],
            differentiation=data["differentiation"],
            production_complexity=Complexity(data["production_complexity"]),
            complexity_basis=data["complexity_basis"],
            evidence=evidence_tuple(data.get("evidence")),
            limitations=as_tuple(data.get("limitations")),
            confidence=ResearchConfidence.from_dict(data["confidence"]),
            family=(
                None if data.get("family") is None else FormatFamily.from_dict(data["family"])
            ),
            source_ids=as_tuple(data.get("source_ids")),
            reference_case_ids=as_tuple(data.get("reference_case_ids")),
            superiority_targets=tuple(
                SuperiorityTarget.from_dict(t) for t in data.get("superiority_targets", ())
            ),
            technical_risks=as_tuple(data.get("technical_risks")),
            content_risks=as_tuple(data.get("content_risks")),
            monetization_reuse=data.get("monetization_reuse", ""),
            stage=OpportunityStage(data.get("stage", "discovered")),
            next_recommended_stage=None if raw_next is None else OpportunityStage(raw_next),
            reviewed_by=data.get("reviewed_by", ""),
            reviewed_on=as_opt_date(data.get("reviewed_on"), "reviewed_on"),
            review_note=data.get("review_note", ""),
            tags=as_tuple(data.get("tags")),
            notes=data.get("notes", ""),
        )
