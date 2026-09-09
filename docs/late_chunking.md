# Late Chunking 논문 분석 및 현재 Chunking 아키텍처 적용

> 대상 논문: *Late Chunking: Contextual Chunk Embeddings Using Long-Context Embedding Models* — Günther et al., 2024  
> https://arxiv.org/abs/2409.04701

## 1. 분석 목적

현재 AI-Ready Data 파이프라인에서는 비정형 문서를 다음과 같이 처리한다.

~~~text
Document
  ↓
Docling Parsing
  ↓
Normalized Document Elements
  ↓
Chunking
  ↓
Chunk Domain Mapping
  ↓
Boundary Resolution
  ↓
Domain-aware Unit
  ↓
Unit Context
  ↓
Embedding
~~~

현재 Chunk는 최종 검색 단위가 아니라, 후속 단계에서 Domain을 안정적으로 판정하기 위한 작은 연속 처리 단위다.

이 구조에서 Late Chunking 논문은 다음 질문과 직접 연결된다.

1. Chunk를 작게 나누면 주변 문맥이 사라지는 문제를 어떻게 해결할 수 있는가?
2. Chunk Boundary를 잘 만드는 것과 Chunk Embedding을 잘 만드는 것은 같은 문제인가?
3. Late Chunking을 현재 Domain Classification용 Chunk Vector에 적용할 수 있는가?
4. 기존 Context Resolution이나 Boundary Agent와 중복되는가?

---

## 2. 기존 Chunking 방식의 문제

일반적인 Vectorization Pipeline은 보통 다음 순서다.

~~~text
Document
 ↓
Chunking
 ↓
Chunk 1 / Chunk 2 / Chunk 3
 ↓
각 Chunk를 독립적으로 Embedding
~~~

예를 들어 원문이 다음과 같다고 하자.

~~~text
[Chunk 1]
Berlin is the capital and largest city of Germany.

[Chunk 2]
The city has a population of approximately 3.8 million.
~~~

기존 방식에서는 두 번째 Chunk만 Embedding Model에 입력한다.

~~~text
"The city has a population of approximately 3.8 million."
                         ↓
                   Embedding Model
~~~

이 경우 Embedding Model은 다음 정보를 알 수 없다.

~~~text
the city = 어떤 도시인가?
~~~

원문 전체에서는 the city = Berlin이라는 관계가 명확하지만, Chunk를 먼저 나누고 독립적으로 Embedding했기 때문에 문맥이 사라진다.

~~~text
Document Context
     ↓
Chunking
     ↓
Context Loss
     ↓
Independent Chunk Embedding
~~~

Late Chunking은 이 문제를 줄이려는 방법이다.

---

## 3. Late Chunking은 새로운 Chunk Boundary 알고리즘이 아니다

Late Chunking이라는 이름 때문에 다음처럼 오해할 수 있다.

> "Semantic Boundary를 더 늦게 결정하는 새로운 Chunking 알고리즘인가?"

그렇지 않다.

Late Chunking은 어디서 Chunk를 나눌 것인가를 결정하는 알고리즘이 아니다. 기존의 다음과 같은 Boundary 기준은 여전히 필요하다.

- Sentence Boundary
- Paragraph Boundary
- Section Boundary
- Fixed Token Size
- Docling Layout Information
- Custom Heuristic

Late Chunking이 바꾸는 것은 다음이다.

> Chunk Boundary를 Transformer 이전에 적용할 것인가, 이후에 적용할 것인가

---

## 4. 기존 방식과 Late Chunking의 차이

### 기존 방식

~~~text
Document
 ↓
Chunking

Chunk 1
 ↓
Transformer
 ↓
Pooling
 ↓
Vector 1

Chunk 2
 ↓
Transformer
 ↓
Pooling
 ↓
Vector 2

Chunk 3
 ↓
Transformer
 ↓
Pooling
 ↓
Vector 3
~~~

