"""The advisory artifact: bounded, versioned, fingerprinted - and unable to grant anything.

This is the one thing the experience store hands to anybody else, and the
external runner reads it across a command line (`tools/engineering_runner/
experience.py` is its reader). Everything about its shape follows from one
invariant:

> **Learning optimises allowed resources. Learning never creates authority.**

## How that is enforced, rather than hoped for

1. **No authority vocabulary can appear in it.** `AUTHORITY_KEYS` names every
   field an authorization is made of - read and write scopes, forbidden
   paths, required tests, risk, reasoning class, profile, attempts,
   approval, merge, publish - and `assert_no_authority_keys` walks the whole
   payload before it is returned. The runner's reader refuses the same set
   independently, so neither side trusts the other to have checked.
2. **Every file suggestion is re-checked against the task's current read
   authority** (`covers`, the same rule the runtime enforces - pinned by
   test). A file the precedent read or changed, that this work order may not
   read, is refused and listed as refused. History cannot widen a read scope
   because the check runs against today's grant, not the precedent's.
3. **Every suggestion is re-checked against the current repository**: the
   file must exist, and when a caller supplied P6B's import graph a Python
   file must be a module in it and a test must still statically reach one of
   this task's modules. Each item says which checks it passed (`checked`);
   one without `import_graph` has not been graph-checked here, and the
   runner - which always graph-checks with its own current P6B map - must do
   it before anything reaches a session. A graph that was supplied and failed
   to build refuses everything: an attempted check that errored is not a pass.
4. **Required tests are never touched.** A suggested test is one the work
   order does *not* already require, offered as a pattern to read; there is no
   field through which a suggestion could remove or replace a required suite,
   and the engineering loop never reads this artifact at all.
5. **It carries no routing.** Historical resource figures are reported with
   their basis as history. Nothing here names a reasoning class, a model tier
   or a profile for the task to use.

## Bounds

At most three precedents, three warnings, three historical references, five
files, three tests, twelve refusals, and `MAX_ADVICE_CHARS` of canonical JSON.
If a payload is still too large the lowest-value lists are cut from the end
and `truncated` says so.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import datetime as dt
import json
from typing import Any

from ai_platform.serde import fingerprint as _fingerprint
from knowledge.company_os.capsules import normalise_path

from .errors import ExperienceError
from .model import EvidenceBasis, Measurement
from .repository import RepositoryView, covers
from .retrieval import Candidate, ExperienceQuery, RetrievalResult, task_modules


ADVICE_KIND = "company_os.experience_advice"
ADVICE_VERSION = 1

MAX_SUGGESTED_FILES = 5
MAX_SUGGESTED_TESTS = 3
MAX_WARNING_LINES = 4
MAX_WARNING_CHARS = 240
MAX_REFUSALS = 12
MAX_ADVICE_CHARS = 8000

# The complete top-level vocabulary. The runner's reader holds the same set.
ADVICE_KEYS: frozenset[str] = frozenset(
    {
        "kind",
        "version",
        "advisory_only",
        "work_order_id",
        "work_order_fingerprint",
        "attempt",
        "as_of",
        "status",
        "abstention",
        "precedents",
        "warnings",
        "historical_only",
        "suggested_files",
        "suggested_tests",
        "refused",
        "resource_history",
        "measurement",
        "truncated",
        "fingerprint",
    }
)

# Every name an authorization is spelled with. None may appear as a key at any
# depth of an advisory payload. Restated in the runner's reader and pinned
# equal by `tests/test_company_external_engineering_runner.py`.
AUTHORITY_KEYS: frozenset[str] = frozenset(
    {
        "acceptance_criteria",
        "allowed_paths",
        "approve",
        "approved",
        "authorized_branch",
        "authorized_paths",
        "authorized_read_paths",
        "authorizes_merge",
        "autonomy_level",
        "capabilities",
        "ceo_approved",
        "deploy",
        "employee",
        "escalation",
        "forbidden_paths",
        "forbidden_read_paths",
        "grant",
        "max_developer_attempts",
        "may_not_modify",
        "may_not_read",
        "may_read",
        "may_write",
        "override",
        "production_write",
        "publish",
        "read_paths",
        "readiness",
        "reasoning_class",
        "reasoning_class_ceiling",
        "required_tests",
        "resource_profile",
        "risk",
        "skip_tests",
        "waive",
        "write_paths",
    }
)


def assert_no_authority_keys(payload: Any, *, where: str = "advice") -> None:
    """Refuse any authority-shaped key anywhere in a payload."""
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            if str(key) in AUTHORITY_KEYS:
                raise ExperienceError(
                    f"{where}.{key}: an experience artifact may not carry authority "
                    "vocabulary; learning never creates authority"
                )
            assert_no_authority_keys(value, where=f"{where}.{key}")
    elif isinstance(payload, (list, tuple)):
        for index, item in enumerate(payload):
            assert_no_authority_keys(item, where=f"{where}[{index}]")


def advice_fingerprint(payload: Mapping[str, Any]) -> str:
    """The digest over everything but the digest - `ai_platform.serde.fingerprint`."""
    return _fingerprint({k: v for k, v in payload.items() if k != "fingerprint"})


# --- revalidation ------------------------------------------------------------------


def read_refusal(path: str, query: ExperienceQuery) -> str:
    """Why the task's *current* read authority does not cover `path`, or ''."""
    if not any(covers(rule, path) for rule in query.read_paths):
        return "outside this work order's current read authority"
    if any(covers(rule, path) for rule in query.forbidden_read_paths):
        return "forbidden to read by this work order"
    return ""


