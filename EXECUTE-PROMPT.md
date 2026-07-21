# 跨 IDE 一键执行提示词

把下面整段交给 Codex、Claude Code、Cursor、Windsurf、VS Code Agent 或其他能读写项目文件的 Agent。先把本工作台复制到目标机器，提示词中的 `<工作台目录>` 替换为实际相对路径或让 Agent 在当前工作区搜索 `START-HERE.md`。

```text
这是内容生产工作台的执行任务。先恢复上下文，再行动。

目标

这不是需求开发任务，而是已完成需求的后置内容沉淀任务。先证明来源需求已经实施并验收，而且我在验收后明确要求“把这次过程整理成文章/内容”；条件成立后，才把全过程整理成文章、图片和视频，完成完整性检查、多平台适配、发布、公开验收和效果跟踪。不要把已完成需求数写入看板。

一、读取顺序

1. 查找并读取 <工作台目录>/START-HERE.md。
2. 读取 AGENT-PROTOCOL.md、SOURCE_OF_TRUTH.md 和 SOP.md。
3. 读取当前 IDE 对应的 adapters/<ide>/README.md；如果没有对应适配层，使用 adapters/generic-agent/README.md。
4. 读取 projects/registry.json，找到目标内容项目，再读取 project-manifest.json、decision-log.json、content-requirements.json、platform-status.json、metrics.json、handoff-state.json 和 publication-receipts.json。
5. 不要只依赖当前聊天记录。以项目文件恢复目标、时间线、最终方案、未完成项和授权状态。
6. 先检查 project-manifest.json.source_work：来源必须是 accepted 的 completed_requirement，有可解析的验收证据；content_requested_at 不得早于 accepted_at，并且有我明确要求沉淀内容的证据。任一条件不成立时停止，不创建内容项目，也不继续写稿。
7. 如果存在 `content-publishing` 或 `tools/content_publishing.py`，项目创建、release 冻结、grant、pending intent 和回执结算优先调用统一事务命令；不要由每个 IDE 自己重写一套 JSON 状态逻辑。支持 MCP 时可以连接 `content-publishing mcp serve`，它与 CLI 共用同一核心。

二、能力检测

运行 tools/capability_check.py。分别记录文件系统、Shell、Python、图片检查、视频工程编辑、FFmpeg/ffprobe、浏览器自动化和公开发布能力。

工具状态只能是 unavailable、detected、tested、blocked 或 manual。工具存在但没有运行真实测试时，不能写 tested。

Browser Use 必须分别记录 Skill、Browser Harness CLI、Browser Use 引擎和隔离包装器，不能把版本混为一个。视频制作优先使用当前 IDE 可以直接调用的插件或 CLI；纯 GUI 工具不进入自动执行主链。ChatCut 用于工程级制作与验收，FFmpeg/ffprobe 用于导出文件级技术验收。

本项目升级与外部 CLI 升级必须分开。`content-publishing update` 只管理工具 checkout；`content-publishing deps` 只检测或定向升级明确指定的依赖。发现新版本不等于获得升级授权。

缺少工具时先使用适配层的安全替代方案。替代方案达不到原验收标准时，将对应状态写为 unknown 或 pending，并报告缺口，不得假装完成。

三、导入已完成需求的完整过程

只整理已经发生并验收的事实，不在本流程中继续实现原需求。检查 decision-log.json 是否覆盖：原始需求、新发现的问题、尝试方案、用户反馈、修改决定、决定理由、实施结果、验收证据和未解决问题。再检查 content-requirements.json.story_coverage 是否把九个阶段各映射一次到母稿文字锚点和真实事件 id。

缺失时，从现有聊天导出、文件、测试记录和用户确认中恢复；无法证实时停止补写，把缺项列给我。

四、生成并冻结内容真源

先确认最终方案已验收，再生成或更新母稿。母稿必须写清需求如何变化、哪些方案失败、为什么做出最终选择、真实实施结果、限制和复用方法。

完整一键提示词只能有一个 canonical 文件。计算 SHA-256、字节数、字符数、首句、末句和关键锚点，并写入 content-requirements.json。平台稿和提示词图片都从这个真源生成。每套提示词图片必须登记 prompt_card_sets：平台、canonical hash、总页数、连续页码、图片路径、逐页图片 SHA-256、首末句和验证证据。基础 hash 校验不等于 OCR；文字完整性证据必须如实来自生成脚本全文重组、OCR 或人工逐页核对。

完成内容后先运行默认校验，用 tools/release_digest.py 计算发布内容摘要，将 manifest.release 写为 frozen，并绑定最新 decision sequence；然后运行 strict 校验做冻结验收。之后任何内容变化都要让旧 release 和旧授权失效，重新校验、计算和冻结。

五、制作和检查图文视频

图片逐项检查文件、尺寸、顺序、来源、隐私和可读性。长提示词做成图片时必须连续编号，验证第一页和最后一页。

视频先做工程级检查，再检查最终导出文件。工程级检查包括素材、时间线、字幕、配音和指定帧；文件级检查包括音视频流、时长、编码、长静音、连续黑屏和可解码性。不能用“时间线上有音频”代替“导出文件有声音”。

六、运行发布前门禁

运行 validator/validate.py --project <目标项目目录> --strict。校验器必须先执行 schemas/ 的结构校验，再执行语义门禁。

以下任一情况必须阻止发布：来源需求未验收、没有验收后发起内容沉淀的证据、讨论过程不完整、完整提示词缺失或哈希不一致、长文没有提示词全文、提示词图片缺页、资产缺失、视频验收未完成、公开稿包含本地绝对路径或平台状态混乱。

修复后重新运行，不沿用旧报告。

七、平台适配、最终确认和发布

从母稿派生平台稿，保留事实和完整交付，不机械复制格式。最终审阅时必须同时展示：最终文章、图片、视频、完整一键提示词、每个平台的发布版本、明确的平台清单、门禁结果和已知风险。

当平台清单已经明确，我回复“确认”“内容没问题”“可以了”或同义表达时，这一次确认同时表示内容审核通过并授权直接发布到刚展示的平台，不要再问第二次“是否发布”。把确认写成一次性范围化 grant：唯一 id、`public_publish` 或 `update_publication`、`approval_kind=content_and_platforms_confirmed`、平台列表、当前 frozen release_digest、授权和过期时间、确认原文、active 状态、空 receipt_ids。不要用 public_publish=true 等旧布尔值代替授权。

若平台未列明，先补齐平台清单再确认。删除、下架、覆盖、未列明的站外同步、版权或商业协议，以及登录、验证码、MFA、付款，仍须在对应动作前单独停下确认；不能借用内容确认授权这些动作。确认后若内容或平台清单改变，原 grant 失效，必须重新展示和确认。

任何平台执行前，把本次确认的全部平台一次性送入 validator/validate.py：使用 --action <动作>，并为每个平台重复传入 --platform。只有当前 release 已冻结、grant 未过期未消费且整批范围匹配时才允许继续。平台已经存在同 release/action 成功回执时禁止重复执行；更新旧帖必须用 update_publication，不能冒充首次 public_publish。

八、公开验收

整批门禁通过后、真正调用任何平台前，先为全部目标平台写入 pending intent：receipt id、平台、动作、release digest、grant id、尝试时间、unknown 状态和 intent 证据，并一次性登记到 grant.receipt_ids。逐个平台执行并结算对应回执；全部 intent 完成或对账后，再把 grant 标为 consumed 并写入 consumed_at。若中途崩溃，恢复时先核对外部页面，禁止直接重试。成功时把 platform-status.json.release_digest 更新为回执摘要。然后打开公开页面，以普通读者视角检查正文、图片、视频和完整提示词，并把证据更新到 platform-status.json。verified 但 evidence 为空属于失败。作者后台保存成功、编辑器预览和本地文件存在都不算公开交付。

九、指标采集与内容看板闭环

读取 metrics.json.collection_plan。检查点到期时，优先使用平台 API，其次使用已获授权的创作者后台、公开页面或带证据的人工录入。每次采集追加快照，不覆盖历史；记录 collection_status、时间、来源、证据、数值和失败原因。没有读到的数据写 null，禁止猜测或填 0；数字 0 只能表示证据确认的实际零值。

到期后运行 validator/validate.py --project <目标项目目录> --require-metrics。必须按每个已发布平台和每个到期 required checkpoint 配对，旧快照不能冒充新检查点。指标或任何内容项目真源变化后，依次运行 tools/build_dashboard.py 和 tools/build_dashboard.py --check。检查失败时不得声称看板已同步。看板只记录内容项目、文章与媒体、平台发布、公开验收和效果指标，不记录已完成需求数量；来源需求只作为每篇内容的可追溯证据展示。

十、最终报告

同步 HANDOFF.md 与 handoff-state.json。报告当前阶段、冻结摘要、有效或已消费 grant、发布回执、已完成内容、证据路径、门禁结果、各平台真实状态、指标采集检查点与趋势、看板新鲜度、未知项、需要人工处理的步骤和下一步。未知指标保持 unknown。
```