각 Chunk가 서로 독립적으로 Transformer에 들어간다. 따라서 Chunk 2의 표현은 Chunk 1이나 Chunk 3의 내용을 보지 못한다.

### Late Chunking

~~~text
Entire Document
       ↓
Long-context Transformer
       ↓
Contextualized Token Embeddings

t1 t2 t3 t4 t5 t6 t7 t8 ...
│──── Chunk 1 ────│
                  │──── Chunk 2 ────│
                                    │── Chunk 3 ──│

       ↓

Chunk별 Token Span Pooling

       ↓

Vector 1
Vector 2
Vector 3
~~~

즉 순서가 다음처럼 바뀐다.

~~~text
기존
Chunking
 ↓
Transformer
 ↓
Pooling

Late Chunking
Transformer
 ↓
Chunk Boundary 적용
 ↓
Pooling
~~~

이것이 Late Chunking의 핵심이다.

---

## 5. 왜 문맥이 보존되는가?

Transformer의 Token Representation은 주변 Token Context를 반영한다.

다음 문서를 전체 Context로 Transformer에 넣는다고 하자.

~~~text
Berlin is the capital of Germany.
The city has 3.8 million residents.
~~~

Transformer는 각 Token에 대해 Contextualized Representation을 만든다. 예를 들어 city라는 Token의 Representation은 단순한 사전적 의미만 담는 것이 아니다.

~~~text
"city"

독립적으로 입력
 ↓
일반적인 도시 의미

전체 Document Context에서 입력
 ↓
앞의 Berlin, Germany, capital 정보를 반영한
Contextualized "city"
~~~

따라서 다음 문장에 해당하는 Token들을 Pooling하면 최종 Chunk Vector에도 앞서 등장한 Berlin 관련 Context가 일정 부분 반영된다.

~~~text
"The city has 3.8 million residents."
~~~

즉 다음과 같은 Vector를 만든다.

~~~text
Local Chunk
+
Global Context
 ↓
Context-aware Chunk Vector
~~~

---

## 6. Mean Pooling 위치가 핵심

일반 Embedding Model의 동작을 단순화하면 다음과 같다.

~~~text
Text
 ↓
Tokenizer
 ↓
Transformer
 ↓
Token Embeddings

v1 v2 v3 v4 v5

 ↓
Pooling
 ↓
Single Vector
~~~

기존 Chunking에서는 Chunk마다 이 과정을 따로 수행한다.

~~~text
Chunk 1
 ↓
Transformer
 ↓
v1 v2 v3
 ↓
Pooling
 ↓
Vector 1

Chunk 2
 ↓
Transformer
 ↓
v4 v5 v6
 ↓
Pooling
 ↓
Vector 2
~~~

Late Chunking은 먼저 Document 전체에 Transformer를 적용한다.

~~~text
Document
 ↓
Transformer
 ↓
v1 v2 v3 v4 v5 v6 v7 v8 ...
~~~

그리고 Chunk별 Token 범위에 대해서만 Pooling한다.

~~~text
Chunk 1 = token 1 ~ 4

mean(v1, v2, v3, v4)
→ Vector 1

Chunk 2 = token 5 ~ 9

mean(v5, v6, v7, v8, v9)
→ Vector 2
~~~

즉 Late라는 표현은 Chunking을 완전히 없앤다는 의미가 아니라 다음을 의미한다.

> Transformer 이후, Pooling 직전까지 Chunk 적용을 늦춘다

---

## 7. Chunk Boundary는 여전히 필요하다

Late Chunking에서도 다음 정보는 반드시 필요하다.

~~~text
Chunk 1: token 0 ~ 120
Chunk 2: token 121 ~ 245
Chunk 3: token 246 ~ 370
~~~

따라서 기존 Docling 기반 Chunking Architecture는 그대로 유효하다.

~~~text
SECTION_HEADER
PARAGRAPH
TABLE
LIST
Sentence
Max Token
~~~

