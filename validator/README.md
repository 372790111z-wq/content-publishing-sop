# 校验器

基础校验不依赖第三方包，兼容 Python 3.9+。

```bash
python3 validator/validate.py --project projects/<project-id>
python3 validator/validate.py --project projects/<project-id> --strict
python3 validator/validate.py --project projects/<project-id> --action public_publish --platform 知乎
python3 validator/validate.py --project projects/<project-id> --postflight
python3 validator/validate.py --project projects/<project-id> --require-metrics
```

模式说明：

- 默认：错误阻断，警告保留。
- `--strict`：警告也阻断，适合冻结内容版本。
- `--action` + `--platform`：检查指定不可逆动作是否有绑定当前冻结摘要、平台范围和有效期的一次性 grant；参数都可重复。
- `--for-publish`：`--action public_publish` 的兼容别名，仍必须指定 `--platform`。
- `--postflight`：已发布平台必须通过普通读者视角验收。
- `--require-metrics`：当前指标检查点到期时，要求每个已发布平台完成采集、部分采集或带证据说明不可获取。

校验器先按 `schemas/` 检查 manifest、决策、内容要求、平台状态、指标、交接状态和回执，再做语义检查。它先要求 `source_work` 证明来源需求已验收、用户在验收后明确发起内容沉淀，再检查九阶段故事映射、完整提示词的 SHA-256/字节数/字符数/首尾行/锚点、长文逐字包含和提示词图片集的页码、hash 与证据。

`project-manifest.json.release` 绑定来源需求身份和当前发布内容集合的确定性摘要。内容或来源变化后摘要不一致会阻断。首次发布和内容更新的 grant 只能来自对最终内容与明确平台清单的一次确认，`approval_kind` 必须是 `content_and_platforms_confirmed`；授权过期、平台越界、已消费、没有回执或重复发布也会阻断。

指标校验会区分真实零值和未知值，并按“已发布平台 + 已到期 required checkpoint”匹配快照。非空数值必须带来源、时间和证据；尚未采集的数据必须保持 `null`，不能伪装成 0。

运行测试：

```bash
cd validator
python3 -m unittest -v test_validator.py
```

图片尺寸支持 PNG、JPEG 和 GIF。检测到 ffprobe 时会检查最终视频的音视频流和时长；长静音与连续黑屏仍需 FFmpeg 深度检测或人工全片复核。
