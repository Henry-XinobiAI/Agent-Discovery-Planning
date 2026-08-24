# bourbon-api 요청 목록 — Agent Discovery 미해결 항목

> **📦 종결·보관 (2026-08-24) — 미발신 초안인 채 종결.** 두 항목 모두 요청 발신 없이 닫혔다.
> **B1**(owner→agent uuid5 파생의 producer-side pin): **발신하지 않기로 결정**(오너 확인) — 파생은
> bourbon-api가 지정한 고정 계약이고 기존 memory-api 체인 버전도 같은 방식으로 구현했다. 변환
> 규칙의 명문화(namespace 상수·known vector·세 repo 재검증)는 `../recommendation_pipeline_design.md`
> S6-0이 갖는다. **B2**(신뢰된 requester identity): 호출자가 bourbon-api가 아니라 **bourbon-agent**로
> 바뀐 새 wire 계약에서 `requester_user_id`로 들어온다 — 신뢰 규율(handler가 task payload에서 채움,
> 모델 공급 신원 비신뢰)은 같은 문서 §2. 본문의 `persona_topic_search_design.md` 참조는 같은 날
> 함께 보관된 문서다(같은 디렉토리).

- **상태**: DRAFT rev 1 (2026-07-28) — 발신 전 오너 확인 대기.
- **요청 주체**: Agent Discovery (`bourbon-agent-recommendation-api`)
- **대상**: `bourbon-api`
- **기준 커밋**: bourbon-api `b84b328`, discovery main `60c4cc2` (전 항목 이 시점 소스 직접 확인).
- **성격**: 미해결 요청 레지스터. 항목별로 독립 처리 가능하다. (자매였던 memory-api 레지스터는
  2026-08-20 소스 전환 확정으로 폐기 — `archive/memory_api_discovery_open_requests.md`. **B1·B2는
  소스와 무관하게 유효하다**: 새 체인(`persona_topic_search_design.md`)의 agent_id hydration과
  requester self-exclusion이 정확히 이 두 계약 위에 선다.)

## 요약

| ID | 항목 | 성격 | 차단 대상 | 우선순위 |
|---|---|---|---|---|
| **B1** | owner→agent identity 파생을 immutable cross-service contract로 선언 + producer-side pin | 계약 명문화 + 테스트 | real-edge turn-on(잔여 위험) | 높음 |
| **B2** | 신뢰된 requester identity 전달 계약 | 신규 계약 | requester self-exclusion | 높음 |

**둘 다 Discovery의 현재 구현을 막지는 않는다.** B1은 이미 동작하는 파생의 *회귀 방지 장치*이고, B2는
`REAL_EDGE_ENABLED` turn-on 전에 닫아야 하는 gate다. 그때까지 Discovery는 production stage에서
real-edge 부팅을 코드로 거부한다.

---

## B1. owner→agent identity 파생 — immutable cross-service contract 선언 + producer-side pin

### 배경

Discovery는 memory-api로부터 **owner_id**(사용자 UUID) 단위의 지식·competence를 받아 추천 후보를 만들고,
응답에서는 **agent_id**를 돌려줘야 한다. 이 변환은 bourbon-api의 결정적 UUID5 파생이다.

```python
# bourbon_api/personal_agents/__init__.py:23, 31-33
AGENT_NAMESPACE: UUID = uuid5(NAMESPACE_DNS, "agent.bourbon.xinobi.net")

def personal_agent_id(user_id: UUID) -> UUID:
    return uuid5(AGENT_NAMESPACE, f"personal_agent:{user_id}")
```

같은 모듈 docstring(`:9`)은 이 namespace가 **"deliberately stage-independent"** — 즉 stage가 달라도 같은
user id는 같은 agent id로 간다고 선언한다.

Discovery가 이 값을 조회할 수 있는 HTTP 경로는 없다. `GET /users/me/personal-agent`
(`api/routers/users.py:114-118`)는 `Depends(get_current_user)`로 **호출자 본인만** 조회하며,
service-to-service 배치 resolve 엔드포인트는 존재하지 않는다. 즉 **현재 조회 계약으로는 배치
resolution이 불가능하다.** Discovery는 추천 hot path에 신규 네트워크 홉을 추가하지 않기 위해
**현 단계에서 이 파생을 자기 코드에 복제한다**(`discovery/providers/identity_resolver.py`,
이번 작업에서 신설). 이는 논리적 필연이 아니라 현재의 선택이며, 대안은 아래 "대안" 절에 있다.

### 문제

