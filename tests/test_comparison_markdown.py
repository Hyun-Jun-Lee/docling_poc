import gzip
import json

from markdown_it import MarkdownIt

from docling_poc.comparison_markdown import fenced, markdown_table, result_markdown


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


def test_result_reads_legacy_json_and_prefers_pretty_without_modifying_inputs(tmp_path):
    legacy = tmp_path / 'raw.json.gz'
    with gzip.open(legacy, 'wt', encoding='utf-8') as stream:
        json.dump({'value': 'old', 'padding': 'x' * 90}, stream)
    before = legacy.read_bytes()
    assert 'old' in result_markdown(tmp_path)
    pretty = tmp_path / 'raw.pretty.json'
    raw = {'value': '최신', 'padding': '가' * 90}
    pretty.write_text(json.dumps(raw, ensure_ascii=False), encoding='utf-8')
    original = pretty.read_bytes()
    result = result_markdown(tmp_path)
    assert '최신' in result and 'old' not in result
    assert '저장된 Markdown 파일이 없습니다.' in result
    assert legacy.read_bytes() == before
    assert pretty.read_bytes() == original
    expected = json.dumps(raw, ensure_ascii=False, indent=2)
    tokens = MarkdownIt('commonmark').parse(result)
    blocks = [t for t in tokens if t.type == 'fence']
    assert len(blocks) == 1
    assert blocks[0].content == expected[:(len(expected) + 2) // 3] + '\n'
    assert '나머지' in result and '유효한 JSON이 아닐 수 있습니다' in result
    pretty.write_text('invalid', encoding='utf-8')
    assert '원본 JSON을 읽을 수 없습니다' in result_markdown(tmp_path)


def test_json_truncation_preserves_full_markdown_body(tmp_path):
    text = '전체 본문\n```\n끝까지 보존'
    (tmp_path / 'content.md').write_text(text, encoding='utf-8')
    (tmp_path / 'raw.pretty.json').write_text('{}', encoding='utf-8')
    result = result_markdown(tmp_path)
    blocks = [t for t in MarkdownIt('commonmark').parse(result) if t.type == 'fence']
    assert blocks[0].content == text + '\n'
    assert blocks[1].content == '{\n'
