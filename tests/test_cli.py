import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from content_publishing.cli import _normalize_global_options, parser, main
from content_publishing.installers import install_host, sync_managed_installations
from content_publishing.projects import initialize_editorial, new_project


ROOT = Path(__file__).resolve().parent.parent


class CliTests(unittest.TestCase):
    def test_version_command(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["version"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["version"], "0.3.0")

    def test_root_is_accepted_before_or_after_subcommand(self):
        before = parser().parse_args(_normalize_global_options(["--root", str(ROOT), "doctor"]))
        after = parser().parse_args(_normalize_global_options(["doctor", "--root", str(ROOT)]))
        equals = parser().parse_args(_normalize_global_options(["doctor", f"--root={ROOT}"]))
        self.assertEqual(before.root, str(ROOT))
        self.assertEqual(after.root, str(ROOT))
        self.assertEqual(equals.root, str(ROOT))

    def test_new_project_registers_without_inventing_story(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "templates").mkdir()
            (root / "projects").mkdir()
            import shutil

            shutil.copytree(ROOT / "templates" / "project", root / "templates" / "project")
            (root / "projects" / "registry.json").write_text('{"schema_version":"1.0","projects":[]}\n', encoding="utf-8")
            result = new_project(
                root,
                "hello-project",
                "示例项目",
                "已经验收的示例需求",
                "2026-07-01T10:00:00+08:00",
                "2026-07-02T10:00:00+08:00",
                "可以复用",
                ["https://example.com/acceptance"],
                ["https://example.com/request"],
                ["知乎"],
            )
            self.assertEqual(result["status"], "created")
            registry = json.loads((root / "projects" / "registry.json").read_text(encoding="utf-8"))
            self.assertEqual(registry["projects"][0]["path"], "./hello-project")
            decisions = json.loads((root / "projects" / "hello-project" / "decision-log.json").read_text(encoding="utf-8"))
            self.assertEqual(len(decisions["events"]), 1)
            project_path = root / "projects" / "hello-project"
            self.assertTrue((project_path / "editorial-policy.json").is_file())
            self.assertTrue((project_path / "editorial-reviews.json").is_file())
            manifest = json.loads((project_path / "project-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["files"]["editorial_policy"], "editorial-policy.json")

    def test_editorial_init_backfills_legacy_project_without_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "projects" / "legacy-project"
            project.mkdir(parents=True)
            import shutil

            shutil.copytree(ROOT / "templates" / "project", root / "templates" / "project")
            manifest = json.loads((ROOT / "templates" / "project" / "project-manifest.json").read_text(encoding="utf-8"))
            manifest["project_id"] = "legacy-project"
            manifest["files"].pop("editorial_policy")
            manifest["files"].pop("editorial_reviews")
            (project / "project-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            result = initialize_editorial(root, "projects/legacy-project")
            self.assertEqual(result["status"], "initialized")
            self.assertTrue((project / "editorial-policy.json").is_file())
            policy = json.loads((project / "editorial-policy.json").read_text(encoding="utf-8"))
            self.assertEqual(policy["project_id"], "legacy-project")
            manifest_after_first = (project / "project-manifest.json").read_bytes()
            second = initialize_editorial(root, "projects/legacy-project")
            self.assertEqual(second["status"], "current")
            self.assertEqual((project / "project-manifest.json").read_bytes(), manifest_after_first)

    def test_editorial_init_rejects_path_outside_project(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "projects" / "unsafe-project"
            project.mkdir(parents=True)
            import shutil

            shutil.copytree(ROOT / "templates" / "project", root / "templates" / "project")
            manifest = json.loads((ROOT / "templates" / "project" / "project-manifest.json").read_text(encoding="utf-8"))
            manifest["project_id"] = "unsafe-project"
            manifest["files"]["editorial_policy"] = "../../outside-policy.json"
            (project / "project-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(Exception, "不能越出项目目录"):
                initialize_editorial(root, "projects/unsafe-project")
            self.assertFalse((root / "outside-policy.json").exists())

    def test_cursor_adapter_install_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source_root = base / "source"
            destination = base / "destination"
            source_root.mkdir()
            destination.mkdir()
            import shutil

            shutil.copytree(ROOT / "adapters", source_root / "adapters")
            shutil.copytree(ROOT / "skills", source_root / "skills")
            (source_root / ".git").mkdir()
            first = install_host(source_root, "cursor", destination)
            second = install_host(source_root, "cursor", destination)
            self.assertEqual(first["status"], "installed")
            self.assertEqual(second["status"], "installed")
            installed_text = (destination / ".cursor" / "rules" / "content-publishing-sop.mdc").read_text(encoding="utf-8")
            self.assertIn(str(source_root.resolve()), installed_text)
            source_file = source_root / "adapters" / "cursor" / "content-publishing-sop.mdc"
            source_file.write_text(source_file.read_text(encoding="utf-8") + "\n# upgraded\n", encoding="utf-8")
            synced = sync_managed_installations(source_root)
            self.assertEqual(synced["status"], "passed")
            self.assertIn("# upgraded", (destination / ".cursor" / "rules" / "content-publishing-sop.mdc").read_text(encoding="utf-8"))

    def test_codex_skill_finds_managed_external_workbench(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source_root = base / "workbench"
            source_root.mkdir()
            import shutil

            shutil.copytree(ROOT / "skills", source_root / "skills")
            shutil.copytree(ROOT / "adapters", source_root / "adapters")
            (source_root / ".git").mkdir()
            for marker in ("START-HERE.md", "AGENT-PROTOCOL.md", "SOURCE_OF_TRUTH.md", "SOP.md"):
                (source_root / marker).write_text("test\n", encoding="utf-8")
            skills_root = base / "codex" / "skills"
            installed = install_host(source_root, "codex", skills_root)
            locator = Path(installed["target"]) / "scripts" / "find_workbench.py"
            unrelated = base / "unrelated"
            unrelated.mkdir()
            completed = subprocess.run(
                [sys.executable, str(locator), "--start", str(unrelated)],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(json.loads(completed.stdout)["selected"], str(source_root.resolve()))


if __name__ == "__main__":
    unittest.main()
