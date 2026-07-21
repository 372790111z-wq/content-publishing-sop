# 安装、升级与能力边界

## 1. 最小环境

- Python 3.9+；
- Git，用于可回滚的工具安装和 fast-forward 升级；
- 能读写 UTF-8、Markdown 和 JSON 的 IDE/Agent；
- 一个能打开本地 HTML 的现代浏览器。

核心校验、CLI、MCP、授权事务、回执和看板只使用 Python 标准库。

## 2. 一次安装

直接使用仓库：

```bash
git clone https://github.com/372790111z-wq/content-publishing-sop.git
cd content-publishing-sop
python3 tools/content_publishing.py doctor --deep
```

安装统一命令并创建受管理 checkout：

```bash
uv tool install 'git+https://github.com/372790111z-wq/content-publishing-sop.git'
# 没有 uv 时：python3 -m pip install --user 'git+https://github.com/372790111z-wq/content-publishing-sop.git'
content-publishing bootstrap --dest ~/content-publishing-sop --host codex
content-publishing --root ~/content-publishing-sop doctor --deep
```

`bootstrap` 不会创建真实文章、安装外部 CLI 或登录平台。目标目录已有未知内容时会阻断。

全局 `content-publishing` 只承担稳定启动；进入工作台或传入 `--root` 后，它自动转交给 checkout 内的最新版 CLI。日常项目升级不需要重新安装 console script。

## 3. IDE 入口

```bash
content-publishing --root ~/content-publishing-sop install --host codex
content-publishing --root ~/content-publishing-sop install --host cursor --dest /path/to/project
content-publishing --root ~/content-publishing-sop install --host claude-code --dest /path/to/project
```

支持 `codex`、`claude-code`、`cursor`、`windsurf`、`vscode-agent` 和 `generic-agent`。安装器只覆盖由本工具安装、带管理标记且未被用户修改的入口；已有团队规则不满足这些条件时返回 `conflict`。

检查或更新已管理入口：

```bash
content-publishing install --host codex --check
content-publishing install --host codex --upgrade
```

## 4. 本项目升级

```bash
content-publishing --root ~/content-publishing-sop update --check
content-publishing --root ~/content-publishing-sop update --dry-run
content-publishing --root ~/content-publishing-sop update
content-publishing --root ~/content-publishing-sop update --to v0.3.0
content-publishing --root ~/content-publishing-sop rollback
```

约束：

- 只管理 `content-publishing-sop` 工具 checkout；
- 工作树不干净时阻断；
- 只接受 fast-forward 目标；
- 升级后自动运行单测、CLI 集成测试、可移植性和看板新鲜度检查；
- 自动同步由本工具安装且未被用户修改的 IDE 入口；发现用户修改时保留文件并报告 conflict；
- 验收失败时恢复升级前提交；
- 不触碰私人内容目录、登录状态或外部 CLI。

非 Git 安装需要先用新版安装包更新 console script，再继续管理 checkout。Release 资产附带 `SHA256SUMS.txt`。

## 5. 外部 CLI 发现与升级

```bash
content-publishing deps list
content-publishing deps check
content-publishing deps check browser-use
content-publishing deps upgrade browser-use
content-publishing deps upgrade browser-use --apply
```

本工具会区分命令、Python 包和安装环境。只有能够确认原安装提供者时才生成升级命令；缺少 `--apply` 只显示计划。不存在“自动升级全部依赖”的入口。

Browser Use 需要分别记录 Skill、Harness CLI、引擎和隔离启动器。FFmpeg 安装通常同时提供 `ffmpeg` 与 `ffprobe`。ChatCut 是 IDE 插件能力，不伪装成跨 IDE CLI。

`deps list` 中 `commands[].version` 是当前可执行命令（通常是 Browser Harness CLI）自己报告的版本；`packages.browser-use` 才是其 Python 引擎包版本。Browser Use Skill 属于 IDE 指令层，不会因为二者版本相同或不同就被判定为重复，也不由 `deps upgrade` 静默替换。

## 6. 可选增强能力

完整 JSON Schema：

```bash
python3 -m pip install -e '.[schema]'
python3 tools/full_schema_check.py
```

视频文件级检查：

```bash
brew install ffmpeg
ffmpeg -version
ffprobe -version
```

图片增强检查：

```bash
python3 -m pip install Pillow
```

这些增强能力不可用时可以降级，但必须如实记录为 `unavailable`、`detected`、`blocked` 或 `manual`，不能伪装成 `tested`。

## 7. 敏感信息

工具、私人内容和本机凭证是三层数据。Cookie、Token、MFA、浏览器用户目录、系统钥匙串和新平台协议永远不进入公共仓库或升级包。详见 `SECURITY.md`。
