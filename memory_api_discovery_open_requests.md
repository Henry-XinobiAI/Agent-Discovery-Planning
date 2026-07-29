# Memory API 요청 목록 — Agent Discovery 미해결 항목

- **상태**: DRAFT rev 1 (2026-07-28) — 발신 전 오너 확인 대기.
- **요청 주체**: Agent Discovery (`bourbon-agent-recommendation-api`)
- **대상**: `bourbon-memory-api`
- **기준 커밋**: memory-api `f246f93`, bourbon-api `b84b328`, discovery main `60c4cc2` (전 항목 이 시점 소스 직접 확인).
- **성격**: 이 문서는 **단건 요청서가 아니라 미해결 요청 레지스터**다. 항목별로 독립 처리 가능하며, R1을 제외한 나머지는 Phase 10 real-edge turn-on(`REAL_EDGE_ENABLED=ON`) 설계 시점에 이미 식별된 blocker다.
- **종결된 선행 요청**: statement `attribution` 계약(K-A1) — 결정 기록은 `archive/memory_api_statement_attribution_followup.md`(rev 5). 응답 필드 `#129`/`3e4e7c1`, 요청 필터 `f246f93`로 **shipped**. 남은 것은 아래 R2(테스트)뿐. 최초 요청서(`owner_asserted: bool` 제안)는 **채택되지 않아** `archive/memory_api_statement_attribution_request.md`로 보관했다.

## 요약

| ID | 항목 | 성격 | 차단 대상 | 우선순위 |
|---|---|---|---|---|
| **R1** | 탈퇴(비활성) owner 라이프사이클 | **신규**(2026-07-28 발견) | real-edge turn-on / 추천 품질 | 높음 |
| **R2** | `attribution` 필터 테스트 green | 기존 기능의 테스트 공백 | `STANCE_JUDGE_ENABLED=ON` release gate | 높음 |
| **R3** | pagination + dangling-link join 완전성 | turn-on blocker | real-edge turn-on | 높음 |
| **R4** | freshness 입력 의미(`evidence_last_seen`) | turn-on blocker | real-edge turn-on / freshness 정확도 | 중간 |
| **R5** | persisted link/entity ownership 검증 | turn-on blocker | real-edge turn-on | 중간 |
| **R6** | stale-competence currentness 계약 | turn-on blocker | real-edge turn-on | 높음 |
| **R7** | `attribution` 의미론 불변식 pin | **deferred/conditional** — 지금 막는 것 없음 | 현재 release·turn-on 아님. `confidence` 의미 변경·재색인 시점 | 낮음 |

R3~R6의 원 출처는 Discovery 스펙 `docs/superpowers/specs/2026-07-24-phase10-real-edge-contract-slice-design.md` §9다. 이 문서는 그중 **memory-api가 소유한 항목만** 추려 memory 팀이 단독으로 읽을 수 있게 재작성했다.

---

## R1. 탈퇴(비활성) owner 라이프사이클 — 신규

### 현상

bourbon-api는 사용자 탈퇴 시 personal agent를 **비활성화**한다.

- `user_deactivated` 이벤트 → `personal_agents.service.disable_for_user` (`bourbon_api/personal_agents/events.py:47-57`)
- 해당 함수는 `Agent.enabled = False`로 내리고 `name`/`picture`/`description`/`config`를 비운다 (`bourbon_api/personal_agents/service.py:110-129`). **row 자체는 남는다.**
- DM room은 별도 `cleanup_user_rooms` 플로우가 철거한다(같은 함수 docstring).

그런데 memory-api 쪽에는 이에 대응하는 경로가 없다(`f246f93` 기준 확인):

- 이벤트 수신 경로 자체가 없다 — 코드베이스에 AMQP/deferq 리스너가 0개.
- owner 단위 purge/tombstone 라우트가 없다(삭제 라우트는 admin stats와 message 단건 삭제뿐).
- owner 상태를 표현하는 필드가 없다 — `active`/`status`/`deactivated` 류의 개념 부재.

따라서 **탈퇴한 사용자의 personal knowledge(entity·grounding link·statement·competence)가 무기한 잔존**하고, cross-owner 조회(`POST /personal/entities/search`, `owner_id` 생략 조회, `POST /personal/statements/search`)에 계속 노출된다.

### Discovery 영향

Discovery는 owner_id를 그대로 추천 후보로 삼는다(owner → agent 매핑은 bourbon-api의 결정적 UUID5 파생 `personal_agent_id`이며, 이 매핑은 **row가 비활성이어도 동일한 값을 계산해 낸다**). 즉 Discovery만으로는 비활성 여부를 알 수 없다.

