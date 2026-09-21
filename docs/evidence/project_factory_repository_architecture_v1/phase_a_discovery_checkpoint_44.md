# Phase A Discovery Checkpoint 44 — P3C matched benchmark accepted; P3 closed

Date: 2026-09-21

Token Efficiency V4 P3C completed the matched replay with the same quality floor as the accepted P2 correction and materially lower developer resource use.

## Quality result

Work order:

`wo-token-efficiency-v4-p3c-benchmark-contract-correction`

Implementation commit:

`1343a4d770cecb0d7ad683d9bff954156606535d`

Changed path:

`tests/test_company_engineering_execution.py` only.

Required suite:

`207 passed in 19.71s`

The implementation contains all six legitimate exact expectation corrections:

1. `order.authorized_paths`;
2. `order.required_tests`;
3. `plan.writing_paths`;
4. `scope.allowed`;
5. `authority.may_write`;
6. `capsule.tests`.

Independent reviewer: pass.

Deterministic review: pass.

Gate:

- 11/11 required suites green;
- readiness: ready;
- blockers: 0;
- report: `integration-readiness-2026-09-21-632403a54cd2cbb3`;
- production integration remains unauthorized.

## P2 developer baseline

- sessions: 1
- turns: 25
- provider cost: USD 0.953491
- cache read: 756,397
- cache creation: 39,802
- output: 13,056
- file reads: 11
- repeated reads: 10
- searches: 7
- provider duration: 217.635 s

## P3C developer result

- sessions: 1
- turns: 12
- provider cost: USD 0.42913475
- cache read: 222,727
- cache creation: 25,041
- output: 6,448
- file reads: 5
- unique reads: 1
- repeated reads: 4
- searches: 0
- provider duration: 99.528 s
- local pre-provider diagnostic: 28.9535 s
- Bash: 0
- git commands: 0
- model-run tests: 0

## P2 -> P3C developer reductions

- turns: 52.0% lower
- provider cost: 55.0% lower
- cache read: 70.6% lower
- cache creation: 37.1% lower
- output: 50.6% lower
- file reads: 54.5% lower
- repeated reads: 60.0% lower
- searches: 100% lower
- provider duration: 54.3% lower

Including the deterministic 28.9535 s base diagnostic, P3C developer navigation + provider elapsed time was 128.482 s, 41.0% below the P2 provider duration.

## P3B -> P3C tradeoff

P3B had lower developer usage but failed quality because its first failure-guided function was clipped before a second stale exact assertion.

P3C restored quality with a modest increase over the failed P3B developer run:

- turns: +9.1%
- provider cost: +14.1%
- cache read: +6.2%
- cache creation: +1.4%
- output: +38.0%
- file reads: +25.0%
- repeated reads: +33.3%
- searches: unchanged at 0
- provider duration: +22.3%

That extra usage bought the missing quality outcome: 207/207 required tests, review pass and READY gate.

## Whole paid-run comparison

P2 corrected paid developer + reviewer:

- sessions: 2
- turns: 31
- provider cost: USD 1.19445475
- cache read: 816,262
- cache creation: 57,651
- output: 17,034

P3C paid developer + reviewer:

- sessions: 2
- turns: 25
- provider cost: USD 0.775347
- cache read: 336,634
- cache creation: 50,924
- output: 11,546

P2 -> P3C whole-run reductions:

- turns: 19.4% lower
- provider cost: 35.1% lower
- cache read: 58.8% lower
- cache creation: 11.7% lower
- output: 32.2% lower

## Remaining bottleneck

P3C reviewer:

- sessions: 1
- turns: 13
- provider cost: USD 0.34621225
- cache read: 113,907
- cache creation: 25,883
- output: 5,098
- file reads: 8
- repeated reads: 5
- searches: 4
- duration: 98.686 s

Compared with the P2 correction reviewer, reviewer cost is 43.7% higher, turns 116.7% higher, cache read 90.3% higher, cache creation 45.0% higher and output 28.2% higher.

The reviewer is therefore the clearest remaining provider-side inefficiency observed in this matched run. It is recorded as a measured bottleneck, not changed inside P3.

## P3 conclusion

P3 is accepted as a quality-preserving efficiency improvement for this matched replay.

This remains one matched sample, not a causal estimate of average savings.

The architectural mechanism that earned acceptance is:

- deterministic immutable-base failure diagnosis;
- exact failing AST-symbol selection;
- complete failure-guided function preservation when it fits the existing global context budget;
- semantic fill only after failure-guided allocation;
- no model-owned required tests, shell, git or MCP work;
- deterministic post-edit validation isolated from stale bytecode caches.

## Next program step

Close P3.

Proceed to the planned P4 content-addressed cache as the next architecture milestone, while carrying the measured reviewer overhead forward as a concrete optimization target for the later reviewer-efficiency / deterministic pre-adjudication work.

Do not fold reviewer redesign into the accepted P3 result.

No canonical merge, deployment, publishing or production integration is authorized.
