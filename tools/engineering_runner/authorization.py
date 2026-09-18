"""The authority a run receives, and the checks that hold it to it.

A coding session is told what it may change. Telling is not enforcing: the
instruction is text in a prompt, and a prompt is a request. This module is the
part that does not depend on the session having read anything.

## The three moments

1. **Before.** `AuthorityEnvelope.parse` reads the briefing Company OS issued
   and refuses one that contradicts itself - a packet whose writable scope is
   not the work order's authorized paths, a transport bundle naming a
   different packet, a reviewer packet that is not read-only. The runner acts
   on an envelope or it does not act.
2. **During.** The workspace is a worktree created at the work order's base
   commit, on the work order's branch, and the session runs there.
3. **After.** `verify_developer_changes` takes what git actually reports and
   compares it with the envelope. Nothing the session *said* participates.

## Why the path rules are written out again here

`company/runtime/path_scope.py` holds the canonical implementation and this
package may not import it - `tools/` is a production root. So the semantics
are restated: forbidden wins over allowed, an empty allow-list allows nothing,
matching is prefix matching on whole path segments, and separators are
normalised because a Windows session reports backslashes for the same file.

A duplicated rule is a rule that can drift, so the drift is made visible
rather than hoped away: `tests/test_company_external_engineering_runner.py`
imports both implementations and asserts they agree on a table of cases,
including the ones where they could plausibly differ. That test is the only
place in the repository where the two halves meet.

## What counts as a violation

Anything that would make the receipt a lie, and two things that would not:

- a changed path outside `may_write`, or inside `may_not_modify`
- a protected governance file whose bytes moved, whatever the diff says
- a branch, worktree or base commit that is not the authorized one
- a base commit that is no longer an ancestor of HEAD, which is a rewrite
- a dependency file changed when the work order did not authorize one

The last one is not strictly an authority matter - `permissions.yaml` routes a
new dependency to a review rather than refusing it - so it is reported as a
violation only when `requirements.txt` is outside the authorized paths, which
is the case that means the session edited a file it was not given.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence

from .errors import IntegrityFailure


_WINDOWS_DRIVE = re.compile(r"[A-Za-z]:")

# Files whose change is a dependency change. `permissions.yaml` sends one to
# architecture_and_security_review; the runner's job is to notice it happened.
DEPENDENCY_FILES: tuple[str, ...] = ("requirements.txt", "pyproject.toml", "setup.cfg")

# A review is a different task from the work it reviews, and Company OS says so
# in the id: `EngineeringWorkOrder.review_specification` builds
# `<work_order_id>-review`, because the two route to different employees by
# different capabilities and that difference *is* the separation of duties. The
# suffix is restated here and pinned to the original in
# `tests/test_company_external_engineering_runner.py`.
REVIEW_TASK_SUFFIX = "-review"


def normalise_path(value: str, field_name: str = "path") -> str:
    """A repository-relative POSIX path, or a refusal.

    Mirrors `company.runtime.path_scope.normalise_path`. An absolute path, a
    drive letter or a `..` segment is refused rather than resolved: a scope
    rule has to name one unambiguous location, and a path that escapes the
    repository is the first thing a scope check must not accept.
    """
    if not isinstance(value, str) or not value.strip():
        raise IntegrityFailure(f"{field_name}: a path is required, got {value!r}")
    text = value.strip().replace("\\", "/")
    while "//" in text:
        text = text.replace("//", "/")
    if text.startswith("./"):
        text = text[2:]
    text = text.rstrip("/")
    if not text:
        raise IntegrityFailure(f"{field_name}: a path is required, got {value!r}")
    if text.startswith("/") or _WINDOWS_DRIVE.fullmatch(text.split("/", 1)[0]):
        raise IntegrityFailure(
            f"{field_name}: {value!r} is absolute; scope rules are repository-relative"
        )
    if any(segment in ("", ".", "..") for segment in text.split("/")):
        raise IntegrityFailure(
            f"{field_name}: {value!r} contains a relative segment; a scope rule must "
            "name one unambiguous location"
        )
    return text


def _covers(rule: str, path: str) -> bool:
    return path == rule or path.startswith(rule + "/")


@dataclass(frozen=True)
class PathRules:
    """What a run may change, and what it may never touch."""

    allowed: tuple[str, ...] = ()
    forbidden: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("allowed", "forbidden"):
            values = getattr(self, name)
            object.__setattr__(
                self,
                name,
                tuple(sorted({normalise_path(item, name) for item in values})),
            )

    @property
    def read_only(self) -> bool:
        return not self.allowed

    def forbids(self, path: str) -> str:
        for rule in self.forbidden:
            if _covers(rule, path):
                return rule
        return ""

    def permits(self, path: str) -> bool:
        return any(_covers(rule, path) for rule in self.allowed)

    def violations(self, paths: Iterable[str]) -> tuple[str, ...]:
        """Every reported path the rules refuse, as sorted findings."""
        found: list[str] = []
        for raw in paths:
            path = normalise_path(raw, "changed path")
            rule = self.forbids(path)
            if rule:
                found.append(f"{path} is covered by forbidden rule {rule}")
            elif not self.permits(path):
                found.append(f"{path} is outside every authorized path")
        return tuple(sorted(set(found)))


@dataclass(frozen=True)
class AuthorityEnvelope:
    """One role's authority for one packet attempt, read off a Company OS brief.

    Every field is copied from the briefing. None is computed, defaulted or
    widened: the envelope is a reading of an authorization, and a reading that
    could add something would be an authorization of its own.
    """

    role: str
    work_order_id: str
    work_order_fingerprint: str
    task_id: str
    packet_fingerprint: str
    packet_attempt: int
    authority_fingerprint: str
    employee: str
    objective: str
    authorized_branch: str
    base_commit: str
    # What *this session* may change. Empty for a reviewer, which is what
    # read-only means.
    may_write: tuple[str, ...]
    # What the *work order* authorized, whoever is reading. A reviewer needs
    # this and must not be given `may_write` instead: judging whether the work
    # stayed in scope means comparing the diff with the grant, and a reviewer
    # shown its own empty scope has nothing to compare against.
    authorized_paths: tuple[str, ...]
    may_not_modify: tuple[str, ...]
    protected_paths: tuple[str, ...]
    required_tests: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    constraints: tuple[str, ...]
    escalate_instead_of: tuple[str, ...]
    context_refs: tuple[str, ...]
    max_developer_attempts: int
    review_instructions: tuple[str, ...] = ()
    implementer: str = ""
    packet: Mapping[str, Any] = field(default_factory=dict)

    @property
    def rules(self) -> PathRules:
        return PathRules(allowed=self.may_write, forbidden=self.may_not_modify)

    @property
    def read_only(self) -> bool:
        return not self.may_write

    def summary(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "work_order_id": self.work_order_id,
            "work_order_fingerprint": self.work_order_fingerprint,
            "packet_fingerprint": self.packet_fingerprint,
            "packet_attempt": self.packet_attempt,
            "authority_fingerprint": self.authority_fingerprint,
            "employee": self.employee,
            "implementer": self.implementer,
            "authorized_branch": self.authorized_branch,
            "base_commit": self.base_commit,
            "may_write": list(self.may_write),
            "authorized_paths": list(self.authorized_paths),
            "may_not_modify": list(self.may_not_modify),
            "required_tests": list(self.required_tests),
            "read_only": self.read_only,
        }

    @classmethod
    def parse(cls, payload: Mapping[str, Any]) -> "AuthorityEnvelope":
        """Read one `brief` or `review-brief` payload, refusing an inconsistent one."""
        if not isinstance(payload, Mapping):
            raise IntegrityFailure("a briefing must be a JSON object")
        role = str(payload.get("role", ""))
        if role not in ("developer", "reviewer"):
            raise IntegrityFailure(f"briefing role {role!r} is neither developer nor reviewer")
        order = payload.get("work_order")
        packet = payload.get("packet")
        transport = payload.get("transport")
        for name, value in (("work_order", order), ("packet", packet), ("transport", transport)):
            if not isinstance(value, Mapping):
                raise IntegrityFailure(f"briefing is missing its {name} object")
        assert isinstance(order, Mapping) and isinstance(packet, Mapping)
        assert isinstance(transport, Mapping)

        packet_fingerprint = str(payload.get("packet_fingerprint", ""))
        if not packet_fingerprint:
            raise IntegrityFailure("briefing names no packet fingerprint")
        persisted = payload.get("persisted", {})
        persisted = persisted if isinstance(persisted, Mapping) else {}
        packet_pointer = persisted.get("packet", {})
        packet_pointer = packet_pointer if isinstance(packet_pointer, Mapping) else {}
        attempt = int(packet_pointer.get("attempt", 0) or 0)
        if str(packet_pointer.get("fingerprint", packet_fingerprint)) != packet_fingerprint:
            raise IntegrityFailure(
                f"the briefing names packet {packet_fingerprint} and the record it "
                f"persisted is {packet_pointer.get('fingerprint')}; the two halves "
                "describe different packets"
            )
        if int(transport.get("packet_attempt", attempt) or 0) != attempt:
            raise IntegrityFailure(
                f"the transport bundle is for attempt {transport.get('packet_attempt')} "
                f"and the persisted packet is attempt {attempt}"
            )
        work_order_id = str(order.get("work_order_id", ""))
        if not work_order_id:
            raise IntegrityFailure("briefing names no work order")
        task_id = str(packet.get("task_id", ""))
        expected_task = (
            work_order_id
            if role == "developer"
            else f"{work_order_id}{REVIEW_TASK_SUFFIX}"
        )
        if task_id != expected_task:
            raise IntegrityFailure(
                f"the {role} packet is for task {task_id!r} and this work order's "
                f"{role} task is {expected_task!r}; the runner will not act on the pair"
            )
        branch = str(order.get("authorized_branch", ""))
        if str(packet.get("expected_branch", branch)) != branch:
            raise IntegrityFailure(
                f"the packet expects branch {packet.get('expected_branch')!r} and the "
                f"work order authorizes {branch!r}"
            )
        base = str(order.get("base_commit", ""))
        if str(packet.get("expected_base_commit", base)) != base:
            raise IntegrityFailure(
                f"the packet expects base {packet.get('expected_base_commit')} and the "
                f"work order names {base}"
            )

        scope = packet.get("path_scope")
        scope_allowed = _strings(scope.get("allowed", ()) if isinstance(scope, Mapping) else ())
        scope_forbidden = _strings(
            scope.get("forbidden", ()) if isinstance(scope, Mapping) else ()
        )
        authorized = _strings(order.get("authorized_paths", ()))
        forbidden = _strings(order.get("forbidden_paths", ()))
        protected = _strings(order.get("protected_paths", ()))

        if role == "developer":
            # Both halves of the packet's scope are checked, not just the
            # permissive one. A packet that allowed the right paths but had
            # lost its forbidden list would pass a naive check and would let a
            # protected file through, because forbidden is what wins.
            if PathRules(allowed=scope_allowed) != PathRules(allowed=authorized):
                raise IntegrityFailure(
                    "the packet's writable scope is not the work order's authorized "
                    f"paths: packet {sorted(scope_allowed)} vs work order "
                    f"{sorted(authorized)}"
                )
            refused = set(forbidden) | set(protected)
            if PathRules(allowed=scope_forbidden) != PathRules(allowed=tuple(refused)):
                raise IntegrityFailure(
                    "the packet's forbidden scope is not the work order's forbidden "
                    f"plus protected paths: packet {sorted(scope_forbidden)} vs work "
                    f"order {sorted(refused)}"
                )
        elif scope_allowed:
            # A reviewer packet is built with no path scope at all, so an empty
            # forbidden list is correct there and only the allow-list matters:
            # an empty allow-list allows nothing, which is what read-only means.
            raise IntegrityFailure(
                "a reviewer packet granted a writable path; review is read-only by "
                "construction and the runner refuses a packet that is not"
            )

        return cls(
            role=role,
            work_order_id=work_order_id,
            work_order_fingerprint=str(order.get("work_order_fingerprint", "")),
            task_id=task_id,
            packet_fingerprint=packet_fingerprint,
            packet_attempt=attempt,
            authority_fingerprint=str(transport.get("authority_fingerprint", "")),
            employee=str(payload.get("employee") or payload.get("reviewer") or ""),
            objective=str(order.get("objective", "")),
            authorized_branch=branch,
            base_commit=base,
            may_write=tuple(sorted(authorized)) if role == "developer" else (),
            authorized_paths=tuple(sorted(authorized)),
            may_not_modify=tuple(sorted(set(forbidden) | set(protected))),
            protected_paths=tuple(sorted(protected)),
            required_tests=_strings(order.get("required_tests", ())),
            acceptance_criteria=_strings(order.get("acceptance_criteria", ())),
            constraints=_strings(order.get("constraints", ())),
            escalate_instead_of=_strings(order.get("escalate_instead_of", ())),
            context_refs=_strings(order.get("context_refs", ())),
            max_developer_attempts=int(order.get("max_developer_attempts", 0) or 0),
            review_instructions=_strings(payload.get("review_instructions", ())),
            implementer=str(payload.get("implementer", "")),
            packet=dict(packet),
        )


@dataclass(frozen=True)
class AuthorityVerdict:
    """Whether a run stayed inside its authority, and every reason it did not."""

    violations: tuple[str, ...] = ()
    checked: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.violations

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "violations": list(self.violations),
            "checked": list(self.checked),
        }


def digest_paths(repo_root: Path, paths: Sequence[str]) -> dict[str, str]:
    """A SHA-256 per path, or the marker `absent`.

    Absent is recorded rather than skipped. A protected file that exists before
    the work and not after has been deleted, and a digest map that simply
    omitted it would compare equal to one that never saw it.
    """
    digests: dict[str, str] = {}
    for raw in paths:
        path = normalise_path(raw, "protected path")
        target = Path(repo_root) / path
        if not target.is_file():
            digests[path] = "absent"
            continue
        digests[path] = hashlib.sha256(target.read_bytes()).hexdigest()
    return digests


def protected_drift(before: Mapping[str, str], after: Mapping[str, str]) -> tuple[str, ...]:
    """Every protected path whose bytes moved between two digest maps."""
    findings: list[str] = []
    for path in sorted(set(before) | set(after)):
        old = before.get(path, "missing")
        new = after.get(path, "missing")
        if old != new:
            findings.append(f"protected path {path} changed ({old[:12]} -> {new[:12]})")
    return tuple(findings)


def verify_developer_changes(
    envelope: AuthorityEnvelope,
    *,
    changed_paths: Sequence[str],
    branch: str,
    head_commit: str,
    base_is_ancestor: bool,
    protected_before: Mapping[str, str],
    protected_after: Mapping[str, str],
    worktree_identity_ok: bool,
    worktree_reason: str = "",
) -> AuthorityVerdict:
    """Compare what git reports with what the work order authorized.

    `changed_paths` comes from `git diff --name-status` plus the porcelain
    status, never from the session's own account of itself. That is the point:
    a session that under-reports its changes is exactly the case this check
    exists for, and a check fed the session's list would agree with it.
    """
    violations: list[str] = []
    checked = [
        "changed paths against may_write",
        "changed paths against may_not_modify",
        "protected governance digests",
        "branch identity",
        "worktree identity",
        "base commit ancestry",
        "dependency files",
    ]

    violations.extend(envelope.rules.violations(changed_paths))
    violations.extend(protected_drift(protected_before, protected_after))

    if branch != envelope.authorized_branch:
        violations.append(
            f"work landed on branch {branch!r}, not the authorized "
            f"{envelope.authorized_branch!r}"
        )
    if not worktree_identity_ok:
        violations.append(
            worktree_reason or "the work did not happen in the authorized worktree"
        )
    if envelope.base_commit and not base_is_ancestor:
        violations.append(
            f"the authorized base {envelope.base_commit[:12]} is not an ancestor of "
            f"{head_commit[:12]}; history was rewritten or the branch was rebased"
        )

    normalised = {normalise_path(item, "changed path") for item in changed_paths}
    for dependency in DEPENDENCY_FILES:
        if dependency in normalised and not envelope.rules.permits(dependency):
            violations.append(
                f"{dependency} changed and the work order does not authorize it; a "
                "dependency change is a separate authorization"
            )

    return AuthorityVerdict(
        violations=tuple(sorted(set(violations))), checked=tuple(checked)
    )


def verify_reviewer_left_no_trace(
    *,
    head_before: str,
    head_after: str,
    status_after: Sequence[str],
) -> AuthorityVerdict:
    """A review changes nothing, and this is how that is known rather than asked."""
    violations: list[str] = []
    if head_before != head_after:
        violations.append(
            f"the review session moved HEAD from {head_before[:12]} to {head_after[:12]}"
        )
    if status_after:
        violations.append(
            "the review session left the worktree dirty: "
            + ", ".join(sorted(status_after)[:5])
        )
    return AuthorityVerdict(
        violations=tuple(violations),
        checked=("HEAD before and after review", "worktree status after review"),
    )


def _strings(values: Any) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, (list, tuple)):
        return ()
    return tuple(str(item) for item in values if str(item).strip())


__all__ = [
    "DEPENDENCY_FILES",
    "REVIEW_TASK_SUFFIX",
    "AuthorityEnvelope",
    "AuthorityVerdict",
    "PathRules",
    "digest_paths",
    "normalise_path",
    "protected_drift",
    "verify_developer_changes",
    "verify_reviewer_left_no_trace",
]
