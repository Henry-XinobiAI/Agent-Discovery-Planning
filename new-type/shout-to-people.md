# 추천으로 답하지 못한 질문을 사람들에게 묻기 — shout

> 상태: **기획 초안, 결정 아님**
> 범위: 사람의 경험이 필요한 질문에 추천이 답하지 못했을 때, 그 질문을 고른 소수의 사용자에게 보내고(shout), 받은 사람이 원하면 나중에 답하게 하는 기능. 이 문서는 **누구에게 보낼지**(받는 사람 선정)와 그것을 지키는 제약·차수·측정을 정하고, 알림·응답 채널은 다른 서비스에 요청할 것으로 적는다
> 비범위: 알림 발송과 응답 UI 자체(bourbon-api·client), shout를 언제 제안할지의 트리거(bourbon-agent — 이 문서는 기대하는 것만 적는다), 경험 기록의 추출 방식(`knowledge-agent-recommendation.md` §7)
> 선행 문서: `new-type/knowledge-agent-recommendation.md`(이하 **knowledge 문서**). 이 문서의 질문 분석·후보·공개 범위는 그 문서의 것을 그대로 쓴다. 절 번호를 "knowledge §9 T3"처럼 적는다
> 이 문서의 "현재"는 agent-discovery-api `435fa16`(origin/main, 2026-10-08) 기준이다

---

## 0. 요약

knowledge 문서의 추천은 **이미 쌓인 경험 기록**에서 답할 사람을 찾는다. 기록에 없는 경험은 찾을 수 없다 — 초기에는 대부분의 질문이 그럴 수 있다(knowledge §13-2 항목 6·7). shout는 그 빈 곳을 사람이 직접, 나중에 채우게 한다. 질문을 고른 몇 명에게 보내고, 받은 사람이 관심이 있으면 답하고, 그 답을 요청자에게 보여 준다.

모든 사용자에게 보낼 수는 없다. 받는 사람의 주의가 이 기능의 비용이고, 관계없는 질문이 자주 오면 스팸이 된다. 그래서 이 문서의 중심은 **받는 사람을 고르는 방법**이다. 뼈대는 다섯 가지다.

1. **선정 근거는 공개된 것만 쓴다.** 받는 사람은 그 질문의 topic을 요청자가 볼 수 있는 tier로 공개한 사람이다. "위스키를 공개 관심사로 두셔서 왔습니다"라고 말할 수 있는 근거만 쓴다 — 그래서 선정은 공개된 row만 가진 discovery가 맡는다(§3, §5).
2. **"답할 수 있는가"와 "답할 것인가"를 따로 본다.** 앞쪽은 knowledge 추천이 떨어뜨린 근접 후보와 관심 강도로, 뒤쪽은 최근 활동과 shout 응답 이력으로 본다. 응답 이력은 지금 어디에도 없어 새로 쌓는다(§5-3).
3. **스팸 방지는 순위가 아니라 하드 제약이다.** 받는 사람별 빈도 상한, 무시가 이어지면 쉬게 하기, topic별 거절. 가중치로 섞지 않고 넘으면 뺀다(§5-4).
4. **적게 보내고, 답이 없을 때만 넓힌다.** 1차는 그 topic의 상위 몇 명, 답이 없으면 2차는 상위·형제 topic으로 넓힌다. 넓히는 축은 인원 수가 아니라 카탈로그 계층이다(§5-5).
5. **답은 경험 기록이 된다.** 받은 사람의 답은 그 사람이 보낸 메시지라, lived-knowledge가 적재하는 방에서 오가면 그 사람의 경험 기록으로 쌓인다. 다음에 비슷한 질문이 오면 shout 없이 추천이 답한다 — shout는 경험 소스의 빈 곳을 채우는 수집 경로이기도 하다(§7).

---

## 1. 흐름

```text
질문 ──▶ bourbon-agent ──▶ discovery POST /recommend/knowledge
                              │ mode: none, empty_reason: nobody_covers
                              ▼
bourbon-agent: "아직 답할 사람을 못 찾았어요. 관심 있는 분들께 물어볼까요?"  ← 요청자 동의
                              │ 예
                              ▼
discovery POST /shout  ──  shout 생성, 1차 받는 사람 선정, shout 원장에 기록
                              │ 받는 사람 목록
                              ▼
bourbon-api: 받는 사람에게 알림 (shout 문장 + 응답 진입점)
                              │
          ┌───────────────────┴────────────────────┐
     받은 사람이 답함                           shout.wave_timeout 동안 답 없음
          │                                        │
bourbon-api: 응답 이벤트 ─▶ discovery: 원장 갱신      discovery 주기 루프: 다음 차수 선정
          │                                        │ (최대 shout.max_waves차, 그 뒤 종료)
          ▼                                        ▼
요청자에게 답 전달                             요청자에게 "아직 답한 사람이 없어요"
          │
lived-knowledge: 답 메시지를 받은 사람의 경험 기록으로 적재
```

