# 샘플 구간 기능별 비교 카드

> 이전 기능의 참고 문서다. 현재 보고서에서는 카드 영역·불러오기·내보내기를 제거했으며,
> `feature-cards.json` 자동 반영과 `--cards` 옵션도 지원하지 않는다.
> 아래 내용은 기존 카드 데이터의 규격과 이전 사용법을 보관한 것이다.

각 문서의 Markdown 추출 결과는 기존 순서대로 나란히 표시한다. 같은 구간의 대응은 사람이
확인하고, **샘플 구간 · 기능별 비교 카드**에 원본 발췌를 붙여넣어 기능 차이를 정리한다.
기존 기능 비교 표는 문서 전체 관찰값이며, 새 카드는 사람이 선정한 발췌 범위의 관찰값이다.
기존 블록 복사·수동 구조 검토 화면은 **기존 구조 검토 도구 펼치기** 안에 유지한다.

## 보고서에서 직접 만들기

1. 카드 제목과 유형을 지정한다. 필요하면 선정 이유와 원본 위치도 적는다.
2. DOCLING에 원본 JSON 항목·배열·문서 객체 또는 `{"items": [...]}`를 붙여넣는다.
   그룹 관계가 필요하면 관련 그룹과 자식 항목도 포함한다. Markdown·일반 텍스트도 선택 가능하다.
3. TIKA에 같은 구간의 Markdown 원문 또는 리소스 JSON 객체·배열을 붙여넣는다.
   `tk:content`와 `X-TIKA:content`를 지원한다. 자동 구간 대응은 하지 않는다.
4. 회차와 출처를 알고 있으면 입력한다. 회차 기본값은 미기록이며 임의로 첫 회차를 부여하지 않는다.
5. **비교 카드 생성**을 누른다. 분류·수준·관계·서식·표·위치 등의 관찰값과 후속 처리가 표시된다.
6. **카드 수정** 또는 **카드 삭제**로 목록을 관리한다.

JSON 속성은 원래 값을 유지하며 null·빈 배열·빈 객체·false를 구분한다. 참조 검사는 붙여넣은
항목 안에서 동일한 `self_ref`를 가진 대상이 유일하게 존재하는지만 확인한다. 발췌에 없는 참조를
파서 오류로 판정하지 않으며 제목·목록의 의미적 소속 관계를 자동 채점하지 않는다.

Markdown은 ATX·Setext 제목, 간단한 목록·굵게·파이프 표의 **표기 후보**만 탐지한다.
완전한 CommonMark 분석이나 원본 구조 복원이 아니다. 이미지 파일명 제목도 포함될 수 있다.
HTML과 일반 텍스트는 구조를 자동 판정하지 않고 원문으로 보존한다. Tika JSON의 리소스
메타데이터는 표시하지만 요소별 좌표를 자동 판정하지 않는다.

표시되는 긴 속성 값과 관찰 목록은 화면에서 생략될 수 있으며, **원본 증거 보기**와 내보낸
JSON에는 붙여넣은 원문이 그대로 남는다. 이미지 base64는 붙여넣지 말고 원본 참조를 기록한다.

## 에이전트 카드 JSON 규격

에이전트는 아래 스키마로 카드 데이터를 반환한다. JSON 안의 `content`는 객체가 아닌
**원본 발췌를 보존하는 문자열**이다. JSON 증거는 원본 객체를 JSON 문자열로 직렬화한다.
원문 공백·줄바꿈을 보존하려면 추출한 문자열을 그대로 넣는다.

