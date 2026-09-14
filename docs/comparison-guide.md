# Tika · Docling 반복 비교

에이전트 없이 실행하는 Windows용 비교 도구다. PDF/DOCX/PPTX를 각 도구로 5회씩 새 프로세스에서 순차 추출하고, 저장된 결과만으로 한국어 HTML·Markdown 보고서를 생성한다. 원본 문서나 추출 결과를 외부로 전송하는 기능은 없다.

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

`index.html`과 `report.md`가 함께 생성된다. `index.html`을 브라우저로 연다. 외부 CDN·서버·LLM이 필요 없다. HTML에는 요약 표와 각 도구의 첫 성공 실행 Markdown을 나란히 표시한다. 성공이 없으면 첫 부분 성공을 표시하고 상태를 명시한다. Tika는 최상위 문서의 Markdown, Docling은 네이티브 Markdown 출력이며, 기본적으로 Markdown 원문을 표시하며, 각 도구의 세 버튼으로 Markdown 원문·스타일 적용·JSON 원본 보기를 전환한다. 선택된 버튼을 강조하며 도구별 선택은 독립적이다. JSON은 같은 대표 회차의 `raw.pretty.json`(없으면 기존 `raw.json.gz`) 전체를 들여쓰기하여 표시한다. 원본 파일이 없거나 손상되면 JSON 보기에 오류를 표시하고 Markdown은 유지한다. 이 기능은 run-comparison.ps1로 새로 생성하는 보고서에도 자동 포함된다. Markdown에서 굵게·제목·표 구분자를 확인하고 JSON 보기에서 전체 속성을 확인할 수 있다. JSON은 외부 요청 없이 HTML 안에 포함되므로 단일 공유본에서도 표시되며, 이미지 base64 등 원본 크기에 따라 HTML 용량이 커질 수 있다. 실행별 수치·좌표·신뢰도 비교는 `analysis.json`, 환경과 시간 기록은 `manifest.json`에 유지한다. 사내 실행에서는 입력 폴더와 새 출력 폴더만 지정하면 된다.

`--standalone` 공유본은 HTML 하나만으로 읽을 수 있으며 별도 파일 링크를 제거한다. 실행 로그나 원본 JSON 자체를 포함하는 압축 묶음은 아니다. 공유본이 필요하면 저장된 비교 결과에서 위 명령으로 생성한다.

## 반복과 재개

- 같은 입력의 실행 순서를 Tika→Docling, Docling→Tika로 교대한다. 동시에 다른 무거운 작업을 실행하지 않는 것이 측정 조건 유지에 필요하다.
- 매번 새 Python 작업 프로세스를 사용하며 Tika는 그 안에서 새 JVM을 실행한다. OS 파일 캐시를 비우지 않고 1회차도 통계에 포함한다. 별도 실험을 했다면 그 이력도 결과 해석에 고려해야 한다.
- Docling은 CPU와 기본 4스레드를 명시한다. OpenMP 환경변수도 설정하지만 JVM 전체 스레드 수를 4로 제한하는 것은 아니다.
- 기본 제한 시간은 도구·문서·회차당 1,800초다. 초과하면 해당 프로세스 트리를 종료하고 실패를 기록한 뒤 다음 실행으로 넘어간다.
- 실패나 부분 성공이 있으면 최종 종료 코드는 1이다. 보고서는 그대로 생성한다. 중간 저장된 기록으로도 보고서를 생성할 수 있다.
- `--resume`은 기록된 실패를 재시도하지 않는다. 미기록 회차만 수행하고 중단 당시 파일도 별도 보존한다. 실패를 새 조건에서 다시 측정하려면 새 출력 폴더를 사용한다.
- 재개 시 실행 코드·Tika 설정/JAR·패키지 버전·기록된 모델/언어 데이터 해시·Java/Tesseract 버전을 검사한다. 다른 PC나 설정의 결과를 한 묶음으로 합치지 않는다. 운영체제 상태, CPU 부하 등 모든 환경을 자동으로 같게 만들지는 않는다.

## 수치 정의

전체 시간은 작업 프로세스 시작부터 모델 초기화, 추출, 원본 JSON/Markdown 저장, 프로세스 종료까지다. 비교용 JSON과 HTML 생성은 제외한다. 내부 시간은 Docling `pipeline_total.times` 합계와 Tika 루트(인덱스 0)의 `tk:parse-time-millis`다. 두 내부 시간의 범위는 같지 않으며 하위 Tika 리소스 시간을 더하지 않는다.

