# Changelog

所有重要变化记录在这里，版本遵循语义化版本。

## 0.3.0 - 2026-07-22

- 增加项目级个人表达档案和六个平台默认风格档案；
- 增加逐交付物读者语言、AI 写作痕迹、平台与媒体适配审校证据；
- 增加结构性重写阈值，阻止问题密集时只做同义词替换；
- 增加自适应提示词载体：短提示词直接交付，已有项目复用直链，无授权不新建外部载体，提示词图片默认最多两页；
- 增加公开 GitHub 提示词载体的只读检测、候选编号和独立人工确认；确认前不写入，候选变化后必须重新确认，接受或拒绝都不改变文章来源类型；匿名 raw 文件校验可在 GitHub API 限流时独立证明公开访问；
- 增加 `editorial-init` CLI/MCP 命令，为旧项目无覆盖补齐新文件；
- 把编辑策略和逐稿审校记录加入 release digest，审校记录同时绑定内容与策略 SHA-256；
- 更新跨 IDE 提示词、Skill、SOP、模板和严格校验门禁。

## 0.2.0 - 2026-07-21

- 增加统一 `content-publishing` CLI 和零依赖 MCP stdio server；
- 增加事务化 `new-project`、`freeze`、`grant`、`prepare`、`settle` 命令；
- 增加本项目 fast-forward 升级、升级后验收和回滚；
- 增加 Browser Use、FFmpeg、Playwright、Pillow 外部依赖发现和定向升级；
- 增加跨 IDE 安装器、GitHub bootstrap 和受管理文件冲突保护；
- 增加完全虚构的端到端示例和非空看板；
- 增加可选完整 JSON Schema 校验、CI、Release、License 和安全说明；
- 修复能力检测把失败 traceback 第一行误当版本号的问题。

## 0.1.0 - 2026-07-20

- 首个公开版本：SOP、模板、校验器、跨 IDE 薄适配器和本地看板。
