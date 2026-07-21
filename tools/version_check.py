#!/usr/bin/env python3
"""Keep VERSION, package metadata, changelog and optional Git tag aligned."""

import os
import re
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.MULTILINE)
    errors = []
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        errors.append(f"VERSION 不是语义化版本：{version}")
    if not match or match.group(1) != version:
        errors.append("pyproject.toml version 与 VERSION 不一致")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    if f"## {version} " not in changelog:
        errors.append("CHANGELOG.md 缺少当前版本条目")
    manifest = json.loads((ROOT / "tool-manifest.json").read_text(encoding="utf-8"))
    if manifest.get("version") != version:
        errors.append("tool-manifest.json version 与 VERSION 不一致")
    tag = os.environ.get("GITHUB_REF_NAME", "")
    if tag.startswith("v") and tag[1:] != version:
        errors.append(f"Git tag {tag} 与 VERSION {version} 不一致")
    if errors:
        print("\n".join(errors))
        return 1
    print(f"version=passed value={version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
