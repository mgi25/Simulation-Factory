"""Rewrite the evidence README's measurement table from measurements.json.

The numbers went stale once already (the harness changed and the prose did
not), which the independent review caught in the one paragraph whose job is to
keep the headline honest. Deriving them removes the way that happens.
"""

import io
import json
import re
from pathlib import Path

EV = Path("docs/evidence/company_os_p6a_typed_evidence_cache_context")
m = json.loads((EV / "measurements.json").read_text(encoding="utf-8"))
cb, ro, cs = m["context_bytes"], m["read_once"], m["cache_stability"]
app = cs["one_unit_appended"]

table = f"""| Measurement | Value |
|---|---|
| bundle chars, nothing compressed | {cb['whole_bundle_chars']:,} |
| bundle chars, compressed | {cb['compressed_bundle_chars']:,} |
| reduction in chars supplied up front | {cb['reduction_pct']}% |
| reads requested / distinct sources | {ro['reads_requested']} / {ro['distinct_sources']} |
| loader calls | {ro['loader_calls']} |
| reads avoided by reuse | {ro['reads_avoided']} |
| reuse ratio | {ro['reuse_ratio']} — hits over *lookups*, and there is one more lookup than there are reads (the deliberate staleness probe). Not {ro['reads_avoided']}/{ro['reads_requested']}. |
| stale rejections after one source was edited | {ro['stale_rejections']}, no unit returned |
| prefix reuse, same units assembled in reverse | {cs['reassembled_in_reverse']['ratio']:.3f} (byte-identical) |
| prefix reuse, appending an evidence unit (sorts last) | {app['evidence_sorts_last']['ratio']:.3f} — the whole previous render is the prefix |
| prefix reuse, appending another module (mid-order) | **{app['another_module_mid_order']['ratio']:.3f}** |
| prefix reuse, appending another capsule (near the top) | **{app['another_capsule_near_the_top']['ratio']:.3f}** |

These are the values in `measurements.json` at this commit. The harness
measures the *live* files, so the byte counts move whenever one of the eight
measured sources is edited — including by a later commit on this branch. The
ratios are structural and do not move. Re-run the harness rather than trusting
the table if the two ever disagree.
"""

path = EV / "README.md"
src = io.open(path, encoding="utf-8").read()

start = src.index("| Measurement | Value |")
end = src.index("**What the ", start)
src = src[:start] + table + "\n" + src[end:]

# the headline paragraph, from the same source
src = re.sub(
    r"\*\*What the [\d.]+% is and is not\.\*\*.*?\"the task costs\s*\n?[\d.]+% less\"\.",
    (
        f"**What the {cb['reduction_pct']}% is and is not.** It is the reduction in "
        "characters *supplied up front*. It is not a reduction in what a session ends "
        "up reading: an elided body is a pointer, and a session that needs the body "
        "expands it, paying the difference then. The claim this number supports is "
        f"\"a bundle can carry {cb['units']} sources for "
        f"{cb['compressed_bundle_chars'] / 1000:.0f} KB instead of "
        f"{cb['whole_bundle_chars'] / 1000:.0f} KB\", not \"the task costs "
        f"{cb['reduction_pct']}% less\"."
    ),
    src,
    flags=re.S,
)

io.open(path, "w", encoding="utf-8", newline="\n").write(src)
print("README numbers rewritten from measurements.json")
print(f"  reduction {cb['reduction_pct']}%  whole {cb['whole_bundle_chars']}  compressed {cb['compressed_bundle_chars']}")
