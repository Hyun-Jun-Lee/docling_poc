# 구조 인지형 Chunk Sequence 아키텍처

## 목적과 책임 경계

이 문서는 Docling이 변환한 `DoclingDocument`를 다양한 문서 형식에서 안정적으로 해석하여, 후속 **Domain Mapping**이 소비할 수 있는 구조 보존형 `Chunk sequence`로 만드는 아키텍처를 정의한다.

이 프로젝트에서 `Chunk`는 최종 검색/RAG 단위가 아니다. 작은 연속 본문 범위를 유지한 Domain 판정 입력이며, 동일 Domain으로 확정된 연속 Chunk를 후속 단계가 경계 보정하여 `Unit`으로 만든다. 최종 검색 벡터는 Unit Context의 `summary + domain_fields`에서 생성한다. 용어와 상위 파이프라인의 기준은 [AI_READY_DATA 프로젝트 컨텍스트](<AI_READY_DATA_project_context (1).md>)를 따른다.

```text
입력 파일
  → 변환 결과와 품질/누락 상태
  → Document IR
  → 구조 신호 보강
  → Domain Mapping용 Chunk sequence       # 이 문서의 산출물
  → Domain Mapping과 경계 보정            # 후속 계층
  → Unit 생성
  → Unit Context / Unit Vector / Hybrid Search
```

이 계층의 책임은 원본·읽기 순서·구조 신호·알려진 누락을 보존하고, 제목·목록·표·캡션을 근거와 함께 주석화하며, 후속 계층이 재분할·재조립할 수 있는 작은 연속 본문 Chunk를 만드는 것이다. 추출하지 못한 내용을 구조 추론으로 메우지 않는다.

다음은 이 계층의 책임이 아니다.

- Domain Dictionary/KNN/LLM Boundary Agent를 통한 Domain 확정
- 동일 Domain Chunk의 Unit 병합과 Unit Context/Vector 생성
- OCR 재시도, 대체 파서, 사람 검토 워크플로우의 구현
- StarRocks 저장·검색 또는 Asset/Group Context 생성

파싱 품질 계층은 이 문서에 필요한 입력 계약만 제공하며, 품질 판정·재처리 전략 자체는 별도 설계에서 소유한다.

## 배경과 문제 정의

현재 프로젝트는 `DoclingDocument`의 JSON/Markdown 내보내기와 Docling 네이티브 `HierarchicalChunker` 호출을 제공한다. 이 출력은 좋은 기준선이지만, 제목 스타일이 없거나 읽기 순서·표·인라인 그룹이 복잡한 문서에서 안정적인 Domain 판정 sequence를 보장하지는 않는다.

예를 들어 `2021 가상오피스 1차 모집 공고` DOCX에서 `1. 모집개요`, `나. 참여조건`, `(1) ...`은 표현상 계층을 이루지만 Docling 항목은 일반 `text`일 수 있다. 반대로 제목 아래의 여러 목록 항목이 하나의 업무 Domain이라는 보장도 없다. 따라서 제목 경로는 유용한 **문맥**이지만, 본문 소유 범위를 강제 병합하는 근거가 되어서는 안 된다.

## 핵심 원칙

1. **원본 불변 보관**: Docling JSON, `ConversionResult`, 설정과 오류는 수정하지 않고 snapshot으로 보관한다.
2. **순서와 근거 보존**: `texts` 배열의 인덱스가 아니라 문서 트리의 명시적 읽기 순서를 사용하고, 모든 파생 결과는 snapshot의 원본 범위를 역추적할 수 있어야 한다.
3. **본문과 문맥 분리**: Chunk가 담당하는 원문은 `body_refs`, 제목·표 헤더·캡션 등 반복 가능한 보조 정보는 `context_refs`로 분리한다.
4. **작은 연속 단위 우선**: Chunk는 Domain 판정과 재분할을 위해 문단·목록 항목·표 행 경계를 가능한 한 유지한다. 구조적으로 같은 절이라는 이유만으로 본문을 먼저 합치지 않는다.
5. **구조는 근거 기반 보강**: 번호, 스타일, 인접성은 후보 신호다. 확정할 수 없는 관계를 사실처럼 만들지 않는다.
6. **누락은 별도 상태**: 낮은 구조 신뢰도와 내용 추출 실패를 구분한다. 알려진 본문 누락을 `UNKNOWN` 또는 `EXCLUDE`로 바꾸지 않는다.
7. **결정론적 기준선**: 기본 경로는 재현 가능한 규칙 기반 처리로 유지한다. LLM은 이 계층의 필수 의존성이 아니다.
8. **관찰된 구조로 청킹 정책 선택**: 파싱 경로는 파일 형식과 지원 기능으로, 구조 보강/Chunk 정책은 실제 추출된 신호로 선택한다.

