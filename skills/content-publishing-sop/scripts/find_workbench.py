#!/usr/bin/env python3
"""Locate the content publishing workbench without hard-coded paths."""

import argparse
import json
import os
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


WORKBENCH_NAMES = {"content-publishing-sop", "content-production-publishing-sop"}
REQUIRED_FILES = ("START-HERE.md", "AGENT-PROTOCOL.md", "SOURCE_OF_TRUTH.md", "SOP.md")
SKIP_DIRS = {".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv"}


def is_workbench(path: Path) -> bool:
    return path.is_dir() and all((path / name).is_file() for name in REQUIRED_FILES)


def add_candidate(rows: List[Tuple[int, Path, str]], priority: int, path: Path, reason: str) -> None:
    try:
        resolved = path.expanduser().resolve()
    except OSError:
        return
    if is_workbench(resolved) and all(existing[1] != resolved for existing in rows):
        rows.append((priority, resolved, reason))


def ancestors(start: Path) -> Iterable[Path]:
    current = start
    while True:
        yield current
        if current.parent == current:
            return
        current = current.parent


def descendants(start: Path, max_depth: int) -> Iterable[Path]:
    base_depth = len(start.parts)
    for root, dirs, files in os.walk(str(start)):
        root_path = Path(root)
        depth = len(root_path.parts) - base_depth
        dirs[:] = sorted(
            name for name in dirs
            if name not in SKIP_DIRS and not name.startswith(".") and depth < max_depth
        )
        if root_path.name in WORKBENCH_NAMES or all(name in files for name in REQUIRED_FILES):
            yield root_path
            dirs[:] = []


def locate(start: Path, max_depth: int) -> Dict[str, object]:
    rows: List[Tuple[int, Path, str]] = []
    configured = os.environ.get("CONTENT_PUBLISHING_SOP_HOME")
    if configured:
        add_candidate(rows, 0, Path(configured), "CONTENT_PUBLISHING_SOP_HOME")

    for directory in ancestors(start):
        add_candidate(rows, 1, directory, "current-or-ancestor")
        for name in WORKBENCH_NAMES:
            add_candidate(rows, 2, directory / name, "sibling-from-ancestor")

    if start.is_dir():
        for path in descendants(start, max_depth):
            add_candidate(rows, 3, path, "workspace-search")

    rows.sort(key=lambda item: (item[0], len(item[1].parts), str(item[1])))
    candidates = [
        {"path": str(path), "reason": reason, "priority": priority}
        for priority, path, reason in rows
    ]
    if not rows:
        return {"status": "not_found", "selected": None, "candidates": []}
    best_priority = rows[0][0]
    best = [item for item in rows if item[0] == best_priority]
    if len(best) > 1:
        return {"status": "ambiguous", "selected": None, "candidates": candidates}
    return {"status": "found", "selected": str(best[0][1]), "candidates": candidates}


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Locate the content publishing SOP workbench")
    parser.add_argument("--start", default=".", help="Workspace or directory to search from")
    parser.add_argument("--max-depth", type=int, default=6, help="Maximum descendant search depth")
    args = parser.parse_args(argv)
    start = Path(args.start).expanduser().resolve()
    result = locate(start, max(0, args.max_depth))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "found" else 2


if __name__ == "__main__":
    raise SystemExit(main())
