# 工具安装与能力边界

如果你还不熟悉工作台的操作顺序，先阅读 `USAGE-GUIDE.md`。本文件只解释工具安装和能力边界。

核心工作台不要求一次装齐所有工具。先运行能力检测，再补当前任务真正需要的能力。

## 最小环境

- 能读写 UTF-8、Markdown 和 JSON 的 IDE 或 Agent；
- 一个现代浏览器，用于打开本地看板；
- Python 3.9+，用于能力检测、校验和重建看板数据。

## 安装 Codex Skill

工作台自带 `skills/content-publishing-sop/`。在工作台根目录运行：

```bash
python3 tools/install_local_skill.py --check
python3 tools/install_local_skill.py
```

安装器默认写入 `$CODEX_HOME/skills/content-publishing-sop`；未设置 `CODEX_HOME` 时写入 `~/.codex/skills/content-publishing-sop`。目标不存在时安装，内容完全一致时跳过，存在不同版本时阻断且不覆盖。安装后下一条 Codex 消息即可使用 `$content-publishing-sop`；若列表未刷新，重新打开 Codex。

这个 Skill 是 Codex 专用薄入口。其他 IDE 使用 `adapters/`，不要把 Codex Skill 当成跨宿主通用安装包。

校验器只使用 Python 标准库。安装后用下面的命令验证，不要只看安装器提示：

```bash
python3 --version
python3 validator/validate.py --help
python3 tools/release_digest.py --help
```

## 视频工具：避免重复理解

ChatCut 和 FFmpeg 有重叠，但验收层不同：

| 能力 | 首选 | 后备 | 证据 |
|---|---|---|---|
| 时间线、字幕、配音、画面编排 | IDE 可调用的 ChatCut 插件 | FFmpeg 或人工时间线 | 工程结构与指定帧 |
| 最终文件流、时长、编码 | ffprobe | 媒体播放器人工检查 | 机器可读流信息 |
| 长静音、连续黑屏 | FFmpeg 过滤器 | 全片人工检查 | 检测日志与时间段 |

FFmpeg 安装包通常同时提供 `ffmpeg` 和 `ffprobe`。macOS 使用 Homebrew 时可运行：

```bash
brew install ffmpeg
ffmpeg -version
ffprobe -version
```

其他系统请使用系统包管理器或 FFmpeg 官方发行方式。命令存在只算 `detected`，至少对一个真实视频运行检查后才能写 `tested`。

剪映等只能通过 GUI 操作的工具不属于自动执行主链，只能记录为人工备选。

## 图片检查

基础校验器可以读取 PNG、JPEG 和 GIF 的尺寸。Pillow 是可选增强项：

```bash
python3 -m pip install Pillow
python3 -c "from PIL import Image; print('Pillow OK')"
```

如果环境禁止安装依赖，保留基础检查并增加人工清晰度检查。

## Browser Use：四层结构

Browser Use 相关能力不得只记录一个版本号：

1. Browser Use Skill：IDE 读取的操作规则；
2. Browser Harness CLI：通常暴露为 `browser-use` 命令；
3. Browser Use 引擎：实际自动化包；
4. 隔离启动器：设备本地策略，例如 `browser-use-isolated`。

安装和连接方式变化较快。对应 IDE 的适配层必须先读取当前官方说明和本机 Skill，再安装。验收至少包括 CLI 帮助、doctor、真实测试页和隔离边界；安装包落盘不算完成。

Browser Use 不可用时，可以使用 IDE 自带浏览器、Playwright 或人工公开页面验收。替代后仍要保留相同证据标准。

发布后的指标采集也遵循同一降级顺序。无论通过平台 API、创作者后台、公开页面还是人工录入，非空指标都必须带采集时间、来源和证据；没有读到的值保持 `null`。工作台不会要求为了展示完整而伪造 0。

## 安装权限

能力检测不会自动安装任何软件。安装、升级、覆盖配置、登录 Cloud 或产生费用前必须单独确认。

## 不需要额外安装的能力

JSON Schema 子集校验、冻结摘要、一次性授权门禁、发布回执、项目注册表、指标检查点和静态看板都由工作台内的 Python 标准库脚本完成。它们不是 Browser Use、ChatCut 或 FFmpeg 的附属能力，也不依赖某个 IDE 插件。
