# AI_READY_DATA 프로젝트 컨텍스트

> 다른 ChatGPT 세션이나 Codex에 전달하기 위한 프로젝트 기준 문서  
> 기준일: 2026-09-03. 최신 설계를 우선하며 미확정 사항은 별도 표시한다.

## 1. 프로젝트 정의

다양한 정형·비정형 기업 데이터를 **Asset**으로 등록하고, 비정형 문서는 Docling 기반으로 구조화한 뒤 Chunk별 업무 Domain을 단계적으로 판정하여 동일 Domain의 연속 구간을 **Unit**으로 구성한다. 이후 Domain Profile 기반 공통 Agent가 Unit의 `summary`와 도메인 특화 `domain_fields`를 생성하고 이를 벡터화한다. Unit Context를 상향 합성하여 Asset Context 및 Group Context를 만들고, 최종적으로 StarRocks에서 **필터 + 키워드 + 벡터 유사도**를 결합한 Hybrid Search를 제공하는 AI-Ready Data / Data Catalog 플랫폼이다.

## 2. 큰 흐름

```text
Upload → Asset 등록 → 유형 분기/검증
  ├─ Document(PDF/PPT/DOCX) → Docling 구조 분석
  └─ CSV/Excel → 검증/표준화 → Iceberg
                         ↓
                Context / Vector
                         ↓
                     StarRocks
                         ↓
          Filter + Keyword + Vector
                  Hybrid Search
```

단순 PDF Chunk RAG가 아니라 데이터 자산의 업무 의미를 구조화하고 관련 데이터를 탐색하는 플랫폼이다.

## 3. 핵심 용어

### Asset
플랫폼의 기본 데이터 자산. 비정형 문서 1개와 Asset 1개가 1:1 대응한다. 원본은 CAS 방식 Object Storage에 저장할 계획이다.

### Document Element
Docling이 추출하는 Heading, Paragraph, Table, List, Picture, Caption, page/slide provenance, bounding box, reading order 등의 구조 요소.

### Chunk
Domain 판정이 가능한 작은 연속 처리 단위.
- 최종 검색 단위가 아니다.
- 원문 Chunk 자체를 최종 검색용으로 임베딩하지 않는다.
- Domain KNN 판정을 위한 Chunk embedding은 사용할 수 있다.
- 정확한 Chunk 기준은 아직 미확정이다.
- 목표는 완벽한 semantic chunk가 아니라 원문 의미/순서를 크게 훼손하지 않는 안정적인 판정 단위다.

### Domain
현재 12개 업무 Domain이 준비되어 있다. Domain별로 용어 사전, Anchor Vector Set, Domain Profile, 특화 추출 필드를 관리한다. Multi-domain Unit은 아직 검토 중이다.

### Unit
**동일 Domain으로 판정된 연속 Chunk들을 경계 보정 후 결합한 문서 내 의미 구간.**

```text
C04 D03
C05 D03
C06 D03
C07 UNKNOWN
C08 D03
...
C14 D03
   ↓ 문맥/경계 보정
C04 ~ C14 = Unit01 / D03
```

Unit 1개가 최종 Vector Search Point 1건이 된다.

### EXCLUDE
현재 12개 Domain에 맞지 않는 구간. 삭제하지 않고 일단 저장하여 향후 Domain 추가나 재처리에 활용하는 방향이다.

### Group
업무적으로 관련 있는 여러 Asset의 집합. 예: CMP 설비 Master + Alarm History + 점검 보고서 + 예방정비 이력.

## 4. 저장 계층

- **Object Storage**: 원본 파일, CAS
- **Iceberg**: CSV/Excel 표준화 Table 및 Snapshot
- **StarRocks**: Asset, Profile, Unit/Asset/Group Context, Vector, Vector Index, Hybrid Search metadata

## 5. Docling Pipeline

```text
PDF/PPT/DOCX
   ↓
Docling
   ↓
OCR / Layout / Table / Text
   ↓
Normalized Document Elements
   ↓
Chunking
   ↓
Domain Mapping용 Chunk Sequence
```

Docling의 핵심 책임:
- Text 및 구조 추출
- Heading/Paragraph/List/Table/Picture/Caption 식별
- page/slide와 원본 위치 provenance 보존
- reading order 최대한 유지
- OCR 및 OCR 품질 판단용 정보 제공
- 저비용 구조 profiling / preview 생성