1. **추천이 먼저다.** shout는 knowledge 추천이 `nobody_covers`로 끝났을 때만 제안한다. 추천이 답한 질문을 shout하면 이미 말한 사람을 두고 다른 사람을 귀찮게 하는 것이다.
2. **요청자가 동의해야 보낸다.** 질문은 요청자의 글이고, 낯선 사람들에게 간다. bourbon-agent가 요청자에게 묻고, 동의하면 shout를 만든다. 언제 어떤 말로 제안할지는 bourbon-agent의 결정이다(§4).
3. **discovery가 shout를 만들고 1차 받는 사람을 고른다**(§5). shout 하나와 받는 사람마다의 발송 기록을 shout 원장에 남긴다(§8). 요청 경로는 discovery DB 읽기뿐이다 — 질문 분석과 근접 후보는 직전 추천의 결과를 다시 쓰고, LLM도 lived-knowledge도 다시 부르지 않는다(§4).
4. **알림은 bourbon-api가 보낸다.** discovery는 누구에게 보낼지만 정한다. 알림에 들어가는 것은 shout 문장(§6)과 응답 진입점이다.
5. **답이 오면** bourbon-api가 discovery에 알리고, 요청자에게 답을 보여 준다. discovery는 원장에 응답을 적는다 — 응답 이력의 재료다(§5-3).
6. **답이 없으면** discovery의 주기 루프가 `shout.wave_timeout_hours`가 지난 shout의 다음 차수를 고른다(§5-5). 마지막 차수에도 답이 없으면 shout를 닫고 요청자에게 알린다.
7. **답은 기록이 된다.** 답 메시지가 lived-knowledge가 받는 `message_created`로 발행되면, 그 사람의 경험 기록으로 적재된다(§7).

---

## 2. 용어

knowledge 문서의 용어(요청자, need, topic, 엔티티, 경험 기록, 관심 소스, 경험 소스, coverage 상태, need 충족, 설정 레지스터)는 그대로 쓴다(knowledge §2). 이 문서가 더하는 것:

| 용어 | 뜻 |
|---|---|
| **shout** | 추천이 답하지 못한 질문 하나를 고른 사용자들에게 보내는 요청. id가 있고, 차수와 상태(`open` · `answered` · `closed`)를 가진다 |
| **받는 사람** | shout를 받는 사용자. 사람 본인이다 — agent가 아니라 사람이 직접 답한다 |
| **shout 문장** | 받는 사람에게 보이는 질문. 요청자의 원문이 아니라 질문 분석의 결과로 다시 쓴 짧은 문장이다(§6) |
| **차수(wave)** | 한 번에 보내는 받는 사람 묶음. 1차에 답이 없으면 2차를 보낸다(§5-5) |
| **근접 후보** | knowledge 추천의 T3가 모았지만 need 충족(knowledge §9 T3)에서 떨어진 경험 소스 후보. 예: 21 팔리아먼트를 물었는데 글렌드로낙 12년을 마신 사람 |
| **응답 의향** | 받는 사람이 답할 가능성. 최근 활동과 shout 응답 이력으로 본다. 답할 능력(그 분야를 아는가)과 따로 본다 |
| **shout 원장** | 누가 언제 어떤 shout를 받고, 열고, 답하고, 거절했는지의 기록. 빈도 상한과 응답 이력이 이것을 읽는다(§8) |
| **탐색 자리** | 차수마다 순위가 조금 낮거나 응답 이력이 없는 사람에게 남겨 두는 자리. 응답 이력이 이미 답한 사람에게만 쌓이지 않게 한다(§5-6) |
| **mute** | 받는 사람이 topic 하나 또는 shout 전체를 그만 받겠다고 한 상태 |

---

## 3. 원칙

1. **받는 사람의 주의가 비용이다.** 추천은 요청자가 보는 화면에 무엇을 보여 줄지의 문제라 틀려도 요청자 한 사람이 넘기면 끝난다. shout는 다른 사람의 알림을 쓴다. 그래서 "더 많이 보내면 더 잘 답한다"가 아니라 "답이 나올 만큼만 보낸다"가 목표다.
2. **선정 근거는 공개된 것만.** 받은 사람은 "왜 나에게 왔지?"를 묻는다. 그 답이 그 사람이 공개하지 않은 것 — private topic, private 방에서 한 말 — 이면 shout 자체가 유출이다. 그래서 자격은 공개된 topic으로만 정한다(§5-2). discovery의 저장소에는 공개된 row만 있으므로(계약 §5 불변식 1) 선정을 discovery에 두면 이것이 구조로 지켜진다.
3. **답할 사람이 아니라 답할 것 같은 사람.** 기존 타입은 owner의 **agent**를 추천하므로 owner 본인이 활동하지 않아도 agent가 답한다 — 그래서 오래 활동하지 않은 owner도 후보에서 빼지 않는다(R31). shout는 사람이 직접 답한다. 오래 활동하지 않은 사람에게 보내면 알림이 쌓일 뿐이다. 이 기능에서만 최근 활동을 자격으로 건다(§5-2).
4. **제약은 섞지 않는다.** 빈도 상한·쿨다운·mute를 순위 feature로 두면 점수가 높은 사람은 상한을 넘어서도 받는다. 넘으면 뺀다.
5. **적게 보내고 넓힌다.** 차수로 나누면 받는 사람 수가 질문의 난이도에 맞춰 정해진다. 쉬운 질문은 1차에서 끝난다.

---

## 4. 언제 shout하나 — bourbon-agent에 기대하는 것

knowledge 문서와 같이, 언제 무엇을 부를지는 bourbon-agent가 정한다(knowledge §9 T0). discovery가 기대하는 것:

