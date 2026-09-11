# Tika · Docling 반복 비교

에이전트 없이 실행하는 Windows용 비교 도구다. PDF/DOCX/PPTX를 각 도구로 5회씩 새 프로세스에서 순차 추출하고, 저장된 결과만으로 한국어 HTML 보고서를 생성한다. 원본 문서나 추출 결과를 외부로 전송하는 기능은 없다.

## 실행

저장소 루트에서 실행한다. 기존 `.venv`에 잠금 파일의 의존성이 설치되어 있어야 한다. Java, `tika-app-4.0.0/tika-app-4.0.0.jar`, Tesseract 및 `kor`, `eng`, `osd` 언어 데이터, `.env`의 로컬 Docling 모델 경로가 필요하다. 현재 OCR 경로는 `C:\Program Files\Tesseract-OCR`이며 `tika-config.json`과 `docling_raw.py`에서 동일하게 설정한다. 새 패키지나 모델을 다운로드하며 측정하지 않도록 Hugging Face offline 모드를 강제한다.

```powershell
# 샘플 3종 × 도구 2종 × 5회 = 30회
.\run-comparison.ps1 -OutputPath reports\sample-comparison

# 사내 문서 폴더: 하위 폴더까지 PDF/DOCX/PPTX 탐색
.\run-comparison.ps1 -InputPath D:\internal-samples -OutputPath reports\internal-comparison

# 중단된 실행의 미기록 회차만 이어서 실행
.\run-comparison.ps1 -OutputPath reports\internal-comparison -Resume

# 변환 없이 HTML만 다시 생성
.\.venv\Scripts\python.exe -m docling_poc.comparison_report reports\internal-comparison

# 문서 전문·분석 수치를 담은 단일 HTML도 생성 (파일 링크는 제거)
.\.venv\Scripts\python.exe -m docling_poc.comparison_report reports\sample-comparison --standalone docs\reports\sample-comparison.html
```

Python으로 직접 실행할 수도 있다.

```powershell
.\.venv\Scripts\python.exe -m docling_poc.comparison --input samples --output reports\sample-comparison --repeat 5 --threads 4 --timeout 1800
```

`index.html`을 브라우저로 연다. 외부 CDN·서버·LLM이 필요 없다. HTML에는 요약 표와 각 도구의 첫 성공 실행 Markdown을 나란히 표시한다. 성공이 없으면 첫 부분 성공을 표시하고 상태를 명시한다. Tika는 최상위 문서의 Markdown, Docling은 네이티브 Markdown 출력이며, 기본적으로 Markdown 원문을 표시하며, 각 도구의 토글 버튼으로 스타일 적용과 원문 보기를 전환한다. 이 기능은 run-comparison.ps1로 새로 생성하는 보고서에도 자동 포함된다. 굵게·제목·표 구분자를 직접 확인할 수 있지만 JSON의 모든 속성을 보존하는 형식은 아니다. 실행별 수치·좌표·신뢰도 비교는 `analysis.json`, 환경과 시간 기록은 `manifest.json`에 유지한다. 사내 실행에서는 입력 폴더와 새 출력 폴더만 지정하면 된다.

`--standalone` 공유본은 HTML 하나만으로 읽을 수 있으며 별도 파일 링크를 제거한다. 실행 로그나 원본 JSON 자체를 포함하는 압축 묶음은 아니다. 현재 저장소의 공개 샘플 실행 결과는 `docs/reports/sample-comparison.html`에 보관한다.

## 반복과 재개