결과: **탈퇴한 사용자의 agent가 추천된다.** 사용자는 추천을 받지만 그 agent는 `enabled=False`이고 DM room도 없어 대화가 불가능하다. 추천 결과의 신뢰를 직접 훼손하는 사용자 노출 버그다.

Discovery가 매 추천 요청마다 bourbon-api에 활성 여부를 조회하는 방식도 이론상 가능하지만, 드문 조건 하나를 위해 추천 hot path에 네트워크 홉을 추가하게 되므로 채택하지 않았다. 데이터 수명주기의 올바른 소유자는 데이터를 보관하는 쪽이라고 판단한다.

### 요청

아래 중 **하나**를 선택해 달라. Discovery는 어느 쪽이든 수용 가능하며, 판단 근거(보존 정책·규제 요건)는 memory 팀에 있다.

**옵션 A — purge.** 탈퇴 수신 시 해당 owner의 personal knowledge를 삭제한다. 가장 단순하고 Discovery 측 변경이 전혀 없다. 보존 요건이 있으면 부적합.

**옵션 B — tombstone + 기본 제외 (권장).** owner 단위 비활성 상태를 기록하고, **cross-owner 읽기 경로에서 기본적으로 제외**한다. 데이터는 남으므로 재가입·감사·분석 여지를 잃지 않는다. Discovery 측 변경 없음(기본 제외이므로).

**옵션 C — 상태 노출.** owner 활성 여부를 응답에 노출하고 필터 파라미터를 제공한다. Discovery가 필터를 보내도록 배선한다. A/B보다 Discovery 작업이 늘고, 필터를 빠뜨린 다른 소비자가 같은 버그를 반복할 수 있어 차선.

어느 옵션이든 **탈퇴 사실을 수신할 경로**가 필요하다. memory-api에 현재 이벤트 소비자가 없으므로, 이벤트 구독 신설 / bourbon-api가 호출하는 내부 엔드포인트 신설 중 어느 쪽이 memory-api 운영 모델에 맞는지도 함께 판단해 달라. (bourbon-api는 이미 `user_deactivated` 이벤트를 발행하고 있으므로 발행 측 추가 작업은 없을 것으로 보인다 — bourbon-api 팀과의 확인은 Discovery가 맡는다.)

### 수용 기준

- 탈퇴 처리된 owner가 `POST /personal/entities/search`, cross-owner 엔티티 조회, `POST /personal/statements/search` 결과에 **나타나지 않는다**.
- 이미 탈퇴한 기존 owner에 대한 backfill 또는 정리 방안이 함께 정해진다(신규 탈퇴만 막으면 기존 잔존분이 그대로 남는다).
- 재활성(재가입)이 가능한 제품이라면 그때의 동작이 정의된다.

---

## R2. `attribution` 필터 테스트 green

### 현상

`f246f93`로 `PersonalStatementSearchRequest.attribution: list[Attribution] | null`이 shipped 됐고, Discovery는 이미 `["owner"]`를 전송하도록 배선을 마쳤다(discovery `7180c25`). 필터가 per-owner cap **이전**에 적용된다는 점도 코드 판독으로 확인했다(`repository.py`에서 attribution→confidence-band range가 OpenSearch `bool.filter`에 들어가고 `terms(owner_id)` + `top_hits(per_owner_limit)` 집계가 필터된 문서 집합 위에서 실행됨).

다만 테스트가 두 군데 비어 있다:

1. **router fake가 새 kwarg를 안 받는다.** `tests/routers/personal/test_router.py:294`의 `_FakeRepo.search_statements` 시그니처에 `attribution` 파라미터가 없다 — 라우터가 이를 전달하면 `TypeError`가 난다.
2. **filter-before-cap acceptance 테스트가 없다.** 이 순서 보장은 이 계약의 핵심이며(뒤에 적용되면 admissible statement가 per-owner top-N에서 밀려 복구 불가), router fake로는 검증할 수 없다 — OpenSearch를 실제로 태우는 테스트가 필요하다.

### Discovery 영향

기능은 동작하고 있으므로 Discovery 개발을 막지는 않는다. 다만 **`STANCE_JUDGE_ENABLED=ON` 활성화 전 release gate 항목**으로 잡아 두었다: 순서 보장이 회귀해도 아무도 모르는 상태로 프로덕션 stance 판정을 켤 수는 없다.

### 요청

