# 수신 이벤트 계약 — 제안 (2026-09-01)

> **문서 지위: 제안이고 결정이 아니다.** 어떤 코드도 이 문서를 근거로 바뀌지 않았고 **어느 팀에도
> 발신하지 않았다.** 설계 정본은 [`recommendation_pipeline_design.md`](recommendation_pipeline_design.md),
> 가려는 곳은 [`recommendation_scoring_design.md`](recommendation_scoring_design.md)가 소유한다.
> 이 문서는 그 설계의 **§12 Q1(대화 이벤트 계약 — 무엇이 발생하고 누가 보내나)** 을 답하려는 하류
> 문서이고, 결정이 생기면 정본으로 올린다.
>
> **범위: 수신 전용.** 우리가 *발신·기록*하는 노출/보상 행의 필드는
> [`recsys_opensource/off_policy.md` §3](recsys_opensource/off_policy.md)이 소유한다. **여기서 다시
> 정의하지 않는다.**
>
> **표기**: `사실` · `판단` · `열린 항목`.
> 유도 과정은 [`recsys_adoption_discussion.md`](recsys_adoption_discussion.md) §5-3~§5-5.

---

## §1 범위 — 수신과 발신을 가르는 선

```text
받는다 (이 문서)                        만든다 (off_policy.md §3)
────────────────────                    ────────────────────────
topic 카탈로그 변경                      decision 행   (후보 전체·제외 사유·버전)
agent 의 공개 보유 집합                  노출 행       (자리·conditional_propensity)
agent·user 의 자격/상태                  보상 행       (decision_id 로 조인)
requester–agent 행동 사건
```

`판단` **경계는 "서빙이 만들어내는 값인가"다.** 후보 집합·자리·노출확률은 우리 서빙이 만드는 값이므로
아무도 우리에게 줄 수 없다. 반대로 누가 무엇을 보유하는지는 우리가 관측할 수 없다.

행동 사건은 **양쪽에 걸친다** — 사건 자체는 받고, 그것을 어느 노출에 귀속시킬지는 우리 로그가 정한다.
그래서 §3-4의 `decision_id`가 이 계약 전체에서 가장 중요한 필드다.

---

## §2 설계 원칙 넷

### ⓵ 델타가 아니라 현재 전체 집합을 받는다

"topic 추가됨/삭제됨"이 아니라 **"이 agent의 현재 공개 topic 집합은 이것"** + `revision`.

우리는 복제본을 유지한다. 델타는 완벽한 순서 보장을 요구하고 **한 건만 유실돼도 영구히 어긋난다.**
전체 집합이면 순서는 최대 `revision` 채택으로 끝나고 중복 전달은 무해하다.

`사실` 발신 측에서 **수용 가능**(2026-09-01 확인).

★ 이 선택이 저장 모양을 결정한다 — **이벤트 1건 = 항목 1개 = 조건부 PutItem 1회.**

### ⓶ 공개 투영만 받는다

`friends`·`private` 보유는 **애초에 받지 않는다.** 그러면 "공개 → 비공개 전환"이 *집합에서 빠지는
것*으로 도착하고, 민감 데이터가 우리 쪽에 존재하지 않으므로 유출 표면 자체가 없다.

`판단` **가장 강한 보호는 받지 않는 것이다.** 그리고 이것이 §4의 등급 분리를 단순하게 만든다 —
남는 것이 정보 문제가 아니라 "이 사람을 이 사람에게 보여주는가"뿐이 된다.

### ⓷ 파생값이 아니라 원천 관측값을 받는다

상류가 계산해 준 판단값(예: "숙련도 3.2")을 받지 않고 **셀 수 있는 것**을 받아 파생은 우리
feature 함수가 한다.

이유 둘. **상류가 공식을 바꾸면 우리 feature가 조용히 이동한다** — 원천값을 받으면 그 변경이 우리 쪽
버전 관리 대상이 된다. 그리고 **이름이 판단을 계약에 새긴다** — 나중에 "그건 그 이름이 아니었다"를
알게 되면 여러 소비자가 이미 그 이름을 읽고 있다.

