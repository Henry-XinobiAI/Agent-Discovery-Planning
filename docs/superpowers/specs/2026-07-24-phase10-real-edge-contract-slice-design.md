# Phase 10 real-edge contract slice — 설계 (competence/groundings → AgentTopicEdge)

- **상태**: PROVISIONAL / 브레인스토밍 수렴본. writing-plans 미착수, 구현 미시작. **memory-api 소스 대조 검증 완료**(2026-07-24, 병렬 adversarial 3축): endpoint/params·`Page.truncated` overfetch·`support_ids` invariant(full competence-scoring 경로 한정; schema/rescore 미강제)·one-owner/QID·필드 surface 확증. 추가 정밀화: nullable `source`/`knowledge_qid`, rescore staleness(부분변경/교체 포함), **freshness 입력(`last_seen`≠evidence recency) provisional 격하**, **dangling-link join으로 `truncated=false`≠complete**, **ownership 검사는 DTO self-consistency 한정** — 셋 다 production turn-on blocker로 §9 추가.
- **날짜**: 2026-07-24 — 2026-07-24 memory-api 소스 계약 감사(`../bourbon-memory-api`) 결과를 반영.
- **범위**: memory-api의 per-owner competence/grounding 신호를 Discovery `AgentTopicEdge`로 투영하는 **contract slice**. **dormant ship**(default-OFF). "Phase 10 완료"·"live turn-on"·"user-facing Alpha 성립"이 **아니다** — `agent_id`·eligibility가 실제 해결되기 전까지 그렇게 부를 수 없다.
- **관련**: [[discovery-phase10-real-edge-promotion]](승격 결정·2026-07-24 감사 정정), `2026-07-20-agentic-stance-retrieval-design.md`(stance는 query-time judge 소유·edge 불변), Phase 2 `HttpKnowledgeEntityProvider`(real HTTP adapter 템플릿), [[discovery-mockfirst-contract-strategy]].

---

## 1. 문제와 감사 결론

배포 `/recommend`는 grounding(real) 이후 후보 단계에서 503을 낸다 — `UnavailableEdgeProvider`/`UnavailableEligibilityProvider`(`api/depends/pipeline.py`)가 hard-required로 배선돼 있기 때문. 이를 해소하려면 real edge source가 필요하다.

**2026-07-24 소스 계약 감사**로 확정된 사실(메모리 노드의 2026-07-14 가정 일부 정정):

- **전용 `/personal/groundings/{qid}` 라우트는 없다.** grounding 정보는 entity 응답에 embed된다. cross-owner 후보 검색은 `GET /{prefix}/personal/entities/{qid}`(owner_id 생략=전 owner) → `Page[PersonalEntityMatch]`.
- **memory-api에 agent identity가 없다.** 정체성 키는 `owner_id`(UUID) 단독. `agent_id`는 상류(bourbon-api `personal_agent_id`)에서 파생 — Discovery가 파생 규칙을 복제하면 안 된다.
- **#64 competence vector**가 per-(owner, QID)로 노출된다(빌드 시 precompute·저장): `Competence{depth, consistency, frequency, breadth, sentiment, support_ids, …}` + Tier-2(`hands_on_ratio`, `opinion_ratio`, `degree`, `last_seen`). 매 `PersonalEntitySummary`에 통째로 투영된다.
- **stance axis/dir/confidence는 갭이 아니다** — for/against 재설계가 그 모델을 폐기했다. stance는 query-time live judge가 산출하며(K-task shipped), `AgentTopicEdge`의 stance 필드는 이 슬라이스에서 건드리지 않는다.
- **eligibility는 어떤 응답에도 없다**(전부 빌드타임 내부). → 진짜 갭은 eligibility 하나로 수렴한다. **dormant contract-slice 구현의 memory-api 블로커는 0**(elig=true stub·mock-first)이지만, **production turn-on은 여러 상류 계약에 blocked**(전부 §9): ① pagination/bounded-retrieval **+ join-integrity**(dangling link skip으로 `truncated=false`가 완전성 미보장, §6 ③), ② **stale-competence lifecycle**(active-set 변경/교체 시 과거 competence 잔존·`with_statements=false`로 감지 불가, §4), ③ **freshness 입력 의미**(`last_seen`이 evidence recency 아님, §4), ④ persisted link/entity ownership fold-검증(정책 ④). real eligibility/identity resolver도 선결이다.

