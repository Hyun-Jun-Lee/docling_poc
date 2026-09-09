# Docling Technical Report 분석 및 비정형 문서 Chunking 설계 적용

> 대상 논문: Docling Technical Report — Auer et al., 2024  
> https://arxiv.org/abs/2408.09869

## 1. 분석 목적

현재 개발 중인 AI-Ready Data 파이프라인은 PDF, PPTX, DOCX 등의 비정형 문서를 Docling으로 파싱한 뒤 아래 흐름으로 처리한다.

~~~text
Document
  ↓
Docling Parsing
  ↓
Normalized Document Elements
  ↓
Chunking
  ↓
Domain Mapping
  ↓
Boundary Resolution
  ↓
Domain-aware Unit
  ↓
Context / Embedding
~~~

여기서 Chunk는 최종 검색 단위가 아니다. Chunk의 주요 목적은 후속 단계에서 각 구간의 업무 Domain을 안정적으로 판정하기 위한 작은 연속 처리 단위를 제공하는 것이다.

이 문서는 다음을 분석한다.

1. Docling이 어떤 문서 구조 정보를 제공하는가?
2. 해당 정보를 Chunking에서 어떻게 활용할 수 있는가?
3. Docling 결과를 바로 text로 flatten하지 않아야 하는 이유는 무엇인가?
4. 다양한 문서 유형에 대응할 수 있는 Chunking Architecture를 어떻게 구성하는 것이 좋은가?

---

## 2. Docling의 역할: Text Extraction이 아니라 Document Reconstruction

Docling을 단순히 다음처럼 이해하면 활용 범위가 크게 줄어든다.

~~~text
PDF → Docling → Text
~~~

Docling Technical Report에서 설명하는 Docling의 역할은 이에 더 가깝다.

~~~text
PDF
 ↓
PDF Backend
 ↓
Text Token + Coordinate / Page Image
 ↓
Layout Analysis / Table Structure Recognition / OCR
 ↓
Document Assembly
 ↓
Reading Order / Caption-Figure Relation / Metadata
 ↓
Structured Document
~~~

즉 Docling은 문자열을 추출하는 것이 아니라 문서를 구성하는 요소들의 구조를 복원한다. 대표적으로 다음 정보가 중요하다.

- Heading / Section Title
- Paragraph
- List Item
- Table
- Picture / Figure
- Caption
- Page
- Bounding Box
- Reading Order
- Relations
- Table Structure

따라서 Docling의 결과를 바로 Markdown이나 plain text로 변환한 뒤 Chunking하는 것은 권장하지 않는다. Docling이 복원한 구조 정보를 상당 부분 잃어버릴 수 있기 때문이다.

### 잘못된 접근

~~~text
Document → Docling → Markdown / Text → Token Chunking
~~~

### 권장 접근

~~~text
Document → Docling → Structured Document
         → Normalized Elements
         → Structure-aware Chunking
~~~

---

## 3. Layout Detection 결과를 Chunking의 신호로 활용한다는 의미

여기서 중요한 오해가 하나 있다.

> "SECTION_HEADER"가 나오면 SECTION_HEADER 단위로 Chunk를 만든다는 뜻인가?

그렇지 않다. Layout Detection 결과는 Chunk 자체를 정의하는 절대적인 기준이라기보다 Chunk boundary를 판단하는 신호로 활용하는 것이 적절하다.

예를 들어 Docling 결과가 다음과 같다고 가정한다.

~~~text
[SECTION_HEADER]
3. 예방정비

[PARAGRAPH]
CMP 설비는 매월 정기점검을 실시한다.

[PARAGRAPH]
점검 결과 이상이 발견되면 담당자 승인을 받아 조치한다.

[SECTION_HEADER]
4. 장애 대응

[PARAGRAPH]
알람 발생 시 장애 이력을 확인한다.
~~~

단순 token chunking을 사용하면 다음처럼 Section 경계와 문장 경계가 모두 훼손될 수 있다.

~~~text
Chunk 1
3. 예방정비
CMP 설비는 매월 정기점검을 실시한다.
점검 결과 이상이 발견되면

Chunk 2
담당자 승인을 받아 조치한다.
4. 장애 대응
알람 발생 시 장애 이력을 확인한다.
~~~

