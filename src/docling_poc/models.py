from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class BBox:
    left: float
    top: float
    right: float
    bottom: float
    coord_origin: str | None = None


@dataclass
class ElementProvenance:
    page_no: int | None = None
    bbox: BBox | None = None


@dataclass
class NormalizedElement:
    element_id: str
    sequence_no: int
    kind: str
    text: str
    markdown: str | None = None
    level: int = 0
    page_no: int | None = None
    provenance: list[ElementProvenance] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DocumentChunk:
    chunk_id: str
    sequence_no: int
    text: str
    element_ids: list[str]
    element_kinds: list[str]
    page_numbers: list[int]
    heading_path: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class OcrQualitySignals:
    text_char_count: int
    page_count: int
    text_coverage_ratio: float
    hangul_ratio: float
    abnormal_char_ratio: float
    table_count: int
    picture_count: int
    pages_with_text: list[int]
    pages_without_text: list[int]
    quality_score: float
    needs_fallback: bool
    reasons: list[str] = field(default_factory=list)


@dataclass
class DocumentProfile:
    source_type: str
    page_count: int
    element_count: int
    element_counts: dict[str, int]
    has_tables: bool
    has_pictures: bool
    ocr: OcrQualitySignals


@dataclass
class ProcessedDocument:
    asset_id: str
    source_path: str
    source_type: str
    status: str
    markdown: str
    elements: list[NormalizedElement]
    chunks: list[DocumentChunk]
    profile: DocumentProfile
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
