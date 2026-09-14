"""Portable sample cards from pasted evidence or an agent's saved card bundle."""

from __future__ import annotations

import json
from collections.abc import Mapping
from html import escape
from pathlib import Path

CARD_SCHEMA = "docling_poc.feature_cards"
CARD_KINDS = {
    "headings": "제목·본문", "lists": "목록·관계", "formatting": "서식",
    "tables": "표 구조", "pictures": "그림·캡션", "furniture": "본문·머리글",
    "location": "원본 위치", "other": "기타",
}
MAX_BUNDLE_BYTES = 20 * 1024 * 1024
MAX_CONTENT_CHARS = 2_000_000
MAX_CARDS = 200

CARD_CSS = """
.sample-cards{margin-top:32px}.sample-cards label{display:block;margin:10px 0}
.sample-cards input[type=text],.sample-cards textarea{display:block;width:100%;box-sizing:border-box;
padding:10px;border:1px solid #b6c3d3;border-radius:6px;font:inherit}
.sample-cards textarea{min-height:100px}.sample-cards .evidence-input{min-height:220px;
font:13px/1.5 Consolas,monospace;white-space:pre}
.sample-cards button,.sample-cards select,.sample-cards input[type=number]{padding:8px;
font:inherit;border:1px solid #aab8c9;border-radius:6px;background:white}
.sample-cards button{cursor:pointer}.sample-cards button:focus-visible{outline:3px solid #60a5fa}
.sample-cards .card-actions{display:flex;flex-wrap:wrap;gap:8px;margin:16px 0}
.sample-cards .create-card{background:#155db1;color:white}.sample-cards .sample-card{background:white;
border:1px solid #cbd5e1;border-radius:10px;padding:20px;margin:20px 0}
.sample-cards .sample-card h4{font-size:20px;margin:0 0 12px}.sample-cards pre{white-space:pre-wrap}
.sample-cards .card-message{white-space:pre-wrap;color:#9a3412}
.sample-cards .card-source{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;color:#526174}
.sample-cards .card-observation{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}
.sample-cards .card-empty{border:1px dashed #b6c3d3;border-radius:8px;padding:24px;color:#64748b}
.sample-cards .card-note{white-space:pre-wrap}
@media print{.sample-cards .card-editor,.sample-cards .card-actions{display:none}}
"""


def validate_evidence_json(value: object, tool: str) -> None:
    if not isinstance(value, (dict, list)):
        raise TypeError(f"{tool}: JSON 증거는 객체 또는 배열이어야 합니다.")
    if tool == "tika":
        items = value if isinstance(value, list) else [value]
        if any(not isinstance(item, dict) for item in items):
            raise ValueError("Tika 리소스는 객체 배열이어야 합니다.")
        for item in items:
            key = "tk:content" if "tk:content" in item else "X-TIKA:content"
            if key in item and not isinstance(item[key], str):
                raise ValueError("Tika 내용 필드는 문자열이어야 합니다.")
        return
    doc = value.get("document", value) if isinstance(value, dict) else value
    if not isinstance(doc, (dict, list)):
        raise TypeError("Docling document는 객체 또는 항목 배열이어야 합니다.")
    collections = [doc] if isinstance(doc, list) else [
        doc[key] for key in ("texts", "groups", "tables", "pictures", "key_value_items",
                            "form_items", "items") if key in doc]
    if any(not isinstance(items, list) or any(not isinstance(item, dict) for item in items)
           for items in collections):
        raise ValueError("Docling 항목은 객체 배열이어야 합니다.")


