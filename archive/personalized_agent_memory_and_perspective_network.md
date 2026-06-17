# 개인화 에이전트: 메모리와 관점 네트워크 아키텍처

## 1. 핵심 비전

이 시스템의 핵심은 모든 유저가 자신만의 **개인화 에이전트**를 가지는 것이다.

개인화 에이전트는 유저와의 대화, 그리고 대화 중 공유되는 미디어를 기반으로 성장한다. 에이전트는 단순히 과거 정보를 저장하는 것이 아니라, 유저의 지식, 취향, 성향, 성격, 대화 방식, 생각하는 방식을 점진적으로 이해하고 반영한다.

즉, 목표는 단순한 메모리 RAG가 아니라 다음과 같다.

> 유저와 함께 성장하는 개인화 에이전트를 만들고, 각 에이전트가 가진 관점과 지식을 바탕으로 새로운 형태의 에이전트 네트워크를 구성한다.

### 1.1 전체 개요 (Overview)

이 시스템은 두 개의 맞물린 제품으로 이루어진다. ①은 주인과의 대화로 성장하는 **개인화 에이전트(Private)**이고, ②는 그 에이전트들이 공개한 관점으로 구성되는 **관점 네트워크(Public/Shared)**다. 둘을 잇는 단 하나의 경로가 **publish**다.

```text
[ ① 개인화 루프 · Private ]   ← "나와 함께 성장하는 개인 에이전트" 제품

  주인(User) ⇄ 개인화 에이전트
        │  대화 + 공유 미디어
        ▼
  Raw Memory Store
        │
        ├─▶ Memory Extraction   →  "무엇을 알고 / 경험 / 선호하는가"
        └─▶ Persona Modeling     →  "어떻게 생각하고 말하는가"
        │        (Memory ⊥ Persona : 승격 관계가 아닌 병렬 차원)
        ▼
  Private Memory   ── 외부 대화에서는 접근 불가 (하드 월)

        │
        ▼  publish (유저 인터랙션)   ── 무엇을, 어떤 동의로 공개할지 결정
              · 사용 권한(에이전트 참조) + 발견 권한(SKL 추천)을 함께 부여

[ ② 관점 네트워크 · Public / Shared ]   ← "다른 사람의 에이전트와 대화" 제품

  Public Agent Memory
        │  projection
        ▼
  Shared Knowledge Layer (SKL)
    ├─ Topic Space        : 주제별 공유 관점·지식 narrative
    └─ Perspective Index  : 에이전트별 관점·스타일·권한 메타데이터
         └─ Agent Perspective Card = Memory ∩ Persona 의 공개 투영
        │
        ▼  query → topic match → 후보 에이전트 검색·추천
  다른 User ⇄ 추천된 에이전트
```

핵심을 한 줄로 요약하면 다음과 같다.

> 개인 대화로 **Memory와 Persona**가 자란다 → 주인이 **publish**한 일부가 **Public Agent Memory**로 공개된다 → 그것이 **SKL**에 투영되어, 다른 유저가 정답 문서가 아니라 **관점을 가진 에이전트를 발견하고 대화**하게 한다.

각 구성요소의 상세는 이후 장에서 다룬다 (메모리 계층 4장, SKL 역할·생애주기 5장, SKL 구조 6장, Perspective Card 7장, 작동 흐름 8장, 전체 아키텍처 9장).

---

## 2. 주요 데이터 소스

초기 핵심 데이터 소스는 외부 기록 전체가 아니라, **개인화 에이전트와의 대화 및 대화 중 공유된 미디어**다.

### 2.1 개인화 에이전트와의 대화

- 유저와 개인화 에이전트 사이의 텍스트 대화
- 유저의 관심사, 의사결정 방식, 선호, 반복 패턴이 드러나는 1차 소스
- 에이전트가 유저를 이해하는 가장 중요한 기반

### 2.2 대화 내 미디어 공유

- 대화 중 공유되는 이미지, 문서, 캡처, 링크, 기타 미디어
- 유저가 무엇을 중요하게 보고, 어떤 맥락에서 정보를 해석하는지 이해하는 데 사용
- 단순 파일 저장이 아니라 대화 맥락과 함께 해석되어야 함

### 2.3 외부 데이터 소스의 위치

SNS, 블로그, 캘린더, YouTube, 라이프로깅 등은 초기 primary source가 아니라 이후 확장 가능한 optional enrichment source로 본다.

초기 제품의 중심은 다음에 있어야 한다.

> 대화와 미디어 기반의 persona / memory extraction

---

## 3. Persona와 Memory의 관계

현재는 **Persona**와 **Memory**를 분리해서 생각한다.

중요한 점은 **Memory가 Persona로 승격되는 구조가 아니라는 것**이다. 둘은 같은 raw interaction에서 파생될 수 있지만, 서로 다른 차원의 모델이다.

- **Memory**는 “무엇을 알고, 겪고, 좋아하고, 기억해야 하는가”에 관한 내용이다.
- **Persona**는 “어떻게 생각하고, 말하고, 반응하고, 판단하는가”에 관한 패턴이다.

즉, Memory는 Persona의 하위 개념이 아니고, Persona도 Memory의 고급 형태가 아니다.

둘은 병렬로 존재한다.

```text
Raw Interaction
  ├─ Memory Extraction
  │   ├─ facts
  │   ├─ preferences
  │   ├─ events
  │   └─ relationships
  │
  └─ Persona Modeling
      ├─ communication style
      ├─ thinking style
      ├─ decision style
      ├─ values
      └─ emotional / social style
```

### 3.1 Memory

Memory는 “무엇을 알고 있는가”에 가깝다.

Memory에는 유저와 관련된 사실, 경험, 선호, 관계, 과거 맥락, 공유된 정보 등이 포함된다.

예시는 다음과 같다.

- 사용자는 특정 주제에 관심이 있다.
- 사용자는 어떤 프로젝트를 진행 중이다.
- 사용자는 특정 사람과 어떤 관계를 가진다.
- 사용자는 이전에 어떤 판단을 했다.
- 사용자는 어떤 미디어를 공유했고, 그에 대해 어떤 반응을 보였다.

Memory는 비교적 명시적이고, 추가·수정·삭제·검증이 가능한 정보다.

### 3.2 Persona

Persona는 “어떤 사람 또는 에이전트처럼 반응하는가”에 가깝다.

Persona에는 유저의 말투, 사고방식, 가치관, 감정 반응, 대화 스타일, 선호하는 설명 방식 등이 포함된다.

예시는 다음과 같다.

- 사용자는 짧고 구조화된 답변을 선호한다.
- 사용자는 결론을 먼저 듣는 것을 좋아한다.
- 사용자는 직설적 피드백을 선호한다.
- 사용자는 전략적/시스템적 사고를 자주 한다.
- 사용자는 특정 주제를 볼 때 장기적 관점에서 판단한다.

Persona는 단일 발화에서 확정하기보다, 반복 패턴을 통해 천천히 형성되어야 한다.

### 3.3 Memory와 Persona의 상호작용

Memory와 Persona는 별도 차원이지만, 서로 영향을 줄 수 있다.

예를 들어 “사용자가 짧은 답변을 선호한다”는 정보는 다음 두 방식으로 사용될 수 있다.

- Memory 관점: 사용자의 명시적 선호로 저장
- Persona 관점: 반복적으로 관찰되는 communication style의 evidence로 사용

따라서 더 정확한 표현은 다음과 같다.

> Memory가 Persona로 승격되는 것이 아니라, 일부 Memory가 Persona를 추론하는 evidence로 사용될 수 있다.

추론 단계에서는 둘이 조합된다.

> Memory는 “무슨 맥락을 참고할지”를 정하고, Persona는 “그 맥락을 어떤 방식으로 사용할지”를 정한다.