- 같은 입력의 실행 순서를 Tika→Docling, Docling→Tika로 교대한다. 동시에 다른 무거운 작업을 실행하지 않는 것이 측정 조건 유지에 필요하다.
- 매번 새 Python 작업 프로세스를 사용하며 Tika는 그 안에서 새 JVM을 실행한다. OS 파일 캐시를 비우지 않고 1회차도 통계에 포함한다. 별도 실험을 했다면 그 이력도 결과 해석에 고려해야 한다.
- Docling은 CPU와 기본 4스레드를 명시한다. OpenMP 환경변수도 설정하지만 JVM 전체 스레드 수를 4로 제한하는 것은 아니다.
- 기본 제한 시간은 도구·문서·회차당 1,800초다. 초과하면 해당 프로세스 트리를 종료하고 실패를 기록한 뒤 다음 실행으로 넘어간다.
- 실패나 부분 성공이 있으면 최종 종료 코드는 1이다. 보고서는 그대로 생성한다. 중간 저장된 기록으로도 보고서를 생성할 수 있다.
- `--resume`은 기록된 실패를 재시도하지 않는다. 미기록 회차만 수행하고 중단 당시 파일도 별도 보존한다. 실패를 새 조건에서 다시 측정하려면 새 출력 폴더를 사용한다.
- 재개 시 실행 코드·Tika 설정/JAR·패키지 버전·기록된 모델/언어 데이터 해시·Java/Tesseract 버전을 검사한다. 다른 PC나 설정의 결과를 한 묶음으로 합치지 않는다. 운영체제 상태, CPU 부하 등 모든 환경을 자동으로 같게 만들지는 않는다.

## 수치 정의

전체 시간은 작업 프로세스 시작부터 모델 초기화, 추출, 원본 JSON 압축/Markdown 저장, 프로세스 종료까지다. 비교용 JSON과 HTML 생성은 제외한다. 내부 시간은 Docling `pipeline_total.times` 합계와 Tika 루트(인덱스 0)의 `tk:parse-time-millis`다. 두 내부 시간의 범위는 같지 않으며 하위 Tika 리소스 시간을 더하지 않는다.

각 도구의 5개 결과에서 가능한 10쌍을 모두 비교한다. 실패는 제외하고 부분 성공은 상태를 명시한 채 비교한다. 시간 요약에는 완전 성공만 포함한다. 텍스트 편집거리는 정확한 Levenshtein 거리이며 차이율은 긴 텍스트 길이로 나눈 백분율이다. 정답 데이터가 없으므로 정확도나 CER로 표기하지 않는다.

비교용 JSON에서는 Unicode NFC와 줄바꿈만 통일한다. 공백과 순서를 보존한다. Docling의 본문 참조 순서·헤더/푸터·미연결 내용·표 셀을 반영하고 Tika는 루트 및 내장 리소스의 `tk:content`를 순서대로 포함한다. 따라서 도구 간 수치는 Markdown 표기와 내용 중복 등 출력 형식 차이도 포함한다. 두 도구의 구조 스키마가 달라 도구 간 구조 일치율은 계산하지 않는다.

Docling 좌표·charspan 및 confidence는 내용·구조와 별도로 비교한다. 좌표는 페이지·종류·텍스트·레이어가 양쪽에서 유일하게 대응하는 항목에 한정하며 대응 불가/중복 개수를 공개한다. Tika가 제공하지 않는 수치는 0이 아니라 미제공이다. 비교용 구조는 원본 JSON 전체를 대신하는 스키마가 아니며 모든 필드를 비교하지 않는다. 원본은 `raw.json.gz`에 보존한다. JSON 비표준 NaN/Infinity만 null로 변환한다.

두 도구에 Tesseract kor/eng 및 PSM 3을 설정해도 OCR 영역 선택과 전처리는 다르다. Tika PDF는 AUTO·216 DPI RGB, Docling은 기본 영역 선택·scale 3이다. Office는 네이티브 추출 경로를 사용하며 별도 그림 OCR을 추가하지 않는다. 따라서 동일 OCR 입력에 대한 엔진 벤치마크가 아니라 각 문서 추출 파이프라인의 결과 비교다.

## 보관 파일

`manifest.json`은 입력 SHA-256, 환경·모델 해시, 설정, 실행 상태와 시간을 보관한다. `analysis.json`은 모든 비교쌍의 수치다. 문서별 폴더에 입력 복사본과 각 실행의 `raw.json.gz`, `content.md`, `snapshot.json`, `worker.log`, `run.json`이 있다. Tika의 압축 전 출력도 보존한다.

`reports/`와 `tmp/`는 Git에서 기본 제외한다. 보고서에는 입력 복사본과 추출 전문이 있으므로 공개 샘플 보고서만 명시적으로 선택하여 공유한다. 사내 문서 결과는 사내에서 생성·보관한다.