각 도구의 5개 결과에서 가능한 10쌍을 모두 비교한다. 실패는 제외하고 부분 성공은 상태를 명시한 채 비교한다. 시간 요약에는 완전 성공만 포함한다. 텍스트 편집거리는 정확한 Levenshtein 거리이며 차이율은 긴 텍스트 길이로 나눈 백분율이다. 정답 데이터가 없으므로 정확도나 CER로 표기하지 않는다.

비교용 JSON에서는 Unicode NFC와 줄바꿈만 통일한다. 공백과 순서를 보존한다. Docling의 본문 참조 순서·헤더/푸터·미연결 내용·표 셀을 반영하고 Tika는 루트 및 내장 리소스의 `tk:content`를 순서대로 포함한다. 따라서 도구 간 수치는 Markdown 표기와 내용 중복 등 출력 형식 차이도 포함한다. 두 도구의 구조 스키마가 달라 도구 간 구조 일치율은 계산하지 않는다.

Docling 좌표·charspan 및 confidence는 내용·구조와 별도로 비교한다. 좌표는 페이지·종류·텍스트·레이어가 양쪽에서 유일하게 대응하는 항목에 한정하며 대응 불가/중복 개수를 공개한다. Tika가 제공하지 않는 수치는 0이 아니라 미제공이다. 비교용 구조는 원본 JSON 전체를 대신하는 스키마가 아니며 모든 필드를 비교하지 않는다. 원본은 `raw.pretty.json`에 보존한다. JSON 비표준 NaN/Infinity만 null로 변환한다.

두 도구에 Tesseract kor/eng 및 PSM 3을 설정해도 OCR 영역 선택과 전처리는 다르다. Tika PDF는 AUTO·216 DPI RGB, Docling은 기본 영역 선택·scale 3이다. 따라서 동일 OCR 입력에 대한 엔진 벤치마크가 아니라 각 문서 추출 파이프라인의 결과 비교다.

## 공정한 비교를 위한 설정과 남는 차이

- **Office OCR**: 비교 실행은 DOCX/PPTX에 한해 Tika의 `skipOcr=true`를 적용한다. Docling의 Office 네이티브 추출도 추가 그림 OCR을 수행하지 않는다. PDF는 기존 OCR 설정을 유지한다. 루트 `tika-config.json`은 수정하지 않으므로 다른 Tika 실행에는 이 정책이 자동 적용되지 않는다.
- **설정 보관**: 실제 전달하는 설정은 출력 폴더의 `execution-config/tika-pdf.json`, `tika-office.json`과 `manifest.json`의 `tika_effective_configs`에 보관한다. Tika의 `run.json`에도 OCR 설정을 기록한다. 재개 시 저장된 설정이 바뀌면 중단한다.
- **추출 범위**: OCR 비활성화가 내장 리소스 파싱 전체를 끄지는 않는다. Tika는 내장 문서·이미지 메타데이터를 계속 처리한다. 발표자 노트, 머리글·바닥글, 첨부 객체 등 실제 추출 범위를 맞춰야 순수 처리 속도를 비교할 수 있다. 기본 기능 비교에서는 이 차이를 유지하며, OOXML만 완전히 동일하게 처리한다고 해석하지 않는다.
- **시간 범위**: Docling의 `pipeline_total`에는 입력 백엔드 초기화가 포함되지 않지만 Tika 루트 시간에는 내장 리소스 파싱이 포함된다. 내부 시간만으로 속도 배수를 결론 내리지 않는다. 전체 시간은 시작·저장·종료를 포함하며, 도구별 초기화와 출력 저장량 차이도 반영한다.
- **자원과 운영 방식**: 현재 CPU·OpenMP 설정은 JVM 전체의 CPU·메모리 사용량을 강제하지 않는다. 운영 성능을 비교하려면 같은 CPU·메모리 한도에서 Tika Server와 docling-serve를 각각 예열하고, 같은 동시 요청 수와 문서 묶음으로 측정해야 한다. 현재 새 프로세스 반복 측정은 서버 처리량 측정이 아니다.
- **PDF 기능**: 같은 OCR 엔진·언어·PSM을 사용해도 OCR 영역은 다르다. Docling의 레이아웃·표·제목 계층 추론은 유지한다. 이 기능들이 제공하는 결과와 소요시간을 함께 비교한다.

과거 Office 결과에는 Tika 이미지 OCR이 포함될 수 있다. 새 조건으로 비교하려면 새 출력 폴더에서 추출을 다시 실행한다. 보고서만 재생성해도 과거의 추출 내용과 시간은 바뀌지 않는다.

