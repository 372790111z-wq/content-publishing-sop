# 工具入口

推荐安装后统一使用：

```bash
content-publishing --help
```

未安装 console script 时，仓库内等价入口是：

```bash
python3 tools/content_publishing.py --help
```

## 生命周期命令

- `bootstrap`：从 GitHub 建立公共工具 checkout，并可安装宿主薄入口；
- `install / uninstall`：只管理由本工具安装且未被用户修改的 IDE 入口；
- `update / rollback`：只管理本项目自身版本；
- `deps list / check / upgrade`：发现和定向升级外部 CLI，缺省只预览；
- `doctor`：检查能力、可移植性、看板和可选测试。

## 内容事务命令

- `new-project`：复制模板、填入真实来源信息并更新注册表；
- `editorial-init`：为旧项目无覆盖补齐个人表达、平台档案和逐稿审校文件；
- `carrier detect / confirm / confirm-none`：只读检测公开 GitHub 提示词候选，并在独立人工确认后登记使用或不使用；
- `freeze`：默认门禁通过后冻结 release digest；
- `grant`：保存用户最终确认并创建范围化一次性授权；
- `prepare`：整批动作门禁通过后创建全部 pending intents；
- `settle`：根据连接器返回证据结算回执和平台状态；
- `platforms`：显示官方 API、浏览器和人工通道能力；
- `mcp serve`：向支持 MCP 的 IDE 暴露同一事务核心。

## 保留的底层脚本

- `capability_check.py`：检测本机能力，不安装、不登录；
- `build_dashboard.py`：公开仓库默认重建脱敏示例；存在本机
  `.content-publishing/registry.json` 时，改为重建被 Git 忽略的私人看板，
  避免真实文章、账号和链接进入公开 `dashboard/data.js`；
- `release_digest.py`：计算发布内容集合 SHA-256；
- `portability_check.py`：检查目录、路径、项目门禁和看板新鲜度；
- `full_schema_check.py`：使用可选标准 `jsonschema` 包运行 Draft 2020-12 检查；
- `version_check.py`：检查 VERSION、包元数据、CHANGELOG 和 Release tag 一致；
- `install_local_skill.py`：旧版 Codex-only 安装入口，兼容保留。

核心流程兼容 Python 3.9+，只使用标准库。完整 JSON Schema、Pillow、FFmpeg、Browser Use 等均属于可选增强能力。
