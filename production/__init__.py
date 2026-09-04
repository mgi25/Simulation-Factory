"""Production: turning a curated batch into finished, checked deliverables.

Nothing in this package simulates, renders, synthesises or encodes anything.
Those already exist and are already tested; this is the layer that runs them
in the right order, proves that what came out is what was asked for, and
packages the result for a person to look at.

Two layers of status, because they answer different questions:

* `automated_status` is what this package can decide. Is the replay the
  battle the manifest selected, is every frame there and the right size, is
  the soundtrack exactly as long as the pictures, is the MP4 the production
  format. All of it is mechanical and all of it is a hard pass or fail.
* `review_status` is what it cannot. Whether a battle is dull despite its
  score, whether the audio is pleasant, whether a Short is worth publishing.
  That defaults to `pending` and only a person changes it.

The other rule this package exists to enforce is that expensive work is not
repeated. Rendering a Short takes two and a half minutes; producing a batch
twice should not take twice as long. Reuse is decided by verification rather
than by a file existing, and every decision is printed.
"""

from __future__ import annotations

from production.delivery import (
    CONTACT_SHEET_NAME,
    PRODUCTION_MANIFEST_NAME,
    PRODUCTION_VERSION,
    DeliveryError,
    deliver_file,
    item_dir_name,
    production_dir_name,
    production_manifest,
    stage_plan,
    summarise,
)
from production.qc import (
    QC_NAME,
    QC_VERSION,
    REVIEW_APPROVED,
    REVIEW_PENDING,
    REVIEW_REJECTED,
    REVIEW_STATUSES,
    STATUS_FAIL,
    STATUS_PASS,
    AudioFacts,
    Evidence,
    LoudnessFacts,
    RenderFacts,
    ReplayFacts,
    VideoFacts,
    evaluate,
    failure_record,
    moov_before_mdat,
    qc_record,
    sequence_digest,
    visual_checkpoints,
    with_review,
)

__all__ = [
    "CONTACT_SHEET_NAME",
    "PRODUCTION_MANIFEST_NAME",
    "PRODUCTION_VERSION",
    "QC_NAME",
    "QC_VERSION",
    "REVIEW_APPROVED",
    "REVIEW_PENDING",
    "REVIEW_REJECTED",
    "REVIEW_STATUSES",
    "STATUS_FAIL",
    "STATUS_PASS",
    "AudioFacts",
    "DeliveryError",
    "Evidence",
    "LoudnessFacts",
    "RenderFacts",
    "ReplayFacts",
    "VideoFacts",
    "deliver_file",
    "evaluate",
    "failure_record",
    "item_dir_name",
    "moov_before_mdat",
    "production_dir_name",
    "production_manifest",
    "qc_record",
    "sequence_digest",
    "stage_plan",
    "summarise",
    "visual_checkpoints",
    "with_review",
]