- **knowledge 추천이 `nobody_covers`로 끝났을 때만** shout를 제안한다. `answerable_without_people`(사실 질문)이면 제안하지 않는다.
- **요청자의 동의를 받고** 부른다. 자동으로 보내지 않는다.
- shout 요청에는 직전 추천의 `recommendation_id`를 싣는다. discovery는 그 추천의 질문 분석 결과(need, topic, 근접 후보)를 다시 쓴다 — T1을 다시 돌리지 않고, 질문 원문을 다시 받지 않는다.
  - 이를 위해 discovery는 `nobody_covers`로 끝난 추천의 need와 topic id, 근접 후보의 id를 짧은 TTL로 남긴다(§8). 원문과 `condition`은 남기지 않는다(knowledge §10-3과 같은 원칙).
  - 남긴 것이 만료됐으면 discovery는 shout를 만들지 않고 "다시 추천부터"를 돌려준다. shout 문장(§6)은 원문 없이 need와 topic에서 만들므로, 이 경우에도 원문을 다시 받을 필요는 없다.

`judge`가 "맞는 후보가 부족하다"고 판정했지만 충족한 사람이 있는 경우(knowledge §9 T4-a)는 shout 대상이 아니다. 추천이 답했고, 요청자가 그 사람과 대화해 보면 된다.

---

## 5. 받는 사람 선정 (discovery)

### 5-1. 쓰는 데이터 — discovery에 이미 있는 것

| 데이터 | 지금 하는 일 | shout에서 |
|---|---|---|
| `visible_topic_rows` (topic, tier, `topic_score`, `topic_maturity`) | 타입 ①②의 검색 대상 전부 | **자격**: 그 topic을 요청자가 볼 수 있는 tier로 공개했는가. **순위**: `topic_score`·`topic_maturity` |
| `catalog_edges` | 하위 topic 펼치기 | **넓히는 축**: 1차 그 topic(+ 하위), 2차 상위·형제 topic(§5-5) |
| `friends` | friends tier 필터(R17, 불변식 2) | friends tier 자격 판정, 요청자의 친구 가산 |
| `agents.last_active_at`, `discoverable` | CF sweep 조건(R19), 노출 가능 여부(R57) | **최근 활동 자격**. 우리 API 요청·`room_created`의 creator·`topics_updated`로 움직인다(R19) — 사람이 앱을 쓰고 있다는 거친 신호다 |
| `departed_users` | 탈퇴자 제외(R68) | 그대로 |
| `popularity`, `interactions`, `room_turns` | 타입 ③의 인기도(R29), CF 학습 입력(R49) | **부하 신호로만.** 이것은 그 사람의 **agent**가 대화를 끌었다는 값이다. 가산하면 이미 바쁜 소수에게 shout가 몰린다 |
| `cf_candidates` | 타입 ③ "이 요청자가 대화할 만한 agent" | 탐색 자리와 동점 정리에만. 요청자가 그 사람의 답을 반길지에 대한 약한 신호이고, 받는 사람의 의향과는 무관하다 |
| `attributions`, decision log, `recommendation_id` | 화면 노출 → 대화 측정(R47, R53) | 측정 방식을 그대로 가져온다 — 발송 → 열람 → 응답 → 요청자 평가(§12) |

그리고 lived-knowledge의 `/candidates`(knowledge §10-2)가 돌려준 **근접 후보**를 쓴다 — 직전 추천에서 이미 받은 것이다(§4).

**discovery에 없는 것 — 새로 쌓는다.**

- **사람의 응답 이력.** discovery의 대화 데이터는 전부 "요청자 → 상대의 agent"이고 owner 본인은 그 방에 없다(R46·R49: agent DM의 turn은 사람 쪽만 센다). "이 사람에게 물으면 답하는가"는 어디에도 없다 — shout 원장(§8)이 처음으로 쌓는다.
- **받는 사람별 발송 기록.** 빈도 상한과 쿨다운의 재료(§8).
- **opt-in·mute.** topic별 "질문 받기"와 그만 받기(§5-2, §15 요청).

### 5-2. 자격 — 하나라도 안 맞으면 뺀다

1. 요청자가 아니다. `departed_users`에 없다. `agents`에 있다.
2. **그 shout의 topic을 요청자가 볼 수 있는 tier로 공개했다** — `public`, 또는 요청자가 친구일 때 `friends`. 이 차수의 topic 범위(§5-5)에 든 topic 가운데 하나다. 쿼리 안에서 건다(R17과 같은 원칙 — 자른 뒤에 빼면 자격 없는 사람이 자리를 차지한다).
3. **최근 `shout.active_within_days`(초기 14일, 추론) 안에 활동했다**(`last_active_at`). 원칙 3.
4. 빈도 상한·쿨다운·mute에 걸리지 않았다(§5-4).
5. 이 shout를 이미 받지 않았다(이전 차수 포함).
6. opt-in이 생기면: 그 topic의 질문 받기를 끄지 않았다. 처음에는 공개를 약한 동의로 보고 시작하되, 알림은 노출보다 무거우므로 opt-in을 서비스화 전에 넣는다(열린 항목 1).

**근접 후보도 2를 통과해야 한다.** 경험 기록은 private 방에서도 나오고(knowledge §12), 그 기록의 topic이 private일 수 있다. 기록이 근거여도, 그 사람을 고른 이유로 말할 수 있는 공개 topic이 없으면 뺀다.

**도달 가능성은 걸지 않는다.** 추천은 요청자가 그 사람과 대화를 시작할 수 있어야 맞지만(knowledge §9 T3), shout는 받는 사람이 요청자에게 답하는 방향이다. 답이 어떤 경로로 요청자에게 가는지는 응답 채널이 정한다(§7, 열린 항목 4).

### 5-3. 순위

