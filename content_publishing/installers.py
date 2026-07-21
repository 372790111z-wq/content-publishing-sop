"""Safe host-adapter installation that never overwrites unknown user files."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from .common import CommandError, atomic_write_json, atomic_write_text, read_json, utc_now


SKILL_NAME = "content-publishing-sop"
MARKER = ".content-publishing-managed.json"


def _installations_path(root: Path) -> Path:
    git_dir = root / ".git"
    return (git_dir if git_dir.is_dir() else root / ".content-publishing") / "managed-installations.json"


def _record_installation(root: Path, host: str, destination: Optional[Path]) -> None:
    path = _installations_path(root)
    data = read_json(path) if path.is_file() else {"schema_version": "1.0", "installations": []}
    destination_value = str(destination.expanduser().resolve()) if destination else None
    rows = [
        item for item in data.get("installations", [])
        if not (isinstance(item, dict) and item.get("host") == host and item.get("destination") == destination_value)
    ]
    rows.append({"host": host, "destination": destination_value, "updated_at": utc_now()})
    data["installations"] = rows
    atomic_write_json(path, data)


def _forget_installation(root: Path, host: str, destination: Optional[Path]) -> None:
    path = _installations_path(root)
    if not path.is_file():
        return
    data = read_json(path)
    destination_value = str(destination.expanduser().resolve()) if destination else None
    data["installations"] = [
        item for item in data.get("installations", [])
        if not (isinstance(item, dict) and item.get("host") == host and item.get("destination") == destination_value)
    ]
    atomic_write_json(path, data)


def _file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _render_adapter(source: Path, root: Path) -> str:
    header = (
        "<!-- Managed by content-publishing-sop. Machine-local path; do not copy this installed file across machines. -->\n"
        f"本机内容发布工作台：`{root.resolve()}`。处理相关任务时先读取该目录下的 `START-HERE.md`。\n\n"
    )
    return header + source.read_text(encoding="utf-8")


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file() and item.name != MARKER and "__pycache__" not in item.parts):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _host_target(host: str, destination: Optional[Path]) -> tuple:
    if host == "codex":
        base = destination or Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "skills"
        return "directory", base.expanduser().resolve() / SKILL_NAME
    if destination is None:
        raise CommandError(f"{host} 安装必须用 --dest 指定 IDE 项目根目录，避免覆盖错误项目。")
    base = destination.expanduser().resolve()
    mapping = {
        "claude-code": ("file", base / "CLAUDE.md"),
        "cursor": ("file", base / ".cursor" / "rules" / "content-publishing-sop.mdc"),
        "windsurf": ("file", base / ".windsurf" / "rules" / "content-publishing-sop.md"),
        "vscode-agent": ("file", base / ".github" / "copilot-instructions.md"),
        "generic-agent": ("file", base / ".content-publishing" / "PROMPT.md"),
    }
    if host not in mapping:
        raise CommandError(f"不支持的宿主：{host}")
    return mapping[host]


def _source(root: Path, host: str) -> Path:
    mapping = {
        "codex": root / "skills" / SKILL_NAME,
        "claude-code": root / "adapters" / "claude-code" / "CLAUDE.md",
        "cursor": root / "adapters" / "cursor" / "content-publishing-sop.mdc",
        "windsurf": root / "adapters" / "windsurf" / "AGENTS.md",
        "vscode-agent": root / "adapters" / "vscode-agent" / "copilot-instructions.md",
        "generic-agent": root / "adapters" / "generic-agent" / "PROMPT.md",
    }
    source = mapping.get(host)
    if source is None or not source.exists():
        raise CommandError(f"缺少 {host} 适配源。")
    return source


def install_host(root: Path, host: str, destination: Optional[Path], check: bool = False, upgrade: bool = False) -> Dict[str, Any]:
    source = _source(root, host)
    kind, target = _host_target(host, destination)
    rendered = None if kind == "directory" else _render_adapter(source, root)
    source_digest = _tree_digest(source) if kind == "directory" else hashlib.sha256(rendered.encode("utf-8")).hexdigest()
    marker_path = target / MARKER if kind == "directory" else target.with_name(target.name + ".managed.json")
    installed_digest = None
    if target.exists():
        if kind == "directory" and not target.is_dir():
            raise CommandError(f"安装目标不是目录：{target}")
        if kind == "file" and not target.is_file():
            raise CommandError(f"安装目标不是文件：{target}")
        installed_digest = _tree_digest(target) if kind == "directory" else _file_digest(target)
        if installed_digest == source_digest:
            if not check:
                marker = {"schema_version": "1.0", "host": host, "source": str(source), "workbench_root": str(root.resolve()), "installed_digest": source_digest}
                atomic_write_json(marker_path, marker)
                _record_installation(root, host, destination)
            return {"status": "installed", "host": host, "target": str(target), "digest": source_digest}
        marker = {}
        if marker_path.is_file():
            try:
                marker = json.loads(marker_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                marker = {}
        managed_unmodified = marker.get("installed_digest") == installed_digest and marker.get("host") == host
        if not upgrade or not managed_unmodified:
            return {
                "status": "conflict",
                "host": host,
                "target": str(target),
                "message": "目标包含不同内容；只有由本工具安装且未被用户修改的适配器才能 --upgrade。",
            }
    if check:
        return {"status": "update_available" if target.exists() else "not_installed", "host": host, "target": str(target)}

    marker = {"schema_version": "1.0", "host": host, "source": str(source), "workbench_root": str(root.resolve()), "installed_digest": source_digest}
    target.parent.mkdir(parents=True, exist_ok=True)
    if kind == "directory":
        staging = Path(tempfile.mkdtemp(prefix=f".{SKILL_NAME}.", dir=str(target.parent)))
        try:
            shutil.rmtree(staging)
            shutil.copytree(source, staging)
            atomic_write_json(staging / MARKER, marker)
            if target.exists():
                backup = target.with_name(target.name + ".replace")
                if backup.exists():
                    shutil.rmtree(backup)
                target.rename(backup)
                try:
                    staging.rename(target)
                except Exception:
                    backup.rename(target)
                    raise
                else:
                    shutil.rmtree(backup)
            else:
                staging.rename(target)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
    else:
        atomic_write_text(target, rendered or source.read_text(encoding="utf-8"))
        atomic_write_json(marker_path, marker)
    _record_installation(root, host, destination)
    return {"status": "installed", "host": host, "target": str(target), "digest": source_digest}


def uninstall_host(root: Path, host: str, destination: Optional[Path]) -> Dict[str, Any]:
    kind, target = _host_target(host, destination)
    marker_path = target / MARKER if kind == "directory" else target.with_name(target.name + ".managed.json")
    if not target.exists():
        _forget_installation(root, host, destination)
        return {"status": "not_installed", "host": host, "target": str(target)}
    if not marker_path.is_file():
        raise CommandError("目标不是由本工具管理，拒绝删除。")
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    actual = _tree_digest(target) if kind == "directory" else _file_digest(target)
    if actual != marker.get("installed_digest"):
        raise CommandError("已安装文件被用户修改，拒绝删除；请人工合并或移除。")
    if kind == "directory":
        shutil.rmtree(target)
    else:
        target.unlink()
        marker_path.unlink(missing_ok=True)
    _forget_installation(root, host, destination)
    return {"status": "uninstalled", "host": host, "target": str(target)}


def sync_managed_installations(root: Path) -> Dict[str, Any]:
    path = _installations_path(root)
    if not path.is_file():
        return {"status": "none", "installations": []}
    data = read_json(path)
    results = []
    for item in data.get("installations", []):
        if not isinstance(item, dict) or not item.get("host"):
            continue
        destination = Path(item["destination"]) if item.get("destination") else None
        try:
            results.append(install_host(root, item["host"], destination, upgrade=True))
        except CommandError as exc:
            results.append({"status": "conflict", "host": item["host"], "destination": item.get("destination"), "message": str(exc)})
    return {
        "status": "passed" if all(item.get("status") == "installed" for item in results) else "conflict",
        "installations": results,
    }
