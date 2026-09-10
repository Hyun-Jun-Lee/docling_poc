# Docling 팀 소개: 구조 데이터와 계층형 청킹

> 발표 범위: 추천 발표 순서 중 **2~6번**. 원본 문서와 PDF 화면을 나란히 보여주는 1번은 제외한다.

## 발표의 핵심 메시지

Docling은 비정형 문서를 곧바로 완벽한 답변 텍스트로 바꾸는 도구라기보다, **문서의 항목·읽기 순서·관계·원본 위치를 보존하는 변환 기반**이다. 이 기반 위에서 형식별 구조 보강, 청킹, 검색, 사람 검수를 설계할 수 있다.

### 도구 선택의 맥락: Docling과 Apache Tika

Docling과 Apache Tika는 경쟁하는 범용 파서이면서도 주력 문제가 다르다. **Tika는 매우 다양한 파일에서 본문·메타데이터를 안정적으로 수집·색인하는 도구**이고, **Docling은 복잡한 문서를 후속 AI 작업에 쓸 구조 데이터로 변환하는 도구**에 가깝다.

| 관점 | Docling | Apache Tika |
| --- | --- | --- |
| 주력 가치 | 문서 항목·관계·좌표를 보존한 구조화 변환 | 폭넓은 형식의 MIME 탐지, 본문·메타데이터 추출 |
| 복잡한 PDF | 레이아웃·읽기 순서·OCR·표 구조를 단계적으로 활용 | PDF 파서와 선택적 OCR로 텍스트·메타데이터·XHTML/Markdown 추출 |
| DOCX/PPTX | OOXML 구조를 `DoclingDocument`라는 통합 모델로 변환 | OOXML 파서가 XHTML/Markdown과 메타데이터로 추출 |
| Python 팀의 사용 방식 | Python SDK/CLI를 직접 사용 | Python에서 REST/gRPC 또는 래퍼로 호출할 수 있지만, 엔진은 Java 서비스로 운영 |
| 대량 처리의 강점 | 구조 품질이 필요한 문서군을 정밀 처리 | 범용 포맷 수집, 장애 격리, 대량 처리 파이프라인 |

따라서 “AI 모델을 쓰는 Docling이 항상 더 좋다”가 아니라, **복잡한 PDF의 구조 품질이 중요한가, 매우 많은 이종 문서를 빠르게 수집하는가**에 따라 기본 경로를 결정해야 한다. 이 발표는 그중 Docling이 제공하는 구조 데이터와 이를 활용하는 방법에 초점을 둔다.

발표 중에는 아래 순서를 유지한다.

2. `*.docling.json`에서 문서 항목과 관계, 좌표를 읽는다.
3. `*.hierarchical-chunks.json`에서 문맥을 붙인 청크와 원본 역추적을 확인한다.
4. PDF·DOCX·PPTX별로 변환 후 보완 전략이 왜 다른지 설명한다.
5. 필요한 모델의 역할과 선택적 보강을 구분한다.
6. OCR·다이어그램 한계와 운영 원칙을 공유한다.

---

## 2. `DoclingDocument`에서 읽을 수 있는 것

`*.docling.json`은 `DocumentConverter`가 만든 `DoclingDocument`의 JSON 내보내기다. `texts`, `tables`, `pictures`, `groups`, `pages`처럼 유형별 컬렉션에 실제 항목이 있고, 각 항목은 `self_ref`, `parent`, `children`, `content_layer`, `label`, `prov`를 통해 문서 안의 의미와 위치를 표현한다.

발표에서는 배열의 순번 자체보다 다음 네 가지를 먼저 보여준다.

| 볼 것 | 의미 | 후속 활용 |
| --- | --- | --- |
| `self_ref` | 항목의 안정적인 원본 식별자 | 파생 청크·구조화 결과의 근거 연결 |
| `body.children`, `parent`, `children` | 읽기 순서와 컨테이너 관계 | 본문 조립, 목록·인라인 묶음 해석 |
| `label`, `content_layer` | Docling이 판단하거나 원본 구조에서 읽은 역할 | 제목·목록·표·그림·반복 노이즈 정책 |
| `prov` | 페이지·bbox·문자 범위 | 원문 뷰어 이동, 하이라이트, 오류 영역 재검수 |

