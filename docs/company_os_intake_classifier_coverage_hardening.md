# Intake classifier hardening, part 2: specialist-vocabulary coverage

**Status: deterministic control-plane fix, verified by deterministic tests and real CLI
dry-run intake. No developer/reviewer session was spawned — same reasoning as part 1
([`company-os-v1-intake-classifier-negation-fix`](../../wt-intake-classifier-negation-fix/docs/company_os_intake_classifier_hardening.md)):
the classifier cannot credibly grade its own work order.**

## 1. Phase 1 — missing-vocabulary root cause

**Current `SPECIALIST_TRIGGERS` (before this pass), by domain:**

- `security` (9): authentication, authorisation, authorization, cryptograph, encrypt,
  sandbox escape, privilege, vulnerabilit, exploit
- `governance` (8): governance policy, governance rules, governance model, permissions
  policy, protected policy, constitution, approval boundary, separation of duties
- `architecture` (10): rewrite, re-architect, rearchitect, redesign, migrate, migration,
  new subsystem, breaking change, schema change, protocol change
- `concurrency` (6): concurren, race condition, deadlock, locking, atomicit, thread saf

**`NOVEL_TRIGGERS`** (6): from scratch, greenfield, no precedent, first of its kind,
prototype a new, invent.

**Reserved-action detection is a separate mechanism**, `screen_reserved()` +
`RESERVED_TRIGGERS` (keyed by the exact `ceo_reserved` action names in
`company/permissions.yaml`), plus `screen_credentials()` + `CREDENTIAL_TRIGGERS`. Both
run before capsule/path derivation and, on a hit, stop intake outright with
`DECISION_REQUIRED` rather than merely raising the model tier.

**Missing verbs/nouns, and where each one belongs under existing policy:**

| Concept | Belongs to | Why |
|---|---|---|
| "architecture change" / "change the architecture" / "system architecture change" / "change system architecture" | existing `architecture` specialist domain (vocabulary added) | Same kind of work as `redesign`/`rewrite`, just phrased with the noun instead of a verb the table already had. A **bare** `"architecture"` was deliberately rejected — see §1a. |
| "approval policy" / "authority policy" | existing `governance` specialist domain (vocabulary added) | Direct siblings of the existing `"permissions policy"`/`"protected policy"` pattern. |
| "synchroniz" (stem) | existing `concurrency` specialist domain (vocabulary added) | Same stemming convention as `"concurren"`/`"atomicit"`. |
| "deploy" / "deployment" | **neither**, under current policy — not added | See §1b. |
| large-scale `"rewrite the architecture"` | **already** a CEO-`reserved_action` (`merge_major_architecture_rewrite`), independent of specialist_domain | Discovered, not changed: an objective containing "rewrite the architecture" reaches both the architecture specialist trigger (`"rewrite"`) **and** `screen_reserved`'s `merge_major_architecture_rewrite` trigger — the two mechanisms are already layered correctly for genuinely large architecture work. |

No new specialist domain was created; every addition is a term inside an already-existing
domain's tuple, per the CEO's explicit allowance ("adding vocabulary to an already-existing
domain is required").

### 1a. Why no bare "architecture" term

A single generic noun was already tried once and rejected: the V3A fix narrowed a bare
`"governance"` trigger to specific action phrases after it matched a page that merely
*displayed* governance activity. Adding bare `"architecture"` would reproduce exactly that
failure — it appears in `"architecture.md documentation cleanup"`,
`"document the system architecture"`, and any diagram/reference sentence. The four phrases
added instead (`"architecture change"`, `"change the architecture"`,
`"system architecture change"`, `"change system architecture"`) are the natural word orders
of an actual change *request*, and none of them occurs in a documentation-reference
sentence (verified in §6).

### 1b. Why "deploy"/"deployment" was not added anywhere

Checked against both tables. `RESERVED_TRIGGERS["publish_public_video"]` is
`("publish", "upload", "go live", "release the video")` — scoped to *public video content*
by its own name, and by the separate, gate-time `mandatory_review_triggers:
production_publish_request: release_and_ceo_gate` entry in `permissions.yaml` (consumed at
the integration gate, not at intake — confirmed by grep across `company/integration/`).
Nothing in this repository's declared policy names a general "deploy a software service"
concept. Two honest options existed: invent one (a specialist domain or a reserved action),
which the CEO's brief explicitly places out of scope ("do not invent a new specialist
domain"; policy semantics are for the CEO to set, not for a vocabulary-coverage pass to
infer); or fold "deploy" into `publish_public_video` anyway, which would conflate two
different concepts (shipping a video vs. shipping software) rather than close a genuine gap
in one. Neither is the "smallest deterministic correction" the brief asked for, so nothing
was added. This is pinned by
`test_deployment_wording_has_no_existing_policy_hook` (both `derive_routing` and
`screen_reserved` checked) so the gap is visible and testable, not silently absent.

