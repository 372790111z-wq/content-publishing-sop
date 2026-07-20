#!/usr/bin/env python3
"""Install the bundled Codex skill without overwriting an existing different skill."""

import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Dict, Iterable, Optional, Sequence, Tuple


SKILL_NAME = "content-publishing-sop"


def files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
            yield path


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in files(root):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def install(source: Path, destination_root: Path, check_only: bool) -> Tuple[int, Dict[str, object]]:
    destination = destination_root / SKILL_NAME
    source_digest = tree_digest(source)
    result: Dict[str, object] = {
        "skill": SKILL_NAME,
        "source": str(source),
        "destination": str(destination),
        "source_digest": source_digest,
    }
    if destination.exists():
        if not destination.is_dir():
            result.update(status="conflict", message="Destination exists and is not a directory")
            return 2, result
        installed_digest = tree_digest(destination)
        result["installed_digest"] = installed_digest
        if installed_digest == source_digest:
            result.update(status="installed", message="The installed skill already matches the bundle")
            return 0, result
        result.update(status="conflict", message="A different installed skill exists; compare it before replacing")
        return 2, result
    if check_only:
        result.update(status="not_installed", message="No installed skill was found")
        return 1, result
    destination_root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination)
    result.update(status="installed", installed_digest=tree_digest(destination), message="Installed successfully")
    return 0, result


def main(argv: Optional[Sequence[str]] = None) -> int:
    workbench = Path(__file__).resolve().parent.parent
    source = workbench / "skills" / SKILL_NAME
    default_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    parser = argparse.ArgumentParser(description="Install the bundled content publishing Codex skill")
    parser.add_argument("--dest", default=str(default_home / "skills"), help="Codex skills directory")
    parser.add_argument("--check", action="store_true", help="Check installation without writing")
    args = parser.parse_args(argv)
    if not (source / "SKILL.md").is_file():
        print(json.dumps({"status": "error", "message": "Bundled skill is missing", "source": str(source)}, ensure_ascii=False, indent=2))
        return 2
    code, result = install(source.resolve(), Path(args.dest).expanduser().resolve(), args.check)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
