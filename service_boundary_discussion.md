# 서비스 경계 — topic-api ↔ agent-discovery 논의 기록 (rev 2, 2026-08-27)

> **문서 지위: 결정이 아니다.** 2026-08-26 dev 배포 공유 직후 슬랙에서 나온 경계 문제 제기와, 그에
> 답하기 위해 **코드에서 확인한 사실**, 그리고 이 논의에 따라 **바뀔 수 있는 방향**을 임시로 모아 둔
> 것이다. 어떤 계약도 이 문서로 바뀌지 않았고 어떤 코드도 이 문서를 근거로 바뀌지 않았다.
> **설계 정본은 `recommendation_pipeline_design.md`**이며, 이 문서가 정본과 어긋나면 정본이 맞다.
> 결정이 생기면 그때 정본 §S1·§S2·§9(열린 결정)로 올리고 이 문서는 그 결정을 가리키는 기록으로 남긴다.
>
> **표기**: `사실`(상류 소스에서 `file:line`으로 확인) · `판단`(이 문서의 의견) · `열린 항목`(협의·측정 대기).
>
> **자매 문서**: `facets_ownership_split_discussion.md`(rev 3) — 같은 경계의 *값 소유* 쪽 절반이다.
> 이 문서는 *해석과 순위 정책* 쪽 절반을 다룬다. §4-2에서 둘이 만난다.
>
> `recsys_serving_discussion.md`(rev 1) — 피드백 루프 기반 추천. **그 문서 §6-3이 §3의 경계 규칙과
> 같은 방향으로 SB1에 답을 준다**: 토픽 축 학습이 피드백 루프를 필요로 하고 루프는 우리가 가지므로
> "자연어+맥락 → 토픽"은 우리 몫이 된다. 결정은 아니다 — 그 문서도 결정 아님이다.

---

## §1 논의의 발단

2026-08-26 agent-discovery dev 배포를 슬랙에 공유한 뒤, `bourbon-agent`를 작업하는 팀원이 제기한 것.
요지는 세 개다.

1. 파이프라인을 `자연어 쿼리+맥락 -(llm)-> 토픽 하나 -(topic api)-> 에이전트 목록 -(?)-> 추천할 에이전트 목록`
   으로 요약했을 때, **에이전트 목록은 전부 가져오는가 아니면 topic-api에서 필터링하는가**.
2. **에이전트 목록에서 추천할 에이전트는 어떤 방법으로 추리는가**.
3. **경계 주장** — 에이전트 목록의 필터링·랭킹은 추천 쪽에 들어가야 하고, 오히려
   `자연어 + 맥락 -> 토픽`은 topic-api에 들어가는 게 좋아 보인다. 마이크로서비스 간 역할이 더
   명확해져야 한다.

1·2는 사실 질문이므로 답으로 닫힌다(§2-7). 이 문서의 본체는 3이다.

---

## §2 사실 — 코드에서 확인한 것

이 절이 이 문서의 본체다. 판단이 바뀌어도 여기는 남는다.
(`bourbon-topic-api` HEAD `9ee67f3`, `bourbon-memory-api` HEAD `454305d`,
`bourbon-agent-discovery-api` HEAD `cfa4c59` 기준, 2026-08-26 확인)

### 2-1 `사실` topic-api의 이름 검색은 어휘 매칭이고 의미 검색이 아니다

`normalize_search_text`(`topic/catalog/graph.py:61-69`) docstring — *"Phase 1 has no morphological
analysis; a name search is substring matching over normalized labels and aliases."*
`TopicGraph.find_by_name`(`:318-343`)은 label/alias를 exact → word-start → substring 3단계와
label/alias 2단계로 티어링해 정렬한다(`:72-77`). 임베딩도 형태소 분석도 동의어 사전도 없다.

→ 팀원 지적 중 **이 부분은 맞다**. 의미가 가까운 다른 표현은 지금 구조로 못 찾는다.

### 2-2 `사실` memory-api는 "호출하는 쪽이 검색어를 만든다"를 계약으로 갖고 있다

`POST /knowledge/entities/search`의 body가 `queries: list[str]`(1–16개, 각 200자 이하)이고
(`api/routers/knowledge/structs.py:25-29`), `fanout`은 쿼리별로 따로 검색해 유니크 결과를 병합하는
스위치다(`:30-36`). 병합은 per-query 랭크를 라운드로빈으로 섞는다(`memory/search/fanout.py:35-46`).
`api/routers/personal/structs.py:31-36`의 공유 `queries` 필드도 같은 모양이고,
`api/routers/knowledge/structs.py:45`의 Swagger 예시 주석은 multi-query cross-fanout을
**"the sense-disambiguation path"**라고 부른다.