Layout 정보를 활용하면 다음처럼 판단할 수 있다.

~~~text
SECTION_HEADER → 강한 Boundary Signal
PARAGRAPH      → 기본적인 결합 후보
TABLE          → 별도 처리 후보
LIST           → List 구조 보존 후보
~~~

그러면 다음과 같은 Chunk 생성이 가능하다.

~~~text
Chunk 1
heading_path:
  - 3. 예방정비
text:
  CMP 설비는 매월 정기점검을 실시한다.
  점검 결과 이상이 발견되면 담당자 승인을 받아 조치한다.

Chunk 2
heading_path:
  - 4. 장애 대응
text:
  알람 발생 시 장애 이력을 확인한다.
~~~

핵심은 다음과 같다.

> "SECTION_HEADER = Chunk"가 아니라  
> "SECTION_HEADER = Chunk 경계 가능성이 높다는 신호"

다만 다양한 기업 문서를 처리해야 하기 때문에 이것조차 절대적인 규칙으로 만들 필요는 없다. Heading이 잘못 탐지되거나 형식적으로만 사용되는 문서도 있을 수 있기 때문이다. 따라서 구조 정보는 hard rule보다는 strong signal에 가깝게 사용하는 것이 안전하다.

---

## 4. Heading을 독립 Chunk로 만들지 않는 이유

다음 구조를 생각해보자.

~~~text
E01 SECTION_HEADER
"3. 예방정비"

E02 PARAGRAPH
"CMP 설비의 필터를 매월 점검한다."

E03 PARAGRAPH
"교체 기준은 압력 0.8 이하이다."
~~~

이를 아래처럼 분리하면 Heading만으로는 Domain을 판정할 정보가 충분하지 않을 수 있다.

~~~text
C01: 3. 예방정비
C02: CMP 설비의 필터를 매월 점검한다.
C03: 교체 기준은 압력 0.8 이하이다.
~~~

따라서 Heading을 독립 Content Chunk로 만들기보다는 후속 Element의 Context로 전달하는 것이 더 유용하다.

~~~text
Chunk
heading_path:
  - 설비 관리
  - 예방정비
text:
  CMP 설비의 필터를 매월 점검한다.
~~~

Domain Mapping 입력 역시 다음처럼 만들 수 있다.

~~~text
[Section]
설비 관리 > 예방정비

[Content]
CMP 설비의 필터를 매월 점검한다.
~~~

즉 Heading은 Content라기보다 Structural Context로 활용할 수 있다.

---

## 5. Table은 Paragraph와 동일하게 처리해서는 안 된다

Docling의 중요한 특징 중 하나가 Table Structure Recognition이다. 표를 단순 문자열이 아니라 논리적인 구조로 복원할 수 있다.

원본 표:

~~~text
설비   | 점검항목 | 기준
CMP01 | 압력     | 0.8
CMP02 | 온도     | 70℃
~~~

이를 다음처럼 flatten하면:

~~~text
CMP01
압력
0.8
CMP02
온도
70℃
~~~

Row와 Column 관계를 잃는다.

따라서 중간 Representation에서는 가능한 경우 다음과 같은 구조를 유지하는 것이 좋다.

~~~text
TableElement
 ├─ headers
 ├─ rows
 ├─ cells
 ├─ spans
 ├─ caption
 ├─ page
 └─ bbox
~~~

Table은 일반 Paragraph와 다른 Chunking Policy가 필요할 수 있다.

~~~text
Paragraph → 주변 Paragraph와 merge 가능
Table     → 가능한 한 구조 유지, 필요할 경우 row group 단위 split
List      → item 관계 유지
Figure    → Caption과 relation 유지
~~~

---

## 6. Chunking Policy

Chunking Policy는 거창한 알고리즘이 아니라, Element 유형 또는 상황별로 Chunk를 어떻게 생성할 것인지 규칙을 분리하는 것이다.

Paragraph 처리 규칙 예시는 다음과 같다.

~~~python
class ParagraphChunkPolicy:
    def can_handle(self, element):
        return element.type == "paragraph"

    def apply(self, element, context):
        return ChunkCandidate(
            text=element.text,
            element_type="paragraph",
            source_element_ids=[element.id],
            heading_path=context.heading_path,
        )