_BASE_CHECKS: tuple[str, ...] = ("read_authority", "exists")
_GRAPH_CHECKS: tuple[str, ...] = _BASE_CHECKS + ("import_graph",)


def _graph_failure(view: RepositoryView) -> str:
    state = view.graph_state
    return f"the supplied import graph could not be built: {state[len('failed: '):]}" if state.startswith("failed") else ""


def _file_check(path: str, query: ExperienceQuery, view: RepositoryView) -> tuple[str, tuple[str, ...]]:
    """Why a file suggestion is refused (or ''), and the checks it passed."""
    denied = read_refusal(path, query)
    if denied:
        return denied, ()
    if not view.is_file(path):
        return "no longer exists", ()
    failure = _graph_failure(view)
    if failure:
        return failure, ()
    if view.graph is None:
        return "", _BASE_CHECKS
    if path.endswith(".py") and path not in view.graph:
        return "not a module in the current import graph", ()
    return "", _GRAPH_CHECKS


def _test_check(
    path: str, query: ExperienceQuery, view: RepositoryView, modules: Sequence[str]
) -> tuple[str, tuple[str, ...]]:
    """Why a test suggestion is refused (or ''), and the checks it passed."""
    denied = read_refusal(path, query)
    if denied:
        return denied, ()
    if not view.is_file(path):
        return "no longer exists", ()
    failure = _graph_failure(view)
    if failure:
        return failure, ()
    graph = view.graph
    if graph is None:
        return "", _BASE_CHECKS
    if path not in graph:
        return "not a module in the current import graph", ()
    reached = set(graph.modules_reached_by(path, transitive=True))
    if not reached & set(modules):
        return "no longer statically reaches any module this task acts on", ()
    return "", _GRAPH_CHECKS


def _outcome_line(candidate: Candidate) -> str:
    out = candidate.episode.outcome
    parts = [f"recorded {out.recorded_outcome or 'nothing'}", f"review {out.review_outcome or 'none'}"]
    if out.gate_readiness:
        parts.append(f"gate {out.gate_readiness}")
    return f"{candidate.precedent_class.value}: " + ", ".join(parts)


def _warning_lines(candidate: Candidate) -> list[str]:
    episode = candidate.episode
    head = f"{episode.work_order_id} attempt {episode.packet_attempt}"
    out = episode.outcome
    lines = [f"{head}: {reason}" for reason in candidate.governance]
    for finding in out.review_findings:
        if finding.severity in ("changes_required", "blocking"):
            lines.append(f"{head} review ({finding.severity}): {finding.summary}")
    if out.tests_failed:
        lines.append(f"{head}: failing suite(s) reported: " + ", ".join(out.tests_failed[:3]))
    if out.required_tests_missing:
        lines.append(f"{head}: required suite(s) not reported: " + ", ".join(out.required_tests_missing[:3]))
    if out.expansions_rejected:
        lines.append(f"{head}: context expansion refused: " + ", ".join(out.expansions_rejected[:3]))
    if not lines:
        lines.append(f"{head}: attempt recorded {out.recorded_outcome or 'no outcome'}, review {out.review_outcome or 'none'}")
    return [line if len(line) <= MAX_WARNING_CHARS else line[: MAX_WARNING_CHARS - 1] + "…" for line in lines]