bourbon-api `tests/personal_agents/test_ids.py`는 네 개의 테스트로 **결정성**과 **구별성**만 검사한다.

- `test_personal_agent_id_is_deterministic` — 같은 입력이 같은 출력을 낸다
- `test_personal_agent_id_differs_by_user` — 다른 입력이 다른 출력을 낸다
- (DM room id에 대한 동일한 2건)

**`AGENT_NAMESPACE` 상수도, 어떤 known vector도 고정하지 않는다.** 그래서 누군가 namespace 문자열
(`"agent.bourbon.xinobi.net"`)이나 포맷 문자열(`f"personal_agent:{user_id}"`)을 바꾸면:

1. bourbon-api CI는 **통과한다** — 바뀐 함수도 여전히 결정적이고 여전히 user별로 다르다.
2. Discovery CI도 **통과한다** — 자기 쪽 복제본과 자기 쪽 하드코딩 기대값만 비교한다.
3. 변경은 **양쪽의 독립 단위 CI에서는 드러나지 않고**, cross-service integration/preflight 또는
   실제 serving에서야 드러난다 — 추천 결과가 존재하지 않는 agent id를 가리킨다.

Discovery 쪽 known-vector 테스트는 이 drift를 잡지 못한다. 그것은 **consumer-side replica pin**이며
"우리가 복제본을 몰래 바꾸지 않았다"만 증명한다. 계약을 실제로 지키려면 **producer 쪽에도 같은 값이
박혀 있어야** 한다.

덧붙여, 이 파생은 이미 **DB에 물리적으로 적재된 PK**다(`Agent.id`). 값이 바뀌면 코드 동시 변경만으로는
부족하고 데이터 마이그레이션이 필요하다. 즉 이것은 사실상 이미 immutable인데 **그 사실이 어디에도
쓰여 있지 않은** 상태다.

### 요청

`tests/personal_agents/test_ids.py`(또는 적절한 위치)에 다음 세 가지를 추가해 달라.

**ⓐ namespace 상수 pin**

```python
def test_agent_namespace_is_pinned() -> None:
    """AGENT_NAMESPACE is an immutable cross-service identity contract."""
    assert AGENT_NAMESPACE == UUID("43d67b39-e156-5cfe-ba68-55c0f82fe30b")
```

**ⓑ known vector pin** — 아래 3쌍. bourbon-api `b84b328`의 `personal_agent_id`를 실제로 실행해 얻은 값이다.

```text
00000000-0000-0000-0000-000000000001 -> 2d4342c6-0ca2-5ef3-b5e4-5c6aaeb6d5e3
3f2504e0-4f89-11d3-9a0c-0305e82c3301 -> 72f0cc1c-7403-570c-bbc9-b010fa65a51c
ffffffff-ffff-ffff-ffff-ffffffffffff -> c42c2e7b-5fca-56f5-8d56-715776ee32c8
```

**ⓒ docstring 선언** — `AGENT_NAMESPACE`와 `personal_agent_id`가 **immutable cross-service identity
contract**임을 모듈/테스트 docstring에 명시. 변경하려면 ① Discovery의 복제본 동시 변경과 ② 기존
`Agent.id` 데이터 마이그레이션이 함께 필요하다는 점까지 적어 달라. 두 값이 무엇을 위해 고정돼 있는지
모르는 사람이 "테스트가 하드코딩돼 있네"라며 지우는 것을 막는 것이 목적이다.

### 수용 기준

- bourbon-api CI에서 namespace 문자열이나 포맷 문자열을 **한 글자만 바꿔도 테스트가 깨진다.**
- 깨진 테스트의 실패 메시지 또는 docstring이 "이건 cross-service 계약이니 Discovery와 같이 바꿔야 한다"를
  읽는 사람에게 알려준다.

### 대안 (요청이 거부될 경우)

Discovery가 복제를 포기하고 **service-to-service 배치 resolve 엔드포인트**(owner_id 목록 → agent_id 목록)를
요청한다. bourbon-api 쪽 신규 엔드포인트 + 인증 + Discovery 쪽 hot-path 네트워크 홉이 모두 생기므로
비용이 훨씬 크다. 두 테스트 계약(namespace pin + known vectors)과 immutable 선언이 이를 대체할 수
있다고 판단해 pin을 1순위로 요청한다.

---

## B2. 신뢰된 requester identity 전달 계약

### 현상

Discovery의 `POST /recommend`는 현재 요청자가 **누구인지 모른다.** 요청 본문은 질의·컨텍스트만 담고,
요청자 신원은 어떤 형태로도 들어오지 않는다.

