# Phase A Discovery Checkpoint 05 — Metadata fix rejected for semantic compression and efficiency

Date: 2026-09-21

## CEO decision

Work order `wo-delegation-planning-test-ownership` reached
`ready_for_approval` at commit
`b717b2c6354a60fa0f4e420b1a3b8ff347293ea8`.

The CEO rejected this exact implementation.

The intended functional change was correct:
- `tests/test_company_objective_planning.py` was added to the
  `company-executive-delegation` capsule's tests.
- `tests/test_company_executive_planning.py` was added to the same list.
- capsule tests pinned both references.
- targeted tests and all 11 integration-gate suites passed.

The implementation was rejected because fitting the additions under the
4,000-character capsule ceiling weakened authoritative prose:
- `functional authority` became `authority`, losing the functional-chain
  qualifier.
- `Scenarios are transcribed from reports on other branches` became
  `Scenarios from branch reports`, losing the explicit manual-transcription
  risk.
- the resulting capsule was approximately 3,990/4,000 characters, leaving
  negligible maintenance headroom.

## AI-efficiency evidence

Measured developer session:
- 42 model turns
- 1,841,036 cache-read units
- 71,003 cache-creation units
- 23,772 output units
- USD 1.958802
- 15 file reads, 9 unique, 6 repeated
- 4 searches, 0 repeated

Measured reviewer session:
- 6 model turns
- 64,868 cache-read units
- 32,283 cache-creation units
- 3,630 output units
- USD 0.32498775
- 3 file reads, all unique
- 1 search

Known cost for this rejected outcome: USD 2.28378975.

Together with the earlier accepted ownership job, known measured program model
spend is USD 4.8144215. The interrupted earlier developer session remains
UNAVAILABLE and is not imputed as zero.

Consumer-mode advisory ceilings were exceeded by the developer:
- turns: 42 observed vs 40 advisory ceiling
- cache read: 1,841,036 observed vs 1,000,000 advisory ceiling

## Follow-up

Issue a fresh metadata-only work order. Preserve the new planning-test
references, restore the two semantic meanings above, and leave at least 100
characters of capsule headroom (canonical size <= 3,900 characters).

Do not merge the rejected implementation into the Repository Architecture V1
program branch or canonical main.
