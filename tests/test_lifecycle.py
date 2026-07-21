import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from content_publishing.bootstrap import bootstrap
from content_publishing.cli import _delegate_to_workbench
from content_publishing.dependencies import upgrade_plan
from content_publishing.updater import rollback, status, update


class LifecycleTests(unittest.TestCase):
    def _git(self, root: Path, *args: str):
        subprocess.run(["git", *args], cwd=str(root), check=True, capture_output=True, text=True)

    def test_bootstrap_from_local_repository(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = base / "source"
            source.mkdir()
            for marker in ("START-HERE.md", "SOP.md", "VERSION"):
                (source / marker).write_text("test\n", encoding="utf-8")
            self._git(source, "init")
            self._git(source, "config", "user.email", "test@example.com")
            self._git(source, "config", "user.name", "Test")
            self._git(source, "add", ".")
            self._git(source, "commit", "-m", "initial")
            destination = base / "installed"
            result = bootstrap(destination, str(source))
            self.assertEqual(result["status"], "installed")
            self.assertTrue((destination / "VERSION").is_file())

    def test_update_dry_run_reports_dirty_without_mutating(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "file.txt").write_text("one\n", encoding="utf-8")
            self._git(root, "init")
            self._git(root, "config", "user.email", "test@example.com")
            self._git(root, "config", "user.name", "Test")
            self._git(root, "add", ".")
            self._git(root, "commit", "-m", "initial")
            self.assertEqual(status(root)["status"], "current")
            (root / "file.txt").write_text("two\n", encoding="utf-8")
            planned = update(root, dry_run=True)
            self.assertEqual(planned["status"], "planned")
            self.assertFalse(planned["can_apply"])

    def test_fast_forward_update_and_explicit_rollback(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            origin = base / "origin"
            origin.mkdir()
            (origin / "file.txt").write_text("one\n", encoding="utf-8")
            self._git(origin, "init")
            self._git(origin, "config", "user.email", "test@example.com")
            self._git(origin, "config", "user.name", "Test")
            self._git(origin, "add", ".")
            self._git(origin, "commit", "-m", "initial")
            local = base / "local"
            subprocess.run(["git", "clone", str(origin), str(local)], check=True, capture_output=True, text=True)
            (origin / "file.txt").write_text("two\n", encoding="utf-8")
            self._git(origin, "add", ".")
            self._git(origin, "commit", "-m", "update")
            with mock.patch("content_publishing.updater._postflight", return_value={"ok": True, "results": []}), mock.patch(
                "content_publishing.updater.sync_managed_installations", return_value={"status": "none", "installations": []}
            ):
                updated = update(local)
                self.assertEqual(updated["status"], "updated")
                self.assertEqual((local / "file.txt").read_text(encoding="utf-8"), "two\n")
                reverted = rollback(local)
                self.assertEqual(reverted["status"], "rolled_back")
                self.assertEqual((local / "file.txt").read_text(encoding="utf-8"), "one\n")

    def test_uv_tool_provider_is_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary) / "uv" / "tools" / "browser-use" / "bin"
            base.mkdir(parents=True)
            interpreter = base / "python"
            interpreter.write_text("", encoding="utf-8")
            command = base / "browser-use"
            command.write_text(f"#!{interpreter}\n", encoding="utf-8")
            detected = {
                "status": "detected",
                "commands": [{"path": str(command)}],
                "packages": {"browser-use": "0.1", "browser-harness": "0.1"},
            }
            with mock.patch("content_publishing.dependencies.detect", return_value=detected), mock.patch(
                "content_publishing.dependencies.shutil.which", return_value="/usr/bin/uv"
            ):
                self.assertEqual(upgrade_plan("browser-use"), ["/usr/bin/uv", "tool", "upgrade", "browser-use"])

    def test_installed_cli_delegates_to_managed_checkout(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for marker in ("START-HERE.md", "SOP.md"):
                (root / marker).write_text("test\n", encoding="utf-8")
            (root / "templates" / "project").mkdir(parents=True)
            (root / "validator").mkdir()
            (root / "validator" / "validate.py").write_text("# marker\n", encoding="utf-8")
            (root / "tools").mkdir()
            (root / "tools" / "content_publishing.py").write_text("raise SystemExit(7)\n", encoding="utf-8")
            self.assertEqual(_delegate_to_workbench(["--root", str(root), "version"]), 7)


if __name__ == "__main__":
    unittest.main()
