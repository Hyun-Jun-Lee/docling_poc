"""Build a semantic section tree from a Docling JSON export."""

from __future__ import annotations

import base64
import mimetypes
import re
import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from docling_poc.docling_raw import (
    build_tesseract_ocr_options,
    conversion_error_details,
    conversion_status,
)

TOP_LEVEL_HEADING = re.compile(r"^(?P<marker>\d+)\.\s+(?P<title>.+)$")
SUB_LEVEL_HEADING = re.compile(
    r"^(?P<marker>[가나다라마바사아자차카타파하])\.\s*"
    r"(?P<title>[^:]+?)(?:\s*:\s*(?P<lead>.+))?$"
)
LIST_ITEM = re.compile(r"^\((?P<marker>\d+)\)\s*(?P<text>.+)$")
CIRCLED_LIST_ITEM = re.compile(r"^(?P<marker>[①-⑳])\s*(?P<text>.+)$")
BULLET_LIST_ITEM = re.compile(r"^(?P<marker>[‧•])\s*(?P<text>.+)$")
PictureOcr = Callable[[Mapping[str, Any]], Mapping[str, Any]]


def build_semantic_document(
    document: Mapping[str, Any],
    *,
    ocr_pictures: bool = False,
    picture_ocr: PictureOcr | None = None,
) -> dict[str, Any]:
    """Convert a DoclingDocument JSON export into an ordered semantic tree.

    The input's ``body.children`` remains the authoritative reading order.  The
    output keeps source references so a semantic block can always be traced
    back to its original Docling item. When ``ocr_pictures`` is true, embedded
    ``pictures[n].image.uri`` data URIs are passed through Docling's image
    pipeline with Tesseract and the result is attached to each picture block.

    ``picture_ocr`` is an injectable OCR function for callers that need a
    different engine or want to test the structure without loading OCR models.
    """
    document = _docling_document(document)
    body = _require_mapping(document, "body")
    children = body.get("children")
    if not isinstance(children, Sequence) or isinstance(children, (str, bytes)):
        raise TypeError("Docling JSON body.children must be an array.")

    semantic_rules_matched = matches_semantic_rules(document)
    root: dict[str, Any] = {
        "schema_name": "docling_poc.semantic_document",
        "version": "1.1.0",
        "origin": document.get("origin"),
        "semantic_rules_matched": semantic_rules_matched,
        "children": [],
    }
    stack: list[dict[str, Any]] = [root]
    active_picture_ocr = picture_ocr if ocr_pictures else None
    if ocr_pictures and active_picture_ocr is None:
        # The current Docling image pipeline does not expose a public shutdown
        # method. Reusing one converter for several images can abort during its
        # native teardown, so each picture deliberately gets a fresh converter.
        active_picture_ocr = ocr_picture

    for child in children:
        if not isinstance(child, Mapping) or not isinstance(child.get("$ref"), str):
            raise TypeError("Each Docling body child must contain a string $ref.")

        block = _flatten_body_item(document, child["$ref"], picture_ocr=active_picture_ocr)
        if block is None:
            continue

        heading = _detect_heading(block) if semantic_rules_matched else None
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
            list_item = _detect_list_item(block["text"]) if semantic_rules_matched else None
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


def matches_semantic_rules(document: Mapping[str, Any]) -> bool:
    """Return whether a document matches the current Korean notice outline rules.

    A match requires both a bold numeric primary heading (``1. 제목``) and a
    Korean secondary heading (``가. 제목``). This conservative gate prevents
    the outline parser from treating ordinary numbered prose as a section.
    """
    document = _docling_document(document)
    body = _require_mapping(document, "body")
    children = body.get("children")
    if not isinstance(children, Sequence) or isinstance(children, (str, bytes)):
        raise TypeError("Docling JSON body.children must be an array.")

    has_primary_heading = False
    has_secondary_heading = False

    for child in children:
        if not isinstance(child, Mapping) or not isinstance(child.get("$ref"), str):
            raise TypeError("Each Docling body child must contain a string $ref.")

        block = _flatten_body_item(document, child["$ref"])
        if block is None or block["type"] != "text":
            continue

        text = block["text"]
        formatting = block.get("formatting")
        is_bold = isinstance(formatting, Mapping) and formatting.get("bold") is True
        has_primary_heading |= is_bold and TOP_LEVEL_HEADING.match(text) is not None
        has_secondary_heading |= SUB_LEVEL_HEADING.match(text) is not None

        if has_primary_heading and has_secondary_heading:
            return True

    return False