자격을 통과한 사람을 다음 feature의 가중 합으로 줄 세운다. 값은 설정 레지스터에 올린다. 곱셈식을 쓰지 않는 이유는 knowledge §9 T4와 같다 — 측정되지 않은 feature가 0이 되어 전원을 지우면 안 된다.

**답할 수 있는가**

- **근접 후보의 coverage 상태**: 상위 엔티티 경로(`record_entity`인데 기준 대상이 아님) > 종류가 맞는 `record_topic` > `record_text`. 가장 강한 신호다 — 그 대상 근처를 실제로 겪었다고 말한 사람이다.
- **관심 강도**: 그 topic의 `topic_score`·`topic_maturity`. topic이 정확히 그것이면 1, 하위 topic이면 그대로, 상위·형제 topic(2차)이면 감쇠(R25의 `0.6^hop`와 같은 방식).

**답할 것인가**

- **최근 활동**: `last_active_at`이 가까울수록.
- **요청자의 친구**: 가산. 아는 사람의 질문에 더 잘 답할 것이다(추론, §12에서 잰다).
- **shout 응답률**: 받은 shout 중 답한 비율, 적은 표본에서는 사전값 쪽으로 당긴다(Beta 사전분포). 쌓이기 전에는 측정되지 않은 feature로 둔다(discovery의 `Features.present`).
- **응답 품질**: 요청자가 그 사람의 답을 도움이 됐다고 평가한 비율. 같은 방식.

**부하 — 감점**

- 최근 `shout.load_window_days` 안에 받은 shout 수.
- `popularity`가 상위인 owner. 그 사람의 agent가 이미 대화를 많이 끌고 있다는 뜻일 뿐 본인이 바쁘다는 뜻은 아니므로 약하게 둔다. 측정으로 정한다(열린 항목 5).

동점은 `(score desc, owner_user_id asc)`로 정한다. 같은 입력이면 늘 같은 순서다.

### 5-4. 스팸 방지 — 하드 제약

| 제약 | 초기값(추론) | 무엇을 막나 |
|---|---|---|
| 받는 사람별 빈도 상한 `shout.per_recipient_per_week` | 3건/7일 | 전문가 몇 명에게 몰리는 것 |
| 연속 무시 쿨다운 `shout.ignore_streak` · `shout.ignore_cooldown_days` | 연속 3건 무시 → 14일 쉼 | 관심 없는 사람에게 계속 가는 것. 열지도 않은 것을 무시로 센다 |
| topic별 mute, 전체 mute | 사용자가 정함 | 원하지 않는 사람 |
| 같은 topic 묶기 `shout.merge_window_hours` | 24시간 | 같은 topic·엔티티의 shout가 짧은 시간에 여러 건이면 한 사람에게는 하나만 간다 |
| 요청자별 상한 `shout.per_requester_per_day` | 3건/1일 | 한 사람이 shout를 남발하는 것 |
| 열린 shout 상한 `shout.open_per_requester` | 3건 | 답이 안 온 shout가 쌓이는 것 |

"같은 topic 묶기"는 두 번째 shout를 버리는 것이 아니다. 이미 그 topic의 shout를 받은 사람을 두 번째 shout의 자격에서 빼고, 다음 사람에게 간다.

### 5-5. 차수와 넓히기

```text
1차  topic 범위: need의 topic + 하위 topic       인원 shout.wave_sizes[0] (초기 4)
     shout.wave_timeout_hours (초기 6) 동안 답이 없으면
2차  topic 범위: + 상위 topic 1 hop과 그 하위(형제)  인원 shout.wave_sizes[1] (초기 8)
     같은 시간 동안 답이 없으면
종료  요청자에게 "아직 답한 사람이 없어요". 늦게 온 답은 그래도 전달한다
```

- **넓히는 축은 카탈로그 계층이다.** 1차에서 답이 없는 이유는 대개 "그 분야 사람이 적다"이지 "그 분야 사람이 4명보다 많은데 그중 아무도 답하지 않았다"가 아니다(추론). 인원만 늘리면 같은 분야의 순위 낮은 사람에게 가고, 분야를 넓히면 "몰트 위스키"에 답할 사람이 없을 때 "위스키" 사람에게 간다.
- 2차에 상위 topic으로 간 사람은 shout 문장에 "위스키에 관심이 있으셔서"처럼 **그 사람이 공개한 topic**을 이유로 단다(§6). 받는 사람이 고른 이유를 이해할 수 있어야 한다.
- **답이 오면 다음 차수를 보내지 않는다.** 첫 답이 오면 shout는 `answered`가 되고 더 넓히지 않는다. 이미 받은 사람의 답은 `shout.answer_window_hours`(초기 72) 동안 계속 받아 전달한 뒤 닫는다.
- 차수는 최대 `shout.max_waves`(초기 2). 1차·2차 합계가 받는 사람 상한이다(초기 12명).

### 5-6. 탐색 자리

차수마다 `shout.explore_slots`(초기 1)자리를 순위 밖에서 채운다 — 응답 이력이 없는 사람 가운데 자격을 통과한 사람을 순위 상위 일부에서 무작위로. 이 자리가 없으면 응답률 feature가 이미 답한 사람에게만 쌓이고, 새로 공개한 사람은 영영 받지 못한다. 탐색 자리의 응답은 따로 표시해 측정에 쓴다(§12). 무작위는 shout id로 시드를 정해 재현할 수 있게 한다.

---

## 6. shout 문장과 공개 범위

**받는 사람에게 요청자의 원문을 보내지 않는다.** 원문에는 요청자의 사정("우리 애가 다섯 살인데…")이 섞여 있고, 받는 사람은 요청자를 모르는 사람이다.

