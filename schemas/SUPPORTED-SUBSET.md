# JSON Schema 校验范围

核心校验器 `validator/schema_validate.py` 为了保持 Python 标准库零依赖，只实现本仓库实际使用的 JSON Schema 子集：

- `type`，包括联合类型数组；
- `required`、`properties`、`additionalProperties=false`；
- `items`、`minItems`、`uniqueItems`；
- `enum`、`const`；
- `minLength`、`minimum`、`pattern`；
- `format=date-time`。

它不是通用 JSON Schema Draft 2020-12 实现。仓库 Schema 引入新的关键词时，必须同时扩展核心校验器和测试，或使用可选的标准 `jsonschema` 包运行完整检查：

```bash
python3 -m pip install -e '.[schema]'
python3 tools/full_schema_check.py
```

CI 同时运行零依赖校验器和标准库实现，防止两者悄悄产生不同结论。
