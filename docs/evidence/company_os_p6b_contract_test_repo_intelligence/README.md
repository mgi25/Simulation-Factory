# P6B — exact contract/test dependency discovery and repository intelligence

Branch `p6b-contract-test-repo-intelligence-v1`, cut from `origin/main` at
`39fbd44ee7d9c755ba2059b5ab9a467e9c399f30`.

## What P6A left open, in its own words

`company/integration/checks.py` carried the deferral as a comment:

> The real fix is to make `capsule.tests` a checked claim against the actual
> test-to-module dependency, which is P6B.

Two facts sat behind it. `capsule.tests` was a declaration nothing verified,
and P6A's own CLI printed eleven Company OS suites that no capsule declared and
the gate therefore never asked about. Those eleven could go red on a green gate.

## The dependency semantics chosen

An edge is a **static import dependency**. If a suite imports a module, running
the suite loads the module. It does not follow that the suite tests it, asserts
anything about it, or would go red if it broke. Nothing in this milestone
claims test coverage, and `DependencyRelation` is worded so a later change
cannot quietly promote the weaker claim:

| value | meaning |
| --- | --- |
| `DIRECT_STATIC` | the file's own import statements name the target |
| `TRANSITIVE_STATIC` | reached through the repository import closure, not directly |
| `DECLARED_CONTRACT` | `capsule.tests` names it |
| `DECLARED_NOT_OBSERVED` | declared, and no static path exists |
| `OBSERVED_NOT_DECLARED` | a static path exists, and no capsule declared it |
| `UNRESOLVED` | cannot be resolved safely |

`DECLARED_NOT_OBSERVED` is a finding, not a fault. A suite that drives a CLI in
a subprocess, reads a fixture file, or greps source text tests the capsule's
code and imports none of it.

## Four resolution rules

1. **Relative imports resolve against the importing package.** 965 imports in
   this repository are written that way.
2. **`from package import name` may name a module.** Resolved by asking whether
   the file exists, never guessed from the name. 482 such statements resolve to
   a real module here.
3. **Importing anything under a package imports the package**, because
   `a/__init__.py` really runs.
4. **What cannot be resolved is named.** 22 dynamic imports are recorded with
   their line and never turned into edges.

Rule 2 over-reports in one case, on purpose: a package `__init__` binding a
name that a sibling module also has produces both edges. Deciding between them
needs execution. The extra edge can only add a required suite, never remove
one.

## The repo-map corrections

`tools/engineering_runner/repo_map.py` recorded `ImportFrom` only at
`node.level == 0` and resolved `from X import y` to `X`, never to `X/y.py`.
Together those made the dominant pattern in this repository invisible: a test
imports a package facade, the facade re-exports its modules with relative
imports, and the graph saw neither hop. `tests/test_company_gate_suite_requirements.py`
is the worked example — it imports `company.integration`, whose `__init__`
reaches `suites.py` relatively, and neither link existed.

Both resolvers were run over the same P6B tree, so the difference below is
the parser and not the repository (`resolver-before-after.json`).

| measure | before | after |
| --- | ---: | ---: |
| modules with at least one direct test | 169 | 173 |
| total module→test edges | 435 | 445 |
| **`production_dependents` entries** | **97** | **248** |
| transitive reach | not computable | closure, cycle-safe |
| dynamic imports reported | 0 | 22 |

The direct-test numbers barely move, and saying so matters more than the
headline would. The old resolver already matched an exact dotted name and a
package prefix, so a test importing `a.b.c` directly was found. What it could
not see was everything written relatively — which is almost all of the
*production* graph, hence 97 → 248 — and it had no closure at all, so a chain
could never be followed.

That chain is the case this milestone exists for.
`tests/test_company_gate_suite_requirements.py` imports the integration
package by its facade; the facade re-exports `suites.py` with a relative
import. The first hop credits only the package (correctly — the names imported
are symbols), the second hop did not exist, and so the suite that most
directly exercises the required-set resolver appeared to have no relationship
to it. It now reaches it transitively, and the audit can say which of those
two kinds of reach it is.

The two reverse indexes are now views of one `_direct_edges` map. Closures are
computed on demand, cycle-safe, and never serialized: a stored transitive
closure over 500 modules is larger than the map and goes stale the same way.

## Why the graph is built twice, and where the boundary is

`company/**` may not import `tools.engineering_runner`, and the runner may not
import the capsule layer. A dependency graph that broke the architecture
boundary in order to describe it would be self-refuting, so no manifest crosses
it and no import does either.

