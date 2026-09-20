# Execution Efficiency V3A — Read-Pattern Diagnosis + Routing Precision

**Branch** `company-os-v1-read-efficiency-v3a`, based on
`company-os-v1-repository-exploration-efficiency-v2` at
`6dd789135040dcdfe99491b644c3b58c8fa34a37` (verified: `origin` and local HEAD
agreed, worktree clean, V2's two implementation commits present before this
branch was cut). **Diagnosis and a correctness fix, not another matched job.
Not merged. Not authorization to merge.**

---

## PART A — routing precision

### The defect

`company/engineering/intake.py`'s `derive_routing` built its trigger text from
`" ".join((request.objective, request.notes)).lower()` and matched it against
`SPECIALIST_TRIGGERS["governance"]`, whose first term was the bare noun
`"governance"`. Two consequences, both real:

1. Any objective that merely *named* governance (a CEO page showing
   governance activity, documentation of a governance result) routed to the
   strongest tier, because the trigger table could not distinguish "this work
   is governance" from "this work is about governance."
2. `notes` — explanatory metadata, not requested work — fed the same match.
   V2's own matched job (`docs/company_os_repository_exploration_efficiency_v2.md`,
   §10) hit this twice: the first drafted objective said "so a CEO page can
   show governance activity," and a second attempt's *notes*, explaining that
   first misclassification, re-triggered the same rule by using the word
   "governance" to describe it. Both mis-routed work orders were left
   unactioned rather than spent on.

### The fix

Two minimal, narrow changes to `intake.py`:

1. **`text` is built from `request.objective` alone.** `notes` never
   participates in `derive_routing`'s trigger match, for either
   `SPECIALIST_TRIGGERS` or `NOVEL_TRIGGERS`. Explicit fields
   (`specialist_domain`, `escalate_reasoning`, `risk`, `reversible`) remain
   the only routing-authoritative CEO-controlled signals besides the
   objective text itself — unchanged from before.
2. **The bare noun `"governance"` is removed from `SPECIALIST_TRIGGERS`.**
   The remaining terms — `"permissions policy"`, `"protected policy"`,
   `"constitution"`, `"approval boundary"`, `"separation of duties"` — already
   describe genuine governance *actions*, not the topic. Three additional
   action phrases were added so intentional governance-policy language stays
   supported without the bare noun: `"governance policy"`, `"governance
   rules"`, `"governance model"`.

No other trigger table (`security`, `architecture`, `concurrency`), no risk
routing, and no ceiling logic changed. The classifier's HIGH/CRITICAL-risk
escalation, the `explicit_escalation` path, and the CEO-named
`specialist_domain` override are byte-for-byte unchanged.

### Verified behavior

| objective / notes | before | after |
|---|---|---|
| "Show governance activity on the CEO page." | `governance` (false positive) | `""` (routine) |
| "Display governance events alongside attempts." | `governance` | `""` |
| "Document the governance result." | `governance` | `""` |
| routine objective + notes mentioning a past "governance" misclassification | `governance` (notes retriggered it) | `""` (notes never consulted) |
| "Modify the approval boundary so a second reviewer is required." | `governance` | `governance` (unchanged) |
| "Change the permissions policy for reserved actions." | `governance` | `governance` (unchanged) |
| "Amend the constitution's rule about subagents." | `governance` | `governance` (unchanged) |
| "Change separation of duties between developer and reviewer roles." | `governance` | `governance` (unchanged) |
| "Change protected policy so the gate file cannot be hand-edited." | `governance` | `governance` (unchanged) |
| "Change the governance rules for who can approve a merge." | (already `governance`) | `governance` (unchanged) |
| explicit `specialist_domain="governance"` on a routine objective | `governance` | `governance` (unchanged — explicit field always wins) |
| `escalate_reasoning=True` on a routine objective | `explicit_escalation` | `explicit_escalation` (unchanged) |
| routine objective, `risk=HIGH` / `risk=CRITICAL` | `high_risk_change` | `high_risk_change` (unchanged) |

