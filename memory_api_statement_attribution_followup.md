# Memory API 계약 종결 기록 — `attribution` (#129) + server-side 필터 (K-A1 rev 4)

- **상태**: ✅ **RESOLVED — 의미론·server-side 필터 둘 다 착지 (2026-07-29 갱신)**. 이 문서는 memory 팀과의 논의 결과를 확정 계약으로 기록한다 (발신용 요청서 아님).
- **관련**: bourbon-memory-api `#129` / `3e4e7c1`(응답 필드) · `f246f93`(요청 필터). 원 요청은 **채택되지 않은 초안**으로 `archive/memory_api_statement_attribution_request.md`(K-A1 rev 3, commit `29c3e73`)에 보관 — 요청한 `owner_asserted: bool`은 만들어지지 않았고 `attribution` enum 투영으로 대체됐다.
- **성격**: Discovery for/against 기능(`STANCE_JUDGE_ENABLED=ON`)의 release blocker였다. **계약 자체는 전부 종결**되었고, 남은 것은 계약이 아니라 memory-api 쪽 **테스트 공백** 하나뿐 → `memory_api_discovery_open_requests.md` **R2**로 이관(§2-5 참조).

---

## 0. 결론 요약

| # | 항목 | 상태 |
| --- | --- | --- |
| 1 | statement-search 응답에 per-statement `attribution` 노출 | ✅ #129 / `3e4e7c1`로 배포 |
| 2 | `attribution == "owner"` = owner 직접 주장 (의미론) | ✅ **종결** — 신뢰 가능 계약으로 합의 |
| 3 | 장기 confidence 재용도 리스크 | 🟡 **연기** — 재색인 시점에 대응 |
| 4 | statement-search **요청**에 `attribution` 필터 | ✅ **`f246f93`로 배포** — `attribution: list[Attribution] \| null`. Discovery는 리스트 `["owner"]`를 전송(`7180c25`) |
| 5 | 필터가 per-owner cap/count/truncated **이전** 적용 | ✅ 코드 판독으로 확인 · ⚠️ **테스트 없음** → R2 |

**계약은 전부 닫혔다.** 4번이 스칼라 `owner_asserted: bool`이 아니라 `attribution: list[Attribution] | null`로 착지한 점만 원 요청과 다르다(scope: null/생략=전체, `[]`=없음, `["owner"]`=owner-only, 복수=OR). 남은 위험은 계약이 아니라 **회귀 감지 수단의 부재**이고, 그것이 R2다.

---

## 1. 의미론 종결 — `attribution == "owner"`는 owner 직접 주장이다 (§2 철회)

원 요청 rev 3 §2·§3-1은 "`attribution`을 `confidence`에서 파생하면 owner 판정이 틀린다"고 우려했다. **이 우려는 철회한다.** 실제 tier 부여 로직을 확인한 결과 현 코드 기준으로 owner 판정은 정확하다.

### 1-1. 근거 (memory-api `_util._statement_confidence`, `_util.py:141-154`)

```python
cited = [sender_by_msg[mid] for mid in provenance if mid in sender_by_msg]
if any(s == owner_id for s in cited):
    return conf_owner            # → attribution OWNER
```

- 이 코드베이스의 `confidence`는 "연관 강도(연속) 점수"가 **아니라 assertion source를 이산 인코딩한 tier**다. 여러 신호를 뭉갠 품질 점수가 아직 아니다.
- `OWNER`는 confidence가 높아서가 아니라, **claim의 provenance 메시지를 owner가 직접 보냈을 때만**(`any(s == owner_id for s in cited)`) 부여된다 — 즉 owner가 실제로 그 claim을 주장한 경우.

### 1-2. 내가 우려했던 두 오류가 구조적으로 안 생기는 이유

