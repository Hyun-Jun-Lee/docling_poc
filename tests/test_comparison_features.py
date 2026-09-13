import gzip
import json
import re
from html import unescape

from docling_poc.comparison_evidence import docling_excerpts
from docling_poc.comparison_features import (
    FEATURES,
    docling_features,
    feature_html,
    field_inventory,
    load_features,
    markup_features,
    tika_features,
)


def test_missing_empty_null_false_and_true_remain_distinct():
    values = [{}, {"bold": None}, {"bold": []}, {"bold": False}, {"bold": True}]
    row = field_inventory([(str(i), v) for i, v in enumerate(values)], ("bold",))[0]
    assert row["states"] == {"필드 없음": 1, "null": 1, "빈 배열": 1, "false": 1, "true": 1}


def test_native_fields_preserve_table_layout_and_heading_level_distribution():
    raw = {"document": {
        "texts": [{"label": "section_header", "text": "제목", "level": 1},
                  {"label": "section_header", "text": "다음 제목", "level": 1},
                  {"label": "text", "formatting": {"bold": False}, "prov": []}],
        "tables": [{"data": {"num_rows": 1, "num_cols": 2, "table_cells": [
            {"text": "병합 셀", "row_span": 1, "col_span": 2, "column_header": True}]}}],
        "groups": [], "origin": {"filename": "doc.docx"}}}
    result = docling_features(raw)
    assert set(result) == set(FEATURES)
    levels = next(r for r in result["headings"]["fields"] if r["field"] == "level")
    assert levels["value_counts"] == {"1": 2}
    cells = next(r for r in result["tables"]["fields"] if r["field"] == "col_span")
    assert cells["examples"][0]["value"] == 2
    assert cells["examples"][0]["source"] == "#/tables/0/data/table_cells/0"
    assert result["resources"]["fields"][0]["states"] == {"필드 없음": 1}


def test_tika_scopes_do_not_turn_image_headings_into_body_accuracy():
    result = tika_features([
        {"tk:content": "본문", "author": "작성자", "xmpTPg:NPages": "2"},
        {"tk:content": "# image3.jpeg\n\n**굵게**\n\n| A | B |\n|---|---|\n|1|2|",
         "resourceName": "image3.jpeg", "tk:embedded-depth": 1, "Content-Type": "image/jpeg"}])
    root, embedded = result["headings"]["scopes"]
    assert root["observed"]["제목 수"] == 0
    assert embedded["observed"]["예시"][0]["text"] == "image3.jpeg"
    assert "내장" in embedded["source"]
    table = result["tables"]["scopes"][1]["observed"]
    assert table["행·셀 예시"] == [{"rows": 2, "cells_per_row": [2, 2]}]
    assert result["location"]["mode"] == "현재 결과에 미제공"
    assert result["resources"]["resource_count"] == 1


def test_markdown_code_is_not_counted_as_heading_or_formatting():
    result = markup_features('```\n# 제목 아님\n**굵게 아님**\n```', 'content')
    assert result["headings"]["observed"]["제목 수"] == 0
    assert result["formatting"]["mode"] == "현재 결과에 미제공"


def test_html_formatting_and_cell_spans_are_observed_without_executing_html():
    result = markup_features('<html><body><h2>제목</h2><p><u>밑줄</u></p>'
                             '<table><tr><td colspan="2">A</td></tr></table>'
                             '<script><strong>가짜</strong></script></body></html>', 'root')
    assert result["formatting"]["observed"]["서식 표기 수"] == {"u": 1}
    assert result["tables"]["observed"]["행·셀 예시"][0]["attributes"] == {"colspan": "2"}


def test_first_success_precedes_partial_and_missing_raw_is_unknown(tmp_path):
    for number in (1, 3):
        directory = tmp_path / str(number)
        directory.mkdir()
        (directory / "content.md").write_text("# 대체 제목", encoding="utf-8")
    runs = [{"number": 1, "status": "partial_success", "path": "1"},
            {"number": 3, "status": "success", "path": "3"}]
    result = load_features(tmp_path, runs, "docling")
    assert result["run"] == 3
    assert "원본 JSON 확인 불가" in result["warning"]
    assert "location" not in result["features"]
    assert result["features"]["headings"]["mode"] == "마크업으로 제공"
    with gzip.open(tmp_path / "3/raw.json.gz", "wt", encoding="utf-8") as stream:
        json.dump({"texts": [{"label": "text", "text": "네이티브"}]}, stream)
    result = load_features(tmp_path, runs, "docling")
    assert result["warning"] == ""
    assert result["features"]["headings"]["mode"] == "현재 결과에 미제공"
    assert load_features(tmp_path, runs[:1], "docling")["status"] == "partial_success"
    assert load_features(tmp_path, [], "tika")["features"] == {}


def test_html_escapes_metadata_and_keeps_all_eight_categories():
    raw = {"origin": {"filename": '<img src=x onerror="bad()">'}}
    result = {"run": 1, "status": "success", "warning": "", "features": docling_features(raw),
              "excerpts": docling_excerpts(raw)}
    html = feature_html({"docling": result, "tika": result})
    assert '<img src=x' not in html
    assert '&lt;img' in html
    assert html.count('<th scope="row">') == 8
    assert '정확도 점수가 아닙니다' in html
    assert '활용과 해석상 한계' not in html
    assert '<th>기능</th><th>DOCLING</th><th>TIKA</th>' in html
    assert '<details>' not in html
    values = [json.loads(unescape(value)) for value in
              re.findall(r'<pre><code>(.*?)</code></pre>', html, re.DOTALL)]
    assert values == [raw, raw]


def test_generate_includes_feature_section_and_serialized_evidence(tmp_path):
    from docling_poc.benchmark_worker import write_json
    from docling_poc.comparison_report import generate

    directory = tmp_path / "run"
    directory.mkdir()
    with gzip.open(directory / "raw.json.gz", "wt", encoding="utf-8") as stream:
        json.dump({"texts": [{"label": "text", "formatting": {"bold": True}}]}, stream)
    write_json(tmp_path / "manifest.json", {
        "created": "test", "settings": {"repeat": 5}, "documents": [{
            "id": "d1", "name": "example.docx", "source": "missing.docx",
            "runs": {"tika": [], "docling": [
                {"number": 1, "status": "success", "path": "run"}]}}]})
    result = generate(tmp_path)
    assert result["documents"][0]["feature_comparison"]["docling"]["run"] == 1
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert '추출 정보 비교' in html
    assert '&quot;formatting&quot;' in html
    assert 'formatting.bold' not in html
