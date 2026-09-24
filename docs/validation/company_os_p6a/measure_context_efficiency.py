"""Measure P6A context efficiency on this repository. Reads only; writes one JSON.

    python docs/validation/company_os_p6a/measure_context_efficiency.py \
        --repo-root . --out docs/evidence/company_os_p6a_typed_evidence_cache_context/measurements.json

What it measures, and what it deliberately does not.

**Measured, locally and reproducibly:** the bytes a bundle costs compressed
versus whole; how many of a realistic read sequence's reads a warm cache
avoids; how many of those reads are refused as stale after the source changes;
and the shared-prefix ratio between two renderings of the same material
assembled differently. All four are functions of this checkout and re-run to
the same numbers.

**Not measured here, and not claimed anywhere:** provider tokens, cache-creation
and cache-read token counts as a provider reports them, dollar cost, READY
rate across real work orders, and reviewer corrections. Those need paid
sessions. None were run for P6A, so the honest statement is NOT MEASURED, not
an extrapolation from the byte counts below. Bytes are not tokens and a
smaller prompt is not automatically a cheaper task.

The read sequence is not invented. It is the pattern an engineering session
actually shows: the capsule for the subsystem, the module it edits, the test
that covers it, then the same module and test again while iterating.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from company.runtime import (  # noqa: E402
    ContextBundle,
    ContextCache,
    UnitAuthority,
    UnitKind,
    cache_stability,
    content_digest,
    recompress,
    unit_from_source,
)


# One realistic task's context: the contract, the module under change, its
# neighbours, and the suites that cover it.
SUBJECTS: tuple[tuple[str, UnitKind, UnitAuthority, str], ...] = (
    (
        "knowledge/company_os/capsules/seeds/company-runtime.json",
        UnitKind.CAPSULE,
        UnitAuthority.CONTRACT,
        "the contract the change must obey",
    ),
    (
        "knowledge/company_os/capsules/seeds/company-production-integration-gate.json",
        UnitKind.CAPSULE,
        UnitAuthority.CONTRACT,
        "the gate's own contract",
    ),
    (
        "company/integration/suites.py",
        UnitKind.FILE,
        UnitAuthority.OBSERVED,
        "the module the change edits",
    ),
    (
        "company/runtime/context_assembly.py",
        UnitKind.FILE,
        UnitAuthority.OBSERVED,
        "the neighbour that selects references",
    ),
    (
        "company/runtime/context_units.py",
        UnitKind.FILE,
        UnitAuthority.OBSERVED,
        "the unit model under change",
    ),
    (
        "company/runtime/context_cache.py",
        UnitKind.FILE,
        UnitAuthority.OBSERVED,
        "the reuse layer under change",
    ),
    (
        "tests/test_company_gate_suite_requirements.py",
        UnitKind.TEST_ANCHOR,
        UnitAuthority.OBSERVED,
        "the suite that must pass",
    ),
    (
        "tests/test_company_typed_evidence_context.py",
        UnitKind.TEST_ANCHOR,
        UnitAuthority.OBSERVED,
        "the suite that must pass",
    ),
)

# The order a session reads in, with the repeats a session actually makes.
READ_SEQUENCE: tuple[str, ...] = (
    "knowledge/company_os/capsules/seeds/company-runtime.json",
    "company/integration/suites.py",
    "tests/test_company_gate_suite_requirements.py",
    "company/integration/suites.py",
    "company/runtime/context_units.py",
    "company/integration/suites.py",
    "tests/test_company_gate_suite_requirements.py",
    "company/runtime/context_cache.py",
    "company/runtime/context_units.py",
    "knowledge/company_os/capsules/seeds/company-runtime.json",
    "company/runtime/context_assembly.py",
    "tests/test_company_typed_evidence_context.py",
    "company/integration/suites.py",
    "company/runtime/context_units.py",
)


def _read(repo_root: Path, relative: str) -> str:
    return (repo_root / relative).read_text(encoding="utf-8")


def _unit(repo_root: Path, relative: str, *, compress_over: int):
    kind, authority, reason = next(
        (k, a, r) for path, k, a, r in SUBJECTS if path == relative
    )
    return unit_from_source(
        _read(repo_root, relative),
        kind=kind,
        source=relative,
        reason=reason,
        authority=authority,
        compress_over=compress_over,
    )


def measure(repo_root: Path) -> dict:
    huge = 10**9

    whole = ContextBundle(
        tuple(_unit(repo_root, path, compress_over=huge) for path, *_ in SUBJECTS)
    )
    compressed = ContextBundle(
        tuple(recompress(unit, threshold_chars=1200) for unit in whole)
    )

    # Reuse, over the read sequence above.
    cache = ContextCache()
    reads = 0
    for relative in READ_SEQUENCE:
        text = _read(repo_root, relative)
        key = _unit(repo_root, relative, compress_over=1200).key()
        digest = content_digest(text)
        before = cache.stats.loads
        cache.read_once(
            key, digest, lambda r=relative: _unit(repo_root, r, compress_over=1200)
        )
        reads += cache.stats.loads - before

    # What a changed source does: one file is edited mid-task.
    edited_key = _unit(
        repo_root, "company/integration/suites.py", compress_over=1200
    ).key()
    stale = cache.lookup(edited_key, content_digest("# a different file\n"))

    # Cache stability: the same material, assembled differently, and the same
    # material with one more unit appended.
    reversed_bundle = ContextBundle(tuple(reversed(compressed.units)))
    reorder = cache_stability(compressed.render(), reversed_bundle.render())

    appended = ContextBundle(
        compressed.units
        + (
            unit_from_source(
                "a later addition\n",
                kind=UnitKind.EVIDENCE,
                source="zzz/appended-last.txt",
                reason="a unit added after the prefix was built",
                authority=UnitAuthority.OBSERVED,
            ),
        )
    )
    growth = cache_stability(compressed.render(), appended.render())

    return {
        "repo_root": repo_root.name,
        "context_bytes": {
            "units": len(compressed),
            "canonical_chars": compressed.canonical_chars(),
            "whole_bundle_chars": whole.chars(),
            "compressed_bundle_chars": compressed.chars(),
            "reduction_pct": round(
                100.0 * (whole.chars() - compressed.chars()) / whole.chars(), 2
            ),
            "note": (
                "Characters, not tokens. The platform is provider-agnostic by "
                "contract, and a token count belongs to one tokenizer."
            ),
        },
        "read_once": {
            "reads_requested": len(READ_SEQUENCE),
            "distinct_sources": len(set(READ_SEQUENCE)),
            "loader_calls": reads,
            "reads_avoided": cache.stats.reads_avoided,
            "hits": cache.stats.hits,
            "misses": cache.stats.misses,
            "stale_rejections": cache.stats.stale_rejections,
            "reuse_ratio": round(cache.stats.reuse_ratio, 4),
            "canonical_chars_reused": cache.stats.canonical_chars_reused,
        },
        "staleness": {
            "outcome": stale.outcome.value,
            "returned_a_unit": stale.unit is not None,
            "detail": stale.detail,
        },
        "cache_stability": {
            "reassembled_in_reverse": reorder.to_dict(),
            "one_unit_appended": growth.to_dict(),
        },
        "not_measured": [
            "provider token counts (input, output, cache creation, cache read)",
            "provider monetary cost",
            "READY rate over real work orders",
            "reviewer corrections",
            "whole-task wall-clock or session count",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)
    payload = measure(Path(args.repo_root).resolve())
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"written {out}")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