**슬라이스 목표**: competence/grounding → `AgentTopicEdge` 투영을 **계약과 테스트로 확정**하고, default-OFF로 dormant ship한다. live 연결·real 데이터 검증은 turn-on gate로 이월한다.

## 2. 구조 — 타입 파이프라인 (isolation)

```text
PersonalEntitySummary
  → [순수 translator]                    → OwnerTopicProjection   (identity 무지)
  → [IdentityResolvingEdgeProvider]       → AgentTopicEdge          (agent_id 결합)
```

투영(순수·안정 계약)과 identity 결합(상류 의존·미해결)을 **분리**한다. resolver 부재 시 fail-loud 지점이 명확하고, 각 단을 독립 테스트할 수 있다.

### 2.1 구성요소 (5)

1. **순수 translator** — `PersonalEntitySummary → OwnerTopicProjection`. identity를 전혀 모른다. §4 매핑을 담는 순수 함수.
2. **`HttpOwnerTopicProjectionProvider`** — memory-api를 호출해 `owner_id` + 투영된 신호를 담은 `list[OwnerTopicProjection]`을 반환한다. `AgentTopicEdge`를 만들지 않는다. Phase 2 `HttpKnowledgeEntityProvider`가 HTTP 패턴 템플릿.
3. **`AllowAllEligibilityProvider`** — 항상 `Eligibility(discoverable=True)`. 이름과 `ProviderVersions.eligibility` 표기에 **stub임을 명시**. real verdict가 아니다.
4. **Composition root 배선** — default-OFF flag(`REAL_EDGE_ENABLED`) 뒤에서 `Unavailable*`를 real로 교체. `discovery/providers/base.py:56-62`의 stale `MemoryEdgeProvider` docstring(존재하지 않는 `GET /personal/groundings/{qid}` → `Page[GroundingMatch]`)을 정정.
5. **`IdentityResolvingEdgeProvider`** — raw projection provider를 감싸는 decorator. `resolve_many(owner_ids) -> Mapping[UUID, str]`(배치 계약, N+1 회피)로 `owner_id → agent_id`를 결합. **최종 `MemoryEdgeProvider.get_edges(anchor_id) -> list[AgentTopicEdge]`는 이 decorator가 구현**한다.

### 2.2 `OwnerTopicProjection` 계약

**최종 edge 생성에 필요한 필드만** 담는다(소비되지 않는 필드는 계약 부채가 되므로 제외):

```text
owner_id: UUID
anchor_id: str            # = requested QID
maturity: float           # [0,1]
evidence_strength: float  # [0,1]
freshness: float          # [0,1]
evidence_refs: list[str]  # ["statement:<uuid>", ...]
```

`hands_on_ratio` 등 raw/debug 신호는 **projection DTO에 넣지 않는다** — 원본이 memory-api 응답에 상존하므로 calibration 때 재사용 가능하고, 지금 관측이 필요하면 별도 내부 `ProjectionDiagnostics`나 structured log로 낸다.

## 3. 데이터 흐름 (`get_edges(anchor_id=QID)`)

검증은 **구조 검증을 전체 page에 먼저** 적용한 뒤에 sparse-skip한다. sparse item을 먼저 skip하면 같은 owner의 두 항목 중 하나가 `competence=None`일 때 duplicate invariant(§6 ⑤)가 숨을 수 있으므로, 순서를 아래로 pin한다:

1. `HttpOwnerTopicProjectionProvider`가 memory-api에 요청 (§5 요청 계약).
2. **page envelope/truncation 검증** (§6 ③).
3. **모든 item의 QID/source/ownership 검증** (§6 ④).
4. **전체 owner uniqueness 검증** (§6 ⑤).
5. **그 후** `competence is None` skip (§6 ①) / `competence != None ∧ support_ids==[]` fail-loud (§6 ②).
6. translator가 각 `PersonalEntitySummary` → `OwnerTopicProjection`(§4). 시그니처는 `translate(entity, *, anchor_id, now)`로 pin. `now`는 **요청당 1회** 읽어 전 projection에 동일 적용.
7. `IdentityResolvingEdgeProvider`가 projection들의 `owner_id`를 모아 `resolve_many()` 1콜 → `agent_id` 결합 → `AgentTopicEdge` 조립. 최종 edge 순서는 projection **입력 순서**를 보존(§6 ⑥).
8. edge 조립 시: stance 필드 명시적 `None`, `discoverable`는 compatibility sentinel(§7), `source_owner`는 기존 `_SOURCE_OWNER` 맵.

