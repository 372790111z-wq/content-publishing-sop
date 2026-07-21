# 从这里开始

这是一套跨机器、跨 IDE 的后置内容沉淀、完整性校验与发布治理工具。它不参与需求开发，也不统计完成了多少需求。只有一个需求已经实施、验收，并被用户判断为值得复用后，才把完整过程整理成文章、图片和视频，并在发布前证明内容没有漏项。

第一次接入的 Agent 可以先读根目录 `tool-manifest.json` 获取机器可读的定位、入口、已实现能力和明确不承诺的能力，再按本文顺序读取真源协议。

先区分能力边界：CLI、MCP、校验器、授权与发布回执已经可执行；真实平台连接器仍需对应平台的官方授权、已登录浏览器或人工操作。仓库不会把“接口已定义”写成“平台已发布”。

第一次使用、需要本机操作步骤或准备换电脑时，先看 `USAGE-GUIDE.md`。它包含从零开始的本机教程、跨机迁移、各 IDE 启动提示词、成功标志和故障处理。

所有 IDE 先使用统一 CLI：`python3 tools/content_publishing.py doctor --deep`。安装 console script 后可直接使用 `content-publishing`。Codex 可以安装仓库内 Skill；其他 IDE 使用受冲突保护的薄适配入口或 MCP，长期规则仍只维护在本工作台。

第一次打开仓库时，`projects/registry.json` 已登记完全虚构的 `examples/quickstart-demo`。重建并打开看板即可看到最终结构，不需要先创建真实项目。

## 如果你是人

1. 先正常完成并验收需求；未完成的需求不进入本工作台。
2. 当你认为它值得复用时，明确说“把这次过程整理成文章”。
3. 此时运行 `content-publishing new-project ...`，事务化创建项目并登记；命令不会编造讨论或验收事实。
4. 打开 `dashboard/index.html` 查看内容项目、内容门禁和平台发布状态；看板不展示需求完成数量。
5. 先运行默认校验，再计算并登记 release digest；写成 frozen 后运行 `--strict` 做冻结验收。
6. 向你展示最终内容、媒体、门禁结果和目标平台。你确认内容无误后，该次确认同时生成这些平台的发布 grant，并直接进入发布执行，不再二次询问。
7. 使用 `grant`、`prepare` 和 `settle` 完成授权、pending intent 与回执事务；只有平台动作取得证据并完成结算后，才把状态写成已发布或失败。

## 如果你是 Agent

按这个顺序读取，不要跳步：

1. `AGENT-PROTOCOL.md`
2. `SOURCE_OF_TRUTH.md`
3. `SOP.md`
4. 目标项目的 `project-manifest.json`
5. `decision-log.json`
6. `content-requirements.json`
7. `handoff-state.json` 与 `publication-receipts.json`
8. `projects/registry.json`
9. 当前 IDE 对应的 `adapters/<ide>/README.md`
10. `EXECUTE-PROMPT.md`

先验证 `source_work`：来源必须是已经验收的需求，且用户明确提出内容沉淀的时间不得早于需求验收。条件不成立时停止，不得提前创建文章项目。条件成立后再运行能力检测和内容校验。缺少工具时使用适配层中的降级步骤，不得把“工具不存在”“作者后台保存成功”或“本地文件存在”写成内容已经交付。

## 五分钟快速检查

```bash
python3 tools/capability_check.py
python3 tools/content_publishing.py version
python3 tools/content_publishing.py doctor --deep
python3 tools/build_dashboard.py
python3 tools/build_dashboard.py --check
python3 tools/portability_check.py
cd validator
python3 -m unittest -v test_validator.py
```

仓库默认不包含个人内容项目，只包含脱敏示例。看板应能重建并保持 `current`，可移植性检查和校验器测试应通过。给项目使用 `--strict` 时，真实警告会阻断；使用 `--action public_publish --platform <平台>` 时，没有当次 grant 或平台已经发布也会阻断，这是预期结果。`--for-publish` 是 `--action public_publish` 的兼容别名，但同样必须给 `--platform`。

基础校验器兼容 Python 3.9+，不依赖第三方包。图片深度检查、视频信号检查和浏览器自动化属于增强能力。

## 完成的定义

只有下面七层同时成立，内容项目才能标记为已完成：

- 文件层：真源、文章、图片、视频和提示词真实存在。
- 来源层：文章来源于已经完成并验收的需求，且用户明确要求沉淀内容。
- 内容层：讨论过程的九阶段映射、最终方案和完整提示词没有遗漏。
- 发布层：目标平台状态真实，审核中不写成已公开。
- 授权层：冻结摘要、范围化一次性授权和逐平台回执能够互相对应。
- 读者层：普通读者能从公开入口看到正文、图片并拿到完整提示词，且验收有证据。
- 复盘层：到期指标已采集或已用证据说明不可用，看板与真源一致。

## 创建第一个项目

使用 `content-publishing new-project <project-id> --help` 创建骨架并登记。填入已经完成并验收的来源需求、全过程、最终交付物和完整一键提示词，再运行门禁。项目内容默认属于本地资料；上传前应单独做隐私和授权检查。

项目自身升级使用 `content-publishing update`；外部 CLI 检测和定向升级使用 `content-publishing deps ...`。二者不会互相隐式调用。

仅仅克隆或打开工作台不会自动安装 Skill、发布内容或写入任何 IDE 的全局规则目录；这些动作都需要显式执行。
