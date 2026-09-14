"""Markdown presentation helpers for saved comparison results."""

from __future__ import annotations

import json
import re
from pathlib import Path

from docling_poc.comparison_features import FEATURES
from docling_poc.comparison_raw import raw_result_path, read_raw_text


def literal(value: object) -> str:
    """Keep metadata from introducing Markdown, HTML, or table delimiters."""
    return ''.join(f'&#{ord(c)};' if c in '&<>\\`*_{}[]()#+-.!|~' else
                   ' ' if c in '\r\n' else c for c in str(value))


def fenced(text: str, language: str = '') -> str:
    size = max((len(m.group()) for m in re.finditer(r'`+', text)), default=0)
    fence = '`' * max(3, size + 1)
    return f'{fence}{language}\n{text}\n{fence}'


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    return '\n'.join([
        '| ' + ' | '.join(literal(h) for h in headers) + ' |',
        '| ' + ' | '.join('---' for _ in headers) + ' |',
        *('| ' + ' | '.join(literal(c) for c in row) + ' |' for row in rows),
    ])


def result_markdown(directory: Path) -> str:
    parts = ['#### Markdown 원문']
    path = directory / 'content.md'
    parts.append(fenced(path.read_text(encoding='utf-8'), 'markdown') if path.is_file()
                 else '저장된 Markdown 파일이 없습니다.')
    parts.append('#### JSON 원본 발췌')
    try:
        raw = json.loads(read_raw_text(raw_result_path(directory)))
        pretty = json.dumps(raw, ensure_ascii=False, indent=2)
        shown = (len(pretty) + 2) // 3
        parts.append(
            f'원본 JSON 앞부분 약 1/3만 표시합니다 '
            f'({shown:,}/{len(pretty):,}자, 나머지 {len(pretty) - shown:,}자 생략). '
            '중간에서 잘린 발췌이므로 유효한 JSON이 아닐 수 있습니다. '
            '전체 내용은 해당 회차의 원본 JSON 파일에서 확인하세요.')
        parts.append(fenced(pretty[:shown], 'text'))
    except (OSError, EOFError, ValueError) as exc:
        parts.append(literal(f'원본 JSON을 읽을 수 없습니다: {exc}'))
    return '\n\n'.join(parts)


def features_markdown(comparison: dict) -> str:
    parts = ['### 추출 정보 비교']
    for key, title in FEATURES.items():
        parts.append(f'#### {title}')
        for tool in ('docling', 'tika'):
            parts.append(f'##### {tool.upper()}')
            result = comparison[tool]
            excerpts = result.get('excerpts', {}).get(key, [])
            if not excerpts:
                parts.append('확인 불가 · 원본 JSON 또는 유효 실행 필요' if not result['features']
                             else '관련 원본 발췌 없음 · 도구 전체의 미지원 판정은 아닙니다.')
            for excerpt in excerpts:
                parts.append(literal(f'{result.get("source_file", "")} · {excerpt["source"]}'))
                if excerpt['note']:
                    parts.append(literal(excerpt['note']))
                language = excerpt['format'] if excerpt['format'] in {
                    'json', 'html', 'markdown'} else ''
                parts.append(fenced(excerpt['content'], language))
    return '\n\n'.join(parts)
