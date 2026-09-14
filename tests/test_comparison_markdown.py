from markdown_it import MarkdownIt

from docling_poc.comparison_markdown import fenced, markdown_table


def test_fence_preserves_nested_code_and_inactive_html():
    source = '```python\nprint(1)\n```\n````\n<script>alert(1)</script>\n![x](https://x)'
    tokens = MarkdownIt('commonmark').parse(fenced(source, 'markdown'))
    assert len(tokens) == 1
    assert tokens[0].type == 'fence'
    assert tokens[0].content == source + '\n'


def test_metadata_cannot_break_table_or_inject_html():
    source = '<img src=x>|[link](https://x)\n# title'
    text = markdown_table(['文書'], [[source]])
    html = MarkdownIt('commonmark').enable('table').render(text)
    assert html.count('<td>') == 1
    assert '<img' not in html and '<a ' not in html
    assert '&lt;img' in html


def test_report_omits_full_sources_but_keeps_features_and_html(tmp_path, monkeypatch):
    from docling_poc import comparison_report
    from docling_poc.benchmark_worker import write_json
    from docling_poc.comparison_data import docling_snapshot

    directory = tmp_path / 'run'
    directory.mkdir()
    raw = {'texts': [{'label': 'text', 'text': '기능 발췌 유지'}],
           'unused_payload': 'LARGE_JSON_PAYLOAD' * 10000}
    write_json(directory / 'raw.pretty.json', raw)
    write_json(directory / 'snapshot.json', docling_snapshot(raw))
    (directory / 'content.md').write_text('FULL_MARKDOWN_BODY' * 10000, encoding='utf-8')
    original = {p.name: p.read_bytes() for p in directory.iterdir()}
    write_json(tmp_path / 'manifest.json', {
        'created': 'test', 'settings': {'repeat': 1}, 'documents': [{
            'id': 'd1', 'name': 'test.docx', 'source': 'input.docx',
            'runs': {'tika': [], 'docling': [
                {'number': 1, 'status': 'success', 'path': 'run', 'total_seconds': 1}]}}]})
    monkeypatch.setattr(comparison_report, 'source_profile', lambda _: {})
    comparison_report.generate(tmp_path)
    markdown = (tmp_path / 'report.md').read_text(encoding='utf-8')
    html = (tmp_path / 'index.html').read_text(encoding='utf-8')
    for marker in ('LARGE_JSON_PAYLOAD', 'FULL_MARKDOWN_BODY'):
        assert marker not in markdown
        assert marker in html
    assert '기능 발췌 유지' in markdown
    assert '## 측정 결과' in markdown and '## 대용량 처리 운영 확장성' in markdown
    assert {p.name: p.read_bytes() for p in directory.iterdir()} == original
