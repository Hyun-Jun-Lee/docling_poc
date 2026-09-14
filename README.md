# Docling POC

이 프로젝트는 PDF, PowerPoint, Word 문서를 Docling으로 변환하고 원본 `DoclingDocument` 구조를 살펴보는 Python POC입니다. Tika와 Docling의 반복 추출 결과, 소요시간, 추출 정보 차이를 비교하는 HTML·Markdown 보고서도 제공합니다. 서비스 운영·임베딩·검색 파이프라인은 구현 범위에 포함하지 않습니다.

기본 JSON 출력은 `ConversionResult`의 변환 메타데이터와 `DoclingDocument`를 함께 담습니다. 문서 본문은 `document` 키 아래에 `DoclingDocument.export_to_dict()` 형식으로 저장되고, 루트에는 상태, 오류, 시간 측정, 신뢰도가 보존됩니다. Markdown 출력은 `DoclingDocument.export_to_markdown()` 결과입니다. `hierarchical-chunks` 출력은 Docling이 제공하는 `HierarchicalChunker`의 원본 `DocChunk` 결과입니다. `semantic-json`은 저장된 JSON의 `document` 본문 순서와 번호 체계를 바탕으로 섹션·문단·목록·표를 재구성한 파생 구조입니다.

## 설치

Python **3.11**을 사용합니다. 저장소 루트에서 실행하며 기존 `.venv`가 있으면 재사용합니다.
`uv`를 사용하는 경우 잠금 파일의 버전으로 설치할 수 있습니다.

```powershell
uv sync --frozen --extra dev
```

Windows에서 `venv`와 `pip`로 설치하려면 다음 명령을 사용합니다. 이 방식은 잠금 파일의 버전을 강제하지 않습니다.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\Activate.ps1
```

POSIX 환경에서는 다음과 같이 설치합니다. 기본 OCR 경로는 Windows용이므로 다른 환경에서는 Tesseract 실행 파일과 언어 데이터 경로를 맞춰야 합니다.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

`.env.example`을 참고해 저장소 루트의 `.env`에 `DOCLING_ARTIFACTS_PATH`를 지정할 수 있습니다. 일반 변환기는 현재 작업 디렉터리의 `.env`를 읽으며, 이미 지정한 환경변수가 우선합니다. 실제 `.env`와 개인 모델 경로는 커밋하지 않습니다.

## 사용

PDF 기본 OCR은 Windows의 `C:\Program Files\Tesseract-OCR\tesseract.exe`를
사용하며, 같은 설치 폴더의 `tessdata`에서 `kor`·`eng` 모델을 읽습니다.
페이지 분할 모드는 PSM 3입니다. `DOCLING_ARTIFACTS_PATH`는 기존처럼
layout·TableFormer·그림 분류 등 Docling 모델 경로로 사용합니다.

PDF 제목 계층 추론은 기본으로 활성화합니다. Docling의 북마크·번호·글꼴 정보를
사용해 제목 `level`을 정하며, 근거가 부족한 제목은 기존 수준을 유지합니다.
글꼴 분석을 위해 `generate_parsed_pages=True`로 중간 페이지 정보를 보존하므로
메모리 사용량이 늘어날 수 있습니다. DOCX·PPTX는 기존 네이티브 추출 경로를 사용합니다.
이 설정은 새 PDF 변환부터 적용되며, 기존 결과는 보고서 재생성만으로 바뀌지 않습니다.

Tika는 `parse-tika.ps1`이 저장소의 `tika-config.json`을 자동으로 전달합니다.
같은 Tesseract 경로·언어·PSM을 사용하고 PDF 렌더링은 216 DPI RGB로 설정합니다.
Tika의 PDF OCR 전략은 `AUTO`이므로 텍스트가 충분한 페이지는 OCR을 생략할 수 있습니다.
Docling과 Tika의 OCR 영역 선택 방식은 서로 다르며 모든 페이지를 강제 OCR하지 않습니다.
`parse-tika.ps1`은 Office에도 루트 설정을 그대로 사용하므로 내장 이미지 OCR이 실행될 수 있습니다. 아래의 **반복 비교 실행**은 별도 Office 설정으로 Tika OCR을 끕니다.
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

## Tika와 Docling 반복 비교

PDF/DOCX/PPTX를 도구별 기본 5회씩 순차 추출하고, 회차마다 도구 실행 순서를 교대합니다. 매번 새 작업 프로세스를 시작하며 Tika는 새 JVM을 실행합니다. 모델은 미리 준비해야 하며 비교 실행에서는 Hugging Face 오프라인 모드를 강제합니다.

```powershell
# samples의 문서를 비교하고 새 출력 폴더에 저장
.\run-comparison.ps1 -OutputPath reports\sample-comparison

# 지정한 폴더의 문서 비교
.\run-comparison.ps1 -InputPath D:\internal-samples -OutputPath reports\internal-comparison

# 미기록 회차만 재개 (기록된 실패는 재시도하지 않음)
.\run-comparison.ps1 -OutputPath reports\internal-comparison -Resume

# 이미 추출된 결과로 보고서만 재생성
.\.venv\Scripts\python.exe -m docling_poc.comparison_report reports\internal-comparison