→ **자연어를 검색어로 펼치는 일은 이미 소비자 쪽에 있다.** agent가 memory-api를 그렇게 쓰고 있고,
agent-discovery ↔ topic-api는 같은 모양을 따른 것이다. 여기만 반대로 가면 두 서비스에 서로 다른
기준이 생긴다.

### 2-3 `사실` topic-api는 이미 LLM을 쓰지만 요청 경로에는 없다

`cli/persona_topics/stages.py:17`이 `cli.llm.structured_completion`을 import하고 `:128`·`:156`에서
호출한다(persona → topic 추출). catalog import triage도 같은 계열이다. 반면 serving 경로
(`api/`, `topic/`)에는 LLM 호출이 없다.

→ **"요청 경로는 결정적 색인 읽기로 유지한다"는 선을 topic-api 저자들이 스스로 그어두고 있다.**
`/search/topics`에 LLM 판단을 넣자는 제안은 그 불변식을 깨자는 제안이 된다.

### 2-4 `사실` internal 검색은 public 검색과 코드를 공유한다

`api/routers/internal/search/router.py:1` — *"The same two searches the public surface answers, for a
service in the cluster."* 두 라우터가 같은 `api/routers/search/queries.py`(`found_topics`,
`ranked_users_by_name`)를 쓰고, public 쪽은 edge-auth로 viewer 신원을 받는다
(`api/routers/search/router.py:32-40`의 `viewer_id: ViewerId`). 마운트는 같은 sub-path를
prefix로만 가른다(`api/main.py:222-226`).

→ 검색 경로에 "모호하면 하나로 확정한다"를 박으면 **유저가 직접 쓰는 검색에도 같이 걸린다.**
그쪽은 모호할 때 후보를 보여주는 게 맞으므로, 하나로 박으면 둘 중 하나는 틀린다.

### 2-5 `사실` "이름 → 유저 랭킹" route는 이미 있고, 동음이의를 합친다

`GET /search/users`(internal: `api/routers/internal/search/router.py:29-33`)의 docstring이
*"Users ranked over every topic whose name or alias matches q"*다. `find_by_name`이 돌려준
**모든** 매칭 토픽에 걸쳐 유저를 랭킹한다.

→ 즉 "이름 주면 유저 랭킹 준다"는 이미 topic-api에 있다. agent-discovery가 그걸 쓰지 않는 이유가
이 층의 존재 이유다: 같은 이름의 다른 주제 보유자가 한 랭킹에 섞인다. 추천은 그 둘을 합치면 안 된다.

### 2-6 `사실` topic-api의 internal 소비자는 현재 agent-discovery 단독이다

`bourbon/` 하위 전 repo에서 `api/internal/svc/topic`을 참조하는 코드는 agent-discovery뿐이고
(`agent_discovery/config.py`, `providers/topic_api/transport.py`), `bourbon-api`는 게이트웨이
dispatch 매니페스트만 갖는다(`k8s/base/api-svc-dispatch.yaml`).

→ **이 사실은 우리 논지 하나를 무효로 만든다.** §3-6 참조.

### 2-7 `사실` 질문 1·2의 답 (현재 구현)

- **목록을 전부 가져오지 않는다.** `GET /topics/{id}/users`를 `visibility=public`(기본 tier,
  `providers/topic_api/client.py:63`)과 `limit=100`(그들의 상한, `:55`)으로 호출한다. 보유자 한정·
  공개범위 필터·랭킹이 모두 topic-api 쪽에서 끝나고, 우리는 그 페이지를 받는다. 페이징은 없다.
- **추리는 방법**: 해석(concept group)이 여럿이면 rank 기반 RRF로 융합
  (`stages/merge.py:26`, `RRF_K=60`) → 요청자 self-exclusion → 불완전 근거(stub pair) 제외 →
  eligibility(현재 allow-all, seam만) → `user_id` 결정적 tiebreak → 상위 n
  (`stages/ordering.py:44-56`). 우리 score는 응답에 나가지 않는다.
- **순위 정책은 아직 실체가 없다.** primary key가 slot으로 비어 있고 기본 전략은 융합 점수만 읽는다
  (`stages/ordering.py:1-12`, `:32-40`) — facets 계약이 열려 있고 상류 값이 dummy라서 지금 식을
  고정하면 생성기에 맞추는 셈이 되기 때문이다.
- **차순위(커버 가능한 대체) 추천은 미구현이다.** 설계 의도만 있고 새 repo에는 단계가 없다.

---

## §3 `판단` 경계를 어디에 긋는가