~~~

Table은 다른 처리 방법이 필요하다.

~~~python
class TableChunkPolicy:
    def can_handle(self, element):
        return element.type == "table"

    def apply(self, element, context):
        return ChunkCandidate(
            text=self.serialize(element),
            element_type="table",
            source_element_ids=[element.id],
            heading_path=context.heading_path,
            splittable=False,
        )

    def serialize(self, table):
        return "\n".join(
            " | ".join(cell.text for cell in row.cells)
            for row in table.rows
        )
~~~

List도 별도 규칙을 가질 수 있다.

~~~python
class ListChunkPolicy:
    def can_handle(self, element):
        return element.type == "list"

    def apply(self, element, context):
        text = "\n".join(f"- {item.text}" for item in element.items)
        return ChunkCandidate(
            text=text,
            element_type="list",
            source_element_ids=[element.id],
            heading_path=context.heading_path,
        )
~~~

Chunker는 Element 유형을 직접 판단하지 않고 등록된 Policy에 위임한다.

~~~python
class Chunker:
    def __init__(self, policies):
        self.policies = policies

    def chunk(self, elements):
        candidates = []
        context = ChunkContext()

        for element in elements:
            context.update(element)
            for policy in self.policies:
                if policy.can_handle(element):
                    candidates.append(policy.apply(element, context))
                    break

        return candidates

chunker = Chunker([
    ParagraphChunkPolicy(),
    TableChunkPolicy(),
    ListChunkPolicy(),
])
~~~

이 구조의 장점은 새로운 문서 케이스가 들어왔을 때 기존 코드를 크게 수정하지 않아도 된다는 점이다. 예를 들어 Callout Box가 중요해지면 CalloutChunkPolicy를 추가하면 된다.

목표는 다음과 같다.

> 새로운 문서 케이스가 생겨도 기존 Chunker를 뜯지 않고 작은 Policy를 추가할 수 있는 구조

---

## 7. Element → Chunk를 바로 만들지 않는 이유

Element Policy가 바로 Final Chunk를 만들도록 할 수도 있지만, 실제 구현에서는 한 단계를 더 두는 것이 유연하다.

~~~text
Normalized Element
       ↓
Element Policy
       ↓
Chunk Candidate
       ↓
Merge / Split Policy
       ↓
Final Chunk
~~~

예를 들어 다음 Docling 결과가 있다고 하자.

~~~text
E01 SECTION_HEADER "3. 예방정비"
E02 PARAGRAPH "CMP 설비는 매월 점검한다."
E03 PARAGRAPH "주요 점검 항목은 다음과 같다."
E04 TABLE ...
E05 PARAGRAPH "이상이 발견되면 즉시 조치한다."
~~~

Element별 Policy는 다음과 같은 Candidate를 만든다.

~~~python
@dataclass
class ChunkCandidate:
    text: str
    element_type: str
    source_element_ids: list[str]
    heading_path: list[str]
    page_no: int
    splittable: bool = True
~~~

예시 결과:

~~~python
[
    ChunkCandidate(
        text="CMP 설비는 매월 점검한다.",
        element_type="paragraph",
        source_element_ids=["E02"],
        heading_path=["3. 예방정비"],
    ),
    ChunkCandidate(
        text="주요 점검 항목은 다음과 같다.",
        element_type="paragraph",
        source_element_ids=["E03"],
        heading_path=["3. 예방정비"],
    ),
    ChunkCandidate(
        text="점검항목 | 주기 | 기준\n압력 | 매월 | 0.8 이상\n온도 | 매월 | 70도 이하",
        element_type="table",
        source_element_ids=["E04"],
        heading_path=["3. 예방정비"],
        splittable=False,
    ),
]
~~~

이후 Merge/Split 단계에서 Final Chunk를 만든다.

~~~python
class MergePolicy:
    def should_merge(self, left, right):
        if left.heading_path != right.heading_path:
            return False
        if left.element_type == "table":
            return False
        if right.element_type == "table":
            return False
        return True
~~~

그 결과 같은 heading 아래의 Paragraph들은 결합하고, Table은 독립 Candidate로 유지할 수 있다. 이렇게 하면 Element 처리와 Chunk 크기 결정 책임을 분리할 수 있다.

