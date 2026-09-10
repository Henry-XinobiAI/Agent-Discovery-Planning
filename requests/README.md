# 요청서 — 다른 팀·서비스에 부탁할 것을 그대로 전달할 수 있는 형태로

> `agent_discovery_events.md` §6의 묶음을 받는 곳마다 한 파일로 풀어 쓴 것(R43, 2026-09-10). 결정은 `decisions.md`에 있고, 여기는 그 결정을 상대 팀이 이해할 수 있는 문장으로 옮긴 것이다. **보내는 시점은 1차 배포가 준비될 즈음**이다 — 그 전에는 로컬 Docker와 CLI 발행으로 우리 쪽 작업을 끝낸다(`implementation_plan.md`).

| 받는 곳 | 파일 | 요약 | 보내는 순서 |
|---|---|---|---|
| 인프라 | [`infra.md`](infra.md) | PostgreSQL 인스턴스(플랫폼에 처음 — 근거 포함), DynamoDB 테이블 1개(prod terraform 시점), deferq용 Redis DB 번호, AMQP 계정 정보 | 1차 배포 2주 전 |
| bourbon-api | [`bourbon-api.md`](bourbon-api.md) | personal agent 새 필드 `discoverable` + `personal_agent_visibility_changed`(R23), 일반 이벤트 `room_created`(R46) | **묶음 안에서 가장 먼저** — 대화 시작 이벤트가 없는 기간의 대화는 소급이 안 된다. 상대 쪽 개발 기간이 필요하므로 보내는 시점이 오면 이것부터 |
| 클라이언트 | [`client.md`](client.md) | 탐색 탭이 우리 API를 직접 호출(`lang` 전달), 카드에서 대화를 시작할 때 우리 route `POST /attributions`에 보고(R47) | bourbon-api와 같이 |
| bourbon-agent | [`bourbon-agent.md`](bourbon-agent.md) | 타입 ① 호출을 새 계약(`/recommend/explicit`)으로, 요청자 = 실제 말한 사람, 카드 meta에 `recommendation_id`(R24·R47). HEXACO는 **아직 요청하지 않는다**(O20) | bourbon-api 다음 |
| bourbon-topic-api | [`bourbon-topic-api.md`](bourbon-topic-api.md) | api 프로세스 AMQP 연결 + visibility 변경 신호 발행(형태는 topic-api 선택, R48), prod 워커 replicas | bourbon-api 다음 |

**쓰는 규칙**

- 요청서는 상대 repo의 파일·함수 이름을 그대로 적는다. 우리가 코드를 읽은 날짜를 함께 적어, 상대가 "그 사이 바뀌었다"를 바로 말할 수 있게 한다.
- 이벤트 payload는 `agent_discovery_events.md` §2의 모양을 그대로 옮긴다. 두 문서가 다르면 이벤트 정의서가 맞다.
- 상대에게 결정을 넘기지 않는다. "이렇게 해 달라"와 "이 중 골라 달라"를 구분해서 적는다.
- 이벤트 요청은 플랫폼 기준(이벤트 정의서 §0: 판정 기준이 명확하고 소비자가 여럿, stateless, 단일 소비자·사후분석은 우리 안에서)에 맞는 것만 낸다. 우리만 읽는 값을 다른 서비스의 route나 이벤트에 얹지 않는다(R46·R47·R48).
- 보낸 뒤의 답과 변경은 `decisions.md`에 R로 기록하고, 여기는 보낸 문장을 그대로 남긴다(무엇을 부탁했는지에 대한 기록).
