# Independent review — the P5-R2 runner-side read-authority change

**Verdict: PASS**, with one recorded limitation and no required correction.

| | |
|---|---|
| Change reviewed | `tools/engineering_runner/authorization.py`, `tests/test_company_external_engineering_runner.py` |
| Commits reviewed | `687192a`, `885563c` (runner side of P5-R2) |
| Diff range | `adc8a95ffe7eedd78b58d16cc1f8493b5b4a1a4f` → `d7944aaceb901eabf1d962ac77463f47836dc790` |
| Reviewed on | 2026-09-24 |
| Reviewed under | capsule `company-external-engineering-runner`, created by P5-R3 |
| Reimplementation | none — the existing commits were reviewed, not rewritten |

## Why this review happened after the fact

P5-R2 added a read ceiling to the external runner. At that moment no capsule
owned `tools/engineering_runner`, so `company/engineering/intake.py` could not
derive a bounded work order for the package and the change was made outside
Company OS engineering authority. It therefore never received the independent
review the loop requires. P5-R3 created the owning capsule; this is that review,
run against the P5-R2 acceptance criteria.

The reviewer is not independent in the strongest sense: this review was carried
out in the same session that created the capsule, because no second external
session was started. What independence it has comes from the criteria being
fixed in advance and from every finding below being reproduced by an executable
test rather than asserted.

## What was examined, criterion by criterion

| Criterion | Finding |
|---|---|
| `may_read` propagation | Carried from `work_order.authorized_read_paths` onto `AuthorityEnvelope.may_read`, and emitted by `summary()`. One construction site serves both roles. |
| `may_not_read` precedence | Denial wins. The denial check runs outside the `if read_allowed:` guard, so a reference that is both allowed by a broad rule and denied by a narrow one is refused. |
| Packet/context refusal | A packet whose path-shaped `context_refs` fall outside the ceiling is refused before the session starts. |
| Wildcard handling | `_read_covers` uses `PurePosixPath.match` for rules containing `*?[`, so `company/*.yaml` covers `company/permissions.yaml` and not `company/runtime/state.yaml`. Pinned against the Company OS implementation by the existing `READ_CASES` table. |
| Serialization integrity | `may_read` and `may_not_read` serialize as lists beside the write fields; no field is dropped. |
| Fail-closed behaviour | See the limitation below. |
| Reviewer/developer difference | Read scope is identical for both roles; only `may_write` differs, and a reviewer envelope is `read_only`. |
| Sandbox limitation stated | Stated twice, in the module docstring and at the field: "This runner cannot stop a process from opening a file… it has no sandbox." |
| No broad repository-read claim | The envelope carries only the order's own paths. The default is `()`, never `.` or a repository root. |

Each row is reproduced by a test added under this review, in
`tests/test_company_external_engineering_runner.py`.

## The one limitation, recorded rather than corrected

**An empty `authorized_read_paths` skips the packet check.** The `if read_allowed:`
guard means a work order carrying no read ceiling produces no refusal here, even
for a context reference naming a path nobody granted.

This is not a hole, and it is not corrected, for three reasons that the review
verified rather than accepted:

1. **The enforcement point fails closed.** `context_expansion_policy._reference_problem`
   returns *"employee may_read is empty; the contract grants no read authority"*
   for any reference when `may_read` is empty. An absent ceiling grants nothing
   where reading is actually adjudicated.
2. **The denial list still binds with no allow-list.** A forbidden read is
   refused whether or not a ceiling was granted, so the empty case is a gap in
   a consistency check, not an escalation route.
3. **Refusing here would strand pre-existing work orders.** P5-R2 required that
   adding the fields restamp nothing (`52825ee`); a work order stored before the
   fields existed decodes to `()`, and refusing on empty would block every one.

The behaviour is now pinned by
`test_an_empty_read_ceiling_skips_the_packet_check_and_that_is_the_limit`, so it
stays deliberate. The residual defect is documentary: the `if read_allowed:`
guard carries no comment saying why empty skips. That is recorded here rather
than fixed, because changing the file to add a comment would be another
ungoverned edit of the kind this review exists to close.

## What this review does not establish

- It does not establish that a session is prevented from reading outside the
  ceiling. Nothing in the runner can do that without an OS sandbox, and the
  code says so.
- It does not review the Company OS side of P5-R2 (`intake.py`,
  `work_order.py`, `transport.py`), which was inside `company-engineering-execution`
  ownership and governed when it was made.
- It does not constitute a CEO approval of P5, or authorize any integration.