## 4. Translation 매핑 (lock)

```python
support_ids       = list(dict.fromkeys(competence.support_ids))   # 단일 order-preserving dedup
n                 = len(support_ids)
maturity          = depth * (MATURITY_DEPTH_BASE + MATURITY_CONSISTENCY_WEIGHT * consistency)
evidence_strength = n / (n + EVIDENCE_SATURATION_K)
age_days          = max((now - last_seen).total_seconds() / 86_400, 0.0)
freshness         = 2 ** (-age_days / FRESHNESS_HALF_LIFE_DAYS) if last_seen else 0.0
evidence_refs     = [f"statement:{sid}" for sid in support_ids]
experience_source_type = experience_specificity = None
```

**named constants**(단일 소스, magic number 금지): `MATURITY_DEPTH_BASE=0.6`, `MATURITY_CONSISTENCY_WEIGHT=0.4`, `EVIDENCE_SATURATION_K=4`, `FRESHNESS_HALF_LIFE_DAYS=90`.

**설계 근거:**

- **maturity = 곱셈** — `maturity ≤ depth`가 보장된다. consistency는 `[0.6, 1.0]` 배율의 contradiction penalty로만 작동해 얕은 depth를 구제하지 못한다. (선형 가중합 `0.6·depth + 0.4·consistency`는 `depth=0.10, consistency=1.0 → 0.46`으로 `MATURITY_MIN=0.45`를 통과시키는 구멍이 있어 기각.)
- **evidence_strength = evidence-volume proxy** — 질이 아니라 양이다(질은 maturity에 반영). `support_ids`는 dedup 후 strength와 refs가 **동일 집합**을 쓴다.
- **evidence_refs = order-preserving unique projection** — dedup을 거치므로 엄밀히는 `support_ids`의 순서 보존 유니크 투영(`["statement:<uuid>", ...]`)이다. **active/current ref라고 주장하지 않는다**(stale-competence 문제로 non-active id가 섞일 수 있음). active evidence 보장은 위 memory-api 선결조건(§9)이 닫힌 뒤에 성립한다.
- **freshness = 90일 half-life** — `2**(-age_days/90)`(e-folding 아님). `age_days`는 `total_seconds()/86400`(초 해상도; `.days`는 하루 단위 계단 decay라 기각). 미래 timestamp는 `age_days`를 0으로 clamp해 1을 넘지 않는다. `last_seen=None → 0.0`(recency 근거 없음). decay이지 hard cutoff 아님. **⚠️ 입력 의미는 provisional — production turn-on blocker(§9):** `last_seen`은 evidence recency가 아니라 GroundingLink 생성·변경 시각에 가깝고 write 경로별로 일관되지 않다(WIKIDATA 재사용 시 미갱신 `pipeline.py:875`; 신규 link만 `first_seen=last_seen=_now()`). 예: 180일 전 최초 grounding + 오늘 새 statement → last_seen 180일 전 그대로 → freshness 0.25 과소; 오래된 대화를 오늘 처음 build → last_seen=now → freshness 1.0 과대. decay 공식 자체는 맞지만 입력 신호가 성립하지 않으므로 **freshness는 확정 신호가 아니라 provisional projection으로 격하**한다.
- **experience_* = None** — `hands_on_ratio`는 experiential/procedural statement의 **비율**이지 경험의 **구체성 점수**가 아니다. `>0`만으로 FIRSTHAND를 주면 noisy 1문장이 experience ranking 최상위 tier를 얻는다. 현 신호로는 `experience_source_type`/`experience_specificity`의 의미를 정직하게 보존할 수 없으므로 방출하지 않는다. FIRSTHAND 판정 규칙과 edge 계약 개편은 calibration과 함께 turn-on gate로 이월.
- **stance 필드 None** — stance는 query-time judge가 Candidate에 채운다(edge 불변).

