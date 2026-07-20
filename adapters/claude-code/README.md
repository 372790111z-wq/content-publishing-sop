# Claude Code 适配

Claude Code 会读取项目级 `CLAUDE.md`，并支持通过 `@path` 导入文件。建议把工作台放在项目根下，再复制本目录的 `CLAUDE.md`；如果项目已经有同名文件，先合并，不覆盖。

运行 `/memory` 可以检查实际加载的规则。规则加载后，再执行能力检测和可移植性验收。

官方说明：https://docs.anthropic.com/zh-CN/docs/claude-code/memory
