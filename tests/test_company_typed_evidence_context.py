"""P6A: typed evidence records, cache-stable context, read-once reuse.

Three claims are under test here, and each one is measured rather than
asserted by inspection:

* a context unit's identity is a function of its content and nothing else, so
  two assemblies of the same material produce the same bytes and the same
  digest - `cache_stability` returns the number;
* compression is reversible against the canonical source and refuses a source
  that has changed, so nothing is lost that cannot be got back;
* reuse is gated on a digest, so a cache miss is what happens when the source
  moved - never a stale hit.
"""

from __future__ import annotations

import datetime as dt

import pytest

from company.runtime import (
    CacheOutcome,
    CacheStats,
    CompressionKind,
    ContextBundle,
    ContextCache,
    ContextUnit,
    EvidenceLedger,
    EvidenceOutcome,
    ExecutionEvidence,
    ExecutionEvidenceKind,
    LifecycleError,
    UnitAuthority,
    UnitKind,
    bundle_of,
    cache_stability,
    compress,
    content_digest,
    expand,
    recompress,
    unit_from_source,
)


TODAY = dt.date(2026, 9, 24)

LONG = "\n".join(f"line {i:03d} of a module that is long enough to be worth eliding" for i in range(1, 121))
SHORT = "def f():\n    return 1\n"


def a_unit(
    *,
    source: str = "company/runtime/context_units.py",
    kind: UnitKind = UnitKind.SYMBOL_SPAN,
    authority: UnitAuthority = UnitAuthority.OBSERVED,
    text: str = SHORT,
    **kwargs,
) -> ContextUnit:
    return unit_from_source(
        text,
        kind=kind,
        source=source,
        reason=kwargs.pop("reason", "the span the task edits"),
        authority=authority,
        **kwargs,
    )


# --------------------------------------------------------------------------
# Reversible compression
# --------------------------------------------------------------------------


def test_a_short_body_is_not_compressed_at_all():
    body = compress(SHORT, source="a/b.py")
    assert body.kind is CompressionKind.NONE
    assert body.render() == SHORT
    assert body.elided_lines == 0


def test_a_long_body_is_elided_and_says_exactly_what_it_removed():
    body = compress(LONG, source="a/b.py")
    assert body.kind is CompressionKind.ELIDED
    assert body.elided_span == (13, 116)
    assert body.elided_lines == 104
    assert body.chars() < body.full_chars
    assert body.saved_chars() > 0


def test_an_elided_body_carries_a_pointer_back_to_its_source():
    body = compress(LONG, source="a/b.py")
    rendered = body.render()
    assert "a/b.py#13-116" in rendered
    assert body.full_digest[:16] in rendered


def test_compression_is_reversible_against_the_canonical_source():
    body = compress(LONG, source="a/b.py")
    assert expand(body, LONG) == LONG


def test_self_contained_distinguishes_whole_from_merely_restorable():
    """Found by independent review: `reversible` was hardcoded True, which is
    a check that cannot fail. What is worth knowing is whether the body can be
    read without going back to the source."""
    assert compress(SHORT, source="a/b.py").self_contained is True
    assert compress(LONG, source="a/b.py").self_contained is False


def test_expanding_against_a_changed_source_is_refused_not_approximated():
    """The whole safety property of compression. A body reconstructed from the
    wrong bytes would be plausible and wrong, which is the worst of both."""
    body = compress(LONG, source="a/b.py")
    with pytest.raises(LifecycleError, match="has changed since it was compressed"):
        expand(body, LONG + "\nline 121 appeared later")


def test_compression_that_would_not_save_anything_declines():
    """Fourteen short lines: eliding one of them costs more in marker than it
    saves in text, so the body is returned whole."""
    text = "\n".join(f"{i}" for i in range(20))
    body = compress(text, source="a/b.py", threshold_chars=1)
    assert body.kind is CompressionKind.NONE
    assert expand(body, text) == text


def test_a_compression_that_keeps_no_anchor_is_refused():
    with pytest.raises(LifecycleError, match="summary cannot be checked"):
        compress(LONG, source="a/b.py", head_lines=0, tail_lines=0)


def test_an_elided_body_must_name_its_span():
    body = compress(LONG, source="a/b.py")
    with pytest.raises(LifecycleError, match="must name the line range"):
        type(body)(
            source=body.source,
            kind=CompressionKind.ELIDED,
            head=body.head,
            tail=body.tail,
            elided_span=None,
            full_digest=body.full_digest,
            full_lines=body.full_lines,
            full_chars=body.full_chars,
        )


