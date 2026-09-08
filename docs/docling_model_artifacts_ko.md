# Docling 모델 아티팩트 배치 가이드

이 문서는 PDF 레이아웃 분석과 표 구조 인식에 필요한 Docling 모델을 인터넷이 가능한 환경에서 내려받은 뒤, 사내망의 실행 환경으로 옮겨 배치하는 방법을 기록한다.

확인 기준 버전:

- Docling: `2.124.0`
- 다운로드 명령: `docling-tools models download layout tableformer`

## 1. 모델 아티팩트 루트

`docling-tools models download`의 기본 저장 위치는 다음과 같다.

```text
~/.cache/docling/models/
```

이 문서에서는 이 디렉터리를 **아티팩트 루트**라고 부른다. 사내에서는 기본 경로 대신 공용 디스크 등의 다른 위치를 사용할 수 있지만, 아티팩트 루트 아래의 디렉터리 구조는 그대로 유지해야 한다.

## 2. 현재 내려받은 구조

`layout`과 `tableformer`를 내려받으면 현재 환경에서는 약 669MB가 다음 구조로 저장된다.

```text
<artifacts-root>/
├── docling-project--docling-layout-heron/
│   ├── model.safetensors                 # PyTorch 레이아웃 모델, 약 164MB
│   ├── config.json
│   ├── preprocessor_config.json
│   ├── README.md
│   └── .cache/huggingface/               # 다운로드 메타데이터
├── docling-project--docling-layout-heron-onnx/
│   ├── model.onnx                        # ONNX 레이아웃 모델, 약 163MB
│   ├── config.json
│   ├── preprocessor_config.json
│   ├── README.md
│   └── .cache/huggingface/
└── docling-project--docling-models/
    ├── config.json
    ├── README.md
    ├── .cache/huggingface/
    └── model_artifacts/
        └── tableformer/
            ├── fast/
            │   ├── tm_config.json
            │   └── tableformer_fast.safetensors      # 약 139MB
            └── accurate/
                ├── tm_config.json
                └── tableformer_accurate.safetensors  # 약 203MB
```

`layout` 모델은 PyTorch용 Heron(`model.safetensors`)과 ONNX용 Heron(`model.onnx`)을 모두 받는다. Docling의 실행 엔진 선택에 따라 필요한 모델이 달라질 수 있으므로 둘 중 하나만 임의로 제외하지 않는다.

`tableformer`는 빠른 처리용 `fast`와 높은 정확도용 `accurate` 가중치를 함께 포함한다.

## 3. Hugging Face repository와 저장 폴더의 대응

각 Hugging Face repository는 다음 규칙으로 아티팩트 루트 아래에 배치된다.

| Hugging Face repository | 아티팩트 루트 아래 디렉터리 |
| --- | --- |
| `docling-project/docling-layout-heron` | `docling-project--docling-layout-heron/` |
| `docling-project/docling-layout-heron-onnx` | `docling-project--docling-layout-heron-onnx/` |
| `docling-project/docling-models` | `docling-project--docling-models/` |

즉 repository ID의 `/`를 `--`로 바꾼 디렉터리를 만들고, **repository 안의 파일과 하위 디렉터리를 원래 상대 경로 그대로** 둔다. 예를 들어 TableFormer 파일을 `tableformer/`로 꺼내거나, `model_artifacts/` 단계를 생략하면 Docling이 모델을 찾지 못한다.

## 4. 사내 반입 방법

가장 안정적인 방법은 인터넷이 가능한 승인 환경에서 Docling CLI로 디렉터리 구조를 생성한 뒤, 그 결과를 통째로 전달하는 것이다.

```powershell
docling-tools models download layout tableformer --output-dir ".\docling-models"
```

생성된 `docling-models` 디렉터리 전체를 압축하거나 파일 전송 수단으로 사내 환경에 복사한다. 숨김 디렉터리인 `.cache/huggingface`도 함께 보존하면 내려받은 revision과 검증 메타데이터까지 동일하게 유지할 수 있다.

사내 환경에서 다음처럼 배치한다.

```text
D:\docling-models\
├── docling-project--docling-layout-heron\
├── docling-project--docling-layout-heron-onnx\
└── docling-project--docling-models\
```

전역 Hugging Face 캐시인 `~/.cache/huggingface/hub`는 이 다운로드에서 실제 가중치를 보관하는 위치가 아니다. 따라서 해당 경로의 참조 파일만 따로 복사하는 방식은 충분하지 않다. 아티팩트 루트 전체를 기준으로 전달한다.

## 5. 실행 환경에서 모델 경로 지정

### 기본 캐시 경로 사용

사내 사용자 계정의 아래 기본 위치에 동일한 구조를 배치하면 별도 설정 없이 Docling이 기본 캐시를 사용할 수 있다.

```text
C:\Users\<사용자 계정>\.cache\docling\models\
```

### 별도 경로 사용

공용 디스크 또는 배포 디렉터리에 둔다면 `DOCLING_ARTIFACTS_PATH` 환경 변수에 아티팩트 루트를 지정한다.

```powershell
$env:DOCLING_ARTIFACTS_PATH = "D:\docling-models"
docling-poc ".\samples\input.pdf"
```

Docling 공식 CLI를 직접 실행하는 경우에는 다음처럼 지정할 수도 있다.

```powershell
docling --artifacts-path "D:\docling-models" ".\samples\input.pdf"
```

`DOCLING_ARTIFACTS_PATH`에는 `docling-project--...` 디렉터리들이 바로 들어 있는 아티팩트 루트를 지정해야 한다. 개별 repository 디렉터리나 `model_artifacts/tableformer` 디렉터리만 지정하면 안 된다.

## 6. 사내 설치 후 확인 항목

1. Docling 패키지 버전을 반입 환경과 맞춘다. 모델 repository의 revision과 Docling 코드가 달라지면 경로나 설정 형식의 호환성이 달라질 수 있다.
2. `DOCLING_ARTIFACTS_PATH`가 실제 디렉터리를 가리키는지 확인한다.
3. PDF 하나를 변환해 레이아웃 요소와 표가 결과 JSON의 `texts`, `tables`, `pictures` 등에 생성되는지 확인한다.
4. 사내 실행 시 Hugging Face 또는 PyPI에 추가 접속을 시도하지 않는지 네트워크 로그와 실행 로그로 확인한다.

현재 POC의 `docling-poc` CLI는 Docling 기본 파이프라인을 사용하므로, 위 환경 변수를 설정하면 별도의 코드 변경 없이 사전 배치한 모델 경로를 사용할 수 있다.
