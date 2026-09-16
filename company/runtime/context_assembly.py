"""Deterministic, reference-only context assembly for one task.

Explicit task context is authoritative input: it is de-duplicated but never
removed to make room for automatically selected knowledge capsules.  Capsule
selection stays in ``knowledge.company_os.capsules.select``; this module only
adapts task metadata to that selector and applies runtime freshness and
resource-class policy to its reference-only result.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum

from ai_platform.context_manifest import ContextKind, ContextManifest, ContextRef
from ai_platform.resource_classes import Classification
from ai_platform.serde import fingerprint
from knowledge.company_os.capsules import (
    CapsuleIndex,
    CapsuleSelection,
    TaskQuery,
    select_capsules,
)
from knowledge.company_os.ledger import KnowledgeStore

from .errors import LifecycleError
from .specification import TaskSpecification


class StaleCapsulePolicy(str, Enum):
    """How explicitly requested stale capsules are handled.

    Automatic stale context is always excluded.  The second mode exists only
    for a caller deliberately preparing a capsule-revalidation task; its
    reference is labelled non-authoritative in the resulting manifest.
    """

    EXCLUDE = "exclude"
    ALLOW_EXPLICIT_FOR_REVALIDATION = "allow_explicit_for_revalidation"


@dataclass(frozen=True)
class ContextAssemblyPolicy:
    """Explicit inputs to freshness and dependency handling."""

    as_of: dt.date = field(default_factory=dt.date.today)
    stale_capsules: StaleCapsulePolicy = StaleCapsulePolicy.EXCLUDE
    include_dependencies: bool = True

    def __post_init__(self) -> None:
        if isinstance(self.as_of, dt.datetime) or not isinstance(self.as_of, dt.date):
            raise LifecycleError("context assembly as_of must be a date")
        if not isinstance(self.stale_capsules, StaleCapsulePolicy):
            raise LifecycleError(
                "context assembly stale_capsules must be a StaleCapsulePolicy value"
            )
        if not isinstance(self.include_dependencies, bool):
            raise LifecycleError(
                "context assembly include_dependencies must be boolean"
            )


@dataclass(frozen=True)
class CapsuleSelectionReason:
    capsule_id: str
    reasons: tuple[str, ...]
    explicitly_requested: bool


@dataclass(frozen=True)
class CapsuleRefRejection:
    capsule_id: str
    ref: str
    stage: str
    reason: str


@dataclass(frozen=True)
class ContextPlan:
    """Compact audit answering why a task received each context reference."""

    task_id: str
    selected_capsule_ids: tuple[str, ...]
    selection_reasons: tuple[CapsuleSelectionReason, ...]
    capsule_refs_accepted: tuple[str, ...]
    capsule_refs_rejected: tuple[CapsuleRefRejection, ...]
    explicit_refs: tuple[str, ...]
    final_manifest_refs: tuple[str, ...]
    duplicate_count: int
    context_ceiling: int
    manifest_fingerprint: str
    task_fingerprint: str
    capsule_fingerprint: str
    cache_identity: str
    as_of: dt.date
    stale_capsule_ids_surfaced: tuple[str, ...] = ()
    manifest_size_chars: int = 0


@dataclass(frozen=True)
class ContextAssembly:
    manifest: ContextManifest
    plan: ContextPlan


def assemble_context(
    specification: TaskSpecification,
    classification: Classification,
    *,
    supplied_manifest: ContextManifest | None = None,
    capsule_index: CapsuleIndex | None = None,
    policy: ContextAssemblyPolicy | None = None,
    knowledge_store: KnowledgeStore | None = None,
    observed_source_digests: Mapping[str, str] | None = None,
) -> ContextAssembly:
    """Combine explicit refs with bounded, fresh capsule refs.

    No referenced content is read or expanded.  The only I/O in the default
    path is loading the small canonical capsule/knowledge indexes.
    """

    assembly_policy = policy or ContextAssemblyPolicy()
    index = capsule_index if capsule_index is not None else CapsuleIndex.load()
    store = knowledge_store if knowledge_store is not None else KnowledgeStore()
    _validate_supplied_manifest(specification, classification, supplied_manifest)

    supplied_refs = supplied_manifest.refs() if supplied_manifest is not None else ()
    explicit_refs, explicit_duplicates = _deduplicate_refs(
        specification.context.refs + supplied_refs
    )
    ceiling = classification.resource_class.max_context_refs
    if len(explicit_refs) > ceiling:
        raise LifecycleError(
            f"task {specification.task_id}: explicit context budget: "
            f"{len(explicit_refs)} refs "
            f"exceed the {ceiling} allowed for class {classification.code.value}; "
            "explicit references are never silently discarded"
        )

    explicit_capsule_ids = _explicit_capsule_ids(specification, explicit_refs)
    missing_capsules = tuple(
        capsule_id for capsule_id in explicit_capsule_ids if capsule_id not in index
    )
    if missing_capsules:
        raise LifecycleError(
            f"task {specification.task_id}: explicitly requested capsule(s) do not "
            f"exist: {', '.join(missing_capsules)}"
        )

    selection = _select_for_task(
        specification,
        explicit_refs,
        explicit_capsule_ids,
        index,
        assembly_policy,
    )
    stale = {
        item.capsule_id: item.reasons
        for item in index.staleness(
            assembly_policy.as_of,
            store,
            observed_source_digests,
        )
    }

    selection_reasons = tuple(
        CapsuleSelectionReason(
            capsule_id=match.capsule.id,
            reasons=match.reasons,
            explicitly_requested=match.capsule.id in explicit_capsule_ids,
        )
        for match in selection.matches
    )
    rejections = [
        CapsuleRefRejection(
            capsule_id=item.capsule_id,
            ref=_capsule_key(item.capsule_id),
            stage="selection",
            reason=item.reason,
        )
        for item in selection.rejected
    ]

    final_refs = list(explicit_refs)
    final_keys = {ref.key for ref in final_refs}
    accepted_auto: list[str] = []
    selected_ids: list[str] = []
    surfaced_stale: list[str] = []
    duplicate_count = explicit_duplicates

    for match, selected_ref in zip(selection.matches, selection.refs()):
        capsule_id = match.capsule.id
        stale_reasons = stale.get(capsule_id, ())
        explicit_request = capsule_id in explicit_capsule_ids
        if stale_reasons:
            may_surface = (
                explicit_request
                and assembly_policy.stale_capsules
                is StaleCapsulePolicy.ALLOW_EXPLICIT_FOR_REVALIDATION
            )
            if not may_surface:
                rejections.append(
                    CapsuleRefRejection(
                        capsule_id=capsule_id,
                        ref=selected_ref.key,
                        stage="freshness",
                        reason="stale capsule excluded: " + "; ".join(stale_reasons),
                    )
                )
                continue
            selected_ref = ContextRef(
                kind=selected_ref.kind,
                ref=selected_ref.ref,
                reason=(
                    "non-authoritative capsule surfaced for explicit revalidation: "
                    + "; ".join(stale_reasons)
                ),
            )
            surfaced_stale.append(capsule_id)

        if selected_ref.key in final_keys:
            duplicate_count += 1
            selected_ids.append(capsule_id)
            continue
        if len(final_refs) >= ceiling:
            rejections.append(
                CapsuleRefRejection(
                    capsule_id=capsule_id,
                    ref=selected_ref.key,
                    stage="resource_ceiling",
                    reason=(
                        f"automatic context rejected: class {classification.code.value} "
                        f"ceiling of {ceiling} refs is already filled"
                    ),
                )
            )
            continue
        final_refs.append(selected_ref)
        final_keys.add(selected_ref.key)
        accepted_auto.append(selected_ref.key)
        selected_ids.append(capsule_id)

    manifest = _build_manifest(
        specification,
        classification,
        tuple(final_refs),
        supplied_manifest,
    )
    try:
        manifest.assert_valid()
    except ValueError as exc:
        raise LifecycleError(str(exc)) from exc

    manifest_fingerprint = manifest.fingerprint()
    task_fingerprint = fingerprint(specification)
    capsule_fingerprint = fingerprint(
        tuple(index.get(capsule_id) for capsule_id in selected_ids)
    )
    cache_identity = fingerprint(
        {
            "task_fingerprint": task_fingerprint,
            "capsule_fingerprint": capsule_fingerprint,
            "manifest_fingerprint": manifest_fingerprint,
        }
    )
    plan = ContextPlan(
        task_id=specification.task_id,
        selected_capsule_ids=tuple(selected_ids),
        selection_reasons=selection_reasons,
        capsule_refs_accepted=tuple(accepted_auto),
        capsule_refs_rejected=tuple(
            sorted(
                rejections,
                key=lambda item: (item.stage, item.capsule_id, item.ref, item.reason),
            )
        ),
        explicit_refs=tuple(ref.key for ref in explicit_refs),
        final_manifest_refs=manifest.keys(),
        duplicate_count=duplicate_count,
        context_ceiling=ceiling,
        manifest_fingerprint=manifest_fingerprint,
        task_fingerprint=task_fingerprint,
        capsule_fingerprint=capsule_fingerprint,
        cache_identity=cache_identity,
        as_of=assembly_policy.as_of,
        stale_capsule_ids_surfaced=tuple(surfaced_stale),
        manifest_size_chars=manifest.size_chars(),
    )
    return ContextAssembly(manifest=manifest, plan=plan)


def _select_for_task(
    specification: TaskSpecification,
    explicit_refs: tuple[ContextRef, ...],
    explicit_capsule_ids: tuple[str, ...],
    index: CapsuleIndex,
    policy: ContextAssemblyPolicy,
) -> CapsuleSelection:
    query = TaskQuery(
        paths=_repository_paths(explicit_refs),
        capabilities=specification.required_capabilities,
        capsule_ids=explicit_capsule_ids,
        owner=specification.capsule_owner,
        include_dependencies=policy.include_dependencies,
        max_capsules=max(1, len(index)),
    )
    return select_capsules(index, query)


def _repository_paths(refs: tuple[ContextRef, ...]) -> tuple[str, ...]:
    path_kinds = {
        ContextKind.MODULE_CONTRACT,
        ContextKind.FILE,
        ContextKind.TEST,
        ContextKind.BENCHMARK,
    }
    return tuple(
        ref.ref
        for ref in refs
        if ref.kind in path_kinds and not ref.ref.startswith("capsule:")
    )


def _explicit_capsule_ids(
    specification: TaskSpecification,
    refs: tuple[ContextRef, ...],
) -> tuple[str, ...]:
    ids = set(specification.capsule_ids)
    ids.update(
        ref.ref.removeprefix("capsule:")
        for ref in refs
        if ref.kind is ContextKind.MODULE_CONTRACT and ref.ref.startswith("capsule:")
    )
    return tuple(sorted(ids))


def _validate_supplied_manifest(
    specification: TaskSpecification,
    classification: Classification,
    supplied: ContextManifest | None,
) -> None:
    if supplied is None:
        return
    if supplied.task_id != specification.task_id:
        raise LifecycleError("context manifest task_id does not match the task")
    if supplied.objective != specification.objective:
        raise LifecycleError("context manifest objective does not match the task")
    if supplied.reasoning_class is not classification.code:
        raise LifecycleError(
            "context manifest reasoning_class does not match the classified resource class"
        )


def _build_manifest(
    specification: TaskSpecification,
    classification: Classification,
    refs: tuple[ContextRef, ...],
    supplied: ContextManifest | None,
) -> ContextManifest:
    groups: dict[str, list[ContextRef]] = {
        "module_contracts": [],
        "files": [],
        "facts": [],
        "tests": [],
        "decisions": [],
        "experiments": [],
    }
    destinations = {
        ContextKind.MODULE_CONTRACT: "module_contracts",
        ContextKind.FILE: "files",
        ContextKind.FACT: "facts",
        ContextKind.TEST: "tests",
        ContextKind.BENCHMARK: "tests",
        ContextKind.DECISION: "decisions",
        ContextKind.EXPERIMENT: "experiments",
    }
    for ref in refs:
        groups[destinations[ref.kind]].append(ref)

    constraints = _deduplicate_text(
        specification.context.constraints
        + (supplied.constraints if supplied is not None else ())
    )
    acceptance_criteria = _deduplicate_text(
        specification.context.acceptance_criteria
        + (supplied.acceptance_criteria if supplied is not None else ())
    )
    return ContextManifest(
        task_id=specification.task_id,
        objective=specification.objective,
        reasoning_class=classification.code,
        constraints=constraints,
        acceptance_criteria=acceptance_criteria,
        notes=supplied.notes if supplied is not None else "",
        **{name: tuple(values) for name, values in groups.items()},
    )


def _deduplicate_refs(
    refs: tuple[ContextRef, ...],
) -> tuple[tuple[ContextRef, ...], int]:
    seen: set[str] = set()
    kept: list[ContextRef] = []
    duplicates = 0
    for ref in refs:
        if ref.key in seen:
            duplicates += 1
            continue
        seen.add(ref.key)
        kept.append(ref)
    return tuple(kept), duplicates


def _deduplicate_text(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _capsule_key(capsule_id: str) -> str:
    return f"{ContextKind.MODULE_CONTRACT.value}:capsule:{capsule_id}"


__all__ = [
    "CapsuleRefRejection",
    "CapsuleSelectionReason",
    "ContextAssembly",
    "ContextAssemblyPolicy",
    "ContextPlan",
    "StaleCapsulePolicy",
    "assemble_context",
]
