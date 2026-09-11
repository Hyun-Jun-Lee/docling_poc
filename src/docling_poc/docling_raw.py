"""Small helpers for inspecting Docling's native conversion output."""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv

SUPPORTED_DOCUMENT_SUFFIXES = {".pdf", ".docx", ".doc", ".pptx", ".ppt"}
RawOutputFormat = Literal["json", "markdown"]
ARTIFACTS_PATH_ENV_VAR = "DOCLING_ARTIFACTS_PATH"


def convert_document(
    source: str | Path,
    *,
    converter: Any | None = None,
    max_num_pages: int | None = None,
    max_file_size: int | None = None,
    picture_classifier: bool = False,
    picture_desc: bool = False,
) -> Any:
    """Return Docling's native ConversionResult for one supported document."""
    source_path = Path(source)
    _validate_supported_source(source_path)

    converter = converter or build_docling_converter(
        picture_classifier=picture_classifier,
        picture_desc=picture_desc,
    )
    convert_kwargs: dict[str, Any] = {"raises_on_error": False}
    if max_num_pages is not None:
        convert_kwargs["max_num_pages"] = max_num_pages
    if max_file_size is not None:
        convert_kwargs["max_file_size"] = max_file_size

    return converter.convert(source_path, **convert_kwargs)


def build_docling_converter(
    *,
    picture_classifier: bool = False,
    picture_desc: bool = False,
) -> Any:
    """Create a converter with Korean RapidOCR for PDF inputs.

    ``DOCLING_ARTIFACTS_PATH`` can be set in the process environment or the
    current working directory's ``.env`` file to use pre-downloaded models.
    """
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

    load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)
    artifacts_path_value = os.getenv(ARTIFACTS_PATH_ENV_VAR)

    pdf_options = PdfPipelineOptions(
        artifacts_path=Path(artifacts_path_value).expanduser()
        if artifacts_path_value
        else None,
        do_ocr=True,
        ocr_options=RapidOcrOptions(
            lang=["korean"],
            backend="onnxruntime",
        ),
        do_picture_classification=picture_classifier,
        do_picture_description=picture_desc,
        generate_picture_images=picture_classifier or picture_desc,
    )
    pdf_options.picture_classification_options.engine_options.top_k = 3
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


def export_conversion_result(result: Any) -> dict[str, Any]:
    """Export one conversion with its metadata and stable DoclingDocument JSON.

    ``ConversionResult.model_dump()`` includes runtime conversion metadata such
    as status, errors, timings, and confidence.  The document itself uses
    ``export_to_dict()`` so it retains Docling's public serialization schema.
    """
    model_dump = getattr(result, "model_dump", None)
    document = getattr(result, "document", None)
    if not callable(model_dump) or document is None:
        raise TypeError("Conversion result cannot be exported to JSON.")

    exported = model_dump(mode="json", exclude={"document"})
    if not isinstance(exported, dict):
        raise TypeError("Conversion result JSON must be an object.")

    exported["document"] = document.export_to_dict()
    return exported


def conversion_status(result: object) -> str:
    """Return Docling's conversion status as a stable lower-case string."""
    status = getattr(result, "status", "unknown")
    return str(getattr(status, "value", status)).lower()


def conversion_error_details(result: object) -> str:
    """Return the available Docling conversion errors as one message."""
    errors = getattr(result, "errors", None) or []
    messages = [
        str(getattr(error, "error_message", getattr(error, "message", error)))
        for error in errors
    ]
    return "; ".join(message for message in messages if message)


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