## 보고서 구성과 과거 결과

문서별 Markdown 원문·스타일 적용·JSON 원본 보기를 제공한다.
문서별 결과 보기 아래에 **추출 정보 비교** 표를 제공한다. 요소 분류, 제목 수준,
그룹·계층, 서식, 표 구조, 원본 위치, 문서 메타데이터, 내장 리소스를 도구별로 비교한다.
각 도구의 첫 완전 성공 회차(없으면 첫 부분 성공)에서 원본 JSON·Markdown/HTML을
발췌한다. 현재 문서와 설정에서 관찰된 결과이며 도구 전체의 지원 여부나 정확도는 아니다.
저장된 결과로 보고서를 재생성하면 표가 추가되며 문서를 다시 추출할 필요는 없다.
`analysis.json` 버전 4는 `feature_comparison`을 다시 제공한다.
수동 구조 검토 도구와 `structure_review`는 복원하지 않는다. 기존 검토 JSON과
`feature-cards.json`은 보고서 생성 시 읽거나 변경하지 않는다.
텍스트·구조 반복 비교, 좌표·신뢰도 변화량과 도구 간 텍스트 차이는 유지한다.

Docling 반복 스냅샷은 버전 2부터 `level`, `marker`, `enumerated`를 비교한다.
버전 3은 본문·머리글·바닥글 순서를 우선하고 캡션·각주의 동일 참조 중복을 방지한다.
HTML만 재생성하면 기존 `snapshot.json`을 그대로 읽으므로 과거 스냅샷의 제한은 유지된다.
과거 결과를 보정하려면 별도 출력 복사본에서 원본 JSON으로 모든 회차의 스냅샷을
같은 버전으로 다시 만들어야 한다. 기존 결과를 일괄 덮어쓰지 않는다.

## 보관 파일 상세

보고서 하단의 **대용량 처리 운영 확장성**은 여러 문서 처리에 대한 Tika Server와
docling-serve의 API 서비스, 병렬 처리, Kubernetes 확장, 자원 관리, 초기화 비용과
장애 격리를 비교한다. 공식 문서 기반 설명이며 현재 단건 반복 테스트의 실측 결과가 아니다.
사내 Tika의 설치 정보와 실제 버전·워커 구성 검증을 구분하며 추가 검증 항목은 표시하지 않는다.

`manifest.json`은 입력 SHA-256, 환경·모델 해시, 설정, 실행 상태와 시간을 보관한다. `analysis.json`은 모든 비교쌍의 수치다. 문서별 폴더에 입력 복사본과 각 실행의 `raw.pretty.json`, `content.md`, `snapshot.json`, `worker.log`, `run.json`이 있다. Tika의 CLI 출력인 `tika-output.json`도 보존한다.

`reports/`와 `tmp/`는 Git에서 기본 제외한다. 보고서에는 입력 복사본과 추출 전문이 있으므로 공개 샘플 보고서만 명시적으로 선택하여 공유한다. 사내 문서 결과는 사내에서 생성·보관한다.

새 원본 결과는 UTF-8, 한글 유지, 들여쓰기 2칸의 비압축 `raw.pretty.json`으로 저장한다. 기존 `raw.json.gz`도 읽을 수 있으며, 둘 다 있으면 `raw.pretty.json`을 우선한다. 보고서 재생성은 기존 압축 원본을 변환하거나 덮어쓰지 않는다. 저장 방식이 달라졌으므로 과거 실행과 전체 시간을 비교할 때 이 차이를 고려한다.

## Markdown 보고서

기존 비교 실행과 보고서 재생성 명령은 `report.md`도 UTF-8로 저장한다. 추가 옵션이나 재추출은 필요 없다. HTML과 동일한 측정값·대표 회차·기능별 발췌를 사용한다. 측정 결과와 운영 확장성은 표로, 도구별 Markdown·전체 JSON과 기능별 발췌는 소제목과 코드 블록으로 표시한다. 원문에 코드 울타리가 있어도 블록이 끊어지지 않도록 처리하며 문서의 HTML·외부 이미지 참조는 실행하지 않고 원문으로 보존한다. 버튼과 스타일 전환은 HTML 전용이다. `--standalone`을 사용해도 Markdown은 원래 결과 폴더의 `report.md`에 저장된다. Markdown에도 추출 전문이 포함되므로 HTML과 동일한 공유 범위를 적용한다.