목표는 완벽한 의미 분석이 아니라 **후속 Domain segmentation이 안정적으로 작동할 입력을 만드는 것**이다.

## 6. OCR 전략

```text
Docling Base OCR
   ↓
OCR Quality Gate
   ├─ PASS → 계속
   └─ FAIL → OCR Topic → OCR Worker → 사내 OCR Model API
```

한국어 문서가 대부분일 것으로 예상한다. 품질 신호 후보:
- OCR engine confidence
- 완성형 한글/비정상 자모 비율
- text coverage
- Docling layout/parse quality
- 한국어 문장 plausibility

가능하면 page/slide 단위 fallback을 사용한다.

## 7. Chunking

정확한 규칙은 미확정이다. 플랫폼 특성상 문서 구조를 예측할 수 없어 특정 Heading/Section 구조에 강하게 의존하는 semantic chunking은 위험하다.

후보 원칙:
- Docling Element/문장/문단 경계를 활용
- 최대 token size 제한
- 가능한 구조 정보 보존
- 원문 순서/provenance 보존
- 실제 의미 구간은 이후 Domain segmentation에서 Unit으로 생성

## 8. Chunk Domain Mapping: 4단계

철학: **싼 방법으로 확실한 것을 먼저 확정하고 LLM은 마지막 애매한 경계에만 사용한다.**

```text
Chunk
 ↓
1. Dictionary Mapping
 ↓ 미확정
2. Embedding KNN
 ↓ 미확정
3. Context Resolution
 ↓ 경계 미확정
4. LLM Boundary Agent
```

### 8.1 용어 사전
Domain별 Catalog 용어에 가중치를 둔다. Chunk 내 가중 점수를 합산하고 확정 threshold를 넘거나 1위가 2위의 2배 이상이면 즉시 확정하고 이후 단계를 생략한다.

### 8.2 Anchor Vector + KNN
각 Domain에 5~20개의 Anchor Vector를 둔다.

**Anchor Vector** = 해당 Domain의 다양한 의미를 대표하는 예문을 embedding한 기준 벡터.

Anchor 예문 초안은 Data Catalog를 Agent에 활용하여 생성한다. Chunk embedding과 각 Domain Anchor를 비교하여 Domain별 최근접 Top-3 평균 등을 계산하고 사전 점수와 결합한다.

```text
Chunk Vector
  ├─ D01 Anchor Set → Top-3 평균
  ├─ D02 Anchor Set → Top-3 평균
  └─ ...
```

Anchor 개수보다 Domain 의미의 coverage/diversity가 중요하다.

### 8.3 Context Resolution
주변 Chunk의 확정 Domain을 이용해 미확정 Chunk를 보정한다.

```text
D03 - UNKNOWN - D03 → D03 - D03 - D03
```

사용 예정 개념:
- 이웃 전파
- 문서 Domain 분포 보정
- 양쪽 이웃 확정 시 사이 Chunk 채택

### 8.4 LLM Boundary Agent
LLM은 12-class Chunk classifier가 아니라 **Boundary Resolver**다.

예:

```text
C28 → D03 확정
C29 → UNKNOWN
C30 → D06 확정
```

Agent에는 C28~C30(또는 조금 넓은 boundary window)의 원문과 양측 후보 Domain의 한 줄 정의를 준다.

```text
D03: 설비 점검 및 정비 이력 관리
D06: 알람 발생 이력과 조치 관리
```

질문도 `C29의 Domain은?`가 아니라 **“정비 서술이 끝나고 알람 서술이 시작되는 전환 지점을 판단하라”**처럼 전환점을 묻는다.

`C29 이후 전환`이면 C29는 D03, C30부터 D06으로 확정한다.

## 9. 경계 보정 및 Unit 생성

Domain sequence가 확정되면 같은 Domain의 연속 Chunk를 결합한다.

```text
p4~p6 D03
p7 UNKNOWN
p8~p9 D03
p10 UNKNOWN
p11~p14 D03
   ↓ 보정
p4 ~ p14 = Unit01 / D03
```

따라서 Unit 생성은 semantic clustering보다 **Domain-aware sequence segmentation**에 가깝다.

12개 Domain에 맞으면 Unit을 생성하고, 아니면 EXCLUDE로 저장한다.

## 10. Domain Profile / Profiler

도메인별 Agent 12개를 두지 않고 **공통 Base Agent + Domain Profile** 구조를 사용한다.