### ⓸ 귀속 키를 처음부터 넣는다

행동 사건에 `decision_id`가 없으면 **"무엇을 보여줬기 때문에 이 대화가 생겼는가"를 영구히 알 수
없다.** 대안인 `(requester, agent, 시간창)` 조인은 같은 사람이 같은 agent를 다른 경로로 만나면
오귀속되고, 그 오차를 나중에 측정할 방법이 없다. **소급 불가 항목이다.**

---

## §3 이벤트 목록

### 3-1 카탈로그 — topic

우리가 topic별 질의 단위(더미 item 또는 색인 키)를 유지해야 하므로 필요하다.

```json
{
  "event_id": "…", "event_type": "topic.changed", "occurred_at": "…",
  "topic_id": "Q12345", "revision": 8,
  "labels": {"ko": "커피", "en": "Coffee"},
  "parent_topic_ids": ["Q999"],
  "status": "active | merged | deleted",
  "merged_into_topic_id": null
}
```

| 필드 | 왜 |
|---|---|
| `labels` | 응답 표시 + 사용자가 보는 라벨. 이 구조에서 topic-api의 주 역할 |
| `parent_topic_ids` | 상위 라벨 질의를 **recall 장치**로 쓰려면 계층을 알아야 한다 |
| `status` / `merged_into_topic_id` | topic은 병합·분할·개명된다. 질의 단위와 색인이 함께 이동해야 한다 |

### 3-2 보유 — 이 계약의 본체

```json
{
  "event_id": "…", "event_type": "agent.public_topics.changed", "occurred_at": "…",
  "personal_agent_id": "…", "owner_user_id": "…",
  "revision": 47,
  "public_topics": [
    {
      "topic_id": "Q12345",
      "mention_count": 42,
      "distinct_conversation_count": 7,
      "first_seen_at": "…",
      "last_reinforced_at": "…"
    }
  ]
}
```

| 필드 | 어디로 | 왜 |
|---|---|---|
| `topic_id` | **Gorse Item `Labels.topics`** | 후보 생성의 전부 |
| `mention_count` · `distinct_conversation_count` | **우리 store** | 원칙 ⓷. Gorse가 못 읽으므로(`recsys_opensource/gorse.md` §11-3) rerank feature |
| `last_reinforced_at` | 우리 store | 최근성 감쇠 |
| `owner_user_id` | 우리 store | self-exclusion · 응답 hydration |
| `revision` | — | 순서·멱등 |

`판단` **"depth"라고 부르지 않는다.** 무엇이 전문성인지는 아직 정해지지 않았고, 위 두 카운트는
전문성이 아니라 **관련성의 세기**다. 정보검색의 `tf`에 해당하고 그 자리에 정확히 들어간다.
전문성 축이 실재하게 되면 그때 별도 필드로 additive하게 붙인다.

`열린 항목` 카운트의 정의(무엇을 1회로 세는가)와 그 안정성. 정의가 바뀌면 `count_schema_version`이 필요하다.

### 3-3 자격·상태

```json
{
  "event_id": "…", "event_type": "agent.status.changed", "occurred_at": "…",
  "personal_agent_id": "…", "owner_user_id": "…", "revision": 12,
  "status": "active | suspended | deleted",
  "languages": ["ko", "en"],
  "last_active_at": "…"
}
```

```json
{"event_type": "user.created", "user_id": "…", "occurred_at": "…"}
{"event_type": "user.deleted", "user_id": "…", "occurred_at": "…"}
{"event_type": "user.blocked", "requester_user_id": "…", "blocked_user_id": "…", "active": true}
```

| 필드 | 비고 |
|---|---|
| `status=deleted` | Gorse `IsHidden=true` + 우리 색인 제거 + Gorse Feedback 정리. §4 상단 등급 |
| `languages` · `last_active_at` | rerank 신호 |
| `user.deleted` | **Gorse User · Gorse Feedback · 우리 store · 이벤트 스트림 네 곳**에 전파 |