### 실제 DOCX 예시: 항목과 부모-자식 관계

현재 [`docx.docling.json`](../parsed/docx.docling.json)에는 다음과 같이 `inline` 그룹과 두 텍스트 항목이 있다.

```json
// #/groups/0
{
  "self_ref": "#/groups/0",
  "parent": {"$ref": "#/body"},
  "children": [{"$ref": "#/texts/11"}, {"$ref": "#/texts/12"}],
  "content_layer": "body",
  "label": "inline"
}

// #/texts/11
{
  "self_ref": "#/texts/11",
  "parent": {"$ref": "#/groups/0"},
  "label": "text",
  "text": "가. 모집대상 :",
  "formatting": {"bold": true}
}

// #/texts/12
{
  "self_ref": "#/texts/12",
  "parent": {"$ref": "#/groups/0"},
  "label": "text",
  "text": "문화콘텐츠산업 창업(예비)자 중 개인사업자"
}
```

여기서 **관계는 `#/groups/0`이 두 텍스트를 묶는다는 사실까지**다. `가. 모집대상`이 하위 제목이고 다음 항목이 그 본문이라는 해석은 가능하지만, 현재 JSON의 `label`은 둘 다 `text`다. 따라서 DOCX 후처리는 번호(`가.`), 굵기, 인접성 같은 신호를 근거로 구조 후보를 보강하되, 확신할 수 없는 관계를 확정 구조로 만들지 않아야 한다.

이 문서에서는 실제로 `1. 모집개요`도 `#/texts/9`, `label: "text"`로 저장되어 있다. 즉 Word의 작성 스타일·개요 수준이 일관되지 않으면 선언적 파일 형식이라도 풍부한 제목 레이블이 보장되지는 않는다.

### 실제 PDF 예시: 레이블과 본문/반복 요소

[`pdf.docling.json`](../parsed/pdf.docling.json)의 첫 제목은 PDF 레이아웃 분석 결과 `section_header`로 분류되어 있다.

```json
{
  "self_ref": "#/texts/0",
  "parent": {"$ref": "#/body"},
  "content_layer": "body",
  "label": "section_header",
  "text": "Apache Airflow를 활용한 데이터 파이프라인 자동화",
  "level": 1
}
```

반대로 같은 페이지의 `#/texts/1`은 `parent`가 `#/body`이지만 `content_layer`가 `furniture`, `label`이 `page_footer`다.

```json
{
  "self_ref": "#/texts/1",
  "content_layer": "furniture",
  "label": "page_footer",
  "text": "Data Engineering by 이현수 @hyunsoo.it"
}
```

이 차이는 검색 대상 선정에 중요하다. 본문은 기본적으로 `content_layer: "body"`에서 조립하고, 머리글·바닥글은 원본 참조를 보존한 채 별도 보관하거나 반복 노이즈 후보로 다룬다. 단, `label`은 항상 완전한 사실이 아니라 해당 변환 결과의 판단이므로, 서비스 규칙은 라벨의 존재 여부와 품질을 대표 문서로 검증해야 한다.

### 실제 PDF 예시: 좌표(`prov.bbox`)와 `BOTTOMLEFT`

PDF 제목 `#/texts/0`의 provenance는 다음과 같다.

```json
{
  "page_no": 1,
  "bbox": {
    "l": 283.31,
    "t": 527.02,
    "r": 1156.67,
    "b": 276.75,
    "coord_origin": "BOTTOMLEFT"
  },
  "charspan": [0, 33]
}
```

`coord_origin: "BOTTOMLEFT"`는 좌표 `(0, 0)`이 페이지의 **왼쪽 아래**라는 뜻이다. 따라서 `l`/`r`은 왼쪽·오른쪽 x 좌표이고, `b`/`t`는 아래·위 y 좌표다. 화면 좌표계처럼 왼쪽 위를 원점으로 쓰는 뷰어에 표시할 때는 페이지 높이를 사용해 y 축을 변환해야 한다.

좌표는 텍스트를 다시 구조화하는 일보다 다음에 특히 유용하다.

- 검색 결과를 원본 PDF의 정확한 페이지·영역으로 이동
- OCR 또는 레이아웃 오류가 난 영역만 사람에게 보여주고 재검수
- 그림·캡션·인접 텍스트의 공간적 관계를 보조 근거로 사용