## 입출력 계약

### Parse snapshot 입력

청킹 계층은 `DoclingDocument`만 받지 않는다. 최소한 다음 정보를 함께 받는다.

```text
parse_snapshot_id
conversion_status             # Docling이 반환한 상태
parser/runtime configuration  # Docling·docling-core·OCR·모델/파서 식별 정보
intentional_truncation        # 예: max_num_pages로 인한 의도적 절단
known_gaps[]                  # 위치, 사유, 복구 가능 여부, 본문 누락 여부
unsupported_regions[]         # 지원하지 않거나 처리하지 않은 영역
```

`conversion_status=success`은 원문 완전성을 증명하지 않는다. 품질 상태를 `ACCEPTED` 같은 단일 값으로 만들려면, 근거·측정 범위·판정 기준이 별도 품질 설계에서 먼저 정의되어야 한다.

### RawBlock

`RawBlock`은 원본 Docling 모델을 복제하지 않는다. 후속 구조화에 필요한 최소 공통 계약과 원본 payload 참조를 제공한다.

```python
@dataclass(frozen=True)
class SourceLocator:
    parse_snapshot_id: str
    self_ref: str
    text_span: tuple[int, int] | None = None
    table_locator: TableLocator | None = None  # 행/셀로 실제 분할했을 때만 사용


@dataclass(frozen=True)
class RawBlock:
    id: str
    sequence_index: int
    kind: Literal["text", "table", "picture", "group", "unknown"]
    text: str | None
    body_source: list[SourceLocator]
    container_refs: list[str]
    native_signals: NativeSignals       # label, heading level, list marker 등
    signal_availability: SignalAvailability
    formatting: FormattingSignals | None
    structure_payload_ref: str | None   # 표 grid, 그림, 병합 셀 등
```

문자 범위와 표 행/셀 범위는 원소를 실제로 분할할 때만 의무화한다. 초기에는 immutable snapshot의 `self_ref`와 opaque payload 참조로 시작해 Docling 모델을 서비스 모델로 재구현하지 않는다.

### StructureAnnotation

구조 보강은 RawBlock을 지우거나 병합하기보다 역할·관계 후보를 낸다.

```python
@dataclass(frozen=True)
class StructureAnnotation:
    block_id: str
    role: Literal["heading", "paragraph", "list_item", "table", "caption",
                  "note", "image", "header_footer", "unknown"]
    level: int | None
    decision_score: float | None
    evidence: list[str]
    related_block_ids: list[str]
    relationship_status: Literal["confirmed", "candidate", "unresolved"]
```

`decision_score`는 확률이 아니다. 점수 산식, 적용 정책, 결측 신호 처리를 기록해야 하며 추출 품질·읽기 순서·역할 판정·관계 판정을 하나의 점수로 합치지 않는다.

### Chunk sequence 출력

```json
{
  "chunk_id": "...",
  "parse_snapshot_id": "parse-snapshot-...",
  "sequence_index": 42,
  "text": "(2) 알람 코드와 발생 시각을 기록한다.",
  "body_refs": [{"self_ref": "#/texts/17"}],
  "context_refs": [{"self_ref": "#/texts/13"}],
  "section_path": ["3. 설비 운영 절차"],
  "block_types": ["list_item"],
  "gap_before": null,
  "structure_evidence": ["numbering:parenthesized_decimal"],
  "chunker_version": "v1"
}
```

`classification_text`는 저장 원문의 대체물이 아니라 Domain 판정 모델에 전달할 때 생성하는 렌더링 결과다. 제목·표 헤더·필수 주석을 붙일 수 있지만, 그것들이 `body_refs`로 중복 누적되어서는 안 된다.

## 처리 단계

### A. 정규화와 정확히 한 번의 순회

