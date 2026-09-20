"""Whether a work order says something a reviewer could falsify.

The first live-delegation pilot stopped because this check did not exist.
A CEO *objective* - "improve the reliability or maintainability of the
engineering system by completing one genuinely useful improvement" - was
submitted to intake and came back `authorized`, correctly scoped to a capsule
and a risk class, carrying the objective verbatim as its own and the derived
criterion *"The stated objective is implemented: <the objective>"*. No reviewer
and no deterministic QA can decide whether that was met, and the derived plan
told the developer to work out what the work was. Planning had been pushed onto
the worker. `docs/company_os_first_live_delegation_pilot.md` is the evidence.

## What this module decides, and what it refuses to decide

It decides one structural question: **does this objective name something, or
does it only name a direction?** That is not a judgement about whether the work
is worth doing, whether the objective is wise, or whether the sentence is true.
Those need a reader. This needs a vocabulary and a tokenizer.

So there is no natural-language understanding here and there should never be.
There are three closed word lists and one phrase list, and the whole check is:
after removing the words that carry no subject, is any subject left?

## Why a closed vocabulary rather than a cleverer test

Every alternative that looked more general was worse. Requiring a file path
refuses "add a field to the engineering result record", which is a perfectly
executable work order the company has been accepting for months. Requiring a
symbol refuses everything written in prose. Scoring the sentence invents a
number nobody can reproduce.

The vocabulary below is **this company's current opinion**, in the same sense
that `org_intelligence.ManagementPolicy`'s span of control is an opinion: it is
data, it is visible, and the tests pin both directions of it. Section 1 of
`tests/test_company_objective_planning.py` asserts that every objective the
existing suites already submit stays accepted, and that each refusal example
from the pilot report stays refused. A change to these lists that breaks
either direction fails there, which is the point of writing them down.

## The three ways an objective earns its way through

An objective does not have to be specific by itself. It has to be specific
*by the time it becomes a work order*, and management has two other ways to
make it so:

1. **It names a subject.** A content word survives the vocabulary below.
2. **It carries explicit acceptance criteria.** A CEO or a manager who writes
   a falsifiable criterion has done the specifying, whatever the title says.
3. **It is tied to a selected candidate.** The candidate register already
   validated the criteria, and the planning decision recorded who chose it and
   why. This is the path `company/delegation/planning.py` builds.

Any one of the three is enough. None of them and the answer is
`PLANNING_REQUIRED`: somebody has to decide what the work is, and that somebody
is not the developer.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import re
from typing import Any

from .errors import EngineeringError

# Words that carry no subject: articles, prepositions, auxiliaries, and the
# polite scaffolding a request sentence is wrapped in.
STOPWORDS: frozenset[str] = frozenset(
    """
    a an the this that these those it its is are be been being was were am
    to of in on at for from by with without within into onto over under
    and or but so nor if then than as such via per
    i me my we our you your they them their he she his her
    give please let make made making do does did doing done
    whether since once when where while after before during until
    any all some each every both either neither no not none
    have has had having can could may might must shall should will would
    there here what which who whom whose how why
    more most less least very much many few several other another same
    up down out off again further also just only even still yet
    """.split()
)

# Verbs that describe *acting* without naming what is acted on. "improve the
# flavour text" keeps `flavour` and `text`; "improve reliability" keeps nothing.
GENERIC_VERBS: frozenset[str] = frozenset(
    """
    improve improving improvement improvements
    fix fixing fixed repair repairing
    implement implements implemented implementing implementation
    complete completes completed completing completion
    address addressing addressed handle handles handled handling
    enhance enhancing enhanced better best betterment
    optimise optimize optimising optimizing optimised optimized
    optimisation optimization
    ensure ensuring ensured maintain maintaining maintained
    identify identifying identified determine determining determined
    assess assessing assessed
    """.split()
)

# Nouns and adjectives that name a direction or a quality rather than a thing.
# A sentence built only from these is a goal, not a task.
ABSTRACT_TERMS: frozenset[str] = frozenset(
    """
    objective objectives goal goals aim aims purpose intent intention
    reliability maintainability usability durability stability scalability
    quality robustness correctness performance efficiency effectiveness
    system systems platform infrastructure
    company organisation organization business
    engineering software codebase repository repo
    work works task tasks job jobs item items piece pieces
    thing things stuff something anything everything nothing
    situation posture health
    value values benefit benefits outcome outcomes
    stated said given above below following
    useful usefully genuine genuinely real really actual actually
    existing already
    low medium high critical minor major
    risk risky
    one two three several
    general generally overall broadly specific specifically
    appropriate appropriately suitable suitably necessary
    missing needed required wanted
    """.split()
)

# Phrases that hand the choice of work to whoever reads the sentence next.
# These refuse regardless of what else the objective contains, because an
# objective that says "work out what to do" has not been planned at all.
DEFERRAL_PHRASES: tuple[str, ...] = (
    "identify the specific work",
    "identify and implement",
    "identify what",
    "decide what",
    "choose what",
    "work out what",
    "figure out what",
    "whatever is missing",
    "whatever is needed",
    "whatever is required",
    "whatever you think",
    "as you see fit",
    "as appropriate",
    "something useful",
    "genuinely useful",
    "already-existing",
    "already existing",
    "the smallest contract that the objective is missing",
    "must identify",
)

_TOKEN = re.compile(r"[a-z][a-z0-9_.\-/]*")
# A concrete anchor: a path, a dotted or underscored identifier, or a test name.
_ANCHOR = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:[./][A-Za-z0-9_]+)+|[a-z]+_[a-z_]+")

MIN_CRITERION_CHARS = 24
"""Below this a criterion is a label, not a criterion. Deliberately short."""


class PlanningRequired(EngineeringError):
    """Raised where a caller asked for a work order and planning has not happened."""


@dataclass(frozen=True)
class SpecificityVerdict:
    """Why an objective is, or is not, executable as written."""

    specific: bool
    subjects: tuple[str, ...]
    anchors: tuple[str, ...]
    deferrals: tuple[str, ...]
    satisfied_by: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "specific": self.specific,
            "subjects": list(self.subjects),
            "anchors": list(self.anchors),
            "deferrals": list(self.deferrals),
            "satisfied_by": self.satisfied_by,
            "reason": self.reason,
        }


def subjects_in(text: str) -> tuple[str, ...]:
    """The content words left once direction, action and scaffolding are gone."""
    if not isinstance(text, str):
        raise EngineeringError("subjects_in takes text")
    out: list[str] = []
    for token in _TOKEN.findall(text.lower()):
        word = token.strip(".-/")
        if not word or len(word) < 3:
            continue
        if word in STOPWORDS or word in GENERIC_VERBS or word in ABSTRACT_TERMS:
            continue
        if word not in out:
            out.append(word)
    return tuple(out)


def anchors_in(text: str) -> tuple[str, ...]:
    """Paths, dotted names and snake_case symbols, which are never ambiguous."""
    if not isinstance(text, str):
        raise EngineeringError("anchors_in takes text")
    seen: list[str] = []
    for match in _ANCHOR.findall(text):
        if match not in seen:
            seen.append(match)
    return tuple(seen)


def deferrals_in(text: str) -> tuple[str, ...]:
    """Every phrase that defers the choice of work to a later reader."""
    if not isinstance(text, str):
        raise EngineeringError("deferrals_in takes text")
    lowered = " ".join(text.lower().split())
    return tuple(phrase for phrase in DEFERRAL_PHRASES if phrase in lowered)


def is_falsifiable_criterion(criterion: Any) -> bool:
    """One criterion a reviewer could mark pass or fail.

    Structural, not semantic: long enough to be a sentence, and naming either a
    subject or an anchor. A criterion that restates a direction names neither.
    """
    if not isinstance(criterion, str):
        return False
    text = criterion.strip()
    if len(text) < MIN_CRITERION_CHARS:
        return False
    if deferrals_in(text):
        return False
    return bool(subjects_in(text)) or bool(anchors_in(text))


def assess_specificity(
    objective: str,
    *,
    acceptance_criteria: Sequence[str] = (),
    candidate_id: str = "",
) -> SpecificityVerdict:
    """Whether this objective can become a work order without further planning.

    Three independent ways through, checked in the order that makes the
    recorded reason most useful: a selected candidate is the strongest claim,
    explicit criteria the next, and the objective's own words the last.
    """
    if not isinstance(objective, str) or not objective.strip():
        raise EngineeringError("assess_specificity takes a non-empty objective")
    deferrals = deferrals_in(objective)
    subjects = subjects_in(objective)
    anchors = anchors_in(objective)
    criteria = tuple(
        item for item in (acceptance_criteria or ()) if is_falsifiable_criterion(item)
    )

    if isinstance(candidate_id, str) and candidate_id.strip():
        return SpecificityVerdict(
            specific=True,
            subjects=subjects,
            anchors=anchors,
            deferrals=deferrals,
            satisfied_by="candidate",
            reason=(
                f"the work order is derived from selected candidate "
                f"{candidate_id.strip()}, whose acceptance criteria were validated "
                "when the candidate was registered and whose selection is recorded "
                "in a planning decision"
            ),
        )
    if criteria:
        return SpecificityVerdict(
            specific=True,
            subjects=subjects,
            anchors=anchors,
            deferrals=deferrals,
            satisfied_by="acceptance_criteria",
            reason=(
                f"{len(criteria)} supplied acceptance criterion/criteria name a "
                "checkable outcome, so the specifying has been done whatever the "
                "objective's own wording"
            ),
        )
    if deferrals:
        return SpecificityVerdict(
            specific=False,
            subjects=subjects,
            anchors=anchors,
            deferrals=deferrals,
            satisfied_by="",
            reason=(
                "the objective defers the choice of work to whoever reads it next "
                f"({', '.join(repr(item) for item in deferrals)}). Choosing which "
                "work advances an objective is a management decision; it is not "
                "the developer's to make because the sentence was broad"
            ),
        )
    if subjects or anchors:
        named = ", ".join(anchors[:3] or subjects[:3])
        return SpecificityVerdict(
            specific=True,
            subjects=subjects,
            anchors=anchors,
            deferrals=deferrals,
            satisfied_by="objective",
            reason=f"the objective names a subject a reviewer can check: {named}",
        )
    return SpecificityVerdict(
        specific=False,
        subjects=(),
        anchors=(),
        deferrals=deferrals,
        satisfied_by="",
        reason=(
            "the objective names a direction but no subject: every word in it is "
            "scaffolding, a generic verb, or a quality. A reviewer asked whether "
            "this was achieved would have nothing to check, so it is a goal to be "
            "planned rather than work to be done"
        ),
    )


__all__ = [
    "ABSTRACT_TERMS",
    "DEFERRAL_PHRASES",
    "GENERIC_VERBS",
    "MIN_CRITERION_CHARS",
    "STOPWORDS",
    "PlanningRequired",
    "SpecificityVerdict",
    "anchors_in",
    "assess_specificity",
    "deferrals_in",
    "is_falsifiable_criterion",
    "subjects_in",
]
