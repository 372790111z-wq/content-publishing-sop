"""Safe, repository-scoped self update with a clean-tree precondition and rollback state."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from .common import CommandError, atomic_write_json, run, utc_now
from .installers import sync_managed_installations


STATE_FILE = "content-publishing-update-state.json"


def _git(root: Path, *args: str, timeout: int = 60) -> Dict[str, Any]:
    result = run(["git", *args], cwd=root, timeout=timeout)
    if not result["ok"]:
        raise CommandError(result["stderr"] or result["stdout"] or f"git {' '.join(args)} 失败")
    return result


def _state_path(root: Path) -> Path:
    git_dir = _git(root, "rev-parse", "--git-dir")["stdout"]
    candidate = Path(git_dir)
    if not candidate.is_absolute():
        candidate = root / candidate
    return candidate.resolve() / STATE_FILE


def status(root: Path, fetch: bool = False, target: Optional[str] = None) -> Dict[str, Any]:
    if not (root / ".git").exists():
        raise CommandError("当前工作台不是 Git checkout；请通过 GitHub Release 或 pip 安装的新版本覆盖工具包。")
    current = _git(root, "rev-parse", "HEAD")["stdout"]
    branch_result = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=root)
    branch = branch_result["stdout"] if branch_result["ok"] else None
    upstream_result = run(["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], cwd=root)
    upstream = upstream_result["stdout"] if upstream_result["ok"] else None
    dirty = bool(_git(root, "status", "--porcelain")["stdout"])
    if fetch:
        _git(root, "fetch", "--tags", "--prune", timeout=180)
    resolved_target = target or upstream
    target_commit = None
    if resolved_target:
        resolved = run(["git", "rev-parse", resolved_target], cwd=root)
        if resolved["ok"]:
            target_commit = resolved["stdout"]
    remote_status = "update_available" if target_commit and target_commit != current else "current"
    return {
        "status": "dirty" if dirty else remote_status,
        "remote_status": remote_status,
        "root": str(root),
        "branch": branch,
        "upstream": upstream,
        "current_commit": current,
        "target": resolved_target,
        "target_commit": target_commit,
        "dirty": dirty,
    }


def _postflight(root: Path) -> Dict[str, Any]:
    commands = [
        [sys.executable, "-m", "unittest", "discover", "-s", "validator", "-p", "test*.py"],
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test*.py"],
        [sys.executable, "tools/portability_check.py"],
        [sys.executable, "tools/build_dashboard.py", "--check"],
    ]
    results = [run(command, cwd=root, timeout=180) for command in commands]
    return {"ok": all(item["ok"] for item in results), "results": results}


def update(root: Path, target: Optional[str] = None, dry_run: bool = False) -> Dict[str, Any]:
    before = status(root, fetch=False, target=target)
    if dry_run:
        return {
            "status": "planned",
            "before": before,
            "can_apply": not before["dirty"],
            "blocker": "工作台存在未提交修改" if before["dirty"] else None,
            "steps": ["git fetch --tags --prune", "git merge --ff-only <target>", "tests + portability + dashboard check"],
        }
    if before["dirty"]:
        raise CommandError("工作台存在未提交修改；升级器拒绝覆盖，请先提交、暂存或移走改动。")
    fetched = status(root, fetch=True, target=target)
    if not fetched["target_commit"]:
        raise CommandError("找不到上游或指定版本。")
    if fetched["target_commit"] == fetched["current_commit"]:
        return {"status": "current", "before": fetched}
    ancestor = run(["git", "merge-base", "--is-ancestor", fetched["current_commit"], fetched["target_commit"]], cwd=root)
    if not ancestor["ok"]:
        raise CommandError("目标不是当前版本的快进升级；请使用 rollback 或人工处理分叉。")
    state_path = _state_path(root)
    state = {"schema_version": "1.0", "updated_at": utc_now(), "previous_commit": fetched["current_commit"], "target_commit": fetched["target_commit"]}
    atomic_write_json(state_path, state)
    merge = run(["git", "merge", "--ff-only", fetched["target_commit"]], cwd=root, timeout=180)
    if not merge["ok"]:
        raise CommandError(f"快进升级失败：{merge['stderr'] or merge['stdout']}")
    checks = _postflight(root)
    if not checks["ok"]:
        rollback_result = run(["git", "reset", "--hard", fetched["current_commit"]], cwd=root, timeout=120)
        raise CommandError(
            "升级后验收失败，已自动恢复旧提交。" if rollback_result["ok"] else "升级后验收失败，自动恢复也失败；请停止使用并人工检查。"
        )
    adapter_sync = sync_managed_installations(root)
    return {
        "status": "updated" if adapter_sync["status"] in {"passed", "none"} else "updated_with_conflicts",
        "previous_commit": fetched["current_commit"],
        "current_commit": fetched["target_commit"],
        "postflight": checks,
        "adapter_sync": adapter_sync,
    }


def rollback(root: Path) -> Dict[str, Any]:
    current = status(root, fetch=False)
    if current["dirty"]:
        raise CommandError("工作台存在未提交修改，拒绝回滚。")
    path = _state_path(root)
    if not path.is_file():
        raise CommandError("没有可用的升级回滚记录。")
    state = json.loads(path.read_text(encoding="utf-8"))
    previous = state.get("previous_commit")
    if not previous:
        raise CommandError("回滚记录缺少 previous_commit。")
    result = run(["git", "reset", "--hard", previous], cwd=root, timeout=120)
    if not result["ok"]:
        raise CommandError(result["stderr"] or result["stdout"])
    return {"status": "rolled_back", "commit": previous, "adapter_sync": sync_managed_installations(root)}
