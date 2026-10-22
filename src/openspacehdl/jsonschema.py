"""A small validator for the JSON Schema 2020-12 keywords the schemas of the Composer use.

Supported: type (one or a list), properties, required, additionalProperties (true, false or a schema), items,
propertyNames, enum, const, minimum, maximum, exclusiveMinimum, maxLength, minItems, pattern, oneOf and $ref to the
$defs of the same document. Annotations (title, description, format, $id, $schema) are ignored. Any other keyword
is an error of the schema, so that a newer schema is not checked half.
"""

from __future__ import annotations

import re

ANNOTATIONS = {"$schema", "$id", "title", "description", "format", "$comment", "default", "examples"}
SUPPORTED = {"type", "properties", "required", "additionalProperties", "items", "propertyNames", "enum", "const",
             "minimum", "maximum", "exclusiveMinimum", "maxLength", "minItems", "pattern", "oneOf", "$ref", "$defs"}
TYPES = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


class SchemaError(Exception):
    """The schema uses a keyword this validator does not support."""


def _path(path: str) -> str:
    return path or "(root)"


def validate(instance, schema: dict, max_errors: int = 20) -> list[str]:
    """The violations of the instance, each as "<JSON path>: <what>"; an empty list when it is valid."""
    root = schema
    out: list[str] = []

    def resolve(ref: str) -> dict:
        if not ref.startswith("#/"):
            raise SchemaError(f"only local $ref is supported: {ref}")
        node = root
        for part in ref[2:].split("/"):
            node = node[part]
        return node

    def check(value, s, path: str) -> list[str]:
        errors: list[str] = []
        unknown = set(s) - SUPPORTED - ANNOTATIONS
        if unknown:
            raise SchemaError(f"unsupported keywords at {_path(path)}: {', '.join(sorted(unknown))}")
        if "$ref" in s:
            errors += check(value, resolve(s["$ref"]), path)
        if "type" in s:
            types = s["type"] if isinstance(s["type"], list) else [s["type"]]
            if not any(TYPES[t](value) for t in types):
                return errors + [f"{_path(path)}: expected {' or '.join(types)}, found {type(value).__name__}"]
        if "const" in s and value != s["const"]:
            errors.append(f"{_path(path)}: must be {s['const']!r}")
        if "enum" in s and value not in s["enum"]:
            errors.append(f"{_path(path)}: must be one of {s['enum']!r}")
        if TYPES["number"](value):
            if "minimum" in s and value < s["minimum"]:
                errors.append(f"{_path(path)}: below the minimum {s['minimum']}")
            if "maximum" in s and value > s["maximum"]:
                errors.append(f"{_path(path)}: above the maximum {s['maximum']}")
            if "exclusiveMinimum" in s and value <= s["exclusiveMinimum"]:
                errors.append(f"{_path(path)}: must be greater than {s['exclusiveMinimum']}")
        if isinstance(value, str):
            if "maxLength" in s and len(value) > s["maxLength"]:
                errors.append(f"{_path(path)}: longer than {s['maxLength']} characters")
            if "pattern" in s and not re.search(s["pattern"], value):
                errors.append(f"{_path(path)}: does not match {s['pattern']}")
        if isinstance(value, list):
            if "minItems" in s and len(value) < s["minItems"]:
                errors.append(f"{_path(path)}: fewer than {s['minItems']} items")
            if "items" in s:
                for i, item in enumerate(value):
                    errors += check(item, s["items"], f"{path}[{i}]")
        if isinstance(value, dict):
            props = s.get("properties", {})
            for name in s.get("required", []):
                if name not in value:
                    errors.append(f"{_path(path)}: the key {name!r} is missing")
            for name, item in value.items():
                sub = f"{path}.{name}" if path else name
                if "propertyNames" in s:
                    errors += check(name, s["propertyNames"], f"{sub} (name)")
                if name in props:
                    errors += check(item, props[name], sub)
                elif s.get("additionalProperties") is False:
                    errors.append(f"{_path(path)}: unknown key {name!r}")
                elif isinstance(s.get("additionalProperties"), dict):
                    errors += check(item, s["additionalProperties"], sub)
        if "oneOf" in s:
            matching = [alt for alt in s["oneOf"] if not check(value, alt, path)]
            if len(matching) != 1:
                errors.append(f"{_path(path)}: matches {len(matching)} of the alternatives of oneOf, not exactly one")
        return errors

    out = check(instance, schema, "")
    return out[:max_errors]
