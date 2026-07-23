import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from content_publishing.carriers import (
    confirm_no_prompt_carrier,
    confirm_prompt_carrier,
    detect_prompt_carrier,
)
from content_publishing.common import CommandError


ROOT = Path(__file__).resolve().parent.parent


class PromptCarrierTests(unittest.TestCase):
    def fixture(self, temporary: str):
        base = Path(temporary)
        project = base / "project"
        source = base / "source"
        shutil.copytree(ROOT / "examples" / "quickstart-demo", project)
        source.mkdir()
        prompt = (project / "content" / "canonical-prompt.md").read_bytes()
        (source / "EXECUTE-PROMPT.md").write_bytes(prompt)
        subprocess.run(["git", "init"], cwd=source, check=True, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "main"], cwd=source, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Fixture"], cwd=source, check=True)
        subprocess.run(["git", "config", "user.email", "fixture@example.com"], cwd=source, check=True)
        subprocess.run(["git", "add", "EXECUTE-PROMPT.md"], cwd=source, check=True)
        subprocess.run(["git", "commit", "-m", "add prompt"], cwd=source, check=True, capture_output=True)
        subprocess.run(
            ["git", "remote", "add", "origin", "https://github.com/example/prompt-project.git"],
            cwd=source,
            check=True,
        )
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=source, check=True, capture_output=True, text=True,
        ).stdout.strip()
        return project, source, prompt, head

    def verified_network(self, prompt: bytes, head: str):
        return (
            patch("content_publishing.carriers._github_visibility", return_value=("public", "fixture-public")),
            patch("content_publishing.carriers._remote_branch_commit", return_value=(head, "fixture-remote")),
            patch("content_publishing.carriers._public_prompt_bytes", return_value=(prompt, "fixture-raw")),
        )

    def test_detect_is_read_only_and_returns_human_confirmation_candidate(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, source, prompt, head = self.fixture(temporary)
            before = (project / "content-requirements.json").read_bytes()
            patches = self.verified_network(prompt, head)
            with patches[0], patches[1], patches[2]:
                result = detect_prompt_carrier(ROOT, str(project), source, "EXECUTE-PROMPT.md")
            self.assertEqual(result["eligibility"], "eligible")
            self.assertTrue(result["requires_human_confirmation"])
            self.assertFalse(result["writes_performed"])
            self.assertEqual((project / "content-requirements.json").read_bytes(), before)
            self.assertIn(f"/blob/{head}/EXECUTE-PROMPT.md", result["public_prompt_url"])

    def test_confirm_rechecks_candidate_and_records_existing_repository(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, source, prompt, head = self.fixture(temporary)
            requirements = json.loads((project / "content-requirements.json").read_text(encoding="utf-8"))
            requirements["prompt_delivery_context"]["existing_public_urls"] = ["https://docs.example.com/prompt"]
            requirements["prompt_delivery_context"]["external_hosting_authorized"] = True
            (project / "content-requirements.json").write_text(
                json.dumps(requirements, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            patches = self.verified_network(prompt, head)
            with patches[0], patches[1], patches[2]:
                detected = detect_prompt_carrier(ROOT, str(project), source, "EXECUTE-PROMPT.md")
            patches = self.verified_network(prompt, head)
            with patches[0], patches[1], patches[2]:
                result = confirm_prompt_carrier(
                    ROOT,
                    str(project),
                    source,
                    "EXECUTE-PROMPT.md",
                    detected["candidate_id"],
                    ["decision-log.json#event-decision"],
                )
            self.assertEqual(result["status"], "confirmed")
            requirements = json.loads((project / "content-requirements.json").read_text(encoding="utf-8"))
            context = requirements["prompt_delivery_context"]
            self.assertEqual(requirements["schema_version"], "1.3")
            self.assertEqual(context["content_origin"], "experience_share")
            self.assertEqual(context["carrier_confirmation"]["status"], "confirmed_existing")
            self.assertEqual(context["existing_public_urls"], ["https://docs.example.com/prompt", detected["public_prompt_url"]])
            self.assertTrue(context["external_hosting_authorized"])

    def test_changed_candidate_requires_a_new_human_confirmation(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, source, prompt, head = self.fixture(temporary)
            before = (project / "content-requirements.json").read_bytes()
            patches = self.verified_network(prompt, head)
            with patches[0], patches[1], patches[2], self.assertRaisesRegex(CommandError, "候选编号已变化"):
                confirm_prompt_carrier(
                    ROOT,
                    str(project),
                    source,
                    "EXECUTE-PROMPT.md",
                    "0" * 64,
                    ["decision-log.json#event-decision"],
                )
            self.assertEqual((project / "content-requirements.json").read_bytes(), before)

    def test_human_can_confirm_not_to_use_an_eligible_repository(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, source, prompt, head = self.fixture(temporary)
            requirements = json.loads((project / "content-requirements.json").read_text(encoding="utf-8"))
            requirements["prompt_delivery_context"]["content_origin"] = "existing_project"
            requirements["prompt_delivery_context"]["existing_public_urls"] = [
                "https://docs.example.com/prompt",
                f"https://github.com/example/prompt-project/blob/{head}/EXECUTE-PROMPT.md",
            ]
            requirements["prompt_delivery_context"]["external_hosting_authorized"] = True
            (project / "content-requirements.json").write_text(
                json.dumps(requirements, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            patches = self.verified_network(prompt, head)
            with patches[0], patches[1], patches[2]:
                detected = detect_prompt_carrier(ROOT, str(project), source, "EXECUTE-PROMPT.md")
            patches = self.verified_network(prompt, head)
            with patches[0], patches[1], patches[2]:
                result = confirm_no_prompt_carrier(
                    ROOT,
                    str(project),
                    source,
                    "EXECUTE-PROMPT.md",
                    detected["candidate_id"],
                    ["decision-log.json#event-decision"],
                )
            self.assertEqual(result["status"], "confirmed_none")
            requirements = json.loads((project / "content-requirements.json").read_text(encoding="utf-8"))
            context = requirements["prompt_delivery_context"]
            self.assertEqual(context["content_origin"], "existing_project")
            self.assertEqual(context["existing_public_urls"], ["https://docs.example.com/prompt"])
            self.assertTrue(context["external_hosting_authorized"])
            self.assertEqual(context["carrier_confirmation"]["status"], "confirmed_none")

    def test_eligibility_change_produces_a_new_candidate_id(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, source, prompt, head = self.fixture(temporary)
            with patch("content_publishing.carriers._github_visibility", return_value=("private", "fixture-private")), patch(
                "content_publishing.carriers._remote_branch_commit", return_value=(head, "fixture-remote")
            ), patch("content_publishing.carriers._public_prompt_bytes", return_value=(None, "raw-github:http-404")):
                private_candidate = detect_prompt_carrier(ROOT, str(project), source, "EXECUTE-PROMPT.md")
            patches = self.verified_network(prompt, head)
            with patches[0], patches[1], patches[2]:
                public_candidate = detect_prompt_carrier(ROOT, str(project), source, "EXECUTE-PROMPT.md")
            self.assertNotEqual(private_candidate["candidate_id"], public_candidate["candidate_id"])

    def test_public_raw_prompt_can_verify_access_when_api_is_rate_limited(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, source, prompt, head = self.fixture(temporary)
            with patch("content_publishing.carriers._github_visibility", return_value=("unknown", "github-api:http-403")), patch(
                "content_publishing.carriers._remote_branch_commit", return_value=(head, "fixture-remote")
            ), patch("content_publishing.carriers._public_prompt_bytes", return_value=(prompt, "fixture-raw")):
                detected = detect_prompt_carrier(ROOT, str(project), source, "EXECUTE-PROMPT.md")
            self.assertEqual(detected["eligibility"], "eligible")
            self.assertEqual(detected["visibility"], "public")
            self.assertEqual(detected["checks"]["public_repository"], "verified")

    def test_remote_credentials_are_never_returned(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, source, prompt, head = self.fixture(temporary)
            subprocess.run(
                ["git", "remote", "set-url", "origin", "https://user:secret-token@github.com/example/prompt-project.git?token=secret-token"],
                cwd=source,
                check=True,
            )
            patches = self.verified_network(prompt, head)
            with patches[0], patches[1], patches[2]:
                detected = detect_prompt_carrier(ROOT, str(project), source, "EXECUTE-PROMPT.md")
            serialized = json.dumps(detected, ensure_ascii=False)
            self.assertNotIn("secret-token", serialized)
            self.assertEqual(detected["slug"], "example/prompt-project")
            self.assertEqual(detected["remote_url"], "https://github.com/example/prompt-project.git")

    def test_private_or_unverified_repository_cannot_be_confirmed(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, source, prompt, head = self.fixture(temporary)
            with patch("content_publishing.carriers._github_visibility", return_value=("private", "fixture-private")), patch(
                "content_publishing.carriers._remote_branch_commit", return_value=(head, "fixture-remote")
            ), patch("content_publishing.carriers._public_prompt_bytes", return_value=(None, "raw-github:http-404")):
                detected = detect_prompt_carrier(ROOT, str(project), source, "EXECUTE-PROMPT.md")
            self.assertEqual(detected["eligibility"], "ineligible")
            with patch("content_publishing.carriers._github_visibility", return_value=("private", "fixture-private")), patch(
                "content_publishing.carriers._remote_branch_commit", return_value=(head, "fixture-remote")
            ), patch("content_publishing.carriers._public_prompt_bytes", return_value=(None, "raw-github:http-404")), self.assertRaisesRegex(
                CommandError, "尚未通过公开性"
            ):
                confirm_prompt_carrier(
                    ROOT,
                    str(project),
                    source,
                    "EXECUTE-PROMPT.md",
                    detected["candidate_id"],
                    ["decision-log.json#event-decision"],
                )


if __name__ == "__main__":
    unittest.main()