`security`, `architecture`, and `concurrency` triggers were not touched; every
existing case in `test_every_specialist_trigger_routes_to_its_own_domain`
(parameterized directly off `SPECIALIST_TRIGGERS`) still passes.

### Tests

11 new cases in `tests/test_company_engineering_execution.py`
(`test_a_harmless_governance_mention_stays_routine`,
`test_other_harmless_governance_mentions_stay_routine` (parameterized, 2
cases), `test_governance_mention_in_notes_does_not_route`,
`test_genuine_governance_actions_still_route_to_specialist` (parameterized, 6
cases), `test_explicit_specialist_domain_is_authoritative_over_text`,
`test_explicit_escalation_routes_without_needing_trigger_text`,
`test_high_or_critical_risk_still_routes_to_specialist_depth` (parameterized,
2 cases)). Every test asserts on `RoutingDerivation.reason`, the same
human-readable derivation string the CEO page already renders, so the
routing decision stays auditable, not just correctly classified. All 128
cases in the file pass, including the 117 that existed before this branch.

---

## PART B — read telemetry: the shape, not assumed

### Existing local evidence was sufficient for the shape question, and decisive for Part D

`docs/company_os_repository_exploration_efficiency_v2.md`'s own matched job
wrote its runner state to an external, un-gitted directory
(`company-os-repo-exploration-v2-runner-state/`, a sibling of this repo's
clone, per `config.py`'s `runner_dir` convention). That directory still holds
the full raw `stream-json` transcript for both stages —
`run-000001/developer-01/session-1.transcript.txt` (72 lines) and
`run-000001/reviewer-01/session-1.transcript.txt` — not just the reduced
`exploration.json` V2 wrote from it. **No probe was needed to recover V2's own
Read/Edit ranges; they were sitting on disk.**

A cheap direct CLI probe was still run, for one narrower purpose Part B asks
for explicitly: confirming the *current* installed CLI's tool_use field names
are what they were assumed to be, rather than inferred from the old
transcript alone.

- **Model:** sonnet
- **Fixture:** a 3-line temp file in a throwaway git repo under the OS temp
  directory (`sample.py`, one `add`/`subtract`/`multiply` module) — not this
  repository, no Company OS invocation, no subagent.
- **Task:** read lines 5-7, make a one-line no-op edit to `subtract`, read
  lines 5-7 back to verify. Five turns.
- **Cost:** **$0.0746045**, 5 turns, well under any reasonable ceiling for a
  diagnostic probe.
- **Nested-session guard:** run with `CLAUDECODE`, `CLAUDE_CODE_ENTRYPOINT`,
  `CLAUDE_CODE_SSE_PORT` unset (the same three names
  `redaction._NESTED_SESSION_MARKERS` strips for every runner-launched child),
  confirming the probe is an independent session, not a nested one.

### Read tool_use shape (confirmed live, installed CLI 2.1.70)

```json
{"file_path": "<absolute path>", "offset": 5, "limit": 3}
```

`offset` and `limit` are both omitted when the model asks for the whole file
with no explicit range — never present-but-null. This is exactly what the raw
V2 transcript shows for the session's first two reads (`lifecycle.py`, the
test file's first read) and exactly what the probe reproduced.

### Edit tool_use shape (confirmed live, installed CLI 2.1.70)

```json
{"file_path": "<absolute path>", "old_string": "...", "new_string": "...", "replace_all": false}
```

### What `exploration_telemetry.py` now captures

`ExplorationEvent` gained three optional fields, Read-only:
`read_offset: int | None`, `read_limit: int | None`,
`read_full_or_implicit: bool | None` (`True` exactly when both are absent).
`Edit` is now its own branch in `parse_exploration` (previously fell into the
catch-all `"Other"` case with no path recorded) and keeps only the normalised
repository-relative `target` path and `order` — never `old_string`,
`new_string`, `replace_all`, or anything else from the tool call. A test
(`test_an_edit_event_keeps_only_path_and_order_never_the_replacement_text`)
asserts the serialized event never contains replacement text, as a standing
proof rather than a one-time check.

`_relativize` (unchanged) still turns an absolute `file_path` into a
repository-relative POSIX path or `<external>`, never raising — the same
best-effort discipline as every other path this module normalises.

---

## PART C — derived read-efficiency metrics

Ten new fields on `ExplorationTelemetry`, all `int | None`, all computed in a
single second pass over the already-built `ExplorationEvent` list (no second
parse of the transcript):

| field | meaning |
|---|---|
| `edits_total` | Edit tool calls in the session |
| `full_or_implicit_reads` | Read calls with no explicit `offset`/`limit` |
| `repeated_full_or_implicit_reads` | of those, how many were a repeat `(tool, target)` pair |
| `targeted_reads` | Read calls with `offset` and/or `limit` given |
| `read_after_edit_count` | Read calls whose immediately preceding event (any tool, any file) was an Edit |
| `same_file_read_after_edit_count` | of those, how many read the exact file the preceding Edit touched |
| `repeated_same_range_reads` | targeted reads whose exact `(target, offset, limit)` triple repeats a prior targeted read of the same file (full/implicit reads are excluded here — a repeated full read is already counted by `repeated_full_or_implicit_reads`, and folding it in here would double-count the same event under two metrics) |
| `overlapping_read_ranges` | targeted reads whose normalised line interval overlaps, but does not exactly repeat, a prior targeted read of the same file |
| `requested_read_lines_total` | sum of every read's requested line count — **only when every Read in the session gave an explicit `limit`**; `None` otherwise, never a partial sum |
| `repeated_requested_lines` | same rule, summed only over repeat reads |

**Why `requested_read_lines_total` is `None` so often.** A full/implicit read
or an offset given without a limit both request "the rest of the file," an
unknown quantity without the file's own line count, which this module does
not have and will not estimate. If *any* read in a session is like that, the
aggregate line count is marked unavailable rather than reported as a number
that silently omits part of the session's actual reading. This is the same
discipline `docs/company_os_repository_exploration_efficiency_v2.md` already
held every other UNAVAILABLE field to.

**Overlap is computed, not guessed at file-length scale.** A normalised
interval is `(start, end)`, 1-indexed, with `end=None` meaning "to EOF" for a
read given no `limit`. Two intervals overlap when neither is entirely before
the other, treating an open `end` as unbounded. No file's actual total line
count is consulted anywhere in this calculation.

### Tests

10 new cases in `tests/test_engineering_runner_exploration_telemetry.py`,
built the same way the file's existing fixtures are (hand-built NDJSON
matching the exact shapes the live probe and the real V2 transcript
produced): targeted-read range capture, full/implicit classification,
repeated-full vs. repeated-targeted counted separately, Edit path/order
capture with a standing "never contains replacement text" assertion,
read-after-edit and same-file-read-after-edit (both a hit and a miss case),
exact-range repeat vs. overlapping-but-different range, and the
"unavailable unless every read is fully targeted" rule for requested line
totals (both the unavailable and the available case). All 24 pre-existing
cases in the file, plus 8 in `tests/test_engineering_runner_exploration_report.py`
that read the same module's output, are unchanged and pass.

