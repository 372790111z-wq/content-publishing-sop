# IDE 适配层

适配层只解决“这个 IDE 怎样加载规则、怎样调用能力”，不复制 SOP 的长期逻辑。

## 推荐安装布局

```text
your-project/
├── content-publishing-sop/
└── 对应 IDE 的薄规则文件
```

先把本目录整体复制为项目根下的 `content-publishing-sop/`，再按对应 README 选择是否复制规则入口。写入现有规则文件前必须查重、比较和合并，不得直接覆盖用户规则。

| IDE | 建议入口 | 无法自动加载时 |
|---|---|---|
| Codex | 项目根 `AGENTS.md` | 粘贴 `EXECUTE-PROMPT.md` |
| Claude Code | 项目根 `CLAUDE.md` | 在会话中引用 `START-HERE.md` |
| Cursor | `.cursor/rules/*.mdc` | `@START-HERE.md` 或粘贴提示词 |
| Windsurf | 项目根 `AGENTS.md` 或 `.windsurf/rules/*.md` | 粘贴提示词 |
| VS Code Agent | `.github/copilot-instructions.md` 或 `AGENTS.md` | 附加 `START-HERE.md` |
| Grok TUI | 经确认后生成 user-invocable bridge | 使用通用提示词 |
| 其他 Agent | `adapters/generic-agent/PROMPT.md` | 手工逐项执行 SOP |

适配成功的最低标准见 `PORTABILITY-TEST.md`。
