import unittest
from pathlib import Path

from content_publishing.mcp_server import handle


ROOT = Path(__file__).resolve().parent.parent


class McpTests(unittest.TestCase):
    def test_initialize_and_tools_list(self):
        initialized = handle(ROOT, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        self.assertEqual(initialized["result"]["serverInfo"]["name"], "content-publishing-sop")
        listed = handle(ROOT, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        names = {item["name"] for item in listed["result"]["tools"]}
        self.assertIn("content_publish_prepare", names)
        self.assertIn("content_receipt_settle", names)


if __name__ == "__main__":
    unittest.main()
