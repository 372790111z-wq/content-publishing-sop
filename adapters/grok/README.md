# Grok TUI 适配

Grok 的用户可调用 bridge 需要写入当前设备的宿主目录，并指向项目真源的绝对路径。因此仓库不会自动生成一个在别的机器上必然失效的 bridge。

默认方式：把 `adapters/generic-agent/PROMPT.md` 交给 Grok，并要求先读取工作台的 `START-HERE.md`。

需要安装成斜杠命令时：

1. 确认工作台在当前机器的最终绝对路径；
2. 检查 `~/.grok/skills/content-publishing-sop/` 是否已有不同配置；
3. 把 `SKILL.template.md` 中的占位路径替换为真实绝对路径；
4. 获得用户确认后再写入宿主目录；
5. 验证 frontmatter 含 `user_invocable: true`，并在 Grok TUI 中实际搜索命令。

未经确认不覆盖旧 bridge，也不写全局目录。