---

## 8. Token Size는 Chunking 기준이 아니라 Guardrail

Chunking을 500 Token 단위처럼 토큰 수 기준으로만 수행하면 문서 구조가 쉽게 깨질 수 있다.

따라서 우선순위는 다음과 같이 두는 편이 적절하다.

~~~text
1. Docling Structural Boundary
        ↓
2. Paragraph / Sentence Boundary
        ↓
3. Token Limit
~~~

즉 Token 제한은 "어디서 의미적으로 자를 것인가?"를 결정하는 주된 기준이라기보다, "Chunk가 너무 커지는 것을 어떻게 방지할 것인가?"를 담당하는 Safety Boundary / Guardrail에 가깝다.

예를 들어 Paragraph 하나가 3,000 token이라면 그때 Sentence 또는 Token 기준으로 fallback split을 한다.

---

## 9. 구조와 Provenance를 보존한 Intermediate Representation

Docling의 결과를 바로 Chunk로 변환하기보다 시스템에서 사용하는 공통 중간 Representation으로 한번 Normalization하는 것을 권장한다.

예를 들어 원본 PDF 12페이지:

~~~text
3. 예방정비

CMP 설비는 매월 정기점검을 실시한다.

[표 3]
점검항목 | 점검주기 | 기준값
압력     | 매월     | 0.8
온도     | 매월     | 70℃
~~~

Docling은 개념적으로 다음처럼 구조화할 수 있다.

~~~python
[
    {
        "id": "E101",
        "type": "section_header",
        "text": "3. 예방정비",
        "page": 12,
        "bbox": [100, 100, 500, 140],
    },
    {
        "id": "E102",
        "type": "paragraph",
        "text": "CMP 설비는 매월 정기점검을 실시한다.",
        "page": 12,
        "bbox": [100, 160, 700, 210],
    },
    {
        "id": "E103",
        "type": "table",
        "page": 12,
        "bbox": [100, 250, 700, 500],
        "rows": [...],
    },
]
~~~

그러나 downstream 서비스 전체가 Docling의 내부 객체를 직접 참조하면 Docling과 시스템 사이의 결합도가 높아진다. 따라서 시스템 내부용 모델로 변환한다.

~~~python
@dataclass
class NormalizedElement:
    id: str
    type: str
    text: str | None
    page_no: int | None
    bbox: tuple | None
    reading_order: int | None
    heading_path: list[str]
    parent_id: str | None
    table_structure: dict | None
    related_element_ids: list[str]
    source_ref: dict
~~~

실제 Element는 다음처럼 표현할 수 있다.

~~~python
NormalizedElement(
    id="E102",
    type="paragraph",
    text="CMP 설비는 매월 정기점검을 실시한다.",
    page_no=12,
    bbox=(100, 160, 700, 210),
    reading_order=15,
    heading_path=["설비관리", "3. 예방정비"],
    table_structure=None,
    source_ref={"docling_element_id": "..."},
)
~~~

이것이 Intermediate Representation, 즉 중간 Representation이다.

---

## 10. "구조를 보존한다"는 의미

Text만 남기면 다음 정보만 남는다.

~~~text
CMP 설비는 매월 정기점검을 실시한다.
~~~

반면 구조를 보존하면 다음 정보를 같이 가지고 있다.

~~~text
element_type = paragraph

heading_path
 └ 설비 관리
    └ 예방정비

page = 12
reading_order = 15
previous_element = section_header
next_element = table
~~~

이 정보가 있기 때문에 Chunker는 다음과 같은 판단을 할 수 있다.

~~~python
if element.heading_path != previous.heading_path:
    split()

if next_element.type == "table":
    # 현재 paragraph가 table introduction인지 판단
~~~

Text로 flatten하고 나면 이런 구조 기반 판단은 대부분 불가능하다.

---

## 11. Provenance

Provenance는 간단하게 말하면 다음과 같다.

> 이 데이터가 원본 문서의 어디에서 왔는지 추적할 수 있는 정보

예를 들어 최종 Chunk가 다음과 같다고 하자.

~~~text
C023

