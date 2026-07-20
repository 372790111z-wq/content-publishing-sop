#!/usr/bin/env python3
"""Small zero-dependency validator for the JSON Schema subset used by this package."""

import json
import re
from datetime import datetime
from typing import Any, Dict, List


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "null":
        return value is None
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return True


def _format_ok(value: str, name: str) -> bool:
    if name != "date-time":
        return True
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def validate_instance(instance: Any, schema: Dict[str, Any], path: str = "$") -> List[str]:
    errors: List[str] = []

    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: 必须等于 {schema['const']!r}")
        return errors
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: 值 {instance!r} 不在允许列表中")
        return errors

    expected_types = schema.get("type")
    if expected_types is not None:
        if isinstance(expected_types, str):
            expected_types = [expected_types]
        if not any(_matches_type(instance, item) for item in expected_types):
            errors.append(f"{path}: 类型不符合 {expected_types}")
            return errors

    if isinstance(instance, dict):
        properties = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in instance:
                errors.append(f"{path}.{key}: 缺少必填字段")
        if schema.get("additionalProperties") is False:
            for key in instance:
                if key not in properties:
                    errors.append(f"{path}.{key}: 不允许的字段")
        for key, value in instance.items():
            child_schema = properties.get(key)
            if isinstance(child_schema, dict):
                errors.extend(validate_instance(value, child_schema, f"{path}.{key}"))

    if isinstance(instance, list):
        minimum = schema.get("minItems")
        if isinstance(minimum, int) and len(instance) < minimum:
            errors.append(f"{path}: 至少需要 {minimum} 项")
        if schema.get("uniqueItems"):
            rendered = [json.dumps(item, ensure_ascii=False, sort_keys=True) for item in instance]
            if len(rendered) != len(set(rendered)):
                errors.append(f"{path}: 数组项必须唯一")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, value in enumerate(instance):
                errors.extend(validate_instance(value, item_schema, f"{path}[{index}]"))

    if isinstance(instance, str):
        minimum = schema.get("minLength")
        if isinstance(minimum, int) and len(instance) < minimum:
            errors.append(f"{path}: 字符长度不能小于 {minimum}")
        pattern = schema.get("pattern")
        if pattern and re.search(pattern, instance) is None:
            errors.append(f"{path}: 不匹配格式 {pattern}")
        format_name = schema.get("format")
        if format_name and not _format_ok(instance, format_name):
            errors.append(f"{path}: 不是有效的 {format_name}")

    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        minimum = schema.get("minimum")
        if minimum is not None and instance < minimum:
            errors.append(f"{path}: 不能小于 {minimum}")

    return errors
