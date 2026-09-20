"""Cross-reference checks specific to the derived dashboard read model."""

from __future__ import annotations

from .models import CompanyStateSnapshot, FreshnessState


FORBIDDEN_AGGREGATE_FIELDS = frozenset({"company_health_score", "ceo_score", "overall_score",
                                        "company_grade", "traffic_light_score", "format_winner",
                                        "project_winner"})


def check_integrity(snapshot: CompanyStateSnapshot) -> tuple[str, ...]:
    issues: list[str] = []
    refs = {item.key: item for item in snapshot.source_refs}
    for section in snapshot.sections:
        for dimension in section.dimensions:
            if _contains_mapping(dimension.value):
                issues.append(
                    f"section {section.name} dimension {dimension.name}: contains an object body; use source references"
                )
        for ref in (*section.source_refs, *section.stale_source_refs,
                    *(ref for dimension in section.dimensions for ref in dimension.source_refs)):
            if ref not in refs:
                issues.append(f"section {section.name}: unknown source reference {ref!r}")
    for decision in snapshot.decision_queue:
        for ref in decision.evidence_refs:
            if ref not in refs:
                issues.append(f"decision {decision.decision_id}: unknown source reference {ref!r}")
        if not decision.reserved_actions:
            issues.append(f"decision {decision.decision_id}: CEO-required item has no reserved-action evidence")
    for attention in snapshot.attention_items:
        for ref in attention.source_refs:
            if ref not in refs:
                issues.append(f"attention {attention.attention_id}: unknown source reference {ref!r}")
        if not attention.resolves_when.strip():
            issues.append(f"attention {attention.attention_id}: no resolution condition")
    expected_stale = {item.key for item in snapshot.source_refs if item.freshness is FreshnessState.STALE}
    actual_stale = set(snapshot.stale_sources)
    if expected_stale != actual_stale:
        issues.append("snapshot stale_sources does not match source-reference freshness")
    payload = snapshot.to_dict()
    for forbidden in FORBIDDEN_AGGREGATE_FIELDS:
        if _contains_key(payload, forbidden):
            issues.append(f"forbidden aggregate verdict field {forbidden!r}")
    return tuple(sorted(set(issues)))


def _contains_key(value: object, wanted: str) -> bool:
    if isinstance(value, dict):
        return wanted in value or any(_contains_key(x, wanted) for x in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_key(x, wanted) for x in value)
    return False


def _contains_mapping(value: object) -> bool:
    if isinstance(value, dict):
        return True
    if isinstance(value, (list, tuple)):
        return any(_contains_mapping(item) for item in value)
    return False
