# Memory API 요청 — statement `owner_asserted` 필드 + 검색 필터 (K-A1)

- **상태**: DRAFT rev 3 — 발신 전 리뷰 필요.
  - rev 2 (2026-07-22): provenance-sender 구성 → **assertion source** 의미론으로 교체, optional server-side 검색 필터 포함.
  - rev 3 (2026-07-22): 필수 계약을 5값 enum에서 **`owner_asserted: bool`**로 단순화(enum은 join이 닫히지 않고 Discovery의 실제 필요는 boolean 하나), "extraction이 asserter를 식별한다"는 전제를 확정 사실이 아닌 **확인할 구현 전제**로 완화, **OR의 범위를 same-claim merge로 한정**(superseding statement는 독립 계산·상속 금지 — confidence max-keep 패턴 적용 금지).
- **요청 주체**: Agent Discovery (bourbon-agent-recommendation-api)
- **대상**: bourbon-memory-api (personal knowledge)
- **관련**: `2026-07-20-agentic-stance-retrieval-design.md` §D6-2, 코드 repo `tasks/todo.md` K-A1/K-A2.
- **성격**: Discovery for/against 기능(`STANCE_JUDGE_ENABLED=ON`)의 **release blocker**. 리드타임이 가장 긴 항목이라 조기 킥오프 요청.

## 1. 무엇을 요청하는가 (한 줄)

`POST /{prefix}/personal/statements/search`에 두 가지를 요청한다:

1. **응답** statement(현 `StatementMatch`)에 required 필드로:
   ```text
   owner_asserted: bool   # "owner가 이 claim을 대화에서 직접 주장한 적이 최소 1회 있는가"
   ```
2. **요청**에 optional 검색 필터로:
   ```text
   owner_asserted: bool | null   # null = 무필터. Discovery는 true를 보낸다.
   ```

## 2. 왜 필요한가 (Discovery 측 correctness 버그)

Discovery의 stance judge는 statement를 근거로 "이 **owner**가 명제 P를 지지/반대하는가"를 판정한다. 그런데 personal knowledge는 설계상 **owner가 shared room에서 노출만 된 타인 발화 유래 statement**를 포함한다(`Statement.speaker` doc 참조). 이런 statement를 owner의 입장 근거로 judge에 넣으면 **타인의 입장을 owner의 입장으로 오귀속**하는 correctness 버그가 된다.

기존 신호로는 이 필터를 안전하게 만들 수 없다:

- **`speaker` (display name)** — 표시 이름이라 동명이인·개명·None·artifact 케이스에서 owner 비교가 불안정.
- **`confidence` (numeric tier)** — `_util._statement_confidence`의 tier(owner 1.0 / other-engaged 0.7 / indeterminate 0.7)는 **attribution 신뢰도이지 attribution 값이 아니다**. `1.0`은 "owner 발화 provenance ≥1"이지 owner가 주장했다는 뜻이 아니며(owner의 문맥성 질문도 포함될 수 있음), 튜너블 상수라 계약으로 삼으면 cross-repo drift 위험도 있다.

참고: `STATEMENT_REQUIRE_OWNER_ENGAGEMENT=True` 기본값이 비관여 타인 발화를 이미 드롭하므로 남는 non-owner 모집단은 other-engaged/indeterminate 정도로 좁지만, 그 좁은 모집단이 정확히 stance 오귀속을 일으키는 케이스다.

## 3. 요청 상세

### 3-1. 의미론: assertion source 기반 boolean

**`owner_asserted = true` ⟺ owner가 이 claim을 대화에서 직접 주장한 assertion 이벤트가 최소 1회 존재.** 다음을 명시적으로 제외한다:

- **provenance-sender 구성으로 파생하지 않는다.** sender-집합 기반 정의는 두 방향으로 틀린다: (과대) provenance에는 owner의 문맥성 질문 등 비주장 메시지가 섞일 수 있어 "owner sender 포함 ⇒ owner 주장"이 성립하지 않고, (과소) 타인이 먼저 주장한 claim을 owner가 나중에 직접 재주장한 경우가 "혼합"으로 가려진다. 파생 원천은 **각 assertion 이벤트에서 그 claim을 주장한 발화 주체**다.
- **asserter 판별 불가(indeterminate) 이벤트는 true로 계산하지 않는다** (unknown ≠ owner).
- **큐레이션은 주장이 아니다** — owner가 artifact를 큐레이션한 것만으로는 true가 되지 않는다.

이 boolean은 **단조(monotonic)**다: 새 assertion 이벤트는 false→true 방향으로만 값을 바꾼다. 병합 재계산은 단순 OR라 join table이 필요 없다.

> **설계 노트 (rev 3에서 enum을 강등한 이유)**: assertion-sources enum(`owner_only|other_only|owner_and_other|indeterminate|owner_curated_artifact`)을 필수 계약으로 검토했으나, `indeterminate`/`owner_curated_artifact`와의 병합 결과가 닫힌 lattice로 정의되지 않아 precedence table이 추가로 필요했고, Discovery가 실제로 소비하는 값은 boolean 하나다. enum이 다른 소비자(예: UI 출처 표시)에 유용하다면 **memory-api 재량의 설명용 projection**으로 두면 되고, 이 계약의 필수 범위는 boolean이다.

### 3-2. 계산 시점·저장 (locus)

