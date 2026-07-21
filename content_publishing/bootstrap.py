"""Create a managed public-tool checkout; personal project data remains outside the installer."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from .common import CommandError, run
from .installers import install_host


DEFAULT_REPOSITORY = "https://github.com/372790111z-wq/content-publishing-sop.git"


def bootstrap(destination: Path, repository: str = DEFAULT_REPOSITORY, host: Optional[str] = None, adapter_destination: Optional[Path] = None) -> Dict[str, Any]:
    destination = destination.expanduser().resolve()
    if destination.exists():
        if all((destination / marker).exists() for marker in ("START-HERE.md", "SOP.md", "VERSION")):
            result: Dict[str, Any] = {"status": "existing", "root": str(destination)}
        else:
            raise CommandError(f"目标已存在且不是 content-publishing-sop：{destination}")
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        cloned = run(["git", "clone", "--depth", "1", repository, str(destination)], timeout=300)
        if not cloned["ok"]:
            raise CommandError(f"克隆失败：{cloned['stderr'] or cloned['stdout']}")
        if not all((destination / marker).exists() for marker in ("START-HERE.md", "SOP.md", "VERSION")):
            raise CommandError("下载内容缺少工作台标记，拒绝继续安装。")
        result = {"status": "installed", "root": str(destination), "repository": repository}
    if host:
        result["adapter"] = install_host(destination, host, adapter_destination)
    result["next"] = f"content-publishing --root {destination} doctor --deep"
    return result
