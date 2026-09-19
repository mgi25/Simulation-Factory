"""Focused proofs for deterministic Company OS context assembly."""

from __future__ import annotations

import datetime as dt
from dataclasses import replace
from pathlib import Path

from ai_platform import ContextKind, ContextRef, Outcome, classify
from ai_platform.serde import dumps
from company.runtime import (
    AttemptReport,
    ContextAssemblyPolicy,
    ContextRequirements,
    ResourceUsageStore,
    StaleCapsulePolicy,
    TaskSpecification,
    assemble_context,
    finalise_attempt,
    load_company_config,
    plan_task,
)
from knowledge.company_os import RecordStatus
from knowledge.company_os.capsules import (
    Capsule,
    CapsuleIndex,
    CapsuleType,
    digest_capsule_sources,
    flag_capsule_for_revalidation,
)


TODAY = dt.date(2026, 9, 16)
ROOT = Path(__file__).resolve().parents[1]


def _capsule(capsule_id: str, path: str, *capabilities: str) -> Capsule:
    return Capsule(
        id=capsule_id,
        type=CapsuleType.MODULE,
        title=f"{capsule_id} module",
        purpose=f"Compact context for {capsule_id}.",
        owner="context-team",
        source="tests/test_company_context_assembly.py",
        created=TODAY,
        last_reviewed=TODAY,
        capabilities=tuple(capabilities),
        owns_paths=(path,),
        tests=("tests/test_company_context_assembly.py",),
    )


def _spec(
    *refs: ContextRef,
    capabilities: tuple[str, ...] = ("software_architecture",),
    capsule_ids: tuple[str, ...] = (),
) -> TaskSpecification:
    return TaskSpecification(
        task_id="context-assembly-test",
        objective="Assemble the minimum authoritative context for a task.",
        required_capabilities=capabilities,
        deterministic_execution_possible=True,
        context=ContextRequirements(
            refs=tuple(refs),
            constraints=("Keep the manifest reference-only.",),
            acceptance_criteria=("Context selection is deterministic.",),
        ),
        capsule_ids=capsule_ids,
    )


def _assemble(
    specification: TaskSpecification,
    index: CapsuleIndex,
    *,
    policy: ContextAssemblyPolicy | None = None,
):
    return assemble_context(
        specification,
        classify(specification.signals()),
        capsule_index=index,
        policy=policy or ContextAssemblyPolicy(as_of=TODAY, include_dependencies=False),
    )


def test_relevant_path_selects_its_capsule_and_excludes_unrelated_capsules() -> None:
    runtime = _capsule("runtime", "company/runtime")
    unrelated = _capsule("unrelated", "ai_platform")
    explicit = ContextRef(
        ContextKind.FILE,
        "company/runtime/specification.py",
        "task implementation path",
    )

    assembled = _assemble(_spec(explicit), CapsuleIndex((runtime, unrelated)))

    assert assembled.plan.selected_capsule_ids == ("runtime",)
    assert assembled.plan.capsule_refs_accepted == ("module_contract:capsule:runtime",)
    assert explicit.key in assembled.plan.final_manifest_refs
    assert any(
        item.capsule_id == "unrelated" and "no query signal" in item.reason
        for item in assembled.plan.capsule_refs_rejected
    )


def test_relevant_capability_selects_its_capsule() -> None:
    context = _capsule("context", "company/context", "context_engineering")
    runtime = _capsule("runtime", "company/runtime", "software_architecture")
    assembled = _assemble(
        _spec(capabilities=("context_engineering",)),
        CapsuleIndex((runtime, context)),
    )

    assert assembled.plan.selected_capsule_ids == ("context",)
    assert assembled.plan.selection_reasons[0].reasons == (
        "capability context_engineering",
    )


def test_explicit_refs_take_precedence_and_duplicates_collapse() -> None:
    runtime = _capsule("runtime", "company/runtime")
    source = ContextRef(
        ContextKind.FILE,
        "company/runtime/specification.py",
        "explicit task source",
    )
    explicit_capsule = ContextRef(
        ContextKind.MODULE_CONTRACT,
        "capsule:runtime",
        "explicitly required contract",
    )
    assembled = _assemble(
        _spec(source, source, explicit_capsule, capsule_ids=("runtime",)),
        CapsuleIndex((runtime,)),
    )

    assert assembled.plan.explicit_refs == (source.key, explicit_capsule.key)
    assert assembled.plan.final_manifest_refs.count(source.key) == 1
    assert assembled.plan.final_manifest_refs.count(explicit_capsule.key) == 1
    assert assembled.plan.capsule_refs_accepted == ()
    assert assembled.plan.duplicate_count == 2


def test_automatic_refs_stop_at_the_resource_ceiling_and_explain_rejections() -> None:
    capsules = tuple(
        _capsule(f"capsule-{index}", f"company/module-{index}") for index in range(3)
    )
    explicit = tuple(
        ContextRef(
            ContextKind.FILE, f"company/explicit-{index}.py", f"explicit {index}"
        )
        for index in range(5)
    )
    specification = _spec(
        *explicit,
        capsule_ids=tuple(capsule.id for capsule in capsules),
    )

    assembled = _assemble(specification, CapsuleIndex(capsules))
    ceiling_rejections = tuple(
        item
        for item in assembled.plan.capsule_refs_rejected
        if item.stage == "resource_ceiling"
    )

    assert assembled.plan.context_ceiling == 6
    assert len(assembled.manifest.refs()) == 6
    assert len(assembled.plan.capsule_refs_accepted) == 1
    assert {item.capsule_id for item in ceiling_rejections} == {
        "capsule-1",
        "capsule-2",
    }
    assert all("ceiling of 6 refs" in item.reason for item in ceiling_rejections)


