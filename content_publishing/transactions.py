"""Transactional release, authorization and publication receipt operations."""

from __future__ import annotations

import copy
import hashlib
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .common import CommandError, atomic_write_bytes, atomic_write_json, read_json, utc_now


VALID_ACTIONS = {"public_publish", "update_publication", "delete_publication", "external_sync"}
APPROVAL_KIND = {
    "public_publish": "content_and_platforms_confirmed",
    "update_publication": "content_and_platforms_confirmed",
    "delete_publication": "destructive_action_confirmed",
    "external_sync": "external_sync_confirmed",
}


def _validator_modules(root: Path):
    validator_root = root / "validator"
    if str(validator_root) not in sys.path:
        sys.path.insert(0, str(validator_root))
    from integrity import compute_release_digest  # type: ignore
    from validate import validate  # type: ignore

    return compute_release_digest, validate


def _paths(project: Path) -> Tuple[Path, Path, Path]:
    return (
        project / "project-manifest.json",
        project / "publication-receipts.json",
        project / "platform-status.json",
    )


def _atomic_group(changes: Iterable[Tuple[Path, Dict[str, Any]]]) -> None:
    rows = list(changes)
    originals = {path: path.read_bytes() for path, _ in rows}
    written: List[Path] = []
    try:
        for path, value in rows:
            atomic_write_json(path, value)
            written.append(path)
    except Exception:
        for path in written:
            atomic_write_bytes(path, originals[path])
        raise


def _project(root: Path, value: str) -> Path:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = candidate.resolve()
    if not (candidate / "project-manifest.json").is_file():
        raise CommandError(f"不是有效内容项目：{candidate}")
    return candidate


def freeze_release(root: Path, project_value: str, version: str) -> Dict[str, Any]:
    project = _project(root, project_value)
    compute_release_digest, validate = _validator_modules(root)
    preflight = validate(project)
    if preflight.get("status") != "passed":
        raise CommandError("默认内容门禁未通过，不能冻结。请先运行 validate 查看错误。")
    manifest_path = project / "project-manifest.json"
    requirements = read_json(project / "content-requirements.json")
    decisions = read_json(project / "decision-log.json")
    manifest = read_json(manifest_path)
    digest = compute_release_digest(project, manifest, requirements)
    sequences = [item.get("sequence") for item in decisions.get("events", []) if isinstance(item, dict) and isinstance(item.get("sequence"), int)]
    if not sequences:
        raise CommandError("decision-log 没有可绑定的决策序号。")
    original = copy.deepcopy(manifest)
    now = utc_now()
    manifest["release"] = {
        "status": "frozen",
        "version": version,
        "frozen_at": now,
        "release_digest": digest,
        "decision_sequence": max(sequences),
        "invalidated_at": None,
        "invalidated_reason": None,
    }
    manifest["updated_at"] = now
    atomic_write_json(manifest_path, manifest)
    strict = validate(project, strict=True)
    if strict.get("status") != "passed":
        atomic_write_json(manifest_path, original)
        raise CommandError("冻结后的 strict 门禁未通过，已恢复原 manifest。")
    return {"status": "frozen", "project": str(project), "version": version, "release_digest": digest}