## 2. Phase 2 — negation-scope audit: PASS, no change

Every required example from the brief was tested directly against the existing
clause/negation logic from the prior pass (`_clauses`/`_escalates` in
`company/engineering/intake.py`), **before writing any new code**:

| Objective | Result |
|---|---|
| "Do not change tests; redesign the architecture." | escalates (`architecture`, via `redesign` in the second clause) |
| "No documentation changes; perform the schema migration." | escalates (`architecture`, via `migration`) |
| "Do not modify the UI, deploy the service." | stays routine — correct, since "deploy" has no trigger anywhere (§1b), not a clause-splitting defect |
| "Avoid changing authentication tests; redesign authentication." | escalates (`security`, via `authentication` in the second clause) |
| "No deployment documentation changes; migrate persistence." | escalates (`architecture`, via `migrate`) |
| "Do not redesign the API, but migrate the database schema." | escalates (`architecture`, via `migrate`; `but` is an existing clause boundary) |
| "No deployment is required; redesign authentication." | escalates (`security`, via `authentication`) |
| "Avoid architecture changes except migrate persistence." | escalates (`architecture`, via `migrate`; `except` is an existing clause boundary) |

All eight already pass with **zero code changes** — the semicolon/`but`/`except`/period
boundaries already in `_CLAUSE_BREAK` are sufficient for every case the brief requires.

**One deliberate, disclosed limit, checked and kept:** clause splitting does **not**
include a bare comma. Tested: `"Do not, under any circumstances, redesign the schema."` —
if a comma were a clause boundary, this would split into `"do not"` / `"under any
circumstances"` / `"redesign the schema"`, and the negation on `"do not"` would no longer
be in the same fragment as `"redesign"`, incorrectly escalating a plainly negated
instruction. Confirmed empirically: with the **current** (comma-safe) implementation this
objective correctly stays routine. Adding comma-splitting would fix nothing the brief
requires (no required case depends on a comma-only boundary once the vocabulary gap in
§1b is accounted for) while introducing this exact new false positive — so it was
considered and rejected, not overlooked.

**Phase 2 verdict: PASS.** No change was made to `_clauses`, `_escalates`,
`_CLAUSE_BREAK`, or `_NEGATION_WORDS`.

## 3. Phase 3/4 — coverage matrix and the fix

`company/engineering/intake.py` changes (+19 lines): the three vocabulary additions from
§1, inside the existing `SPECIALIST_TRIGGERS["architecture"|"governance"|"concurrency"]`
tuples. `tests/test_company_engineering_execution.py` changes (+181 lines, section 13c):

- **16 positive-coverage tests** (parametrized): one representative objective per concept
  across all four specialist domains plus migration — asserts `specialist_domain != ""`.
- **1 deployment-gap pin**: both `derive_routing` and `screen_reserved` checked, asserts
  the gap stays open and visible.
- **9 negated-coverage tests**: the new vocabulary run through the same negation check as
  the old vocabulary — proves there is no separate, re-breakable code path.
- **7 mixed-clause tests**: reproduces every Phase 2 example as a permanent regression,
  plus two using the new vocabulary.
- **3 benign-reference tests**: `"architecture.md documentation cleanup"`,
  `"Update the deployment test assertions."`, `"Document the system architecture in the
  README."` — all correctly stay routine.
- **2 pre-existing-limitation pins** (§4 below).
- **1 replay** of the original correction-job false-positive text, to prove the new
  vocabulary did not reopen it.

**Result:** `pytest tests/test_company_engineering_execution.py -q` → **197 passed**
(158 from the negation-fix pass + 39 new).

## 4. Phase 6 — adversarial reference-vs-action tests: two real findings disclosed, not fixed

Per the brief's own instruction — *"If this cannot be achieved without a broader
classifier redesign, STOP and report the limitation rather than hiding it"* — two
adversarial cases were tested and **do** over-escalate, and are pinned as known current
behaviour rather than forced to pass or silently patched:

| Objective | Result | Why |
|---|---|---|
| "Improve migration test coverage for this suite." | escalates (`architecture`, via `migration`) | `"migration"` is a **pre-existing** single-word trigger (present before either hardening pass). Bare-substring matching cannot tell a test-authoring mention from the action. |
| "Rename the authentication fixture used by these tests." | escalates (`security`, via `authentication`) | Same shape, `"authentication"` is pre-existing. |