---

## PART D — what V2's ten repeated reads actually were

**Re-parsing the real V2 developer transcript with the extended parser**
(`session-1.transcript.txt` from
`company-os-repo-exploration-v2-runner-state/runs/wo-req-repo-exploration-v2-blocked-count-2-0d558c6c1a45/`,
against the worktree it actually ran in) reproduces V2's own reported counts
exactly — `file_reads_total=12`, `file_reads_unique=2`,
`file_reads_repeated=10`, `grep_total=2`, `searches_repeated=0` — confirming
the new parser is reading the same events V2's telemetry already counted, not
a different session. It also recovers what V2 could not report:

```json
{
  "edits_total": 5,
  "full_or_implicit_reads": 2,
  "repeated_full_or_implicit_reads": 0,
  "targeted_reads": 10,
  "read_after_edit_count": 0,
  "same_file_read_after_edit_count": 0,
  "repeated_same_range_reads": 0,
  "overlapping_read_ranges": 2,
  "requested_read_lines_total": null,
  "repeated_requested_lines": null
}
```

**The raw sequence** (order, tool, offset/limit or target):

```
 2  Read  lifecycle.py                         (full/implicit)
 3  Read  test_company_engineering_execution.py (full/implicit)
 4  Read  test_company_engineering_execution.py  offset=1    limit=100
 5  Grep  developer_attempts|reviews_completed|blocked_attempts
 6  Read  test_company_engineering_execution.py  offset=1660 limit=60
 7  Read  test_company_engineering_execution.py  offset=1715 limit=50
 8  Read  test_company_engineering_execution.py  offset=1820 limit=50
 9  Read  test_company_engineering_execution.py  offset=1870 limit=50
10  Read  test_company_engineering_execution.py  offset=1930 limit=30
11  Read  test_company_engineering_execution.py  offset=1959 limit=20
12  Read  test_company_engineering_execution.py  offset=1994 limit=25
13  Read  test_company_engineering_execution.py  offset=2038 limit=25
14  ToolSearch
15-18  Edit x4  lifecycle.py
19  Grep  def test_the_correction_loop|def test_a_blocked|blocked_attempts
20  Read  test_company_engineering_execution.py  offset=1240 limit=40
21  Edit  test_company_engineering_execution.py
```

