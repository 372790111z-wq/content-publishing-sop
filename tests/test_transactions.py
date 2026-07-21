import json
import shutil
import tempfile
import unittest
from pathlib import Path

from content_publishing.transactions import create_grant, freeze_release, prepare_intents, settle_receipt


ROOT = Path(__file__).resolve().parent.parent


class TransactionTests(unittest.TestCase):
    def test_freeze_grant_intent_and_settle(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            shutil.copytree(ROOT / "examples" / "quickstart-demo", project)
            platform_path = project / "platform-status.json"
            platforms = json.loads(platform_path.read_text(encoding="utf-8"))
            platforms["platforms"][0]["status"] = "ready"
            platform_path.write_text(json.dumps(platforms, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            frozen = freeze_release(ROOT, str(project), "v1")
            self.assertEqual(frozen["status"], "frozen")
            grant = create_grant(ROOT, str(project), "public_publish", ["example"], "用户确认最终内容和 example 平台")
            prepared = prepare_intents(ROOT, str(project), grant["grant"]["id"])
            receipt_id = prepared["receipts"][0]["id"]
            settled = settle_receipt(
                ROOT,
                str(project),
                receipt_id,
                "succeeded",
                ["https://example.com/public"],
                "https://example.com/public",
                "demo-1",
                True,
                "full_text",
            )
            self.assertEqual(settled["grant_status"], "consumed")
            manifest = json.loads((project / "project-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "published")
            self.assertEqual(manifest["authorization"]["grants"][0]["status"], "consumed")


if __name__ == "__main__":
    unittest.main()
