import gzip
import json
from html import unescape

import pytest

from docling_poc.comparison_report import result_views


@pytest.mark.parametrize('legacy', [False, True])
@pytest.mark.parametrize('raw', [{'document': {'text': '</code><script>한글</script>'}},
                                 [{'tk:content': '표\n| A | B |'}]])
def test_json_view_preserves_full_raw_and_escapes_html(tmp_path, legacy, raw):
    content = json.dumps(raw, ensure_ascii=False)
    if legacy:
        (tmp_path / 'raw.json.gz').write_bytes(gzip.compress(content.encode('utf-8')))
    else:
        (tmp_path / 'raw.pretty.json').write_text(content, encoding='utf-8')
    html = result_views(tmp_path, 'test-panel')
    assert html.count('class="view-toggle"') == 3
    assert html.count('aria-pressed="true"') == 1
    assert '<script>' not in html
    code = html.split('<code>', 1)[1].split('</code>', 1)[0]
    assert json.loads(unescape(code)) == raw
    assert '저장된 Markdown 파일이 없습니다.' in html


@pytest.mark.parametrize('payload', [None, b'{invalid', b'\xff'])
def test_json_error_does_not_hide_markdown(tmp_path, payload):
    (tmp_path / 'content.md').write_text('# 제목', encoding='utf-8')
    if payload is not None:
        (tmp_path / 'raw.pretty.json').write_bytes(payload)
    html = result_views(tmp_path, 'test-panel')
    assert '<h1>제목</h1>' in html
    assert '원본 JSON을 읽을 수 없습니다' in html
