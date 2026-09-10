from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from docling_poc.cli import main
from docling_poc.docling_raw import build_docling_converter, export_conversion_result
from docling_poc.semantic import build_semantic_document, matches_semantic_rules, ocr_picture


def test_build_semantic_document_groups_sections_lists_and_tables() -> None:
    document = {
        "origin": {"filename": "notice.docx"},
        "body": {
            "children": [
                {"$ref": "#/texts/0"},
                {"$ref": "#/groups/0"},
                {"$ref": "#/texts/3"},
                {"$ref": "#/texts/4"},
                {"$ref": "#/tables/0"},
                {"$ref": "#/texts/5"},
            ]
        },
        "texts": [
            {"self_ref": "#/texts/0", "text": "1. 모집개요", "formatting": {"bold": True}},
            {"self_ref": "#/texts/1", "text": "가. 모집대상 :", "formatting": {"bold": True}},
            {
                "self_ref": "#/texts/2",
                "text": "문화콘텐츠산업 창업(예비)자 중 개인사업자",
                "formatting": {"bold": False},
            },
            {"self_ref": "#/texts/3", "text": "나. 참여조건", "formatting": {"bold": True}},
            {"self_ref": "#/texts/4", "text": "(1) 경기도내 주소지 사업자등록(예정)자"},
            {"self_ref": "#/texts/5", "text": "2. 지원내용", "formatting": {"bold": True}},
        ],
        "groups": [
            {
                "self_ref": "#/groups/0",
                "children": [{"$ref": "#/texts/1"}, {"$ref": "#/texts/2"}],
            }
        ],
        "tables": [
            {
                "self_ref": "#/tables/0",
                "data": {"num_rows": 1, "num_cols": 1, "table_cells": [{"text": "표 내용"}]},
            }
        ],
        "pictures": [],
    }

    semantic = build_semantic_document(document)

    overview, support = semantic["children"]
    assert overview["title"] == "모집개요"
    assert overview["source_refs"] == ["#/texts/0"]

    target, conditions = overview["children"]
    assert target["title"] == "모집대상"
    assert target["children"] == [
        {
            "type": "paragraph",
            "text": "문화콘텐츠산업 창업(예비)자 중 개인사업자",
            "source_refs": ["#/groups/0", "#/texts/1", "#/texts/2"],
        }
    ]
    assert conditions["title"] == "참여조건"
    assert conditions["children"][0]["type"] == "list_item"
    assert conditions["children"][0]["marker"] == "1"
    assert conditions["children"][1]["type"] == "table"
    assert conditions["children"][1]["data"]["table_cells"][0]["text"] == "표 내용"

    assert support["title"] == "지원내용"