또한 둘이 **공개 가능한 형태로 함께 투영되는 지점**이 하나 있는데, 그것이 뒤에 나오는 **Agent Perspective Card**다. Perspective Card는 Memory(무엇을 알고 어떤 입장인가)와 Persona(어떻게 말하는가)를 한 장에 담는다. 이에 대해서는 7장에서 다시 설명한다.

**추출과 저장: 넓게 관찰하고, 늦게 해석한다.** LLM은 대화에서 Memory·Persona 후보를 꽤 잘 뽑지만, "사실/지식/의견/취향/성향"을 항상 깨끗하게 분리하지는 못한다 — 언어 안에서 이 경계가 자주 겹치기 때문이다. 예컨대 "초기 스타트업은 PLG보다 founder-led sales가 먼저다"라는 한 문장에는 *관심 주제(GTM)·의견(직접 영업 우선)·선호(현장 검증 중시)·도메인 지식·성향 evidence*가 동시에 들어 있다. 그래서 추출은 한 항목에 타입 하나를 박는 분류가 아니라, **여러 축을 동시에 다는 다중 라벨링**으로 본다.

- 후보마다 `fact / preference / opinion / knowledge / relationship / persona_evidence` 같은 축을 **배타적이지 않게** 부여한다.
- 각 후보는 **원문 evidence와 context를 반드시 연결**하고, 확정값이 아니라 `extraction_confidence · source · observed_at · revision 가능성`을 달고 저장한다. 여기서 `extraction_confidence`는 *추출 후보 자체*의 신뢰도이며, `persona_maturity`(페르소나 추정 성숙도)·`perspective_confidence`(관점 근거 강도)와는 다른 신호다.
- **Persona는 단발 발화로 갱신하지 않는다.** 반복 관찰이 쌓이며 `persona_maturity`가 천천히 오른다 (3.4).

핵심은 **Memory와 Persona는 별도 차원으로 두되, 그 근거가 되는 evidence(원문 관찰)는 둘이 공유한다**는 점이다. 위 "짧게 답해줘"가 Memory(명시적 선호)이자 동시에 Persona evidence(brevity 성향)였던 것처럼, 한쪽을 다른 쪽으로 환원하면 정보가 손상된다. 특히 preference가 겹쳐 보이기 쉬운데 — **명시적으로 표현된 preference는 Memory 항목**이고, **반복 패턴에서 추정된 preference function은 Persona core**다. 같은 "선호"라도 층위가 다르다.

> 그래서 이 시스템이 피해야 할 패턴은 "LLM이 한 번 판단했으니 이건 Persona다 / Memory다"라는 **단정 저장**이다. 더 안전한 모델은 **관찰은 넓게 저장하고, 해석(코어·입장 확정)은 늦게 한다.**

### 3.4 Persona의 내부 구조: stable core ⊥ contextual overlay

Persona는 단일 평면이 아니라 두 층으로 본다.

- **stable core (맥락이 바뀌어도 유지되는 안정적 코어)**: 심리학 연구에 기반한 소수의 *축*으로 표현된다. 자기 진술로 일부 드러나기도 하지만 대부분은 여러 맥락의 관찰에서 추정되며, 단순한 사실·데이터가 아니라 그 사실에 대한 **그 사람의 의견·취향·선호·가치**가 이 코어를 이룬다.
- **contextual overlay (맥락에 따라 다르게 관찰되는 표층)**: 대화 상대, 상황, 사용자가 처한 맥락, 장소, 시간 등 여러 변수에 따라 코어가 통과해 나오는 **컨텍스트 게이트**다. 코어가 그대로 표현되는 pass-through일 수도, 왜곡일 수도, 사회적 가면처럼 코어와 다르게(때로는 반대로) 나타날 수도 있다.

즉 대화에서 관찰하는 것은 코어 그 자체가 아니라 **"코어 × 컨텍스트 게이트"의 출력**이다(직관일 뿐, 수학적 분해를 뜻하지 않는다). 따라서 관찰을 곧바로 persona core로 저장하지 않는다.

- 각 관찰을 **상황·상대·주제·감정 상태 같은 context와 함께** 기록한다.
- 여러 context에서 **반복되는 안정적 패턴은 core 후보**로, **특정 context에서만 나타나는 변형은 overlay**로 분리해 추정한다. core 후보가 더 많은 context에서 반복될수록 `persona_maturity`가 오른다.
- 단순 평균은 피한다. 예: 평소 직설적인 사람이 투자자 미팅·공개 발표에서만 조심스럽다면, "약간 직설+약간 조심"으로 평균 내지 않고 — **core = 직설적**, **overlay = 권위자·공개·고위험 상황에서 조심스럽게 필터링**으로 본다.

서로 모순돼 보이는 관찰은 대개 "코어가 바뀐 것"이 아니라 "다른 게이트를 통과한 것"이다.

**점진적 추정과 변화 탐지.** LLM은 사람의 페르소나 회로를 완성된 회로도처럼 한 번에 발견할 수 없다. 대신 대화를 통해 입력→출력 관계를 **점진적으로 추정**하며, "완벽히 안다"가 아니라 조금씩 더 깊고 정교해진다. 그래서:

- Persona 추정이 얼마나 믿을 만한가는 사실의 참/거짓이 아니라 **`persona_maturity`(추정 성숙도)**로 본다 — 얼마나 많고 일관된 관찰로 무르익었는가. 이는 SKL 랭킹·Perspective Card의 **`perspective_confidence`**(관점의 근거 강도)와는 다른 층의 신호이며, 이름부터 구분한다.
- **변화 탐지**가 명시적 메커니즘이 되어야 한다. 새 관찰이 들어왔을 때 "코어가 실제로 drift했는가" vs "단지 다른 컨텍스트 게이트를 통과했는가"를 구분해, 전자만 코어를 수정하고 후자는 overlay 모델을 보강한다.

**Memory와의 경계.** 이 2층 구조는 Memory ⊥ Persona를 흔들지 않는다 (Persona *내부* 구조일 뿐이다). 다만 경계를 분명히 하면: 특정 **의견·선호의 *내용***("PLG보다 직접 영업이 우선")은 저장·검증 가능한 **Memory** 항목이고, 그 의견을 생성하는 **안정적 성향·가치·취향 함수**가 **Persona core**다. 코어와 Memory가 만나 구체적 의견이 만들어진다.

### 3.5 사용자 모델을 채우는 방식: 흐름을 깨지 않는 프로빙

이 점진적 추정에 필요한 신호를 모으는 방식에도 원칙이 있다.

- **질문만 던지는 시스템은 쓰이지 않는다.** 시스템은 기본적으로 대화를 통해 유저를 이해하되, 모델의 빈 곳을 채우기 위한 질문을 *대화 맥락을 해치지 않고* 적절한 타이밍에 하나씩 자연스럽게 섞어 던진다. 빈 곳 중에서도 **추정 가치가 높은 곳**부터 채운다.
- **온보딩도 질문 set 덤프가 아니다.** OAuth 로그인 등으로 가져올 수 있는 정보는 묻지 않고, 정말 기본 질문 3개 정도만 던진다. 그다음은 유저의 정보·답변과 부가 정보(문화권, 시간 등)로 **추론해 개인화된 질문을 생성**한다. 온보딩의 목표는 "그 사람을 다 이해한다"가 아니라 **개인화된 출발점**을 만드는 것이다.
- **능동적 자기노출 유도.** 이 프로빙이 잘 작동하려면 유저가 스스로를 더 능동적으로 드러내고 싶어져야 한다. 그 위에 agent character, dialogue design, gamified feedback 같은 UX 레이어가 함께 설계되어야 한다.

(질문을 어떤 런타임 컴포넌트가 생성·주입하는지는 구현 문제로 별도 문서에서 다룬다.)

---

## 4. 메모리 계층 구조

개인화 에이전트의 메모리는 접근 범위에 따라 최소 세 계층으로 나눌 수 있다.

세 계층의 접근 규칙을 먼저 한눈에 정리하면 다음과 같다.

