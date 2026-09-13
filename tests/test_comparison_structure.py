import gzip
import json
from copy import deepcopy

import pytest

from docling_poc.comparison_data import compare_pair, docling_snapshot, tika_snapshot
from docling_poc.comparison_structure import (
    docling_blocks,
    load_structure,
    markup_blocks,
    tika_blocks,
)


def document():
    return {'body': {'children': [{'$ref': '#/texts/0'}, {'$ref': '#/texts/1'},
                                  {'$ref': '#/texts/2'}, {'$ref': '#/texts/3'}]},
            'texts': [{'label': 'section_header', 'text': '지원 대상', 'level': 1},
                      {'label': 'section_header', 'text': '신청 자격', 'level': 3},
                      {'label': 'text', 'text': '본문'},
                      {'label': 'page_header', 'text': '기관명'}]}


def test_heading_levels_and_list_markers_affect_stability():
    raw = document()
    first = docling_snapshot(raw)
    raw['texts'][0]['level'] = 2
    assert not compare_pair(first, docling_snapshot(raw))['content_equal']
    raw['texts'][0] = {'label': 'list_item', 'text': '목록', 'marker': '1.', 'enumerated': True}
    first = docling_snapshot(raw)
    raw['texts'][0].update(marker='•', enumerated=False)
    assert not compare_pair(first, docling_snapshot(raw))['content_equal']


def test_structure_level_gaps_furniture_and_sources():
    blocks = docling_blocks(document())
    assert blocks[1]['level'] == 3
    assert blocks[1]['parent_heading'] == '#/texts/0'
    assert blocks[2]['path'] == [{'id': '#/texts/0', 'text': '지원 대상'},
                                {'id': '#/texts/1', 'text': '신청 자격'}]
    assert blocks[2]['relation'] == 'level_order'
    assert blocks[3]['kind'] == 'page_header'
    assert blocks[3]['path'] == []
    assert blocks[0]['source_ref'] == '#/texts/0'


def test_unlevelled_heading_does_not_invent_hierarchy():
    raw = document()
    del raw['texts'][1]['level']
    blocks = docling_blocks(raw)
    assert blocks[1]['level'] is None
    assert blocks[1]['relation'] == 'unresolved'
    assert blocks[2]['path'] == []


def test_explicit_ancestors_and_duplicate_references():
    raw = document()
    raw['body']['children'] = [{'$ref': '#/texts/0'}]
    raw['texts'][0]['children'] = [{'$ref': '#/texts/1'}]
    raw['texts'][1]['children'] = [{'$ref': '#/texts/2'}]
    del raw['texts'][0]['level']
    del raw['texts'][1]['level']
    blocks = docling_blocks(raw)
    assert blocks[2]['relation'] == 'explicit'
    assert len(blocks[2]['path']) == 2
    raw['body']['children'].append({'$ref': '#/texts/2'})
    assert len(docling_blocks(raw)) == len(blocks)


@pytest.mark.parametrize('ref', ['#/texts/-1', '#/texts/99', 'texts/0'])
def test_invalid_references_are_errors(ref):
    raw = document()
    raw['body']['children'] = [{'$ref': ref}]
    with pytest.raises(ValueError):
        docling_blocks(raw)


def test_cycles_are_errors():
    raw = document()
    raw['texts'][0]['children'] = [{'$ref': '#/texts/0'}]
    with pytest.raises(ValueError, match='Cyclic'):
        docling_blocks(raw)


def test_caption_references_do_not_reorder_body():
    raw = {'body': {'children': [{'$ref': '#/pictures/0'}, {'$ref': '#/texts/0'},
                                 {'$ref': '#/texts/1'}]},
           'pictures': [{'label': 'picture', 'captions': [{'$ref': '#/texts/1'}]}],
           'texts': [{'label': 'text', 'text': '본문 먼저'},
                     {'label': 'caption', 'text': '캡션 나중'}]}
    assert [b['text'] for b in docling_blocks(raw)] == ['', '본문 먼저', '캡션 나중']


def test_markdown_explicit_headings_not_bold_or_number_guesses():
    blocks = markup_blocks('# 지원 대상\n\n### 신청 자격\n\n**굵은 문장**\n\n'
                           '```\n# 코드 제목 아님\n```\n\n- 항목\n')
    assert [b['level'] for b in blocks if b['kind'] == 'heading'] == [1, 3]
    assert blocks[2]['kind'] == 'unknown'
    assert any(b['kind'] == 'list' for b in blocks)
    assert blocks[1]['relation'] == 'level_order'
    html_code = markup_blocks('```html\n<h1>코드 제목 아님</h1>\n```')
    assert not any(b['kind'] == 'heading' for b in html_code)