규칙 한 줄로 쓰면: **데이터를 소유한 쪽이 사실과 그 위의 검색 프리미티브를 갖고, 호출하는 쪽이
해석·정책·실패 계약을 갖는다.** 자연어 해석은 사실이 아니라 정책이다.

### 3-1 선례 대칭

§2-2. memory-api ↔ agent가 이미 이 규칙으로 가 있고 잘 돌고 있다. 기준을 뒤집으려면 memory-api
계약도 같이 뒤집어야 하는데 그건 아무도 제안하지 않고 있다.

### 3-2 topic-api 자신의 불변식

§2-3·§2-4. 요청 경로에 LLM이 없고, 그 경로는 유저 대면 라우트와 코드를 공유한다.

### 3-3 동음이의를 접지 않는 것이 이 층이다

§2-5. 그리고 확정에 실패했을 때 무엇이 정답인지가 호출하는 쪽마다 다르다 — 추천은 실패로 답해야
하고(422 매칭 없음 / 422 모호 / 503 판단 도달 못 함, 정본 §S2) 검색 화면은 후보를 보여줘야 한다.

### 3-4 차순위 추천이 grounding과 같은 결정이다

정확히 맞는 주제의 agent가 없을 때 커버 가능한 차순위를 내는 것(§2-7의 미구현 항목)은 "하나로
확정한다"와 **같은 결정**이다. 확정을 topic-api가 하면, "정확히 맞는 게 없다"는 판정이 그쪽에서 나온
뒤 커버할 토픽을 찾기 위해 우리가 카탈로그를 다시 검색해야 한다. 하나의 결정이 서비스 두 개로
쪼개지고, 그게 바로 팀원이 걱정하는 "역할이 불명확한" 상태다.

### 3-5 평가를 가진 쪽이 knob을 가져야 한다

자연어에서 토픽을 고른 게 잘 된 건지는 "추천 결과가 좋았는가"로만 측정된다. topic-api에는 추천
eval set이 없고 만들 이유도 없다. (우리 쪽 평가 트랙은 코드 repo `tasks/todo.md` PR 7 = E0–E3.)

### 3-6 버린 논지 — "공유 서비스가 LLM 비용·장애를 갖게 되면 모든 소비자가 상속한다"

첫 답변 초안에서 이걸 첫 번째 근거로 썼다가 버렸다. §2-6대로 topic-api의 internal 소비자는
agent-discovery 단독이므로 **오늘 기준 상속할 다른 소비자가 없다.** 재사용 논거로는 성립하지 않는다.
같은 취지가 성립하는 형태는 §3-2(요청 경로 불변식 + public 라우트 코드 공유)뿐이고, 그건 소비자
수와 무관하다.

★**규율: 공유 서비스를 근거로 "다른 소비자들이 비용을 상속한다"고 쓰기 전에 소비자를 센다.**
소비자가 하나면 그 논거는 상대에게 즉시 반박당하고, 같이 있던 옳은 논거의 신뢰도까지 깎는다.

---

## §4 이 논의에 따라 바뀔 수 있는 것

### 4-1 `열린 항목` topic-api에 의미론적 후보 검색을 요청한다

팀원 지적의 옳은 절반(§2-1)을 요청으로 바꾸는 것. 형태소·동의어·의미론적 후보 검색은 topic-api가
소유한 데이터 위의 **결정적 retrieval 프리미티브**이고 프롬프트도 정책도 끼지 않으므로 그쪽이 맞다.

바뀌는 것: 지금 S1 LLM 확장의 일부는 상류에 의미 검색이 없어서 하는 **보정**이다. 상류가 지원하면
확장의 폭이 줄고(비용·지연 감소) grounding recall이 오른다. 확장 자체가 사라지는 것은 아니다 —
맥락으로 동음이의를 가르는 일과 실패를 구분하는 일은 남는다(§3-3).

정리 방향: **"자연어 + 맥락 → 토픽을 topic-api에 넣자"가 아니라 "topic-api 검색을 의미론적 검색까지
확장하자"로 나눈다.** 프리미티브는 상류, 해석·실패 계약·차순위는 소비자.

미결: 요청을 발신할지, 어떤 형태(색인 방식·계약·비용 부담)로 할지. 발신 전이다.

### 4-2 `열린 항목` 순위 정책의 소유 — `facets_ownership_split_discussion.md`와 만나는 지점

팀원 지적 중 "랭킹은 추천 쪽" 부분에는 **동의한다.** 지금 topic-api 순위를 그대로 따르는 것은 위에
얹을 지표가 없기 때문이고(§2-7), 값이 확정되면 순위 정책은 agent-discovery의 ordering strategy로
들어온다 — 슬롯이 이미 비워져 있다.

여기서 두 가지를 섞지 않는다.