def _docling_document(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    """Accept either a DoclingDocument export or a ConversionResult export."""
    nested_document = payload.get("document")
    if isinstance(nested_document, Mapping):
        return nested_document
    return payload


def ocr_picture(picture: Mapping[str, Any], *, converter: Any | None = None) -> dict[str, str]:
    """OCR a Docling picture that stores its image as a base64 data URI.

    The decoded image is temporary: the semantic result retains only the OCR
    text and the original ``source_refs``, avoiding a duplicate base64 payload.
    """
    image = _require_mapping(picture, "image")
    mimetype = image.get("mimetype")
    uri = image.get("uri")
    if not isinstance(mimetype, str) or not mimetype.startswith("image/"):
        raise TypeError("Docling picture image.mimetype must be an image MIME type.")
    if not isinstance(uri, str):
        raise TypeError("Docling picture image.uri must be a base64 data URI.")

    payload = _decode_image_data_uri(uri, mimetype)
    extension = mimetypes.guess_extension(mimetype) or ".img"
    converter = converter or _build_image_ocr_converter()

    with tempfile.TemporaryDirectory(prefix="docling-poc-picture-ocr-") as temp_dir:
        image_path = Path(temp_dir) / f"picture{extension}"
        image_path.write_bytes(payload)
        result = converter.convert(image_path, raises_on_error=False)

    if conversion_status(result) not in {"success", "partial_success"}:
        raise RuntimeError(f"Picture OCR failed: {_conversion_failure_message(result)}")

    converted_document = getattr(result, "document", None)
    if converted_document is None:
        raise RuntimeError("Picture OCR failed: Docling returned no document.")
    export_to_markdown = getattr(converted_document, "export_to_markdown", None)
    if not callable(export_to_markdown):
        raise TypeError("Picture OCR result cannot be exported to Markdown.")

    text = str(export_to_markdown()).strip()
    if text.startswith("<!-- image -->"):
        text = text.removeprefix("<!-- image -->").strip()

    return {
        "status": "completed",
        "engine": "tesseract",
        "text": text,
    }


def _build_image_ocr_converter() -> Any:
    try:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, ImageFormatOption
    except ImportError as exc:
        raise RuntimeError(
            "docling is required for picture OCR. Install the project dependencies first."
        ) from exc

    pipeline_options = PdfPipelineOptions(
        do_ocr=True,
        ocr_options=build_tesseract_ocr_options(),
    )
    return DocumentConverter(
        allowed_formats=[InputFormat.IMAGE],
        format_options={
            InputFormat.IMAGE: ImageFormatOption(pipeline_options=pipeline_options),
        },
    )


def _decode_image_data_uri(uri: str, mimetype: str) -> bytes:
    header, separator, encoded = uri.partition(",")
    if not separator:
        raise ValueError("Docling picture image.uri is not a valid data URI.")

    match = re.fullmatch(r"data:(image/[A-Za-z0-9.+-]+);base64", header)
    if match is None:
        raise ValueError("Docling picture image.uri must be a base64 image data URI.")
    if match[1].lower() != mimetype.lower():
        raise ValueError("Docling picture image.uri MIME type does not match image.mimetype.")

    try:
        return base64.b64decode(encoded, validate=True)
    except ValueError as exc:
        raise ValueError("Docling picture image.uri contains invalid base64 data.") from exc


def _conversion_failure_message(result: object) -> str:
    return conversion_error_details(result) or "no error details"


def _flatten_body_item(
    document: Mapping[str, Any],
    ref: str,
    *,
    picture_ocr: PictureOcr | None = None,
) -> dict[str, Any] | None:
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
        block: dict[str, Any] = {
            "type": "picture",
            "source_refs": [ref],
            "captions": item.get("captions", []),
            "references": item.get("references", []),
        }
        if picture_ocr is not None:
            try:
                ocr = picture_ocr(item)
                if not isinstance(ocr, Mapping):
                    raise TypeError("Picture OCR must return an object.")
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                block["ocr"] = {"status": "failed", "error": str(exc)}
            else:
                block["ocr"] = dict(ocr)
        return block

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
