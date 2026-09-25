# P6C-R1 - experience advisory fail-safe correction

An append-only correction record for the one blocking finding of the
independent P6C review. It does not amend that review: its verdict,
`CHANGES_REQUIRED`, is historical and stands. Whether this correction
resolves B1 is for a fresh independent reviewer to decide
(see [Next action](#next-action)).

| | |
|---|---|
| starting point | `e4eb260278be5f5bec2d925ad05315afb0969634` (P6C evidence tip; implementation frozen at `16d5a39`) |
| `origin/main` at start | `4fd5fafa92767a83afb966c9a2210fdb016fc28d` |
| correction branch | `p6c-experience-failsafe-fix-v1` |
| correction commit | `0d697d87e87e1eb4e98585c1f9a4e1a9c4a90238` |
| `p6c-experience-store-v1` | not modified (still `e4eb260` on origin) |
| merged | no |
| paid benchmarks | none re-run |

Scope is B1 only. The P6C residuals (R1-R6 in the P6C README) and the
review's nonblocking notes are untouched, as is all carried-forward backlog.

## B1, as the review reported it

> A malformed experience advisory can escape the runner's advisory error
> handling and crash the runner.

`EngineeringRunner._experience` caught exactly `(ExperienceAdviceRejected,
AttributeError, TypeError, ValueError)` around parse and revalidation. The
review reproduced two advisories that raise something else:

- **A.** A precedent whose `why` is an object. `parse` computed
  `(item.get("why") or ())[:4]`; slicing a dict raises **KeyError**, not
  TypeError, because slice objects are hashable since Python 3.12.
- **B.** Nesting deep inside an otherwise ignored field (`measurement`). The
  recursive authority-key scan `_authority_keys` raises **RecursionError**.

Around its stage loop `run_one` catches only `AuthorityViolation`,
`BackendFailure`, `RunnerError` and `OSError`; `watch` calls `run_one`
unguarded, and `main` catches only `ConfigurationError`, `OSError`,
`RunnerError` and `KeyboardInterrupt`. So both escaped the process. The
developer brief had already moved the job to `developing`, which is
actionable and resumes through `_developer_stage` and `_experience`, so a
restarted runner met the same advisory again.

## Reproduction

The regression tests below were written first and run against the unfixed
production code: the final test files over `tools/` at `e4eb260`, in a
detached worktree. Result: **26 failed, 4 passed**. Full output:
[`b1-reproduction-before-fix.txt`](b1-reproduction-before-fix.txt).

Every runner-level case goes through the real path,
`run_one -> _stage -> _developer_stage -> _experience`, with the scripted
control plane handing the runner the payload exactly as
`ControlPlane.experience_advice` would.

| advisory | behaviour before the fix |
|---|---|
| precedent `why` = `{"shares": ...}` (case A) | `KeyError: slice(None, 4, None)` escapes `run_one` (`experience.py:244`, reached from `runner.py:1578`) |
| `measurement` nested `getrecursionlimit() + 500` = 1500 deep (case B) | `RecursionError` escapes `run_one` (`_authority_keys`, `experience.py:166/169`, reached from `parse` at `:225`) |
| unforeseen `RuntimeError` raised in `parse` | escapes `run_one` |
| unforeseen `RuntimeError` raised in `revalidate` | escapes `run_one` |
| `OSError` writing `experience-advice.json` | reaches `run_one`'s `(RunnerError, OSError)` handler: **run ends `failed`** |
| `OSError` writing `experience.json` | same: **run ends `failed`** |
| precedent `why` = a bare string | accepted; one character per reason, rendered into the prompt |
| precedent `why` holding an object | accepted; the object `str()`-ed into the prompt |
| warning `lines` = a mapping | accepted; the mapping's keys rendered as warning lines |
| warning `lines` holding an array | accepted; the array `str()`-ed into the prompt |

Case B is not a payload only a test could build. On this machine (CPython
3.13.0, recursion limit 1000), probing both nested lists and nested objects
from the top of the stack:

| depth (sampled) | courier `json.loads` | `write_json` (`indent=2`) | `_authority_keys` |
|---|---|---|---|
| 200, 300, 400, 500, 700, 900 | ok | ok | ok |
| 1000, 1200, 1500, 2000 | ok | ok | **RecursionError** |
| every 50 from 2050 to 2950 | ok | ok | (not sampled; deeper than 1000) |
| 3000 | RecursionError | RecursionError | RecursionError |

So a payload nested anywhere from about 1000 to about 2999 deep is decoded
and delivered by the courier, then crashes the parse. Inside a running
runner the stack is already deeper than in this probe, so the scan fails
somewhat sooner. At 3000 the courier's own `json.loads` fails, and that
call was already inside a broad `except Exception`. The test asserts
`json.loads(json.dumps(payload)) == payload` for its 1500-deep payload,
which is what the courier's decoder does to it.

## Root cause

Two defects, which compounded:

1. **The boundary was a hand-kept list of expected exceptions.** An optional
   step's failure policy depended on predicting every exception type a
   parser, a revalidation and two writes can raise. KeyError (a
   `LookupError`) and RecursionError (a `RuntimeError`) were not predicted.
   Neither was `OSError` from the advisory write, which sat outside the
   `try` entirely.
2. **`parse` read producer fields without checking their shape.** It sliced
   and iterated `why` and `lines` as whatever they happened to be. That is
   the source of case A, and of the silent stringification rows in the table
   above.

## The fix

Two production files, two functions.

### Strict item shape (`tools/engineering_runner/experience.py`)

A new helper, `_strings(item, key, where)`, validates a producer-declared
list of strings **before** anything iterates or slices it:

- absent: reads as empty, as every optional field in the reader already did;
- present: it must be a `list`, and every member must be a `str`;
- otherwise it raises `ExperienceAdviceRejected`, naming the field and the
  offending type, never the value:
  `precedents[0].why must be a list of strings, not dict`, or
  `warnings[0].lines[0] must be a string, not list`.

`parse` now reads `precedent.why` and `warning.lines` only through it. So a
mapping (empty or not), a bare string, an integer, `null`, a nested object,
a nested array or a non-string member is refused with the whole payload.
Nothing is coerced into prose.

The producer's existing bounds are unchanged: `why` is still read to at
most four reasons, warning lines are still refused beyond
`MAX_WARNING_LINES = 4`, and the 16000-character payload ceiling still
applies. What the producer emits
(`company/experience/advice.py`: `"why": list(c.why())`, `"lines": lines`,
always lists of strings, never `null`) all passes. No fixture anywhere in
`tests/` used another shape.

### Runner fail-safe (`tools/engineering_runner/runner.py`)

`EngineeringRunner._experience` now wraps the payload write, `parse`,
`revalidate`, the summary and the record write in a single `try ... except
Exception`. It returns `(None, {"enabled": True, "available": False,
"rejected": _brief_reason(exc)})`: the existing bounded field, one line and
at most 400 characters, with no traceback and no payload. The control-plane
call keeps its own boundary and its own `reason` field, unchanged.

`BaseException` is deliberately **not** caught. `KeyboardInterrupt`,
`SystemExit` and `GeneratorExit` still stop the process, and a test pins it
(`test_process_level_control_is_never_absorbed_as_missing_advice`, which uses
a `BaseException` subclass so it cannot stop pytest itself).

The import of `ExperienceAdviceRejected` into `runner.py` became unused and
was removed. `experience.py` still defines and exports it.

### Persistence failure (Phase 4): yes, it could stop the job; fixed

`write_json(stage_dir / "experience-advice.json", payload)` ran **before**
the `try`. An `OSError` there (a full disk, a permission error, a path
problem) reached `run_one`'s `except (RunnerError, OSError)` and ended the
run as `failed`. The reproduction shows this for both experience artifacts.
Both writes are now inside the boundary. Recording `experience.json` is
inside it too: if the runner cannot record which advice it used, it uses
none, so the evidence always matches what the session was given. A write
failure on the developer stage's own artifacts (`resources.json`,
`execution-context.json`, `instructions.md`) is unchanged and still stops
the run. Runner artifact storage was not redesigned.

### Deep nesting (Phase 5): absorbed at the boundary; the scan is unchanged

The minimum outcome holds: a 1500-deep advisory gives `advice = None`,
`rejected = "RecursionError: maximum recursion depth exceeded"`, and a
completed job.

Making the parser itself reject excessive nesting, with a bounded iterative
walk, was evaluated and not adopted:

- The producer declares **no** nesting bound. A depth ceiling chosen by the
  runner would be a new producer contract, which is a design change, not
  hardening. The reader's rule is to refuse what the producer's own
  declarations exclude.
- It would mean rewriting `_authority_keys`, the authority-vocabulary scan.
  Leaving it byte-identical is the stronger "no authority logic changed"
  claim.
- The boundary already makes the outcome independent of where the recursion
  limit falls. Nothing outside `_experience` walks the raw payload: `parse`
  returns a typed, frozen `ExperienceAdvice`, and the raw payload is dropped.

After the boundary, the developer stage still calls `experience.primary()`
and `experience.render()`. Both operate on already-validated, typed tuples
of strings, and `render()` has already run once inside the boundary (via
`summary()`), deterministically, over the same frozen data.

## Tests added

In `tests/test_external_engineering_runner.py` (runner level, through
`run_one`) and `tests/test_engineering_runner_execution_context.py` (parse
level). The numbers are the brief's Phase 6 list.

| # | brief item | test |
|---|---|---|
| 1 | dict-valued precedent `why` | `test_a_precedent_why_that_is_not_a_list_of_strings_is_refused[mapping, empty-mapping]`; runner: `test_a_malformed_advisory_runs_the_job_exactly_as_without_advice[why_is_a_mapping]` |
| 2 | dict-valued warning `lines` | `test_warning_lines_that_are_not_a_list_of_strings_are_refused[mapping, empty-mapping]`; runner: `[lines_is_a_mapping]` |
| 3 | scalar string for `why` | `...why...[bare-string]` (also `integer`, `null`); runner: `[why_is_a_string]` |
| 4 | nested non-string member in `why` | `...why...[nested-object, nested-array, non-string-member]`; runner: `[why_holds_an_object]` |
| 5 | nested non-string member in `lines` | `...lines...[nested-object, nested-array, non-string-member]`; runner: `[lines_holds_an_array]` |
| 6 | deep nesting | runner: `[nested_past_the_recursion_limit]` (1500 deep, courier-decodable) |
| 7 | unexpected parser exception absorbed | `test_an_unforeseen_parser_or_revalidation_exception_is_absorbed[parse]` |
| 8 | unexpected revalidation exception absorbed | `test_an_unforeseen_parser_or_revalidation_exception_is_absorbed[revalidate]` |
| 9 | malformed = no-advice behaviour | every runner-level test above, via `_runs_as_without_advice` |
| 10 | `--no-experience-advice` unchanged | `test_the_no_experience_advice_flag_still_switches_advice_off` (CLI flag to config), `test_switched_off_experience_never_reads_even_a_malformed_advisory`, and the existing `test_experience_advice_can_be_switched_off` |
| - | persistence failure (Phase 4) | `test_a_failed_experience_write_is_no_advice_not_a_failed_run[experience-advice.json, experience.json]` |
| - | `BaseException` not absorbed | `test_process_level_control_is_never_absorbed_as_missing_advice` |
| - | existing bounds kept | `test_well_formed_why_and_lines_keep_their_existing_bounds` |

**No-advice equivalence (item 9) is asserted whole, not sampled.** A
module-scoped fixture runs the same job in a second, identical repository
with `experience_advice=False`. `_runs_as_without_advice` then requires the
run to complete to `ready_for_approval`, and requires the experience record
to be `available: false` with a bounded `rejected` reason and no
`experience.json`. On top of that it requires the whole developer stage to
be **equal** to the no-advice run:

- the developer `SessionRequest` (role, model, tools, disallowed tools,
  read-only flag, timeout, cost ceiling);
- the full instructions text;
- the full `execution-context.json`;
- `resources.json`, minus only the `experience` record (the one thing meant
  to differ) and the base diagnostic's wall-clock `duration_s`;
- `authority.json`;
- the run outcome, final state and stage list.

Before comparing, it normalises only the temporary directory and the
fixture's base-commit id, which a throwaway probe of two identical no-advice
runs showed to be the only other differences. The brief's explicit checks
are also asserted by name, for readability: no experience file in the
primary ranking, no prior-experience block, an unchanged authority envelope
and required tests, the same developer model, and the same adaptive-routing
decision.

## No architecture or authority change (Phase 7)

`git diff-tree -r --name-status e4eb260 0d697d8` names four files:

```
M  tests/test_engineering_runner_execution_context.py
M  tests/test_external_engineering_runner.py
M  tools/engineering_runner/experience.py
M  tools/engineering_runner/runner.py
```

The rest of the tree is identical by object id at `e4eb260` and at the
correction:

| path | object id | covers |
|---|---|---|
| `company/` | `84486d6da30b` | experience episode schema, identity, capture, staleness, retrieval, abstention, replay; KnowledgeStore; required-suite resolver; risk and reasoning compatibility; P6B dependency graph; integration gate |
| `knowledge/` | `ac1b06327484` | capsule seeds and contracts |
| `ai_platform/`, `intelligence/` | `ad9aa0eb3ad4`, `50db54864d3c` | - |
| `tools/engineering_runner/authorization.py` | `2692cf953d00` | the authority envelope, read and write checks |
| `tools/engineering_runner/controlplane.py` | `ca28378d76de` | the advisory courier |
| `tools/engineering_runner/briefs.py`, `execution_context.py` | `7157123439bb`, `c8e9f2883ab2` | prompt and primary-file ranking |
| `tools/engineering_runner/config.py`, `__main__.py` | `01afb8ce2b29`, `0d9b0dd38eac` | `--no-experience-advice` |
| `tests/test_company_experience_store.py`, `..._retrieval.py` | `b9d8beb5c1ca`, `6d132a55abda` | the P6C producer suites |
| `docs/evidence/.../replay_harness.py` | `4e20d587f468` | the replay, which imports only `company.experience` and `company.integration`, so its fingerprint cannot move |

Inside the two changed production files, an AST comparison of every
top-level and class-level definition between the revisions finds exactly:

- `experience.py`: 29 definitions identical. The ones that differ are the
  module docstring, `ExperienceAdvice.parse`, and the new `_strings`.
  `_authority_keys`, `AUTHORITY_KEYS`, `ADVICE_KEYS`, `fingerprint`,
  `_items`, `_line`, `revalidate`, `RevalidatedAdvice` and every `MAX_*`
  bound are byte-identical.
- `runner.py`: 57 definitions identical. The ones that differ are the import
  block (one unused name removed) and `EngineeringRunner._experience`.
  `run_one`, `_developer_stage` and `_adaptive_developer_model` are
  byte-identical.

The tests pinning the runner's restated vocabulary to the producer's
(`tests/test_company_external_engineering_runner.py`) pass unchanged.

## Focused validation (Phase 8)

CPython 3.13.0, run from a worktree in the local temp directory (not
OneDrive):

| suites | result |
|---|---|
| `tests/test_external_engineering_runner.py` | **203 passed** (190 before + 13 new) |
| `tests/test_engineering_runner_execution_context.py`, `tests/test_company_external_engineering_runner.py`, `tests/test_company_experience_store.py`, `tests/test_company_experience_retrieval.py` | **281 passed** |
| `tests/test_company_dependency_graph.py`, `tests/test_company_gate_suite_requirements.py`, `tests/test_company_integration_gate.py`, `tests/test_company_read_authority.py` | **223 passed** |
| the 30 B1 tests alone, before the fix | **26 failed, 4 passed** ([`b1-reproduction-before-fix.txt`](b1-reproduction-before-fix.txt)) |
| the 30 B1 tests alone, at the correction | **30 passed** ([`b1-tests-after-fix.txt`](b1-tests-after-fix.txt)) |

The four that pass before the fix are the ones that pin unchanged
behaviour: `BaseException` is not absorbed, the switched-off path is never
read, the CLI flag still maps to the config, and the existing bounds still
hold.

## Required suites (Phase 9)

Re-derived at the correction commit with
`python -m company.integration required-suites --repo-root . --json`
([`required-suites.json`](required-suites.json)), not copied:

| | P6C (`e4eb260`) | P6C-R1 (`0d697d8`) |
|---|---|---|
| suites | 47 | **47** |
| fingerprint | `f5de72a66d79bb83` | **`f5de72a66d79bb83`** |
| unresolved | `[]` | `[]` |
| undeclared Company OS suites | `[]` | `[]` |

The derived payload is equal to P6C's `required-suites.json` field for field.
That is expected: the set is derived from capsule contracts and the observed
dependency graph, and the correction changes neither a capsule nor an import
edge.

All 47 ran, inside the full-suite run below
([`required-suite-results-0d697d8.json`](required-suite-results-0d697d8.json)):
**3261 passed, 3 failed, 1 skipped**. The three failures are the known
research branch-scope guards, one each in `test_company_os_research.py`,
`test_company_os_research_batches.py` and
`test_company_os_research_ingestion.py`:
`test_this_branch_changed_no_race_fight_or_v30_code`. Each asserts that
`git diff --name-only origin/main...HEAD` touches no production root, and
`tools/` is one; P6C already touched `tools/`, so they were red on the P6C
branch for the same reason. They are branch-red, not hidden. With
`origin/main` modelled at the correction they pass (see the end of the next
section); that is a model, not integration proof.

## Full regression (Phase 10)

The whole suite ran at the correction, then at `e4eb260`, on the same machine
in the same session, in three chunks that cover all 168 `tests/test_*.py`
files exactly once ([`full-suite-run.txt`](full-suite-run.txt)):

| | `e4eb260` (baseline) | `0d697d8` (correction) |
|---|---|---|
| failed | 21 | **21** |
| passed | 7101 | **7131** |
| skipped | 441 | **441** |
| errors | 0 | **0** |
| test cases | 7563 | **7593** |

- **Failing node ids are identical at both revisions**
  ([`full-suite-failures-e4eb260.txt`](full-suite-failures-e4eb260.txt),
  [`full-suite-failures-0d697d8.txt`](full-suite-failures-0d697d8.txt)):
  nothing newly fails, and nothing that failed now passes or skips.
- **The +30 test cases are the 30 new tests**, and all pass: 13 in the runner
  suite (190 to 203) and 17 in `test_engineering_runner_execution_context.py`.
  The skip count is unchanged.
- **Against `main` (`4fd5faf`)**: the 21 are exactly the 18 node ids of
  main's recorded baseline (`../baseline-failures-main.txt`: 12 stale race2
  branch-scope guards, 5 sloped-world tests that need gitignored `output/`
  files, and 1 neon/Godot test), plus the 3 research branch-scope guards.
  None of main's 18 is missing.
