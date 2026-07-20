# Codex 适配

1. 把工作台目录放在项目根下，命名为 `content-publishing-sop`。
2. 检查项目根是否已有 `AGENTS.md`。
3. 没有时，可以复制本目录的 `AGENTS.md`；已有时只合并不重复的薄入口，不覆盖原规则。
4. 新建任务后让 Codex 读取 `content-publishing-sop/START-HERE.md`。
5. 最终内容与明确平台清单在当前任务中一次确认后直接发布，不再重复确认；危险动作仍按核心协议单独确认。

不要把这个项目适配器写入 `~/.codex/AGENTS.md`。除非用户单独要求全局同步，并完成远端真源、查重和冲突检查。
