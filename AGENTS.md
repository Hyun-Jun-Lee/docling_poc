# 프로젝트 작업 지침

이 지침은 저장소 전체에 적용한다. 사용자 요청에 맞춰 필요한 범위만 변경하고, 설명과 작업 결과는 기본적으로 한국어로 작성한다.

## 목적과 현재 구현

PDF·Word·PowerPoint를 Docling으로 변환하고 원본 구조를 확인하는 Python POC다. 네이티브 JSON/Markdown/HierarchicalChunker 출력과, 저장된 JSON을 한국어 공고문 규칙으로 재구성하는 semantic 출력을 제공한다.

- `README.md`: 설치, CLI와 Python API 사용법.
- `src/docling_poc/cli.py`: argparse 진입점, 옵션 검증, 변환 경로 선택, JSON/Markdown 출력과 파일 저장.
- `src/docling_poc/docling_raw.py`: Docling 변환기 구성, 변환 상태·오류 처리, 원본 내보내기와 네이티브 청킹.
- `src/docling_poc/semantic.py`: JSON 참조 해석, 제목·목록·표·그림의 semantic 트리 구성, 선택적 그림 OCR.
- `src/docling_poc/__init__.py`: 공개 Python API와 `__all__`.
- `tests/test_semantic.py`: semantic 구조뿐 아니라 CLI, 원본 JSON 내보내기, PDF 옵션과 모델 경로도 검증한다.
- `comparison.py`·`benchmark_worker.py`: 도구별 새 프로세스에서 Tika/Docling을 순차 반복 측정한다. `run-comparison.ps1`이 Windows 진입점이다.
- `comparison_data.py`·`comparison_report.py`: 저장된 결과의 모든 반복쌍을 비교하고 외부 리소스 없는 HTML을 만든다. 실행 방법과 지표 범위는 `docs/comparison-guide.md`, 회귀 테스트는 `tests/test_comparison.py`에 있다.
- `comparison_features.py`·`comparison_evidence.py`·`comparison_markup.py`: 도구별 추출 정보와 원본 발췌를 비교표로 구성한다. 회귀 테스트는 `tests/test_comparison_features.py`와 `tests/test_comparison_evidence.py`에 있다.
- `comparison_raw.py`: 비압축 원본 JSON과 기존 gzip 결과의 읽기 호환성을 제공한다. `tests/test_comparison_raw.py`에서 검증한다.
- `samples/`: 실제 입력 문서. `parsed/`: 기존 변환 결과. 검증 목적으로 기존 파일을 덮어쓰지 말고 별도 임시 경로를 사용한다.
- `docs/`: 기술 조사와 확장 설계. 후속 구조화·Domain Mapping 작업 시 `semantic_chunking_architecture_ko.md`를 참고한다. 설계 문서의 기능을 이미 구현된 것으로 취급하지 않는다.

현재는 서비스, 임베딩·검색 파이프라인, Domain Mapping/Unit 생성까지 구현하지 않는다. 요청 없이 이러한 계층을 추가하지 않는다.

## 환경과 명령

Python **3.11**을 사용한다. `pyproject.toml`은 `>=3.11,<3.12`, `.python-version`은 `3.11`을 지정한다. 빌드 백엔드는 Hatchling이며 실행 명령은 `docling-poc = docling_poc.cli:main`이다.

저장소 루트에서 실행한다. 기존 가상환경이 있으면 재사용한다.

`uv`를 사용하면 `uv sync --frozen --extra dev`로 잠금 버전과 개발 의존성을 설치한다. 아래 `pip install -e` 방식은 잠금 파일의 버전을 강제하지 않는다.

```powershell
# Windows PowerShell에서 최초 설치
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"

# 검증
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .

# 모델 추론 없이 CLI와 기존 JSON 처리 확인
.\.venv\Scripts\python.exe -m docling_poc.cli --help
.\.venv\Scripts\python.exe -m docling_poc.cli parsed/docx.docling.json --to semantic-rules

# 새 출력 폴더에 반복 비교 실행
.\run-comparison.ps1 -OutputPath reports\sample-comparison

# 이미 추출된 결과로 보고서만 재생성 (변환·OCR 없음)
.\.venv\Scripts\python.exe -m docling_poc.comparison_report reports\sample-comparison
```

POSIX 환경에서는 `python3.11 -m venv .venv`로 생성하고 위의 Python 경로를 `.venv/bin/python`으로 바꾼다. 활성화된 환경에서는 `python -m pytest`, `python -m ruff check .`, `docling-poc ...`로 실행할 수 있다.

