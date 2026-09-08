from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from docling_poc.docling_raw import (
    convert_document,
    create_hierarchical_chunks,
    export_document,
    export_hierarchical_chunks,
)


class FakeDocument:
    def export_to_dict(self):
        return {
            "schema_name": "DoclingDocument",
            "name": "report",
            "texts": [{"text": "점검 결과"}],
        }

    def export_to_markdown(self):
        return "# 점검 결과\n\n정상입니다."


class FakeConverter:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def convert(self, source, **kwargs):
        self.calls.append({"source": source, **kwargs})
        return self.result


class FakeChunk:
    def __init__(self, text: str):
        self.text = text

    def model_dump(self, *, mode: str):
        assert mode == "json"
        return {"text": self.text, "meta": {"headings": ["점검 결과"]}}


class FakeChunker:
    def __init__(self, chunks):
        self.chunks = chunks
        self.documents = []

    def chunk(self, document):
        self.documents.append(document)
        return iter(self.chunks)


def test_convert_document_returns_docling_conversion_result_without_normalization(tmp_path: Path):
    source = tmp_path / "report.docx"
    source.write_bytes(b"sample")
    result = SimpleNamespace(document=FakeDocument(), status="success")
    converter = FakeConverter(result)

    actual = convert_document(
        source,
        converter=converter,
        max_num_pages=3,
        max_file_size=1024,
    )

    assert actual is result
    assert converter.calls == [
        {
            "source": source,
            "raises_on_error": False,
            "max_num_pages": 3,
            "max_file_size": 1024,
        }
    ]


def test_export_document_returns_raw_docling_json_dict():
    payload = export_document(FakeDocument(), output_format="json")

    assert payload == {
        "schema_name": "DoclingDocument",
        "name": "report",
        "texts": [{"text": "점검 결과"}],
    }


def test_export_document_returns_docling_markdown():
    payload = export_document(FakeDocument(), output_format="markdown")

    assert payload == "# 점검 결과\n\n정상입니다."


def test_convert_document_rejects_unsupported_suffix(tmp_path: Path):
    source = tmp_path / "data.csv"
    source.write_text("a,b\n1,2")

    with pytest.raises(ValueError, match="Unsupported document type"):
        convert_document(source, converter=FakeConverter(SimpleNamespace(document=FakeDocument())))


def test_convert_document_returns_failed_docling_result_unchanged(tmp_path: Path):
    source = tmp_path / "report.pptx"
    source.write_bytes(b"sample")
    result = SimpleNamespace(document=None, status="failure", errors=["parse failed"])
    converter = FakeConverter(result)

    assert convert_document(source, converter=converter) is result


def test_export_document_rejects_unknown_format():
    with pytest.raises(ValueError, match="Unsupported output format"):
        export_document(FakeDocument(), output_format="yaml")


def test_create_hierarchical_chunks_uses_docling_chunker_with_original_document():
    document = FakeDocument()
    chunks = [FakeChunk("첫 번째 청크"), FakeChunk("두 번째 청크")]
    chunker = FakeChunker(chunks)

    actual = create_hierarchical_chunks(document, chunker=chunker)

    assert actual == chunks
    assert chunker.documents == [document]


def test_export_hierarchical_chunks_returns_docling_chunk_json():
    payload = export_hierarchical_chunks([FakeChunk("첫 번째 청크")])

    assert payload == [{"text": "첫 번째 청크", "meta": {"headings": ["점검 결과"]}}]


def test_cli_writes_raw_docling_document_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from docling_poc import cli

    source = tmp_path / "report.docx"
    output = tmp_path / "out" / "report.json"
    source.write_bytes(b"sample")
    result = SimpleNamespace(document=FakeDocument(), status="success")
    monkeypatch.setattr(cli, "convert_document", lambda *args, **kwargs: result)
    monkeypatch.setattr(
        sys,
        "argv",
        ["docling-poc", str(source), "--out", str(output), "--to", "json"],
    )

    cli.main()

    assert json.loads(output.read_text(encoding="utf-8")) == FakeDocument().export_to_dict()


def test_cli_rejects_failed_conversion_even_when_docling_returns_a_document(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from docling_poc import cli

    source = tmp_path / "report.docx"
    output = tmp_path / "out" / "report.json"
    source.write_bytes(b"sample")
    result = SimpleNamespace(
        document=FakeDocument(),
        status="failure",
        errors=["parse failed"],
    )
    monkeypatch.setattr(cli, "convert_document", lambda *args, **kwargs: result)
    monkeypatch.setattr(
        sys,
        "argv",
        ["docling-poc", str(source), "--out", str(output)],
    )

    with pytest.raises(SystemExit, match="2"):
        cli.main()

    assert not output.exists()


def test_cli_writes_hierarchical_chunk_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from docling_poc import cli

    source = tmp_path / "report.pptx"
    output = tmp_path / "out" / "report.chunks.json"
    source.write_bytes(b"sample")
    document = FakeDocument()
    result = SimpleNamespace(document=document, status="success")
    chunks = [FakeChunk("첫 번째 청크")]
    monkeypatch.setattr(cli, "convert_document", lambda *args, **kwargs: result)
    monkeypatch.setattr(cli, "create_hierarchical_chunks", lambda actual: chunks if actual is document else [])
    monkeypatch.setattr(
        sys,
        "argv",
        ["docling-poc", str(source), "--out", str(output), "--to", "hierarchical-chunks"],
    )

    cli.main()

    assert json.loads(output.read_text(encoding="utf-8")) == [
        {"text": "첫 번째 청크", "meta": {"headings": ["점검 결과"]}}
    ]