- `body.children`을 읽기 순서의 시작점으로 삼고 `$ref`를 해소한다.
- 컨테이너(`group`, table cell group 등)와 자식 중 어느 항목을 본문으로 emit할지 명시적으로 결정한다.
- 본문 leaf를 정확히 한 번만 출력한다. 컨테이너는 자식의 렌더링·관계 보존에 사용할 수 있지만 같은 텍스트를 별도 본문으로 다시 emit하지 않는다.
- `furniture`, header/footer, 미지원·알 수 없는 요소도 원본 참조 없이 조용히 버리지 않는다. body/context/excluded/unsupported/missing disposition을 기록한다.
- 표는 Markdown 문자열 하나로 축소하지 않는다. grid, 병합 셀, 헤더 여부는 원본 payload 또는 참조로 유지한다.

Docling이 제공하는 읽기 순서를 보존하는 일과, 그 순서가 원문과 정확히 일치하는지 검증하는 일은 별도 책임이다.

### B. 구조 신호 보강

정책은 동일 블록에 독립적인 근거를 더할 수 있다.

```text
NativeStructurePolicy
  → Docling heading/list/table/caption 레이블과 부모 관계

NumberingPatternPolicy
  → 1. / 1.1 / 가. / (1) / ① / 제1조 등 번호 체계 후보

VisualStylePolicy
  → 실제 backend가 제공한 굵기·크기·들여쓰기·여백만 보조 신호로 사용

RepetitionNoisePolicy
  → 반복 머리글·바닥글·로고·면책 문구를 보존한 채 검색 노이즈 후보로 표시
```

번호 인식은 제목·계층 확정과 분리한다. 주석·각주·경고문도 명시적 표식이나 참조 관계를 인접성보다 우선하며, 관계가 불명확하면 `unresolved`로 남긴다.

### 정책 확장 계약

새 문서 사례는 공통 순회나 Chunk 조립기를 수정하는 대신, 가능한 한 작은 `StructurePolicy`를 추가해 처리한다. 정책은 원본과 다른 정책의 결과를 변경하지 않고, 자신의 근거를 담은 `StructureAnnotation`만 추가한다.

```python
class StructurePolicy(Protocol):
    name: str
    version: str
    priority: int

    def applies_to(self, snapshot: ParseSnapshot, blocks: Sequence[RawBlock]) -> bool: ...
    def annotate(
        self, snapshot: ParseSnapshot, blocks: Sequence[RawBlock]
    ) -> Sequence[StructureAnnotation]: ...
```

각 정책은 다음을 선언하거나 테스트로 증명해야 한다.

- 적용 대상과 필요한 native signal
- 생성하는 역할·관계 후보와 `evidence` 형식
- 다른 정책과 충돌할 수 있는 결정 및 `priority`
- 대표 fixture와 기대 annotation

`PolicyRegistry`는 적용 가능한 정책을 실행하고, `AnnotationResolver`는 같은 블록 또는 관계에 대한 결과를 중앙에서 해소한다. 우선순위는 확정 관계에만 사용하며, 동등한 근거 또는 불충분한 근거는 하나를 임의 선택하지 않고 `candidate`/`unresolved`로 남긴다. 정책은 Chunk를 직접 만들거나 `RawBlock`을 수정하지 않는다.

```text
RawBlock sequence
  → PolicyRegistry
  → 독립 StructurePolicy들의 annotation
  → AnnotationResolver
  → 공통 Assembler
  → Chunk sequence
```

예를 들어 한국 공고문의 `가.`, `(1)`, `※`는 `KoreanNoticeNumberingPolicy`, 반복 머리글은 `RepetitionNoisePolicy`, 표의 제목·헤더 관계는 `TableContextPolicy`로 추가한다. 정상화·원본 참조·공통 Assembler는 바꾸지 않는 것이 기본이다. 새 정책이 필요한 정보를 RawBlock에서 얻을 수 없는 경우에만, 계약을 확장할지 먼저 검토한다.

### C. 보수적 Chunk 조립

- 제목은 `section_path`와 `context_refs`를 제공하지만 제목만으로 하위 본문과 강제 병합하지 않는다.
- 목록 항목·문단·표 행은 가능한 한 독립적인 연속 body 범위를 유지한다.
- 짧은 연속 항목의 묶음은 Domain 판정 정확도와 재분할 가능성을 해치지 않는다는 근거가 있을 때만 허용한다.
- 표 본문은 문단과 임의로 섞지 않는다. 표를 실제로 분할하면 제목·헤더·적용 조건을 context로 반복하고 row/cell locator를 남긴다.
- 제목만 있는 슬라이드나 절도 원본 요소로 보존한다. Chunk 분류 대상 여부와 원본 보존 여부를 혼동하지 않는다.

