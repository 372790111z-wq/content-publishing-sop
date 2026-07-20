#!/usr/bin/env python3
"""Print the deterministic digest for the exact content release in a project."""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

VALIDATOR_ROOT = Path(__file__).resolve().parent.parent / "validator"
sys.path.insert(0, str(VALIDATOR_ROOT))
from integrity import compute_release_digest  # noqa: E402


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="计算内容冻结版本的 SHA-256 身份")
    parser.add_argument("--project", required=True, help="包含 project-manifest.json 的项目目录")
    args = parser.parse_args(argv)
    project = Path(args.project).resolve()
    manifest = json.loads((project / "project-manifest.json").read_text(encoding="utf-8"))
    files = manifest.get("files", {})
    requirements_path = (project / files.get("content_requirements", "content-requirements.json")).resolve()
    requirements = json.loads(requirements_path.read_text(encoding="utf-8"))
    print(compute_release_digest(project, manifest, requirements))
    return 0


if __name__ == "__main__":
    sys.exit(main())
