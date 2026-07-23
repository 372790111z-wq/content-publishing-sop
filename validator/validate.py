#!/usr/bin/env python3
"""Zero-dependency content completeness validator (Python 3.9+)."""

import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
from difflib import SequenceMatcher
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from integrity import compute_release_digest
from schema_validate import validate_instance

REQUIRED_STAGES = [
    "original_need",
    "new_problem",
    "attempt",
    "user_feedback",
    "decision",
    "rationale",
    "implementation_result",
    "acceptance_evidence",
    "unresolved",
]

METRIC_FIELDS = ("views", "likes", "favorites", "comments", "shares", "follower_change")
METRIC_COLLECTION_STATUSES = {"not_collected", "captured", "partial", "unavailable", "failed"}
METRIC_SOURCES = {"unknown", "platform_api", "creator_backend", "public_page", "manual"}
METRIC_COMPLETE_STATUSES = {"captured", "partial", "unavailable"}
IRREVERSIBLE_ACTIONS = {"public_publish", "update_publication", "delete_publication", "external_sync"}
GITHUB_PROMPT_URL = re.compile(r"^https?://(?:www\.)?(?:github\.com|raw\.githubusercontent\.com)/", re.IGNORECASE)

PUBLIC_PATH_PATTERNS = [
    (re.compile(r"file://", re.IGNORECASE), "file URL"),
    (re.compile(r"/Users/[^/\s]+/"), "macOS absolute user path"),
    (re.compile(r"[A-Za-z]:\\\\Users\\\\[^\\\s]+\\\\"), "Windows absolute user path"),
    (re.compile(r"/(?:home|private)/[^/\s]+/"), "local absolute path"),
]


class Report:
    def __init__(
        self,
        project_id: str,
        strict: bool,
        for_publish: bool,
        postflight: bool,
        require_metrics: bool,
        actions: Sequence[str],
        platforms: Sequence[str],
    ) -> None:
        self.project_id = project_id
        self.strict = strict
        self.for_publish = for_publish
        self.postflight = postflight
        self.require_metrics = require_metrics
        self.actions = list(actions)
        self.platforms = list(platforms)
        self.release_digest: Optional[str] = None
        self.issues: List[Dict[str, Any]] = []
        self.checks = 0

    def add(self, severity: str, code: str, message: str, path: Optional[str] = None) -> None:
        self.checks += 1
        issue = {"severity": severity, "code": code, "message": message}
        if path:
            issue["path"] = path
        self.issues.append(issue)

    def ok(self, code: str, message: str, path: Optional[str] = None) -> None:
        self.add("info", code, message, path)

    def warn(self, code: str, message: str, path: Optional[str] = None) -> None:
        self.add("warning", code, message, path)

    def fail(self, code: str, message: str, path: Optional[str] = None) -> None:
        self.add("error", code, message, path)

    def result(self) -> Dict[str, Any]:
        errors = sum(1 for issue in self.issues if issue["severity"] == "error")
        warnings = sum(1 for issue in self.issues if issue["severity"] == "warning")
        effective_blockers = errors + (warnings if self.strict else 0)
        gates: Dict[str, Dict[str, int]] = {}
        for issue in self.issues:
            gate = issue["code"].split(".", 1)[0]
            bucket = gates.setdefault(gate, {"error": 0, "warning": 0, "info": 0})
            bucket[issue["severity"]] += 1
        gate_rows = []
        for name, counts in sorted(gates.items()):
            blocked = counts["error"] > 0 or (self.strict and counts["warning"] > 0)
            gate_rows.append({"gate": name, "status": "blocked" if blocked else "passed", **counts})
        return {
            "schema_version": "1.0",
            "project_id": self.project_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": {
                "strict": self.strict,
                "for_publish": self.for_publish,
                "postflight": self.postflight,
                "require_metrics": self.require_metrics,
                "actions": self.actions,
                "platforms": self.platforms,
            },
            "release_digest": self.release_digest,
            "status": "blocked" if effective_blockers else "passed",
            "summary": {
                "checks": self.checks,
                "errors": errors,
                "warnings": warnings,
                "informational": len(self.issues) - errors - warnings,
            },
            "gates": gate_rows,
            "issues": self.issues,
        }


def load_json(path: Path, report: Report, code: str) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        report.fail(f"{code}.missing", "缺少 JSON 文件", path.name)
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        report.fail(f"{code}.invalid_json", f"JSON 无法读取：{exc}", path.name)
        return None
    if not isinstance(data, dict):
        report.fail(f"{code}.wrong_type", "JSON 顶层必须是对象", path.name)
        return None
    report.ok(f"{code}.loaded", "JSON 已读取", path.name)
    return data


def check_schema(data: Optional[Dict[str, Any]], schema_name: str, report: Report, code: str, path: str) -> None:
    if data is None:
        return
    schema_path = Path(__file__).resolve().parent.parent / "schemas" / schema_name
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        report.fail(f"{code}.schema_unavailable", f"Schema 无法读取：{exc}", str(schema_path))
        return
    errors = validate_instance(data, schema)
    if errors:
        for message in errors[:50]:
            report.fail(f"{code}.schema", message, path)
        if len(errors) > 50:
            report.fail(f"{code}.schema", f"另有 {len(errors) - 50} 个 Schema 错误未展开", path)
    else:
        report.ok(f"{code}.schema", "JSON Schema 校验通过", path)


def resolve(project: Path, relative: str) -> Path:
    return (project / relative).resolve()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def meaningful_lines(text: str) -> Tuple[str, str]:
    lines = [line.strip() for line in text.replace("\r\n", "\n").split("\n") if line.strip()]
    if not lines:
        return "", ""
    return lines[0], lines[-1]