def validate_bundle(payload: object, documents: list[Mapping]) -> list[dict]:
    """Validate all cards before importing; paths are provenance strings, never file reads."""
    if not isinstance(payload, dict) or payload.get("schema") != CARD_SCHEMA or (
        type(payload.get("version")) is not int or payload["version"] != 1
    ):
        raise ValueError("카드 JSON의 schema/version을 확인하세요.")
    cards = payload.get("cards")
    if not isinstance(cards, list) or len(cards) > MAX_CARDS:
        raise ValueError(f"cards는 {MAX_CARDS}개 이하의 배열이어야 합니다.")
    if len(json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")) > MAX_BUNDLE_BYTES:
        raise ValueError("카드 JSON은 20 MB 이하로 보관하세요.")
    known = {d["id"]: d for d in documents}
    seen = set()
    for card in cards:
        if not isinstance(card, dict):
            raise TypeError("각 카드는 JSON 객체여야 합니다.")
        for key in ("id", "document_id", "document_sha256", "title", "kind",
                    "reason", "source_location", "note"):
            if not isinstance(card.get(key), str):
                raise TypeError(f"카드의 {key}는 문자열이어야 합니다.")
        if not card["id"].strip() or not card["title"].strip() or card["kind"] not in CARD_KINDS:
            raise ValueError("카드 ID·제목·유형을 확인하세요.")
        if card["id"] in seen:
            raise ValueError(f"중복 카드 ID: {card['id']}")
        seen.add(card["id"])
        doc = known.get(card["document_id"])
        if doc is None or card["document_sha256"] != doc.get("sha256", ""):
            raise ValueError(f"카드 {card['id']}: 문서 ID 또는 SHA-256이 보고서와 다릅니다.")
        if card.get("original_checked") is not None and type(card["original_checked"]) is not bool:
            raise ValueError("original_checked는 true, false 또는 null이어야 합니다.")
        if card.get("docling") is None and card.get("tika") is None:
            raise ValueError("카드에는 적어도 한 도구의 증거가 필요합니다.")
        for tool in ("docling", "tika"):
            evidence = card.get(tool)
            if evidence is None:
                continue
            if not isinstance(evidence, dict) or evidence.get("format") not in {
                "json", "markdown", "text",
            }:
                raise ValueError(f"{tool}: format은 json, markdown, text 중 하나여야 합니다.")
            content = evidence.get("content")
            if not isinstance(content, str) or not content.strip() or len(content) > MAX_CONTENT_CHARS:
                raise ValueError(f"{tool}: 비어 있지 않은 200만 자 이하 content가 필요합니다.")
            if not isinstance(evidence.get("source_file"), str) or not isinstance(
                evidence.get("source_refs"), list
            ) or not all(isinstance(r, str) for r in evidence["source_refs"]):
                raise ValueError(f"{tool}: source_file과 source_refs를 확인하세요.")
            run = evidence.get("run")
            if run is not None and (type(run) is not int or run < 1 or not any(
                r["number"] == run for r in doc["runs"][tool]
            )):
                raise ValueError(f"{tool}: 보고서에 없는 회차입니다.")
            if evidence["format"] == "json":
                try:
                    def reject_constant(value: str) -> None:
                        raise ValueError(f"JSON 비표준 값: {value}")

                    value = json.loads(content, parse_constant=reject_constant)
                except ValueError as exc:
                    raise ValueError(f"{tool}: content의 JSON이 잘못되었습니다.") from exc
                validate_evidence_json(value, tool)
    return cards


def load_cards(path: Path | None, documents: list[Mapping]) -> list[dict]:
    if path is None:
        return []
    if path.stat().st_size > MAX_BUNDLE_BYTES:
        raise ValueError("카드 JSON은 20 MB 이하로 불러오세요.")
    return validate_bundle(json.loads(path.read_text(encoding="utf-8")), documents)


def cards_html(document: Mapping, cards: list[dict]) -> str:
    context = {
        "id": document["id"], "name": document["name"], "sha256": document.get("sha256", ""),
        "runs": {tool: [{"number": r["number"], "status": r["status"]}
                        for r in document["runs"][tool]] for tool in ("docling", "tika")},
        "cards": [c for c in cards if c["document_id"] == document["id"]],
    }
    encoded = escape(json.dumps(context, ensure_ascii=False), quote=True)
    kinds = "".join(f'<option value="{key}">{label}</option>' for key, label in CARD_KINDS.items())
    return f"""
<div class="sample-cards">
<textarea class="sample-card-data" hidden>{encoded}</textarea>
<h3>샘플 구간 · 기능별 비교 카드</h3>
<p>같은 원본 구간의 Docling·Tika 결과를 붙여넣거나 에이전트의 카드 JSON을 불러오세요.
원본 증거, 발췌에서 확인한 속성, 후속 처리 방법을 카드로 보여줍니다. 구간 대응은 직접 확인합니다.</p>
<div class="card-actions">
<label>카드 JSON 불러오기 (전체 문서)<input class="import-cards" type="file" accept=".json"></label>
<button type="button" class="export-cards">전체 카드 JSON 내보내기</button>
<button type="button" class="export-card-html">카드 포함 HTML 저장</button>
</div>
<details class="card-editor" open>
<summary>샘플 구간을 붙여넣어 카드 만들기</summary>
<label>카드 제목<input class="card-title" type="text" placeholder="예: 신청 자격 목록"></label>
<label>비교 유형<select class="card-kind">{kinds}</select></label>
<label>선정 이유<input class="card-reason" type="text" placeholder="이 구간에서 확인할 기능 차이"></label>
<label>원본 위치<input class="card-location" type="text" placeholder="예: 3페이지, 신청 자격"></label>
<div class="grid evidence-editors"></div>
<label>원본 확인 여부<select class="original-checked"><option value="unknown">미기록</option>
<option value="true">원본 확인함 (작성자 기록)</option><option value="false">추출 결과 기반 후보</option>
</select></label>
<label>검토 메모<textarea class="card-note-input" placeholder="원본 대조 결과와 대응이 불확실한 부분"></textarea></label>
<div class="card-actions"><button type="button" class="create-card">비교 카드 생성</button>
<button type="button" class="reset-card">입력 초기화</button></div>
</details>
<p class="card-message" role="status" aria-live="polite"></p>
<p class="muted">JSON 필드와 Markdown 표기 후보를 구분합니다. 없는 속성은 ‘발췌에 없음’이며
도구 미지원 판정이 아닙니다. 문서·회차 일치와 원본 증거 검증은 별개입니다.
새로고침 전 JSON 또는 카드 포함 HTML로 저장하세요. 모든 처리는 이 브라우저 안에서 실행됩니다.</p>
<div class="sample-card-list"></div>
</div>
"""


def cards_script() -> str:
    return Path(__file__).with_suffix(".js").read_text(encoding="utf-8")
