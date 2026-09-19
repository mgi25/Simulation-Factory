"""Knowledge capsules: compact authoritative context, selected deterministically.

Read `knowledge/company_os/capsules/README.md` first. The modules are:

    budget    The size contract - one line per field, pointer-shaped pointers,
              short lists, a character ceiling. Enforced at construction.
    capsule   The `Capsule` itself: four types, one dataclass, no hierarchy.
    index     A directory of JSON files, every lookup by an explicit field, and
              the single-source-of-truth checks a capsule cannot run on itself.
    select    Task metadata in, `ContextRef`s out. No expansion by default.

Dependency direction is unchanged and one-way:

    ai_platform  <-  knowledge.company_os  <-  knowledge.company_os.capsules

Nothing here imports production code, and no production module imports this
(`company/README.md`, dependency rule). Standard library only.

What is deliberately absent: embeddings, a vector store, a similarity score, an
LLM summariser, a git watcher. Constitution rule 17 - prove need before
building. Staleness detection takes the observed digests as an argument rather
than going and looking, which keeps it a pure function and keeps this layer out
of the repository's business.

This package is not re-exported from `knowledge.company_os`; import it by its
own name, so the capsule layer can be added to or removed from a session's
context on its own.
"""

from knowledge.company_os.capsules.budget import (
    DEFAULT_BUDGET,
    POINTER_PATTERN,
    TAG_PATTERN,
    CapsuleBudget,
    CapsuleError,
    assert_line,
    assert_pointer,
    assert_tag,
)
from knowledge.company_os.capsules.capsule import (
    KNOWLEDGE_FIELDS,
    POINTER_FIELDS,
    STATEMENT_FIELDS,
    Capsule,
    CapsuleType,
    SourceDigest,
    budget_problems,
    flag_capsule_for_revalidation,
)
from knowledge.company_os.capsules.index import (
    REPO_ROOT,
    SEED_ROOT,
    CapsuleIndex,
    CapsuleStaleness,
    normalise_path,
    path_related,
)
from knowledge.company_os.capsules.digests import (
    digest_capsule_sources,
    digest_source_file,
    digest_source_files,
)
from knowledge.company_os.capsules.select import (
    CapsuleMatch,
    CapsuleSelection,
    Rejection,
    SelectionMetrics,
    TaskQuery,
    refs_for_task,
    select_capsules,
)

__all__ = [
    "DEFAULT_BUDGET",
    "KNOWLEDGE_FIELDS",
    "POINTER_FIELDS",
    "POINTER_PATTERN",
    "REPO_ROOT",
    "SEED_ROOT",
    "STATEMENT_FIELDS",
    "TAG_PATTERN",
    "Capsule",
    "CapsuleBudget",
    "CapsuleError",
    "CapsuleIndex",
    "CapsuleMatch",
    "CapsuleSelection",
    "CapsuleStaleness",
    "CapsuleType",
    "Rejection",
    "SelectionMetrics",
    "SourceDigest",
    "TaskQuery",
    "assert_line",
    "assert_pointer",
    "assert_tag",
    "budget_problems",
    "digest_capsule_sources",
    "digest_source_file",
    "digest_source_files",
    "flag_capsule_for_revalidation",
    "normalise_path",
    "path_related",
    "refs_for_task",
    "select_capsules",
]
