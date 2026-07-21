"""First-run diagnostics with concise evidence instead of raw tracebacks."""

from __future__ import annotations

import platform
import json
import sys
from pathlib import Path
from typing import Any, Dict

from .common import run


def diagnose(root: Path, deep: bool = False) -> Dict[str, Any]:
    checks = []

    def add(name: str, result: Dict[str, Any]) -> None:
        output = result["stdout"] or result["stderr"]
        summary = output.splitlines()[-1] if output.splitlines() else ""
        if result["stdout"].lstrip().startswith("{"):
            try:
                payload = json.loads(result["stdout"])
                if name == "capabilities":
                    capabilities = payload.get("capabilities", {})
                    summary = "python={python} browser={browser} publish={publish}".format(
                        python=capabilities.get("python", {}).get("status", "unknown"),
                        browser=capabilities.get("browser_automation", {}).get("status", "unknown"),
                        publish=capabilities.get("public_publish", {}).get("status", "unknown"),
                    )
                else:
                    summary = str(payload.get("status") or payload.get("summary") or "completed")
            except json.JSONDecodeError:
                pass
        checks.append(
            {
                "name": name,
                "status": "passed" if result["ok"] else "failed",
                "exit_code": result["exit_code"],
                "summary": summary,
            }
        )

    add("capabilities", run([sys.executable, "tools/capability_check.py"], cwd=root, timeout=30))
    add("dashboard", run([sys.executable, "tools/build_dashboard.py", "--check"], cwd=root, timeout=30))
    add("portability", run([sys.executable, "tools/portability_check.py"], cwd=root, timeout=60))
    if deep:
        add("validator_tests", run([sys.executable, "-m", "unittest", "discover", "-s", "validator", "-p", "test*.py"], cwd=root, timeout=180))
        add("cli_tests", run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test*.py"], cwd=root, timeout=180))
    return {
        "schema_version": "1.0",
        "status": "passed" if all(item["status"] == "passed" for item in checks) else "blocked",
        "root": str(root),
        "python": {"version": platform.python_version(), "path": sys.executable, "supported": sys.version_info >= (3, 9)},
        "checks": checks,
    }