# --------------------------------------------------------------------------
# Typed units, and the authority rule
# --------------------------------------------------------------------------


def test_a_unit_carries_its_source_digest_not_its_rendered_digest():
    unit = a_unit(text=LONG)
    assert unit.content_digest == content_digest(LONG)
    assert unit.body.kind is CompressionKind.ELIDED


def test_only_a_contract_unit_binds():
    assert a_unit(authority=UnitAuthority.CONTRACT).binding is True
    assert a_unit(authority=UnitAuthority.OBSERVED).binding is False
    assert a_unit(authority=UnitAuthority.DERIVED).binding is False


def test_binding_is_derived_and_cannot_be_set():
    """Learning must not create authority, and the way that is enforced is
    that there is no writable flag to set."""
    unit = a_unit(authority=UnitAuthority.DERIVED)
    with pytest.raises((AttributeError, TypeError)):
        unit.binding = True  # type: ignore[misc]
    with pytest.raises((AttributeError, TypeError)):
        unit.authority = UnitAuthority.CONTRACT  # type: ignore[misc]


def test_compression_carries_authority_through_unchanged():
    unit = unit_from_source(
        LONG,
        kind=UnitKind.CAPSULE,
        source="knowledge/company_os/capsules/seeds/company-runtime.json",
        reason="the contract the task must obey",
        authority=UnitAuthority.CONTRACT,
        compress_over=10 ** 9,
    )
    assert unit.body.kind is CompressionKind.NONE
    shrunk = recompress(unit, threshold_chars=100)
    assert shrunk.body.kind is CompressionKind.ELIDED
    assert shrunk.authority is unit.authority
    assert shrunk.content_digest == unit.content_digest


def test_a_bundle_separates_what_binds_from_what_was_merely_learned():
    bundle = bundle_of(
        (
            a_unit(source="a/contract.json", kind=UnitKind.CAPSULE, authority=UnitAuthority.CONTRACT),
            a_unit(source="b/observed.py", authority=UnitAuthority.OBSERVED),
            a_unit(source="c/ranked.py", authority=UnitAuthority.DERIVED),
        )
    )
    assert [u.source for u in bundle.contract_units()] == ["a/contract.json"]
    assert [u.source for u in bundle.derived_units()] == ["c/ranked.py"]


def test_a_unit_and_its_body_must_name_one_source():
    with pytest.raises(LifecycleError, match="name one source"):
        ContextUnit(
            kind=UnitKind.FILE,
            source="a/b.py",
            reason="why",
            authority=UnitAuthority.OBSERVED,
            body=compress(SHORT, source="somewhere/else.py"),
        )


def test_two_units_cannot_claim_the_same_place_in_a_bundle():
    with pytest.raises(LifecycleError, match="same place"):
        bundle_of((a_unit(), a_unit(text=LONG)))


# --------------------------------------------------------------------------
# Cache-stable identity, measured
# --------------------------------------------------------------------------


def _three_units() -> tuple[ContextUnit, ...]:
    return (
        a_unit(source="company/runtime/authority.py", text=LONG),
        a_unit(source="ai_platform/serde.py"),
        a_unit(
            source="knowledge/company_os/capsules/seeds/company-runtime.json",
            kind=UnitKind.CAPSULE,
            authority=UnitAuthority.CONTRACT,
        ),
    )


def test_the_same_units_render_identically_however_they_were_assembled():
    units = _three_units()
    forwards = ContextBundle(units)
    backwards = ContextBundle(tuple(reversed(units)))
    measured = cache_stability(forwards.render(), backwards.render())
    assert measured.identical
    assert measured.ratio == 1.0
    assert forwards.digest() == backwards.digest()


def test_unit_identity_holds_no_clock_no_absolute_path_and_no_session():
    identity = a_unit().identity()
    assert set(identity) == {
        "version",
        "kind",
        "source",
        "span",
        "symbol",
        "content_digest",
        "authority",
        "compression",
        "elided_span",
    }
    flat = repr(identity)
    assert "C:\\" not in flat and "/Users/" not in flat
    assert str(TODAY.year) not in flat


def test_a_changed_source_changes_the_unit_id_and_nothing_else_does():
    before = a_unit()
    same_again = a_unit(reason="a differently worded justification")
    changed = a_unit(text=SHORT + "\n# one more line\n")
    assert before.unit_id() == same_again.unit_id()
    assert before.unit_id() != changed.unit_id()