def normalized(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def is_http_url(value: Any) -> bool:
    return bool(re.match(r"^https?://[^\s]+$", str(value or "").strip(), re.IGNORECASE))


def has_resolvable_evidence(project: Path, evidence: Any) -> bool:
    if not isinstance(evidence, list):
        return False
    for item in evidence:
        value = str(item or "").strip()
        if re.match(r"^https?://", value, re.IGNORECASE):
            return True
        local_value, separator, fragment = value.partition("#")
        if not local_value:
            continue
        path = resolve(project, local_value)
        if not path.is_file():
            continue
        if not separator or not fragment:
            return True
        try:
            if fragment in path.read_text(encoding="utf-8"):
                return True
        except (OSError, UnicodeError):
            continue
    return False


def valid_iso_datetime(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def parse_iso_datetime(value: Any) -> Optional[datetime]:
    if not valid_iso_datetime(value):
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def image_dimensions(path: Path) -> Optional[Tuple[int, int]]:
    try:
        with path.open("rb") as handle:
            header = handle.read(32)
            if header.startswith(b"\x89PNG\r\n\x1a\n") and len(header) >= 24:
                return struct.unpack(">II", header[16:24])
            if header[:6] in (b"GIF87a", b"GIF89a") and len(header) >= 10:
                return struct.unpack("<HH", header[6:10])
            if header.startswith(b"\xff\xd8"):
                handle.seek(2)
                while True:
                    byte = handle.read(1)
                    while byte == b"\xff":
                        byte = handle.read(1)
                    if not byte:
                        return None
                    marker = byte[0]
                    if marker in (0xD8, 0xD9):
                        continue
                    length_bytes = handle.read(2)
                    if len(length_bytes) != 2:
                        return None
                    length = struct.unpack(">H", length_bytes)[0]
                    if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                        payload = handle.read(5)
                        if len(payload) != 5:
                            return None
                        height, width = struct.unpack(">HH", payload[1:5])
                        return width, height
                    handle.seek(max(0, length - 2), os.SEEK_CUR)
    except OSError:
        return None
    return None


def ffprobe(path: Path) -> Optional[Dict[str, Any]]:
    executable = shutil.which("ffprobe")
    if not executable:
        return None
    command = [
        executable,
        "-v", "error",
        "-show_entries", "format=duration,format_name:stream=index,codec_type,codec_name,width,height,r_frame_rate",
        "-of", "json",
        str(path),
    ]
    try:
        completed = subprocess.run(command, check=True, capture_output=True, text=True, timeout=30)
        return json.loads(completed.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return {}


def check_manifest(project: Path, manifest: Dict[str, Any], report: Report) -> None:
    for field in ("project_id", "title", "status", "updated_at", "source_work", "files", "authorization"):
        if field not in manifest:
            report.fail("manifest.required", f"manifest 缺少字段：{field}", "project-manifest.json")
    if manifest.get("schema_version") != "1.2":
        report.fail("manifest.schema", "不支持的 schema_version", "project-manifest.json")
    source = manifest.get("source_work")
    if isinstance(source, dict):
        accepted_at = parse_iso_datetime(source.get("accepted_at"))
        requested_at = parse_iso_datetime(source.get("content_requested_at"))
        if source.get("source_type") != "completed_requirement" or source.get("status") != "accepted":
            report.fail("source_work.not_completed", "内容项目只能来源于已经完成并验收的需求", "project-manifest.json")
        if accepted_at is None or requested_at is None:
            report.fail("source_work.time", "来源需求验收时间和内容发起时间必须有效", "project-manifest.json")
        elif requested_at < accepted_at:
            report.fail("source_work.trigger_order", "内容沉淀不能早于需求验收完成", "project-manifest.json")
        if not has_resolvable_evidence(project, source.get("acceptance_evidence")):
            report.fail("source_work.acceptance_evidence", "缺少可解析的需求验收证据", "project-manifest.json")
        if not has_resolvable_evidence(project, source.get("request_evidence")):
            report.fail("source_work.request_evidence", "缺少用户明确要求沉淀内容的证据", "project-manifest.json")
        if not str(source.get("reuse_reason") or "").strip():
            report.fail("source_work.reuse_reason", "没有记录这次需求为什么值得复用", "project-manifest.json")
        if not any(issue["code"].startswith("source_work.") and issue["severity"] == "error" for issue in report.issues):
            report.ok("source_work.verified", "来源需求已验收，且内容沉淀在验收之后由用户触发", "project-manifest.json")
    files = manifest.get("files", {})
    if isinstance(files, dict):
        for key in (
            "decision_log", "content_requirements", "platform_status", "metrics", "checksums",
            "master_content", "handoff", "handoff_state", "publication_receipts",
        ):
            relative = files.get(key)
            if not relative:
                report.fail("manifest.file_pointer", f"缺少文件入口：{key}", "project-manifest.json")
            elif not resolve(project, relative).is_file():
                report.fail("manifest.file_missing", f"入口文件不存在：{key}", relative)
            else:
                report.ok("manifest.file_exists", f"入口文件存在：{key}", relative)
    authorization = manifest.get("authorization", {})
    if any(authorization.get(key) for key in ("public_publish", "delete_or_overwrite", "external_sync")):
        report.warn("authorization.legacy_boolean", "旧布尔授权不再构成不可逆动作授权，只接受范围化 grant", "project-manifest.json")


def check_decisions(data: Optional[Dict[str, Any]], project_id: str, report: Report) -> None:
    if not data:
        return
    if data.get("project_id") != project_id:
        report.fail("decisions.project_id", "decision-log 的 project_id 不一致", "decision-log.json")
    events = data.get("events")
    if not isinstance(events, list):
        report.fail("decisions.events", "events 必须是数组", "decision-log.json")
        return
    stages = {event.get("stage") for event in events if isinstance(event, dict)}
    for stage in REQUIRED_STAGES:
        if stage not in stages:
            report.fail("decisions.stage_missing", f"讨论时间线缺少阶段：{stage}", "decision-log.json")
        else:
            report.ok("decisions.stage_present", f"讨论阶段已记录：{stage}", "decision-log.json")
    sequences = [event.get("sequence") for event in events if isinstance(event, dict)]
    event_ids = [event.get("id") for event in events if isinstance(event, dict)]
    if len(event_ids) != len(events) or any(not str(value or "").strip() for value in event_ids) or len(set(event_ids)) != len(event_ids):
        report.fail("decisions.id", "事件 id 必须是非空唯一值", "decision-log.json")
    valid_sequences = [value for value in sequences if isinstance(value, int)]
    if len(valid_sequences) != len(events) or len(set(valid_sequences)) != len(valid_sequences):
        report.fail("decisions.sequence", "事件 sequence 必须是唯一整数", "decision-log.json")
    elif valid_sequences != sorted(valid_sequences):
        report.warn("decisions.sequence_order", "事件没有按 sequence 排列", "decision-log.json")
    for event in events:
        if not isinstance(event, dict) or not str(event.get("summary", "")).strip():
            report.fail("decisions.summary", "存在缺少 summary 的事件", "decision-log.json")
            continue
        evidence = event.get("evidence")
        if not isinstance(evidence, list) or not evidence or any(not str(item or "").strip() for item in evidence):
            report.fail("decisions.evidence", f"事件 {event.get('id')} 缺少可追溯证据", "decision-log.json")


def check_prompt(project: Path, requirements: Dict[str, Any], report: Report) -> Optional[str]:
    prompt = requirements.get("canonical_prompt", {})
    if not isinstance(prompt, dict) or not prompt.get("required", False):
        report.warn("prompt.not_required", "项目没有要求完整提示词；请确认这不是误设", "content-requirements.json")
        return None
    relative = prompt.get("path")
    if not relative:
        report.fail("prompt.path", "缺少 canonical prompt 路径", "content-requirements.json")
        return None
    path = resolve(project, relative)
    if not path.is_file():
        report.fail("prompt.missing", "完整提示词真源不存在", relative)
        return None
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        report.fail("prompt.encoding", f"完整提示词不是 UTF-8：{exc}", relative)
        return None
    actual_hash = hashlib.sha256(raw).hexdigest()
    if actual_hash != prompt.get("sha256"):
        report.fail("prompt.sha256", f"SHA-256 不一致：实际 {actual_hash}", relative)
    else:
        report.ok("prompt.sha256", "完整提示词 SHA-256 一致", relative)
    if len(raw) != prompt.get("bytes"):
        report.fail("prompt.bytes", f"字节数不一致：实际 {len(raw)}", relative)
    if len(text) != prompt.get("characters"):
        report.fail("prompt.characters", f"字符数不一致：实际 {len(text)}", relative)
    first, last = meaningful_lines(text)
    if first != prompt.get("first_line"):
        report.fail("prompt.first_line", f"首个非空行不一致：{first}", relative)
    if last != prompt.get("last_line"):
        report.fail("prompt.last_line", f"最后非空行不一致：{last}", relative)
    for anchor in prompt.get("anchors", []):
        if anchor not in text:
            report.fail("prompt.anchor", f"缺少关键锚点：{anchor}", relative)
        else:
            report.ok("prompt.anchor", f"关键锚点存在：{anchor}", relative)
    return text


def check_prompt_delivery_context(
    project: Path,
    requirements: Dict[str, Any],
    report: Report,
) -> Dict[str, Any]:
    context = requirements.get("prompt_delivery_context")
    if not isinstance(context, dict):
        if requirements.get("schema_version") in {"1.2", "1.3"}:
            report.fail(
                "prompt_delivery.context_missing",
                "1.2 及以上内容项目必须记录内容来源、提示词阈值、现成公开载体和外部托管授权",
                "content-requirements.json",
            )
        return {}

    urls = context.get("existing_public_urls", [])
    if not isinstance(urls, list):
        urls = []
    for url in urls:
        if not is_http_url(url):
            report.fail("prompt_delivery.existing_url", "现成公开载体不是 HTTP(S) 链接", "content-requirements.json")
    if not has_resolvable_evidence(project, context.get("decision_evidence")):
        report.fail(
            "prompt_delivery.decision_evidence",
            "提示词载体决定缺少可解析证据",
            "content-requirements.json",
        )
    else:
        report.ok("prompt_delivery.context", "提示词载体上下文和决定证据已记录", "content-requirements.json")

    if requirements.get("schema_version") == "1.3":
        confirmation = context.get("carrier_confirmation")
        if not isinstance(confirmation, dict):
            report.fail(
                "prompt_delivery.carrier_confirmation_missing",
                "1.3 内容项目必须在自动检测后记录人工确认结果",
                "content-requirements.json",
            )
            return context
        status = confirmation.get("status")
        if status == "pending":
            report.fail(
                "prompt_delivery.carrier_confirmation_pending",
                "仓库检测结果尚未经过人工确认；不能据此使用或放弃 GitHub 链接",
                "content-requirements.json",
            )
            return context
        if not has_resolvable_evidence(project, confirmation.get("evidence")):
            report.fail(
                "prompt_delivery.carrier_confirmation_evidence",
                "仓库使用决定缺少可解析的人工确认记录",
                "content-requirements.json",
            )
        if not valid_iso_datetime(confirmation.get("confirmed_at")):
            report.fail(
                "prompt_delivery.carrier_confirmation_time",
                "仓库使用决定缺少有效确认时间",
                "content-requirements.json",
            )

        origin = context.get("content_origin")
        urls = context.get("existing_public_urls", []) if isinstance(context.get("existing_public_urls"), list) else []
        confirmed_url = confirmation.get("confirmed_url")
        repository = confirmation.get("repository")
        if status == "confirmed_existing":
            if not confirmation.get("candidate_id"):
                report.fail("prompt_delivery.carrier_candidate_id", "人工确认缺少检测候选编号", "content-requirements.json")
            if not is_http_url(confirmed_url) or confirmed_url not in urls:
                report.fail(
                    "prompt_delivery.carrier_confirmed_url",
                    "人工确认的提示词直达链接必须进入 existing_public_urls",
                    "content-requirements.json",
                )
            if not isinstance(repository, dict):
                report.fail("prompt_delivery.carrier_repository", "人工确认缺少 GitHub 仓库证据", "content-requirements.json")
            else:
                canonical = requirements.get("canonical_prompt")
                canonical_sha256 = canonical.get("sha256") if isinstance(canonical, dict) else None
                if repository.get("prompt_sha256") != canonical_sha256:
                    report.fail(
                        "prompt_delivery.carrier_prompt_sha256",
                        "确认仓库中的提示词哈希与当前 canonical prompt 不一致",
                        "content-requirements.json",
                    )
                else:
                    report.ok("prompt_delivery.carrier_confirmed", "GitHub 提示词载体已检测并经人工确认", "content-requirements.json")
        elif status == "confirmed_none":
            if origin == "existing_project" and not confirmation.get("candidate_id"):
                report.fail(
                    "prompt_delivery.carrier_candidate_id",
                    "现有项目确认不使用仓库载体时也必须绑定刚刚展示的检测候选编号",
                    "content-requirements.json",
                )
            github_urls = [url for url in urls if isinstance(url, str) and GITHUB_PROMPT_URL.match(url)]
            if github_urls or confirmed_url is not None or repository is not None:
                report.fail(
                    "prompt_delivery.carrier_none_conflict",
                    "已确认本篇不使用 GitHub 载体，但仍残留 GitHub 提示词链接或仓库证据",
                    "content-requirements.json",
                )
            else:
                report.ok("prompt_delivery.carrier_none_confirmed", "已人工确认本篇不使用 GitHub 载体", "content-requirements.json")
        else:
            report.fail(
                "prompt_delivery.carrier_confirmation_status",
                f"未知的仓库人工确认状态：{status}",
                "content-requirements.json",
            )
    return context


def check_deliverables(
    project: Path,
    requirements: Dict[str, Any],
    prompt_text: Optional[str],
    delivery_context: Dict[str, Any],
    report: Report,
) -> None:
    deliverables = requirements.get("deliverables", [])
    if not isinstance(deliverables, list):
        report.fail("deliverables.type", "deliverables 必须是数组", "content-requirements.json")
        return
    for item in deliverables:
        if not isinstance(item, dict):
            report.fail("deliverables.item", "deliverable 必须是对象", "content-requirements.json")
            continue
        relative = item.get("path")
        if not relative:
            report.fail("deliverables.path", "deliverable 缺少路径", "content-requirements.json")
            continue
        path = resolve(project, relative)
        if not path.is_file():
            severity = report.fail if item.get("required") else report.warn
            severity("deliverables.missing", "交付文件不存在", relative)
            continue
        report.ok("deliverables.exists", "交付文件存在", relative)
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            report.fail("deliverables.encoding", "文本交付物无法按 UTF-8 读取", relative)
            continue
        for pattern, label in PUBLIC_PATH_PATTERNS:
            match = pattern.search(text)
            if match:
                report.fail("deliverables.local_path", f"公开稿包含 {label}：{match.group(0)}", relative)
        if item.get("prompt_delivery") == "full_text" and prompt_text is not None:
            if normalized(prompt_text) not in normalized(text):
                report.fail("deliverables.prompt_incomplete", "要求全文交付，但没有逐字包含 canonical prompt", relative)
            else:
                report.ok("deliverables.prompt_complete", "已逐字包含完整提示词", relative)
        if item.get("prompt_delivery") == "accessible_link":
            access_url = item.get("prompt_access_url")
            if not is_http_url(access_url):
                report.fail(
                    "prompt_delivery.access_url",
                    "可访问链接交付必须填写直接定位完整提示词的 HTTP(S) 链接",
                    "content-requirements.json",
                )
                continue
            existing_urls = {
                str(value).strip() for value in delivery_context.get("existing_public_urls", [])
                if is_http_url(value)
            }
            if access_url not in existing_urls and not delivery_context.get("external_hosting_authorized", False):
                report.fail(
                    "prompt_delivery.external_hosting_authorization",
                    "提示词链接不属于已记录的现成公开载体，且没有新建外部载体授权",
                    "content-requirements.json",
                )
            else:
                report.ok("prompt_delivery.accessible_link", "完整提示词使用已确认的直接链接交付", access_url)


def _platform_key(value: Any) -> str:
    return str(value or "").strip().casefold()


def _editorial_severity(report: Report):
    return report.fail if report.strict or any(action in IRREVERSIBLE_ACTIONS for action in report.actions) else report.warn


def check_editorial_policy(
    project: Path,
    requirements: Dict[str, Any],
    policy: Optional[Dict[str, Any]],
    policy_path: Optional[Path],
    report: Report,
) -> Tuple[Optional[str], Dict[str, Dict[str, Any]]]:
    severity = _editorial_severity(report)
    if policy is None or policy_path is None:
        severity("editorial.policy_missing", "缺少读者语言与平台风格策略；运行 editorial-init 后补全", "project-manifest.json")
        return None, {}
    if policy.get("project_id") != report.project_id:
        report.fail("editorial.project_id", "editorial-policy 的 project_id 不一致", policy_path.name)
    policy_digest = sha256(policy_path)
    author = policy.get("author_voice", {}) if isinstance(policy.get("author_voice"), dict) else {}
    if author.get("status") != "verified":
        severity("editorial.author_voice", "个人表达档案尚未验证", policy_path.name)
    else:
        profile = author.get("profile", {}) if isinstance(author.get("profile"), dict) else {}
        required_profile_fields = ("point_of_view", "sentence_rhythm", "preferred_vocabulary", "stance_markers", "avoid")
        empty = [field for field in required_profile_fields if not profile.get(field)]
        if empty:
            report.fail("editorial.author_profile", f"已验证的个人表达档案仍缺少：{', '.join(empty)}", policy_path.name)
        if not has_resolvable_evidence(project, author.get("evidence")):
            report.fail("editorial.author_evidence", "个人表达档案缺少可解析证据", policy_path.name)
        samples = author.get("sample_paths", []) if isinstance(author.get("sample_paths"), list) else []
        mode = author.get("mode")
        minimum = 3 if mode == "writing_samples" else 1 if mode == "approved_content" else 0
        if len(samples) < minimum:
            report.fail("editorial.author_samples", f"{mode} 模式至少需要 {minimum} 个样本", policy_path.name)
        if mode == "writing_samples" and len(samples) > 5:
            report.warn("editorial.author_samples", "个人表达校准建议只使用 3–5 个明确认可的代表样本", policy_path.name)
        for relative in samples:
            if not resolve(project, relative).is_file():
                report.fail("editorial.author_sample_missing", "个人表达样本不存在", relative)
        if not any(issue["code"].startswith("editorial.author_") and issue["severity"] == "error" for issue in report.issues):
            report.ok("editorial.author_verified", "个人表达档案和证据已验证", policy_path.name)

    profiles = policy.get("platform_profiles", []) if isinstance(policy.get("platform_profiles"), list) else []
    profile_ids = [item.get("id") for item in profiles if isinstance(item, dict)]
    if len(profile_ids) != len(set(profile_ids)):
        report.fail("editorial.profile_id", "平台档案 id 必须唯一", policy_path.name)
    aliases: Dict[str, Dict[str, Any]] = {}
    for profile in profiles:
        if not isinstance(profile, dict):
            continue
        names = [profile.get("platform"), *profile.get("aliases", [])]
        for name in names:
            key = _platform_key(name)
            if not key:
                continue
            if key in aliases and aliases[key].get("id") != profile.get("id"):
                report.fail("editorial.profile_alias", f"平台别名重复：{name}", policy_path.name)
            aliases[key] = profile

    delivery_compatibility = {
        "full_text": {"full_text"},
        "prompt_cards": {"prompt_cards"},
        "accessible_link": {"accessible_link"},
        "prompt_cards_or_accessible_link": {"prompt_cards", "accessible_link"},
        "adaptive": {"full_text", "prompt_cards", "accessible_link"},
    }
    for deliverable in requirements.get("deliverables", []):
        if not isinstance(deliverable, dict) or not deliverable.get("platform"):
            continue
        platform = deliverable.get("platform")
        profile = aliases.get(_platform_key(platform))
        if profile is None:
            severity("editorial.platform_profile", f"{platform} 没有独立平台风格档案", policy_path.name)
            continue
        expected = delivery_compatibility.get(profile.get("prompt_delivery"), set())
        if deliverable.get("prompt_delivery") not in expected and deliverable.get("prompt_delivery") != "not_required":
            report.fail(
                "editorial.prompt_delivery",
                f"{platform} 的交付方式 {deliverable.get('prompt_delivery')} 与平台档案 {profile.get('prompt_delivery')} 不一致",
                policy_path.name,
            )
        else:
            report.ok("editorial.platform_profile", f"{platform} 已绑定平台档案 {profile.get('id')}", policy_path.name)
    return policy_digest, aliases


def check_editorial_reviews(
    project: Path,
    requirements: Dict[str, Any],
    reviews_data: Optional[Dict[str, Any]],
    reviews_path: Optional[Path],
    policy: Optional[Dict[str, Any]],
    policy_digest: Optional[str],
    profiles: Dict[str, Dict[str, Any]],
    report: Report,
) -> None:
    severity = _editorial_severity(report)
    if reviews_data is None or reviews_path is None:
        severity("editorial.reviews_missing", "缺少逐交付物的读者语言与平台风格审校记录", "project-manifest.json")
        return
    if reviews_data.get("project_id") != report.project_id:
        report.fail("editorial.review_project_id", "editorial-reviews 的 project_id 不一致", reviews_path.name)
    reviews = reviews_data.get("reviews", []) if isinstance(reviews_data.get("reviews"), list) else []
    review_ids = [item.get("id") for item in reviews if isinstance(item, dict)]
    if len(review_ids) != len(reviews) or any(not value for value in review_ids) or len(set(review_ids)) != len(review_ids):
        report.fail("editorial.review_id", "审校记录 id 必须非空且唯一", reviews_path.name)
    by_deliverable: Dict[str, List[Dict[str, Any]]] = {}
    for item in reviews:
        if isinstance(item, dict):
            by_deliverable.setdefault(str(item.get("deliverable_id") or ""), []).append(item)

    rules = policy.get("quality_rules", {}) if isinstance(policy, dict) and isinstance(policy.get("quality_rules"), dict) else {}
    threshold = rules.get("structural_rewrite_threshold", {}) if isinstance(rules.get("structural_rewrite_threshold"), dict) else {}
    minimum_hits = int(threshold.get("minimum_pattern_hits", 5))
    minimum_categories = int(threshold.get("minimum_category_hits", 3))
    require_uniform = bool(threshold.get("require_uniform_structure", True))
    text_kinds = {"master", "longform", "social", "video_script"}
    for deliverable in requirements.get("deliverables", []):
        if not isinstance(deliverable, dict) or not deliverable.get("required") or deliverable.get("kind") not in text_kinds:
            continue
        deliverable_id = str(deliverable.get("id") or "")
        matches = by_deliverable.get(deliverable_id, [])
        if not matches:
            severity("editorial.review_missing", f"必需交付物 {deliverable_id} 没有审校记录", reviews_path.name)
            continue
        if len(matches) != 1:
            report.fail("editorial.review_duplicate", f"交付物 {deliverable_id} 必须且只能有一条当前审校记录", reviews_path.name)
            continue
        review = matches[0]
        issue_start = len(report.issues)
        relative = deliverable.get("path")
        content_path = resolve(project, relative) if relative else Path("__missing__")
        if review.get("status") != "verified":
            severity("editorial.review_status", f"交付物 {deliverable_id} 的审校状态不是 verified", reviews_path.name)
        if not valid_iso_datetime(review.get("reviewed_at")) or not str(review.get("reviewer") or "").strip():
            report.fail("editorial.review_identity", f"交付物 {deliverable_id} 缺少审校时间或审校者", reviews_path.name)
        if content_path.is_file() and review.get("content_sha256") != sha256(content_path):
            report.fail("editorial.review_content", f"交付物 {deliverable_id} 已在审校后变化", relative)
        if policy_digest is None or review.get("policy_sha256") != policy_digest:
            report.fail("editorial.review_policy", f"交付物 {deliverable_id} 没有绑定当前 editorial policy", reviews_path.name)
        if not has_resolvable_evidence(project, review.get("evidence")):
            report.fail("editorial.review_evidence", f"交付物 {deliverable_id} 缺少可解析审校证据", reviews_path.name)

        platform = deliverable.get("platform")
        if _platform_key(review.get("platform")) != _platform_key(platform):
            report.fail("editorial.review_platform", f"交付物 {deliverable_id} 的审校平台与交付物不一致", reviews_path.name)
        profile = profiles.get(_platform_key(platform)) if platform else None
        if platform:
            if profile is None or review.get("profile_id") != profile.get("id") or review.get("profile_version") != profile.get("version"):
                report.fail("editorial.review_profile", f"交付物 {deliverable_id} 没有绑定当前平台档案", reviews_path.name)
        elif review.get("profile_id") is not None or review.get("profile_version") is not None:
            report.fail("editorial.review_profile", f"非平台母稿 {deliverable_id} 不应绑定平台档案", reviews_path.name)

        checks = review.get("checks", {}) if isinstance(review.get("checks"), dict) else {}
        for check in ("fact_fidelity", "process_completeness", "ai_trace", "author_voice", "medium_fit"):
            if checks.get(check) != "verified":
                severity("editorial.review_check", f"交付物 {deliverable_id} 的 {check} 未通过", reviews_path.name)
        expected_prompt = "not_applicable" if deliverable.get("prompt_delivery") == "not_required" else "verified"
        if checks.get("prompt_integrity") != expected_prompt:
            severity("editorial.review_check", f"交付物 {deliverable_id} 的 prompt_integrity 应为 {expected_prompt}", reviews_path.name)
        expected_platform = "verified" if platform else "not_applicable"
        if checks.get("platform_fit") != expected_platform:
            severity("editorial.review_check", f"交付物 {deliverable_id} 的 platform_fit 应为 {expected_platform}", reviews_path.name)

        audit = review.get("ai_audit", {}) if isinstance(review.get("ai_audit"), dict) else {}
        threshold_hit = (
            int(audit.get("pattern_hits", 0)) >= minimum_hits
            and int(audit.get("category_hits", 0)) >= minimum_categories
            and (not require_uniform or bool(audit.get("uniform_structure")))
        )
        if threshold_hit and review.get("rewrite_mode") != "structural":
            report.fail("editorial.rewrite_mode", f"交付物 {deliverable_id} 已达到结构重写阈值，不能只做词语修补", reviews_path.name)
        if not any(issue["severity"] in {"warning", "error"} for issue in report.issues[issue_start:]):
            report.ok("editorial.review_verified", f"交付物 {deliverable_id} 的审校记录有效", reviews_path.name)


def check_platform_differentiation(
    project: Path,
    requirements: Dict[str, Any],
    prompt_text: Optional[str],
    report: Report,
) -> None:
    rows: List[Tuple[str, str, str]] = []
    prompt = normalized(prompt_text) if prompt_text else ""
    for deliverable in requirements.get("deliverables", []):
        if not isinstance(deliverable, dict) or not deliverable.get("required") or not deliverable.get("platform"):
            continue
        if deliverable.get("kind") not in {"longform", "social", "video_script", "master"}:
            continue
        relative = deliverable.get("path")
        path = resolve(project, relative) if relative else Path("__missing__")
        if not path.is_file():
            continue
        try:
            text = normalized(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError):
            continue
        if prompt:
            text = text.replace(prompt, "")
        comparison = re.sub(r"[\W_]+", "", text, flags=re.UNICODE).casefold()
        if comparison:
            rows.append((str(deliverable.get("platform")), str(deliverable.get("id")), comparison))
    severity = _editorial_severity(report)
    for index, (platform_a, id_a, text_a) in enumerate(rows):
        for platform_b, id_b, text_b in rows[index + 1:]:
            if _platform_key(platform_a) == _platform_key(platform_b):
                continue
            ratio = SequenceMatcher(None, text_a, text_b, autojunk=False).ratio()
            if ratio >= 0.92:
                severity(
                    "editorial.platform_similarity",
                    f"平台稿 {id_a}/{platform_a} 与 {id_b}/{platform_b} 去除完整提示词后仍有 {ratio:.0%} 相似度，疑似机械复制",
                    "content-requirements.json",
                )
            else:
                report.ok(
                    "editorial.platform_differentiated",
                    f"平台稿 {id_a}/{platform_a} 与 {id_b}/{platform_b} 已形成结构差异（相似度 {ratio:.0%}）",
                    "content-requirements.json",
                )


def check_story_coverage(
    project: Path,
    manifest: Dict[str, Any],
    requirements: Dict[str, Any],
    decisions: Optional[Dict[str, Any]],
    report: Report,
) -> None:
    files = manifest.get("files", {}) if isinstance(manifest.get("files"), dict) else {}
    master_relative = files.get("master_content")
    master_path = resolve(project, master_relative) if master_relative else Path("__missing__")
    if not master_path.is_file():
        report.fail("story.master", "母稿真源不存在", master_relative or "project-manifest.json")
        return
    try:
        master_text = master_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        report.fail("story.master", "母稿无法按 UTF-8 读取", master_relative)
        return

    coverage = requirements.get("story_coverage")
    if not isinstance(coverage, list):
        report.fail("story.coverage", "story_coverage 必须是数组", "content-requirements.json")
        return
    stage_counts: Dict[str, int] = {}
    events = decisions.get("events", []) if isinstance(decisions, dict) else []
    event_map = {item.get("id"): item for item in events if isinstance(item, dict)}
    for item in coverage:
        if not isinstance(item, dict):
            report.fail("story.coverage", "story_coverage 项必须是对象", "content-requirements.json")
            continue
        stage = item.get("stage")
        stage_counts[stage] = stage_counts.get(stage, 0) + 1
        anchors = item.get("master_anchors", [])
        for anchor in anchors if isinstance(anchors, list) else []:
            if anchor not in master_text:
                report.fail("story.anchor", f"母稿缺少 {stage} 锚点：{anchor}", master_relative)
            else:
                report.ok("story.anchor", f"母稿包含 {stage} 锚点：{anchor}", master_relative)
        references = item.get("decision_event_ids", [])
        for event_id in references if isinstance(references, list) else []:
            event = event_map.get(event_id)
            if not event:
                report.fail("story.event_ref", f"{stage} 引用了不存在的事件：{event_id}", "content-requirements.json")
            elif event.get("stage") != stage:
                report.fail("story.event_stage", f"事件 {event_id} 的阶段不是 {stage}", "content-requirements.json")
    for stage in REQUIRED_STAGES:
        if stage_counts.get(stage) != 1:
            report.fail("story.stage_coverage", f"story_coverage 必须且只能覆盖一次：{stage}", "content-requirements.json")


def check_prompt_card_sets(
    project: Path,
    requirements: Dict[str, Any],
    prompt_text: Optional[str],
    delivery_context: Dict[str, Any],
    report: Report,
) -> None:
    prompt = requirements.get("canonical_prompt", {}) if isinstance(requirements.get("canonical_prompt"), dict) else {}
    sets = requirements.get("prompt_card_sets")
    if not isinstance(sets, list):
        report.fail("prompt_cards.type", "prompt_card_sets 必须是数组", "content-requirements.json")
        return
    by_platform = {item.get("platform"): item for item in sets if isinstance(item, dict)}
    image_paths = {
        item.get("path") for item in requirements.get("media", {}).get("images", [])
        if isinstance(item, dict)
    }
    for deliverable in requirements.get("deliverables", []):
        if not isinstance(deliverable, dict) or deliverable.get("prompt_delivery") != "prompt_cards":
            continue
        platform = deliverable.get("platform")
        card_set = by_platform.get(platform)
        if not card_set:
            report.fail("prompt_cards.missing_set", f"{platform} 要求提示词图片，但没有对应 card set", "content-requirements.json")
            continue
        pages = card_set.get("pages", [])
        total = card_set.get("total_pages")
        maximum_pages = delivery_context.get("max_prompt_card_pages")
        maximum_characters = delivery_context.get("short_prompt_max_characters")
        if isinstance(maximum_pages, int) and isinstance(total, int) and total > maximum_pages:
            report.fail(
                "prompt_cards.page_limit",
                f"{platform} 提示词图片共 {total} 页，超过项目上限 {maximum_pages} 页；改用正文全文或已确认的直接链接",
                "content-requirements.json",
            )
        if isinstance(maximum_characters, int) and prompt_text is not None and len(prompt_text) > maximum_characters:
            report.fail(
                "prompt_cards.prompt_too_long",
                f"{platform} 提示词共 {len(prompt_text)} 字符，超过图片交付阈值 {maximum_characters}；改用正文全文或已确认的直接链接",
                "content-requirements.json",
            )
        page_numbers = [item.get("page") for item in pages if isinstance(item, dict)]
        if not isinstance(total, int) or page_numbers != list(range(1, total + 1)):
            report.fail("prompt_cards.sequence", f"{platform} 提示词图片页码不连续或总页数不一致", "content-requirements.json")
        if card_set.get("canonical_prompt_sha256") != prompt.get("sha256"):
            report.fail("prompt_cards.sha256", f"{platform} 提示词图片没有绑定当前 canonical prompt", "content-requirements.json")
        if card_set.get("first_line") != prompt.get("first_line") or card_set.get("last_line") != prompt.get("last_line"):
            report.fail("prompt_cards.boundary", f"{platform} 提示词图片首尾锚点与真源不一致", "content-requirements.json")
        if card_set.get("verification_status") != "verified" or not card_set.get("verification_evidence"):
            report.fail("prompt_cards.verification", f"{platform} 提示词图片尚无完整性验证证据", "content-requirements.json")
        elif not has_resolvable_evidence(project, card_set.get("verification_evidence")):
            report.fail("prompt_cards.evidence", f"{platform} 提示词图片证据没有可解析文件或 URL", "content-requirements.json")
        for page in pages:
            if not isinstance(page, dict):
                continue
            image_path = page.get("image_path")
            if image_path not in image_paths:
                report.fail("prompt_cards.image_manifest", f"提示词图片未进入媒体清单：{image_path}", "content-requirements.json")
            elif not resolve(project, image_path).is_file():
                report.fail("prompt_cards.image_missing", "提示词图片文件不存在", image_path)
            elif sha256(resolve(project, image_path)) != page.get("image_sha256"):
                report.fail("prompt_cards.image_sha256", "提示词图片已变化，与已验收文件不一致", image_path)
            else:
                report.ok("prompt_cards.image_sha256", "提示词图片 SHA-256 与验收记录一致", image_path)
            expected_token = f"-{int(page.get('page', 0)):02d}-of-{int(total or 0):02d}"
            if expected_token not in Path(str(image_path)).stem:
                report.fail("prompt_cards.filename", f"提示词图片文件名缺少页码标记 {expected_token}", image_path)


def check_media(project: Path, requirements: Dict[str, Any], report: Report) -> None:
    media = requirements.get("media", {})
    images = media.get("images", []) if isinstance(media, dict) else []
    for image in images:
        relative = image.get("path")
        path = resolve(project, relative) if relative else Path("__missing__")
        if not relative or not path.is_file():
            severity = report.fail if image.get("required") else report.warn
            severity("images.missing", "图片文件不存在", relative or "content-requirements.json")
            continue
        dimensions = image_dimensions(path)
        expected = (image.get("width"), image.get("height"))
        if dimensions is None:
            report.warn("images.dimensions_unknown", "无法读取图片尺寸，需要人工检查", relative)
        elif all(isinstance(value, int) for value in expected) and dimensions != expected:
            report.fail("images.dimensions", f"图片尺寸 {dimensions[0]}×{dimensions[1]}，预期 {expected[0]}×{expected[1]}", relative)
        else:
            report.ok("images.verified", f"图片存在，尺寸 {dimensions[0]}×{dimensions[1]}", relative)
        if image.get("privacy") != "verified":
            report.warn("images.privacy", "图片隐私检查尚未标记 verified", relative)
    videos = media.get("videos", []) if isinstance(media, dict) else []
    for video in videos:
        relative = video.get("path")
        path = resolve(project, relative) if relative else Path("__missing__")
        if not relative or not path.is_file():
            severity = report.fail if video.get("required") else report.warn
            severity("videos.missing", "视频文件不存在", relative or "content-requirements.json")
            continue
        if video.get("project_verification") != "verified":
            report.warn("videos.project_verification", "视频工程级验收尚未 verified", relative)
        elif not video.get("project_evidence"):
            report.fail("videos.project_evidence", "视频工程级验收标记 verified 但没有证据", relative)
        elif not has_resolvable_evidence(project, video.get("project_evidence")):
            report.fail("videos.project_evidence", "视频工程级验收证据无法解析", relative)
        if video.get("file_verification") != "verified":
            report.warn("videos.file_verification", "视频导出文件级验收尚未 verified", relative)
        elif not video.get("file_evidence"):
            report.fail("videos.file_evidence", "视频文件级验收标记 verified 但没有证据", relative)
        elif not has_resolvable_evidence(project, video.get("file_evidence")):
            report.fail("videos.file_evidence", "视频文件级验收证据无法解析", relative)
        probe = ffprobe(path)
        if probe is None:
            report.warn("videos.ffprobe_unavailable", "ffprobe 不可用，需人工检查最终文件", relative)
            continue
        if probe == {}:
            report.fail("videos.ffprobe_failed", "ffprobe 无法读取视频", relative)
            continue
        streams = probe.get("streams", [])
        video_streams = [stream for stream in streams if stream.get("codec_type") == "video"]
        audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]
        if not video_streams:
            report.fail("videos.video_stream", "导出文件没有视频流", relative)
        if not audio_streams:
            report.fail("videos.audio_stream", "导出文件没有音频流", relative)
        if video_streams and audio_streams:
            report.ok("videos.streams", f"检测到 {len(video_streams)} 个视频流和 {len(audio_streams)} 个音频流", relative)
        try:
            duration = float(probe.get("format", {}).get("duration"))
        except (TypeError, ValueError):
            duration = None
        expected_duration = video.get("expected_duration_seconds")
        tolerance = float(video.get("duration_tolerance_seconds", 1.0))
        if duration is None:
            report.fail("videos.duration", "无法读取视频时长", relative)
        elif expected_duration is not None and abs(duration - float(expected_duration)) > tolerance:
            report.fail("videos.duration", f"视频时长 {duration:.3f}s，预期 {expected_duration}s±{tolerance}s", relative)
        else:
            report.ok("videos.duration", f"视频时长 {duration:.3f}s", relative)


def check_platforms(data: Optional[Dict[str, Any]], project_id: str, report: Report) -> None:
    if not data:
        return
    if data.get("project_id") != project_id:
        report.fail("platforms.project_id", "platform-status 的 project_id 不一致", "platform-status.json")
    platforms = data.get("platforms")
    if not isinstance(platforms, list):
        report.fail("platforms.type", "platforms 必须是数组", "platform-status.json")
        return
    for item in platforms:
        name = item.get("platform", "unknown")
        status = item.get("status")
        public_url = item.get("public_url")
        reader_validation = item.get("reader_validation")
        if status == "published" and not public_url:
            report.fail("platforms.public_url", f"{name} 标记已发布但没有公开链接", "platform-status.json")
        elif public_url and not re.match(r"^https?://", str(public_url), re.IGNORECASE):
            report.fail("platforms.public_url", f"{name} 的公开链接不是 HTTP(S)", "platform-status.json")
        if status == "published" and not valid_iso_datetime(item.get("published_at")):
            report.fail("platforms.published_at", f"{name} 已发布但缺少有效发布时间", "platform-status.json")
        if status == "published" and not item.get("release_digest"):
            message = f"{name} 已发布，但尚不知道线上内容对应哪个 release digest"
            (report.fail if report.postflight else report.warn)("platforms.release_digest", message, "platform-status.json")
        if report.postflight and status == "published" and reader_validation != "verified":
            report.fail("platforms.reader_validation", f"{name} 已发布但读者视角未验证", public_url or "platform-status.json")
        elif status == "published" and reader_validation != "verified":
            report.warn("platforms.reader_validation", f"{name} 的公开读者验收不是 verified", public_url or "platform-status.json")
        if status in ("under_review", "submitted") and reader_validation == "verified":
            report.fail("platforms.state_conflict", f"{name} 尚未公开却标记读者验收 verified", "platform-status.json")
        if reader_validation == "verified" and not item.get("evidence"):
            report.fail("platforms.reader_evidence", f"{name} 标记读者验收 verified 但没有证据", "platform-status.json")
        if item.get("prompt_delivery") == "unknown":
            report.warn("platforms.prompt_delivery", f"{name} 的完整提示词交付方式未知", "platform-status.json")


def check_metrics(
    data: Optional[Dict[str, Any]],
    platforms_data: Optional[Dict[str, Any]],
    project_id: str,
    report: Report,
) -> None:
    if not data:
        return
    if data.get("project_id") != project_id:
        report.fail("metrics.project_id", "metrics 的 project_id 不一致", "metrics.json")

    collection_plan = data.get("collection_plan")
    checkpoint_map: Dict[str, Dict[str, Any]] = {}
    due_checkpoint_ids: List[str] = []
    if not isinstance(collection_plan, dict):
        report.warn("metrics.collection_plan", "缺少 collection_plan，无法判断采集检查点", "metrics.json")
    else:
        checkpoints = collection_plan.get("checkpoints")
        if not isinstance(checkpoints, list) or not checkpoints:
            report.warn("metrics.checkpoints", "collection_plan 没有配置采集检查点", "metrics.json")
        else:
            checkpoint_ids = [item.get("id") for item in checkpoints if isinstance(item, dict)]
            if len(checkpoint_ids) != len(checkpoints) or any(not str(item or "").strip() for item in checkpoint_ids):
                report.fail("metrics.checkpoints", "每个采集检查点都必须有 id", "metrics.json")
            elif len(set(checkpoint_ids)) != len(checkpoint_ids):
                report.fail("metrics.checkpoints", "采集检查点 id 必须唯一", "metrics.json")
            else:
                report.ok("metrics.checkpoints", f"已配置 {len(checkpoints)} 个采集检查点", "metrics.json")
                checkpoint_map = {item["id"]: item for item in checkpoints}
                now = datetime.now(timezone.utc)
                for checkpoint in checkpoints:
                    if not checkpoint.get("required"):
                        continue
                    due_at = checkpoint.get("due_at")
                    if not valid_iso_datetime(due_at):
                        message = f"必填检查点 {checkpoint['id']} 没有有效 due_at"
                        (report.fail if report.require_metrics else report.warn)("metrics.checkpoint_due", message, "metrics.json")
                        continue
                    parsed_due = datetime.fromisoformat(str(due_at).replace("Z", "+00:00"))
                    if parsed_due.tzinfo is None:
                        parsed_due = parsed_due.replace(tzinfo=timezone.utc)
                    if parsed_due <= now:
                        due_checkpoint_ids.append(checkpoint["id"])

    snapshots = data.get("snapshots")
    if not isinstance(snapshots, list):
        report.fail("metrics.snapshots", "snapshots 必须是数组", "metrics.json")
        return

    platform_items = platforms_data.get("platforms", []) if isinstance(platforms_data, dict) else []
    known_platforms = {
        item.get("platform") for item in platform_items
        if isinstance(item, dict) and str(item.get("platform", "")).strip()
    }
    published_platforms = {
        item.get("platform") for item in platform_items
        if isinstance(item, dict) and item.get("status") == "published"
    }
    latest: Dict[str, Tuple[str, int, Dict[str, Any]]] = {}
    latest_by_checkpoint: Dict[Tuple[str, str], Tuple[str, int, Dict[str, Any]]] = {}
    snapshot_ids: List[str] = []

    for index, snapshot in enumerate(snapshots):
        path = f"metrics.json#snapshots[{index}]"
        if not isinstance(snapshot, dict):
            report.fail("metrics.snapshot", "指标快照必须是对象", path)
            continue
        platform = snapshot.get("platform")
        if not isinstance(platform, str) or not platform.strip():
            report.fail("metrics.platform", "指标快照缺少 platform", path)
            continue
        if known_platforms and platform not in known_platforms:
            report.fail("metrics.platform", f"指标平台不在 platform-status.json 中：{platform}", path)
        snapshot_id = snapshot.get("id")
        if not isinstance(snapshot_id, str) or not snapshot_id.strip():
            report.fail("metrics.id", f"{platform} 的指标快照缺少 id", path)
        else:
            snapshot_ids.append(snapshot_id)
        checkpoint = snapshot.get("checkpoint")
        if checkpoint not in checkpoint_map:
            report.fail("metrics.checkpoint_ref", f"{platform} 引用了不存在的检查点：{checkpoint}", path)

        status = snapshot.get("collection_status")
        if status not in METRIC_COLLECTION_STATUSES:
            report.fail("metrics.collection_status", f"{platform} 的 collection_status 无效：{status}", path)

        source = snapshot.get("source")
        if source not in METRIC_SOURCES:
            report.fail("metrics.source", f"{platform} 的 source 无效：{source}", path)

        evidence = snapshot.get("evidence")
        if not isinstance(evidence, list):
            report.fail("metrics.evidence", f"{platform} 的 evidence 必须是数组", path)
            evidence = []

        values = snapshot.get("values")
        if not isinstance(values, dict):
            report.fail("metrics.values", f"{platform} 的 values 必须是对象", path)
            values = {}

        known_values = 0
        for field in METRIC_FIELDS:
            if field not in values:
                report.fail("metrics.field_missing", f"{platform} 缺少指标字段：{field}", path)
                continue
            value = values.get(field)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, int):
                report.fail("metrics.value_type", f"{platform}.{field} 必须是整数或 null", path)
                continue
            if field != "follower_change" and value < 0:
                report.fail("metrics.value_range", f"{platform}.{field} 不能是负数", path)
                continue
            known_values += 1

        captured_at = snapshot.get("captured_at")
        attempted_at = snapshot.get("attempted_at")
        if captured_at is not None and not valid_iso_datetime(captured_at):
            report.fail("metrics.captured_at", f"{platform} 的 captured_at 不是有效 ISO 时间", path)
        if attempted_at is not None and not valid_iso_datetime(attempted_at):
            report.fail("metrics.attempted_at", f"{platform} 的 attempted_at 不是有效 ISO 时间", path)

        if status == "not_collected":
            if known_values:
                report.fail("metrics.state_conflict", f"{platform} 标记 not_collected 却包含数值", path)
            if source != "unknown":
                report.fail("metrics.state_conflict", f"{platform} 尚未采集时 source 必须是 unknown", path)
        elif status in ("captured", "partial"):
            if not known_values:
                report.fail("metrics.state_conflict", f"{platform} 标记 {status} 却没有任何数值", path)
            if status == "captured" and known_values != len(METRIC_FIELDS):
                report.fail("metrics.captured_incomplete", f"{platform} 标记 captured 但仍有 null；应改为 partial", path)
            if status == "partial" and known_values == len(METRIC_FIELDS):
                report.fail("metrics.partial_complete", f"{platform} 所有指标均已采集，不应标记 partial", path)
            if source == "unknown":
                report.fail("metrics.source", f"{platform} 有指标数值但来源未知", path)
            if not evidence:
                report.fail("metrics.evidence", f"{platform} 有指标数值但没有证据", path)
            if not valid_iso_datetime(captured_at):
                report.fail("metrics.captured_at", f"{platform} 已采集但没有有效 captured_at", path)
        elif status == "unavailable":
            if known_values:
                report.fail("metrics.state_conflict", f"{platform} 标记 unavailable 时数值应保持 null", path)
            if source == "unknown" or not evidence:
                report.fail("metrics.unavailable_evidence", f"{platform} 标记 unavailable 必须记录尝试来源和证据", path)
            if not (valid_iso_datetime(attempted_at) or valid_iso_datetime(captured_at)):
                report.fail("metrics.attempted_at", f"{platform} 标记 unavailable 但没有有效尝试时间", path)
        elif status == "failed":
            if known_values:
                report.fail("metrics.state_conflict", f"{platform} 采集失败时数值应保持 null", path)
            if source == "unknown":
                report.fail("metrics.source", f"{platform} 采集失败但没有记录尝试来源", path)
            if not evidence and not str(snapshot.get("error") or "").strip():
                report.fail("metrics.failure_evidence", f"{platform} 采集失败但没有证据或错误原因", path)
            if not (valid_iso_datetime(attempted_at) or valid_iso_datetime(captured_at)):
                report.fail("metrics.attempted_at", f"{platform} 采集失败但没有有效尝试时间", path)

        sort_key = str(captured_at or attempted_at or "")
        previous = latest.get(platform)
        if previous is None or (sort_key, index) >= (previous[0], previous[1]):
            latest[platform] = (sort_key, index, snapshot)
        checkpoint_key = (platform, str(checkpoint))
        previous_checkpoint = latest_by_checkpoint.get(checkpoint_key)
        if previous_checkpoint is None or (sort_key, index) >= (previous_checkpoint[0], previous_checkpoint[1]):
            latest_by_checkpoint[checkpoint_key] = (sort_key, index, snapshot)

    if len(snapshot_ids) != len(set(snapshot_ids)):
        report.fail("metrics.id", "指标快照 id 必须唯一", "metrics.json")

    for platform in sorted(published_platforms):
        if report.require_metrics:
            for checkpoint_id in due_checkpoint_ids:
                entry = latest_by_checkpoint.get((platform, checkpoint_id))
                if entry is None:
                    report.fail("metrics.checkpoint_missing", f"{platform} 缺少到期检查点 {checkpoint_id} 的快照", "metrics.json")
                    continue
                status = entry[2].get("collection_status")
                if status in METRIC_COMPLETE_STATUSES:
                    report.ok("metrics.checkpoint_complete", f"{platform}/{checkpoint_id} 指标状态为 {status}", "metrics.json")
                else:
                    report.fail("metrics.checkpoint_incomplete", f"{platform}/{checkpoint_id} 指标状态为 {status}", "metrics.json")
        else:
            latest_entry = latest.get(platform)
            if latest_entry is None:
                report.warn("metrics.platform_missing", f"{platform} 已发布但没有指标快照", "metrics.json")
                continue
            status = latest_entry[2].get("collection_status")
            if status in METRIC_COMPLETE_STATUSES:
                report.ok("metrics.platform_complete", f"{platform} 最新指标状态为 {status}", "metrics.json")
            else:
                report.warn("metrics.platform_incomplete", f"{platform} 最新指标状态为 {status}，本轮采集尚未闭环", "metrics.json")


def check_checksums(project: Path, data: Optional[Dict[str, Any]], report: Report) -> None:
    if not data:
        report.warn("checksums.missing", "没有可验证的 checksums.json")
        return
    if data.get("algorithm") != "SHA-256":
        report.fail("checksums.algorithm", "checksums 只接受 SHA-256", "checksums.json")
    files = data.get("files")
    if not isinstance(files, dict):
        report.fail("checksums.files", "checksums.files 必须是对象", "checksums.json")
        return
    for relative, expected in files.items():
        path = resolve(project, relative)
        if not path.is_file():
            report.fail("checksums.file_missing", "校验清单中的文件不存在", relative)
            continue
        actual = sha256(path)
        if actual != expected:
            report.fail("checksums.mismatch", f"SHA-256 不一致：实际 {actual}", relative)
        else:
            report.ok("checksums.verified", "SHA-256 一致", relative)


def check_release(
    project: Path,
    manifest: Dict[str, Any],
    requirements: Optional[Dict[str, Any]],
    decisions: Optional[Dict[str, Any]],
    report: Report,
) -> Optional[str]:
    if not isinstance(requirements, dict):
        report.fail("release.requirements", "无法在缺少 content-requirements 时计算发布摘要", "project-manifest.json")
        return None
    actual = compute_release_digest(project, manifest, requirements)
    report.release_digest = actual
    release = manifest.get("release")
    if not isinstance(release, dict):
        report.fail("release.missing", "manifest 缺少 release 对象", "project-manifest.json")
        return actual

    status = release.get("status")
    if status != "frozen":
        message = f"当前内容版本状态为 {status}，不可执行不可逆动作"
        if any(action in IRREVERSIBLE_ACTIONS for action in report.actions):
            report.fail("release.not_frozen", message, "project-manifest.json")
        else:
            report.warn("release.not_frozen", message, "project-manifest.json")
        return actual

    if release.get("release_digest") != actual:
        report.fail("release.digest", f"冻结摘要已失效；当前应为 {actual}", "project-manifest.json")
    else:
        report.ok("release.digest", "冻结摘要与当前全部发布内容一致", "project-manifest.json")
    if not valid_iso_datetime(release.get("frozen_at")):
        report.fail("release.frozen_at", "冻结版本缺少有效 frozen_at", "project-manifest.json")

    events = decisions.get("events", []) if isinstance(decisions, dict) else []
    sequences = [item.get("sequence") for item in events if isinstance(item, dict) and isinstance(item.get("sequence"), int)]
    latest_sequence = max(sequences) if sequences else None
    if release.get("decision_sequence") != latest_sequence:
        report.fail(
            "release.decision_sequence",
            f"冻结版本没有绑定最新决策序号；记录 {release.get('decision_sequence')}，实际 {latest_sequence}",
            "project-manifest.json",
        )
    else:
        report.ok("release.decision_sequence", f"冻结版本已绑定最新决策序号 {latest_sequence}", "project-manifest.json")
    return actual


def check_authorization(
    manifest: Dict[str, Any],
    release_digest: Optional[str],
    known_platforms: Sequence[str],
    report: Report,
) -> None:
    authorization = manifest.get("authorization", {})
    grants = authorization.get("grants", []) if isinstance(authorization, dict) else []
    if not isinstance(grants, list):
        report.fail("authorization.grants", "authorization.grants 必须是数组", "project-manifest.json")
        return
    grant_ids = [item.get("id") for item in grants if isinstance(item, dict)]
    if len(grant_ids) != len(grants) or len(set(grant_ids)) != len(grant_ids):
        report.fail("authorization.grant_id", "授权 grant id 必须非空且唯一", "project-manifest.json")

    now = datetime.now(timezone.utc)
    expected_approval = {
        "public_publish": "content_and_platforms_confirmed",
        "update_publication": "content_and_platforms_confirmed",
        "delete_publication": "destructive_action_confirmed",
        "external_sync": "external_sync_confirmed",
    }
    for grant in grants:
        if not isinstance(grant, dict):
            continue
        granted_at = parse_iso_datetime(grant.get("granted_at"))
        expires_at = parse_iso_datetime(grant.get("expires_at"))
        if granted_at is not None and expires_at is not None and expires_at <= granted_at:
            report.fail("authorization.time_range", f"授权 {grant.get('id')} 的 expires_at 必须晚于 granted_at", "project-manifest.json")
        if grant.get("status") == "active" and expires_at is not None and expires_at <= now:
            report.fail("authorization.expired_active", f"授权 {grant.get('id')} 已过期但仍标记 active", "project-manifest.json")
        expected = expected_approval.get(grant.get("action"))
        if expected and grant.get("approval_kind") != expected:
            report.fail("authorization.approval_kind", f"授权 {grant.get('id')} 的确认类型必须是 {expected}", "project-manifest.json")

    requested_actions = [action for action in report.actions if action in IRREVERSIBLE_ACTIONS]
    if not requested_actions:
        return
    requested_platforms = set(report.platforms)
    if not requested_platforms:
        report.fail("authorization.platform_scope", "不可逆动作必须用 --platform 明确平台范围", "project-manifest.json")
        return
    unknown = requested_platforms - set(known_platforms)
    if unknown:
        report.fail("authorization.platform_unknown", f"请求包含未登记平台：{', '.join(sorted(unknown))}", "platform-status.json")

    for action in requested_actions:
        candidates: List[Dict[str, Any]] = []
        for grant in grants:
            if not isinstance(grant, dict) or grant.get("action") != action or grant.get("status") != "active":
                continue
            if grant.get("approval_kind") != expected_approval.get(action):
                continue
            if grant.get("release_digest") != release_digest:
                continue
            grant_platforms = set(grant.get("platforms", []))
            if not requested_platforms.issubset(grant_platforms):
                continue
            granted_at = parse_iso_datetime(grant.get("granted_at"))
            expires_at = parse_iso_datetime(grant.get("expires_at"))
            if granted_at is None or expires_at is None or granted_at > now or expires_at <= now:
                continue
            if not str(grant.get("evidence") or "").strip() or grant.get("consumed_at") is not None or grant.get("receipt_ids"):
                continue
            candidates.append(grant)
        if not candidates:
            report.fail(
                "authorization.missing_grant",
                f"没有覆盖动作 {action}、平台 {', '.join(sorted(requested_platforms))} 和当前冻结摘要的一次性有效授权",
                "project-manifest.json",
            )
        else:
            report.ok("authorization.valid_grant", f"一次性授权有效：{candidates[0].get('id')} ({action})", "project-manifest.json")


def check_handoff(
    data: Optional[Dict[str, Any]],
    manifest: Dict[str, Any],
    project_id: str,
    report: Report,
) -> None:
    if not data:
        return
    if data.get("project_id") != project_id:
        report.fail("handoff.project_id", "handoff-state 的 project_id 不一致", "handoff-state.json")
    if manifest.get("status") in {"paused", "blocked"}:
        if not data.get("pending_items"):
            report.fail("handoff.pending", "暂停或阻塞项目必须列出 pending_items", "handoff-state.json")
        if not str(data.get("next_action") or "").strip():
            report.fail("handoff.next_action", "暂停或阻塞项目必须给出下一步", "handoff-state.json")
    grants = manifest.get("authorization", {}).get("grants", [])
    expected = sorted(
        item.get("id") for item in grants
        if isinstance(item, dict) and item.get("status") == "active" and item.get("id")
    )
    actual = sorted(data.get("active_grant_ids", [])) if isinstance(data.get("active_grant_ids"), list) else []
    if actual != expected:
        report.fail("handoff.grants", f"active_grant_ids 与 manifest 不一致；应为 {expected}", "handoff-state.json")
    else:
        report.ok("handoff.grants", "交接状态与当前有效授权一致", "handoff-state.json")


def check_receipts(
    data: Optional[Dict[str, Any]],
    platforms_data: Optional[Dict[str, Any]],
    manifest: Dict[str, Any],
    project_id: str,
    release_digest: Optional[str],
    report: Report,
) -> None:
    if not data:
        return
    if data.get("project_id") != project_id:
        report.fail("receipts.project_id", "publication-receipts 的 project_id 不一致", "publication-receipts.json")
    receipts = data.get("receipts", [])
    if not isinstance(receipts, list):
        report.fail("receipts.type", "receipts 必须是数组", "publication-receipts.json")
        return
    receipt_map = {item.get("id"): item for item in receipts if isinstance(item, dict) and item.get("id")}
    if len(receipt_map) != len(receipts):
        report.fail("receipts.id", "发布回执 id 必须非空且唯一", "publication-receipts.json")

    platform_items = platforms_data.get("platforms", []) if isinstance(platforms_data, dict) else []
    by_platform = {item.get("platform"): item for item in platform_items if isinstance(item, dict)}
    for platform, item in by_platform.items():
        if item.get("status") != "published":
            continue
        matches = [
            receipt for receipt in receipts
            if isinstance(receipt, dict)
            and receipt.get("platform") == platform
            and receipt.get("status") in {"succeeded", "verified_existing"}
            and receipt.get("public_url") == item.get("public_url")
            and (not item.get("release_digest") or receipt.get("release_digest") == item.get("release_digest"))
        ]
        if not matches:
            message = f"{platform} 已发布但没有与公开链接及线上 release 匹配的成功回执"
            (report.fail if report.postflight else report.warn)("receipts.published_missing", message, "publication-receipts.json")
        else:
            report.ok("receipts.published", f"{platform} 的公开状态有回执可追溯", "publication-receipts.json")

    grants = manifest.get("authorization", {}).get("grants", [])
    grant_map = {item.get("id"): item for item in grants if isinstance(item, dict) and item.get("id")}
    for receipt in receipts:
        if not isinstance(receipt, dict) or receipt.get("action") == "historical_import":
            continue
        grant = grant_map.get(receipt.get("grant_id"))
        if grant is None:
            report.fail("receipts.grant", f"回执 {receipt.get('id')} 没有对应授权", "publication-receipts.json")
            continue
        if receipt.get("id") not in grant.get("receipt_ids", []):
            report.fail("receipts.grant_link", f"回执 {receipt.get('id')} 未反向登记到授权 {grant.get('id')}", "project-manifest.json")
        if receipt.get("release_digest") != grant.get("release_digest"):
            report.fail("receipts.release", f"回执 {receipt.get('id')} 与授权 {grant.get('id')} 的 release digest 不一致", "publication-receipts.json")
        if receipt.get("platform") not in grant.get("platforms", []) or receipt.get("action") != grant.get("action"):
            report.fail("receipts.scope", f"回执 {receipt.get('id')} 超出授权范围", "publication-receipts.json")

    for grant in grants:
        if not isinstance(grant, dict):
            continue
        receipt_ids = grant.get("receipt_ids", [])
        if grant.get("status") == "active" and receipt_ids:
            pending = [receipt_map.get(receipt_id) for receipt_id in receipt_ids]
            if any(not isinstance(item, dict) or item.get("status") != "unknown" for item in pending):
                report.fail("authorization.active_receipts", f"有效授权 {grant.get('id')} 的已登记回执不是 pending intent", "project-manifest.json")
            else:
                report.warn("authorization.pending_intent", f"授权 {grant.get('id')} 有未结算的外部动作，必须先对账", "project-manifest.json")
        if grant.get("status") == "consumed":
            if not valid_iso_datetime(grant.get("consumed_at")) or not receipt_ids:
                report.fail("authorization.consumed", f"已消费授权 {grant.get('id')} 缺少消费时间或回执", "project-manifest.json")
            for receipt_id in receipt_ids:
                if receipt_id not in receipt_map:
                    report.fail("authorization.receipt_missing", f"授权 {grant.get('id')} 引用了不存在的回执 {receipt_id}", "project-manifest.json")

    for action in report.actions:
        for platform in report.platforms:
            item = by_platform.get(platform, {})
            state = item.get("status")
            if action == "public_publish" and state not in {"ready", "awaiting_authorization"}:
                report.fail("receipts.state", f"{platform} 当前状态 {state} 不允许 public_publish", "platform-status.json")
            if action in {"update_publication", "delete_publication"} and state != "published":
                report.fail("receipts.state", f"{platform} 当前状态 {state} 不允许 {action}", "platform-status.json")
            if action == "public_publish" and item.get("status") == "published":
                report.fail("receipts.duplicate_publish", f"{platform} 已发布；应明确使用 update_publication，而不是重复 public_publish", "platform-status.json")
            same_release = [
                receipt for receipt in receipts
                if isinstance(receipt, dict)
                and receipt.get("platform") == platform
                and receipt.get("action") == action
                and receipt.get("release_digest") == release_digest
                and receipt.get("status") == "succeeded"
            ]
            if same_release:
                report.fail("receipts.idempotency", f"{platform}/{action} 对当前冻结版本已有成功回执，禁止重复执行", "publication-receipts.json")
            pending_intents = [
                receipt for receipt in receipts
                if isinstance(receipt, dict)
                and receipt.get("platform") == platform
                and receipt.get("action") == action
                and receipt.get("release_digest") == release_digest
                and receipt.get("status") == "unknown"
            ]
            if pending_intents:
                report.fail("receipts.pending_intent", f"{platform}/{action} 存在未结算 intent，先核对外部平台，禁止重试", "publication-receipts.json")


def validate(
    project: Path,
    strict: bool = False,
    for_publish: bool = False,
    postflight: bool = False,
    require_metrics: bool = False,
    actions: Sequence[str] = (),
    platforms: Sequence[str] = (),
) -> Dict[str, Any]:
    project = project.resolve()
    requested_actions = list(dict.fromkeys(actions))
    if for_publish and "public_publish" not in requested_actions:
        requested_actions.append("public_publish")
    requested_platforms = list(dict.fromkeys(platforms))
    manifest_path = project / "project-manifest.json"
    bootstrap = Report(project.name, strict, for_publish, postflight, require_metrics, requested_actions, requested_platforms)
    manifest = load_json(manifest_path, bootstrap, "manifest")
    if not manifest:
        return bootstrap.result()
    project_id = str(manifest.get("project_id") or project.name)
    report = Report(project_id, strict, for_publish, postflight, require_metrics, requested_actions, requested_platforms)
    report.issues.extend(bootstrap.issues)
    report.checks = bootstrap.checks
    check_schema(manifest, "project-manifest.schema.json", report, "manifest", manifest_path.name)
    check_manifest(project, manifest, report)
    files = manifest.get("files", {}) if isinstance(manifest.get("files"), dict) else {}
    decision_path = resolve(project, files.get("decision_log", "decision-log.json"))
    requirements_path = resolve(project, files.get("content_requirements", "content-requirements.json"))
    platform_path = resolve(project, files.get("platform_status", "platform-status.json"))
    metrics_path = resolve(project, files.get("metrics", "metrics.json"))
    handoff_path = resolve(project, files.get("handoff_state", "handoff-state.json"))
    receipts_path = resolve(project, files.get("publication_receipts", "publication-receipts.json"))
    editorial_policy_relative = files.get("editorial_policy")
    editorial_reviews_relative = files.get("editorial_reviews")
    editorial_policy_path = resolve(project, editorial_policy_relative) if editorial_policy_relative else None
    editorial_reviews_path = resolve(project, editorial_reviews_relative) if editorial_reviews_relative else None
    decisions = load_json(decision_path, report, "decisions")
    requirements = load_json(requirements_path, report, "requirements")
    platform_data = load_json(platform_path, report, "platforms")
    metrics = load_json(metrics_path, report, "metrics")
    handoff = load_json(handoff_path, report, "handoff")
    receipts = load_json(receipts_path, report, "receipts")
    editorial_policy = load_json(editorial_policy_path, report, "editorial_policy") if editorial_policy_path else None
    editorial_reviews = load_json(editorial_reviews_path, report, "editorial_reviews") if editorial_reviews_path else None
    checksums = load_json(resolve(project, files.get("checksums", "checksums.json")), report, "checksums")
    check_schema(decisions, "decision-log.schema.json", report, "decisions", decision_path.name)
    check_schema(requirements, "content-requirements.schema.json", report, "requirements", requirements_path.name)
    check_schema(platform_data, "platform-status.schema.json", report, "platforms", platform_path.name)
    check_schema(metrics, "metrics.schema.json", report, "metrics", metrics_path.name)
    check_schema(handoff, "handoff-state.schema.json", report, "handoff", handoff_path.name)
    check_schema(receipts, "publication-receipts.schema.json", report, "receipts", receipts_path.name)
    if editorial_policy_path:
        check_schema(editorial_policy, "editorial-policy.schema.json", report, "editorial_policy", editorial_policy_path.name)
    if editorial_reviews_path:
        check_schema(editorial_reviews, "editorial-reviews.schema.json", report, "editorial_reviews", editorial_reviews_path.name)
    check_decisions(decisions, project_id, report)
    if requirements:
        if requirements.get("project_id") != project_id:
            report.fail("requirements.project_id", "content-requirements 的 project_id 不一致", "content-requirements.json")
        prompt_text = check_prompt(project, requirements, report)
        delivery_context = check_prompt_delivery_context(project, requirements, report)
        check_deliverables(project, requirements, prompt_text, delivery_context, report)
        policy_digest, profiles = check_editorial_policy(project, requirements, editorial_policy, editorial_policy_path, report)
        check_editorial_reviews(
            project, requirements, editorial_reviews, editorial_reviews_path,
            editorial_policy, policy_digest, profiles, report,
        )
        check_platform_differentiation(project, requirements, prompt_text, report)
        check_story_coverage(project, manifest, requirements, decisions, report)
        check_prompt_card_sets(project, requirements, prompt_text, delivery_context, report)
        check_media(project, requirements, report)
    check_platforms(platform_data, project_id, report)
    release_digest = check_release(project, manifest, requirements, decisions, report)
    known_platforms = [
        item.get("platform") for item in (platform_data or {}).get("platforms", [])
        if isinstance(item, dict) and item.get("platform")
    ]
    check_authorization(manifest, release_digest, known_platforms, report)
    check_handoff(handoff, manifest, project_id, report)
    check_receipts(receipts, platform_data, manifest, project_id, release_digest, report)
    check_metrics(metrics, platform_data, project_id, report)
    check_checksums(project, checksums, report)
    return report.result()


def print_report(result: Dict[str, Any]) -> None:
    summary = result["summary"]
    print(f"[{result['status'].upper()}] {result['project_id']}")
    print(f"checks={summary['checks']} errors={summary['errors']} warnings={summary['warnings']}")
    for issue in result["issues"]:
        if issue["severity"] == "info":
            continue
        location = f" ({issue['path']})" if issue.get("path") else ""
        print(f"- {issue['severity'].upper()} {issue['code']}: {issue['message']}{location}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="检查内容项目的讨论、提示词、图文、视频和发布状态")
    parser.add_argument("--project", required=True, help="包含 project-manifest.json 的项目目录")
    parser.add_argument("--strict", action="store_true", help="把警告也视为阻断项")
    parser.add_argument("--for-publish", action="store_true", help="额外检查当前公开发布授权")
    parser.add_argument("--action", action="append", choices=sorted(IRREVERSIBLE_ACTIONS), default=[], help="要执行的不可逆动作；可重复")
    parser.add_argument("--platform", action="append", default=[], help="动作的平台范围；可重复")
    parser.add_argument("--postflight", action="store_true", help="要求已发布平台完成读者视角验收")
    parser.add_argument("--require-metrics", action="store_true", help="要求已发布平台完成当前指标采集检查点")
    parser.add_argument("--write-report", help="写入 JSON 报告；相对路径以项目目录为基准")
    args = parser.parse_args(argv)
    project = Path(args.project)
    result = validate(
        project,
        strict=args.strict,
        for_publish=args.for_publish,
        postflight=args.postflight,
        require_metrics=args.require_metrics,
        actions=args.action,
        platforms=args.platform,
    )
    print_report(result)
    if args.write_report:
        output = Path(args.write_report)
        if not output.is_absolute():
            output = project / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"report={output.resolve()}")
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