**stale-competence — production turn-on blocker(§9), translator에서 해결 불가:** memory-api rescore 경로(`rescore_personal_knowledge()`, `pipeline.py:2704-2718`)는 **active set이 바뀌어도** prior `depth`·`consistency`·`support_ids`를 그대로 보존하고 `frequency`·`breadth`만 재계산한다(memory-api 테스트가 `support_ids == prior_support_ids`를 명시 확인). 따라서 zero-active뿐 아니라 부분 변경·전면 교체 상황 모두에서 stale competence가 발생한다:

```text
# (a) zero-active
active statements       = 0
competence/support_ids  = 과거 값 유지

# (b) active-set 변경/교체
current active          = [new-A, new-B]
support_ids             = [old-X, old-Y]         # prior 유지
depth/consistency       = old-X/old-Y로 판정한 값  # 현재 evidence가 뒷받침하지 않음
```

이 owner는 정책 ①(`competence is None`)에도 ②(`support_ids==[]`)에도 걸리지 않고 **stale competence 전체가 추천 후보로 남는다**. `with_statements=false` 계약에서는 currentness를 검증할 정보가 없어 **Discovery가 응답만으로 감지할 수 없다**. translator는 이를 해결하지 않는다(현 payload로 신뢰성 있게 판별 불가). `with_statements=true` 우회도 권장하지 않는다 — 200 owner payload가 커지고 per-match statement cap 때문에 전체 support set의 current 여부를 증명하지 못한다. **정확한 해결책은 upstream competence lifecycle 수정**(§9)이다. 단순히 `support_ids`만 현재 IDs로 교체하는 것은 **안 된다** — 과거 evidence로 만든 `depth`를 현재 evidence가 뒷받침하는 것처럼 위장한다.

## 5. memory-api 요청 계약 (adapter)

```text
GET /{prefix}/personal/entities/{qid}?limit=200&with_statements=false&with_trace=false&sort=confidence
```

- **`owner_id`는 생략**(전 owner cross-owner). `owner_id=None` 문자열 전송 금지 — UUID validation 실패 위험.
- `limit=200`(엔드포인트 최대), `with_statements=false`, `with_trace=false`, `sort=confidence`를 요청 계약에 명시 pin(`sort`는 server default 변경 방어).
- 응답 `Page[PersonalEntityMatch]`. adapter는 memory-api wire DTO를 **미러**하고, 도메인은 `OwnerTopicProjection`만 본다(wire shape 누출 금지 — stance adapter와 동일 규율).

## 6. 검증·실패 정책 (adapter/decorator)