- shout 문장은 need와 topic, 공개 이름에서 만든다 — "몰트 위스키 · 글렌드로낙 21 팔리아먼트를 마셔 본 경험을 묻는 질문이 있어요". 엔티티의 공개 이름(knowledge §7-3의 레지스트리 label)과 need의 종류만 쓴다.
  - `condition`(영어 조건 구절)은 사용자의 글로 다루므로(knowledge §13-1) 그대로 싣지 않는다. 조건을 싣고 싶으면 요청자가 동의 단계에서 직접 쓴 한 줄을 받는다(열린 항목 2).
- 받는 사람을 고른 이유를 함께 보여 준다 — "위스키를 공개 관심사로 두셔서 보내 드려요". 그 사람이 공개한 topic의 카탈로그 이름이다(§5-2).
- **요청자는 기본적으로 받는 사람에게 밝히지 않는다.** 답한 사람은 요청자에게 밝혀진다 — 답은 그 사람이 직접, 알고 보낸 것이다. 요청자를 밝힐지(친구에게는 밝히는 등)는 열린 항목 3.
- shout 문장, 요청자가 쓴 한 줄, 답의 본문은 로그·예외·Sentry에 원문으로 남기지 않는다(불변식 7). decision log에는 id, 길이, digest만.

---

## 7. 응답 경로와 경험 기록

응답 UI와 채널은 bourbon-api·client의 일이다(§15). discovery가 요구하는 것은 셋이다.

1. **답한 사람이 분명해야 한다.** 답은 받는 사람 본인이 보낸 메시지다(`sender_type == user`). agent가 대신 답하지 않는다 — 그것은 knowledge 추천이 이미 한 일이다.
2. **답이 요청자에게만 보여야 한다.** 다른 받는 사람에게 서로의 답을 보여 줄지는 열린 항목 6.
3. **답이 lived-knowledge가 적재하는 메시지여야 한다.** 답이 `bourbon.message_created`로 발행되는 방에서 오가면, lived-knowledge가 그 사람의 경험 기록으로 적재한다(knowledge §7-1). 기록은 보낸 사람 기준이라 귀속도 맞다.
   - "응 그거 괜찮았어"는 앞의 질문 없이는 뜻이 없다. 추출이 무엇에 대한 답인지 알 수 있게, shout 문장이 그 방에 문맥 메시지로 있어야 한다(knowledge §7-1 4·6 — 문맥 메시지에서는 기록을 뽑지 않는다).
   - 그 방의 종류와 visibility는 knowledge §12의 규칙을 그대로 따른다. 답에서 나온 기록의 공개 범위는 그 기록의 topic에 대한 답한 사람의 visibility다.

**이것이 이 기능의 가장 큰 효과다.** 추천은 이미 말한 경험만 찾는다. shout의 답은 추천이 찾지 못한 바로 그 질문에 대한 경험이고, 답한 순간 경험 소스에 들어간다. 다음에 비슷한 질문이 오면 shout 없이 추천이 답한다 — knowledge §13-2 항목 6·7의 데이터 밀도 문제를 직접 줄이는 경로다. 측정한다(§12의 "기록 기여").

**도달 가능성.** 답이 요청자에게 가는 방향은 bourbon-api의 agent DM 게이트("친구이거나 agent가 public", knowledge §6-1)와 반대다. 받은 사람이 요청자의 친구도 아니고 요청자의 agent가 public도 아닐 때 답이 가도 되는지, 답 뒤에 두 사람이 대화를 이어 갈 수 있는지는 응답 채널을 정할 때 함께 정한다(열린 항목 4).

---

## 8. 저장 — shout 원장

### 8-1. 무엇을

```text
shouts
  shout_id            uuid
  requester_user_id   uuid
  recommendation_id   uuid        이 shout를 낳은 knowledge 추천
  topic_ids           text[]      need의 topic (1차 범위의 출발점)
  entity_labels       jsonb       shout 문장에 쓴 공개 이름 (레지스트리 label)
  kind                text        need의 종류
  wave                smallint    지금 차수
  status              text        open | answered | closed
  next_wave_at        timestamptz 다음 차수를 고를 시각 (open일 때)
  created_at, closed_at

shout_deliveries
  shout_id            uuid
  recipient_user_id   uuid
  wave                smallint
  reason_topic_id     text        이 사람을 고른 이유로 보여 준 공개 topic
  explore             bool        탐색 자리였는가 (§5-6)
  sent_at             timestamptz
  opened_at, answered_at, declined_at, muted_at   timestamptz | null
  helpful             bool | null 요청자의 평가
  (shout_id, recipient_user_id) PK, (recipient_user_id, sent_at) 인덱스

shout_mutes
  user_id, topic_id (null = 전체), created_at
```

`nobody_covers`로 끝난 추천의 need·topic id·근접 후보 id(§4)는 DynamoDB의 `REC#{recommendation_id}` key space(R44)에 짧은 TTL로 둔다 — 추천 근거(knowledge §10-3)와 같은 자리다.

**저장하지 않는 것**: 질문 원문, `condition`, 요청자가 쓴 한 줄, 답의 본문. 답의 본문은 bourbon-api에 있고, 기록은 lived-knowledge에 있다. 원장에는 id와 시각과 공개 이름만 있다.

### 8-2. 왜 PostgreSQL인가

