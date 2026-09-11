import json
import random

from docling_poc.comparison_data import compare_pair, docling_snapshot, edit_distance, stability


def snapshot(text):
    return {"text": text, "blocks": [{"kind": "text", "text": text}],
            "geometry": [], "scores": {}}


def test_distance_and_all_ten_pairs():
    assert edit_distance("kitten", "sitting") == 3
    assert edit_distance("한글", "한굴") == 1
    assert edit_distance("", "") == 0
    summary = stability([snapshot("같음")] * 5)
    assert len(summary["pairs"]) == 10
    assert summary["unique_content"] == 1
    assert summary["equal_pairs"] == 10
    assert compare_pair(snapshot(""), snapshot(""))["text_difference_pct"] == 0


def test_snapshot_preserves_reading_order_and_separates_coordinates():
    doc = {"body": {"children": [{"$ref": "#/texts/1"}, {"$ref": "#/texts/0"}]},
           "texts": [{"label": "text", "text": "A"},
                     {"label": "text", "text": "B", "prov": [
                         {"page_no": 1, "bbox": {"l": 2, "t": 4}}]}]}
    a = docling_snapshot({"document": doc})
    doc["texts"][1]["prov"][0]["bbox"]["l"] = 2.001
    b = docling_snapshot({"document": doc})
    assert a["text"] == "B\nA"
    delta = compare_pair(a, b)
    assert delta["content_equal"] is True
    assert delta["geometry"]["changed_values"] == 1
    assert abs(delta["geometry"]["max_abs_delta"] - 0.001) < 1e-8


def test_normalization_does_not_hide_spaces_or_order():
    assert compare_pair(snapshot("a b"), snapshot("ab"))["content_equal"] is False
    assert compare_pair(snapshot("a\r\nb"), snapshot("a\nb"))["content_equal"] is True
    assert compare_pair(snapshot("가"), snapshot("가"))["content_equal"] is True


def test_table_cell_geometry_is_not_structural_difference():
    doc = {"body": {"children": [{"$ref": "#/tables/0"}]}, "tables": [
        {"label": "table", "data": {"num_rows": 1, "num_cols": 1,
         "table_cells": [{"text": "x", "bbox": {"l": 1}, "row_span": 1}]}}]}
    a = docling_snapshot({"document": doc})
    other = json.loads(json.dumps(doc))
    other["tables"][0]["data"]["table_cells"][0]["bbox"]["l"] = 2
    b = docling_snapshot({"document": other})
    assert compare_pair(a, b)["content_equal"] is True
    other["tables"][0]["data"]["table_cells"][0]["row_span"] = 2
    assert compare_pair(a, docling_snapshot({"document": other}))["content_equal"] is False


def test_bitvector_distance_matches_dynamic_programming():
    rng = random.Random(42)
    for _ in range(100):
        a = ''.join(rng.choices('abc한글', k=rng.randrange(20)))
        b = ''.join(rng.choices('abc한글', k=rng.randrange(20)))
        row = list(range(len(b) + 1))
        for i, ca in enumerate(a, 1):
            nxt = [i]
            for j, cb in enumerate(b, 1):
                nxt.append(min(nxt[-1] + 1, row[j] + 1, row[j-1] + (ca != cb)))
            row = nxt
        assert edit_distance(a, b) == row[-1]


def test_report_preserves_run_numbers_and_escapes_document_content(tmp_path):
    from docling_poc.benchmark_worker import write_json
    from docling_poc.comparison_report import generate

    runs = []
    for n in (2, 4):
        directory = tmp_path / f'docling-{n}'
        directory.mkdir()
        write_json(directory / 'snapshot.json', {
            **snapshot('<script>alert(1)</script>'), 'counts': {'text': 1}})
        (directory / 'content.md').write_text('<script>alert(1)</script>', encoding='utf-8')
        runs.append({'number': n, 'status': 'partial_success' if n == 4 else 'success',
                     'path': directory.name, 'total_seconds': 1})
    runs.insert(0, {'number': 1, 'status': 'failure', 'path': 'failed'})
    write_json(tmp_path / 'manifest.json', {
        'created': 'test', 'settings': {'repeat': 5}, 'documents': [{
            'id': 'd1', 'name': '<img src=x onerror=alert(1)>', 'source': 'input.pdf',
            'bytes': 1, 'sha256': 'abc', 'runs': {'docling': runs, 'tika': []}}]})
    result = generate(tmp_path)
    pairs = result['documents'][0]['tools']['docling']['pairs']
    assert len(pairs) == 1
    assert (pairs[0]['left'], pairs[0]['right']) == (2, 4)
    html = (tmp_path / 'index.html').read_text(encoding='utf-8')
    assert '<script>alert(1)</script>' not in html and '<img src=x' not in html
    assert html.count('<script>') == 1  # Only the report's fixed toggle controller.
    assert '&lt;script&gt;' in html
    assert '미실행 2' in html
    assert 'n=1' in html
    assert '유효 결과 2회 동일 (예정 5회) · 부분 성공 포함' in html
    assert '5회 모두 동일' not in html
    assert '전체 1개 비교쌍에서 텍스트·구조 일치' in html
    assert 'class="markdown" id="markdown-d1-docling"' in html
    assert 'aria-controls="markdown-d1-docling"' in html
    assert 'aria-pressed="false"' in html
    assert '<div class="markdown-rendered" hidden>' in html
    assert '항목 수와 추출 전문' not in html
    assert '실행 환경과 재현 정보' not in html


