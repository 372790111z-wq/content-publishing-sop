# 项目注册表

`registry.json` 是看板和跨机器 Agent 发现项目的唯一清单。新项目推荐放在 `projects/<project-id>/`，也可以用相对路径引用工作台旁边的项目。

公共仓库默认只登记完全虚构的 `examples/quickstart-demo`，用于展示最终效果。真实项目应留在本地或受控私有存储，不要提交回公共工具仓库。

只有来源需求已经完成并验收、且用户在验收后明确要求整理内容时，才能新增内容项目。需求开发中、仅完成验收但尚未提出内容请求，或只是 Agent 判断“可能值得写”，都不能提前登记。

推荐使用事务化命令新增项目：

```bash
content-publishing new-project <project-id> --help
```

该命令完成模板复制、project id 替换、个人表达与平台档案初始化和注册表更新，但不会编造真实讨论、验收证据或个人经历。后续仍由 Agent 从事实来源补全内容并逐稿审校。

已有项目升级到 0.3.0 后运行：

```bash
content-publishing editorial-init projects/<project-id>
```

命令不会覆盖已有文件；新增编辑策略后需要重新审校并冻结 release。

人工新增项目时：

1. 复制 `templates/project/` 为 `projects/<project-id>/`；
2. 填写 `project-manifest.json.source_work`，绑定验收证据、复用理由和用户内容请求证据；
3. 替换其余占位值，创建内容真源和个人表达档案；
4. 在 `registry.json.projects` 追加 `{ "path": "./<project-id>", "enabled": true, "kind": "project" }`；
5. 对用户明确给出的文章来源项目只读运行 `carrier detect`，展示候选；根据用户的独立决定运行 `carrier confirm` 或 `carrier confirm-none`；
6. 为每个目标平台生成独立版本，完成逐稿审校后运行默认与严格校验；
7. 重建看板并运行可移植性检查。

`enabled=false` 表示暂时不进入看板；不要通过删除注册项隐藏失败项目。路径不存在、项目 id 重复或已启用项目默认门禁失败，`tools/portability_check.py` 会阻断交付。

看板只统计这些内容项目及其平台发布、公开验收和效果数据，不统计来源需求数量。
