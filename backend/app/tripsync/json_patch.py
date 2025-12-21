from __future__ import annotations

from typing import Any, Dict, List, Tuple, Union


class JsonPatchError(ValueError):
    pass


def _parse_path(path: str) -> List[str]:
    if not path.startswith("/"):
        raise JsonPatchError("path must start with '/'")
    # RFC6901 unescaping (~1 => /, ~0 => ~)
    parts = path.split("/")[1:]
    out: List[str] = []
    for p in parts:
        out.append(p.replace("~1", "/").replace("~0", "~"))
    return out


def _get_parent_and_key(doc: Any, parts: List[str]) -> Tuple[Any, Union[str, int]]:
    if not parts:
        raise JsonPatchError("path cannot be empty")
    cur = doc
    for seg in parts[:-1]:
        if isinstance(cur, list):
            try:
                idx = int(seg)
            except Exception:
                raise JsonPatchError("list index must be an int")
            try:
                cur = cur[idx]
            except Exception:
                raise JsonPatchError("list index out of range")
        elif isinstance(cur, dict):
            if seg not in cur:
                raise JsonPatchError("path does not exist")
            cur = cur[seg]
        else:
            raise JsonPatchError("path traverses non-container")

    last = parts[-1]
    if isinstance(cur, list):
        if last == "-":
            return cur, -1
        try:
            return cur, int(last)
        except Exception:
            raise JsonPatchError("list index must be an int")
    return cur, last


def apply_json_patch(doc: Any, patch_ops: List[Dict[str, Any]]) -> Any:
    """
    Minimal JSON Patch (RFC6902) applier supporting: add, remove, replace.
    Mutates the input doc in place and returns it.
    """
    if not isinstance(patch_ops, list):
        raise JsonPatchError("patch must be a list")

    for op in patch_ops:
        if not isinstance(op, dict):
            raise JsonPatchError("patch operation must be an object")
        kind = op.get("op")
        path = op.get("path")
        if kind not in {"add", "remove", "replace"}:
            raise JsonPatchError("unsupported op")
        if not isinstance(path, str):
            raise JsonPatchError("path must be a string")
        parts = _parse_path(path)

        if kind in {"add", "replace"} and "value" not in op:
            raise JsonPatchError("value is required for add/replace")

        parent, key = _get_parent_and_key(doc, parts)

        if kind == "remove":
            if isinstance(parent, list):
                if key == -1:
                    raise JsonPatchError("cannot remove '-'")
                try:
                    parent.pop(key)  # type: ignore[arg-type]
                except Exception:
                    raise JsonPatchError("remove index out of range")
            else:
                if key not in parent:
                    raise JsonPatchError("remove path does not exist")
                del parent[key]
            continue

        value = op["value"]
        if kind == "add":
            if isinstance(parent, list):
                if key == -1:
                    parent.append(value)
                else:
                    if key < 0 or key > len(parent):
                        raise JsonPatchError("add index out of range")
                    parent.insert(key, value)
            else:
                parent[key] = value
            continue

        # replace
        if isinstance(parent, list):
            if key == -1:
                raise JsonPatchError("cannot replace '-'")
            try:
                parent[key] = value  # type: ignore[index]
            except Exception:
                raise JsonPatchError("replace index out of range")
        else:
            if key not in parent:
                raise JsonPatchError("replace path does not exist")
            parent[key] = value

    return doc


