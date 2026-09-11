"""Deterministic projections and exact pairwise metrics, without an LLM or reference truth."""

from __future__ import annotations

import difflib
import hashlib
import itertools
import json
import math
import unicodedata
from collections import Counter, defaultdict


def normalized(value):
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n"))
    if isinstance(value, list):
        return [normalized(v) for v in value]
    if isinstance(value, dict):
        return {k: normalized(v) for k, v in value.items()}
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def canonical(value):
    return json.dumps(normalized(value), sort_keys=True, ensure_ascii=False, allow_nan=False)


def content_hash(snapshot):
    return hashlib.sha256(canonical(snapshot["blocks"]).encode("utf-8")).hexdigest()


def edit_distance(a: str, b: str) -> int:
    """Exact unit-cost Levenshtein using Myers' bit-vector recurrence (Python integers)."""
    if a == b:
        return 0
    if len(a) > len(b):
        a, b = b, a
    if not a:
        return len(b)
    masks = {}
    for i, char in enumerate(a):
        masks[char] = masks.get(char, 0) | (1 << i)
    positive, negative, distance = ~0, 0, len(a)
    highest = 1 << (len(a) - 1)
    for char in b:
        equal = masks.get(char, 0)
        vertical = equal | negative
        horizontal = (((equal & positive) + positive) ^ positive) | equal
        plus = negative | ~(horizontal | positive)
        minus = positive & horizontal
        distance += bool(plus & highest) - bool(minus & highest)
        plus = (plus << 1) | 1
        minus <<= 1
        positive = minus | ~(vertical | plus)
        negative = plus & vertical
    return distance


def docling_snapshot(raw):
    doc = raw.get("document", raw)
    blocks, geometry, visited = [], [], set()

    def visit(ref, layer, depth, active):
        if ref in active:
            raise ValueError(f"Cyclic Docling reference: {ref}")
        kind, index = ref.removeprefix("#/").split("/")
        item = doc[kind][int(index)]
        visited.add(ref)
        label = item.get("label", kind)
        prov = item.get("prov", [])
        page = [p["page_no"] for p in prov]
        core = {"kind": label, "layer": layer, "depth": depth,
                "page": page, "text": item.get("text", "")}
        if item.get("formatting"):
            core["formatting"] = item["formatting"]
        geo = {"prov": [{"bbox": p.get("bbox"), "charspan": p.get("charspan")}
                        for p in prov]}
        if kind == "tables":
            data = item.get("data", {})
            core["table"] = {k: v for k, v in data.items() if k not in {"table_cells", "grid"}}
            core["table"]["table_cells"] = [
                {k: v for k, v in cell.items() if k != "bbox"}
                for cell in data.get("table_cells", [])]
            geo["cells"] = [cell.get("bbox") for cell in data.get("table_cells", [])]
            core["text"] = "\n".join(c.get("text", "") for c in data.get("table_cells", []))
        if kind in {"key_value_items", "form_items"}:
            core["data"] = {k: v for k, v in item.items()
                            if k not in {"self_ref", "parent", "prov", "children"}}
        blocks.append(core)
        geometry.append({"key": [page, label, core["text"], layer],
                         "source_ref": ref, "values": geo})
        for child in item.get("children", []):
            visit(child["$ref"], layer, depth + 1, active | {ref})
        for name in ("captions", "footnotes"):
            for child in item.get(name, []):
                if child["$ref"] not in visited:
                    visit(child["$ref"], layer, depth + 1, active | {ref})

    for layer in ("body", "furniture"):
        for child in doc.get(layer, {}).get("children", []):
            visit(child["$ref"], layer, 0, set())
    # Keep unattached content visible instead of silently dropping items.
    for kind in ("texts", "tables", "pictures", "key_value_items", "form_items"):
        for index in range(len(doc.get(kind, []))):
            ref = f"#/{kind}/{index}"
            if ref not in visited:
                visit(ref, "unattached", 0, set())
    return normalized({
        "text": "\n".join(b["text"] for b in blocks if b["text"]), "blocks": blocks,
        "geometry": geometry, "scores": raw.get("confidence", {}),
        "counts": dict(Counter(b["kind"] for b in blocks)),
        "pages": len(doc.get("pages", {})),
    })