같은 정보는 여전히 Chunk Boundary를 정하는 데 사용한다.

두 기술의 역할은 다르다.

~~~text
Docling / Chunk Policy
        ↓
"Chunk의 경계를 어디로 잡을 것인가?"

Late Chunking
        ↓
"해당 Chunk의 Vector를 어떤 Context에서 만들 것인가?"
~~~

즉 둘은 경쟁 관계가 아니라 서로 보완적인 관계다.

---

## 8. Overlap Chunking과의 차이

Context Loss를 줄이는 일반적인 방법 중 하나는 Overlap이다.

~~~text
Chunk 1
A B C D

Chunk 2
    C D E F

Chunk 3
        E F G H
~~~

예를 들어 다음처럼 설정할 수 있다.

~~~text
chunk_size = 500
overlap = 100
~~~

Overlap은 주변 Context를 일부 복제해주는 방식이다. 하지만 필요한 Context 범위가 문서마다 다르기 때문에 overlap 크기는 heuristic에 의존한다.

Late Chunking은 다른 접근을 사용한다.

~~~text
Full Context
 ↓
Transformer
 ↓
Contextualized Token Representation
 ↓
Local Chunk Pooling
~~~

즉 Chunk Text 자체를 복제하는 것이 아니라, 더 넓은 Context 안에서 만들어진 Token Representation을 사용한다.

---

## 9. 작은 Chunk일수록 Late Chunking이 중요한 이유

다음 Chunk를 생각해보자.

~~~text
담당자의 승인을 받아야 한다.
~~~

이 Chunk만 보면 무엇에 대한 승인인지, 어떤 업무인지, 어떤 대상이나 상황인지 알기 어렵다. 작은 Chunk일수록 자체 Context가 부족할 가능성이 높다.

반대로 매우 긴 Chunk라면 내부에 이미 Context가 많이 포함되어 있다.

~~~text
Small Chunk
 ↓
Context 부족 가능성 큼
 ↓
Late Chunking 효과가 커질 가능성

Large Chunk
 ↓
내부 Context 충분
 ↓
추가 Contextualization 효과 감소 가능
~~~

이 점은 현재 프로젝트와 특히 관련이 있다. 현재 Chunk는 최종 Retrieval 단위가 아니라 Domain Classification을 위한 비교적 작은 Evidence 단위이기 때문이다.

---

## 10. 긴 문서는 어떻게 처리하는가?

Late Chunking의 전제는 Embedding Model의 Context Window 안에 입력이 들어가야 한다는 것이다.

예를 들어 모델 최대 Context가 8,192 tokens인데 문서가 50,000 tokens라면 전체 문서를 한 번에 Transformer에 넣을 수 없다.

이 경우 큰 Context Window 단위로 문서를 먼저 나눌 수 있다.

~~~text
50,000 Token Document
      ↓

Macro Window 1
0 ~ 8,191

Macro Window 2
7,000 ~ 15,191

Macro Window 3
14,000 ~ 22,191

...
~~~

Macro Window 간에는 일부 Overlap을 사용할 수 있다. 각 Macro Window 내부에서는 다음을 수행한다.

~~~text
Macro Window
 ↓
Long-context Transformer
 ↓
Contextualized Tokens
 ↓
Small Chunk Span Pooling
~~~

즉 두 단계의 크기가 존재한다.

~~~text
Document
 ↓
Large Context Window
 ↓
Transformer
 ↓
Small Chunk
 ↓
Vector
~~~

여기서 Large Context Window는 Transformer 입력 범위이고, Small Chunk는 실제 검색 또는 분류에 사용할 단위다.

---

## 11. 별도 모델 학습 없이 적용할 수 있다는 장점

Late Chunking의 기본 방식은 Embedding Model을 반드시 다시 학습해야 하는 방식은 아니다. 필요한 조건은 대략 다음과 같다.

