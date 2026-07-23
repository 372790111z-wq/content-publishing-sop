window.CONTENT_SOP_DATA = {
  "dashboard_schema_version": "1.4",
  "schema_version": "1.0",
  "generated_at": "2026-07-22T10:49:53.490935+00:00",
  "source_digest": "2ceba500d5c8e1b7c395c357c407a5906e5f396b17ca09ae5b6af8e75477bbbc",
  "registry": "../projects/registry.json",
  "summary": {
    "projects": 0,
    "examples": 1,
    "project_statuses": {
      "content_generation": 1
    },
    "platform_statuses": {
      "not_started": 1
    },
    "metrics": {
      "platform_statuses": {
        "not_collected": 1
      },
      "published_platforms": 0,
      "complete_published_platforms": 0
    }
  },
  "projects": [
    {
      "kind": "example",
      "project_id": "quickstart-demo",
      "title": "第一次运行的完整示例",
      "summary": "用虚构需求展示从验收到内容沉淀、校验和待发布状态的完整数据结构。",
      "status": "content_generation",
      "updated_at": "2026-07-02T10:00:00+08:00",
      "source_work": {
        "source_type": "completed_requirement",
        "title": "为团队建立可复用的发布检查清单",
        "status": "accepted",
        "accepted_at": "2026-07-01T18:00:00+08:00",
        "acceptance_evidence": [
          "decision-log.json#event-acceptance"
        ],
        "reuse_reason": "这段过程展示了如何把已完成需求转成可验证的内容资产，适合其他团队复用。",
        "content_requested_at": "2026-07-02T09:00:00+08:00",
        "request_evidence": [
          "decision-log.json#event-content-request"
        ]
      },
      "authorization": {
        "local_changes": false,
        "public_publish": false,
        "delete_or_overwrite": false,
        "external_sync": false,
        "note": "示例没有发布授权。",
        "grants": []
      },
      "active_grants": [],
      "release": {
        "status": "draft",
        "version": "v0",
        "frozen_at": null,
        "release_digest": null,
        "decision_sequence": null,
        "invalidated_at": null,
        "invalidated_reason": null
      },
      "handoff_state": {
        "schema_version": "1.0",
        "project_id": "quickstart-demo",
        "updated_at": "2026-07-02T10:00:00+08:00",
        "current_stage": "content_generation",
        "last_success": "完成脱敏母稿和完整提示词",
        "verified_evidence": [
          "content/master.md",
          "content/canonical-prompt.md"
        ],
        "pending_items": [
          "这是示例，不执行真实发布"
        ],
        "blockers": [],
        "next_action": "创建自己的内容项目",
        "decisions_required": [],
        "last_validation": {
          "status": "unknown",
          "at": null,
          "report": null
        },
        "metrics": {
          "checkpoint": null,
          "status": "not_due",
          "evidence": []
        },
        "dashboard": {
          "generated_at": null,
          "status": "unknown"
        },
        "active_grant_ids": []
      },
      "validation": {
        "status": "unknown",
        "summary": {},
        "gates": []
      },
      "editorial": {
        "author_voice_status": "verified",
        "author_voice_mode": "project_context",
        "platform_profiles": 1,
        "required_reviews": 1,
        "verified_reviews": 1
      },
      "counts": {
        "decisions": 10,
        "deliverables": 1,
        "images": 0,
        "videos": 0,
        "platforms": 1,
        "receipts": 0
      },
      "decisions": [
        {
          "id": "event-original",
          "sequence": 1,
          "at": "2026-06-28T10:00:00+08:00",
          "stage": "original_need",
          "summary": "团队需要一份发布检查清单。",
          "details": "检查内容、平台和公开结果。",
          "evidence": [
            "content/master.md#原始需求"
          ],
          "supersedes": []
        },
        {
          "id": "event-problem",
          "sequence": 2,
          "at": "2026-06-28T14:00:00+08:00",
          "stage": "new_problem",
          "summary": "普通清单无法证明内容没有漏项。",
          "details": "尤其容易遗漏完整提示词。",
          "evidence": [
            "content/master.md#新发现的问题"
          ],
          "supersedes": []
        },
        {
          "id": "event-attempt",
          "sequence": 3,
          "at": "2026-06-29T09:00:00+08:00",
          "stage": "attempt",
          "summary": "先尝试只维护一篇 Markdown。",
          "details": "无法表示平台状态和发布回执。",
          "evidence": [
            "content/master.md#尝试过的方案"
          ],
          "supersedes": []
        },
        {
          "id": "event-feedback",
          "sequence": 4,
          "at": "2026-06-29T15:00:00+08:00",
          "stage": "user_feedback",
          "summary": "用户要求过程、媒体和完整提示词都能检查。",
          "details": "并要求其他 IDE 能恢复。",
          "evidence": [
            "content/master.md#用户反馈"
          ],
          "supersedes": []
        },
        {
          "id": "event-decision",
          "sequence": 5,
          "at": "2026-06-30T10:00:00+08:00",
          "stage": "decision",
          "summary": "采用单一真源加确定性门禁。",
          "details": "平台稿只作为派生物。",
          "evidence": [
            "content/master.md#最终决定"
          ],
          "supersedes": [
            "event-attempt"
          ]
        },
        {
          "id": "event-rationale",
          "sequence": 6,
          "at": "2026-06-30T11:00:00+08:00",
          "stage": "rationale",
          "summary": "可验证状态比模糊的完成描述更可靠。",
          "details": "摘要、授权和回执可以互相校验。",
          "evidence": [
            "content/master.md#决定理由"
          ],
          "supersedes": []
        },
        {
          "id": "event-result",
          "sequence": 7,
          "at": "2026-07-01T16:00:00+08:00",
          "stage": "implementation_result",
          "summary": "完成模板、校验器和本地看板。",
          "details": "示例只展示内容治理，不伪装真实发布。",
          "evidence": [
            "content/master.md#实施结果"
          ],
          "supersedes": []
        },
        {
          "id": "event-acceptance",
          "sequence": 8,
          "at": "2026-07-01T18:00:00+08:00",
          "stage": "acceptance_evidence",
          "summary": "结构校验和可移植性检查通过。",
          "details": "需求被明确验收。",
          "evidence": [
            "content/master.md#验收证据"
          ],
          "supersedes": []
        },
        {
          "id": "event-unresolved",
          "sequence": 9,
          "at": "2026-07-01T18:10:00+08:00",
          "stage": "unresolved",
          "summary": "真实平台仍需要登录、授权和连接器。",
          "details": "示例保持未发布状态。",
          "evidence": [
            "content/master.md#未解决问题"
          ],
          "supersedes": []
        },
        {
          "id": "event-content-request",
          "sequence": 10,
          "at": "2026-07-02T09:00:00+08:00",
          "stage": "user_feedback",
          "summary": "用户在验收后要求把过程整理成可复用示例。",
          "details": "内容流程由此正式开始。",
          "evidence": [
            "content/master.md#为什么形成这篇内容"
          ],
          "supersedes": []
        }
      ],
      "platforms": [
        {
          "platform": "example",
          "status": "not_started",
          "content_path": "content/master.md",
          "public_url": null,
          "published_at": null,
          "release_digest": null,
          "reader_validation": "unknown",
          "prompt_delivery": "full_text",
          "evidence": [],
          "blocker": null
        }
      ],
      "metrics": {},
      "metrics_history": {},
      "metrics_trends": {},
      "metrics_summary": {
        "platform_statuses": {
          "not_collected": 1
        },
        "published_platforms": 0,
        "complete_published_platforms": 0,
        "latest_at": null
      },
      "links": {
        "project": "../examples/quickstart-demo",
        "manifest": "../examples/quickstart-demo/project-manifest.json",
        "handoff": "../examples/quickstart-demo/HANDOFF.md"
      }
    }
  ]
};
