"""Detect and confirm an existing public GitHub carrier for a canonical prompt."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from .common import CommandError, atomic_write_bytes, atomic_write_json, read_json, utc_now


GITHUB_SCP = re.compile(r"^(?:[^@]+@)?github\.com:([^/]+)/(.+?)(?:\.git)?$", re.IGNORECASE)


def _project(root: Path, value: str) -> Path:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = candidate.resolve()
    if not (candidate / "project-manifest.json").is_file():
        raise CommandError(f"不是有效内容项目：{candidate}")
    return candidate


def _prompt_relative(value: str) -> str:
    path = Path(value)
    if path.is_absolute() or not value.strip() or ".." in path.parts:
        raise CommandError("prompt-path 必须是来源仓库内的安全相对路径。")
    return path.as_posix()


def _git(repo: Path, *arguments: str, timeout: float = 8.0) -> subprocess.CompletedProcess:
    environment = dict(os.environ)
    environment["GIT_TERMINAL_PROMPT"] = "0"
    environment["GCM_INTERACTIVE"] = "Never"
    environment["GIT_SSH_COMMAND"] = "ssh -o BatchMode=yes"
    try:
        return subprocess.run(
            ["git", "-C", str(repo), *arguments],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            env=environment,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CommandError(f"Git 检测失败：{exc}") from exc


def _stdout(completed: subprocess.CompletedProcess) -> str:
    return completed.stdout.decode("utf-8", errors="replace").strip()


def _github_slug(remote_url: str) -> Optional[str]:
    value = remote_url.strip()
    parsed = urlparse(value)
    if parsed.scheme.casefold() in {"http", "https", "ssh"}:
        if parsed.hostname and parsed.hostname.casefold() == "github.com":
            parts = parsed.path.strip("/").removesuffix(".git").split("/")
            if len(parts) == 2 and all(parts):
                return f"{parts[0]}/{parts[1]}"
        return None
    match = GITHUB_SCP.match(value)
    if match:
        return f"{match.group(1)}/{match.group(2)}"
    return None


def _safe_remote_url(remote_url: str) -> str:
    """Remove credentials and URL parameters before display or persistence."""
    value = remote_url.strip()
    parsed = urlparse(value)
    if parsed.scheme.casefold() in {"http", "https", "ssh"} and parsed.hostname:
        host = parsed.hostname
        if parsed.port:
            host = f"{host}:{parsed.port}"
        return f"{parsed.scheme}://{host}{parsed.path}"
    value = value.split("?", 1)[0].split("#", 1)[0]
    scp_match = re.match(r"^(?:[^@]+@)?([^:]+):(.+)$", value)
    if scp_match:
        return f"{scp_match.group(1)}:{scp_match.group(2)}"
    return value


def _is_github_http_url(value: Any) -> bool:
    parsed = urlparse(str(value or "").strip())
    return parsed.scheme.casefold() in {"http", "https"} and (parsed.hostname or "").casefold() in {
        "github.com",
        "www.github.com",
        "raw.githubusercontent.com",
    }


def _unique_strings(*groups: Any) -> List[str]:
    result: List[str] = []
    for group in groups:
        if not isinstance(group, list):
            continue
        for item in group:
            value = str(item or "").strip()
            if value and value not in result:
                result.append(value)
    return result


def _github_visibility(slug: str, timeout: float) -> Tuple[str, str]:
    request = Request(
        f"https://api.github.com/repos/{slug}",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "content-publishing-sop"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return ("private" if payload.get("private") else "public", f"github-api:{slug}")
    except HTTPError as exc:
        if exc.code == 404:
            return "not_public_or_missing", f"github-api:http-{exc.code}"
        return "unknown", f"github-api:http-{exc.code}"
    except (URLError, OSError, ValueError) as exc:
        return "unknown", f"github-api:{type(exc).__name__}"


def _remote_branch_commit(repo: Path, branch: str, timeout: float) -> Tuple[Optional[str], str]:
    completed = _git(repo, "ls-remote", "origin", f"refs/heads/{branch}", timeout=timeout)
    if completed.returncode != 0:
        return None, "git-ls-remote:failed"
    line = _stdout(completed).splitlines()
    commit = line[0].split()[0] if line and line[0].split() else None
    return commit, "git-ls-remote:verified" if commit else "git-ls-remote:missing-branch"


def _public_prompt_bytes(slug: str, commit: str, prompt_path: str, timeout: float) -> Tuple[Optional[bytes], str]:
    encoded_path = quote(prompt_path, safe="/")
    url = f"https://raw.githubusercontent.com/{slug}/{commit}/{encoded_path}"
    request = Request(url, headers={"User-Agent": "content-publishing-sop"})
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.read(), url
    except HTTPError as exc:
        return None, f"raw-github:http-{exc.code}"
    except (URLError, OSError) as exc:
        return None, f"raw-github:{type(exc).__name__}"


def _candidate_id(identity: Dict[str, Any]) -> str:
    raw = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def detect_prompt_carrier(
    root: Path,
    project_value: str,
    source: Path,
    prompt_path: str,
    timeout: float = 5.0,
) -> Dict[str, Any]:
    """Return a read-only candidate. Never mutate project or source repositories."""
    project = _project(root, project_value)
    manifest = read_json(project / "project-manifest.json")
    requirements = read_json(project / "content-requirements.json")
    project_id = str(manifest.get("project_id") or project.name)
    relative = _prompt_relative(prompt_path)
    source = source.expanduser().resolve()
    if not source.is_dir():
        raise CommandError(f"来源项目目录不存在：{source}")

    root_result = _git(source, "rev-parse", "--show-toplevel")
    if root_result.returncode != 0:
        identity = {"project_id": project_id, "source": str(source), "prompt_path": relative, "reason": "not_git_repository"}
        return {
            "status": "candidate",
            "candidate_id": _candidate_id(identity),
            "eligibility": "ineligible",
            "reason": "not_git_repository",
            "source_path": str(source),
            "requires_human_confirmation": True,
            "writes_performed": False,
            "checks": {"explicit_source": "verified", "git_repository": "failed"},
        }

    repo = Path(_stdout(root_result)).resolve()
    remote_result = _git(repo, "remote", "get-url", "origin")
    remote_url = _stdout(remote_result) if remote_result.returncode == 0 else ""
    safe_remote_url = _safe_remote_url(remote_url) if remote_url else ""
    slug = _github_slug(remote_url) if remote_url else None
    head_result = _git(repo, "rev-parse", "HEAD")
    head_commit = _stdout(head_result) if head_result.returncode == 0 else ""
    branch_result = _git(repo, "symbolic-ref", "--quiet", "--short", "HEAD")
    branch = _stdout(branch_result) if branch_result.returncode == 0 else None

    show_result = _git(repo, "show", f"HEAD:{relative}") if head_commit else None
    head_prompt = show_result.stdout if show_result is not None and show_result.returncode == 0 else None
    head_prompt_sha256 = hashlib.sha256(head_prompt).hexdigest() if head_prompt is not None else None
    local_prompt = repo / relative
    local_prompt_is_regular = local_prompt.is_file() and not local_prompt.is_symlink()
    local_prompt_sha256 = hashlib.sha256(local_prompt.read_bytes()).hexdigest() if local_prompt_is_regular else None
    canonical = requirements.get("canonical_prompt", {}) if isinstance(requirements.get("canonical_prompt"), dict) else {}
    canonical_sha256 = canonical.get("sha256")

    visibility, visibility_evidence = ("unknown", "not-github")
    remote_commit: Optional[str] = None
    remote_commit_evidence = "not-checked"
    remote_prompt: Optional[bytes] = None
    remote_prompt_evidence = "not-checked"
    if slug:
        visibility, visibility_evidence = _github_visibility(slug, timeout)
        if branch:
            remote_commit, remote_commit_evidence = _remote_branch_commit(repo, branch, timeout)
        if head_commit:
            remote_prompt, remote_prompt_evidence = _public_prompt_bytes(slug, head_commit, relative, timeout)
    remote_prompt_sha256 = hashlib.sha256(remote_prompt).hexdigest() if remote_prompt is not None else None
    public_access_verified = visibility == "public" or remote_prompt is not None
    effective_visibility = "public" if public_access_verified else visibility

    checks = {
        "explicit_source": "verified",
        "git_repository": "verified",
        "github_remote": "verified" if slug else "failed",
        "public_repository": "verified" if public_access_verified else visibility,
        "prompt_tracked_in_head": "verified" if head_prompt is not None else "failed",
        "working_prompt_matches_head": "verified" if local_prompt_sha256 and local_prompt_sha256 == head_prompt_sha256 else "failed",
        "canonical_prompt_matches_head": "verified" if canonical_sha256 and canonical_sha256 == head_prompt_sha256 else "failed",
        "head_matches_remote_branch": "verified" if head_commit and remote_commit == head_commit else ("unknown" if remote_commit is None else "failed"),
        "public_prompt_matches_head": "verified" if remote_prompt_sha256 and remote_prompt_sha256 == head_prompt_sha256 else ("unknown" if remote_prompt is None else "failed"),
    }
    required_checks = (
        "github_remote",
        "public_repository",
        "prompt_tracked_in_head",
        "working_prompt_matches_head",
        "canonical_prompt_matches_head",
        "head_matches_remote_branch",
        "public_prompt_matches_head",
    )
    eligible = all(checks[name] == "verified" for name in required_checks)
    identity = {
        "project_id": project_id,
        "remote_url": safe_remote_url or None,
        "slug": slug,
        "branch": branch,
        "head_commit": head_commit,
        "remote_commit": remote_commit,
        "prompt_path": relative,
        "prompt_sha256": head_prompt_sha256,
        "canonical_prompt_sha256": canonical_sha256,
        "public_prompt_sha256": remote_prompt_sha256,
        "visibility": effective_visibility,
        "checks": checks,
    }
    public_prompt_url = (
        f"https://github.com/{slug}/blob/{head_commit}/{quote(relative, safe='/')}"
        if slug and head_commit and head_prompt_sha256 else None
    )
    return {
        "status": "candidate",
        "candidate_id": _candidate_id(identity),
        "eligibility": "eligible" if eligible else "ineligible",
        "reason": None if eligible else "one_or_more_checks_failed",
        "source_path": str(source),
        "repository_root": str(repo),
        "repository_url": f"https://github.com/{slug}" if slug else None,
        "remote_url": safe_remote_url or None,
        "provider": "github" if slug else None,
        "slug": slug,
        "branch": branch,
        "head_commit": head_commit or None,
        "remote_commit": remote_commit,
        "prompt_path": relative,
        "prompt_sha256": head_prompt_sha256,
        "public_prompt_url": public_prompt_url,
        "visibility": effective_visibility,
        "evidence": [visibility_evidence, remote_commit_evidence, remote_prompt_evidence],
        "checks": checks,
        "requires_human_confirmation": True,
        "writes_performed": False,
    }


def _evidence_resolvable(project: Path, evidence: List[str]) -> bool:
    for item in evidence:
        value = str(item or "").strip()
        if re.match(r"^https?://", value, re.IGNORECASE):
            return True
        relative, separator, fragment = value.partition("#")
        if not relative:
            continue
        path = (project / relative).resolve()
        try:
            path.relative_to(project.resolve())
        except ValueError:
            continue
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


def _write_confirmation(project: Path, requirements: Dict[str, Any], confirmation: Dict[str, Any]) -> None:
    requirements_path = project / "content-requirements.json"
    manifest_path = project / "project-manifest.json"
    manifest = read_json(manifest_path)
    now = utc_now()
    release = manifest.get("release", {}) if isinstance(manifest.get("release"), dict) else {}
    if release.get("status") == "frozen":
        release.update(
            status="invalidated",
            invalidated_at=now,
            invalidated_reason="提示词公开载体经过人工确认后发生变化，需重新审校并冻结",
        )
    manifest["updated_at"] = now
    context = requirements.setdefault("prompt_delivery_context", {})
    context.update(confirmation)
    requirements["schema_version"] = "1.3"

    originals = {requirements_path: requirements_path.read_bytes(), manifest_path: manifest_path.read_bytes()}
    written: List[Path] = []
    try:
        atomic_write_json(requirements_path, requirements)
        written.append(requirements_path)
        atomic_write_json(manifest_path, manifest)
        written.append(manifest_path)
    except Exception:
        for path in written:
            atomic_write_bytes(path, originals[path])
        raise


def confirm_prompt_carrier(
    root: Path,
    project_value: str,
    source: Path,
    prompt_path: str,
    candidate_id: str,
    evidence: List[str],
    timeout: float = 5.0,
) -> Dict[str, Any]:
    project = _project(root, project_value)
    if not _evidence_resolvable(project, evidence):
        raise CommandError("人工确认必须提供项目内可解析证据或公开 HTTP(S) 证据。")
    candidate = detect_prompt_carrier(root, project_value, source, prompt_path, timeout)
    if candidate.get("candidate_id") != candidate_id:
        raise CommandError("候选编号已变化；请重新展示最新检测结果并再次人工确认。")
    if candidate.get("eligibility") != "eligible":
        raise CommandError("候选仓库尚未通过公开性、远端提交和提示词一致性检查，不能确认使用。")
    now = utc_now()
    url = str(candidate["public_prompt_url"])
    requirements = read_json(project / "content-requirements.json")
    context = requirements.get("prompt_delivery_context", {}) if isinstance(requirements.get("prompt_delivery_context"), dict) else {}
    origin = context.get("content_origin")
    if origin not in {"experience_share", "existing_project"}:
        raise CommandError("请先在 prompt_delivery_context.content_origin 中确认内容来源类型。")
    _write_confirmation(project, requirements, {
        "content_origin": origin,
        "short_prompt_max_characters": int(context.get("short_prompt_max_characters", 1800)),
        "max_prompt_card_pages": int(context.get("max_prompt_card_pages", 2)),
        "existing_public_urls": _unique_strings(context.get("existing_public_urls"), [url]),
        "external_hosting_authorized": bool(context.get("external_hosting_authorized", False)),
        "decision_evidence": _unique_strings(context.get("decision_evidence"), evidence),
        "carrier_confirmation": {
            "status": "confirmed_existing",
            "candidate_id": candidate_id,
            "confirmed_url": url,
            "confirmed_at": now,
            "evidence": evidence,
            "repository": {
                "provider": "github",
                "slug": candidate["slug"],
                "remote_url": candidate["remote_url"],
                "branch": candidate["branch"],
                "commit": candidate["head_commit"],
                "prompt_path": candidate["prompt_path"],
                "prompt_sha256": candidate["prompt_sha256"],
            },
        },
    })
    return {"status": "confirmed", "project": str(project), "candidate_id": candidate_id, "prompt_url": url}


def confirm_no_prompt_carrier(
    root: Path,
    project_value: str,
    source: Path,
    prompt_path: str,
    candidate_id: str,
    evidence: List[str],
    timeout: float = 5.0,
) -> Dict[str, Any]:
    project = _project(root, project_value)
    if not _evidence_resolvable(project, evidence):
        raise CommandError("人工确认必须提供项目内可解析证据或公开 HTTP(S) 证据。")
    candidate = detect_prompt_carrier(root, project_value, source, prompt_path, timeout)
    if candidate.get("candidate_id") != candidate_id:
        raise CommandError("候选编号已变化；请重新展示最新检测结果并再次人工确认。")
    now = utc_now()
    requirements = read_json(project / "content-requirements.json")
    context = requirements.get("prompt_delivery_context", {}) if isinstance(requirements.get("prompt_delivery_context"), dict) else {}
    origin = context.get("content_origin")
    if origin not in {"experience_share", "existing_project"}:
        raise CommandError("请先在 prompt_delivery_context.content_origin 中确认内容来源类型。")
    remaining_urls = [
        value for value in _unique_strings(context.get("existing_public_urls"))
        if not _is_github_http_url(value)
    ]
    _write_confirmation(project, requirements, {
        "content_origin": origin,
        "short_prompt_max_characters": int(context.get("short_prompt_max_characters", 1800)),
        "max_prompt_card_pages": int(context.get("max_prompt_card_pages", 2)),
        "existing_public_urls": remaining_urls,
        "external_hosting_authorized": bool(context.get("external_hosting_authorized", False)),
        "decision_evidence": _unique_strings(context.get("decision_evidence"), evidence),
        "carrier_confirmation": {
            "status": "confirmed_none",
            "candidate_id": candidate_id,
            "confirmed_url": None,
            "confirmed_at": now,
            "evidence": evidence,
            "repository": None,
        },
    })
    return {"status": "confirmed_none", "project": str(project), "candidate_id": candidate_id}