1. **ingestion 시 계산 + statement 문서에 저장 + 색인.** 검색 시 재파생 금지 — 응답은 저장된 필드를 projection하고, §3-3의 필터도 색인된 값으로 동작한다.
2. **★ same-claim merge 시 재계산 — 단 OR의 범위는 "같은 claim"에 한정된다.** 두 경로를 계약에서 분리해 달라:
   - **same-claim NOOP / provenance-merge**: reconciler가 provenance를 union으로 병합할 때(`update.py` `_merge_provenance`), `새 값 = 기존 값 OR (이번 assertion 이벤트가 owner의 직접 주장인가)`. claim의 주장 주체 집합은 시간이 지나며 커지므로 최초 insert에서만 계산하면 stale해진다. 예: `false`였던 claim을 owner가 직접 재주장하면 `true`가 되어야 한다(그래야 Discovery admit 대상이 됨 — 올바른 방향). 단조 OR라 저렴하고 순서 무관이다.
   - **★ superseding statement는 상속 금지**: supersede는 claim이 갱신·반전되는 경로다 — **superseding statement의 `owner_asserted`는 그 새 statement 자신의 assertion 이벤트로 독립 계산하며, superseded statement의 `true`를 상속하지 않는다.** 특히 기존 confidence의 max-keep 이월 패턴(`_supersede`)을 이 필드에 **따라 적용하지 말 것** — 그러면 owner가 주장한 적 없는 새 claim에 owner의 주장이 찍힌다. superseded 문서 자신의 값은 어차피 검색 대상이 아니므로(active-only) replacement의 값과 무관하다.
3. **★ 확인이 필요한 구현 전제 (확정 사실 아님)**: 이 파생은 "assertion 이벤트별 발화 주체를 안정적 sender identity로 식별"할 수 있어야 성립한다. 공개 계약상 statement가 노출하는 것은 display-name `speaker`뿐이므로, **내부적으로 sender ID 수준의 asserter 연결이 이미 가능한지, 아니면 extractor 계약 변경이 필요한지는 memory-api 확인이 필요하다**(speaker→confidence tier 파생이 ingestion에서 돌고 있어 가능하리라 추정하지만, 추정이다). 이 확인 결과가 구현 비용과 일정의 핵심 변수다.

### 3-3. 노출 + 검색 필터

- **응답**: statement 객체에 **required 필드**로. (Discovery는 wire에서 required로 받아 누락 시 fail-loud한다.)
- **★ 요청 필터** (`owner_asserted: bool | null`, null=무필터): Discovery가 client-side로만 거르면 **owner당 relevance cap(`per_owner_limit`)이 필터보다 먼저 적용**되어, BM25 top-N이 inadmissible statement(타인 주장 등)로 채워질 때 admissible statement가 검색 단계에서 밀려나 client-side에서 복구 불가능하다. server-side 필터면 cap이 필터 **후에** 적용되어 이 구조적 recall 손실이 사라진다. **"필터가 per-owner cap보다 먼저 적용된다"를 계약 조항(acceptance)으로 명시해 달라** — Discovery는 서버 내부를 테스트할 수 없어 이 조항에 의존한다. attribution은 **query-agnostic 저장 속성**이므로 이 필터는 "stance-relative 지식은 memory-api가 모른다"는 기존 ownership 경계를 침범하지 않는다(§D6-2의 neutral primitive 성격 유지). 색인을 요청하는 실질 이유가 이 필터다.
- 다른 statement projection(`StatementSummary` 등)에의 노출 여부는 memory-api 재량 — Discovery 계약은 statement-search 응답·요청만이다.

### 3-4. 기존 필드는 변경 요청 없음 (non-goals)

- numeric `confidence` tier의 의미·값 변경을 요청하지 않는다.
- `speaker` 필드 변경/삭제를 요청하지 않는다.
- 과거 데이터 backfill 방식(재빌드 vs lazy)은 memory-api 재량 — 단 Discovery가 필터를 켜는 시점에는 검색 대상 statement 전부에 값이 있어야 한다.

## 4. Discovery 측 사용 계획 (참고)

- 검색 요청에 `owner_asserted: true`를 **항상** 지정(어댑터 불변식)하고, client-side `_admit`이 응답의 projection 값을 재검증한다(defense in depth).
- `owner_asserted == false`(타인만 주장·asserter 불명·큐레이션만)는 stance 근거에서 제외 — 노출·큐레이션은 입장 주장이 아니라는 의도적 정책.
- 이 필터(K-A2)는 Discovery for/against 기능 활성화(`STANCE_JUDGE_ENABLED=ON`)의 release blocker다. 계약이 닫히기 전에는 기능을 켜지 않는다.

## 5. 타임라인 요청

구현 착지 일정보다 먼저 두 가지의 합의/확인을 요청한다:

1. **계약 shape 합의**: §3-1 boolean 의미론(3가지 제외 규칙 포함), §3-2 재계산 시점, §3-3 필터 파라미터와 filter-before-cap 조항.
2. **구현 전제 확인**(§3-2-3): assertion 이벤트별 asserter를 sender ID 수준으로 식별 가능한지 — 가능하면 이 요청은 저비용이고, extractor 계약 변경이 필요하면 일정 재협의.

shape이 닫히면 Discovery는 wire DTO·요청 필터 배선·계약 테스트(K-A2)를 선제 준비할 수 있다.
