import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class DashboardIsolationTests(unittest.TestCase):
    def test_local_registry_writes_private_dashboard_without_touching_public_demo(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "tools").mkdir()
            (root / "dashboard").mkdir()
            (root / "projects").mkdir()
            (root / ".content-publishing").mkdir()
            shutil.copy2(ROOT / "tools" / "build_dashboard.py", root / "tools" / "build_dashboard.py")
            for asset in ("index.html", "styles.css", "app.js", "README.md"):
                shutil.copy2(ROOT / "dashboard" / asset, root / "dashboard" / asset)

            public_data = 'window.CONTENT_PUBLISHING_DATA = {"sentinel":"public-demo"};\n'
            (root / "dashboard" / "data.js").write_text(public_data, encoding="utf-8")
            (root / "projects" / "registry.json").write_text(
                json.dumps({"schema_version": "1.0", "projects": []}),
                encoding="utf-8",
            )
            (root / ".content-publishing" / "registry.json").write_text(
                json.dumps({"schema_version": "1.0", "projects": []}),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [sys.executable, str(root / "tools" / "build_dashboard.py")],
                check=True,
                capture_output=True,
                text=True,
            )

            private_dashboard = root / ".content-publishing" / "dashboard"
            self.assertIn(str(private_dashboard / "data.js"), completed.stdout)
            self.assertTrue((private_dashboard / "data.js").is_file())
            for asset in ("index.html", "styles.css", "app.js", "README.md"):
                self.assertTrue((private_dashboard / asset).is_file())
            self.assertEqual((root / "dashboard" / "data.js").read_text(encoding="utf-8"), public_data)


if __name__ == "__main__":
    unittest.main()
