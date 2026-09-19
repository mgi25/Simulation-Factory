# Independent review of an authorized engineering attempt

You are the reviewer chief_architect. The work was implemented by software_implementation_engineer, in a different session, and you have none of its conversation. Your packet grants no writable path: read, and report.

Work order: wo-stage-timing (77a1e240a19dd20c)
Objective:  Tell me how long each stage of an engineering job took, measured from the job's own recorded transitions, so I can see where the work actually waits.
Worktree:   C:\Users\mgial\OneDrive\Documents\projects\wt-company-os-runner-tasks\eng-stage-timing  (read-only to you)
Diff:       C:\Users\mgial\OneDrive\Documents\projects\company-os-runner-state\runs\wo-stage-timing-0c21b800bd64\run-000001\reviewer-01\diff.patch

## What the work order authorized
  may change:
    - company/engineering
    - tests/test_company_engineering_execution.py
  must not change:
    - ai_platform/policy.py
    - company/agent_contract.schema.yaml
    - company/constitution.md
    - company/integration
    - company/integration/checks.py
    - company/integration/policy.py
    - company/integration/suites.py
    - company/org_registry.yaml
    - company/permissions.yaml
    - company/runtime
    - company/task_handoff.schema.yaml
    - company/validation/no_subagents.py
    - sloped
    - tools

## Acceptance criteria - answer every one
  - The stated objective is implemented: Tell me how long each stage of an engineering job took, measured from the job's own recorded transitions, so I can see where the work actually waits.
  - company-engineering-execution invariant still holds: The authorized work order is immutable; every later stage carries its fingerprint and refuses a mismatch.
  - company-engineering-execution invariant still holds: A review outcome is the worst of the attested and deterministic verdicts, so a reviewer PASS cannot rescue a failed check.
  - company-engineering-execution invariant still holds: The implementer and the reviewer are different employees, routed by disjoint capabilities.
  - company-engineering-execution invariant still holds: The protected governance surface is digested before the work and re-read at review; a change blocks the job.
  - company-engineering-execution invariant still holds: No state means approved and nothing merges, deploys or publishes; the CEO decision is recorded, not acted on.
  - company-engineering-execution invariant still holds: The gate verdict is read from the gate's own report; this subsystem holds no code that can produce one.
  - Every declared test passes: tests/test_company_engineering_execution.py

## What a review is, per the work order
  - read the work order, the diff, the reported tests and the changed paths
  - answer every acceptance criterion with a reference to what satisfies it
  - report one finding per defect, with a severity and a reference
  - change nothing: this packet grants no writable path
  - return pass, changes_required or blocked, and never an approval

## What the implementer reported

```json
{
  "context_refs_used": [
    "module_contract:capsule:company-engineering-execution",
    "test:tests/test_company_engineering_execution.py"
  ],
  "evidence": [
    "company/engineering/lifecycle.py",
    "company/engineering/__init__.py",
    "tests/test_company_engineering_execution.py"
  ],
  "invariants_preserved": [
    "The authorized work order is immutable; every later stage carries its fingerprint and refuses a mismatch.",
    "A review outcome is the worst of the attested and deterministic verdicts, so a reviewer PASS cannot rescue a failed check.",
    "The implementer and the reviewer are different employees, routed by disjoint capabilities.",
    "The protected governance surface is digested before the work and re-read at review; a change blocks the job.",
    "No state means approved and nothing merges, deploys or publishes; the CEO decision is recorded, not acted on.",
    "The gate verdict is read from the gate's own report; this subsystem holds no code that can produce one."
  ],
  "notes": "StageTiming is a frozen dataclass on the read path only; it adds no transition, no state, and no mutation to the job. The existing 95 tests all still pass alongside the 5 new ones (100 total).",
  "outcome": "accepted",
  "rejection_reason": "",
  "summary": "Added StageTiming dataclass and EngineeringJob.stage_timings() method that derives how long a job spent in each state from its own recorded transitions. Each visit to a state gets one timing entry with entered_on, exited_on and days; the current (open) state has exited_on=None and days=0. Five tests cover the full loop, fresh jobs, day arithmetic, open intervals and serialization.",
  "unresolved_risks": [
    "StageTiming measures calendar days (dt.date granularity) because that is what transitions record; sub-day precision is not available from the job's own data."
  ]
}
```

