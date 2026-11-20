#!/usr/bin/env python3
"""Lightweight JSON-RPC 2.0 Remote MCP server for iOS App Intents & Devin Bots.

Exposes offline phantom QA status, NAS cold-backup SHA-256 verification, and FRP relay checks.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "scripts"))
from gamma_phantom_check import run_qa_suite  # noqa: E402

REPORT_PATH = ROOT_DIR / "reports" / "latest_qa_report.json"

TOOLS: List[Dict[str, Any]] = [
    {
        "name": "get_latest_gamma_report",
        "description": "Return the latest offline synthetic water-phantom 3D gamma-index and DVH report.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "rerun": {"type": "boolean", "description": "If true, recompute the synthetic QA benchmark live."}
            },
        },
    },
    {
        "name": "verify_nas_cold_backup_checksum",
        "description": "Verify SHA-256 checksums for files in a local or mounted cold-backup staging directory.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "directory": {"type": "string", "description": "Relative path to audit (defaults to reports)."}
            },
        },
    },
    {
        "name": "get_frp_tunnel_status",
        "description": "Check TCP reachability of a configured FRP relay endpoint (defaults to localhost test port).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "host": {"type": "string"},
                "port": {"type": "integer"},
            },
        },
    },
]


def _tool_get_latest_gamma_report(args: Dict[str, Any]) -> Dict[str, Any]:
    if args.get("rerun") or not REPORT_PATH.exists():
        report = run_qa_suite()
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report
    return json.loads(REPORT_PATH.read_text(encoding="utf-8"))


def _tool_verify_nas_checksum(args: Dict[str, Any]) -> Dict[str, Any]:
    rel = args.get("directory", "reports")
    target = (ROOT_DIR / rel).resolve()
    if not str(target).startswith(str(ROOT_DIR)) or not target.exists():
        return {"status": "ERROR", "detail": f"Directory not accessible inside workspace: {rel}"}

    checksums: Dict[str, str] = {}
    for file_path in sorted(target.rglob("*")):
        if file_path.is_file():
            digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
            checksums[str(file_path.relative_to(ROOT_DIR))] = digest
    return {"status": "OK", "files_verified": len(checksums), "sha256_manifest": checksums}


def _tool_get_frp_tunnel_status(args: Dict[str, Any]) -> Dict[str, Any]:
    host = str(args.get("host") or os.getenv("FRP_RELAY_HOST", "127.0.0.1"))
    port = int(args.get("port") or os.getenv("FRP_RELAY_PORT", "7000"))
    try:
        with socket.create_connection((host, port), timeout=1.5):
            return {"host": host, "port": port, "reachable": True}
    except OSError as exc:
        return {"host": host, "port": port, "reachable": False, "detail": str(exc)}


def handle_rpc(payload: Dict[str, Any]) -> Dict[str, Any]:
    req_id = payload.get("id")
    method = payload.get("method", "")
    params = payload.get("params") or {}

    if method == "initialize":
        result = {
            "protocolVersion": "2025-03-26",
            "serverInfo": {"name": "rt-phantom-mcp-ops", "version": "0.1.0"},
            "capabilities": {"tools": {}},
        }
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        dispatch = {
            "get_latest_gamma_report": _tool_get_latest_gamma_report,
            "verify_nas_cold_backup_checksum": _tool_verify_nas_checksum,
            "get_frp_tunnel_status": _tool_get_frp_tunnel_status,
        }
        if name not in dispatch:
            return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Unknown tool: {name}"}}
        data = dispatch[name](args)
        result = {"content": [{"type": "text", "text": json.dumps(data, indent=2)}]}
    else:
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Unknown method: {method}"}}

    return {"jsonrpc": "2.0", "id": req_id, "result": result}


class MCPHandler(BaseHTTPRequestHandler):
    def _send_json(self, code: int, body: Dict[str, Any]) -> None:
        raw = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(200, {"status": "ok", "service": "rt-phantom-mcp-ops"})
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path != "/mcp":
            self._send_json(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            self._send_json(400, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
            return
        self._send_json(200, handle_rpc(payload))


def main() -> None:
    host = os.getenv("MCP_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_PORT", "8765"))
    server = ThreadingHTTPServer((host, port), MCPHandler)
    print(f"rt-phantom-mcp-ops Remote MCP server listening on http://{host}:{port}/mcp")
    server.serve_forever()


if __name__ == "__main__":
    main()