Domain Profile은 DB Table로 버전 관리한다.

예: `Domain03 - 정비`
- 점검항목
- 조치내역
- 대상 시스템

Unit Context 단계에서 말하는 Profiler는 사실상 다음 역할이다.

> Unit의 확정 Domain에 맞는 Profile을 조회하고, 공통 Base Agent가 무엇을 추출할지 결정하여 extraction schema/input을 구성하는 계층.

구현명으로는 `ProfileResolver`, `DomainProfileProvider`, `ProfileInjector` 등이 더 명확할 수 있다.

Profile에는 field name뿐 아니라 가능하면 type, description, required, allow_multiple, examples, extraction_instruction 등을 버전 관리한다.

## 11. Unit Context Agent

```text
Unit Original Text
 + Domain Definition
 + Domain Profile
 + Extraction Schema
        ↓
 Common Base Agent
        ↓
 Unit Context
```

Agent 산출물:

### summary
Unit 구간의 업무 의미 요약.

### domain_fields
Domain Profile이 정의한 schema에 따라 원문에서 값을 추출.

예:

```json
{
  "summary": "CMP 설비의 정기점검 결과와 이상 발생 후 정비 조치를 설명하는 구간",
  "domain_fields": {
    "점검항목": "진공펌프 압력",
    "조치내역": "필터 교체",
    "대상시스템": "CMP 설비"
  }
}
```

Agent는 단순 요약기가 아니라 **비정형 원문 → Domain-specific structured representation 변환기**다.

## 12. Unit Vector

확정 사항: **원문은 최종 embedding에 넣지 않는다.**

```text
Unit Original Text
   ↓ Context Agent
summary + domain_fields
   ↓ Embedding
Unit Vector
```

- `summary + domain_fields`만 embedding
- Unit 1개 = 검색 포인트 1건
- Chunk vector는 Domain classification용, Unit vector는 최종 검색용

## 13. Asset Context 상향 합성

Unit Context들의 요약/구조화 정보를 이용해 Asset Context를 만든다.

```text
Unit01 Context ─┐
Unit02 Context ─┼→ Asset Context
Unit03 Context ─┘
```

Asset Context 예:

```yaml
asset_name: 설비 점검 보고서
asset_type: document
business_domain:
  - 설비 유지보수
business_object:
  - CMP 설비
  - 예방 정비
  - 설비 알람
topics:
  - 점검 결과
  - 고장 원인
  - 장비 이력
related_assets:
  - 설비 master
  - 알람 이력 table
```

Context hierarchy:

```text
원문 → Chunk → Unit → Unit Context → Asset Context → Group Context
```

위로 갈수록 추상화 수준이 올라간다.

## 14. Group Context

서로 관련된 Asset들의 상위 업무 의미를 생성한다.

```yaml
group_summary: CMP 설비 운영 및 유지보수
members:
  - CMP 설비 Master
  - CMP Alarm History
  - CMP 설비 점검 보고서
```

정형 데이터의 실제 Join 관계와 비정형 Asset의 Domain/business object 등의 의미 관계를 함께 활용할 가능성이 높다.

## 15. Hybrid Search

최종 검색은 Vector similarity 단독이 아니다.

```text
User Query
  ↓
Query Understanding
  ├─ Filter
  ├─ Keyword
  └─ Vector Similarity
        ↓
    Result Fusion
        ↓
      Top-K
```

예: `CMP 설비의 예방정비 중 진공계통 이상 조치 관련 자료`

- Filter: `domain=maintenance`, `asset_type=document`
- Keyword: `CMP`, `진공`
- Vector: 예방정비/진공계통 이상 조치의 의미 검색

Domain Profile에서 추출한 `domain_fields`는 structured filter에도 활용할 수 있다.

StarRocks Vector Index를 이용하여 **필터 + 키워드 + 유사도** Hybrid Search를 지원할 계획이다.

## 16. Kafka / K8s 분산 처리

초기 자료의 개념적 흐름:

```text
Ingestion Event
 ↓
Parse Topic
 ↓
Parser Worker (Docling)
 ↓
OCR Topic
 ↓
OCR Worker
 ↓
Chunk Topic
 ↓
Chunk Worker
 ↓
Domain / Unit Processing
 ↓
Embedding Topic
 ↓
Embedding Worker
 ↓
Insert Topic
 ↓
Save Worker
 ↓
StarRocks
```