| 계층 | 소유 | 접근 주체 | 타인이 내 에이전트와 대화할 때 |
|---|---|---|---|
| Private Memory | 주인 | 주인 ↔ 본인 에이전트 대화에서만 | **참조 불가 (하드 월)** |
| Public Agent Memory | 에이전트 | 그 에이전트만 | **에이전트가 참조 가능** |
| Shared Knowledge Layer | 공유 | 발견·추천 인덱스 | 라우팅(추천)에만 사용 |

핵심 원칙은 다음과 같다.

> Private Memory는 외부 대화에서 접근 경로 자체가 없다. 타인이 내 에이전트와 대화할 때 에이전트가 참고할 수 있는 것은 오직 Public Agent Memory뿐이다.

### 4.1 Private Memory

Private Memory는 주인과 개인화 에이전트의 대화에서만 접근 가능한 메모리다.

포함될 수 있는 정보는 다음과 같다.

- 유저의 개인적 사실
- 취향과 선호
- 성향과 성격
- 관계와 맥락
- 주인과의 대화에서만 의미 있는 정보
- 민감하거나 사적인 정보

Private Memory는 개인화의 핵심이지만, 가장 강한 프라이버시 보호가 필요하다.

### 4.2 Public Agent Memory

Public Agent Memory는 해당 개인화 에이전트가 소유하는 **공개 메모리**다. 외부 유저가 직접 열람하는 공개 DB가 아니라, **외부 대화에서 그 에이전트가 참조하도록 공개 승인된 메모리**다 — 들고 다니는 주체가 그 에이전트 하나뿐이라 내부적으로 'agent-scoped'라 부르기도 하지만, 담긴 내용의 성격은 공개 정보다.

예시는 다음과 같다.

- 해당 에이전트의 대화 스타일
- 해당 에이전트가 대표하는 관점
- 에이전트가 특정 주제에서 갖는 전문성 요약
- 다른 유저가 이 에이전트와 대화할 때 참고 가능한 공개 프로필

Public Agent Memory는 “이 에이전트가 어떤 존재인가”를 구성한다.

이 계층의 내용은 처음부터 여기에 직접 쌓이는 것이 아니라, **Private Memory에서 파생(publish)되어 넘어온다.** 즉 주인의 유저 인터랙션을 통해 private한 내용이 public으로 공개된다. 어떤 내용을, 어떤 규칙으로, 어떤 동의를 거쳐 공개할지의 구체적인 UI/UX는 다음 단계에서 다룬다. 다만 모델 차원에서 중요한 점은 다음 두 가지다.

- public으로 넘어가는 경로는 **Private → Public Agent Memory 파생(publish) 단계 하나**로 모이며, 누출 위험도 전적으로 이 시점에 집중된다. 그래서 publish는 단일 클릭이 아니라 최소 파이프라인(privacy classifier → 주인 승인 → audit log)을 거친다 (5.2 참고).
- 이렇게 공개되는 순간, 그 관점·지식은 **Shared Knowledge Layer에도 함께 반영된다.** (publish = 사용 권한 + 발견 권한이 한 묶음 — 5장 참고)

> 용어 주의: 'Public Agent Memory'와 '공개 메모리'는 **모델 차원의 이름**이다. 외부 유저가 프로필처럼 직접 열람한다는 뜻이 아니므로(위 참조), UX·API 표면에서는 *Approved / Published Agent Context* 같이 오해가 덜한 라벨을 쓸 수 있다 — publish와 마찬가지로 모델 용어와 UX 라벨은 별개 층위다 (5.2 참고).

### 4.3 Shared Knowledge Layer

Shared Knowledge Layer(이하 SKL)는 모든 개인 정보를 모아 직접 답변하는 정답 DB가 아니다.

대신, 여러 개인화 에이전트들이 주인과의 대화에서 형성한 지식, 관점, 전문성, 사고방식의 요약 메타레이어다.

핵심 목적은 다음과 같다.

> 어떤 에이전트가 어떤 관점과 지식을 가지고 대화할 수 있는지를 찾고 추천하는 것

---

## 5. Shared Knowledge Layer의 역할

Shared Knowledge Layer는 정보를 직접 제공하는 저장소가 아니라, **에이전트 발견과 추천을 위한 관점 인덱스**다.

즉, 사용자가 어떤 질문을 했을 때 Shared Knowledge Layer가 직접 답변을 생성하는 것이 아니다.

대신 다음을 찾아준다.

- 이 주제에 대해 강한 관점을 가진 에이전트
- 이 분야 경험이나 지식이 축적된 에이전트
- 특정 방식으로 문제를 바라보는 에이전트
- 특정 대화 스타일을 가진 에이전트
- 유저가 지금 대화하면 도움이 될 만한 에이전트

예를 들어 유저가 “초기 스타트업 GTM 전략을 고민 중”이라고 말하면, Shared Knowledge Layer는 GTM 정답을 주는 것이 아니라 다음과 같은 에이전트를 추천한다.

- B2B SaaS 창업자 관점의 에이전트
- PLG 성장 경험이 많은 에이전트
- 엔터프라이즈 세일즈 관점의 에이전트
- 실전적이고 직설적인 조언을 주는 에이전트

그 후 유저는 해당 에이전트와 직접 대화하면서 그 에이전트의 관점과 지식을 기반으로 대화를 이어간다.

**SKL이 담지 않는 것 — 그리고 왜.** SKL을 "정답 DB가 아니다"라고만 말하면 부족하다. 무엇을 *담지 않는지*, 그리고 왜 안 담는지가 더 중요하다. 판단 기준은 **대체 가능성(fungibility)**이다.

- **세계 지식 (fungible)** — 누구에게 물어도 같은 답이 나오는 일반 지식은 SKL의 고유 적재물이 아니다. 이런 지식은 이미 LLM 가중치에 압축적으로 들어 있고, 최신성·정확성·출처가 중요한 영역이라면 별도 검색/RAG/도구로 보강하면 된다 — 어느 쪽이든 SKL이 직접 소유·복제할 대상은 아니다.
- **개인적 사실** — 이것은 SKL이 아니라 private / public agent memory 계층의 몫이다.
- **non-fungible 관점 (의견·취향·입장·스타일)** — *누구의* 것인지가 본질이라 중립 모델로 뭉갤 수 없는 이 층만이 SKL의 고유 적재물이다. 즉 SKL은 "무엇이 사실인가"가 아니라 **"이 사람이 그것을 어떻게 보는가"**를 사람에 귀속시켜 담는다.

또 하나의 결정적 이유는 **에이전트와의 연결을 끊지 않기 위해서**다. SKL이 완전한 답을 들고 있으면 유저는 그 에이전트와 대화할 이유가 사라진다 — 제품의 핵심 가치인 연결을 스스로 disintermediate하게 된다. 따라서 SKL은 **의도적으로 답으로서 불완전**해야 한다. "누가, 어떤 주제를, 어떻게 보는가"까지만 주고, 나머지(실제 내용·맥락·뉘앙스)는 대화 뒤에 둔다.

> 비유: 관점 요약 = 광고, 대화 = 제품. 광고에 제품을 다 넣으면 제품 수요가 사라진다.
>
> 정리: SKL은 **payload가 아니라 pointer**다. Fungible 지식 → LLM, 개인적 사실 → memory 계층, non-fungible 관점 → SKL(사람에 귀속, pointer로만).

여기서 말하는 non-fungible 관점이 페르소나 차원에서 어떻게 생기는지는 3.4(stable core ⊥ contextual overlay)에서, 한 장의 카드로 어떻게 공개·라우팅되는지는 7장(Agent Perspective Card)에서 다룬다. 셋은 "코어의 의견·취향 → publish → 카드로 투영 → SKL의 발견 단위"라는 하나의 사슬이다.

### 5.1 SKL은 독립 저장소가 아니라 projection이다

Shared Knowledge Layer는 별도로 write되는 독립 store가 아니다. Public Agent Memory가 publish될 때 그로부터 갱신되므로, **SKL은 Public Agent Memory를 topic 단위로 비춘 projection(투영)**으로 보는 것이 정확하다.

