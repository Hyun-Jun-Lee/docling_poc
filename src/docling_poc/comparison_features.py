"""Evidence-based feature inventory from saved outputs, without inference or scoring."""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Mapping
from html import escape
from html.parser import HTMLParser
from pathlib import Path

from docling_poc.comparison_evidence import docling_excerpts, markup_excerpts, tika_excerpts
from docling_poc.comparison_raw import raw_result_path, read_raw_text

FEATURES = {
    "classification": "요소 분류",
    "headings": "제목 수준",
    "hierarchy": "그룹·계층",
    "formatting": "서식",
    "tables": "표 구조",
    "location": "원본 위치",
    "metadata": "문서 메타데이터",
    "resources": "내장 리소스",
}
MISSING = object()


def preview(value: object) -> object:
    """Bound examples, especially images and large table/metadata values."""
    if isinstance(value, str):
        if value.startswith("data:"):
            return "[data URI 생략]"
        return value if len(value) <= 180 else value[:180] + "…"
    if isinstance(value, list):
        return [preview(v) for v in value[:3]] + (["…"] if len(value) > 3 else [])
    if isinstance(value, Mapping):
        return {k: preview(v) for k, v in list(value.items())[:12]}
    return value


def field_inventory(items: list[tuple[str, Mapping]], fields: tuple[str, ...]) -> list[dict]:
    result = []
    for field in fields:
        states: Counter = Counter()
        examples = []
        values: Counter = Counter()
        for ref, item in items:
            value = item
            for key in field.split("."):
                value = value.get(key, MISSING) if isinstance(value, Mapping) else MISSING
            state = ("필드 없음" if value is MISSING else "null" if value is None
                     else "false" if value is False else "true" if value is True
                     else "빈 배열" if value == [] else "빈 객체" if value == {}
                     else "빈 문자열" if value == "" else "값 있음")
            states[state] += 1
            if value is not MISSING:
                if len(examples) < 3:
                    examples.append({"source": ref, "value": preview(value),
                                     "text": preview(item.get("text", ""))})
                if isinstance(value, (str, int, bool)):
                    values[json.dumps(value, ensure_ascii=False)] += 1
        result.append({"field": field, "targets": len(items), "states": dict(states),
                       "value_counts": dict(values.most_common(8)), "examples": examples})
    return result


def native_feature(items: list[tuple[str, Mapping]], fields: tuple[str, ...]) -> dict:
    inventory = field_inventory(items, fields)
    present = any(row["targets"] > row["states"].get("필드 없음", 0) for row in inventory)
    return {"mode": "명시적 필드 제공" if present else "현재 결과에 미제공",
            "fields": inventory}


def docling_features(raw: Mapping) -> dict:
    doc = raw.get("document", raw)
    if not isinstance(doc, Mapping):
        raise TypeError("Docling document must be an object")

    def items(kind: str) -> list[tuple[str, Mapping]]:
        value = doc.get(kind, [])
        if not isinstance(value, list) or any(not isinstance(v, Mapping) for v in value):
            raise ValueError(f"Invalid Docling collection: {kind}")
        return [(f"#/{kind}/{i}", v) for i, v in enumerate(value)]

    texts, tables, pictures, groups = (items(k) for k in ("texts", "tables", "pictures", "groups"))
    elements = texts + tables + pictures + items("key_value_items") + items("form_items")
    headings = [(r, v) for r, v in texts if v.get("label") in {"title", "section_header"}]
    cells = [(f"{ref}/data/table_cells/{i}", cell) for ref, item in tables
             for i, cell in enumerate(item.get("data", {}).get("table_cells", []))]
    provenance = [(f"{ref}/prov/{i}", prov) for ref, item in elements
                  for i, prov in enumerate(item.get("prov") or [])]
    result = {
        "classification": native_feature(elements, ("label",)),
        "headings": native_feature(headings, ("label", "level")),
        "hierarchy": native_feature([("#", doc)], ("groups", "body.children")),
        "formatting": native_feature(texts, ("formatting", "formatting.bold",
                                             "formatting.italic", "formatting.underline")),
        "tables": native_feature(tables, ("data.num_rows", "data.num_cols")),
        "location": native_feature(elements, ("prov",)),
        "metadata": native_feature([("#", doc)], ("origin", "name")),
        "resources": native_feature(pictures + tables, ("self_ref", "label", "captions",
                                                         "references", "image.mimetype")),
    }
    result["hierarchy"]["fields"] += field_inventory(groups + elements, ("parent", "children"))
    result["tables"]["fields"] += field_inventory(cells, (
        "text", "start_row_offset_idx", "end_row_offset_idx", "start_col_offset_idx",
        "end_col_offset_idx", "row_span", "col_span", "column_header", "row_header"))
    result["location"]["fields"] += field_inventory(provenance, ("page_no", "bbox", "charspan"))
    return result


