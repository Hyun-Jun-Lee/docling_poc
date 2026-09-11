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
- `samples/`: 실제 입력 문서. `parsed/`: 기존 변환 결과. 검증 목적으로 기존 파일을 덮어쓰지 말고 별도 임시 경로를 사용한다.
- `docs/`: 기술 조사와 확장 설계. 특히 `semantic_chunking_architecture_ko.md`와 `AI_READY_DATA_project_context (1).md`는 후속 구조화·Domain Mapping 작업 시 참고한다. 설계 문서의 기능을 이미 구현된 것으로 취급하지 않는다.

현재는 서비스, 임베딩·검색 파이프라인, Domain Mapping/Unit 생성까지 구현하지 않는다. 요청 없이 이러한 계층을 추가하지 않는다.

## 환경과 명령

Python **3.11**을 사용한다. `pyproject.toml`은 `>=3.11,<3.12`, `.python-version`은 `3.11`을 지정한다. 빌드 백엔드는 Hatchling이며 실행 명령은 `docling-poc = docling_poc.cli:main`이다.

저장소 루트에서 실행한다. 기존 가상환경이 있으면 재사용한다.

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

- PDF 기본 OCR은 `C:\Program Files\Tesseract-OCR\tesseract.exe`와 같은 폴더의 `tessdata`를 사용하는 Tesseract CLI다. 언어는 `kor`, `eng`, PSM은 3이다. `tika-config.json`과 경로·언어·PSM을 맞춘다. Tika PDF는 AUTO, 216 DPI RGB이며 두 도구의 OCR 영역 선택은 다르다. semantic 그림 OCR은 별도 RapidOCR 경로다. PDF 그림 분류 또는 설명을 활성화하면 `generate_picture_images`도 활성화한다.
- `build_docling_converter()`는 현재 작업 디렉터리의 `.env`를 `override=False`로 읽는다. `DOCLING_ARTIFACTS_PATH`로 사전 다운로드한 모델 경로를 지정하며 프로세스 환경변수가 우선한다. `.env.example`을 참고하고 실제 `.env`와 개인 경로를 커밋하지 않는다.
- semantic 그림 OCR의 `_build_image_ocr_converter()`는 별도 경로이며 현재 PDF 변환기의 `.env`/모델 경로 설정을 명시적으로 재사용하지 않는다. 양쪽에 같은 설정이 적용된다고 가정하지 않는다.
- semantic 그림 OCR은 명시적으로 켰을 때만 수행한다. `image.uri`의 base64 이미지, MIME 일치 여부와 인코딩을 검증하고 임시 파일은 정리한다. semantic 결과에는 base64를 복제하지 않는다.
- 그림 하나의 OCR 오류는 해당 노드의 `ocr.status="failed"`와 `error`로 남기고 나머지 문서 처리를 계속한다.
- 기본 semantic 그림 OCR은 **그림마다 새 변환기**를 만든다. 네이티브 종료 과정의 중단 문제를 피하기 위한 의도적인 동작이므로 단순 최적화 목적으로 공유 변환기로 바꾸지 않는다.
- Docling의 무거운 import와 모델 초기화는 해당 기능을 실행할 때 수행하는 구조를 유지한다. 실제 변환·OCR·그림 설명은 모델 다운로드와 상당한 실행 시간이 필요할 수 있으므로 단위 테스트와 구분한다.

## 변경과 검증 원칙

- 기존의 작은 함수, 타입 힌트, `pathlib.Path`, `Mapping` 기반 처리를 따른다. Ruff 설정은 Python 3.11, 줄 길이 100이다. 무관한 전체 파일 재포맷은 피한다.
- CLI는 인자·입출력 조정에 집중하고, 변환 로직은 `docling_raw.py`, 파생 구조화는 `semantic.py`에 둔다. 공개 API를 바꾸면 `__init__.py`와 README 예제도 확인한다.
- 동작 변경에는 관련 회귀 테스트를 추가하거나 수정한다. 문서만 바뀌는 경우 불필요한 테스트를 추가하지 않는다.
- 테스트에서는 `tmp_path`, `monkeypatch`, 가짜 변환기와 주입 가능한 `converter`/`chunker`/`picture_ocr`를 활용한다. 일부 기존 테스트는 실제 Docling 구성 객체를 import하므로 의존성 설치가 필요하지만 모델 추론은 단위 테스트에 끌어들이지 않는다.
- semantic 수정 시 읽기 순서, 제목 규칙의 일치·불일치, 원본 참조, 중첩 그룹, 표·그림·form 항목 보존과 잘못된 입력을 확인한다. OCR 수정 시 MIME/base64 검증, 실패 격리와 그림별 변환기 생성을 확인한다.
- 코드 변경 후 관련 pytest와 Ruff 검사를 수행한다. 실제 문서 변환이 필요한 변경은 적절한 샘플로 별도 확인하되 모델 다운로드 여부와 실행 환경을 고려한다.
- 기존 샘플·변환 결과를 일괄 재생성하지 않는다. 결과 보고에는 변경 내용, 실행한 검사와 미실행 이유 또는 남은 한계를 간단히 적는다.
