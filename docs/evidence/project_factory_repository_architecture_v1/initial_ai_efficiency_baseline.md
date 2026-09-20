# Repository Architecture V1 — Initial AI Efficiency Baseline

**Date:** 2026-09-21  
**Nature:** historical baseline assembled from already-recorded repository evidence; no new experiment is claimed here.

## Known measured evidence

The existing repository-exploration efficiency work provides a useful starting point for the AI Efficiency Platform Engineer.

From the recorded V1 → V2 matched engineering job:

| Metric | V1 | V2 | Recorded change |
|---|---:|---:|---:|
| Developer turns | 27 | 26 | -3.7% |
| Developer output units | 8,184 | 6,033 | -26.3% |
| Developer cache-read units | 990,324 | 783,941 | -20.84% |
| Developer cache-creation units | 61,384 | 41,926 | -31.7% |
| Developer cost | $1.083562 | $0.804993 | -25.7% |
| Developer wall time | 209.6 s | 151.96 s | -27.5% |
| Reviewer turns | 9 | 5 | -44.4% |
| Reviewer cache-read units | 158,520 | 47,922 | -69.8% |
| Reviewer cost | ~ $0.374 | $0.213690 | -42.9% |
| Total recorded job cost | ~ $1.457 | $1.018683 | -30.1% |

The V2 developer trace recorded:

- 12 file reads;
- 2 unique files;
- 10 repeated reads;
- 2 searches;
- 0 repeated searches;
- 0 files read but never changed.

This is important: the remaining observed read waste was concentrated in repeated reads of an already-identified file, rather than broad repository discovery.

## What this baseline does prove

- deterministic repository intelligence can reduce some discovery/context cost;
- reviewer scope reduction can materially reduce reviewer resource consumption;
- file-level exploration telemetry can reveal waste that aggregate cache usage alone cannot explain;
- context optimization should continue to be measured against accepted quality.

## What this baseline does NOT prove

It does not prove that Company OS as a whole is cheaper than a normal direct session.

It does not measure every role/stage in the new repository architecture program.

It does not expose authoritative ChatGPT consumer-plan token quotas.

It does not establish that a 20.84% reduction will repeat on other tasks; the source report explicitly notes n=1 and natural workload variance.

It does not establish the best workflow for tiny, normal, high-risk, and architecture-level tasks.

## Current measurement gaps to close

1. **Direct-session comparator:** no frozen Direct-vs-Company-OS matched protocol existed before this program.
2. **Whole-company attribution:** total resource usage needs to be grouped by role/stage, not only developer/reviewer.
3. **Purpose attribution:** planning, discovery, implementation, review, rework, and redundant work need separate accounting where observable.
4. **Plan-level visibility:** consumer-plan quota/token use is not assumed measurable. The program must distinguish provider telemetry from plan-level UI/account usage.
5. **Accepted-outcome economics:** cost must be tied to accepted verified outcomes so failed/rejected work is not hidden.
6. **Selective routing evidence:** we do not yet know when direct execution is more efficient than full Company OS.
7. **Architecture-work efficiency:** the cost of specialist architecture reasoning itself has not yet been benchmarked within this program.

## Initial efficiency objective

Reduce avoidable context/retrieval/rework cost while preserving or improving accepted quality.

The AI Efficiency Platform Engineer should treat Company OS itself as an object of optimization. Company structure is not exempt from measurement merely because the company created the measurement system.