The Company OS side builds its graph from `GateScan`, which already parses
every root on each run and already resolves relative imports. That makes gate
evidence a pure function of the tree — it cannot be stale, so it needs no
freshness window. The runner keeps its own map for its own job, which is
localizing context for a session.

`tests/test_company_dependency_graph.py` pins both parsers to the same cases,
the pattern the runner already uses for the four control-plane contracts it
restates. On the real tree the two agree on **all 525 modules** they both map.

## Capsule/test contract semantics

`capsule.tests` is a **bounded witness set**, not a complete dependent-test
list. Three pieces of repository evidence decide it:

* `capsule.py` states the MODULE requirement as "names a test", singular.
* `budget.py` caps every list at eight items and says why: a capsule stops
  being cheaper than the code it summarises if it grows.
* The graph itself. A package `__init__` re-exports its modules, so the
  transitive dependent set of one Company OS module is most of the Company OS
  suite list. A "complete" declaration would be a copy of `tests/`.

So the audit asks whether each declaration is *true*, never whether it is
exhaustive. **19 of 20** capsules owning Python had a static witness before the
change and **20 of 20** do after; the three with none own the constitution and
its schemas, a docs directory, and nothing at all, and no import can reach any
of them.

**The budget was not raised.** `max_list_items` is still 8 and
`max_capsule_chars` still 4000, and `test_the_capsule_budget_is_unchanged`
pins both.

## The eleven undeclared suites

Analysed through the graph, not by filename — see `eleven-undeclared-suites.json`
for each one's direct dependencies and the capsules that own them.

Correcting the declarations was measured and rejected. The binding constraint
is not the eight-item list but the 4,000-character capsule ceiling:
`company-executive-delegation` sits at 3,967 and would need about 300 more
characters for its six suites, and `company-youtube-connectivity` sits at 3,987.
Trimming prose to make an audit fit is the move the budget exists to prevent.

That is the finding: `capsule.tests` was serving two masters. It is a bounded
witness set by its own contract and it was the gate's only source of required
suites, and those two purposes size differently.

`SuiteOrigin.DEPENDENCY_OBSERVED` separates them. A `test_company*` file whose
own imports name a module an in-force capsule owns is evidence the contract
needs, declared or not. On this repository that is **exactly the eleven and no
twelfth**: all Company OS suites reach owned code and the rest were already
required. Derived, so the twelfth suite is required the day it is written, and
no capsule grew by one character.

| origin | suites |
| --- | ---: |
| canonical | 11 |
| capsule contract | 33 |
| change scope | 0 |
| dependency observed | 39 |
| **total required** | **45** (was 32) |
| **undeclared Company OS suites** | **0** (was 11) |

The two capsule-id lists are kept apart. Merging them produced report lines
reading "declared by ai-platform" for a suite `ai-platform` has never
mentioned.

## The external-runner capsule deletion (P6A residual B2)

Deleting a capsule takes its `owns_paths` with it, so 21 of the 22 leave an
unclaimed Company OS module behind. `company-external-engineering-runner` owns
`tools/engineering_runner`, `tools` is a *production* root, and the
unclaimed-module scan walks only the four Company OS roots — so deleting it
left a store that was internally consistent, every module claimed, and the gate
still READY.

Hard-coding the capsule id was available and rejected. The general rule comes
from the import graph: a production package that a `test_company*` suite imports
is one the contract depends on, and those imports are not deleted when the
capsule is.

Run against this repository it finds **two** packages, which is the evidence
that it generalises rather than describing one case:

| package | Company OS suites reaching it | owner |
| --- | ---: | --- |
| `tools/engineering_runner` | 3 | `company-external-engineering-runner` |
| `tools/youtube_fetch` | 1 | `company-youtube-fetch-client` (new) |

The second had no owner and nobody had noticed. It gets its own capsule rather
than joining `company-youtube-connectivity`, whose `must_not_modify` forbids
`tools/**` — the two halves of the YouTube path cannot be changed under one
capsule by design.

Intentionally unowned production code is untouched: no Company OS suite imports
`sloped/`, `race/`, `engine/` or anything else in the simulation tree, and no
Company OS module imports a production root at all (verified).

## Gate policy

`architecture.governed_subsystem_ownership` is **REQUIRED**, added to
`REQUIRED_CHECKS` in `policy.py` as a visible diff with the reasoning inline.
`architecture.subsystem_ownership_bounded` stays **ADVISORY**: an unclaimed
Company OS module is a context-selection gap; production code the contract
depends on losing its governance is not. The two are separate checks precisely
so the policy line is the diff.

