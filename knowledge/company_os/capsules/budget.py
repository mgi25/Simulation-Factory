"""The size contract, as numbers a test can fail on.

A capsule exists to stop a future session reading `company/runtime/` in full
before it can safely change one function in it. That only works while the
capsule is *cheaper than the thing it replaces*. Nothing about a capsule
resists growth on its own: the natural life of an authoritative document is to
accrete, and the accreted version is a second README, which is the failure mode
this layer exists to prevent.

So the limits live here, they are enforced at construction, and a capsule that
exceeds them cannot be built.

## The four rules that do the work

1. **No field holds more than one line.** This is the whole anti-dump rule. A
   pasted function, a copied config block, a quoted diff - all of them carry a
   newline, and all of them fail before anything else is checked.
2. **A pointer field must look like a pointer.** Paths, globs, test node ids
   and record ids match `POINTER_PATTERN`; a line of source does not, because
   source has spaces, parentheses and semicolons in it. Rule 1 catches the
   multi-line dump, this catches the one-liner.
3. **Lists are short.** Eight items. A module with nine invariants has not
   found nine invariants, it has written down nine sentences.
4. **The whole capsule has a ceiling.** `MAX_CAPSULE_CHARS` is measured over
   the capsule's own canonical JSON, which is exactly what a session pays to
   read it.

## Why characters and not tokens

A token count belongs to one tokenizer, and the platform is provider-agnostic
by contract (`ai_platform/README.md`). Characters are stable across providers,
reproducible from the file alone, and monotone in the thing we actually care
about. The numbers below are budgets, not measurements: they were chosen so
that a truthful capsule for a real Company OS module fits with room to spare
and a capsule that started copying its module does not.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ai_platform.references import ReferenceViolation, assert_text

# A pointer: a repo path, a glob, a test node id, a capsule id, a record id.
# Deliberately narrow. Spaces, quotes, parentheses, braces, commas, equals and
# semicolons are absent, which is what makes a line of source fail it.
POINTER_PATTERN = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_./*:#@-]{0,199}$")

# A capability tag, the vocabulary the selector matches on.
TAG_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,63}$")


class CapsuleError(ValueError):
    """A capsule that would mislead or bloat a future session if it were stored."""


@dataclass(frozen=True)
class CapsuleBudget:
    """Every limit in one place, so tightening the contract is a one-line change."""

    max_capsule_chars: int = 4000
    max_title_chars: int = 80
    max_owner_chars: int = 80
    max_purpose_chars: int = 400
    max_statement_chars: int = 240
    max_list_items: int = 8
    max_paths: int = 12
    max_knowledge_links: int = 12
    max_references: int = 48


DEFAULT_BUDGET = CapsuleBudget()


def assert_line(value: str, field: str, limit: int) -> str:
    """Return `value` if it is a single line within `limit` characters.

    The three failures, in order: empty, multi-line, too long. The multi-line
    message names the count because the caller almost always pasted something.
    """
    assert_text(value, field)
    if "\n" in value or "\r" in value:
        raise CapsuleError(
            f"{field}: a capsule field is one line; this has "
            f"{value.count(chr(10)) + 1}. Reference the source instead of copying it."
        )
    if len(value) > limit:
        raise CapsuleError(
            f"{field}: {len(value)} characters exceeds the {limit}-character limit. "
            "Say less, or point at the file that says it."
        )
    return value


def assert_pointer(value: str, field: str) -> str:
    """Return `value` if it is pointer-shaped, else raise.

    Runs `assert_line` first so a pasted block fails with the honest message,
    then requires the pointer shape so a single line of source fails too.
    """
    assert_line(value, field, 200)
    if not POINTER_PATTERN.match(value):
        raise CapsuleError(
            f"{field}: {value!r} is not a reference. A capsule points at paths, "
            "globs, test node ids and record ids - it never carries their contents."
        )
    return value


def assert_tag(value: str, field: str) -> str:
    if not isinstance(value, str) or not TAG_PATTERN.match(value):
        raise CapsuleError(
            f"{field}: capability tag {value!r} must be lowercase [a-z0-9_], "
            "start with a letter, and be 2-64 characters"
        )
    return value


def assert_list(
    values: tuple[str, ...], field: str, limit: int, check, arg: int | None = None
) -> tuple[str, ...]:
    """Apply `check` to every item and refuse a list longer than `limit`."""
    if len(values) > limit:
        raise CapsuleError(
            f"{field}: {len(values)} items exceeds the {limit} a capsule may carry. "
            "A longer list is a document, and a document belongs behind a reference."
        )
    for index, value in enumerate(values):
        label = f"{field}[{index}]"
        try:
            if arg is None:
                check(value, label)
            else:
                check(value, label, arg)
        except ReferenceViolation as exc:  # keep one error type at the boundary
            raise CapsuleError(str(exc)) from exc
    return values
