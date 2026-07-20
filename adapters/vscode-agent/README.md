# VS Code Agent 适配

VS Code 当前支持项目根的 `AGENTS.md`，也会自动读取 `.github/copilot-instructions.md`。本目录提供后者的薄入口；已有文件时先合并，不覆盖团队规则。

可以从 Chat 的自定义指令诊断中确认规则是否实际加载。未加载时手动附加 `START-HERE.md`。

官方说明：https://code.visualstudio.com/docs/agent-customization/custom-instructions
