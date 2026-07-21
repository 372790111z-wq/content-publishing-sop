"""Project scaffolding with registry updates and no invented acceptance facts."""

from __future__ import annotations

import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .common import CommandError, atomic_write_json, read_json, utc_now


PROJECT_ID = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")


def _replace_project_id(value: Any, project_id: str) -> Any:
    if isinstance(value, dict):
        return {key: _replace_project_id(item, project_id) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_project_id(item, project_id) for item in value]
    if value == "replace-with-project-id":
        return project_id
    return value


def new_project(
    root: Path,
    project_id: str,
    title: str,
    source_title: str,
    accepted_at: str,
    requested_at: str,
    reuse_reason: str,
    acceptance_evidence: List[str],
    request_evidence: List[str],
    platforms: Optional[List[str]] = None,
    owner: str = "",
) -> Dict[str, Any]:
    if not PROJECT_ID.fullmatch(project_id):
        raise CommandError("project-id 必须是 3-64 位小写英文、数字或短横线。")
    if not title.strip() or not source_title.strip() or not reuse_reason.strip():
        raise CommandError("title、source-title 和 reuse-reason 不能为空。")
    if not acceptance_evidence or not request_evidence:
        raise CommandError("必须提供验收证据和内容发起证据；CLI 不会替你编造证据。")
    try:
        accepted = datetime.fromisoformat(accepted_at.replace("Z", "+00:00"))
        requested = datetime.fromisoformat(requested_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CommandError("accepted-at 和 requested-at 必须是 ISO 8601 时间。") from exc
    if accepted.tzinfo is None:
        accepted = accepted.replace(tzinfo=timezone.utc)
    if requested.tzinfo is None:
        requested = requested.replace(tzinfo=timezone.utc)
    if requested.astimezone(timezone.utc) < accepted.astimezone(timezone.utc):
        raise CommandError("内容发起时间不能早于需求验收时间。")

    template = root / "templates" / "project"
    destination = root / "projects" / project_id
    registry_path = root / "projects" / "registry.json"
    if destination.exists():
        raise CommandError(f"项目已存在：{destination}")
    if not template.is_dir():
        raise CommandError(f"项目模板不存在：{template}")

    registry = read_json(registry_path)
    entries = registry.get("projects", [])
    if any(isinstance(item, dict) and item.get("path") == f"./{project_id}" for item in entries):
        raise CommandError(f"注册表已经包含项目：{project_id}")

    staging_parent = destination.parent
    staging_parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{project_id}.", dir=str(staging_parent)))
    try:
        shutil.rmtree(staging)
        shutil.copytree(template, staging)
        for path in sorted(staging.glob("*.json")):
            data = _replace_project_id(read_json(path), project_id)
            atomic_write_json(path, data)

        now = utc_now()
        manifest_path = staging / "project-manifest.json"
        manifest = read_json(manifest_path)
        manifest.update(title=title, summary=f"由已验收需求“{source_title}”沉淀的可复用内容。", created_at=now, updated_at=now, owner=owner)
        manifest["source_work"].update(
            title=source_title,
            accepted_at=accepted_at,
            acceptance_evidence=acceptance_evidence,
            reuse_reason=reuse_reason,
            content_requested_at=requested_at,
            request_evidence=request_evidence,
        )
        atomic_write_json(manifest_path, manifest)

        handoff = read_json(staging / "handoff-state.json")
        handoff["updated_at"] = now
        atomic_write_json(staging / "handoff-state.json", handoff)

        platform_data = read_json(staging / "platform-status.json")
        requested_platforms = list(dict.fromkeys(platforms or []))
        platform_data["platforms"] = [
            {
                "platform": name,
                "status": "not_started",
                "content_path": None,
                "public_url": None,
                "published_at": None,
                "release_digest": None,
                "reader_validation": "unknown",
                "prompt_delivery": "unknown",
                "evidence": [],
                "blocker": None,
            }
            for name in requested_platforms
        ]
        atomic_write_json(staging / "platform-status.json", platform_data)

        staging.rename(destination)
        new_registry = dict(registry)
        new_registry["projects"] = list(entries) + [
            {"path": f"./{project_id}", "enabled": True, "kind": "project"}
        ]
        try:
            atomic_write_json(registry_path, new_registry)
        except Exception:
            shutil.rmtree(destination)
            raise
    finally:
        if staging.exists():
            shutil.rmtree(staging)

    return {
        "status": "created",
        "project_id": project_id,
        "path": str(destination),
        "registry": str(registry_path),
        "next": "补全真实 decision-log、母稿和 canonical prompt，然后运行 validate。",
    }
