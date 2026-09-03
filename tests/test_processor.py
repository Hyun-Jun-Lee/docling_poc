from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar

import pytest

from docling_poc.models import ElementProvenance, NormalizedElement
from docling_poc.processor import DoclingProcessConfig, build_chunks, normalize_docling_document


@dataclass
class Label:
    value: str


@dataclass
class BBox:
    l: float
    t: float
    r: float
    b: float


@dataclass
class Prov:
    page_no: int
    bbox: BBox | None = None


class TextItem:
    def __init__(self, label: str, text: str, page_no: int, self_ref: str):
        self.label = Label(label)
        self.text = text
        self.prov = [Prov(page_no, BBox(1, 2, 3, 4))]
        self.self_ref = self_ref


class TableItem:
    label = Label("table")
    prov: ClassVar[list[Prov]] = [Prov(2)]
    self_ref = "#/tables/0"

    def export_to_markdown(self, doc=None):
        return "| 항목 | 값 |\n| --- | --- |\n| 압력 | 정상 |"


class PictureItem:
    label = Label("picture")
    prov: ClassVar[list[Prov]] = [Prov(2)]
    self_ref = "#/pictures/0"


class FakeDoc:
    pages: ClassVar[dict[int, object]] = {1: object(), 2: object()}

    def __init__(self):
        self.items = [
            (TextItem("title", "CMP 설비 점검 보고서", 1, "#/texts/0"), 0),
            (TextItem("paragraph", "진공펌프 압력과 필터 상태를 점검했다.", 1, "#/texts/1"), 1),
            (TableItem(), 1),
            (PictureItem(), 1),
            (TextItem("section_header", "조치 내역", 2, "#/texts/2"), 1),
            (TextItem("paragraph", "필터를 교체하고 재가동 후 압력이 안정화되었다.", 2, "#/texts/3"), 2),
        ]

    def iterate_items(self, traverse_pictures=False):
        return iter(self.items)

    def export_to_markdown(self, traverse_pictures=False):
        self.traverse_pictures = traverse_pictures
        return "# CMP 설비 점검 보고서"

    def num_pages(self):
        return 2


class SparseDoc:
    pages: ClassVar[dict[int, object]] = {1: object(), 2: object(), 3: object()}

    def iterate_items(self, traverse_pictures=False):
        return iter(
            [
                (TextItem("paragraph", "ㄱㄴ�", 1, "#/texts/0"), 0),
                (PictureItem(), 2),
            ]
        )

    def export_to_markdown(self):
        return ""

    def num_pages(self):
        return 3


def test_normalize_docling_document_preserves_tables_pictures_and_provenance(tmp_path: Path):
    source = tmp_path / "report.pdf"
    source.write_bytes(b"sample")

    processed = normalize_docling_document(
        FakeDoc(),
        source_path=source,
        config=DoclingProcessConfig(max_chunk_chars=180, min_chunk_chars=20),
    )

    assert processed.source_type == "pdf"
    assert processed.markdown == "# CMP 설비 점검 보고서"
    assert [element.kind for element in processed.elements] == [
        "title",
        "paragraph",
        "table",
        "picture",
        "section_header",
        "paragraph",
    ]
    assert processed.elements[2].markdown.startswith("| 항목 |")
    assert processed.elements[3].text == "[Picture]"
    assert processed.elements[0].provenance[0].bbox.left == 1.0
    assert processed.profile.has_tables is True
    assert processed.profile.has_pictures is True
    assert processed.profile.ocr.hangul_ratio > 0


def test_normalize_exports_markdown_with_picture_traversal(tmp_path: Path):
    source = tmp_path / "report.pdf"
    source.write_bytes(b"sample")
    document = FakeDoc()

    normalize_docling_document(document, source_path=source)

    assert document.traverse_pictures is True


def test_build_chunks_keeps_reading_order_and_page_sets(tmp_path: Path):
    source = tmp_path / "deck.pptx"
    source.write_bytes(b"sample")
    processed = normalize_docling_document(
        FakeDoc(),
        source_path=source,
        config=DoclingProcessConfig(max_chunk_chars=90, min_chunk_chars=20),
    )

    assert len(processed.chunks) >= 2
    assert processed.chunks[0].text.index("CMP 설비") < processed.chunks[0].text.index("진공펌프")
    assert any("압력 | 정상" in chunk.text for chunk in processed.chunks)
    assert processed.chunks[-1].heading_path == ["CMP 설비 점검 보고서", "조치 내역"]
    assert processed.chunks[-1].page_numbers == [2]