def create_grant(
    root: Path,
    project_value: str,
    action: str,
    platforms: List[str],
    evidence: str,
    expires_minutes: int = 120,
) -> Dict[str, Any]:
    if action not in VALID_ACTIONS:
        raise CommandError(f"不支持的动作：{action}")
    if not platforms:
        raise CommandError("必须明确至少一个平台。")
    if not evidence.strip():
        raise CommandError("必须保存用户确认原文或可解析证据。")
    if expires_minutes <= 0:
        raise CommandError("expires-minutes 必须大于 0。")
    project = _project(root, project_value)
    manifest_path = project / "project-manifest.json"
    handoff_path = project / "handoff-state.json"
    manifest = read_json(manifest_path)
    handoff = read_json(handoff_path)
    release = manifest.get("release", {})
    digest = release.get("release_digest")
    if release.get("status") != "frozen" or not isinstance(digest, str) or len(digest) != 64:
        raise CommandError("当前 release 未冻结。")
    known = {item.get("platform") for item in read_json(project / "platform-status.json").get("platforms", []) if isinstance(item, dict)}
    unknown = set(platforms) - known
    if unknown:
        raise CommandError(f"平台尚未登记：{', '.join(sorted(unknown))}")
    existing_grants = manifest.get("authorization", {}).get("grants", [])
    duplicate = next(
        (
            item for item in existing_grants
            if isinstance(item, dict)
            and item.get("status") == "active"
            and item.get("action") == action
            and item.get("release_digest") == digest
            and set(platforms).issubset(set(item.get("platforms", [])))
        ),
        None,
    )
    if duplicate:
        raise CommandError(f"已有覆盖当前动作、平台和 release 的有效 grant：{duplicate.get('id')}")
    now = datetime.now(timezone.utc)
    grant_id = f"grant-{now.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    grant = {
        "id": grant_id,
        "action": action,
        "approval_kind": APPROVAL_KIND[action],
        "platforms": list(dict.fromkeys(platforms)),
        "release_digest": digest,
        "granted_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=expires_minutes)).isoformat(),
        "status": "active",
        "consumed_at": None,
        "evidence": evidence,
        "receipt_ids": [],
    }
    manifest.setdefault("authorization", {}).setdefault("grants", []).append(grant)
    manifest["updated_at"] = now.isoformat()
    original = read_json(manifest_path)
    original_handoff = read_json(handoff_path)
    handoff["active_grant_ids"] = sorted(
        item.get("id") for item in manifest["authorization"]["grants"]
        if isinstance(item, dict) and item.get("status") == "active" and item.get("id")
    )
    handoff["updated_at"] = now.isoformat()
    _atomic_group([(manifest_path, manifest), (handoff_path, handoff)])
    _, validate = _validator_modules(root)
    result = validate(project, actions=[action], platforms=platforms)
    if result.get("status") != "passed":
        _atomic_group([(manifest_path, original), (handoff_path, original_handoff)])
        raise CommandError("动作门禁未通过，授权未写入。")
    return {"status": "active", "grant": grant}


def prepare_intents(root: Path, project_value: str, grant_id: str) -> Dict[str, Any]:
    project = _project(root, project_value)
    manifest_path, receipts_path, _ = _paths(project)
    manifest = read_json(manifest_path)
    receipts = read_json(receipts_path)
    grants = manifest.get("authorization", {}).get("grants", [])
    grant = next((item for item in grants if isinstance(item, dict) and item.get("id") == grant_id), None)
    if not grant or grant.get("status") != "active":
        raise CommandError("找不到有效的 active grant。")
    if grant.get("receipt_ids"):
        raise CommandError("该 grant 已准备过 pending intent；必须先对账，不能重复创建。")
    _, validate = _validator_modules(root)
    gate = validate(project, actions=[grant["action"]], platforms=grant["platforms"])
    if gate.get("status") != "passed":
        raise CommandError("整批动作门禁未通过，未创建 pending intent。")
    now = utc_now()
    created = []
    for platform in grant["platforms"]:
        receipt_id = f"receipt-{uuid.uuid4().hex}"
        created.append(
            {
                "id": receipt_id,
                "platform": platform,
                "action": grant["action"],
                "release_digest": grant["release_digest"],
                "grant_id": grant_id,
                "attempted_at": now,
                "status": "unknown",
                "public_url": None,
                "external_id": None,
                "evidence": ["pending intent created before external call"],
            }
        )
    receipts["receipts"].extend(created)
    grant["receipt_ids"] = [item["id"] for item in created]
    manifest["status"] = "publishing"
    manifest["updated_at"] = now
    _atomic_group([(receipts_path, receipts), (manifest_path, manifest)])
    return {"status": "prepared", "grant_id": grant_id, "receipts": created}