CMP 설비는 매월 정기점검을 실시한다.
주요 점검 항목은 다음과 같다.
~~~

다음과 같이 Source 정보를 유지할 수 있다.

~~~python
Chunk(
    id="C023",
    text="CMP 설비는 매월 정기점검을 실시한다.\n주요 점검 항목은 다음과 같다.",
    source_element_ids=["E102", "E103"],
    page_range=(12, 12),
    bbox_refs=[
        (100, 160, 700, 210),
        (100, 220, 700, 245),
    ],
)
~~~

그러면 다음과 같은 역추적이 가능하다.

~~~text
Unit
 ↓
Chunk
 ↓
Normalized Element
 ↓
Docling Element
 ↓
Original PDF
 ↓
Page 12 / Bounding Box
~~~

이 정보는 다음 영역에서 중요하다.

- Debugging
- HITL
- Golden Dataset
- Parsing Quality Evaluation
- Chunk Quality Evaluation
- Search Result Highlighting
- Audit / Explainability
- Reprocessing

예를 들어 Domain Mapping 결과가 틀렸다면 Chunk C023 → D03에서 끝나는 것이 아니라, E102/E103 및 PDF Page 12의 Original Bounding Box까지 확인할 수 있다.

---

## 12. Downstream 목적에 따라 Chunk Policy를 적용한다는 의미

동일한 문서라도 최종 목적에 따라 적절한 Chunk 크기가 다를 수 있다.

~~~text
Heading:
3. 예방정비

Paragraph:
CMP 설비는 매월 정기점검을 실시한다.

Paragraph:
점검 항목은 압력, 온도, 진동이다.

Table:
점검항목 | 기준값
...
~~~

일반적인 RAG가 목적이라면 의미 Context를 최대한 유지하기 위해 큰 단위로 묶을 수도 있다.

~~~text
Chunk01
3. 예방정비

CMP 설비는 매월 정기점검을 실시한다.
점검 항목은 압력, 온도, 진동이다.

점검항목 | 기준값
...
~~~

반면 현재 AI-Ready Data 프로젝트에서는 Chunk가 최종 Retrieval 단위가 아니다. 목적은 다음과 같다.

~~~text
Chunk → Domain Classification
~~~

따라서 조금 더 작은 단위가 유리할 수 있다.

~~~text
C01: CMP 설비는 매월 정기점검을 실시한다.
C02: 점검 항목은 압력, 온도, 진동이다.
C03: [Table] 점검항목 | 기준값 ...
~~~

Domain Mapping 결과가 다음과 같다면:

~~~text
C01 → D03
C02 → D03
C03 → D03
~~~

실제 의미 구간은 이후 단계에서 다시 합친다.

~~~text
C01 + C02 + C03 → Unit01 / D03
~~~

따라서 현재 프로젝트의 Chunking 목적은 일반적인 Semantic Chunking과 조금 다르다.

~~~text
일반 RAG
Document → Semantic Chunk → Embedding → Retrieval

현재 프로젝트
Document → Stable Chunk Sequence → Domain Mapping
         → Boundary Resolution → Domain-aware Unit
         → Context → Embedding
~~~

따라서 현재 Chunk를 설명하는 표현으로는 다음이 더 적절하다.

> Stable Evidence Segmentation for Domain Classification

즉 완벽한 Semantic Unit을 만드는 것이 아니라 Domain 판정에 충분하고 안정적인 evidence 단위를 만드는 것이다.

---

## 13. Reading Order를 절대적인 정답으로 보면 안 된다

Docling은 문서의 Reading Order를 복원한다. 하지만 복잡한 multi-column layout, table 삽입, page break 등의 경우 항상 의미적으로 완벽한 순서를 보장한다고 생각해서는 안 된다.

~~~text
Docling Reading Order
       ≠
Guaranteed Semantic Order
~~~

Docling 결과 뒤에 Normalization 계층을 두는 또 하나의 이유다.

향후 필요한 경우 다음과 같은 Policy를 추가할 수 있다.

- RepeatedHeaderFooterNormalizer
- BrokenParagraphMerger
- ReadingOrderValidator
- CaptionRelationNormalizer
- TableNormalizer

