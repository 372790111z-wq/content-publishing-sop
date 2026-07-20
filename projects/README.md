# 项目注册表

`registry.json` 是看板和跨机器 Agent 发现项目的唯一清单。新项目推荐放在 `projects/<project-id>/`，也可以用相对路径引用工作台旁边的项目。

只有来源需求已经完成并验收、且用户在验收后明确要求整理内容时，才能新增内容项目。需求开发中、仅完成验收但尚未提出内容请求，或只是 Agent 判断“可能值得写”，都不能提前登记。

新增项目：

1. 复制 `templates/project/` 为 `projects/<project-id>/`；
2. 填写 `project-manifest.json.source_work`，绑定验收证据、复用理由和用户内容请求证据；
3. 替换其余占位值，创建内容真源；
4. 在 `registry.json.projects` 追加 `{ "path": "./<project-id>", "enabled": true, "kind": "project" }`；
5. 运行默认校验，修复结构和内容错误；
6. 重建看板并运行可移植性检查。

`enabled=false` 表示暂时不进入看板；不要通过删除注册项隐藏失败项目。路径不存在、项目 id 重复或已启用项目默认门禁失败，`tools/portability_check.py` 会阻断交付。

看板只统计这些内容项目及其平台发布、公开验收和效果数据，不统计来源需求数量。
