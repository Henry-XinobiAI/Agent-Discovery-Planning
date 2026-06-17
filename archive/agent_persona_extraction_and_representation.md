# 에이전트 페르소나: 추출과 발현 (참고 문서)

> 이 문서는 메인 설계 문서 `personalized_agent_memory_and_perspective_network.md`의 **참고(companion) 문서**다. 메인 문서가 **discovery(에이전트 발견·추천)**에 집중하는 동안, 그 전제가 되는 **persona/memory의 추출(extraction)과 발현(representation)** 레이어를 따로 정리한다.
>
> 메인 문서의 3장(Persona ⊥ Memory), 4장(메모리 계층), 7장(Agent Perspective Card)을 전제로 하며, 여기서 다루는 내용은 메인 문서에 자세히 넣지 않고 이 문서로 참조한다.

---

## 0. 한 줄 구분

- **이 문서(추출·발현)**: 에이전트가 *무엇을, 어떻게 말하는가* — 페르소나를 뽑고(extraction), 대화에 싣는다(representation).
- **메인 문서(discovery)**: 그 에이전트를 *어떻게 찾는가* — Perspective Card·Index·SKL.

두 문서의 접점은 단 하나, **Public Agent Memory(공개 승인된 원본)와 거기서 나온 Perspective Card**다.

---

## 1. 저장 모델과 발현은 다른 층이다

가장 중요한 전제는 **"persona를 저장하는 모델"과 "persona가 발현되는 정책"이 별개 층**이라는 점이다. 메인 문서는 추출·저장(3장)과 공개·발견(4~8장)은 잘 다루지만, 그 사이의 *발현*은 다루지 않는다.

하나의 **source of truth(evidence-linked structured records)**에서 용도가 다른 여러 compiled view가 파생된다.

```text
structured evidence store  (source of truth: 다중 라벨 + evidence·context + extraction_confidence)
   ├─ Private Memory ───────┐
   │                        ├─▶ 자기 발현 brief   (private+public, 서술형)   → system prompt
   └─(publish gate)─▶ Public Agent Memory
                            ├─▶ 대변 발현 brief   (public-only, 페르소나 채택형) → system prompt
                            └─▶ Perspective Cards (public, topic-sliced, 구조화)  → SKL / discovery
```

핵심: brief 두 종과 Perspective Card는 **같은 store에서 나오지만, 입자(granularity)·privacy 경계·용도가 다른 별개 산출물**이다. "같은 것의 두 포맷"으로 뭉뚱그리지 않는다.

---

## 2. Persona Artifact: 원본 vs compiled view

팀 논의의 "최대 10k 토큰 수준의 개인 설명 문서(markdown/XML)" 아이디어는 **저장 단위가 아니라 발현 단위**로 두어야 한다.

- **원본(source of truth)** = evidence-linked structured records. 다중 라벨, 원문 evidence·context, `extraction_confidence·source·observed_at`을 유지한다. 추적·conflict·revision이 여기서 보장된다.
- **10k persona brief** = 그 원본에서 컴파일된 **prompt 주입용 view/cache**다. 압축된 persona brief이며, 원본만 보존되면 언제든 재생성 가능하다.

> 10k 프로즈 문서를 *원본*으로 삼으면 — 증거 추적, conflict 해소, 부분 revision이 약해진다. 메인 문서 3.3이 경고하는 **"단정 저장"** 그 자체가 된다. 그래서 10k 문서는 source of truth가 아니라 compiled artifact다.

또한 이 brief는 **discovery용 Perspective Card와 다른 view**다 (1장 다이어그램). 둘의 관계는 3장 끝에서 다룬다.

---

## 3. 발현 정책 (Representation Policy)

같은 페르소나 본문에 **모드별 래퍼(framing)**를 씌워 발현한다. 두 모드의 차이는 인칭 토글이 아니라 **content 경계 + 프레이밍**이다.

| | 자기 발현 (나와의 대화) | 대변 발현 (타인이 내 에이전트와 대화) |
|---|---|---|
| 프레이밍 | "유저는 이런 사람이야" — 상대에 대한 **서술** | "이 관점·스타일로 말해" — 페르소나 **채택** |
| content 경계 | private 포함 가능 | **public-only (하드 월)** |
| 에이전트 역할 | 내가 상대하는 *유저*를 이해 | 유저를 *대표하는* 에이전트 |

**불변식 (가장 중요):**

> 대변 발현에서도 에이전트는 **1인칭으로 유저 본인 행세를 하지 않는다.** 어디까지나 그 유저를 대표하는 **별개의 대리 에이전트**로서, 유저의 **관점과 스타일만 채택**해 말한다. (style/perspective는 embody, identity는 대리 에이전트)

이 설계가 "본인인 척하는 복제체" 위험을 **구조적으로 제거**한다 — 별도의 가드레일이나 opt-in 토글이 필요 없다. 두 모드 모두 "에이전트는 자기 정체성으로 말한다"는 전제를 공유한다.

### 3.1 discovery와의 연결: brief vs Card는 흐름의 다른 단계

brief와 Perspective Card는 중복이 아니라 **메인 문서 8장 흐름의 다른 단계**를 담당한다.

