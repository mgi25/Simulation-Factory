"""What a session is given - as a list of pointers, with a size you can measure.

The context policy in `ai_platform/README.md` lists what a request should
contain: objective, module contract, files, tests, current decision and
experiment evidence, constraints, acceptance criteria. A manifest is that list,
built before the session starts, and it holds *references* to those things.

## The invariant

A manifest never embeds content. Every `ContextRef.ref` goes through
`ai_platform.references.assert_reference`, so a path, a test node id, a commit
sha or a knowledge-record id is accepted and a pasted paragraph of source is a
construction error. This is the only mechanism in the platform that resists the
default failure of agent context assembly, which is not "we forgot a file" but
"we pasted six of them just in case".

The consequence worth stating plainly: a manifest is small enough that keeping
one per task is free, and keeping them is what makes context spend measurable
at all.

## What it buys

Three of the efficiency metrics in the README fall out of the structure rather
than needing separate instrumentation:

- *duplicated context* - `validate()` reports repeated ref keys, because
  constitution rule 15 says a canonical fact is stored once;
- *context supplied but unused* - `unused()` compares what was handed over
  against the keys the session actually reports touching;
- *cache hit rate* - `fingerprint()` is stable across sessions, so an identical
  manifest can be recognised as an identical request.

## What it does not do

It does not fetch anything. Resolving a ref to bytes is the caller's job and
happens at execution time, outside this module, which is why a manifest can be
built, validated, stored and diffed without touching the repository it
describes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ai_platform.references import assert_reference, assert_text
from ai_platform.resource_classes import ReasoningClass, resource_class
from ai_platform.serde import fingerprint as _fingerprint


class ContextKind(Enum):
    """The kinds of thing a session can be pointed at."""

    MODULE_CONTRACT = "module_contract"
    FILE = "file"
    FACT = "fact"
    TEST = "test"
    BENCHMARK = "benchmark"
    DECISION = "decision"
    EXPERIMENT = "experiment"


@dataclass(frozen=True)
class ContextRef:
    """One pointer, and the reason it earned its place in the manifest.

    `reason` is required and not decoration: a ref nobody can justify in a
    phrase is a ref that should not be in the request. It is also what the next
    session reads when deciding whether the manifest is still right.
    """

    kind: ContextKind
    ref: str
    reason: str
    span: tuple[int, int] | None = None  # optional line range; still a pointer
    digest: str = ""  # optional content hash, for cache validation

    def __post_init__(self) -> None:
        assert_reference(self.ref, f"{self.kind.value} ref")
        assert_text(self.reason, f"{self.kind.value} reason")
        if self.span is not None:
            start, end = self.span
            if start < 1 or end < start:
                raise ValueError(f"{self.ref}: invalid line span {self.span!r}")

    @property
    def key(self) -> str:
        """Stable identity, used for de-duplication and usage accounting."""
        if self.span is None:
            return f"{self.kind.value}:{self.ref}"
        return f"{self.kind.value}:{self.ref}#{self.span[0]}-{self.span[1]}"


# Which kinds may appear in which group. A structural check, so a manifest
# cannot quietly file a source file under "facts".
_GROUP_KINDS: dict[str, frozenset[ContextKind]] = {
    "module_contracts": frozenset({ContextKind.MODULE_CONTRACT}),
    "files": frozenset({ContextKind.FILE}),
    "facts": frozenset({ContextKind.FACT}),
    "tests": frozenset({ContextKind.TEST, ContextKind.BENCHMARK}),
    "decisions": frozenset({ContextKind.DECISION}),
    "experiments": frozenset({ContextKind.EXPERIMENT}),
}

# Declaration order of the groups, which is also the order `refs()` returns.
_GROUPS: tuple[str, ...] = tuple(_GROUP_KINDS)


@dataclass(frozen=True)
class ContextManifest:
    """Everything one session is handed, and nothing else."""

    task_id: str
    objective: str
    reasoning_class: ReasoningClass
    module_contracts: tuple[ContextRef, ...] = ()
    files: tuple[ContextRef, ...] = ()
    facts: tuple[ContextRef, ...] = ()
    tests: tuple[ContextRef, ...] = ()
    decisions: tuple[ContextRef, ...] = ()
    experiments: tuple[ContextRef, ...] = ()
    constraints: tuple[str, ...] = ()
    acceptance_criteria: tuple[str, ...] = ()
    notes: str = ""

    def __post_init__(self) -> None:
        assert_reference(self.task_id, "task_id")
        assert_text(self.objective, "objective")

    def refs(self) -> tuple[ContextRef, ...]:
        """Every ref, in declared group order - stable across sessions."""
        out: list[ContextRef] = []
        for group in _GROUPS:
            out.extend(getattr(self, group))
        return tuple(out)

    def keys(self) -> tuple[str, ...]:
        return tuple(ref.key for ref in self.refs())

    def validate(self) -> tuple[str, ...]:
        """Return the manifest's violations. Empty means it is fit to send."""
        problems: list[str] = []

        if not self.acceptance_criteria:
            problems.append(
                "no acceptance criteria: the context policy requires explicit "
                "acceptance criteria, and 'make it better' is not one "
                "(constitution, Reference superiority)"
            )

        for group in _GROUPS:
            allowed = _GROUP_KINDS[group]
            for ref in getattr(self, group):
                if ref.kind not in allowed:
                    names = "/".join(sorted(k.value for k in allowed))
                    problems.append(f"{group}: {ref.key} is a {ref.kind.value}, expected {names}")

        seen: dict[str, int] = {}
        for key in self.keys():
            seen[key] = seen.get(key, 0) + 1
        for key, count in sorted(seen.items()):
            if count > 1:
                problems.append(f"duplicated context: {key} supplied {count} times")

        ceiling = resource_class(self.reasoning_class).max_context_refs
        supplied = len(self.refs())
        if supplied > ceiling:
            problems.append(
                f"context budget: {supplied} refs exceeds the {ceiling} allowed for "
                f"class {self.reasoning_class.value}"
            )

        return tuple(problems)

    def assert_valid(self) -> ContextManifest:
        problems = self.validate()
        if problems:
            raise ValueError(f"invalid context manifest {self.task_id}: " + "; ".join(problems))
        return self

    def fingerprint(self) -> str:
        """A stable digest of the request, usable as a retrieval-cache key."""
        return _fingerprint(self)

    def size_chars(self) -> int:
        """The manifest's own footprint - what the reference discipline costs.

        Counts the objective, constraints, criteria and every ref plus reason.
        Not the size of what the refs point at, which is the entire point:
        this number stays in the hundreds while the referenced material runs to
        hundreds of thousands.
        """
        total = len(self.objective) + len(self.task_id)
        total += sum(len(text) for text in self.constraints)
        total += sum(len(text) for text in self.acceptance_criteria)
        for ref in self.refs():
            total += len(ref.key) + len(ref.reason) + len(ref.digest)
        return total

    def unused(self, used_keys: tuple[str, ...] | list[str]) -> tuple[str, ...]:
        """Refs supplied but never touched - the README's 'context supplied but unused'."""
        used = set(used_keys)
        return tuple(key for key in self.keys() if key not in used)

    def utilisation(self, used_keys: tuple[str, ...] | list[str]) -> float:
        """Fraction of supplied refs the session actually used, 0.0 to 1.0."""
        supplied = self.keys()
        if not supplied:
            return 1.0
        used = set(used_keys) & set(supplied)
        return len(used) / len(supplied)