def test_adding_a_unit_at_the_end_preserves_the_cached_prefix():
    """A provider cache reuses a prefix. Appending must not move what came
    before it, and `cache_stability` is how that is checked rather than hoped
    for."""
    units = _three_units()
    small = ContextBundle(units)
    larger = ContextBundle(units + (a_unit(source="zzz/last.py"),))
    measured = cache_stability(small.render(), larger.render())
    assert not measured.identical
    assert measured.shared_prefix_chars == small.chars()
    assert measured.ratio > 0.9


def test_every_kind_and_authority_has_a_declared_place_in_the_order():
    """A missing rank would raise at bundle construction, which is the wrong
    moment. A new `UnitKind` must be given a position deliberately."""
    from company.runtime.context_units import _AUTHORITY_ORDER, _KIND_ORDER

    assert set(_KIND_ORDER) == set(UnitKind)
    assert set(_AUTHORITY_ORDER) == set(UnitAuthority)
    assert sorted(_KIND_ORDER.values()) == list(range(len(UnitKind)))
    assert sorted(_AUTHORITY_ORDER.values()) == list(range(len(UnitAuthority)))


def test_contracts_come_first_and_derived_material_last():
    """A provider cache reuses a prefix, so the top of a bundle must be what
    changes least often. Measured, not assumed: with the units ordered
    `kind:source` instead, appending one evidence unit to a real eight-unit
    bundle dropped the shared prefix from 100% to 19.4%."""
    bundle = bundle_of(
        (
            a_unit(source="z/derived.py", authority=UnitAuthority.DERIVED),
            a_unit(source="a/evidence.json", kind=UnitKind.EVIDENCE),
            a_unit(source="m/module.py", kind=UnitKind.FILE),
            a_unit(source="z/contract.json", kind=UnitKind.CAPSULE, authority=UnitAuthority.CONTRACT),
        )
    )
    assert [u.source for u in bundle] == [
        "z/contract.json",
        "m/module.py",
        "a/evidence.json",
        "z/derived.py",
    ]


def test_appending_a_unit_of_any_kind_keeps_the_prefix_when_it_sorts_last():
    """The regression the measurement found. An evidence unit appended to a
    bundle of contracts and files must land at the end, not in the middle."""
    base = bundle_of(
        (
            a_unit(source="a/contract.json", kind=UnitKind.CAPSULE, authority=UnitAuthority.CONTRACT),
            a_unit(source="b/module.py", kind=UnitKind.FILE),
            a_unit(source="c/test.py", kind=UnitKind.TEST_ANCHOR),
        )
    )
    grown = bundle_of(base.units + (a_unit(source="d/evidence.json", kind=UnitKind.EVIDENCE),))
    measured = cache_stability(base.render(), grown.render())
    assert measured.shared_prefix_chars == base.chars()


def test_a_bundle_reports_what_compression_bought():
    bundle = ContextBundle(_three_units())
    assert bundle.canonical_chars() > bundle.chars()


# --------------------------------------------------------------------------
# Read-once reuse
# --------------------------------------------------------------------------


def test_a_second_lookup_of_unchanged_content_is_a_hit():
    cache = ContextCache()
    unit = a_unit()
    cache.put(unit)
    found = cache.lookup(unit.cache_key(), unit.content_digest)
    assert found.outcome is CacheOutcome.HIT
    assert found.unit is unit
    assert cache.stats.hits == 1


def test_a_changed_source_is_a_stale_rejection_and_evicts():
    """A cache miss is preferable to stale evidence, and the two are counted
    separately because they mean opposite things."""
    cache = ContextCache()
    unit = a_unit()
    cache.put(unit)
    moved = cache.lookup(unit.cache_key(), content_digest(SHORT + "# edited\n"))
    assert moved.outcome is CacheOutcome.STALE
    assert moved.unit is None
    assert cache.stats.stale_rejections == 1
    assert unit.cache_key() not in cache


def test_a_non_hit_can_never_carry_a_unit():
    from company.runtime.context_cache import CacheLookup

    with pytest.raises(LifecycleError, match="must not carry a unit"):
        CacheLookup(key="k", outcome=CacheOutcome.MISS, unit=a_unit())


def test_a_lookup_without_an_observed_digest_is_refused():
    cache = ContextCache()
    with pytest.raises(LifecycleError, match="as it is now"):
        cache.lookup("file:a/b.py", "")