`structured`, `numbered`, `table_heavy`, `slide_deck` 같은 명칭은 업무 `Domain Profile`과 구별해 `StructureProfile`이라 부른다. 초기 구현은 프로파일별 완성형 조립기 대신 공통 조립기와 경계/문맥 정책으로 시작한다. 복합 문서에서 어떤 정책이 우선하는지는 대표 문서 검증 뒤에 확정한다.

### D. 누락과 fallback

| 상황 | 처리 |
| --- | --- |
| 내용은 추출됐으나 제목·관계가 불명확 | 보수적 Chunk 생성, 구조 관계를 candidate/unresolved로 기록 |
| 본문 누락 또는 OCR/변환 실패가 알려짐 | `known_gap`을 순서상 남기고 후속 Unit 병합 가능 여부를 명시 |
| 의도적 페이지 제한 | 문서 tail의 truncation으로 기록하고 완전 문서로 취급하지 않음 |
| 지원하지 않는 요소 | `unsupported` disposition과 원본 참조·사유 보존 |
| 현재 Domain에 맞지 않음 | 후속 계층의 `EXCLUDE`; 이 계층이 내용 누락과 혼동하지 않음 |

알려진 본문 누락은 양쪽 Chunk를 자동으로 하나의 Unit으로 잇는 장벽이 될 수 있다. 단, 정책적으로 제외한 장식 요소나 실제 본문이 없는 영역까지 동일한 장벽으로 취급하지 않는다.

### E. 렌더링과 토큰 제한

토큰은 RawBlock이나 본문만이 아니라 실제 모델 입력 전체에서 측정한다.

```text
classification_text
  = 문서 제목 + section_path + 표 헤더/필수 주석 + body + 모델 prefix
```

- Chunk의 토큰 예산은 Domain 판정 모델의 토크나이저로 측정한다.
- Unit Context와 Unit Vector의 토큰 예산은 후속 계층에서 별도로 관리한다.
- 한 Chunk가 한도를 넘으면 원본 문단·목록·행 경계에서만 분할하고, 분할 locator를 남긴다.
- overlap은 강제 분할에서만 최소한으로 사용한다.

## 기준선과 검증

커스텀 정책을 확대하기 전에 설치된 Docling 버전의 `HierarchicalChunker`와 `HybridChunker`를 같은 대표 문서로 비교한다. 목록 병합, 작은 peer 병합, 표 헤더 반복, 토큰 분할이 실제 반입 버전에서 어떻게 동작하는지 측정한 뒤 커스텀 범위를 결정한다.

평가는 다음 계층을 구분한다.

| 계층 | 확인 항목 |
| --- | --- |
| Parsing/OCR | 변환 오류, 의도적 절단, 알려진 누락·미지원 영역 |
| Normalization/IR | 읽기 순서, 정확히 한 번의 body 출력, 원본 참조와 disposition |
| Chunking | body/context 분리, 구조 근거, 토큰 한도, 재분할 locator |
| Domain Mapping | Dictionary/KNN/문맥 기반 Domain 판정 품질 |
| Unit Segmentation | gap을 넘지 않는 병합, Domain 경계 보정 품질 |
| Retrieval | Unit Context와 Unit Vector 기반 Hybrid Search 품질 |

골든 테스트는 결과 snapshot뿐 아니라 다음 불변 조건을 포함한다.

- 처리된 본문 요소는 body/context/excluded/unsupported/missing 중 적절한 disposition을 가진다.
- 동일 본문은 body로 중복 출력되지 않는다.
- 모든 Chunk는 parse snapshot 안의 원본 범위를 역추적할 수 있다.
- 렌더링된 Domain 판정 입력은 토큰 한도를 넘지 않는다.
- 알려진 본문 누락을 넘어 자동 Unit 병합하지 않는다.

초기 smoke corpus는 현재 지원 대상의 정상 DOCX, 제목 스타일 없는 공고문, 병합 셀이 있는 표, 기본 PDF/PPTX와 알려진 실패 fixture로 시작한다. 이미지형 Office 문서, 혼합 스캔 PDF, 다단 PDF, 차트·도식, 암호화·손상 파일, 발표자 노트는 capability matrix에서 `supported`, `unsupported`, `unverified`로 명시하고 실제 입력 분포와 실패 사례에 따라 확장한다.

