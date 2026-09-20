# Authorized engineering work order

You are the session Company OS issued packet 1f146021562d64ef to, acting as the employee software_implementation_engineer. This is attempt 1 of 3 the work order authorizes.

Work order: wo-attempt-ledger (4418d6288e06d39d)
Objective:  Show me, for one engineering job, every developer attempt that was made and what each one cost, so I can tell whether an automated run is converging or thrashing without reading the whole history.
Branch:     eng-attempt-ledger
Base commit:7ca7edd9153b633af25f99620f7860b09b806342
Worktree:   C:\Users\mgial\OneDrive\Documents\projects\wt-company-os-runner-tasks\eng-attempt-ledger

## You may change exactly these paths
  - company/engineering
  - tests/test_company_engineering_execution.py

## You may not touch these, for any reason
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

Every path you change is checked against those two lists after you finish, by reading git rather than by reading what you say. A change outside the first list, or inside the second, makes the whole attempt BLOCKED and it is escalated to the CEO rather than retried.

## Acceptance criteria - all of them, each answerable with a reference
  - The stated objective is implemented: Show me, for one engineering job, every developer attempt that was made and what each one cost, so I can tell whether an automated run is converging or thrashing without reading the whole history.
  - company-engineering-execution invariant still holds: The authorized work order is immutable; every later stage carries its fingerprint and refuses a mismatch.
  - company-engineering-execution invariant still holds: A review outcome is the worst of the attested and deterministic verdicts, so a reviewer PASS cannot rescue a failed check.
  - company-engineering-execution invariant still holds: The implementer and the reviewer are different employees, routed by disjoint capabilities.
  - company-engineering-execution invariant still holds: The protected governance surface is digested before the work and re-read at review; a change blocks the job.
  - company-engineering-execution invariant still holds: No state means approved and nothing merges, deploys or publishes; the CEO decision is recorded, not acted on.
  - company-engineering-execution invariant still holds: The gate verdict is read from the gate's own report; this subsystem holds no code that can produce one.
  - Every declared test passes: tests/test_company_engineering_execution.py

## Tests the work order requires
  - tests/test_company_engineering_execution.py

Run them yourself and iterate until they pass. They are run again afterwards, at the commit, and a failure there ends the attempt.

## Stop and say so instead of doing any of these
  - changing architecture outside the authorized paths
  - adding a dependency the work order did not authorize
  - reading or using any credential, token or secret
  - widening the objective beyond what the work order states
  - editing any protected governance path
  - deciding a business question the work order leaves open
  - any destructive operation on repository or company data
  - merging, deploying, publishing or tagging anything

## How this session ends

Do NOT run `git commit`, `git push`, `git merge`, `git tag` or `git rebase`. The runner commits what you leave in the working tree, after it has checked it against the lists above. Leave the work in the tree.
Do NOT start nested agents or subagents. Constitution rule 2 forbids them.
Do NOT read, print or use any credential, token or environment secret.
Work only inside the worktree above.

Write your report to: C:\Users\mgial\OneDrive\Documents\projects\company-os-runner-state\runs\wo-attempt-ledger-93c5b79f0e3b\run-000001\developer-01\report.json

It must be one JSON object with exactly these keys:
  outcome: "accepted" if the work order is implemented, "rejected" if not
  summary: two or three sentences: what you changed and why, for the next reader
  rejection_reason: required when outcome is rejected; empty otherwise
  invariants_preserved: list of strings: what you were careful not to break
  unresolved_risks: list of strings: what a reviewer should look at hardest
  evidence: list of repository paths or references a reviewer can open
  context_refs_used: list of the packet's context reference keys you actually used
  notes: anything else worth recording; may be empty

That report is the only thing you return. Everything else in the receipt - the commit, the changed files, the test results - is measured from the repository, not taken from you.

## The packet Company OS issued, verbatim