의존성 선언은 `pyproject.toml`, 잠금 정보는 `uv.lock`에 있다. `requirements.txt`는 런타임 의존성을 내보낸 생성 파일이므로 직접 편집하지 않는다. 의존성을 변경할 때는 잠금 파일을 갱신하고 파일 상단에 기록된 다음 명령으로 다시 생성한다. 무관한 의존성 업그레이드는 피한다.

```bash
uv lock
uv export --format requirements.txt --frozen --no-hashes --no-emit-project --no-dev --output-file requirements.txt
```

## 유지해야 할 동작

### 원본 변환과 CLI

- 기본 `json` 출력은 `ConversionResult`의 메타데이터를 유지하고, `document`에는 `export_to_dict()` 결과를 넣는다. `status`, `errors`, `timings`, `confidence`를 잃지 않는다.
- `export_document(..., output_format="json")`은 문서 본문만 반환한다. CLI 기본 JSON과 이 API의 출력 계약을 혼동하지 않는다.
- Markdown은 `export_to_markdown()`, hierarchical chunks는 Docling `HierarchicalChunker`와 `DocChunk.model_dump(mode="json")`를 사용한다. 파생 semantic 규칙을 네이티브 출력에 적용하지 않는다.
- 변환은 `raises_on_error=False`로 호출하고 `success`와 `partial_success`를 허용한다. 실패 상태와 오류 정보를 숨기지 않는다.
- `--ocr-pictures`는 `semantic-json` 전용이다. `--picture-classifier`와 `--picture-desc`는 PDF의 일반 변환 출력에서만 허용하며 각각 독립적으로 동작한다.
- 입력·출력 경로가 같으면 거부한다. 파일 출력은 같은 디렉터리의 임시 파일에 쓴 뒤 `os.replace()`로 교체하는 방식을 유지한다.
- JSON은 UTF-8, `ensure_ascii=False`, 들여쓰기 2칸을 유지한다. `--out`이 없으면 stdout에 출력하며 결과에 진단용 출력을 섞지 않는다.
- `--max-file-size`는 일반 변환과 semantic JSON 입력 모두에 적용한다. `--max-num-pages`는 일반 변환에 전달되며 저장된 JSON을 자르는 기능은 아니다.
- 확장자 검사에는 `.pdf`, `.docx`, `.doc`, `.pptx`, `.ppt`가 포함되지만 실제 변환 가능 여부는 설치된 Docling의 `InputFormat` 지원에 달려 있다. 구형 Office 형식 지원을 무조건 보장하지 않는다.

### Semantic 구조

- 입력은 문서 본문 JSON과 `document`로 감싼 변환 결과 JSON을 모두 허용한다.
- 읽기 순서는 `body.children`을 기준으로 삼는다. `texts` 배열 순서로 재정렬하지 않는다.
- 파생 노드의 `source_refs`를 유지해 원본으로 역추적할 수 있게 한다. 중첩 그룹의 참조와 텍스트 순서도 보존한다.
- 현재 스키마는 `docling_poc.semantic_document`, 버전은 `1.1.0`이다. 출력 계약 변경 시 호환성, 버전과 테스트를 함께 검토한다.
- 굵은 숫자 제목(`1. 제목`)과 한글 하위 제목(`가. 제목`)이 모두 있어야 semantic 규칙이 활성화된다. 한글 하위 제목은 굵지 않아도 된다. 규칙이 맞지 않으면 제목·목록처럼 보이는 텍스트도 일반 문단으로 유지한다.
- 현재 목록 표기는 `(1)`, `①`~`⑳`, `‧`, `•`다. 규칙 확장 시 일반 번호 문장이 잘못 구조화되지 않는 사례도 검증한다.
- 표의 `data`, 그림의 `captions`/`references`, form/key-value 항목의 원본 데이터를 보존한다.
- 잘못된 참조·음수 또는 범위 밖 인덱스·잘못된 JSON 타입은 명시적인 오류로 처리한다. 현재 그룹 병합은 텍스트와 중첩 텍스트 그룹을 대상으로 하며 비텍스트 자식은 오류다. 지원 범위를 넓힐 때 내용을 조용히 누락시키지 않는다.

### OCR과 모델

