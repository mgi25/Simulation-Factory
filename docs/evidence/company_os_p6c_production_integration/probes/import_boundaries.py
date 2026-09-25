"""Import-boundary scan for the P6C integration (AST and raw text, with positive controls)."""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
COMPANY_OS = ("company", "ai_platform", "knowledge", "intelligence")


def modules(package: str) -> list[Path]:
    return sorted((ROOT / package).rglob("*.py"))


def ast_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                found.add(node.module)
        elif isinstance(node, ast.Call) and getattr(node.func, "attr", getattr(node.func, "id", "")) in (
            "import_module",
            "__import__",
        ):
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                found.add(node.args[0].value)
    return found


def hits(package: str, targets: tuple[str, ...]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {"ast": [], "text": []}
    pattern = re.compile(r"^\s*(?:from|import)\s+(" + "|".join(re.escape(t) for t in targets) + r")(?:\.|\s|$)", re.M)
    for path in modules(package):
        rel = path.relative_to(ROOT).as_posix()
        for name in sorted(ast_imports(path)):
            if any(name == t or name.startswith(t + ".") for t in targets):
                out["ast"].append(f"{rel} -> {name}")
        for match in pattern.finditer(path.read_text(encoding="utf-8")):
            out["text"].append(f"{rel}: {match.group(0).strip()}")
    return out


report = {
    "company/experience -> company.integration": hits("company/experience", ("company.integration",)),
    "company/experience -> tools.engineering_runner / tools": hits("company/experience", ("tools.engineering_runner", "tools")),
    "tools/engineering_runner -> Company OS": hits("tools/engineering_runner", COMPANY_OS),
    "company (all) -> tools.engineering_runner": hits("company", ("tools.engineering_runner",)),
    # positive controls: these must be non-zero or the scanner is blind
    "CONTROL company/experience -> company.*": hits("company/experience", ("company",)),
    "CONTROL tools/engineering_runner -> json/subprocess": hits("tools/engineering_runner", ("json", "subprocess")),
}
cli = []
for path in modules("tools/engineering_runner"):
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if "company.experience" in line or "company.integration" in line:
            cli.append(f"{path.relative_to(ROOT).as_posix()}:{lineno}: {line.strip()}")
report["runner lines naming a Company OS module (CLI contract only)"] = {"ast": [], "text": cli}
summary = {k: {"ast": len(v["ast"]), "text": len(v["text"])} for k, v in report.items()}
print(json.dumps(summary, indent=2))
for k, v in report.items():
    if not k.startswith("CONTROL") and (v["ast"] or v["text"]):
        print("VIOLATION", k, v)
json.dump({"summary": summary, "detail": report}, open(sys.argv[2], "w", encoding="utf-8", newline="\n"), indent=2, sort_keys=True)