def test_read_once_calls_the_loader_exactly_once_for_unchanged_content():
    cache = ContextCache()
    calls: list[int] = []

    def loader() -> ContextUnit:
        calls.append(1)
        return a_unit()

    key = a_unit().cache_key()
    digest = content_digest(SHORT)
    first, first_lookup = cache.read_once(key, digest, loader)
    second, second_lookup = cache.read_once(key, digest, loader)
    assert calls == [1]
    assert first_lookup.outcome is CacheOutcome.MISS
    assert second_lookup.outcome is CacheOutcome.HIT
    assert first == second
    assert cache.stats.loads == 1
    assert cache.stats.reads_avoided == 1


def test_read_once_re_reads_when_the_source_moved():
    cache = ContextCache()
    calls: list[str] = []
    edited = SHORT + "# edited\n"

    def loader_a() -> ContextUnit:
        calls.append("a")
        return a_unit()

    def loader_b() -> ContextUnit:
        calls.append("b")
        return a_unit(text=edited)

    key = a_unit().cache_key()
    cache.read_once(key, content_digest(SHORT), loader_a)
    unit, lookup = cache.read_once(key, content_digest(edited), loader_b)
    assert calls == ["a", "b"]
    assert lookup.outcome is CacheOutcome.STALE
    assert unit.content_digest == content_digest(edited)


def test_read_once_refuses_a_loader_that_returns_something_else():
    cache = ContextCache()
    with pytest.raises(LifecycleError, match="worse than no cache"):
        cache.read_once(
            "file:a/other.py", content_digest(SHORT), lambda: a_unit()
        )


def test_read_once_refuses_a_loader_that_read_different_bytes():
    cache = ContextCache()
    with pytest.raises(LifecycleError, match="changed mid-read"):
        cache.read_once(
            a_unit().cache_key(), content_digest(SHORT + "x"), lambda: a_unit()
        )
    assert len(cache) == 0


def test_the_cache_may_not_change_what_a_unit_is_allowed_to_decide():
    cache = ContextCache()
    cache.put(a_unit(authority=UnitAuthority.OBSERVED))
    with pytest.raises(LifecycleError, match="may not change what a unit"):
        cache.put(a_unit(authority=UnitAuthority.CONTRACT))


def test_reuse_ratio_is_zero_rather_than_a_division_by_zero():
    assert CacheStats().reuse_ratio == 0.0
    assert CacheStats().lookups == 0


def test_the_cache_reads_nothing_itself():
    """Read authority lives in `company/runtime/authority.py`. A cache that
    could fetch its own misses would be a second one."""
    import ast
    from pathlib import Path

    tree = ast.parse(
        (Path(__file__).resolve().parents[1] / "company/runtime/context_cache.py")
        .read_text(encoding="utf-8")
    )
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    assert roots.isdisjoint({"pathlib", "os", "io", "subprocess", "open"})


# --------------------------------------------------------------------------
# Typed execution evidence
# --------------------------------------------------------------------------


def an_event(**kwargs) -> ExecutionEvidence:
    defaults = dict(
        kind=ExecutionEvidenceKind.SUITE_RUN,
        subject="tests/test_company_runtime.py",
        outcome=EvidenceOutcome.PASS,
        observed_on=TODAY,
        reported_by="external-engineering-runner",
        attempt_id="wo-p6a-attempt-1",
        sequence=1,
        commit="3f8da0a",
        selected=120,
    )
    defaults.update(kwargs)
    return ExecutionEvidence(**defaults)  # type: ignore[arg-type]


def test_the_same_observation_re_derived_keeps_one_identity():
    assert an_event().record_id() == an_event().record_id()


def test_a_volatile_measurement_does_not_move_the_identity():
    """`duration_s` describes the machine, not the event. Including it would
    make a deterministic re-observation produce a new id every time, which is
    the failure a UUID has."""
    assert an_event(duration_s=1.5).record_id() == an_event(duration_s=91.0).record_id()


def test_the_same_thing_observed_twice_stays_two_records():
    before = an_event(sequence=1, outcome=EvidenceOutcome.FAIL, failed=2)
    after = an_event(sequence=2)
    assert before.record_id() != after.record_id()
    ledger = EvidenceLedger(attempt_id="wo-p6a-attempt-1")
    ledger.extend((before, after))
    assert len(ledger) == 2


def test_a_changed_observation_changes_the_identity():
    assert an_event().record_id() != an_event(outcome=EvidenceOutcome.FAIL, failed=1).record_id()
    assert an_event().record_id() != an_event(commit="deadbee").record_id()