1. router fake 시그니처에 `attribution` 추가 및 라우터 테스트 green.
2. OpenSearch 기반 acceptance 테스트 1건: 동일 owner에 non-owner attribution statement를 relevance 상위에 두고 owner statement를 하위에 둔 뒤 `per_owner_limit=1`로 검색 → **owner statement가 남아야 한다.**

### 수용 기준

위 2번 테스트가 CI에서 통과한다. (Discovery는 같은 시나리오를 자체 eval fake에 이미 미러링해 두었다 — discovery `2cd583b`.)

---

## R3. pagination + dangling-link join 완전성

### 현상

link → entity join에서 **엔티티 레코드가 없는 link(dangling link)를 조용히 skip**한다 (`memory/knowledge/personal/repository.py:242` `entities_grounded_to` docstring: "Pairs whose entity record is missing (dangling link) are skipped").

`limit`이 걸린 조회에서 link 단위로 자른 뒤 join에서 일부가 탈락하면, 반환된 pair 수가 limit보다 적으면서도 `truncated` 신호는 "더 있음/없음"을 join 이후 기준으로 말해 주지 못한다.

### Discovery 영향

Discovery는 cross-owner 조회 결과로 후보 집합을 만든다. `truncated=false`가 "이 QID의 모든 유효 owner를 받았다"를 의미하지 못하면, **일부 owner가 조용히 누락된 채 추천이 나간다.** 누락을 관측할 방법이 없다는 점이 특히 문제다.

### 요청

다음 중 하나를 보장해 달라.

- **(a)** dangling link 발견 시 endpoint fail-loud — 데이터 무결성 위반을 조용히 넘기지 않는다.
- **(b)** 유효 joined pair가 `limit + 1` 개가 될 때까지 계속 조회한 뒤 자른다 — `truncated`가 join 이후 기준으로 정확해진다.
- **(c)** join 이후 기준의 total 또는 cursor를 제공한다 — Discovery가 완전성을 스스로 판단할 수 있다.

### 수용 기준

`truncated=false`가 **join 이후 완전성**을 의미한다는 것이 문서와 테스트로 고정된다.

---

## R4. freshness 입력 의미 — `evidence_last_seen`

### 현상

Discovery는 owner competence의 `last_seen` 계열 신호를 `AgentTopicEdge.freshness`로 투영한다. 그런데 이 값이 **"가장 최근 qualifying evidence의 실제 시각"인지 "마지막 build 실행 시각"인지가 계약으로 고정돼 있지 않다.**

### Discovery 영향

build 실행 시각으로 갱신되는 값이라면, **오래된 evidence가 매 build마다 새것처럼 보인다.** freshness는 랭킹 ordering key이므로 이는 조용한 랭킹 왜곡이다. 현재 Discovery는 freshness를 provisional projection으로 취급하고 있다.

### 요청

`evidence_last_seen`(해당 owner·주제에 대한 가장 최근 qualifying evidence의 실제 timestamp)을 제공하거나, 기존 `last_seen`의 lifecycle을 그 의미로 수정해 달라.

**명시적 금지: 단순 build 실행 시각으로의 갱신.**

### 수용 기준

필드 의미가 문서에 고정되고, evidence 추가 없이 rebuild만 했을 때 값이 변하지 않음을 보이는 테스트가 있다.

---

## R5. persisted link/entity ownership 검증

### 현상

`GroundingLink`와 `PersonalEntity`를 pair로 fold할 때 **양쪽의 `owner_id`가 같은지 검증하지 않는다.** 현재 응답은 `link.owner_id`를 노출하지 않으므로 Discovery는 DTO 자체의 self-consistency까지만 확인할 수 있고, 저장된 데이터가 실제로 같은 owner의 것인지는 확인할 방법이 없다.

### Discovery 영향

owner 경계를 넘는 fold가 발생하면 **A의 지식이 B의 competence로 귀속**된다. Discovery는 그 결과를 그대로 추천 근거로 쓰므로 오귀속이 사용자에게 그대로 노출된다.

### 요청

fold 이전에 `GroundingLink.owner_id == PersonalEntity.owner_id`를 검증하고, 불일치 시 fail-loud 처리해 달라.

### 수용 기준

owner가 어긋난 pair를 심은 테스트가 조용한 성공이 아니라 명시적 실패로 끝난다.

---

## R6. stale-competence currentness 계약

### 현상

competence 벡터는 판정 시점의 evidence set을 근거로 만들어진다. 이후 statement가 비활성화·삭제·갱신되어도 **competence가 재판정 전까지 과거 판정을 유지**하며, 소비자는 그 불일치를 알 수 없다.

