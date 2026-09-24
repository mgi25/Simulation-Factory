"""Which conditions block the boundary and which are only worth seeing.

The split is written down here, once, as two frozen sets of check ids. It is
not a weight, not a severity ladder and not a per-category threshold, because
any of those would let the gate be tuned until it passes. A check is required
or it is advisory, and moving one across the line is a visible diff.

## The rule used to classify

**Required** if the condition failing would make it unsafe or dishonest to wire
Company OS into production: a production module importing the control plane, a
write path into the simulation tree, an authority that opens instead of
closing, a private number with no provenance, a suite nobody ran.

**Advisory** if the condition failing would make Company OS *worse* without
making the boundary unsafe: a module no capsule claims, a decision queue with
nothing in it yet. These stay in the report, with their status, and do not
block.

## Why an unclassified check is an error

`assert_covers` refuses a check id that appears in neither set. The tempting
alternative - default to advisory - means a new required condition can be added
and silently stop blocking, which is the same failure as having no gate.

## Why `not_applicable` is allow-listed

`not_applicable` is the one non-blocking status that is not a proof. Left
open, any check could quietly declare itself irrelevant. Only the ids in
`not_applicable_allowed` may return it; `coerce` downgrades the rest to
`unknown`, which blocks if the check is required.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .errors import PolicyError
from .model import GateCheck, GateStatus


POLICY_VERSION = 1


REQUIRED_CHECKS = frozenset(
    {
        # Architecture: Company OS must remain a removable, acyclic control plane.
        "architecture.production_does_not_import_company_os",
        "architecture.production_tests_independent",
        "architecture.no_subsystem_import_cycle",
        "architecture.capsule_graph_acyclic",
        "architecture.capsule_graph_integrity",
        # P6B. Production code the Company OS contract imports must have a
        # capsule owner. Required, not advisory, and the reason is the failure
        # it closes rather than the category it sits in: without it, deleting
        # `company-external-engineering-runner` removes a subsystem's entire
        # contract - its owner, its invariants and six required suites - and
        # every remaining check still passes. A gate that keeps saying READY
        # while the thing it is gating loses its governance is not reporting a
        # gap, it is wrong. Its advisory neighbour
        # `architecture.subsystem_ownership_bounded` stays advisory: an
        # unclaimed Company OS module is a context-selection gap, and the two
        # conditions are kept apart so that this line is the visible diff.
        "architecture.governed_subsystem_ownership",
        # Execution safety: every authority fails closed, and nothing spawns.
        "execution.read_authority_fails_closed",
        "execution.write_authority_fails_closed",
        "execution.authority_snapshot_immutable",
        "execution.receipt_validation_enforced",
        "execution.no_subagent_runtime_lock",
        # Data and evidence: a number carries its provenance or does not exist.
        "data.private_metric_boundary",
        "data.evidence_required_for_claims",
        "data.missing_evidence_stays_unknown",
        "data.audit_records_append_only",
        # Workforce: authority is granted by permissions.yaml, never taken.
        "workforce.ceo_reserved_actions_present",
        "workforce.restricted_states_cannot_write_production",
        "workforce.advisory_cannot_self_approve",
        # Finance: nothing spends, and an unmeasured cost is not a zero cost.
        "finance.no_autonomous_spend_approval",
        "finance.recurring_paid_api_spend_reserved",
        "finance.unknown_is_not_zero",
        # Analytics: observation and learning stay apart.
        "analytics.causal_overclaim_refused",
        "analytics.learning_requires_results",
        "analytics.competitor_private_metrics_unavailable",
        # Executive visibility: the CEO can see the gaps, and cannot act from the view.
        "executive.dashboard_available",
        "executive.missing_and_stale_evidence_visible",
        "executive.dashboard_cannot_approve",
        # Test and build health: the suites ran, and nothing new was pulled in.
        "health.required_suites_pass",
        "health.sources_parse",
        "health.no_new_dependency",
        "health.no_network_or_model_dependency",
        # Production boundary: nothing here can publish, mutate or delete.
        "production.no_publishing_capability",
        "production.no_automatic_production_mutation",
        "production.no_production_delete_authority",
        "production.integration_remains_disabled",
    }
)


ADVISORY_CHECKS = frozenset(
    {
        # A module no capsule claims is a context-selection gap, not a safety one.
        "architecture.subsystem_ownership_bounded",
        # Both need company records that a bootstrap state directory may not hold yet.
        "workforce.capability_gaps_visible",
        "executive.decision_queue_preserves_source_refs",
        # Separating a production-environment failure from a Company OS regression
        # needs the caller to say which suites are which.
        "health.production_failures_separated",
    }
)


# The only checks that may answer `not_applicable`. Both concern a subject the
# repository may simply not contain, which is the one honest use of the status.
NOT_APPLICABLE_ALLOWED = frozenset(
    {
        "architecture.production_tests_independent",
        "production.no_automatic_production_mutation",
    }
)


@dataclass(frozen=True)
class GatePolicy:
    """The required/advisory split, and the narrow `not_applicable` allow-list."""

    required: frozenset[str] = REQUIRED_CHECKS
    advisory: frozenset[str] = ADVISORY_CHECKS
    not_applicable_allowed: frozenset[str] = NOT_APPLICABLE_ALLOWED
    version: int = POLICY_VERSION

    def __post_init__(self) -> None:
        overlap = self.required & self.advisory
        if overlap:
            raise PolicyError(
                "a check is required or advisory, never both: " + ", ".join(sorted(overlap))
            )
        stray = self.not_applicable_allowed - (self.required | self.advisory)
        if stray:
            raise PolicyError(
                "not_applicable_allowed names unclassified check(s): "
                + ", ".join(sorted(stray))
            )

    def is_required(self, check_id: str) -> bool:
        return check_id in self.required

    def classification(self, check_id: str) -> str:
        if check_id in self.required:
            return "required"
        if check_id in self.advisory:
            return "advisory"
        raise PolicyError(
            f"{check_id} is classified neither required nor advisory. Add it to one "
            "of the two sets in company/integration/policy.py; an unclassified check "
            "would become advisory by accident and stop blocking without a diff."
        )

    def assert_covers(self, check_ids: Iterable[str]) -> None:
        """Refuse a run whose checks the policy does not classify, in both directions."""
        produced = set(check_ids)
        unclassified = sorted(produced - self.required - self.advisory)
        if unclassified:
            raise PolicyError(
                "the gate produced check(s) the policy does not classify: "
                + ", ".join(unclassified)
            )
        missing = sorted((self.required | self.advisory) - produced)
        if missing:
            raise PolicyError(
                "the policy classifies check(s) the gate did not produce: "
                + ", ".join(missing)
                + ". A named condition that silently stops running is a gate with a hole."
            )

    def coerce(self, check: GateCheck) -> GateCheck:
        """Downgrade an unauthorised `not_applicable` to `unknown`.

        Returns the check unchanged in every other case, so this is safe to run
        over the whole set.
        """
        if check.status is not GateStatus.NOT_APPLICABLE:
            return check
        if check.check_id in self.not_applicable_allowed:
            return check
        from dataclasses import replace

        return replace(
            check,
            status=GateStatus.UNKNOWN,
            not_applicable_reason="",
            missing_evidence=(
                f"{check.check_id} declared itself not applicable, which the gate policy "
                f"does not allow for this check: {check.not_applicable_reason}",
            ),
            remediation=(
                check.remediation
                or "Establish the evidence, or add this check to "
                "company/integration/policy.py NOT_APPLICABLE_ALLOWED with a reason."
            ),
        )


DEFAULT_POLICY = GatePolicy()


__all__ = [
    "ADVISORY_CHECKS",
    "DEFAULT_POLICY",
    "NOT_APPLICABLE_ALLOWED",
    "POLICY_VERSION",
    "REQUIRED_CHECKS",
    "GatePolicy",
]
