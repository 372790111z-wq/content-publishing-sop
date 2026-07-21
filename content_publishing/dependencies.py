"""Discover external CLIs separately from this project's own update lifecycle."""

from __future__ import annotations

import importlib.metadata
import json
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from .common import CommandError, run


DEPENDENCIES = {
    "browser-use": {
        "commands": [("browser-use", ["--version"])],
        "packages": ["browser-harness", "browser-use"],
        "role": "浏览器自动化与隔离执行",
    },
    "ffmpeg": {
        "commands": [("ffmpeg", ["-version"]), ("ffprobe", ["-version"])],
        "packages": [],
        "role": "视频文件级检查",
    },
    "playwright": {
        "commands": [("playwright", ["--version"])],
        "packages": ["playwright"],
        "role": "浏览器自动化后备",
    },
    "pillow": {
        "commands": [],
        "packages": ["Pillow"],
        "role": "图片深度检查",
    },
}


def _first_line(value: str) -> str:
    return value.splitlines()[0].strip() if value.strip() else ""


def _package_version(name: str) -> Optional[str]:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _executable_python(path: Path) -> Optional[str]:
    try:
        first = path.read_text(encoding="utf-8", errors="ignore").splitlines()[0]
    except (OSError, IndexError):
        return None
    if first.startswith("#!"):
        candidate = first[2:].strip()
        if Path(candidate).is_file():
            return candidate
    return None


def _environment_package_versions(interpreter: str, packages: List[str]) -> Dict[str, Optional[str]]:
    script = (
        "import importlib.metadata as m,json;"
        f"names={packages!r};"
        "out={};"
        "\nfor name in names:\n"
        " try: out[name]=m.version(name)\n"
        " except m.PackageNotFoundError: out[name]=None\n"
        "print(json.dumps(out))"
    )
    result = run([interpreter, "-c", script], timeout=15)
    if not result["ok"]:
        return {}
    try:
        value = json.loads(result["stdout"])
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def detect(name: str) -> Dict[str, Any]:
    spec = DEPENDENCIES.get(name)
    if not spec:
        raise CommandError(f"未知依赖：{name}")
    commands = []
    for executable, args in spec["commands"]:
        path = shutil.which(executable)
        if not path:
            commands.append({"name": executable, "status": "unavailable", "path": None, "version": None})
            continue
        result = run([path] + args, timeout=12)
        output = result["stdout"] or result["stderr"]
        commands.append(
            {
                "name": executable,
                "status": "tested" if result["ok"] else "detected",
                "path": path,
                "version": _first_line(output) if result["ok"] else None,
                "diagnostic": None if result["ok"] else _first_line(output),
            }
        )
    packages = {package: _package_version(package) for package in spec["packages"]}
    interpreters = [
        _executable_python(Path(item["path"]))
        for item in commands
        if item.get("path")
    ]
    for interpreter in (item for item in interpreters if item):
        environment_versions = _environment_package_versions(interpreter, spec["packages"])
        for package, version in environment_versions.items():
            if version:
                packages[package] = version
    available = any(item["status"] in {"tested", "detected"} for item in commands) or any(packages.values())
    return {"id": name, "role": spec["role"], "status": "detected" if available else "unavailable", "commands": commands, "packages": packages}


def list_dependencies() -> Dict[str, Any]:
    return {"schema_version": "1.0", "dependencies": [detect(name) for name in DEPENDENCIES]}


def _pypi_latest(package: str) -> Dict[str, Optional[str]]:
    url = f"https://pypi.org/pypi/{package}/json"
    request = urllib.request.Request(url, headers={"User-Agent": "content-publishing-sop/0.2"})
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
        version = payload.get("info", {}).get("version")
        return {"status": "verified" if version else "unknown", "version": version, "error": None}
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return {"status": "unknown", "version": None, "error": str(exc)[:300]}


def check_updates(name: Optional[str] = None) -> Dict[str, Any]:
    names = [name] if name else list(DEPENDENCIES)
    rows = []
    for dependency in names:
        current = detect(dependency)
        latest = {package: _pypi_latest(package) for package in DEPENDENCIES[dependency]["packages"]}
        current["latest_packages"] = latest
        update_available = any(
            installed and latest.get(package, {}).get("version") and installed != latest[package]["version"]
            for package, installed in current["packages"].items()
        )
        checked_installed = [
            latest.get(package, {}).get("status") == "verified"
            for package, installed in current["packages"].items()
            if installed
        ]
        current["update_status"] = "available" if update_available else ("current" if checked_installed and all(checked_installed) else "unknown")
        if dependency == "ffmpeg" and shutil.which("brew"):
            outdated = run([shutil.which("brew") or "brew", "outdated", "--json=v2", "ffmpeg"], timeout=45)
            current["brew_check"] = {
                "status": "verified" if outdated["ok"] else "unknown",
                "outdated": bool(outdated["ok"] and '"ffmpeg"' in outdated["stdout"]),
                "error": None if outdated["ok"] else (outdated["stderr"] or outdated["stdout"])[:300],
            }
            if current["brew_check"]["outdated"]:
                current["update_status"] = "available"
            elif outdated["ok"]:
                current["update_status"] = "current"
        rows.append(current)
    return {"schema_version": "1.0", "dependencies": rows}


def upgrade_plan(name: str) -> List[str]:
    current = detect(name)
    if current["status"] == "unavailable":
        raise CommandError(f"{name} 未安装，升级命令不会擅自把安装变成新增。")
    if name == "ffmpeg":
        brew = shutil.which("brew")
        ffmpeg = shutil.which("ffmpeg")
        if brew and ffmpeg and ("homebrew" in ffmpeg or "/usr/local/" in ffmpeg):
            return [brew, "upgrade", "ffmpeg"]
        raise CommandError("无法确认 FFmpeg 的安装提供者；请使用原包管理器升级。")
    if name == "pillow":
        return [sys.executable, "-m", "pip", "install", "--upgrade", "Pillow"]
    command_path = next((item.get("path") for item in current["commands"] if item.get("path")), None)
    interpreter = _executable_python(Path(command_path)) if command_path else None
    if not interpreter:
        raise CommandError("无法确认该 CLI 属于哪个 Python 环境，拒绝跨环境升级。")
    interpreter_path = Path(interpreter)
    interpreter_parts = interpreter_path.parts
    if "uv" in interpreter_parts and "tools" in interpreter_parts:
        tools_index = interpreter_parts.index("tools")
        tool_name = interpreter_parts[tools_index + 1] if len(interpreter_parts) > tools_index + 1 else name
        uv = shutil.which("uv")
        if uv:
            return [uv, "tool", "upgrade", tool_name]
    packages = DEPENDENCIES[name]["packages"]
    return [interpreter, "-m", "pip", "install", "--upgrade", *packages]


def upgrade(name: str, apply: bool) -> Dict[str, Any]:
    command = upgrade_plan(name)
    if not apply:
        return {"status": "planned", "dependency": name, "command": command, "message": "追加 --apply 才会执行。"}
    result = run(command, timeout=600)
    if not result["ok"]:
        raise CommandError(f"升级失败：{result['stderr'] or result['stdout']}")
    return {"status": "upgraded", "dependency": name, "command": command, "after": detect(name)}
