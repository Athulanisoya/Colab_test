"""Verify the documented source layout, ignoring only known runtime artifacts."""

from __future__ import annotations

import os
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DISCUSSION = PROJECT_ROOT / "ResQ_Kerala_Complete_Project_Discussion.md"
LEGACY_PATHS = (
    "tests", "backend/schemas.py", "backend/services.py", "backend/security.py",
    "backend/routers/operations.py", "backend/routers/content.py", "backend/routers/ai.py",
    "backend/ai/service.py", "backend/ai/tools.py", "backend/ai/knowledge.json",
    "backend/ai/smoke.py", "backend/ai/tool_smoke.py",
    "frontend/src/pages/Admin.jsx", "frontend/src/pages/Dashboard.jsx",
    "frontend/src/pages/Incidents.jsx", "frontend/src/pages/Login.jsx", "frontend/src/pages/Services.jsx",
    "docs/implementation.md", "docs/api.md", "docs/database.md",
)


def documented_paths() -> dict[str, bool]:
    source = DISCUSSION.read_text(encoding="utf-8")
    section = source.split("# 11. Recommended FastAPI Project Folder Structure", 1)[1].split("# 12. API Structure", 1)[0]
    tree = section.split("```text", 1)[1].split("```", 1)[0]
    parents: list[str] = []
    result = {}
    for line in tree.splitlines():
        match = re.match(r"^([│ ]*)(?:├──|└──)\s+([^#]+)", line)
        if not match:
            continue
        prefix, entry = match.groups()
        depth = len(prefix) // 4
        entry = entry.strip()
        directory = entry.endswith("/")
        name = entry.rstrip("/")
        parents = parents[:depth]
        relative = "/".join([*parents, name])
        result[relative] = directory
        if directory:
            parents.append(name)
    return result


def runtime_artifact(relative: str) -> bool:
    parts = Path(relative).parts
    if any(part in {".venv", ".git", ".codex", ".agents", ".aws", ".pytest_cache", "__pycache__", "node_modules", ".ipynb_checkpoints"} for part in parts):
        return True
    if any(relative == directory or relative.startswith(directory + "/")
           for directory in ("output", "frontend/dist", "data/uploads")):
        return True
    return relative.startswith("data/") and bool(re.search(r"\.db(?:-|$)", relative))


def verify_structure(root: Path = PROJECT_ROOT) -> list[str]:
    expected = documented_paths()
    open_directories = {path for path, directory in expected.items()
                        if directory and not any(other.startswith(path + "/") for other in expected)}
    errors = []
    for relative, directory in expected.items():
        path = root / relative
        if not (path.is_dir() if directory else path.is_file()):
            errors.append(f"Missing documented {'directory' if directory else 'file'}: {relative}")
    for relative in LEGACY_PATHS:
        if (root / relative).exists():
            errors.append(f"Obsolete path remains: {relative}")
    for parent, directories, files in os.walk(root):
        relative_parent = Path(parent).relative_to(root).as_posix()
        for name in [*directories, *files]:
            relative = name if relative_parent == "." else f"{relative_parent}/{name}"
            if runtime_artifact(relative):
                continue
            if relative in expected or any(relative.startswith(path + "/") for path in open_directories):
                continue
            if name == "__init__.py" and relative_parent in expected:
                continue
            errors.append(f"Unexpected source path: {relative}")
        directories[:] = [name for name in directories
                          if not runtime_artifact(name if relative_parent == "." else f"{relative_parent}/{name}")]
    return errors


if __name__ == "__main__":
    failures = verify_structure()
    if failures:
        print("\n".join(failures))
        raise SystemExit(1)
    paths = documented_paths()
    print(f"PASS: {len(paths)} documented paths exist; obsolete source paths are absent; no unexpected source paths.")
