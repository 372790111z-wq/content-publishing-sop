# 工具

`capability_check.py` 只检测，不安装、不登录、不打开公开页面。它会把 Skill、CLI、引擎和本机包装器拆开记录。

`build_dashboard.py` 读取 `projects/registry.json`，把登记项目的真源数据重建为 `dashboard/data.js`。看板从 `file://` 打开时也能工作，不需要本地服务器。使用 `--check` 可验证现有缓存与注册表、真源摘要及内容是否一致，检查模式不会写文件。看板保留每个平台最近 30 条快照，并在最近两条有数值的快照之间计算变化量。

`release_digest.py` 计算当前发布内容集合的确定性 SHA-256，用于冻结版本和绑定一次性授权。

`install_local_skill.py` 把仓库内的 `content-publishing-sop` Skill 安全安装到 Codex 用户 Skill 目录。目标已存在且不同会阻断，不会静默覆盖。

`portability_check.py` 检查目录完整性、JSON、项目注册表、注册项目默认门禁、适配器绝对路径和看板引用。各内容项目的提示词、资产哈希和发布门禁由 `validator/validate.py` 检查。

这些脚本都兼容 Python 3.9+，只使用标准库。

可选依赖：

```text
Pillow  # 更深入的图片检查，基础尺寸读取不需要
ffmpeg  # 最终视频技术检查
```