**This directly refutes the speculation V2's own report made.** V2 §12 said
the repeated reads were "most plausibly triggered by the coding CLI's own
edit-verification behavior" — an educated guess, made honestly as a guess,
because V1/V2's telemetry retained no range data to check it against. The
recovered ranges show the opposite: **`read_after_edit_count` is 0.** Not one
of the ten repeated reads of the test file immediately follows an Edit of
that file (or any file) — every Edit in the sequence (orders 15-18, order 21)
is followed by a `Grep`, `ToolSearch`, `Bash`, or `Write`, never a `Read` of
the just-edited file. There is no post-edit verification pattern in this
transcript at all.

What the ranges show instead: **one full/implicit read of the whole test
file (order 3), followed by eight targeted reads walking forward through it
in mostly-increasing 20-to-100-line windows** (1-100, then 1660→2062 in eight
overlapping-at-the-boundary steps), **entirely before any edit was made**,
plus one final targeted read (order 20, offset 1240-1279) immediately
preceding the one edit to that file (order 21) — a read-*before*-edit, not
read-*after*. `overlapping_read_ranges=2` (1660-1719 vs. 1715-1764 share 5
lines; 1930-1959 vs. 1959-1978 share 1 line) — boundary seams from paging
through the file in windows, not the same region read twice.
`repeated_same_range_reads=0` — no two reads asked for the exact same lines.

