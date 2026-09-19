# Intake classifier hardening: negation-blind specialist escalation

**Status: deterministic control-plane fix, verified by deterministic tests and real CLI
dry-run intake. No developer/reviewer session was spawned for this pass — this is a
direct fix to the classifier itself, not a Company OS work order run through
`tools/engineering_runner`, because the classifier is the thing being fixed and cannot
credibly grade its own work order.**

## 1. The defect

`company/engineering/intake.py`'s `derive_routing()` decides `specialist_domain` (which
model tier a job runs at) by checking whether any `SPECIALIST_TRIGGERS` term, or any
`NOVEL_TRIGGERS` term, occurs **anywhere as a plain substring** in the lowercased
objective — `term in text`. There was no clause boundary, no word boundary beyond what
each multi-word phrase already implied, and no concept of negation. An objective that
**prohibits** specialist work escalated exactly as if it had requested it:

- "do not redesign the schema" → matches `"redesign"` (architecture)
- "no migration machinery" → matches `"migration"` (architecture)

This was not hypothetical: it happened for real while drafting the work order that fixed
`EngineeringResult`'s null-crash
([[company-os-supervised-burnin-job-a-correction-stop-condition]]). The objective's first
draft ended "...it must not redesign the field's representation or introduce any migration
machinery," and intake returned `specialist_domain: "architecture"`, which would have run
the job at a tier above the CEO's explicit "one STANDARD developer" policy had it not been
caught by a dry-run first.

## 2. Reproduction (real CLI, deterministic, no model call)

Dry-run intake against a scratch state directory, using the exact historical objective
text, on the unfixed classifier at `c78e444` (the current burn-in tip before this fix):

```
outcome: authorized
specialist_domain: 'architecture'
specialist_reason: the objective names 'redesign', which is architecture work
```

## 3. Root cause

`derive_routing()`, `company/engineering/intake.py`:

```python
text = request.objective.lower()
novel = request.novel or any(term in text for term in NOVEL_TRIGGERS)
...
for name, terms in SPECIALIST_TRIGGERS.items():
    hit = next((term for term in terms if term in text), "")
```

Both loops test `term in text` against the **entire objective as one string**. Answers to
the CEO's specific root-cause questions:

- **Where matched:** `derive_routing()`, the sole classification function; nowhere else.
- **How detected:** plain Python substring containment (`in`), not token-, regex-, or
  phrase-boundary matching beyond the trigger strings' own literal spelling.
