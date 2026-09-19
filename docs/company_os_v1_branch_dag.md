# Company OS V1 — Branch DAG (derived from git ancestry, not names)

Every relationship below was produced by `git merge-base`, `git merge-base
--is-ancestor`, `git rev-list --count` and `git diff --stat` against
`origin/company-os-v1-read-efficiency-v3b` (`4acee87`) and
`origin/company-os-v1-bootstrap` (`01a1638`), run on 2026-09-19. Raw output:
`docs/validation/company_os_v1_integration_audit/branch_audit_results.txt`.

## 1. The headline finding

**There is one line, not thirty-seven.** `company-os-v1-bootstrap` no longer
names an early commit — it has been fast-forwarded to `01a1638`, the same
commit `company-os-v1-external-runner-hardening` points to. Every other
`company-os-v1-*` branch except two (§3) is `merge-base --is-ancestor`-true
against that commit, and `01a1638` is itself `--is-ancestor`-true against
`company-os-v1-read-efficiency-v3b`. The "37 branches" are checkpoints along
one already-merged history, not 37 things waiting to be merged.

## 2. The backbone, in actual commit order

Diverges from `main` at `eaca65e` (V26 integration). 50 commits follow to
`01a1638` (23 of them real `git merge` commits, not squashes — second parents
verified below), then 15 more first-parent commits to `4acee87`
(`company-os-v1-read-efficiency-v3b`, the audit's base).

### 2a. Direct bootstrap commits (no branch merge)
`e3dcdd3` control-plane boundary → `1e5bdf5` constitution → `0100e3e`
workforce registry → `437a84e` autonomy/CEO gates → `ccbb13b` employee
contract schema → `bf26b58` task handoff schema.

### 2b. Merged phase branches, in merge order (earliest first)
| # | Merge commit | Subject | Branch merged | Branch HEAD |
|---|---|---|---|---|
| 1 | `b43ffa2` | Merge Company OS deterministic core runtime | `company-os-v1-core-runtime` | `3b17a4e` |
| 2 | `ab76396` | Merge Company OS AI efficiency and knowledge primitives | `company-os-v1-ai-efficiency` | `1802c8f` |
| 3 | `dde3b96` | Merge Company OS Phase 2 runtime lifecycle | `company-os-v1-runtime-integration` | `c1b1ee6` |
| 4 | `21ee017` | Merge Company OS Phase 2 knowledge capsules | `company-os-v1-knowledge-capsules` | `924b144` |
| 5 | `2cdc2d6` | Merge Company OS Phase 3 context assembly | `company-os-v1-context-assembly` | `e2a7a8e` |
| 6 | `c106f53` | Merge Company OS Phase 3 research intelligence | `company-os-v1-research-intelligence` | `3cea5a9` |
| 7 | `5ab5441` | Merge Company OS Phase 4 research ingestion | `company-os-v1-research-ingestion` | `e49ce38` |
| 8 | `a961e3e` | Merge Company OS external session execution | `company-os-v1-session-execution` | `054b96b` |
| 9 | `be654e0` | Merge Company OS Phase 5 research batches | `company-os-v1-research-batches` | `b89734e` |
| 10 | `aef2dbd` | Merge first Company OS dogfood task | `company-os-v1-dogfood-research-capsule` | `09d837f` |
| 11 | `156531b` | Merge Company OS workforce foundation | `company-os-v1-workforce-foundation` | `eb2014d` |
| 12 | `46bf9e2` | Merge audited context expansion | `company-os-v1-context-expansion` | `5c05aab` |
| 13 | `01ab762` | Merge organizational intelligence foundation | `company-os-v1-org-intelligence` | `6d49cb0` |
| 14 | `3e08281` | Merge audited external execution transport | `company-os-v1-execution-transport` | `a523d38` |
| 15 | `d604139` | Merge finance foundation | `company-os-v1-finance-foundation` | `a88f586` |
| 16 | `d9afc48` | Merge analytics and experiment intelligence | `company-os-v1-analytics-experiments` | `b75865b` |
| 17 | `746b4b7` | Merge CEO dashboard foundation | `company-os-v1-ceo-dashboard` | `e762f52` |
| 18 | `47543e3` | Merge runtime-validation decoupling | `company-os-v1-runtime-validation-decouple` | `f71ab99` |
| 19 | `afed4f2` | Merge finance usage-cost dogfood | `company-os-v1-finance-cost-dogfood` | `a653a2f` |
| 20 | `ac9049d` | Merge YouTube Studio export ingestion | `company-os-v1-youtube-studio-ingestion-**reviewed**` | `583e457` |
| 21 | `69caed2` | Merge production integration gate | `company-os-v1-production-integration-gate` | `1149f89` |
| 22 | `f49df25` | Merge dashboard record identity fix | `company-os-v1-dashboard-observation-identity-fix-**reviewed**` | `d899467` |
| 23 | `208b6fb` | Merge Company OS v1 real-evidence acceptance | `company-os-v1-real-evidence-acceptance` | `cf6b1c7` |

Row 20 and row 22 merge the **`-reviewed`** branch, not the plainer-named
one — see §3, this is the naming trap the milestone brief warned about.

### 2c. Direct commits after the last merge, up to bootstrap/runner-hardening HEAD
`d28d68b` measure context/token efficiency (= `company-os-v1-efficiency-harness`
HEAD, exact SHA match) → `ce0d8f5` emit real execution efficiency telemetry
(= `company-os-v1-real-efficiency-telemetry` HEAD) → `290a37d`/`48b8341`/
`40c56da`/`895f436`/`324539c` YouTube connectivity work (`324539c` =
`company-os-v1-youtube-connectivity` HEAD) → `6b50b11`/`79e0bdd`/`d8a1516`
engineering lifecycle work (`d8a1516` = `company-os-v1-engineering-execution`
HEAD) → `4b78729`/`7ca7edd`/`89915ce`/`152da44`/`c29ad37`/`bf62eaa`/`ed2c65d`/
`e930467`/`44fbfb1` external runner build-out (`44fbfb1` =
`company-os-v1-external-engineering-runner` HEAD) → `021a618`/`01a1638`
hardening fixes (`01a1638` = `company-os-v1-external-runner-hardening` =
`company-os-v1-bootstrap`, current ref).

### 2d. Post-bootstrap efficiency lineage (the 15 commits to V3B)
`5c1c035` **eng-ai-resource-efficiency-v2** (attempt 1, `wo-ceo-2026-09-18-ai-resource-efficiency-v2`,
REJECTED at review) is *not* on this line — it is a sibling of the next three
commits, same work order, earlier attempt. → `25fddf8`→`1a50f5e`→`5d73557`
**eng-ai-resource-efficiency-v2-operational** (attempts 2–3 of the same work
order, `changes_required` fixed) → `8a3c45d`→`1083652`→`89cd588`→`4b6064d`
**company-os-v1-consumer-resource-mode** → `30878b1`→`70a62f4`
**company-os-v1-repository-exploration-efficiency** → `9b5f224`→`274d124`→
`6dd7891` **company-os-v1-repository-exploration-efficiency-v2** → `ba851fa`
**company-os-v1-read-efficiency-v3a** → `9e6c604`→`4acee87`
**company-os-v1-read-efficiency-v3b** (audit base).

## 3. The two naming traps (verified by diff, not by name)

**`company-os-v1-dashboard-observation-identity-fix-reviewed`** (`d899467`)
is the *ancestor*; **`company-os-v1-dashboard-observation-identity-fix`**
(`a9bd079`) is 2 commits *ahead* of it (`noop`, `Remove accidental review
artifact`), and the two trees are byte-identical (`git diff --stat` empty).
The plain name is the messier duplicate, not the earlier draft.

**`company-os-v1-youtube-studio-ingestion-reviewed`** (`583e457`) is the
*ancestor*; **`company-os-v1-youtube-studio-ingestion`** (`41f8d74`) is 12
commits ahead (`temp`, `noop`, `x`, `cleanup accidental temporary file` ×4,
repeated), trees again byte-identical. Same trap, larger.

## 4. Branches this DAG does not place on the backbone

10 `eng-*` single/few-commit branches fork off specific points on the
backbone or the post-bootstrap lineage and go nowhere else — each is a
matched-benchmark dogfood job, several with their receipts already stored
inside V3B's own `docs/validation/` tree. Detail and evidence in
`docs/company_os_v1_integration_audit.md` §4–§5.