- PDF는 `heading_hierarchy_options.enabled=True`와 `generate_parsed_pages=True`로 제목 계층 추론과 중간 페이지 정보를 활성화한다. Word·PowerPoint에는 PDF 옵션을 적용하지 않고 네이티브 백엔드 기본 설정을 사용한다. 기존 PDF 결과는 보고서만 재생성해도 바뀌지 않는다.
- PDF 기본 OCR은 `C:\Program Files\Tesseract-OCR\tesseract.exe`와 같은 폴더의 `tessdata`를 사용하는 Tesseract CLI다. 언어는 `kor`, `eng`, PSM은 3이다. `tika-config.json`과 경로·언어·PSM을 맞춘다. Tika PDF는 AUTO, 216 DPI RGB이며 두 도구의 OCR 영역 선택은 다르다. semantic 그림 OCR도 `build_tesseract_ocr_options()`를 통해 PDF와 동일한 Tesseract 설정을 사용한다. 성공 결과의 `ocr.engine`은 `tesseract`다. PDF 그림 분류 또는 설명을 활성화하면 `generate_picture_images`도 활성화한다.
- 반복 비교는 DOCX·PPTX에만 Tika `skipOcr=true`를 적용하며 PDF OCR은 유지한다. Docling Office에는 추가 이미지 OCR을 적용하지 않는다. 실제 Tika 설정은 `execution-config/tika-pdf.json`, `tika-office.json`, manifest의 `tika_effective_configs`와 Tika 실행 메타데이터에 기록한다. 재개 시 저장된 설정 변경을 거부한다.
- 이 Office OCR 정책은 비교 실행 전용이다. 루트 `tika-config.json`을 사용하는 `parse-tika.ps1`에는 자동 적용되지 않는다. OCR을 꺼도 Tika의 내장 리소스 파싱은 유지되며, 원본 JSON의 `TesseractOCRParser` 이름만으로 OCR 실행 여부를 단정하지 않는다.
- `build_docling_converter()`는 현재 작업 디렉터리의 `.env`를 `override=False`로 읽는다. `DOCLING_ARTIFACTS_PATH`로 사전 다운로드한 모델 경로를 지정하며 프로세스 환경변수가 우선한다. `.env.example`을 참고하고 실제 `.env`와 개인 경로를 커밋하지 않는다.
- semantic 그림 OCR의 `_build_image_ocr_converter()`는 별도 경로이며 현재 PDF 변환기의 `.env`/모델 경로 설정을 명시적으로 재사용하지 않는다. 양쪽에 같은 설정이 적용된다고 가정하지 않는다.
- semantic 그림 OCR은 명시적으로 켰을 때만 수행한다. `image.uri`의 base64 이미지, MIME 일치 여부와 인코딩을 검증하고 임시 파일은 정리한다. semantic 결과에는 base64를 복제하지 않는다.
- 그림 하나의 OCR 오류는 해당 노드의 `ocr.status="failed"`와 `error`로 남기고 나머지 문서 처리를 계속한다.
- 기본 semantic 그림 OCR은 **그림마다 새 변환기**를 만든다. 네이티브 종료 과정의 중단 문제를 피하기 위한 의도적인 동작이므로 단순 최적화 목적으로 공유 변환기로 바꾸지 않는다.
- Docling의 무거운 import와 모델 초기화는 해당 기능을 실행할 때 수행하는 구조를 유지한다. 실제 변환·OCR·그림 설명은 모델 다운로드와 상당한 실행 시간이 필요할 수 있으므로 단위 테스트와 구분한다.

### 비교 결과와 보고서

- `comparison_markdown.py`는 Markdown 표와 기능별 발췌를 렌더링한다. `report.md`에서는 도구별 Markdown·JSON 원문 비교를 제외한다. 측정값·실행 상태·기능별 발췌·운영 확장성은 유지하며 HTML 원문 보기와 저장된 원본은 변경하지 않는다. 발췌의 코드 울타리·HTML이 보고서 구조를 깨뜨리지 않도록 보존한다. 관련 테스트는 `tests/test_comparison_markdown.py`에 있다.

