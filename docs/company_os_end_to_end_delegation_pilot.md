# The first complete objective-to-result pilot

**Classification: `END_TO_END_DELEGATION_ESCALATED_CORRECTLY`.**

The company took one CEO objective, chose its own work, implemented it,
reviewed it, corrected it, and passed deterministic QA — then stopped one step
from integration on a real separation-of-duties rule. The CEO was not consulted
at any point before that, and the stop is the system working.

**Spend: USD 2.375925 of 6.00.**

---

## 1. CEO report

| | |
|---|---|
| **OBJECTIVE** | Improve the reliability, maintainability or operating efficiency of the Company OS engineering system by completing ONE genuinely useful existing engineering improvement that Company OS itself determines is appropriate. |
| **STATUS** | Escalated at the final step. Work complete, reviewed, QA-green, not integrated. |
| **WHAT THE COMPANY CHOSE** | Disambiguate bare authentication and migration trigger words in `company/engineering/intake.py`. |
| **WHY IT CHOSE IT** | Deterministic eligibility left two candidates of seven. One bounded executive session chose the other one first; normal intake refused that one; management fell back to this one, which intake authorized. |
| **WORK COMPLETED** | `_QUOTED_IDENT` strips backtick-quoted identifiers before routing, so `Fix \`test_authentication_flow\`` no longer escalates to a specialist, while `Run a schema migration` still does. 2 files, +24/-1, 19 new test lines. |
| **RESULT** | Reviewer: pass. Deterministic QA: 11/11 required suites green. Job state `ready_for_approval`. |
| **EXECUTIVE DECISIONS** | CTO (`chief_architect`) selected the candidate through one bounded planning session. |
| **MANAGEMENT DECISIONS** | Engineering Manager (`engineering_delivery_manager`) fell back to the second eligible candidate after intake refused the first, then authorized bounded correction 1 of 1. Neither reached the CEO. |
| **INDEPENDENT REVIEW** | First round: attested pass, deterministic `changes_required`, three findings. Second round: attested pass, deterministic pass. |
| **QUALITY RESULT** | Gate: 11/11 required suites green at `477f9435e876`. Full suite 6 failed / 5168 passed — the six documented pre-existing render-artefact failures, unchanged. |
| **INTERNAL INTEGRATION** | **Not performed.** See the exception below. |
| **EXCEPTIONS** | One, genuine and CEO-reserved. |
| **CEO DECISIONS REQUIRED** | One: who approves integration of work the Chief Architect reviewed. |
| **AI COST** | **2.375925 / 6.00 USD.** Remaining 3.624075. |
| **TIME** | One orchestration pass, 2026-09-20. Four provider sessions, 11m 15s of model wall time. |
| **FINAL OUTCOME** | The delegation chain works. The company cannot finish this particular job because one person holds two of its roles. |

## 2. The exception, in full

Integration was requested by the Engineering Manager and evaluated through
`evaluate_live` under the pilot activation. The answer was **escalate to the
CEO**, and the reason is structural rather than a gap:

- `cto` **does** hold `approve_integration_merge` at MEDIUM risk.
- The CTO seat's employee is `chief_architect`.
- `chief_architect` was the **independent reviewer** of this work.
- A seat is disqualified from deciding work its own employee reviewed, checked
  before any ceiling. So the chain walked past the CTO.
- The next seat up, `coo`, does not hold `approve_integration_merge`.
- Above the COO is the CEO.

Probed both ways, to be sure it is the rule and not a missing grant:

```
reviewer=chief_architect   -> escalate, actor=ceo
reviewer=someone_else      -> approved, actor=cto
```

**The company has one employee who is both its only engineering reviewer and
the holder of its integration authority.** Every job reviewed by the Chief
Architect will escalate at integration, forever, until either a second reviewer
exists or some other seat holds integration authority. That is the CEO decision
this pilot surfaced, and it is worth more than the code change.

No approval loop was started. The run stopped, recorded, and reported.

## 3. What each layer actually did

| Layer | Did |
|---|---|
| **CEO** | Set one objective and one envelope. Made no other decision. Is now asked one question. |
| **EXECUTIVE** | CTO selected `reserved-screening-negation-blindness` from two eligible candidates in one bounded session, with stated value, risk and resource reasoning. |
| **MANAGEMENT** | Engineering Manager moved to the second eligible candidate when intake refused the first, and authorized bounded correction 1 of 1 after the reviewer asked for changes. |
| **WORKER** | Two developer sessions (`software_implementation_engineer`), each bounded to two files, each producing a receipt. Never chose what to work on. |
| **REVIEWER** | Two reviewer sessions (`chief_architect`), read-only, structured verdicts. Raised the over-match defect that the correction fixed. |
| **DETERMINISTIC CONTROL** | Intake refused the executive's first choice. Receipt validation refused the first attempt. Review adjudication took the worse of attested and deterministic. The gate ran 11 suites. `evaluate_live` refused the integration. **Every refusal in this pilot came from deterministic code.** |
| **OUTER ORCHESTRATION** | Composed the branch, started the runner, and made one configuration error (below). Chose no work, wrote no code, approved nothing. |