def test_markdown_preview_preserves_literal_syntax_without_active_content():
    from docling_poc.comparison_report import render_markdown

    markdown = ('# 제목\n\n**굵게**\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n'
                           '<script>alert(1)</script>\n\n'
                           '![image](https://example.com/image.png) '
                           '[link](https://example.com)')
    html = render_markdown(markdown)
    from html import unescape

    assert unescape(html.split('<code>', 1)[1].split('</code>', 1)[0]) == markdown
    assert '# 제목' in html and '**굵게**' in html and '|---|---|' in html
    assert '<h1>' not in html and '<table>' not in html
    assert '<script>' not in html and '<img' not in html and 'href=' not in html


def test_styled_markdown_keeps_document_code_and_images_inactive():
    from docling_poc.comparison_report import styled_markdown

    html = styled_markdown('# 제목\n\n**굵게**\n\n<script>alert(1)</script>\n\n'
                           '![image](https://example.com/image.png)')
    assert '<h1>제목</h1>' in html and '<strong>굵게</strong>' in html
    assert '<script>' not in html and '<img' not in html


def test_ocr_config_rejects_language_drift(monkeypatch):
    from pathlib import Path
    from types import SimpleNamespace

    import pytest

    from docling_poc import docling_raw
    from docling_poc.comparison import validate_ocr_config

    options = SimpleNamespace(tesseract_cmd=str(Path('ocr/tesseract.exe')),
                              path=str(Path('ocr/tessdata')), lang=['kor', 'eng'], psm=3)
    monkeypatch.setattr(docling_raw, 'build_tesseract_ocr_options', lambda: options)
    config = {'parsers': [{'tesseract-ocr-parser': {
        'tesseractPath': 'ocr', 'tessdataPath': 'ocr/tessdata',
        'language': 'kor+eng', 'pageSegMode': '3', 'skipOcr': False}}]}
    assert validate_ocr_config(config) == (Path(options.tesseract_cmd), Path(options.path))
    config['parsers'][0]['tesseract-ocr-parser']['language'] = 'eng'
    with pytest.raises(ValueError, match='must match'):
        validate_ocr_config(config)


def test_tika_internal_time_uses_root_without_summing_children(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from docling_poc import benchmark_worker

    raw = [{'tk:content': 'root', 'tk:parse-time-millis': '1234'},
           {'tk:content': 'embedded', 'tk:parse-time-millis': '900',
            'tk:exception:embedded-exception': 'decode failed'}]

    def fake_run(command, *, stdout, **kwargs):
        stdout.write(json.dumps(raw).encode('utf-8'))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(benchmark_worker.subprocess, 'run', fake_run)
    args = SimpleNamespace(java='java', jar='tika.jar', config='config.json',
                           source=tmp_path / 'input.pdf', output=tmp_path)
    saved, text, result = benchmark_worker.run_tika(args)
    assert saved == raw and text == 'root'
    assert result['internal_seconds'] == 1.234
    assert result['status'] == 'partial_success'
    assert result['errors'][0]['item'] == 1


def test_timeout_records_failure_and_terminates_worker(tmp_path):
    import os
    import sys

    from docling_poc.comparison import execute

    result = execute([sys.executable, '-c', 'import time; time.sleep(30)'],
                     tmp_path, 0.2, os.environ.copy())
    assert result['status'] == 'failure'
    assert result['timeout'] is True
    assert result['exit_code'] != 0
    assert result['total_seconds'] >= 0.2
    assert json.loads((tmp_path / 'run.json').read_text(encoding='utf-8')) == result