def tika_snapshot(raw):
    blocks = [{"kind": "document" if i == 0 else "embedded_resource",
               "text": item.get("tk:content", item.get("X-TIKA:content", "")),
               "resource": item.get("tk:resource-name", item.get("resourceName", "")),
               "depth": item.get("tk:embedded-depth"),
               "content_type": item.get("Content-Type")}
              for i, item in enumerate(raw)]
    return normalized({"text": "\n".join(b["text"] for b in blocks if b["text"]),
                       "blocks": blocks, "geometry": None, "scores": None,
                       "counts": {"document": 1, "embedded_resource": len(raw) - 1},
                       "pages": raw[0].get("xmpTPg:NPages")})


def numeric_delta(a, b):
    deltas, changed_shape = [], 0

    def walk(left, right):
        nonlocal changed_shape
        if isinstance(left, dict) and isinstance(right, dict):
            changed_shape += len(set(left) ^ set(right))
            for k in left.keys() & right.keys():
                walk(left[k], right[k])
        elif isinstance(left, list) and isinstance(right, list):
            changed_shape += abs(len(left) - len(right))
            for lv, rv in zip(left, right):
                walk(lv, rv)
        elif isinstance(left, (int, float)) and isinstance(right, (int, float)):
            if left != right:
                deltas.append(abs(left - right))
        elif left != right:
            changed_shape += 1

    walk(a, b)
    return {"changed_values": len(deltas), "max_abs_delta": max(deltas, default=0),
            "non_numeric_or_shape_changes": changed_shape}


def geometry_delta(a, b):
    if a is None or b is None:
        return None
    left, right = defaultdict(list), defaultdict(list)
    for item in a:
        left[canonical(item["key"])].append(item["values"])
    for item in b:
        right[canonical(item["key"])].append(item["values"])
    keys = [key for key in left.keys() & right.keys()
            if len(left[key]) == len(right[key]) == 1]
    delta = numeric_delta([left[k][0] for k in sorted(keys)],
                          [right[k][0] for k in sorted(keys)])
    delta.update(matched_items=len(keys), unmatched_or_ambiguous_left=len(a) - len(keys),
                 unmatched_or_ambiguous_right=len(b) - len(keys))
    return delta


def compare_pair(a, b):
    ta, tb = normalized(a["text"]), normalized(b["text"])
    distance = edit_distance(ta, tb)
    left = [canonical(block) for block in a["blocks"]]
    right = [canonical(block) for block in b["blocks"]]
    counts = {"added": 0, "deleted": 0, "replaced_left": 0, "replaced_right": 0}
    spans = []
    for tag, i, j, k, l in difflib.SequenceMatcher(None, left, right, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        spans.append({"operation": tag, "left_range": [i, j], "right_range": [k, l]})
        if tag == "insert":
            counts["added"] += l - k
        elif tag == "delete":
            counts["deleted"] += j - i
        else:
            counts["replaced_left"] += j - i
            counts["replaced_right"] += l - k
    return {"content_equal": left == right, "text_equal": ta == tb,
            "edit_distance": distance,
            "text_difference_pct": distance / max(len(ta), len(tb), 1) * 100,
            "block_changes": counts, "changed_spans": spans,
            "geometry": geometry_delta(a.get("geometry"), b.get("geometry")),
            "scores": numeric_delta(a["scores"], b["scores"])
            if a.get("scores") is not None and b.get("scores") is not None else None}


def stability(snapshots):
    pairs = [{"left": i + 1, "right": j + 1, **compare_pair(a, b)}
             for (i, a), (j, b) in itertools.combinations(enumerate(snapshots), 2)]
    return {"unique_content": len({content_hash(s) for s in snapshots}),
            "equal_pairs": sum(p["content_equal"] for p in pairs), "pairs": pairs}