## 모듈 경계

```text
src/docling_poc/
  docling_raw.py       # Docling 변환 어댑터, 원본 export
  chunking/
    contracts.py       # parse snapshot, RawBlock, StructureAnnotation, Chunk
    normalize.py       # DoclingDocument → 순서 보존 RawBlock
    policies/
      base.py          # StructurePolicy 프로토콜과 공통 보조 도구
      native_structure.py
      numbering.py
      repetition_noise.py
      table_context.py
      korean_notice.py # 새 문서 사례는 독립 정책으로 추가
    policy_registry.py # 적용 가능한 정책 선택과 실행
    resolve_annotations.py # 정책 충돌 해소, 후보/미확정 관계 보존
    assemble.py        # 보수적 body Chunk + context 관계 조립
    render.py          # classification_text와 metadata 생성
    tokenize.py        # Domain 판정 토크나이저 기반 길이 제한
    evaluate.py        # IR/Chunk 불변 조건과 기준선 비교
```

### 모듈별 책임과 분리 이유

| 모듈 | 단일 책임 | 분리 이유 |
| --- | --- | --- |
| `docling_raw.py` | Docling 호출, `ConversionResult` 반환, 원본 직렬화 | Docling API 의존성을 격리한다. Docling 버전·변환 옵션 변경이 구조 정책과 Chunk 조립에 전파되지 않는다. |
| `contracts.py` | `ParseSnapshot`, `RawBlock`, `StructureAnnotation`, `Chunk`, locator의 안정된 계약 | 모든 단계가 같은 용어와 데이터 형태를 사용한다. 정책이 추가돼도 공유 모델은 독립적으로 진화한다. |
| `normalize.py` | Docling의 `$ref`, `body.children`, group, table을 순서 보존 `RawBlock`으로 변환 | Docling 내부 JSON을 아는 코드를 한곳에 가둔다. 이후 정책은 Docling 전용 구조가 아닌 RawBlock만 해석한다. |
| `policies/base.py` | `StructurePolicy` 프로토콜과 annotation 생성 보조 도구 | 새 정책의 작성 방식과 불변 조건을 통일한다. 정책이 원본이나 Chunk를 직접 변경하지 못하게 한다. |
| `policies/native_structure.py` | Docling이 제공한 heading/list/table/caption 신호 해석 | 가장 신뢰도 높은 native 신호를 독립적으로 보존하고, Docling 신호 변경의 영향을 국소화한다. |
| `policies/numbering.py` | 일반 번호 체계의 후보 식별 | 번호 표현은 언어와 문서군별로 변화가 잦으므로 공통 조립기에서 분리한다. |
| `policies/repetition_noise.py` | 반복 머리글·바닥글·로고·면책 문구 후보 식별 | 요소를 삭제하지 않고 검색 노이즈 annotation만 추가한다. 보존, metadata 이전, 모델 입력 제외의 결정을 분리한다. |
| `policies/table_context.py` | 표 제목·헤더·행·병합 셀의 문맥 관계 생성 | 표 구조와 일반 문단 조립을 분리하여 표 처리 변경이 본문 Chunk 규칙에 영향을 주지 않게 한다. |
| `policies/korean_notice.py` | 한국 공고문의 `가.`, `(1)`, `※` 등 특화 표기 해석 | 특정 문서군의 예외를 범용 번호 정책이나 Assembler의 조건문으로 누적하지 않는다. |
| `policy_registry.py` | 적용 가능한 정책 선택·실행, 정책 버전·설정 기록 | 문서 유형 분기를 한곳에 모으고, 어떤 정책이 적용됐는지 재현 가능하게 한다. |
| `resolve_annotations.py` | 정책 결과의 충돌 해소와 `confirmed`/`candidate`/`unresolved` 결정 | 각 정책이 서로를 알 필요가 없다. 예를 들어 번호 정책과 스타일 정책이 다르게 판단해도 중앙에서 일관되게 처리한다. |
| `assemble.py` | 해소된 annotation과 RawBlock에서 body Chunk·context 관계 조립 | 정책은 “무엇처럼 보이는가”, Assembler는 “어디까지가 본문 범위인가”만 책임지도록 분리한다. |
| `render.py` | 원문, `classification_text`, metadata 렌더링 | 제목·표 헤더 같은 문맥을 모델 입력에 넣어도 본문 원문과 source ref가 중복 저장되지 않는다. |
| `tokenize.py` | 실제 Domain 판정 모델 토크나이저 기반 길이 측정·강제 분할 | 문자 수가 아닌 모델 기준 한도를 보장한다. 모델 교체의 영향을 국소화한다. |
| `evaluate.py` | fixture, 골든 결과, 순서·누락·중복·토큰·gap 불변 조건 검증 | 새 정책이 기존 사례를 망가뜨리지 않는지 회귀 검증한다. |

