#!/usr/bin/env python3
"""Build a file:// friendly dashboard data bundle from project manifests."""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


DATA_PREFIX = "window.CONTENT_SOP_DATA = "
DASHBOARD_SCHEMA_VERSION = "1.4"
METRIC_COMPLETE_STATUSES = {"captured", "partial", "unavailable"}
SOURCE_FILE_KEYS = (
    "decision_log", "content_requirements", "platform_status", "metrics",
    "handoff_state", "publication_receipts", "editorial_policy", "editorial_reviews",
)
METRIC_FIELDS = ("views", "likes", "favorites", "comments", "shares", "follower_change")


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return default


def resolve(project: Path, value: Optional[str], fallback: str) -> Path:
    return (project / (value or fallback)).resolve()


def latest_metrics(metrics: Dict[str, Any]) -> Dict[str, Any]:
    latest: Dict[str, Dict[str, Any]] = {}
    latest_keys: Dict[str, tuple] = {}
    for index, snapshot in enumerate(metrics.get("snapshots", [])):
        if not isinstance(snapshot, dict):
            continue
        platform = snapshot.get("platform", "unknown")
        sort_key = (str(snapshot.get("captured_at") or snapshot.get("attempted_at") or ""), index)
        if platform not in latest or sort_key >= latest_keys[platform]:
            latest[platform] = snapshot
            latest_keys[platform] = sort_key
    return latest


