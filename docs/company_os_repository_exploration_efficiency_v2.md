# Repository Exploration Efficiency V2

**Branch** `company-os-v1-repository-exploration-efficiency-v2`, based on
`company-os-v1-repository-exploration-efficiency` at `9b5f2242e2dfbcbf06c68ea678d8e9cbd8046df4`
(verified: local and remote HEAD agreed, worktree clean, all three V1 commits
present, before this branch was cut). **Not merged. Not authorization to merge.**

V1 passed: one matched job, developer `cache_read_units` down 46.0% against
Consumer Mode V1 (`990,324` vs `1,835,390`), STANDARD tier, one attempt, one
reviewer, gate READY, zero regressions. V1 also named its own limits plainly:
exploration inside the session was still invisible (`--output-format json`),
the repo map had no reverse *production* dependency index despite claiming to,
the model still discovered exact symbols and line ranges itself, and the
46.0% figure was n=1 on a task slightly easier than its own baseline. This
milestone is that improve-and-prove step repeated once, honestly, against
those four named gaps.

---

## 1. Making exploration observable

### The CLI probed live, not assumed

V1's docstrings stated "there is no stream-json ... for any session, ever."
That was true of every *stored* session, because every stored session was
launched with `--output-format json`. It was not a fact about the CLI. Probed
directly against the installed binary (`claude --version` → `2.1.70`):

```text
--output-format <format>   "text" (default), "json" (single result), or
                            "stream-json" (realtime streaming)
```

`stream-json` exists. Two more facts only a live probe found, not documented
in `--help`:

1. **Under `--print`, `stream-json` requires `--verbose`** or the CLI refuses
   to start: `Error: When using --print, --output-format=stream-json requires
   --verbose`.
2. **The final `stream-json` line is byte-for-byte the same envelope shape**
   `backends.normalise_claude_usage` already parses from plain
   `--output-format json` (`session_id`, `usage`, `modelUsage`,
   `total_cost_usd`, `num_turns`, `is_error`, `subtype`, `permission_denials`)
   - confirmed by capturing a real transcript and diffing the last line's keys
     against what that function reads. So switching formats needed **zero**
     changes to cost/token parsing; `exploration_telemetry.split_result_envelope`
     is the seam that hands `normalise_claude_usage` the same dict either way.

A third finding, incidental but worth recording: the nested-session guard
(`CLAUDECODE` etc.) blocks a probe run from inside a Claude Code session, and
`redaction.child_environment()` already strips those three variables for every
child this runner starts - the probe simply had to do by hand what the runner
already does.

### What changed, and what deliberately did not

