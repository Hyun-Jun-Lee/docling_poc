# Docling POC

이 프로젝트는 PDF, PowerPoint, Word 같은 비정형 문서를 Docling으로 분석한 뒤 downstream Domain/Unit 파이프라인이 사용할 수 있는 안정적인 중간 표현을 만드는 POC입니다.

첨부된 프로젝트 컨텍스트 기준 핵심 목표는 원문을 바로 RAG chunk로 쓰는 것이 아니라, Docling의 구조 추출 결과를 `NormalizedElement`와 `DocumentChunk` sequence로 변환하고 page/slide provenance, table, picture placeholder, OCR 품질 신호를 보존하는 것입니다.

## 설치

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## 사용

```bash
docling-poc samples/report.pdf --out parsed/report.json
docling-poc samples/deck.pptx --max-chunk-chars 1800
docling-poc samples/spec.docx --ocr-lang ko --ocr-lang en
```

Python에서 직접 사용할 수도 있습니다.

```python
from docling_poc import DoclingProcessConfig, process_document

processed = process_document(
    "samples/report.pdf",
    config=DoclingProcessConfig(ocr_languages=("ko", "en")),
)

for chunk in processed.chunks:
    print(chunk.chunk_id, chunk.page_numbers, chunk.text[:200])
```

## 산출물

- `asset_id`: 원본 파일 content hash 기반 deterministic id
- `elements`: Docling reading order를 따른 Heading, Paragraph, Table, Picture 등 정규화 요소
- `chunks`: Domain mapping 후보로 쓸 연속 처리 단위
- `profile`: table/image/page 수, 텍스트 커버리지, 한국어/비정상 문자 비율, OCR fallback 필요 여부
- `markdown`: Docling이 내보낸 전체 markdown preview

이 POC의 chunk는 최종 검색 단위가 아니라 Domain 판정용 입력입니다. 최종 Vector Search Point는 이후 동일 Domain chunk를 경계 보정해 결합한 Unit이 됩니다.