- **Against the P6C record**: the independent review measured 21 failed /
  7101 passed / 441 skipped at `16d5a39`, which this baseline reproduces
  exactly. The P6C authoring list (`../full-suite-failures-16d5a39.txt`) has
  one more, the runner test
  `test_the_review_is_adjudicated_against_the_tree_the_work_happened_in`,
  which P6C recorded as environmental. It passed in both runs here, as it did
  twice in the review.

Classification: **zero newly introduced failures.** The only failures not
on main's list are the three research branch-scope guards. In a
fast-forward model (a `--shared` clone whose own `origin/main` was set to
the correction; the shared repository's refs were not touched), those three
files give 321 passed. That is a modelled result, not integration evidence.

## Files

| file | what |
|---|---|
| `README.md` | this record |
| `b1-reproduction-before-fix.txt` | the final B1 tests against unfixed `tools/` (`e4eb260`) |
| `b1-tests-after-fix.txt` | the same tests at the correction commit |
| `required-suites.json` | the required-suite set, re-derived at the correction commit |
| `required-suite-results-0d697d8.json`, `required-suite-results-e4eb260.json` | per-suite results for the 47, from each full run's JUnit XML |
| `full-suite-failures-0d697d8.txt` | full-suite failing node ids at the correction commit |
| `full-suite-failures-e4eb260.txt` | the same, same machine, same session, at `e4eb260` |
| `full-suite-run.txt` | chunk summary lines for both runs, and the modelled guard run |

## Next action

A **fresh** independent reviewer, not this authoring session, reviews only:

1. the B1 reproduction above;
2. the correction diff (`e4eb260..0d697d8`, two production files and
   two test files);
3. that a malformed advisory now always degrades to no advice;
4. that no architecture or authority behaviour changed.

No merge until that review returns. No further optimisation phase.
