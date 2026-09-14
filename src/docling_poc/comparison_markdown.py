"""Markdown presentation helpers for saved comparison results."""

from __future__ import annotations

import re

from docling_poc.comparison_features import FEATURES


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
