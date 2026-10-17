"""Bounded read-only import/symbol relevance ranking; no repository-wide prompt dump."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import re
import subprocess

from .security import contained_path, redact


def select_context(root: Path, goal: str, budget_tokens: int = 4000) -> dict:
    if not 128 <= budget_tokens <= 16000:
        raise ValueError("Invalid context budget")
    root = root.resolve()
    names = (
        subprocess.run(
            ["git", "ls-files", "-z"], cwd=root, check=True, capture_output=True
        )
        .stdout.decode()
        .split("\0")
    )
    words = set(re.findall(r"[a-z][a-z0-9_]{2,}", goal.casefold()))
    candidates = []
    scanned = 0
    scanned_bytes = 0
    for name in sorted(filter(None, names))[:2000]:
        path = root / name
        if path.is_symlink() or path.suffix not in {
            ".py",
            ".md",
            ".toml",
            ".json",
            ".h",
            ".c",
            ".cpp",
            ".js",
            ".ts",
            ".tsx",
        }:
            continue
        if path.name.lower().startswith((".env", "auth.", "credentials.")) or any(
            p in {".git", "node_modules", "vendor", ".venv"} for p in path.parts
        ):
            continue
        try:
            contained_path(root, name)
            size = path.stat().st_size
            if size > 65536 or scanned_bytes + size > 1024 * 1024:
                continue
            text = path.read_text(encoding="utf-8")
            scanned += 1
            scanned_bytes += size
        except (PermissionError, OSError, UnicodeError):
            continue
        name_words = set(re.findall(r"[a-z][a-z0-9_]{2,}", name.casefold()))
        score = len(words & name_words) * 8
        imports = set()
        symbols = set()
        if path.suffix == ".py":
            try:
                tree = ast.parse(text)
                for node in ast.walk(tree):
                    if isinstance(
                        node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                    ):
                        symbols.add(node.name.casefold())
                    if isinstance(node, ast.ImportFrom) and node.module:
                        imports.add(node.module.split(".")[0])
                    if isinstance(node, ast.Import):
                        imports.update(alias.name.split(".")[0] for alias in node.names)
            except SyntaxError:
                pass
        score += sum(3 for symbol in symbols if any(word in symbol for word in words))
        if path.name == "AGENTS.md":
            score += 100
        if path.name in {"README.md", "pyproject.toml"}:
            score += 2
        if path.name.startswith("test_") and score > 0:
            score += 4
        candidates.append(
            {"path": name, "content": redact(text), "score": score, "imports": imports}
        )
    seeds = {Path(c["path"]).stem for c in candidates if c["score"] >= 8}
    for candidate in candidates:
        candidate["score"] += 4 * len(candidate["imports"] & seeds)
    selected = []
    used = 0
    for candidate in sorted(candidates, key=lambda c: (-c["score"], c["path"])):
        if candidate["score"] <= 0:
            continue
        item = {
            "path": candidate["path"],
            "content": candidate["content"],
            "relevance": candidate["score"],
        }
        cost = len(json.dumps(item, ensure_ascii=True))
        if used + cost > budget_tokens * 4:
            continue
        selected.append(item)
        used += cost
    return {
        "advisory_context": selected,
        "metrics": {
            "files_scanned": scanned,
            "bytes_scanned": scanned_bytes,
            "files_selected": len(selected),
            "estimated_tokens": (used + 3) // 4,
            "selected_paths": [c["path"] for c in selected],
        },
    }


def relevance(metrics: dict, touched: list[str]) -> float:
    selected = set(metrics.get("selected_paths", []))
    return len(selected.intersection(touched)) / len(selected) if selected else 0.0
