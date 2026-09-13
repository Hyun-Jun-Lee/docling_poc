import json
from copy import deepcopy

import pytest

from docling_poc.comparison_cards import cards_html, load_cards, validate_bundle


def document():
    return {"id": "d1", "name": "sample.docx", "sha256": "abc", "source": "sample.docx",
            "runs": {"docling": [{"number": 1, "status": "success", "path": "docling-1"}],
                     "tika": [{"number": 2, "status": "partial_success", "path": "tika-2"}]}}


def bundle():
    return {"schema": "docling_poc.feature_cards", "version": 1, "cards": [{
        "id": "c1", "document_id": "d1", "document_sha256": "abc", "kind": "headings",
        "title": "지원 대상", "reason": "제목 수준 확인", "source_location": "1페이지",
        "note": "에이전트 메모", "original_checked": False,
        "docling": {"format": "json", "content": '{"label":"section_header","level":2}',
                    "run": 1, "source_file": "docling-1/raw.json.gz", "source_refs": ["#/texts/0"]},
        "tika": {"format": "markdown", "content": "## 지원 대상\n\n본문  ", "run": 2,
                 "source_file": "tika-2/content.md", "source_refs": []},
    }]}


def test_card_bundle_preserves_literal_evidence_and_partial_run():
    payload = bundle()
    before = deepcopy(payload)
    assert validate_bundle(payload, [document()]) == payload["cards"]
    assert payload == before
    assert payload["cards"][0]["tika"]["content"].endswith("  ")


@pytest.mark.parametrize("change", [
    {"document_sha256": "different"}, {"document_id": "d2"}, {"kind": "invalid"},
    {"title": ""}, {"original_checked": "yes"}, {"docling": None, "tika": None},
])
def test_invalid_cards_do_not_pass_validation(change):
    payload = bundle()
    payload["cards"][0].update(change)
    with pytest.raises((ValueError, TypeError)):
        validate_bundle(payload, [document()])


@pytest.mark.parametrize("change", [{"run": 9}, {"format": "auto"}, {"content": "{} trailing"},
                                   {"content": "false"}, {"content": '{"value":NaN}'},
                                   {"content": '{"texts":null}'},
                                   {"content": '{"document":false}'},
                                   {"source_refs": "#/texts/0"}])
def test_invalid_evidence_is_rejected(change):
    payload = bundle()
    payload["cards"][0]["docling"].update(change)
    with pytest.raises((ValueError, TypeError)):
        validate_bundle(payload, [document()])


def test_duplicate_card_ids_are_rejected():
    payload = bundle()
    payload["cards"].append(deepcopy(payload["cards"][0]))
    with pytest.raises(ValueError, match="중복"):
        validate_bundle(payload, [document()])


def test_agent_card_payload_is_escaped_and_source_paths_are_not_opened(tmp_path):
    payload = bundle()
    marker = '</textarea><script>alert("x")</script>'
    payload["cards"][0]["note"] = marker
    payload["cards"][0]["docling"]["source_file"] = "/does-not-exist/private.json"
    path = tmp_path / "cards.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    cards = load_cards(path, [document()])
    html = cards_html(document(), cards)
    assert marker not in html
    assert "&lt;/textarea&gt;" in html
    assert "/does-not-exist/private.json" in html
    assert "카드 포함 HTML 저장" in html


@pytest.mark.parametrize("saved_content", [json.dumps(bundle()), "invalid JSON"])
def test_generate_omits_cards_and_keeps_feature_table_and_review(tmp_path, saved_content):
    from docling_poc.comparison_report import generate

    doc = document()
    doc["runs"] = {"docling": [], "tika": []}
    (tmp_path / "manifest.json").write_text(json.dumps({
        "created": "test", "settings": {"repeat": 5}, "documents": [doc],
    }), encoding="utf-8")
    path = tmp_path / "feature-cards.json"
    path.write_text(saved_content, encoding="utf-8")
    generate(tmp_path)
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "샘플 구간 · 기능별 비교 카드" not in html
    assert "sample-cards" not in html
    assert "카드 JSON 불러오기" not in html
    assert "지원 대상" not in html
    assert '<details class="legacy-review">' in html
    assert "추출 정보 비교" in html
    assert html.count('<script>') == 1
    assert "docling_poc.feature_cards" not in html
    assert 'fetch(' not in html
    assert path.read_text(encoding="utf-8") == saved_content
