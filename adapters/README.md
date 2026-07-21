# IDE 适配层

适配层只解决“这个 IDE 怎样加载规则、怎样调用能力”，不复制 SOP 的长期逻辑。

## 推荐安装布局

```text
your-project/
├── content-publishing-sop/
└── 对应 IDE 的薄规则文件
```

优先使用统一安装命令：

```bash
content-publishing --root /path/to/content-publishing-sop install --host <host> --dest /path/to/your-project
```

Codex 的默认目标是用户 Skill 目录，因此可省略 `--dest`。安装器遇到已有不同规则会阻断；只有由本工具管理且未被用户修改的入口才能使用 `--upgrade`。不使用 CLI 时，再按对应 README 人工复制和合并。

支持 MCP 的 IDE 可以直接连接 `content-publishing mcp serve`，规则入口仍负责要求 Agent 先读取 `START-HERE.md`。

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
