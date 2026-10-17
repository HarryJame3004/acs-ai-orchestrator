"""Conservative glob ownership. Coordination is not a filesystem sandbox."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
import re

from .security import contained_path


def scope(value: str) -> str:
    if (
        not value
        or len(value) > 512
        or value != value.strip()
        or "\\" in value
        or "\x00" in value
    ):
        raise ValueError("Invalid ownership scope")
    parts = PurePosixPath(value).parts
    if (
        value.startswith("/")
        or any(p in {".", ".."} for p in value.split("/"))
        or not parts
    ):
        raise ValueError("Ownership must be a normalized repository-relative path")
    if any(c in value for c in "[]{}!") or value in {"*", "**", "**/*"}:
        raise ValueError("Unsupported or unbounded ownership pattern")
    if (
        any(c in parts[0] for c in "*?")
        or parts[0].casefold() == ".git"
        or tuple(p.casefold() for p in parts[:2]) == (".github", "workflows")
    ):
        raise ValueError("Ownership may not include repository controls")
    if "// " in value or "//" in value or value.endswith("/"):
        raise ValueError("Noncanonical ownership scope")
    return value


def matches(pattern: str, name: str) -> bool:
    pattern, name = scope(pattern).casefold(), name.casefold()
    expression = ""
    i = 0
    while i < len(pattern):
        if pattern[i : i + 3] == "**/":
            expression += "(?:.*/)?"
            i += 3
        elif pattern[i : i + 2] == "**":
            expression += ".*"
            i += 2
        elif pattern[i] == "*":
            expression += "[^/]*"
            i += 1
        elif pattern[i] == "?":
            expression += "[^/]"
            i += 1
        else:
            expression += re.escape(pattern[i])
            i += 1
    return re.fullmatch(expression, name) is not None


def overlaps(left: str, right: str) -> bool:
    left, right = scope(left).casefold(), scope(right).casefold()
    if not any(c in left for c in "*?"):
        return matches(right, left)
    if not any(c in right for c in "*?"):
        return matches(left, right)
    # Fixed prefixes that disagree cannot intersect. Otherwise serialize: false
    # positives cost concurrency, false negatives would cost isolation.
    a = re.split("[*?]", left, maxsplit=1)[0]
    b = re.split("[*?]", right, maxsplit=1)[0]
    return a.startswith(b) or b.startswith(a)


def validate_changes(root: Path, names: list[str], owns: list[str]) -> None:
    seen: dict[str, str] = {}
    for name in names:
        contained_path(root, name)
        folded = name.casefold()
        if folded in seen and seen[folded] != name:
            raise PermissionError("Case-insensitive path collision")
        seen[folded] = name
        if not any(matches(pattern, name) for pattern in owns):
            raise PermissionError("Actual diff exceeds task ownership")