def _resource_entry(candidate: Candidate) -> dict[str, Any]:
    res = candidate.episode.resources
    tokens = (
        Measurement(res.tokens_total, res.tokens_basis)
        if res.tokens_total is not None
        else Measurement(None, EvidenceBasis.UNAVAILABLE)
        if res.tokens_basis is EvidenceBasis.UNAVAILABLE
        else Measurement(res.tokens_input if res.tokens_input is not None else res.tokens_output, res.tokens_basis)
    )
    estimated = (
        Measurement(res.estimated_tokens_total, EvidenceBasis.ESTIMATED, "ceil(packet bytes / 4)")
        if res.estimated_tokens_total is not None
        else Measurement(None, EvidenceBasis.UNAVAILABLE)
    )
    return {
        "experience_id": candidate.experience_id,
        "packet_attempt": candidate.episode.packet_attempt,
        "tokens": tokens.to_dict(),
        "estimated_tokens": estimated.to_dict(),
        "duration_s": Measurement(res.duration_s, res.duration_basis).to_dict(),
        "model": (
            Measurement(res.model, EvidenceBasis.OBSERVED).to_dict()
            if res.model
            else Measurement(None, EvidenceBasis.UNAVAILABLE).to_dict()
        ),
        "unreliable_metrics": list(res.unreliable_metrics),
        "note": "history, not a routing decision",
    }


# --- the artifact ------------------------------------------------------------------


def build_advice(
    query: ExperienceQuery,
    result: RetrievalResult,
    view: RepositoryView,
    *,
    work_order_fingerprint: str,
    as_of: dt.date,
    capture: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """Assemble the advisory for one task from one retrieval, revalidating every item.

    `capture` is the count of what the preceding capture pass indexed and
    refused, reported so a reader can see how much history the answer rests on.
    """
    refused: list[dict[str, str]] = []
    files: list[dict[str, Any]] = []
    tests: list[dict[str, Any]] = []
    graph_state = "not_needed"

    if result.precedents:
        graph_state = view.graph_state
        modules = task_modules(query, view)
        required = {normalise_path(t) for t in query.required_tests}
        seen_files: dict[str, dict[str, Any]] = {}
        seen_tests: dict[str, dict[str, Any]] = {}
        refused_seen: set[str] = set()

        def refuse(kind: str, path: str, reason: str) -> None:
            key = f"{kind}:{path}"
            if key not in refused_seen:
                refused_seen.add(key)
                refused.append({"item": key, "reason": reason})

        for candidate in result.precedents:
            episode = candidate.episode
            proposals: list[tuple[str, str]] = []
            proposals += [(p, f"changed by accepted precedent {episode.work_order_id}") for p in episode.outcome.files_changed]
            proposals += [(p, f"read by accepted precedent {episode.work_order_id}") for p in episode.outcome.files_read]
            proposals += [
                (key.split(":", 1)[1], f"approved context expansion in {episode.work_order_id}")
                for key in episode.outcome.expansions_approved
                if key.startswith("file:")
            ]
            for raw, reason in proposals:
                path = normalise_path(raw)
                if path.startswith("tests/"):
                    continue
                if path in seen_files:
                    if candidate.experience_id not in seen_files[path]["precedents"]:
                        seen_files[path]["precedents"].append(candidate.experience_id)
                    continue
                problem, checked = _file_check(path, query, view)
                if problem:
                    refuse("file", path, problem)
                    continue
                seen_files[path] = {
                    "path": path,
                    "reason": reason,
                    "precedents": [candidate.experience_id],
                    "checked": list(checked),
                }
            test_proposals = list(episode.features.required_tests) + list(episode.outcome.tests_passed)
            test_proposals += [p for p in episode.outcome.files_changed if p.startswith("tests/")]
            for raw in test_proposals:
                path = normalise_path(raw)
                if not path.startswith("tests/") or path in required:
                    continue
                if path in seen_tests:
                    if candidate.experience_id not in seen_tests[path]["precedents"]:
                        seen_tests[path]["precedents"].append(candidate.experience_id)
                    continue
                problem, checked = _test_check(path, query, view, modules)
                if problem:
                    refuse("test", path, problem)
                    continue
                seen_tests[path] = {
                    "path": path,
                    "reason": f"exercised by accepted precedent {episode.work_order_id}; a pattern to read, not a substitute for a required suite",
                    "precedents": [candidate.experience_id],
                    "checked": list(checked),
                }
        files = list(seen_files.values())[:MAX_SUGGESTED_FILES]
        tests = list(seen_tests.values())[:MAX_SUGGESTED_TESTS]

    warnings: list[dict[str, Any]] = []
    lines_used = 0
    for candidate in result.warnings:
        lines = _warning_lines(candidate)[: max(MAX_WARNING_LINES - lines_used, 0)]
        if not lines:
            break
        lines_used += len(lines)
        warnings.append(
            {
                "experience_id": candidate.experience_id,
                "work_order_id": candidate.episode.work_order_id,
                "class": candidate.precedent_class.value,
                "lines": lines,
                "why": list(candidate.why()),
            }
        )

    payload: dict[str, Any] = {
        "kind": ADVICE_KIND,
        "version": ADVICE_VERSION,
        "advisory_only": True,
        "work_order_id": query.work_order_id,
        "work_order_fingerprint": work_order_fingerprint,
        "attempt": query.attempt,
        "as_of": as_of.isoformat(),
        "status": result.status,
        "abstention": {"code": result.abstention, "detail": result.detail} if result.status != "precedent" else None,
        "precedents": [
            {
                "experience_id": c.experience_id,
                "work_order_id": c.episode.work_order_id,
                "packet_attempt": c.episode.packet_attempt,
                "class": c.precedent_class.value,
                "validity": c.validity.status.value,
                "settled_on": c.episode.settled_on.isoformat(),
                "outcome": _outcome_line(c),
                "why": list(c.why()),
                "signals": c.signals.to_dict(),
            }
            for c in result.precedents
        ],
        "warnings": warnings,
        "historical_only": [
            {
                "experience_id": c.experience_id,
                "work_order_id": c.episode.work_order_id,
                "class": c.precedent_class.value,
                "validity": c.validity.status.value,
                "reasons": list(c.validity.reasons[:4]),
            }
            for c in result.historical
        ],
        "suggested_files": files,
        "suggested_tests": tests,
        "refused": refused[:MAX_REFUSALS],
        "resource_history": [_resource_entry(c) for c in result.precedents],
        "measurement": {
            "episodes_in_store": result.episodes_in_store,
            "considered": result.considered,
            "excluded": dict(result.excluded),
            "refused_suggestions": len(refused),
            "store_problems": len(result.store_problems),
            "repository_graph": graph_state,
            "capture": dict(sorted((capture or {}).items())),
        },
        "truncated": False,
    }
    payload = _bounded(payload)
    assert_no_authority_keys(payload)
    unknown = set(payload) - ADVICE_KEYS
    if unknown:  # pragma: no cover - a vocabulary slip in this module
        raise ExperienceError(f"advice carries undeclared key(s): {sorted(unknown)}")
    payload["fingerprint"] = advice_fingerprint(payload)
    return payload


def _size(payload: Mapping[str, Any]) -> int:
    return len(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False))


