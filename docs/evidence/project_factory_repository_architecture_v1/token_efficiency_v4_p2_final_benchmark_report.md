# Token Efficiency V4 P2 — Final Matched Benchmark Report

Date: 2026-09-21

## Executive result

Token Efficiency V4 P2 successfully removed the historical shell/test-loop multiplication pattern from routine consumer-profile engineering work while preserving deterministic quality controls.

The benchmark was not a clean one-shot quality success because the original benchmark work order was under-scoped: adding a second semantic test to `company-engineering-execution` legitimately changed exact engineering-execution test expectations that were outside the original writable scope. A separate bounded correction repaired those expectations and reached READY with zero blockers.

A second, pre-existing test dependency defect in `tests/test_company_review_separation.py` was then exposed by extended validation and repaired separately. That repair is excluded from P2 benchmark accounting.

No canonical merge, deployment, publishing or production integration was performed.

## Validated P2 runner

P2 implementation commit:

`619b2a0374ab935c1eb21b19517d3eeecc7d0b42`

Key controls observed in live execution:

- routine consumer developer tools were exactly Glob, Grep, Read, Edit, Write;
- Bash absent;
- TodoWrite absent;
- MCP servers empty;
- model did not run deterministic tests;
- model did not run git commands;
- runner owned deterministic validation;
- every paid provider subprocess was preserved as a numbered session artifact;
- no hidden provider retry occurred.

## Historical developer baseline

Historical V2 developer aggregate:

- provider sessions: 2
- turns: 46
- cache read: 2,111,924
- cache creation: 124,470
- output: 65,525
- provider cost: USD 3.4722695

The historical first developer session alone used 38 turns, 1,917,651 cache-read units, 85,218 cache-creation units, 61,693 output units and USD 3.033953 before a second paid session completed the work.

## P2 matched benchmark — first developer attempt

Work order:

`wo-token-efficiency-v4-p2-review-test-ownership-v2`

Worker commit:

`287d690b7bf87c988edb3eb34d1f57a4dcec5ab1`

Developer:

- provider sessions: 1
- turns: 10
- cache read: 156,514
- cache creation: 22,671
- output: 2,960
- provider cost: USD 0.29400075
- Bash calls: 0
- test commands: 0
- git commands: 0
- MCP servers: 0

Directional reduction versus historical developer aggregate:

- provider sessions: 50.0%
- turns: 78.3%
- cache read: 92.6%
- cache creation: 81.8%
- output: 95.5%
- provider cost: 91.5%

These are one-sample directional measurements, not a causal performance estimate.

The patch itself was semantically correct and changed only the intended capsule test list plus its capsule regression assertion. Deterministic validation correctly rejected it because `tests/test_company_engineering_execution.py` contained exact expectations that also needed updating.

## Bounded benchmark correction

Correction work order:

`wo-token-efficiency-v4-p2-benchmark-contract-correction`

Correction commit:

`615dfea4ddadc56bedc108d91aae1663448f9f94`

The correction changed only:

`tests/test_company_engineering_execution.py`

It updated six exact tuple assertions across five failing test functions. Assertions remained exact and were not weakened.

Correction developer:

- provider sessions: 1
- turns: 25
- cache read: 756,397
- cache creation: 39,802
- output: 13,056
- provider cost: USD 0.953491
- Bash calls: 0
- test commands: 0
- git commands: 0
- MCP servers: 0

Correction reviewer:

- provider sessions: 1
- turns: 6
- cache read: 59,865
- cache creation: 17,849
- output: 3,978
- provider cost: USD 0.24096375

Focused deterministic validation:

- `tests/test_company_engineering_execution.py`: 207 passed

Review:

- attested: pass
- deterministic: pass
- final: pass

Integration gate:

- report: `integration-readiness-2026-09-21-baa5829b6a7b362f`
- blockers: 0
- readiness: READY
- lifecycle: `ready_for_approval`

