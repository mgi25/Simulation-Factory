"""A structured reading of somebody else's video. Analysis, never a spec.

Constitution rule 8: references teach principles, mechanics, psychology and
quality targets; external protected expression is not copied. A `ReferenceCase`
is what that rule looks like as a form to fill in. It asks nine questions about
a reference and refuses to be built until all nine are answered, and the last
one is `OriginalityBoundary` - what must not be copied, and what abstract
principle may inspire something of our own.

## Why the sections are separate dataclasses

`HookAnalysis`, `CoreLoop`, `ViewerPsychology` and the rest could all be loose
fields on one record. They are not, because a flat record with thirty optional
strings gets filled in down to the first blank line and a reviewer cannot tell
a thin analysis from a complete one. A section that must be constructed as a
whole is a section that was either answered or not attempted.

## An empty field is not an answer, and "none" is

Every prose field in every section is required. That reads as heavy until you
try to fill one in: the honest entry for a reference with no identification
mechanism is "none - the marbles are unnamed and interchangeable", which is a
finding. An empty string is the absence of one. The validator cannot tell a
thoughtful analyst from a lazy one, but it can insist that every question was
looked at, and "none, because X" costs six words.

## Numbers arrive as `Measurement` or not at all

`seconds_to_premise`, `loop_seconds` and `cuts_per_10s` are optional, and when
present they are `Measurement`s carrying a method and an evidence pointer.
There is no float field anywhere in this module that a researcher can simply
type a plausible number into. The brief's prohibition on fabricated reference
measurements is enforced by the type, not by review.

## Mechanics tags are open

`KNOWN_MECHANICS` lists the six the brief names. It is documentation, not a
whitelist - a new mechanic is a slug, not a code change. The slug rule is the
only constraint, so that `battle_royale` and `battle royale` cannot both exist.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any, ClassVar

from ai_platform.serde import as_date, as_tuple
from intelligence.research.common import (
    Complexity,
    Measurement,
    ResearchConfidence,
    assert_nonempty,
    assert_reference,
    assert_research_id,
    assert_slugs,
    assert_text,
    assert_texts,
    opt_measurement,
)
from intelligence.research.errors import ResearchError

KNOWN_MECHANICS: tuple[str, ...] = (
    "race",
    "fight",
    "survival",
    "branching",
    "elimination",
    "destruction",
)
"""The six the brief names. Open tags are allowed; this is the shared spelling."""


@dataclass(frozen=True)
class HookAnalysis:
    """The first seconds: what is shown, what is understood, why anyone stays."""

    opening_image: str
    premise_comprehension: str
    viewer_commitment: str
    seconds_to_premise: Measurement | None = None

    def __post_init__(self) -> None:
        assert_text(self.opening_image, "hook opening_image (what appears immediately)")
        assert_text(self.premise_comprehension, "hook premise_comprehension")
        assert_text(self.viewer_commitment, "hook viewer_commitment (why a viewer stays)")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HookAnalysis:
        return cls(
            opening_image=data["opening_image"],
            premise_comprehension=data["premise_comprehension"],
            viewer_commitment=data["viewer_commitment"],
            seconds_to_premise=opt_measurement(data.get("seconds_to_premise")),
        )


@dataclass(frozen=True)
class CoreLoop:
    """Predict, watch, learn, predict again - the four beats, named separately.

    A reference whose loop cannot be written in these four fields usually has
    no loop, and finding that out is the point of making them four fields.
    """

    prediction: str
    event: str
    consequence: str
    renewed_prediction: str
    loop_seconds: Measurement | None = None

    def __post_init__(self) -> None:
        assert_text(self.prediction, "core loop prediction (what the viewer expects next)")
        assert_text(self.event, "core loop event (what actually happens)")
        assert_text(self.consequence, "core loop consequence (what it changes)")
        assert_text(self.renewed_prediction, "core loop renewed_prediction (the next question)")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CoreLoop:
        return cls(
            prediction=data["prediction"],
            event=data["event"],
            consequence=data["consequence"],
            renewed_prediction=data["renewed_prediction"],
            loop_seconds=opt_measurement(data.get("loop_seconds")),
        )


@dataclass(frozen=True)
class ViewerPsychology:
    """Six levers, six answers. "None, because X" is a valid answer to any."""

    curiosity: str
    identification: str
    suspense: str
    uncertainty: str
    anticipation: str
    payoff: str

    FIELDS: ClassVar[tuple[str, ...]] = (
        "curiosity",
        "identification",
        "suspense",
        "uncertainty",
        "anticipation",
        "payoff",
    )

    def __post_init__(self) -> None:
        for field in self.FIELDS:
            assert_text(getattr(self, field), f"viewer psychology {field}")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ViewerPsychology:
        return cls(**{field: data[field] for field in cls.FIELDS})


@dataclass(frozen=True)
class VisualAnalysis:
    hierarchy: str
    color: str
    materials: str
    readability: str
    environment: str
    depth: str

    FIELDS: ClassVar[tuple[str, ...]] = (
        "hierarchy",
        "color",
        "materials",
        "readability",
        "environment",
        "depth",
    )

    def __post_init__(self) -> None:
        for field in self.FIELDS:
            assert_text(getattr(self, field), f"visual {field}")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VisualAnalysis:
        return cls(**{field: data[field] for field in cls.FIELDS})


@dataclass(frozen=True)
class CameraEditAnalysis:
    shot_style: str
    continuity: str
    anticipation: str
    orientation: str
    pacing: str
    cuts_per_10s: Measurement | None = None

    FIELDS: ClassVar[tuple[str, ...]] = (
        "shot_style",
        "continuity",
        "anticipation",
        "orientation",
        "pacing",
    )

    def __post_init__(self) -> None:
        for field in self.FIELDS:
            assert_text(getattr(self, field), f"camera/edit {field}")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CameraEditAnalysis:
        return cls(
            cuts_per_10s=opt_measurement(data.get("cuts_per_10s")),
            **{field: data[field] for field in cls.FIELDS},
        )


@dataclass(frozen=True)
class AudioAnalysis:
    feedback: str
    escalation: str
    payoff: str

    FIELDS: ClassVar[tuple[str, ...]] = ("feedback", "escalation", "payoff")

    def __post_init__(self) -> None:
        for field in self.FIELDS:
            assert_text(getattr(self, field), f"audio {field}")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AudioAnalysis:
        return cls(**{field: data[field] for field in cls.FIELDS})


@dataclass(frozen=True)
class FormatAnalysis:
    """Can this be made again, and can it be made differently?"""

    repeatability: str
    variation_potential: str

    def __post_init__(self) -> None:
        assert_text(self.repeatability, "format repeatability")
        assert_text(self.variation_potential, "format variation_potential")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FormatAnalysis:
        return cls(
            repeatability=data["repeatability"],
            variation_potential=data["variation_potential"],
        )


@dataclass(frozen=True)
class TechnicalAnalysis:
    """What it would cost us, why we think so, and what we would reuse."""

    estimated_complexity: Complexity
    basis: str
    reusable_components: tuple[str, ...] = ()
    likely_risks: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        assert_text(self.basis, "technical basis (why this complexity estimate)")
        object.__setattr__(
            self, "reusable_components", assert_texts(self.reusable_components, "reusable_components")
        )
        object.__setattr__(self, "likely_risks", assert_texts(self.likely_risks, "likely_risks"))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TechnicalAnalysis:
        return cls(
            estimated_complexity=Complexity(data["estimated_complexity"]),
            basis=data["basis"],
            reusable_components=as_tuple(data.get("reusable_components")),
            likely_risks=as_tuple(data.get("likely_risks")),
        )


@dataclass(frozen=True)
class OriginalityBoundary:
    """The line rule 8 draws, drawn once per reference and drawn in writing.

    Both lists are required. `must_not_copy` alone would be a legal note;
    `transferable_principles` alone would be a licence to lift. The pair is the
    finding: this specific expression is theirs, that abstract mechanism is
    anyone's, and here is the reasoning that separated them.
    """

    must_not_copy: tuple[str, ...]
    transferable_principles: tuple[str, ...]
    rationale: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "must_not_copy", assert_texts(self.must_not_copy, "must_not_copy"))
        object.__setattr__(
            self,
            "transferable_principles",
            assert_texts(self.transferable_principles, "transferable_principles"),
        )
        assert_text(self.rationale, "originality boundary rationale")
        assert_nonempty(
            self.must_not_copy,
            "must_not_copy",
            "name the protected expression, or the boundary was never drawn (rule 8)",
        )
        assert_nonempty(
            self.transferable_principles,
            "transferable_principles",
            "a reference that teaches nothing transferable is not worth a case file",
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OriginalityBoundary:
        return cls(
            must_not_copy=as_tuple(data.get("must_not_copy")),
            transferable_principles=as_tuple(data.get("transferable_principles")),
            rationale=data["rationale"],
        )


@dataclass(frozen=True)
class ReferenceCase:
    """Nine sections, all required, anchored to one source.

    `strengths`, `weaknesses` and `extractable_principles` are each required to
    hold at least one entry. A case with no weakness is admiration rather than
    analysis, and one with no extractable principle did not need to be written.
    """

    kind: ClassVar[str] = "reference_case"

    id: str
    source_id: str
    title: str
    analyst: str
    created: dt.date
    hook: HookAnalysis
    core_loop: CoreLoop
    psychology: ViewerPsychology
    visual: VisualAnalysis
    camera_edit: CameraEditAnalysis
    audio: AudioAnalysis
    format: FormatAnalysis
    technical: TechnicalAnalysis
    originality: OriginalityBoundary
    confidence: ResearchConfidence
    strengths: tuple[str, ...]
    weaknesses: tuple[str, ...]
    extractable_principles: tuple[str, ...]
    mechanics: tuple[str, ...] = ()
    notes: str = ""

    def __post_init__(self) -> None:
        assert_research_id(self.id, "reference_case")
        assert_reference(self.source_id, "reference_case source_id")
        assert_research_id(self.source_id, "source")
        assert_text(self.title, "reference_case title")
        assert_text(self.analyst, "reference_case analyst")
        if not isinstance(self.created, dt.date):
            raise ResearchError("a reference case must record the date it was written")
        object.__setattr__(self, "strengths", assert_texts(self.strengths, "strengths"))
        object.__setattr__(self, "weaknesses", assert_texts(self.weaknesses, "weaknesses"))
        object.__setattr__(
            self,
            "extractable_principles",
            assert_texts(self.extractable_principles, "extractable_principles"),
        )
        object.__setattr__(self, "mechanics", assert_slugs(self.mechanics, "mechanic"))
        assert_nonempty(self.strengths, "strengths", "name what the reference does well")
        assert_nonempty(
            self.weaknesses,
            "weaknesses",
            "a reference with no weakness is admiration, not analysis - and the "
            "weaknesses are where our superiority targets come from",
        )
        assert_nonempty(
            self.extractable_principles,
            "extractable_principles",
            "state what we learned that we can use without copying anything",
        )
        if not isinstance(self.originality, OriginalityBoundary):
            raise ResearchError(
                f"reference_case {self.id!r}: an originality boundary is required on every "
                "reference case (constitution rule 8)"
            )

    @property
    def novel_mechanics(self) -> tuple[str, ...]:
        """Tags outside the six the brief named - the vocabulary as it grows."""
        return tuple(m for m in self.mechanics if m not in KNOWN_MECHANICS)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReferenceCase:
        return cls(
            id=data["id"],
            source_id=data["source_id"],
            title=data["title"],
            analyst=data["analyst"],
            created=as_date(data["created"], "created"),
            hook=HookAnalysis.from_dict(data["hook"]),
            core_loop=CoreLoop.from_dict(data["core_loop"]),
            psychology=ViewerPsychology.from_dict(data["psychology"]),
            visual=VisualAnalysis.from_dict(data["visual"]),
            camera_edit=CameraEditAnalysis.from_dict(data["camera_edit"]),
            audio=AudioAnalysis.from_dict(data["audio"]),
            format=FormatAnalysis.from_dict(data["format"]),
            technical=TechnicalAnalysis.from_dict(data["technical"]),
            originality=OriginalityBoundary.from_dict(data["originality"]),
            confidence=ResearchConfidence.from_dict(data["confidence"]),
            strengths=as_tuple(data.get("strengths")),
            weaknesses=as_tuple(data.get("weaknesses")),
            extractable_principles=as_tuple(data.get("extractable_principles")),
            mechanics=as_tuple(data.get("mechanics")),
            notes=data.get("notes", ""),
        )