`판단` **`recommendable`은 wire에 싣지 않는다.** 현재는 topic 공개에서 파생되므로, 실으면 발신 측이
상수를 계산해 넣게 되고 "판정했다"와 "할 말이 없어 채웠다"가 wire 위에서 구별되지 않는다. 그리고
매번 `true`가 도착하면 게이트가 이미 처리된 것처럼 보인다.

대신 **판정할 자리를 우리 gate에 만든다** — `is_recommendable(agent, requester)`. 오늘 구현은
"공개 topic이 하나라도 있으면 참"이다. 자명한 판정도 판정이고, 축이 생기면 이 함수와 이벤트 필드
하나만 바뀐다.

★ **필드를 예약하지 말고 판정을 예약한다.** 필드는 모양을 미리 정하지만 판정은 그렇지 않다.
agent 단위 공개 축이 이진일지 tier일지 표면별일지 아직 모르고, 그중 셋에서 이진 필드는 틀린 모양이다.

### 3-4 행동 — 퍼널

```json
{
  "event_id": "…", "event_type": "conversation.started", "occurred_at": "…",
  "decision_id": "dec-123",
  "requester_user_id": "…", "personal_agent_id": "…",
  "surface": "topic_search | home",
  "topic_id": "Q12345"
}
```

단계: `card.selected` · `conversation.started` · `conversation.depth_reached` · `resolved` ·
`requery.other_agent`.

| 어디로 | 무엇 |
|---|---|
| **우리 이벤트 스트림** | 원본 전부. 여기서 `recsys_opensource/off_policy.md` §3-3의 보상 행을 만든다 |
| **Gorse Feedback** | `(requester_user_id, personal_agent_id, type, timestamp)` 투영만 |

`판단` **Gorse에 보내는 것은 투영이고 원본이 아니다.** Gorse 스키마에는 `decision_id`·`position`·
`conditional_propensity`를 담을 자리가 없다. 원본은 우리가 append-only로 갖는다.

`판단` `decision_id`는 **우리가 응답에 실어 보낸 값을 그대로 돌려받는 것**이다. 발신 측이 새로 만드는
값이 아니다.

> **투영 규칙은 [`recsys_opensource/feedback_semantics.md`](recsys_opensource/feedback_semantics.md)가
> 소유한다.** 이 목록의 어느 단계를 Gorse의 positive·read·negative 중 무엇으로 보낼지는 여기서
> 정하지 않는다. 다만 그 문서가 확인한 두 가지가 이 퍼널에 직접 걸린다 — **`negative`는 영구
> 제외이므로 `requery.other_agent`를 negative로 보내면 그 조합이 다시는 추천되지 않고**(§2-5),
> **의미가 정해지지 않은 단계는 Gorse에 보내지 않는다** — 버킷 미지정은 중립이 아니라 조용한
> 제외다(§6-1). 원본은 어차피 우리 스트림에 있으므로 늦게 투영하는 비용이 없다.

---

## §4 지연 허용치 — 두 등급

| 등급 | 이벤트 | 허용 지연 | 처리 |
|---|---|---|---|
| **차단·삭제·자격 상실** | `status=deleted` · `user.deleted` · `user.blocked` · 공개 집합에서 빠짐 | 초 단위 | **우리 store에서 서빙 시점에 읽고, 최종 N명을 원본으로 재확인.** 캐시 갱신에 의존하지 않는다 |
| **품질** | 새 topic · 카운트 증가 · `last_active_at` · `languages` | 분~십수분 | Gorse `cache_expire`로 조절 (`gorse.md` §11-4) |

`판단` **이것은 정보 보안 등급이 아니다.** 원칙 ⓶ 때문에 우리는 공개 사실만 갖고 있고, 추천 결과가
드러낼 수 있는 것도 공개 사실뿐이다. 내용 보호는 하류(agent·memory·persona)가 소유한다.