```json
{
  "acceptance_criteria": [
    "The stated objective is implemented: Show me, for one engineering job, every developer attempt that was made and what each one cost, so I can tell whether an automated run is converging or thrashing without reading the whole history.",
    "company-engineering-execution invariant still holds: The authorized work order is immutable; every later stage carries its fingerprint and refuses a mismatch.",
    "company-engineering-execution invariant still holds: A review outcome is the worst of the attested and deterministic verdicts, so a reviewer PASS cannot rescue a failed check.",
    "company-engineering-execution invariant still holds: The implementer and the reviewer are different employees, routed by disjoint capabilities.",
    "company-engineering-execution invariant still holds: The protected governance surface is digested before the work and re-read at review; a change blocks the job.",
    "company-engineering-execution invariant still holds: No state means approved and nothing merges, deploys or publishes; the CEO decision is recorded, not acted on.",
    "company-engineering-execution invariant still holds: The gate verdict is read from the gate's own report; this subsystem holds no code that can produce one.",
    "Every declared test passes: tests/test_company_engineering_execution.py"
  ],
  "automatic_context_refs": [
    "module_contract:capsule:ai-platform",
    "module_contract:capsule:company-knowledge-capsules",
    "module_contract:capsule:company-knowledge-store",
    "module_contract:capsule:company-runtime",
    "module_contract:capsule:company-validation"
  ],
  "completion_protocol": [
    "implement the objective, changing only allowed paths",
    "run every required test and report the result",
    "commit the work",
    "push the assigned branch",
    "verify the exact remote SHA matches the local commit",
    "do not merge",
    "return a compact handoff receipt"
  ],
  "constraints": [],
  "context_cache_key": "6508657d5996fd7c",
  "context_fingerprint": "abe6bd5b5f08fe1f",
  "context_refs": [
    {
      "digest": "",
      "kind": "module_contract",
      "reason": "owns company/engineering for task path company/engineering",
      "ref": "capsule:company-engineering-execution",
      "span": null
    },
    {
      "digest": "",
      "kind": "module_contract",
      "reason": "dependency of company-engineering-execution",
      "ref": "capsule:ai-platform",
      "span": null
    },
    {
      "digest": "",
      "kind": "module_contract",
      "reason": "dependency of company-engineering-execution",
      "ref": "capsule:company-knowledge-capsules",
      "span": null
    },
    {
      "digest": "",
      "kind": "module_contract",
      "reason": "dependency of company-engineering-execution",
      "ref": "capsule:company-knowledge-store",
      "span": null
    },
    {
      "digest": "",
      "kind": "module_contract",
      "reason": "dependency of company-engineering-execution",
      "ref": "capsule:company-runtime",
      "span": null
    },
    {
      "digest": "",
      "kind": "module_contract",
      "reason": "dependency of company-engineering-execution",
      "ref": "capsule:company-validation",
      "span": null
    },
    {
      "digest": "",
      "kind": "test",
      "reason": "declared test of the owning capsule",
      "ref": "tests/test_company_engineering_execution.py",
      "span": null
    }
  ],
  "employee": "software_implementation_engineer",
  "evidence_required": true,
  "executor": "claude_code",
  "expected_base_commit": "7ca7edd9153b633af25f99620f7860b09b806342",
  "expected_branch": "eng-attempt-ledger",
  "explicit_context_refs": [
    "module_contract:capsule:company-engineering-execution",
    "test:tests/test_company_engineering_execution.py"
  ],
  "no_subagents": true,
  "objective": "Show me, for one engineering job, every developer attempt that was made and what each one cost, so I can tell whether an automated run is converging or thrashing without reading the whole history.",
  "path_scope": {
    "allowed": [
      "company/engineering",
      "tests/test_company_engineering_execution.py"
    ],
    "forbidden": [
      "ai_platform/policy.py",
      "company/agent_contract.schema.yaml",
      "company/constitution.md",
      "company/integration",
      "company/integration/checks.py",
      "company/integration/policy.py",
      "company/integration/suites.py",
      "company/org_registry.yaml",
      "company/permissions.yaml",
      "company/runtime",
      "company/task_handoff.schema.yaml",
      "company/validation/no_subagents.py",
      "sloped",
      "tools"
    ]
  },
  "reasoning_class": "D",
  "required_tests": [
    "tests/test_company_engineering_execution.py"
  ],
  "resource_class": "specialist_reasoning",
  "task_id": "wo-attempt-ledger",
  "version": 1
}
```
