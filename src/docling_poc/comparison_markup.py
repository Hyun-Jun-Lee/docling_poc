"""Read markup blocks for the report feature inventory without rendering HTML."""

from __future__ import annotations

import re
from html.parser import HTMLParser

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
    return result