- **사람으로 찾아야 한다.** 빈도 상한과 응답률은 "이 사람이 최근 받은 것"이다. 추천 근거처럼 `REC#{id}`로만 두면 사람으로 역조회할 수 없다(knowledge §10-3이 일부러 그렇게 했다). PostgreSQL의 `(recipient_user_id, sent_at)` 인덱스가 이 읽기다.
- **선정이 원장과 한 트랜잭션이어야 한다.** 두 shout가 동시에 같은 사람을 고르면 빈도 상한이 깨진다. 받는 사람을 고르는 쿼리와 `shout_deliveries` 삽입을 한 트랜잭션에 두고, 받는 사람별 advisory lock으로 순서를 정한다(R68의 탈퇴 확인과 같은 방식).
- discovery의 다른 쓰기 테이블(`attributions`, `interactions`)과 같은 곳이다.

### 8-3. 탈퇴와 보존

- **탈퇴(R68)**: 받는 사람이 탈퇴하면 그 사람의 `shout_deliveries`·`shout_mutes`를 지운다. 요청자가 탈퇴하면 그 사람의 `shouts`를 닫고 지운다(딸린 `shout_deliveries`도). `interactions`의 actor 행처럼 익명화해 남기지 않는다(R49) — 응답률은 그 사람 자신에 대한 값이라 함께 지운다.
- **보존**: `shout_deliveries`는 `shout.retention_days`(초기 180일, 추론) 뒤 retention sweep(`worker/retention.py`)이 지운다. 응답률 계산 창보다 길면 된다.
- 선정 쿼리는 첫 statement에서 `departed_users`를 확인한다 — 늦게 처리된 탈퇴에 shout가 가지 않게.

---

## 9. 예제

knowledge §5의 예제를 잇는다. 요청자 R이 "글렌드로낙 21 팔리아먼트 마셔 본 사람"을 찾았고, A는 R이 대화할 수 없는 사람이라 빠졌으며(knowledge §5-4 끝), 남은 사람 중 n0을 충족한 사람이 없어 `nobody_covers`다.

```text
직전 추천이 남긴 것 (REC#…, TTL)
  need n0: kind=experienced, topic=몰트 위스키, entity_labels=[GlenDronach, GlenDronach 21 Parliament]
  근접 후보: C (글렌드로낙 12년, 상위 엔티티 경로)

R이 동의 → POST /shout

1차 (topic 범위: 몰트 위스키 + 하위)
  자격   C: 몰트 위스키 public, 3일 전 활동            ✔
         D: 몰트 위스키 topic 없음, 위스키 public        ✘ (1차 범위에 공개 topic이 없다)
         E: 몰트 위스키 public, topic_score 0.9, 응답률 2/3   ✔
         F: 몰트 위스키 friends, R의 친구               ✔
         G: 몰트 위스키 public, 이번 주 shout 3건 받음    ✘ (빈도 상한)
         H: 몰트 위스키 public, 40일 전 활동             ✘ (최근 활동)
  순위   C (근접 후보: 상위 엔티티) > F (친구 가산) > E (관심 강도·응답률)
  탐색   I: 몰트 위스키 public, 응답 이력 없음
  발송   C, F, E, I — "몰트 위스키를 공개 관심사로 두셔서 보내 드려요"

6시간 동안 답 없음 → 2차 (topic 범위: + 위스키와 그 하위)
  D: 위스키 public                                  ✔ — "위스키를 공개 관심사로 두셔서"
  …

D가 답함: "21은 아니고 18 알라데일은 마셔 봤는데, 팔리아먼트는 셰리가 더 세다고 들었어요"
  → R에게 전달, shout는 answered (다음 차수 없음)
  → lived-knowledge: D의 기록 — 18 알라데일 experienced. "들었어요"는 전해 들은 것이라 기록하지 않는다(knowledge 열린 항목 6)
```

D의 답에서 나온 기록의 topic은 위스키·몰트 위스키다(knowledge §7-4 — 가장 넓은 이름과 가장 구체적인 이름). D는 몰트 위스키를 갖고 있지 않으므로 가장 가까운 상위인 위스키의 tier(public)를 따르고(knowledge §12), 다음에 누군가 "글렌드로낙 18 마셔 본 사람"을 물으면 추천이 D를 찾는다(D는 public topic이 있어 agent가 public이다, R57). D가 몰트 위스키를 private으로 두었다면 "가장 제한적인 쪽" 규칙으로 그 기록은 추천에서 가려진다 — shout가 경험 소스를 채우는 정도는 답한 사람의 visibility에 묶인다.

---

## 10. API 초안

discovery 쪽만. 알림·응답 채널의 계약은 bourbon-api와 정한다(§15).

```http
POST /api/internal/svc/agent-discovery/shout
```

```json
{"user_id": "uuid", "recommendation_id": "uuid", "lang": "ko"}
```

```json
{"shout_id": "uuid",
 "wave": 1,
 "recipients": [{"user_id": "uuid", "reason_topic_id": "…", "reason_label": "몰트 위스키"}],
 "shout_text": {"ko": "몰트 위스키 · 글렌드로낙 21 팔리아먼트를 마셔 본 경험을 묻는 질문이 있어요"},
 "next_wave_at": "2026-10-08T09:00:00Z",
 "empty_reason": null}
```

- 요청자는 `user_id`이고, 직전 추천의 요청자와 같아야 한다. 다르거나, 추천이 만료됐거나, `nobody_covers`가 아니면 거절한다.
- `recipients`가 비면 `empty_reason`: `nobody_eligible`(자격을 통과한 사람이 없다), `requester_limit`(요청자 상한).
- bourbon-agent는 이 응답을 bourbon-api의 발송에 넘긴다 — 또는 discovery가 bourbon-api를 직접 부른다. 어느 쪽인지는 §15 요청 1.

