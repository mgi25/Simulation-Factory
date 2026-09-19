# Company OS knowledge capsules

A capsule is what a session is given *instead of* reading a subsystem. Seven of
them describe the whole control plane in 17,918 characters; the control plane
itself is 196,246. That ratio is the only reason this layer exists, and every
constraint below protects it.

No database, no embeddings, no similarity score, no git watcher. `dataclasses`,
`json`, and a directory of files.

## Where capsules live

```
knowledge/company_os/capsules/seeds/<id>.json
```

`<id>` is lowercase `[a-z0-9._-]`, because it is also the filename. Files are
written with sorted keys, so two sessions writing different capsules never
conflict and a capsule change shows up in `git diff` as the sentence that
changed.

## The four types

| Type | Answers | Must declare |
|---|---|---|
| `module` | What is this code, and what may I do to it? | `owns_paths`, `tests` |
| `system` | What is this made of? | `dependencies` |
| `policy` | What rules bind me here? | `invariants` |
| `project` | What is this piece of work? | `owns_paths` |

One dataclass, one enum, four rows in `_TYPE_REQUIREMENTS`. No inheritance: a
base class and four subclasses would buy polymorphism nobody calls.

## The size contract

Enforced at construction. A capsule that breaks any of these cannot be built.

| Limit | Value | Why |
|---|---|---|
| capsule, canonical JSON | 4000 chars | above it, it is a second README |
| any field | **one line** | the whole anti-dump rule |
| pointer fields | `POINTER_PATTERN` | source has spaces and parens; pointers do not |
| `purpose` | 400 chars | |
| any statement | 240 chars | |
| any list | 8 items | nine invariants is nine sentences, not nine invariants |
| paths per field | 12 | |
| knowledge links, all four fields | 12 | |

Characters, not tokens: a token count belongs to one tokenizer, and the
platform is provider-agnostic by contract.

The one-line rule does the heavy lifting. A pasted function, a copied config
block and a quoted diff all carry a newline. A single line of source gets past
that and is caught by the pointer shape instead.

## What a capsule links, and what it does not

`facts`, `decisions`, `experiment_learnings`, `failure_learnings` — by id,
never by content. There is deliberately **no `hypotheses` field**: a capsule is
handed to a session as authoritative context, and an open hypothesis is the one
record type that is explicitly not authoritative (constitution rule 16).

For the same reason there is no prose "key decisions" field beside the
`decisions` id list. Rule 15 stores a canonical fact once; a summary of a
decision inside a capsule is a second copy that will drift, invisibly, because
both look authoritative.

## Selecting

```python
from knowledge.company_os.capsules import CapsuleIndex, TaskQuery, select_capsules

index = CapsuleIndex.load()                       # defaults to seeds/
selection = select_capsules(index, TaskQuery(
    paths=("company/runtime/",),
    capabilities=("capability_routing",),
))
selection.ids()                                   # ('company-runtime', 'company-validation')
selection.refs()                                  # ContextRefs, ready for a ContextManifest
selection.metrics().chars                         # what sending them costs
```

`types` and `owner` are **filters** — fail one and you are out. `paths`,
`capabilities` and `capsule_ids` are **signals** — they score, and a capsule
that matches none of them is not selected. Every rejection carries which of the
two happened.

Ranking is `(-score, id)`; an explicit id is worth 100, every other signal 10, a
dependency 1. Coarse on purpose: anybody can reproduce the ranking by hand from
the query, which is what makes a selection reviewable.

`refs()` returns references. `knowledge_refs()` and `test_refs()` are separate,
opt-in calls — a task that needs the decision behind a boundary asks for it,
and a task that does not never pays for it.

## Freshness

Four conditions, each a pure function of data the caller supplies:

```python
index.staleness(today, store, observed_digests)
```

| Condition | Comes from |
|---|---|
| review expired | `last_reviewed` + the `Freshness` class |
| source changed | `source_digests` vs the digests the caller observed |
| decision superseded | the `KnowledgeStore` |
| flagged | `flag_capsule_for_revalidation(capsule, reason)` |

Nothing here reads the repository or shells out to git — that is why staleness
stays a pure function and why `observed_digests` is an argument. **The shipped
seeds carry no `source_digests` yet**, so the source-changed condition cannot
fire on them until a caller supplies them.

`digest_source_file`, `digest_source_files`, and `digest_capsule_sources`
provide the missing observation mechanism. They calculate SHA-256 over raw
bytes for caller-supplied repository-relative file paths. They never expand a
directory or glob, scan the repository, or invoke Git. Seed digests remain a
separate maintenance pass so adding the mechanism does not rewrite every seed.

Flagging a `permanent` capsule raises, for the reason it raises for a record:
if an invariant needs revalidation, the class was wrong.

## Integrity

`index.integrity(store, repo_root)` reports what a capsule cannot notice about
itself: two capsules claiming one path, a dependency on a capsule id nobody
defines, a link to a record that is not in the store, a path that has left the
repository. Both arguments are optional — the structural checks run with
neither a store nor a checkout.

It does not look for contradictions between two English sentences. That is a
reasoning task, and `KnowledgeStore.contradictions` already draws the same line.

## From the command line

```
python -m knowledge.company_os.capsules list
python -m knowledge.company_os.capsules select --path company/runtime/ --capability capability_routing
python -m knowledge.company_os.capsules show company-runtime
python -m knowledge.company_os.capsules check          # non-zero if anything is wrong or stale
```

## Writing one

Build a `Capsule`, then `CapsuleIndex.write(capsule)`. Validation is at
construction, so a capsule that exists is a capsule that fits. Keep
`last_reviewed` honest: it is asserted by the author, not measured, and it is
the only thing standing between a capsule and confident staleness.