class MarkupHTMLInventory(HTMLParser):
    """Inspect explicit HTML tags; never render document markup."""

    def __init__(self) -> None:
        super().__init__()
        self.counts: Counter = Counter()
        self.examples: list[dict] = []
        self.ignored = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in {"script", "style"}:
            self.ignored += 1
        if self.ignored:
            return
        self.counts[tag] += 1
        if tag in {"td", "th"} and len(self.examples) < 3:
            self.examples.append({"tag": tag, "attributes": dict(attrs)})

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self.ignored:
            self.ignored -= 1


def markup_features(text: str, source: str) -> dict:
    from markdown_it import MarkdownIt

    from docling_poc.comparison_structure import markup_blocks

    blocks = markup_blocks(text, source)
    headings = [b for b in blocks if b["kind"] == "heading"]
    is_html = bool(re.match(r"\s*(?:<!doctype\s+html[^>]*>\s*)?"
                            r"<(?:html|body|div|p|h[1-6]|table)(?:\s|>)", text, re.IGNORECASE))
    table_examples = []
    if is_html:
        parser = MarkupHTMLInventory()
        parser.feed(text)
        counts = parser.counts
        formatting = {k: counts[k] for k in ("strong", "b", "em", "i", "u") if counts[k]}
        nesting = {k: counts[k] for k in ("ul", "ol", "blockquote") if counts[k]}
        table_examples = parser.examples
        table_count = counts["table"]
    else:
        tokens = MarkdownIt("commonmark", {"html": False}).enable("table").parse(text)
        formatting = dict(Counter(t.type for token in tokens for t in (token.children or [])
                                  if t.type in {"strong_open", "em_open"}))
        nesting = dict(Counter(t.type for t in tokens if t.type in {
            "bullet_list_open", "ordered_list_open", "blockquote_open"}))
        table_count = sum(t.type == "table_open" for t in tokens)
        current = None
        for token in tokens:
            if token.type == "table_open":
                current = {"rows": 0, "cells_per_row": []}
            elif current is not None and token.type == "tr_open":
                current["rows"] += 1
                current["cells_per_row"].append(0)
            elif current is not None and token.type in {"td_open", "th_open"}:
                current["cells_per_row"][-1] += 1
            elif token.type == "table_close":
                if len(table_examples) < 3:
                    table_examples.append(preview(current))
                current = None

    def observed(details: dict, present: bool) -> dict:
        return {"mode": "마크업으로 제공" if present else "현재 결과에 미제공",
                "source": source, "markup": "HTML" if is_html else "Markdown",
                "observed": details}

    classified = dict(Counter(b["kind"] for b in blocks if b["kind"] != "unknown"))
    return {
        "classification": observed({"출력 블록 분류": classified}, bool(classified)),
        "headings": observed({"제목 수": len(headings),
            "수준별 개수": dict(Counter(str(b["level"]) for b in headings)),
            "예시": [{"text": preview(b["text"]), "level": b["level"]}
                     for b in headings[:3]]}, bool(headings)),
        "hierarchy": observed({"목록·인용 컨테이너": nesting,
                               "제목 경로": "수준·읽기 순서로 후처리로 추론 필요"},
                              bool(nesting or headings)),
        "formatting": observed({"서식 표기 수": formatting,
                                "원문 예시": preview(text)}, bool(formatting)),
        "tables": observed({"표 수": table_count, "행·셀 예시": table_examples}, bool(table_count)),
    }


def tika_features(raw: list) -> dict:
    if not isinstance(raw, list) or not raw or any(not isinstance(v, Mapping) for v in raw):
        raise ValueError("Tika result must be a nonempty array of objects")
    scopes = {k: [] for k in ("classification", "headings", "hierarchy", "formatting", "tables")}
    for i, item in enumerate(raw):
        content = item.get("tk:content", item.get("X-TIKA:content", ""))
        if not isinstance(content, str):
            raise TypeError("Tika content must be a string")
        observed = markup_features(content, f"resource-{i} ({'루트' if i == 0 else '내장'})")
        for key, values in scopes.items():
            values.append(observed[key])
    result = {key: {"mode": "마크업으로 제공" if any(
        s["mode"] == "마크업으로 제공" for s in values) else "현재 결과에 미제공",
        "scopes": values} for key, values in scopes.items()}
    resources = [(f"resource-{i}", item) for i, item in enumerate(raw[1:], 1)]
    result["hierarchy"]["resource_fields"] = field_inventory(resources, (
        "tk:embedded-depth", "tk:embedded-resource-path", "X-TIKA:embedded_depth",
        "X-TIKA:embedded_resource_path"))
    if any(row["targets"] > row["states"].get("필드 없음", 0)
           for row in result["hierarchy"]["resource_fields"]):
        result["hierarchy"]["mode"] = (
            "명시적 필드 제공 (리소스 계층) / " + result["hierarchy"]["mode"] + " (본문)")
    root = raw[0]
    metadata = tuple(k for k in root if k not in {"tk:content", "X-TIKA:content"})
    result["metadata"] = native_feature([("resource-0", root)], metadata)
    result["location"] = {
        "mode": "현재 결과에 미제공",
        "note": "현재 비교 경로에서는 요소별 page_no/bbox/charspan을 확인하지 않음. "
                "아래 페이지 관련 문서 메타데이터는 요소 위치가 아님.",
        "fields": field_inventory([("resource-0", root)], tuple(
            k for k in metadata if "page" in k.lower())),
    }
    result["resources"] = native_feature(resources, (
        "tk:resource-name", "resourceName", "Content-Type", "tk:embedded-depth",
        "X-TIKA:embedded_depth", "tk:content", "X-TIKA:content"))
    result["resources"]["resource_count"] = len(resources)
    return result