중요한 점은 처음부터 모든 예외를 구현하는 것이 아니다. 실제 Golden Dataset에서 반복적으로 발견되는 오류를 Policy로 추가하는 방식이 적절하다.

---

## 14. OCR도 별도의 품질 판단 대상으로 본다

Docling은 OCR을 지원하지만 모든 페이지에 무조건 OCR을 수행하는 방식은 비용 측면에서 비효율적일 수 있다.

현재 프로젝트에서 생각하고 있는 구조는 합리적이다.

~~~text
Docling Base OCR
 ↓
OCR Quality Gate
 ├─ PASS
 │
 └─ FAIL
      ↓
   Internal OCR API
~~~

추가로 가능하다면 OCR 필요성 판단과 OCR 결과 품질 판단을 분리할 수도 있다.

~~~text
Native Text Extraction
 ↓
OCR Required?
 ↓
OCR
 ↓
OCR Quality Gate
~~~

특히 대규모 Batch Processing에서는 모든 페이지에 동일한 비용을 사용하기보다 필요한 페이지에서만 비싼 처리를 수행하는 것이 중요하다.

단, Docling Technical Report의 OCR 관련 benchmark와 backend 구성은 2024년 시점의 내용이므로 현재 Docling 구현과 동일하다고 가정해서는 안 된다.

---

## 15. Parser / OCR Fallback은 처음부터 복잡하게 만들 필요가 없다

Docling Technical Report에서는 PDF backend에 따라 성능과 품질 특성이 달라질 수 있음을 설명한다. 이를 현재 프로젝트에 적용하면 다음과 같은 확장 가능성은 있다.

~~~text
Primary Parser
 ↓
Parse Quality Gate
 ├─ PASS
 │
 └─ FAIL
      ↓
 Fallback Parser
~~~

하지만 처음부터 여러 Parser를 운영하는 것은 복잡도만 높일 수 있다.

권장 순서는 다음과 같다.

1. Docling 단일 Parser로 시작
2. Parsing Golden Dataset 구축
3. 반복적으로 실패하는 문서 유형 확인
4. 원인이 명확한 경우에만 Fallback / Normalization Policy 추가

즉 실제 실패 Case가 Architecture를 확장하게 하는 구조를 가져가는 것이 좋다.

---

## 16. 최종 권장 Architecture

Docling Technical Report와 현재 프로젝트 목표를 함께 고려하면 다음과 같은 구조가 적절하다.

~~~text
PDF / PPTX / DOCX
        ↓
      Docling
        ↓
 Raw DoclingDocument
        ↓
    Normalizer
        ↓
NormalizedElement[]
        │
        ├─ type
        ├─ text
        ├─ page
        ├─ bbox
        ├─ reading_order
        ├─ heading_path
        ├─ relation
        ├─ table structure
        └─ provenance
        ↓
 Element Policies
        │
        ├─ ParagraphPolicy
        ├─ TablePolicy
        ├─ ListPolicy
        ├─ FigurePolicy
        └─ CaptionPolicy
        ↓
 ChunkCandidate[]
        ↓
 Merge / Split Policies
        │
        ├─ Structure Boundary
        ├─ Heading Boundary
        ├─ Element Compatibility
        ├─ Relation
        └─ Max Token Guardrail
        ↓
   ChunkSequence
        ↓
  Domain Mapping
        ↓
  D03 D03 D03 D06 ...
        ↓
Boundary Resolution
        ↓
      Unit
~~~

각 계층의 책임은 다음과 같다.

| Layer | Responsibility |
| --- | --- |
| Docling | 원본 문서의 Layout / Text / Table 등의 구조 복원 |
| Normalizer | Docling 결과를 서비스 공통 Representation으로 변환 |
| Element Policy | Element 유형별 Chunk Candidate 생성 방식 결정 |
| Merge / Split Policy | Candidate 결합 및 최종 Chunk 크기 결정 |
| Domain Mapping | Chunk의 업무 Domain 판정 |
| Boundary Resolution | Domain 전환 경계 보정 |
| Unit Segmentation | 실제 업무 의미 구간 생성 |

---

## 17. NormalizedElement 권장 최소 Schema

초기 구현에서는 지나치게 많은 정보를 넣기보다는 다음 정도를 우선 고려할 수 있다.

