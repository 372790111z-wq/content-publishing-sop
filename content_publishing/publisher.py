"""Publisher-core planning surface and connector capability registry."""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any, Dict, List

from .common import CommandError, read_json


def registry() -> Dict[str, Any]:
    text = resources.files("content_publishing").joinpath("platforms.json").read_text(encoding="utf-8")
    return json.loads(text)


def publication_plan(project: Path, action: str, requested: List[str]) -> Dict[str, Any]:
    if action not in {"public_publish", "update_publication"}:
        raise CommandError("publisher plan 当前只接受 public_publish 或 update_publication。")
    platform_state = read_json(project / "platform-status.json")
    known_state = {item.get("platform"): item for item in platform_state.get("platforms", []) if isinstance(item, dict)}
    capabilities = registry()
    by_name = {item["name"]: item for item in capabilities["platforms"]}
    rows = []
    for name in requested:
        if name not in known_state:
            raise CommandError(f"项目没有登记平台：{name}")
        capability = by_name.get(name, {"name": name, "official_api": "unknown", "browser": "unknown", "manual": "supported"})
        selected = next(
            (
                channel
                for channel in capabilities["execution_order"]
                if capability.get(channel) == "tested" or (channel == "manual" and capability.get(channel) == "supported")
            ),
            "manual",
        )
        rows.append(
            {
                "platform": name,
                "current_status": known_state[name].get("status"),
                "selected_channel": selected,
                "capabilities": {key: capability.get(key, "unknown") for key in ("official_api", "browser", "manual")},
                "requires_human": ["login", "CAPTCHA", "MFA", "new platform agreement"],
            }
        )
    return {
        "schema_version": "1.0",
        "action": action,
        "project": str(project),
        "platforms": rows,
        "next": "创建范围化 grant，通过整批门禁后 prepare pending intents；连接器成功后再 settle 回执。",
    }
