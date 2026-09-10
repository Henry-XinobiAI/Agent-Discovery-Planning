# bourbon-agent 요청서 — 타입 ① 호출의 새 계약과 카드 meta

> 코드 읽은 기준: bourbon-agent main `208a6286`(2026-09-08), persona 쪽 2026-09-10. 결정: R02(타입 ①), R24(`recommendation_id`), R40(`lang`), R42(HEXACO — **이 요청서에 넣지 않는다**).

## 1. 타입 ① 호출을 새 계약으로

지금 `bourbon_agent/api_internal_client/agent_discovery.py`가 `POST /recommend`를 부르고 `agents/personal_agent/recommendation/tools.py`가 사용한다. 새 route는 아래다(내부 API, edge-auth 없음).

```
POST /api/internal/svc/agent-discovery/recommend/explicit
{
  "user_id": "uuid",               // 요청자 — 아래 §1-1. 결과에서 본인은 제외
  "topic_text": "…",               // 유저가 말한 topic. 1~200자
  "context": "…",                  // 최근 대화 일부. ≤2000자, 선택
  "max_results": 3,                // 1~20, 기본 3
  "room_id": "uuid",               // 로그 추적용, 선택. 우리는 room을 읽지 않는다
  "lang": "ko"                     // ko | en | ja. 보내 주기를 요청한다 — 없으면 en으로 답한다(R40)
}
```

응답 envelope는 `contract_version`, `recommendation_id`, `resolved_topics[]`(free text에서 확정된 topic 1~3개), `agents[]`(각각 agent_id, owner_user_id, position, matched_topics[{topic_id, label, requested, owner_note}], signals, fit), `empty`, `degraded[]`다. 스키마는 `agent_discovery_contract.md` §2-1·§3. 기존 `POST /recommend`는 전환 기간 뒤 닫는다 — 시점은 §4에서 맞춘다.

### 1-1. 요청자는 "실제로 말한 사람"

지금 코드는 항상 agent **소유자**를 요청자로 보낸다. 자기 agent에게 묻는 경우는 소유자와 같으니 문제없다. 타인의 agent 방에서 그 agent에게 "추천해 줘"라고 묻는 경우가 제품에 있다면, 요청자는 **말한 사람**이어야 한다 — 추천은 요청자의 topic·친구 관계로 필터되고 요청자 본인은 결과에서 빠지기 때문이다. 그 경우가 제품에 없다면 지금 코드 그대로도 맞다. **어느 쪽인지 알려 주시면 된다.**

### 1-2. 우리 API가 유저의 글을 다루는 방식

`topic_text`·`context`는 topic 확정에만 쓰고 로그·예외·Sentry에 원문으로 남기지 않는다(계약 §5 불변식 7). 응답의 `owner_note`는 소유자가 쓴 문장이라 카드에 그대로 보여 주기만 하면 된다 — bourbon-agent 쪽 로그에도 남기지 않기를 요청한다.

## 2. 추천 카드 meta에 `recommendation_id`

타입 ① 응답의 `recommendation_id`를 추천 카드(bourbon-api를 거쳐 클라이언트로 가는 메시지)의 meta에 실어 주시면 된다. 클라이언트는 그 카드에서 대화를 시작할 때 이 값을 우리 route `POST /api/svc/agent-discovery/attributions`에 `entry="recommend_explicit"`과 함께 보고한다(클라이언트 요청서 §2, R47). bourbon-api는 거치지 않는다. 카드 하나에 agent가 여럿이면 `recommendation_id`는 하나(응답 단위)다.

**왜**: 우리는 이 보고를 bourbon-api의 방 생성 이벤트와 이어 결정 로그와 조인해 "이 추천이 대화를 만들었나"를 잰다. 소급이 안 되는 값이라 첫 배포부터 필요하다.

## 3. 요청하지 않는 것 — 기록으로

- **HEXACO 성향 벡터**(R42·O20): persona 중 topic으로 오지 않는 HEXACO 추정치를 나중에 타입 ③ feature로 쓸 방향이 정해져 있고, 받는 경로는 **이벤트**(확정 아님)다. bourbon-agent에 API를 열 가능성은 없다는 것을 알고 있다. 무엇을 내보낼지와 동의 범위가 정해진 뒤 별도로 요청한다(추출 노트의 추정치에는 visibility 구분이 없다). 지금 우리 코드는 자리만 있고 값은 0이다.
- **turn 이벤트**: 필요 없다. bourbon-api의 `message_created`로 센다.
- **`persona_updated`**: 그대로 두면 된다. 우리는 직접 사용하지 않고 topic-api의 `topics_updated`를 받는다.

## 4. 확인 질문

1. §1-1 — 타인 agent 방에서 추천을 요청하는 경우가 제품에 있는가.
2. §1 — 기존 `POST /recommend`를 닫아도 되는 배포 시점.
3. §2 — 카드 meta의 필드 이름(클라이언트와 같은 이름을 쓰면 된다).