- **Perspective Card** = "이 에이전트와 *이 주제로 대화할까?*" — 발견·매칭 (topic-sliced, 구조화, 메인 7장)
- **10k brief** = 매칭된 뒤 "*그 대화에서 에이전트가 어떻게 말하는가*" — 대화 구동 (holistic)

발견(Card) → 대화 진입 → 발현(brief). 같은 Public Agent Memory에서 나오되, **발견 단계 vs 대화 단계**로 분업한다.

---

## 4. 추출 규율 (Extraction)

메인 문서 3.3의 "넓게 관찰하고, 늦게 해석한다"(다중 라벨링, evidence 공유)를 전제로 하고, 여기서는 추출의 *깊이·기준*을 보강한다.

### 4.1 일반화 + 구체, 둘 다 저장

팀 논의는 "게이샤·에티오피아 커피를 좋아해"보다 "꽃·과일향, 산미 있는 라이트로스팅을 좋아해"처럼 **일반화된 취향**을 저장하자고 본다. 일반화는 더 다양한 맥락에 적용·매칭되므로 옳은 방향이고, 메인 문서의 persona core(3.4)·다중 라벨(3.3) 정신에 부합한다.

다만 **둘 다 유지한다.**

- **구체값**("게이샤 좋아함") = **Memory evidence**로 남긴다 (검증·회상 가능).
- **일반화된 선호 함수**("산미 라이트로스팅 선호") = **Persona core / derived preference profile**로 만든다.

일반화만 남기면 검증·회상 가능한 구체 사실이 소실된다. 층위를 나눠 둘 다 보존한다.

### 4.2 Conversation Dynamics

쓰는 표현, 문장 길이, 문장 구조 등 **대화 역학**도 별도로 추출한다. 이는 메인 문서 Perspective Card의 `conversation_style`(Persona 계열)에 대응한다.

### 4.3 source별 차등과 attribution

source마다 페르소나 신뢰도가 다르다. 대화 > 블로그 > 유튜브 > 업로드 자료 순으로 "본인의 생각·말투"라는 보장이 약해진다. (같은 사람이라도 유튜브 표현 방식과 평소가 다르듯 — 메인 3.4 contextual overlay의 한 사례다.)

특히 **업로드 자료는 본인 생각이 아닐 수 있다.** 그래서 추출 후보에 출처 메타데이터를 단다.

- `source_type` — 대화 / 블로그 / 영상 / 업로드 문서 등
- `author_attribution` — 본인 발화인가, 인용·타인 글인가
- `ownership_confidence` — 이게 *이 유저의* 생각이라는 확신도
- `persona_applicability` — persona 추정에 써도 되는 자료인가

기존 페르소나와 **conflict**가 생기면, moderator가 대화에서 검증하거나 우선순위를 정한다 (메인 3.4 변화 탐지의 확장 — drift vs 다른 게이트 vs *출처 오염* 구분).

---

## 5. 검증과 Calibration

추출이 잘 됐는지 확인하는 메커니즘이 필요하다 (메인 문서엔 없음, 향후 쟁점).

- **round-trip 검증**: 추출된 페르소나로 대화를 생성하고, 그 대화에서 원 페르소나가 다시 추출되는지 확인. — 유용하지만 **필요조건이지 충분조건은 아니다.** round-trip이 통과해도 실제 유저에게 맞는지는 별개다.
- 그래서 함께 쓴다: **사용자 정정, 선택형 피드백, 심리테스트형 calibration, 대화 만족도 신호.**
- UX 후보: 페르소나에게 "네가 생각하는 나"를 직접 그리게/평가하게 하면 — 얼마나 잘 아는지 측정도 되고, 틀린 부분을 정정시켜 학습을 가속할 수도 있다. 메인 문서 3.5(능동적 자기노출 유도)와 연결된다.

---

## 6. 범위 밖 (다른 문서 소관)

- **Dialogue Moderator / Conversation Orchestrator 런타임** — 어떤 질문을 언제 할지, 어떻게 반응할지, 어떤 액션(추천·초대)을 할지를 결정하는 런타임 계층. 메인 문서 3.5가 "별도 문서"로 미룬 부분이며, `agent_event_driven_architecture.md` 소관이다.
- **에이전트 초대(invite) 액션** — discovery의 추천(recommendation)과 별개로, 유저가 명시적으로 트리거하는 새 액션 타입. 개념적으로 discovery에 닿지만 구동은 런타임 소관.

---

## 7. 메인 문서 매핑 (빠른 참조)

| 이 문서 | 메인 문서 접점 |
|---|---|
| evidence store = source of truth | 3.3 (넓게 관찰, 늦게 해석) |
| 자기/대변 발현 content 경계 | 4.1 Private / 4.2 Public Agent Memory (하드 월) |
| source별 차등 = 컨텍스트별 관찰 | 3.4 contextual overlay |
| 일반화 선호 함수 | 3.4 persona core / 3.3 다중 라벨 |
| conversation dynamics | 7장 `conversation_style` |
| brief vs Card (대화 vs 발견) | 7장 Card · 8장 흐름 |
| 능동적 자기노출 calibration | 3.5 / 12.4 |
