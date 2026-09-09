"""Build a semantic section tree from a Docling JSON export."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

TOP_LEVEL_HEADING = re.compile(r"^(?P<marker>\d+)\.\s+(?P<title>.+)$")
SUB_LEVEL_HEADING = re.compile(
    r"^(?P<marker>[가나다라마바사아자차카타파하])\.\s*"
    r"(?P<title>[^:]+?)(?:\s*:\s*(?P<lead>.+))?$"
)
LIST_ITEM = re.compile(r"^\((?P<marker>\d+)\)\s*(?P<text>.+)$")
CIRCLED_LIST_ITEM = re.compile(r"^(?P<marker>[①-⑳])\s*(?P<text>.+)$")
BULLET_LIST_ITEM = re.compile(r"^(?P<marker>[‧•])\s*(?P<text>.+)$")


def build_semantic_document(document: Mapping[str, Any]) -> dict[str, Any]:
    """Convert a DoclingDocument JSON export into an ordered semantic tree.

    The input's ``body.children`` remains the authoritative reading order.  The
    output keeps source references so a semantic block can always be traced
    back to its original Docling item.
    """
    body = _require_mapping(document, "body")
    children = body.get("children")
    if not isinstance(children, Sequence) or isinstance(children, (str, bytes)):
        raise TypeError("Docling JSON body.children must be an array.")

    root: dict[str, Any] = {
        "schema_name": "docling_poc.semantic_document",
        "version": "1.0.0",
        "origin": document.get("origin"),
        "children": [],
    }
    stack: list[dict[str, Any]] = [root]

    for child in children:
        if not isinstance(child, Mapping) or not isinstance(child.get("$ref"), str):
            raise TypeError("Each Docling body child must contain a string $ref.")

        block = _flatten_body_item(document, child["$ref"])
        if block is None:
            continue

        heading = _detect_heading(block)
        if heading is not None:
            while stack[-1].get("level", 0) >= heading["level"]:
                stack.pop()

            section = {
                "type": "section",
                "level": heading["level"],
                "marker": heading["marker"],
                "title": heading["title"],
                "source_refs": block["source_refs"],
                "children": [],
            }
            stack[-1]["children"].append(section)
            stack.append(section)

            if heading["lead"]:
                section["children"].append(
                    {
                        "type": "paragraph",
                        "text": heading["lead"],
                        "source_refs": block["source_refs"],
                    }
                )
            continue

        if block["type"] == "text":
            list_item = _detect_list_item(block["text"])
            if list_item:
                stack[-1]["children"].append(
                    {
                        "type": "list_item",
                        "kind": list_item["kind"],
                        "marker": list_item["marker"],
                        "text": list_item["text"],
                        "source_refs": block["source_refs"],
                    }
                )
            else:
                stack[-1]["children"].append(
                    {
                        "type": "paragraph",
                        "text": block["text"],
                        "source_refs": block["source_refs"],
                    }
                )
        else:
            stack[-1]["children"].append(block)

    return root


def _flatten_body_item(document: Mapping[str, Any], ref: str) -> dict[str, Any] | None:
    kind, item = _dereference(document, ref)

    if kind == "texts":
        return _text_block(item, [ref])

    if kind == "groups":
        runs, source_refs = _group_text_runs(document, ref)
        text = " ".join(_item_text(run) for run in runs if _item_text(run))
        if not text:
            return None
        formatting = runs[0].get("formatting") if runs else None
        return {
            "type": "text",
            "text": text,
            "source_refs": source_refs,
            "formatting": formatting if isinstance(formatting, Mapping) else {},
        }

    if kind == "tables":
        data = item.get("data")
        if not isinstance(data, Mapping):
            raise ValueError(f"Table {ref} has no data object.")
        return {"type": "table", "source_refs": [ref], "data": dict(data)}

    if kind == "pictures":
        return {
            "type": "picture",
            "source_refs": [ref],
            "captions": item.get("captions", []),
            "references": item.get("references", []),
        }

    if kind in {"form_items", "key_value_items"}:
        return {
            "type": kind.removesuffix("s"),
            "source_refs": [ref],
            "data": dict(item),
        }

    # Furniture and unrecognised Docling item types do not form body content.
    return None


def _text_block(item: Mapping[str, Any], source_refs: list[str]) -> dict[str, Any] | None:
    text = _item_text(item)
    if not text:
        return None
    formatting = item.get("formatting")
    return {
        "type": "text",
        "text": text,
        "source_refs": source_refs,
        "formatting": formatting if isinstance(formatting, Mapping) else {},
    }


def _detect_heading(block: Mapping[str, Any]) -> dict[str, Any] | None:
    if block["type"] != "text":
        return None

    text = block["text"]
    formatting = block.get("formatting")
    is_bold = isinstance(formatting, Mapping) and formatting.get("bold") is True
    if is_bold and (match := TOP_LEVEL_HEADING.match(text)):
        return {
            "level": 1,
            "marker": match["marker"],
            "title": match["title"].strip(),
            "lead": None,
        }

    if match := SUB_LEVEL_HEADING.match(text):
        return {
            "level": 2,
            "marker": match["marker"],
            "title": match["title"].strip(),
            "lead": match["lead"].strip() if match["lead"] else None,
        }
    return None


def _detect_list_item(text: str) -> dict[str, str] | None:
    for kind, pattern in (
        ("ordered", LIST_ITEM),
        ("ordered", CIRCLED_LIST_ITEM),
        ("bullet", BULLET_LIST_ITEM),
    ):
        if match := pattern.match(text):
            return {"kind": kind, "marker": match["marker"], "text": match["text"]}
    return None


def _group_text_runs(
    document: Mapping[str, Any], ref: str
) -> tuple[list[Mapping[str, Any]], list[str]]:
    kind, group = _dereference(document, ref)
    if kind != "groups":
        raise ValueError(f"Expected a Docling group reference: {ref}")

    runs: list[Mapping[str, Any]] = []
    source_refs = [ref]
    for child_ref in _child_refs(group):
        child_kind, child = _dereference(document, child_ref)
        if child_kind == "texts":
            runs.append(child)
            source_refs.append(child_ref)
        elif child_kind == "groups":
            nested_runs, nested_refs = _group_text_runs(document, child_ref)
            runs.extend(nested_runs)
            source_refs.extend(nested_refs)
        else:
            raise ValueError(f"Docling group contains non-text child: {child_ref}")
    return runs, source_refs


def _dereference(document: Mapping[str, Any], ref: str) -> tuple[str, Mapping[str, Any]]:
    if not ref.startswith("#/"):
        raise ValueError(f"Unsupported Docling reference: {ref}")

    parts = ref.removeprefix("#/").split("/")
    if len(parts) != 2:
        raise ValueError(f"Unsupported Docling reference: {ref}")
    kind, raw_index = parts
    if kind not in {"texts", "groups", "tables", "pictures", "form_items", "key_value_items"}:
        raise ValueError(f"Unsupported Docling body item type: {kind}")
    if not raw_index.isdecimal():
        raise ValueError(f"Docling reference does not exist: {ref}")

    items = document.get(kind)
    if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
        raise TypeError(f"Docling JSON {kind} must be an array.")
    try:
        item = items[int(raw_index)]
    except (IndexError, ValueError) as exc:
        raise ValueError(f"Docling reference does not exist: {ref}") from exc
    if not isinstance(item, Mapping):
        raise TypeError(f"Docling reference does not resolve to an object: {ref}")
    return kind, item


def _child_refs(group: Mapping[str, Any]) -> list[str]:
    children = group.get("children", [])
    if not isinstance(children, Sequence) or isinstance(children, (str, bytes)):
        raise TypeError("Docling group children must be an array.")
    refs = [child.get("$ref") for child in children if isinstance(child, Mapping)]
    if len(refs) != len(children) or not all(isinstance(ref, str) for ref in refs):
        raise ValueError("Each Docling group child must contain a string $ref.")
    return refs


def _item_text(item: Mapping[str, Any]) -> str:
    text = item.get("text", "")
    if not isinstance(text, str):
        raise TypeError("Docling text item text must be a string.")
    return text.strip()


def _require_mapping(document: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = document.get(key)
    if not isinstance(value, Mapping):
        raise TypeError(f"Docling JSON {key} must be an object.")
    return value
