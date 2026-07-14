# Agent Discovery & Recommendation — 동작 설명서 (시나리오 walkthrough)

> 이 문서는 **"요청이 들어와서 응답이 나갈 때까지 실제로 무슨 일이 일어나는가"** 를 쉬운 말로, 시나리오별로 따라가는 문서다.
> 정확한 필드/임계값/계약은 `agent_discovery_recommendation_build_plan.md`(이하 *build_plan*)가 source of truth이고, 여기서는 그 동작을 풀어 설명한다.
> 대상 범위는 **Alpha**(Pull 모드, for/against까지). Push·orthogonal은 마지막에 미리보기로만 다룬다.

---

## 0. 한눈에 — 이 서비스가 하는 일

**"이 주제(topic)에 대해, 이런 이유(need)로 추천할 만한 agent를 찾아서 순서대로 돌려준다."**

입력은 *주제 + 필요(need)*, 출력은 *순위가 매겨진 agent 목록*(또는 "줄 만한 게 없음=침묵"). 그게 전부다.

```
요청(RecommendRequest)
   │
   ▼
⓪ 정규화 → ① 주제를 QID로 변환 → ② 그 주제의 agent edge 모으기
   → ③ 자격 게이트 → ④ need별 순서 매기기 → ⑤ 응답 만들기 → ⑥ 기록
   │
   ▼
응답(RecommendResponse): 순위 매긴 agent 목록 + 침묵 여부 + 로그 id
```

핵심 감각 3가지(자세한 건 §6):
1. **점수(score)를 만들지 않는다.** "0.83점" 같은 스칼라는 없다. need마다 정해진 **정렬 키 순서(ordering)** 로만 줄을 세운다.
2. **주제(anchor)의 인기도(importance/pageview)는 추천 점수가 아니다.** 그건 "어느 주제인지 알아맞히는 데"만 쓴다.
3. **Alpha에서 memory-api로부터 진짜로 받는 건 "주제(anchor) 정보"뿐**이다. agent의 전문성 edge·persona·노출자격은 Alpha에선 mock(가짜 fixture)으로 채운다.

---

## 1. 요청은 어떻게 생겼나 — `RecommendRequest`

`POST /recommend` 에 이 JSON을 보낸다 (`extra=forbid` — 모르는 필드는 거부):

| 필드 | 필수 | 기본 | 뜻 |
|---|---|---|---|
| `topic_text` | ✓ | — | 찾고 싶은 주제 텍스트 (예: `"강화학습"`) |
| `need_type` | ✓ | — | 왜 찾나: `depth`/`experience`/`for`/`against`/`coverage` |
| `user_stance_ref` | | `null` | for/against일 때 "내 입장". 문법 `axis=…; dir=for|against|neutral; text=…` |
| `lang` | | `"ko"` | linker 언어 힌트 |
| `limit` | | `10` | 최대 몇 개 받을지 (1–50) |
| `context` | | `null` | 노출자격(eligibility) 판단용 호출 맥락 |

```jsonc
// 가장 단순한 요청
{ "topic_text": "강화학습", "need_type": "depth", "lang": "ko", "limit": 5 }
```

**need_type 5종을 한 줄로:**
- `depth` — 이 주제를 **깊이 아는** agent
- `experience` — 이 주제를 **직접 해본** agent (지식만 많은 게 아니라)
- `for` — 내 입장을 **같이 지지하는** agent
- `against` — 내 입장에 **반대하는** agent (일부러 반대 관점)
- `coverage` — 한쪽으로 쏠리지 않게 **다양하게** 섞어서

---

## 2. memory-api에서 무엇을 받나 — 실제 있는 것 vs 아직 없는 것

이 절은 **"우리가 memory-api에서 가져온다고 가정하는 값들"** 을 하나씩, ① 어느 단계에서 ② 어떤 endpoint로 가져오며 ③ 그게 **memory-api에 실제로 있는지**로 갈라 정리한다. 결론부터: **Alpha가 real로 받는 건 "주제(anchor) 정보"뿐**이고, 추천의 핵심 신호(agent edge/persona/eligibility)는 memory-api에 **아직 없어서** mock fixture로 채운다.
(필드·임계값의 원전은 build_plan §3.1(struct)·§3.2(신호 소비 맵). 이 절은 그 소비 맵을 "실제 memory-api 대비"로 풀어 쓴 것이다.)