이 관점의 장점은 다음과 같다.

- public 정보의 **단일 진실 원천(single source of truth)은 Public Agent Memory 하나**다.
- Topic Space와 Perspective Index는 독립적으로 수정되는 것이 아니라 같은 publish 이벤트로부터 함께 갱신되므로, 둘 사이의 sync 문제가 상당 부분 자동으로 해소된다. (12.2 참고)

여기서 "함께 갱신"은 **논리적 동시성**이지 물리적 실시간 동기화가 아니다. 실제 갱신은 publish 이벤트를 받아 약간의 지연을 두고 반영된다. 또 SKL은 어디까지나 Public Agent Memory의 projection이므로, 원본만 보존되면 **언제든 다시 빌드할 수 있다.** 이 두 성질(지연 허용 + 재빌드 가능)이 뒤따르는 갱신/생애주기 설계의 전제가 된다 (5.3 참고).

### 5.2 publish는 사용 권한과 발견 권한을 함께 켠다

publish 한 번이 두 가지 권한을 동시에 부여한다.

- **사용 권한**: 누군가 내 에이전트와 대화할 때 에이전트가 이 정보를 참조할 수 있다.
- **발견 권한**: SKL을 통해 내 에이전트가 이 주제로 검색·추천된다 (`discoverable: true`).

초기(MVP)에는 **이미 공개된 정보라는 전제 아래 이 둘을 하나로 묶는다.** 즉 publish = 사용 + 발견이며, 별도 토글을 두지 않는다. "public agent memory로는 공개하되 SKL 추천에는 띄우지 않는다"와 같이 둘을 분리하는 `discoverable` 토글은 필요해지는 시점에 향후 확장으로 연다.

**publish 파이프라인 (최소).** private 누출은 이 시스템의 최대 리스크다. 따라서 publish는 단일 동작이 아니라 최소한 다음 단계를 거치는 것으로 본다.

> publish candidate 생성 → **privacy classifier**(자동 민감정보·PII 검사) → **user review**(주인 승인) → **immutable audit log**(무엇이·언제·왜 공개됐는지 append-only 기록) → **projection**(Public Agent Memory 반영 + SKL 갱신)

- candidate는 자동 생성할 수 있지만, **공개 확정은 반드시 주인 승인 이후**다 (4.2).
- **audit log는 불변(append-only)**으로 남겨 공개 이력과 책임 소재를 추적할 수 있게 한다. 공개 철회(revoke)도 이 로그 위에서 다룬다 — 해당 항목을 Public Agent Memory에서 비공개로 되돌리고, SKL projection에서는 다음 재빌드 때 빠지도록 무효화하며, 이미 외부 대화에 실린 cached context는 TTL/무효화로 만료시키고, audit log에는 삭제가 아니라 `revoke` 이벤트를 덧붙인다(불변 원칙 유지).
- 이 파이프라인은 이벤트 문서의 `MemoryCandidate → Safety Processor → 승인 → PublicKnowledgeIndexed` 체인과 대응한다.

누출 방지의 대규모 대비(자동 PII 탐지 강화, 추론 공격 방어)는 13.5, 남은 설계 쟁점은 12.3에서 다룬다.

> 용어 주의: 여기서 **publish는 모델 차원의 개념**이다 — 동의를 거친 Private → Public Agent Memory 전이를 가리키는 단일 게이트의 이름이다. 유저 대면 표현이나 이를 관리하는 설정 화면까지 "publish"라고 부를 필요는 없으며, 오히려 "공개/공유" 같은 가벼운 동사나 'privacy controls' 같은 프레임이 더 적절할 수 있다. 즉 **모델 용어(publish)와 UX 라벨은 별개 층위**로 본다.

### 5.3 관점의 생애주기: 갱신과 active-set 관리

SKL을 projection으로 두면 곧바로 두 가지 운영 문제가 따라온다. **(1) 갱신을 언제·어떻게 반영할 것인가, (2) 시간이 지나며 무한히 쌓이는 관점을 어떻게 다룰 것인가.** 이 두 문제를 처음부터 설계에 넣어야 SKL이 비대해지거나 발견 품질이 떨어지지 않는다. 아래 메커니즘은 대규모 대비책이 아니라 **MVP 단계부터 필요한 핵심 설계**다.

#### 5.3.1 갱신은 debounce 배치로 (왜 실시간이 아니어도 되는가)

새 관점이 publish된 직후 곧바로 검색에 떠야 할 이유는 없다. 관점이 몇 분 늦게 발견 가능해져도 제품 경험에는 영향이 없다. 이 **"실시간 불필요"** 성질을 활용해, 같은 토픽에 대한 publish들을 일정 윈도 동안 모아 **한 번의 배치로 반영(debounce)**한다.

- **왜 필요한가**: publish를 들어오는 즉시 반영하면, 인기 토픽에서 같은 대상에 대한 동시 쓰기 경합이 생긴다. debounce는 이를 "토픽당 윈도당 1회 반영"으로 직렬화해 **쓰기 경합 자체를 제거**하고, 재작성 횟수(write amplification)도 배치 계수만큼 줄인다.
- **손실 안전망**: debounce 윈도 사이에 장애가 나도, SKL은 Public Agent Memory의 projection이므로 **원본에서 다시 빌드**하면 된다. 따라서 배치 손실은 치명적이지 않다. (단, raw publish 이벤트 자체는 durable하게 남겨야 한다.)

#### 5.3.2 active-set은 freshness와 perspective_confidence로 관리 (왜 무한히 쌓으면 안 되는가)

publish가 누적되면 한 토픽의 관점 수가 무한히 늘어난다. 모든 관점을 영구히 hot 상태로 두면 SKL이 비대해지고, 오래되거나 약한 관점이 검색을 어지럽혀 **발견 품질이 떨어진다.**

그래서 SKL이 실제로 들고 있는 것은 전체가 아니라 **active-set**이다. 관점은 두 신호로 관리된다.

- **freshness(최신성)**와 **perspective_confidence(품질·근거 강도)**를 **결합**해 축출 여부를 정한다.
- 축출 기준은 **"오래되었고 *동시에* 저품질"**인 경우로 한정한다. 오래되었어도 perspective_confidence가 높은 evergreen 관점은 active-set에 유지한다.
- 축출된 관점은 삭제가 아니라 cold 저장소로 내려, 필요 시 복구 가능하게 둔다 (compaction은 5.3.1의 배치에서 함께 수행).

이렇게 하면 한 토픽의 active-set 크기가 "역대 누적 인구"가 아니라 **"의미 있게 활성/유효한 인구"**로 bound된다. 이것이 단순한 단일 저장 모델(논리적으로 파일로 표현하든, 물리적으로 단일 DB든 — 6장 표기 주의 참고)에서도 SKL이 작게 유지되는 핵심 이유다.

> 요약: **debounce(언제 반영) + freshness·perspective_confidence 결합 축출(무엇을 유지)**가 SKL을 작고 신선하게 유지한다. 둘 다 "실시간 불필요"와 "projection은 재빌드 가능"이라는 두 전제 위에서 성립한다.

---

## 6. Shared Knowledge Layer의 구조

> **표기 주의 — 논리 구조 vs 물리 저장**: 이 장에서 `topic.md` / `perspectives.yaml` 같은 **파일·디렉토리 표기는 구조를 사람이 읽기 쉽게 보여주기 위한 *논리 모델*이다. 파일로 구현하라는 뜻이 아니다.** 런타임은 stateless하게 동작하므로(워커 간 공유 파일시스템 부재, 쓰기 동시성·락 문제) 파일 기반 저장은 부적합하다. **물리적으로는 MVP에서도 이 논리 구조를 데이터베이스에 투영해 저장한다.**
> 따라서 이후 이 장과 13장에 나오는 'MVP=파일 / 이후=DB' 식 표기도 *파일→DB 전환*이 아니라, **같은 논리 구조를 단일 DB → 분산/특화 저장으로 키우는 것**으로 읽어야 한다. (구체 DB 제품은 지정하지 않는다.)