~~~python
@dataclass
class NormalizedElement:
    element_id: str
    element_type: str
    text: str | None
    page_no: int | None
    bbox: tuple | None
    reading_order: int | None
    heading_path: list[str]
    parent_id: str | None
    table_structure: dict | None
    related_element_ids: list[str]
    source_ref: dict
~~~

여기서 중요한 원칙은 다음과 같다.

> 모든 Metadata를 Chunk Text에 넣는 것이 아니라 원문 구조와 Provenance를 데이터로 잃지 않고 유지하는 것

Domain Mapping에 실제로 어떤 정보를 넣을지는 별도로 결정하면 된다.

~~~text
Embedding / Classifier Input

[Heading]
설비 관리 > 예방정비

[Content]
CMP 설비는 매월 정기점검을 실시한다.
~~~

반면 bbox, source_ref, page_no, docling element id 등은 Classifier에 전달하지 않아도 저장할 수 있다.

---

## 18. 중요한 설계 원칙

### 18.1 Docling 결과를 너무 일찍 flatten하지 않는다

~~~text
DoclingDocument → Markdown → Plain Text
~~~

로 너무 빨리 변환하면 Layout, Table, Relation, Provenance를 다시 복구하기 어렵다. 따라서 구조화된 Intermediate Representation을 먼저 만든다.

### 18.2 Chunker에게 Semantic Intelligence를 너무 많이 넣지 않는다

현재 시스템에서는 실제 의미 구간을 이후 Domain-aware Unit 단계에서 결정한다.

따라서 Chunker까지 LLM 등을 사용하여 완벽한 Semantic Boundary를 찾도록 하면 다음 문제가 생긴다.

~~~text
Semantic Chunking
        ↓
Domain Boundary Resolution
~~~

두 단계가 사실상 같은 문제를 중복으로 해결하게 된다.

현재 목표에 더 맞는 구조는 다음과 같다.

~~~text
Stable Structural Chunk
        ↓
Domain Mapping
        ↓
Boundary Resolution
        ↓
Semantic / Domain-aware Unit
~~~

### 18.3 Document Structure는 Signal이지 항상 Rule은 아니다

~~~text
SECTION_HEADER → 강한 split signal
TABLE          → 독립 처리 가능성이 높은 signal
same heading_path → merge 가능성이 높은 signal
~~~

하지만 다음처럼 절대화해서는 안 된다.

~~~text
SECTION_HEADER → 무조건 Split
TABLE → 무조건 독립 Chunk
PAGE → 무조건 Split
~~~

기업 문서의 구조가 매우 다양하기 때문이다. Golden Dataset을 통해 어떤 구조 정보가 실제로 신뢰할 만한지 확인해야 한다.

### 18.4 Element Type별 Policy와 Merge/Split Policy를 분리한다

두 책임을 한 코드에 모두 넣으면 규칙이 복잡해진다.

~~~text
Element Policy
→ 이 Element를 어떤 Candidate로 표현할 것인가?

Merge/Split Policy
→ Candidate들을 어디까지 합치거나 나눌 것인가?
~~~

로 책임을 분리하는 것이 확장성이 좋다.

### 18.5 Provenance는 최대한 끝까지 유지한다

다음 Chain이 가능해야 한다.

~~~text
Search Result
 ↓
Unit
 ↓
Chunk
 ↓
Element
 ↓
Original Document
 ↓
Page / Slide / Bounding Box
~~~

이는 향후 HITL, Debugging, Golden Dataset, 평가, 원문 Highlight 등에 활용할 수 있다.

---

## 19. 아직 결정하면 안 되는 부분

현재 단계에서 다음 규칙을 지나치게 일찍 고정하는 것은 위험하다.

~~~text
Chunk = Paragraph 1개
Chunk = Section 1개
TABLE = 항상 Chunk 1개
Heading = 항상 Split
Page = 항상 Split
Maximum Token = N
~~~

이러한 값은 Architecture의 핵심 원칙이 아니라 Policy Configuration으로 두는 것이 좋다.

~~~yaml
chunking:
  max_tokens: 512

  heading:
    boundary_strength: strong

  table:
    standalone: true

  paragraph:
    allow_merge: true
~~~

