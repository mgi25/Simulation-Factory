# Evidence — executive planning and bounded discovery

Produced by running the shipped code and one real provider session. **Total
model spend for this phase: USD 0.028659.**

| File | What it shows |
|---|---|
| `low_objective.json` | the failed pilot's CEO objective and envelope, at its original LOW ceiling |
| `low_replay_ceo_report.txt` | `no_eligible_work_candidate` after discovery ran and proposed nothing — at zero model cost |
| `low_replay.json` | the full run record: every candidate, the named check each failed, discovery provenance |
| `planning_brief.json` | exactly what the executive planner was given: 2,876 characters, no source, no paths to read |
| `planner_prompt.txt` | the instructions plus the brief, as submitted |
| `planner_session_raw.json` | the real session envelope: answer, usage, cost, turns, model |
| `medium_objective.json` | the same envelope at a MEDIUM ceiling, where two candidates qualify |
| `medium_replay_ceo_report.txt` | the executive choice, its five reasoning fields, and the session telemetry |
| `medium_replay.json` | the full run record for the selection |
| `medium_plan_run_cli.txt` | the same result through `python -m company.delegation plan-run` |

## The session

```
model            claude-haiku-4-5-20251001 (anthropic)
input / output   9 / 2612 tokens
cache create     12472      cache read 0
cost             0.028659 USD   of a 1.50 USD ceiling
wall / turns     25.4s / 1
tool calls       0
```

Invoked with `--max-budget-usd 1.50`, a ceiling the provider enforces rather
than one the session agrees to, and with every tool disallowed. It had no
authority: the strongest thing it produced was a recorded recommendation that
`assert_choice_within` then accepted.

**A note on the numbers.** The brief is ~1,100 tokens and the session billed
12,472 cache-creation tokens. The gap is CLI scaffolding, not the brief.
Bounding the planner's context bought less than it appears to, and future work
on planning cost should start there. Recorded rather than averaged away.

## Reproducing

```
python -m company.delegation plan-run --objective-file low_objective.json \
    --as-of 2026-09-20 --discover

python -m company.delegation plan-run --objective-file medium_objective.json \
    --as-of 2026-09-20 --planner-answer-file planner_session_raw.json
```

The second replays the recorded session answer, so reproducing costs nothing.
`test_the_real_session_answer_is_accepted_by_the_deterministic_contract` pins
the same answer in the suite for the same reason.