```http
POST /api/internal/svc/agent-discovery/shout/{shout_id}/events
```

```json
{"recipient_user_id": "uuid", "event": "opened | answered | declined | muted", "topic_id": null, "occurred_at": "…"}
```

- bourbon-api(또는 client)가 받는 사람의 행동을 알린다. `muted`는 `topic_id`가 있으면 그 topic, 없으면 전체.
- 요청자의 평가는 `POST /shout/{shout_id}/feedback` `{recipient_user_id, helpful}` — 요청자 본인만.

다음 차수는 route가 아니라 worker의 주기 루프가 고른다(`shout.sweep_minutes`) — `status = open AND next_wave_at <= now`인 shout를 잡아 §5를 다시 돌리고, 고른 사람을 bourbon-api에 넘긴다. 실행 이벤트가 없는 시간 경과가 계기라서 기존의 "이벤트가 깨우지 않는 job"(README의 여섯 루프)과 같은 자리다.

---

## 11. 실패

| 실패 | 동작 |
|---|---|
| 직전 추천의 기록이 만료 | shout를 만들지 않고 "다시 추천부터" |
| 직전 추천이 경험 소스 없이 끝남(`experience_unavailable`) | 근접 후보 없이 관심 소스만으로 고른다. shout는 그래도 나간다 — 근접 후보는 순위의 한 feature다 |
| 자격을 통과한 사람이 0명 | `nobody_eligible`. 2차 범위로 바로 넘어가 다시 고르고, 그래도 0명이면 요청자에게 알린다 |
| 발송 실패(bourbon-api) | `shout_deliveries`의 `sent_at`을 채우지 않는다. 빈도 상한은 `sent_at`이 있는 것만 센다 — 받지 않은 shout로 상한이 차지 않게. 루프가 다시 넘긴다(시도 상한) |
| 주기 루프 실패 | `next_wave_at`이 지난 shout가 남아 다음 사이클이 잡는다. deferq task가 아니라 sweep이라 스스로 다시 잡는다(R19와 같은 이유) |
| 동시에 두 shout가 같은 사람을 고름 | 받는 사람별 advisory lock으로 순서를 정하고, 늦은 쪽은 상한을 다시 확인한다(§8-2) |
| 탈퇴 이벤트 유실 | 탈퇴자에게 shout가 갈 수 있다. bourbon-api 발송 쪽의 사용자 상태 확인이 두 번째 방어다(§15 요청 1) |

---

## 12. 측정

**퍼널** — 차수별, 탐색 자리 여부별로 나눈다.

```text
shout 제안 → 요청자 동의 → 발송 → 열람 → 답 → 요청자가 "도움이 됐다"
```

- 응답률, 첫 답까지 걸린 시간(퍼센타일), shout당 받는 사람 수, 1차에서 끝난 비율.
- **비용 지표(guardrail)**: 받은 사람의 거절·mute 비율, 연속 무시 쿨다운에 들어간 사람의 비율. 이것이 오르면 차수 인원과 빈도 상한을 줄인다. 응답률보다 먼저 본다 — 응답률은 많이 보낼수록 쉽게 오르지만, 비용은 사용자가 떠난 뒤에야 보인다.
- **순위 feature의 기여**: 근접 후보·친구·관심 강도·응답률별 응답률. 친구 가산이 정말 응답률을 올리는지(§5-3의 추론).
- **기록 기여**: shout의 답에서 나온 경험 기록 수, 그 기록이 이후 knowledge 추천의 need 충족에 쓰인 횟수(§7). 이 기능이 경험 소스를 얼마나 채우는가.
- decision log에는 원문 없이: shout id, 차수, 자격 단계마다 빠진 수(활동·상한·mute·tier), 고른 사람의 순위 feature, 탐색 자리.

**합성 데이터로는 응답을 잴 수 없다.** 합성 모집단(knowledge §13-3)은 대화를 만들 수 있지만 "알림을 받은 사람이 답하는가"는 만들 수 없다 — 생성기의 가정이 결과가 된다. 합성 데이터로는 선정 로직(자격·상한·차수가 의도대로 도는가)만 확인하고, 응답률은 dev에서 실제 사용자로 잰다.

---

## 13. 구현 단계

```text
0. knowledge 1단계 (관심 소스 추천) ──▶ 1. 선정만 (dry-run) ──▶ 2. dev 실발송 ──▶ 3. 근접 후보·응답 이력 ──▶ 서비스화
```

- **0. 선행**: knowledge 추천의 1단계(knowledge §14)가 `nobody_covers`를 낼 수 있어야 한다. 경험 소스(2단계)가 없어도 시작할 수 있다 — 그때는 관심 소스만으로 고른다.
- **1. 선정만(dry-run)**: `POST /shout`이 받는 사람을 고르고 원장에 쓰지만 발송하지 않는다. decision log로 자격 단계별 탈락 수와 topic별 자격 인원을 본다 — **topic visibility의 기본값이 원래 private이라**(knowledge §12) 공개한 사람이 적은 topic에서는 자격 인원이 차수 크기보다 적을 수 있다. 이 숫자가 opt-in을 얼마나 일찍 넣을지 정한다(열린 항목 1).
- **2. dev 실발송**: bourbon-api의 발송과 응답 채널(§15)이 생긴 뒤. 관심 소스·친구·최근 활동만으로 순위. 퍼널과 비용 지표를 잰다.
- **3. 근접 후보와 응답 이력**: knowledge 2단계(경험 소스)가 생긴 뒤 근접 후보를, 원장이 쌓인 뒤 응답률·응답 품질을 순위에 넣는다. 기록 기여를 잰다.
- **서비스화**: opt-in·mute UI, 요청자 익명 정책(열린 항목 3), knowledge §12의 공개 범위·동의와 함께.

