"""The two boundaries, both read off the syntax tree.

Production may not import Company OS, and Company OS may not reach into
production. They are different questions and they need different evidence.

## Inbound: an import is a name, so match names

`production_import_violations` walks every production module's imports and
reports any whose root is a Company OS package. Relative imports are already
resolved by `sources.module_imports`, so `from ..company import x` cannot slip
past by spelling. A finding names the file, the line and the module, which is
the whole fix list.

## Outbound: a write is a call, so match calls

Company OS writes constantly - every store puts JSON into a caller-supplied
state directory - so "does it write" is the wrong question and would answer
yes. The question is whether a write is *aimed at production*, and the
deterministic form of that is: a filesystem-mutating call one of whose
constant string arguments names a path under a production root.

`_call_constants` collects those constants from the call's arguments and from
the receiver chain, so `Path("sloped/scale.py").write_text(...)` is caught by
the constant on the receiver rather than missed because the call itself takes
only the text. A store that takes `output_dir` from its caller contributes no
constants and is not reported, which is correct: its authority is the caller's,
and the caller is bounded by `PathScope`.

This cannot see a path assembled at runtime from a variable, and says so. The
conditions that cover that case are the other three: no network, no process
spawn, and no delete - together they mean a Company OS module cannot publish,
shell out or destroy regardless of what path it computes.

## Why a shell counts as a network and a delete counts as production authority

`subprocess` is every capability at once: it can run `git push`, `ffmpeg`, or
`rm`. A control plane that may not publish therefore may not spawn, and the
check treats the import itself as the finding rather than trying to classify
the command. Deletion is refused everywhere in Company OS, not only under
production paths, because every store here is append-only by contract and a
delete call is evidence that one is not.
"""

from __future__ import annotations

import ast
from collections.abc import Sequence
from dataclasses import dataclass

from .sources import (
    COMPANY_OS_IMPORT_ROOTS,
    SourceModule,
    module_imports,
)


# Anything that can open a socket, directly or through a client library.
NETWORK_MODULES: frozenset[str] = frozenset(
    {
        "aiohttp",
        "ftplib",
        "http",
        "httpx",
        "imaplib",
        "poplib",
        "requests",
        "smtplib",
        "socket",
        "socketserver",
        "ssl",
        "telnetlib",
        "urllib",
        "urllib3",
        "webbrowser",
        "websocket",
        "websockets",
        "xmlrpc",
    }
)

# Model and inference clients. Bootstrap Mode runs deterministic code; a model
# call inside the control plane would also be an unbudgeted external spend.
MODEL_MODULES: frozenset[str] = frozenset(
    {
        "anthropic",
        "cohere",
        "google",
        "huggingface_hub",
        "litellm",
        "mistralai",
        "ollama",
        "openai",
        "tiktoken",
        "torch",
        "transformers",
        "vertexai",
    }
)

# Spawning a process hands out every authority this package refuses to hold.
PROCESS_MODULES: frozenset[str] = frozenset(
    {"multiprocessing", "pty", "subprocess"}
)

# `os` functions that spawn. Imported as attributes rather than modules, so
# they are matched on the call rather than on the import.
_PROCESS_OS_CALLS: frozenset[str] = frozenset(
    {
        "execl",
        "execle",
        "execlp",
        "execv",
        "execve",
        "execvp",
        "fork",
        "forkpty",
        "popen",
        "posix_spawn",
        "spawnl",
        "spawnv",
        "system",
    }
)

# Names that mean the filesystem whatever they are called on. `write_text` is
# not a method of anything else in this codebase, and `rmtree` is not a method
# of anything at all.
_UNAMBIGUOUS_FS_CALLS: frozenset[str] = frozenset(
    {
        "copytree",
        "hardlink_to",
        "makedirs",
        "mkdir",
        "removedirs",
        "rmtree",
        "symlink_to",
        "touch",
        "write_bytes",
        "write_text",
    }
)

# Names that mean the filesystem unless the receiver is another module.
# `destination.rename("sloped/x")` is exactly the write the scan exists to
# find, so a variable receiver has to count; `shutil.move` counts too.
_RECEIVER_QUALIFIED_FS_CALLS: frozenset[str] = frozenset(
    {
        "chmod",
        "copy2",
        "copyfile",
        "link",
        "move",
        "open",
        "rename",
        "renames",
        "rmdir",
        "symlink",
        "truncate",
        "unlink",
    }
)

