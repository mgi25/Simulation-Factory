"""A strict loader for the small YAML subset used by bootstrap contracts.

The supported subset is deliberately narrow: indented mappings, scalar block
lists, inline scalar lists, strings, integers, floats, booleans, and null.
Unsupported YAML is rejected instead of being interpreted approximately.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

from .errors import YamlSubsetError


_INTEGER = re.compile(r"[-+]?\d+")
_FLOAT = re.compile(r"[-+]?(?:\d+\.\d*|\d*\.\d+)(?:[eE][-+]?\d+)?")


@dataclass(frozen=True)
class _Line:
    indent: int
    text: str
    number: int


def load_yaml_subset(path: str | Path) -> dict[str, Any]:
    """Load one bootstrap YAML file as a mapping."""

    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise YamlSubsetError(f"cannot read {source}: {exc}") from exc
    value = parse_yaml_subset(text, source=str(source))
    if not isinstance(value, dict):
        raise YamlSubsetError(f"{source}: top-level value must be a mapping")
    return value


def parse_yaml_subset(text: str, *, source: str = "<string>") -> Any:
    """Parse supported bootstrap YAML and return standard Python values."""

    lines = _tokenize(text, source)
    if not lines:
        return {}
    if lines[0].indent != 0:
        _fail(source, lines[0], "top-level content must not be indented")
    value, next_index = _parse_block(lines, 0, 0, source)
    if next_index != len(lines):
        _fail(source, lines[next_index], "unexpected content")
    return value


def _tokenize(text: str, source: str) -> list[_Line]:
    result: list[_Line] = []
    for number, raw_line in enumerate(text.splitlines(), start=1):
        if "\t" in raw_line[: len(raw_line) - len(raw_line.lstrip())]:
            raise YamlSubsetError(f"{source}:{number}: tabs are not valid indentation")
        uncommented = _strip_comment(raw_line).rstrip()
        if not uncommented.strip():
            continue
        indent = len(uncommented) - len(uncommented.lstrip(" "))
        if indent % 2:
            raise YamlSubsetError(
                f"{source}:{number}: indentation must use multiples of two spaces"
            )
        result.append(_Line(indent, uncommented[indent:], number))
    return result


def _strip_comment(line: str) -> str:
    quote: str | None = None
    escaped = False
    for index, character in enumerate(line):
        if escaped:
            escaped = False
            continue
        if character == "\\" and quote == '"':
            escaped = True
            continue
        if quote:
            if character == quote:
                quote = None
            continue
        if character in {"'", '"'}:
            quote = character
        elif character == "#" and (index == 0 or line[index - 1].isspace()):
            return line[:index]
    return line


def _parse_block(
    lines: list[_Line], index: int, indent: int, source: str
) -> tuple[Any, int]:
    if lines[index].indent != indent:
        _fail(source, lines[index], f"expected indentation level {indent}")
    if lines[index].text == "-" or lines[index].text.startswith("- "):
        return _parse_list(lines, index, indent, source)
    return _parse_mapping(lines, index, indent, source)


def _parse_mapping(
    lines: list[_Line], index: int, indent: int, source: str
) -> tuple[dict[str, Any], int]:
    result: dict[str, Any] = {}
    while index < len(lines) and lines[index].indent == indent:
        line = lines[index]
        if line.text == "-" or line.text.startswith("- "):
            _fail(source, line, "cannot mix mapping and list entries at one level")
        key, raw_value = _split_mapping_entry(line.text, source, line)
        if key in result:
            _fail(source, line, f"duplicate key {key!r}")
        index += 1
        if raw_value:
            result[key] = _parse_scalar(raw_value, source, line)
            if index < len(lines) and lines[index].indent > indent:
                _fail(source, lines[index], f"scalar key {key!r} cannot have children")
            continue
        if index >= len(lines) or lines[index].indent <= indent:
            _fail(source, line, f"key {key!r} requires an indented value")
        if lines[index].indent != indent + 2:
            _fail(source, lines[index], "nested content must be indented by two spaces")
        result[key], index = _parse_block(lines, index, indent + 2, source)
    if index < len(lines) and lines[index].indent > indent:
        _fail(source, lines[index], "unexpected indentation")
    return result, index


def _parse_list(
    lines: list[_Line], index: int, indent: int, source: str
) -> tuple[list[Any], int]:
    result: list[Any] = []
    while index < len(lines) and lines[index].indent == indent:
        line = lines[index]
        if not (line.text == "-" or line.text.startswith("- ")):
            _fail(source, line, "cannot mix list and mapping entries at one level")
        raw_value = line.text[1:].strip()
        index += 1
        if raw_value:
            if _find_unquoted_colon(raw_value) is not None:
                _fail(source, line, "mapping entries inside block lists are unsupported")
            result.append(_parse_scalar(raw_value, source, line))
            if index < len(lines) and lines[index].indent > indent:
                _fail(source, lines[index], "scalar list entry cannot have children")
            continue
        if index >= len(lines) or lines[index].indent != indent + 2:
            _fail(source, line, "empty list entry requires a value indented by two spaces")
        value, index = _parse_block(lines, index, indent + 2, source)
        result.append(value)
    if index < len(lines) and lines[index].indent > indent:
        _fail(source, lines[index], "unexpected indentation")
    return result, index


def _split_mapping_entry(text: str, source: str, line: _Line) -> tuple[str, str]:
    separator = _find_unquoted_colon(text)
    if separator is None:
        _fail(source, line, "mapping entry must contain ':'")
    key = text[:separator].strip()
    if not key or key[0] in {"'", '"'}:
        _fail(source, line, "mapping keys must be non-empty unquoted strings")
    return key, text[separator + 1 :].strip()


def _find_unquoted_colon(text: str) -> int | None:
    quote: str | None = None
    escaped = False
    bracket_depth = 0
    for index, character in enumerate(text):
        if escaped:
            escaped = False
            continue
        if character == "\\" and quote == '"':
            escaped = True
            continue
        if quote:
            if character == quote:
                quote = None
            continue
        if character in {"'", '"'}:
            quote = character
        elif character == "[":
            bracket_depth += 1
        elif character == "]":
            bracket_depth -= 1
        elif character == ":" and bracket_depth == 0:
            return index
    return None


def _parse_scalar(raw: str, source: str, line: _Line) -> Any:
    if raw.startswith("["):
        if not raw.endswith("]"):
            _fail(source, line, "inline list is missing closing ']'")
        inner = raw[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(part, source, line) for part in _split_inline_list(inner, source, line)]
    if raw.startswith(("'", '"')):
        try:
            value = ast.literal_eval(raw)
        except (SyntaxError, ValueError) as exc:
            raise YamlSubsetError(f"{source}:{line.number}: invalid quoted string") from exc
        if not isinstance(value, str):
            _fail(source, line, "quoted scalar must be a string")
        return value
    lowered = raw.casefold()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in {"null", "~"}:
        return None
    if _INTEGER.fullmatch(raw):
        return int(raw)
    if _FLOAT.fullmatch(raw):
        return float(raw)
    if raw.startswith(("{", "&", "*", "!", "|", ">")):
        _fail(source, line, "unsupported YAML construct")
    return raw


def _split_inline_list(inner: str, source: str, line: _Line) -> list[str]:
    parts: list[str] = []
    start = 0
    quote: str | None = None
    escaped = False
    for index, character in enumerate(inner):
        if escaped:
            escaped = False
            continue
        if character == "\\" and quote == '"':
            escaped = True
            continue
        if quote:
            if character == quote:
                quote = None
            continue
        if character in {"'", '"'}:
            quote = character
        elif character == ",":
            part = inner[start:index].strip()
            if not part:
                _fail(source, line, "inline list contains an empty item")
            parts.append(part)
            start = index + 1
        elif character in "[]{}":
            _fail(source, line, "nested inline collections are unsupported")
    if quote:
        _fail(source, line, "unterminated quote in inline list")
    final = inner[start:].strip()
    if not final:
        _fail(source, line, "inline list contains an empty item")
    parts.append(final)
    return parts


def _fail(source: str, line: _Line, message: str) -> None:
    raise YamlSubsetError(f"{source}:{line.number}: {message}")