남는 것은 **"이 사람을 이 사람에게 보여주지 않는다"**이고, 이건 하류가 대신할 수 없다 — 그쪽은 대화
내용을 막지 만남 자체를 막지 못한다. 그래서 상단 등급은 유출 방지가 아니라 **노출 자체의 차단**이다.

★ 상단 등급을 Gorse 캐시 갱신에 태우면 `cache_expire`가 곧 노출 창(window)이 된다.

★ **최종 N명 재확인은 "잘라낸 나머지"를 전제한다.** 재확인이 한 명을 떨어뜨리면 N−1명으로 답하거나
뒤에서 채워야 하는데, 채우려면 순위를 자른 뒤에도 나머지를 들고 있어야 한다. 현재 구현은 자르고
버린다(`agent_discovery/stages/ordering.py` — `ranked[:max_results]`). **재확인을 켜기 전에 이것부터
열어야 하고, 지금은 아무도 쓰지 않으므로 싸다.**

`판단` 후보 전체의 자격을 미리 읽어 S4에 넘기는 배치도 가능하지만, 3명을 답하려고 300명을 조회하게
된다. 최종 N명 재확인이 맞고, 위 한 줄이 그 전제다.

---

## §5 받지 않고 우리가 만드는 것

| 무엇 | 왜 우리 것인가 |
|---|---|
| decision · 노출 · 보상 행 | 서빙이 만들어내는 값. `off_policy.md` §3이 소유 |
| coverage · focus 점수 | 질의 시점 계산 |
| `is_recommendable()` 판정 | §3-3 |
| 최종 자격 판정 | `recsys_opensource/README.md` §9 |

---

## §6 협의 상태

| # | 항목 | 상태 | 비고 |
|---|---|---|---|
| **E1** | 행동 이벤트에 `decision_id`를 실을 수 있는가 | **미확인 — 임계경로** | 실을 수 있을 것으로 보나 확인 전. **소급 불가**이므로 가장 먼저 닫는다 |
| **E2** | 전체 집합 + `revision` 방식 | **✅ 수용 가능** | 저장 모양이 여기서 확정됨 |
| **E3** | 보유 강도의 형식 | **재정의됨** | "depth"를 요구하지 않고 원천 카운트를 받는 것으로 바꿈(⓷). 카운트 정의는 열림 |
| **E4** | `recommendable` 동의 축 | **닫힘 (현재 기준)** | topic 공개에서 파생. wire 제외, gate에 자리 |
| **E5** | 보안 등급 전달 보장 | **좁혀짐** | 정보 보안이 아니라 차단·삭제 전파로 축소. 서빙 시점 조회로 해결 |
| **E6** | topic 병합·분할 시 과거 로그 처리 | **보류** | 아래 한 줄만 지금 고정하면 보류가 안전하다 |

`판단` **E6 보류의 조건**: 지금 "**과거 로그의 `topic_id`를 재작성하지 않는다**"만 정해두면 된다.
로그는 그때의 사실이고, 병합이 실제로 일어날 때 매핑 테이블로 해석하면 된다. 재작성하는 쪽을 나중에
고르면 소급 작업이 생기지만, 안 하는 쪽을 지금 정해두면 선택지가 계속 열려 있다.
**판단이 아니라 옵션 보존이므로 지금 정해도 비용이 없다.**

---

## §7 이 문서가 하지 않은 것

- **어느 팀에도 발신하지 않았다.** E1은 확인 전이다.
- **코드 변경 없음.** 어떤 repo도 이 문서를 근거로 바뀌지 않았다.
- **노출·보상 필드를 정의하지 않았다.** `recsys_opensource/off_policy.md` §3이 소유한다.
- **저장 제품을 고르지 않았다.** ⓵이 "이벤트 1건 = 항목 1개"를 함의한다는 것까지만 적었다.
- **카운트의 정의를 정하지 않았다**(§3-2 열린 항목). 무엇을 1회로 세는지는 상류가 답할 질문이다.
- **전달 보장 수준을 정하지 않았다.** at-least-once + 멱등(⓵)을 전제했을 뿐 협의하지 않았다.