1. Long-context Embedding Model
2. Transformer Token-level Hidden State 접근
3. Original Text ↔ Token Offset Mapping
4. Chunk ↔ Token Span Mapping
5. Span 단위 Pooling

하지만 중요한 실무 제약이 있다. Embedding API가 최종 Vector만 반환한다면 Late Chunking을 직접 구현하기 어렵다. Token-level Hidden States를 얻을 수 있어야 하기 때문이다.

따라서 현재 사내 Embedding Model 또는 API가 이를 지원하는지 확인해야 한다.

---

## 12. Fine-tuning까지 가능하지만 초기 단계에서는 필요 없다

Late Chunking은 추가 학습 없이 사용할 수 있지만 논문에서는 Span 기반 Fine-tuning 아이디어도 다룬다.

~~~text
일반 학습
Document
 ↓
Pooling
 ↓
Document Vector

Late Chunking Inference
Document
 ↓
Transformer
 ↓
Relevant Span Pooling
 ↓
Chunk Vector
~~~

Training과 Inference 구조의 차이를 줄이기 위해 특정 Span을 Pooling해 학습하는 방식도 생각할 수 있다.

하지만 현재 프로젝트에서는 우선순위가 낮다. 먼저 Golden Dataset에서 Naive Chunk Embedding과 Late Chunking Embedding을 비교하는 것이 우선이다.

---

## 13. 현재 프로젝트에는 두 종류의 Embedding이 존재한다

현재 구조에서는 Embedding을 하나로 보면 안 된다. 다음 두 목적이 다르다.

~~~text
1. Chunk Embedding
   ↓
Domain Anchor KNN Classification

2. Unit Embedding
   ↓
Final Retrieval
~~~

따라서 Late Chunking 적용 가능성도 각각 따로 검토해야 한다.

---

## 14. Chunk Domain Mapping에는 적용 가치가 높을 가능성이 있다

다음 예를 보자.

~~~text
C28
CMP 설비의 정기 점검 결과 이상이 확인되었다.

C29
담당자의 승인을 받아 조치해야 한다.

C30
알람 발생 이력을 시스템에 등록한다.
~~~

C29만 독립적으로 Embedding하면 다음 문장만 입력된다.

~~~text
"담당자의 승인을 받아 조치해야 한다."
~~~

이 문장만으로는 D03 정비인지, D06 알람인지, 다른 Domain인지 판정이 애매할 수 있다.

현재 시스템에서는 이런 문제를 해결하기 위해 다음 구조를 사용한다.

~~~text
Dictionary
 ↓
Anchor KNN
 ↓
Context Resolution
 ↓
Boundary Agent
~~~

Late Chunking을 적용하면 C29 Vector 자체가 C28, C29, C30이 존재하는 Context 안에서 생성된다.

~~~text
C29
"담당자의 승인을 받아 조치해야 한다."

      ↓

Context-aware Vector

      ↓

앞의 "정기점검"
뒤의 "알람 발생"
정보가 일정 부분 반영
~~~

따라서 Domain Anchor KNN 단계에서 애매한 Chunk 표현을 개선할 가능성이 있다. 이 부분은 현재 프로젝트에서 가장 실험 가치가 높은 적용 포인트다.

---

## 15. Context Resolution을 대체하는 기술은 아니다

Late Chunking을 적용한다고 해서 다음처럼 구조를 단순화할 수 있다는 근거는 없다.

~~~text
Dictionary
 ↓
Embedding KNN
 ↓
Domain 확정
~~~

Late Chunking은 Better Chunk Representation을 만드는 기술이다. 반면 현재 Context Resolution과 Boundary Agent는 Neighbor Domain, Sequence Pattern, Domain Transition, Boundary Decision을 처리한다.

~~~text
Late Chunking
      ↓
Chunk Representation 개선

Context Resolution
      ↓
Chunk Sequence 보정

Boundary Agent
      ↓
Domain Transition 판단
~~~