`backends.py`'s `ClaudeCodeBackend.launch` now passes `--output-format
stream-json --verbose` instead of `json`. `_read` calls
`exploration_telemetry.split_result_envelope` (finds the final `result`-typed
line, or falls back to parsing the whole text as one object for a plain-json
transcript) and `parse_exploration` (walks every `assistant`/`user` message's
`tool_use` blocks). `CommandRunner.run` in `process.py` was **not touched**:
it still calls `subprocess.run(capture_output=True)` and returns once the
process exits. The shape of the one string that comes back changed (many
JSON lines instead of one); *when* it comes back did not. Real mid-session
observation would need incremental reads from a live pipe - a materially
larger change to the one subprocess boundary this package has - and the
brief named live enforcement as secondary. So: **POST_SESSION_OBSERVABLE**,
honestly, not a live ceiling dressed up as one.

### What is extracted, and what is refused

Per tool call: a tool name, a category, and - for `Read`, `Grep`, `Glob` - a
normalised repository-relative path or search pattern, in call order, capped
at 500 events (`exploration_telemetry.MAX_EVENTS`). A `Bash` call is reduced
to one of four categories (`git` / `test` / `search` / `other`) from its
command text; **the command text itself is never kept**. No tool output, no
file contents, no assistant prose. `CommandRunner.run` already scrubs
`stdout` for credentials before this module ever sees it, so the parser reads
already-redacted text and adds no second redaction pass.

Every count is `int | None`, never defaulted to `0`: `format="unsupported"`
(a plain-json transcript, an older CLI, a non-Claude backend) means every
count is `None` - UNAVAILABLE, not a session that explored nothing.

Derived, from the events: `file_reads_total` / `_unique` / `_repeated`,
`grep_total`, `glob_total`, `searches_total`, `searches_repeated`,
`git_commands`, `test_commands`, `other_shell_commands`, `bash_total`,
`tool_errors`. `exploration_report.py` adds two correlations that need a
second file to answer (`changes.json`'s measured `files_changed`):
`files_read_never_changed` and (given a neighborhood) `files_read_outside_neighborhood`.

Tests: `tests/test_engineering_runner_exploration_telemetry.py` (16 cases,
built from the exact shapes a live probe produced - tool_use, tool_result
errors, the plain-json fallback, the event cap) plus 8 new cases in
`tests/test_engineering_runner_exploration_report.py`.

### Where it lands

`SessionOutcome` gained `exploration` (the small metrics dict, safe inside
`to_dict()`) and `exploration_events` (the bounded event list, kept out of
`to_dict()` on purpose so that record stays the size it always was).
`runner.py` writes a companion `exploration.json` beside `session.json` for
any stage whose backend produced one - a `ScriptedBackend` in a test, or the
`codex` backend, produces none, and none is written; that absence is the
honest case, not an empty placeholder. `evidence.py`'s `_usage()` promotes
three summary counts into `receipt.usage`: `repo_file_reads`,
`repeated_file_reads`, `repo_searches` - the three the milestone brief names
for the budget table (§6).

---

## 2. Upgrading the repository map

Two gaps V1 named in its own limitations section, both closed additively in
`tools/engineering_runner/repo_map.py`:

**A. Symbol definitions with line spans.** `ModuleMap.symbols` is now a tuple
of `SymbolSpan(qualified_name, kind, start_line, end_line)` for every
top-level class, top-level function, and class method (one level of nesting -
a function nested inside a function is not a symbol a session would ask for
by name). `qualified_name` is `Class.method` for a method, so a method and a
same-named top-level function never collide.

**B. Reverse production dependencies.** V1's own docstring claimed the map
"help[s] identify modules that already depend on authorized files," but only
`tests_by_module` existed - a *test* reverse index, not a production one.
`RepoMap.production_dependents` is the missing half: module path → other
*production* modules that import it, resolved by real dotted-name matching
(exact or package-prefix), the same way the test index already was, minus
self-imports. Shares one new helper, `_resolve_imports_to_paths`, with the
existing test-index builder rather than duplicating the matching logic.

**C. Bounded neighborhood.** `neighborhood(repo_map, path)` returns one
`Neighborhood`: the module's own symbols, its imports, its production
dependents, its covering tests, and which of its dependents are themselves
entry points - all bounded (`symbol_limit`, `dependent_limit`, `test_limit`,
`import_limit`), all plain dict lookups against indexes built once at map-build
time. No recursion, no traversal of a dependent's own dependents.

Measured on this repository's own real tree (`company` + `tools` + `tests`):
the map still builds in about the same time as V1 measured (~2s), and the two
new indexes add no new file walk - they are extra passes over the same parsed
`ModuleMap` list `build_repo_map` already produces.

Tests: 8 new cases in `tests/test_engineering_runner_repo_map.py` (symbol
spans across class/method/function, the reverse production index resolving a
real import, self-imports excluded, neighborhood bundling, entry points among
dependents, an unknown path reporting `found=False`, bounded limits, a
`SymbolSpan` round trip) - all 20 cases in that file pass, including the 12
inherited from V1 unchanged.

---

## 3. The compiled execution context

New module, `tools/engineering_runner/execution_context.py`. `ExecutionContextBundle`
replaces two things V1 rendered separately: the free-text repo-map query
result, and - in the developer briefing only - the **entire packet dumped as
JSON** at the end of every developer briefing (§4 explains why that was mostly
duplication).

**Size budget, chosen before the matched job:** `MAX_BUNDLE_CHARS = 6000`.
Chosen for scale against the consumer-mode baseline's own referenced material
(3,661-16,985 characters), not tuned after seeing a result. `render()` is a
hard truncation (`bundle.truncated` says so), not a suggestion.

**What it contains, per file:** owner, a one-line reason it is there, its
symbols with exact line spans, its production dependents, its covering tests,
which dependents are entry points, and - for at most one file, at most two
symbols (`MAX_FILES_WITH_EXCERPTS`, `MAX_SYMBOLS_PER_EXCERPT`) - a small exact
source excerpt (`MAX_EXCERPT_LINES = 25`, `MAX_EXCERPT_CHARS = 600`).
Excerpt symbols are chosen biggest-and-most-anchoring first (a class before a
function, larger spans before smaller), not file order - measured live: file
order on this repository's own `repo_map.py` picked a two-line tokenizer
helper over the `SymbolSpan`/`ModuleMap`/`RepoMap` classes the file is
actually about.

**Ranking is the caller's job, not this module's**, and the two callers
differ on purpose (§5): `briefs.rank_primary_files` (developer) puts
authorized paths first, then a *small, capped* number of the objective's own
best text matches; `runner.py`'s reviewer path uses the diff's own changed
paths directly, no text query at all.

**A ranking defect found and fixed before it shipped.** The first version
padded every developer bundle out to `limit` (5) files using the free-text
query alone. Measured on this repository's own real scale (593 Python files,
not the tests' small synthetic fixture): a query for "extend repo_map.py with
symbol spans and reverse production dependencies" ranked two unrelated test
files - `tests/test_company_finance.py`, `tests/test_company_youtube_studio_
ingestion.py` - at the same score as the file actually being changed, because
a test file's path routinely repeats its subject's name
(`test_engineering_runner_repo_map.py` contains "repo" and "map" too) and
`query()`'s path-token weighting cannot tell that apart from the module
itself. Raising a score threshold would not have fixed it - the false
positives scored *exactly* as high as the true one. Fixed by capping the
*guessed* portion (`max_query_fill = 2`, and only enough to reach
`minimum_files = 2` total, not up to `limit`), not by reworking `query()`'s
general scoring, which V1 already shipped and tested and which this milestone
was not asked to redesign. Recorded here as an honest finding about the
existing mechanism's behavior at real scale, not swept into "adopted, no
caveats."

Tests: `tests/test_engineering_runner_execution_context.py` (17 cases:
ranking order, deduplication, the size budget's hard cut, excerpt inclusion
and exclusion, an unknown path, no-repo-map degradation, context-ref
rendering as pointers).

---

## 4. Briefing duplication

Traced concretely, not by inspection alone: `company/engineering/transport.py`
builds a briefing payload from **two** sources that mostly say the same
thing - `_work_order_terms(order)` (objective, branch, base commit, authorized
paths, forbidden paths, acceptance criteria, constraints, required tests) and
`packet.to_dict()` (objective, path_scope, expected_branch,
expected_base_commit, acceptance_criteria, constraints, required_tests - plus
its own bookkeeping: `context_fingerprint`, `context_cache_key`, `version`,
`executor`, `completion_protocol`). V1's `developer_instructions` rendered the
first source field-by-field **and then dumped the second, whole, as JSON** at
the end of the briefing - the packet's operative fields repeating what had
already been printed in prose, plus fingerprints and cache keys a session
cannot act on.

The one genuinely non-duplicate thing buried inside that dump was
`packet["context_refs"]` - the work order's actual `{kind, ref, reason, span}`
pointers - which V1's `developer_instructions` never rendered anywhere else.
Removing the whole-packet dump without replacing that would have deleted real
content, not just duplication.

**Fix:** the whole-packet JSON dump is gone from `developer_instructions`.
`ExecutionContextBundle` now renders `context_refs` as a compact, one-line-per-
reference pointer list (`  - [file] path#12-40 - reason`) alongside the
ranked file list, in the one new "Execution context" section that replaced
both the old repo-map section and the packet dump.