DOCX 예시의 `#/texts/11`, `#/texts/12`는 `prov: []`다. 즉 모든 형식·항목에서 PDF 수준의 위치 정보가 있다고 가정하면 안 된다. 좌표는 **존재할 때 보존하고 활용하는 선택 신호**로 설계한다.

---

## 3. 계층형 청크: 문맥을 붙이고 원본으로 돌아가기

[`pdf.hierarchical-chunks.json`](../parsed/pdf.hierarchical-chunks.json)은 `HierarchicalChunker`의 결과다. 청크의 `text`는 검색·분류에 쓸 후보 본문이고, `meta.headings`는 그 텍스트가 속한 제목 문맥, `meta.doc_items`는 원본 `DoclingDocument`의 근거다.

### 실제 청크 예시: 본문과 문맥의 분리

```json
{
  "text": "Name         이현수",
  "meta": {
    "doc_items": [
      {
        "self_ref": "#/texts/8",
        "parent": {"cref": "#/groups/0"},
        "label": "text",
        "prov": [{"page_no": 2, "bbox": {"coord_origin": "BOTTOMLEFT"}}]
      }
    ],
    "headings": ["| 프로필"],
    "origin": {"filename": "pdf_test_sample.pdf"}
  }
}
```

이 예시에서 검색·분류할 핵심 본문은 `Name 이현수`이고, `| 프로필`은 **해석을 돕는 문맥**이다. 제목을 본문에 무조건 합쳐 원문을 중복 저장하기보다, 서비스 스키마에서 아래처럼 분리하는 편이 안전하다.

```text
body_refs      = [#/texts/8]          # 실제 본문 근거
context_refs   = [제목 항목의 self_ref] # 제목·캡션·표 헤더 등의 보조 문맥
section_path   = ["| 프로필"]
```

같은 파일에서 경력 목록 청크는 `#/texts/12`부터 `#/texts/16`까지 다섯 개 `list_item`을 하나의 청크에 담고, `meta.headings`에 `| 경력`을 보관한다. 이처럼 계층형 청커는 원문 항목을 버리지 않고 문맥을 함께 제공한다.

### 원본 역추적 흐름

발표에서는 다음 한 줄을 보여주면 된다.

```text
검색/구조화 결과
  → 청크 meta.doc_items[].self_ref  (#/texts/8)
  → pdf.docling.json의 원본 항목
  → prov.page_no + prov.bbox
  → 원본 PDF 2페이지의 해당 영역 하이라이트
```

`self_ref`가 있으면 파생 결과가 원본 문장을 임의로 바꾸거나 합친 뒤에도 근거를 남길 수 있다. `prov`가 있으면 원본 파일의 페이지와 영역까지 되돌아갈 수 있다. 따라서 청킹·도메인 매핑·LLM 보강 결과에는 항상 최소한 `source_refs` 또는 `body_refs`를 보관해야 한다.

주의할 점은 `HierarchicalChunker`의 결과가 최종 검색 단위를 자동으로 확정해 주지는 않는다는 것이다. 업무 도메인 단위로 추가 분할·병합하더라도 제목은 `context`로, 실제 문장은 `body`로, 근거는 `self_ref`로 분리해 보존한다.

---

## 4. 형식별 처리 방식: 구조 추론과 파서 추출

세 형식 모두 변환 후에는 하나의 `DoclingDocument`로 만난다. 따라서 원본 보존, 읽기 순서, source reference, chunk 출력 계약은 공통으로 가져갈 수 있다. 차이는 그 공통 파이프라인에 들어오는 **구조 신호의 밀도와 신뢰 근거**다.

### Docling과 Tika의 형식별 처리 차이