따라서 현재 구조를 유지하면서 Embedding 단계의 개선 후보로 보는 것이 적절하다.

---

## 16. 최종 Unit Vector에는 효과가 낮을 수도 있다

현재 Unit Vector는 Raw Text를 그대로 Embedding하지 않는다.

~~~text
Unit Original Text
 ↓
Context Agent
 ↓
summary
+
domain_fields
 ↓
Embedding
~~~

예를 들어 다음 원문이:

~~~text
점검을 실시하였다.
이상이 확인되었다.
담당자의 승인 후 필터를 교체하였다.
~~~

Context Agent를 거쳐 아래처럼 변환된다고 하자.

~~~text
summary:
CMP 설비 예방정비 과정에서 필터 이상을 발견하고
담당자 승인 후 교체 조치를 수행함.

domain_fields:
대상시스템: CMP
점검항목: 필터
조치내역: 교체
~~~

이 경우 모호한 대명사, 짧은 문장, 주변 Context 부족, 업무 의미 누락이 이미 어느 정도 해결되어 있다. LLM Context Agent가 명시적인 의미 Representation을 생성해주기 때문이다.

따라서 summary + domain_fields Embedding에 Late Chunking을 추가했을 때 얻는 이점은 Chunk Domain Mapping 단계보다 작을 가능성이 있다.

현재 프로젝트에서는 우선 다음 실험이 더 논리적이다.

> Domain Classification용 Chunk Embedding에 Late Chunking을 적용하는 실험

---

## 17. Docling 기반 Chunking과 Late Chunking 연결

현재 앞단 Architecture는 다음과 같다.

~~~text
Docling
 ↓
NormalizedElement
 ↓
Element Policy
 ↓
ChunkCandidate
 ↓
Merge / Split Policy
 ↓
ChunkSequence
~~~

이 구조는 그대로 유지한다.

기존 Embedding 방식은 다음과 같다.

~~~text
ChunkSequence

C01 → Embedding Model → V01
C02 → Embedding Model → V02
C03 → Embedding Model → V03
~~~

Late Chunking을 적용하면 다음과 같다.

~~~text
ChunkSequence
       ↓
Chunk Boundary / Offset 유지
       ↓
Long-context Encoder
       ↓
Contextualized Token Embeddings
       ↓

C01 Token Span → Pooling → V01
C02 Token Span → Pooling → V02
C03 Token Span → Pooling → V03
~~~

즉 Chunk는 그대로 존재한다. 차이는 Chunk별 Vector 생성 방식이다.

---

## 18. Provenance / Offset 보존이 더 중요해진다

Late Chunking을 구현하려면 다음 Mapping이 필요하다.

~~~text
Original Document
 ↓
Normalized Element
 ↓
Chunk
 ↓
Character Offset
 ↓
Token Offset
~~~

예를 들어 다음 관계를 알아야 한다.

~~~text
C23
char_start = 2201
char_end   = 2387

Tokenizer 이후:
token_start = 451
token_end   = 493
~~~

그래야 Transformer 전체 Output에서 다음 Span을 Pooling해서 C23 Vector를 만들 수 있다.

~~~text
hidden_states[451:493]
~~~

따라서 앞서 Docling Architecture에서 강조했던 Provenance, Offset, Source Element ID, Reading Order 등의 보존은 Late Chunking을 고려할 때도 유용하다.

---

## 19. Late Chunking이 현재 Chunking 철학과 잘 맞는 이유

현재 Architecture에서는 앞단에서 완벽한 Semantic Chunk를 만들지 않는 방향을 택하고 있다.

~~~text
완벽한 Semantic Boundary 탐색
           X

안정적인 작은 Chunk 생성
           ↓
Domain Mapping
           ↓
Boundary Resolution
           ↓
Semantic / Domain-aware Unit
~~~

Late Chunking 역시 모든 문제를 Chunk Boundary에 집중하지 않는다. 따라서 다음 조합을 생각할 수 있다.

