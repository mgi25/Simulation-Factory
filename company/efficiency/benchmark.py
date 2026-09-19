"""Credit-free, deterministic benchmarks for Company OS context assembly."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from ai_platform.context_manifest import ContextKind, ContextManifest, ContextRef
from ai_platform.resource_classes import ReasoningClass
from ai_platform.serde import dumps, fingerprint, to_jsonable
from company.runtime.packets import SessionPacket
from company.runtime.path_scope import PathScope
from knowledge.company_os.capsules import CapsuleIndex, TaskQuery, select_capsules
from knowledge.company_os.capsules.index import path_related

from .providers import (
    GRAPHIFY_STATUS,
    RTK_STATUS,
    CodeIntelligenceQuery,
    CodeQueryKind,
    ReferenceRepositoryProvider,
)
from .telemetry import (
    BenchmarkMode,
    CostMeasurement,
    EfficiencyComparison,
    EfficiencyRecord,
    IntegrationStatus,
    ReuseTier,
    check_reuse,
    compare_efficiency,
    estimate_tokens,
)


@dataclass(frozen=True)
class BenchmarkScenario:
    name: str
    objective: str
    capabilities: tuple[str, ...]
    capsule_ids: tuple[str, ...] = ()
    paths: tuple[str, ...] = ()
    include_dependencies: bool = True
    repository_candidates: tuple[str, ...] = ()
    raw_context_paths: tuple[str, ...] = ()
    expansion_approved_paths: tuple[str, ...] = ()
    expansion_denied_paths: tuple[str, ...] = ()
    repetitions: int = 1


@dataclass(frozen=True)
class BenchmarkReport:
    records: tuple[EfficiencyRecord, ...]
    comparisons: tuple[EfficiencyComparison, ...]

    def to_dict(self) -> dict[str, object]:
        return to_jsonable(self)


MINIMALISM_STATUS = IntegrationStatus(
    "minimalism_policy", True, True,
    "deterministic reuse-tier check; no model call",
)


def default_scenarios() -> tuple[BenchmarkScenario, ...]:
    """Six stable fixtures covering selection, dependencies, I/O, expansion and cache."""
    return (
        BenchmarkScenario(
            "small_one_capsule",
            "Validate one bounded configuration change.",
            ("capability_yaml_subset",),
            include_dependencies=False,
        ),
        BenchmarkScenario(
            "dependency_closure",
            "Assemble runtime context and its declared dependencies.",
            ("capability_context_assembly",),
        ),
        BenchmarkScenario(
            "research_task",
            "Evaluate evidence and confidence for a reference case.",
            ("capability_reference_analysis",),
        ),
        BenchmarkScenario(
            "repository_task",
            "Change context assembly using only relevant repository files.",
            ("capability_context_assembly",),
            paths=("company/runtime/context_assembly.py",),
            repository_candidates=(
                "company/runtime/context_assembly.py",
                "tests/test_company_context_assembly.py",
                "intelligence/research/ingestion.py",
            ),
            raw_context_paths=(
                "company/runtime/packets.py",
                "tests/test_company_os_research_ingestion.py",
            ),
        ),
        BenchmarkScenario(
            "context_expansion",
            "Begin with core research context and approve one necessary file.",
            ("capability_reference_analysis",),
            expansion_approved_paths=("intelligence/research/reference_case.py",),
            expansion_denied_paths=("company/permissions.yaml",),
        ),
        BenchmarkScenario(
            "warm_cache",
            "Repeat an identical capsule selection and record cache reuse.",
            ("capability_context_assembly",),
            repetitions=2,
        ),
    )


class BenchmarkRunner:
    def __init__(self, repo_root: str | Path, index: CapsuleIndex | None = None) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.index = index or CapsuleIndex.load()
        self.repository = ReferenceRepositoryProvider(self.repo_root)
        self._cache: set[str] = set()

    def run(
        self,
        scenarios: Iterable[BenchmarkScenario] | None = None,
        modes: tuple[BenchmarkMode, ...] = (
            BenchmarkMode.BASELINE,
            BenchmarkMode.CAPSULE_OPTIMIZED,
            BenchmarkMode.FULL_RAW_CONTEXT,
        ),
    ) -> BenchmarkReport:
        selected_scenarios = tuple(scenarios) if scenarios is not None else default_scenarios()
        records: list[EfficiencyRecord] = []
        for scenario in selected_scenarios:
            for mode in modes:
                for iteration in range(1, scenario.repetitions + 1):
                    records.append(self._run_once(scenario, mode, iteration))

        comparisons: list[EfficiencyComparison] = []
        for scenario in selected_scenarios:
            matching = [record for record in records if record.task_id == scenario.name]
            baseline = [record for record in matching if record.mode is BenchmarkMode.BASELINE]
            optimized = [
                record for record in matching
                if record.mode is BenchmarkMode.CAPSULE_OPTIMIZED
            ]
            if baseline and optimized:
                comparisons.append(compare_efficiency(baseline[-1], optimized[-1]))
        return BenchmarkReport(tuple(records), tuple(comparisons))

    def _run_once(
        self, scenario: BenchmarkScenario, mode: BenchmarkMode, iteration: int
    ) -> EfficiencyRecord:
        selection = select_capsules(
            self.index,
            TaskQuery(
                paths=scenario.paths,
                capabilities=scenario.capabilities,
                capsule_ids=scenario.capsule_ids,
                include_dependencies=scenario.include_dependencies,
                max_capsules=max(1, len(self.index)),
            ),
        )
        capsules = (
            selection.capsules
            if mode is BenchmarkMode.CAPSULE_OPTIMIZED
            else self.index.all()
        )
        candidate_paths = scenario.repository_candidates
        if mode is BenchmarkMode.CAPSULE_OPTIMIZED:
            owned = tuple(path for capsule in capsules for path in capsule.owns_paths)
            candidate_paths = tuple(
                path for path in candidate_paths
                if any(path_related(path, owner) for owner in owned)
            )
        elif mode is BenchmarkMode.FULL_RAW_CONTEXT:
            candidate_paths = tuple(dict.fromkeys(candidate_paths + scenario.raw_context_paths))

        query = CodeIntelligenceQuery(
            CodeQueryKind.LIKELY_FILES,
            scenario.objective,
            candidate_paths=candidate_paths + scenario.expansion_approved_paths,
        )
        repository_result = self.repository.query(query)
        files_read, file_text = self._read_files(repository_result.references)

        module_refs = tuple(
            ContextRef(
                ContextKind.MODULE_CONTRACT,
                f"capsule:{capsule.id}",
                "selected by deterministic efficiency benchmark",
            )
            for capsule in capsules
        )
        file_refs = tuple(
            ContextRef(ContextKind.FILE, path, "opened by deterministic repository provider")
            for path in files_read
        )
        manifest = ContextManifest(
            task_id=scenario.name,
            objective=scenario.objective,
            reasoning_class=ReasoningClass.F,
            module_contracts=module_refs,
            files=file_refs,
            acceptance_criteria=("Record reproducible efficiency measurements.",),
        ).assert_valid()
        capsule_text = "".join(dumps(capsule) for capsule in capsules)
        context_text = capsule_text + file_text
        cache_key = fingerprint(
            {"manifest": manifest.fingerprint(), "context": fingerprint(context_text)}
        )
        hit = cache_key in self._cache
        self._cache.add(cache_key)

        packet = SessionPacket(
            task_id=scenario.name,
            objective=scenario.objective,
            employee="efficiency-harness",
            reasoning_class=ReasoningClass.F,
            resource_class="deterministic_benchmark",
            context_refs=manifest.refs(),
            explicit_context_refs=(),
            automatic_context_refs=manifest.keys(),
            context_fingerprint=manifest.fingerprint(),
            context_cache_key=cache_key,
            constraints=("No external model or network call.",),
            acceptance_criteria=manifest.acceptance_criteria,
            path_scope=PathScope(),
            expected_branch="efficiency-benchmark",
        )
        packet_json = dumps(packet)
        tool_output = "\n".join(repository_result.references)
        run_id = f"{scenario.name}:{mode.value}:{iteration}"
        return EfficiencyRecord(
            run_id=run_id,
            task_id=scenario.name,
            mode=mode,
            capabilities_selected=tuple(sorted(scenario.capabilities)),
            capsules_selected=tuple(capsule.id for capsule in capsules),
            capsule_count=len(capsules),
            capsule_chars=sum(capsule.size_chars() for capsule in capsules),
            context_chars=len(context_text),
            context_bytes=len(context_text.encode("utf-8")),
            context_manifest_fingerprint=manifest.fingerprint(),
            execution_packet_chars=packet.size_chars(),
            execution_packet_bytes=len(packet_json.encode("utf-8")),
            repository_references_selected=repository_result.references,
            repository_files_read=files_read,
            tool_calls=1,
            tool_output_chars=len(tool_output),
            tool_output_bytes=len(tool_output.encode("utf-8")),
            tool_context_chars=len(tool_output),
            tool_context_bytes=len(tool_output.encode("utf-8")),
            tokens=estimate_tokens(packet_json + context_text),
            cache_hits=1 if hit else 0,
            cache_misses=0 if hit else 1,
            context_expansion_requests=(
                len(scenario.expansion_approved_paths) + len(scenario.expansion_denied_paths)
            ),
            context_expansion_approvals=len(scenario.expansion_approved_paths),
            context_expansion_denials=len(scenario.expansion_denied_paths),
            latency_ms=None,
            model=None,
            cost=CostMeasurement.unavailable(
                "deterministic fixture made no provider call and has no monetary rate"
            ),
            packet_fingerprint=packet.fingerprint(),
            packet_attempt=iteration,
            minimalism=check_reuse(
                ReuseTier.SMALL_IMPLEMENTATION,
                "reused capsule selection, packets, fingerprints and execution-store conventions",
            ),
            integrations=(GRAPHIFY_STATUS, RTK_STATUS, MINIMALISM_STATUS),
        )

    def _read_files(self, references: tuple[str, ...]) -> tuple[tuple[str, ...], str]:
        read: list[str] = []
        chunks: list[str] = []
        for reference in references:
            path = self.repo_root / reference
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                continue
            read.append(reference)
            chunks.append(text)
        return tuple(read), "".join(chunks)


def run_default_benchmarks(repo_root: str | Path) -> BenchmarkReport:
    return BenchmarkRunner(repo_root).run()