def test_re_adding_an_identical_record_is_a_no_op():
    ledger = EvidenceLedger(attempt_id="wo-p6a-attempt-1")
    first = ledger.add(an_event())
    second = ledger.add(an_event())
    assert first == second
    assert len(ledger) == 1


def test_a_record_may_not_be_rewritten_under_its_own_id():
    """A derived id is only trustworthy while what is behind it cannot change."""
    ledger = EvidenceLedger(attempt_id="wo-p6a-attempt-1")
    ledger.add(an_event())
    with pytest.raises(LifecycleError, match="body differs"):
        ledger.add(an_event(duration_s=42.0))


def test_evidence_from_another_attempt_is_refused():
    ledger = EvidenceLedger(attempt_id="wo-p6a-attempt-1")
    with pytest.raises(LifecycleError, match="another run"):
        ledger.add(an_event(attempt_id="wo-p6a-attempt-2"))


def test_a_passing_record_cannot_report_failures():
    with pytest.raises(LifecycleError, match="green or it is not"):
        an_event(failed=3)


def test_an_unknown_outcome_must_say_what_could_not_be_observed():
    with pytest.raises(LifecycleError, match="unexplained unknown is a shrug"):
        an_event(outcome=EvidenceOutcome.UNKNOWN, detail="")
    assert an_event(
        outcome=EvidenceOutcome.UNKNOWN, detail="the worktree was gone"
    ).outcome is EvidenceOutcome.UNKNOWN


def test_a_ledger_is_complete_only_when_nothing_failed_and_nothing_is_unknown():
    ledger = EvidenceLedger(attempt_id="wo-p6a-attempt-1")
    ledger.add(an_event())
    assert ledger.complete()
    ledger.add(
        an_event(sequence=2, outcome=EvidenceOutcome.UNKNOWN, detail="gate timed out")
    )
    assert not ledger.complete()
    assert len(ledger.unknowns()) == 1


def test_a_ledger_round_trips_and_refuses_a_forged_id():
    ledger = EvidenceLedger(attempt_id="wo-p6a-attempt-1")
    ledger.extend((an_event(), an_event(sequence=2, kind=ExecutionEvidenceKind.GATE_REPORT,
                                        subject="docs/gate.json")))
    payload = ledger.to_dict()
    restored = EvidenceLedger.from_dict(payload)
    assert restored.fingerprint() == ledger.fingerprint()
    assert restored.ordered() == ledger.ordered()

    payload["records"][0]["record_id"] = "0" * 16
    with pytest.raises(LifecycleError, match="does not match"):
        EvidenceLedger.from_dict(payload)


def test_a_record_refuses_a_field_outside_its_schema():
    with pytest.raises(LifecycleError, match="unknown field"):
        ExecutionEvidence.from_dict({**an_event().to_dict(), "and_also": "trust me"})


def test_a_record_holds_a_pointer_rather_than_a_body():
    with pytest.raises(LifecycleError, match="payload_digest is the pointer"):
        an_event(detail="x" * 2001)


def test_the_ledger_fingerprint_ignores_insertion_order():
    one = EvidenceLedger(attempt_id="a")
    two = EvidenceLedger(attempt_id="a")
    events = (
        an_event(attempt_id="a", sequence=1),
        an_event(attempt_id="a", sequence=2),
    )
    one.extend(events)
    two.extend(reversed(events))
    assert one.fingerprint() == two.fingerprint()


# --------------------------------------------------------------------------
# From the independent review
# --------------------------------------------------------------------------