def test_html_and_embedded_resources_do_not_share_section_paths():
    raw = [{'tk:content': '<html><body><h1>제목</h1><p>내용</p>'
                         '<table><tr><td>A</td><td>B</td></tr></table>'
                         '<script>danger()</script></body></html>'},
           {'tk:content': '내장 내용', 'resourceName': 'embedded.docx'}]
    blocks = tika_blocks(raw)
    assert blocks[0]['kind'] == 'heading'
    assert blocks[0]['evidence'] == 'html'
    assert blocks[1]['kind'] == 'paragraph'
    assert blocks[2]['kind'] == 'table'
    assert all('danger' not in b['text'] for b in blocks)
    assert blocks[-1]['path'] == []
    assert blocks[-1]['resource'] == 'embedded.docx'


def test_raw_priority_fallback_and_fingerprint(tmp_path):
    directory = tmp_path / 'run'
    directory.mkdir()
    doc = {'id': 'd1', 'sha256': 'hash'}
    run = {'path': 'run', 'number': 2, 'status': 'partial_success'}
    (directory / 'content.md').write_text('# 출력 제목', encoding='utf-8')
    fallback = load_structure(tmp_path, doc, 'docling', run)
    assert fallback['warnings']
    assert fallback['blocks'][0]['evidence'] == 'markdown'
    raw = document()
    with gzip.open(directory / 'raw.json.gz', 'wt', encoding='utf-8') as stream:
        json.dump(raw, stream)
    result = load_structure(tmp_path, doc, 'docling', run)
    assert not result['warnings']
    assert result['blocks'][0]['text'] == '지원 대상'
    assert result['fingerprint'] != fallback['fingerprint']
    assert result['status'] == 'partial_success'


def test_review_payload_escapes_document_content():
    from docling_poc.comparison_review import review_html

    raw = deepcopy(document())
    raw['texts'][0]['text'] = '</textarea><script>evil()</script>'
    html = review_html({'id': 'x', 'name': '</textarea>'},
                       {'docling': [{'blocks': docling_blocks(raw)}], 'tika': []})
    assert '<script>evil()' not in html
    assert '&lt;/textarea&gt;' in html
    assert '검토 JSON 내보내기' in html


@pytest.mark.parametrize('tool', ['docling', 'tika'])
@pytest.mark.parametrize('has_markdown', [True, False])
def test_report_isolates_truncated_gzip_and_continues_other_documents(tmp_path, tool, has_markdown):
    from docling_poc.benchmark_worker import write_json
    from docling_poc.comparison_report import generate

    raw = document() if tool == 'docling' else [{'tk:content': '# 정상 제목'}]
    snapshot = docling_snapshot(raw) if tool == 'docling' else tika_snapshot(raw)
    compressed = gzip.compress(json.dumps(raw, ensure_ascii=False).encode('utf-8'))
    truncated = compressed[:-8]  # Missing gzip trailer raises EOFError during reading.
    documents = []
    for identifier, payload in [('broken', truncated), ('healthy', compressed)]:
        directory = tmp_path / identifier
        directory.mkdir()
        (directory / 'raw.json.gz').write_bytes(payload)
        write_json(directory / 'snapshot.json', snapshot)
        if has_markdown:
            (directory / 'content.md').write_text('# 대체 제목', encoding='utf-8')
        runs = {'docling': [], 'tika': []}
        runs[tool] = [{'number': 1, 'status': 'success', 'path': identifier}]
        documents.append({'id': identifier, 'name': f'{identifier}.docx',
                          'source': f'{identifier}/input.docx', 'runs': runs})
    write_json(tmp_path / 'manifest.json', {
        'created': 'test', 'settings': {'repeat': 1}, 'documents': documents})

    analysis = generate(tmp_path)

    broken, healthy = analysis['documents']
    fallback = broken['structure_review'][tool][0]
    assert fallback['warnings'][0].startswith('원본 구조 분석 실패:')
    assert fallback['status'] == 'success'  # Preserve the recorded extraction status.
    assert broken['feature_comparison'][tool]['warning'].startswith('원본 JSON 확인 불가:')
    if has_markdown:
        assert fallback['blocks'][0]['text'] == '대체 제목'
        assert fallback['blocks'][0]['evidence'] == 'markdown'
        assert fallback['fingerprint']
    else:
        assert fallback['blocks'] == []
    assert healthy['structure_review'][tool][0]['warnings'] == []
    assert healthy['structure_review'][tool][0]['blocks']
    assert healthy['feature_comparison'][tool]['warning'] == ''
    html = (tmp_path / 'index.html').read_text(encoding='utf-8')
    assert '원본 구조 분석 실패:' in html and 'healthy.docx' in html
    assert (tmp_path / 'analysis.json').is_file()
    assert (tmp_path / 'broken/raw.json.gz').read_bytes() == truncated