| # | 조건 | 정책 |
|---|---|---|
| ① | `competence is None` | **skip** owner + counter (정상: active statement 없음, **또는 아직 competence 미판정** owner — rescore는 prior competence가 없으면 active가 있어도 `None` 유지). 즉 `competence is None`이 반드시 "active 없음"을 뜻하진 않지만 skip 결론은 동일 |
| ② | `competence != None ∧ dedup(support_ids) == []` | **fail-loud** projection contract error + counter. **full competence-scoring 경로**에서는 active evidence가 있으면 `support_ids=active_ids`가 항상 채워지므로(no-active→`competence=None`, judge-disabled/failure backbone도 동일 경로) 이는 sparse가 아니라 위반이다. 단 **schema와 rescore 경로는 이를 강제하지 않으므로** 우리 fail-loud는 redundant가 아니라 정당한 cross-service 방어 |
| ③ | `response.truncated is True` (owner > 200) | **fail-loud**. partial edge 절대 반환 안 함. error에 `anchor_id` + `requested_limit=200` 포함. 현 엔드포인트에 다음-페이지 계약이 없어 partial은 silent owner-recall 상한을 만든다 → pagination/bounded-retrieval 계약 전엔 turn-on 불가. **판정은 오직 `response.truncated`** — memory-api Page는 `limit+1` overfetch로 `truncated = len(rows) > limit`를 계산하고 `ExcludeNoneRoute`가 bool을 drop하지 않아 필드가 항상 응답되므로, 결과수 == limit(정확히 200명인 정상 응답)를 실패로 보면 안 된다 (검증: `api/routers/base.py:202-213`, `router.py:486-509`). **주의: `truncated=false ⇒ complete`는 dangling-free upstream invariant 하에서만 성립** — repo가 link 201개를 join하며 entity 없는 dangling link를 조용히 skip(`repository.py:263`)한 뒤 router가 축소된 pair 수로 truncated를 계산하므로(`router.py:487`), top-201에 dangling이 있으면 유효 owner가 누락돼도 `truncated=false`가 될 수 있다 → join-integrity는 §9 blocker |
| ④ | QID mismatch / non-public grounding / ownership 불일치 | **fail-loud**. 최소 검증: `match.entity.knowledge_qid == anchor_id` ∧ `match.entity.source == GroundingSource.WIKIDATA`(값은 소문자 `"wikidata"`) ∧ `match.owner_id == match.entity.owner_id`(**응답 DTO self-consistency만** 검증 — 둘 다 `entity.owner_id`에서 파생되므로 persisted `GroundingLink.owner_id == PersonalEntity.owner_id`는 검증하지 못한다; `link.owner_id`가 응답에 미노출. persisted link ownership 검증은 memory-api가 pair fold 전에 하고 불일치 시 fail-loud해야 함 — §9). `source`/`knowledge_qid`는 **nullable**(`GroundingSource \| None` / `str \| None`)이므로 Wire DTO도 nullable로 정확히 미러링하고, **`None`·`LOCAL`·`NONE`·기타 값·qid 불일치는 전부 fail-loud**(그것이 의도 — exact-QID 조회 결과에 non-WIKIDATA·타 QID가 섞이면 구조적 위반). anchor를 요청 QID로 덮어써 복구하지 않는다 |
| ⑤ | 같은 owner가 응답에 2회 등장 | **fail-loud** (memory-api one-owner/one-QID invariant 위반, ③④와 동류) |
| ⑥ | resolver 결과가 exact mapping이 아님 | **fail-loud** `UnresolvedOwnerIdentityError`. `set(resolved) == set(requested_owner_ids)` 강제 — **누락(`requested − resolved ≠ ∅`)과 불필요한 extra key 모두 거부**. 서로 다른 owner가 **동일 agent_id로 resolve되면** fail-loud. 최종 edge 순서는 batch mapping의 iteration order와 무관하게 **projection 입력 순서를 보존**. 단순 Mapping 계약에서 silent skip은 resolver 장애와 정상 미등록을 구분 못 한다 — "agent 없는 owner는 정상 제외" 계약이 생기면 resolver 반환타입을 resolved/unmapped로 확장(이월) |

**구분 원칙**: ①만 정상 발생 가능한 per-owner 데이터 조건이라 skip. ②–⑥은 구조적/계약 위반이라 fail-loud. wire DTO는 `truncated`를 **required**로 두고 `response.limit == 200` ∧ `len(items) <= 200`도 검증. 정책 ④ wire 필드 존재 확인: `PersonalEntityMatch.owner_id`, `.entity.owner_id`, `.entity.knowledge_qid`, `.entity.source`.

## 7. eligibility stub과 안전 불변식

`AllowAllEligibilityProvider`는 **contract-test/dev 전용**이며 eligibility-first 보안 불변식을 만족하는 real 구현이 아니다. `discoverable`은 translator가 만들지 않고(memory projection에 privacy 신호 없음), 최종 edge 조립 시 **compatibility sentinel**로만 주입하되 stub provenance를 명시한다.

**composition 가드.** 현 composition에는 production/dev를 구별하는 계약이 없으므로, 환경 이름에 의존하지 않고 **provider 생성 위치**로 강제한다:

- **production API composition은 `AllowAllEligibilityProvider`를 절대 생성하지 않는다.** AllowAll은 테스트 또는 별도 dev composition에서만 직접 주입한다.
- **`REAL_EDGE_ENABLED=true`인 production builder는 real eligibility와 identity resolver가 모두 주입되지 않으면 fail-loud.**
- 추가 불변식(fail-loud): `STANCE_JUDGE_ENABLED ∧ eligibility is AllowAll → configuration error` — eligibility 미검증 owner 전체가 statement search 대상이 되는 privacy/disclosure 위반을 막는다.

일반 depth/experience 추천도 eligibility 없이 owner를 사용자에게 노출하므로, AllowAll이 production composition에서 아예 생성되지 않아야 "turn-on gate"(real eligibility 요구)가 실제로 강제된다.

## 8. 테스트 전략 / DoD