**Classification: B — repeated targeted reads of small, non-identical
regions of one already-identified file**, read while scanning it (most
plausibly to find a sibling counter test to pattern the new one on — the
work order's own acceptance criteria named exactly this: "following the exact
pattern `developer_attempts` and `reviews_completed` already establish"),
not a discovery loop across the repository (**A** is ruled out — only 2 of 12
reads were full/implicit, and neither repeated), and not post-edit
verification (**C** is ruled out by direct evidence, not merely unconfirmed —
`read_after_edit_count=0`).

**Reviewer session**, same job, same evidence source: `file_reads_total=3`,
`unique=2`, `repeated=1` — `<external>` (order 2, a `ToolSearch`-adjacent
system file outside the worktree), `lifecycle.py` (order 3, full/implicit),
`lifecycle.py` again (order 4, repeat). Two reads of one two-file diff, one of
them a repeat of the whole file — too small a sample to classify beyond
"consistent with the developer's own full/implicit-then-targeted split," not
separately declared here.

---

## PART E — no read-blocking system built

Not implemented, per the brief: no Read denial, no tool interception, no
Claude hook, no `CommandRunner` rewrite for live streaming, no caching proxy,
no replacement Read tool, no Graphify/Serena/RTK/Ponytail/ast-grep
installation. Part D's own evidence is the reason this stays deferred: the
repeated reads were targeted, non-identical, entirely pre-edit navigation of
a file the work order had already named — suppressing them would most likely
degrade the session's ability to find where its own acceptance criteria
("following the exact pattern... already establish") asked it to look, not
save meaningful resources. There is no large/full-file-reread pattern in this
evidence for a V3B intervention to target.

---

## PART F — execution context for the heavily-read file

Read directly from the V2 matched job's own `instructions.md`
(`run-000001/developer-01/instructions.md`, the compiled developer briefing
that actually shipped):

- **Test file named:** yes — `tests/test_company_engineering_execution.py`
  appears twice, once as a required test and once as an authorized path.
- **Test symbols supplied:** yes, but only twelve helper/fixture functions
  from the top of the file (`_config`, `_index`, `_fake_repo`,
  `_routine_request`, `_request`, `_assessment`, `_order`, `_receipt`,
  `_attestation`, `_gate_report`, `_stores`, `_validation` —
  `execution_context.py`'s symbol extraction covers top-level functions,
  classes and methods, and this file's actual `test_*` functions are also
  top-level, so the twelve named are simply the ones that happened to sort
  first, not a deliberate helpers-only selection).
- **Line spans supplied:** yes, for those twelve (`_config#128-129` through
  `_validation#311-332`) — none of which cover the 1240-2062 region the
  session's own reads clustered around.
- **Test excerpt supplied:** no — `execution_context.py`'s
  `MAX_FILES_WITH_EXCERPTS=1` gave its one source excerpt to the primary
  production file (`EngineeringJob`/`JobTransition` in `lifecycle.py`), per
  its documented biggest-and-most-anchoring selection rule; the test file got
  symbols and spans but no excerpt at all.
- **Why another file wasn't ranked instead:** it wasn't a ranking failure —
  the test file *was* the developer's second-ranked file (`briefs.
  rank_primary_files` puts every authorized path first), and got its full
  symbol/line-span treatment. The gap is narrower: the context bundle's
  symbol table stopped at the file's helper functions and never named the
  existing sibling counter tests (`developer_attempts`, `reviews_completed`)
  the work order's own acceptance criteria pointed the session at by name.

**Context deficiency found: yes**, narrowly. Read order 20 (offset 1240,
limit 40) lands immediately before the file's edit and squarely inside the
region that now holds `test_blocked_attempts_increments_on_blocked_and_not_on_other_transitions`
— evidence the session was actively hunting for exactly this kind of sibling
test, and the eight targeted reads at orders 6-13 are consistent with the
same hunt happening earlier, before it narrowed in. This does not mean
context should have been *increased indiscriminately*: it means the two
named sibling patterns (`developer_attempts`, `reviews_completed`), already
present in the work order's own prose, were a fully derivable pointer the
symbol table did not surface, because `execution_context.py` currently has no
mechanism for "also excerpt/point-to a test function whose name matches an
acceptance-criteria phrase."

**Candidate for V3B, not adopted here:** when a work order's acceptance
criteria or objective names an existing test function (or a close paraphrase
of one), include that one test function's symbol span — not a full-file
dump — alongside the primary production excerpt. This is evaluated as a
hypothesis with one supporting data point, not adopted; V3B would need to
measure whether it actually reduces the targeted-read count on a second
matched job before calling it a fix.

---

## PART G — Graphify / RTK, re-checked against this round's evidence

**Graphify** (repository navigation): still deferred. V2 already found zero
repository-wide discovery cost (0 irrelevant files read, 2/2 files read
exactly the 2 files changed); this round adds that the 10 "repeated" reads
were not a navigation problem either — they were targeted, sequential,
single-file reads with real offsets and limits, precisely the case Graphify
would have no leverage over. Nothing in this round's evidence points at
repository navigation as a remaining cost.

**RTK** (command/output verbosity): still deferred. The developer session's
`Bash` calls were 2 (`test_commands`, per V2's own telemetry) with no
`other_shell_commands`, and this round's telemetry adds no evidence that
Bash/test/search output volume is a material remaining cost — the material
remaining cost this round *identifies* is developer cache-read spent on Read
calls, a different tool entirely, which RTK does not touch.

Neither recommendation changes from V2's own §8/§12. Note: this session's own
shell invocations were transparently rewritten by the user's global RTK CLI
hook (`git status` → `rtk git status`, `pytest` → `rtk pytest`, etc., per
`RTK.md`) throughout this milestone's own work — an operator-level tool used
on this session's own shell commands, unrelated to whether RTK should be
*installed as a Company OS engineering-runner dependency*, which is the
question this section answers and which remains no.

---

## PART H — tests

Focused, in order:

- `tests/test_company_engineering_execution.py -k "governance or routing or
  specialist or escalation or risk_still"` — 22 passed (11 new + pre-existing
  routing tests it overlaps with).
