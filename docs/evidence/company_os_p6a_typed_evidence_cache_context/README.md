# P6A — typed evidence, gate evidence completeness, cache-stable context

Branch `p6a-typed-evidence-cache-context-v1`, from `origin/main` at
`6cf59c95843c05c552332c81687c8f55df1f2331`.

Two commits, deliberately separate:

| Commit | What |
|---|---|
| baseline | two stale `owns_paths` test expectations corrected |
| P6A | the feature work described below |

---

## 1. Baseline repair

`knowledge/company_os/capsules/seeds/company-research-intelligence.json` was
widened from `("intelligence/research",)` to
`("intelligence/__init__.py", "intelligence/research")` by the reviewed work
order in `23b4189`. That commit updated `tests/test_company_os_capsules.py` and
left two other call sites pinned to the old tuple, so both have been red on
`main` since the P5 integration.

Verified this is the whole defect before touching anything:

* the seed value is correct — `company-research-intelligence` is the **only**
  claimant of `intelligence/__init__.py`, and `index.integrity(repo_root)`
  returns `()`;
* the assertion that fails is the `owns_paths` tuple comparison alone. The
  capsule *budget* assertion in the same two tests passes, despite both tests
  being named after it — see the P5 stop-condition note;
* `23b4189` shows the intent explicitly, in a comment it added to the third
  call site.

Fix: two expectations updated to the canonical value. 389 passed across
`test_company_os_research_ingestion`, `test_company_os_research_batches`,
`test_company_os_capsules` and `test_company_os_research`.

---

## 2. Gate evidence completeness

### The defect

`company.integration.suites.REQUIRED_SUITES` was a hand-written list of eleven
canonical subsystem suites, and it was the *whole* answer to "what evidence
does the gate need". A capsule could declare a suite in `capsule.tests` and the
gate would never ask about it. On 2026-09-24 a candidate reached READY while
two tests declared by the active `company-research-intelligence` capsule were
failing, because neither name was in the list.

Appending the two names would have closed that instance and left the hole open.

### The solution

The required set is **derived on every run** by
`resolve_required_suites(index, changed_paths=...)`, from three origins:

| Origin | Question it answers |
|---|---|
| `canonical` | which subsystems do the gate's own checks depend on? A floor. |
| `capsule_contract` | which suites does the Company OS contract itself name? Every `tests/` entry of every capsule **in force** — `active` *or* `needs_revalidation`. |
| `change_scope` | which suites does *this* change reach? Capsules whose owned paths it touches (whatever their status), and Company OS test files it edits. |

On this checkout that is **32 suites**, not 11.

