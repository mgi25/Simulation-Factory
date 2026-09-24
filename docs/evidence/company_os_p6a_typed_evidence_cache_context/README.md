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
| `active_capsule` | which suites does the Company OS contract itself name? Every `tests/` entry of every `status == active` capsule. |
| `change_scope` | which suites does *this* change reach? Capsules whose owned paths it touches (whatever their status), and Company OS test files it edits. |

On this checkout that is **32 suites**, not 11.

Four properties, each with a test:

1. **Scope only widens.** There is no input that makes the gate ask for less.
   A gate that gets cheaper when you describe the change less fully is a gate
   with a dial on it. `test_change_scope_never_shrinks_the_set`.
2. **An underivable set is not an empty set.** `RequiredSuites.unresolved`
   names every reason the set could not be determined, and
   `health.required_suites_pass` answers `unknown` while it is non-empty.
   A capsule store that will not load *and an empty one* both count — in a
   Company OS checkout they are the same fact.
3. **Supplied red evidence is never discarded.** A result the caller marked
   `company_os: true` and reported failing blocks even when no contract named
   that suite.
4. **The gate still runs nothing.** The resolver imports no `subprocess`, no
   `os`, no `pytest`; `test_deriving_the_set_spawns_no_process` parses the
   module and checks its import roots (a text grep finds the word
   `subprocess` in the module's own docstring explaining why it is absent).

### Regression coverage

`tests/test_company_gate_suite_requirements.py` reproduces the P5 miss on a
**synthetic** capsule store, so the reproduction cannot rot when the real seeds
are edited:

* `test_the_p5_integration_miss_is_reproduced_and_now_blocks` — all eleven
  canonical suites green, one capsule-declared suite red → `FAIL`, `BLOCKED`,
  and the blocker names both the suite and the capsule that required it;
* `test_a_capsule_declared_suite_with_no_evidence_is_unknown_not_pass` — the
  other half: silence must not read as green.

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
  re-deriving the same observation gives the same id — a retry or a re-export
  is idempotent rather than doubling the evidence.
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
`ContextCache.put` refuses to re-store a key under a different authority. There
is no call anywhere in the package that raises a unit's authority.

**Identity holds nothing incidental.** `ContextUnit.identity()` is exactly
`{version, kind, source, span, symbol, content_digest, authority, compression}`
— no clock, no absolute path, no session id, no insertion order.
`test_unit_identity_holds_no_clock_no_absolute_path_and_no_session` asserts the
field set, not a sample.

**Reversible compression.** `compress()` keeps a verbatim head and tail and
names the exact line range it elided, with the full SHA-256 of the original.
`expand()` reconstructs from the canonical source and **raises** if that source
has changed. Compression that would not actually save bytes declines and
returns the whole body. A compression that would keep no verbatim anchor is
refused outright — an elision with no anchor is a summary, and a summary cannot
be checked.

**Read-once reuse.** `ContextCache` is keyed by `(kind, source, symbol, span)`
and validated by content digest. `lookup` requires the digest the caller
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
| bundle chars, nothing compressed | 118,890 |
| bundle chars, compressed | 8,054 |
| reduction in chars supplied up front | 93.2% |
| reads requested / distinct sources | 14 / 7 |
| loader calls | 7 |
| reads avoided by reuse | 7 (reuse ratio 0.467) |
| stale rejections after one source was edited | 1, no unit returned |
| prefix reuse, same units assembled in reverse | 1.000 (byte-identical) |
| prefix reuse, one unit appended | 0.981 (whole previous render is the prefix) |

**What the 93.2% is and is not.** It is the reduction in characters *supplied
up front*. It is not a reduction in what a session ends up reading: an elided
body is a pointer, and a session that needs the body expands it, paying the
difference then. The claim this number supports is "a bundle can carry eight
sources for 8 KB instead of 116 KB", not "the task costs 93% less".

**The ordering defect the measurement found.** With units sorted by
`kind:source`, the string `"evidence:"` sorts between `"capsule:"` and
`"file:"`, so appending one evidence unit to the eight-unit bundle moved
everything after it and dropped the shared prefix from 100% to **19.4%**. The
bundle now orders by a declared rank — authority (contracts first, derived
last), then kind, then key — and the same append keeps the entire previous
render as its prefix. This is the whole reason the brief said *measure* cache
stability rather than assume it; assuming it would have shipped the 19.4%.

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

Every suite in the derived required set (32) at the P6A tip:

```
2292 passed in 439.45s
```

Plus, individually, for the gate's `--suite-evidence` file: `suites.json` in
this directory, 32/32 green, and the gate report `gate-report.json` computed
from it.

Zero P6A-introduced failures. The four `test_company_integration_gate.py`
tests that changed behaviour did so **by design**: their fixture built evidence
from `REQUIRED_SUITES`, which is now the floor rather than the answer, so they
were supplying eleven results against a thirty-two-suite demand. The fixture
now derives the set the same way the gate does.

---

## 7. Remaining correctness findings — preserved, not fixed

Carried forward from P5 and untouched here, because none is required by P6A:

1. **Nested capsule co-selection conflict.** Seven capsules forbid `tools/**`;
   a work order co-selecting one with `company-external-engineering-runner`
   inherits the broader rule and forbidden wins.
2. **No named superseded lifecycle state.** `RecordStatus.SUPERSEDED` exists on
   the record model but no capsule uses it, so "this contract was replaced by
   that one" cannot be stated. P6A's derivation already handles it correctly
   when it appears (a non-active capsule's tests are not required unless the
   change touches its paths), but nothing produces it yet.
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

### For P6B

**Exact contract/test dependency discovery.** P6A derives the required set from
what a capsule *declares*. It does not verify that the declaration is true — a
capsule can name a suite that does not exercise it, or omit one that does.
Deriving the real dependency (which tests import which modules) and comparing
it with `capsule.tests` would turn `capsule.tests` from an assertion into a
checked claim. `tools/engineering_runner/repo_map.py` already builds the
reverse test index this needs.