| 형식 | Docling | Apache Tika | 선택·보완의 초점 |
| --- | --- | --- | --- |
| PDF | 페이지의 레이아웃·읽기 순서·OCR·표 구조를 결합해 `section_header`, `list_item`, `page_header/footer`, bbox 등을 추론 | PDF 파서가 본문·메타데이터와 가능한 XHTML/Markdown 구조를 추출한다. 시각적 레이아웃 레이블 추론은 주력 기능이 아니다 | 스캔·다단·표·반복 헤더가 중요하면 Docling을 우선 검증한다. 단순 텍스트 PDF는 Tika의 처리량도 함께 비교한다 |
| DOCX | OOXML의 스타일·개요 수준·번호 매기기·표·인라인 객체를 통합 문서 모델로 변환 | OOXML 파서가 문서 본문·표·링크·메타데이터를 추출 | 원본 스타일이 일관적이면 품질 격차보다 결과 스키마와 운영성이 중요하다 |
| PPTX | 제목 자리표시자, 텍스트 도형, 글머리표/번호, 슬라이드·그룹 구조를 통합 모델로 표현 | 슬라이드 순서와 OOXML 내부 텍스트·메타데이터를 추출 | 자유 배치 텍스트·도형·다이어그램은 두 도구 모두 대표 파일로 검증한다 |

PDF에서 Docling의 차별점은 텍스트 추출 자체보다, 원본이 구조를 명시하지 않은 경우에도 시각적 배치에서 항목의 역할과 읽기 순서를 추론한다는 점이다. 반면 Tika의 구조는 파서가 원본 포맷에서 읽어 낼 수 있는 논리 구조를 보존하는 성격이 강하다. 따라서 Tika도 제목·목록·표를 출력할 수 있지만, 일반적인 PDF에서 `page_header`나 `list_item` 같은 시각적 레이블을 보장하는 도구로 보면 안 된다.

DOCX와 PPTX는 원본 OOXML에 문단·스타일·목록·표·슬라이드 등의 논리 정보가 이미 기록되어 있다. 이 때문에 PDF에서 보이는 Docling의 레이아웃 추론 우위가 그대로 적용되지는 않는다. Docling의 Office 문서 장점은 PDF 결과와 동일한 `DoclingDocument`/JSON 계약으로 후속 청킹·검색 코드를 통일할 수 있다는 데 있고, Tika의 장점은 폭넓은 형식 지원과 대량 추출 경로에 있다.

### 현재 Docling 결과에서 보는 형식별 보완

따라서 가장 정확한 개념은 **“PDF·DOCX·PPTX는 `DoclingDocument` 변환 이후 보완의 컨셉이 다르다”**이다.

- PDF는 Docling이 추론한 레이블을 비교적 공통된 출발점으로 사용할 수 있으므로, 기본 정책 수를 줄일 여지가 있다. 하지만 라벨·OCR이 완벽하다는 전제는 두지 않는다.
- DOCX는 원본의 선언적 구조를 활용할 수 있지만, 작성자가 스타일·개요·번호 설정을 어떻게 했는지에 따라 결과가 크게 달라진다. 현재 샘플처럼 `text`가 대부분이면 문서군별 보강 정책이 필요하다.
- PPTX는 DOCX처럼 원본의 선언적 신호를 읽는 면이 강하지만, 슬라이드 텍스트 상자와 시각적 배치의 영향도 크다. 따라서 “PDF와 동일” 또는 “DOCX와 동일”로 단순 분류하기보다, PPTX 전용 대표 샘플로 자리표시자·목록·그룹 품질을 확인한다.

공통 설계는 `body.children`의 읽기 순서와 `self_ref`를 기준으로 한 번만 순회하고, 형식별 차이는 작은 `StructurePolicy`로 격리하는 방식이 적절하다. 현재 [`semantic.py`](../src/docling_poc/semantic.py)는 한국 공고문 DOCX의 `1.`, `가.`, `(1)` 패턴을 보강하는 기준선이다. PDF에는 같은 정규식 정책을 먼저 적용하기보다 `section_header`, `list_item`, `table`, `picture` 같은 네이티브 신호를 우선 소비하고, 신호가 누락된 사례에만 제한적으로 보강 규칙을 더하는 편이 낫다.

---

## 5. 필요한 모델과 선택적 보강

PDF 변환은 단일 모델 하나의 결과가 아니다. 레이아웃, OCR, 표 구조, 그림 이해는 서로 다른 단계이며, 기능을 실제로 쓸 때만 해당 모델을 확보한다.