---

## 14. knowledge 문서와의 관계

- shout는 knowledge 추천의 **다음 단계**이지 대체가 아니다. 추천이 답하면 shout하지 않는다(§4).
- 질문 분석(T1)·topic(T2)·후보(T3)는 knowledge 추천의 결과를 다시 쓴다. shout가 새로 하는 것은 자격·순위·제약·차수다.
- 답은 lived-knowledge의 기록이 된다(§7). shout가 잘 돌수록 knowledge 추천이 답하는 질문이 늘고, shout가 줄어든다 — 두 기능의 지표를 함께 본다(§12의 기록 기여).
- knowledge 열린 항목 33(답변 모드)과 이어진다. 답변 모드가 생기면 "기록으로 답변 → 부족하면 사람 추천 → 그래도 없으면 shout" 순서가 된다.

---

## 15. 요청하고 확인할 것

**bourbon-api · client**

1. **발송.** discovery가 고른 받는 사람에게 shout 문장과 응답 진입점을 알림으로 보내는 경로. discovery가 bourbon-api의 내부 route를 부를지, bourbon-agent가 discovery의 응답을 받아 넘길지. 발송 직전에 받는 사람의 활성 상태를 확인해 주시면 탈퇴 이벤트 유실의 두 번째 방어가 된다(§11).
2. **응답 채널.** 받은 사람이 답하는 곳 — 새 방 종류인지, 요청자의 agent와의 방인지, 알림 안의 답장인지. discovery의 요구는 §7의 셋이다(답한 사람이 분명하다, 요청자에게만 보인다, `message_created`로 발행되고 shout 문장이 문맥으로 그 방에 있다). 그리고 도달 가능성(§7) — 친구도 public도 아닌 요청자에게 답이 가도 되는지.
3. **행동 보고.** 열람·답·거절·mute를 discovery의 `POST /shout/{id}/events`로 보고하는 것(§10). 어트리뷰션 보고(R47)와 같은 방식 — client가 직접 보고해도 된다.
4. **opt-in·mute UI.** topic별 "질문 받기"와 그만 받기(§5-2).

**bourbon-agent**

5. **트리거와 동의.** `nobody_covers`일 때 shout를 제안하고, 요청자가 동의하면 `POST /shout`을 부른다(§4). 제안 문구와 빈도는 그쪽의 판단이다.
6. **답의 전달.** 답이 왔을 때 요청자에게 어떻게 보여 줄지 — 요청자의 agent가 전하는지, 알림으로 가는지. 채널(요청 2)과 함께 정한다.

**lived-knowledge**

7. shout 답이 오가는 방을 적재 대상으로 두는 것(§7). 방 종류가 새로 생기면 `room_type`의 값이 하나 늘고, knowledge §12의 방 범위 규칙이 그 값도 다뤄야 한다.

---

## 16. 열린 항목

1. **opt-in을 언제 넣을지.** 처음에는 공개 topic을 약한 동의로 보고 시작하지만 알림은 노출보다 무겁다. dry-run(§13 1단계)의 topic별 자격 인원을 보고 정한다.
2. **조건을 shout 문장에 실을지.** `condition`은 사용자의 글이라 그대로 싣지 않는다. 요청자가 동의 단계에서 쓴 한 줄을 받을지, need와 공개 이름만으로 충분한지(§6).
3. **요청자를 받는 사람에게 밝힐지.** 기본은 밝히지 않는다. 친구에게는 밝히면 응답률이 오를 수 있다(§6).
4. **답의 도달 가능성.** 친구도 public도 아닌 요청자에게 답이 가는 것, 답 뒤의 대화(§7). 응답 채널(§15 요청 2)과 함께.
5. **부하 신호.** `popularity`를 감점에 쓸지, 받은 shout 수만으로 충분한지(§5-3).
6. **받는 사람끼리 답을 보여 줄지.** 다른 사람의 답을 보면 답하기 쉬워지지만, 답한 사람의 동의 범위가 넓어진다(§7).
7. **초기값 전부** — `shout.wave_sizes`, `shout.wave_timeout_hours`, `shout.max_waves`, `shout.answer_window_hours`, `shout.active_within_days`, `shout.per_recipient_per_week`, `shout.ignore_streak`, `shout.ignore_cooldown_days`, `shout.merge_window_hours`, `shout.per_requester_per_day`, `shout.open_per_requester`, `shout.explore_slots`, `shout.retention_days`, `shout.sweep_minutes`. 지금 값은 모두 추론이고 dev 실발송(§13 2단계)에서 정한다.
8. **늦게 온 답.** shout를 닫은 뒤 온 답을 전달할지, 언제까지 받을지.
9. **응답률의 사전값과 창.** 표본이 적을 때 당기는 정도, 계산 창(§5-3).
10. **2차에서 넓히는 범위.** 상위 1 hop이 맞는지, 형제까지 갈지, drawer(`selectable: false`) 노드를 지나 올라갈지(R25의 계층 감쇠와 같은 기준으로 볼지).