# The three names that are ordinary methods of ordinary values. `str.replace`
# is in every path-normalising function in this repository, `list.remove` in
# half the stores, and `dict.copy` everywhere - and `text.replace("sloped/",
# "")` would otherwise read as a write into the race tree. These require the
# receiver to name a filesystem module, and accept the resulting blind spot:
# a false blocker on a string method would make the whole gate ignorable.
_STRING_LIKE_CALLS: frozenset[str] = frozenset({"copy", "remove", "replace"})

# Receivers that make an ambiguous name a filesystem call.
_FS_RECEIVERS: frozenset[str] = frozenset({"os", "shutil", "pathlib", "Path"})

# Removal names that are not a method of anything else.
_UNAMBIGUOUS_DELETE_CALLS: frozenset[str] = frozenset(
    {"removedirs", "rmdir", "rmtree", "unlink"}
)

# `remove` is `list.remove` far more often than it is `os.remove`, so it is the
# one deletion name that has to name its receiver.
_QUALIFIED_DELETE_CALLS: frozenset[str] = frozenset({"remove"})


@dataclass(frozen=True)
class Finding:
    """One violation: where it is, and what was found there."""

    path: str
    line: int
    detail: str

    def reference(self) -> str:
        return f"{self.path}:{self.line}"

    def rendered(self) -> str:
        return f"{self.path}:{self.line} {self.detail}"


def production_import_violations(modules: Sequence[SourceModule]) -> tuple[Finding, ...]:
    """Production modules that import Company OS, in file order."""
    out: list[Finding] = []
    for module in modules:
        for ref in module_imports(module):
            if ref.root in COMPANY_OS_IMPORT_ROOTS:
                out.append(
                    Finding(
                        module.path,
                        ref.line,
                        f"imports {ref.module!r}; production may not depend on Company OS",
                    )
                )
    return tuple(sorted(out, key=lambda item: (item.path, item.line)))


def forbidden_import_violations(
    modules: Sequence[SourceModule], forbidden: frozenset[str], why: str
) -> tuple[Finding, ...]:
    """Company OS modules importing a root from `forbidden`."""
    out: list[Finding] = []
    for module in modules:
        for ref in module_imports(module):
            if ref.root in forbidden:
                out.append(Finding(module.path, ref.line, f"imports {ref.module!r}: {why}"))
    return tuple(sorted(out, key=lambda item: (item.path, item.line)))


def non_first_party_imports(
    modules: Sequence[SourceModule], first_party: Sequence[str]
) -> tuple[Finding, ...]:
    """Imports that are neither standard library nor a first-party root.

    A new third-party dependency in the control plane is a
    `mandatory_review_triggers.new_dependency` event in `permissions.yaml`, and
    it also breaks the claim that Company OS can be dropped into any checkout.
    """
    from .sources import is_stdlib

    allowed = set(first_party)
    out: list[Finding] = []
    for module in modules:
        for ref in module_imports(module):
            root = ref.root
            if not root or root in allowed or is_stdlib(root):
                continue
            out.append(
                Finding(module.path, ref.line, f"imports {ref.module!r}, which is not stdlib")
            )
    return tuple(sorted(out, key=lambda item: (item.path, item.line)))


def process_spawn_violations(modules: Sequence[SourceModule]) -> tuple[Finding, ...]:
    """Process spawning, by import or by `os.<call>`."""
    out = list(
        forbidden_import_violations(
            modules,
            PROCESS_MODULES,
            "spawning a process grants every authority this package refuses to hold",
        )
    )
    for module in modules:
        for node in ast.walk(module.tree):
            if not isinstance(node, ast.Call):
                continue
            name = _called_name(node.func)
            if name in _PROCESS_OS_CALLS and _receiver_root(node.func) == "os":
                out.append(Finding(module.path, node.lineno, f"calls os.{name}"))
    return tuple(sorted(set(out), key=lambda item: (item.path, item.line, item.detail)))