| 처리 단계 | 필요한 이유 | 모델/구성 예 | 우선순위 |
| --- | --- | --- | --- |
| 레이아웃 분석 | 페이지에서 제목·문단·목록·표·그림 영역을 찾고 라벨·bbox를 만든다 | `docling-project/docling-layout-heron` | PDF 표준 파이프라인의 핵심 |
| 표 구조 인식 | 표를 단순 텍스트가 아니라 행·열·셀 관계로 만든다 | `docling-project/docling-models`의 TableFormer 자산 | 표를 구조화·검색해야 하면 필요 |
| OCR | 스캔 PDF·이미지 기반 텍스트를 읽는다 | 현재 프로젝트는 한국어 RapidOCR + ONNX Runtime 사용 | 스캔/이미지 문서 비중에 따라 필요 |
| 그림 유형 분류 | 그림·차트·다이어그램을 구분해 후속 처리 대상을 선별한다 | `docling-project/DocumentFigureClassifier-v2.5` | 선택 사항; VLM 호출 비용을 줄이고 싶을 때 |
| 그림 설명 생성 | 다이어그램·도형 중심 그림을 자연어 설명으로 보강한다 | `HuggingFaceTB/SmolVLM-256M-Instruct` 등 VLM | 선택 사항; OCR의 대체물이 아니라 그림 이해 보강 |

운영 원칙은 **기본 변환에 필요한 모델과 선택적 품질 보강 모델을 분리**하는 것이다. 특히 그림 분류와 그림 설명은 모든 그림에 일괄 적용하지 말고, 분류 결과·문서 중요도·사람 검수 필요성에 따라 대상만 선택한다. VLM이 만든 설명은 원문 OCR 결과를 덮어쓰지 않고 `generated_description`, 사용 모델, 생성 시각, `source_ref`를 별도 필드로 저장한다.

모델별 엔드포인트 제공 여부와 플러그인 연결 방식은 발표의 핵심이라기보다 배포 설계 항목이다. 문서 처리 기능이 어떤 입력·출력을 요구하는지 먼저 확정하고, 사내 제공 방식이 로컬 파일인지 KServe V2/OpenAI-compatible API인지에 따라 Docling 기본 경로 또는 커스텀 플러그인으로 연결한다.

---

## 6. 품질 한계와 운영 원칙

### 대량 문서 처리: 단일 도구 선택보다 라우팅 정책

문서량이 매우 많은 환경에서는 모든 문서를 동일한 고비용 파이프라인으로 처리하기보다, 문서군별로 경로를 나누는 선택지도 검토한다.

```text
입력 문서
  → 형식·스캔 여부·페이지 수·표/다단 여부를 기록
  → 일반 문서·대량 수집 후보: Tika 기반 빠른 추출을 비교
  → 복잡 PDF·스캔·표 중심 후보: Docling 정밀 변환을 비교
  → 형식별 품질, 문서당 시간, 실패율, 비용을 함께 기록
```

- **대량의 이종 문서 수집과 색인**이 핵심이면 Tika의 범용 포맷 지원과 대량 처리 경로를 우선 평가한다.
- **복잡한 PDF를 신뢰 가능한 구조 데이터로 변환**해야 하면 Docling을 기본 또는 선택 경로로 평가한다.
- 최종 선택은 단일 도구의 절대 우위가 아니라, 대표 문서군에서 측정한 품질·처리 시간·리소스 비용·재시도율로 결정한다.

### 실제 PDF 그림 예시: `#/pictures/6`

[`pdf.docling.json`](../parsed/pdf.docling.json)의 `#/pictures/6`은 6페이지의 그림 영역이다.

```json
{
  "self_ref": "#/pictures/6",
  "label": "picture",
  "children": ["#/texts/61", "...", "#/texts/125"],
  "prov": [{
    "page_no": 6,
    "bbox": {
      "l": 190.10, "t": 382.82,
      "r": 1213.32, "b": 93.99,
      "coord_origin": "BOTTOMLEFT"
    }
  }]
}
```

이 그림의 자식 텍스트에는 `Business group 1`, `DATALAKE`, `ETL`, `DATA WAREHOUSE`, `DATAMART`처럼 의미 있는 단어도 있지만, `.` , `0101`, `후후` 같은 오인식도 섞여 있다. 도형·점선·연결선·작은 글자가 함께 있는 다이어그램에서 OCR이 선을 문자로 오인하거나 텍스트를 잘못 읽는 전형적인 사례다.

