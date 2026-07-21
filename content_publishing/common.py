"""Shared path, process and atomic-file helpers."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


REPO_MARKERS = ("START-HERE.md", "SOP.md", "templates/project", "validator/validate.py")


class CommandError(RuntimeError):
    """A user-facing command failure with no hidden side effects."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def find_workbench(start: Optional[Path] = None) -> Path:
    override = os.environ.get("CONTENT_PUBLISHING_HOME")
    candidates: List[Path] = []
    if override:
        candidates.append(Path(override).expanduser())
    if start:
        candidates.append(start)
    candidates.extend([Path.cwd(), Path(__file__).resolve().parent.parent])
    seen = set()
    for candidate in candidates:
        candidate = candidate.resolve()
        for root in (candidate, *candidate.parents):
            if root in seen:
                continue
            seen.add(root)
            if all((root / marker).exists() for marker in REPO_MARKERS):
                return root
    raise CommandError(
        "找不到 content-publishing-sop 工作台；请在仓库内运行，或设置 CONTENT_PUBLISHING_HOME。"
    )


def read_json(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CommandError(f"文件不存在：{path}") from exc
    except json.JSONDecodeError as exc:
        raise CommandError(f"JSON 无效：{path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CommandError(f"JSON 顶层必须是对象：{path}")
    return value


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    temp_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(str(temp_path), str(path))
    finally:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass


def atomic_write_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    temp_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(str(temp_path), str(path))
    finally:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass


def atomic_write_json(path: Path, value: Dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def run(command: Iterable[str], cwd: Optional[Path] = None, timeout: int = 60) -> Dict[str, Any]:
    argv = [str(item) for item in command]
    try:
        completed = subprocess.run(
            argv,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "exit_code": None, "stdout": "", "stderr": str(exc), "command": argv}
    return {
        "ok": completed.returncode == 0,
        "exit_code": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "command": argv,
    }


def json_print(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))
