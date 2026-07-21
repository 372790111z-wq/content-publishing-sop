# 真源与派生关系

## 真源优先级

1. `project-manifest.json`：内容项目身份、已验收来源需求 `source_work`、阶段、冻结版本、范围化授权和文件入口。
2. `decision-log.json`：需求演化和决策证据。
3. `content-requirements.json`：内容必须包含什么，以及完整提示词的真源。
4. `content/master.*`：母稿。
5. `platform-status.json`：平台稿和公开状态。
6. `publication-receipts.json`：每次外部动作的逐平台回执和幂等证据。
7. `metrics.json`：公开后的采集计划、历史快照、来源和证据。
8. `handoff-state.json`：跨机器恢复所需的机器可读当前状态。
9. `projects/registry.json`：看板纳入哪些项目的唯一清单。
10. `validation-report.json`：一次校验快照，不是真源。
11. `dashboard/data.js`：展示缓存，随时可以重建。

## 派生关系

```text
已完成并验收的需求 + 验收证据
        ↓ 用户在验收后明确要求沉淀
project-manifest.json.source_work
        ↓
decision-log.json
        ↓
母稿 + 完整提示词真源
        ↓
平台稿 / 图片 / 视频
        ↓
发布前校验报告 + frozen release digest
        ↓ 用户确认最终内容和明确平台清单
content_and_platforms_confirmed 一次性 grant
公开发布
        ↓
逐平台回执 + 公开页面验收 + metrics.json
        ↓
指标门禁
        ↓
dashboard/data.js（可重建缓存）
```

## 路径规则

- 数据文件中的路径都相对于项目目录，不使用某台机器的绝对路径。
- 使用 UTF-8、Markdown、JSON、JSON Schema 和 SHA-256。
- 资产文件名稳定后不随平台标题改变。
- 任何平台稿不得只写“完整提示词见本地文件”。
- 看板不直接编辑真源，只展示数据和证据链接。
- 看板只统计内容项目、平台发布、公开验收和效果数据；来源需求只用于单篇内容溯源，不统计完成需求数量。
- 指标快照只追加、不覆盖；没有证据的数据保持 `null`。
- 一个冻结版本由发布内容集合的 SHA-256 摘要标识；内容变化会使旧授权失效。
- 首次发布或内容更新的授权来自用户对最终内容和明确平台清单的一次确认，必须限制动作、平台、冻结摘要和有效期；旧布尔授权不构成执行权限。
- 一个外部平台动作对应一张回执；成功回执用于防止重复发布。
- `dashboard/data.js` 必须由构建脚本生成，禁止手工维护统计结果。
- 工具版本由根目录 `VERSION` 与 Git tag 标识；工具升级状态不写进个人项目 JSON。
- Browser Use、FFmpeg 等外部 CLI 的检测和升级结果属于本机能力，不得写成内容发布回执。

## 完整提示词规则

完整提示词只能有一个 canonical 文件。平台交付方式可以不同：

- 长文平台：正文内必须出现完整文本；
- 图文平台：可以使用连续高清文字图，但必须验证页码、首句、末句和哈希对应关系；
- 视频平台：简介放用途和风险边界，完整提示词必须提供普通读者可访问的交付方式；评论区不能是唯一入口；
- 任何平台：本地路径、作者后台草稿和登录后才能看的评论都不算公开交付。

## 更新顺序

先改真源，再把旧 release 标为 invalidated，重新生成派生物、校验并冻结新摘要，最后更新状态。禁止直接修平台稿后忘记回写真源，也禁止沿用旧 grant。项目、平台、指标、回执或校验状态变化后，必须重建看板并运行 `tools/build_dashboard.py --check`，确认展示缓存与真源一致。
