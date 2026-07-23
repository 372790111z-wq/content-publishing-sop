#!/usr/bin/env python3
"""Deterministic release identity shared by validation and authorization tooling."""

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


def _unique_sources(project: Path, manifest: Dict[str, Any], requirements: Dict[str, Any]) -> Iterable[Tuple[str, Path]]:
    files = manifest.get("files", {}) if isinstance(manifest.get("files"), dict) else {}
    sources: List[Tuple[str, Path]] = []
    for label in ("decision_log", "content_requirements", "editorial_policy", "editorial_reviews"):
        relative = files.get(label)
        if relative:
            sources.append((label, (project / relative).resolve()))

    canonical = requirements.get("canonical_prompt", {})
    if isinstance(canonical, dict) and canonical.get("path"):
        sources.append(("canonical_prompt", (project / canonical["path"]).resolve()))

    for index, item in enumerate(requirements.get("deliverables", [])):
        if isinstance(item, dict) and item.get("path"):
            sources.append((f"deliverable:{item.get('id', index)}", (project / item["path"]).resolve()))

    media = requirements.get("media", {}) if isinstance(requirements.get("media"), dict) else {}
    for kind in ("images", "videos"):
        for index, item in enumerate(media.get(kind, [])):
            if isinstance(item, dict) and item.get("path"):
                sources.append((f"{kind}:{index}", (project / item["path"]).resolve()))

    seen = set()
    for label, path in sources:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        yield label, path


def compute_release_digest(project: Path, manifest: Dict[str, Any], requirements: Dict[str, Any]) -> str:
    digest = hashlib.sha256()
    identity = {
        "project_id": manifest.get("project_id"),
        "title": manifest.get("title"),
        "summary": manifest.get("summary"),
        "source_work": manifest.get("source_work"),
    }
    digest.update(b"manifest_identity\0")
    digest.update(json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    digest.update(b"\0")
    for label, path in _unique_sources(project.resolve(), manifest, requirements):
        digest.update(label.encode("utf-8"))
        digest.update(b"\0")
        try:
            digest.update(path.read_bytes())
        except OSError:
            digest.update(b"<missing>")
        digest.update(b"\0")
    return digest.hexdigest()
