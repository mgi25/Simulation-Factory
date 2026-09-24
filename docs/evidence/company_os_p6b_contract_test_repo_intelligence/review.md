# P6B — adversarial review pass

## What this is, and what it is not

This is a **separate adversarial pass over the P6B diff, run in the same
session that wrote it**. It is not an independent Company OS review and it is
not an attestation: no second employee ran it, no reviewer packet was issued,
and nothing was written to `docs/evidence/reviews/`, which is the attestation
surface `company-evidence-review` owns and which exists precisely so that an
independent verdict cannot be confused with a self-assessment.

The package brief asked for a genuinely separate top-level independent
reviewer. The same brief's operating rules forbid subagents, and this
repository's standing instruction is the same. The pass was therefore run at
top level and adversarially, against the attack list the brief named, with
every claim checked by executing a probe rather than by reading. Where that is
weaker than an independent review, it is weaker, and the CEO decision on
integration should treat it as one reviewer's word rather than two.

## Method

Two probe scripts, each building synthetic repositories and running the real
resolvers over them, plus one comparison across the whole checkout. Findings
below are what the probes returned, not what the code appeared to say.

The first probe had a fixture bug of its own — a path helper that mangled
`__init__.py` — and reported that `from . import core` inside a package
`__init__` produced no edge. That was false, and the corrected probe showed the
edge present on both sides. It is recorded here because a review that hides its
own false positive is not reporting its error rate.

## Verdict: PASS, with three findings, all fixed in this branch

### Findings addressed

**R1 — the gate report named the required set but not the graph it came from.**
`RequiredSuites.fingerprint()` covers the set, and the provenance line named
the capsule count, so a reader disputing the set could see three of its four
inputs. The fourth — the import graph — was invisible. Fixed: the provenance
line now carries the graph fingerprint, the module count and the
dependency-observed origin count, and `test_the_gate_report_names_the_graph_it_derived_from`
pins it.

**R2 — a latent unsatisfiable pair.** A subsystem is a package directory, so a
Company OS suite importing a *top-level* `tools/` script would name the
subsystem `tools`, and the capsule layer forbids any capsule claiming `tools`
because a claim that wide would hand one work order write authority over every
production script in it. The check's remediation line would have sent a reader
to do exactly the thing the guards refuse. No Company OS suite imports a
top-level `tools/` script today. Fixed by writing the case and its real
remedy — move the script into a package, or drop the dependency — into the
check's docstring rather than leaving it to be discovered.

**R3 — an unnamed over-report.** If a package `__init__` binds a name that a
sibling module also has (`core = 1` beside `core.py`), `from pkg import core`
produces both edges though only one runs. Deciding needs execution. The extra
edge can only add a required suite or a recommended file, never remove one, so
it errs in the direction the rest of the design already chose. Fixed by naming
it where the rule lives rather than leaving the graph quietly imprecise.

## The attack list, item by item

| attack | result |
| --- | --- |
| false dependency edges | Aliased `import a.b as c`, stdlib and third-party imports, and symbol-only `from X import Name` all resolve correctly. One deliberate over-report, R3 above. |
| missed relative imports | 965 previously dropped. Levels 1 and 2 verified, with and without a module name; a level deeper than the package resolves to nothing rather than clamping. |
| transitive closure mistakes | Direct and transitive are separate answers and separately asserted; a module the facade does not re-export is not reached. |
| package/`__init__` mistakes | `from . import core` inside an `__init__` resolves on both sides; ancestor packages are edges because they really run. |
| circular dependency handling | BFS over a visited set; a closure never contains its own start; bounded at 100,000 expansions. |
| dynamic-import overclaims | 22 dynamic imports recorded with file and line, none resolved, even when the argument is a literal. |
| filename heuristics disguised as facts | None in either module. `test_core.py` has no relation to `core.py` without an import; asserted by test. |
| forcing every observed test into `capsule.tests` | The audit mutates nothing, asserted by test. No capsule gained a declaration. |
| quietly expanding capsule budgets | `max_list_items` still 8, `max_capsule_chars` still 4000, asserted by test. The 4,000-char ceiling is what made declaration correction infeasible, and it was left alone. |
| stale graph reuse | The gate graph is recomputed from the scan each run and cannot be stale. The runner manifest refuses stale, missing, corrupt and newer-schema alike. |
| graph identity not tied to repository content | `DependencyManifest.tree_fingerprint` ties to content; `matches()` fails closed on tree, roots, schema and version together. |
| repository intelligence creating authority | `ChangeImpact` carries no authority field and `authorization.py` imports neither it nor the map; asserted by test. |
| new required conditions hidden without a `GatePolicy` change | The new condition is its own check with its own `policy.py` line; its advisory neighbour stayed advisory; the split is pinned by count. |
| Company OS importing the external runner | No `company/**` module imports `tools`, by AST. |
| runner importing capsule internals | No runner module imports `company`, `ai_platform`, `knowledge` or `intelligence`, by AST. |
| tests removed from required evidence by narrowing scope | Six scopes tried, including the empty one; the required set never shrank below the unscoped set. |

## Two measurements the review produced that the design did not claim

**The two parsers agree on all 525 modules they both map.** Company OS builds
its graph from `GateScan` and the runner builds its own; they are independent
implementations of one contract, and on this repository their answers to
"which tests reach this module" are identical for every module in the
intersection. That is stronger evidence for the restated-contract pattern than
the drift test alone.

**No Company OS module imports a production root.** Checked across every
Company OS module's imports. This bounds the blast radius of
`governed_subsystem_ownership`: the only way a production package enters its
result is a Company OS *test* importing it, which is the narrow case the rule
was written for, rather than a chain through some Company OS module.

## What this review does not establish

* It is not independent. One reader, in the session that wrote the code.
* It says nothing about provider cost, tokens or latency. P6B ran no paid
  benchmark and the evidence makes no cost claim.
* It does not establish that any suite *tests* the code it imports. Every
  claim here is about static import structure, which is the only thing the
  graph can support.
* It did not review the simulation tree. P6B touches none of it, and the
  full-suite comparison against `39fbd44` is the evidence for that, not this.
