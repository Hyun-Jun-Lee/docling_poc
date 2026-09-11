"""Self-contained review UI embedded in the portable comparison report."""

import json
from html import escape
from pathlib import Path

REVIEW_CSS = """
.structure-review textarea{width:100%;box-sizing:border-box;min-height:110px}
.structure-review select,.structure-review input,.structure-review button{font:inherit;
padding:6px;margin:4px;max-width:100%}.structure-review label{display:inline-block}
.structure-review .tool-panel{min-width:0;border:1px solid #cbd5e1;padding:14px}
.structure-review .outline{max-height:360px;overflow:auto;background:#f8fafc;padding:12px}
.structure-review .blocks{height:460px;overflow:auto;border-top:1px solid #cbd5e1}
.structure-review .block{padding:12px;border-bottom:1px solid #cbd5e1;scroll-margin:12px}
.structure-review .block:target{background:#fef3c7}
.structure-review .block pre{max-height:220px;margin:4px 0}
.structure-review .block button{float:right}.structure-review .outline ul{padding-left:20px}
.structure-review .review-message{white-space:pre-wrap;color:#9a3412}
.structure-review .preview{white-space:pre-wrap;background:#f1f5f9;padding:10px}
.structure-review .paste-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.structure-review .expectation{padding:12px;background:#f8fafc}
.structure-review .review-table td{max-width:380px;overflow-wrap:anywhere;white-space:pre-wrap}
.structure-review .copy-fallback{margin:10px 0}.structure-review .review-count{font-weight:bold}
@media(max-width:800px){.structure-review .paste-grid{display:block}}
"""


def review_html(document: dict, structures: dict) -> str:
    payload = {"document_id": document["id"], "document_sha256": document.get("sha256", ""),
               "name": document["name"], "tools": structures}
    encoded = escape(json.dumps(payload, ensure_ascii=False, allow_nan=False), quote=True)
    return f"""
<div class="structure-review">
<textarea class="structure-data" hidden>{encoded}</textarea>
<h3>문서 개요와 구간별 구조</h3>
<p>제목 수준 미제공과 분류 정보 없음을 구분합니다. 네이티브 속성, 출력 마크업,
수준·읽기 순서로 만든 파생 관계를 각각 표시합니다. 아래 실행 선택은 구조 보기에 적용됩니다.</p>
<div class="grid structure-tools"></div>
<div class="copy-fallback" hidden><label>비교용 복사 텍스트
<textarea class="copy-text" readonly></textarea></label>
<p>자동 복사가 안 되면 위 텍스트를 선택해 복사하세요.</p></div>
<h3>복사·붙여넣기로 구간 비교</h3>
<p>같은 내용의 구간을 각 도구에서 복사해 넣으세요. 자동 구간 대응은 하지 않습니다.
일반 텍스트에는 구조 정보가 없으며, Markdown은 명시된 출력 표기만 해석합니다.</p>
<div class="paste-grid"></div>
<div class="expectation">
<label>기대 분류 <select class="expected-kind"><option value="">미지정</option>
<option value="title">문서 제목</option><option value="heading">섹션 제목</option>
<option value="paragraph">일반 문단</option><option value="list">목록</option>
<option value="table">표</option><option value="page_header">페이지 머리글</option>
<option value="page_footer">페이지 바닥글</option></select></label>
<label>기대 수준 <input class="expected-level" type="number" min="1" step="1"></label>
<label>기대 직속 상위 제목 <input class="expected-parent" type="text"></label>
<label>검토 메모 <input class="review-note" type="text"></label>
<p>기대값은 단일 블록에만 판정합니다. 복수 블록은 내부 대응을 가정하지 않습니다.
상대 구간 없음은 자동으로 누락 오류를 의미하지 않습니다.</p>
</div>
<button type="button" class="add-comparison">비교 추가</button>
<button type="button" class="reset-draft">입력 초기화</button>
<p class="review-message" role="status" aria-live="polite"></p>
<h3>검토 구간 비교 목록</h3>
<p class="review-count"></p>
<div class="scroll"><table class="review-table"><thead><tr>
<th>DOCLING</th><th>TIKA</th><th>차이·정보 부족</th><th>기대 결과·메모</th><th>관리</th>
</tr></thead><tbody></tbody></table></div>
<button type="button" class="export-reviews">검토 JSON 내보내기</button>
<label>검토 JSON 불러오기 <input class="import-reviews" type="file" accept=".json"></label>
<p>파일로 내보내야 검토 내용이 보존됩니다. JSON에는 문서 내용이 포함됩니다.
불러오기는 기존 목록에 추가하며, 출처가 다르면 자동 재연결하지 않고 표시합니다.
수치는 검토한 구간에만 해당하며 문서 전체 정확도가 아닙니다.</p>
</div>"""


def review_script() -> str:
    return Path(__file__).with_name("comparison_review.js").read_text(encoding="utf-8")
