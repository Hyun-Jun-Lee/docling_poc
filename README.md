# Docling POC

이 프로젝트는 PDF, PowerPoint, Word 문서를 Docling으로 변환하고, Docling이 제공하는 원본 `DoclingDocument` 구조를 직접 살펴보기 위한 최소 POC입니다.

기본 JSON 출력은 `ConversionResult`의 변환 메타데이터와 `DoclingDocument`를 함께 담습니다. 문서 본문은 `document` 키 아래에 `DoclingDocument.export_to_dict()` 형식으로 저장되고, 루트에는 상태, 오류, 시간 측정, 신뢰도가 보존됩니다. Markdown 출력은 `DoclingDocument.export_to_markdown()` 결과입니다. `hierarchical-chunks` 출력은 Docling이 제공하는 `HierarchicalChunker`의 원본 `DocChunk` 결과입니다. `semantic-json`은 저장된 JSON의 `document` 본문 순서와 번호 체계를 바탕으로 섹션·문단·목록·표를 재구성한 파생 구조입니다.

## 설치

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## 사용

PDF 기본 OCR은 Windows의 `C:\Program Files\Tesseract-OCR\tesseract.exe`를
사용하며, 같은 설치 폴더의 `tessdata`에서 `kor`·`eng` 모델을 읽습니다.
페이지 분할 모드는 PSM 3입니다. `DOCLING_ARTIFACTS_PATH`는 기존처럼
layout·TableFormer·그림 분류 등 Docling 모델 경로로 사용합니다.

Tika는 `parse-tika.ps1`이 저장소의 `tika-config.json`을 자동으로 전달합니다.
같은 Tesseract 경로·언어·PSM을 사용하고 PDF 렌더링은 216 DPI RGB로 설정합니다.
Tika의 PDF OCR 전략은 `AUTO`이므로 텍스트가 충분한 페이지는 OCR을 생략할 수 있습니다.
Docling과 Tika의 OCR 영역 선택 방식은 서로 다르며 모든 페이지를 강제 OCR하지 않습니다.
저장된 JSON에 대한 `semantic-json --ocr-pictures`도 같은 Tesseract 설정을 사용하며, 새 결과의 `ocr.engine`은 `tesseract`입니다. 기존 JSON 결과는 자동으로 변경되지 않습니다.

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

기본 분류 모델은 `DocumentFigureClassifier-v2.5`이며 분류 결과는 상위 3개(`top_k=3`)로 제한합니다. 기본 설명 모델은 `HuggingFaceTB/SmolVLM-256M-Instruct`입니다. 첫 실행 시 필요한 모델이 자동으로 내려받아질 수 있으며, 오프라인 실행이나 초기 실행 시간을 제어하려면 미리 내려받을 수 있습니다.

```bash
docling-tools models download picture_classifier smolvlm
```

그림 분류와 설명 옵션은 PDF 표준 변환 전용입니다. `semantic-json`/`semantic-rules` 출력이나 Word·PowerPoint 입력에서는 사용할 수 없습니다. 분류 결과와 설명은 각 `PictureItem`의 메타데이터에 보존되며, JSON으로 내보낸 결과에도 포함됩니다. 그림 렌더링을 위해 해당 옵션 중 하나를 쓰면 picture image 생성도 함께 활성화됩니다.

Python에서 직접 사용할 수도 있습니다.

```python
from docling_poc import (
    convert_document,
    create_hierarchical_chunks,
    export_conversion_result,
    export_document,
    export_hierarchical_chunks,
)

result = convert_document(
    "samples/report.pdf",
    picture_classifier=True,
    picture_desc=True,
)
conversion_json = export_conversion_result(result)
document_markdown = export_document(result.document, output_format="markdown")
chunks = create_hierarchical_chunks(result.document)
chunk_json = export_hierarchical_chunks(chunks)

print(conversion_json["confidence"])
print(conversion_json["document"]["texts"])
print(document_markdown)
print(chunk_json[0]["text"])
```

## Tika 비교용 PowerShell 스크립트

Windows PowerShell 5.1 또는 PowerShell 7에서 아래 스크립트를 실행할 수 있습니다. 예시는 프로젝트 루트 기준이며, `-InputPath`와 `-OutputPath`에는 절대 경로 또는 현재 작업 디렉터리 기준 상대 경로를 지정합니다. 공백이 있는 경로는 따옴표로 감쌉니다.

### 문서 → 본문 포함 JSON

[`parse-tika.ps1`](parse-tika.ps1)은 Tika의 `--jsonRecursive`로 문서 본문과 메타데이터를 추출합니다. Java 17 이상과 Tika 4.0.0 배포본이 필요하며, 배포본은 별도로 준비해 다음 위치에 압축을 해제합니다. JAR만 옮기지 말고 `lib/` 등 배포본 전체 구조를 유지합니다.

```text
docling_poc/
├── parse-tika.ps1
└── tika-app-4.0.0/
    ├── tika-app-4.0.0.jar
    ├── lib/
    └── ... 배포본의 나머지 파일과 폴더
```

```powershell
.\parse-tika.ps1 `
    -InputPath ".\samples\pdf_test_sample.pdf" `
    -OutputPath ".\parsed\pdf.tika.json"

# DOCX와 PPTX도 입력 경로만 변경해 실행
.\parse-tika.ps1 -InputPath ".\samples\docx_test_sample.docx" -OutputPath ".\parsed\docx.tika.json"
.\parse-tika.ps1 -InputPath ".\samples\pptx_test_sample.pptx" -OutputPath ".\parsed\pptx.tika.json"
```

