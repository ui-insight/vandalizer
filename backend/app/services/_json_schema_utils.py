"""Utility to inline $defs references in a JSON schema.

Replaces the removed pydantic_ai._json_schema.InlineDefsJsonSchemaTransformer.
"""

from copy import deepcopy
from typing import Any


def inline_defs(schema: dict[str, Any]) -> dict[str, Any]:
    """Resolve all ``$ref`` pointers against ``$defs`` and return a self-contained schema."""
    defs = schema.get("$defs", {})
    if not defs:
        return schema

    def _resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                ref_path = node["$ref"]  # e.g. "#/$defs/Foo"
                name = ref_path.rsplit("/", 1)[-1]
                if name in defs:
                    return _resolve(deepcopy(defs[name]))
                return node
            return {k: _resolve(v) for k, v in node.items() if k != "$defs"}
        if isinstance(node, list):
            return [_resolve(item) for item in node]
        return node

    result = _resolve(schema)
    assert isinstance(result, dict)
    return result
