"""Versioned JSON contracts shared by prompts, providers and validators."""

import copy
import json
import re
from pathlib import Path


CONTRACT_FILES = {
    "gm_turn": ("gm-turn/1", "gm_turn.schema.json", "output_contract.txt"),
    "story_arc": ("story-arc/1", "story_arc.schema.json", "story_arc_contract.txt"),
}


def load_contract(kind, api_directory=None):
    version, schema_name, text_name = CONTRACT_FILES[kind]
    root = Path(api_directory or Path(__file__).resolve().parent) / "content"
    schema = json.loads((root / schema_name).read_text(encoding="utf-8"))
    text = (root / text_name).read_text(encoding="utf-8")
    return {"kind": kind, "version": version, "schema": schema, "text": text}


def contract_document_ids(kind):
    if kind == "gm_turn":
        return "contract.gm_turn.text", "contract.gm_turn.schema"
    return "contract.story_arc.text", "contract.story_arc.schema"


def contract_from_documents(kind, documents):
    text_id, schema_id = contract_document_ids(kind)
    indexed = {item["document_id"]: item for item in documents}
    if text_id not in indexed or schema_id not in indexed:
        raise ValueError(f"content revision is missing {kind} contract")
    schema = json.loads(indexed[schema_id]["text_content"])
    return {"kind": kind,
            "version": CONTRACT_FILES[kind][0],
            "schema": schema,
            "text": indexed[text_id]["text_content"]}


def _matches_type(value, expected):
    if isinstance(expected, list):
        return any(_matches_type(value, item) for item in expected)
    return {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": type(value) is int,
        "boolean": type(value) is bool,
        "null": value is None,
    }.get(expected, True)


def validate_json_schema(value, schema, label="$", root=None):
    """Validate the JSON-Schema subset used by bundled strict contracts."""
    root = root or schema
    if "$ref" in schema:
        target = root
        for part in schema["$ref"].removeprefix("#/").split("/"):
            target = target[part.replace("~1", "/").replace("~0", "~")]
        return validate_json_schema(value, target, label, root)
    alternatives = schema.get("anyOf") or schema.get("oneOf")
    if alternatives:
        errors = []
        for option in alternatives:
            try:
                validate_json_schema(value, option, label, root)
                return
            except ValueError as exc:
                errors.append(str(exc))
        raise ValueError(f"{label}不匹配任何允许结构")
    if "const" in schema and value != schema["const"]:
        raise ValueError(f"{label}必须为{schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{label}不是允许的枚举值")
    expected_type = schema.get("type")
    if expected_type is not None and not _matches_type(value, expected_type):
        raise ValueError(f"{label}类型无效")
    if value is None:
        return
    if isinstance(value, dict):
        required = set(schema.get("required", []))
        missing = required - set(value)
        if missing:
            raise ValueError(f"{label}缺少字段：{','.join(sorted(missing))}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            unknown = set(value) - set(properties)
            if unknown:
                raise ValueError(f"{label}含未知字段：{','.join(sorted(unknown))}")
        for key, child in value.items():
            if key in properties:
                validate_json_schema(child, properties[key], f"{label}.{key}", root)
    elif isinstance(value, list):
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", 10**9):
            raise ValueError(f"{label}数组长度无效")
        for index, child in enumerate(value):
            validate_json_schema(child, schema.get("items", {}), f"{label}[{index}]", root)
    elif isinstance(value, str):
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", 10**9):
            raise ValueError(f"{label}文本长度无效")
        if schema.get("pattern") and re.search(schema["pattern"], value) is None:
            raise ValueError(f"{label}文本格式无效")
    elif type(value) is int:
        if value < schema.get("minimum", value) or value > schema.get("maximum", value):
            raise ValueError(f"{label}数值越界")


def validate_contract(value, kind, contract=None):
    contract = contract or load_contract(kind)
    validate_json_schema(value, contract["schema"])
    return copy.deepcopy(value)