그리고 실제 Golden Dataset 결과를 바탕으로 조정한다.

---

## 20. Table과 앞 Paragraph 관계는 별도 검토가 필요하다

예를 들어:

~~~text
주요 점검 기준은 다음 표와 같다.

[Table]
점검항목 | 기준값
압력     | 0.8
온도     | 70℃
~~~

단순 Policy:

~~~text
Paragraph → Chunk01
Table     → Chunk02
~~~

가 항상 좋은 것은 아니다. 첫 번째 Paragraph는 Table 없이는 의미가 부족하기 때문이다.

따라서 향후 다음과 같은 Context Policy가 필요할 수 있다.

~~~text
TableContextPolicy

IF
    paragraph immediately precedes table

AND
    paragraph contains table-reference expression
    ("다음과 같다", "아래 표", "다음 표 참조" ...)

THEN
    paragraph + table association 유지
~~~

중요한 것은 반드시 하나의 Chunk로 합쳐야 한다는 의미는 아니다. 다음처럼 relation만 유지하는 것도 가능하다.

~~~text
Chunk01
text:
  주요 점검 기준은 다음 표와 같다.
related_chunk:
  Chunk02

Chunk02
type:
  table
related_chunk:
  Chunk01
~~~

이 판단 역시 실제 문서 사례와 downstream Domain Mapping 성능을 보고 결정하는 것이 좋다.

---

## 21. 현재 프로젝트에 가장 중요한 결론

Docling Technical Report를 현재 프로젝트 관점에서 해석했을 때 핵심은 다음 한 문장으로 정리할 수 있다.

> Docling이 복원한 문서 구조를 너무 일찍 plain text로 flatten하지 말고, structure와 provenance를 유지하는 중간 Representation으로 변환한 뒤, downstream Domain Classification 목적에 맞는 작은 Policy들을 조합하여 안정적인 Chunk Sequence를 생성한다.

따라서 목표는 완벽한 Semantic Chunker를 만드는 것이 아니다.

현재 파이프라인에서 앞단 Chunker의 역할은 다음과 같다.

~~~text
다양한 문서
    ↓
구조를 최대한 보존
    ↓
안정적인 Chunk Sequence
    ↓
Domain 판정에 충분한 Evidence 제공
~~~

실제 Semantic / Business Boundary는 이후 단계에서 해결한다.

~~~text
Chunk
 ↓
Domain Mapping
 ↓
Context Resolution
 ↓
LLM Boundary Resolution
 ↓
Unit
~~~

---

## 22. 최종 요약

~~~text
Docling
│
│  문서 구조 복원
│
▼
NormalizedElement
│
│  구조 / provenance 보존
│
▼
Element Policy
│
│  Element별 처리
│
▼
ChunkCandidate
│
▼
Merge / Split Policy
│
│  구조 신호 + token guardrail
│
▼
Stable Chunk Sequence
│
▼
Domain Mapping
│
▼
Boundary Resolution
│
▼
Domain-aware Unit
~~~

이 Architecture의 핵심 설계 철학은 다음과 같다.

1. Docling을 단순 Text Extractor로 사용하지 않는다.
2. Layout 정보는 Chunk boundary 판단의 Signal로 활용한다.
3. Heading, Paragraph, Table, List 등을 동일하게 취급하지 않는다.
4. Element 유형별 처리 Policy를 분리한다.
5. Element 처리와 Merge/Split 책임을 분리한다.
6. Token Limit은 의미 경계보다는 Guardrail로 활용한다.
7. Docling 구조를 서비스 독립적인 NormalizedElement로 변환한다.
8. 원문으로 돌아갈 수 있도록 Provenance를 유지한다.
9. Chunk 자체를 완벽한 Semantic Unit으로 만들려고 하지 않는다.
10. 실제 업무 의미 경계는 Domain Mapping 이후 Unit 단계에서 해결한다.
11. 새로운 문서 Case는 기존 코드 수정보다 새로운 Policy 추가로 대응한다.
12. 구체적인 Chunk 규칙과 Threshold는 Golden Dataset으로 검증하면서 결정한다.

---

## Reference

- Auer et al., *Docling Technical Report*, 2024  
  https://arxiv.org/abs/2408.09869