**Measured, honestly, not tuned to produce a smaller number.** On a
representative real work order (one authorized file in this repository, two
context refs, run against this repository's own live repo map):

| | V1 | V2 | change |
|---|---:|---:|---:|
| developer instructions | 7,321 chars | 7,291 chars | -30 (-0.4%) |

Character count is roughly flat, not smaller, and that is reported as
measured rather than pushed down further by cutting content. The removed
verbatim packet dump was worth about 1,100 characters of near-total
duplication; the new bundle spends a comparable amount on **new, non-
duplicate** information the old briefing never gave the session at all -
exact symbols with line spans, production dependents, and (for the top file)
a small source excerpt. Section 4 asked to stop rendering the same
information twice, which this does; it did not ask for the smallest possible
prompt at the cost of the richer navigation §2/§3 exist to provide, and this
milestone did not trade one for the other to make a headline number look
better. The number that actually matters for this milestone - developer
session `cache_read_units` on a live job - is reported in §10/§11, separately,
honestly, whichever way it lands.

---

## 5. Reviewer context, smaller and more precise

V1's `review_instructions` called the *same* free-text query the developer
got, scoped to `authorized_paths` - the whole work order's grant, which can be
much larger than what one attempt actually changed - and never rendered
`context_refs` at all (reviewer had strictly less than developer, not by
design, just because nobody had wired it).

**Fix:** the reviewer's bundle is built from the receipt's own measured
`files_changed` - the diff's actual paths, known exactly, needing no
free-text guess - with no source excerpts (`include_excerpts=False`: the
reviewer already has the diff itself for the bytes that changed; an excerpt of
surrounding code would repeat the developer's discovery aid for a session that
is judging, not discovering) and a materially smaller neighborhood
(`symbol_limit=6`, `dependent_limit=5`, `test_limit=3`, against the
developer's `symbol_limit=12`, `dependent_limit=8`, `test_limit=5`).

Measured on the same representative work order, developer changed one file,
reviewer scoped to it:

| | V1 | V2 | change |
|---|---:|---:|---:|
| reviewer instructions | 3,749 chars | 4,155 chars | -406 (-10.8%) |

Larger, not smaller, for the same reason as §4: the reviewer went from *zero*
visibility into symbols, production dependents and context refs to a small,
bounded amount of all three. Precision (scoped to what changed, not to the
whole grant; no free-text noise; no excerpts) is what this section asked for,
and that is what changed - not "smaller at any cost."

---

## 6. Exploration budget

`company/efficiency/budget.py`'s `DIMENSIONS` table: `repo_file_reads` and
`repo_searches` move from `UNAVAILABLE` to `POST_SESSION_OBSERVABLE`, and a
new dimension, `repeated_file_reads`, is added at the same class. All three
are scored like `input_tokens`/`output_tokens` already were - "observation
only," no ceiling, `exceeded` always `False` - never `LIVE_ENFORCEABLE`: a
session cannot be stopped mid-turn for reading too much, and nothing here
pretends otherwise. `check_budget` gained three optional keyword parameters
of the same names; `None` (no `stream-json` trace) leaves them correctly
unscored, exactly like every other POST_SESSION_OBSERVABLE dimension a caller
does not supply. `company/efficiency/emission.py` passes
`receipt.usage.repo_file_reads` / `.repo_searches` / `.repeated_file_reads`
through at the one call site that already scores everything else.

`company/runtime/receipts.py`'s `ReceiptUsage` gained the same three optional
fields, validated the same way every other optional integer on that dataclass
already is (non-negative or `None`) - `from_mapping`'s unknown-field refusal
needed no change, since the new names are now recognised dataclass fields.

Tests: two existing dimension-classification tests updated to state the new
truth (`test_company_efficiency.py`), one renamed to state precisely what it
now proves (unscored-without-a-value, not "never scorable"), and one new test
proving all three score as real observations, never as enforced violations,
when a value is supplied. One new end-to-end test
(`test_exploration_telemetry_survives_the_receipt_round_trip`) drives a real
`SessionOutcome.exploration` block through `evidence.build_receipt` into
`SessionReceipt.from_mapping` and `validate_receipt`, proving the whole chain
rather than each half in isolation.

---

## 7. Governance

Nothing here touches: the Company OS / tools boundary (every new symbol in
`tools/engineering_runner/execution_context.py` and
`exploration_telemetry.py` imports only stdlib and sibling modules in the same
package - no `company/` import, checked by the same
`architecture.production_does_not_import_company_os` gate V1 relied on), the
no-subagents rule, the separate-reviewer routing, CEO approval, automatic-
merge refusal, publish/deploy refusal, or the integration gate. `company/`
changes (`receipts.py`, `budget.py`, `emission.py`) are schema and wiring
extensions of exactly the kind V1 itself made to the same two files - no
architecture check was exempted, extended or weakened to land this work.

`tools/` is watched by three research branch-scope guards
(`test_company_os_research{,_batches,_ingestion}.py`) that refuse a
*modification* under a production root and allow only *additions* under
`tools/engineering_runner/` and `tools/youtube_fetch/`. Every file this
milestone touches under `tools/` is inside `tools/engineering_runner/`, and
none of it exists on `origin/main` at all (Company OS has never merged there),
so every change - new file or edited one - shows as an addition in the
`origin/main...HEAD` diff those guards read, the same way V1's did. Re-checked
after committing, per the standing project note that this failure mode is
invisible before a commit.

---

## 8. External tools

No new tool installed, probed with a fresh fetch, or added to
`requirements.txt`. Graphify, Serena, RTK, ast-grep and the Ponytail package
are all **DEFERRED**, exactly as instructed - this milestone's own findings
(§3's ranking defect, in particular) are recorded as gaps in the *existing*
internal mechanism, with a documented, bounded workaround, not as evidence
that an external tool is now needed. No gap found this round required a
capability `ast` plus a hand-written index cannot express.

---

## 9. Predeclared threshold

Per the brief, declared before the live job and not moved afterward:

- V1 developer `cache_read_units`: **990,324**
- **V2 threshold: developer `cache_read_units` ≤ 792,259** (20% reduction from V1)
- Aspirational range 700k-750k, explicitly **not** the acceptance bar.

Also predeclared to report regardless of outcome: model, turns (where
reliable), output units, cache-read, cache-creation, wall time, cost,
instruction chars, execution-context chars, file reads/unique/repeated
(where trustworthy), searches/repeated searches (where trustworthy), files
changed, tests, reviewer result, gate result.

---

## 10. Deterministic validation, then the one matched job

Full suite at `274d124` (this milestone's implementation commit): **4,600
passed, 6 failed, 337 skipped** - the known gitignored-artifact fingerprint
(`test_neon_proof`'s missing replay, `test_sloped_v251_world` x4 and
`test_sloped_v252_world` x1 missing `output/sloped_race_v1/cameras_v221_5432.json`),
**zero new failures**. One regression was caught and fixed *before* this
count: the first full run added a 7th failure,
`test_company_os_remains_removable_and_production_does_not_import_it` - a
plain substring scan for `"import company"` / `"from company"` across
`tools/`, tripped by this milestone's own docstring prose ("an `import
company.widgets` reaches everything under it," a synthetic example name
mirroring the test fixtures) rather than by an actual import. Reworded, not
suppressed; re-ran clean. The three `tools/`-watching research branch-scope
guards (`test_this_branch_changed_no_race_fight_or_v30_code` in each of
`test_company_os_research{,_batches,_ingestion}.py`) were re-checked *after*
committing, per the standing project note that their failure mode is
invisible before a commit: all three pass, every new and changed file sitting
inside `tools/engineering_runner/`, which does not exist on `origin/main` at
all and so shows as additive in that diff regardless of how many times V1 and
V2 between them have touched it.

**The matched job.** Objective: a new `blocked_attempts` counter on
`EngineeringJob`, incrementing once per transition into `BLOCKED`, following
the exact pattern `developer_attempts` and `reviews_completed` already
establish. Same subsystem (`company/engineering`), same authorized-path shape
(one module + its test file), same risk level (`medium`) as the historical
`attempts-remaining` / `reviews-completed` jobs - and, unlike those two
counters, genuinely not yet implemented anywhere in the repository, confirmed
by grep before the request was written.

**A real classification defect, caught before it reached the session.** The
first drafted objective used the word "governance" in one sentence ("so a CEO
page can show governance activity..."). `company/engineering/intake.py`'s
`SPECIALIST_TRIGGERS` table fires a `specialist_domain` on that exact word,
which would have forced this job away from the routine STANDARD tier this
milestone needs to measure - the same class of defect Consumer Resource Mode
V1 (`docs/company_os_consumer_resource_mode.md`) found and fixed for the
*default* specialist domain, now triggered by this request's own wording
instead. Caught
by reading the `request` command's derivation output before running anything
expensive, not by inspection: `specialist_domain: "governance"`,
`specialist_reason: "the objective names 'governance', which is governance
work"`. A second attempt's *notes* field re-triggered the same rule by
explaining the first failure using the word "governance" - reworded again,
confirmed clean (`specialist_domain: ""`, routine classification), and *that*
version is the one run. The two earlier, mis-classified work orders
(`wo-req-repo-exploration-v2-blocked-attempts`,
`wo-req-repo-exploration-v2-blocked-count`) were left unactioned in the
private dogfood state directory - `developer_attempts: 0` on both, so nothing
was spent on them.

Run via `python -m company.engineering request` then `python -m
tools.engineering_runner run-one`, consumer profile, one developer attempt,
one reviewer pass, no automatic retry, on top of this milestone's own commit
(`base_commit 274d1246a691672600c15b9d72faf8dade7a545c`). Result: **developer
accepted, reviewer verdict `pass` (attested pass, deterministic pass, zero
findings), gate 11/11 required suites green with zero blockers, final state
`ready_for_approval`.** The reviewer's own evidence pointers were exact file
and line citations (`company/engineering/lifecycle.py:197`, `:345`, `:214`,
`:449`) for every one of the five acceptance criteria.

---

## 11. Result

| | V1 (`reviews-completed`) | V2 (`blocked-count`) | change |
|---|---:|---:|---:|
| model | sonnet (standard tier) | sonnet (standard tier) | same |
| developer turns | 27 | 26 | -3.7% |
| developer output units | 8,184 | 6,033 | -26.3% |
| **developer cache-read units** | **990,324** | **783,941** | **-20.84%** |
| developer cache-creation units | 61,384 | 41,926 | -31.7% |
| developer cost | $1.083562 | $0.804993 | -25.7% |
| developer wall time | 209.6 s | 151.96 s | -27.5% |
| developer instruction chars | (not recorded by V1) | 9,807 | - |
| execution-context chars (developer) | n/a - no such artifact | 3,330 | - |
| repo file reads (total / unique / repeated) | UNAVAILABLE | 12 / 2 / 10 | now observable |
| repo searches / repeated | UNAVAILABLE | 2 / 0 | now observable |
| files read but never changed | UNAVAILABLE | **0** | now observable |
| files changed | 2 | 2 | same |
| reviewer turns | 9 | 5 | -44.4% |
| reviewer cache-read units | 158,520 | 47,922 | -69.8% |
| reviewer cost | ~$0.374 | $0.213690 | -42.9% |
| reviewer instruction chars | (not recorded by V1) | 10,158 | - |
| execution-context chars (reviewer) | n/a | 1,729 | - |
| total job cost | ~$1.457 | $1.018683 | -30.1% |
| review | pass | pass, 0 findings | - |
| gate | READY 11/11 | READY 11/11 | - |

**Threshold: developer `cache_read_units` ≤ 792,259. Result: 783,941. PASS**,
by 8,318 units (about 1.05% under the ceiling; the underlying reduction
against V1 is 20.84%, just clearing the declared 20% bar). Reported as
measured, at face value, not rounded up or reframed - this is a narrow pass,
n=1, and is described as one.

**What the new telemetry actually shows, for the first time.** Of the
developer session's 12 `Read` calls, only **2 were of distinct files** -
exactly the two files the work order authorized and the developer changed.
**Zero files were read that were not changed.** Ten of the twelve reads were
repeats of the *same* file, `tests/test_company_engineering_execution.py`,
interleaved with four `Edit` calls against it - a read-edit-reread pattern on
one already-identified file, not a discovery loop across the repository. This
is a materially different profile from the grep-and-read exploration this
milestone exists to reduce, and it is only visible because §1's telemetry now
exists at all: V1 could not have distinguished "the session re-read one known
file ten times" from "the session searched the whole repository ten times" -
both were simply UNAVAILABLE.

---

## 12. Interpreting the result honestly

**Attribution, separated where the evidence allows it:**

- **Compiled execution context (§3):** the developer session never issued a
  single `Grep`/`Glob` against the codebase to *find* `EngineeringJob` or its
  test file - both were named, with exact symbol spans, in the briefing. The
  two `Grep` calls it did make were narrow, targeted checks
  (`developer_attempts|reviews_completed|blocked_attempts` and a search for an
  existing test naming convention) *inside* files it already knew mattered,
  not repository-wide discovery. This is the mechanism most directly
  supported by the event trace: discovery cost is close to zero in this run.
- **Reverse production-dependency index (§2):** the briefing named
  `company/dashboard/builder.py` as a production dependent of
  `lifecycle.py` before the session asked. Whether this changed developer
  behavior cannot be separated from the rest of the bundle in a single run -
  the developer's own `unresolved_risks` do not mention checking it - but it
  is exactly the piece of information V1 claimed to provide and did not.
- **Reviewer context (§5):** the largest single relative improvement
  (-69.8% cache-read, -44.4% turns) and the easiest to attribute: the reviewer
  went from a broad, `authorized_paths`-scoped free-text query to a two-file,
  diff-scoped neighborhood with no source excerpts. This is a scope change,
  not a request for the model to work faster, and the effect size matches the
  scope reduction reasonably well.
- **Briefing-size effect (§4):** near-neutral, as §4 already reported before
  this job ran (developer instructions actually *grew* slightly in the earlier
  synthetic measurement). Not a plausible explanation for the cache-read
  reduction either way.
- **Natural workload variance:** real and not dismissed. This is n=1, on a
  task chosen to be comparable but not identical to V1's `reviews-completed`
  job (a boolean-shaped counter on the same dataclass, arguably marginally
  simpler than a second int already derived from the same transitions list).
  The 20.84% reduction clears the declared 20% bar by a margin (1.05% of the
  ceiling) that is well within the range V1 itself already documented as
  variance between two runs of the *same* task on the *same* model
  ($1.27 vs $1.74, a 37% spread, per
  `docs/company_os_consumer_resource_mode.md`). **This threshold clearance
  should not be read as proof the mechanism reliably delivers >20%**; it is
  the one measurement this milestone committed to taking, taken once, honestly
  reported.
- **Model-tier lever:** unchanged from V1 and Consumer V1's own finding - both
  sessions ran the same tier (standard/sonnet) as their comparators, so tier
  selection contributes nothing to the delta measured here.

**The gap the result itself names for next time:** ten of twelve reads were
repeats of one file already known to be relevant. Neither the repo map nor
the execution context can address that - it is a session re-reading a file it
is actively editing, most plausibly triggered by the coding CLI's own
edit-verification behavior rather than by anything this milestone's briefing
said. Recorded as an open question, not solved here: a future pass could
check whether the CLI offers a way to reduce redundant post-edit reads, but
that is a CLI-behavior question, not a repository-navigation one, and it is
out of this milestone's stated scope.

---

## 13. Autonomous engineering status

Unchanged by this milestone, and this milestone does not change it on its
own. The controlling record remains
`docs/company_os_consumer_resource_mode.md`: **autonomous Company OS
engineering is PAUSED**, pending a CEO/operator decision to resume it -
`docs/company_os_repository_exploration_efficiency.md` (V1) already named
itself the precondition, not the lifting, of that pause, and this V2 pass is
the same kind of evidence, not a different kind of authorization. The current
acceptable operating stance stays **controlled routine dogfood only**: routine
STANDARD-tier jobs, consumer profile, one developer attempt, one reviewer,
CEO/operator approval, no merge/deploy/publish without explicit approval -
which is exactly the shape of the one job this milestone ran.

---

## FINAL REPORT

**baseline branch:** `company-os-v1-repository-exploration-efficiency` @ `9b5f2242e2dfbcbf06c68ea678d8e9cbd8046df4`
**baseline SHA:** `9b5f2242e2dfbcbf06c68ea678d8e9cbd8046df4`
**new branch:** `company-os-v1-repository-exploration-efficiency-v2`
**new SHA:** `274d1246a691672600c15b9d72faf8dade7a545c`
**pushed:** yes (this milestone branch, after deterministic verification and the one matched job, per the brief)
**merged:** no

**CLI exploration telemetry capability:** present.
**streaming supported:** yes - `--output-format stream-json`, probed live against the installed CLI (2.1.70), not assumed from documentation. Requires `--verbose` under `--print` (undocumented finding).
**telemetry reliability:** POST_SESSION_OBSERVABLE - read only after the session ends, from the CLI's own transcript; never claimed as a live/mid-session limit.

**V1 repo-map limitations found:** no symbol line spans (module-level granularity only); a claimed-but-missing reverse *production* dependency index (only a test reverse index existed).
**V2 repo-map changes:** `ModuleMap.symbols` (qualified name, kind, start/end line) for every class, function and method; `RepoMap.production_dependents`; bounded `neighborhood()` query combining both with tests and entry points.
**symbol indexing:** present, tested (8 new cases), used live in the matched job (the briefing named `EngineeringJob#188-454`, `JobTransition#160-184`, etc., with excerpts).
**reverse dependencies:** present, tested, used live (`company/dashboard/builder.py` named as a production dependent of `lifecycle.py`).
**test indexing:** unchanged from V1 (already correct); reused by the new neighborhood query.

**execution context mechanism:** `ExecutionContextBundle` - ranked/given files, their symbols+spans, production dependents, covering tests, entry points, and (for the top developer file) small source excerpts; renders to one canonical "Execution context" section in both developer and reviewer briefings, replacing V1's free-text repo-map section and (developer only) a near-duplicate whole-packet JSON dump.
**execution context max size:** 6,000 characters (`MAX_BUNDLE_CHARS`), hard-truncated, chosen and documented before the matched job.
**actual matched-job context size:** 3,330 chars (developer), 1,729 chars (reviewer) - both comfortably under budget, neither truncated.
**developer instruction chars:** 9,807 (real matched job).
**reviewer instruction chars:** 10,158 (real matched job).

**exploration metrics available:** yes, POST_SESSION_OBSERVABLE, for the `claude_code` backend when its transcript parses as `stream-json`.
**file reads:** 12 total (developer), 3 total (reviewer).
**unique file reads:** 2 (developer), 2 (reviewer).
**repeated reads:** 10 (developer, all of one file), 1 (reviewer).
**searches:** 2 grep (developer), 0 (reviewer).
**repeated searches:** 0 (developer), 0 (reviewer).
**files read but not changed:** 0 (developer) - both files read were both files changed.

**external tools:**
**adopted:** none new; the internal `ast`-based repo map, extended.
**rejected:** none re-evaluated this round (ast-grep's V1 rejection stands, unrevisited).
**deferred:** Graphify, Serena, RTK, ast-grep (beyond V1's rejection), Ponytail package - none needed this round; the one gap found (the free-text query's real-scale ranking defect, §3) was fixed inside the existing mechanism, not used as grounds to adopt anything external.

**V1 matched result:** developer 27 turns, 8,184 output units, 990,324 cache-read units, 61,384 cache-creation units, $1.083562, 2 files changed, 209.6 s; reviewer 9 turns, 158,520 cache-read, ~$0.374; total ~$1.457.
**V2 matched result:** developer 26 turns, 6,033 output units, **783,941 cache-read units**, 41,926 cache-creation units, $0.804993, 2 files changed, 151.96 s; reviewer 5 turns, 47,922 cache-read, $0.213690; total $1.018683.
**change:** developer cache-read -20.84%, turns -3.7%, output -26.3%, cost -25.7%, wall time -27.5%; reviewer cache-read -69.8%, turns -44.4%, cost -42.9%; total job cost -30.1%.

**threshold:** developer `cache_read_units` ≤ 792,259 (20% reduction from V1's 990,324), declared before the job ran.
**threshold met:** **yes - 783,941, a narrow pass** (8,318 units / 1.05% under the ceiling). Reported as narrow because it is narrow; n=1 variance documented in §12 is real and larger than this margin.

**quality:**
**tests:** developer's own required suite (`tests/test_company_engineering_execution.py`) 115/115 passed; full deterministic suite at the implementation commit 4,600 passed / 6 failed (known fingerprint) / 337 skipped, zero regressions after one caught-and-fixed defect (§10).
**review:** verdict `pass` (attested pass, deterministic pass), 0 findings, 5/5 acceptance criteria satisfied with exact file:line evidence.
**gate:** READY, 11/11 required suites green, 0 blockers.

**consumer viability:** SUPPORTED. One provider, one session per stage, one developer attempt, one reviewer pass, no automatic retry, total job cost $1.018683 - inside the consumer profile's $3.00 session ceiling with room to spare, $0.439 cheaper than V1's own comparable job.

**recommendation:** keep the internal mechanism. The one real gap found this round (the free-text query's ranking defect at real repository scale, §3) was fixed inside the existing `ast`-based approach without new infrastructure, and the matched job's own telemetry (§11-12) shows the remaining cache-read cost concentrated in repeated reads of a single already-identified file - a CLI-behavior question, not a repository-navigation gap an external indexing tool would close. No evidence surfaced this round that Graphify, Serena, RTK or ast-grep would move that number. Investigate the repeated-read pattern (§12) before reaching for a new tool.

**verdict: REPOSITORY EXPLORATION EFFICIENCY V2: PASS** (narrow - see §12). Every §10 acceptance condition met: STANDARD tier resolved and used (after catching and correcting a real specialist-domain misclassification in this milestone's own request wording), deterministic suite clean at the known fingerprint, tests PASS, review PASS, gate READY, no automatic retry occurred, telemetry trustworthy (`unreliable_metrics: []` on both sessions), and repository exploration - measured as the developer attempt's `cache_read_units`, the threshold declared in §9 before this job ran - came in 20.84% below V1's matched figure against a 20% bar. The four gaps V1 named in its own limitations section (§0) are each addressed with evidence, not merely claimed fixed.

**This does not authorize autonomous Company OS engineering to resume.** See §13. The evidence continues to accumulate in the direction the pause named; the decision to act on it remains the CEO's/operator's, exactly as V1's own document already said of itself.

---