- [ ] **순수 translator + 경계값 테스트** — depth×consistency 곱셈(얕은 depth 미구제), dedup 후 volume saturation, half-life decay(초 해상도·미래 clamp·`last_seen=None→0.0`), experience_*=None.
- [ ] **wire DTO 미러 HTTP adapter + MockTransport 테스트** — 요청 계약(§5: owner_id 생략·limit=200·with_*=false·sort=confidence) / 응답 파싱 / 오류 / **`truncated is True` fail-loud** vs 정확히 200명(`truncated=false`) 정상 통과.
- [ ] **검증 순서·정책 ①–⑤ 테스트** — 순서 pin(§3: 구조검증 전체 선행 → sparse-skip 후행; 특히 owner 중복 항목 중 하나가 `competence=None`일 때 ⑤가 숨지 않음) + skip vs fail-loud 분기 각각.
- [ ] **injected fake resolver로 owner_id→agent_id 결합** + 정책 ⑥ 테스트 — 누락·extra key·동일 agent_id 충돌 각각 fail-loud, edge 순서=projection 입력 순서 보존.
- [ ] **`AllowAllEligibilityProvider`** 이름·provider version stub 명시 + production composition이 이를 생성하지 않음을 테스트.
- [ ] **default-OFF composition 배선** + 안전 가드 fail-loud 테스트(`STANCE_JUDGE_ENABLED ∧ AllowAll`; `REAL_EDGE_ENABLED` production builder에 real eligibility/resolver 미주입).
- [ ] **OFF일 때 기존 동작·`eval/corpus/baseline.json` byte-identical 불변**.
- [ ] mypy/ruff/format clean, 전체 스위트 green, eval gate exit 0.

## 9. turn-on gate로 이월 (이 슬라이스 밖)

- live memory-api 연결 + real 데이터 분포 검증(sparse edge·one-hop 발동·maturity 분포 vs 0.45).
- formula calibration(maturity 계수, evidence_strength 질 가중, freshness half-life).
- real eligibility provider(privacy/safety verdict) — AllowAll 대체.
- production identity resolver(bourbon-api `personal_agent_id`) + partial-unmapped 정상 제외 계약.
- `experience_*` 신호 계약 개편(FIRSTHAND 판정 규칙 or edge 필드 재정의).
- **pagination/bounded-retrieval + join-integrity 계약**(정책 ③) — **production turn-on blocker**. repo가 link→entity join에서 dangling link를 skip(`repository.py:263`)하므로 `truncated=false`가 완전성을 보장하려면 memory-api가 다음 중 하나를 보장해야 한다: (a) dangling link 발견 시 endpoint fail-loud, (b) 유효 joined pair가 `limit+1` 될 때까지 계속 조회, (c) join 이후 기준 total/cursor 제공.
- **freshness 입력 의미 수정**(§4) — **production turn-on blocker**. memory-api가 `evidence_last_seen`(가장 최근 qualifying owner evidence의 실제 timestamp)를 제공하거나 기존 `last_seen` lifecycle을 그 의미로 고쳐야 한다. **단순 build 실행 시각으로 갱신하면 오래된 evidence가 새것처럼 보이므로 금지.** 그 전까지 freshness는 provisional projection.
- **persisted link/entity ownership 검증**(정책 ④) — memory-api가 pair를 fold하기 전에 `GroundingLink.owner_id == PersonalEntity.owner_id`를 검증하고 불일치 시 fail-loud해야 한다(현 응답은 `link.owner_id` 미노출이라 Discovery가 DTO self-consistency까지만 확인 가능).
- **stale-competence lifecycle 수정**(§4) — **production turn-on blocker**. 일반 해결책은 **현재 active statement set과 competence가 판정한 evidence set의 currentness를 검증할 serving 계약**이다: 불일치하면 competence를 미노출/`None` 처리하거나 재판정 완료 전 Discovery 후보에서 제외한다. `competence=None` clear는 zero-active의 **필수 특례**일 뿐이고, 일반 해결책은 active-set 변경까지 다루는 **currentness/signature 계약**이어야 한다(`support_ids`만 현재 IDs로 바꾸는 것은 금지 — depth 위장). 기존 stale 데이터 rebuild/backfill 완료도 선결. Discovery 측에 **stale/zero-active integration test**(currentness 불일치 owner가 후보로 새지 않음)를 추가해 회귀를 막는다. 이것이 닫히기 전 real edge turn-on 금지.
