"""Compact deterministic text view over a CompanyStateSnapshot."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .diff import diff_snapshots
from .models import AttentionLevel, CompanyStateSnapshot


@dataclass(frozen=True)
class CEOBrief:
    snapshot_id: str
    as_of: str
    changed: tuple[str, ...]
    decisions: tuple[str, ...]
    blocked: tuple[str, ...]
    performing_and_learning: tuple[str, ...]
    money: tuple[str, ...]
    unknowns: tuple[str, ...]
    inspect_next: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"snapshot_id": self.snapshot_id, "as_of": self.as_of,
                "changed": list(self.changed), "decisions": list(self.decisions),
                "blocked": list(self.blocked),
                "performing_and_learning": list(self.performing_and_learning),
                "money": list(self.money), "unknowns": list(self.unknowns),
                "inspect_next": list(self.inspect_next)}

    def render_text(self) -> str:
        lines = [f"CEO brief — {self.as_of}", f"Snapshot: {self.snapshot_id}"]
        for title, values in (("What changed", self.changed), ("Needs my decision", self.decisions),
                              ("Blocked", self.blocked), ("Performing / learning", self.performing_and_learning),
                              ("Money", self.money), ("Unknown", self.unknowns),
                              ("Inspect next", self.inspect_next)):
            lines.append("")
            lines.append(title + ":")
            lines.extend(f"- {value}" for value in (values or ("None recorded.",)))
        return "\n".join(lines) + "\n"


def build_brief(snapshot: CompanyStateSnapshot,
                previous: CompanyStateSnapshot | None = None) -> CEOBrief:
    changed = ("No previous snapshot supplied.",)
    if previous is not None:
        delta = diff_snapshots(previous, snapshot)
        changed = tuple(f"{x.category}: {x.identity}" for x in delta.changes[:8]) or ("No structured changes.",)
    decisions = tuple(f"{x.subject} — {x.why_ceo_attention} [{x.evidence_refs[0]}]"
                      for x in snapshot.decision_queue[:8])
    blocked = tuple(f"{x.subject} — {x.reason} [{x.source_refs[0]}]"
                    for x in snapshot.attention_items if x.level is AttentionLevel.BLOCKED)[:8]
    analytics = snapshot.section("analytics")
    research = snapshot.section("research")
    execution = snapshot.section("execution")
    performing = (execution.summary, analytics.summary, research.summary)
    finance = snapshot.section("finance")
    money = tuple(_dimension_line(finance, name) for name in ("known_cost", "known_revenue", "known_contribution"))
    unknowns = tuple(snapshot.known_missing_sources[:8])
    inspect: list[str] = []
    inspect.extend(x.evidence_refs[0] for x in snapshot.decision_queue[:3])
    inspect.extend(x.source_refs[0] for x in snapshot.attention_items[:3] if x.source_refs)
    if not inspect:
        inspect.extend(x.key for x in snapshot.source_refs[:3])
    return CEOBrief(snapshot.snapshot_id, snapshot.as_of.isoformat(), changed, decisions,
                    blocked, performing, money, unknowns, tuple(dict.fromkeys(inspect)))


def _dimension_line(section: Any, name: str) -> str:
    try:
        item = section.dimension(name)
    except KeyError:
        return f"{name}: unknown (no Finance records supplied)"
    return f"{name}: {item.value if item.known else 'unknown'}" + (f" ({item.note})" if item.note else "")