~~~text
Docling Structural Signal
       +
Paragraph / Sentence Boundary
       +
Token Guardrail
       ↓
Stable Chunk
       ↓
Context-aware Chunk Representation
       ↓
Domain Mapping
       ↓
Boundary Resolution
       ↓
Unit
~~~

핵심 아이디어는 다음과 같다.

> 완벽한 Chunk Boundary를 찾지 못하더라도, Chunk Representation에서 주변 Context를 일부 보존할 수 있다.

---

## 20. 바로 Architecture에 넣으면 안 되는 이유

Late Chunking은 현재 프로젝트에서 아직 실험 후보로 보는 것이 맞다.

### 20.1 논문의 주요 평가 목적은 Retrieval

논문은 주로 Information Retrieval 성능을 평가한다. 현재 적용하려는 대상은 Chunk → Domain Classification이다.

따라서 Late Chunking이 Domain Classification 정확도를 향상한다는 것은 논문에서 직접 검증된 결과가 아니다. 별도 Golden Dataset 실험이 필요하다.

### 20.2 계산량 증가 가능성

기존에는 200 tokens 수준의 Chunk를 Embedding할 수 있지만, Late Chunking은 8,000 tokens 같은 Large Context Window를 Transformer에 넣을 수 있다. GPU Memory, Throughput, Latency, Batch Size, Attention Cost를 실제 측정해야 한다.

### 20.3 Embedding Model 지원 여부

Late Chunking에는 Token Hidden State 접근이 필요하다. 사내 Embedding 환경이 Input Text → Embedding API → Final Vector만 제공한다면 적용이 어렵다.

먼저 다음을 확인해야 한다.

- Embedding Model 직접 로딩 가능 여부
- Token-level Hidden State 접근 가능 여부
- Max Context Length
- Tokenizer Offset Mapping 지원
- Custom Pooling 가능 여부

---

## 21. 권장 A/B Test

현재 Architecture에 바로 적용하기보다 동일한 Chunking 결과를 가지고 비교하는 것이 좋다.

~~~text
                Same Chunk Sequence
                       │
             ┌─────────┴─────────┐
             │                   │
             ▼                   ▼
     A. Naive Embedding    B. Late Chunking
             │                   │
             └─────────┬─────────┘
                       ↓
                  Same Anchor Set
                       ↓
                     KNN
                       ↓
                 Domain Prediction
~~~

평가 지표 후보는 다음과 같다.

- Accuracy
- Macro F1
- Per-domain Precision / Recall / F1
- UNKNOWN Rate
- Boundary Chunk Accuracy
- Ambiguous Chunk Accuracy

---

## 22. 특히 별도로 평가해야 할 Case

Late Chunking의 효과를 정확히 보려면 전체 Accuracy만 보면 안 된다. Golden Dataset을 다음 Case로 나눠 평가하는 것이 좋다.

### Case A — Chunk만 보고 Domain 판정 가능

~~~text
CMP 설비 예방정비를 실시한다.
~~~

주변 문맥 없이도 명확하다.

### Case B — 이전 Chunk가 있어야 이해 가능

~~~text
C01
CMP 설비의 예방정비 결과 이상이 확인되었다.

C02
담당자의 승인을 받아야 한다.
~~~

C02만 보면 의미가 부족하다.

### Case C — 다음 Chunk가 있어야 이해 가능

~~~text
C01
해당 이력을 등록해야 한다.

C02
Alarm History 시스템에 장애 발생 시간을 저장한다.
~~~

### Case D — Domain Transition Boundary

~~~text
C28 → D03
C29 → ?
C30 → D06
~~~

현재 Boundary Agent가 처리하려는 대표 Case다.

### Case E — Heading Context가 필요한 경우

~~~text
[Heading]
예방정비

[Paragraph]
담당자의 승인을 받아 수행한다.
~~~

