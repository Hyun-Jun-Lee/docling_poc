"""Generate a portable Korean HTML report from saved benchmark outputs; no inference."""

from __future__ import annotations

import argparse
import itertools
import json
import re
import statistics
import zipfile
from html import escape
from pathlib import Path
from xml.etree import ElementTree

from docling_poc.benchmark_worker import write_json
from docling_poc.comparison_data import edit_distance, stability
from docling_poc.comparison_review import REVIEW_CSS, review_html, review_script
from docling_poc.comparison_structure import load_structure

CSS = """
:root{color-scheme:light;font-family:'Segoe UI','Malgun Gothic',sans-serif;color:#1d2939;
background:#f2f5f9}body{max-width:1280px;margin:auto;padding:32px}h1{font-size:32px}
h2{border-bottom:2px solid #cbd5e1;padding-bottom:12px;margin-top:40px}h3{margin-top:28px}
p,li{line-height:1.7}a{color:#155db1}section,.card{background:white;padding:24px;
border:1px solid #dae1eb;border-radius:12px;margin:18px 0}table{border-collapse:collapse;
width:100%;margin:16px 0;font-size:14px}th,td{text-align:left;border:1px solid #d5dde7;
padding:10px;vertical-align:top}th{background:#edf2f8}pre{white-space:pre-wrap;
overflow-wrap:anywhere;background:#f7f9fc;padding:16px;font-size:12px;max-height:600px;
overflow:auto}summary{cursor:pointer;padding:10px;font-weight:600}.ok{background:#dcfce7}
.different{background:#fef3c7}.failure{background:#fee2e2}.muted{color:#64748b}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}.scroll{overflow-x:auto}
.grid article{min-width:0}.markdown{height:70vh;overflow:auto;padding:18px;
border:1px solid #d5dde7;border-radius:8px;overflow-wrap:anywhere;font-size:14px}
.markdown .markdown-source{margin:0;padding:0;background:transparent;max-height:none;
white-space:pre;overflow:visible;font-family:Consolas,monospace;font-size:13px}
small{font-size:11px;color:#64748b}
.view-toggle{padding:8px 14px;margin:0 0 10px;border:1px solid #94a3b8;
border-radius:6px;background:white;color:#1d2939;cursor:pointer;font:inherit}
.view-toggle[aria-pressed="true"]{background:#155db1;color:white}
.view-toggle:focus-visible{outline:3px solid #60a5fa;outline-offset:2px}
.markdown-rendered h1{font-size:24px}.markdown-rendered h2{font-size:21px}
.markdown-rendered h3{font-size:18px}.markdown-rendered table{display:block;overflow-x:auto}
[hidden]{display:none!important}
.diff_add{background:#dcfce7}.diff_sub{background:#fee2e2}.diff_chg{background:#fef3c7}
table.diff{font-family:monospace;font-size:12px}table.diff td{white-space:pre-wrap;
overflow-wrap:anywhere;max-width:560px}.badge{padding:4px 8px;border-radius:5px}
@media(max-width:800px){body{padding:12px}.grid{display:block}section{padding:14px}}
@media print{body{background:white;padding:0}details{break-inside:avoid}
pre{max-height:none}a{color:inherit}section{border:0;padding:0}}
@media print{.markdown{height:auto;overflow:visible}.grid{display:block}}
"""


def esc(value):
    return escape(str(value), quote=True)


def render_markdown(markdown: str) -> str:
    """Show literal Markdown syntax without interpreting document markup."""
    return '<pre class="markdown-source"><code>' + esc(markdown) + '</code></pre>'


def styled_markdown(markdown: str) -> str:
    """Render formatting while keeping document HTML and external images inactive."""
    from markdown_it import MarkdownIt

    renderer = MarkdownIt('commonmark', {'html': False}).enable('table')

    def image_placeholder(self, tokens, idx, options, env):
        return '<span>[이미지: ' + esc(tokens[idx].content) + ']</span>'

    def link_open(self, tokens, idx, options, env):
        return '<span>'

    def link_close(self, tokens, idx, options, env):
        return '</span>'

    renderer.add_render_rule('image', image_placeholder)
    renderer.add_render_rule('link_open', link_open)
    renderer.add_render_rule('link_close', link_close)
    return renderer.render(markdown)


