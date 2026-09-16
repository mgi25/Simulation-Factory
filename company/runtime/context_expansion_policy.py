"""Deterministic policy evaluation for explicit context expansion requests."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from ai_platform.context_manifest import ContextKind, ContextRef
from ai_platform.resource_classes import resource_class
from knowledge.company_os.capsules import CapsuleIndex

from .context_expansion import (
    ContextExpansionDecision,
    ContextExpansionLedger,
    ContextExpansionRequest,
    ContextRefRejection,
    _decision_outcome,
    effective_context_fingerprint,
)
from .errors import LifecycleError
from .packets import SessionPacket
from .path_scope import normalise_path


_PATH_KINDS = frozenset(
    {
        ContextKind.MODULE_CONTRACT,
        ContextKind.FILE,
        ContextKind.TEST,
        ContextKind.BENCHMARK,
    }
)


def decide_context_expansion(
    packet: SessionPacket,
    request: ContextExpansionRequest,
    employee_contract: Mapping[str, Any],
    *,
    ledger: ContextExpansionLedger | None = None,
    capsule_index: CapsuleIndex | None = None,
    repo_root: str | Path | None = None,
) -> ContextExpansionDecision:
    """Approve only explicit, readable refs that fit the packet's original ceiling."""

    current = ledger or ContextExpansionLedger.for_packet(packet)
    current.assert_for_packet(packet)
    index = capsule_index if capsule_index is not None else CapsuleIndex.load()
    may_read = _contract_paths(employee_contract, "may_read")
    may_not_read = _contract_paths(employee_contract, "may_not_read")
    supplied = set(packet.context_keys()) | {ref.key for ref in current.approved_refs}
    approved: list[ContextRef] = []
    rejected: list[ContextRefRejection] = []
    already: list[str] = []

    boundary_failure = ""
    if request.task_id != packet.task_id:
        boundary_failure = (
            f"request task {request.task_id!r} does not match packet task "
            f"{packet.task_id!r}"
        )
    elif request.packet_fingerprint != packet.fingerprint():
        boundary_failure = "request belongs to another packet"
    elif request.sequence != len(current.decisions) + 1:
        boundary_failure = (
            f"request sequence {request.sequence} is not the next expansion sequence "
            f"{len(current.decisions) + 1}"
        )

    ceiling = resource_class(packet.reasoning_class).max_context_refs
    for requested in request.requested_refs:
        if boundary_failure:
            rejected.append(ContextRefRejection(requested, boundary_failure))
            continue
        problem = _reference_problem(
            requested, may_read, may_not_read, index, repo_root
        )
        if problem:
            rejected.append(ContextRefRejection(requested, problem))
            continue

        candidate = _capsule_first(requested, index, repo_root)
        if candidate.key != requested.key:
            problem = _reference_problem(
                candidate, may_read, may_not_read, index, repo_root
            )
            if problem:
                rejected.append(
                    ContextRefRejection(
                        requested, f"capsule-first replacement rejected: {problem}"
                    )
                )
                continue
        if candidate.key in supplied or candidate.key in {ref.key for ref in approved}:
            already.append(requested.key)
            continue
        if len(supplied) + len(approved) >= ceiling:
            rejected.append(
                ContextRefRejection(
                    requested,
                    f"context ceiling of {ceiling} refs for class "
                    f"{packet.reasoning_class.value} would be exceeded; the task was not "
                    "silently reclassified",
                )
            )
            continue
        approved.append(candidate)

    previous = current.effective_context_fingerprint
    all_approved = current.approved_refs + tuple(approved)
    resulting = effective_context_fingerprint(
        current.initial_context_fingerprint, all_approved
    )
    return ContextExpansionDecision(
        task_id=packet.task_id,
        packet_fingerprint=packet.fingerprint(),
        request_id=request.request_id,
        request_fingerprint=request.fingerprint(),
        sequence=len(current.decisions) + 1,
        required_to_continue=request.required_to_continue,
        outcome=_decision_outcome(tuple(approved), tuple(rejected), tuple(already)),
        approved_refs=tuple(approved),
        rejected_refs=tuple(rejected),
        already_present_refs=tuple(already),
        previous_context_fingerprint=previous,
        resulting_context_fingerprint=resulting,
    )


