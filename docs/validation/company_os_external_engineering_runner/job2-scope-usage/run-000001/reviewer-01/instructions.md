# Independent review of an authorized engineering attempt

You are the reviewer chief_architect. The work was implemented by software_implementation_engineer, in a different session, and you have none of its conversation. Your packet grants no writable path: read, and report.

Work order: wo-scope-usage (8d57bdf95a8685de)
Objective:  For one work order, show me which of the paths it was authorized to change the work actually touched, so I can see how much of the scope I granted was used.
Worktree:   C:\Users\mgial\OneDrive\Documents\projects\wt-company-os-runner-tasks\eng-scope-usage  (read-only to you)
Diff:       C:\Users\mgial\OneDrive\Documents\projects\company-os-runner-state\runs\wo-scope-usage-060a017cc09c\run-000001\reviewer-01\diff.patch

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
  - The stated objective is implemented: For one work order, show me which of the paths it was authorized to change the work actually touched, so I can see how much of the scope I granted was used.
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
    "company/engineering/result.py",
    "company/engineering/__init__.py",
    "tests/test_company_engineering_execution.py"
  ],
  "invariants_preserved": [
    "The authorized work order is immutable; ScopeUsage is derived at read time from the existing authorized_paths and changed_files fields, adding no mutable state.",
    "A review outcome is the worst of the attested and deterministic verdicts; no review logic was changed.",
    "The implementer and the reviewer are different employees, routed by disjoint capabilities; routing logic was not touched.",
    "The protected governance surface is digested before the work and re-read at review; protected.py was not modified.",
    "No state means approved and nothing merges, deploys or publishes; the result still reports and does not act.",
    "The gate verdict is read from the gate's own report; gate_evidence.py was not modified.",
    "The fingerprint round-trip test still passes; ScopeUsage is computed, not stored, so the fingerprint is unchanged."
  ],
  "notes": "ScopeUsage is a frozen dataclass with a from_result() classmethod. It uses first-match prefix semantics: a changed file is assigned to the first authorized path it falls under (authorized_paths are sorted, so shortest prefixes come first). The feature adds no new dependencies and no stored state.",
  "outcome": "accepted",
  "rejection_reason": "",
  "summary": "Added ScopeUsage dataclass and scope_usage() method to EngineeringResult, plus a SCOPE USAGE section in the CEO render_text() page. For each authorized path the result now shows [USED] or [UNUSED] with file counts, so the CEO can see how much of the granted scope was actually touched. Six new tests cover the feature including exact matches, empty changes, and the render output.",
  "unresolved_risks": [
    "A changed file that falls outside all authorized paths (e.g. from a path scope violation) is not shown under any authorized path in the scope usage section. This is correct behaviour but a reviewer should verify it reads clearly."
  ]
}
```

## The receipt the runner measured and Company OS validated

```json
{
  "base_commit": "89915ce85eae30df3b3d12ad7f946413be97a3da",
  "branch": "eng-scope-usage",
  "commit_sha": "be5255dfbacc723da8e5371d8076c0f6558b06a1",
  "dependencies_added": [],
  "evidence": [
    "company/engineering/result.py",
    "company/engineering/__init__.py",
    "tests/test_company_engineering_execution.py",
    "commit:be5255dfbacc723da8e5371d8076c0f6558b06a1"
  ],
  "files_changed": [
    "company/engineering/__init__.py",
    "company/engineering/result.py",
    "tests/test_company_engineering_execution.py"
  ],
  "invariants_preserved": [
    "The authorized work order is immutable; ScopeUsage is derived at read time from the existing authorized_paths and changed_files fields, adding no mutable state.",
    "A review outcome is the worst of the attested and deterministic verdicts; no review logic was changed.",
    "The implementer and the reviewer are different employees, routed by disjoint capabilities; routing logic was not touched.",
    "The protected governance surface is digested before the work and re-read at review; protected.py was not modified.",
    "No state means approved and nothing merges, deploys or publishes; the result still reports and does not act.",
    "The gate verdict is read from the gate's own report; gate_evidence.py was not modified.",
    "The fingerprint round-trip test still passes; ScopeUsage is computed, not stored, so the fingerprint is unchanged."
  ],
  "merge_performed": false,
  "outcome": "accepted",
  "summary": "Added ScopeUsage dataclass and scope_usage() method to EngineeringResult, plus a SCOPE USAGE section in the CEO render_text() page. For each authorized path the result now shows [USED] or [UNUSED] with file counts, so the CEO can see how much of the granted scope was actually touched. Six new tests cover the feature including exact matches, empty changes, and the render output.",
  "tests": [
    {
      "command": "tests/test_company_engineering_execution.py",
      "passed": true,
      "summary": "101 passed in 18.41s"
    }
  ],
  "unresolved_risks": [
    "A changed file that falls outside all authorized paths (e.g. from a path scope violation) is not shown under any authorized path in the scope usage section. This is correct behaviour but a reviewer should verify it reads clearly."
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