- **과대(false positive)** — "owner가 `왜 그렇게 생각하세요?`라고 질문만 함": 그 질문은 claim의 provenance가 아니다(주장한 provenance sender는 상대방). owner의 참여는 별도 신호 `owner_in_band`가 잡아 `conf_other_engaged`(**ENGAGED**)로 간다(docstring `_util.py:126-130`). owner 질문은 OWNER로 오분류되지 않는다.
- **과소(false negative)** — "타인이 먼저 주장한 claim을 owner가 나중에 직접 재주장": reconciliation이 confidence를 상위 tier로 승격시켜 **OWNER**가 된다(원 요청 §3-2가 요청한 same-claim OR 병합과 동일 동작).

### 1-3. 합의된 계약

> **Discovery는 `attribution == "owner"`를 "owner가 직접 주장한 claim"으로 신뢰하고 K-A2를 구현한다.**

### 1-4. 연기된 장기 리스크 (재색인 시점 대응)

`attribution`이 `confidence`에서 파생되므로, **`confidence`가 훗날 다른 목적(일반 품질 점수 등)으로 재용도되면** OWNER 파생이 깨질 수 있다. 다만 그런 변경은 어차피 **재색인을 요구**하므로, 그 시점에 함께 대응하기로 합의했다(지금 blocker 아님).

- **요청(가벼움)**: 가능하면 memory-api 쪽에서 `attribution == "owner"` ⟺ owner 직접 주장 불변식을 **테스트/계약으로 고정**해 주면, 재용도 변경이 이 의미를 조용히 깨는 것을 CI에서 잡을 수 있다.

---

## 2. server-side `attribution` 필터 — ✅ 착지 (`f246f93`)

> **2026-07-29 갱신.** 이 절은 원래 "유일한 잔여 blocker"를 기술했다. 필터가 배포되어 **blocker는 해소**됐다.
> 아래 2-2·2-3·2-4는 *왜 client-side로 대체 불가였는가*와 *무엇을 수용 기준으로 합의했는가*의 기록으로
> 남긴다 — 그 수용 기준의 **테스트가 아직 없다는 것**이 유일한 잔여 항목이고, §2-5로 이관했다.

### 2-1. 현재 상태 (`f246f93` 이후)

`POST /personal/statements/search`:
- 응답 `owners[].statements[].attribution`: 있음 ✅ (`#129` / `3e4e7c1`)
- 요청 `attribution: list[Attribution] | null` 필터: **있음** ✅ (`f246f93`, `structs.py:122`)
- OpenSearch 쿼리의 attribution→confidence-band 필터: **있음** ✅ — `bool.filter`(must)에 들어가고
  `terms(owner_id)` + `top_hits(per_owner_limit)` 집계가 그 필터된 문서 집합 위에서 실행됨
  (`repository.py:877-903`) → per-owner top-N / count / truncated 전부 post-filter.

*(이전 판에 적혀 있던 "필터 없음 / `subject_qids`·`owner_ids`·`queries`·`per_owner_limit`·`limit`만 받음"은
`f246f93` 이전 상태였다.)*

### 2-2. 왜 client-side 필터로 대체 불가인가 (filter-before-cap)

client-side로만 거르면 서버가 `per_owner_limit`(owner별 relevance top-N)을 **필터보다 먼저** 적용한다. owner의 BM25 top-N이 non-owner statement로 채워지면 owner-asserted statement가 **검색 단계에서 밀려나** 응답에 오지 않고, client는 복구할 수 없다 — 구조적·복구 불가 recall 손실. per_owner_limit을 키워도 비용만 늘 뿐 근본 해소 안 됨.

### 2-3. 요청

1. `POST /personal/statements/search` **요청**에 `attribution=owner` 조건 지원 (Discovery는 항상 owner-asserted만 요청).
2. **★ 이 조건이 owner별 top-N / count / truncated 계산보다 먼저 적용될 것** — acceptance 조항으로 명시. Discovery는 서버 내부를 테스트할 수 없어 이 조항에 의존한다.

### 2-4. Acceptance test (합의된 수용 기준)

> **engaged statement의 BM25 점수가 더 높고 `per_owner_limit=1`이어도, `attribution=owner` 요청에서는 owner statement가 반환되어야 한다. `count`와 `truncated`도 필터링된(owner-only) statement 집합을 기준으로 계산되어야 한다.**