`Topic`은 Kafka 용어이며 특정 종류의 메시지가 흐르는 논리 채널이다.

설계 의도:
- 단계별 독립 scale-out
- 장애 격리
- 처리량 차이를 Kafka가 buffer
- 특정 단계부터 재처리
- CPU/GPU Worker 분리

대용량 처리 시 주의:
- idempotency
- deterministic ID
- retry / DLQ
- pipeline/profile/prompt/model versioning
- Kafka lag / backpressure
- content hash 기반 중복 embedding skip
- DB UPSERT/중복 방지

## 17. Agent 사용 위치와 철학

이 시스템은 LLM-first가 아니다.

### 1) Anchor Example 생성
Data Catalog를 참고하여 Domain별 Anchor 예문 초안 생성.

### 2) Boundary Agent
사전/KNN/문맥으로 해결되지 않은 **Domain 전환 경계**만 판정.

### 3) Unit Context Agent
공통 Base Agent에 Domain Profile을 주입하여 `summary + domain_fields` 생성.

### 4) Asset/Group Context Agent
Unit Context를 상향 합성하여 Asset/Group의 상위 의미 Context 생성.

전체 철학:

```text
Rule / Dictionary
       ↓
Embedding / KNN
       ↓
Context Heuristic
       ↓
LLM only when needed
```

비용, latency, 재현성, 운영 안정성을 위해 deterministic 처리와 Agent 판단을 분리한다.

## 18. 현재 담당할 가능성이 높은 영역

초기 업무는 주로 다음 앞단이다.

```text
Document
  ↓
Docling Parsing
  ↓
OCR / OCR Quality Gate
  ↓
Normalized Elements
  ↓
Chunking
  ↓
Domain Mapping이 사용할 안정적인 입력 제공
```

핵심 성공 기준은 “완벽한 semantic chunk”가 아니라 **다양한 형태의 PDF/PPT/DOCX를 downstream Domain/Unit pipeline에서 일관되게 처리할 수 있는 representation으로 변환하는 것**이다.

## 19. 현재 미확정 / 확인 필요 사항

1. **Chunk 기준**: Docling element / paragraph / sentence / token hybrid 중 어떤 정책을 사용할지.
2. **Multi-domain Unit**: 최신 자료는 single-domain처럼 보이나 multi-domain 지원은 검토 중.
3. **Unit 내부 Chunk split**: 하나의 Chunk 내부에서 Domain 전환이 일어나면 Chunk 자체를 재분할할지 한쪽에 귀속할지.
4. **OCR Quality threshold**: 실제 한국어 Golden Dataset으로 calibration 필요.
5. **Anchor Vector 운영**: 5~20개 생성 후 품질 검수, diversity, negative/boundary example 관리, versioning 방법.
6. **Asset/Group Vector 정책**: Unit Vector 외에 Asset/Group Vector를 최종적으로 모두 유지할지 최신 설계 확인 필요.
7. **related_assets / Group 생성 로직**: join key, schema similarity, domain/business object, rule/agent의 책임 경계.
8. **Profile schema 상세**: field type/description/examples/extraction rule까지 DB에서 관리할지.
9. **EXCLUDE 재처리 정책**: 새 Domain/Profile 추가 시 어떤 버전 기준으로 재판정할지.

## 20. 설계상 중요한 평가 포인트

Golden Dataset을 단계별로 분리해 평가하는 것이 적절하다.

- Parsing/OCR Golden Set
- Chunking Golden Set
- Chunk Domain Classification Golden Set
- Boundary Detection Golden Set
- Unit Segmentation Golden Set
- Unit Context / domain_fields Extraction Golden Set
- Retrieval Golden Set

특히 Anchor 생성에 사용한 예문/데이터와 Domain Classification 평가용 Golden Dataset은 분리해야 한다.

## 21. 한 문장 요약

> **Docling으로 다양한 비정형 문서를 안정적인 Chunk sequence로 변환하고, `사전 → Anchor KNN → 문맥 → LLM 경계 판정`으로 Domain-aware Unit을 생성한 뒤, 버전 관리되는 Domain Profile을 공통 Agent에 주입하여 `summary + domain_fields`를 생성·벡터화하고, 이를 Asset/Group Context로 상향 합성하여 StarRocks Hybrid Search에 제공하는 AI-Ready Data 플랫폼이다.**
