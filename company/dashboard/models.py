"""Immutable executive read models for Company OS.

The dashboard owns no operational fact.  Every statement is either a compact
dimension or a reference to a canonical record in another subsystem.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from ai_platform.serde import dumps, fingerprint


class DashboardError(ValueError):
    """A dashboard read model is internally inconsistent."""


class SourceSubsystem(str, Enum):
    EXECUTION = "execution"
    RESEARCH = "research"
    ANALYTICS = "analytics"
    FINANCE = "finance"
    WORKFORCE = "workforce"
    ORGANIZATION = "organization"
    SYSTEM = "system"


class FreshnessState(str, Enum):
    CURRENT = "current"
    STALE = "stale"
    UNKNOWN = "unknown"


class Availability(str, Enum):
    AVAILABLE = "available"
    MISSING = "missing"
    PARTIAL = "partial"


class AttentionLevel(str, Enum):
    INFO = "info"
    WATCH = "watch"
    ACTION_REQUIRED = "action_required"
    BLOCKED = "blocked"


@dataclass(frozen=True, order=True)
class SourceReference:
    subsystem: SourceSubsystem
    kind: str
    record_id: str
    record_ref: str
    fingerprint: str
    freshness: FreshnessState = FreshnessState.UNKNOWN
    recheck_on: dt.date | None = None

    def __post_init__(self) -> None:
        for name in ("kind", "record_id", "record_ref", "fingerprint"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise DashboardError(f"source reference {name} must be non-empty")
        if self.record_ref.startswith(("/", "\\")) or ".." in self.record_ref.replace("\\", "/").split("/"):
            raise DashboardError("source record_ref must be a relative, non-escaping pointer")

    @property
    def key(self) -> str:
        return f"{self.subsystem.value}:{self.kind}:{self.record_id}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "subsystem": self.subsystem.value,
            "kind": self.kind,
            "record_id": self.record_id,
            "record_ref": self.record_ref.replace("\\", "/"),
            "fingerprint": self.fingerprint,
            "freshness": self.freshness.value,
            "recheck_on": self.recheck_on.isoformat() if self.recheck_on else None,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SourceReference":
        due = data.get("recheck_on")
        return cls(
            subsystem=SourceSubsystem(data["subsystem"]),
            kind=str(data["kind"]),
            record_id=str(data["record_id"]),
            record_ref=str(data["record_ref"]),
            fingerprint=str(data["fingerprint"]),
            freshness=FreshnessState(data.get("freshness", "unknown")),
            recheck_on=dt.date.fromisoformat(due) if due else None,
        )


@dataclass(frozen=True)
class ExecutiveDimension:
    """One independently readable company dimension; unknown is not zero."""

    name: str
    value: Any = None
    known: bool = True
    unit: str = ""
    source_refs: tuple[str, ...] = ()
    note: str = ""

    def __post_init__(self) -> None:
        if not self.name or not isinstance(self.name, str):
            raise DashboardError("dimension name must be non-empty")
        if not self.known and self.value is not None:
            raise DashboardError(f"unknown dimension {self.name!r} cannot carry a value")
        object.__setattr__(self, "source_refs", tuple(sorted(set(self.source_refs))))

    def to_dict(self) -> dict[str, Any]:
        value = list(self.value) if isinstance(self.value, tuple) else self.value
        return {
            "name": self.name,
            "known": self.known,
            "value": value,
            "unit": self.unit,
            "source_refs": list(self.source_refs),
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ExecutiveDimension":
        value = data.get("value")
        if isinstance(value, list):
            value = tuple(value)
        return cls(
            name=str(data["name"]),
            value=value,
            known=bool(data.get("known", True)),
            unit=str(data.get("unit", "")),
            source_refs=tuple(data.get("source_refs", ())),
            note=str(data.get("note", "")),
        )


@dataclass(frozen=True)
class ExecutiveSection:
    name: str
    availability: Availability
    summary: str
    dimensions: tuple[ExecutiveDimension, ...] = ()
    source_refs: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    stale_source_refs: tuple[str, ...] = ()
    integrity_issues: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.name or not self.summary:
            raise DashboardError("section name and summary must be non-empty")
        names = [item.name for item in self.dimensions]
        if len(names) != len(set(names)):
            raise DashboardError(f"section {self.name!r} repeats a dimension name")
        object.__setattr__(self, "dimensions", tuple(sorted(self.dimensions, key=lambda x: x.name)))
        for name in ("source_refs", "missing", "stale_source_refs", "integrity_issues"):
            object.__setattr__(self, name, tuple(sorted(set(getattr(self, name)))))

    def dimension(self, name: str) -> ExecutiveDimension:
        for item in self.dimensions:
            if item.name == name:
                return item
        raise KeyError(name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "availability": self.availability.value,
            "summary": self.summary,
            "dimensions": [item.to_dict() for item in self.dimensions],
            "source_refs": list(self.source_refs),
            "missing": list(self.missing),
            "stale_source_refs": list(self.stale_source_refs),
            "integrity_issues": list(self.integrity_issues),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ExecutiveSection":
        return cls(
            name=str(data["name"]),
            availability=Availability(data["availability"]),
            summary=str(data["summary"]),
            dimensions=tuple(ExecutiveDimension.from_dict(x) for x in data.get("dimensions", ())),
            source_refs=tuple(data.get("source_refs", ())),
            missing=tuple(data.get("missing", ())),
            stale_source_refs=tuple(data.get("stale_source_refs", ())),
            integrity_issues=tuple(data.get("integrity_issues", ())),
        )


@dataclass(frozen=True)
class CEODecisionItem:
    decision_id: str
    type: str
    source_subsystem: SourceSubsystem
    subject: str
    why_ceo_attention: str
    evidence_refs: tuple[str, ...]
    financial_impact: str | None = None
    risk: str = "unknown"
    reversibility: str = "unknown"
    deadline: dt.date | None = None
    current_state: str = "proposed"
    reserved_actions: tuple[str, ...] = ()
    blocked: bool = False
    created_on: dt.date | None = None

    def __post_init__(self) -> None:
        for name in ("decision_id", "type", "subject", "why_ceo_attention", "current_state"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise DashboardError(f"CEO decision {name} must be non-empty")
        if not self.evidence_refs:
            raise DashboardError(f"CEO decision {self.decision_id!r} has no source/evidence reference")
        object.__setattr__(self, "evidence_refs", tuple(sorted(set(self.evidence_refs))))
        object.__setattr__(self, "reserved_actions", tuple(sorted(set(self.reserved_actions))))

    @property
    def sort_key(self) -> tuple[Any, ...]:
        return (
            0 if self.blocked else 1,
            0 if self.deadline else 1,
            self.deadline or dt.date.max,
            0 if self.reserved_actions else 1,
            {"high": 0, "medium": 1, "low": 2}.get(self.risk, 3),
            self.created_on or dt.date.max,
            self.decision_id,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "type": self.type,
            "source_subsystem": self.source_subsystem.value,
            "subject": self.subject,
            "why_ceo_attention": self.why_ceo_attention,
            "evidence_refs": list(self.evidence_refs),
            "financial_impact": self.financial_impact,
            "risk": self.risk,
            "reversibility": self.reversibility,
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "current_state": self.current_state,
            "reserved_actions": list(self.reserved_actions),
            "blocked": self.blocked,
            "created_on": self.created_on.isoformat() if self.created_on else None,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CEODecisionItem":
        return cls(
            decision_id=str(data["decision_id"]),
            type=str(data["type"]),
            source_subsystem=SourceSubsystem(data["source_subsystem"]),
            subject=str(data["subject"]),
            why_ceo_attention=str(data["why_ceo_attention"]),
            evidence_refs=tuple(data.get("evidence_refs", ())),
            financial_impact=data.get("financial_impact"),
            risk=str(data.get("risk", "unknown")),
            reversibility=str(data.get("reversibility", "unknown")),
            deadline=dt.date.fromisoformat(data["deadline"]) if data.get("deadline") else None,
            current_state=str(data.get("current_state", "proposed")),
            reserved_actions=tuple(data.get("reserved_actions", ())),
            blocked=bool(data.get("blocked", False)),
            created_on=dt.date.fromisoformat(data["created_on"]) if data.get("created_on") else None,
        )


@dataclass(frozen=True)
class AttentionItem:
    attention_id: str
    subject: str
    reason: str
    source_refs: tuple[str, ...]
    category: str
    level: AttentionLevel
    resolves_when: str

    def __post_init__(self) -> None:
        for name in ("attention_id", "subject", "reason", "category", "resolves_when"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise DashboardError(f"attention item {name} must be non-empty")
        if not self.source_refs:
            raise DashboardError(f"attention item {self.attention_id!r} has no source reference")
        object.__setattr__(self, "source_refs", tuple(sorted(set(self.source_refs))))

    @property
    def sort_key(self) -> tuple[int, str]:
        order = {AttentionLevel.BLOCKED: 0, AttentionLevel.ACTION_REQUIRED: 1,
                 AttentionLevel.WATCH: 2, AttentionLevel.INFO: 3}
        return order[self.level], self.attention_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "attention_id": self.attention_id,
            "subject": self.subject,
            "reason": self.reason,
            "source_refs": list(self.source_refs),
            "category": self.category,
            "level": self.level.value,
            "resolves_when": self.resolves_when,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AttentionItem":
        return cls(
            attention_id=str(data["attention_id"]), subject=str(data["subject"]),
            reason=str(data["reason"]), source_refs=tuple(data.get("source_refs", ())),
            category=str(data["category"]), level=AttentionLevel(data["level"]),
            resolves_when=str(data["resolves_when"]),
        )


@dataclass(frozen=True)
class FormatView:
    format_id: str
    analyzed_videos: int
    experiment_count: int
    recent_learning_refs: tuple[str, ...] = ()
    known_cost: str | None = None
    known_revenue: str | None = None
    unresolved_hypothesis_refs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"format_id": self.format_id, "analyzed_videos": self.analyzed_videos,
                "experiment_count": self.experiment_count,
                "recent_learning_refs": list(self.recent_learning_refs),
                "known_cost": self.known_cost, "known_revenue": self.known_revenue,
                "unresolved_hypothesis_refs": list(self.unresolved_hypothesis_refs)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "FormatView":
        return cls(str(data["format_id"]), int(data["analyzed_videos"]),
                   int(data["experiment_count"]), tuple(data.get("recent_learning_refs", ())),
                   data.get("known_cost"), data.get("known_revenue"),
                   tuple(data.get("unresolved_hypothesis_refs", ())))


@dataclass(frozen=True)
class ProjectView:
    project_id: str
    active_work_refs: tuple[str, ...] = ()
    last_accepted_task_ref: str | None = None
    known_cost: str | None = None
    experiment_refs: tuple[str, ...] = ()
    blocker_refs: tuple[str, ...] = ()
    decision_refs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"project_id": self.project_id, "active_work_refs": list(self.active_work_refs),
                "last_accepted_task_ref": self.last_accepted_task_ref, "known_cost": self.known_cost,
                "experiment_refs": list(self.experiment_refs), "blocker_refs": list(self.blocker_refs),
                "decision_refs": list(self.decision_refs)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ProjectView":
        return cls(str(data["project_id"]), tuple(data.get("active_work_refs", ())),
                   data.get("last_accepted_task_ref"), data.get("known_cost"),
                   tuple(data.get("experiment_refs", ())), tuple(data.get("blocker_refs", ())),
                   tuple(data.get("decision_refs", ())))


@dataclass(frozen=True)
class CompanyStateSnapshot:
    snapshot_id: str
    generated_at: dt.date
    as_of: dt.date
    source_refs: tuple[SourceReference, ...]
    sections: tuple[ExecutiveSection, ...]
    known_missing_sources: tuple[str, ...] = ()
    stale_sources: tuple[str, ...] = ()
    unresolved_integrity_issues: tuple[str, ...] = ()
    decision_queue: tuple[CEODecisionItem, ...] = ()
    attention_items: tuple[AttentionItem, ...] = ()
    format_views: tuple[FormatView, ...] = ()
    project_views: tuple[ProjectView, ...] = ()
    north_star: str = "long-term profitable audience growth"
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.generated_at > self.as_of:
            raise DashboardError("generated_at cannot be after as_of")
        object.__setattr__(self, "source_refs", tuple(sorted(self.source_refs, key=lambda x: x.key)))
        object.__setattr__(self, "sections", tuple(sorted(self.sections, key=lambda x: x.name)))
        object.__setattr__(self, "decision_queue", tuple(sorted(self.decision_queue, key=lambda x: x.sort_key)))
        object.__setattr__(self, "attention_items", tuple(sorted(self.attention_items, key=lambda x: x.sort_key)))
        object.__setattr__(self, "format_views", tuple(sorted(self.format_views, key=lambda x: x.format_id)))
        object.__setattr__(self, "project_views", tuple(sorted(self.project_views, key=lambda x: x.project_id)))
        for name in ("known_missing_sources", "stale_sources", "unresolved_integrity_issues"):
            object.__setattr__(self, name, tuple(sorted(set(getattr(self, name)))))
        _unique("source reference", [item.key for item in self.source_refs])
        _unique("section", [item.name for item in self.sections])
        _unique("decision", [item.decision_id for item in self.decision_queue])
        _unique("attention item", [item.attention_id for item in self.attention_items])

    def section(self, name: str) -> ExecutiveSection:
        for section in self.sections:
            if section.name == name:
                return section
        raise KeyError(name)

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "snapshot_id": self.snapshot_id,
                "generated_at": self.generated_at.isoformat(), "as_of": self.as_of.isoformat(),
                "north_star": self.north_star,
                "source_refs": [x.to_dict() for x in self.source_refs],
                "sections": [x.to_dict() for x in self.sections],
                "known_missing_sources": list(self.known_missing_sources),
                "stale_sources": list(self.stale_sources),
                "unresolved_integrity_issues": list(self.unresolved_integrity_issues),
                "decision_queue": [x.to_dict() for x in self.decision_queue],
                "attention_items": [x.to_dict() for x in self.attention_items],
                "format_views": [x.to_dict() for x in self.format_views],
                "project_views": [x.to_dict() for x in self.project_views]}

    def canonical_json(self) -> str:
        return dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CompanyStateSnapshot":
        return cls(
            snapshot_id=str(data["snapshot_id"]), generated_at=dt.date.fromisoformat(data["generated_at"]),
            as_of=dt.date.fromisoformat(data["as_of"]),
            source_refs=tuple(SourceReference.from_dict(x) for x in data.get("source_refs", ())),
            sections=tuple(ExecutiveSection.from_dict(x) for x in data.get("sections", ())),
            known_missing_sources=tuple(data.get("known_missing_sources", ())),
            stale_sources=tuple(data.get("stale_sources", ())),
            unresolved_integrity_issues=tuple(data.get("unresolved_integrity_issues", ())),
            decision_queue=tuple(CEODecisionItem.from_dict(x) for x in data.get("decision_queue", ())),
            attention_items=tuple(AttentionItem.from_dict(x) for x in data.get("attention_items", ())),
            format_views=tuple(FormatView.from_dict(x) for x in data.get("format_views", ())),
            project_views=tuple(ProjectView.from_dict(x) for x in data.get("project_views", ())),
            north_star=str(data.get("north_star", "long-term profitable audience growth")),
            schema_version=int(data.get("schema_version", 1)),
        )


def make_snapshot_id(payload: Mapping[str, Any]) -> str:
    return "company-state-" + fingerprint(payload)


def _unique(label: str, values: list[str]) -> None:
    duplicates = sorted({value for value in values if values.count(value) > 1})
    if duplicates:
        raise DashboardError(f"duplicate {label} ID(s): {', '.join(duplicates)}")