def delete_call_violations(modules: Sequence[SourceModule]) -> tuple[Finding, ...]:
    """Any call that removes a file or directory."""
    out: list[Finding] = []
    for module in modules:
        for node in ast.walk(module.tree):
            if not isinstance(node, ast.Call):
                continue
            name = _called_name(node.func)
            deletes = name in _UNAMBIGUOUS_DELETE_CALLS or (
                name in _QUALIFIED_DELETE_CALLS and _receiver_root(node.func) in _FS_RECEIVERS
            )
            if deletes:
                out.append(
                    Finding(
                        module.path,
                        node.lineno,
                        f"calls {name}(); Company OS stores are append-only and hold "
                        "no delete authority",
                    )
                )
    return tuple(sorted(out, key=lambda item: (item.path, item.line)))


def production_write_violations(
    modules: Sequence[SourceModule], production_roots: Sequence[str]
) -> tuple[Finding, ...]:
    """Filesystem-mutating calls aimed at a constant path under a production root."""
    roots = set(production_roots)
    out: list[Finding] = []
    for module in modules:
        modules_bound = _module_names(module)
        for node in ast.walk(module.tree):
            if not isinstance(node, ast.Call) or not is_filesystem_call(node, modules_bound):
                continue
            for constant in _call_constants(node):
                root = _path_root(constant)
                if root and root in roots:
                    out.append(
                        Finding(
                            module.path,
                            node.lineno,
                            f"{_called_name(node.func)}() targets {constant!r} under the "
                            f"production root {root}/",
                        )
                    )
    return tuple(sorted(set(out), key=lambda item: (item.path, item.line, item.detail)))


def is_filesystem_call(node: ast.Call, module_names: frozenset[str] = frozenset()) -> bool:
    """Does this call touch the filesystem?

    Four answers, in order. The name means nothing else (`write_text`,
    `rmtree`) - yes. The name is also an ordinary method of an ordinary value
    (`replace`, `remove`, `copy`) - only with a filesystem module in front of
    it. The name is ambiguous and the receiver is another module - no, which
    is how `dataclasses.replace` stops being `Path.replace`. Otherwise the
    receiver is a variable or an expression that could hold a path, and the
    call counts: `destination.rename("sloped/x")` is exactly the write this
    scan exists to find, and the production-root constant is what turns it
    into a finding rather than noise.
    """
    name = _called_name(node.func)
    if not name:
        return False
    if name in _UNAMBIGUOUS_FS_CALLS:
        return True
    if name in _STRING_LIKE_CALLS:
        return _receiver_root(node.func) in _FS_RECEIVERS
    if name not in _RECEIVER_QUALIFIED_FS_CALLS:
        return False
    if isinstance(node.func, ast.Name):
        return name == "open"  # the builtin
    root = _receiver_root(node.func)
    if root in _FS_RECEIVERS:
        return True
    return root not in module_names


def _module_names(module: SourceModule) -> frozenset[str]:
    """Names this file binds to a module, so `x.replace` can be told from `Path.replace`."""
    names: set[str] = set()
    for node in ast.walk(module.tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".", 1)[0])
    return frozenset(names)


def _called_name(func: ast.expr) -> str:
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _receiver_root(func: ast.expr) -> str:
    """The leftmost name in `a.b.c` - `a` - or an empty string."""
    node: ast.expr = func
    while isinstance(node, ast.Attribute):
        node = node.value
    return node.id if isinstance(node, ast.Name) else ""


def _call_constants(node: ast.Call) -> tuple[str, ...]:
    """Every string constant in the call's arguments and in its receiver chain."""
    out: list[str] = []
    sources: list[ast.AST] = list(node.args) + [kw.value for kw in node.keywords]
    if isinstance(node.func, ast.Attribute):
        sources.append(node.func.value)
    for source in sources:
        for child in ast.walk(source):
            if isinstance(child, ast.Constant) and isinstance(child.value, str):
                out.append(child.value)
    return tuple(out)


def _path_root(value: str) -> str:
    """The first path segment of `value`, if it looks like a relative path."""
    text = value.strip().replace("\\", "/")
    if not text or text.startswith("/") or ":" in text.split("/", 1)[0]:
        return ""
    while text.startswith("./"):
        text = text[2:]
    head = text.split("/", 1)[0]
    return head if head and head not in (".", "..") else ""


__all__ = [
    "MODEL_MODULES",
    "NETWORK_MODULES",
    "PROCESS_MODULES",
    "Finding",
    "delete_call_violations",
    "forbidden_import_violations",
    "is_filesystem_call",
    "non_first_party_imports",
    "process_spawn_violations",
    "production_import_violations",
    "production_write_violations",
]