This is the identical class of problem the V3A fix solved for a bare `"governance"`
mention — except here the offending terms (`"authentication"`, `"migration"`) are already
load-bearing, in-production single-word triggers, not something either hardening pass
introduced. Narrowing or removing them the way `"governance"` was narrowed is a
materially bigger, riskier change than adding a bounded new phrase: it risks
**under**-escalating real authentication/migration work that does not happen to use
whatever narrower replacement phrase would be chosen, trading a known false-positive for
an unmeasured false-negative. That is not "the smallest deterministic correction" this
pass was chartered to make, so nothing was changed. Both cases are pinned by
`test_pre_existing_bare_word_triggers_cannot_distinguish_a_reference` so a future change
to this behaviour is a deliberate decision, not a silent regression either way.

**Three other adversarial cases correctly stay routine**, confirming the new §1 vocabulary
did not reintroduce the bare-noun problem it was designed to avoid:
`"architecture.md documentation cleanup"`, `"Update the deployment test assertions."`,
`"Document the system architecture in the README."`.

## 5. A related, disclosed, un-fixed finding: reserved-action screening shares the old bug

Testing "the FULL intake result, not merely specialist_domain" (per the brief) surfaced
that `screen_reserved()` and `screen_credentials()` — the CEO-reserved-action and
credential-material gates, checked before specialist routing and capable of stopping
intake outright with `DECISION_REQUIRED` — use the exact same negation-blind
`term in text` pattern the prior pass fixed in `derive_routing`. Reproduced for real:

```
'Do not merge this branch into main.'      -> reserved: ['merge_major_architecture_rewrite']
'Please do not delete anything in this pass.' -> reserved: ['delete_important_production_or_company_data']
'Do not touch any password in this change.'   -> credential: True
```

**This fails safe, not open**: every case above *blocks* a routine job with a spurious
`DECISION_REQUIRED` rather than silently permitting a reserved action or a credential
touch. It is real, disclosed, and **not fixed in this pass** — the brief's Phase 4 scope
was the specialist-vocabulary coverage gap, and reusing `_clauses`/`_escalates` inside
`screen_reserved`/`screen_credentials` would be a second, distinct code change beyond what
was authorized here (it does not touch "reserved-action policy semantics" — no action name
or trigger phrase changes meaning — but it is still a change this specific brief did not
ask for). Recorded for a future, separately-scoped pass; not chased further here, per the
CEO's own standing instruction against unbounded hardening loops.

## 6. Historical before/after (real CLI dry-run intake, both classes)

**False-positive class (unchanged from part 1, replayed to confirm no reopening):** the
exact correction-job objective text stays `specialist_domain: ""` on this branch.

**False-negative class (new in this pass):**

| Objective | Before (`da4f3ce`, negation-fix only) | After (`12f7cf8`, this branch) |
|---|---|---|
| "An architecture change is required for this feature." | `""` | `"architecture"` (`architecture change`) |
| "We must change system architecture to support this." | `""` | `"architecture"` (`change system architecture`) |
| "Modify the approval policy for reserved actions." | `""` | `"governance"` (`approval policy`) |
| "Alter the authority policy for developer sessions." | `""` | `"governance"` (`authority policy`) |
| "Change the synchronization strategy for these workers." | `""` | `"concurrency"` (`synchroniz`) |

## 7. Broader regression

| | passed | failed | skipped |
|---|---:|---:|---:|
| Negation-fix baseline (`da4f3ce`) | 4662 | 6 | 337 |
| Coverage-fix (`12f7cf8`) | 4701 | 6 | 337 |

Same 6 failures, confirmed identical by name: `test_a_missing_godot_is_reported_rather_
than_raised`, `test_the_siting_tool_uses_the_scenes_own_edit_map`,
`test_the_projector_puts_each_node_in_the_frame_named_for_it`,
`test_every_authored_site_lands_in_at_least_one_frame`,
`test_the_analytic_parallax_finds_a_spread_in_every_chase`,
`test_the_geometric_parallax_field_is_identical_to_v251s` — the same pre-existing
gitignored-artifact failures documented in part 1. The +39 passed is exactly the new test
count. **Zero new regressions.**

## 8. Evidence

- This file: `docs/company_os_intake_classifier_coverage_hardening.md`
- Fix commit: `12f7cf8` on `company-os-v1-intake-classifier-coverage-fix` (base `da4f3ce`,
  pushed, local = remote, **not merged anywhere**)
- Files changed: `company/engineering/intake.py` (+19), `tests/test_company_engineering_
  execution.py` (+181/-0 net; some lines in the existing historical-regression test were
  reorganized, not removed)
- Targeted suite: 197 passed. Full suite: 4701 passed / 6 failed / 337 skipped vs.
  4662/6/337 baseline — same 6 failures by name.
- Real CLI dry-run intake, before/after, for both the false-positive class (replayed) and
  the false-negative class (new) — §6.