### Discovery 영향

Discovery는 competence를 maturity / evidence_strength / freshness로 투영해 **게이트 통과 여부와 랭킹 순서를 결정**한다. 근거가 사라진 owner가 계속 상위 후보로 남는다.

### 요청

**현재 active statement set과 competence가 판정 근거로 삼은 evidence set의 currentness를 검증할 serving 계약**을 정의해 달라. 불일치 시 competence를 미노출/`None` 처리하거나 재판정 완료 전까지 노출에서 제외하는 방식을 상정하고 있다.

두 가지를 명시적으로 구분해 달라.

- **`competence=None` clear는 zero-active(근거가 전부 사라진 경우)의 필수 특례일 뿐**이며, 일반 해결책이 아니다.
- **`support_ids`만 현재 ID로 갈아끼우는 것은 금지** — 근거 개수는 유지된 채 내용만 바뀌므로 depth를 위장하게 된다.

기존에 쌓인 stale 데이터의 rebuild/backfill 완료도 함께 필요하다.

### 수용 기준

- currentness 불일치 상태의 owner가 cross-owner 조회에 competence를 노출하지 않는다(또는 불일치 사실을 소비자가 판별할 수 있다).
- 기존 stale 데이터 정리 계획이 정해진다.
- (Discovery 측) currentness 불일치 owner가 후보로 새지 않는 회귀 테스트를 추가한다 — 이건 Discovery가 맡는다.

---

## R7. `attribution` 의미론 불변식 pin — deferred / conditional

> **지금 아무것도 막지 않는다.** 현재 release도, `STANCE_JUDGE_ENABLED=ON`도, real-edge turn-on도 이 항목을
> 기다리지 않는다. 트리거가 왔을 때 꺼내 볼 항목으로 등록해 둔 것이다 — R1~R6과 성격이 다르므로 blocker
> 목록으로 읽지 말 것.

### 현상

Discovery는 `attribution == "owner"`를 "owner가 그 claim을 직접 주장했다"로 신뢰하고 stance evidence를
admit한다. 이 신뢰의 근거는 `attribution`이 assertion-source **tier**에서 파생된다는 점이다 —
`_util._statement_confidence`가 claim의 provenance 메시지 sender에 owner가 있을 때만(`any(s == owner_id for
s in cited)`) OWNER를 부여한다. 즉 numeric confidence가 높아서가 아니다.

이 파생이 계약으로 고정되어 있지 않다. `confidence`가 훗날 다른 목적(일반 품질 점수 등)으로 **재용도되면**
OWNER 파생이 조용히 깨지고, Discovery는 owner가 주장하지 않은 statement를 owner 주장으로 읽는다 — stance
verdict의 근거가 오염되는데 아무 오류도 나지 않는다.

### 요청

`attribution == "owner"` ⟺ claim provenance에 owner sender가 있음, 이 불변식을 **테스트로 고정**해 달라.
그러면 `confidence`의 의미를 바꾸는 변경이 이 파생을 깨뜨릴 때 memory-api CI에서 먼저 잡힌다.

### 트리거 (이 시점 전에 처리)

- `confidence` tier를 재용도하거나 의미를 바꾸는 변경
- `attribution` 파생 규칙 자체의 변경

둘 다 어차피 **재색인을 요구**하는 변경이라, 그 작업과 함께 처리하기로 2026-07-23에 합의했다.

### 배경

이 항목은 K-A1 협의(rev 4 §1-4)에서 "연기된 장기 리스크"로 합의된 것이다. 의미론 종결의 코드 근거와 내가
우려했던 두 오분류(owner의 질문이 OWNER로 잡히는 과대 / 타인 선주장 claim의 owner 재주장이 누락되는 과소)가
왜 구조적으로 생기지 않는지는 `archive/memory_api_statement_attribution_followup.md` §1에 기록돼 있다.

---

## 부록 — Discovery가 memory-api에 **요청하지 않는** 것

혼선을 줄이기 위해 명시한다.

- **stance axis/direction/confidence 필드** — 요청하지 않는다. stance는 Discovery가 query-time live judge로 산출한다.
- **evidence 원문 노출 확대** — 요청하지 않는다. `support_ids` 투영으로 충분하다.
- **agent identity** — 요청하지 않는다. owner_id만 주면 되고, agent_id는 bourbon-api의 결정적 파생이다.
- **eligibility(privacy/safety) 판정** — 요청하지 않는다. Discovery 소유이며 현재는 승인된 임시 정책(allow-all)으로 운영한다.