def test_stale_capsules_are_excluded_unless_explicitly_surfaced_for_revalidation() -> (
    None
):
    stale = flag_capsule_for_revalidation(
        _capsule("stale-runtime", "company/runtime"),
        "runtime contract changed",
    )
    assert stale.status is RecordStatus.NEEDS_REVALIDATION
    specification = _spec(capsule_ids=(stale.id,))
    index = CapsuleIndex((stale,))

    excluded = _assemble(specification, index)
    assert excluded.plan.selected_capsule_ids == ()
    assert any(
        item.stage == "freshness" and "runtime contract changed" in item.reason
        for item in excluded.plan.capsule_refs_rejected
    )

    surfaced = _assemble(
        specification,
        index,
        policy=ContextAssemblyPolicy(
            as_of=TODAY,
            stale_capsules=StaleCapsulePolicy.ALLOW_EXPLICIT_FOR_REVALIDATION,
            include_dependencies=False,
        ),
    )
    assert surfaced.plan.selected_capsule_ids == (stale.id,)
    assert surfaced.plan.stale_capsule_ids_surfaced == (stale.id,)
    assert "non-authoritative" in surfaced.manifest.module_contracts[0].reason


def test_context_plan_fingerprints_and_cache_identity_are_deterministic() -> None:
    capsule = _capsule("runtime", "company/runtime")
    source = ContextRef(
        ContextKind.FILE,
        "company/runtime/lifecycle.py",
        "task source",
    )
    specification = _spec(source)
    index = CapsuleIndex((capsule,))

    first = _assemble(specification, index)
    second = _assemble(specification, index)
    changed_capsule = _assemble(
        specification,
        CapsuleIndex((replace(capsule, purpose="Updated compact context."),)),
    )

    assert first.plan == second.plan
    assert first.plan.manifest_fingerprint == first.manifest.fingerprint()
    assert first.plan.cache_identity == second.plan.cache_identity
    assert changed_capsule.plan.manifest_fingerprint == first.plan.manifest_fingerprint
    assert changed_capsule.plan.capsule_fingerprint != first.plan.capsule_fingerprint
    assert changed_capsule.plan.cache_identity != first.plan.cache_identity


def test_manifest_contains_references_without_expanding_capsule_bodies() -> None:
    capsule = _capsule("runtime", "company/runtime")
    assembled = _assemble(
        _spec(
            ContextRef(
                ContextKind.FILE,
                "company/runtime/lifecycle.py",
                "task source",
            )
        ),
        CapsuleIndex((capsule,)),
    )

    assert [ref.ref for ref in assembled.manifest.module_contracts] == [
        "capsule:runtime"
    ]
    assert all("\n" not in ref.ref for ref in assembled.manifest.refs())
    assert capsule.purpose not in dumps(assembled.manifest)


def test_source_digest_is_binary_safe_and_detects_changed_content(
    tmp_path: Path,
) -> None:
    source = tmp_path / "company" / "runtime" / "payload.bin"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"\x00before\xff")
    capsule = _capsule("runtime", "company/runtime")

    before = digest_capsule_sources(
        capsule,
        tmp_path,
        ("company/runtime/payload.bin",),
    )
    source.write_bytes(b"\x00after\xff")
    after = digest_capsule_sources(
        capsule,
        tmp_path,
        ("company/runtime/payload.bin",),
    )

    assert len(before[0].digest) == 64
    assert before[0].digest != after[0].digest
    reviewed = replace(capsule, source_digests=before)
    assert reviewed.changed_sources({after[0].path: after[0].digest}) == (
        "company/runtime/payload.bin",
    )


def test_usage_record_retains_manifest_and_context_plan_linkage(tmp_path: Path) -> None:
    capsule = _capsule("runtime", "company/runtime", "software_architecture")
    source = ContextRef(
        ContextKind.FILE,
        "company/runtime/lifecycle.py",
        "task source",
    )
    specification = _spec(source)
    plan = plan_task(
        specification,
        load_company_config(ROOT / "company"),
        capsule_index=CapsuleIndex((capsule,)),
        context_policy=ContextAssemblyPolicy(as_of=TODAY, include_dependencies=False),
    )
    result = finalise_attempt(
        plan,
        AttemptReport(
            outcome=Outcome.ACCEPTED,
            result="Context assembly verified.",
            context_refs_used=(source.key,),
        ),
        ResourceUsageStore(tmp_path),
    )

    assert plan.context_plan is not None
    assert plan.context_manifest is not None
    assert plan.preparation is not None
    assert (
        result.usage_record.context_fingerprint == plan.context_manifest.fingerprint()
    )
    assert result.usage_record.context_cache_key == plan.context_plan.cache_identity
    assert result.usage_record.explicit_context_sources == (source.key,)
    assert result.usage_record.automatic_context_sources == (
        "module_contract:capsule:runtime",
    )
    assert result.usage_record.unused_context == ("module_contract:capsule:runtime",)
    assert plan.preparation.context_cache_key == plan.context_plan.cache_identity