Heading이 없으면 Domain 판정이 어려울 수 있다.

---

## 23. Late Chunking과 Context Resolution의 관계도 실험해야 한다

현재 Architecture에는 이미 Context Resolution이 존재한다.

~~~text
D03
UNKNOWN
D03

↓

D03
D03
D03
~~~

Late Chunking 역시 주변 Context를 Embedding에 반영한다. 따라서 다음 질문을 검증해야 한다.

~~~text
Late Chunking
+
Context Resolution

↓

상호 보완인가?

OR

동일한 Context 정보를
두 번 활용하는 중복인가?
~~~

이를 다음과 같이 비교할 수 있다.

~~~text
Experiment A
Naive Embedding
+
No Context Resolution

Experiment B
Naive Embedding
+
Context Resolution

Experiment C
Late Chunking
+
No Context Resolution

Experiment D
Late Chunking
+
Context Resolution
~~~

결과를 비교하면 각 단계의 실제 기여도를 확인할 수 있다.

---

## 24. 현재 Architecture에 적용한다면

현재 Architecture는 다음과 같다.

~~~text
Document
 ↓
Docling
 ↓
NormalizedElement
 ↓
Chunking
 ↓
Chunk Embedding
 ↓
Anchor KNN
 ↓
Context Resolution
 ↓
Boundary Agent
 ↓
Unit
~~~

Late Chunking 후보 적용 구조는 다음과 같다.

~~~text
Document
 ↓
Docling
 ↓
NormalizedElement
 ↓
Stable Chunk Sequence
 ↓
Chunk / Token Offset Mapping
 ↓
Long-context Encoder
 ↓
Contextualized Token Embeddings
 ↓
Chunk Span Pooling
 ↓
Context-aware Chunk Vector
 ↓
Anchor KNN
 ↓
Context Resolution
 ↓
Boundary Agent
 ↓
Unit
~~~

중요한 것은 Chunking Architecture를 교체하는 것이 아니라 Chunk Vector 생성 방식을 교체한다는 점이다.

---

## 25. 현재 프로젝트에 대한 최종 판단

Late Chunking을 지금 바로 핵심 Architecture에 포함시키는 것은 권장하지 않는다.

현재 단계에서는 다음 위치에 두는 것이 적절하다.

~~~text
Chunk Embedding Strategy

├─ NaiveEmbeddingStrategy
│
└─ LateChunkingEmbeddingStrategy
~~~

즉 구현 전략을 교체할 수 있게 만들어 두고 Golden Dataset으로 비교한다.

~~~python
class ChunkEmbeddingStrategy:
    def embed(self, document, chunks):
        raise NotImplementedError
~~~

기존 방식:

~~~python
class NaiveChunkEmbeddingStrategy(ChunkEmbeddingStrategy):
    def embed(self, document, chunks):
        return [
            embedding_model.encode(chunk.text)
            for chunk in chunks
        ]
~~~

Late Chunking:

~~~python
class LateChunkEmbeddingStrategy(ChunkEmbeddingStrategy):
    def embed(self, document, chunks):
        token_embeddings = embedding_model.encode_tokens(document.text)
        vectors = []

        for chunk in chunks:
            span = token_embeddings[chunk.token_start:chunk.token_end]
            vectors.append(mean_pool(span))

        return vectors
~~~

실제 구현은 모델 API에 따라 달라지지만 Architecture 관점에서는 이런 분리가 적절하다.

---

## 26. 핵심 설계 원칙

Late Chunking 논문에서 현재 프로젝트에 가져갈 수 있는 핵심 원칙은 다음과 같다.