def test_lines_are_newline_delimited_and_nothing_else():
    """Found by independent review. `str.splitlines()` also splits on form
    feed, vertical tab, the separators, NEL and U+2028/9, so a file containing
    any of them would be numbered differently here than by an editor, `sed -n`
    or a pytest node id - and the line range in the marker is the whole reason
    a compressed body is checkable rather than a summary."""
    for exotic in ("\f", "\v", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029"):
        text = "\n".join(
            (f"page{exotic}break" if i == 30 else f"line {i}") for i in range(1, 80)
        )
        body = compress(text, source="a/b.py", threshold_chars=10)
        assert body.full_lines == text.count("\n") + 1, repr(exotic)


def test_head_and_tail_are_verbatim_slices_of_crlf_text():
    crlf = "\r\n".join(f"line {i}" for i in range(1, 200))
    body = compress(crlf, source="a/b.py")
    assert crlf.startswith(body.head)
    assert crlf.endswith(body.tail)
    assert expand(body, crlf) == crlf


def test_the_elided_span_names_real_line_numbers_of_a_real_file():
    """Reconstruct this repository's own module from its marker."""
    from pathlib import Path

    relative = "company/integration/suites.py"
    text = (Path(__file__).resolve().parents[1] / relative).read_text(encoding="utf-8")
    body = compress(text, source=relative)
    start, end = body.elided_span
    lines = text.split("\n")
    assert "\n".join([body.head] + lines[start - 1 : end] + [body.tail]) == text


def test_a_stored_elision_does_not_answer_a_lookup_for_the_whole_file():
    """Found by independent review. The two share a source and a digest, so
    nothing was stale - the caller simply received less material than it asked
    for, counted as a saving."""
    whole = unit_from_source(
        LONG,
        kind=UnitKind.FILE,
        source="a/b.py",
        reason="the whole module",
        authority=UnitAuthority.OBSERVED,
        compress_over=10 ** 9,
    )
    elided = recompress(whole, threshold_chars=200)
    assert whole.cache_key() != elided.cache_key()

    cache = ContextCache()
    cache.put(elided)
    found = cache.lookup(whole.cache_key(), whole.content_digest)
    assert found.outcome is CacheOutcome.MISS
    assert found.unit is None


def test_two_elisions_with_different_budgets_are_not_the_same_unit():
    whole = unit_from_source(
        LONG,
        kind=UnitKind.FILE,
        source="a/b.py",
        reason="the whole module",
        authority=UnitAuthority.OBSERVED,
        compress_over=10 ** 9,
    )
    small = recompress(whole, threshold_chars=200)
    from company.runtime.context_units import compress as _compress

    wide = ContextUnit(
        kind=whole.kind,
        source=whole.source,
        reason=whole.reason,
        authority=whole.authority,
        body=_compress(LONG, source="a/b.py", head_lines=40, tail_lines=10, threshold_chars=200),
    )
    assert small.body.elided_span != wide.body.elided_span
    assert small.unit_id() != wide.unit_id()
    assert small.cache_key() != wide.cache_key()


def test_the_authority_refusal_survives_a_stale_eviction():
    """Found by independent review. The guard lived only in the live entry, so
    a stale eviction - exactly when a source is changing under the task -
    cleared it along with the value."""
    cache = ContextCache()
    cache.put(a_unit(authority=UnitAuthority.OBSERVED))
    key = a_unit().cache_key()
    assert cache.lookup(key, content_digest("something else\n")).outcome is CacheOutcome.STALE
    with pytest.raises(LifecycleError, match="may not change what a unit"):
        cache.put(a_unit(authority=UnitAuthority.CONTRACT))


def test_the_authority_refusal_survives_invalidate():
    cache = ContextCache()
    cache.put(a_unit(authority=UnitAuthority.OBSERVED))
    assert cache.invalidate(a_unit().cache_key())
    with pytest.raises(LifecycleError, match="may not change what a unit"):
        cache.put(a_unit(authority=UnitAuthority.CONTRACT))


def test_clear_forgets_the_remembered_authority_too():
    """`clear()` is the one operation that means "this task is over"."""
    cache = ContextCache()
    cache.put(a_unit(authority=UnitAuthority.OBSERVED))
    cache.clear()
    cache.put(a_unit(authority=UnitAuthority.CONTRACT))
    assert len(cache) == 1


def test_a_caller_can_still_construct_a_contract_unit():
    """The honest limit of the authority rule, stated as a test.

    No code path *in this package* raises a unit's authority - not
    `recompress`, not `ContextCache`, not `ContextBundle`. A caller that
    constructs a `CONTRACT` unit directly, or reaches for
    `dataclasses.replace`, is asserting authority itself, which is what
    construction means. The guarantee is about the package, not about Python.
    """
    from dataclasses import replace

    promoted = replace(a_unit(authority=UnitAuthority.DERIVED), authority=UnitAuthority.CONTRACT)
    assert promoted.binding is True


def test_the_ledger_names_the_field_that_differs():
    """Found by independent review: excluding `duration_s` from the identity
    buys a stable id, not a free retry, and the caller should be able to see
    which it was."""
    ledger = EvidenceLedger(attempt_id="wo-p6a-attempt-1")
    ledger.add(an_event(duration_s=1.0))
    with pytest.raises(LifecycleError, match="duration_s"):
        ledger.add(an_event(duration_s=1.5))