스크립트는 현재 PATH에서 Java를 찾고, 찾지 못하면 프로세스·사용자·시스템의 `JAVA_HOME`과 PATH를 확인합니다. Tika 위치는 스크립트 파일이 있는 디렉터리를 기준으로 찾습니다. 현재 버전과 폴더명은 `4.0.0`으로 고정되어 있습니다.

Java의 UTF-8 출력 바이트를 직접 저장하므로 PowerShell 파이프라인의 인코딩 변환으로 인한 한글 깨짐을 피합니다. 출력은 원본 문서와 내장 항목의 객체 배열이며, 원본 문서의 본문은 첫 번째 객체의 `tk:content`에 들어갑니다. 본문은 Tika 4.0.0의 기본 Markdown 형식입니다. 메타데이터만 출력하는 `--json`과 구분합니다. 진단 로그가 필요하면 실행 명령에 `-Verbose`를 추가합니다.

### Tika JSON → Markdown

[`tika-json-to-markdown.ps1`](tika-json-to-markdown.ps1)은 저장된 Tika JSON을 읽고 첫 번째 문서의 `tk:content`를 UTF-8 Markdown으로 저장합니다. 기존 버전의 `X-TIKA:content` 키도 지원합니다. 이 단계에서는 Java나 Tika를 실행하지 않습니다.

```powershell
.\tika-json-to-markdown.ps1 `
    -InputPath ".\parsed\pdf.tika.json" `
    -OutputPath ".\parsed\pdf.tika.md"
```

JSON 문자열의 `\n`이 실제 줄바꿈으로 복원되어 본문을 읽기 편해집니다. 내장 이미지·첨부파일 객체의 본문을 합치거나 이미지 파일을 따로 추출하지는 않습니다. 본문 문자열을 그대로 저장하는 스크립트이므로, HTML로 생성한 Tika JSON을 Markdown 문법으로 변환하는 기능은 없습니다. 본문 키가 없는 메타데이터 전용 JSON은 오류로 처리합니다.

두 스크립트 모두 출력 폴더를 자동으로 생성하고 입력·출력이 같은 경로이면 거부합니다. 기존 출력 파일은 작업이 성공했을 때 교체하며, 원본 입력은 수정하지 않습니다.

### Docling Markdown과 비교

같은 PDF를 Docling Markdown으로 변환한 뒤 VS Code에서 비교할 수 있습니다.

```powershell
docling-poc ".\samples\pdf_test_sample.pdf" --to markdown --out ".\parsed\pdf.docling.md"
code --diff ".\parsed\pdf.tika.md" ".\parsed\pdf.docling.md"
```

위 Docling 명령은 PDF를 다시 변환합니다. 현재 CLI는 저장된 Docling JSON을 Markdown으로 내보내는 모드를 제공하지 않습니다. 본문·읽기 순서는 Markdown으로 비교하고, 좌표·표 셀·원본 참조 등은 원본 JSON으로 별도 확인합니다.

## 산출물

### 변환 시간

기본 변환기를 만들 때 Docling의 프로세스 전역 설정인
`settings.debug.profile_pipeline_timings = True`를 활성화합니다. 이후 새로 변환한
기본 JSON에는 `timings` 아래에 Docling이 계측한 단계별 `times`(초)가 저장됩니다.
기존 JSON의 빈 `timings`는 다시 변환해야 채워집니다. 외부에서 `converter`를 직접
주입하는 경우에는 호출자가 프로파일링 설정을 관리합니다.

`timings`는 명령 실행부터 파일 저장 완료까지의 전체 시간이 아닙니다. 단계별 시간이
중첩되거나 병렬로 측정될 수 있으므로 전부 더해 총 소요시간으로 사용하지 않습니다.
Markdown과 청크 출력에는 변환 메타데이터가 포함되지 않으므로 시간 비교 시 기본 JSON을
보관하세요. 저장된 JSON의 semantic 변환은 별도 처리이며 이 계측 대상이 아닙니다.

- JSON: `ConversionResult`의 `status`, `errors`, `timings`, `confidence`와 `document` 아래 DoclingDocument의 `texts`, `tables`, `pictures`, `body`, `furniture`, `groups`, `pages`, provenance, bbox 등 원본 구조
- Markdown: DoclingDocument가 내보내는 문서 표현
- Hierarchical chunks: Docling `HierarchicalChunker`가 생성한 `DocChunk` 배열. 각 청크는 `text`, 제목 문맥, 원본 문서 항목과 provenance metadata를 포함
- Semantic JSON: `body.children`의 읽기 순서를 유지하며 번호 제목, 한글 하위 제목, 목록, 표를 섹션 트리로 재구성한 구조. 각 노드는 원본 Docling 항목의 `source_refs`를 보존. `--ocr-pictures`를 지정하면 `pictures[n].image.uri`의 base64 이미지를 임시 파일로 복원해 Docling Image + Tesseract로 인식하고, picture 노드에 OCR 텍스트를 추가한다. 사진 하나가 실패하면 해당 노드에 `ocr.status: "failed"`와 오류를 남기고 나머지 구조화는 계속한다. semantic JSON 입력에도 `--max-file-size`를 적용할 수 있다
- Semantic rules: 현재 한국어 공고문 규칙에 맞는지 JSON boolean으로 출력. 굵은 `1. 제목`과 `가. 제목` 형식이 함께 있어야 `true`

`ConversionResult`에는 변환 상태와 오류 정보도 포함됩니다. JSON/Markdown을 확인한 뒤 서비스 요구사항에 맞춰 구조 기반 청킹, 품질 관리, 임베딩 단계를 별도 모듈로 설계합니다.
