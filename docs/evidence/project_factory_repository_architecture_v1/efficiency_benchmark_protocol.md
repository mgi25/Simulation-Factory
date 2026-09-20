# Repository Architecture V1 — Efficiency Benchmark Protocol

**Status:** frozen before new program benchmark results  
**Date:** 2026-09-21  
**Purpose:** determine whether Company OS improves total engineering economics and reliability relative to a direct engineering session.

## 1. Question

For real Project Factory engineering work, does the Company OS workflow reduce total cost per accepted verified outcome, improve reliability enough to justify any added coordination cost, or add overhead without compensating value?

No outcome is preferred in advance.

## 2. Experimental unit

A matched pair consists of two independent attempts at the same bounded engineering task:

- **A — Direct session**
- **B — Company OS workflow**

Each pair must start from the same base commit and receive equivalent task authority.

A task may be used only when both paths can legitimately execute it. Major architecture approval, deployment, publishing, destructive cleanup, credential work, or other CEO-reserved actions are excluded from this benchmark because a direct routine coding session and bounded Company OS do not have equivalent authority for them.

## 3. Task selection

Use real useful work discovered by the architecture/efficiency program. Do not invent toy changes merely to make the benchmark easy.

Prefer tasks that are:

- independently testable;
- low or medium risk;
- reversible;
- bounded to a small coherent surface;
- representative of recurring Project Factory work;
- not already solved on the benchmark base commit.

Avoid deliberately selecting only tasks known to favor either workflow.

Target at least three matched pairs when practical. One pair is evidence about one job, not a company-wide conclusion.

## 4. Frozen equality conditions

Within one pair, both paths use:

- the same base commit;
- the same objective wording or semantically equivalent canonical objective;
- the same authorized paths;
- the same acceptance criteria;
- the same required tests;
- the same protected surfaces;
- the same quality threshold;
- the same stop conditions.

If model/provider differs, record that as a confounder and do not silently attribute the outcome to workflow.

## 5. Direct-session path

The direct path receives the minimum sufficient task packet and executes without Company OS management stages.

It may use the repository's deterministic navigation tools if those tools are part of the normal engineering environment; the benchmark is testing orchestration overhead/value, not intentionally handicapping one side.

Record all exposed resource telemetry.

A direct session must still satisfy the same tests and acceptance criteria before it counts as accepted.

## 6. Company OS path

Count **all** resource use caused by the Company OS workflow, including when present:

- intake/routing;
- planning;
- Chief Architect/specialist reasoning;
- AI Efficiency analysis;
- developer execution;
- review;
- correction/retry;
- final reporting/handoff.

Deterministic software work is reported separately from model usage but its wall time should remain visible.

Do not report only developer cost as "Company OS cost."

## 7. Primary outcome

**Total measured AI resource cost per accepted verified outcome.**

Where authoritative monetary cost exists, report monetary cost.

Where it does not, report exposed token/unit measures separately. Never convert unknown consumer-plan usage into invented dollars or tokens.

An outcome is "accepted verified" only when:

- acceptance criteria pass;
- required deterministic tests pass;
- required review/gates pass;
- no known program-blocking regression remains.

A failed attempt still counts toward the resources consumed by its path.

## 8. Secondary outcomes

For each path record, where available:

- input units/tokens;
- output units/tokens;
- cache-read units;
- cache-creation units;
- context/instruction characters;
- model turns;
- tool events;
- file reads;
- unique file reads;
- repeated reads;
- searches;
- repeated searches;
- files read but not changed;
- retries/corrections;
- wall time;
- reviewer findings;
- first-pass acceptance;
- tests/gate result;
- regressions;
- changed-file count;
- reusable knowledge/tooling produced.

## 9. Overhead accounting

Company OS overhead includes measured model/resource use that would not exist in the direct path solely because of orchestration, management, handoff, or independent review.

Do not automatically label all review cost waste. Review is overhead only in the accounting sense; its value is measured through defects caught, corrections prevented, architecture protection, and improved acceptance reliability.

Report:

`coordination_overhead_share = company_orchestration_resource / total_company_os_resource`

only for a resource dimension that is actually measured.

## 10. Waste categories

When evidence permits, classify consumption as:

- necessary reasoning;
- repository discovery;
- implementation;
- validation/review;
- coordination/handoff;
- rework;
- redundant read/search;
- reporting.

Classification must come from observable events/artifacts where possible. Unknown remains unknown.

## 11. Decision interpretation

Do not use one scalar "winner" if the evidence is mixed.

Possible evidence-backed conclusions include:

- Company OS cheaper with comparable quality;
- Company OS more expensive but with materially better reliability;
- Company OS beneficial only above a task-risk/size threshold;
- Company OS direct path preferable for tiny local work;
- Company OS overhead not justified and should be simplified;
- evidence insufficient due to variance/confounding.

The program should prefer selective routing if task classes show materially different economics.

## 12. Variance and honesty rules

- Do not generalize from n=1.
- Keep each raw matched result.
- Do not change thresholds after seeing results.
- Record failed benchmark attempts rather than deleting them.
- Record model/provider/version differences.
- Record missing telemetry explicitly as **UNAVAILABLE**.
- Do not claim consumer-plan token usage unless the platform exposes an authoritative measurement.

## 13. Historical reference, not benchmark result

Existing repository-efficiency evidence already reports a matched Company OS engineering comparison between prior internal versions, including a V2 developer cache-read reduction of 20.84% versus V1 and lower reviewer resource use. That is useful historical evidence for repository-navigation improvements, but it is **not** the Direct-vs-Company-OS benchmark defined here.

This protocol exists specifically to answer the broader economic question without redefining the experiment after observing its outcome.
