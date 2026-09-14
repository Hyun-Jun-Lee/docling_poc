import gzip
import json

import pytest

from docling_poc.comparison_features import load_features
from docling_poc.comparison_raw import raw_result_path, read_raw_text
from docling_poc.comparison_structure import load_structure


@pytest.mark.parametrize('tool', ['docling', 'tika'])
@pytest.mark.parametrize('legacy', [False, True])
def test_report_reads_plain_and_legacy_raw(tmp_path, tool, legacy):
    raw = {'body': {'children': [{'$ref': '#/texts/0'}]},
           'texts': [{'label': 'section_header', 'level': 1, 'text': '지원 대상'}]}
    if tool == 'tika':
        raw = [{'tk:content': '# 지원 대상'}]
    content = json.dumps(raw, ensure_ascii=False, indent=2)
    name = 'raw.json.gz' if legacy else 'raw.pretty.json'
    path = tmp_path / name
    if legacy:
        path.write_bytes(gzip.compress(content.encode('utf-8')))
    else:
        path.write_text(content, encoding='utf-8')
        # A stale compressed file must not override the current output.
        (tmp_path / 'raw.json.gz').write_bytes(b'not gzip')
    assert raw_result_path(tmp_path) == path
    assert read_raw_text(path) == content
    run = {'path': '.', 'number': 1, 'status': 'success'}
    features = load_features(tmp_path, [run], tool)
    assert features['warning'] == ''
    assert features['source_file'].endswith(name)
    structure = load_structure(tmp_path, {'id': 'd1'}, tool, run)
    assert structure['warnings'] == []
    assert structure['blocks'][0]['text'] == '지원 대상'


def test_invalid_plain_raw_does_not_fall_back_to_stale_gzip(tmp_path):
    (tmp_path / 'raw.pretty.json').write_text('{bad', encoding='utf-8')
    (tmp_path / 'raw.json.gz').write_bytes(gzip.compress(b'{}'))
    run = {'path': '.', 'number': 1, 'status': 'success'}
    assert load_features(tmp_path, [run], 'docling')['warning']
    assert load_structure(tmp_path, {'id': 'd1'}, 'docling', run)['warnings']
