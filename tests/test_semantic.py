from __future__ import annotations

import json
import sys

import pytest

from docling_poc.cli import main
from docling_poc.semantic import build_semantic_document


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
                "body": {"children": [{"$ref": "#/texts/0"}]},
                "texts": [{"text": "1. 모집개요", "formatting": {"bold": True}}],
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

    overview = build_semantic_document(document)["children"][0]

    assert overview["children"] == [
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