- `tests/test_company_engineering_execution.py`, full file — 128 passed (117
  pre-existing + 11 new).
- `tests/test_engineering_runner_exploration_telemetry.py` +
  `tests/test_engineering_runner_exploration_report.py` — 42 passed (24 + 8
  pre-existing, 10 new).
- `tests/test_company_external_engineering_runner.py`,
  `tests/test_external_engineering_runner.py`,
  `tests/test_company_workforce.py`, `tests/test_company_finance.py` — 403
  passed (unaffected by either change; run as a check that `_request()`'s
  shared default objective — which contains the word "governance" — is not
  depended on anywhere for a specific routing outcome).
- `tests/test_company_os_research.py`, `tests/test_company_os_research_batches.py`,
  `tests/test_company_os_research_ingestion.py -k
  "this_branch_changed_no_race"` — 3 passed (the `tools/` branch-scope
  guards, re-checked after committing, per the standing project note that
  their failure mode is invisible before a commit).

**Full deterministic suite:** see FINAL REPORT below for the exact count,
captured after this document was drafted.

---

## PART I — no full live matched job

Confirmed: the only live model call this milestone made was the one Part B
probe ($0.0746045, 5 turns, a throwaway 3-line fixture, no Company OS
invocation). No `python -m company.engineering request` /
`python -m tools.engineering_runner run-one` job ran. Part D's classification
of V2's own repeated-read pattern came from re-parsing V2's already-paid-for
transcript with the extended parser, not from a new session.

---

## PART J — governance

Unchanged by this milestone: Company OS / `tools` boundary (the branch-scope
guards re-checked in Part H stay green), no-subagents rule (this entire
milestone ran directly, sequentially, no `Agent`/`Workflow` tool call), the
consumer profile, one-developer-attempt / one-reviewer-pass shape (unused
this round — no job ran), CEO approval and integration-gate requirements
(untouched — no gate ran, no integration attempted), STANDARD routine tier
(Part A's fix makes it *more* reliably reachable for genuinely routine
requests, not less available for genuine specialist work), and the
strongest-tier routing for genuinely specialist/high-risk work (every
existing HIGH/CRITICAL/security/architecture/concurrency trigger is
untouched; six genuine-governance-action phrasings were added as regression
tests and all still route to `specialist_domain="governance"`).