### 문제 — requester self-exclusion

요청자 본인의 personal agent가 자기 자신에게 추천된다. 사용자가 어떤 주제로 질문하면, 그 주제에 대한
지식을 가진 owner 중에는 **요청자 자신**이 있을 수 있고(대개 있다 — 자기가 쓴 글이 자기 메모리에 있으므로),
Discovery는 그를 배제할 근거가 없다. 이는 real-edge turn-on의 명시적 blocker로 기록돼 있다
(Discovery spec `docs/superpowers/specs/2026-07-24-phase10-real-edge-contract-slice-design.md` §9).

Discovery가 자체적으로 해결할 수 없다. 배제하려면 **요청자의 owner_id를 알아야** 하고, 그 값은
bourbon-api가 소유한다.

### 요청

bourbon-api가 Discovery를 호출할 때 **무결성이 보장된 requester owner_id**를 전달하는 계약을 정의해 달라.

핵심 요건은 하나다 — **클라이언트가 그 값을 조작할 수 없어야 한다.**

- 값은 bourbon-api가 **자기 세션/토큰에서 파생**한 것이어야 하며, 클라이언트 요청 본문에서 그대로
  옮겨 담은 것이면 안 된다.
- 전달 채널(요청 본문 필드 / 헤더 / service-to-service 토큰 클레임)은 bourbon-api 운영 모델에 맞게
  선택해 달라. **다만 헤더라는 이유만으로 신뢰하지는 않는다** — Discovery는 그 채널이 신뢰 가능한
  근거(예: mTLS, 서명된 내부 토큰, 네트워크 경계)를 계약 문서에 함께 요구한다.
- 익명/비로그인 호출 경로가 존재한다면, **그 호출이 real-edge 추천을 사용할 수 있는지**도 함께
  정의해 달라. Discovery 측 규칙은 이미 확정돼 있다 — **production real-edge 요청에서 requester
  identity의 부재 또는 `null`은 self-exclusion no-op이 아니라 fail-loud이며, 빈 문자열은 유효하지
  않은 identity로 거부한다**(Discovery spec §9 (4)). no-op을 허용하면 identity 전달 누락이 조용히
  통과해 turn-on 안전 규칙으로 성립하지 않기 때문이다. 따라서 값이 **없음**으로 오는 것과
  **비어 있음**으로 오는 것을 계약에서 구분해 달라 — 둘 다 거부되지만 원인 진단이 달라진다.

### 수용 기준

- `/recommend` 호출에 requester owner_id가 실려 오고, 그 값이 Discovery가 신뢰할 수 있는 경로로
  왔음을 계약 문서가 설명한다.
- 클라이언트가 임의의 owner_id를 넣어 다른 사용자를 사칭할 수 없음이 테스트로 고정된다.
- 익명 호출의 표현이 명확히 정의된다(필드 부재 vs `null` vs 빈 값).
- (Discovery 측) **production real-edge 요청에 requester identity가 없으면 추천이 실행되지 않는다**는
  테스트가 고정된다 — 이건 Discovery가 맡는다.

---

## 부록 — Discovery가 bourbon-api에 **요청하지 않는** 것

혼선을 줄이기 위해 명시한다.

- **owner→agent 조회 엔드포인트** — 요청하지 않는다(B1 대안으로만 언급). 순수 파생을 복제하는 편이
  hot path에 유리하며, B1의 pin으로 안전성을 확보한다.
- **탈퇴/비활성 owner 필터링** — bourbon-api에 요청하지 않는다. bourbon-api는 이미
  `user_deactivated` 이벤트를 발행하고 `disable_for_user`로 agent를 비활성화한다
  (`bourbon_api/personal_agents/events.py:47-57`). 문제는 그 사실이 memory-api에 전달되지 않는다는
  점이며, 해당 요청은 memory-api 문서 **R1**에 있다. 단, R1 해결책으로 "bourbon-api가 memory-api에
  통지"가 채택되면 그때 bourbon-api 쪽 작업이 생길 수 있다.
- **agent 존재/활성 여부 조회** — 현재는 요청하지 않는다. 다만 파생은 **row의 실제 존재를 보장하지
  않으므로**(legacy 누락·부분 이관 시 파생은 성공하지만 catalog에 row가 없을 수 있다), Discovery는
  real-memory CLI E2E preflight와 최종 turn-on acceptance에서 "추천된 agent id가 실제 catalog에
  존재하는가"를 확인한다. 이 검증이 실패율을 유의미하게 드러내면 그때 별도 요청으로 올린다.