# 파일 링크를 제거한 단일 HTML 공유본도 생성
.\.venv\Scripts\python.exe -m docling_poc.comparison_report reports\internal-comparison --standalone reports\internal-comparison-share.html
```

`-Repeat`(기본 5), `-TimeoutSeconds`(회차당 기본 1800초), `-Threads`(기본 4)를 조정할 수 있습니다. 재개 시 원래 반복 횟수·스레드 수를 사용해야 하며 코드·설정·의존성 등의 변경을 검사합니다. 조건을 바꿨다면 새 출력 폴더를 사용합니다.

### OCR과 측정 범위

- **PDF:** 두 도구 모두 Tesseract `kor`·`eng`, PSM 3을 사용합니다. Tika는 AUTO·216 DPI RGB이며 OCR 영역 선택과 전처리는 Docling과 다릅니다.
- **DOCX·PPTX:** Tika에 `skipOcr=true`를 적용합니다. Docling도 추가 이미지 OCR 없이 Office 네이티브 백엔드를 사용합니다. Tika의 내장 리소스·이미지 메타데이터 처리는 유지되므로 모든 추출 범위가 동일해지는 것은 아닙니다.
- **전체 소요시간:** 작업 프로세스 시작부터 초기화·추출·원본 저장·종료까지입니다. 비교 분석과 HTML 생성 시간은 제외합니다.
- **내부 파싱 시간:** Tika 루트 파싱 시간과 Docling `pipeline_total`입니다. 입력 백엔드 초기화·내장 리소스 처리 등 포함 범위가 다르며, Tika 하위 리소스 시간을 루트 시간에 더하지 않습니다.
- **반복 일관성:** 같은 도구의 결과 간 텍스트·구조 동일 여부입니다. 정확도를 뜻하지 않습니다. 시간 통계에는 완전 성공만 포함합니다.

현재 측정은 새 프로세스의 반복 실행입니다. Tika Server·docling-serve의 상시 운영 처리량이나 동일 CPU·메모리 한도에서의 병렬 성능 측정은 아닙니다.

### 보고서와 저장 파일

보고서 생성 명령은 `index.html`과 `report.md`를 함께 저장합니다. 생성된 `index.html`을 브라우저로 엽니다. 외부 CDN이나 별도 서버는 필요하지 않습니다.

- **측정 결과:** 도구별 소요시간과 반복 일관성, 실행 상태를 표시합니다.
- **결과 보기:** Markdown 원문·스타일 적용·JSON 원본을 도구별 버튼으로 전환합니다.
- **추출 정보 비교:** 요소 분류, 제목 수준, 그룹·계층, 서식, 표 구조, 원본 위치, 메타데이터, 내장 리소스의 실제 원본 발췌를 나란히 표시합니다. 각 도구의 첫 완전 성공 회차를 사용하며, 없으면 첫 부분 성공을 사용합니다. 현재 문서의 관찰 결과이며 도구 전체의 기능 지원 여부나 정확도 평가는 아닙니다.
- **대용량 처리 운영 확장성:** 여러 문서의 API 처리·병렬 확장·자원 관리 차이를 설명합니다. 현재 실행의 실측 결과는 아닙니다.

| 파일·폴더 | 내용 |
|---|---|
| `report.md` | 측정 결과, 도구별 Markdown 원문·JSON 앞부분 약 1/3 발췌, 기능별 추출 정보, 운영 확장성 |
| `manifest.json` | 입력·환경·설정·해시와 회차별 상태·시간 |
| `analysis.json` | 반복쌍 비교와 추출 정보 비교. 현재 스키마 버전 4 |
| `execution-config/` | 실제 전달한 PDF·Office용 Tika 설정 |
| `execution-code/` | 측정에 사용한 코드 사본 |
| `document-*/input/` | 입력 문서 복사본 |
| 도구별 회차 폴더 | `raw.pretty.json`, `content.md`, `snapshot.json`, `run.json`, `worker.log` |

새 원본 결과는 UTF-8·한글 유지·들여쓰기 2칸의 비압축 `raw.pretty.json`으로 저장합니다. Tika의 CLI 출력 `tika-output.json`도 보존합니다. 기존 `raw.json.gz`는 읽기 호환성을 유지하며, 두 파일이 있으면 `raw.pretty.json`을 우선합니다.

Markdown 보고서의 JSON은 들여쓰기한 문자열의 문자 수 기준 앞부분 약 1/3만 표시하고 생략량을 안내합니다. 잘린 발췌이므로 유효한 JSON이 아닐 수 있으며 원본 JSON 파일과 HTML의 전체 JSON 보기는 유지합니다. Markdown 본문과 기능별 발췌는 기존 범위를 유지합니다.

Markdown 보고서는 도구별 결과와 기능별 발췌를 소제목·코드 블록으로 표시하며 버튼이나 스타일 전환은 제공하지 않습니다. 원본 안의 HTML과 이미지 참조는 코드 블록에 보존합니다. `--standalone`은 추가 HTML 공유본만 지정하며 `report.md`는 원래 결과 폴더에 저장합니다.

보고서만 재생성하면 복원된 추출 정보 비교표도 표시됩니다. 기존 OCR 결과·측정 시간·스냅샷은 바뀌지 않습니다. 수동 구조 검토 도구는 제공하지 않습니다.

`reports/`와 `tmp/`는 Git 제외 대상입니다. 보고서·단일 HTML에는 문서 전문이 포함될 수 있으므로 사내 결과는 사내에서 보관합니다. 상세 지표와 제약은 [비교 실행 안내](docs/comparison-guide.md)를 참고하세요.

## 검증

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
```

단위 테스트는 실제 모델 추론과 구분합니다. 실제 변환을 확인할 때는 새 출력 경로를 사용해 기존 샘플 결과를 덮어쓰지 않습니다.