def _bounded(payload: dict[str, Any]) -> dict[str, Any]:
    """Cut the lowest-value lists from the end until the payload fits."""
    order = ("refused", "historical_only", "resource_history", "warnings", "suggested_tests", "suggested_files", "precedents")
    for key in order:
        while _size(payload) > MAX_ADVICE_CHARS and payload[key]:
            payload[key] = payload[key][:-1]
            payload["truncated"] = True
    return payload


def unavailable_advice(
    work_order_id: str, work_order_fingerprint: str, attempt: int, *, as_of: dt.date, reason: str
) -> dict[str, Any]:
    """The advisory when experience itself failed: abstain, say why, carry nothing."""
    payload: dict[str, Any] = {
        "kind": ADVICE_KIND,
        "version": ADVICE_VERSION,
        "advisory_only": True,
        "work_order_id": work_order_id,
        "work_order_fingerprint": work_order_fingerprint,
        "attempt": attempt,
        "as_of": as_of.isoformat(),
        "status": "abstain",
        "abstention": {"code": "experience_unavailable", "detail": " ".join(reason.split())[:400]},
        "precedents": [],
        "warnings": [],
        "historical_only": [],
        "suggested_files": [],
        "suggested_tests": [],
        "refused": [],
        "resource_history": [],
        "measurement": {},
        "truncated": False,
    }
    payload["fingerprint"] = advice_fingerprint(payload)
    return payload


__all__ = [
    "ADVICE_KEYS",
    "ADVICE_KIND",
    "ADVICE_VERSION",
    "AUTHORITY_KEYS",
    "MAX_ADVICE_CHARS",
    "MAX_SUGGESTED_FILES",
    "MAX_SUGGESTED_TESTS",
    "advice_fingerprint",
    "assert_no_authority_keys",
    "build_advice",
    "read_refusal",
    "unavailable_advice",
]