처리 흐름은 단방향으로 유지한다.

```text
Docling
  → normalize.py
  → RawBlock sequence
  → policies/*
  → resolve_annotations.py
  → assemble.py
  → render.py + tokenize.py
  → Chunk sequence
```

이 경계에서 `normalize.py`는 “원본에 무엇이 있었는가”, `policies/*`는 “무엇처럼 보이는가”, `assemble.py`는 “Domain 판정 본문 범위를 어디까지로 할 것인가”, `render.py`는 “모델에 어떤 문맥을 보여줄 것인가”만 담당한다. 한 모듈이 앞 단계의 원본을 수정하거나 뒤 단계의 결정을 대신하지 않는다.

### 새 문서 사례를 추가하는 절차

기본적인 확장 단위는 아래 세 가지다.

```text
새 문서 fixture 추가
  + policies/<new_case>.py 추가 또는 기존 정책의 제한적 보강
  + PolicyRegistry 등록
  + 기대 annotation과 회귀 테스트 추가
```

예를 들어 한국 공고문은 `korean_notice.py`만 추가하고, 다단 PDF의 반복 머리글은 `repetition_noise.py`를 보강한다. 이 경우 `normalize.py`, `assemble.py`, 원본 참조 규칙을 바꾸지 않는다.

반대로 공통 모듈 변경은 다음 경우에만 검토한다.

- 새 사례를 표현하는 데 필요한 신호가 RawBlock 계약에 없음
- 동일 사례가 아니라 모든 문서의 읽기 순서·원본 참조·body/context 의미를 바꿔야 함
- 정책 충돌을 현재 Resolver 계약으로 표현할 수 없음

이는 새 케이스의 예외 규칙이 공통 흐름에 누적되는 것을 막고, 공통 계약을 확장해야 할 진짜 구조 변화를 구분하기 위한 기준이다.

`docling_raw`는 변환과 원본 직렬화만 소유한다. 파싱 품질·재시도 계층과 Domain/Unit 계층은 이 모듈 밖의 소비자이며, 계약을 통해 연결한다.

## 단계적 개발 방향

1. **계약 확립**: parse snapshot, known gap, RawBlock, body/context ref, disposition을 정의한다.
2. **최소 IR**: 정확히 한 번의 순회, 원본 참조, 표 payload 보존을 구현하고 누락·중복 테스트를 만든다.
3. **보수적 Chunk 기준선**: 문단·목록·표 경계와 `classification_text` 렌더링을 구현한다.
4. **Docling 비교**: native `HierarchicalChunker`/`HybridChunker`와 대표 문서에서 차이를 측정한다.
5. **후속 연동 검증**: Domain Mapping과 Unit segmentation 골든 테스트로 Chunk sequence가 경계 오류를 늘리지 않는지 확인한다.
6. **제한된 정책 확장**: 측정된 실패에만 독립 `StructurePolicy`와 fixture를 추가한다. 공통 순회·Assembler 변경은 기존 RawBlock 계약으로 표현할 수 없는 정보가 확인된 경우에만 검토한다.

## 미확정 사항

- Chunk 내부에서 Domain 전환이 의심될 때 즉시 재분할할지, Boundary Agent에 맡길지
- 일부 본문 누락 문서를 후속 Domain/Unit 처리에 전달할 조건
- OCR 품질 임계값과 재시도/검토의 소유 계층
- 이미지형 Office 문서, 차트 내부 텍스트, 발표자 노트의 초기 지원 범위
- 실제 Domain 판정 모델과 Unit 임베딩 모델의 토크나이저·입력 예산
- StructureProfile 충돌 우선순위와 표/슬라이드 복합 문서의 조립 정책

이 설계의 목표는 모든 문서를 완벽히 이해하는 청커가 아니라, 무엇을 읽었고 무엇을 읽지 못했는지 드러내면서 후속 Domain/Unit 파이프라인이 안전하게 사용할 수 있는 구조화된 Chunk sequence를 만드는 것이다.