## The receipt the runner measured and Company OS validated

```json
{
  "base_commit": "bf62eaa574f11d3df3bb94f37c0c5de08bc17dae",
  "branch": "eng-stage-timing",
  "commit_sha": "ae703ff78e1c6d48f2f718bf2fea4ab7225b8174",
  "dependencies_added": [],
  "evidence": [
    "company/engineering/lifecycle.py",
    "company/engineering/__init__.py",
    "tests/test_company_engineering_execution.py",
    "commit:ae703ff78e1c6d48f2f718bf2fea4ab7225b8174"
  ],
  "files_changed": [
    "company/engineering/__init__.py",
    "company/engineering/lifecycle.py",
    "tests/test_company_engineering_execution.py"
  ],
  "invariants_preserved": [
    "The authorized work order is immutable; every later stage carries its fingerprint and refuses a mismatch.",
    "A review outcome is the worst of the attested and deterministic verdicts, so a reviewer PASS cannot rescue a failed check.",
    "The implementer and the reviewer are different employees, routed by disjoint capabilities.",
    "The protected governance surface is digested before the work and re-read at review; a change blocks the job.",
    "No state means approved and nothing merges, deploys or publishes; the CEO decision is recorded, not acted on.",
    "The gate verdict is read from the gate's own report; this subsystem holds no code that can produce one."
  ],
  "merge_performed": false,
  "outcome": "accepted",
  "summary": "Added StageTiming dataclass and EngineeringJob.stage_timings() method that derives how long a job spent in each state from its own recorded transitions. Each visit to a state gets one timing entry with entered_on, exited_on and days; the current (open) state has exited_on=None and days=0. Five tests cover the full loop, fresh jobs, day arithmetic, open intervals and serialization.",
  "tests": [
    {
      "command": "tests/test_company_engineering_execution.py",
      "passed": true,
      "summary": "100 passed in 22.67s"
    }
  ],
  "unresolved_risks": [
    "StageTiming measures calendar days (dt.date granularity) because that is what transitions record; sub-day precision is not available from the job's own data."
  ],
  "working_tree_clean": true
}
```

## How this session ends

Your final message must be exactly one JSON object and nothing else - no prose before it, no code fence, no commentary after it.

Keys:
  verdict: "pass", "changes_required" or "blocked"
  criteria: list of {"criterion": <the exact criterion text>, "satisfied": true/false, "evidence_ref": <a POINTER that shows it - one line, at most 200 characters, such as a path, a path with a line span, a symbol name or a commit. Not the reasoning. Required when satisfied is true.>}
  findings: list of {"finding_id": <lowercase id, 3-64 chars>, "severity": "advisory"|"changes_required"|"blocking", "summary": <one sentence>, "evidence_ref": <where to look; the same one-line 200-character pointer>}
  evidence: list of references you read; pointers, at most 32, one line each
  changed_paths_reviewed: the paths you actually reviewed; at most 64
  notes: anything the CEO should know that is not a finding

A satisfied criterion must name what satisfies it. A verdict of `pass` with an unanswered criterion is refused by Company OS, not by me.
Every `evidence_ref` is a POINTER: one line, at most 200 characters. Put the reasoning in `notes` or in a finding's `summary`, and put a place to look in `evidence_ref`. A reference longer than that is refused as content.
You cannot approve anything: `pass` means the work is ready to be read by the CEO, and approval is the CEO's and only the CEO's.
Do not start nested agents. Do not edit, write or run anything.
