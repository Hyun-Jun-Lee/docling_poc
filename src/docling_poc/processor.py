from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from docling_poc.models import (
    BBox,
    DocumentChunk,
    DocumentProfile,
    ElementProvenance,
    NormalizedElement,
    OcrQualitySignals,
    ProcessedDocument,
)

SUPPORTED_DOCUMENT_SUFFIXES = {".pdf", ".docx", ".doc", ".pptx", ".ppt"}
HEADING_KINDS = {"title", "section_header", "heading"}
TABLE_KINDS = {"table"}
PICTURE_KINDS = {"picture", "chart"}


@dataclass(frozen=True)
class DoclingProcessConfig:
    max_chunk_chars: int = 1_600
    min_chunk_chars: int = 350
    enable_ocr: bool = True
    ocr_languages: tuple[str, ...] = ("ko", "en")
    ocr_quality_threshold: float = 0.55
    include_markdown: bool = True
    include_tables_as_markdown: bool = True
    include_picture_placeholders: bool = True
    max_num_pages: int | None = None
    max_file_size: int | None = None


def process_document(
    source: str | Path,
    *,
    config: DoclingProcessConfig | None = None,
    converter: Any | None = None,
) -> ProcessedDocument:
    """Convert one PDF, PPT/PPTX, or Word document into normalized elements and chunks."""
    config = config or DoclingProcessConfig()
    source_path = Path(source)
    _validate_supported_source(source_path)

    converter = converter or build_docling_converter(config)
    convert_kwargs: dict[str, Any] = {"raises_on_error": False}
    if config.max_num_pages is not None:
        convert_kwargs["max_num_pages"] = config.max_num_pages
    if config.max_file_size is not None:
        convert_kwargs["max_file_size"] = config.max_file_size

    result = converter.convert(source_path, **convert_kwargs)
    document = getattr(result, "document", None)
    status = _stringify(getattr(result, "status", "success"))
    errors = _collect_conversion_errors(result)
    if document is None:
        raise RuntimeError(f"Docling conversion did not return a document: {errors or status}")

    return normalize_docling_document(
        document,
        source_path=source_path,
        status=status,
        errors=errors,
        config=config,
    )


def build_docling_converter(config: DoclingProcessConfig) -> Any:
    """Create a Docling converter configured for document-heavy enterprise inputs."""
    try:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption
    except ImportError as exc:
        raise RuntimeError(
            "docling is required for conversion. Install this project with `pip install -e .`."
        ) from exc

    allowed_formats = [
        fmt
        for name in ("PDF", "DOCX", "DOC", "PPTX", "PPT")
        if (fmt := getattr(InputFormat, name, None)) is not None
    ]

    pdf_options = PdfPipelineOptions()
    _set_if_present(pdf_options, "do_ocr", config.enable_ocr)
    _set_if_present(pdf_options, "do_table_structure", True)
    _set_if_present(pdf_options, "generate_page_images", False)
    _set_if_present(pdf_options, "generate_picture_images", False)

    ocr_options = getattr(pdf_options, "ocr_options", None)
    if ocr_options is not None:
        _set_if_present(ocr_options, "lang", list(config.ocr_languages))

    format_options = {}
    if getattr(InputFormat, "PDF", None) is not None:
        format_options[InputFormat.PDF] = PdfFormatOption(pipeline_options=pdf_options)

    return DocumentConverter(allowed_formats=allowed_formats, format_options=format_options)


def normalize_docling_document(
    document: Any,
    *,
    source_path: str | Path,
    config: DoclingProcessConfig | None = None,
    status: str = "success",
    errors: Iterable[str] = (),
) -> ProcessedDocument:
    """Normalize a DoclingDocument-like object without requiring Docling at test time."""
    config = config or DoclingProcessConfig()
    path = Path(source_path)
    asset_id = _asset_id(path)
    markdown = _export_document_markdown(document) if config.include_markdown else ""
    elements = _extract_elements(document, asset_id=asset_id, config=config)
    chunks = build_chunks(elements, asset_id=asset_id, config=config)
    profile = build_document_profile(document, path.suffix.lower().lstrip("."), elements, config)

    return ProcessedDocument(
        asset_id=asset_id,
        source_path=str(path),
        source_type=path.suffix.lower().lstrip("."),
        status=status,
        markdown=markdown,
        elements=elements,
        chunks=chunks,
        profile=profile,
        errors=list(errors),
    )


