# Independent review of an authorized engineering attempt

You are the reviewer chief_architect. The work was implemented by software_implementation_engineer, in a different session, and you have none of its conversation. Your packet grants no writable path: read, and report.

Work order: wo-attempt-ledger (4418d6288e06d39d)
Objective:  Show me, for one engineering job, every developer attempt that was made and what each one cost, so I can tell whether an automated run is converging or thrashing without reading the whole history.
Worktree:   C:\Users\mgial\OneDrive\Documents\projects\wt-company-os-runner-tasks\eng-attempt-ledger  (read-only to you)
Diff:       C:\Users\mgial\OneDrive\Documents\projects\company-os-runner-state\runs\wo-attempt-ledger-93c5b79f0e3b\run-000003\reviewer-01\diff.patch

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
  - The stated objective is implemented: Show me, for one engineering job, every developer attempt that was made and what each one cost, so I can tell whether an automated run is converging or thrashing without reading the whole history.
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
    "company/engineering/attempt_ledger.py",
    "company/engineering/__init__.py",
    "tests/test_company_engineering_execution.py"
  ],
  "invariants_preserved": [
    "The authorized work order is immutable; the new module is read-only and writes nothing to any store",
    "A review outcome is the worst of the attested and deterministic verdicts; no review logic was changed",
    "The implementer and the reviewer are different employees; routing logic is untouched",
    "The protected governance surface is digested before the work and re-read at review; no governance code changed",
    "No state means approved and nothing merges, deploys or publishes; the ledger is a read-only projection",
    "The gate verdict is read from the gate's own report; no gate code was changed"
  ],
  "notes": "The ledger is purely additive \u2014 one new module, its re-export, and four tests. No existing module was modified except the package __init__.py (imports and __all__) and the test file (imports and new test functions).",
  "outcome": "accepted",
  "rejection_reason": "",
  "summary": "Added company/engineering/attempt_ledger.py with AttemptLedger, AttemptLedgerEntry and build_attempt_ledger(), which joins the engineering, execution and usage stores to produce a per-attempt cost view for one job. Exported from __init__.py and covered by four new tests in the existing suite (100 total pass).",
  "unresolved_risks": [
    "The usage-record-to-attempt correlation assumes records appear in sequence order (1-based index); a store with gaps or out-of-order records would mis-correlate",
    "Cost fields (input_units, output_units, duration_s) may all be None when the provider did not expose them; the ledger propagates None honestly but the CEO surface must handle it"
  ]
}
```

## The receipt the runner measured and Company OS validated

```json
{
  "base_commit": "7ca7edd9153b633af25f99620f7860b09b806342",
  "branch": "eng-attempt-ledger",
  "commit_sha": "d681c5a1b970470bd98c54f352f4f969f97f5ab2",
  "dependencies_added": [],
  "evidence": [
    "company/engineering/attempt_ledger.py",
    "company/engineering/__init__.py",
    "tests/test_company_engineering_execution.py",
    "commit:d681c5a1b970470bd98c54f352f4f969f97f5ab2"
  ],
  "files_changed": [
    "company/engineering/__init__.py",
    "company/engineering/attempt_ledger.py",
    "tests/test_company_engineering_execution.py"
  ],
  "invariants_preserved": [
    "The authorized work order is immutable; the new module is read-only and writes nothing to any store",
    "A review outcome is the worst of the attested and deterministic verdicts; no review logic was changed",
    "The implementer and the reviewer are different employees; routing logic is untouched",
    "The protected governance surface is digested before the work and re-read at review; no governance code changed",
    "No state means approved and nothing merges, deploys or publishes; the ledger is a read-only projection",
    "The gate verdict is read from the gate's own report; no gate code was changed"
  ],
  "merge_performed": false,
  "outcome": "accepted",
  "summary": "Added company/engineering/attempt_ledger.py with AttemptLedger, AttemptLedgerEntry and build_attempt_ledger(), which joins the engineering, execution and usage stores to produce a per-attempt cost view for one job. Exported from __init__.py and covered by four new tests in the existing suite (100 total pass).",
  "tests": [
    {
      "command": "tests/test_company_engineering_execution.py",
      "passed": true,
      "summary": "100 passed in 20.08s"
    }
  ],
  "unresolved_risks": [
    "The usage-record-to-attempt correlation assumes records appear in sequence order (1-based index); a store with gaps or out-of-order records would mis-correlate",
    "Cost fields (input_units, output_units, duration_s) may all be None when the provider did not expose them; the ledger propagates None honestly but the CEO surface must handle it"
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
