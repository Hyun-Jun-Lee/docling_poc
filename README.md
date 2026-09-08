# Docling POC

이 프로젝트는 PDF, PowerPoint, Word 문서를 Docling으로 변환하고, Docling이 제공하는 원본 `DoclingDocument` 구조를 직접 살펴보기 위한 최소 POC입니다.

서비스 전용 `elements`, `chunks`, `profile` 같은 파생 구조는 만들지 않습니다. 이 프로젝트의 JSON 출력은 `DoclingDocument.export_to_dict()` 결과이며, Markdown 출력은 `DoclingDocument.export_to_markdown()` 결과입니다. 다만 `hierarchical-chunks` 출력은 Docling이 제공하는 `HierarchicalChunker`의 원본 `DocChunk` 결과입니다.

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
```

Python에서 직접 사용할 수도 있습니다.

```python
from docling_poc import (
    convert_document,
    create_hierarchical_chunks,
    export_document,
    export_hierarchical_chunks,
)

result = convert_document("samples/report.pdf")
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

`ConversionResult`에는 변환 상태와 오류 정보도 포함됩니다. JSON/Markdown을 확인한 뒤 서비스 요구사항에 맞춰 구조 기반 청킹, 품질 관리, 임베딩 단계를 별도 모듈로 설계합니다.