def load_features(output: Path, runs: list[Mapping], tool: str) -> dict:
    runs = sorted(runs, key=lambda r: r["number"])
    selected = next((r for r in runs if r["status"] == "success"),
                    next((r for r in runs if r["status"] == "partial_success"), None))
    result = {"run": selected["number"] if selected else None,
              "status": selected["status"] if selected else "비교 불가",
              "features": {}, "excerpts": {}, "source_file": "", "warning": ""}
    if selected is None:
        result["warning"] = "비교할 성공·부분 성공 결과가 없습니다."
        return result
    directory = output / selected["path"]
    try:
        raw_path = raw_result_path(directory)
        raw = json.loads(read_raw_text(raw_path))
        result["features"] = docling_features(raw) if tool == "docling" else tika_features(raw)
        result["excerpts"] = docling_excerpts(raw) if tool == "docling" else tika_excerpts(raw)
        result["source_file"] = f'{selected["path"]}/{raw_path.name}'
    except (OSError, EOFError, ValueError, TypeError, KeyError, AttributeError) as exc:
        result["warning"] = f"원본 JSON 확인 불가: {exc}. 필드 미제공으로 판정하지 않습니다."
        markdown = directory / "content.md"
        if markdown.is_file():
            result["features"] = markup_features(markdown.read_text(encoding="utf-8"),
                                                  "content.md (원본 JSON 대체 보기)")
            result["excerpts"] = markup_excerpts(markdown.read_text(encoding="utf-8"), "content.md")
            result["source_file"] = f'{selected["path"]}/content.md'
    return result


def feature_html(comparison: Mapping) -> str:
    def esc(value: object) -> str:
        return escape(str(value), quote=True)

    parts = ['<h3>추출 정보 비교</h3>',
             ('<p>각 도구의 첫 완전 성공 회차를 사용하며, 없으면 첫 부분 성공을 표시합니다. '
             '아래는 현재 문서·설정의 관찰 결과이며 도구 전체의 기능 유무나 정확도 점수가 아닙니다. '
             '구조 보기의 회차 선택과는 독립적입니다.</p>'),
             ('<p>코드 영역에는 실제 JSON 필드·값 또는 Markdown·HTML 원문만 표시합니다. '
             '각 항목은 최대 3개 발췌이며 두 도구의 발췌 구간이 자동으로 대응되지는 않습니다. '
             'JSON은 관련 필드를 선택하고 배열은 앞 3개까지 표시하며 생략 범위를 별도 안내합니다. '
             'grid·data URI·2만 자 초과 문자열 필드와 2만 자 초과 마크업 구간은 생략합니다. '
             '참조 대상은 발췌 밖에 있을 수 있습니다. 빈 값과 false는 원본 그대로 유지합니다.</p>'),
             ('<p>출처의 문자 범위는 Python 문자열 인덱스 [시작:끝), 끝 제외입니다. '
             'Tika의 리소스 깊이는 본문 계층이 아니며 이미지 파일명 제목은 본문 제목과 '
             '구분해서 확인해야 합니다.</p>')]
    for tool, result in comparison.items():
        parts.append(f'<p><b>{esc(tool.upper())}</b> · 회차 {esc(result["run"])} · '
                     f'{esc(result["status"])} {esc(result["warning"])}</p>')
    parts.append('<div class="scroll"><table class="feature-comparison">'
                 '<colgroup><col style="width:20%"><col style="width:40%">'
                 '<col style="width:40%"></colgroup><thead><tr><th>기능</th><th>DOCLING</th>'
                 '<th>TIKA</th></tr></thead><tbody>')
    for key, title in FEATURES.items():
        parts.append(f'<tr><th scope="row">{title}</th>')
        for tool in ("docling", "tika"):
            result = comparison[tool]
            excerpts = result.get("excerpts", {}).get(key, [])
            parts.append('<td>')
            if not excerpts:
                message = ("확인 불가 · 원본 JSON 또는 유효 실행 필요" if not result["features"]
                           else "관련 원본 발췌 없음 · 도구 전체의 미지원 판정은 아닙니다.")
                parts.append(f'<p class="muted">{message}</p>')
            for excerpt in excerpts:
                parts.append(f'<p class="muted">{esc(result.get("source_file", ""))}<br>'
                             f'{esc(excerpt["source"])} · {esc(excerpt["format"].upper())}</p>')
                if excerpt["note"]:
                    parts.append(f'<p class="muted">{esc(excerpt["note"])}</p>')
                parts.append('<pre><code>' + esc(excerpt["content"]) + '</code></pre>')
            parts.append('</td>')
        parts.append('</tr>')
    return "\n".join(parts) + '</tbody></table></div>'
