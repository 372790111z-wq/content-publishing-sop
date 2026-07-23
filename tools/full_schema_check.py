#!/usr/bin/env python3
"""Validate registered projects with the optional full Draft 2020-12 implementation."""

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
FILE_SCHEMAS = {
    "project-manifest.json": "project-manifest.schema.json",
    "decision-log.json": "decision-log.schema.json",
    "content-requirements.json": "content-requirements.schema.json",
    "platform-status.json": "platform-status.schema.json",
    "publication-receipts.json": "publication-receipts.schema.json",
    "metrics.json": "metrics.schema.json",
    "handoff-state.json": "handoff-state.schema.json",
}
OPTIONAL_FILE_SCHEMAS = {
    "editorial_policy": "editorial-policy.schema.json",
    "editorial_reviews": "editorial-reviews.schema.json",
}


def main() -> int:
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        print("jsonschema is not installed; use: python3 -m pip install -e '.[schema]'", file=sys.stderr)
        return 3
    registry_path = ROOT / "projects" / "registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    errors = []
    registry_schema = json.loads((ROOT / "schemas" / "project-registry.schema.json").read_text(encoding="utf-8"))
    errors.extend(f"projects/registry.json: {item.message}" for item in Draft202012Validator(registry_schema).iter_errors(registry))
    for entry in registry.get("projects", []):
        if not entry.get("enabled"):
            continue
        project = (registry_path.parent / entry["path"]).resolve()
        manifest = json.loads((project / "project-manifest.json").read_text(encoding="utf-8"))
        for filename, schema_name in FILE_SCHEMAS.items():
            data = json.loads((project / filename).read_text(encoding="utf-8"))
            schema = json.loads((ROOT / "schemas" / schema_name).read_text(encoding="utf-8"))
            errors.extend(f"{project.name}/{filename}: {item.message}" for item in Draft202012Validator(schema).iter_errors(data))
        for pointer, schema_name in OPTIONAL_FILE_SCHEMAS.items():
            relative = manifest.get("files", {}).get(pointer)
            if not relative:
                continue
            data = json.loads((project / relative).read_text(encoding="utf-8"))
            schema = json.loads((ROOT / "schemas" / schema_name).read_text(encoding="utf-8"))
            errors.extend(f"{project.name}/{relative}: {item.message}" for item in Draft202012Validator(schema).iter_errors(data))
    if errors:
        print("\n".join(errors))
        return 1
    print(f"full_schema=passed projects={sum(bool(item.get('enabled')) for item in registry.get('projects', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
