#!/usr/bin/env python3

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from integrity import compute_release_digest
from validate import REQUIRED_STAGES, validate


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class ValidatorTests(unittest.TestCase):
    def freeze(self, project: Path) -> str:
        manifest_path = project / "project-manifest.json"
        manifest = read_json(manifest_path)
        requirements = read_json(project / "content-requirements.json")
        digest = compute_release_digest(project, manifest, requirements)
        manifest["release"] = {
            "status": "frozen",
            "version": "v1",
            "frozen_at": "2026-07-20T00:00:00+08:00",
            "release_digest": digest,
            "decision_sequence": 9,
            "invalidated_at": None,
            "invalidated_reason": None,
        }
        write_json(manifest_path, manifest)
        return digest

    def make_project(self, root: Path) -> Path:
        project = root / "fixture"
        (project / "content").mkdir(parents=True)
        prompt = "第一行\n关键锚点\n最后一行\n"
        prompt_path = project / "content" / "canonical-prompt.md"
        prompt_path.write_text(prompt, encoding="utf-8")
        story = "\n".join(f"ANCHOR-{stage}" for stage in REQUIRED_STAGES)
        (project / "content" / "master.md").write_text("# 完整故事\n\n" + story + "\n\n" + prompt, encoding="utf-8")
        write_json(project / "project-manifest.json", {
            "schema_version": "1.2",
            "project_id": "fixture-project",
            "title": "Fixture",
            "summary": "validator fixture",
            "status": "ready_to_publish",
            "created_at": "2026-07-20T00:00:00+08:00",
            "updated_at": "2026-07-20T00:00:00+08:00",
            "owner": "test",
            "source_work": {
                "source_type": "completed_requirement",
                "title": "已完成测试需求",
                "status": "accepted",
                "accepted_at": "2026-07-19T00:00:00+08:00",
                "acceptance_evidence": ["decision-log.json#event-08"],
                "reuse_reason": "该需求适合作为可复用测试内容",
                "content_requested_at": "2026-07-20T00:00:00+08:00",
                "request_evidence": ["decision-log.json#event-09"],
            },
            "files": {
                "decision_log": "decision-log.json",
                "content_requirements": "content-requirements.json",
                "platform_status": "platform-status.json",
                "metrics": "metrics.json",
                "checksums": "checksums.json",
                "master_content": "content/master.md",
                "handoff": "HANDOFF.md",
                "handoff_state": "handoff-state.json",
                "publication_receipts": "publication-receipts.json",
            },
            "authorization": {
                "local_changes": True,
                "public_publish": False,
                "delete_or_overwrite": False,
                "external_sync": False,
                "note": "legacy booleans are informational only",
                "grants": [],
            },
            "release": {
                "status": "draft", "version": "v0", "frozen_at": None,
                "release_digest": None, "decision_sequence": None,
                "invalidated_at": None, "invalidated_reason": None,
            },
            "last_validation": {"status": "pending", "at": None, "report": None},
        })
        events = []
        coverage = []
        for index, stage in enumerate(REQUIRED_STAGES, start=1):
            event_id = "event-%02d" % index
            events.append({
                "id": event_id,
                "sequence": index,
                "stage": stage,
                "summary": stage,
                "evidence": [f"content/master.md#ANCHOR-{stage}"],
            })
            coverage.append({
                "stage": stage,
                "master_anchors": [f"ANCHOR-{stage}"],
                "decision_event_ids": [event_id],
            })
        write_json(project / "decision-log.json", {
            "schema_version": "1.1",
            "project_id": "fixture-project",
            "required_stages": REQUIRED_STAGES,
            "events": events,
        })
        write_json(project / "content-requirements.json", {
            "schema_version": "1.1",
            "project_id": "fixture-project",
            "required_story_stages": REQUIRED_STAGES,
            "story_coverage": coverage,
            "canonical_prompt": {
                "required": True,
                "path": "content/canonical-prompt.md",
                "sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                "bytes": len(prompt.encode("utf-8")),
                "characters": len(prompt),
                "first_line": "第一行",
                "last_line": "最后一行",
                "anchors": ["关键锚点"],
            },
            "deliverables": [{
                "id": "master",
                "kind": "master",
                "path": "content/master.md",
                "required": True,
                "prompt_delivery": "full_text",
                "platform": None,
            }],
            "prompt_card_sets": [],
            "media": {"images": [], "videos": []},
        })
        write_json(project / "platform-status.json", {
            "schema_version": "1.1",
            "project_id": "fixture-project",
            "platforms": [{
                "platform": "example",
                "status": "ready",
                "content_path": "content/master.md",
                "public_url": None,
                "published_at": None,
                "release_digest": None,
                "reader_validation": "unknown",
                "prompt_delivery": "full_text",
                "evidence": [],
                "blocker": None,
            }],
        })
        write_json(project / "metrics.json", {
            "schema_version": "1.1",
            "project_id": "fixture-project",
            "collection_plan": {
                "mode": "hybrid",
                "timezone": "Asia/Shanghai",
                "checkpoints": [{"id": "first-review", "due_at": "2020-01-01T00:00:00Z", "required": True}],
                "last_attempt_at": None,
                "next_due_at": None,
            },
            "snapshots": [],
        })
        write_json(project / "checksums.json", {
            "algorithm": "SHA-256",
            "generated_at": "2026-07-20",
            "files": {"content/canonical-prompt.md": hashlib.sha256(prompt.encode("utf-8")).hexdigest()},
        })
        (project / "HANDOFF.md").write_text("# HANDOFF\n", encoding="utf-8")
        write_json(project / "handoff-state.json", {
            "schema_version": "1.0",
            "project_id": "fixture-project",
            "updated_at": "2026-07-20T00:00:00+08:00",
            "current_stage": "preflight",
            "last_success": "内容已冻结",
            "verified_evidence": ["validation-report.json"],
            "pending_items": [],
            "blockers": [],
            "next_action": "等待授权",
            "decisions_required": [],
            "last_validation": {"status": "pending", "at": None, "report": None},
            "metrics": {"checkpoint": "first-review", "status": "not_due", "evidence": []},
            "dashboard": {"generated_at": None, "status": "unknown"},
            "active_grant_ids": [],
        })
        write_json(project / "publication-receipts.json", {
            "schema_version": "1.0", "project_id": "fixture-project", "receipts": [],
        })
        self.freeze(project)
        return project

    def publish_platform(self, project: Path, evidence=True) -> None:
        data = read_json(project / "platform-status.json")
        data["platforms"][0].update({
            "status": "published",
            "public_url": "https://example.com/article",
            "published_at": "2026-07-20T12:00:00+08:00",
            "release_digest": None,
            "reader_validation": "verified",
            "evidence": ["https://example.com/article"] if evidence else [],
        })
        write_json(project / "platform-status.json", data)

    def add_valid_grant(self, project: Path, action="public_publish") -> None:
        path = project / "project-manifest.json"
        manifest = read_json(path)
        digest = manifest["release"]["release_digest"]
        manifest["authorization"]["grants"].append({
            "id": "grant-001",
            "action": action,
            "approval_kind": {
                "public_publish": "content_and_platforms_confirmed",
                "update_publication": "content_and_platforms_confirmed",
                "delete_publication": "destructive_action_confirmed",
                "external_sync": "external_sync_confirmed",
            }[action],
            "platforms": ["example"],
            "release_digest": digest,
            "granted_at": "2026-07-20T00:00:00Z",
            "expires_at": "2099-01-01T00:00:00Z",
            "status": "active",
            "consumed_at": None,
            "evidence": "用户确认",
            "receipt_ids": [],
        })
        write_json(path, manifest)
        handoff = read_json(project / "handoff-state.json")
        handoff["active_grant_ids"] = ["grant-001"]
        write_json(project / "handoff-state.json", handoff)

    def test_valid_content_passes_default_mode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = validate(self.make_project(Path(directory)))
            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["summary"]["errors"], 0)

    def test_content_project_requires_an_accepted_source_requirement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            manifest = read_json(project / "project-manifest.json")
            manifest["source_work"]["status"] = "implementation"
            write_json(project / "project-manifest.json", manifest)
            result = validate(project)
            self.assertTrue(any(issue["code"] == "source_work.not_completed" for issue in result["issues"]))

    def test_content_project_rejects_requirement_lifecycle_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            manifest = read_json(project / "project-manifest.json")
            manifest["status"] = "implementation"
            write_json(project / "project-manifest.json", manifest)
            result = validate(project)
            self.assertTrue(any(issue["code"] == "manifest.schema" for issue in result["issues"]))

    def test_content_request_cannot_precede_requirement_acceptance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            manifest = read_json(project / "project-manifest.json")
            manifest["source_work"]["content_requested_at"] = "2026-07-18T00:00:00+08:00"
            write_json(project / "project-manifest.json", manifest)
            result = validate(project)
            self.assertTrue(any(issue["code"] == "source_work.trigger_order" for issue in result["issues"]))

    def test_source_evidence_fragment_must_exist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            manifest = read_json(project / "project-manifest.json")
            manifest["source_work"]["request_evidence"] = ["decision-log.json#missing-event"]
            write_json(project / "project-manifest.json", manifest)
            result = validate(project)
            self.assertTrue(any(issue["code"] == "source_work.request_evidence" for issue in result["issues"]))

    def test_publish_without_scoped_authorization_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            manifest = read_json(project / "project-manifest.json")
            manifest["authorization"]["public_publish"] = True
            write_json(project / "project-manifest.json", manifest)
            result = validate(project, for_publish=True, platforms=["example"])
            self.assertEqual(result["status"], "blocked")
            self.assertTrue(any(issue["code"] == "authorization.missing_grant" for issue in result["issues"]))

    def test_publish_with_current_scoped_grant_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            self.add_valid_grant(project)
            result = validate(project, actions=["public_publish"], platforms=["example"])
            self.assertEqual(result["status"], "passed")

    def test_publish_grant_must_come_from_content_and_platform_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            self.add_valid_grant(project)
            manifest = read_json(project / "project-manifest.json")
            manifest["authorization"]["grants"][0]["approval_kind"] = "destructive_action_confirmed"
            write_json(project / "project-manifest.json", manifest)
            result = validate(project, actions=["public_publish"], platforms=["example"])
            self.assertTrue(any(issue["code"] == "authorization.approval_kind" for issue in result["issues"]))
            self.assertTrue(any(issue["code"] == "authorization.missing_grant" for issue in result["issues"]))

    def test_action_without_platform_scope_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            self.add_valid_grant(project)
            result = validate(project, actions=["public_publish"])
            self.assertTrue(any(issue["code"] == "authorization.platform_scope" for issue in result["issues"]))

    def test_one_grant_can_validate_a_multi_platform_batch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            platform = read_json(project / "platform-status.json")
            second = dict(platform["platforms"][0])
            second["platform"] = "example-2"
            platform["platforms"].append(second)
            write_json(project / "platform-status.json", platform)
            self.add_valid_grant(project)
            manifest = read_json(project / "project-manifest.json")
            manifest["authorization"]["grants"][0]["platforms"] = ["example", "example-2"]
            write_json(project / "project-manifest.json", manifest)
            result = validate(project, actions=["public_publish"], platforms=["example", "example-2"])
            self.assertEqual(result["status"], "passed")

    def test_tampered_prompt_invalidates_release(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            (project / "content" / "canonical-prompt.md").write_text("内容被改动\n", encoding="utf-8")
            result = validate(project)
            self.assertTrue(any(issue["code"] == "prompt.sha256" for issue in result["issues"]))
            self.assertTrue(any(issue["code"] == "release.digest" for issue in result["issues"]))

    def test_verified_reader_without_evidence_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            self.publish_platform(project, evidence=False)
            result = validate(project)
            self.assertTrue(any(issue["code"] == "platforms.reader_evidence" for issue in result["issues"]))

    def test_prompt_cards_without_card_set_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            requirements = read_json(project / "content-requirements.json")
            requirements["deliverables"][0]["prompt_delivery"] = "prompt_cards"
            requirements["deliverables"][0]["platform"] = "example"
            write_json(project / "content-requirements.json", requirements)
            self.freeze(project)
            result = validate(project)
            self.assertTrue(any(issue["code"] == "prompt_cards.missing_set" for issue in result["issues"]))

    def test_missing_schema_field_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            data = read_json(project / "platform-status.json")
            del data["platforms"][0]["published_at"]
            write_json(project / "platform-status.json", data)
            result = validate(project)
            self.assertTrue(any(issue["code"] == "platforms.schema" for issue in result["issues"]))

    def test_metric_zero_without_source_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            data = read_json(project / "metrics.json")
            data["snapshots"] = [self.metric_snapshot("bad-zero", "first-review", "captured", "unknown", [])]
            write_json(project / "metrics.json", data)
            result = validate(project)
            self.assertTrue(any(issue["code"] == "metrics.source" for issue in result["issues"]))
            self.assertTrue(any(issue["code"] == "metrics.evidence" for issue in result["issues"]))

    def metric_snapshot(self, snapshot_id, checkpoint, status, source, evidence):
        captured = status in {"captured", "partial"}
        return {
            "id": snapshot_id,
            "platform": "example",
            "checkpoint": checkpoint,
            "collection_status": status,
            "captured_at": "2026-07-20T12:00:00+08:00" if captured else None,
            "attempted_at": "2026-07-20T12:00:00+08:00" if captured else None,
            "source": source,
            "evidence": evidence,
            "values": {field: (0 if captured else None) for field in (
                "views", "likes", "favorites", "comments", "shares", "follower_change"
            )},
            "error": None,
        }

    def test_due_checkpoint_cannot_be_satisfied_by_old_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            self.publish_platform(project)
            data = read_json(project / "metrics.json")
            data["collection_plan"]["checkpoints"].append({
                "id": "second-review", "due_at": "2020-01-02T00:00:00Z", "required": True,
            })
            data["snapshots"] = [self.metric_snapshot("old", "first-review", "captured", "public_page", ["https://example.com/article"])]
            write_json(project / "metrics.json", data)
            result = validate(project, require_metrics=True)
            self.assertTrue(any(issue["code"] == "metrics.checkpoint_missing" for issue in result["issues"]))

    def test_evidenced_zero_passes_required_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            self.publish_platform(project)
            data = read_json(project / "metrics.json")
            data["snapshots"] = [self.metric_snapshot(
                "captured-zero", "first-review", "captured", "public_page", ["https://example.com/article"]
            )]
            write_json(project / "metrics.json", data)
            result = validate(project, require_metrics=True)
            metric_errors = [issue for issue in result["issues"] if issue["code"].startswith("metrics.") and issue["severity"] == "error"]
            self.assertEqual(metric_errors, [])

    def test_postflight_requires_publication_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            self.publish_platform(project)
            result = validate(project, postflight=True)
            self.assertTrue(any(issue["code"] == "receipts.published_missing" for issue in result["issues"]))

    def test_duplicate_publish_is_blocked_even_with_grant(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            self.publish_platform(project)
            self.add_valid_grant(project)
            result = validate(project, actions=["public_publish"], platforms=["example"])
            self.assertTrue(any(issue["code"] == "receipts.duplicate_publish" for issue in result["issues"]))

    def test_pending_intent_blocks_retry_after_interruption(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            self.add_valid_grant(project)
            manifest = read_json(project / "project-manifest.json")
            digest = manifest["release"]["release_digest"]
            manifest["authorization"]["grants"][0]["receipt_ids"] = ["intent-001"]
            write_json(project / "project-manifest.json", manifest)
            write_json(project / "publication-receipts.json", {
                "schema_version": "1.0",
                "project_id": "fixture-project",
                "receipts": [{
                    "id": "intent-001", "platform": "example", "action": "public_publish",
                    "release_digest": digest, "grant_id": "grant-001",
                    "attempted_at": "2026-07-20T12:00:00Z", "status": "unknown",
                    "public_url": None, "external_id": None, "evidence": ["intent created"],
                }],
            })
            result = validate(project, actions=["public_publish"], platforms=["example"])
            self.assertTrue(any(issue["code"] == "receipts.pending_intent" for issue in result["issues"]))
            self.assertTrue(any(issue["code"] == "authorization.missing_grant" for issue in result["issues"]))

    def test_old_release_receipt_remains_valid_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            manifest = read_json(project / "project-manifest.json")
            old_digest = "a" * 64
            manifest["authorization"]["grants"].append({
                "id": "old-grant", "action": "public_publish", "approval_kind": "content_and_platforms_confirmed", "platforms": ["example"],
                "release_digest": old_digest, "granted_at": "2026-01-01T00:00:00Z",
                "expires_at": "2026-01-02T00:00:00Z", "status": "consumed",
                "consumed_at": "2026-01-01T00:01:00Z", "evidence": "historical authorization",
                "receipt_ids": ["old-receipt"],
            })
            write_json(project / "project-manifest.json", manifest)
            write_json(project / "publication-receipts.json", {
                "schema_version": "1.0", "project_id": "fixture-project", "receipts": [{
                    "id": "old-receipt", "platform": "example", "action": "public_publish",
                    "release_digest": old_digest, "grant_id": "old-grant",
                    "attempted_at": "2026-01-01T00:00:30Z", "status": "succeeded",
                    "public_url": "https://example.com/old", "external_id": "old", "evidence": ["old page"],
                }],
            })
            result = validate(project)
            self.assertFalse(any(issue["code"] == "receipts.release" for issue in result["issues"]))

    def test_consumed_grant_and_current_receipt_pass_postflight(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            self.add_valid_grant(project)
            manifest = read_json(project / "project-manifest.json")
            digest = manifest["release"]["release_digest"]
            grant = manifest["authorization"]["grants"][0]
            grant.update({
                "status": "consumed",
                "consumed_at": "2026-07-20T12:01:00Z",
                "receipt_ids": ["receipt-001"],
            })
            write_json(project / "project-manifest.json", manifest)
            handoff = read_json(project / "handoff-state.json")
            handoff["active_grant_ids"] = []
            write_json(project / "handoff-state.json", handoff)
            self.publish_platform(project)
            platform = read_json(project / "platform-status.json")
            platform["platforms"][0]["release_digest"] = digest
            write_json(project / "platform-status.json", platform)
            write_json(project / "publication-receipts.json", {
                "schema_version": "1.0", "project_id": "fixture-project", "receipts": [{
                    "id": "receipt-001", "platform": "example", "action": "public_publish",
                    "release_digest": digest, "grant_id": "grant-001",
                    "attempted_at": "2026-07-20T12:00:00Z", "status": "succeeded",
                    "public_url": "https://example.com/article", "external_id": "article",
                    "evidence": ["https://example.com/article"],
                }],
            })
            result = validate(project, postflight=True)
            self.assertEqual(result["status"], "passed")
            self.assertFalse(any(issue["code"].startswith("receipts.") and issue["severity"] == "error" for issue in result["issues"]))


if __name__ == "__main__":
    unittest.main()