Shared Knowledge Layer는 하나의 문서 저장소가 아니라, **Topic Space**와 **Perspective Index**가 결합된 동적 지식/관점 레이어로 보는 것이 적절하다.

중요한 원칙은 다음과 같다.

> Topic Space와 Perspective Index는 논리적으로는 분리하되, 초기 구현에서는 같은 topic 단위 패키지 안에서 함께 관리한다.

즉, 둘은 역할이 다르다.

- **Topic Space**는 사람이 읽고 LLM이 맥락으로 사용할 수 있는 주제별 narrative/context 레이어다.
- **Perspective Index**는 에이전트 검색, 추천, 권한, `perspective_confidence`, freshness 관리를 위한 structured metadata 레이어다.

```text
Shared Knowledge Layer
  ├─ Topic Space
  │   ├─ 주제별 공유 지식 요약
  │   ├─ 반복적으로 등장하는 관점
  │   ├─ 관점 간 차이
  │   └─ 관련 에이전트 연결
  │
  └─ Perspective Index
      ├─ 특정 에이전트가 특정 주제에서 가진 관점
      ├─ 대화 스타일
      ├─ 추천 가능한 사용 사례
      ├─ evidence_strength / perspective_confidence
      └─ access policy
```

### 6.1 왜 완전 분리하지 않는가

초기부터 Topic Space와 Perspective Index를 완전히 다른 저장소나 디렉토리로 나누면 다음 문제가 생길 수 있다.

```text
/topic-space/startup-gtm.md
/perspective-index/startup-gtm.yaml
```

이 방식은 개념적으로는 깔끔하지만, MVP 단계에서는 운영 복잡도가 높다.

문제가 될 수 있는 지점은 다음과 같다.

- topic 내용은 업데이트됐는데 perspective index는 오래된 상태로 남을 수 있음
- agent card는 있는데 topic summary에는 반영되지 않을 수 있음
- 같은 관점이 여러 위치에 중복 저장될 수 있음
- 사람이 읽고 수정하기 어려워질 수 있음
- topic과 perspective 사이의 연결 관계를 별도로 관리해야 함

따라서 초기에는 완전 분리보다 **같은 topic 단위 안에서 함께 관리**하는 편이 적절하다.

### 6.2 왜 하나의 문서에 완전히 섞지 않는가

반대로 하나의 markdown 문서 안에 narrative와 YAML metadata를 모두 섞는 방식도 장기적으로는 위험하다.

예시는 다음과 같다.

```text
# Startup GTM

## Summary
...

# ↓ 같은 .md 파일 안에 구조화 메타데이터가 그대로 박힌다
agent_perspective_cards:
  - agent_id: ...
    stance: ...
```

이 방식은 처음에는 읽기 쉽지만, 시간이 지나면 다음 문제가 생긴다.

- structured data 파싱이 불편해짐
- ranking, filtering, permission check에 쓰기 어려움
- perspective card의 부분 업데이트가 어려움
- 에이전트 수가 많아질수록 문서가 비대해짐
- 사람이 읽는 문서와 시스템이 읽는 metadata의 목적이 섞임

특히 Perspective Index는 이후 다음 기능에 사용될 가능성이 높다.

- agent search
- agent ranking
- permission filtering
- freshness 계산
- perspective_confidence update
- graph traversal
- agent recommendation

따라서 Perspective Index는 처음부터 structured data로 분리해 다루는 것이 좋다.

### 6.3 논리 구조 예시: 같은 topic 단위 안의 narrative/metadata 분리

논리 구조는 topic 단위로 묶는다. 아래 디렉토리/파일 표기는 그 **논리 레코드 예시**이며, 물리 저장은 DB다(6장 머리 표기 주의 참고).

```text
/shared-knowledge-layer/
  startup-gtm/
    topic.md
    perspectives.yaml
```

조금 더 확장하면 다음과 같다.

```text
/shared-knowledge-layer/
  startup-gtm/
    topic.md
    perspectives.yaml
    agents/
      agent_123.yaml
      agent_456.yaml
```

각 파일의 역할은 다음과 같다.

| 파일 | 역할 |
|---|---|
| `topic.md` | 사람이 읽는 주제 요약, 주요 관점, 논점 구조 |
| `perspectives.yaml` | 에이전트 추천/검색용 structured metadata |
| `agents/*.yaml` | 규모가 커졌을 때 agent별 perspective card 분리 |

물리 구현(DB)에서는 이 논리 구조가 다음처럼 매핑되고, 규모가 커지면 다음으로 분화한다.

```text
Topic Space = document store / object store
Perspective Index = structured DB or graph index
```

### 6.4 Topic Space

Topic Space는 여러 에이전트가 공개 또는 공유한 지식과 관점을 주제별로 조직한 공간이다.

이 레이어는 전통적인 wiki처럼 고정된 문서 저장소로 이해되면 안 된다. 더 정확히는 주제별로 축적된 지식, 관점, 메타데이터, 에이전트 연결이 함께 관리되는 **동적 knowledge/perspective space**다.

LLM 기반 지식 조직 방식이나 open knowledge sharing 포맷에서 볼 수 있는 것처럼, 요약·맥락·메타데이터·관점 차이를 함께 관리하는 패턴은 참고할 수 있다. 다만 특정 포맷을 고정 표준으로 삼기보다는, 제품 목적에 맞게 가볍고 진화 가능한 구조로 시작하는 것이 좋다.

`topic.md` 예시는 다음과 같다.

```md
# Startup GTM

## Summary
초기 스타트업 GTM에 대해 여러 에이전트에서 반복적으로 공유된 관점 요약.

## Common Patterns
- 초기에는 ICP를 좁히는 것이 중요하다는 관점이 반복됨.
- founder-led sales가 초기 학습에 중요하다는 의견이 많음.
- PLG는 제품 성숙도 이후에 적합하다는 관점이 있음.

## Major Perspectives

### Founder-led Sales
초기에는 창업자가 직접 고객과 대화하며 문제, ICP, 가격 민감도를 검증해야 한다.

### PLG Growth
제품 내 activation loop와 self-serve onboarding을 빠르게 설계해야 한다.

## Linked Perspective Cards
- agent_123: founder-led sales 중심
- agent_789: PLG growth 중심
```

Topic Space의 역할은 다음과 같다.

- 특정 주제에서 반복적으로 등장한 지식과 관점을 요약
- 여러 에이전트 관점의 공통점과 차이점 정리
- 어떤 관점들이 존재하는지 보여줌
- 어떤 에이전트들이 이 주제에 강한지 연결
- LLM이 추천/검색/요약 시 사용할 수 있는 topic-level context 제공

중요한 점은 Topic Space도 정답 문서가 아니라는 것이다.

> Topic Space는 정답을 제공하는 문서가 아니라, 여러 에이전트들이 공유한 관점과 지식을 주제별로 조직한 동적 공간이다.

### 6.5 Perspective Index

Perspective Index는 특정 에이전트가 특정 주제에서 어떤 관점을 가지고 있는지를 나타내는 메타데이터 레이어다.

이 인덱스는 문서 본문이라기보다 다음을 위한 routing layer다.

- 에이전트 검색
- 에이전트 추천
- 권한 확인
- 출처 및 신뢰도 관리
- 대화 스타일 매칭
- 원본 private memory 보호

`perspectives.yaml` 예시는 다음과 같다.