```json
{
  "schema": "docling_poc.feature_cards",
  "version": 1,
  "cards": [
    {
      "id": "sample-heading-001",
      "document_id": "manifest.json의 documents[].id",
      "document_sha256": "해당 문서의 sha256",
      "title": "신청 자격 제목",
      "kind": "headings",
      "reason": "제목 수준과 후속 처리 방법 비교",
      "source_location": "원본 위치를 확인한 경우 기록",
      "original_checked": false,
      "note": "예시 데이터입니다. 실제 원본 증거로 교체하세요.",
      "docling": {
        "format": "json",
        "run": null,
        "source_file": "실제 회차의 raw.json.gz 경로",
        "source_refs": ["#/texts/0"],
        "content": "{\"label\":\"section_header\",\"level\":2,\"text\":\"신청 자격\"}"
      },
      "tika": {
        "format": "markdown",
        "run": null,
        "source_file": "실제 회차의 content.md 또는 tika-output.json 경로",
        "source_refs": ["리소스 배열 인덱스와 내용 필드의 발췌 위치"],
        "content": "## 신청 자격"
      }
    }
  ]
}
```

위 예시는 형식 설명용이다. 문서 ID·SHA-256·출처·내용은 실제 관찰값으로 교체해야 한다.

| 필드 | 규칙 |
|---|---|
| `id` | 보고서 전체에서 중복되지 않는 문자열 |
| `document_id`, `document_sha256` | 현재 보고서 manifest의 문서와 정확히 일치 |
| `title` | 비어 있지 않은 카드 제목 |
| `kind` | `headings`, `lists`, `formatting`, `tables`, `pictures`, `furniture`, `location`, `other` |
| `reason`, `source_location`, `note` | 문자열. 미기록이면 빈 문자열 |
| `original_checked` | `true`: 작성자가 원본 확인, `false`: 추출 결과 기반 후보, `null`: 미기록 |
| `docling`, `tika` | 각 도구의 증거 객체. 미입력이면 `null`; 적어도 한쪽 증거 필요 |
| 증거의 `format` | `json`, `markdown`, `text` |
| 증거의 `run` | manifest에 존재하는 양의 정수 회차. 불명확하면 `null` |
| 증거의 `source_file` | 출처 문자열. 이 경로를 열거나 외부로 요청하지 않음 |
| 증거의 `source_refs` | 원본 항목 참조·리소스 인덱스·문자 범위 등을 적은 문자열 배열 |
| 증거의 `content` | 비어 있지 않은 원문 문자열. 200만 자 이하 |

파일은 20 MB 이하, 전체 카드는 최대 200개다. 문서·해시·회차·필수 필드·JSON 형식이 맞지
않으면 전체 불러오기를 거부하며 기존 목록을 유지한다. 기존 카드와 ID가 중복되면 거부한다.

문서·해시·회차 일치는 발췌 내용의 원본 일치 검증이 아니다. 원문·참조·대응 구간은 자동으로
대조하지 않는다. 원본 확인 여부와 메모는 작성자·에이전트의 기록으로 표시한다.

## 저장과 재생성

- **카드 JSON 불러오기 (전체 문서)**: 하나의 파일에 여러 문서의 카드를 넣으면 해당 문서에 배치한다.
- **전체 카드 JSON 내보내기**: 현재 보고서의 모든 새 샘플 카드를 `feature-cards.json`으로 다운로드한다.
- **카드 포함 HTML 저장**: 입력한 카드를 포함하는 단일 HTML을 다운로드한다. 다시 열어도 카드가 표시된다.
  기존 구조 검토 도구의 검토 목록은 이 기능의 저장 대상이 아니므로 기존 검토 JSON으로 따로 내보낸다.

내보낸 `feature-cards.json`을 보고서 출력 폴더에 두면 보고서 재생성 시 자동으로 포함한다.
다른 위치의 파일은 `--cards`로 지정한다. 두 경우 모두 모델 추론을 다시 실행하지 않는다.

```bash
.venv/bin/python -m docling_poc.comparison_report reports/sample-comparison-macos-01 \
  --cards /path/to/feature-cards.json
```

새로고침 전에 JSON 또는 카드 포함 HTML을 저장해야 한다. 외부 서버나 CDN, LLM 호출은 없다.

## 검증

```bash
.venv/bin/python -m pytest tests/test_comparison_cards.py
node --test tests/test_comparison_cards.cjs tests/test_comparison_cards_controller.cjs
.venv/bin/python -m ruff check .
```