def test_build_chunks_keeps_short_intro_under_previous_heading():
    elements = [
        _element("e0", 0, "title", "문서 개요", 1, level=0),
        _element("e1", 1, "paragraph", "짧은 소개", 1, level=1),
        _element("e2", 2, "section_header", "조치 내역", 1, level=1),
        _element("e3", 3, "paragraph", "필터 교체", 1, level=2),
    ]

    chunks = build_chunks(
        elements,
        asset_id="asset_test",
        config=DoclingProcessConfig(max_chunk_chars=200, min_chunk_chars=80),
    )

    assert [chunk.element_ids for chunk in chunks] == [["e0", "e1"], ["e2", "e3"]]
    assert chunks[0].heading_path == ["문서 개요"]
    assert chunks[1].heading_path == ["문서 개요", "조치 내역"]


def test_build_chunks_ignores_empty_elements():
    chunks = build_chunks([], asset_id="asset_test")

    assert chunks == []


def test_build_chunks_allows_overflow_until_minimum_size_then_splits():
    elements = [
        _element("e0", 0, "title", "점검 개요", 1, level=0),
        _element("e1", 1, "paragraph", "A" * 40, 1, level=1),
        _element("e2", 2, "paragraph", "B" * 40, 1, level=1),
        _element("e3", 3, "paragraph", "C" * 20, 2, level=1),
    ]

    chunks = build_chunks(
        elements,
        asset_id="asset_test",
        config=DoclingProcessConfig(max_chunk_chars=75, min_chunk_chars=60),
    )

    assert [chunk.element_ids for chunk in chunks] == [["e0", "e1", "e2"], ["e3"]]
    assert chunks[0].heading_path == ["점검 개요"]
    assert chunks[1].page_numbers == [2]


def test_build_chunks_splits_when_current_chunk_is_large_enough():
    elements = [
        _element("e0", 0, "title", "점검 개요", 1, level=0),
        _element("e1", 1, "paragraph", "A" * 40, 1, level=1),
        _element("e2", 2, "paragraph", "B" * 40, 2, level=1),
    ]

    chunks = build_chunks(
        elements,
        asset_id="asset_test",
        config=DoclingProcessConfig(max_chunk_chars=75, min_chunk_chars=30),
    )

    assert [chunk.element_ids for chunk in chunks] == [["e0", "e1"], ["e2"]]
    assert chunks[0].page_numbers == [1]
    assert chunks[1].page_numbers == [2]


def test_build_chunks_splits_single_oversized_element():
    elements = [
        _element("e0", 0, "title", "본문", 1, level=0),
        _element("e1", 1, "paragraph", "A" * 95, 1, level=1),
    ]

    chunks = build_chunks(
        elements,
        asset_id="asset_test",
        config=DoclingProcessConfig(max_chunk_chars=40, min_chunk_chars=10),
    )

    assert [chunk.element_ids for chunk in chunks] == [["e0"], ["e1"], ["e1"], ["e1"]]
    assert all(len(chunk.text) <= 40 for chunk in chunks)
    assert chunks[1].metadata["split_from_oversized_element"] is True
    assert chunks[1].metadata["split_part_count"] == 3


def test_build_chunks_rejects_invalid_size_config():
    with pytest.raises(ValueError, match="min_chunk_chars"):
        build_chunks(
            [_element("e0", 0, "paragraph", "text", 1)],
            asset_id="asset_test",
            config=DoclingProcessConfig(max_chunk_chars=10, min_chunk_chars=20),
        )


def test_ocr_quality_flags_sparse_abnormal_image_heavy_document(tmp_path: Path):
    source = tmp_path / "scan.pdf"
    source.write_bytes(b"sample")

    processed = normalize_docling_document(
        SparseDoc(),
        source_path=source,
        config=DoclingProcessConfig(ocr_quality_threshold=0.8),
    )

    assert processed.profile.ocr.needs_fallback is True
    assert processed.profile.ocr.pages_with_text == [1]
    assert processed.profile.ocr.pages_without_text == [2, 3]
    assert "low_text_volume" in processed.profile.ocr.reasons
    assert "low_page_text_coverage" in processed.profile.ocr.reasons
    assert "high_abnormal_character_ratio" in processed.profile.ocr.reasons
    assert "image_heavy_low_text" in processed.profile.ocr.reasons


