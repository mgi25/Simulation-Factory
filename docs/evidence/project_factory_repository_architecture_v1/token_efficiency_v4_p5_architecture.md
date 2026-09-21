# Token Efficiency V4 P5 — Adaptive model routing

Date: 2026-09-21

## Objective

Reduce provider cost further by routing only strongly localized routine developer tasks to a cheaper model tier, without weakening the existing standard/strongest quality boundary.

P5 starts from fully accepted P4C:

`0cff265e5b92dc73c8ca1526da8664126d06af1b`

P5 branch:

`project-factory-token-efficiency-v4-p5`

Current P5 source:

`533ae4e4f03f6faf10b5b316ada7edcabb49972d`

## Core safety rule

Company OS never emits `economy` as the primary `model_tier`.

Primary recommendations remain:

- `standard`
- `strongest`

The runner may downshift a `standard` developer session to the abstract `economy` target only after deterministic execution evidence passes every P5 gate.

The runner maps the abstract economy target to provider alias `haiku` by default. Company OS does not name the vendor model.

## Static Company OS candidate boundary

A task is only marked as an economy candidate when all are true:

- developer session, not review;
- consumer resource profile;
- reasoning class C;
- low risk;
- no escalation;
- first packet attempt;
- exactly one authorized writable path;
- one or two required tests;
- not novel;
- no specialist domain;
- primary recommendation remains standard.

Failing any one condition makes the task statically ineligible.

Review sessions are not downshifted in P5.

Correction attempts are not downshifted in P5.

Strongest-tier tasks are never downshifted.

## Runtime deterministic gate

Static eligibility is not sufficient.

Before provider launch, the runner requires:

1. the immutable-base required-test diagnostic ran;
2. it reported at least one counted failing test;
3. failure-symbol hints were extracted;
4. counted failures equal unique failure-symbol hints;
5. every hint appears as a failure-guided compiled span;
6. every such compiled span covers the complete AST symbol;
7. runtime authority still contains exactly one writable path;
8. required-test count remains inside the bounded base-diagnostic ceiling;
9. the operator did not explicitly pin a developer model;
10. resource-strategy application is enabled.

Only when every condition passes is the applied model changed from the standard alias to the economy alias.

## P3B lesson encoded as a routing veto

P3B selected the correct failing test function but clipped the function before a second stale assertion.

P5 therefore does not accept "correct symbol selected" as enough evidence for a cheaper model.

Every failure-guided span must reach the complete AST symbol boundary before an economy downshift is allowed.

## Evidence

Developer `resources.json` records an `adaptive_model_routing` object containing:

- candidate;
- source tier;
- requested/target tier;
- applied;
- counted base failures;
- failure-symbol hint count;
- complete failure-guided span count;
- veto reasons.

A reader can therefore distinguish:

- not nominated;
- nominated but vetoed;
- nominated and actually downshifted.

## Operator override

An explicit `--developer-model` remains authoritative and disables adaptive downshift.

P5 also adds `--economy-model` to map the abstract economy target to a provider alias.

## Artifact protocol

Resource-strategy artifact version advances to 2.

Runner compatibility accepts resource-strategy versions 1 and 2 during transition.

The primary `model_tier` parser still refuses `economy`; the cheaper tier is reachable only through the adaptive routing gate.

## Acceptance plan

Before any provider spend:

1. compile modified routing modules;
2. Company OS efficiency strategy tests;
3. Company engineering briefing tests;
4. external runner adaptive-routing tests;
5. complete runner-focused suite;
6. 11 canonical Company OS suites;
7. integration gate READY with zero blockers.

After static acceptance, use a fresh matched replay of the accepted P3C benchmark task to compare economy vs the quality-preserving Sonnet P3C baseline.

A cheaper result only counts if the same quality floor passes.

No canonical merge, deployment, publishing or production integration is authorized.