`needs_revalidation` counts, and that is not an oversight — it is
[B1](#what-the-independent-review-found) below.

Five properties, each with a test:

1. **Scope only widens.** There is no input that makes the gate ask for less.
   A gate that gets cheaper when you describe the change less fully is a gate
   with a dial on it. `test_change_scope_never_shrinks_the_set`.
2. **An underivable set is not an empty set.** `RequiredSuites.unresolved`
   names every reason the set could not be determined, and
   `health.required_suites_pass` answers `unknown` while it is non-empty. Four
   things put an entry there: an index that would not load, an **empty** one,
   a **structurally incomplete** one, and a capsule naming something in
   `tests` that is not a suite path.
3. **Supplied red evidence is never discarded.** A result the caller marked
   `company_os: true` and reported failing blocks even when no contract named
   that suite.
4. **Present and green is not the same as observed.** A required result with
   `selected == 0` (pytest collected nothing) or an `observed_on` in the
   future (which makes the freshness window unreachable) is treated as
   *missing*, not as a pass.
5. **The gate still runs nothing.** The resolver imports no `subprocess`, no
   `os`, no `pytest`; `test_deriving_the_set_spawns_no_process` parses the
   module and checks its import roots (a text grep finds the word
   `subprocess` in the module's own docstring explaining why it is absent).
   One filesystem read exists in the module — `undeclared_company_os_suites`,
   below — and it is reached only from the CLI, never from a check.

### Regression coverage

`tests/test_company_gate_suite_requirements.py` reproduces the P5 miss on a
**synthetic** capsule store, so the reproduction cannot rot when the real seeds
are edited:

* `test_the_p5_integration_miss_is_reproduced_and_now_blocks` — all eleven
  canonical suites green, one capsule-declared suite red → `FAIL`, `BLOCKED`,
  and the blocker names both the suite and the capsule that required it;
* `test_a_capsule_declared_suite_with_no_evidence_is_unknown_not_pass` — the
  other half: silence must not read as green.

### What the independent review found

A separate reviewer session went at this looking for exactly the failure this
work exists to prevent, and found **two reproduced ways** the gate could still
say PASS while a relevant suite was missing. Both are fixed, both have a
regression test naming the review.

**B1 — flagging a capsule for revalidation removed its suites.** The resolver
took `status is ACTIVE`, and `RecordStatus` also has `needs_revalidation`,
which `flag_capsule_for_revalidation()` sets. Reproduced: flagging
`company-executive-delegation` dropped `tests/test_company_delegation.py` from
the required set with no `unresolved` entry, and the gate then said READY.

That is the P5 defect again, reached through the lifecycle instead of a static
list — and in one respect worse than the behaviour it replaced, because the
old list could not shrink at all. The original argument ("a retired contract
is not in force") is sound for `retired` and `superseded` and **backwards** for
`needs_revalidation`: a capsule whose description of a subsystem is under
suspicion is precisely the one whose tests you still want run. `_IN_FORCE` is
now `{active, needs_revalidation}`, and `SuiteOrigin.ACTIVE_CAPSULE` was
renamed `CAPSULE_CONTRACT` because the old name had become a lie.

**B2 — a partially loaded capsule store was accepted as complete.** Only
`len(index) == 0` produced an `unresolved` entry. Reproduced: a directory
holding 1 of the 22 seeds resolved cleanly, the set fell 32 → 14, and 14 green
results gave PASS. The argument against an empty store applies with identical
force to one that lost half its files. `CapsuleIndex.integrity()` — called with
no knowledge store and no checkout, so the resolver stays pure — reports
dangling dependencies from the capsules' own declarations, and a partial store
usually has one. It now contributes an `unresolved` entry.

**"Usually" is measured, and it is not "always".** A *downward closed* subset of
the dependency graph is internally consistent by construction, so the second
review pass quantified the residual:

| case | caught |
|---|---|
| random half-copies (11 of 22 capsules) | 8/8 |
| random deletions of 2, 3 or 5 capsules | 40/40 each |
| **single-capsule stores** | 18 of 22 — `ai-platform`, `company-bootstrap-policy`, `company-validation` and `company-external-engineering-runner` still resolve cleanly |
| **single-file deletions**, before the `derived_from` change | 17 of 22; worst case dropped **six** required suites at READY |
| single-file deletions, after | still 17 of 22 — see below |

Coupling the check to unclaimed modules would take that last row to 21 of 22,
and is **deliberately not done**: `architecture.subsystem_ownership_bounded`
classifies an unclaimed module as *advisory*, and making it block here would
move a condition across the required/advisory line without the visible
`policy.py` diff `GatePolicy`'s own contract demands. It would also conflate
"this store is short" with "this repository has an unowned module", which are
different facts with different remedies.

What is done instead: `RequiredSuites.derived_from` carries the capsule ids the
set was read off, and they are **inside `fingerprint()`**. A store that has lost
a capsule is a different set identity even when every surviving declaration is
untouched, the fingerprint and the capsule count are both in the check detail,
and both archived gate reports carry them. The loss becomes a diff between two
reports rather than something a reader has to notice.

The one deletion that still slips entirely is
`company-external-engineering-runner`, which owns only `tools/engineering_runner`
— a *production* root, not one of the four Company OS roots the scan walks — and
which nothing depends on. It is named in a test
(`test_a_capsule_that_quietly_vanishes_changes_the_set_identity`) rather than
left to be rediscovered. Closing it properly needs `capsule.tests` to become a
checked claim against the real test-to-module dependency: **P6B**.

Also fixed from the same review, each with a test: a stored *elision* could
answer a cache lookup for the *whole* file (`cache_key()` now carries the
representation); the authority refusal was cleared by a stale eviction or
`invalidate()` (authority is now remembered past both); `compress()` used
`str.splitlines()`, which also splits on form feed, NEL and U+2028/9, so a file
containing any of them got line numbers no editor would agree with — and the
line range is the entire reason an elision is checkable rather than a summary.

The reviewer also confirmed clean: no stale-cache path, 45-input compression
round trip, 21 change-scope shapes all widening, `missing`/`failing`/`stale`
all receiving the derived names, and `measurements.json` reproducing byte for
byte.

### What the derivation exposed: 11 undeclared Company OS suites

Deriving the required set from the contracts immediately showed what the
contracts do not cover. Eleven `tests/test_company*.py` files on this checkout
are declared by **no capsule at all**, so nothing requires them:

```
tests/test_company_bounded_engineering_activation.py
tests/test_company_bounded_engineering_autonomy.py
tests/test_company_context_expansion.py
tests/test_company_delegation_pilot.py
tests/test_company_executable_work_planning.py
tests/test_company_executive_planning.py
tests/test_company_objective_planning.py
tests/test_company_review_separation.py
tests/test_company_runtime_integration.py
tests/test_company_session_execution.py
tests/test_company_youtube_end_to_end.py
```

This is **pre-existing** — it is a gap in the capsule contracts, not something
P6A introduced, and the old static list did not surface it either.

It is **reported, never required**. `undeclared_company_os_suites()` is called
only from `python -m company.integration required-suites`; no check uses it,
and `test_the_undeclared_list_changes_no_verdict` pins that. Inventing a
requirement from a directory listing would make the gate's verdict depend on
what happens to be on disk rather than on what a capsule says, which is the
opposite of the property this work is for. It is the only I/O in
`suites.py`.

Adopting these eleven into the right capsules is a semantic ownership
judgement of the kind `wo-capsule-ownership-semantic-review` made before. It
is not P6A's to make, and some of the candidate capsules are near the
eight-item `tests` limit.

### How a caller learns the set

```
python -m company.integration required-suites --repo-root . --json
```

Exit 0 when resolved, **exit 2 when not** — the gate's own code for "evidence
is missing". `tools/engineering_runner` asks across this command line rather
than keeping a second copy of the list, because that package may not import or
even *name* the capsule layer the set is derived from
(`test_no_module_under_tools_even_mentions_the_capsule_layer_by_name`).
`ControlPlane.required_suites` refuses an unresolved answer rather than running
the partial list, which would produce evidence that looks complete and is not.

`REQUIRED_SUITES` itself is unchanged, so the runner's pinned copy of it still
matches (`test_company_external_engineering_runner.py::...`).

---

## 3. Typed evidence records

`company/runtime/evidence_records.py`. One shape for every observation an
attempt produces, with a **re-derivable** `record_id`.

* `record_id` is a fingerprint over the record's semantic fields, so
  re-deriving the same observation gives the same id. **Re-exporting a stored
  record is therefore idempotent; re-*running* an observation is not** — the
  second run measures a new `duration_s`, the bodies differ, and `add` refuses
  and names the field. That is deliberate (accepting it would mean silently
  keeping one of two measurements), but it means excluding `duration_s` from
  `identity()` buys a stable **id**, not a free retry. A retry that re-measures
  is a new observation and takes the next `sequence`.
* `sequence` is *inside* the identity, so two genuinely distinct events that
  describe the same thing (one suite run before the fix and one after) stay two
  records instead of collapsing into one.
* `duration_s` is *outside* it. It measures the machine, not the event;
  including it would make a deterministic re-observation produce a new id every
  time, which is a UUID's failure arrived at by accident.
* `EvidenceLedger.add` refuses a second record with the same id and a different
  body. A derived id is only trustworthy while what is behind it cannot change.
* `UNKNOWN` requires a reason. An unexplained unknown is a shrug.

This addresses the recorded defect that no `ResourceUsageRecord` field is a
stable per-event id. It does **not** migrate the existing records — see
*remaining findings*.

---

## 4. Cache-stable context, read-once reuse, reversible compression

`company/runtime/context_units.py` and `company/runtime/context_cache.py`.

**Typed units.** `ContextUnit` carries `kind`, `source`, `span`, `symbol`,
`reason`, `freshness`, a `CompressedBody`, and an `authority`.

**Learning must not create authority.** `UnitAuthority` is `CONTRACT`,
`OBSERVED` or `DERIVED`. `binding` is a *property* (`authority is CONTRACT`),
never a settable flag; `recompress` carries authority through and asserts it;
`ContextCache.put` refuses to re-store a key under a different authority, and
that refusal now survives eviction and `invalidate()` — only `clear()`, which
means "this task is over", forgets it.

The honest limit, stated because the review asked for it: **no code path in
this package raises a unit's authority.** A caller that constructs a `CONTRACT`
unit directly, or reaches for `dataclasses.replace`, is asserting authority
itself, which is what construction means. The guarantee is about the package,
not about Python, and `test_a_caller_can_still_construct_a_contract_unit`
records that rather than implying otherwise.

**Identity holds nothing incidental.** `ContextUnit.identity()` is exactly
`{version, kind, source, span, symbol, content_digest, authority, compression,
elided_span}` — no clock, no absolute path, no session id, no insertion order.
`test_unit_identity_holds_no_clock_no_absolute_path_and_no_session` asserts the
field set, not a sample. (`elided_span` joined it with the cache-key fix below:
two elisions of one file made with different head and tail budgets are
different material and must not share an id.)

**Restorable compression.** `compress()` keeps a verbatim head and tail and
names the exact line range it elided, with the full SHA-256 of the original.
Lines are split on `"\n"` and nothing else, so the range is the number an
editor, `sed -n` or a pytest node id would give, and CRLF text keeps its `\r`
inside the verbatim slices.

`expand(body, canonical_text)` **verifies** rather than reconstructs: it checks
the supplied bytes against `full_digest` and returns them, raising if they have
changed. The caller must be able to fetch the source again. For a repository
file at a known commit it always can; for a synthesised repo map or a transient
blob it may not, and `CompressedBody.self_contained` is the property that says
which is which (`True` only for an uncompressed body). Compress the second kind
with a threshold that declines, or not at all.

Compression that would not actually save bytes declines and returns the whole
body. A compression that would keep no verbatim anchor is refused outright — an
elision with no anchor is a summary, and a summary cannot be checked.

**Read-once reuse.** `ContextCache` is keyed by `ContextUnit.cache_key()` —
kind, source, symbol, span *and which representation of it this is* — and
validated by content digest. Representation is in the key because a whole file
and an elision of it share a source and a digest, so keying on the bundle slot
alone let a stored elision answer a lookup for the whole file: nothing was
stale, and the caller simply got less material than it asked for, counted as a
saving. `lookup` requires the digest the caller
observed *now*; a mismatch evicts the entry and returns `STALE` with no unit
attached — `CacheLookup` refuses at construction to carry a unit on a non-hit.
`misses` and `stale_rejections` are counted separately because they mean
opposite things. The cache reads nothing itself (`test_the_cache_reads_nothing_itself`
parses its imports); read authority stays in `company/runtime/authority.py`.

---

## 5. Measurements

`docs/validation/company_os_p6a/measure_context_efficiency.py`, output in
`measurements.json` beside this file. Re-run it to reproduce.

The subject is one realistic engineering task's context — two capsule
contracts, four modules, two suites — and a fourteen-step read sequence with
the repeats a session actually makes.

| Measurement | Value |
|---|---|
| bundle chars, nothing compressed | 144,781 |
| bundle chars, compressed | 7,981 |
| reduction in chars supplied up front | 94.5% |
| reads requested / distinct sources | 14 / 7 |
| loader calls | 7 |
| reads avoided by reuse | 7 |
| reuse ratio | 0.467 — hits over *lookups*, and there is one more lookup than there are reads (the deliberate staleness probe). Not 7/14. |
| stale rejections after one source was edited | 1, no unit returned |
| prefix reuse, same units assembled in reverse | 1.000 (byte-identical) |
| prefix reuse, appending an evidence unit (sorts last) | 0.981 — the whole previous render is the prefix |
| prefix reuse, appending another module (mid-order) | **0.325** |
| prefix reuse, appending another capsule (near the top) | **0.008** |

**What the 94.49% is and is not.** It is the reduction in
characters *supplied up front*. It is not a reduction in what a session ends up
reading: an elided body is a pointer, and a session that needs the body expands
it, paying the difference then. The claim this number supports is "a bundle can
carry eight sources for 7 KB instead of
144 KB", not "the task costs
94.49% less".

**The ordering defect the measurement found.** With units sorted by
`kind:source`, the string `"evidence:"` sorts between `"capsule:"` and
`"file:"`, so appending one evidence unit to the eight-unit bundle moved
everything after it and dropped the shared prefix from 100% to **19.4%**. The
bundle now orders by a declared rank — authority (contracts first, derived
last), then kind, then key — and the same append keeps the entire previous
render as its prefix. This is the whole reason the brief said *measure* cache
stability rather than assume it; assuming it would have shipped the 19.4%.

**And the last three rows are why one append number would have been dishonest.**
The 0.981 case is the *best* case by construction: an evidence unit is the last
kind, so it lands at the end. The independent review pointed this out, so the
harness now also measures what a real task does — acquire another module
(0.325) or another capsule (0.008). **Any total order loses the prefix when a
unit lands before the end.** The declared order does not prevent that; it
chooses *which* additions are cheap, by putting the material that changes most
often at the bottom. A task that picks up a new capsule pays for the whole
bundle, and that is now on the table rather than in a footnote.

**NOT MEASURED, and not claimed anywhere:**

* provider token counts — input, output, cache creation, cache read;
* provider monetary cost;
* READY rate across real work orders;
* reviewer corrections;
* whole-task wall-clock, session count or resource totals.

All five need paid sessions. **None were run for P6A.** Characters are not
tokens, and a smaller prompt is not automatically a cheaper task. Anyone
quoting the table above outside this section is quoting a byte count as if it
were a cost.

---

## 6. Validation

### Full suite

`pytest --continue-on-collection-errors` over the whole repository at the P6A
tip: **21 failed, 6223 passed, 441 skipped, 1 collection error** in 44m47s.

Against `main`'s recorded fingerprint of **20**:

| | |
|---|---|
| the 18 inherited stale branch-scope and artefact guards | still failing, unchanged |
| the 2 `owns_paths` failures | **gone** — the baseline commit |
| 3 × `test_this_branch_changed_no_race_fight_or_v30_code` | **new, and self-healing** |

The three new ones fail *by construction* on any branch that touches `tools/`:
they diff `origin/main...HEAD` and `tools/` is a declared production root. The
assertion names exactly the two files this change edits,
`tools/engineering_runner/{controlplane,runner}.py`, and nothing else.

That self-healing is **demonstrated, not asserted**: cloning the branch and
pointing `refs/remotes/origin/main` at its own tip — which is the state a
fast-forward merge produces — makes the diff empty and all three pass.

The collection error is `tests/test_company_review_separation.py` importing
`yaml`, which is in no requirements file. Pre-existing; it fails identically on
the primary tree. Finding 8 below.

**Zero P6A-introduced failures.**

### The derived required set

All 32, run individually, in two states:

| State | Evidence | Gate | Result |
|---|---|---|---|
| on the branch, as it stands | `suites.json` — 29/32 green | `gate-report-on-branch.json` | **BLOCKED**, 1 blocker |
| post-merge simulation | `suites-post-merge.json` — 32/32 green | `gate-report-post-merge.json` | **READY**, 0 blockers |

Both reports carry `source_commit 6271e1ab`, the P6A tip.

The BLOCKED one is **the feature working**, and it is left in this directory
rather than tidied away. Its single blocker is
`health.required_suites_pass`, naming the three research guards *and the
capsule that required each* — evidence the old static list would have thrown
away, because none of those three suites is in `REQUIRED_SUITES`.

The READY one is the readiness claim, and its three `unknown` checks are all
advisory (`executive.decision_queue_preserves_source_refs`,
`health.production_failures_separated`, `workforce.capability_gaps_visible`),
each because no state directory was supplied.

Two caveats a reader of that file alone would miss, both raised by the review:
the post-merge pass on those three guards is **vacuous** — an empty diff can
never trip them — so it is evidence about the guard's construction, not about
this branch's content; and `gate-report-post-merge.json` read on its own would
look like a statement about the branch, which it is not. The independent review
diffed the two reports check by check: all 38 check ids identical, exactly one
status moved (`health.required_suites_pass`, fail → pass), so nothing else was
quietly greened by pointing `origin/main` at the tip.

### The four modified gate tests

`test_company_integration_gate.py` kept every assertion; only the fixture
changed. It built evidence from `REQUIRED_SUITES`, which is now the floor
rather than the answer, so it was supplying eleven results against a
thirty-two-suite demand and every one of those tests was exercising the
missing-evidence path by accident. It now derives the set the way the gate
does.

That does make them partly tautological, which the independent review noted.
`test_the_derived_set_never_loses_the_canonical_floor` is the compensating
control, and it is worth saying plainly that it would **not** have caught B1 —
losing one capsule's suites keeps the canonical floor intact. The tests that
catch B1 are the lifecycle ones added after the review, and they compare
against the real seed store rather than against the code's own output.

---

## 7. Remaining correctness findings — preserved, not fixed

Carried forward from P5 and untouched here, because none is required by P6A:

1. **Nested capsule co-selection conflict.** Seven capsules forbid `tools/**`;
   a work order co-selecting one with `company-external-engineering-runner`
   inherits the broader rule and forbidden wins.
2. **No named superseded lifecycle state.** `RecordStatus.SUPERSEDED` exists on
   the record model but no capsule uses it, so "this contract was replaced by
   that one" cannot be stated. P6A's derivation handles it correctly when it
   appears — a capsule that is not *in force* (`superseded` or `retired`, not
   merely non-active: `needs_revalidation` **is** in force) stops requiring its
   tests unless the change touches its paths — but nothing produces it yet.
   Related: nothing checks that a retired capsule's territory is covered by
   anything else.
3. **Runner import-guard breadth.** The recursive import guard is narrower than
   the boundary it defends.
4. **Gate reports are not archived** by default.

New, recorded here:

5. **`ResourceUsageRecord` is not migrated to `ExecutionEvidence`.** The typed
   record and its derived id exist and are tested; nothing in
   `company/efficiency/` or `tools/engineering_runner/` writes them yet. The
   stable-per-event-id defect is therefore *solvable* now, not *solved*.
6. **`ContextCache` is not wired into `build_execution_context`.** The runner
   still resolves spans afresh per bundle. The cache is exercised by its own
   suite and by the measurement harness, not by a real runner session.
7. **Eleven Company OS test files are declared by no capsule** — listed above.
   Reported by the CLI, adopted by nobody.
8. **`tests/test_company_review_separation.py` imports `yaml`, which is not in
   `requirements.txt`** and is not installed in this venv. It is the only
   importer of `yaml` in the repository. A bare `pytest` run therefore aborts
   during *collection*, so the whole-suite fingerprint cannot be taken without
   `--continue-on-collection-errors`. Pre-existing: it fails identically on the
   primary tree. Note that `health.no_new_dependency` passes, so the gate's
   dependency check does not see a test-only undeclared import.

9. **Change scope buys nothing on this checkout, and the runner does not use
   it.** All 22 seed capsules are in force, so `CHANGE_SCOPE`-via-capsule never
   fires today — the set is 32 with no scope and 32 with any `--changed-path`.
   Only an undeclared Company OS test file widens it. And
   `tools/engineering_runner` passes no `changed_paths` at all, so the runner
   path never exercises scope. It starts to matter the moment a capsule is
   flagged, superseded or retired; wiring the runner's `git diff --name-only`
   into it is P6B-sized, not P6A-sized.
10. **`CompressedBody` is restorable, not self-contained.** See §4: an elided
    unit whose canonical source can no longer be produced byte-for-byte has
    lost its middle. Safe for a repository file at a commit; not safe for a
    synthesised artefact, and nothing currently stops a caller compressing one.

### For P6B

**Exact contract/test dependency discovery.** P6A derives the required set from
what a capsule *declares*. It does not verify that the declaration is true — a
capsule can name a suite that does not exercise it, or omit one that does.
Deriving the real dependency (which tests import which modules) and comparing
it with `capsule.tests` would turn `capsule.tests` from an assertion into a
checked claim. `tools/engineering_runner/repo_map.py` already builds the
reverse test index this needs.
