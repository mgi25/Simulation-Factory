# The final end-to-end delegation pilot

**Classification: `NO_EXECUTABLE_WORK_CANDIDATE`. USD 0.00 of 6.00 spent.**

The company was given one objective and an envelope, chose its own work, and
stopped before any paid session because the one piece of work it was allowed to
choose cannot be authorized. Nothing was reworded to get past that.

---

## 1. What the CEO asked for

> Improve the reliability, maintainability, or operating efficiency of the
> Company OS by completing ONE useful engineering improvement selected by the
> company itself.

Engineering, MEDIUM risk ceiling, USD 6.00 total, one developer, one
independent reviewer, at most one bounded correction. No standing grant.

## 2. What the company chose, and how

Deterministically, and without a model. Seven candidates were considered and
six failed eligibility:

| candidate | why not |
|---|---|
| `auth-migration-classifier-ambiguity` | completed — canonicalized earlier in this pass by CEO exception |
| `intake-unfalsifiable-acceptance-criteria` | completed |
| `deployment-policy-gap` | blocked, and HIGH risk exceeds the MEDIUM ceiling |
| `provider-usage-event-identifier` | blocked, and `ai_platform` is outside the envelope's departments |
| `runner-zero-required-tests-policy` | blocked on a policy decision nobody has taken |
| `runner-blocked-attempt-repo-dir` | fails `capsule_owned` — **nothing owns `tools/`** |
| `reserved-screening-negation-blindness` | **eligible** |

One eligible candidate means the one-candidate rung: arithmetic, not judgment.
No executive planning session was opened and no model was called, so planning
cost USD 0.00. Neither this orchestration session nor any developer picked the
work.

## 3. Why it stopped

The selected candidate went to normal intake with its title unchanged:

> Teach reserved and credential screening to respect negation

Intake returned `decision_required`:

> the objective names credential material: credential
> Credential access is an escalation, not a work-order scope. Authorize it
> explicitly and separately, or restate the objective without it.

`screen_credentials()` matches the bare word `credential` anywhere in the
objective text. The candidate's *subject* is credential screening. **The defect
blocks the authorization of its own fix.**

Three probes pin this down (`deadlock_analysis.json`):

- As selected: `decision_required`.
- With the word `credential` deleted: `authorized`. This is a **diagnostic, not
  a change**. Deleting the word from a candidate that exists to fix credential
  screening is exactly the wording hack this pilot forbids.
- The candidate's own claim is true: *"Refactor the retry helper. This work does
  not touch credentials."* — a sentence that explicitly denies the trigger —
  escalates identically to *"Rotate the production credentials."* The screening
  is negation-blind, as the candidate says it is.

## 4. Why management had nowhere to move

The rule is that management may consider another planning-eligible candidate
before a developer starts. It could not: the table above has exactly one
eligible row. Two candidates are completed, three are blocked or out of
department, and the last fails capsule ownership.

So the honest answer is `NO_EXECUTABLE_WORK_CANDIDATE`, and the correct action
is to stop without spending anything on a developer or a reviewer.

## 5. What was proved before any of this

Twenty deterministic checks ran before a cent could be spent
(`pre_spend_validation.json`), all passing.

The ordinary chain, each request raised by the seat that actually raises it:

| action | raised by | decided by | CEO |
|---|---|---|---|
| `approve_code_change` | developer | `engineering_manager` | no |
| `approve_test_progression` | developer | `engineering_manager` | no |
| `approve_review_outcome` | reviewer | `engineering_manager` | no |
| `request_bounded_correction` | reviewer | `engineering_manager` | no |
| `approve_integration_merge` | manager | `cto` | no |

And the refusals: QA failure blocks test progression; an explicit override of
an independent control is refused; all three protected refs (`main`, `master`,
`company-os-v1-bootstrap`) are blocked; HIGH risk is above the envelope;
deployment, staging release and production render are outside the pilot; spend
outside the envelope is refused; the first bounded correction is permitted and
the second is the CEO's call; architecture review still puts the CTO in
self-conflict and still reaches the CEO; and with no activation the default
authorizes nothing.

Two of those probes were wrong before they were right, which is worth recording
because both looked like product defects:

- QA is gated at `APPROVE_TEST_PROGRESSION`, not at integration. Probing
  integration with a failed QA proves nothing. Integration ordering is the
  runner's job, so that is recorded as an observation rather than dressed up as
  a gate.
- The correction ceiling is decided by `authorize_correction` with
  `used >= ceiling`, not by the request-shaped gate in `pilot.py` that reads
  `corrections_used > ceiling`. Testing the wrong one made a working ceiling
  look like an off-by-one.

## 6. What the CEO is being asked to decide

One thing, and it is not urgent:

**The engineering backlog has no executable item.** The only eligible candidate
is unauthorizable by the defect it describes. There are three ways out, all of
them CEO calls because each widens something:

1. Authorize `reserved-screening-negation-blindness` explicitly as an
   exception, the way the classifier fix was authorized in this same pass. The
   work itself is routine and its scope ceiling is two files.
2. Give `tools/` a capsule owner, which makes `runner-blocked-attempt-repo-dir`
   eligible and gives the company a second piece of routine work. This is an
   ownership decision, not an engineering one.
3. Authorize a bounded discovery run to find new candidates. Not taken here:
   discovery is the zero-eligible rung and one candidate was eligible.

Nothing in this pilot took any of them.

## 7. End state

- Canonical `company-os-v1-bootstrap` at `13abeb1`, `mode: shadow`, no pilot
  module present. Untouched by this pilot.
- `main` at `8b1022a`. Untouched.
- Live delegation remains pilot-only, on this branch, activated nowhere.
- No general autonomy. No second objective.
- USD 0.00 spent.
