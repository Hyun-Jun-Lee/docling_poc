"""Select literal excerpts for the feature table; annotations stay outside the evidence."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from html.parser import HTMLParser

LIMIT = 3
MAX_TEXT = 20_000
MARKUP_KEYS = ("classification", "headings", "hierarchy", "formatting", "tables")


def json_excerpt(value: Mapping, source: str) -> dict:
    omitted = []

    def copy(item, path):
        if isinstance(item, Mapping):
            result = {}
            for key, child in item.items():
                child_path = f"{path}/{key}"
                if (key == "grid" or isinstance(child, str)
                        and (child.startswith("data:") or len(child) > MAX_TEXT)):
                    omitted.append(child_path)
                else:
                    result[key] = copy(child, child_path)
            return result
        if isinstance(item, list):
            if len(item) > LIMIT:
                omitted.append(f"{path}: 전체 {len(item)}개 중 앞 {LIMIT}개 표시")
            return [copy(child, f"{path}/{i}") for i, child in enumerate(item[:LIMIT])]
        return item

    content = json.dumps(copy(value, source), ensure_ascii=False, indent=2)
    return {"source": source, "format": "json", "content": content,
            "note": "생략: " + "; ".join(omitted) if omitted else ""}


def docling_excerpts(raw: Mapping) -> dict:
    doc = raw.get("document", raw)
    prefix = "#/document" if "document" in raw else "#"

    def items(key):
        return [(f"{prefix}/{key}/{i}", item) for i, item in enumerate(doc.get(key, []))]

    texts, groups, tables, pictures = (items(k) for k in ("texts", "groups", "tables", "pictures"))
    elements = texts + tables + pictures + items("key_value_items") + items("form_items")

    def choose(rows, keys=None):
        selected = []
        for source, value in rows[:LIMIT]:
            projected = {k: v for k, v in value.items() if keys is None or k in keys}
            if projected:
                excerpt = json_excerpt(projected, source)
                if keys is not None:
                    excerpt["note"] = "관련 필드만 발췌. " + excerpt["note"]
                selected.append(excerpt)
        return selected

    # Show distinct labels rather than three consecutive paragraphs of the same kind.
    labels = set()
    classified = []
    for source, item in elements:
        label = item.get("label")
        if label is not None and label not in labels:
            classified.append((source, item))
            labels.add(label)
    formatting = [(r, v) for r, v in texts if "formatting" in v or "hyperlink" in v]
    formatting.sort(key=lambda row: not any(
        v is True for v in (row[1].get("formatting") or {}).values()))
    locations = [(r, v) for r, v in elements if "prov" in v]
    locations.sort(key=lambda row: not bool(row[1]["prov"]))
    return {
        "classification": choose(classified, {"self_ref", "label", "text", "content_layer"}),
        "headings": choose([(r, v) for r, v in texts
                            if v.get("label") in {"title", "section_header"}],
                           {"self_ref", "label", "text", "level", "parent", "children"}),
        "hierarchy": choose(groups if groups else
                            [(f"{prefix}/body", doc["body"])] if "body" in doc else []),
        "formatting": choose(formatting, {"self_ref", "text", "orig", "formatting", "hyperlink"}),
        "tables": choose(tables),
        "location": choose(locations, {"self_ref", "text", "label", "prov"}),
        "metadata": choose([(prefix, doc)], {"origin", "name"}),
        "resources": choose(pictures),
    }


class HTMLRanges(HTMLParser):
    """Find original element spans without serializing or executing HTML."""

    def __init__(self, text: str):
        super().__init__(convert_charrefs=False)
        self.text = text
        self.offsets = [0]
        for match in re.finditer("\n", text):
            self.offsets.append(match.end())
        self.stack = []
        self.ranges = {key: [] for key in MARKUP_KEYS}
        self.ignored = 0

    def position(self):
        line, column = self.getpos()
        return self.offsets[line - 1] + column

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.ignored += 1
        if self.ignored:
            return
        kinds = []
        if tag in {"p", "table", "ul", "ol", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6"}:
            kinds.append("classification")
        if re.fullmatch("h[1-6]", tag):
            kinds.append("headings")
        if tag in {"ul", "ol", "blockquote"}:
            kinds.append("hierarchy")
        if tag in {"b", "strong", "em", "i", "u"}:
            kinds.append("formatting")
        if tag == "table":
            kinds.append("tables")
        if kinds:
            self.stack.append((tag, self.position(), kinds))

    def handle_endtag(self, tag):
        if self.ignored:
            if tag in {"script", "style"}:
                self.ignored -= 1
            return
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                _, start, kinds = self.stack.pop(i)
                end = self.text.find(">", self.position()) + 1
                if end:
                    for kind in kinds:
                        self.ranges[kind].append((start, end))
                break


def markup_excerpts(text: str, source: str) -> dict:
    from markdown_it import MarkdownIt

    ranges = {key: [] for key in MARKUP_KEYS}
    is_html = bool(re.match(r"\s*(?:<!doctype\s+html[^>]*>\s*)?"
                            r"<(?:html|body|div|p|h[1-6]|table|ul|ol|blockquote|strong|b|em|i|u)"
                            r"(?:\s|>)", text, re.IGNORECASE))
    if is_html:
        parser = HTMLRanges(text)
        parser.feed(text)
        ranges = parser.ranges
    else:
        # MarkdownIt normalizes CRLF/CR, but vertical tabs are not line boundaries.
        offsets = [0] + [match.end() for match in re.finditer(r"\r\n|\r|\n", text)]
        if offsets[-1] != len(text):
            offsets.append(len(text))
        for token in MarkdownIt("commonmark", {"html": False}).enable("table").parse(text):
            if token.map is None:
                continue
            span = (offsets[token.map[0]], offsets[token.map[1]])
            if token.type in {"heading_open", "paragraph_open", "table_open",
                              "bullet_list_open", "ordered_list_open", "blockquote_open"}:
                ranges["classification"].append(span)
            if token.type == "heading_open":
                ranges["headings"].append(span)
            if token.type in {"bullet_list_open", "ordered_list_open", "blockquote_open"}:
                ranges["hierarchy"].append(span)
            if token.type == "table_open":
                ranges["tables"].append(span)
            if token.type == "inline" and any(
                child.type in {"strong_open", "em_open"} for child in token.children or []
            ):
                ranges["formatting"].append(span)
    result = {}
    for key, spans in ranges.items():
        eligible = [(start, end) for start, end in sorted(set(spans))
                    if end - start <= MAX_TEXT]
        result[key] = [
            {"source": f"{source} [{start}:{end})", "format": "html" if is_html else "markdown",
             "content": text[start:end], "note": ""}
            for start, end in eligible[:LIMIT]]
    return result


def tika_excerpts(raw: list) -> dict:
    result = {key: [] for key in (*MARKUP_KEYS, "location", "metadata", "resources")}
    for i, resource in enumerate(raw):
        key = "tk:content" if "tk:content" in resource else "X-TIKA:content"
        markup = markup_excerpts(resource.get(key, ""), f"#/{i}/{key}")
        for kind, excerpts in markup.items():
            result[kind].extend(excerpts[:max(0, LIMIT - len(result[kind]))])
        metadata = {k: v for k, v in resource.items() if k not in {"tk:content", "X-TIKA:content"}}
        if i == 0:
            if metadata:
                result["metadata"].append(json_excerpt(metadata, "#/0"))
            pages = {k: v for k, v in metadata.items() if "page" in k.lower()}
            if pages:
                excerpt = json_excerpt(pages, "#/0")
                excerpt["note"] = ("페이지 관련 문서 메타데이터 발췌. 개별 요소의 위치가 아닙니다. "
                                   + excerpt["note"])
                result["location"].append(excerpt)
        elif len(result["resources"]) < LIMIT:
            excerpt = json_excerpt(metadata, f"#/{i}")
            excerpt["note"] = "내장 리소스 메타데이터 발췌. " + excerpt["note"]
            result["resources"].append(excerpt)
    return result
