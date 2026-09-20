# Repository Architecture V1 — Phase A Discovery Checkpoint 01

**Date:** 2026-09-21  
**Status:** discovery in progress; no production code moved  
**Source priority:** current source code > current canonical baseline docs > historical validation artifacts.

## 1. Confirmed current architectural planes

Current `company/integration/sources.py` defines four Company OS roots:

- `company/`
- `ai_platform/`
- `knowledge/`
- `intelligence/`

It defines these production roots:

- `engine/`
- `entities/`
- `godot/`
- `marble3d/`
- `modes/`
- `powers/`
- `production/`
- `race/`
- `race2/`
- `sloped/`
- `audio/`
- `evaluation/`
- `rendering/`
- `replay/`
- `tools/`

and production entry points:

- `main.py`
- `race_main.py`

The strongest current architecture invariant remains one-way control-plane coupling: production code must not import Company OS roots. The current integration code checks this by AST rather than grep.

## 2. Current product state

The canonical pre-media-loop baseline states:

- Race #2 V33.1 is shipped and frozen;
- Race #2 V32.2 is shipped;
- race/race2/sloped/marble3d and the simulation/evaluation/render/delivery/QC surfaces remain test-covered production assets;
- Race and Fight are the first two format-family portfolio assets in the master company design.

A complete ACTIVE/SUPPORTED/LEGACY/EXPERIMENTAL/ARCHIVED classification for every production root does **not** yet exist as one authoritative machine-readable map. That is a discovery deliverable, not something this checkpoint guesses.

## 3. Ownership gaps confirmed

The canonical baseline records:

- `architecture.subsystem_ownership_bounded` has reported seven Company OS modules with no capsule claim, including `company/workforce/*` and `knowledge/__init__.py`;
- `tools/` is owned by nobody in the capsule model.

This matters twice:

1. architecture responsibility is incomplete;
2. Company OS cannot safely select some otherwise-routine work under an ownership-based execution rule.

Ownership completeness is therefore both a maintainability issue and an AI-efficiency issue.

## 4. Knowledge-freshness drift found

A current active capsule, `knowledge/company_os/capsules/seeds/company-os-control-plane.json`, was last reviewed on 2026-09-16 and still contains statements such as:

- "Company OS stays unconnected to production execution until the integration gate ... passes";
- risk: "The integration gate has not passed".

The canonical repository baseline records that the Company OS integration gate passed and Company OS was consolidated into `main` afterwards.

This is a concrete stale-knowledge condition.

### Why it matters

A future model given the capsule as minimal context could reason from a historically true but currently false state. It might then:

- perform unnecessary repository exploration to resolve the contradiction;
- escalate work that is already valid;
- make an incorrect architecture claim;
- reread historical documents to reconstruct current state.

Therefore "minimum context" is not sufficient by itself. Context must also be **current, provenance-aware, and invalidated by architectural change**.

The program should add freshness/conformance rules so a capsule whose source facts changed cannot silently remain authoritative.

## 5. Historical evidence must not be treated as live architecture

Historical gate reports in `docs/validation/` contain statements from earlier checkouts, for example that `race2/` was a declared-but-absent production root.

Current `company/integration/sources.py` includes `race2` and the repository contains it.

The historical reports are valid evidence of what was true at their recorded commit. They are not current-state architecture.

The target documentation model therefore needs explicit separation between:

- **current authoritative architecture**;
- **immutable historical evidence**;
- **decisions/ADRs**;
- **experimental reports**.

AI retrieval should prefer current architecture for "what is true now" queries and historical evidence only when the task asks why/how the state evolved.

## 6. Existing technical debt that intersects this program

The canonical baseline already carries these relevant items:

- `pilot*.py` names are historical even though those modules are now live authority runtime;
- semantic capsule ownership is incomplete;
- `tools/` lacks an owner;
- provider usage lacks a stable per-event identifier;
- runner cost telemetry and turn/token telemetry have different granularity;
- some cleanup decisions historically relied on git ancestry alone and accidentally deleted branch refs still used as test fixtures.

These are not automatically approved for immediate repair. They are inputs into target-state design and migration prioritization.

## 7. Efficiency findings carried forward

Historical repository-efficiency evidence shows that deterministic repository intelligence can reduce exploration cost, but remaining read waste can occur after discovery.

The V2 trace recorded 12 developer reads of only 2 unique files, with 10 repeated reads and zero files read that were not changed.

Therefore future efficiency work must distinguish:

- **finding the right file**;
- **re-reading an already-known file during edit/verification**.

Adding another repository index is unlikely to fix the second problem by itself.

## 8. Initial architecture risks

### A. Current-vs-history ambiguity
Repository evidence is rich, but current truth and historical truth are not always separated strongly enough for cheap AI retrieval.

### B. Lifecycle ambiguity
Multiple generations of Race/Marble implementation remain production roots. Their precise lifecycle states are not centrally machine-readable.

### C. Ownership incompleteness
Some Company OS modules and all of `tools/` lack semantic ownership.

### D. Tooling boundary overloaded
`tools/` is both a production root and home to external engineering/runtime utilities. It needs semantic classification before any structural move is proposed.

### E. Telemetry attribution limits
Existing usage evidence is useful but not yet sufficient for exact role/stage/event accounting across the whole company.

## 9. Next discovery work

Before target-state design, continue with:

1. enumerate Company OS subpackages and current capsule ownership;
2. classify every production root by lifecycle and purpose;
3. map dependency directions between active roots;
4. identify duplicate/parallel implementations that are truly redundant versus deliberately preserved history;
5. identify current documentation/capsule statements invalidated by the final pre-media-loop integration;
6. map current test/fixture dependencies that make deletion unsafe;
7. measure where architecture/context metadata is currently duplicated;
8. produce the candidate set for architecture fitness functions.

## 10. No-change statement

This checkpoint changes no production code, no Company OS authority, no workforce state, no canonical branch, and no frozen release.

It records evidence that will constrain later design.