```yaml
topic: startup_gtm

perspectives:
  - agent_id: agent_123
    perspective_id: startup_gtm_founder_sales_agent_123
    perspective_summary: 초기 B2B SaaS에서 founder-led sales와 좁은 ICP 검증을 중시하는 관점.
    useful_for:
      - 초기 GTM 전략 점검
      - ICP narrowing
      - founder sales script 피드백
    stance:
      - 초기에는 PLG보다 직접 고객 대화가 우선
      - 시장보다 ICP 선명도가 먼저
    conversation_style:
      - direct
      - practical
      - framework-oriented
    perspective_confidence: medium
    freshness: 2026-06
    access_policy:
      discoverable: true
      requires_permission: false
      exposes_private_memory: false
```

Topic Space만 존재하면 다음 문제가 생긴다.

- 어떤 지식이 어떤 에이전트 관점에서 나왔는지 흐려짐
- 추천 대상 에이전트를 찾기 어려움
- 권한/출처/신뢰도 관리가 어려움
- 제품이 “에이전트와 대화”가 아니라 “문서 기반 답변”으로 흐를 위험이 있음

따라서 Perspective Index는 필요하다.

### 6.6 정리

정리하면 **논리 구조**는 다음과 같다(파일 표기는 논리 레코드 예시, 물리 저장은 DB).

```text
논리 모델:
  /shared-knowledge-layer/{topic}/topic.md
  /shared-knowledge-layer/{topic}/perspectives.yaml
  (규모 시) /shared-knowledge-layer/{topic}/agents/{agent_id}.yaml

물리 구현:
  MVP        = 단일 DB (문서 + 구조화 인덱스)
  대규모      = Topic Space → document/object store, Perspective Index → 분산 vector/graph index
```

한 문장으로 정리하면 다음과 같다.

> Topic Space와 Perspective Index는 역할이 분리되어야 한다 — 사람이 읽는 narrative와 시스템이 읽는 metadata. 논리적으로는 같은 topic 단위 안에 나누어 표현하고, 물리 저장은 DB다 (6장 머리 표기 주의 참고).

---

## 7. Agent Perspective Card

Agent Perspective Card는 Perspective Index를 구성하는 최소 단위다.

다만 이 카드는 지식 본문이 아니라, **에이전트 추천과 라우팅을 위한 메타데이터 카드**다.

즉, Agent Perspective Card는 “이 에이전트가 무엇을 알고 있는가”를 전부 담는 문서가 아니다.

대신 다음 질문에 답해야 한다.

> 이 에이전트와 대화하면 어떤 주제에서 어떤 관점과 방식으로 도움을 받을 수 있는가?

또한 Agent Perspective Card는 3장에서 설명한 **Memory와 Persona가 공개 표면에서 만나는 지점**이다. 두 차원은 평소 병렬로 존재하지만, 카드 위에서 공개 가능한 형태로 함께 투영된다.

- `stance`, `useful_for` → **Memory 계열** (무엇을 알고 어떤 입장인가)
- `conversation_style` → **Persona 계열** (어떻게 말하는가)

즉 Agent Perspective Card는 **Memory ∩ Persona를 공개 가능한 형태로 투영한 것**으로 이해할 수 있다.

### 7.1 Agent Perspective Card가 필요한 이유

Agent Perspective Card가 필요한 이유는 다음과 같다.

- 주제별 문서와 에이전트 추천을 연결하기 위해
- 특정 관점을 가진 에이전트를 찾기 위해
- private memory를 노출하지 않고도 에이전트의 공개 가능한 전문성을 표현하기 위해
- 에이전트 간 차이를 비교하기 위해
- 권한, 공개 범위, perspective_confidence, freshness를 관리하기 위해

### 7.2 Agent Perspective Card의 예시

```yaml
agent_perspective_card:
  agent_id: agent_123
  topic: startup_gtm

  perspective_summary: >
    초기 B2B SaaS에서 founder-led sales와 좁은 ICP 검증을 중시하는 관점.

  useful_for:
    - 초기 GTM 전략 점검
    - ICP narrowing
    - pricing 실험
    - founder sales script 피드백

  stance:
    - "초기에는 PLG보다 직접 고객 대화가 우선"
    - "시장보다 ICP 선명도가 먼저"
    - "pricing은 value metric 검증과 함께 봐야 함"

  conversation_style:
    - direct
    - practical
    - framework-oriented

  evidence:
    source_type: aggregated_conversations
    evidence_strength: medium        # 원자료의 양·일관성
    perspective_confidence: medium   # evidence_strength에서 산출 (persona_maturity와 구분)
    freshness: 2026-06
    privacy_level: public_summary_only

  access_policy:
    discoverable: true
    requires_permission: false
    exposes_private_memory: false
```

### 7.3 최소 필드

초기에는 다음 필드만 있어도 된다.

```yaml
agent_id: string
topic: string
perspective_summary: string
useful_for: list
stance: list
conversation_style: list
perspective_confidence: low | medium | high   # evidence_strength에서 산출. persona_maturity(페르소나 추정 성숙도)와 다른 신호
freshness: date
access_policy:
  discoverable: boolean
  requires_permission: boolean
  exposes_private_memory: false
```

초기 제품에서는 너무 복잡한 스키마보다, 추천 품질과 프라이버시 경계를 확인할 수 있는 최소 구조가 더 중요하다.

---

## 8. Shared Knowledge Layer의 작동 흐름

전체 작동 흐름은 다음과 같다.

```text
User query
  ↓
Topic match
  ↓
Shared Topic Space에서 관련 주제와 주요 관점 탐색
  ↓
Agent Perspective Card / Index로 후보 에이전트 검색
  ↓
권한, 공개 범위, perspective_confidence, style match 확인
  ↓
에이전트 추천
  ↓
User ↔ Selected Agent 대화
```

이 흐름에서 Shared Knowledge Layer는 직접 최종 답변을 제공하는 것이 아니라, 적절한 에이전트를 찾는 데 사용된다.

즉, 제품 경험의 중심은 다음이다.

> “문서에서 답을 찾는다”가 아니라 “이 관점을 가진 에이전트와 대화한다.”

### 8.1 추천 랭킹: perspective_confidence와 freshness는 분리한다

위 흐름의 "perspective_confidence, style match 확인" 단계에서 가장 중요한 원칙은 **perspective_confidence(품질)와 freshness(최신성)를 별개의 신호로 다루는 것**이다.

- **왜 분리하는가**: freshness를 단순한 hard cutoff(예: "6개월 지난 관점은 제외")로 쓰면, **오래됐지만 가치 있는 evergreen 관점이 발견에서 통째로 사라진다.** 1년 전에 훌륭한 GTM 관점을 남긴 창업자가 단지 최근 활동이 없다는 이유로 추천되지 않는 것은 제품 가치에 반한다. perspective_confidence(이 관점이 얼마나 강하고 근거 있는가)와 freshness(얼마나 최근인가)는 직교하는 축이므로, 하나로 뭉뚱그리면 둘 중 하나를 반드시 희생하게 된다.
- **어떻게 쓰는가**: freshness는 cutoff가 아니라 **ranking의 decay 가중치**로 사용한다. 대략 다음과 같은 형태다.

> `score = relevance × perspective_confidence × freshness_decay × style_match`

이렇게 하면 최신 관점이 자연스럽게 우대받으면서도, perspective_confidence가 높은 evergreen 관점은 살아남는다.

또한 `style_match`는 **stable core의 심리 축 위에서의 거리**로 계산하는 것이 안전하다 (3.4 참고). contextual overlay의 단발 관찰값(특정 대화 한 번의 말투)으로 재면 컨텍스트 게이트 노이즈에 휘둘린다. 에이전트 쪽 스타일도 여러 컨텍스트의 관찰에서 코어를 역산해 추정한 값을 쓴다.

이 분리 원칙은 5.3.2의 active-set 축출과도 일관된다. 축출은 "오래됐고 *동시에* 저품질"일 때만 일어나고(active-set 유지), 랭킹은 그 안에서 perspective_confidence·freshness를 가중치로 조합한다(노출 순서 결정). 단, 실제 가중치 함수와 perspective_confidence·freshness의 계산 방식은 별도의 고도화 설계가 필요하다 (12장 참고).

---

## 9. 전체 아키텍처 관점