1. Chunk Boundary와 Chunk Representation은 서로 다른 문제다.
2. 좋은 Chunking만으로 Context Loss가 완전히 해결되는 것은 아니다.
3. 작은 Chunk를 독립적으로 Embedding하면 주변 문맥을 잃을 수 있다.
4. Late Chunking은 Transformer 이후에 Chunk별 Pooling을 수행한다.
5. Chunk Boundary 자체는 여전히 필요하다.
6. Docling 기반 Structural Chunking과 Late Chunking은 서로 보완적이다.
7. Late Chunking은 Semantic Chunking을 대체하지 않는다.
8. 현재 프로젝트에서는 최종 Unit Embedding보다 Domain Classification용 Chunk Embedding에 더 적용 가치가 있을 가능성이 높다.
9. Context Resolution과 Boundary Agent를 제거할 근거는 없다.
10. 도입 전에 Golden Dataset 기반 A/B Test가 필요하다.
11. 특히 Context-dependent Chunk와 Domain Boundary Case를 별도로 평가해야 한다.
12. Token Hidden State 접근 및 Long-context Model 지원 여부가 실제 도입 가능성을 결정한다.

---

## 27. Docling 분석과 함께 보면

앞서 Docling Technical Report에서 얻은 핵심은 다음과 같다.

> Document Structure를 너무 일찍 Plain Text로 Flatten하지 않는다.

Late Chunking에서 얻는 핵심은 다음과 같다.

> Chunk를 너무 일찍 독립된 Embedding Context로 만들지 않는다.

두 내용을 합치면 다음과 같은 설계 철학으로 정리할 수 있다.

~~~text
Document
 ↓
Docling
 ↓
구조를 잃지 않은
Normalized Representation
 ↓
Structure-aware
Stable Chunking
 ↓
문맥을 잃지 않은
Chunk Representation
 ↓
Domain Mapping
 ↓
Domain-aware Unit
~~~

즉 두 논문에서 공통적으로 얻을 수 있는 교훈은 다음과 같다.

> 정보를 너무 이른 단계에서 버리지 않는다.

Docling 관점에서는 Layout / Relation / Provenance를 버리지 않는 것이고, Late Chunking 관점에서는 Surrounding Semantic Context를 너무 일찍 버리지 않는 것이다.

---

## 28. 최종 요약

~~~text
                    Document
                       ↓
                    Docling
                       ↓
              NormalizedElement
                       ↓
              Structural Chunking
                       ↓
                ChunkSequence
                       │
      ┌────────────────┴───────────────┐
      │                                │
      │      기존 방식                 │
      │                                │
      │ C01 → Embedding                │
      │ C02 → Embedding                │
      │ C03 → Embedding                │
      │                                │
      └────────────────────────────────┘

                       VS

      ┌────────────────────────────────┐
      │        Late Chunking           │
      │                                │
      │ C01 C02 C03 C04                │
      │       ↓                        │
      │ Long-context Transformer       │
      │       ↓                        │
      │ Contextualized Tokens          │
      │       ↓                        │
      │ Chunk Span Pooling             │
      │       ↓                        │
      │ V01 V02 V03 V04                │
      └────────────────────────────────┘

                       ↓
                  Anchor KNN
                       ↓
               Context Resolution
                       ↓
                Boundary Agent
                       ↓
                     Unit
~~~

현재 프로젝트 관점에서 가장 중요한 결론은 다음과 같다.

> Late Chunking은 현재 Docling 기반 Chunking Architecture를 대체하는 기술이 아니라, 생성된 작은 Chunk가 주변 문맥을 잃지 않도록 Domain Classification용 Vector Representation을 개선할 수 있는 Embedding Strategy 후보로 보는 것이 가장 적절하다.

따라서 현재 단계의 권장 방향은 다음과 같다.

~~~text
Architecture에 즉시 고정
          X

Embedding Strategy로 격리
          ↓
Golden Dataset
          ↓
Naive vs Late Chunking
          ↓
Domain Classification 성능 비교
          ↓
효과가 검증될 경우 채택
~~~

---

## Reference

- Günther et al., *Late Chunking: Contextual Chunk Embeddings Using Long-Context Embedding Models*, 2024  
  https://arxiv.org/abs/2409.04701

