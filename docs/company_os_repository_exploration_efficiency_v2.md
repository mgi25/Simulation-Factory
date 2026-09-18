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