- 새 원본은 UTF-8, `ensure_ascii=False`, 들여쓰기 2칸의 비압축 `raw.pretty.json`으로 저장한다. 비교 worker는 비유한 수를 JSON `null`로 변환한다. 기존 `raw.json.gz` 읽기를 유지하고 두 파일이 있으면 비압축 파일을 우선한다. Tika의 `tika-output.json`도 보존한다.
- 보고서는 저장된 원본·스냅샷을 읽어 `index.html`, `report.md`, `analysis.json`을 생성한다. 보고서만 재생성할 때 변환·OCR을 실행하거나 기존 원본·스냅샷·측정값을 변경하지 않는다.
- `analysis.json`은 현재 버전 4이며 `feature_comparison`을 포함한다. 스냅샷 버전과 별개다. 삭제된 수동 구조 검토 UI와 `structure_review`는 복원하지 않으며, 기존 검토 JSON과 `feature-cards.json`은 읽거나 변경하지 않는다.
- 결과 보기는 도구별 세 버튼(Markdown 원문·스타일 적용·JSON 원본)으로 전환한다. 원본 텍스트와 JSON은 HTML 이스케이프하며, Markdown 스타일 보기에서도 문서의 HTML·스크립트를 실행하거나 외부 이미지·리소스를 요청하지 않는다.
- 「추출 정보 비교」는 제목과 표만 표시한다. 표 앞의 안내 문단과 도구별 회차·상태 문구를 다시 추가하지 않는다. 표 안의 출처·생략 안내·확인 불가 표시는 유지한다. 각 도구의 첫 완전 성공 회차(없으면 첫 부분 성공)에서 원본을 발췌하며, 관찰 결과를 도구 전체의 지원 여부나 정확도로 해석하지 않는다.
- 「측정 기준」 섹션 대신 전체·내부 시간 차이와 반복 일관성이 정확도가 아니라는 설명을 「측정 결과」 표 아래에 작게 표시한다. 하단 「대용량 처리 운영 확장성」은 운영 방식 설명이며 현재 실행의 실측 결과가 아니다. 「추가 검증 항목」은 표시하지 않는다.

## 변경과 검증 원칙

- 반복 비교에서 전체 시간(프로세스 시작~출력 저장·종료)과 도구 내부 시간을 분리한다. Tika 루트 parse time에 하위 리소스 시간을 더하지 않는다. 정답 데이터 없는 텍스트 차이율을 정확도라고 표기하지 않는다.
- 비교 실행은 기본 도구별 5회, 순차 실행과 순서 교대다. 텍스트·구조와 좌표·신뢰도를 분리하며 실패를 일치로 취급하지 않는다. Tesseract 설정이 같아도 OCR 영역 선택과 Office 추출 경로가 같다고 설명하지 않는다.
- 시간 통계는 완전 성공만 사용한다. 부분 성공은 상태를 명시하고 반복 비교에 포함한다. `--resume`은 미기록 회차만 실행하며 기록된 실패는 재시도하지 않는다. 측정 코드·설정·반복 횟수·스레드·JAR·패키지·기록된 모델과 언어 데이터·실행 파일 버전의 재개 검증을 유지한다.
- Docling `pipeline_total`은 입력 백엔드 초기화를 제외하고, Tika 루트 시간은 내장 리소스 처리를 포함한다. 전체 시간에는 초기화·저장·종료가 포함되며 보고서 생성은 제외한다. 현재 새 프로세스 반복 결과를 예열된 서버 처리량으로 설명하지 않는다. CPU/OpenMP 스레드 설정이 JVM 전체 자원 제한과 같다고 가정하지 않는다.
- `reports/`와 `tmp/`는 Git 제외 대상이다. 사내 입력 복사본과 추출 전문이 포함된 결과를 샘플 산출물로 착각해 커밋하지 않는다. 공개 샘플 산출물도 명시적으로 선택한다.

- 기존의 작은 함수, 타입 힌트, `pathlib.Path`, `Mapping` 기반 처리를 따른다. Ruff 설정은 Python 3.11, 줄 길이 100이다. 무관한 전체 파일 재포맷은 피한다.
- CLI는 인자·입출력 조정에 집중하고, 변환 로직은 `docling_raw.py`, 파생 구조화는 `semantic.py`에 둔다. 공개 API를 바꾸면 `__init__.py`와 README 예제도 확인한다.
- 동작 변경에는 관련 회귀 테스트를 추가하거나 수정한다. 문서만 바뀌는 경우 불필요한 테스트를 추가하지 않는다.
- 테스트에서는 `tmp_path`, `monkeypatch`, 가짜 변환기와 주입 가능한 `converter`/`chunker`/`picture_ocr`를 활용한다. 일부 기존 테스트는 실제 Docling 구성 객체를 import하므로 의존성 설치가 필요하지만 모델 추론은 단위 테스트에 끌어들이지 않는다.
- semantic 수정 시 읽기 순서, 제목 규칙의 일치·불일치, 원본 참조, 중첩 그룹, 표·그림·form 항목 보존과 잘못된 입력을 확인한다. OCR 수정 시 MIME/base64 검증, 실패 격리와 그림별 변환기 생성을 확인한다.
- 코드 변경 후 관련 pytest와 Ruff 검사를 수행한다. 실제 문서 변환이 필요한 변경은 적절한 샘플로 별도 확인하되 모델 다운로드 여부와 실행 환경을 고려한다.
- 기존 샘플·변환 결과를 일괄 재생성하지 않는다. 결과 보고에는 변경 내용, 실행한 검사와 미실행 이유 또는 남은 한계를 간단히 적는다.
