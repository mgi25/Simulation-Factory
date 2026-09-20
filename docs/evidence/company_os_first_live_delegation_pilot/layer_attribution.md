# Who did what — layer attribution

Phase 14 requires that the evidence distinguish the layers. In a run that
stopped at Phase 1, four of the five layers did nothing, and that emptiness is
the finding.

| Layer | Acted? | What it did |
|---|---|---|
| **CEO** | yes | Set one objective and one operating envelope (department, LOW risk ceiling, $6.00, internal target, one correction, short expiry). Approved no work order. Made no routine decision. |
| **EXECUTIVE / MANAGEMENT** | **no** | The `coo`, `cto` and `engineering_manager` seats are filled, active and funded. None was asked to decide anything: the decision the objective required — *which work* — is not a representable act, so it could not be put to them. No `LivePilotDecisionRecord` was produced. |
| **WORKER** | **no** | No developer session started. No provider call was made in a worker role. $0.00 spent. |
| **INDEPENDENT CONTROL** | **no** | No reviewer, no deterministic QA, no integration gate. Nothing reached them. (`deterministic_qa` and `integration_gate` are both `vacant` seats in the current registry, which would have needed resolving before Phase 6 regardless.) |
| **OUTER ORCHESTRATION** | yes, and only here | Read the pilot lineage; enumerated the action set; ran `pilot-policy`, `policy` and `chart`; submitted the CEO objective to deterministic intake as a probe; wrote this evidence. |

## The line that was deliberately not crossed

The outer orchestration session did **not** select a task.

Candidate work certainly exists in the repository — the objective's premise is
sound. Naming one here would have produced a run that looked like a successful
pilot and proved nothing, because the planning step the pilot exists to
demonstrate would have been performed by the orchestration session rather than
by Company OS management. The authorization forbids exactly that, and the
prohibition is what makes the Phase 1 result meaningful.

## Commands run, all read-only

```
python -m company.delegation pilot-policy      -> pilot_policy.txt
python -m company.delegation policy            -> delegation_policy.txt
python -m company.delegation chart
python -m company.engineering request ...      -> phase1_probe_intake_result.json
```

The intake probe wrote records only to a session scratchpad directory outside
the repository. No Company OS state directory in the repository was written, no
pilot activation token was created, and no tracked file outside this evidence
bundle and the report was modified.
