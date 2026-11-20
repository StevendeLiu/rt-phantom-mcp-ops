"""Regression unit tests for synthetic water-phantom 3D gamma QA and MCP RPC handlers."""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "mcp_server"))

from gamma_phantom_check import run_qa_suite  # noqa: E402
from server import handle_rpc  # noqa: E402


class TestPhantomQAAndMCP(unittest.TestCase):
    def test_synthetic_gamma_passes_tolerance(self) -> None:
        report = run_qa_suite(dd_pct=2.0, dta_mm=2.0, prescription_gy=78.0, noise_sigma=0.008)
        self.assertEqual(report["status"], "PASS")
        self.assertGreaterEqual(report["gamma"]["gamma_pass_rate_pct"], 95.0)

    def test_mcp_tools_list_and_call(self) -> None:
        list_resp = handle_rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        tool_names = [t["name"] for t in list_resp["result"]["tools"]]
        self.assertIn("get_latest_gamma_report", tool_names)

        call_resp = handle_rpc(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "get_latest_gamma_report", "arguments": {"rerun": True}},
            }
        )
        parsed = json.loads(call_resp["result"]["content"][0]["text"])
        self.assertEqual(parsed["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