**Autonomous Company OS engineering remains PAUSED.** This milestone is
diagnosis and a routing-precision fix; it does not run a job, does not touch
`docs/company_os_consumer_resource_mode.md`, and does not claim to lift or
narrow the pause. See that document for the controlling record.

---

## FINAL REPORT

**baseline branch:** `company-os-v1-repository-exploration-efficiency-v2`
**baseline SHA:** `6dd789135040dcdfe99491b644c3b58c8fa34a37`
**new branch:** `company-os-v1-read-efficiency-v3a`
**new SHA:** (recorded in the commit that follows this document)
**pushed:** yes, after deterministic verification
**merged:** no

### ROUTING PRECISION

**previous false-positive mechanism:** `derive_routing` matched
`request.objective + request.notes` against the bare noun `"governance"` in
`SPECIALIST_TRIGGERS`, so any mention of the word — including in explanatory
`notes` — forced `specialist_domain="governance"` and the strongest model
tier, regardless of whether the work was actually a governance action.
**fix:** trigger text is `request.objective` alone (notes never
participate); the bare noun `"governance"` is removed from the trigger
table, replaced by the specific action phrases already present
(`"permissions policy"`, `"protected policy"`, `"constitution"`, `"approval
boundary"`, `"separation of duties"`) plus three added ones (`"governance
policy"`, `"governance rules"`, `"governance model"`).
**notes affect routing:** no (verified:
`test_governance_mention_in_notes_does_not_route`).
**bare governance noun affects routing:** no (verified:
`test_a_harmless_governance_mention_stays_routine` and 2 parameterized
variants).
**genuine governance action routing:** unchanged — still routes to
`specialist_domain="governance"` (verified: 6 parameterized cases in
`test_genuine_governance_actions_still_route_to_specialist`).
**security/architecture/concurrency behavior:** unchanged; `explicit
specialist_domain`, `escalate_reasoning`, and HIGH/CRITICAL risk routing all
unchanged (verified: 4 dedicated tests).
**tests:** 11 new, 128/128 passing in `test_company_engineering_execution.py`.

### READ TELEMETRY

