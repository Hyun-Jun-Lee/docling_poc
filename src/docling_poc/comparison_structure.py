"""Report-only structural projections. No inferred headings or model execution."""

from __future__ import annotations

import gzip
import hashlib
import json
import re
from collections.abc import Mapping
from html.parser import HTMLParser
from pathlib import Path

KINDS = {
    "title": "title", "section_header": "heading", "text": "paragraph",
    "paragraph": "paragraph", "list_item": "list", "table": "table",
    "picture": "picture", "page_header": "page_header", "page_footer": "page_footer",
}


def block(identifier: str, text: str, label: str, level: int | None = None,
          evidence: str = "native", **extra: object) -> dict:
    return {"id": identifier, "text": text, "label": label,
            "kind": KINDS.get(label, "unknown"), "level": level,
            "evidence": evidence, "path": [], "parent_heading": None,
            "relation": "unresolved", "location": "", **extra}


def assign_paths(blocks: list[dict]) -> list[dict]:
    """Use explicit ancestors first, otherwise a level stack within each content scope."""
    by_id = {b["id"]: b for b in blocks}
    stack: list[dict] = []
    previous_scope = None
    for b in blocks:
        scope = b.get("scope", "body")
        if scope != previous_scope:
            stack = []
            previous_scope = scope
        explicit = [by_id[r] for r in b.get("ancestors", [])
                    if r in by_id and by_id[r]["kind"] in {"title", "heading"}]
        is_heading = b["kind"] in {"title", "heading"}
        if b["kind"] in {"page_header", "page_footer"} or scope == "furniture":
            b["relation"] = "not_section"
            continue
        level = b["level"]
        if is_heading:
            if level is None:
                stack = []
            else:
                while stack and (stack[-1]["level"] is None or stack[-1]["level"] >= level):
                    stack.pop()
        parents = explicit or stack[:]
        if explicit:
            b["relation"] = "explicit"
        elif parents or is_heading and level == 1:
            b["relation"] = "level_order"
        b["parent_heading"] = parents[-1]["id"] if parents else None
        b["path"] = [{"id": p["id"], "text": p["text"]} for p in parents]
        # An unlevelled heading cannot establish an order-derived section boundary.
        if is_heading and level is not None:
            stack = parents + [b]
    return blocks


def docling_blocks(raw: Mapping) -> list[dict]:
    doc = raw.get("document", raw)
    if not isinstance(doc, Mapping):
        raise TypeError("Docling document must be an object")
    blocks: list[dict] = []
    visited: set[str] = set()
    auxiliary: list[tuple[str, str, list[str], set[str]]] = []

    def visit(ref: str, scope: str, ancestors: list[str], active: set[str]) -> None:
        if ref in active:
            raise ValueError(f"Cyclic Docling reference: {ref}")
        match = re.fullmatch(r"#/([a-z_]+)/(\d+)", ref)
        if not match:
            raise ValueError(f"Invalid Docling reference: {ref}")
        kind, index = match.group(1), int(match.group(2))
        items = doc.get(kind)
        if not isinstance(items, list) or index >= len(items):
            raise ValueError(f"Missing Docling reference: {ref}")
        item = items[index]
        if not isinstance(item, Mapping):
            raise TypeError(f"Invalid Docling item: {ref}")
        if ref in visited:
            return
        visited.add(ref)
        label = item.get("label", kind)
        level = item.get("level")
        if level is not None and (type(level) is not int or level < 1):
            raise ValueError(f"Invalid heading level: {ref}")
        text = item.get("text", "")
        if kind == "tables":
            text = "\n".join(c.get("text", "")
                             for c in item.get("data", {}).get("table_cells", []))
        if kind != "groups":
            pages = list(dict.fromkeys(p.get("page_no") for p in item.get("prov", [])))
            blocks.append(block(ref, text, label, level, scope=scope, ancestors=ancestors,
                                location=", ".join(f"페이지 {p}" for p in pages),
                                source_ref=ref, marker=item.get("marker"),
                                enumerated=item.get("enumerated")))
        for child in item.get("children", []):
            visit(child["$ref"], scope, ancestors + [ref], active | {ref})
        for field in ("captions", "footnotes"):
            for child in item.get(field, []):
                auxiliary.append((child["$ref"], scope, ancestors + [ref], active | {ref}))

    for scope in ("body", "furniture"):
        for child in doc.get(scope, {}).get("children", []):
            visit(child["$ref"], scope, [], set())
    # References to captions must not pull later body items forward in reading order.
    for ref, scope, ancestors, active in auxiliary:
        if ref not in visited:
            visit(ref, f"auxiliary:{ref}", ancestors, active)
    for kind in ("texts", "tables", "pictures", "key_value_items", "form_items"):
        for index in range(len(doc.get(kind, []))):
            ref = f"#/{kind}/{index}"
            if ref not in visited:
                visit(ref, f"unattached:{ref}", [], set())
    return assign_paths(blocks)