전체 시스템은 다음 흐름으로 볼 수 있다.

```text
User ↔ Personal Agent
        ↓
Conversation + Shared Media
        ↓
Raw Memory Store
        ↓
Memory Extraction / Persona Modeling
        ↓
Private Memory                         ← 주인 전용. 외부 대화에서 접근 불가
        │
        │  publish (유저 인터랙션)       ← 어떤 내용을 공개할지 결정
        ▼
Public Agent Memory ──반영──▶ Shared Knowledge Layer
                                          (Topic Space + Perspective Index)
        ↓
                          Agent Discovery / Recommendation
                                          ↓
                                  User ↔ Recommended Agent
```

중요한 방향성은 다음과 같다. Private Memory가 먼저 형성되고, 그중 일부가 **publish 단계를 거쳐 Public Agent Memory로 파생**된다. Shared Knowledge Layer는 이 publish로부터 Public Agent Memory를 비춘 projection으로 갱신된다(실제 반영은 약간의 지연을 두는 비동기 — 5.3 참고). 즉 세 계층이 동시에 갈라지는 것이 아니라, Private → Public Agent Memory → (projection) SKL의 방향이 있다.

각 계층의 역할은 다음과 같다.

| 계층 | 역할 |
|---|---|
| Conversation + Media | 개인화의 원천 데이터 |
| Raw Memory Store | 대화와 미디어의 원본 저장 |
| Memory Extraction | 사실, 선호, 관계, 경험 추출 |
| Persona Modeling | 말투, 사고방식, 성향, 대화 패턴 모델링 |
| Private Memory | 주인과 에이전트만 접근 가능한 메모리. 외부 대화에서 참조 불가 |
| publish (유저 인터랙션) | private 내용을 public agent memory로 공개하는 게이트 |
| Public Agent Memory | 에이전트가 소유·접근. 외부 대화에서 에이전트가 참조 가능 |
| Shared Knowledge Layer | Public Agent Memory의 topic 단위 projection (Topic Space + Perspective Index) |
| Topic Space / Directory | 주제별로 정리된 공유 관점과 지식 |
| Perspective Index | 에이전트별 관점, 스타일, 권한, 추천 메타데이터 |
| Agent Discovery | 유저에게 적절한 에이전트를 추천 |

---

## 10. 제품적 차별점

이 제품의 차별점은 단순한 개인 메모리 저장이 아니다.

핵심 차별점은 다음 네 가지다.

### 10.1 성장하는 개인화 에이전트

에이전트는 유저와 대화할수록 유저의 지식, 취향, 성향, 사고방식을 더 잘 이해한다.

### 10.2 Persona와 Memory의 분리

Memory는 유저가 무엇을 알고 경험했는지 저장하고, Persona는 유저 또는 에이전트가 어떻게 생각하고 말하는지를 모델링한다.

둘은 승격 관계가 아니라 별도 차원이다. 다만 같은 raw interaction에서 추출될 수 있고, 일부 memory는 persona modeling의 evidence로 쓰일 수 있다.

### 10.3 관점 기반 에이전트 네트워크

Shared Knowledge Layer는 정보를 직접 제공하는 정답 DB가 아니라, 다양한 관점과 지식을 가진 에이전트를 발견하게 해주는 네트워크다.

이는 “지식 검색”이 아니라 “관점 검색”이다.

### 10.4 Topic Space + Perspective Index 구조

Shared Knowledge Layer는 Topic Space와 Perspective Index의 결합체다.

Topic Space는 공유된 지식과 관점을 주제별로 조직하고, Perspective Index는 어떤 에이전트와 대화해야 할지 결정하는 추천/라우팅 정보를 제공한다. (둘의 논리/물리 구조는 6장 참고.)

또한 Shared Knowledge Layer는 독립적으로 채워지는 저장소가 아니라 **Public Agent Memory의 topic 단위 projection**이다. publish 한 번이 사용 권한(에이전트 참조)과 발견 권한(SKL 추천)을 함께 켜며, public 정보의 단일 진실 원천은 Public Agent Memory다.

---

## 11. 현재 기준 정리 문장

현재까지의 제품 정의는 다음과 같이 요약할 수 있다.

> 모든 유저는 자신만의 개인화 에이전트를 가진다. 이 에이전트는 유저와의 대화 및 공유 미디어를 통해 memory와 persona를 성장시킨다. Memory는 유저가 무엇을 알고 경험했는지에 대한 정보이고, Persona는 유저 또는 에이전트가 어떻게 생각하고 대화하는지에 대한 별도 모델이다. 둘은 승격 관계가 아니라 병렬 차원이며, 일부 memory는 persona modeling의 evidence로 사용될 수 있다. 각 에이전트는 private memory, public agent memory, shared knowledge layer를 구분해 사용한다. Private memory는 주인과의 대화에서만 접근 가능하며 외부 대화에서는 참조되지 않고, 그중 일부가 주인의 publish 인터랙션을 거쳐 public agent memory로 공개된다. 이 publish는 사용 권한과 발견 권한을 함께 켠다. Shared knowledge layer는 모든 정보를 공개하는 저장소가 아니라, Public Agent Memory를 주제별로 비춘 projection이며 Topic Space와 Perspective Index를 결합한 구조다. 논리적으로는 같은 topic 단위 안에서 narrative와 metadata로 나누어 표현하되(물리 저장은 DB), 역할은 분리한다. 이를 통해 유저는 정답 문서를 받는 것이 아니라, 특정 관점과 지식을 가진 에이전트를 발견하고 그 에이전트와 대화할 수 있다.

---

## 12. 향후 정리할 쟁점

앞으로 더 구체화해야 할 질문을 주제별로 정리한다.

### 12.1 Persona / Memory 모델링

- Persona와 Memory를 각각 어떤 스키마로 정의할 것인가?
- Memory와 Persona가 같은 evidence를 공유할 때 충돌을 어떻게 관리할 것인가?
- Persona feature의 `persona_maturity`(성숙도 — 추정이 얼마나 무르익었는가)와 freshness를 어떻게 계산할 것인가?

### 12.2 발견과 랭킹 (Discovery & Ranking)

- **perspective_confidence/freshness 분리 랭킹의 고도화 설계** — 8.1에서 원칙(분리해서 freshness를 decay 가중치로)은 정했지만, 실제 설계는 더 필요하다. 구체적으로:
  - `score = relevance × perspective_confidence × freshness_decay × style_match`에서 각 항의 **가중치와 결합 방식**을 어떻게 정할 것인가?
  - **freshness decay 곡선**(선형 / 지수 / 토픽별 차등)을 어떻게 설계할 것인가? 토픽마다 정보의 noise/신선도 민감도가 다르다.
  - **`perspective_confidence`(및 그 입력 `evidence_strength`)를 무엇으로 산정**할 것인가? (evidence 양, 관점의 일관성, 사용자 피드백 등)
  - relevance(주제 적합도)와 style match(대화 스타일 적합도)를 어떻게 수치화할 것인가?
- **active-set 축출 정책** — 5.3.2의 "오래됐고 동시에 저품질" 기준을 구체적으로 어떻게 임계화하고, cold로 내린 관점의 복구·재승격은 어떻게 다룰 것인가?
- **갱신 운영** — debounce 윈도 크기, projection 재빌드 트리거/주기는 어떻게 정할 것인가? (5.3.1 참고)
- Agent Perspective Card의 품질을 어떻게 평가할 것인가?
- Topic Space의 구조와 업데이트 규칙, 그리고 `topic.md`와 `perspectives.yaml`의 versioning·ownership을 어떻게 관리할 것인가? (sync 문제는 SKL을 Public Agent Memory의 projection으로 보는 것으로 상당 부분 해소됨 — 5.1 참고)

### 12.3 프라이버시 경계

