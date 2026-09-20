"""A reference is a pointer, never a body.

The context policy in `ai_platform/README.md` says a request should contain the
relevant module contract, files, tests and evidence. It does not say it should
contain their *contents*. The difference is the whole point of the AI platform:
a manifest that names `sloped/scale.py:59-71` costs a line, and one that pastes
the file costs a thousand - and the second one is what happens by accident,
every time, unless something refuses it.

So refusal lives here, in one guard that both the context manifest and the
knowledge records call. A reference is a single line, short enough to be a
path, an id, a commit sha or a URL. The moment a caller tries to smuggle a
paragraph of source through a `ref=` field, construction fails with the field
name that did it.

`MAX_REF_CHARS` is a budget, not a measurement: paths in this repository run to
about 60 characters and the longest plausible reference (a path plus a line
span plus a test node id) is well under 200. A value over it is not a long
path, it is content.
"""

from __future__ import annotations

MAX_REF_CHARS = 200


class ReferenceViolation(ValueError):
    """A field that must hold a pointer was given content, or nothing."""


def assert_reference(value: str, field: str) -> str:
    """Return `value` if it is a usable single-line reference, else raise.

    The three failure modes, in the order they are checked: nothing supplied,
    more than one line, longer than a reference can plausibly be.
    """
    if not isinstance(value, str) or not value.strip():
        raise ReferenceViolation(f"{field}: a reference is required, got {value!r}")
    if "\n" in value or "\r" in value:
        raise ReferenceViolation(
            f"{field}: a reference is one line; this is embedded content "
            f"({value.count(chr(10)) + 1} lines). Reference the source instead."
        )
    if len(value) > MAX_REF_CHARS:
        raise ReferenceViolation(
            f"{field}: {len(value)} characters exceeds the {MAX_REF_CHARS}-character "
            "reference budget. This is content, not a pointer."
        )
    return value


def assert_text(value: str, field: str) -> str:
    """Return `value` if it is non-empty prose, else raise.

    Prose fields - an objective, a rationale, a rollback plan - may be long and
    may wrap. They are held to existence only.
    """
    if not isinstance(value, str) or not value.strip():
        raise ReferenceViolation(f"{field}: must not be empty")
    return value
