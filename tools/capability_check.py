#!/usr/bin/env python3
"""Detect agent-callable capabilities without installing or mutating tools."""

import argparse
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


def run(command: List[str], timeout: int = 8) -> Dict[str, Any]:
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        output = (completed.stdout or completed.stderr).strip()
        return {"ok": completed.returncode == 0, "exit_code": completed.returncode, "output": output[:1200]}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "exit_code": None, "output": str(exc)}


def first_line(text: str) -> str:
    return text.splitlines()[0].strip() if text.strip() else ""


def executable_capability(name: str, version_args: List[str]) -> Dict[str, Any]:
    path = shutil.which(name)
    if not path:
        return {"status": "unavailable", "path": None, "version": None, "evidence": "command not found"}
    result = run([path] + version_args)
    return {
        "status": "tested" if result["ok"] else "detected",
        "path": path,
        "version": first_line(result["output"]),
        "evidence": f"exit={result['exit_code']}",
    }


def detect_host() -> Dict[str, Any]:
    env = os.environ
    if env.get("CODEX_THREAD_ID") or env.get("CODEX_HOME"):
        host = "codex"
    elif env.get("CLAUDE_CODE") or env.get("CLAUDE_PROJECT_DIR"):
        host = "claude-code"
    elif env.get("CURSOR_TRACE_ID") or "cursor" in env.get("TERM_PROGRAM", "").lower():
        host = "cursor"
    elif "windsurf" in env.get("TERM_PROGRAM", "").lower():
        host = "windsurf"
    elif env.get("VSCODE_PID"):
        host = "vscode-agent"
    else:
        host = "generic-agent"
    return {"status": "tested", "name": host, "evidence": "environment markers"}


def browser_use_versions(executable: Optional[str]) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "skill": {"status": "unavailable", "paths": []},
        "cli": {"status": "unavailable", "path": executable, "reported_version": None},
        "engine": {"status": "unknown", "version": None},
        "harness": {"status": "unknown", "version": None},
        "isolated_wrapper": {"status": "unavailable", "path": shutil.which("browser-use-isolated")},
    }
    home = Path.home()
    skill_candidates = [
        home / ".codex" / "skills" / "browser-use" / "SKILL.md",
        home / ".agents" / "skills" / "browser-use" / "SKILL.md",
    ]
    skill_paths = [str(path) for path in skill_candidates if path.is_file()]
    if skill_paths:
        result["skill"] = {"status": "detected", "paths": skill_paths}
    if executable:
        version = run([executable, "--version"])
        result["cli"] = {
            "status": "tested" if version["ok"] else "detected",
            "path": executable,
            "reported_version": first_line(version["output"]),
        }
        try:
            shebang = Path(executable).read_text(encoding="utf-8", errors="ignore").splitlines()[0]
        except (OSError, IndexError):
            shebang = ""
        interpreter = shebang[2:].strip() if shebang.startswith("#!") else ""
        if interpreter and Path(interpreter).is_file():
            script = (
                "import importlib.metadata as m,json;"
                "o={};"
                "[(o.__setitem__(n,m.version(n))) for n in ['browser-use','browser-harness'] "
                "if any((d.metadata.get('Name') or '').lower()==n for d in m.distributions())];"
                "print(json.dumps(o))"
            )
            versions = run([interpreter, "-c", script])
            if versions["ok"]:
                try:
                    parsed = json.loads(versions["output"])
                    if parsed.get("browser-use"):
                        result["engine"] = {"status": "detected", "version": parsed["browser-use"]}
                    if parsed.get("browser-harness"):
                        result["harness"] = {"status": "detected", "version": parsed["browser-harness"]}
                except json.JSONDecodeError:
                    pass
    if result["isolated_wrapper"]["path"]:
        result["isolated_wrapper"]["status"] = "detected"
    return result


def chatcut_capability() -> Dict[str, Any]:
    root = Path.home() / ".codex" / "plugins" / "cache" / "chatcut-inc" / "chatcut"
    skills = sorted(root.glob("*/skills/verification/SKILL.md")) if root.exists() else []
    if not skills:
        return {"status": "unavailable", "paths": [], "scope": "host adapter only"}
    return {
        "status": "detected",
        "paths": [str(path) for path in skills],
        "scope": "工程级制作和时间线/指定帧验收；实际项目调用后才能标 tested",
    }


def browser_binary() -> Dict[str, Any]:
    candidates = ["google-chrome", "chromium", "chromium-browser", "msedge", "firefox"]
    paths = [path for path in (shutil.which(name) for name in candidates) if path]
    if platform.system() == "Darwin":
        mac_candidates = [
            Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
        ]
        paths.extend(str(path) for path in mac_candidates if path.is_file())
    return {"status": "detected" if paths else "unavailable", "paths": sorted(set(paths))}


def collect() -> Dict[str, Any]:
    browser_use_executable = shutil.which("browser-use")
    pillow = importlib.util.find_spec("PIL") is not None
    python_status = "tested" if sys.version_info >= (3, 9) else "blocked"
    ffmpeg = executable_capability("ffmpeg", ["-version"])
    ffprobe_cap = executable_capability("ffprobe", ["-version"])
    report = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "system": {
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "host": detect_host(),
        "capabilities": {
            "filesystem": {"status": "tested", "evidence": "capability checker read its workspace"},
            "python": {
                "status": python_status,
                "path": sys.executable,
                "version": platform.python_version(),
                "minimum": "3.9",
            },
            "static_dashboard": {"status": "detected", "browser": browser_binary()},
            "image_dimensions": {
                "status": "tested",
                "builtin_formats": ["PNG", "JPEG", "GIF"],
                "pillow": {"status": "detected" if pillow else "unavailable"},
            },
            "video_project_editing": {
                "chatcut": chatcut_capability(),
                "fallback": "ffmpeg CLI or manual timeline",
            },
            "video_file_validation": {
                "status": "tested" if ffmpeg["status"] == "tested" and ffprobe_cap["status"] == "tested" else "unavailable",
                "ffmpeg": ffmpeg,
                "ffprobe": ffprobe_cap,
            },
            "browser_automation": {
                "status": "detected" if browser_use_executable else "unavailable",
                "browser_use": browser_use_versions(browser_use_executable),
                "note": "未运行真实页面连接测试，因此顶层最多为 detected",
            },
            "public_publish": {
                "status": "manual",
                "note": "登录、验证码、协议和最终提交必须由人确认；能力检测不会发布",
            },
        },
    }
    return report


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="检测当前机器可由 IDE/Agent 直接调用的内容生产能力")
    parser.add_argument("--write", help="把检测结果写入 JSON")
    args = parser.parse_args(argv)
    report = collect()
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    print(rendered, end="")
    if args.write:
        path = Path(args.write)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