- **Negation/context considered:** none. No clause splitting, no word-boundary check on
  the *trigger* term itself (multi-word phrases like `"sandbox escape"` are fine because
  they're already specific), and — the actual bug — no check for a negation word anywhere
  near the match.
- **Domains affected:** **all four** `SPECIALIST_TRIGGERS` categories (`security`,
  `governance`, `architecture`, `concurrency`) share the identical `term in text` check, so
  the same false-positive shape applies to e.g. "do not modify authentication" (security)
  or "avoid a race condition here" (concurrency) exactly as it did to "redesign"/
  "migration" (architecture). `NOVEL_TRIGGERS` (a separate list feeding `novel`, not
  `specialist_domain`) uses the identical pattern and has the identical defect — e.g. "we
  do not need to invent a new format" would have set `novel=True`.
- **General or architecture-only:** general. This is a single substring-matching defect in
  one shared code shape, applied twice (once per trigger table), not an architecture- or
  domain-specific bug.

## 4. The fix

Smallest deterministic correction: split the objective into clauses, then require a
trigger term to occur in some clause **without a negation word earlier in that same
clause**.

```python
_CLAUSE_BREAK = re.compile(
    r"[.;!?\n]+|\bbut\b|\bhowever\b|\bexcept\b|\balthough\b|\bthough\b|\byet\b"
)
_NEGATION_WORDS = frozenset({"not", "no", "never", "without", "avoid", "cannot"})
_NEGATION_WORD_PATTERN = re.compile(r"[a-z']+")

def _clauses(text: str) -> tuple[str, ...]:
    return tuple(part for part in _CLAUSE_BREAK.split(text) if part.strip())

def _escalates(term: str, clauses: tuple[str, ...]) -> bool:
    for clause in clauses:
        start = 0
        while True:
            index = clause.find(term, start)
            if index == -1:
                break
            words_before = frozenset(_NEGATION_WORD_PATTERN.findall(clause[:index]))
            if not (words_before & _NEGATION_WORDS):
                return True
            start = index + 1
    return False
```

`derive_routing()` now calls `_escalates(term, clauses)` in place of `term in text`, for
both `NOVEL_TRIGGERS` and every `SPECIALIST_TRIGGERS` domain — one shared fix for the
general defect, not four domain-specific patches. Negation words are matched as whole
tokens (via `_NEGATION_WORD_PATTERN`), not substrings, specifically so that words like
"innovative" or "notation" can never be misread as containing "no"/"not". Every occurrence
of a term is checked, not just the first, so a term negated in one clause can still escalate
via a genuine, independent occurrence elsewhere.

**Files changed:** `company/engineering/intake.py` (+44/-2),
`tests/test_company_engineering_execution.py` (+111/-0). Nothing else.

**Explicitly not changed** (per the CEO's scope): the authority model, employee contracts,
work-order lifecycle, `SPECIALIST_TRIGGERS`/`NOVEL_TRIGGERS` vocabulary (no term added or
removed from any domain), resource-mode policy, reviewer or gate behavior. Model-tier
policy changes only as the natural downstream effect of a corrected `specialist_domain`.

## 5. Test matrix (deterministic, `tests/test_company_engineering_execution.py`, section 13b)

18 new focused tests, all against the real `derive_routing()`:

**Negated — must stay routine (7, parametrized):**
"do not redesign the schema", "no schema redesign", "no migration is required", "do not
perform a migration", "do not modify authentication", "never rewrite the queue consumer",
"avoid a breaking change" — all assert `specialist_domain == ""`.

**Positive, same vocabulary — must still escalate (4, parametrized):** "redesign the
schema", "perform a schema migration", "rewrite the queue consumer", "redesign
authentication" — all assert `specialist_domain != ""`.

**Mixed clauses — must still escalate (3, parametrized):** "Do not redesign the API.
Migrate the persistence schema to version 3." / "No deployment is required; redesign
authentication for this service." / "Avoid architecture changes except migrate the
persistence schema." — each has one negated clause and one genuinely positive clause, and
each asserts `specialist_domain != ""`.

**Normal routine wording — unaffected (3):** the file's existing `ROUTINE_OBJECTIVE` plus
two new representative Company OS objectives with no trigger vocabulary at all.

**Historical regression (1):** the exact objective text that produced the real false
positive (§2), now asserted routine.

**Result:** `pytest tests/test_company_engineering_execution.py -q` → **158 passed**
(140 pre-existing + 18 new). The pre-existing
`test_every_specialist_trigger_routes_to_its_own_domain` (every trigger term, unnegated,
still routes to its domain) and `test_a_harmless_governance_mention_stays_routine`
(the earlier V3A bare-word fix) both still pass unmodified — this fix does not regress
either prior classifier correction.

## 6. Historical false-positive: before/after (real CLI dry-run intake)

Same request file, same objective text, two branches:

| | `specialist_domain` | reason |
|---|---|---|
| **Before** (`c78e444`, unfixed) | `"architecture"` | `the objective names 'redesign', which is architecture work` |
| **After** (`80a1ee6`, fixed) | `""` | `the objective names no security, governance, architecture or concurrency work and the risk is not high, so this is routine implementation` |

## 7. Genuine specialist-positive control (real CLI dry-run intake, fixed branch)

Objective: "Redesign the authentication module's schema and migrate existing sessions to
the new format." →

```
outcome: authorized
specialist_domain: 'security'
specialist_reason: the objective names 'authentication', which is security work
```

Confirms escalation still fires on real specialist-shaped wording after the fix (routed to
`security` here because that domain is checked first in `SPECIALIST_TRIGGERS`' declared
order and `"authentication"` matches independently of `"redesign"`/`"migrate"`).

## 8. Broader regression (full repository suite, `pytest tests/ -q`)

| | passed | failed | skipped |
|---|---:|---:|---:|
| Baseline (`c78e444`, unfixed) | 4644 | 6 | 337 |
| Fixed (`80a1ee6`) | 4662 | 6 | 337 |

The 6 failures are byte-identical by name on both branches (confirmed by running the three
containing files directly against the unfixed base): `test_a_missing_godot_is_reported_
rather_than_raised`, `test_the_siting_tool_uses_the_scenes_own_edit_map`,
`test_the_projector_puts_each_node_in_the_frame_named_for_it`,
`test_every_authored_site_lands_in_at_least_one_frame`,
`test_the_analytic_parallax_finds_a_spread_in_every_chase`,
`test_the_geometric_parallax_field_is_identical_to_v251s` — all `FileNotFoundError`/
`SystemExit` on a gitignored `output/` render artifact absent from any fresh checkout, in
files entirely unrelated to `company/engineering` (Godot/marble-race rendering tests). The
+18 passed is exactly the new test count. **Zero new regressions.**

## 9. A second, distinct, previously-unrecorded defect found while building this matrix

Building the CEO's own required "positive/must escalate" cases surfaced a **false-negative**
gap that this pass does **not** fix: `"change system architecture"`, `"deploy the
service"`, and `"security architecture change required"` do not escalate — **not because
of negation**, but because no term in `SPECIALIST_TRIGGERS` matches bare `"architecture"`
or any form of `"deploy"`/`"deployment"` at all, in either the unfixed or the fixed
classifier. This is a vocabulary-coverage gap, not a scoping bug, and closing it means
adding trigger terms — a change to the specialist-domain *vocabulary*, which the CEO's
brief for this pass explicitly placed out of scope ("do not change... specialist
definitions"). It is recorded here, unresolved, and carried into the autonomy-readiness
review as control area 14 (`PARTIAL`, not `PASS`) rather than hidden or silently patched.

## 10. Evidence

- This file: `docs/company_os_intake_classifier_hardening.md`
- Fix commit: `80a1ee6adc65f6b4e65633a98148a5af8fa52a1b` on
  `company-os-v1-intake-classifier-negation-fix` (base `c78e444`, pushed, local = remote,
  **not merged anywhere**)
- Full diff: `company/engineering/intake.py` (+44/-2),
  `tests/test_company_engineering_execution.py` (+111/-0)
- Targeted suite: 158 passed (`tests/test_company_engineering_execution.py`)
- Full suite: 4662 passed / 6 failed / 337 skipped, vs. baseline 4644 passed / 6 failed /
  337 skipped at `c78e444` — same 6 failures by name
- Real CLI dry-run intake transcripts: historical-wording before/after (§6), positive
  control (§7) — reproduced from this session's command history, not estimated