def test_semantic_json_cli_reads_a_docling_json_file(tmp_path, monkeypatch) -> None:
    source = tmp_path / "input.docling.json"
    output = tmp_path / "output.semantic.json"
    source.write_text(
        json.dumps(
            {
                "origin": {"filename": "notice.docx"},
                "body": {"children": [{"$ref": "#/texts/0"}, {"$ref": "#/texts/1"}]},
                "texts": [
                    {"text": "1. 모집개요", "formatting": {"bold": True}},
                    {"text": "가. 모집대상"},
                ],
                "groups": [],
                "tables": [],
                "pictures": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["docling-poc", str(source), "--to", "semantic-json", "--out", str(output)],
    )

    main()

    assert json.loads(output.read_text(encoding="utf-8"))["children"][0]["title"] == "모집개요"


def test_semantic_json_cli_reads_a_conversion_result_json_file(tmp_path, monkeypatch) -> None:
    source = tmp_path / "input.conversion.json"
    output = tmp_path / "output.semantic.json"
    source.write_text(
        json.dumps(
            {
                "status": "success",
                "confidence": {"mean_grade": "GOOD"},
                "document": {
                    "origin": {"filename": "notice.docx"},
                    "body": {"children": [{"$ref": "#/texts/0"}, {"$ref": "#/texts/1"}]},
                    "texts": [
                        {"text": "1. 모집개요", "formatting": {"bold": True}},
                        {"text": "가. 모집대상"},
                    ],
                    "groups": [],
                    "tables": [],
                    "pictures": [],
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["docling-poc", str(source), "--to", "semantic-json", "--out", str(output)],
    )

    main()

    assert json.loads(output.read_text(encoding="utf-8"))["children"][0]["title"] == "모집개요"


def test_semantic_rules_cli_outputs_a_boolean(tmp_path, monkeypatch) -> None:
    source = tmp_path / "input.docling.json"
    output = tmp_path / "semantic-rules.json"
    source.write_text(
        json.dumps(
            {
                "body": {"children": [{"$ref": "#/texts/0"}, {"$ref": "#/texts/1"}]},
                "texts": [
                    {"text": "1. 모집개요", "formatting": {"bold": True}},
                    {"text": "가. 모집대상"},
                ],
                "groups": [],
                "tables": [],
                "pictures": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["docling-poc", str(source), "--to", "semantic-rules", "--out", str(output)],
    )

    main()

    assert json.loads(output.read_text(encoding="utf-8")) is True


@pytest.mark.parametrize(
    ("cli_arguments", "expected_classifier", "expected_desc"),
    (
        (("--picture-classifier",), True, False),
        (("--picture-desc",), False, True),
        (("--picture-classifier", "--picture-desc"), True, True),
    ),
)
def test_json_cli_forwards_picture_enrichment_flags_to_conversion(
    tmp_path,
    monkeypatch,
    cli_arguments,
    expected_classifier,
    expected_desc,
) -> None:
    source = tmp_path / "input.pdf"
    output = tmp_path / "output.docling.json"
    source.write_bytes(b"%PDF-1.4")
    observed: dict[str, object] = {}

    class FakeDocument:
        def export_to_dict(self) -> dict[str, object]:
            return {"pictures": []}

    class FakeResult:
        status = SimpleNamespace(value="success")
        document = FakeDocument()

        def model_dump(self, *, mode: str, exclude: set[str]) -> dict[str, object]:
            assert mode == "json"
            assert exclude == {"document"}
            return {"status": "success", "confidence": {"mean_grade": "GOOD"}}

    def fake_convert(source_path, **kwargs):
        observed["source"] = source_path
        observed.update(kwargs)
        return FakeResult()

    monkeypatch.setattr("docling_poc.cli.convert_document", fake_convert)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "docling-poc",
            str(source),
            *cli_arguments,
            "--out",
            str(output),
        ],
    )

    main()

    assert observed["picture_classifier"] is expected_classifier
    assert observed["picture_desc"] is expected_desc
    output_json = json.loads(output.read_text(encoding="utf-8"))
    assert output_json["confidence"]["mean_grade"] == "GOOD"
    assert output_json["document"] == {"pictures": []}


def test_export_conversion_result_preserves_result_metadata_and_document() -> None:
    class FakeDocument:
        def export_to_dict(self) -> dict[str, object]:
            return {"schema_name": "DoclingDocument", "texts": []}

    class FakeResult:
        document = FakeDocument()

        def model_dump(self, *, mode: str, exclude: set[str]) -> dict[str, object]:
            assert mode == "json"
            assert exclude == {"document"}
            return {"status": "success", "confidence": {"low_grade": "FAIR"}}

    assert export_conversion_result(FakeResult()) == {
        "status": "success",
        "confidence": {"low_grade": "FAIR"},
        "document": {"schema_name": "DoclingDocument", "texts": []},
    }


@pytest.mark.parametrize(
    ("source_name", "output_format"),
    (
        ("input.docling.json", "semantic-json"),
        ("input.docling.json", "semantic-rules"),
        ("input.docx", "json"),
    ),
)
def test_cli_rejects_picture_enrichment_for_non_pdf_conversion(
    source_name, output_format, tmp_path, monkeypatch, capsys
) -> None:
    source = tmp_path / source_name
    source.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        ["docling-poc", str(source), "--to", output_format, "--picture-classifier"],
    )

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 2
    assert "--picture-classifier and --picture-desc require PDF conversion output." in capsys.readouterr().err


@pytest.mark.parametrize(
    ("picture_classifier", "picture_desc"),
    ((False, False), (True, False), (False, True), (True, True)),
)
def test_build_docling_converter_configures_pdf_picture_enrichment(
    picture_classifier, picture_desc
) -> None:
    from docling.datamodel.base_models import InputFormat

    converter = build_docling_converter(
        picture_classifier=picture_classifier,
        picture_desc=picture_desc,
    )
    pdf_options = converter.format_to_options[InputFormat.PDF].pipeline_options

    assert pdf_options.do_picture_classification is picture_classifier
    assert pdf_options.do_picture_description is picture_desc
    assert pdf_options.generate_picture_images is (picture_classifier or picture_desc)


def test_build_docling_converter_reads_artifacts_path_from_dotenv(tmp_path, monkeypatch) -> None:
    from docling.datamodel.base_models import InputFormat

    artifacts_path = tmp_path / "docling-models"
    (tmp_path / ".env").write_text(
        f"DOCLING_ARTIFACTS_PATH={artifacts_path}\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DOCLING_ARTIFACTS_PATH", raising=False)

    converter = build_docling_converter()

    pdf_options = converter.format_to_options[InputFormat.PDF].pipeline_options
    assert pdf_options.artifacts_path == artifacts_path


def test_semantic_json_cli_can_enable_picture_ocr(tmp_path, monkeypatch) -> None:
    source = tmp_path / "input.docling.json"
    output = tmp_path / "output.semantic.json"
    source.write_text(
        json.dumps(
            {
                "body": {"children": []},
                "texts": [],
                "groups": [],
                "tables": [],
                "pictures": [],
            }
        ),
        encoding="utf-8",
    )
    observed: dict[str, object] = {}

    def fake_build(document: dict[str, object], *, ocr_pictures: bool = False) -> dict[str, bool]:
        observed["document"] = document
        observed["ocr_pictures"] = ocr_pictures
        return {"ocr_pictures": ocr_pictures}

    monkeypatch.setattr("docling_poc.cli.build_semantic_document", fake_build)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "docling-poc",
            str(source),
            "--to",
            "semantic-json",
            "--ocr-pictures",
            "--out",
            str(output),
        ],
    )

    main()

    assert observed["ocr_pictures"] is True
    assert json.loads(output.read_text(encoding="utf-8")) == {"ocr_pictures": True}


def test_semantic_json_cli_reports_picture_ocr_errors(tmp_path, monkeypatch, capsys) -> None:
    source = tmp_path / "input.docling.json"
    source.write_text(
        json.dumps(
            {
                "body": {"children": []},
                "texts": [],
                "groups": [],
                "tables": [],
                "pictures": [],
            }
        ),
        encoding="utf-8",
    )

    def fail_build(document: dict[str, object], *, ocr_pictures: bool = False) -> None:
        raise RuntimeError("Picture OCR failed: no error details")

    monkeypatch.setattr("docling_poc.cli.build_semantic_document", fail_build)
    monkeypatch.setattr(
        sys,
        "argv",
        ["docling-poc", str(source), "--to", "semantic-json", "--ocr-pictures"],
    )

    with pytest.raises(SystemExit):
        main()

    assert "Could not build semantic JSON: Picture OCR failed: no error details" in capsys.readouterr().err


@pytest.mark.parametrize("output_format", ["json", "semantic-rules"])
def test_cli_rejects_picture_ocr_outside_semantic_json(output_format, tmp_path, monkeypatch, capsys) -> None:
    source = tmp_path / "input.docling.json"
    source.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        ["docling-poc", str(source), "--to", output_format, "--ocr-pictures"],
    )

    with pytest.raises(SystemExit):
        main()

    assert "--ocr-pictures can only be used with --to semantic-json." in capsys.readouterr().err


def test_semantic_json_cli_honors_max_file_size(tmp_path, monkeypatch, capsys) -> None:
    source = tmp_path / "input.docling.json"
    source.write_text('{"body":{"children":[]}}', encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        ["docling-poc", str(source), "--to", "semantic-json", "--max-file-size", "1"],
    )

    with pytest.raises(SystemExit):
        main()

    assert "Input file exceeds --max-file-size (1 bytes)." in capsys.readouterr().err


def test_ocr_picture_decodes_docling_image_data_uri_for_rapidocr() -> None:
    converted: dict[str, object] = {}

    class FakeConverter:
        def convert(self, source: object, *, raises_on_error: bool) -> object:
            assert isinstance(source, Path)
            converted["bytes"] = source.read_bytes()
            converted["suffix"] = source.suffix
            converted["raises_on_error"] = raises_on_error
            return SimpleNamespace(
                status="success",
                document=SimpleNamespace(export_to_markdown=lambda: "<!-- image -->\n\n이미지 OCR 결과"),
            )

    picture = {
        "image": {
            "mimetype": "image/png",
            "uri": "data:image/png;base64," + base64.b64encode(b"png bytes").decode(),
        }
    }

    ocr = ocr_picture(picture, converter=FakeConverter())

    assert converted == {
        "bytes": b"png bytes",
        "suffix": ".png",
        "raises_on_error": False,
    }
    assert ocr == {
        "status": "completed",
        "engine": "rapidocr",
        "text": "이미지 OCR 결과",
    }


@pytest.mark.parametrize(
    ("picture", "error"),
    [
        ({"image": {"mimetype": "text/plain", "uri": "data:text/plain;base64,WA=="}}, "MIME"),
        ({"image": {"mimetype": "image/png"}}, "image.uri"),
        ({"image": {"mimetype": "image/png", "uri": "not-a-data-uri"}}, "valid data URI"),
        (
            {"image": {"mimetype": "image/png", "uri": "data:image/jpeg;base64,WA=="}},
            "does not match",
        ),
        ({"image": {"mimetype": "image/png", "uri": "data:image/png;base64,%%%"}}, "invalid base64"),
    ],
)
def test_ocr_picture_rejects_invalid_data_uris(picture, error) -> None:
    with pytest.raises((TypeError, ValueError), match=error):
        ocr_picture(picture)


def test_ocr_picture_reports_docling_conversion_errors() -> None:
    class FailedConverter:
        def convert(self, source: object, *, raises_on_error: bool) -> object:
            return SimpleNamespace(status="failure", errors=[SimpleNamespace(error_message="OCR engine error")])

    picture = {"image": {"mimetype": "image/png", "uri": "data:image/png;base64,WA=="}}

    with pytest.raises(RuntimeError, match="OCR engine error"):
        ocr_picture(picture, converter=FailedConverter())


def test_semantic_document_adds_opt_in_picture_ocr_result() -> None:
    document = {
        "body": {"children": [{"$ref": "#/pictures/0"}]},
        "texts": [],
        "groups": [],
        "tables": [],
        "pictures": [
            {
                "self_ref": "#/pictures/0",
                "captions": [],
                "references": [],
                "image": {"mimetype": "image/png", "uri": "data:image/png;base64,WA=="},
            }
        ],
    }

    semantic = build_semantic_document(
        document,
        ocr_pictures=True,
        picture_ocr=lambda picture: {
            "status": "completed",
            "engine": "rapidocr",
            "text": picture["image"]["mimetype"],
        },
    )

    assert semantic["children"] == [
        {
            "type": "picture",
            "source_refs": ["#/pictures/0"],
            "captions": [],
            "references": [],
            "ocr": {
                "status": "completed",
                "engine": "rapidocr",
                "text": "image/png",
            },
        }
    ]


def test_semantic_document_keeps_other_content_when_picture_ocr_fails() -> None:
    document = {
        "body": {"children": [{"$ref": "#/texts/0"}, {"$ref": "#/pictures/0"}]},
        "texts": [{"text": "본문"}],
        "groups": [],
        "tables": [],
        "pictures": [{"captions": [], "references": [], "image": {}}],
    }

    def fail_ocr(picture: dict[str, object]) -> dict[str, str]:
        raise ValueError("잘못된 이미지")

    semantic = build_semantic_document(document, ocr_pictures=True, picture_ocr=fail_ocr)

    assert semantic["children"] == [
        {"type": "paragraph", "text": "본문", "source_refs": ["#/texts/0"]},
        {
            "type": "picture",
            "source_refs": ["#/pictures/0"],
            "captions": [],
            "references": [],
            "ocr": {"status": "failed", "error": "잘못된 이미지"},
        },
    ]


def test_semantic_picture_ocr_uses_a_fresh_docling_converter_per_picture(monkeypatch) -> None:
    created_converters: list[object] = []

    class FakeConverter:
        def convert(self, source: object, *, raises_on_error: bool) -> object:
            return SimpleNamespace(
                status="success",
                document=SimpleNamespace(export_to_markdown=lambda: "OCR 결과"),
            )

    def fake_build_converter() -> FakeConverter:
        converter = FakeConverter()
        created_converters.append(converter)
        return converter

    document = {
        "body": {"children": [{"$ref": "#/pictures/0"}, {"$ref": "#/pictures/1"}]},
        "texts": [],
        "groups": [],
        "tables": [],
        "pictures": [
            {
                "image": {"mimetype": "image/png", "uri": "data:image/png;base64,WA=="},
                "captions": [],
                "references": [],
            },
            {
                "image": {"mimetype": "image/png", "uri": "data:image/png;base64,WQ=="},
                "captions": [],
                "references": [],
            },
        ],
    }
    monkeypatch.setattr("docling_poc.semantic._build_image_ocr_converter", fake_build_converter)

    build_semantic_document(document, ocr_pictures=True)

    assert len(created_converters) == 2


def test_semantic_rules_require_bold_primary_and_korean_subheading() -> None:
    matching_document = {
        "body": {"children": [{"$ref": "#/texts/0"}, {"$ref": "#/texts/1"}]},
        "texts": [
            {"text": "1. 모집개요", "formatting": {"bold": True}},
            {"text": "가. 모집대상"},
        ],
        "groups": [],
        "tables": [],
        "pictures": [],
    }
    generic_document = {
        **matching_document,
        "texts": [
            {"text": "1. 일반 목록", "formatting": {"bold": False}},
            {"text": "본문 문단"},
        ],
    }

    assert matches_semantic_rules(matching_document) is True
    assert matches_semantic_rules(generic_document) is False

    semantic = build_semantic_document(generic_document)
    assert semantic["semantic_rules_matched"] is False
    assert semantic["children"][0]["type"] == "paragraph"


def test_build_semantic_document_recognizes_unbolded_outline_and_common_list_markers() -> None:
    document = {
        "body": {
            "children": [
                {"$ref": "#/texts/0"},
                {"$ref": "#/texts/1"},
                {"$ref": "#/texts/2"},
                {"$ref": "#/groups/0"},
            ]
        },
        "texts": [
            {"text": "1. 모집개요", "formatting": {"bold": True}},
            {"text": "가. 참여조건", "formatting": {"bold": False}},
            {"text": "① 경기도내 주소지 사업자등록(예정)자"},
            {"text": "‧ 제출서류를 확인하세요"},
        ],
        "groups": [{"children": [{"$ref": "#/texts/3"}]}],
        "tables": [],
        "pictures": [],
    }

    overview = build_semantic_document(document)["children"][0]
    conditions = overview["children"][0]

    assert conditions["type"] == "section"
    assert conditions["title"] == "참여조건"
    assert conditions["children"] == [
        {
            "type": "list_item",
            "kind": "ordered",
            "marker": "①",
            "text": "경기도내 주소지 사업자등록(예정)자",
            "source_refs": ["#/texts/2"],
        },
        {
            "type": "list_item",
            "kind": "bullet",
            "marker": "‧",
            "text": "제출서류를 확인하세요",
            "source_refs": ["#/groups/0", "#/texts/3"],
        },
    ]


@pytest.mark.parametrize("ref", ["#/texts/-1", "#/texts/1"])
def test_build_semantic_document_rejects_invalid_references(ref) -> None:
    document = {
        "body": {"children": [{"$ref": ref}]},
        "texts": [{"text": "only item"}],
        "groups": [],
        "tables": [],
        "pictures": [],
    }

    with pytest.raises(ValueError, match="reference"):
        build_semantic_document(document)


def test_build_semantic_document_preserves_nested_groups_and_native_form_items() -> None:
    document = {
        "body": {
            "children": [
                {"$ref": "#/texts/0"},
                {"$ref": "#/groups/0"},
                {"$ref": "#/key_value_items/0"},
                {"$ref": "#/form_items/0"},
                {"$ref": "#/texts/2"},
            ]
        },
        "texts": [
            {"text": "1. 모집개요", "formatting": {"bold": True}},
            {"text": "중첩 그룹 본문"},
            {"text": "1. 일반 번호 목록", "formatting": {"bold": False}},
        ],
        "groups": [
            {"children": [{"$ref": "#/groups/1"}]},
            {"children": [{"$ref": "#/texts/1"}]},
        ],
        "tables": [],
        "pictures": [],
        "key_value_items": [{"self_ref": "#/key_value_items/0", "pairs": []}],
        "form_items": [{"self_ref": "#/form_items/0", "value": "checked"}],
    }

    semantic = build_semantic_document(document)

    assert semantic["semantic_rules_matched"] is False
    assert semantic["children"] == [
        {
            "type": "paragraph",
            "text": "1. 모집개요",
            "source_refs": ["#/texts/0"],
        },
        {
            "type": "paragraph",
            "text": "중첩 그룹 본문",
            "source_refs": ["#/groups/0", "#/groups/1", "#/texts/1"],
        },
        {
            "type": "key_value_item",
            "source_refs": ["#/key_value_items/0"],
            "data": {"self_ref": "#/key_value_items/0", "pairs": []},
        },
        {
            "type": "form_item",
            "source_refs": ["#/form_items/0"],
            "data": {"self_ref": "#/form_items/0", "value": "checked"},
        },
        {
            "type": "paragraph",
            "text": "1. 일반 번호 목록",
            "source_refs": ["#/texts/2"],
        },
    ]