## Conservative end-to-end developer comparison

To avoid overstating P2, count both developer sessions required to reach the corrected benchmark implementation:

P2 benchmark + correction developers:

- provider sessions: 2
- turns: 35
- cache read: 912,911
- cache creation: 62,473
- output: 16,016
- provider cost: USD 1.24749175

Versus historical V2 developer aggregate:

- turns: 46 -> 35, 23.9% lower
- cache read: 2,111,924 -> 912,911, 56.8% lower
- cache creation: 124,470 -> 62,473, 49.8% lower
- output: 65,525 -> 16,016, 75.6% lower
- provider cost: USD 3.4722695 -> USD 1.24749175, 64.1% lower

This conservative comparison includes the cost of correcting the benchmark's initial under-scoping.

## Whole paid P2 benchmark path, including reviewers

First benchmark reviewer:

- turns: 5
- cache read: 47,050
- cache creation: 17,647
- output: 3,830
- cost: USD 0.22959375

Correction reviewer:

- turns: 6
- cache read: 59,865
- cache creation: 17,849
- output: 3,978
- cost: USD 0.24096375

Whole benchmark path, benchmark plus correction:

- provider sessions: 4
- turns: 46
- cache read: 1,019,826
- cache creation: 97,969
- output: 23,824
- provider cost: USD 1.71804925

This whole-path number is not directly comparable to the historical developer-only baseline and is recorded only for completeness.

## Pre-existing YAML dependency repair — excluded from benchmark accounting

Extended validation discovered that `tests/test_company_review_separation.py` imported third-party `yaml` even though PyYAML is not declared in `requirements.txt` and Company OS deliberately uses its own YAML-subset loader.

Separate repair work order:

`wo-token-efficiency-v4-review-separation-yaml-dependency`

Repair commit:

`baea7830f2a069b381aa035b16a98612ba504496`

The repair changed only the test file:

- removed `import yaml`;
- imported `company.validation.yaml_subset.load_yaml_subset`;
- changed the registry fixture to use the canonical loader;
- changed no behavioral assertion.

Focused deterministic validation:

- engineering execution: 207 passed
- review separation: 32 passed

Review:

- attested: pass
- deterministic: pass
- final: pass

Gate:

- report: `integration-readiness-2026-09-21-9e13de94f5e23be9`
- blockers: 0
- readiness: READY
- lifecycle: `ready_for_approval`

Separate repair provider usage:

- provider sessions: 2
- turns: 13
- cache read: 205,235
- cache creation: 39,002
- output: 3,384
- cost: USD 0.431045

This usage is excluded from P2 matched benchmark accounting.

## Architecture findings

### P2 control effectiveness

The live runs establish that P2 achieved its intended control change:

- no model-owned deterministic test loop;
- no Bash loop;
- no git loop;
- no hidden paid retry;
- restricted tool surface applied to the actual provider session;
- deterministic failures can overrule an incorrect model-review PASS.

### Remaining dominant inefficiency

P2 did not eliminate repeated semantic reading.

The correction developer touched one file but used:

- 25 turns;
- 11 file reads, 10 repeated;
- 7 searches;
- 756,397 cache-read units.

The unrelated YAML repair, also a one-file task, used only:

- 8 turns;
- 2 file reads, 0 repeated;
- 1 search;
- 141,128 cache-read units.

This variance is strong evidence that the next optimization should attack context discovery and repeated reading rather than shell/test execution.

## Next phase

Proceed to P3: deterministic semantic context compilation / read-once context delivery.

The next phase should focus on:

1. local/free extraction of exact relevant spans before the model starts;
2. stable symbol/reference/test anchors;
3. read-once context bundles;
4. explicit duplicate-read detection and evidence;
5. preserving P2's restricted tool surface and runner-owned validation;
6. matched measurement against the high-read correction pattern.

P2 is accepted as a quality-preserving directional efficiency improvement.

No canonical merge is authorized by this report.
