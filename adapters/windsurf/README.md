# Windsurf 适配

Windsurf 可以读取仓库中的 `AGENTS.md`，也支持工作区 `.windsurf/rules/*.md`。优先使用本目录提供的薄 `AGENTS.md`，因为它也方便其他 Agent 复用；如果项目已有规则，只合并入口。

不要依赖自动生成的 Memory 作为真源。规则只负责指向工作台，项目状态继续存放在 JSON 和 Markdown 中。

官方说明：https://docs.windsurf.com/zh/windsurf/cascade/memories
