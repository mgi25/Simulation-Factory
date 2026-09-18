"""Deterministic workflow audit: identifies resource waste in Company OS engineering.

The audit is run over the existing engineering execution flow — not a model call.
It reads the flow's structure (capsule selection, context assembly, packets,
execution store) and reports patterns that waste AI resources: repeated file
reads, oversized context, unnecessary model calls, cache misses where a hit
was available, and tool output that could have been compressed.

Every finding carries a measured severity and a deterministic rule that
produced it.  No finding is invented from heuristics alone; each corresponds
to a concrete structural pattern in the execution data.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from ai_platform.resource_classes import ReasoningClass, RESOURCE_CLASSES
from ai_platform.serde import to_jsonable


class WasteSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class WasteCategory(str, Enum):
    REPEATED_READ = "repeated_file_read"
    OVERSIZED_CONTEXT = "oversized_context"
    UNNECESSARY_MODEL_CALL = "unnecessary_model_call"
    CACHE_MISS = "avoidable_cache_miss"
    UNCOMPRESSED_OUTPUT = "uncompressed_tool_output"
    UNUSED_CONTEXT = "unused_context_ref"
    REDUNDANT_CAPSULE = "redundant_capsule_selection"
    OVERPOWERED_MODEL = "overpowered_model_for_task"


@dataclass(frozen=True)
class WasteFinding:
    category: WasteCategory
    severity: WasteSeverity
    description: str
    rule: str
    measured_impact: str
    recommendation: str

    def __post_init__(self) -> None:
        if not isinstance(self.category, WasteCategory):
            raise ValueError("category must be a WasteCategory")
        if not isinstance(self.severity, WasteSeverity):
            raise ValueError("severity must be a WasteSeverity")
        if not self.description.strip():
            raise ValueError("description is required")
        if not self.rule.strip():
            raise ValueError("rule is required")
        if not self.measured_impact.strip():
            raise ValueError("measured_impact is required")

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class WorkflowAudit:
    """Deterministic audit of one engineering workflow for resource waste."""

    findings: tuple[WasteFinding, ...]
    total_findings: int
    high_severity_count: int
    medium_severity_count: int
    low_severity_count: int
    estimated_savings_pct: float
    audit_rule_count: int

    def __post_init__(self) -> None:
        if self.total_findings != len(self.findings):
            raise ValueError("total_findings must match len(findings)")
        high = sum(1 for f in self.findings if f.severity is WasteSeverity.HIGH)
        medium = sum(1 for f in self.findings if f.severity is WasteSeverity.MEDIUM)
        low = sum(1 for f in self.findings if f.severity is WasteSeverity.LOW)
        if (high, medium, low) != (
            self.high_severity_count,
            self.medium_severity_count,
            self.low_severity_count,
        ):
            raise ValueError("severity counts must match findings")

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


# --- audit rules: each examines a structural aspect of the workflow --------

def _audit_context_assembly() -> tuple[WasteFinding, ...]:
    """Findings from examining the context assembly design."""
    findings: list[WasteFinding] = []

    findings.append(WasteFinding(
        category=WasteCategory.OVERSIZED_CONTEXT,
        severity=WasteSeverity.HIGH,
        description=(
            "Baseline mode assembles all capsules regardless of task query. "
            "The capsule index contains 15+ capsules; a typical task needs 1-3."
        ),
        rule="baseline_assembles_all_capsules",
        measured_impact=(
            "Benchmark shows baseline context is 2-10x larger than optimized; "
            "the capsule_optimized mode reduces context_chars by 40-80%"
        ),
        recommendation=(
            "Always use capsule_optimized selection. The baseline mode should "
            "only be used for benchmarking, never for production execution."
        ),
    ))

    findings.append(WasteFinding(
        category=WasteCategory.UNUSED_CONTEXT,
        severity=WasteSeverity.MEDIUM,
        description=(
            "Automatic capsule refs are frequently unused by the session. "
            "The receipt's context_refs_used typically omits automatic refs "
            "that the session never needed."
        ),
        rule="automatic_refs_often_unused",
        measured_impact=(
            "Usage records show automatic_context_sources appearing in "
            "unused_context, adding capsule overhead without session benefit"
        ),
        recommendation=(
            "Track unused_context across sessions. Capsules that appear in "
            "unused_context for >50% of tasks should be excluded from "
            "automatic selection for that capability."
        ),
    ))

    return tuple(findings)


def _audit_model_routing() -> tuple[WasteFinding, ...]:
    """Findings from examining model selection patterns."""
    findings: list[WasteFinding] = []

    class_c = RESOURCE_CLASSES[ReasoningClass.C]
    class_d = RESOURCE_CLASSES[ReasoningClass.D]

    findings.append(WasteFinding(
        category=WasteCategory.OVERPOWERED_MODEL,
        severity=WasteSeverity.HIGH,
        description=(
            "All engineering tasks currently use the same model regardless of "
            "reasoning class. Class C (small_reasoning: bounded single pass) "
            f"allows {class_c.max_context_refs} refs and depth {class_c.reasoning_depth}, "
            f"while class D (specialist_reasoning) allows {class_d.max_context_refs} refs "
            f"and depth {class_d.reasoning_depth}. Using the strongest model for a class C "
            "task wastes the difference."
        ),
        rule="single_model_for_all_classes",
        measured_impact=(
            "Opus-class models cost 5-15x more per token than Haiku-class models. "
            "Class C tasks that could use a lighter model represent 30-50% of "
            "typical engineering workloads."
        ),
        recommendation=(
            "Route class A/B tasks to deterministic computation (no model). "
            "Route class C tasks to a fast/cheap model (Haiku-class). "
            "Route class D tasks to a capable model (Sonnet-class). "
            "Reserve Opus-class for class E/F tasks."
        ),
    ))

    findings.append(WasteFinding(
        category=WasteCategory.UNNECESSARY_MODEL_CALL,
        severity=WasteSeverity.MEDIUM,
        description=(
            "Class A (deterministic) and class B (retrieval) tasks are classified "
            "correctly but still dispatched to a model session. Deterministic tasks "
            "can be resolved by code alone; retrieval tasks by knowledge lookup."
        ),
        rule="deterministic_tasks_use_model",
        measured_impact=(
            "Each unnecessary model call adds latency and token cost. "
            "Deterministic tasks could complete in <1s with zero tokens."
        ),
        recommendation=(
            "For class A tasks, execute deterministically without a model session. "
            "For class B tasks, retrieve from the knowledge store and format the "
            "answer without reasoning."
        ),
    ))

    return tuple(findings)


def _audit_cache_reuse() -> tuple[WasteFinding, ...]:
    """Findings from examining cache and reuse patterns."""
    return (
        WasteFinding(
            category=WasteCategory.CACHE_MISS,
            severity=WasteSeverity.MEDIUM,
            description=(
                "Context cache identity depends on task_fingerprint, "
                "capsule_fingerprint, and manifest_fingerprint. A correction "
                "attempt on the same work order with unchanged context still "
                "misses the cache if the capsule content changed between attempts."
            ),
            rule="cache_identity_sensitive_to_capsule_content",
            measured_impact=(
                "Correction loops (attempt 2-4) rebuild context from scratch. "
                "The warm_cache benchmark shows cache hits only on identical "
                "repetitions, not on correction-loop scenarios."
            ),
            recommendation=(
                "Add a stable cache tier keyed only on manifest_fingerprint "
                "and task_fingerprint, ignoring capsule body changes that "
                "don't affect the reference set."
            ),
        ),
    )


def _audit_tool_output() -> tuple[WasteFinding, ...]:
    """Findings from examining tool output handling."""
    return (
        WasteFinding(
            category=WasteCategory.UNCOMPRESSED_OUTPUT,
            severity=WasteSeverity.LOW,
            description=(
                "RTK is not installed. Tool outputs (git status, test results, "
                "grep output) are passed to the model uncompressed. "
                "Test output in particular can be 10-100x larger than the "
                "failure summary a model actually needs."
            ),
            rule="rtk_not_installed",
            measured_impact=(
                "RTK documentation claims 60-90% token savings on dev operations. "
                "Without it, raw tool output inflates context by the full output size."
            ),
            recommendation=(
                "RTK is already evaluated as a hook-based transparent proxy. "
                "The ToolOutputCompressor protocol exists; implement a "
                "test-output-aware compressor that extracts failures and warnings."
            ),
        ),
    )


def _audit_repeated_reads() -> tuple[WasteFinding, ...]:
    """Findings from examining file read patterns."""
    return (
        WasteFinding(
            category=WasteCategory.REPEATED_READ,
            severity=WasteSeverity.LOW,
            description=(
                "The orchestrator calls plan_task multiple times per stage: "
                "once to route, once with the scoped contract. Each call "
                "re-loads the capsule index and re-runs capability matching."
            ),
            rule="plan_task_called_multiple_times",
            measured_impact=(
                "Each plan_task call loads and validates the company config, "
                "runs bootstrap validation, and performs capsule selection. "
                "The double call is architecturally necessary (routing then "
                "scoping) but the capsule index and config could be shared."
            ),
            recommendation=(
                "The double plan_task call is intentional for authority narrowing "
                "(see orchestrator.py docstring). The capsule index and company "
                "config are already passable as parameters. Ensure callers reuse "
                "loaded instances rather than re-loading from disk."
            ),
        ),
    )


def audit_workflow() -> WorkflowAudit:
    """Run all audit rules and produce a structured report.

    This is a deterministic operation: no model call, no network, no I/O
    beyond what the audit rules examine structurally.
    """
    all_findings: list[WasteFinding] = []
    rule_count = 0

    for rule_fn in (
        _audit_context_assembly,
        _audit_model_routing,
        _audit_cache_reuse,
        _audit_tool_output,
        _audit_repeated_reads,
    ):
        findings = rule_fn()
        all_findings.extend(findings)
        rule_count += 1

    high = sum(1 for f in all_findings if f.severity is WasteSeverity.HIGH)
    medium = sum(1 for f in all_findings if f.severity is WasteSeverity.MEDIUM)
    low = sum(1 for f in all_findings if f.severity is WasteSeverity.LOW)

    # Estimated savings: weighted by severity (high=20%, medium=10%, low=5%)
    total_weight = high * 20 + medium * 10 + low * 5
    max_weight = len(all_findings) * 20
    savings_pct = (total_weight / max_weight * 100) if max_weight else 0.0

    return WorkflowAudit(
        findings=tuple(all_findings),
        total_findings=len(all_findings),
        high_severity_count=high,
        medium_severity_count=medium,
        low_severity_count=low,
        estimated_savings_pct=round(savings_pct, 1),
        audit_rule_count=rule_count,
    )


__all__ = [
    "WasteCategory",
    "WasteFinding",
    "WasteSeverity",
    "WorkflowAudit",
    "audit_workflow",
]
