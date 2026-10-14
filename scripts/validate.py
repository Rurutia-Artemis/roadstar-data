#!/usr/bin/env python3
"""Validate an untrusted Issue body against the repository's schema (stdlib only)."""

import argparse
import json
from pathlib import Path
import re
import sys


MARKER = "<!-- roadstar-dispatch-data -->"
SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schema" / "dispatch-v1.json"
JSON_BLOCK = re.compile(r"^```json[ \t]*\r?\n(.*?)^```[ \t]*(?:\r?\n|$)", re.M | re.S)


def _same_value(value, choice):
    # Python considers True == 1; JSON Schema does not.
    if isinstance(value, bool) or isinstance(choice, bool):
        return type(value) is type(choice) and value == choice
    return value == choice and (
        type(value) is type(choice)
        or (type(value) in (int, float) and type(choice) in (int, float))
    )


def _check(value, spec, path, errors):
    """Implement only the vocabulary used in dispatch-v1.json; fail closed otherwise."""
    supported = {
        "$schema", "$id", "title", "description", "type", "const", "enum",
        "pattern", "required", "properties", "additionalProperties", "items",
        "minItems", "maxItems", "minimum", "maximum", "multipleOf", "anyOf",
    }
    if set(spec) - supported:
        raise ValueError("schema 含未支持的校验规则")
    if len(errors) >= 10:
        return

    def error(message):
        if len(errors) < 10:
            errors.append(f"{path}：{message}")

    if "anyOf" in spec:
        alternatives = []
        for option in spec["anyOf"]:
            problems = []
            _check(value, option, path, problems)
            alternatives.append(problems)
        if all(alternatives):
            error("不符合允许的类型或格式")
        return
    kind = spec.get("type")
    types = {
        "object": lambda v: type(v) is dict,
        "array": lambda v: type(v) is list,
        "string": lambda v: type(v) is str,
        "integer": lambda v: type(v) is int,
        "boolean": lambda v: type(v) is bool,
        "null": lambda v: v is None,
    }
    if kind is not None:
        if kind not in types:
            raise ValueError("schema 含未支持的类型")
        if not types[kind](value):
            error("字段类型不符合 schema")
            return
    if "const" in spec and not _same_value(value, spec["const"]):
        error("不是规定的固定值")
    if "enum" in spec and not any(_same_value(value, x) for x in spec["enum"]):
        error("不在允许的选项中")
    if "pattern" in spec and re.fullmatch(spec["pattern"], value) is None:
        error("格式不符合 schema")
    if kind == "object":
        properties = spec.get("properties", {})
        for key in spec.get("required", []):
            if key not in value:
                error(f"缺少必填字段 {key}")
        if spec.get("additionalProperties") is False and set(value) - set(properties):
            # Never echo arbitrary keys or values into public rejection comments.
            error("含 schema 未允许的额外字段")
        for key, child in properties.items():
            if key in value:
                _check(value[key], child, f"{path}.{key}", errors)
    if kind == "array":
        if len(value) < spec.get("minItems", 0):
            error("记录数量少于允许的最小值")
        if "maxItems" in spec and len(value) > spec["maxItems"]:
            error("批次超过 200 条记录")
        for index, item in enumerate(value):
            _check(item, spec["items"], f"{path}[{index}]", errors)
            if len(errors) >= 10:
                break
    if kind == "integer":
        if "minimum" in spec and value < spec["minimum"]:
            error("数值低于允许的最小值")
        if "maximum" in spec and value > spec["maximum"]:
            error("数值超过允许的最大值")
        if "multipleOf" in spec and value % spec["multipleOf"] != 0:
            error("数值不是规定步长的整数倍")


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("JSON 含重复字段")
        result[key] = value
    return result


def _constant(_value):
    raise ValueError("JSON 含非标准数值")


def validate_and_parse(body):
    """Return (public result, parsed batch). Errors never contain untrusted text."""
    errors = []
    batch = None
    count = 0
    if not isinstance(body, str):
        return {"ok": False, "records": 0, "errors": ["Issue 正文必须是文本"]}, None
    if not body.splitlines() or body.splitlines()[0] != MARKER:
        errors.append("正文第一行缺少规定的标记行")
    blocks = list(JSON_BLOCK.finditer(body))
    if len(blocks) != 1:
        errors.append("正文必须包含且仅包含一个 json 代码块")
    else:
        block = blocks[0]
        outside = body[:block.start()] + body[block.end():]
        if outside.startswith(MARKER):
            outside = outside[len(MARKER):]
        if "```" in outside or "~~~" in outside:
            errors.append("json 代码块外不能含其他代码块")
        if len(outside.strip()) > 200:
            errors.append("代码块外的文本超过 200 字符")
        try:
            batch = json.loads(block.group(1), object_pairs_hook=_object, parse_constant=_constant)
        except (ValueError, RecursionError):
            errors.append("JSON 无效（语法错误、重复字段或非标准数值）")
        else:
            if isinstance(batch, dict) and isinstance(batch.get("records"), list):
                count = len(batch["records"])
            schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
            _check(batch, schema, "批次", errors)
    return {"ok": not errors, "records": count, "errors": errors[:10]}, batch


def validate_body(body):
    return validate_and_parse(body)[0]


def main(argv=None):
    parser = argparse.ArgumentParser(description="校验 Issue 正文；省略文件或使用 - 时读取 stdin")
    parser.add_argument("file", nargs="?", default="-")
    args = parser.parse_args(argv)
    try:
        body = sys.stdin.read() if args.file == "-" else Path(args.file).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        parser.error("无法读取 UTF-8 正文文件")
    result = validate_body(body)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