## 4. The orchestration error, disclosed

The first developer attempt was run with `--no-push`, chosen to keep the run
away from the remote. The receipt protocol requires the work branch to be
verifiable on the remote, so the developer recorded `outcome: rejected`,
`remote_verified: false` — despite its own tests passing 183/183 and the
reviewer attesting pass.

That failure was mine, not the company's. It cost **USD 0.860478** in a
developer session whose work was sound.

The remedy taken was *not* to edit the receipt — it is the developer's record —
and *not* to spend the bounded correction on it alone. The work branch was
pushed (an ordinary internal feature branch, not `main`, not canonical, not a
protected ref, not a deployment or a publication), and the correction was
authorized on its own merits: the reviewer had raised two genuine defects
beside the protocol failure.

**One further deviation, also mine.** The company's resource strategy
recommended the `strongest` tier for this work order — reasoning class D,
because the word *migration* in the title triggers specialist depth. The CEO
brief said "ONE STANDARD developer", so both developer sessions were pinned to
Sonnet. The runner recorded this honestly as `model_source: operator` rather
than `tier:strongest`.

## 5. How the work was chosen

Seven candidates in the register. Deterministic eligibility, under an
engineering / MEDIUM / USD 6.00 envelope:

| Candidate | Result |
|---|---|
| `auth-migration-classifier-ambiguity` | **eligible** |
| `reserved-screening-negation-blindness` | **eligible** |
| `deployment-policy-gap` | rejected: status_open, risk_within_ceiling |
| `intake-unfalsifiable-acceptance-criteria` | rejected: status_open |
| `provider-usage-event-identifier` | rejected: department_permitted, status_open |
| `runner-blocked-attempt-repo-dir` | rejected: capsule_owned |
| `runner-zero-required-tests-policy` | rejected: capsule_owned, status_open |

Two eligible, so one bounded executive session ran — the deterministic rungs
(zero candidates, one candidate) never call a model. It chose
`reserved-screening-negation-blindness`:

> "The negation blindness is a documented recurrent defect that defeated
> previous hardening attempts (da4f3ce); screen_credentials already handles
> negation correctly, so this is alignment work on a known-good pattern. The
> classifier ambiguity is valid but secondary — a vocabulary coverage gap
> rather than a systemic rule defect."

**Then normal intake refused it**, because the work order derived from that
candidate is titled *"Teach reserved and **credential** screening to respect
negation"* and `screen_credentials()` fires on the word *credential*. The
candidate describes a defect whose symptom blocks the work order proposing to
fix it.

Management moved to the second eligible candidate. Intake authorized it. **No
wording was changed to get past intake**, and no developer session had started,
so this is ordinary planning behaviour rather than a retry.

## 6. Spend

| Session | Role | Model | Turns | Wall | Cost |
|---|---|---|---|---|---|
| `f6f8…` | executive planner | haiku-4.5 | 1 | 22 s | 0.024266 |
| `9d8ff23f` | developer, attempt 1 | sonnet | 12 | 270 s | 0.860478 |
| `dacc1609` | reviewer, round 1 | sonnet | 12 | 121 s | 0.385341 |
| `…` | developer, correction | sonnet | 22 | 188 s | 0.798134 |
| `…` | reviewer, round 2 | sonnet | 9 | 96 s | 0.307706 |
| | | | | **TOTAL** | **2.375925 / 6.00** |

Each session ran under a provider-enforced `--max-budget-usd` ceiling of 3.00
from the consumer profile. The reviewer start was checked against remaining
budget before it began, as the brief requires.

## 7. A defect this pilot found in the planning layer

The first work order passed intake and then failed at the runner with *"base
commit is not in this repository"*. A `WorkOrderProposal` carried acceptance
criteria, scope, risk and budget — and never said which checkout it was
planning against. `authorized_branch` and `base_commit` are now fields on the
proposal. Found by running the chain, not by reading it.

## 8. What did not happen

- `main` is untouched at `8b1022a`.
- Canonical is at `92b308c`, `mode: shadow`, and carries **no** pilot runtime.
- Nothing was deployed or published.
- No authority was expanded, no policy changed, no organization restructured.
- The pilot activation is objective-bound, expires 2026-09-27, and grants
  nothing after it.
- `PROTECTED_REFS` still holds `main`, `master` and `company-os-v1-bootstrap`,
  and was not altered.
