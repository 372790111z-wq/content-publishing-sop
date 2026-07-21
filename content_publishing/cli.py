"""Cross-IDE command-line entry point."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional, Sequence

from . import __version__
from .bootstrap import DEFAULT_REPOSITORY, bootstrap
from .common import CommandError, find_workbench, json_print
from .dependencies import check_updates, list_dependencies, upgrade as upgrade_dependency
from .doctor import diagnose
from .installers import install_host, uninstall_host
from .mcp_server import serve
from .projects import new_project
from .publisher import publication_plan, registry
from .transactions import create_grant, freeze_release, prepare_intents, settle_receipt
from .updater import rollback, status as update_status, update


HOSTS = ["codex", "claude-code", "cursor", "windsurf", "vscode-agent", "generic-agent"]


def _normalize_global_options(argv: Sequence[str]) -> list[str]:
    """Accept --root before or after a subcommand without duplicating it everywhere."""
    root_options: list[str] = []
    remainder: list[str] = []
    values = list(argv)
    index = 0
    while index < len(values):
        value = values[index]
        if value == "--root":
            root_options.append(value)
            if index + 1 < len(values):
                root_options.append(values[index + 1])
                index += 2
                continue
            index += 1
            continue
        elif value.startswith("--root="):
            root_options.extend(["--root", value.split("=", 1)[1]])
            index += 1
            continue
        remainder.append(value)
        index += 1
    return root_options + remainder


def _root(args: argparse.Namespace) -> Path:
    return find_workbench(Path(args.root).expanduser() if getattr(args, "root", None) else None)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="content-publishing", description="跨 IDE 内容生产、校验与发布治理工具")
    root.add_argument("--root", help="工作台根目录；默认从当前目录或 CONTENT_PUBLISHING_HOME 查找")
    commands = root.add_subparsers(dest="command", required=True)

    commands.add_parser("version", help="显示本项目版本")
    bootstrap_parser = commands.add_parser("bootstrap", help="从 GitHub 创建受管理的公共工具 checkout")
    bootstrap_parser.add_argument("--dest", required=True, help="工具仓库安装目录")
    bootstrap_parser.add_argument("--repository", default=DEFAULT_REPOSITORY)
    bootstrap_parser.add_argument("--host", choices=HOSTS)
    bootstrap_parser.add_argument("--adapter-dest", help="非 Codex IDE 的项目根目录")
    doctor = commands.add_parser("doctor", help="检查首次运行闭环")
    doctor.add_argument("--deep", action="store_true", help="同时运行全部测试")

    install = commands.add_parser("install", help="安装当前 IDE 的薄入口")
    install.add_argument("--host", choices=HOSTS, default="codex")
    install.add_argument("--dest", help="非 Codex 宿主必须指定 IDE 项目根目录")
    install.add_argument("--check", action="store_true")
    install.add_argument("--upgrade", action="store_true", help="只更新由本工具安装且未修改的入口")

    uninstall = commands.add_parser("uninstall", help="卸载由本工具管理且未修改的 IDE 入口")
    uninstall.add_argument("--host", choices=HOSTS, default="codex")
    uninstall.add_argument("--dest")

    self_update = commands.add_parser("update", help="只升级 content-publishing-sop 本身")
    self_update.add_argument("--check", action="store_true", help="获取上游并检查新版本")
    self_update.add_argument("--dry-run", action="store_true")
    self_update.add_argument("--to", help="升级到指定 Git tag/ref；必须是快进目标")

    commands.add_parser("rollback", help="回滚最近一次由 update 完成的项目升级")

    deps = commands.add_parser("deps", help="检测或定向升级外部 CLI，不升级本项目")
    deps_sub = deps.add_subparsers(dest="deps_command", required=True)
    deps_sub.add_parser("list")
    deps_check = deps_sub.add_parser("check")
    deps_check.add_argument("name", nargs="?", choices=list_dependencies_ids())
    deps_upgrade = deps_sub.add_parser("upgrade")
    deps_upgrade.add_argument("name", choices=list_dependencies_ids())
    deps_upgrade.add_argument("--apply", action="store_true", help="实际执行；缺省只显示计划")

    project = commands.add_parser("new-project", help="事务化创建并登记内容项目")
    project.add_argument("project_id")
    project.add_argument("--title", required=True)
    project.add_argument("--source-title", required=True)
    project.add_argument("--accepted-at", required=True)
    project.add_argument("--requested-at", required=True)
    project.add_argument("--reuse-reason", required=True)
    project.add_argument("--acceptance-evidence", action="append", required=True)
    project.add_argument("--request-evidence", action="append", required=True)
    project.add_argument("--platform", action="append", default=[])
    project.add_argument("--owner", default="")

    freeze = commands.add_parser("freeze", help="校验并冻结一个 release")
    freeze.add_argument("project")
    freeze.add_argument("--version", required=True)

    grant = commands.add_parser("grant", help="创建范围化一次性授权")
    grant.add_argument("project")
    grant.add_argument("--action", choices=["public_publish", "update_publication", "delete_publication", "external_sync"], required=True)
    grant.add_argument("--platform", action="append", required=True)
    grant.add_argument("--evidence", required=True)
    grant.add_argument("--expires-minutes", type=int, default=120)

    prepare = commands.add_parser("prepare", help="整批门禁后创建 pending intents")
    prepare.add_argument("project")
    prepare.add_argument("--grant-id", required=True)

    settle = commands.add_parser("settle", help="用外部执行证据结算一个 pending intent")
    settle.add_argument("project")
    settle.add_argument("--receipt-id", required=True)
    settle.add_argument("--status", choices=["succeeded", "failed", "verified_existing"], required=True)
    settle.add_argument("--evidence", action="append", required=True)
    settle.add_argument("--public-url")
    settle.add_argument("--external-id")
    settle.add_argument("--reader-verified", action="store_true")
    settle.add_argument("--prompt-delivery", choices=["full_text", "prompt_cards", "accessible_link", "not_required"])

    platforms = commands.add_parser("platforms", help="查看平台连接能力")
    platforms.add_argument("--project")
    platforms.add_argument("--action", choices=["public_publish", "update_publication"], default="public_publish")
    platforms.add_argument("--platform", action="append", default=[])

    mcp = commands.add_parser("mcp", help="启动零依赖 MCP stdio server")
    mcp.add_argument("mcp_command", choices=["serve"])
    return root


def list_dependencies_ids():
    return ["browser-use", "ffmpeg", "playwright", "pillow"]


def _delegate_to_workbench(argv: Sequence[str]) -> Optional[int]:
    """Keep the installed console script as a shim while the checkout owns current logic."""
    if os.environ.get("CONTENT_PUBLISHING_BUNDLED") == "1":
        return None
    explicit_root = None
    values = list(argv)
    if "--root" in values:
        index = values.index("--root")
        if index + 1 < len(values):
            explicit_root = Path(values[index + 1]).expanduser()
    try:
        workbench = find_workbench(explicit_root)
    except CommandError:
        return None
    package_root = Path(__file__).resolve().parent.parent
    bundled_entry = workbench / "tools" / "content_publishing.py"
    if workbench.resolve() == package_root.resolve() or not bundled_entry.is_file():
        return None
    environment = dict(os.environ)
    environment["CONTENT_PUBLISHING_BUNDLED"] = "1"
    completed = subprocess.run([sys.executable, str(bundled_entry), *values], env=environment)
    return completed.returncode


def main(argv: Optional[Sequence[str]] = None) -> int:
    values = _normalize_global_options(list(argv) if argv is not None else sys.argv[1:])
    delegated = _delegate_to_workbench(values)
    if delegated is not None:
        return delegated
    args = parser().parse_args(values)
    try:
        if args.command == "version":
            json_print({"name": "content-publishing-sop", "version": __version__})
            return 0
        if args.command == "bootstrap":
            result = bootstrap(
                Path(args.dest),
                args.repository,
                args.host,
                Path(args.adapter_dest) if args.adapter_dest else None,
            )
            json_print(result)
            return 0
        if args.command == "deps":
            if args.deps_command == "list":
                result = list_dependencies()
            elif args.deps_command == "check":
                result = check_updates(args.name)
            else:
                result = upgrade_dependency(args.name, args.apply)
            json_print(result)
            return 0
        if args.command == "platforms" and not args.project:
            json_print(registry())
            return 0
        root = _root(args)
        if args.command == "doctor":
            result = diagnose(root, args.deep)
        elif args.command == "install":
            result = install_host(root, args.host, Path(args.dest) if args.dest else None, args.check, args.upgrade)
        elif args.command == "uninstall":
            result = uninstall_host(root, args.host, Path(args.dest) if args.dest else None)
        elif args.command == "update":
            result = update_status(root, fetch=True, target=args.to) if args.check else update(root, args.to, args.dry_run)
        elif args.command == "rollback":
            result = rollback(root)
        elif args.command == "new-project":
            result = new_project(
                root, args.project_id, args.title, args.source_title, args.accepted_at, args.requested_at,
                args.reuse_reason, args.acceptance_evidence, args.request_evidence, args.platform, args.owner,
            )
        elif args.command == "freeze":
            result = freeze_release(root, args.project, args.version)
        elif args.command == "grant":
            result = create_grant(root, args.project, args.action, args.platform, args.evidence, args.expires_minutes)
        elif args.command == "prepare":
            result = prepare_intents(root, args.project, args.grant_id)
        elif args.command == "settle":
            result = settle_receipt(
                root, args.project, args.receipt_id, args.status, args.evidence, args.public_url,
                args.external_id, args.reader_verified, args.prompt_delivery,
            )
        elif args.command == "platforms":
            if args.project:
                project = Path(args.project)
                if not project.is_absolute():
                    project = root / project
                result = publication_plan(project.resolve(), args.action, args.platform)
        elif args.command == "mcp":
            return serve(root)
        else:
            raise CommandError(f"未知命令：{args.command}")
        json_print(result)
        if isinstance(result, dict) and result.get("status") in {"blocked", "failed", "conflict", "updated_with_conflicts"}:
            return 2
        return 0
    except CommandError as exc:
        json_print({"status": "error", "message": str(exc)})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
