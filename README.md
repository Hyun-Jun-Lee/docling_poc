# Docling POC

이 프로젝트는 PDF, PowerPoint, Word 문서를 Docling으로 변환하고, Docling이 제공하는 원본 `DoclingDocument` 구조를 직접 살펴보기 위한 최소 POC입니다.

기본 JSON 출력은 `DoclingDocument.export_to_dict()` 결과이며, Markdown 출력은 `DoclingDocument.export_to_markdown()` 결과입니다. `hierarchical-chunks` 출력은 Docling이 제공하는 `HierarchicalChunker`의 원본 `DocChunk` 결과입니다. `semantic-json`은 저장된 Docling JSON의 본문 순서와 번호 체계를 바탕으로 섹션·문단·목록·표를 재구성한 파생 구조입니다.

## 설치

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## 사용

```bash
docling-poc samples/report.pdf --out parsed/report.json
docling-poc samples/deck.pptx --to markdown --out parsed/deck.md
docling-poc samples/spec.docx --max-num-pages 10
docling-poc samples/report.pdf --to hierarchical-chunks --out parsed/report.chunks.json
docling-poc samples/report.pdf --picture-classifier --picture-desc --out parsed/report.enriched.json
docling-poc parsed/docx.docling.json --to semantic-json --out parsed/docx.semantic.json
docling-poc parsed/docx.docling.json --to semantic-json --ocr-pictures --out parsed/docx.semantic.ocr.json
docling-poc parsed/docx.docling.json --to semantic-rules
```

### PDF 그림 분류와 설명 추가

PDF 변환에서 `--picture-classifier`와 `--picture-desc`를 지정하면 그림별 분류와 자연어 설명을 `DoclingDocument`에 추가합니다. 각각 독립적으로 사용할 수 있습니다.

```bash
# 그림 유형만 분류
docling-poc samples/report.pdf --picture-classifier --out parsed/report.classified.json

# 그림 설명만 생성
docling-poc samples/report.pdf --picture-desc --out parsed/report.described.json

# 분류와 설명을 모두 생성
docling-poc samples/report.pdf --picture-classifier --picture-desc --out parsed/report.enriched.json
```

기본 분류 모델은 `DocumentFigureClassifier-v2.5`이고, 기본 설명 모델은 `HuggingFaceTB/SmolVLM-256M-Instruct`입니다. 첫 실행 시 필요한 모델이 자동으로 내려받아질 수 있으며, 오프라인 실행이나 초기 실행 시간을 제어하려면 미리 내려받을 수 있습니다.

```bash
docling-tools models download picture_classifier smolvlm
```

그림 분류와 설명 옵션은 PDF 표준 변환 전용입니다. `semantic-json`/`semantic-rules` 출력이나 Word·PowerPoint 입력에서는 사용할 수 없습니다. 분류 결과와 설명은 각 `PictureItem`의 메타데이터에 보존되며, JSON으로 내보낸 결과에도 포함됩니다. 그림 렌더링을 위해 해당 옵션 중 하나를 쓰면 picture image 생성도 함께 활성화됩니다.

Python에서 직접 사용할 수도 있습니다.

```python
from docling_poc import (
    convert_document,
    create_hierarchical_chunks,
    export_document,
    export_hierarchical_chunks,
)

result = convert_document(
    "samples/report.pdf",
    picture_classifier=True,
    picture_desc=True,
)
document_json = export_document(result.document, output_format="json")
document_markdown = export_document(result.document, output_format="markdown")
chunks = create_hierarchical_chunks(result.document)
chunk_json = export_hierarchical_chunks(chunks)

print(document_json["texts"])
print(document_markdown)
print(chunk_json[0]["text"])
```

## 산출물

- JSON: DoclingDocument의 `texts`, `tables`, `pictures`, `body`, `furniture`, `groups`, `pages`, provenance, bbox 등 원본 구조
- Markdown: DoclingDocument가 내보내는 문서 표현
- Hierarchical chunks: Docling `HierarchicalChunker`가 생성한 `DocChunk` 배열. 각 청크는 `text`, 제목 문맥, 원본 문서 항목과 provenance metadata를 포함
- Semantic JSON: `body.children`의 읽기 순서를 유지하며 번호 제목, 한글 하위 제목, 목록, 표를 섹션 트리로 재구성한 구조. 각 노드는 원본 Docling 항목의 `source_refs`를 보존. `--ocr-pictures`를 지정하면 `pictures[n].image.uri`의 base64 이미지를 임시 파일로 복원해 Docling Image + RapidOCR로 인식하고, picture 노드에 OCR 텍스트를 추가한다. 사진 하나가 실패하면 해당 노드에 `ocr.status: "failed"`와 오류를 남기고 나머지 구조화는 계속한다. semantic JSON 입력에도 `--max-file-size`를 적용할 수 있다
- Semantic rules: 현재 한국어 공고문 규칙에 맞는지 JSON boolean으로 출력. 굵은 `1. 제목`과 `가. 제목` 형식이 함께 있어야 `true`

`ConversionResult`에는 변환 상태와 오류 정보도 포함됩니다. JSON/Markdown을 확인한 뒤 서비스 요구사항에 맞춰 구조 기반 청킹, 품질 관리, 임베딩 단계를 별도 모듈로 설계합니다.
