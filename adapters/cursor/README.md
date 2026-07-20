# Cursor 适配

Cursor 当前推荐把项目规则放在 `.cursor/rules/*.mdc`，旧的 `.cursorrules` 已进入兼容状态。把工作台放在项目根下，再把本目录中的 MDC 文件复制到 `.cursor/rules/`。已有同名规则时先比较和合并。

规则未自动加载时，在 Agent 对话中用 `@` 引用 `content-publishing-sop/START-HERE.md`，或直接粘贴 `EXECUTE-PROMPT.md`。

官方说明：https://docs.cursor.com/context/rules