### 2.1 실제로 있고 Alpha가 real로 쓰는 것 — `/knowledge/*` (anchor)

memory-api 라우터 `api/routers/knowledge/router.py` (prefix `/knowledge`)에 아래가 실재한다. Alpha 파이프라인이 실제로 호출하는 건 이 중 **2개**다(`search_candidates`·`expand_connections`). **★2026-07-14 갱신:** `/knowledge/entities/suggest` 라우트 + `EntitySuggestion` struct는 memory-api에서 **삭제됨(#87)** — grounding은 이미 search-only라 런타임 무영향이나, discovery provider의 `suggest()`/`EntitySuggestion`(providers/base·entity_http·structs/entity)는 이제 stale(code repo cleanup 필요). 또한 `GET /knowledge/entities` search가 `context=`/`types=` 파라미터를 추가로 받게 됐다(§2.2):

| 값(응답 모델) | 쓰는 단계 | endpoint (params) | 실제 존재 | Alpha가 호출? |
|---|---|---|---|---|
| 후보 검색 `Page[EntitySummary]` | ① Linker recall | `GET /knowledge/entities` (`q`,`limit`,`context`,`types`) | ✅ | ✅ `search_candidates` (현재 `context`/`types` 미전달 → 확장 예정) |
| ~~자동완성 `Page[EntitySuggestion]`~~ | autocomplete 전용(① recall 아님) | ~~`GET /knowledge/entities/suggest`~~ | ❌ **삭제됨(#87)** | ⛔ provider 메서드 stale |
| 이웃 `EntityConnections` | ② 이웃 확장(직접 edge가 희박할 때만) | `GET /knowledge/entities/{qid}/connections` (`limit`) | ✅ | ✅ `expand_connections` |
| 단건 상세 `Entity` | (계약엔 있으나 Alpha 경로 미사용) | `GET /knowledge/entities/{qid}` | ✅ | ⛔ 아직 안 부름 |
| 기사 검색 `Page[ArticleHit]` | (계약엔 있으나 Alpha 경로 미사용) | `GET /knowledge/articles` (`q`,`qid`,`lang`,`limit`) | ✅ | ⛔ 아직 안 부름 |

각 응답에서 **우리가 실제로 다루는 필드**:
- `qid` — 주제 식별자. agent edge를 join하는 열쇠(`anchor_id`)이자 응답의 `anchor.qid`.
- `label`·`description` — Linker가 "어느 주제인지" 고를 때 비교하는 텍스트 + 응답 표시. (discovery가 채점에 **실제로 읽는** 유일한 텍스트.)
- `EntityConnections`의 `broader`/`narrower`/`links_out`/`links_in` — ②에서 이웃 QID를 뽑아 풀을 넓힐 때.
- `EntitySummary`의 랭킹 신호(`importance`/`pageview`/`pagerank`/`sitelink_count`) — **응답 payload엔 담겨 오지만 discovery는 선택/추천에 쓰지 않는다.** 이미 memory-api가 서버측에서 이걸로 **후보 순서**를 정해 보냈기 때문(§2.2). 우리는 그 순서만 결정적 tie-break로 받는다(D2).
- `Page[T]{items,limit,truncated}` — list 응답 봉투. provider가 `.items`만 꺼내고 봉투(limit/truncated)는 버린다.

> **주의 — 흔한 오해 3개(실제 코드 기준 정정):**
> 1. `aliases`·`labels`(다국어 표기)는 **full `Entity`에만** 있고 `EntitySummary` 투영엔 없다. 즉 별칭은 memory-api **서버 안에서** 검색 recall을 높이는 데 쓰일 뿐, discovery 쪽엔 **별칭 목록이 넘어오지 않는다**.
> 2. 이웃 확장은 `Entity.linked_qids`(역시 full Entity 필드)가 아니라 **`/connections` endpoint**로 한다. Alpha는 full `Entity`를 안 부르므로 `linked_qids`를 직접 보지 않는다.
> 3. `importance`가 후보 순서에 미치는 영향은 **memory-api 서버측**에서 일어난다(§2.2). discovery의 Linker 자신은 popularity를 **전혀 안 읽고** symbolic label-match confidence로만 채점한다(D2).

**우리가 직접 계산하는 것**(memory-api가 안 줌): **linker confidence / margin** — "이 주제로 확정해도 되나?"를 판단하는 채택 게이트(시나리오 A ①). Alpha의 채택 코어는 deterministic symbolic confidence다(exact-label symbolic core가 기본). LLM rerank는 Phase 8A에서 **폴백**으로 이미 shipped됐다 — ambiguity(모호) 시 rung ②로만 뜨고, 평상시엔 symbolic core가 그대로 결정한다(build_plan §4①).

### 2.2 그 anchor 값들은 memory-api 안에서 어떻게 만들어지나

`/knowledge/*`가 주는 값은 **오프라인 빌드 파이프라인**의 산출물이다(런타임 계산이 아님). Wikidata 덤프 → 단계별 enrich → OpenSearch 색인:

```
Wikidata 덤프 ─▶ import(entities, sitelink_count) ─▶ closure(subclass 폐포)
   ─▶ enrich: corpus(abstract) · pageviews · links(pagerank + linked_qids) · surface(aliases + categories)
   ─▶ importance(마지막에 blend) ─▶ OpenSearch 색인 (qid = 문서 _id, 재색인 멱등)
```

주요 필드가 만들어지는 방식(`memory/knowledge/public/dump.py`·`enrich/*`·`importance.py`):

| 필드 | 출처/생성 과정 |
|---|---|
| `qid`·`label`·`labels`·`description`·`aliases` | Wikidata 엔티티에서 import 시 그대로 추출(별칭은 이후 Wikipedia redirect 제목으로 보강). |
| `instance_of`(P31)·`subclass_of`(P279)·`occupations`(P106) | Wikidata claim의 대상 qid들. |
| `sitelink_count`·`sitelinks` | 언어판 수(=notability 신호)와 `{site:title}` 맵. |
| `pageview` | 월간 조회수 합(Wikimedia REST 또는 pageview 덤프). |
| `pagerank`·`linked_qids` | `links` 단계에서 (lang,title)→QID 링크 그래프를 만들어 PageRank 실행, 상위 이웃을 `linked_qids`로 저장. |
| `abstract`·`categories` | Wikipedia 도입부 텍스트·비숨김 카테고리. |
| `importance` | **아래 blend 공식**, 코퍼스 전체 대상으로 **맨 마지막에** 오프라인 계산. |
| `fetched_at` | import 시각. |

**`importance` blend 공식**(`memory/knowledge/public/importance.py`) — 각 신호를 정규화한 가중합:

```
importance(qid) = 0.5·norm(log1p(pageview)) + 0.3·norm(pagerank) + 0.2·norm(log1p(sitelink_count))
```
(pageview·sitelink_count는 heavy-tail이라 `log1p` 압축 후, pagerank는 그대로 — 모두 코퍼스 min-max 정규화 [0,1].)

이 `importance`는 **검색 시점**에 OpenSearch `function_score`(`field_value_factor`, `modifier: ln2p`, `boost_mode: multiply`)로 텍스트 관련도를 부스트한다. 즉 `GET /knowledge/entities`가 돌려주는 **후보의 순서**가 이 popularity blend로 정해진다. discovery의 Linker는 이 순서를 **결정적 tie-break**로만 받고(D2), 그 위에 자기 symbolic confidence를 얹는다. **★2026-07-14 갱신:** 검색이 이제 `context=`(prose 필드에 `should` multi_match, boost 0.5)·`types=`(`instance_of` **positive** 필터)도 받아 그 순서를 sense 쪽으로 편향시킬 수 있다(§8-7·[11 §8-7](impl/11-phase-8-9-roadmap.md)). 그리고 **별도의 importance tie-break 신설은 §8-7에서 폐기**됐다 — context-무시 popularity prior라 저인기 의도를 오검색시키고, 어차피 backend `_score`에 이미 접혀 있어 중복. 채택은 "context-반영 backend 순서로 동점 깨기"로 가고 importance는 backend `_score` 성분으로만 관여한다.

### 2.3 아직 memory-api에 없어서 mock으로 채우는 것 (추천 신호)

추천의 **핵심 신호**는 memory-api에 **필드 자체가 존재하지 않는다**(리포 전체 grep에서 0건). 그래서 Alpha는 local/eval mock fixture로 채우고, edge의 real 연동은 **Phase 10**(user-facing Alpha의 마지막 조각)으로 간다. Alpha에서 real이 되는 건 edge뿐이고, eligibility는 allow-all stub·persona는 NullProvider로 남는다:

| 계약(provider) | 쓰는 단계 | 미래 endpoint | 필드 | memory-api 실재 |
|---|---|---|---|---|
| `AgentTopicEdge` (`get_edges`) | ② Retrieve | (미정 — §2.4 참고) | `maturity`·`evidence_strength`·`freshness`·`experience_source_type`·`experience_specificity`·`observed_stance`·`stance_axis`·`stance_summary`·`stance_confidence`·`evidence_refs`·`discoverable` | ❌ edge 필드로는 없음 (단 #64 competence vector가 투영 입력 제공 → §2.4) |
| — (agent 식별) | ②~ | — | `agent_id` | ❌ 없음(memory엔 `owner_id`만; `agent_id`는 bourbon-api `personal_agent_id`로 **downstream 파생**) |
| `PersonaPrior` (`get_prior`) | ③ Gate에서 fetch → ④ Rank에서 소비(보조) | (미정) | `prior_stance`·`stable_traits`·`expertise_claims` | ❌ 개념 자체 없음 |
| `Eligibility` (`check`) | ③ Gate | (미정) | `discoverable`·(향후 `privacy_clearance`/`safety_verdict`) | ❌ 개념 자체 없음 |

> **`discoverable`가 두 번 나오는 건 오타가 아니다 — 서로 다른 두 플래그다:**
> - `AgentTopicEdge.discoverable`(privacy-owned) — **이 주제-edge 하나**의 노출 여부. "이 agent가 이 주제에 대해선 공개 안 함"을 표현(edge 단위). 시나리오 A에서 a_20을 떨군 게 이쪽이다.
> - `Eligibility.discoverable` — **agent 자체**를 애초에 surface해도 되는가(agent 단위 자격 판정). Alpha에서 유일하게 active인 eligibility 필드.
> ③ Gate는 이 **둘 다** 통과해야 후보를 살린다(어느 하나라도 `False`면 탈락).

> 즉 Alpha는 **"진짜 주제(anchor) 위에 가짜 agent edge를 얹어" 동작을 검증**한다. 배포본에서 이 real 의존이 아직 없으면 edge/eligibility는 **503을 정직하게** 낸다(시나리오 G). persona만 예외로 `None`을 돌려주고 진행한다(보조 신호).

### 2.4 가장 가까운 실제 소스, 그리고 왜 그대로는 못 쓰나 (edge)

memory-api에서 agent-edge에 **가장 가까운 실재 소스**는 personal graph의 grounding이고, **★2026-07-14 감사 기준 그 소스가 상당히 자라났다**(#64 competence vector):

- `GET /personal/groundings/{qid}?owner_ids=…`(생략 시 **전 owner**) → `Page[GroundingMatch]{ owner_id, entity: PersonalEntitySummary }` — "이 QID에 grounding된 owner들"을 **cross-owner로** 준다.
- 실제로 주는 신호: grounding `confidence`/`margin`/`method`/`depth`, entity `salience`, 그리고 **#64 competence vector** — `Competence{frequency, breadth, depth, consistency, sentiment + depth/consistency_rationale, aspects_covered, open_questions, persona_blurb, support_ids}` + Tier-2(`degree`=centrality, `hands_on_ratio`=경험/실무 비중, `last_seen`, `opinion_ratio`). 커밋(`8092bc3`)이 이를 명시적으로 "salience-orthogonal expertise axis **for Discovery**"라 부른다.

**그래서 Phase 10은 "edge를 새로 만들어달라"가 아니라 "이 신호를 `AgentTopicEdge`로 투영하는 계약 + translation layer"다** (2026-07-14 감사로 재정의 — §2.3 표의 "❌ 전부 없음"은 이제 부분적으로만 참):
1. **매핑 가능(직접 대체는 아님·translation layer 입력):** maturity←`depth`(+breadth+consistency), evidence_strength←`support_ids` 수+confidence+consistency/frequency, experience_source_type/specificity←`hands_on_ratio`(**strong candidate**이지 1:1 아님 — `StatementKind.EXPERIENTIAL/PROCEDURAL` 원자료 필요), freshness←`last_seen`(now−last_seen decay/normalize transform), coverage/reason 재료←`breadth`/`aspects_covered`/`persona_blurb`.
2. **agent 식별은 갭 아님:** `owner_id`가 오므로 bourbon-api가 `personal_agent_id`로 파생(rec-signal owner_id-only 계약 그대로).
3. **진짜 남은 갭:** ⓐ eligibility(discoverable/privacy/safety) ⓑ stance axis/dir/confidence(`sentiment`만 있고 축이 아님) ⓒ `support_ids`(UUID)의 외부 노출·dereference 계약 ⓓ query-time relevance `_score` projection(tie margin용·`EntitySummary` 필드 불변). 대부분 discovery·bourbon-api·persona 몫.

→ 결론: 이름만 매핑하면 되는 게 아니라 **competence→edge translation layer + Discovery edge projection(eligibility·stance)**이 필요하다. 그래서 edge의 real 연동은 **Phase 10**(user-facing Alpha) 스코프이고, 그때까지 Alpha는 mock으로 둔다. (eligibility는 Phase 10에서도 allow-all stub, persona는 NullProvider로 남고 — real이 되는 건 edge뿐이다.)

---

## 3. 처리 6단계 (모든 시나리오 공통 골격)

| 단계 | 이름 | 한 줄 설명 | 쓰는 provider |
|---|---|---|---|
| ⓪ | normalize | 요청을 내부 형태로. `user_stance_ref` 문자열 → `{axis,dir,text}` | — |
| ① | **Linker** | 주제 텍스트 → **QID 하나로 확정**. 못 풀면 여기서 422 | anchor (real) |
| ② | Retrieve | 그 QID에 달린 **agent edge 모으기** (희박하면 이웃으로 확장) | edge (Alpha=mock) + anchor/connections (real, 이웃 확장 시) |
| ③ | **Gate** | 자격 미달 agent를 **떨군다**[^disc] (점수 깎기 ❌, 통과/탈락 ⭕). 생존자엔 persona도 여기서 fetch해 bind | eligibility + persona (mock) |
| ④ | **Rank** | need별 **정렬 키 순서**로 줄 세움 (스칼라 점수 없음) | persona (③에서 bound, 보조 신호) |
| ⑤ | Serve | 응답 payload 만들기 + 침묵 판정 | — |
| ⑥ | Log | 입력·중간값·탈락 이유 전부 기록 (나중에 평가용) | — |

이 골격은 **모든 need, 모든 시나리오가 동일**하다. need에 따라 바뀌는 건 ③ gate의 일부 필터와 ④ rank의 정렬 키뿐이다.

[^disc]: ③ Gate가 검사하는 `discoverable`은 **별개의 두 플래그**다 — [`AgentTopicEdge.discoverable`](#23-아직-memory-api에-없어서-mock으로-채우는-것-추천-신호)(edge 단위 노출) + [`Eligibility.discoverable`](#23-아직-memory-api에-없어서-mock으로-채우는-것-추천-신호)(agent 단위 자격). 어느 하나라도 `False`면 탈락한다. 자세히는 **§2.3의 discoverable 박스** 참고.

---

## 4. 응답은 어떻게 생겼나 — `RecommendResponse`

```jsonc
{
  "anchor": { "qid": "Q176789", "label": "강화학습" },   // ①에서 확정한 주제
  "need_type": "depth",
  "recommendations": [
    { "agent_id": "a_07", "rank": 1,                      // ★ score 없음, rank만
      "reasons": ["maturity 0.91·evidence 0.85"],
      "evidence_refs": ["msg:..."] }
  ],
  "silence": { "silent": false, "reason": null },         // "줄 게 없어서 침묵"인지
  "decision_log_id": "dl_8f2a"                             // ⑥ 로그와 연결
}
```

에러는 3가지뿐:

| code | status | 언제 |
|---|---|---|
| `grounding_failed` | 422 | 주제를 QID로 못 풀거나 확신이 부족 (①) |
| `invalid_need` | 422 | for/against인데 `user_stance_ref`가 없음/파싱 실패 |
| `upstream_unavailable` | 503 | memory-api 호출 실패, 또는 edge/eligibility real 미연동 |

> **"0개"의 두 가지를 구분한다:** 주제를 못 풀어서 0 → **422 에러**(추천 자체가 성립 안 함). 주제는 풀었는데 줄 agent가 0 → **200 + 빈 목록 + 침묵**(정상 결정). (시나리오 E vs F)

---

## 5. 시나리오별 walkthrough

> 아래 모든 edge 숫자는 **Alpha mock fixture 예시값**이다(memory-api가 주는 게 아님). band 기준: `high≥0.75, medium≥0.50, low<0.50`. gate maturity 최소 = `0.45`. for/against 신뢰도 최소 `τ=0.60`.

---

### 시나리오 A — `depth`: "강화학습 잘 아는 agent" (풀 트레이스, 기본형)

**요청**
```jsonc
{ "topic_text": "강화학습", "need_type": "depth", "lang": "ko", "limit": 5 }
```

**⓪ normalize** — need=`depth`, stance 없음. 끝.

**① Linker (topic → QID)**
- `search_candidates("강화학습")` → 후보(search-only):
  - `Q176789` "강화학습" — 정규화 label == query → exact-label match, confidence **1.0**
  - `Q2539` "기계학습" (상위개념, 비슷해 보임) — non-exact, confidence **0.55**
- `margin = top1 − top2 = 1.0 − 0.55 = 0.45`
- 채택 게이트: top이 exact-label match(`1.0`) ✓ 그리고 `margin 0.45 ≥ 0.15` ✓ → **`Q176789` 확정**.

**② Retrieve** — `get_edges("Q176789")` 로 이 주제에 달린 agent edge를 모은다 (Alpha=mock):

| agent | maturity | evidence | freshness | discoverable |
|---|---|---|---|---|
| a_07 | 0.91 (high) | 0.85 | 0.70 | ✓ |
| a_03 | 0.62 (medium) | 0.90 | 0.60 | ✓ |
| a_11 | 0.30 (low) | 0.95 | 0.80 | ✓ |
| a_20 | 0.80 (high) | 0.70 | 0.50 | ✗ |

**③ Gate** — `maturity ≥ 0.45 ∧ discoverable ∧ on_topic`:
- a_11 탈락 (maturity 0.30 < 0.45) — evidence가 아무리 높아도 **게이트는 못 넘음**.
- a_20 탈락 (discoverable=✗).
- 생존: **a_07, a_03**.

**④ Rank (depth)** — 정렬 키: `maturity_band → evidence_strength → freshness → agent_id`
- a_07: band=high(2), a_03: band=medium(1) → **밴드가 1차 키라 a_07이 먼저**.
- (a_03의 evidence 0.90 > a_07의 0.85지만, 밴드에서 이미 갈렸으므로 evidence는 보지 않는다.)
- 결과: **rank1 = a_07, rank2 = a_03**.

**⑤ Serve & ⑥ Log**
```jsonc
{
  "anchor": { "qid": "Q176789", "label": "강화학습" },
  "need_type": "depth",
  "recommendations": [
    { "agent_id": "a_07", "rank": 1,
      "reasons": ["maturity 0.91(high)·evidence 0.85"] },
    { "agent_id": "a_03", "rank": 2,
      "reasons": ["maturity 0.62(medium)·evidence 0.90"] }
  ],
  "silence": { "silent": false, "reason": null },
  "decision_log_id": "dl_8f2a"
}
```
로그에는 a_11(maturity)·a_20(discoverable) **탈락 이유까지** 남는다.

---

### 시나리오 B — `experience`: "강화학습 직접 해본 agent" (depth와 뭐가 다른가)

**요청** — 시나리오 A와 주제는 같고 `need_type`만 다르다:
```jsonc
{ "topic_text": "강화학습", "need_type": "experience", "limit": 5 }
```

①②③은 A와 동일하게 흐른다. 차이는 **④ Rank의 정렬 키**다. experience는 *직접 경험 근거*를 앞세운다:

`experience_source_rank → experience_specificity_rank → evidence_strength → freshness → maturity_band → agent_id`

같은 생존 후보를 experience 신호로 다시 보면 (mock):

| agent | experience_source_type | source_rank | specificity | maturity |
|---|---|---|---|---|
| a_07 | `None` (추상 지식만) | 0 | — (None→0.0) | 0.91 (high) |
| a_03 | `firsthand` (직접 함) | 2 | 0.70 | 0.62 (medium) |
| a_15 | `secondhand` (전해 들음) | 1 | 0.50 | 0.80 (high) |

정렬: `source_rank`가 1차 키 → **a_03(2) > a_15(1) > a_07(0)**.

> **포인트:** depth에서 1등이던 **a_07이 experience에선 꼴찌**가 된다. "근거 많은 expert"(a_07)와 "직접 겪은 agent"(a_03)를 구분하려고 experience need는 `experience_source_type`을 1차 키로 쓰기 때문이다. `None`(직접 경험 없음=추상 지식)은 rank 0이라 자연히 뒤로 밀린다 — 별도 필터 없이 순서로만 표현한다.

---

### 시나리오 C — `for` / `against`: "내 입장과 같은/반대인 agent"

**요청** (`for`)
```jsonc
{ "topic_text": "원자력 발전", "need_type": "for",
  "user_stance_ref": "axis=원자력 확대; dir=for", "limit": 5 }
```

**⓪ normalize** — `user_stance_ref` 문자열을 `{axis:"원자력 확대", dir:"for"}`로 파싱.
(만약 for/against인데 이 값이 없거나 파싱 실패면 → **`invalid_need` 422**, 파이프라인 진입 전.)

①② 진행 후, **④ Rank에 *필터*가 추가**된다. for/against는 **상대 need**라 요구 방향이 user_stance 기준으로 정해진다. `for`의 정렬 전 필터(이 예시는 `user_stance.dir=for`):
`same_axis ∧ observed_stance = user_stance.dir(=for) ∧ stance_confidence ≥ 0.60`

이 주제 edge들 (mock):

| agent | stance_axis | observed_stance | stance_confidence | maturity | for 후보? |
|---|---|---|---|---|---|
| a_31 | 원자력 확대 | `for` | 0.82 | 0.88 (high) | ✅ |
| a_44 | 원자력 확대 | `for` | 0.41 | 0.90 (high) | ❌ 신뢰도 < 0.60 |
| a_52 | 원자력 확대 | `against` | 0.90 | 0.85 (high) | ❌ 반대 입장 |
| a_60 | 탈원전 속도 | `for` | 0.75 | 0.80 (high) | ❌ 다른 축(axis) |

→ 필터 통과는 **a_31 하나**. 통과한 것끼리는 `maturity_band → evidence → freshness → stance_confidence → agent_id`로 정렬.

> **포인트 (expertise-primary):** stance가 안 맞으면 **점수를 깎는 게 아니라 후보집합에서 빠진다**(hard filter). 그리고 통과한 뒤의 1순위는 `stance_confidence`가 아니라 **maturity(전문성)** 다 — "입장만 같고 잘 모르는 agent"가 위로 오지 않게. **`for`는 `observed_stance = user_stance.dir`, `against`는 `observed_stance = opposite(user_stance.dir)`를 요구한다** — 절대값(`for`/`against`)이 아니라 유저 입장 대비 상대 방향이다. 위 예시는 `user_stance.dir=for`라 우연히 `observed_stance=for`와 일치할 뿐, 유저가 `dir=against`면 요구 방향도 뒤집힌다.

---

### 시나리오 D — `coverage`: "한쪽으로 쏠리지 말고 다양하게"

**요청**
```jsonc
{ "topic_text": "기후 정책", "need_type": "coverage", "limit": 6 }
```

①②③ 동일. **④ Rank**는 생존 agent를 **축/출처/클러스터로 그룹핑한 뒤 round-robin**으로 한 명씩 번갈아 뽑는다(그룹 내부는 maturity_band→evidence→freshness→agent_id 순):

```
그룹 A(찬성 축)   : a_31, a_07
그룹 B(반대 축)   : a_52, a_19
그룹 C(경제 관점) : a_88
→ round-robin: a_31(A) → a_52(B) → a_88(C) → a_07(A) → a_19(B) → …
```

한 그룹이 목록을 독점하지 않게 **번갈아** 뽑는 게 핵심. (MMR/DPP 같은 정교한 다양화는 Open Beta; Alpha는 round-robin dedupe.)

---

### 시나리오 E — 주제를 못 찾음 → `grounding_failed` 422

**요청**
```jsonc
{ "topic_text": "asdf 뭐시기", "need_type": "depth" }
```

**① Linker:**
- 후보가 아예 안 나오거나,
- 동음이의로 후보 둘이 비슷하게 떠서 **margin이 부족**한 경우 (예: `Q1` conf 0.55 vs `Q2` conf 0.52 → margin 0.03 < 0.15) — 어느 주제인지 **확신할 수 없으니 일부러 확정하지 않는다**.

→ `grounding_failed` **422**. (잘못된 주제로 엉뚱한 agent를 추천하느니 실패를 알린다.) 이후 단계는 실행되지 않는다.

---

### 시나리오 F — 주제는 풀렸는데 줄 agent가 없음 → 200 + 빈 목록 + 침묵

**요청**
```jsonc
{ "topic_text": "아주 희귀한 주제", "need_type": "depth" }
```

①에서 QID는 잘 확정됐다. 그런데 ②에서 edge가 0개거나, ③ gate에서 전원 탈락(전부 maturity 미달/비공개)이면:

```jsonc
{
  "anchor": { "qid": "Q...", "label": "..." },
  "need_type": "depth",
  "recommendations": [],
  "silence": { "silent": true, "reason": "no_candidates" },
  "decision_log_id": "dl_..."
}
```

→ **에러가 아니다(200).** "줄 만한 게 없으면 침묵하는 것"도 정상 결정이고, 로그에는 누가 왜 탈락했는지 남는다. (E와의 차이: E는 *주제 자체*를 못 풀어서 422.)

---

### 시나리오 G — 아직 연동 안 된 의존 → `upstream_unavailable` 503

**상황:** Alpha **배포본**은 edge/eligibility의 real 구현이 아직 없다. 이때:
- ① anchor grounding은 real이라 **정상 동작**(주제는 풀림).
- ② edge를 부르는 순간 `UnavailableEdgeProvider`가 **503 `upstream_unavailable`**.

> 일부러 이렇게 한다 — mock으로 가짜 후보를 만들어 내보내느니, **"아직 그 의존이 없다"를 정직하게** 알린다. 단, **persona는 예외**: 없어도 503이 아니라 `NullPersonaProvider`가 `None`을 돌려주고 추천은 계속된다(persona는 보조 신호라). 후보까지 도는 end-to-end는 로컬/eval(mock 주입)에서 검증한다.

---

### 시나리오 H — Push 모드 (Open Beta 미리보기, Alpha는 shadow만)

지금까지는 전부 **Pull**(유저/스킬이 직접 `/recommend` 호출)이다. **Push**는:
- **moderation/runtime 훅**이 대화 흐름에서 "지금 추천이 필요하다"를 감지해 **typed request를 대신 만들어** 같은 `/recommend`를 부른다 (Discovery가 대화를 직접 엿보지 않는다).
- 핵심은 **침묵**: 추천이 약하면 끼어들지 않고 `silence.silent=true`로 조용히 있는다. 이 임계(silence threshold)는 요청 입력이 아니라 **서버측 serving 정책**이다.

**엔드포인트는 똑같이 하나**다(평행 엔드포인트 없음). Alpha에서 Push는 노출하지 않고 **shadow**로만 돈다(같은 파이프라인을 태워 "이 시점에 추천/침묵했을 것"을 로깅). Open Beta에서 요청 DTO에 push 전용 필드(`anchor_hint`, `need_confidence`, `context_safety_verdict` 등)를 **additive하게** 더한다.

---

## 6. 꼭 기억할 약속 (gotchas)

1. **스칼라 점수가 없다.** need마다 정해진 **정렬 키 순서**로만 줄 세운다. "왜 이 순서?"는 로그의 `ordering_keys`+raw feature로 설명된다.
2. **주제(anchor)의 인기도는 추천 신호가 아니다.** `importance`/`pageview`는 "어느 주제인지 알아맞히기"에만 쓰고, agent 추천 순서에는 절대 안 들어간다.
3. **safety/privacy/maturity는 게이트지 가중치가 아니다.** 통과 아니면 탈락. 점수로 trade-off하지 않는다. (Alpha에서 safety는 inactive, discoverable만 active.)
4. **stance(for/against)는 hard filter다.** 안 맞으면 빠진다. 통과 후 1순위는 전문성(maturity), stance_confidence는 신뢰도 guard + 막판 tie-break.
5. **Alpha의 추천 신호(edge/persona/eligibility)는 mock**이다. 진짜 추천 품질이 아니라 **동작·회귀(regression)** 를 검증한다. edge의 real 연동은 **Phase 10**(user-facing Alpha; persona=Null·eligibility=stub 유지), 실사용 품질 평가는 Open Beta.
6. **422 vs 200(빈 목록):** 주제를 못 풀면 422(에러), 주제는 풀었는데 줄 게 없으면 200+침묵(정상).

---

### 더 깊이
- 필드·임계값·정렬 키 정의: *build_plan* §3.1(struct)·§4.1(API)·§4.2(ordering)·§4.3(decision-log)
- memory-api 신호 소비 맵: *build_plan* §3.2
- need별 의미의 원전: `agent_discovery_recommendation_directions.md` §2.3·§5
- 평가/시나리오 코퍼스가 이 동작들을 어떻게 검증하는지: *build_plan* §8
