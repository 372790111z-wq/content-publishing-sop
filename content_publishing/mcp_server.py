"""Zero-dependency MCP stdio server for IDEs that support MCP."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from . import __version__
from .common import CommandError, find_workbench
from .doctor import diagnose
from .projects import new_project
from .publisher import publication_plan, registry
from .transactions import create_grant, freeze_release, prepare_intents, settle_receipt


PROTOCOL_VERSION = "2024-11-05"


TOOLS = [
    {
        "name": "content_doctor",
        "description": "Check workbench, dashboard, portability and optional tests without publishing.",
        "inputSchema": {"type": "object", "properties": {"deep": {"type": "boolean"}}},
    },
    {
        "name": "content_platforms",
        "description": "List configured platform connector capabilities.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "content_publication_plan",
        "description": "Build a publication plan without performing an external action.",
        "inputSchema": {
            "type": "object",
            "required": ["project", "action", "platforms"],
            "properties": {
                "project": {"type": "string"},
                "action": {"enum": ["public_publish", "update_publication"]},
                "platforms": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
    {
        "name": "content_release_freeze",
        "description": "Freeze a validated content release and bind its digest to the latest decision.",
        "inputSchema": {"type": "object", "required": ["project", "version"], "properties": {"project": {"type": "string"}, "version": {"type": "string"}}},
    },
    {
        "name": "content_grant_create",
        "description": "Create a scoped one-time grant from explicit user confirmation evidence.",
        "inputSchema": {
            "type": "object",
            "required": ["project", "action", "platforms", "evidence"],
            "properties": {
                "project": {"type": "string"},
                "action": {"type": "string"},
                "platforms": {"type": "array", "items": {"type": "string"}},
                "evidence": {"type": "string"},
                "expires_minutes": {"type": "integer"},
            },
        },
    },
    {
        "name": "content_publish_prepare",
        "description": "Validate the full platform batch and create all pending intents before external calls.",
        "inputSchema": {"type": "object", "required": ["project", "grant_id"], "properties": {"project": {"type": "string"}, "grant_id": {"type": "string"}}},
    },
    {
        "name": "content_receipt_settle",
        "description": "Settle one pending intent after the connector returns evidence.",
        "inputSchema": {
            "type": "object",
            "required": ["project", "receipt_id", "status", "evidence"],
            "properties": {
                "project": {"type": "string"},
                "receipt_id": {"type": "string"},
                "status": {"enum": ["succeeded", "failed", "verified_existing"]},
                "evidence": {"type": "array", "items": {"type": "string"}},
                "public_url": {"type": "string"},
                "external_id": {"type": "string"},
                "reader_verified": {"type": "boolean"},
                "prompt_delivery": {"type": "string"},
            },
        },
    },
]


def _content(value: Any, is_error: bool = False) -> Dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False, indent=2)}], "isError": is_error}


def call_tool(root: Path, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    if name == "content_doctor":
        return diagnose(root, bool(arguments.get("deep")))
    if name == "content_platforms":
        return registry()
    if name == "content_publication_plan":
        project = Path(arguments["project"])
        if not project.is_absolute():
            project = root / project
        return publication_plan(project.resolve(), arguments["action"], arguments["platforms"])
    if name == "content_release_freeze":
        return freeze_release(root, arguments["project"], arguments["version"])
    if name == "content_grant_create":
        return create_grant(root, arguments["project"], arguments["action"], arguments["platforms"], arguments["evidence"], int(arguments.get("expires_minutes", 120)))
    if name == "content_publish_prepare":
        return prepare_intents(root, arguments["project"], arguments["grant_id"])
    if name == "content_receipt_settle":
        return settle_receipt(
            root,
            arguments["project"],
            arguments["receipt_id"],
            arguments["status"],
            arguments["evidence"],
            arguments.get("public_url"),
            arguments.get("external_id"),
            bool(arguments.get("reader_verified")),
            arguments.get("prompt_delivery"),
        )
    raise CommandError(f"未知 MCP tool：{name}")


def handle(root: Path, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    request_id = request.get("id")
    method = request.get("method")
    if method == "notifications/initialized":
        return None
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "content-publishing-sop", "version": __version__},
            },
        }
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = request.get("params", {})
        try:
            result = _content(call_tool(root, params.get("name", ""), params.get("arguments", {})))
        except (CommandError, KeyError, TypeError, ValueError) as exc:
            result = _content({"error": str(exc)}, is_error=True)
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}


def serve(root: Optional[Path] = None) -> int:
    workbench = root or find_workbench()
    for line in sys.stdin:
        try:
            request = json.loads(line)
            response = handle(workbench, request)
            if response is not None:
                print(json.dumps(response, ensure_ascii=False), flush=True)
        except (json.JSONDecodeError, TypeError) as exc:
            print(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(exc)}}), flush=True)
    return 0