def _reference_problem(
    ref: ContextRef,
    may_read: tuple[str, ...],
    may_not_read: tuple[str, ...],
    index: CapsuleIndex,
    repo_root: str | Path | None,
) -> str:
    paths: tuple[str, ...]
    if ref.kind is ContextKind.MODULE_CONTRACT and ref.ref.startswith("capsule:"):
        capsule_id = ref.ref.removeprefix("capsule:")
        if capsule_id not in index:
            return f"capsule {capsule_id!r} does not exist"
        paths = (f"knowledge/company_os/capsules/seeds/{capsule_id}.json",)
    elif ref.kind in _PATH_KINDS:
        try:
            path = _reference_path(ref)
        except LifecycleError as exc:
            return str(exc)
        paths = (path,)
        if repo_root is not None and not (Path(repo_root) / path).exists():
            return f"repository reference {path!r} does not exist"
    elif ref.kind in {ContextKind.FACT, ContextKind.DECISION, ContextKind.EXPERIMENT}:
        paths = ("knowledge/company_os",)
    else:
        return f"unsupported context kind {ref.kind.value}"

    if not may_read:
        return "employee may_read is empty; the contract grants no read authority"
    denied = tuple(
        path for path in paths if not any(_covers(rule, path) for rule in may_read)
    )
    if denied:
        return "requested context is outside employee may_read: " + ", ".join(denied)
    forbidden = tuple(
        path for path in paths if any(_overlaps(rule, path) for rule in may_not_read)
    )
    if forbidden:
        return "requested context crosses employee may_not_read: " + ", ".join(
            forbidden
        )
    return ""


def _capsule_first(
    requested: ContextRef,
    index: CapsuleIndex,
    repo_root: str | Path | None,
) -> ContextRef:
    """Prefer a capsule for a broad path, never for an explicit narrow file."""
    if requested.kind not in {ContextKind.FILE, ContextKind.MODULE_CONTRACT}:
        return requested
    if requested.kind is ContextKind.MODULE_CONTRACT and requested.ref.startswith(
        "capsule:"
    ):
        return requested
    path = _reference_path(requested)
    target = Path(repo_root) / path if repo_root is not None else None
    broad = (
        target.is_dir()
        if target is not None and target.exists()
        else not Path(path).suffix
    )
    if not broad:
        return requested
    matches = index.by_path(path)
    if not matches:
        return requested
    capsule = matches[0]
    return ContextRef(
        kind=ContextKind.MODULE_CONTRACT,
        ref=f"capsule:{capsule.id}",
        reason=f"capsule-first expansion for {requested.ref}: {requested.reason}",
    )


def _reference_path(ref: ContextRef) -> str:
    raw = ref.ref.split("::", 1)[0].split("#", 1)[0]
    return normalise_path(raw, f"{ref.kind.value} expansion ref")


def _contract_paths(contract: Mapping[str, Any], field: str) -> tuple[str, ...]:
    values = contract.get(field, ()) if isinstance(contract, Mapping) else ()
    if isinstance(values, (str, bytes)) or not isinstance(values, (list, tuple)):
        raise LifecycleError(f"agent_contract.{field} must be a list of paths")
    paths = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise LifecycleError(f"agent_contract.{field} must contain non-empty paths")
        text = value.strip().replace("\\", "/")
        while text.endswith(("/**", "/*")):
            text = text.rsplit("/", 1)[0]
        paths.append(normalise_path(text, f"agent_contract.{field}"))
    return tuple(sorted(set(paths)))


def _covers(rule: str, path: str) -> bool:
    if "*" in rule or "?" in rule or "[" in rule:
        return PurePosixPath(path).match(rule)
    return path == rule or path.startswith(rule + "/")


def _overlaps(rule: str, path: str) -> bool:
    if _covers(rule, path) or _covers(path, rule):
        return True
    wildcard = min(
        (position for token in ("*", "?", "[") if (position := rule.find(token)) >= 0),
        default=-1,
    )
    if wildcard < 0:
        return False
    static_prefix = rule[:wildcard].rstrip("/")
    return bool(static_prefix) and _covers(path, static_prefix)


__all__ = ["decide_context_expansion"]