| 구분 | 지금 상태 | 바뀔 수 있는 방향 |
|---|---|---|
| **지표 값의 소유·저장·전달** | topic-api가 producer로부터 주입받아 내려준다 (`facets_ownership_split_discussion.md` §2-1) | 값을 producer DynamoDB로 옮기고 우리가 read-only join하는 안이 열려 있다(같은 문서 §1) |
| **그 값으로 순위를 매기는 정책** | 실체 없음 — topic-api rank를 그대로 씀 | agent-discovery가 갖는다 |

두 칸은 독립이다. 값이 어디서 오든 정책은 소비자 쪽이고, 정책이 우리 쪽이라는 것이 값을 우리가
소유해야 한다는 뜻은 아니다. **슬랙 스레드에서 이 둘을 한 문장에 섞으면 어느 한쪽에 미리 못 박히므로
분리해서 말한다.**

### 4-3 `판단` 바뀌지 않는 것

- 하나로 확정하는 결정(S2)과 실패 3분기는 소비자 쪽에 남는다(§3-3).
- 차순위 추천도 소비자 쪽이다(§3-4).
- topic-api가 소유하는 것 — 카탈로그 그래프, 멤버십, visibility, 그 위의 검색·랭킹 프리미티브 — 은
  그대로다. 우리가 가져오자는 제안은 이 문서에 없다.

### 4-4 `사실` 타이밍 — closed beta가 일주일 미만 남았다

2026-08-27 기준. 구조를 옮기는 작업은 이 일정 안에 들어갈 수 없으므로, §4-1·§4-2는 베타 이후
항목이다. 슬랙 답변도 그 선에서 닫았다: 역할을 명확히 하는 데는 동의하고, 지금 구조를 옮기긴
어렵고, 실제로 열려 있는 것은 score·평가지표 소유권이니 베타 후 그것과 같이 정리한다.

---

## §5 열린 항목 정리

| # | 항목 | 상태 |
|---|---|---|
| SB1 | topic-api에 의미론적 후보 검색 요청 (§4-1) | 미발신. 발신 여부·형태 미정 |
| SB2 | 순위 정책이 agent-discovery로 들어오는 시점 (§4-2) | facets 값 계약 확정 대기 |
| SB3 | 지표 값의 소유·저장 위치 (§4-2 표 첫 칸) | `facets_ownership_split_discussion.md`가 소유. 착수 자격은 그쪽 §7-1 |
| SB4 | 경계 규칙을 정본에 절로 올릴지 (§3의 한 줄 규칙) | 미정. 올린다면 `recommendation_pipeline_design.md` §10(구조 원칙) |
| SB5 | 차순위(커버 가능한 대체) 추천 설계 (§3-4) | 설계 의도만. 단계 미설계·미구현 |

---

## §6 이 문서가 하지 않은 것

- 코드 변경 **없음**. `bourbon-agent-discovery-api`는 `cfa4c59` 그대로다.
- 정본(`recommendation_pipeline_design.md`) 변경 **없음**. §3의 규칙을 §10으로 올리는 것은 SB4다.
- `topic_api_analysis.md` §11(열린 질문) 갱신 **없음** — SB1이 확정 요청이 되면 그때 그쪽 레지스터로.
- topic-api 팀에 **요청을 발신하지 않았다.** 슬랙 스레드에서 방향만 제안했다.
- 팀원 개인에 대한 판단은 담지 않는다. 이 문서는 경계 논지와 그 근거만 갖는다.

## 변경 이력

- **2026-08-27 rev 1** — 신설. 2026-08-26 슬랙 스레드(경계 문제 제기)와 그에 답하기 위해 확인한
  사실·판단·열린 항목을 임시 기록. §2는 세 repo(`9ee67f3`·`454305d`·`cfa4c59`)에서 `file:line`으로
  확인했다. ★규율 두 개: ⑴ §3-6 — 공유 서비스의 "다른 소비자가 비용을 상속한다"는 논거는 **소비자를
  세고 나서** 쓴다(여기선 단독이라 무효였다) ⑵ §4-2 — **값의 소유와 그 값을 쓰는 정책의 소유는 다른
  질문이다**. 한 문장에 섞으면 아직 열려 있는 쪽에 미리 못 박힌다.
- **2026-08-27 rev 2** — 자매 문서 `recsys_serving_discussion.md`(rev 1) 역참조 추가, facets 문서
  참조를 rev 3으로 갱신. 논지 변경은 없다. SB1의 상태도 그대로 "미발신"이다 — 그 문서 §6-3은 **왜**
  우리 몫인지에 대한 새 논거(피드백 루프 소유)를 주지만, 발신 여부를 바꾸지는 않는다.
