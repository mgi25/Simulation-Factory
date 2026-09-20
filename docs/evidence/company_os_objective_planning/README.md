# Evidence — objective-to-work planning

Every file here was produced by running the shipped CLIs against the shipped
seed register. Nothing was hand-written to look like output. **No worker,
reviewer or executive model session ran; total model spend for this pass is
$0.00.**

## The replay that motivated the capability

| File | What it shows |
|---|---|
| `replay_objective.json` | the failed pilot's CEO objective and envelope, verbatim, at the original LOW ceiling |
| `replay_result.json` | `no_eligible_work_candidate` — every candidate measured, each rejection naming the check it failed |

The same objective text produced `"outcome": "authorized"` before this pass
(`docs/evidence/company_os_first_live_delegation_pilot/phase1_probe_intake_result.json`).
It now produces `planning_required` at intake and
`no_eligible_work_candidate` at planning.

## The positive path, end to end

| File | What it shows |
|---|---|
| `medium_objective.json` | the same envelope with the ceiling raised to MEDIUM |
| `medium_result.json` | **escalated** — two candidates are equally eligible and the system refuses to guess between them |
| `medium_selected.json` | a named preference resolves it; the planning decision records the executive, the manager, the alignment and what was rejected |
| `derived_work_order_request.json` | the bounded work order that selection produced |
| `derived_work_order_intake.json` | intake **refuses** it — see below |
| `medium_selected_b.json`, `derived_work_order_request_b.json` | the other eligible candidate, selected |
| `derived_work_order_intake_b.json` | `"outcome": "authorized"`, scoped to the candidate's declared paths |

## The refusal worth reading

`derived_work_order_intake.json` refuses the work order for
`reserved-screening-negation-blindness` with:

> the objective names credential material: credential

The candidate's title is *"Teach reserved and credential screening to respect
negation"*. The word `credential` matched, in an objective about the screening
code itself — **which is precisely the defect that candidate describes.** The
bug caught the work order proposing to fix it.

That is the strongest available evidence that the seeded register holds real
problems rather than plausible-sounding ones, and it is why the clean
end-to-end demonstration uses the sibling candidate instead.

## State of the system

| File | What it shows |
|---|---|
| `candidate_register.txt` | all seven seeded candidates, with each blocker spelled out |
| `policy_after_select_work.txt` | the policy loading with `select_work` granted; seats and ceilings otherwise unchanged |
| `chart.txt` | the hierarchy, including the two deterministic controls |
| `planning_tests.txt` | 90 passed |

## How to reproduce

```
python -m company.delegation candidates
python -m company.delegation plan --objective-file <this dir>/replay_objective.json --as-of 2026-09-20
python -m company.delegation plan --objective-file <this dir>/medium_objective.json \
    --prefer auth-migration-classifier-ambiguity --as-of 2026-09-20
python -m company.engineering request --request-file <this dir>/derived_work_order_request_b.json \
    --state-dir <a scratch dir> --repo-root . --as-of 2026-09-20
```
