import json
from copy import deepcopy

from docling_poc.comparison_evidence import (
    docling_excerpts,
    json_excerpt,
    markup_excerpts,
    tika_excerpts,
)


def test_json_preserves_values_and_reports_omissions_outside_content():
    raw = {"prov": [], "nullable": None, "bold": False, "text": "문장\n  그대로",
           "cells": [1, 2, 3, 4], "image": {"uri": "data:image/png;base64,secret"}}
    before = deepcopy(raw)
    excerpt = json_excerpt(raw, "#/tables/0")
    assert json.loads(excerpt["content"]) == {
        "prov": [], "nullable": None, "bold": False, "text": "문장\n  그대로",
        "cells": [1, 2, 3], "image": {}}
    assert "전체 4개 중 앞 3개" in excerpt["note"]
    assert "#/tables/0/image/uri" in excerpt["note"]
    assert "secret" not in excerpt["content"]
    assert raw == before


def test_native_table_keeps_cells_together_and_empty_provenance_is_not_invented():
    cell = {"text": "첫 셀", "row_span": 1, "col_span": 2, "column_header": True}
    table = {"self_ref": "#/tables/0", "label": "table", "prov": [],
             "data": {"num_rows": 1, "num_cols": 2, "table_cells": [cell]}}
    result = docling_excerpts({"document": {"tables": [table]}})
    assert json.loads(result["tables"][0]["content"]) == table
    assert result["tables"][0]["source"] == "#/document/tables/0"
    assert json.loads(result["location"][0]["content"]) == {
        "self_ref": "#/tables/0", "label": "table", "prov": []}
    assert "page_no" not in result["location"][0]["content"]


def test_formatting_selects_actual_emphasis_and_retains_exact_markdown():
    paragraph = "&#32; **실제 강조** 뒤  \n"
    table = "| A | B |\n|---|---|\n|1|2|\n"
    text = "앞부분 " * 100 + "\n\n```\n**가짜**\n```\n\n" + paragraph + "\n" + table
    result = markup_excerpts(text, "#/0/tk:content")
    assert [e["content"] for e in result["formatting"]] == [paragraph]
    assert result["tables"][0]["content"] == table
    assert "가짜" not in result["formatting"][0]["content"]
    assert f'[{text.index(paragraph)}:{text.index(paragraph) + len(paragraph)})' in (
        result["formatting"][0]["source"])


def test_html_keeps_source_tags_entities_and_ignores_scripts():
    text = ('<html><body><script><b>가짜</b></script><p><u class="x">밑줄&amp;</u></p>'
            '<table><tr><td colspan="2">A</td></tr></table></body></html>')
    result = markup_excerpts(text, "#/0/tk:content")
    assert result["formatting"][0]["content"] == '<u class="x">밑줄&amp;</u>'
    assert result["tables"][0]["content"] == (
        '<table><tr><td colspan="2">A</td></tr></table>')
    assert len(result["formatting"]) == 1


def test_markdown_offsets_preserve_crlf_and_vertical_tabs():
    text = "앞\v부분\r\n\r\n**강조**\r\n"
    excerpt = markup_excerpts(text, "root")["formatting"][0]
    assert excerpt["content"] == "**강조**\r\n"
    assert excerpt["source"] == f"root [{text.index('**')}:{len(text)})"


def test_tika_metadata_literal_keys_and_embedded_sources_are_preserved():
    raw = [{"tk:content": "본문", "xmpTPg:NPages": "2", "dotted.key": False},
           {"X-TIKA:content": "**강조**", "resourceName": "image.png",
            "tk:embedded-depth": 1}]
    result = tika_excerpts(raw)
    assert json.loads(result["metadata"][0]["content"]) == {
        "xmpTPg:NPages": "2", "dotted.key": False}
    assert result["formatting"][0]["source"].startswith("#/1/X-TIKA:content")
    assert result["formatting"][0]["content"] == "**강조**"
    assert json.loads(result["location"][0]["content"]) == {"xmpTPg:NPages": "2"}
    assert "개별 요소의 위치가 아닙니다" in result["location"][0]["note"]
    assert result["hierarchy"] == []


def test_native_formatting_prefers_emphasis_and_preserves_false_fields():
    result = docling_excerpts({"texts": [
        {"text": "보통", "formatting": {"bold": False}},
        {"text": "강조", "formatting": {"bold": True, "italic": False}}]})
    assert json.loads(result["formatting"][0]["content"]) == {
        "text": "강조", "formatting": {"bold": True, "italic": False}}
