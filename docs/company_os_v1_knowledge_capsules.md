# Handoff — Company OS v1, Phase 2 (knowledge capsules + retrieval)

Branch: `company-os-v1-knowledge-capsules`, from the integrated bootstrap head
`ab76396`.

## Objective

Build the smallest useful capsule/retrieval layer that materially reduces
future context usage without losing accuracy. A future session working in
`company/runtime/` should receive one 2,300-character contract instead of
reading a 17,167-character package to establish six facts.

No vector database, no embeddings, no LLM retrieval, no semantic agent, no
external dependency, no git monitoring. Standard library only.

## What was built

`knowledge/company_os/capsules/`, four modules and a seed directory:

| Module | Holds |
|---|---|
| `budget.py` | Every size limit, and the three primitive guards that enforce them |
| `capsule.py` | `Capsule`, four types, one dataclass, no hierarchy |
| `index.py` | `CapsuleIndex`: deterministic lookup, integrity, staleness |
| `select.py` | `TaskQuery` → `CapsuleSelection` → `ContextRef`s and metrics |
| `__main__.py` | `list` / `select` / `show` / `check` from a shell |
| `seeds/*.json` | Seven authoritative Company OS capsules |

## Architecture in six lines

    task metadata (paths, capability tags, ids)
        -> TaskQuery            filters: type, owner. signals: paths, tags, ids
        -> select_capsules      rank (-score, id), cut to max_capsules
        -> CapsuleSelection     matches + every rejection with its reason
        -> refs()               ContextRefs, ids only, nothing expanded
        -> ContextManifest      the existing ai_platform structure, unchanged

Dependency direction is unchanged and one-way:
`ai_platform <- knowledge.company_os <- knowledge.company_os.capsules`.
The package is *not* re-exported from `knowledge.company_os`, so the capsule
layer can be added to or removed from a session's context on its own.

## The measurement that justifies the layer

| | chars |
|---|---|
| `company/runtime/` source | 17,167 |
| `company-runtime` capsule | 2,300 |
| whole control plane (`company/`, `ai_platform/`, `knowledge/company_os/`) | 196,246 |
| all seven capsules | 17,918 |

7.5× for one boundary, 11.0× for the set. Both ratios are asserted as tests
with margin, so a capsule that starts growing into a README fails CI rather
than quietly costing more than it saves.

## The seven seed capsules

| id | type | owner | covers |
|---|---|---|---|
| `company-os-control-plane` | system | company-os | composes the other six |
| `company-bootstrap-policy` | policy | ceo | constitution, permissions, org, both schemas |
| `company-runtime` | module | workstream-codex | `company/runtime` |
| `company-validation` | module | workstream-codex | `company/validation` |
| `ai-platform` | module | workstream-claude | `ai_platform` |
| `company-knowledge-store` | module | workstream-claude | records, freshness, ledger |
| `company-knowledge-capsules` | module | workstream-claude | this layer |

The brief asked for five; `company-bootstrap-policy` was added because the
constitutional rules are the context every session needs first and nothing else
pointed at them, and `company-knowledge-capsules` because the layer has to
describe itself or the next session reads it in full to find out what it is.
The policy capsule is also the only real instance of the `policy` type — a type
with no user is the design smell this contract exists to avoid.

Every capsule was written from the current files and tests. Nothing in Race,
Fight, V30 or any production module was read or scanned.

## Size contract

Enforced at construction; a capsule that breaks any of it cannot be built.

- capsule canonical JSON ≤ 4000 chars (largest seed: 2,780)
- **no field holds more than one line** — this is the anti-dump rule, and it is
  what a pasted function, config block or diff fails first
- pointer fields must match `POINTER_PATTERN` — this is what a *single line* of
  source fails, since source carries spaces, parens and semicolons
- purpose ≤ 400, any statement ≤ 240, any list ≤ 8, paths ≤ 12 per field,
  knowledge links ≤ 12 across all four link fields

Characters, not tokens: a token count belongs to one tokenizer and the platform
is provider-agnostic by contract. These are budgets chosen so a truthful capsule
fits with roughly 30% headroom, not measurements.

## Invariants preserved

1. **No subagents.** This session spawned none. The layer adds no execution
   path of any kind. `test_the_no_subagent_rule_is_exactly_where_it_was`
   re-asserts both enforcement points (`ExecutionPolicy`,
   `enforce_no_subagents`) from this branch's test file.