TOGGLE_SCRIPT = """
<script>
document.querySelectorAll('.view-toggle').forEach(button => {
  button.addEventListener('click', () => {
    const panel = document.getElementById(button.getAttribute('aria-controls'));
    const styled = button.getAttribute('aria-pressed') !== 'true';
    panel.querySelector('.markdown-raw').hidden = styled;
    panel.querySelector('.markdown-rendered').hidden = !styled;
    button.setAttribute('aria-pressed', String(styled));
    button.textContent = styled ? '스타일 적용 중 · Markdown 원문 보기' : 'Markdown 원문 · 스타일 적용';
  });
});
</script>
"""


def table(headers, rows):
    return ('<div class="scroll"><table><thead><tr>'
            + ''.join(f'<th>{esc(h)}</th>' for h in headers) + '</tr></thead><tbody>'
            + ''.join('<tr>' + ''.join(f'<td>{cell}</td>' for cell in row) + '</tr>'
                      for row in rows) + '</tbody></table></div>')


def statistics_text(runs, field):
    values = [r[field] for r in runs if r.get('status') == 'success'
              and isinstance(r.get(field), (int, float))]
    if not values:
        return '완전 성공 측정 없음'
    return (f'중앙값 {statistics.median(values):.3f}s · '
            f'범위 {min(values):.3f}–{max(values):.3f}s · n={len(values)}')


def source_profile(path: Path):
    """Describe directly countable source features, not a ground-truth transcription."""
    if path.suffix.lower() == '.pdf':
        import pypdfium2

        with pypdfium2.PdfDocument(path) as pdf:
            counts = []
            for page in pdf:
                try:
                    textpage = page.get_textpage()
                    try:
                        counts.append(len(textpage.get_text_range().strip()))
                    finally:
                        textpage.close()
                finally:
                    page.close()
            return {'PDF 페이지': len(pdf), '텍스트 레이어가 비어 있지 않은 페이지':
                    sum(c > 0 for c in counts), '텍스트 레이어가 비어 있는 페이지':
                    sum(c == 0 for c in counts)}
    if path.suffix.lower() in {'.docx', '.pptx'}:
        with zipfile.ZipFile(path) as package:
            if path.suffix.lower() == '.docx':
                root = ElementTree.fromstring(package.read('word/document.xml'))
                ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
                return {'document.xml 문단 요소(표 내부 포함)': len(root.findall('.//w:p', ns)),
                        'document.xml 표 요소': len(root.findall('.//w:tbl', ns))}
            slides = [n for n in package.namelist()
                      if n.startswith('ppt/slides/slide') and n.endswith('.xml')
                      and '/' not in n.removeprefix('ppt/slides/')]
            return {'PPTX 슬라이드 XML 수': len(slides)}
    return {}


