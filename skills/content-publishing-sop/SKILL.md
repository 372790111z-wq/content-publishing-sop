---
name: content-publishing-sop
description: Turn a completed and accepted requirement into a complete, reusable content package; calibrate the user's voice; create genuinely different platform versions; validate reader language, AI-writing traces, articles/images/video/canonical prompts; publish after one final content-and-platform confirmation; verify public delivery; collect metrics; and maintain the dashboard. Use when the user asks to整理成文章、沉淀经验、去AI味、按平台改写、生成图文或视频、全平台发布、修复已发布内容、检查完整提示词、恢复内容发布项目、查看发布看板，或在另一台机器/IDE 继续内容生产与发布。
---

# Content Publishing SOP

Use the workspace workbench as the only source of truth. Keep this skill as a thin launcher and orchestrator; never copy the full SOP into the installed skill or invent a second workflow.

When `<workbench>/tools/content_publishing.py` is available, prefer its transactional commands (or the bundled MCP server) for project creation, release freezing, grants, pending intents and receipt settlement. Do not reimplement those mutations ad hoc in the skill.

## Locate the workbench

Run:

```bash
python3 <skill-dir>/scripts/find_workbench.py --start <current-workspace>
```

Use `selected` only when the result is `found`. If the result is `ambiguous`, show the candidates and ask which workbench to use. If it is `not_found`, stop and ask the user to clone, attach, extract, or point to the content publishing workbench; do not reconstruct the workbench from memory.

After locating it, refer to it as `<workbench>`.

## Read only what the task needs

Always read these files completely before acting:

1. `<workbench>/START-HERE.md`
2. `<workbench>/AGENT-PROTOCOL.md`
3. `<workbench>/SOURCE_OF_TRUTH.md`
4. `<workbench>/SOP.md`
5. `<workbench>/EDITORIAL-QUALITY.md`

For a new or resumed content project, also read:

1. `<workbench>/projects/registry.json`
2. the target `project-manifest.json`
3. every source file referenced by the manifest
4. `HANDOFF.md` and `handoff-state.json`

Read `<workbench>/USAGE-GUIDE.md` when the user asks how to use, install, migrate, or troubleshoot the system. Read `<workbench>/INSTALL.md` only when capability installation or tool boundaries matter. Read the matching `<workbench>/adapters/<host>/README.md` when configuring another IDE.

## Enforce the entry boundary

Start a content project only when all conditions are true:

- the source requirement is implemented and accepted;
- acceptance has resolvable evidence;
- the user explicitly asks to turn the completed work into reusable content;
- the content request occurs after acceptance;
- the reuse value is recorded.

Write these facts to `project-manifest.json.source_work`. If the requirement is unfinished, exit this skill workflow and continue the original requirement task. Do not create a content project, count completed requirements, or write a success story early. Tell the user when this boundary pauses the content workflow.

## Choose the operation

### Start a new content project

1. Copy `<workbench>/templates/project/` to `<workbench>/projects/<project-id>/`.
2. Reconstruct the full completed process in `decision-log.json`.
3. Bind acceptance and content-request event IDs in `source_work`.
4. Create the master article and the single canonical prompt.
5. Run the read-only `content-publishing carrier detect` only against the explicitly identified source project. Show the complete candidate and require a separate human decision before `carrier confirm` or `carrier confirm-none`; never write, upload, commit, push, or use a detected repository automatically.
6. Record `prompt_delivery_context`: keep factual content origin separate from the human GitHub-carrier decision, preserve the confirmed origin whether the human accepts or declines a candidate, prefer full text or at most two prompt cards for short prompts, reuse a confirmed direct public URL for long prompts, and never create GitHub or another public host without explicit authorization.
7. Establish `editorial-policy.json`: use 3–5 approved writing samples when available; otherwise record the weaker evidence source and its limitation.
8. Generate each platform version from the same facts through its own profile; never fabricate personal experience to make copy sound human.
9. Complete `editorial-reviews.json` for every required text deliverable and bind each review to the content and policy SHA-256.
10. Register the project in `projects/registry.json`.
11. Run the default validator and report evidence gaps before producing publication claims.