2. **Production independence.** Zero existing files were modified — the diff is
   purely additive. Two tests prove it from both directions: the capsule
   package imports only stdlib, `ai_platform` and `knowledge`; and no file in
   `sloped/` or `tools/` mentions either package.
3. **Facts ≠ hypotheses ≠ decisions.** A capsule links facts, decisions and
   both learning types by id, and has no `hypotheses` field — a capsule is
   authoritative context and an open hypothesis is explicitly not.
4. **One source of truth.** No prose twin of any linked record; `integrity()`
   detects duplicate path ownership, dangling dependencies and links to records
   that are not in the store.
5. **Minimum relevant context.** `refs()` returns ids. Expanding to knowledge
   or test references is a separate, explicit call.
6. **Determinism.** Sorted loading, sorted ids, `(-score, id)` ranking, sorted
   rejections, canonical JSON. Two loads agree; two selections agree.
7. **Codex-owned code untouched.** `company/runtime/` and `company/validation/`
   are described by capsules and not edited; both capsules record the real
   import cycle between them as a risk.

## Tests

`tests/test_company_os_capsules.py` — 66 tests, all passing. Combined Company
OS run: **151 passed** across

    tests/test_company_os_capsules.py
    tests/test_company_os_knowledge.py
    tests/test_company_os_ai_platform.py
    tests/test_company_runtime.py

Each item the brief asked to be proved has a test: bounded size; source and
file dumps refused as references (both the multi-line and the single-line
form); deterministic serialisation and byte-identical seed files; deterministic
lookup ordering; the worked path+capability selection; unrelated capsules
rejected with a reason; missing knowledge references detected; all four
staleness conditions, individually and accumulated; duplicate capsule ids
refused; the seven seeds loading and passing integrity against the real store
and checkout; no production dependency in either direction; and the no-subagent
rule unchanged.

Two tests failed on first run and both were my claims, not the code: the seed
set is *not* smaller than one module's source (17,918 vs 17,167 — the true
claim is per-capsule, 7.5×), and `./ai_platform/` is refused rather than
normalised, because one canonical spelling per path is what stops the duplicate
check being dodged. Both are now asserted as what is actually true.

## Dependencies

None added. Standard library, plus `ai_platform` and `knowledge.company_os`,
which were already there. `pytest` for tests, as before.

## Risks and open questions

1. **Seeds carry no `source_digests`.** The structure and the comparison
   function exist and are tested, but nothing populates them, so the
   source-changed condition cannot fire on shipped capsules. Populating them
   needs a digest-computing step, which is the git-monitoring half the brief
   deferred. Until then, review expiry and manual flagging are the live
   conditions.
2. **`last_reviewed` is asserted, not measured.** A capsule is only as true as
   its author's claim about when they last checked it. Nothing detects a
   capsule that says it was reviewed today and was not.
3. **`max_capsules=6` and 4000 chars are judgment.** They are budgets, and the
   only evidence for them is that seven honest capsules fit with headroom. If
   a later capsule genuinely cannot fit, the right response is to check whether
   it is describing two boundaries, not to raise the number.
4. **Path ownership dedup is exact-match after normalisation.** A `system`
   capsule owning `company/` and a `module` capsule owning `company/runtime`
   would not be flagged. That is deliberate — containment is composition, not
   duplication — but it means the check cannot catch a badly drawn boundary,
   only a literally duplicated one. The seeds avoid the situation entirely:
   `company-os-control-plane` owns no paths.
5. **The runtime/validation cycle is real.** `runtime.config` imports
   `validation.yaml_subset`; `validation.bootstrap` imports `runtime.config`.
   `dependency_closure` handles it and there is a test for that, but the cycle
   is in the code Codex owns and is not this branch's to fix.

## Recommended next integration step

Wire the selector into whatever assembles a session's request, so a task's
paths and capability tags produce `module_contracts=selection.refs()` on a
`ContextManifest` instead of a hand-written list. That is one call
(`refs_for_task`) and it is the point at which the ratio above stops being a
measurement and starts being a saving.

After that, and only if wanted: a small `digest` step that fills
`source_digests` at review time, which turns condition 2 on without becoming a
git watcher.

## Rollback

Delete `knowledge/company_os/capsules/` and
`tests/test_company_os_capsules.py`. Nothing else references either. No
existing file was modified, so there is nothing to revert.