Missing evidence answers UNKNOWN, never PASS: no capsule store, or a tree that
did not fully parse, both block rather than pass. The same rule applies one
level up — `resolve_required_suites` with no graph returns an *unresolved* set,
so omitting the graph cannot be the cheapest way to shrink the gate.

## Change scope

The runner has always known its change set — `workspace.changed_paths()` runs
`git diff --name-status` and the result reaches the receipt as `files_changed`.
Nothing joined it to the map. `change_impact()` does, and the reviewer brief
now carries the answer: what imports the changed files, which suites import
them, which reach them through another module, and which changed paths have no
import answer at all.

It is localization and says so. It widens no authorized path, relaxes no read
ceiling, excuses no required suite, and `authorization.py` does not import it —
asserted by `test_change_impact_creates_no_authority`.

## Bounded queries

See `measurements.json`. Every answer names how many modules it considered and
which of its lists were truncated, because a truncated answer that does not say
so is a wrong answer.

| path | considered | returned |
| --- | ---: | ---: |
| `company/runtime/routing.py` | 735 | 38 |
| `company/integration/suites.py` | 735 | 20 |
| `company/runtime/__init__.py` | 735 | 94 (truncated) |
| `tools/engineering_runner/repo_map.py` | 735 | 13 |

Queries complete in under a millisecond. The graph is deterministic: the same
scan produces the same fingerprint, and the gate report now names the graph it
derived from as well as the required set.

Stale evidence is refused rather than warned about: `DependencyManifest`
carries schema, version, tree fingerprint, roots and digest, and
`load_dependency_manifest` returns `None` for stale, missing, corrupt and
newer-schema alike.

## What was measured, and what was not

No provider, token or monetary measurement was taken. P6B ran no paid
benchmark and makes no cost claim. The claims here are dependency completeness,
localization precision, deterministic graph and query behaviour, bounded result
size, and stale-evidence refusal.

## Known limitation, written down rather than left to be found

A subsystem is a package directory, so a Company OS suite importing a
*top-level* `tools/` script would name the subsystem `tools` — and the capsule
layer forbids any capsule claiming `tools`, because a claim that wide would
hand one work order write authority over every production script in it. The two
rules would be jointly unsatisfiable. The way out is to move the script into a
package or drop the dependency, never to widen the claim. No Company OS suite
imports a top-level `tools/` script today.

## A gap P6B found and did not close

`satisfying/` is 43 Python modules of production simulation code, and it is
**not in `DECLARED_PRODUCTION_ROOTS`**. The integration gate therefore does not
scan it at all: `architecture.production_does_not_import_company_os` never
looks at it, `health.sources_parse` never parses it, and
`architecture.governed_subsystem_ownership` — P6B's own new check — cannot see
it either, because it only considers roots the gate already declares.

Nothing in it imports Company OS today; that was checked directly against
`origin/main`, which is now `bf0dd1f`. So this is a gap in coverage, not a live
violation.

It is **not fixed here**, deliberately. Which trees the gate polices is a
governance decision with its own blast radius — adding a root makes 43 modules
newly subject to four required checks — and it belongs to whoever owns the
production boundary, not to a milestone about contract/test dependency
discovery. It is reported so the decision is made rather than defaulted.

The same reasoning applies to `intelligence/`, which *is* scanned, because it
is in `COMPANY_OS_ROOTS`. `satisfying/` is in neither list.

## Files

| file | what it holds |
| --- | --- |
| `dependency-graph-summary.json` | module, edge, unresolved and parse-failure counts; roots scanned |
| `unresolved-dependencies.json` | all 22 dynamic imports, with file, line and reason |
| `capsule-test-matrix.json` | every in-force capsule measured against the graph |
| `required-suites.json` | the derived set, its fingerprint, and the per-origin breakdown |
| `governed-subsystems.json` | the two production packages the contract depends on |
| `eleven-undeclared-suites.json` | each of the eleven, its dependencies and its disposition |
| `measurements.json` | graph, runner-map, bounded-query and change-impact measurements |
| `resolver-before-after.json` | the 39fbd44 resolver and the P6B resolver over the same tree |
| `suites.json` | the 45 required suites as actually run on the branch |
| `gate-report-on-branch.json` | the real gate run: BLOCKED |
| `suites-post-merge-modelled.json` | the same, with the three branch-scope guards modelled |
| `gate-report-post-merge-modelled.json` | the modelled gate run: READY. Supporting evidence, not proof |
| `full-suite.md` | the 6,767-test run and every failure classified against 39fbd44 |