def settle_receipt(
    root: Path,
    project_value: str,
    receipt_id: str,
    status: str,
    evidence: List[str],
    public_url: Optional[str] = None,
    external_id: Optional[str] = None,
    reader_verified: bool = False,
    prompt_delivery: Optional[str] = None,
) -> Dict[str, Any]:
    if status not in {"succeeded", "failed", "verified_existing"}:
        raise CommandError("settle 状态必须是 succeeded、failed 或 verified_existing。")
    if not evidence:
        raise CommandError("结算回执必须提供证据。")
    project = _project(root, project_value)
    manifest_path, receipts_path, platforms_path = _paths(project)
    handoff_path = project / "handoff-state.json"
    manifest = read_json(manifest_path)
    receipts = read_json(receipts_path)
    platform_data = read_json(platforms_path)
    handoff = read_json(handoff_path)
    receipt = next((item for item in receipts.get("receipts", []) if isinstance(item, dict) and item.get("id") == receipt_id), None)
    if not receipt:
        raise CommandError("找不到回执。")
    if receipt.get("status") != "unknown":
        raise CommandError("回执已经结算，不能重复覆盖。")
    if status in {"succeeded", "verified_existing"} and receipt.get("action") in {"public_publish", "update_publication"} and not public_url:
        raise CommandError("发布或更新成功的回执必须提供普通读者可访问的 public-url。")
    receipt.update(status=status, evidence=evidence, public_url=public_url, external_id=external_id)
    grant = next(
        (item for item in manifest.get("authorization", {}).get("grants", []) if isinstance(item, dict) and item.get("id") == receipt.get("grant_id")),
        None,
    )
    if not grant:
        raise CommandError("回执对应的 grant 不存在。")
    platform = next((item for item in platform_data.get("platforms", []) if isinstance(item, dict) and item.get("platform") == receipt.get("platform")), None)
    if not platform:
        raise CommandError("回执对应的平台不存在。")
    now = utc_now()
    if status in {"succeeded", "verified_existing"} and receipt.get("action") in {"public_publish", "update_publication"}:
        platform.update(
            status="published",
            public_url=public_url,
            published_at=now,
            release_digest=receipt.get("release_digest"),
            evidence=evidence,
            blocker=None,
        )
        if reader_verified:
            platform["reader_validation"] = "verified"
            existing_delivery = platform.get("prompt_delivery")
            if prompt_delivery:
                platform["prompt_delivery"] = prompt_delivery
            elif existing_delivery == "unknown":
                raise CommandError("读者验收必须明确记录实际提示词交付方式，不能把未知值默认成可访问链接。")
    elif status in {"succeeded", "verified_existing"} and receipt.get("action") == "delete_publication":
        platform.update(
            status="archived",
            public_url=None,
            release_digest=None,
            reader_validation="not_applicable",
            prompt_delivery="not_required",
            evidence=evidence,
            blocker=None,
        )
    elif status in {"succeeded", "verified_existing"}:
        platform.update(evidence=evidence, blocker=None)
    else:
        platform.update(status="failed", evidence=evidence, blocker="外部动作失败，详见发布回执。")

    receipt_map = {item.get("id"): item for item in receipts.get("receipts", []) if isinstance(item, dict)}
    batch = [receipt_map.get(value) for value in grant.get("receipt_ids", [])]
    if batch and all(isinstance(item, dict) and item.get("status") != "unknown" for item in batch):
        grant["status"] = "consumed"
        grant["consumed_at"] = now
        all_succeeded = all(item.get("status") in {"succeeded", "verified_existing"} for item in batch)
        if not all_succeeded:
            manifest["status"] = "blocked"
        elif grant.get("action") == "delete_publication":
            manifest["status"] = "archived"
        elif grant.get("action") in {"public_publish", "update_publication"}:
            manifest["status"] = "published"
    handoff["active_grant_ids"] = sorted(
        item.get("id") for item in manifest.get("authorization", {}).get("grants", [])
        if isinstance(item, dict) and item.get("status") == "active" and item.get("id")
    )
    handoff["updated_at"] = now
    manifest["updated_at"] = now
    _atomic_group([(receipts_path, receipts), (platforms_path, platform_data), (manifest_path, manifest), (handoff_path, handoff)])
    return {"status": status, "receipt": receipt, "grant_status": grant.get("status")}
