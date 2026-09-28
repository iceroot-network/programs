"""Offline validation for the JSON Schema vocabulary used in this repository."""

import json
import re
from datetime import datetime


class Invalid(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise Invalid(message)


def load(path):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, f"duplicate JSON key: {key}")
            result[key] = value
        return result
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs,
                      parse_constant=lambda value: require(False, f"invalid number: {value}"))


def instant(value):
    require(isinstance(value, str) and re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", value),
            "timestamp must use UTC seconds")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise Invalid(f"invalid timestamp: {value}") from error


def check(value, schema, path="$", root=None):
    """Unsupported keywords fail closed; no schema or reference is fetched."""
    root = schema if root is None else root
    supported = {"$schema", "$id", "$defs", "title", "description", "$ref", "type",
                 "properties", "required", "additionalProperties", "items", "minItems",
                 "maxItems", "uniqueItems", "pattern", "minLength", "maxLength", "enum",
                 "const", "minimum", "maximum", "anyOf", "format"}
    require(not (set(schema) - supported), f"{path}: unsupported schema keywords")
    if "$ref" in schema:
        ref = schema["$ref"]
        require(ref.startswith("#/$defs/"), f"{path}: only local references supported")
        check(value, root["$defs"][ref.split("/")[-1]], path, root)
    if "anyOf" in schema:
        errors = []
        for choice in schema["anyOf"]:
            try:
                check(value, choice, path, root)
                break
            except Invalid as error:
                errors.append(str(error))
        else:
            raise Invalid(f"{path}: no schema choice matches: {'; '.join(errors)}")
    types = {"object": lambda x: isinstance(x, dict), "array": lambda x: isinstance(x, list),
             "string": lambda x: isinstance(x, str), "integer": lambda x: type(x) is int,
             "boolean": lambda x: type(x) is bool, "null": lambda x: x is None}
    if "type" in schema:
        names = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        require(all(name in types for name in names), f"{path}: unsupported schema type")
        require(any(types[name](value) for name in names), f"{path}: expected {names}")
    if "const" in schema:
        require(type(value) is type(schema["const"]) and value == schema["const"], f"{path}: wrong constant")
    if "enum" in schema:
        require(any(type(value) is type(x) and value == x for x in schema["enum"]), f"{path}: invalid choice")
    if isinstance(value, dict):
        props = schema.get("properties", {})
        require(set(schema.get("required", [])) <= set(value), f"{path}: missing required fields")
        if schema.get("additionalProperties") is False:
            require(set(value) <= set(props), f"{path}: unknown fields {set(value) - set(props)}")
        for key in value.keys() & props.keys():
            check(value[key], props[key], f"{path}.{key}", root)
    if isinstance(value, list):
        require(len(value) >= schema.get("minItems", 0), f"{path}: too few items")
        require(len(value) <= schema.get("maxItems", len(value)), f"{path}: too many items")
        if schema.get("uniqueItems"):
            require(len({json.dumps(x, sort_keys=True) for x in value}) == len(value), f"{path}: duplicate items")
        for i, item in enumerate(value):
            if "items" in schema:
                check(item, schema["items"], f"{path}[{i}]", root)
    if isinstance(value, str):
        require(len(value) >= schema.get("minLength", 0), f"{path}: too short")
        require(len(value) <= schema.get("maxLength", len(value)), f"{path}: too long")
        if "pattern" in schema:
            require(re.search(schema["pattern"], value) is not None, f"{path}: invalid format")
        if "format" in schema:
            require(schema["format"] == "date-time", f"{path}: unsupported format")
            instant(value)
    if type(value) is int:
        require(value >= schema.get("minimum", value), f"{path}: below minimum")
        require(value <= schema.get("maximum", value), f"{path}: above maximum")
