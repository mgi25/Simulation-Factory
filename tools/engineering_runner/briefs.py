"""Turning a Company OS packet into the text a session actually reads.

The packet is already the briefing. Section 6 of the milestone is explicit
that a backend should receive the existing `SessionPacket` rather than a new
handcrafted prompt, and this module is what keeps that true: it renders the
packet and the work order's own terms, and adds only the things a process
boundary makes necessary - where to put the answer, and that the runner (not
the session) will commit.

## Nothing here is persuasion

There is no role-play preamble, no "think carefully", no quality exhortation.
Every line is either a term Company OS authorized or a mechanical instruction
about the handoff. That matters for a reason beyond taste: if the runner's
prose could change what gets built, then the work order is no longer the
ceiling, and a prompt edit becomes an ungoverned authorization.

## The session does not commit

The runner commits, after it has checked the diff against `may_write`. A
session that committed its own work would be choosing what the evidence says,
and the one thing the authority check must not consume is the session's
account of itself.

## The session does not push, merge, tag or deploy

Those are named as refusals rather than omitted, because a capable session
that believes it is finishing a job will otherwise do the tidy thing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .authorization import AuthorityEnvelope
from .execution_context import (
    ExecutionContextBundle,
    build_execution_context,
    rank_primary_files,
    rank_task_spans,
    rank_test_anchors,
)
from .repo_map import RepoMap
from .resources import ResourceStrategy


DEVELOPER_REPORT_NAME = "report.json"
REVIEW_DIFF_NAME = "diff.patch"

# The narrative a receipt needs and a machine cannot observe. Everything else
# in the receipt - the commit, the changed paths, the test results - the runner
# measures, so the session is never asked for it.
DEVELOPER_REPORT_FIELDS: tuple[tuple[str, str], ...] = (
    ("outcome", '"accepted" if the work order is implemented, "rejected" if not'),
    ("summary", "two or three sentences: what you changed and why, for the next reader"),
    ("rejection_reason", "required when outcome is rejected; empty otherwise"),
    ("invariants_preserved", "list of strings: what you were careful not to break"),
    ("unresolved_risks", "list of strings: what a reviewer should look at hardest"),
    ("evidence", "list of repository paths or references a reviewer can open"),
    ("context_refs_used", "list of the packet's context reference keys you actually used"),
    ("notes", "anything else worth recording; may be empty"),
)

REVIEW_REPORT_FIELDS: tuple[tuple[str, str], ...] = (
    ("verdict", '"pass", "changes_required" or "blocked"'),
    (
        "criteria",
        'list of {"criterion": <the exact criterion text>, "satisfied": true/false, '
        '"evidence_ref": <a POINTER that shows it - one line, at most 200 characters, '
        'such as a path, a path with a line span, a symbol name or a commit. Not the '
        'reasoning. Required when satisfied is true.>}',
    ),
    (
        "findings",
        'list of {"finding_id": <lowercase id, 3-64 chars>, "severity": '
        '"advisory"|"changes_required"|"blocking", "summary": <one sentence>, '
        '"evidence_ref": <where to look; the same one-line 200-character pointer>}',
    ),
    ("evidence", "list of references you read; pointers, at most 32, one line each"),
    ("changed_paths_reviewed", "the paths you actually reviewed; at most 64"),
    ("notes", "anything the CEO should know that is not a finding"),
)


def _ceiling_lines(strategy: "ResourceStrategy | None", *, role: str) -> list[str]:
    """What this session may spend, and which of those limits actually binds.

    One wording for both roles. Telling a session an advisory number and an
    enforced one in the same list, and saying which is which, is the whole
    point: a session that treats the turn ceiling as a wall stops early for no
    reason, and one that treats the wall clock as advice is terminated
    mid-sentence.
    """
    if strategy is None:
        return []
    out = [
        "",
        "## How much of the company this job is worth",
        "",
        (
            f"Company OS runs this under its {strategy.profile!r} resource profile "
            f"and recommended the {strategy.model_tier} model tier "
            f"({strategy.strategy_reason})."
        ),
        "",
        "Which of these binds, and which does not:",
        (
            f"  - wall clock: {strategy.max_wall_seconds}s. **Enforced** - this "
            "session's process is terminated at that point, mid-sentence if need be."
        ),
    ]
    if strategy.max_session_cost:
        out.append(
            f"  - spend: {strategy.max_session_cost} {strategy.cost_currency}. "
            "**Enforced by the provider** when the backend accepts a ceiling."
        )
    if strategy.max_turns_advisory:
        out.append(
            f"  - turns: about {strategy.max_turns_advisory}. **Not enforced** - "
            "nothing stops you at it. It is the shape of a session that fits, and "
            "going far past it means the task was larger than the work order "
            "described."
        )
    out.append("")
    if role == "developer":
        out.append(
            "Work to finish inside them rather than up to them. If the task turns "
            "out not to fit, stop, leave what is complete and correct in the working "
            "tree, and say so in your report: a partial result somebody can continue is worth more "
            "than a complete one that was cut off at the ceiling."
        )
    else:
        out.append(
            "If the diff is larger than these allow, say so in your notes and "
            "report on what you did read. A review that ran out of budget and said "
            "nothing is worse than a short one that says where it stopped."
        )
    out.append(
        "Prefer reading the specific file you need over searching the whole "
        "repository, and do not re-read a file you have already read."
    )
    return out


# Fixed and non-negotiable in the sense that every field here already exists:
# this is not a quality exhortation, it is the same ordering the runner itself
# applies before adding anything under `tools/` - reuse first, extend the
# smallest surface, reach for the standard library before a new dependency,
# keep the diff small, and do not build for a case the objective did not ask
# for. Stated once, plainly, rather than left to be inferred from the size of
# the packet.
_MINIMALISM_LINES: tuple[str, ...] = (
    "## Preference order for how you get there",
    "",
    "  1. Reuse existing code before writing new code.",
    "  2. Modify the smallest existing surface that satisfies the objective.",
    "  3. Reach for the standard library or an already-declared dependency "
    "before adding a new one.",
    "  4. Prefer the smallest coherent diff over a larger, tidier-looking one.",
    "  5. Do not build an abstraction, a config flag or a fallback path for a "
    "case the objective did not ask for.",
    "",
    "This is an ordering, not a ban: a genuinely new capability still gets "
    "written. It is a tie-breaker for the many points where more than one "
    "correct-looking change exists.",
    "",
)


def developer_execution_context(
    repo_map: "RepoMap | None",
    *,
    envelope: AuthorityEnvelope,
    worktree: Path,
    preferred_symbols: Sequence[tuple[str, str]] = (),
) -> ExecutionContextBundle:
    """The developer's bundle: authorized paths first, then the objective's
    own best matches - see `execution_context.rank_primary_files`."""
    primary = rank_primary_files(
        repo_map, objective=envelope.objective, focus_paths=envelope.may_write
    )
    test_paths = tuple(
        dict.fromkeys(
            [
                str(ref.get("ref", ""))
                for ref in envelope.packet.get("context_refs", ())
                if isinstance(ref, Mapping) and ref.get("kind") == "test"
            ]
            + [path for path in envelope.may_write if path.startswith("tests/")]
        )
    )
    semantic_paths = tuple(
        dict.fromkeys(
            [
                *envelope.may_write,
                *test_paths,
                *envelope.required_tests,
            ]
        )
    )
    compiled_spans = rank_task_spans(
        repo_map,
        objective=envelope.objective,
        acceptance_criteria=envelope.acceptance_criteria,
        paths=semantic_paths,
        repo_root=worktree,
        preferred_symbols=preferred_symbols,
    )
    test_anchors = rank_test_anchors(
        repo_map,
        objective=envelope.objective,
        acceptance_criteria=envelope.acceptance_criteria,
        test_paths=test_paths,
        repo_root=worktree,
        # P3 compiled spans already carry the relevant source body. Keep test
        # anchors as cheap pointers instead of injecting a duplicate excerpt.
        with_excerpt=not bool(compiled_spans),
    )
    return build_execution_context(
        repo_map,
        primary=primary,
        context_refs=envelope.packet.get("context_refs", ()),
        test_anchors=test_anchors,
        compiled_spans=compiled_spans,
        repo_root=worktree,
        # If P3 found useful task spans, do not repeat the generic first-symbol
        # excerpt. A compiler miss falls back to the exact P2 behavior.
        include_excerpts=not bool(compiled_spans),
    )


def _reviewer_execution_context(
    repo_map: "RepoMap | None", *, envelope: AuthorityEnvelope, changed_paths: Sequence[str]
) -> ExecutionContextBundle:
    """The reviewer's bundle: the diff's own changed paths, not the objective's
    text and not the full authorized scope - see section 5 of the milestone
    brief. No excerpts: a reviewer reads the diff itself for the bytes that
    changed, and an excerpt of the pre-existing surrounding code would be the
    developer's discovery aid repeated for a session that is judging, not
    discovering.
    """
    primary = tuple((path, "changed by this attempt") for path in changed_paths)
    return build_execution_context(
        repo_map,
        primary=primary,
        context_refs=envelope.packet.get("context_refs", ()),
        include_excerpts=False,
        # Smaller than the developer's own neighborhood, per section 5 of the
        # milestone brief: the diff already shows what changed, so the
        # reviewer mainly needs blast radius (dependents) and coverage
        # (tests), not every symbol in the file repeated as a list.
        symbol_limit=6,
        dependent_limit=5,
        test_limit=3,
    )


def developer_instructions(
    envelope: AuthorityEnvelope,
    *,
    report_path: Path,
    worktree: Path,
    attempt: int,
    prior_findings: Sequence[str] = (),
    strategy: "ResourceStrategy | None" = None,
    repo_map: "RepoMap | None" = None,
    context_bundle: "ExecutionContextBundle | None" = None,
) -> str:
    lines: list[str] = []
    add = lines.append

    add("# Authorized engineering work order")
    add("")
    add(
        f"You are the session Company OS issued packet {envelope.packet_fingerprint} to, "
        f"acting as the employee {envelope.employee}. This is attempt {attempt} of "
        f"{envelope.max_developer_attempts} the work order authorizes."
    )
    add("")
    add(f"Work order: {envelope.work_order_id} ({envelope.work_order_fingerprint})")
    add(f"Objective:  {envelope.objective}")
    add(f"Branch:     {envelope.authorized_branch}")
    add(f"Base commit:{envelope.base_commit}")
    add(f"Worktree:   {worktree}")
    add("")
    add("## You may change exactly these paths")
    for path in envelope.may_write:
        add(f"  - {path}")
    add("")
    add("## You may not touch these, for any reason")
    for path in envelope.may_not_modify:
        add(f"  - {path}")
    add("")
    add(
        "Every path you change is checked against those two lists after you finish, "
        "by reading git rather than by reading what you say. A change outside the "
        "first list, or inside the second, makes the whole attempt BLOCKED and it is "
        "escalated to the CEO rather than retried."
    )
    add("")

    if envelope.acceptance_criteria:
        add("## Acceptance criteria - all of them, each answerable with a reference")
        for item in envelope.acceptance_criteria:
            add(f"  - {item}")
        add("")
    if envelope.constraints:
        add("## Constraints")
        for item in envelope.constraints:
            add(f"  - {item}")
        add("")
    lines.extend(_MINIMALISM_LINES)
    bundle = context_bundle or developer_execution_context(
        repo_map, envelope=envelope, worktree=worktree
    )
    lines.append(bundle.render())
    if envelope.required_tests:
        add("## Tests the work order requires")
        for item in envelope.required_tests:
            add(f"  - {item}")
        add("")
        add(
            "Do not run these tests inside this model session. The runner owns "
            "deterministic validation and runs every required test afterwards at "
            "the committed implementation SHA. Treat these commands as acceptance "
            "evidence you must design for, not as work for the model to execute."
        )
        add("")

    add("## Stop and say so instead of doing any of these")
    for item in envelope.escalate_instead_of:
        add(f"  - {item}")
    add("")
    add("## How this session ends")
    add("")
    add(
        "Do NOT run `git commit`, `git push`, `git merge`, `git tag` or `git rebase`. "
        "The runner commits what you leave in the working tree, after it has checked "
        "it against the lists above. Leave the work in the tree."
    )
    add("Do NOT start nested agents or subagents. Constitution rule 2 forbids them.")
    add("Do NOT read, print or use any credential, token or environment secret.")
    add("Work only inside the worktree above.")
    add("")
    add(f"Write your report to: {report_path}")
    add("")
    add("It must be one JSON object with exactly these keys:")
    for name, description in DEVELOPER_REPORT_FIELDS:
        add(f"  {name}: {description}")
    add("")
    add(
        "That report is the only thing you return. Everything else in the receipt - "
        "the commit, the changed files, the test results - is measured from the "
        "repository, not taken from you."
    )

    if prior_findings:
        add("")
        add("## A previous attempt was reviewed and sent back. The findings were:")
        for item in prior_findings:
            add(f"  - {item}")
        add("")
        add(
            "Address them inside the same authorized paths. The work order has not "
            "changed and cannot be widened."
        )

    lines.extend(_ceiling_lines(strategy, role="developer"))

    return "\n".join(lines) + "\n"


def review_instructions(
    envelope: AuthorityEnvelope,
    *,
    diff_path: Path,
    worktree: Path,
    receipt: Mapping[str, Any],
    developer_report: Mapping[str, Any],
    strategy: "ResourceStrategy | None" = None,
    repo_map: "RepoMap | None" = None,
) -> str:
    lines: list[str] = []
    add = lines.append

    add("# Independent review of an authorized engineering attempt")
    add("")
    add(
        f"You are the reviewer {envelope.employee}. The work was implemented by "
        f"{envelope.implementer}, in a different session, and you have none of its "
        "conversation. Your packet grants no writable path: read, and report."
    )
    add("")
    add(f"Work order: {envelope.work_order_id} ({envelope.work_order_fingerprint})")
    add(f"Objective:  {envelope.objective}")
    add(f"Worktree:   {worktree}  (read-only to you)")
    add(f"Diff:       {diff_path}")
    add("")
    add("## What the work order authorized")
    add("  may change:")
    for path in envelope.authorized_paths:
        add(f"    - {path}")
    add("  must not change:")
    for path in envelope.may_not_modify:
        add(f"    - {path}")
    add("")
    add("## Acceptance criteria - answer every one")
    for item in envelope.acceptance_criteria:
        add(f"  - {item}")
    add("")
    changed_paths = tuple(str(p) for p in receipt.get("files_changed", ()) or ())
    lines.append(
        _reviewer_execution_context(
            repo_map, envelope=envelope, changed_paths=changed_paths
        ).render()
    )
    if envelope.review_instructions:
        add("## What a review is, per the work order")
        for item in envelope.review_instructions:
            add(f"  - {item}")
        add("")
    add("## What the implementer reported")
    add("")
    add("```json")
    add(json.dumps(_readable(dict(developer_report)), indent=2, sort_keys=True))
    add("```")
    add("")
    add("## The receipt the runner measured and Company OS validated")
    add("")
    add("```json")
    add(json.dumps(_readable(_receipt_digest(receipt)), indent=2, sort_keys=True))
    add("```")
    add("")
    add("## How this session ends")
    add("")
    add(
        "Your final message must be exactly one JSON object and nothing else - no "
        "prose before it, no code fence, no commentary after it."
    )
    add("")
    add("Keys:")
    for name, description in REVIEW_REPORT_FIELDS:
        add(f"  {name}: {description}")
    add("")
    add(
        "A satisfied criterion must name what satisfies it. A verdict of `pass` with "
        "an unanswered criterion is refused by Company OS, not by me."
    )
    add(
        "Every `evidence_ref` is a POINTER: one line, at most 200 characters. Put the "
        "reasoning in `notes` or in a finding's `summary`, and put a place to look in "
        "`evidence_ref`. A reference longer than that is refused as content."
    )
    add(
        "You cannot approve anything: `pass` means the work is ready to be read by "
        "the CEO, and approval is the CEO's and only the CEO's."
    )
    add("Do not start nested agents. Do not edit, write or run anything.")
    lines.extend(_ceiling_lines(strategy, role="reviewer"))
    return "\n".join(lines) + "\n"


def repair_instructions(previous: str, problem: str) -> str:
    """One bounded nudge when a returned report cannot be read.

    This adds no authority and changes no term: it repeats the same request and
    names the decoding error. If the second attempt is also unreadable the
    stage fails and is recorded as failed, rather than being retried until
    something parses.
    """
    return (
        f"{previous}\n\n"
        "## The previous answer could not be read\n\n"
        f"{problem}\n\n"
        "Answer again, in exactly the format above, and change nothing else."
    )


def _receipt_digest(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """The receipt without the fields a reviewer would only be repeating back."""
    keep = (
        "outcome",
        "branch",
        "base_commit",
        "commit_sha",
        "files_changed",
        "tests",
        "dependencies_added",
        "invariants_preserved",
        "unresolved_risks",
        "evidence",
        "working_tree_clean",
        "merge_performed",
        "summary",
    )
    return {name: receipt[name] for name in keep if name in receipt}


def _readable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _readable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_readable(item) for item in value]
    return value


__all__ = [
    "DEVELOPER_REPORT_FIELDS",
    "DEVELOPER_REPORT_NAME",
    "REVIEW_DIFF_NAME",
    "REVIEW_REPORT_FIELDS",
    "developer_execution_context",
    "developer_instructions",
    "repair_instructions",
    "review_instructions",
]