이 테스트가 통과하면 filter-before-cap 계약이 올바르게 구현된 것으로 본다.

### 2-5. 잔여 항목 = 이 acceptance test의 부재 → **R2**

§2-1에서 확인한 순서 보장은 **코드 판독**의 결과이지 테스트가 지키는 것이 아니다. memory-api 쪽에 두 공백이
남아 있다: router fake(`tests/routers/personal/test_router.py:294` `_FakeRepo.search_statements`)가 새
`attribution` kwarg를 안 받아 라우터 테스트가 `TypeError`를 내고, §2-4 acceptance test가 없다(이 순서는
router fake로 검증 불가 — OpenSearch를 실제로 태워야 함).

기능은 동작하므로 Discovery 개발을 막지 않는다. 다만 **`STANCE_JUDGE_ENABLED=ON` 이전 release gate**로
남는다. 이 항목의 권위 있는 위치는 이 문서가 아니라
[`memory_api_discovery_open_requests.md` **R2**](memory_api_discovery_open_requests.md#r2-attribution-필터-테스트-green)이다
— 진행 상황은 거기서 추적한다.

---

## 3. Discovery 측 K-A2 계획 — ✅ 구현 완료

- 검색 어댑터는 `attribution=["owner"]`를 **항상** 지정하는 것을 불변식으로 둔다 → 구현됨(`7180c25`,
  `_SearchRequest.attribution`은 adapter 내부 정책이라 `search()` 시그니처에 없음).
- client-side `_admit`이 응답의 `attribution == "owner"`를 **재검증**한다(defense in depth — 서버 계약이 깨져도 오귀속이 사용자에게 새지 않도록) → 구현됨(`fdf80dd`).
- **활성화 게이트**: server-side 필터(§2)는 착지했으나 **§2-4 acceptance test는 아직 없다**(§2-5 = R2).
  따라서 `STANCE_JUDGE_ENABLED=ON`은 여전히 대기 상태이고, K-A2 배선은 dormant로 실려 있다. 다른 turn-on
  게이트(8-4 B2 judge 품질, staging latency)는 이 문서 범위 밖이다.

---

## 4. 변경 요약 (rev 3 → rev 4 → rev 5)

**rev 5 (2026-07-29)** — 상태 갱신:
- **§2 server-side 필터 착지**: `f246f93`으로 `attribution: list[Attribution] | null`이 배포됨. 원 요청의
  스칼라 `owner_asserted: bool`이 아니라 **리스트 enum 필터**로 착지했고, Discovery는 `["owner"]`를 보낸다.
  이전 판이 이 절을 "유일한 잔여 blocker / ❌ PENDING"으로 적어 두어 실제 상태와 어긋나 있었다.
- **잔여 항목을 계약에서 테스트로 재분류**: 남은 것은 필터가 아니라 §2-4 acceptance test와 router fake의
  공백이며, 권위 있는 추적 위치를 `memory_api_discovery_open_requests.md` **R2**로 이관(§2-5).
- **원 요청서 보관**: `archive/memory_api_statement_attribution_request.md`로 이동 + "채택되지 않은 초안"
  masthead 추가. 이 문서 §1·§4가 그 §2·§3-1·§3-2를 인용하므로 삭제하지 않고 archive에 남겼다.

**rev 4 (2026-07-23)**:

- **§2 의미론 우려 철회**: `_util._statement_confidence` 확인 결과 `attribution == "owner"`는 현 코드 기준 owner 직접 주장으로 정확. (rev 3 §2·§3-1의 confidence-파생 반대 근거는 assertion-source tier 구현을 확인하지 못한 데서 비롯된 과한 우려였다.)
- **장기 리스크 연기**: confidence 재용도 시점 = 재색인 시점에 대응. 불변식 테스트만 가볍게 요청.
- **server-side 필터를 유일 blocker로 확정** + acceptance test(§2-4) 명시.
