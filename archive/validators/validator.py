"""Schema Validator - validates JSON, reports missing fields, supports repair loop."""
import json as _json, os as _os, copy as _copy

_SCHEMA_DIR = _os.path.join(_os.path.dirname(__file__), "..", "schemas")

def _load_schema(name: str) -> dict:
    with open(_os.path.join(_SCHEMA_DIR, name), encoding='utf-8') as f:
        return _json.load(f)

def validate(data: dict, schema_name: str) -> tuple:
    """Returns (is_valid: bool, issues: list[str], repaired: dict).
    If invalid, issues contains specific missing/wrong fields.
    repaired is a best-effort patched version."""
    schema = _load_schema(schema_name)
    issues = []
    repaired = _copy.deepcopy(data)

    if not isinstance(data, dict):
        return False, ["Root must be an object"], {}

    # Check required fields
    for key in schema.get("required", []):
        if key not in data:
            issues.append("MISSING required field: " + key)
            repaired.setdefault(key, _default_for_key(key, schema))
        elif data[key] is None or data[key] == "":
            issues.append("EMPTY required field: " + key)
            repaired[key] = _default_for_key(key, schema)

    # Check array items
    for key, prop in schema.get("properties", {}).items():
        if key not in data:
            continue
        if prop.get("type") == "array" and isinstance(data[key], list):
            min_items = prop.get("minItems", 0)
            actual = len(data[key])
            if actual < min_items:
                issues.append("TOO_FEW items in " + key + ": got " + str(actual) + ", need " + str(min_items))
            if "items" in prop and isinstance(prop["items"], dict):
                item_schema = prop["items"]
                item_required = item_schema.get("required", [])
                for i, item in enumerate(data[key]):
                    if isinstance(item, dict):
                        for rk in item_required:
                            if rk not in item or item[rk] is None:
                                issues.append("MISSING " + key + "[" + str(i) + "]." + rk)

    return len(issues) == 0, issues, repaired

def _default_for_key(key: str, schema: dict) -> any:
    """Return sensible default for a missing required field."""
    prop = schema.get("properties", {}).get(key, {})
    ptype = prop.get("type", "string")
    if ptype == "array":
        items = prop.get("items", {})
        if items.get("type") == "object":
            required = items.get("required", [])
            default_obj = {r: _default_for_key(r, {"properties": items.get("properties",{})}) for r in required}
            return [default_obj] if prop.get("minItems", 0) > 0 else []
        return []
    if ptype == "object":
        required = prop.get("required", [])
        return {r: _default_for_key(r, {"properties": prop.get("properties",{})}) for r in required}
    if ptype == "integer" or ptype == "number":
        return 0
    if ptype == "boolean":
        return False
    return ""