해결 목표는 잘못 읽은 OCR 문자열을 억지로 정답처럼 고치는 것이 아니라, **그림을 올바른 처리 경로로 보내고 오류 근거를 보존하는 것**이다.

| 그림 유형 | 기본 처리 | 추가 조치 |
| --- | --- | --- |
| 사진·단순 스크린샷 | OCR 텍스트와 원본 그림 참조 보존 | 필요 시 사람 검수 |
| 표·차트 | 표 구조 인식 또는 차트별 처리 우선 | 셀/축/범례 품질 확인 |
| 도형·점선·흐름 다이어그램 | OCR을 정답 텍스트로 사용하지 않음 | 선택적으로 VLM 설명 생성, `generated_description`으로 별도 저장 |
| 품질이 낮거나 업무상 중요한 그림 | 자동 결과와 근거를 함께 보관 | 원본 페이지·bbox 기반 사람 검수 또는 재처리 |

### 권장 저장 및 품질 정책

1. **원본 JSON은 불변 snapshot으로 보관한다.** OCR·VLM·규칙 기반 결과를 원본 `text`에 덮어쓰지 않는다.
2. **모든 파생 블록에 `source_refs`를 남긴다.** 최소한 `#/pictures/6`, `#/texts/8` 같은 `self_ref`를 보존한다.
3. **본문 추출 오류와 구조 불확실성을 구분한다.** 제목 관계를 확신할 수 없는 경우는 `candidate`/`unresolved`, OCR이 망가진 경우는 별도의 품질 상태로 기록한다.
4. **VLM 설명은 선택적 보강이다.** 그림의 원문·OCR·생성 설명·모델 정보를 분리해 저장하고, 생성 설명만으로 사실을 확정하지 않는다.
5. **대표 문서군으로 정책을 검증한다.** PDF는 본문 누락·라벨·OCR·읽기 순서·표 행/열을, DOCX는 스타일·번호 체계·표를, PPTX는 슬라이드 경계·자리표시자·텍스트 상자·슬라이드 그룹을 각자 측정한다.
6. **품질만 분리해서 보지 않는다.** 형식별로 문서당 처리 시간, 메모리 또는 가속기 비용, 실패·재시도율, 원본 `self_ref`와 `prov`를 통한 역추적 가능성도 함께 기록한다.

---

## 마무리 문장

> Docling의 가치는 단순 텍스트 추출이 아니라, 문서 항목과 위치·관계를 보존해 후속 구조화와 검수를 가능하게 하는 데 있다. 공통 파이프라인은 원본 참조와 읽기 순서를 지키고, 형식별 차이는 관찰된 구조 신호에 맞춰 작게 보강한다. 대량의 이종 문서를 빠르게 수집해야 한다면 Tika가 유리할 수 있고, 복잡한 PDF를 구조 데이터로 바꿔야 한다면 Docling이 강하다.

## 발표 중 함께 열어볼 참고 자료

- [공식 가이드 번역: DoclingDocument, 레이블, 문서 구조와 provenance](docling_official_guides_ko.md#3-doclingdocument-통합-문서-모델)
- [공식 가이드 번역: PDF 파이프라인 모델 카탈로그](docling_official_guides_ko.md#4-모델-카탈로그-pdf-파이프라인을-이루는-모델들)
- [공식 가이드 번역: 청킹](docling_official_guides_ko.md#9-청킹)
- [Apache Tika 공식 문서: 통합 방식과 대량 처리](https://tika.apache.org/docs/4.0.x/using-tika/)
- [Apache Tika 공식 문서: OOXML 파서](https://tika.apache.org/4.0.0/api/org/apache/tika/parser/microsoft/ooxml/OOXMLParser.html)
- [구조 인지형 Chunk Sequence 아키텍처](semantic_chunking_architecture_ko.md)
- [PDF 원본 변환 결과](../parsed/pdf.docling.json), [PDF 계층형 청크](../parsed/pdf.hierarchical-chunks.json), [DOCX 원본 변환 결과](../parsed/docx.docling.json), [PPTX 원본 변환 결과](../parsed/pptx.docling.json)
