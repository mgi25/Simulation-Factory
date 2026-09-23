# Independent evidence review — the attestation surface

This directory is the **only** place Company OS may write when it reviews an
evidence record. It is owned by the `company-evidence-review` capsule, and that
capsule owns nothing else under `docs/`.

## Why the directory exists at all

Company OS derives a work order's writable scope from capsule ownership
(`company/engineering/intake.py`). Before this surface existed, no capsule
owned any `docs/` path, so an objective of the form "independently review this
evidence record" matched no capsule and stopped at DECISION REQUIRED — the
company could produce evidence it was structurally unable to audit.

The obvious repair — giving a capsule `docs/` or `docs/evidence/` — is the one
that must not be made. `owns_paths` becomes `authorized_paths` becomes the
developer contract's `may_write`, with no role distinction in between, so a
capsule owning `docs/evidence` hands a developer session write authority over
every frozen evidence record in the repository. That is measured, not asserted:
see `test_owning_the_evidence_root_would_hand_a_developer_the_frozen_record`
in `tests/test_company_evidence_review.py`.

So the writable surface is this directory, which holds attestations, and the
evidence being reviewed stays **unowned and therefore unwritable**. Fail-closed
is the default: a path no capsule owns is outside every `may_write`, and
`PathScope` refuses a change to it.

## What belongs here

One file per review: the verdict, what was examined, and what the evidence does
**not** establish. An attestation names the evidence record it reviewed and the
digest it read, so the verdict cannot drift from the bytes it was about.

## What does not belong here

An evidence record itself. Nothing under this directory is the subject of a
review — it is only ever the output of one. A new evidence record goes in its
own directory under `docs/evidence/`, where no capsule owns it.

## Correcting frozen evidence

An attestation cannot edit the record it reviews, and this is deliberate. If a
review finds a factual defect, the correction is an **addendum** carrying its
own provenance — the original bytes stay. Overwriting reviewed evidence would
destroy the thing the review was about.