def generate(output: Path):
    output = Path(output).resolve()
    manifest = json.loads((output / 'manifest.json').read_text(encoding='utf-8'))
    repeat = manifest['settings']['repeat']
    parsers = manifest['settings'].get('tika_config', {}).get('parsers', [])
    tika_ocr = next((p['tesseract-ocr-parser'] for p in parsers
                     if 'tesseract-ocr-parser' in p), {})
    analysis = {'schema_version': 2, 'documents': []}
    summary_rows = []
    parts = ['<!doctype html><html lang="ko"><meta charset="utf-8">',
             '<meta name="viewport" content="width=device-width,initial-scale=1">',
             '<title>Tika · Docling 추출 비교</title>', f'<style>{CSS}{REVIEW_CSS}</style><body>',
             '<header><p class="muted">DOCUMENT EXTRACTION · REPRODUCIBLE BENCHMARK</p>',
             '<h1>Tika · Docling 추출 비교</h1>',
             (f'<p>{esc(manifest["created"])} · 문서 {len(manifest["documents"])}개 · '
             f'도구별 {repeat}회 · Tesseract {esc(tika_ocr.get("language", "설정 미기록"))}</p></header>'),
             '<!--SUMMARY-->',
             ('<section><h2>측정 기준</h2><p>같은 문서를 도구별로 새 프로세스에서 '
              f'{repeat}회 실행했습니다. 시간은 성공한 실행의 중앙값과 최소~최대입니다.</p>'
              '<p><b>전체</b>는 시작·초기화·변환·결과 저장·종료까지, <b>내부</b>는 '
              '각 도구가 기록한 파싱 구간입니다. 보고서 생성 시간은 제외합니다.</p>'
              '<p>반복 결과는 텍스트·구조의 동일 여부이며 정확도를 뜻하지 않습니다. '
              '아래에는 각 도구의 첫 성공 실행을 표시하며 버튼으로 Markdown 원문과 스타일을 전환합니다. '
              'Tika는 최상위 문서 내용, Docling은 네이티브 Markdown 출력입니다.</p></section>'),
             '<nav>' + ' · '.join(f'<a href="#{esc(d["id"])}">{esc(d["name"])}</a>'
                                   for d in manifest['documents']) + '</nav>']
    for doc in manifest['documents']:
        doc_result = {'id': doc['id'], 'name': doc['name'], 'tools': {}}
        extension = Path(doc['source']).suffix.lstrip('.').upper()
        parts += [f'<section id="{esc(doc["id"])}"><h2>{esc(extension)}</h2>',
                  f'<p>{esc(doc["name"])}</p>',
                  '<div class="grid">']
        try:
            profile = source_profile(output / doc['source'])
        except Exception as exc:  # noqa: BLE001 - source diagnostics must not hide extraction results
            profile = {'원본 특성 확인 오류': str(exc)}
        doc_result['source_profile'] = profile
        snapshots = {}
        structures = {}
        for tool in ('tika', 'docling'):
            runs = sorted(doc['runs'][tool], key=lambda r: r['number'])
            structures[tool] = [load_structure(output, doc, tool, run) for run in runs
                                if run['status'] in {'success', 'partial_success'}]
            valid, snaps = [], []
            for run in runs:
                path = output / run['path'] / 'snapshot.json'
                if run['status'] in {'success', 'partial_success'} and path.is_file():
                    valid.append(run)
                    snaps.append(json.loads(path.read_text(encoding='utf-8')))
            snapshots[tool] = (valid, snaps)
            result = stability(snaps)
            for p in result['pairs']:
                p['left'] = valid[p['left'] - 1]['number']
                p['right'] = valid[p['right'] - 1]['number']
            doc_result['tools'][tool] = result
            success = sum(r['status'] == 'success' for r in runs)
            partial = sum(r['status'] == 'partial_success' for r in runs)
            failed = sum(r['status'] == 'failure' for r in runs)
            if len(valid) < 2:
                repeat_label = f'비교 불가 (유효 결과 {len(valid)}회)'
            elif result['unique_content'] == 1:
                repeat_label = (f'{repeat}회 모두 동일' if len(valid) == repeat
                                else f'유효 결과 {len(valid)}회 동일 (예정 {repeat}회)')
            else:
                repeat_label = f'{len(valid)}회 결과 중 차이 있음 ({result["unique_content"]}종류)'
            if partial:
                repeat_label += ' · 부분 성공 포함'
            pair_count = len(result['pairs'])
            verification = (f'전체 {pair_count}개 비교쌍에서 텍스트·구조 일치'
                            if pair_count and result['equal_pairs'] == pair_count
                            else f'{pair_count}개 비교쌍 중 {result["equal_pairs"]}쌍에서 텍스트·구조 일치')
            if any(s.get('schema_version', 1) < 2 for s in snaps) and tool == 'docling':
                verification += ' (과거 스냅샷: 제목 수준·목록 속성 검증 범위 제한)'
            summary_rows.append([
                esc(doc['name']), tool.upper(), f'{success}/{repeat}',
                statistics_text(runs, 'total_seconds'),
                statistics_text(runs, 'internal_seconds'),
                esc(repeat_label) + '<br><small>' + esc(verification) + '</small>',
                str(result['unique_content'])])
            parts.append(f'<article><h3>{tool.upper()}</h3>')
            parts.append(f'<p class="muted">성공 {success} · 부분 성공 {partial} · '
                         f'실패 {failed} · 미실행 {repeat-len(runs)}</p>')
            for run in runs:
                if run.get('error') or run.get('errors'):
                    parts.append(f'<p class="failure">{run["number"]}회: '
                                 f'{esc(run.get("error", run.get("errors")))}</p>')
            selected = next((r for r in valid if r['status'] == 'success'),
                            valid[0] if valid else None)
            if selected:
                path = output / selected['path'] / 'content.md'
                parts.append(f'<p class="muted">{selected["number"]}회차 · '
                             f'{esc(selected["status"])}</p>')
                if path.is_file():
                    markdown = path.read_text(encoding='utf-8')
                    panel_id = f'markdown-{doc["id"]}-{tool}'
                    parts.append(
                        f'<button type="button" class="view-toggle" aria-pressed="false" '
                        f'aria-controls="{esc(panel_id)}">Markdown 원문 · 스타일 적용</button>'
                        f'<div class="markdown" id="{esc(panel_id)}">'
                        '<div class="markdown-raw">' + render_markdown(markdown) + '</div>'
                        '<div class="markdown-rendered" hidden>' + styled_markdown(markdown)
                        + '</div></div>')
                else:
                    parts.append('<p>저장된 Markdown 파일이 없습니다.</p>')
            else:
                parts.append('<p>표시할 추출 결과가 없습니다.</p>')
            parts.append('</article>')
        parts.append('</div>')
        doc_result['structure_review'] = structures
        parts.append(review_html(doc, structures))
        cross = []
        distances = {}
        for (ra, a), (rb, b) in itertools.product(zip(*snapshots['tika']),
                                                  zip(*snapshots['docling'])):
            key = (a['text'], b['text'])
            if key not in distances:
                distances[key] = edit_distance(*key)
            distance = distances[key]
            cross.append({'tika_run': ra['number'], 'docling_run': rb['number'],
                          'edit_distance': distance,
                          'text_difference_pct': distance / max(len(a['text']), len(b['text']), 1)*100})
        doc_result['cross_tool_text'] = cross
        parts.append('</section>')
        analysis['documents'].append(doc_result)
    parts.append(TOGGLE_SCRIPT.replace('</script>', review_script() + '\n</script>')
                 + '</body></html>')
    write_json(output / 'analysis.json', analysis)
    summary = '<section><h2>측정 결과</h2>' + table(
        ['문서', '도구', '완전 성공', '전체 소요시간', '내부 파싱 시간', '동일 도구의 반복 일관성', '고유 결과 수'],
        summary_rows) + '</section>'
    (output / 'index.html').write_text('\n'.join(parts).replace('<!--SUMMARY-->', summary),
                                     encoding='utf-8')
    return analysis


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--standalone', type=Path,
                        help='Also save a single HTML with external file links removed')
    args = parser.parse_args()
    generate(args.output)
    if args.standalone:
        source = (args.output / 'index.html').resolve()
        if args.standalone.resolve() == source:
            parser.error('--standalone must differ from the standard index.html')
        html = source.read_text(encoding='utf-8')
        # Only links emitted by this generator; document contents have already been escaped.
        html = re.sub(r'<a href="(?!#)[^"]*">(.*?)</a>', r'\1', html, flags=re.DOTALL)
        html = html.replace('<body>', '<body><p class="muted">단일 HTML 공유본</p>', 1)
        args.standalone.parent.mkdir(parents=True, exist_ok=True)
        args.standalone.write_text(html, encoding='utf-8')


if __name__ == '__main__':
    main()