- Private Memory와 Public Agent Memory의 경계는 어디인가?
- Shared Knowledge Layer에 공개 가능한 정보의 최소 단위는 무엇인가?
- Agent Perspective Card가 private memory를 간접적으로 노출하지 않도록 어떻게 보장할 것인가? (즉 publish 파생 단계에서의 누출 방지)
- 타인이 내 에이전트와 대화할 때, 프롬프트 인젝션·탈옥 등으로 public agent memory 범위를 넘어선 정보를 끌어내려는 시도를 어떻게 방어할 것인가? (private는 접근 경로 자체가 없어 하드 월로 보장되지만 — 4.1·4.2 — LLM 서빙 레이어는 별도의 공격면이다)

### 12.4 제품 경험

- Shared Knowledge Layer가 “정보 제공”이 아니라 “에이전트 추천”으로 작동하도록 제품 경험을 어떻게 설계할 것인가?
- 유저가 스스로를 더 능동적으로 드러내고 싶게 만드는 UX 레이어(agent character, dialogue design, gamified feedback)를 어떻게 설계할 것인가? (3.5 참고)

---

## 13. 확장성 고려사항 (Scale-out)

이 절은 MVP 범위가 아니라, 서비스가 대규모(예: 1억 유저 이상)로 성장했을 때를 대비한 **향후 과제**다.

**전제**: 본문에 이미 들어간 핵심 메커니즘 — **5.3의 debounce 갱신 + freshness·perspective_confidence 결합 active-set 축출**, **8.1의 분리 랭킹** — 이 적용되어 있다고 가정한다. 이 메커니즘들 덕분에 단순한 단일 저장 모델(6장 표기 주의 참고 — 논리는 파일, 물리는 단일 DB)에서도 한 토픽의 active-set이 작게 유지되고 쓰기 경합이 사라지므로, **상당한 초기 트래픽까지는 단일 저장 구조로도 운영 가능할 가능성이 높다.** 정확한 한계는 publish 빈도·topic cardinality·active-set 크기·LLM 호출 정책에 따라 달라지며, 부하 모델 없이 특정 숫자를 단정하지는 않는다. 아래 항목들은 그 이후, 즉 **active-set 자체나 집계 규모가 단일 노드의 한계를 넘어설 때** 비로소 문제가 되는 것들이다.

또 하나의 전제는 다음과 같다.

> Private / Public Agent Memory는 유저·에이전트 단위로 샤딩되는 수평 확장 구조라 규모 자체가 큰 문제가 아니다. 확장성 리스크는 거의 전부 **공유 레이어(SKL)와 LLM 파이프라인**에 집중된다.

### 13.1 SKL 저장 구조: 단일 DB → 분산 벡터 인덱스

active-set 축출(5.3.2)로 토픽별 크기는 bound되지만, 토픽 수와 에이전트 수가 함께 늘면 **집계 규모**(전체 토픽 × 에이전트)가 결국 단일 DB의 한계를 넘는다.

- 대응: Perspective Index를 **분산 vector DB + ANN 인덱스**로 전환. `agent_id × topic × perspective`를 임베딩 + 구조화 메타데이터로 색인.
- 이는 단순 저장소 교체가 아니라 **retrieval/ranking 문제로의 전환**이다 (13.3 참고).

### 13.2 단일 토픽의 active-set이 거대해질 때

5.3.2로 대부분의 토픽은 active-set이 평형을 이루지만, **지속적으로 초인기인 토픽**은 freshness 윈도 안에서도 활성 인구가 수십만 이상으로 커질 수 있다. 이때는 토픽 하나조차 단일 narrative/단일 인덱스로 감당이 안 된다.

- 대응: 토픽을 평면이 아니라 **계층/클러스터 구조**로. 관점을 임베딩 클러스터링해 sub-perspective로 쪼개고, narrative는 대표 클러스터만 동적 생성한다. 즉 `topic.md`는 "전체 요약"이 아니라 "클러스터 인덱스"가 된다.
- 토픽 내부도 **샤딩**(sub-topic / 클러스터 단위)한다.

### 13.3 Discovery = 대규모 retrieval + ranking

8장·8.1의 발견·랭킹 로직 자체는 본문에서 정의되지만, 대규모에서는 그것을 **분산 실행**하는 문제가 남는다 (1억 에이전트 × 다수 토픽 = 수십억 perspective 벡터).

- **분산 ANN**(ScaNN/FAISS/vector DB) 필수.
- **권한 필터링을 인덱스 안으로 push-down**: `access_policy`를 query 시점 post-filter로 처리하면 수십억 후보를 스캔하게 된다. 파티셔닝/메타 필터로 pre-filter해야 한다.
- **고정 topic taxonomy 회피**: 대규모 토픽 공간은 long-tail이다. 사전 정의 디렉토리가 아니라 **임베딩 기반 동적 토픽 발생/클러스터링**으로 가야 한다.

### 13.4 LLM 파이프라인 비용

저장소보다 비용 비중이 큰 영역이다.

- **Memory Extraction / Persona Modeling**: 메시지마다 LLM 호출은 1억 유저 규모에서 하루 수십억 콜이 된다. → 증분 업데이트 + 배치 재계산, extraction용 소형(distill) 모델, 매 메시지가 아닌 트리거 기반 갱신.
- **타인 에이전트와의 대화 서빙**: 매 대화가 persona + public agent memory를 컨텍스트로 올리는 풀 LLM 세션이다. → persona 캐싱, 컨텍스트 압축.
- **Hot agent 문제**: 소수 에이전트(셀럽/전문가)에 쿼리·대화가 쏠린다. → per-agent rate limit, 캐싱, 컨텍스트 복제.

### 13.5 Privacy at scale

- publish 시 private→public 자동 추출의 누출률이 매우 낮아도, 수십억 카드 규모에서는 **절대량의 누출이 보장**된다. 주인 수동 검토(1인당 선형 확장)에만 의존하지 말고, **자동 PII / private-content 탐지를 파생 파이프라인에 내장**해야 한다.
- 다수 에이전트를 조회해 정보를 triangulate하는 **추론 공격**이 규모에서 현실화된다. → rate limit, 노출 예산(differential-privacy류) 검토.

### 13.6 projection 워커의 분산

5.3.1의 debounce projection은 본문 단계에서 이미 비동기 배치다. 대규모에서 남는 과제는 그 **projection 워커 자체를 수평 분산**하는 것이다.

- 토픽/샤드 단위로 워커를 파티셔닝하고, raw publish 이벤트를 durable 큐(event stream)로 받아 eventual consistency로 반영한다.
- projection은 언제든 원본(Public Agent Memory)에서 재빌드 가능하므로(5.1), 워커 장애·재처리 설계가 단순해진다.

### 13.7 정리

| 영역 | 본문(MVP) 구조 | 대규모 전환 |
|---|---|---|
| Private / Public Agent Memory | 유저·에이전트 단위 저장 | 샤딩으로 수평 확장 (큰 문제 아님) |
| SKL 갱신 | debounce 비동기 배치 (5.3.1) | projection 워커 수평 분산 + durable 큐 |
| active-set 관리 | freshness·perspective_confidence 결합 축출 (5.3.2) | 토픽 내부 샤딩/클러스터링 |
| Perspective Index | 단일 DB 인덱스 (논리: `perspectives.yaml`) | 분산 vector DB + ANN |
| Topic Space | 단일 DB 문서 (논리: `topic.md`) | 임베딩 클러스터 + 대표 narrative 동적 생성 |
| 발견·랭킹 | 분리 랭킹 로직 (8.1) | 분산 retrieval + 권한 push-down |
| Memory/Persona 추출 | 대화마다 LLM | 증분·배치, 소형 모델, 트리거 기반 |
| Privacy | 주인 승인 게이트 | + 자동 PII 탐지, 추론공격 방어 |

이로써 **본문은 "왜 단일 저장 MVP가 견디는가"(5.3·8.1)를 핵심 설계로 설명하고, 13장은 그 위에서 정말로 대규모가 되었을 때 남는 과제**만 다루는 구조가 된다.