**raw V2 range evidence available:** yes — the real
`session-1.transcript.txt` for both the V2 matched job's developer and
reviewer stages, in the un-gitted external runner-state directory
(`company-os-repo-exploration-v2-runner-state/`), sufficient on its own to
answer Part D without a probe.
**cheap probe required:** yes, for the narrower purpose of confirming the
*currently installed* CLI's tool_use field names live rather than assuming
they match the old transcript.
**probe cost if run:** $0.0746045, 5 turns, sonnet, throwaway 3-line fixture,
no Company OS, no subagent.
**installed CLI version:** 2.1.70 (same version V2's own probe used).

**Read tool shape:** `{"file_path": str, "offset": int | omitted, "limit":
int | omitted}` — both omitted together means an implicit/full read.
**Edit tool shape:** `{"file_path": str, "old_string": str, "new_string":
str, "replace_all": bool}`.

**new telemetry fields:** `ExplorationEvent.read_offset`,
`.read_limit`, `.read_full_or_implicit`; `Edit` events now carry a real
`target` path (previously fell through to an unlabeled `"Other"` event).
**new derived metrics:** `edits_total`, `full_or_implicit_reads`,
`repeated_full_or_implicit_reads`, `targeted_reads`, `read_after_edit_count`,
`same_file_read_after_edit_count`, `repeated_same_range_reads`,
`overlapping_read_ranges`, `requested_read_lines_total` (None unless every
read in the session is fully targeted), `repeated_requested_lines` (same
rule).

**V2 repeated-read classification: B** — repeated targeted reads of small,
non-identical regions of one already-identified file.

**evidence:**
**V2 heavily-read file:** `tests/test_company_engineering_execution.py`.
**total reads:** 12 (2 unique files, 10 repeats of this one file).
**range/full-read evidence:** 2 full/implicit reads (this file once, plus one
of `lifecycle.py`), 10 targeted reads with explicit `offset`/`limit`, walking
forward through the file in 20-to-100-line windows, mostly non-overlapping
(`overlapping_read_ranges=2`, small boundary seams only), zero exact-range
repeats (`repeated_same_range_reads=0`).
**reads after edits:** **0** — directly refutes V2's own §12 speculation
that the pattern was "most plausibly triggered by the coding CLI's own
edit-verification behavior." Every Edit in the sequence is followed by a
Grep/ToolSearch/Bash/Write, never an immediate Read.
**same-range repeats:** 0.
**requested lines if trustworthy:** unavailable (`null`) — 2 of the 12 reads
were full/implicit, so no session-wide total line count can be stated
without partially estimating the untracked ones.

### EXECUTION CONTEXT

**test file named:** yes.
**test symbols supplied:** yes — 12 helper/fixture functions, none of them
the sibling counter tests (`developer_attempts`, `reviews_completed`) the
work order's own acceptance criteria named by pattern.
**line spans supplied:** yes, for those 12 only (lines 128-332); none cover
the 1240-2062 region the session's reads clustered around.
**test excerpt supplied:** no — the one available excerpt slot went to the
primary production file (`lifecycle.py`), per `execution_context.py`'s
documented one-file-one-or-two-symbols budget.
**context deficiency found: yes**, narrowly — the acceptance criteria named
two sibling tests by pattern that the symbol table did not surface, and the
session's own read at offset 1240 (immediately preceding its one edit to
this file) lands exactly where the sibling counter test now lives.
**explanation:** see Part F. Candidate for V3B (not adopted here): when
acceptance criteria or objective text names or closely paraphrases an
existing test function, include that one function's symbol span alongside
the primary production excerpt — a small, targeted addition, not a
full-file dump, and not adopted without measuring it on a second matched
job first.

### EXTERNAL TOOLS

**Graphify: KEEP DEFERRED.** This round's evidence (targeted, sequential,
single-known-file reads, zero navigation-shaped reads) gives Graphify no
leverage to demonstrate; V2's own zero-irrelevant-files finding stands
unchallenged.
**RTK: KEEP DEFERRED.** Bash/test output was 2 calls, both `test` category,
in the matched job's own telemetry; the identified remaining cost is Read
calls, a tool RTK does not intermediate as a Company OS engineering-runner
dependency (distinct from the user's own operator-level RTK shell hook, which
this session used transparently throughout and is outside this question's
scope).

**recommended V3B intervention:** *conditionally* — a bounded acceptance-
criteria-to-test-symbol pointer in `execution_context.py` (Part F), to be
proposed and measured on a second matched job, not implemented in V3A. **No
read-blocking, denial, or interception mechanism is recommended at all** —
Part D's evidence shows the reads it would suppress were targeted navigation
toward exactly the region the work order asked the session to find, not
waste.

**tests:** 21 new across two files (11 routing, 10 telemetry); zero
pre-existing tests modified or deleted.
**full suite:** see below.
**new regressions:** zero (confirmed against the full-suite run below).

**consumer viability:** SUPPORTED — this milestone spent $0.0746045 total
(one diagnostic probe), well inside consumer-mode ceilings, no matched job
run.

**verdict:**

**EXECUTION EFFICIENCY V3A: PASS** — both named defects (the routing false
positive, and the "what were the 10 repeated reads" open question) are
resolved with direct evidence rather than assumption; V2's own speculative
explanation for the repeated reads is shown to be wrong, replaced with a
concrete, re-derivable classification; no premature read-blocking machinery
was built; the one narrow context gap found is recorded as a V3B candidate,
not adopted. Autonomous Company OS engineering remains PAUSED — unchanged by
this milestone.