class ContentHTMLParser(HTMLParser):
    """Read block tags only; never fetch links, render HTML or execute its contents."""

    def __init__(self) -> None:
        super().__init__()
        self.blocks: list[dict] = []
        self.current: tuple[str, int | None] | None = None
        self.text: list[str] = []
        self.ignored = 0

    def flush(self) -> None:
        text = "".join(self.text).strip()
        if text:
            label, level = self.current or ("unknown", None)
            self.blocks.append(block(str(len(self.blocks)), text, label, level, "html"))
        self.text = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in {"script", "style"}:
            self.ignored += 1
        if self.ignored:
            return
        if re.fullmatch(r"h[1-6]", tag) or tag in {"p", "li", "table", "header", "footer"}:
            if self.current and self.current[0] == "table":
                return
            self.flush()
            label = {"p": "paragraph", "li": "list_item", "table": "table",
                     "header": "unknown", "footer": "unknown"}.get(tag, "section_header")
            self.current = (label, int(tag[1]) if re.fullmatch(r"h[1-6]", tag) else None)
        elif tag in {"br", "tr", "td", "th"}:
            self.text.append("\n" if tag in {"br", "tr"} else "\t")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self.ignored:
            self.ignored -= 1
            return
        if self.ignored:
            return
        if self.current and self.current[0] == "table" and tag != "table":
            return
        if re.fullmatch(r"h[1-6]", tag) or tag in {"p", "li", "table", "header", "footer"}:
            self.flush()
            self.current = None

    def handle_data(self, data: str) -> None:
        if not self.ignored:
            self.text.append(data)


def markup_blocks(text: str, prefix: str = "content") -> list[dict]:
    if re.match(r"\s*(?:<!doctype\s+html[^>]*>\s*)?"
                r"<(?:html|body|div|p|h[1-6]|table)(?:\s|>)", text, re.IGNORECASE):
        parser = ContentHTMLParser()
        parser.feed(text)
        parser.close()
        parser.flush()
        result = parser.blocks
    else:
        from markdown_it import MarkdownIt

        tokens = MarkdownIt("commonmark", {"html": False}).enable("table").parse(text)
        result = []
        table_end = -1
        list_depth = 0
        for i, token in enumerate(tokens):
            if token.type in {"bullet_list_open", "ordered_list_open"}:
                list_depth += 1
            elif token.type in {"bullet_list_close", "ordered_list_close"}:
                list_depth -= 1
            if i <= table_end:
                continue
            if token.type == "table_open":
                table_end = next(j for j in range(i + 1, len(tokens))
                                 if tokens[j].type == "table_close")
                content = "\n".join(t.content for t in tokens[i:table_end] if t.type == "inline")
                result.append(block(str(i), content, "table", evidence="markdown"))
            elif token.type in {"heading_open", "paragraph_open"}:
                content = tokens[i + 1].content
                heading = token.type == "heading_open"
                label = "section_header" if heading else "list_item" if list_depth else "unknown"
                result.append(block(str(i), content, label,
                                    int(token.tag[1:]) if heading else None,
                                    "markdown" if heading or list_depth else "text"))
            elif token.type in {"fence", "code_block"}:
                result.append(block(str(i), token.content, "code", evidence="markdown"))
    for i, b in enumerate(result):
        b.update(id=f"{prefix}:{i}", source_ref=f"{prefix}:{i}", scope=prefix,
                 location=f"{prefix} 블록 {i + 1}")
    return assign_paths(result)


def tika_blocks(raw: list) -> list[dict]:
    if not isinstance(raw, list) or not raw:
        raise ValueError("Tika result must be a nonempty array")
    result = []
    for i, resource in enumerate(raw):
        content = resource.get("tk:content", resource.get("X-TIKA:content", ""))
        blocks = markup_blocks(content, f"resource-{i}")
        name = resource.get("tk:resource-name", resource.get("resourceName", ""))
        for b in blocks:
            b["resource"] = str(name)
        result.extend(blocks)
    return result


def load_structure(output: Path, document: Mapping, tool: str, run: Mapping) -> dict:
    directory = output / run["path"]
    raw_path = directory / "raw.json.gz"
    warnings = []
    fingerprint = ""
    blocks = []
    if raw_path.is_file():
        try:
            with gzip.open(raw_path, "rt", encoding="utf-8") as stream:
                raw_text = stream.read()
            fingerprint = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
            raw = json.loads(raw_text)
            blocks = docling_blocks(raw) if tool == "docling" else tika_blocks(raw)
        except (ValueError, TypeError, KeyError, OSError, AttributeError) as exc:
            warnings.append(f"원본 구조 분석 실패: {exc}")
    else:
        warnings.append("원본 JSON 없음: Markdown 출력만 표시하며 네이티브 구조는 확인 불가")
    if not blocks and (directory / "content.md").is_file():
        markdown = (directory / "content.md").read_text(encoding="utf-8")
        if not fingerprint:
            fingerprint = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
        # Empty native extraction is distinct from an actual fallback.
        if warnings:
            blocks = markup_blocks(markdown)
    return {"schema_version": 1, "document_id": document["id"],
            "document_sha256": document.get("sha256", ""), "tool": tool,
            "run": run["number"], "fingerprint": fingerprint, "status": run["status"],
            "warnings": warnings, "blocks": blocks}
