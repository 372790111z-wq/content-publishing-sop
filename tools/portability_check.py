#!/usr/bin/env python3
"""Audit the SOP package for portable paths, valid data and source-of-truth drift."""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from build_dashboard import build, dashboard_is_current, read_bundle

VALIDATOR_ROOT = Path(__file__).resolve().parent.parent / "validator"
sys.path.insert(0, str(VALIDATOR_ROOT))
from schema_validate import validate_instance  # noqa: E402
from validate import validate  # noqa: E402


REQUIRED_PATHS = [
    "VERSION",
    "tool-manifest.json",
    "LICENSE",
    "CHANGELOG.md",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "pyproject.toml",
    "setup.py",
    ".github/workflows/ci.yml",
    ".github/workflows/release.yml",
    "START-HERE.md",
    "USAGE-GUIDE.md",
    "skills/content-publishing-sop/SKILL.md",
    "skills/content-publishing-sop/agents/openai.yaml",
    "skills/content-publishing-sop/scripts/find_workbench.py",
    "tools/install_local_skill.py",
    "tools/content_publishing.py",
    "tools/full_schema_check.py",
    "tools/version_check.py",
    "content_publishing/cli.py",
    "content_publishing/mcp_server.py",
    "content_publishing/transactions.py",
    "content_publishing/updater.py",
    "content_publishing/dependencies.py",
    "content_publishing/platforms.json",
    "AGENT-PROTOCOL.md",
    "SOURCE_OF_TRUTH.md",
    "SOP.md",
    "EXECUTE-PROMPT.md",
    "INSTALL.md",
    "validator/validate.py",
    "validator/schema_validate.py",
    "validator/integrity.py",
    "tools/capability_check.py",
    "tools/build_dashboard.py",
    "dashboard/index.html",
    "dashboard/styles.css",
    "dashboard/app.js",
    "dashboard/data.js",
    "projects/registry.json",
    "projects/README.md",
    "schemas/project-registry.schema.json",
    "schemas/SUPPORTED-SUBSET.md",
    "examples/quickstart-demo/project-manifest.json",
    "docs/assets/dashboard-demo.png",
]


def add(issues: List[Dict[str, str]], severity: str, code: str, message: str, path: str = "") -> None:
    issue = {"severity": severity, "code": code, "message": message}
    if path:
        issue["path"] = path
    issues.append(issue)


def audit(root: Path) -> Dict[str, object]:
    root = root.resolve()
    issues: List[Dict[str, str]] = []
    for relative in REQUIRED_PATHS:
        if not (root / relative).is_file():
            add(issues, "error", "structure.missing", "缺少必须文件", relative)

    for path in sorted(root.rglob("*.json")):
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            add(issues, "error", "json.invalid", str(exc), str(path.relative_to(root)))

    registry_path = root / "projects/registry.json"
    registry = {}
    if registry_path.is_file():
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        schema_path = root / "schemas/project-registry.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8")) if schema_path.is_file() else {}
        for message in validate_instance(registry, schema):
            add(issues, "error", "registry.schema", message, "projects/registry.json")
        project_ids = []
        for index, item in enumerate(registry.get("projects", [])):
            if not isinstance(item, dict) or not item.get("enabled"):
                continue
            project_path = (registry_path.parent / str(item.get("path", ""))).resolve()
            if not (project_path / "project-manifest.json").is_file():
                add(issues, "error", "registry.project_missing", "注册项目不存在或缺少 manifest", str(item.get("path")))
                continue
            result = validate(project_path)
            project_ids.append(result.get("project_id"))
            if result.get("status") != "passed":
                add(issues, "error", "registry.project_blocked", "注册项目未通过默认内容门禁", str(item.get("path")))
        if len(project_ids) != len(set(project_ids)):
            add(issues, "error", "registry.project_id", "注册项目的 project_id 必须唯一", "projects/registry.json")

    absolute_patterns = [
        re.compile(r"/Users/[^/\s]+/"),
        re.compile(r"[A-Za-z]:\\Users\\[^\\\s]+\\"),
        re.compile(r"file://", re.IGNORECASE),
    ]
    scan_roots = [root / "adapters", root / "templates", root / "schemas"]
    for scan_root in scan_roots:
        for path in sorted(item for item in scan_root.rglob("*") if item.is_file()):
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeError:
                continue
            for pattern in absolute_patterns:
                if pattern.search(text):
                    add(issues, "error", "portability.absolute_path", "适配层或模板包含设备绝对路径", str(path.relative_to(root)))

    adapter_files = {
        "codex": root / "adapters/codex/AGENTS.md",
        "claude-code": root / "adapters/claude-code/CLAUDE.md",
        "cursor": root / "adapters/cursor/content-publishing-sop.mdc",
        "windsurf": root / "adapters/windsurf/AGENTS.md",
        "vscode-agent": root / "adapters/vscode-agent/copilot-instructions.md",
        "grok": root / "adapters/grok/SKILL.template.md",
        "generic-agent": root / "adapters/generic-agent/PROMPT.md",
    }
    for host, path in adapter_files.items():
        if not path.is_file():
            add(issues, "error", "adapter.missing", "缺少 IDE 入口", host)
            continue
        text = path.read_text(encoding="utf-8")
        if "START-HERE.md" not in text:
            add(issues, "error", "adapter.entry", "适配器没有指向 START-HERE.md", str(path.relative_to(root)))
        if len(text) > 12000:
            add(issues, "warning", "adapter.too_long", "薄适配器超过 12000 字符", str(path.relative_to(root)))

    dashboard_html = (root / "dashboard/index.html").read_text(encoding="utf-8") if (root / "dashboard/index.html").is_file() else ""
    for asset in ("styles.css", "data.js", "app.js"):
        if asset not in dashboard_html:
            add(issues, "error", "dashboard.reference", "看板没有引用必须资产", asset)

    dashboard_data_path = root / "dashboard/data.js"
    if dashboard_data_path.is_file() and re.search(r"/Users/[^/\s]+/|[A-Za-z]:\\\\Users\\\\", dashboard_data_path.read_text(encoding="utf-8")):
        add(issues, "error", "dashboard.absolute_path", "看板缓存包含设备绝对路径", "dashboard/data.js")
    expected_dashboard = build(root / "examples", dashboard_data_path)
    if not dashboard_is_current(read_bundle(dashboard_data_path), expected_dashboard):
        add(issues, "error", "dashboard.stale", "看板缓存与当前真源不一致，请重建后再交付", "dashboard/data.js")

    errors = sum(issue["severity"] == "error" for issue in issues)
    warnings = sum(issue["severity"] == "warning" for issue in issues)
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root": str(root),
        "status": "passed" if errors == 0 else "blocked",
        "summary": {"errors": errors, "warnings": warnings, "checks": len(REQUIRED_PATHS)},
        "issues": issues,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    script_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="检查工作台是否可跨机器和跨 IDE 复制")
    parser.add_argument("--root", default=str(script_root))
    parser.add_argument("--write", help="写入 JSON 报告")
    args = parser.parse_args(argv)
    result = audit(Path(args.root))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.write:
        output = Path(args.write)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