### Resume an existing project

1. Restore state from the manifest, handoff files, receipts, platform status, metrics, and latest validation report.
2. Report the current stage, frozen digest, active grant, pending intents, blockers, and next smallest action.
3. Reconcile any `unknown` pending intent against the external platform before retrying.

### Review or repair content

1. Compare the decision log, story coverage, deliverables, media, canonical prompt, author-voice evidence, platform profiles and per-deliverable editorial reviews.
2. Repair the source of truth first, then regenerate derivatives.
3. Use targeted repair for isolated writing traces. If the recorded pattern/category density and uniform structure reach the policy threshold, rebuild the structure from verified facts instead of replacing words.
4. Invalidate the previous release after any publication-content or editorial-policy change.
5. Re-run validation and freeze a new digest before asking for final review.

### Publish or update

1. Show the final article, images, video, complete canonical prompt, validation result, and explicit platform list together.
2. Treat the user's “确认 / 内容没问题 / 可以了” as one confirmation only when that final content and platform list are visible.
3. For first publication or content updates, create a scoped one-time grant with `approval_kind=content_and_platforms_confirmed` and enter publication without asking “是否发布” again.
4. Validate the complete platform batch before any external call.
5. Create all pending intents before execution, settle each receipt, then consume the grant.
6. Perform reader-view postflight verification and record public evidence.

Do not infer platform scope when the platform list is missing. Require separate confirmation for deletion, takedown, overwrite, unlisted external sync, copyright/commercial agreements, login, CAPTCHA, MFA, payment, or disclosure of private information. Explicitly tell the user when one of these boundaries pauses execution.

Do not require a repository for ordinary experience-sharing articles. Creating or uploading to GitHub, Gist, cloud storage, or another public host is an external publication action unless the project already has an approved public carrier; obtain explicit authorization before doing it.

## Run deterministic gates

From `<workbench>` use:

```bash
python3 tools/content_publishing.py editorial-init <project>
python3 validator/validate.py --project <project>
python3 tools/release_digest.py --project <project>
python3 validator/validate.py --project <project> --strict
python3 validator/validate.py --project <project> --action <action> --platform <platform>
python3 validator/validate.py --project <project> --postflight
python3 validator/validate.py --project <project> --require-metrics
python3 tools/build_dashboard.py
python3 tools/build_dashboard.py --check
```

Treat nonzero exits as gates, not cosmetic failures. Diagnose safe fixes; never edit generated dashboard data to hide a source problem.

Project self-update and external dependency update are separate operations. `content-publishing update` only manages the tool checkout. `content-publishing deps` may inspect external CLIs, but an actual named dependency upgrade still requires explicit user authorization and `--apply`.

## Keep the dashboard content-only

Track only content projects, articles, media, publication status, reader verification, receipts, and performance metrics. Show the completed requirement only as provenance for its derived content. Never add completed-requirement counts, development progress, or acceptance throughput to the dashboard.

Use `null`/`unknown` for unavailable metrics. Use numeric `0` only with evidence that the platform value is truly zero.

## Handle machine and IDE migration

On a new machine:

1. Clone the approved private repository, or download a source snapshot from that repository.
2. Verify the Git remote, branch, and selected commit before continuing.
3. Restore private content projects separately only after privacy and authorization review.
4. Re-run capability detection; never reuse the old machine's capability report.
5. Re-read the project registry and handoff state.
6. Re-run default validation, dashboard rebuild/check, and portability check.
7. Require the user to re-establish login, CAPTCHA, MFA, local permissions, plugins, and secrets as needed.

Use IDE adapters for non-Codex hosts. Do not install this Codex skill as a substitute for Claude, Cursor, Windsurf, VS Code, or Grok adapter rules.

## Finish with evidence

Report:

- source requirement and acceptance evidence;
- content stage and completed deliverables;
- author-voice evidence, platform-profile bindings and editorial-review status;
- canonical prompt status;
- release version and digest;
- validation results;
- platform, receipt, and reader-verification states;
- metric checkpoint and dashboard freshness;
- true unknowns and remaining human steps.

Never claim public delivery from a local file, editor preview, or creator-backend save alone.