def metric_history(metrics: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    history: Dict[str, List[tuple]] = {}
    for index, snapshot in enumerate(metrics.get("snapshots", [])):
        if not isinstance(snapshot, dict):
            continue
        platform = str(snapshot.get("platform") or "unknown")
        sort_key = (str(snapshot.get("captured_at") or snapshot.get("attempted_at") or ""), index)
        history.setdefault(platform, []).append((sort_key, snapshot))
    return {
        platform: [item[1] for item in sorted(rows, key=lambda item: item[0])][-30:]
        for platform, rows in history.items()
    }


def metric_trends(history: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Dict[str, Optional[int]]]:
    trends: Dict[str, Dict[str, Optional[int]]] = {}
    for platform, snapshots in history.items():
        measured = [
            item for item in snapshots
            if item.get("collection_status") in {"captured", "partial"} and isinstance(item.get("values"), dict)
        ]
        row: Dict[str, Optional[int]] = {field: None for field in METRIC_FIELDS}
        if len(measured) >= 2:
            previous = measured[-2].get("values", {})
            current = measured[-1].get("values", {})
            for field in METRIC_FIELDS:
                before, after = previous.get(field), current.get(field)
                if isinstance(before, int) and not isinstance(before, bool) and isinstance(after, int) and not isinstance(after, bool):
                    row[field] = after - before
        trends[platform] = row
    return trends


def metrics_summary(platforms: List[Dict[str, Any]], latest: Dict[str, Any]) -> Dict[str, Any]:
    status_counts: Dict[str, int] = {}
    published = [item.get("platform") for item in platforms if item.get("status") == "published"]
    complete = 0
    latest_at: Optional[str] = None
    for item in platforms:
        platform = item.get("platform")
        snapshot = latest.get(platform, {})
        status = snapshot.get("collection_status", "not_collected")
        status_counts[status] = status_counts.get(status, 0) + 1
        if platform in published and status in METRIC_COMPLETE_STATUSES:
            complete += 1
        timestamp = snapshot.get("captured_at") or snapshot.get("attempted_at")
        if timestamp and (latest_at is None or timestamp > latest_at):
            latest_at = timestamp
    return {
        "platform_statuses": status_counts,
        "published_platforms": len(published),
        "complete_published_platforms": complete,
        "latest_at": latest_at,
    }


def discover_projects(root: Path, registry_path: Optional[Path] = None) -> tuple:
    registry = registry_path or (root.parent / "projects" / "registry.json")
    if registry.is_file():
        data = read_json(registry, {})
        projects: List[Path] = []
        for item in data.get("projects", []):
            if not isinstance(item, dict) or not item.get("enabled", False) or not item.get("path"):
                continue
            path = (registry.parent / item["path"]).resolve()
            if (path / "project-manifest.json").is_file():
                projects.append(path)
        return projects, registry.resolve()
    return [path.parent for path in sorted(root.glob("*/project-manifest.json"))], None


def source_digest(projects: List[Path], registry_path: Optional[Path]) -> str:
    digest = hashlib.sha256()
    if registry_path:
        digest.update(b"registry\n")
        digest.update(registry_path.read_bytes())
        digest.update(b"\n")
    for project in sorted(projects, key=lambda item: str(item)):
        manifest_path = project / "project-manifest.json"
        manifest = read_json(manifest_path, {})
        files = manifest.get("files", {}) if isinstance(manifest.get("files"), dict) else {}
        sources = [("project_manifest", manifest_path)]
        for key in SOURCE_FILE_KEYS:
            sources.append((key, resolve(project, files.get(key), f"{key}.json")))
        sources.append(("validation_report", project / "validation-report.json"))
        for label, path in sources:
            digest.update(f"{project.name}:{label}\n".encode("utf-8"))
            try:
                digest.update(path.read_bytes())
            except OSError:
                digest.update(b"<missing>")
            digest.update(b"\n")
    return digest.hexdigest()


def project_record(project: Path, dashboard: Path, kind: str = "project") -> Dict[str, Any]:
    manifest = read_json(project / "project-manifest.json", {})
    files = manifest.get("files", {}) if isinstance(manifest.get("files"), dict) else {}
    decisions = read_json(resolve(project, files.get("decision_log"), "decision-log.json"), {})
    requirements = read_json(resolve(project, files.get("content_requirements"), "content-requirements.json"), {})
    platform_status = read_json(resolve(project, files.get("platform_status"), "platform-status.json"), {})
    metrics = read_json(resolve(project, files.get("metrics"), "metrics.json"), {})
    handoff = read_json(resolve(project, files.get("handoff_state"), "handoff-state.json"), {})
    receipts = read_json(resolve(project, files.get("publication_receipts"), "publication-receipts.json"), {})
    editorial_policy = read_json(resolve(project, files.get("editorial_policy"), "editorial-policy.json"), {})
    editorial_reviews = read_json(resolve(project, files.get("editorial_reviews"), "editorial-reviews.json"), {})
    validation = read_json(project / "validation-report.json", {})
    media = requirements.get("media", {}) if isinstance(requirements.get("media"), dict) else {}
    platform_items = platform_status.get("platforms", [])
    latest_metric_values = latest_metrics(metrics)
    histories = metric_history(metrics)
    trends = metric_trends(histories)
    path_from_dashboard = Path(os.path.relpath(project, dashboard))
    grants = manifest.get("authorization", {}).get("grants", [])
    active_grants = [item for item in grants if isinstance(item, dict) and item.get("status") == "active"]
    text_kinds = {"master", "longform", "social", "video_script"}
    required_text_ids = {
        str(item.get("id")) for item in requirements.get("deliverables", [])
        if isinstance(item, dict) and item.get("required") and item.get("kind") in text_kinds and item.get("id")
    }
    review_items = [item for item in editorial_reviews.get("reviews", []) if isinstance(item, dict)]
    verified_review_ids = {
        str(item.get("deliverable_id")) for item in review_items
        if item.get("status") == "verified" and item.get("deliverable_id") in required_text_ids
    }
    author_voice = editorial_policy.get("author_voice", {}) if isinstance(editorial_policy.get("author_voice"), dict) else {}
    platform_profiles = editorial_policy.get("platform_profiles", []) if isinstance(editorial_policy.get("platform_profiles"), list) else []
    return {
        "kind": kind,
        "project_id": manifest.get("project_id", project.name),
        "title": manifest.get("title", project.name),
        "summary": manifest.get("summary", ""),
        "status": manifest.get("status", "unknown"),
        "updated_at": manifest.get("updated_at"),
        "source_work": manifest.get("source_work", {}),
        "authorization": manifest.get("authorization", {}),
        "active_grants": active_grants,
        "release": manifest.get("release", {}),
        "handoff_state": handoff,
        "validation": {
            "status": validation.get("status", manifest.get("last_validation", {}).get("status", "unknown")),
            "summary": validation.get("summary", {}),
            "gates": validation.get("gates", []),
        },
        "editorial": {
            "author_voice_status": author_voice.get("status", "unknown"),
            "author_voice_mode": author_voice.get("mode"),
            "platform_profiles": len(platform_profiles),
            "required_reviews": len(required_text_ids),
            "verified_reviews": len(verified_review_ids),
        },
        "counts": {
            "decisions": len(decisions.get("events", [])),
            "deliverables": len(requirements.get("deliverables", [])),
            "images": len(media.get("images", [])),
            "videos": len(media.get("videos", [])),
            "platforms": len(platform_status.get("platforms", [])),
            "receipts": len(receipts.get("receipts", [])),
        },
        "decisions": decisions.get("events", []),
        "platforms": platform_items,
        "metrics": latest_metric_values,
        "metrics_history": histories,
        "metrics_trends": trends,
        "metrics_summary": metrics_summary(platform_items, latest_metric_values),
        "links": {
            "project": path_from_dashboard.as_posix(),
            "manifest": (path_from_dashboard / "project-manifest.json").as_posix(),
            "handoff": (path_from_dashboard / files.get("handoff", "HANDOFF.md")).as_posix(),
        },
    }


def build(root: Path, output: Path, registry_path: Optional[Path] = None) -> Dict[str, Any]:
    project_paths, registry = discover_projects(root, registry_path)
    kinds: Dict[Path, str] = {}
    if registry:
        registry_data = read_json(registry, {})
        for item in registry_data.get("projects", []):
            if isinstance(item, dict) and item.get("path"):
                kinds[(registry.parent / item["path"]).resolve()] = str(item.get("kind") or "project")
    projects = [project_record(path, output.parent, kinds.get(path.resolve(), "project")) for path in project_paths]
    status_counts: Dict[str, int] = {}
    platform_counts: Dict[str, int] = {}
    metric_counts: Dict[str, int] = {}
    published_metric_total = 0
    published_metric_complete = 0
    for project in projects:
        status = project["status"]
        status_counts[status] = status_counts.get(status, 0) + 1
        for platform in project["platforms"]:
            state = platform.get("status", "unknown")
            platform_counts[state] = platform_counts.get(state, 0) + 1
            metric_state = project["metrics"].get(platform.get("platform"), {}).get("collection_status", "not_collected")
            metric_counts[metric_state] = metric_counts.get(metric_state, 0) + 1
        published_metric_total += project["metrics_summary"]["published_platforms"]
        published_metric_complete += project["metrics_summary"]["complete_published_platforms"]
    return {
        "dashboard_schema_version": DASHBOARD_SCHEMA_VERSION,
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_digest": source_digest(project_paths, registry),
        "registry": Path(os.path.relpath(registry, output.parent)).as_posix() if registry else None,
        "summary": {
            "projects": sum(project.get("kind") != "example" for project in projects),
            "examples": sum(project.get("kind") == "example" for project in projects),
            "project_statuses": status_counts,
            "platform_statuses": platform_counts,
            "metrics": {
                "platform_statuses": metric_counts,
                "published_platforms": published_metric_total,
                "complete_published_platforms": published_metric_complete,
            },
        },
        "projects": projects,
    }


def read_bundle(path: Path) -> Optional[Dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return None
    if not text.startswith(DATA_PREFIX) or not text.endswith(";"):
        return None
    try:
        payload = json.loads(text[len(DATA_PREFIX):-1])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def dashboard_is_current(current: Optional[Dict[str, Any]], expected: Dict[str, Any]) -> bool:
    if current is None:
        return False
    for key in ("dashboard_schema_version", "source_digest", "summary", "projects"):
        if current.get(key) != expected.get(key):
            return False
    return True


def main(argv: Optional[Sequence[str]] = None) -> int:
    script_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="重建本地静态看板的数据文件")
    parser.add_argument("--projects-root", default=str(script_root / "examples"))
    parser.add_argument("--output", default=str(script_root / "dashboard" / "data.js"))
    parser.add_argument("--registry", help="可选项目注册表；默认读取 projects/registry.json")
    parser.add_argument("--check", action="store_true", help="只检查现有看板是否与真源一致，不写文件")
    args = parser.parse_args(argv)
    root = Path(args.projects_root).resolve()
    output = Path(args.output).resolve()
    registry = Path(args.registry).resolve() if args.registry else None
    payload = build(root, output, registry)
    if args.check:
        if dashboard_is_current(read_bundle(output), payload):
            print(f"dashboard=current source_digest={payload['source_digest']}")
            return 0
        print(f"dashboard=stale source_digest={payload['source_digest']}")
        return 1
    rendered = DATA_PREFIX + json.dumps(payload, ensure_ascii=False, indent=2) + ";\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")
    print(f"projects={len(payload['projects'])} output={output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