def test_process_document_passes_converter_limits_and_preserves_status(tmp_path: Path):
    from docling_poc.processor import process_document

    source = tmp_path / "report.docx"
    source.write_bytes(b"sample")
    converter = FakeConverter(SimpleNamespace(document=FakeDoc(), status="partial", errors=["warn"]))

    processed = process_document(
        source,
        converter=converter,
        config=DoclingProcessConfig(max_num_pages=3, max_file_size=1024),
    )

    assert converter.calls == [
        {
            "source": source,
            "raises_on_error": False,
            "max_num_pages": 3,
            "max_file_size": 1024,
        }
    ]
    assert processed.status == "partial"
    assert processed.errors == ["warn"]


def test_process_document_raises_when_converter_returns_no_document(tmp_path: Path):
    from docling_poc.processor import process_document

    source = tmp_path / "report.pdf"
    source.write_bytes(b"sample")
    converter = FakeConverter(SimpleNamespace(document=None, status="failure", error="parse failed"))

    with pytest.raises(RuntimeError, match="parse failed"):
        process_document(source, converter=converter)


def test_process_document_rejects_non_document_suffix(tmp_path: Path):
    from docling_poc.processor import process_document

    source = tmp_path / "data.csv"
    source.write_text("a,b\n1,2")

    with pytest.raises(ValueError, match="Unsupported document type"):
        process_document(source, converter=object())


def test_cli_writes_json_and_forwards_options(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from docling_poc import cli

    source = tmp_path / "deck.pptx"
    output = tmp_path / "out" / "deck.json"
    source.write_bytes(b"sample")
    calls = []

    def fake_process_document(path, *, config):
        calls.append((path, config))
        return SimpleNamespace(to_dict=lambda: {"source": str(path), "chunk_size": config.max_chunk_chars})

    monkeypatch.setattr(cli, "process_document", fake_process_document)
    monkeypatch.setattr(
        "sys.argv",
        [
            "docling-poc",
            str(source),
            "--out",
            str(output),
            "--max-chunk-chars",
            "900",
            "--min-chunk-chars",
            "120",
            "--ocr-lang",
            "ko",
            "--ocr-lang",
            "en",
            "--disable-ocr",
        ],
    )

    cli.main()

    assert output.read_text(encoding="utf-8").strip().startswith("{")
    assert calls[0][0] == source
    assert calls[0][1].max_chunk_chars == 900
    assert calls[0][1].min_chunk_chars == 120
    assert calls[0][1].ocr_languages == ("ko", "en")
    assert calls[0][1].enable_ocr is False


def test_cli_rejects_output_equal_to_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from docling_poc import cli

    source = tmp_path / "report.pdf"
    source.write_bytes(b"%PDF sample")
    monkeypatch.setattr("sys.argv", ["docling-poc", str(source), "--out", str(source)])

    with pytest.raises(SystemExit):
        cli.main()

    assert source.read_bytes() == b"%PDF sample"


def test_cli_prints_json_to_stdout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys):
    from docling_poc import cli

    source = tmp_path / "report.pdf"
    source.write_bytes(b"sample")
    monkeypatch.setattr(
        cli,
        "process_document",
        lambda path, *, config: SimpleNamespace(to_dict=lambda: {"source": str(path)}),
    )
    monkeypatch.setattr("sys.argv", ["docling-poc", str(source)])

    cli.main()

    assert '"source"' in capsys.readouterr().out


class FakeConverter:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def convert(self, source, **kwargs):
        self.calls.append({"source": source, **kwargs})
        return self.result


def _element(
    element_id: str,
    sequence_no: int,
    kind: str,
    text: str,
    page_no: int,
    *,
    level: int = 0,
) -> NormalizedElement:
    return NormalizedElement(
        element_id=element_id,
        sequence_no=sequence_no,
        kind=kind,
        text=text,
        level=level,
        page_no=page_no,
        provenance=[ElementProvenance(page_no=page_no)],
    )
