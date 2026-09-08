"""Small helpers for inspecting Docling's native conversion output."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any, Literal

SUPPORTED_DOCUMENT_SUFFIXES = {".pdf", ".docx", ".doc", ".pptx", ".ppt"}
RawOutputFormat = Literal["json", "markdown"]


def convert_document(
    source: str | Path,
    *,
    converter: Any | None = None,
    max_num_pages: int | None = None,
    max_file_size: int | None = None,
) -> Any:
    """Return Docling's native ConversionResult for one supported document."""
    source_path = Path(source)
    _validate_supported_source(source_path)

    converter = converter or build_docling_converter()
    convert_kwargs: dict[str, Any] = {"raises_on_error": False}
    if max_num_pages is not None:
        convert_kwargs["max_num_pages"] = max_num_pages
    if max_file_size is not None:
        convert_kwargs["max_file_size"] = max_file_size

    return converter.convert(source_path, **convert_kwargs)


def build_docling_converter() -> Any:
    """Create a converter with Korean RapidOCR for PDF inputs."""
    try:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption
    except ImportError as exc:
        raise RuntimeError(
            "docling is required for conversion. Install the project dependencies first."
        ) from exc

    allowed_formats = [
        input_format
        for name in ("PDF", "DOCX", "DOC", "PPTX", "PPT")
        if (input_format := getattr(InputFormat, name, None)) is not None
    ]

    pdf_options = PdfPipelineOptions(
        do_ocr=True,
        ocr_options=RapidOcrOptions(
            lang=["korean"],
            backend="onnxruntime",
        ),
    )
    return DocumentConverter(
        allowed_formats=allowed_formats,
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_options),
        },
    )


def export_document(document: Any, *, output_format: RawOutputFormat) -> dict[str, Any] | str:
    """Export a DoclingDocument without changing its structure."""
    if output_format == "json":
        return document.export_to_dict()
    if output_format == "markdown":
        return str(document.export_to_markdown())
    raise ValueError(f"Unsupported output format: {output_format}")


def create_hierarchical_chunks(document: Any, *, chunker: Any | None = None) -> list[Any]:
    """Create Docling-native hierarchy-aware chunks from a DoclingDocument."""
    chunker = chunker or build_hierarchical_chunker()
    return list(chunker.chunk(document))


def build_hierarchical_chunker() -> Any:
    """Create Docling's native HierarchicalChunker."""
    try:
        from docling.chunking import HierarchicalChunker
    except ImportError as exc:
        raise RuntimeError(
            "docling is required for hierarchical chunking. Install the project dependencies first."
        ) from exc

    return HierarchicalChunker()


def export_hierarchical_chunks(chunks: Iterable[Any]) -> list[dict[str, Any]]:
    """Export native DocChunk objects to JSON-compatible dictionaries."""
    return [chunk.model_dump(mode="json") for chunk in chunks]


def _validate_supported_source(source_path: Path) -> None:
    if source_path.suffix.lower() not in SUPPORTED_DOCUMENT_SUFFIXES:
        allowed = ", ".join(sorted(SUPPORTED_DOCUMENT_SUFFIXES))
        raise ValueError(f"Unsupported document type: {source_path.suffix or '<none>'}. Allowed: {allowed}")