def build_chunks(
    elements: list[NormalizedElement],
    *,
    asset_id: str,
    config: DoclingProcessConfig | None = None,
) -> list[DocumentChunk]:
    config = config or DoclingProcessConfig()
    _validate_chunk_config(config)
    chunks: list[DocumentChunk] = []
    current: list[NormalizedElement] = []
    heading_path: list[str] = []

    def append_chunk(
        chunk_elements: list[NormalizedElement],
        *,
        text_override: str | None = None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> None:
        if not chunk_elements:
            return
        sequence_no = len(chunks)
        chunk_text = (
            text_override
            if text_override is not None
            else "\n\n".join(_element_chunk_text(element) for element in chunk_elements).strip()
        )
        page_numbers = sorted(
            {
                page
                for element in chunk_elements
                for page in _element_page_numbers(element)
                if page is not None
            }
        )
        metadata = {
            "char_count": len(chunk_text),
            "start_sequence_no": chunk_elements[0].sequence_no,
            "end_sequence_no": chunk_elements[-1].sequence_no,
        }
        metadata.update(extra_metadata or {})
        chunks.append(
            DocumentChunk(
                chunk_id=f"{asset_id}:c{sequence_no:05d}",
                sequence_no=sequence_no,
                text=chunk_text,
                element_ids=[element.element_id for element in chunk_elements],
                element_kinds=[element.kind for element in chunk_elements],
                page_numbers=page_numbers,
                heading_path=list(heading_path),
                metadata=metadata,
            )
        )

    def flush() -> None:
        nonlocal current
        if not current:
            return
        append_chunk(current)
        current = []

    for element in elements:
        element_text = _element_chunk_text(element)
        if not element_text:
            continue

        if element.kind in HEADING_KINDS:
            flush()
            heading_path = _update_heading_path(heading_path, element)

        if len(element_text) > config.max_chunk_chars:
            flush()
            split_parts = _split_long_text(element_text, config.max_chunk_chars)
            for part_index, part_text in enumerate(split_parts):
                append_chunk(
                    [element],
                    text_override=part_text,
                    extra_metadata={
                        "split_from_oversized_element": True,
                        "split_part_index": part_index,
                        "split_part_count": len(split_parts),
                        "source_element_char_count": len(element_text),
                    },
                )
            continue

        would_exceed = current and _current_len(current) + len(element_text) > config.max_chunk_chars
        if would_exceed and _current_len(current) >= config.min_chunk_chars:
            flush()

        current.append(element)

        if element.kind in TABLE_KINDS | PICTURE_KINDS and _current_len(current) >= config.min_chunk_chars:
            flush()

    flush()
    return chunks


def build_document_profile(
    document: Any,
    source_type: str,
    elements: list[NormalizedElement],
    config: DoclingProcessConfig | None = None,
) -> DocumentProfile:
    config = config or DoclingProcessConfig()
    page_count = _page_count(document, elements)
    counts = Counter(element.kind for element in elements)
    ocr = _build_ocr_quality(elements, page_count=page_count, threshold=config.ocr_quality_threshold)
    return DocumentProfile(
        source_type=source_type,
        page_count=page_count,
        element_count=len(elements),
        element_counts=dict(sorted(counts.items())),
        has_tables=any(kind in TABLE_KINDS for kind in counts),
        has_pictures=any(kind in PICTURE_KINDS for kind in counts),
        ocr=ocr,
    )


def _extract_elements(
    document: Any,
    *,
    asset_id: str,
    config: DoclingProcessConfig,
) -> list[NormalizedElement]:
    items = list(_iterate_docling_items(document))
    elements: list[NormalizedElement] = []
    for sequence_no, (item, level) in enumerate(items):
        kind = _item_kind(item)
        text, markdown = _item_text_and_markdown(item, document=document, config=config)
        if not text and kind in PICTURE_KINDS and config.include_picture_placeholders:
            text = "[Picture]"
        if not text and not markdown:
            continue

        provenance = _item_provenance(item)
        page_no = next((prov.page_no for prov in provenance if prov.page_no is not None), None)
        elements.append(
            NormalizedElement(
                element_id=f"{asset_id}:e{len(elements):05d}",
                sequence_no=len(elements),
                kind=kind,
                text=text.strip(),
                markdown=markdown.strip() if markdown else None,
                level=level,
                page_no=page_no,
                provenance=provenance,
                metadata=_item_metadata(item),
            )
        )
    return elements


def _iterate_docling_items(document: Any) -> Iterable[tuple[Any, int]]:
    iterator = getattr(document, "iterate_items", None)
    if iterator is None:
        raise TypeError("Expected a DoclingDocument-like object with iterate_items().")

    try:
        yield from iterator(traverse_pictures=True)
    except TypeError:
        yield from iterator()


def _item_text_and_markdown(
    item: Any,
    *,
    document: Any,
    config: DoclingProcessConfig,
) -> tuple[str, str | None]:
    kind = _item_kind(item)
    raw_text = getattr(item, "text", None) or getattr(item, "orig", None) or ""

    markdown: str | None = None
    if kind in TABLE_KINDS and config.include_tables_as_markdown:
        markdown = _call_export(item, "export_to_markdown", doc=document)
        raw_text = markdown or raw_text
    elif kind in PICTURE_KINDS:
        captions = _extract_caption_text(item)
        raw_text = captions or raw_text

    return str(raw_text or ""), markdown


def _item_kind(item: Any) -> str:
    label = getattr(item, "label", None)
    value = getattr(label, "value", None)
    if value:
        return str(value).lower()
    if label:
        return str(label).lower()
    return item.__class__.__name__.replace("Item", "").lower()


def _item_provenance(item: Any) -> list[ElementProvenance]:
    provenances = []
    for prov in getattr(item, "prov", []) or []:
        bbox = getattr(prov, "bbox", None)
        provenances.append(
            ElementProvenance(
                page_no=getattr(prov, "page_no", None),
                bbox=_bbox_from_docling(bbox),
            )
        )
    return provenances


def _bbox_from_docling(bbox: Any) -> BBox | None:
    if bbox is None:
        return None
    return BBox(
        left=float(getattr(bbox, "l", getattr(bbox, "left", 0.0))),
        top=float(getattr(bbox, "t", getattr(bbox, "top", 0.0))),
        right=float(getattr(bbox, "r", getattr(bbox, "right", 0.0))),
        bottom=float(getattr(bbox, "b", getattr(bbox, "bottom", 0.0))),
        coord_origin=_stringify(getattr(bbox, "coord_origin", None)) or None,
    )


def _item_metadata(item: Any) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for attr in ("self_ref", "name"):
        value = getattr(item, attr, None)
        if value:
            metadata[attr] = str(value)
    return metadata


def _build_ocr_quality(
    elements: list[NormalizedElement],
    *,
    page_count: int,
    threshold: float,
) -> OcrQualitySignals:
    text = "\n".join(
        element.text
        for element in elements
        if element.text and element.kind not in PICTURE_KINDS
    )
    text_char_count = len(text)
    pages_with_text = sorted(
        {
            page
            for element in elements
            if element.text and element.kind not in PICTURE_KINDS
            for page in _element_page_numbers(element)
            if page is not None
        }
    )
    all_pages = set(range(1, page_count + 1))
    pages_without_text = sorted(all_pages - set(pages_with_text))

    hangul_count = sum(1 for char in text if "\uac00" <= char <= "\ud7a3")
    abnormal_count = sum(1 for char in text if char == "\ufffd" or "\u3130" <= char <= "\u318f")
    hangul_ratio = _safe_ratio(hangul_count, text_char_count)
    abnormal_char_ratio = _safe_ratio(abnormal_count, text_char_count)
    text_coverage_ratio = _safe_ratio(len(pages_with_text), page_count)

    table_count = sum(1 for element in elements if element.kind in TABLE_KINDS)
    picture_count = sum(1 for element in elements if element.kind in PICTURE_KINDS)
    reasons: list[str] = []
    if text_char_count < max(80, page_count * 40):
        reasons.append("low_text_volume")
    if text_coverage_ratio < 0.5:
        reasons.append("low_page_text_coverage")
    if abnormal_char_ratio > 0.03:
        reasons.append("high_abnormal_character_ratio")
    if picture_count > 0 and text_char_count < picture_count * 30:
        reasons.append("image_heavy_low_text")

    quality_score = max(
        0.0,
        min(
            1.0,
            0.45 * min(1.0, text_char_count / max(1, page_count * 600))
            + 0.35 * text_coverage_ratio
            + 0.20 * (1.0 - min(1.0, abnormal_char_ratio * 12)),
        ),
    )
    needs_fallback = quality_score < threshold or bool(
        {"low_page_text_coverage", "high_abnormal_character_ratio"} & set(reasons)
    )

    return OcrQualitySignals(
        text_char_count=text_char_count,
        page_count=page_count,
        text_coverage_ratio=round(text_coverage_ratio, 4),
        hangul_ratio=round(hangul_ratio, 4),
        abnormal_char_ratio=round(abnormal_char_ratio, 4),
        table_count=table_count,
        picture_count=picture_count,
        pages_with_text=pages_with_text,
        pages_without_text=pages_without_text,
        quality_score=round(quality_score, 4),
        needs_fallback=needs_fallback,
        reasons=reasons,
    )


def _export_document_markdown(document: Any) -> str:
    return _call_export(document, "export_to_markdown", traverse_pictures=True) or ""


def _call_export(obj: Any, method_name: str, **kwargs: Any) -> str | None:
    method = getattr(obj, method_name, None)
    if method is None:
        return None
    try:
        return str(method(**kwargs))
    except TypeError:
        try:
            return str(method())
        except Exception:  # noqa: BLE001
            return None
    except Exception:  # noqa: BLE001
        return None


def _extract_caption_text(item: Any) -> str:
    captions = getattr(item, "captions", None) or []
    parts = []
    for caption in captions:
        text = getattr(caption, "text", None)
        if text:
            parts.append(str(text))
    return "\n".join(parts)


def _element_chunk_text(element: NormalizedElement) -> str:
    if element.kind in TABLE_KINDS and element.markdown:
        return element.markdown
    if element.kind in PICTURE_KINDS and element.text == "[Picture]":
        return f"{element.text} page={element.page_no}" if element.page_no else element.text
    return element.text


def _current_len(elements: list[NormalizedElement]) -> int:
    return sum(len(_element_chunk_text(element)) + 2 for element in elements)


def _split_long_text(text: str, max_chars: int) -> list[str]:
    remaining = text.strip()
    parts: list[str] = []
    while len(remaining) > max_chars:
        cut_at = remaining.rfind("\n", 0, max_chars + 1)
        if cut_at < max_chars // 2:
            cut_at = remaining.rfind(" ", 0, max_chars + 1)
        if cut_at < max_chars // 2:
            cut_at = max_chars
        parts.append(remaining[:cut_at].strip())
        remaining = remaining[cut_at:].strip()
    if remaining:
        parts.append(remaining)
    return parts


def _element_page_numbers(element: NormalizedElement) -> list[int | None]:
    pages = [prov.page_no for prov in element.provenance if prov.page_no is not None]
    if not pages and element.page_no is not None:
        pages = [element.page_no]
    return pages


def _update_heading_path(heading_path: list[str], element: NormalizedElement) -> list[str]:
    level = max(0, element.level)
    next_path = heading_path[:level]
    next_path.append(element.text)
    return next_path


def _page_count(document: Any, elements: list[NormalizedElement]) -> int:
    num_pages = getattr(document, "num_pages", None)
    if callable(num_pages):
        try:
            return int(num_pages())
        except (TypeError, ValueError):
            pass
    pages = getattr(document, "pages", None)
    if isinstance(pages, dict) and pages:
        return len(pages)
    page_numbers = [page for element in elements for page in _element_page_numbers(element) if page]
    return max(page_numbers, default=0)


def _asset_id(path: Path) -> str:
    digest = hashlib.sha256()
    if path.exists() and path.is_file():
        with path.open("rb") as file:
            for block in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(block)
    else:
        digest.update(str(path).encode("utf-8"))
    return f"asset_{digest.hexdigest()[:16]}"


def _collect_conversion_errors(result: Any) -> list[str]:
    errors = []
    for attr in ("errors", "error"):
        value = getattr(result, attr, None)
        if not value:
            continue
        if isinstance(value, list):
            errors.extend(str(item) for item in value)
        else:
            errors.append(str(value))
    return errors


def _validate_supported_source(source_path: Path) -> None:
    suffix = source_path.suffix.lower()
    if suffix not in SUPPORTED_DOCUMENT_SUFFIXES:
        supported = ", ".join(sorted(SUPPORTED_DOCUMENT_SUFFIXES))
        raise ValueError(f"Unsupported document type `{suffix}`. Supported suffixes: {supported}")
    if not source_path.exists():
        raise FileNotFoundError(source_path)


def _validate_chunk_config(config: DoclingProcessConfig) -> None:
    if config.max_chunk_chars <= 0:
        raise ValueError("max_chunk_chars must be greater than 0.")
    if config.min_chunk_chars < 0:
        raise ValueError("min_chunk_chars must be greater than or equal to 0.")
    if config.min_chunk_chars > config.max_chunk_chars:
        raise ValueError("min_chunk_chars must be less than or equal to max_chunk_chars.")


def _set_if_present(obj: Any, attr: str, value: Any) -> None:
    if hasattr(obj, attr):
        setattr(obj, attr, value)


def _safe_ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    enum_value = getattr(value, "value", None)
    return str(enum_value if enum_value is not None else value)
