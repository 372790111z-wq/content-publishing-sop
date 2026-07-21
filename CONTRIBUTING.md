# 贡献指南

## 原则

- 不提交真实账号、Cookie、Token、MFA、私人项目、未公开链接或受限素材；
- 平台后台保存不等于公开发布，连接器必须返回可核对回执；
- 新增不可逆动作必须先有范围化授权和 pending intent；
- 新增 Schema 关键词时同步更新零依赖校验器、完整 Schema 检查和测试；
- IDE 适配器保持薄入口，长期规则只维护在工作台真源。

## 本地验证

```bash
python3 -m unittest discover -s validator -p 'test*.py' -v
python3 -m unittest discover -s tests -p 'test*.py' -v
python3 validator/validate.py --project examples/quickstart-demo
python3 tools/portability_check.py
python3 tools/build_dashboard.py --check
```

安装了可选依赖后再运行：

```bash
python3 tools/full_schema_check.py
```

Pull Request 应说明修改的真源、兼容性影响、测试证据和是否涉及外部状态。
