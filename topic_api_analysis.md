# bourbon-topic-api 분석과 Discovery 방향 재정립

> **문서 지위**: 분석 기록 + 방향 결정 기록. **설계 문서가 아니다.**
> 이 문서는 `persona_topic_search_design.md`(rev 14)를 대체하기 위한 **재설계의 입력**이며,
> 재설계 결과가 나오면 그 문서가 새 정본이 된다.
>
> **작성 근거**: 2026-08-21, `../bourbon-topic-api` 전수 읽기 + 테스트 실행 + 카탈로그 시드
> 실측. 초판은 HEAD `296723d`, rev 3은 HEAD `107f5cd`(#17 카탈로그 산출물 전환),
> **rev 4는 HEAD `80c650f`(2026-08-24)** — PR #16(인덱스 2분할+tier 집합 랭킹),
> #18–#25(응답 재구성·internal 표면 통합·3언어 서술·응답 트리·demo persona seed)를 반영했다.
> **rev 5(2026-08-24)는 오너 전언 3건 반영** — facets는 dummy·계약 미확정, item=null 의미
> 확인, 트리 depth 2 + 이하 rollup.
> 대조 대상은 `../../iac`(origin/main `d364d3c`, rev 4에서 `592e34c`로 재확인),
> `../bourbon-api`(origin/main `943b5f5`), `../bourbon-agent`(HEAD `18fbcac`).
>
> **표기 규율**: 모든 주장에 `검증됨`(코드/실측) · `가정`(명시된 추정) · `미확인`(확인 필요) 중
> 하나가 붙는다. 숫자는 전부 실측이며, 재현 방법은 부록 B에 있다.
> 추정을 실측으로 제시하지 않는다 — 이 문서 작성 중 그 실수를 한 번 했고 §2의 표가 그 교정 결과다.

---

## §0 한 페이지 요약

**무엇을 발견했나.** `bourbon-topic-api`는 이미 구현된 독립 마이크로서비스다. 큐레이션된
Wikidata 기반 토픽 카탈로그(2,605개 — **이미지에 커밋된 JSON 산출물**)와 유저별 토픽 점수
(DynamoDB 1테이블)를 두고,
"토픽 → 그 토픽을 가진 유저 랭킹"을 답한다. **OpenSearch를 쓰지 않는다.**

**우리 rev 14와의 관계.** rev 14는 "extractor가 bourbon-agent 안에 있고, 우리가 전용 테이블에
topic/claim을 소유하며, DynamoDB Streams로 AOSS에 색인하고, 요청마다 LLM으로 relevance를
판정한다"는 그림이었다. **입력 사슬 전제는 맞았다** — extractor는 bourbon-agent 안이고 입력은
deferq 이벤트다(오너 확인, 2026-08-21 — §1.5). 틀린 것은 그 다음 전부다: **topic의 저장·색인·
검색·랭킹의 주체가 우리가 아니라 topic-api다.**

**확정된 방향.** topic-api를 **축(axis)** 으로 삼는다. 폐기가 아니라 **축의 이전**이다.
rev 14에서 저장소·색인·스트림·동시성 계약은 폐기하고, 규율(실패 의미, gate 직교성,
self-exclusion, 판정 입력 비신뢰)과 얇은 보정층(ordering 키, rerank)만 승계한다.
**병렬로 두 시스템을 굴리는 것은 금지한다.**

**가장 큰 리스크는 품질이 아니라 데이터다.** 프라이버시 정책상 유저 토픽은 private이 기본이고
유저가 직접 public으로 올려야 한다. 랭킹은 public 파티션만 읽는다. 따라서
`서빙 가능성 = 카탈로그 커버리지 × 공개 밀도`이고, **두 번째 항이 현재 0이다.**

**rev 4에서 움직인 것 (2026-08-24).** 인덱스가 rank/holder 2개로 갈리고 friends가 랭킹
가능 tier로 추가됐다(#16). 검색 응답이 설명 트리로 재편됐고(#21–#24), **랭킹 응답에 원
facets(`score_detail`)가 실리기 시작했다** — §4.2의 걸림돌(N+1)이 해소됐다(§11-3 닫힘).
internal 표면은 별도 워크로드에서 같은 워크로드의 `/api/internal/svc/topic` prefix로
통합됐다(#19). **컷 한계(§9)와 공개 밀도 0(§6.4)은 그대로다.** 단 rev 5의 오너 전언:
**현재 facets는 dummy이고 필드·의미가 모두 바뀔 수 있다** — 재가중 재료의 운반 경로는
확보됐지만 의미는 아직 계약이 아니며, ordering 키 식은 facets 계약 확정(§11-18) 전에
잠그지 않는다.

**재설계가 답해야 하는 것**은 §13에 목록으로 있다.

---

## §1 bourbon-topic-api는 무엇인가 (검증됨)

### 1.1 정체와 스택

| 항목 | 내용 |
|---|---|
| 형태 | 독립 마이크로서비스. bourbon 호스트 `/api/svc/topic/` 뒤, edge-auth 사이드카 경유 |
| 스택 | FastAPI + DynamoDB(**user topic 1테이블**) + uv + structlog. **Python `>=3.14,<3.15`**. 카탈로그는 테이블이 아니라 `catalog_dist/catalog.json`(133k줄, git 커밋·이미지 포함) — 시작 시 1회 로드, 변경은 redeploy로 반영(#17) |
| 문법 | PEP 758(`except A, B:` 괄호 없는 다중 예외) 실사용 — **3.13에서는 컴파일 실패** |
| 인증 | 코드 0줄. `bourbon.xinobi.ai/edge-auth` 라벨이 붙은 파드의 사이드카가 토큰 검증 후 `x-user-id` 주입, `Authorization`/`Cookie` 제거 |
| 규모 | Python ~11k줄 |
| 테스트 | rev 4 HEAD `80c650f`에서 재실행: **1208 passed / 86 skipped / 0 failed**. skip은 DynamoDB 로컬 엔드포인트 미설정. rev 3(107f5cd)은 942/50/0, 초판(296723d)은 922/62/1이었다 |

`AWS_REGION`은 configmap에 고정(`ap-northeast-1`). botocore가 기본값을 갖지 않아 누락 시
클라이언트 생성 단계에서 `NoRegionError`로 죽는다.

### 1.2 두 표면 — 워크로드 하나, prefix 두 개 (#19에서 재편)

~~`SERVICE_ROLE`이 프로세스에 존재하는 라우터 집합을 결정한다~~ — **rev 4에서 소멸.**
#19가 역할 분리를 워크로드에서 **마운트 prefix**로 옮겼다. 한 워크로드가 두 표면을 서빙하고,
`api/depends/surfaces.py`의 두 목록이 어느 라우터가 어느 prefix 아래 붙는지를 정하며, 표면
테스트가 그 분리를 고정한다("엉뚱한 목록에 있는 엔드포인트는 보안 결정이 잘못된 것").

| 표면 | prefix | edge-auth | 라우터 |
|---|---|---|---|
| public | `/api/svc/topic` | 있음 (게이트웨이 라우트 필요) | topics · me · users · search |
| internal | `/api/internal/svc/topic` | **skip** (bourbon-api 관례 prefix — 게이트웨이가 IP gate 뒤로 라우팅) | internal/topics · internal/search · internal/users(score 주입·extraction 쓰기·유저 삭제·읽기 미러) |

쓰기 라우트는 public 표면에 **아예 마운트되지 않는다** — 게이트웨이 오설정으로도 노출 불가.
internal 표면에는 검증된 호출자 신원이 없다: `x-user-id`는 보낸 쪽이 넣은 값 그대로이고,
어느 internal 라우트도 그것을 읽지 않는다. `/me`는 미러하지 않는다(호출자가 없으므로) —
이 사실이 §6의 프라이버시 결론에서 결정적으로 쓰인다. internal 응답은 한 언어가 아니라
**언어 맵(ko/en/ja) 전체**를 답한다 — 언어 선택이 우리(호출자) 몫이 된다.

internal용 `AuthorizationPolicy`는 여전히 없어(재확인 — k8s에는 dev docs용 oauth2-proxy
정책뿐) 메시 내 어느 파드나 호출할 수 있고, README가 이를 "accepted risk"로 유지한다.

### 1.3 3층 구조

```
① 카탈로그 (토픽 DAG)        topic/catalog/*      catalog_dist/catalog.json (git 커밋, 이미지 포함)
     {built_at, dump_version, topics[], edges[[child,parent]]} — 시작 시 1회 로드해 인메모리
     그래프로. TTL·reload 라우트 없음: 편집은 discover→review→build→커밋→redeploy (#17)

② 유저 토픽 아이템             topic/user_topics/* + topic/storage/user_topics.py (#18에서 저장층 분리)
     DynamoDB: bourbon-user-topic-tokyo-{stage}   PK=USER#{uuid}  SK=TOPIC#{id}
     score(0-100) · visibility(4단) · descriptions(ko/en/ja — #20에서 3언어화)
     · blocks(이미지, 구 image_ids) · score_detail(facets/relation/confidence — 구 score_inputs)
     GSI 2개(#16):
       topic-rank-index    PK=rank_key={topic_id}#{visibility}#{shard}  SK=score  KEYS_ONLY  ← 랭킹
       topic-holder-index  PK=SK  SK=PK  KEYS_ONLY  ← tier 무관 전수 보유자(merge 이송·삭제용)

③ 검색·랭킹                    topic/search/*
     텍스트→토픽: 인메모리 부분문자열 스캔        (§2.1)
     토픽→유저 : GSI 스트림 + threshold 병합      (§2.2)
```

`topic_id`는 불투명하다. `topic/catalog/ids.py`에서 생성하며 **표시 이름에서 파생하지 않는다** —
한 단어가 여러 개념을 가리키므로(커피 버번 / 위스키 버번) 이름 파생 식별자는 먼저 만들어진
개념이 이름을 독점하게 만든다. Wikidata 출처가 있으면 `uuid5(고정namespace, "wikidata:{qid}")`
로 **결정적**이고, 그룹 자체 토픽은 `uuid5(ns, "group:{key}")`다. **#17부터 모든 id가 파생이다**
— 운영자 수동 생성 라우트와 함께 `uuid4` 랜덤 경로가 제거됐다("Every identifier is derived;
there is no random path").

`rank_key = {topic_id}#{visibility}#{shard}`는 visibility에서 파생되는 **저장 속성**이고,
`RANKED_TIERS = {public, friends}`일 때만 존재한다 — GSI는 키 속성이 있는 아이템만 담으므로
private/hidden이 랭킹 인덱스에 없는 것은 버그가 아니라 **sparse index 메커니즘 그 자체**다
(#16). tier를 바꾸는 쓰기(`patch_settings`)만 rank_key를 SET/REMOVE하고, injection·extraction은
불가침이다. 파생은 `topic/connectors/dynamodb/keys.py` 한 곳(#18에서 모듈 이동)에만 있고,
인덱스 이름도 그 모듈이 소유한다("reader와 writer가 어긋날 수 없게"). shard는 현재 전부
0(`SOLE_SHARD`) — 키 포맷에 미리 실어 두어 나중에 넓혀도 저장 포맷이 안 바뀐다.
(rev 3의 `backfill_index_key.py` 언급은 삭제 — 스크립트 자체가 사라졌고, 배포 인덱스의 유일한
명세는 `scripts/dynamodb/create_tables.py`다 — §7-1.)

한 아이템을 **세 writer가 disjoint 속성으로 나눠 쓴다**(storage 모듈 docstring에 계약 명시):
user(visibility·rank_key) / extraction(descriptions·blocks) / injection(score·score_detail).
겹침은 `updated_at` 하나뿐이고 거기서는 LWW가 올바른 의미다. 세 쓰기 모두
`visibility = if_not_exists(:private)`를 심는다 — **어느 경로로 먼저 착지하든 private**이
opt-in 정책의 저장층 구현이다(§6.1).

### 1.4 카탈로그 파이프라인

`python -m cli catalog` 3단계, 시드 디렉터리 하나 위에서 순서대로 돈다.

| 명령 | 읽는 것 | 쓰는 것 |
|---|---|---|
| `discover` | `groups.yaml`, knowledge API(bourbon-memory-api-v2 `/knowledge/*`), LLM 프록시 | `reviewed/{group_key}.yaml` |
| `review` | `reviewed/*.yaml` | 같은 파일 제자리 |
| `build` (#17 — 舊 `apply` 대체) | `groups.yaml`, `reviewed/*.yaml`, `merges.yaml` | `catalog_dist/catalog.json` — **working tree에만** 쓴다. 테이블 접근 없음 |
| `merge` / `migrate-items` (#17) | 아래 | merge=파일(ledger+산출물 재빌드), migrate-items=**라이브 user topic 테이블**(dry-run 기본, `--execute`) |

- seed qid에서 **아래로만**(`narrower`) 확장한다. seed 서브트리 밖은 후보에 들어오지 않는다.
- 값싼 카드 필터 → 상세 조회 → LLM 배치 분류(기본 `openai/gpt-5.6-luna`, confidence 임계 0.8).
- LLM에게 "카탈로그는 깊게 저장하지만 독자는 2단만 본다"를 미리 알려주고, 상위 레벨의 다른
  자식들 옆에서 노이즈로 읽히는 변종은 `too_specific`으로 떨어뜨린다.
- 동음이의 의심·중복 라벨·`min_importance` ±10% 경계·LLM parent와 기계적 parent 불일치는
  **항상 사람에게** 넘어간다.
- 재실행 안전: 사람의 결정은 다음 discover에서도 살아남는다. 캐시는 `dump_version`으로 스코프.
- id가 qid에서 파생되고 산출물이 통째로 재빌드되므로 "패치 vs 신규" 매칭 문제 자체가 없다.
  초판이 지적한 수동 생성 토픽의 중복 위험은 **랜덤 id 경로와 함께 #17에서 소멸**했다.
- merge는 두 단계로 갈라졌다: `merge`가 `merges.yaml` ledger에 기록하고 산출물을 재빌드
  (파일만 — 커밋·redeploy로 반영), `migrate-items`가 옛 토픽의 유저 아이템을 3개 tier 전부
  쓸어 새 토픽으로 옮긴다(비원자적·멱등, 재실행이 복구 경로, dry-run 기본). 빌드는 dangling
  merge·자기참조·`MAX_MERGE_HOPS` 초과 체인을 **읽기가 아니라 배포 전에** 거부한다.
  두 명령 사이의 간극은 명시적으로 수용됐다: 아이템은 먼저 옮겨지고 merged 마크는 다음
  배포에 착지 — 그 사이 옛 토픽 검색은 "카탈로그가 설명하기 전에 빈 결과"가 된다.

### 1.5 페르소나 → 토픽 추출 (현재는 임시 형태)

`cli persona extract`. **이 CLI/마크다운 형태는 persona extractor 계약이 미정이라 임시로
만들어 둔 것이다**(담당자 확인, 2026-08-21).

**확정된 생산 사슬 (오너 확인, 2026-08-21).** topic의 재료는 기존 그림과 같이 **deferq 이벤트를
받은 bourbon-agent의 persona extractor가 생성한 것**이다:

```
bourbon-api deferq 이벤트 (at-most-once)
 → bourbon-agent persona extractor      ← 아직 없음: user_persona 저장소·CAS 쓰기 경로는 있으나
                                           레포에 save_persona 호출자가 0건이고, 주석 자신이
                                           "extraction lands somewhere outside this repo"라고 말한다
 → user_persona 슬롯 (SHARABLE / PRIVATE × bio·traits·preferences)
 → topic-api의 persona→topic 파이프라인   ← 아래 임시 CLI가 그 스탠드인
 → POST /api/internal/svc/topic/users/{uid}/scores
```

이 사슬에서 따라 나오는 두 가지:

1. **freshness는 끝까지 best-effort다.** deferq는 at-most-once이고, bourbon-agent의 이벤트
   ingest는 명시적으로 "logged and dropped + backfill로 보수"다. rev 14 §1-①의 best-effort
   선언이 주체만 바뀌어 승계된다(§9) — 우리는 topic 데이터의 최신성을 가정하지 않는다.
2. **생산 입력은 마크다운 파일이 아니라 persona 슬롯 텍스트다.** 어느 슬롯이 추출 입력인지
   (sharable만? private 포함?)는 열린 질문이다(§11-14). private 포함이면: topic의 공개 자체는
   유저의 토글 동의를 거치지만, LLM이 쓰는 per-topic `description`이 private 서술의 뉘앙스를
   실어 나를 수 있다. 슬롯 텍스트는 세 필드짜리 짧은 텍스트라, 현 CLI가 읽는 풍부한 마크다운과
   **입력 밀도가 다르다** — facets 품질이 슬롯 텍스트에서도 유지되는지는 extractor 쪽 검증 사항.

현 임시 파이프라인:

```
persona markdown
 → ①signals   LLM 1회: evidence · 한국어 description · 영어 query_phrases 2~4개 · facets 5개
 → ②grounding internal GET /search/topics + 상세의 children. 활성만, dedupe, signal당 40개 캡
 → ③marking   LLM 1회/signal: 후보 목록에서 exact|ancestor|related + confidence + 한국어 description
                              **모델은 인덱스만 답한다** (id를 주면 그럴듯한 것을 발명하므로)
 → score = 존재하는 facet들의 등가중 평균 × relation할인(1.0/0.85/0.6) × confidence
```

- 출력은 **디스크 JSON**(`.persona_topics/`)뿐이다. 실 테이블 적재 경로는
  `scripts/dynamodb/seed_local.py`(loopback 전용) 하나이고, dev/prod에는
  `POST /api/internal/svc/topic/users/{uid}/scores`(구 `/internal/topic/scores/bulk` — #18에서
  users 아래로 통합)를 부를 주체가 **아직 없다**.
- 이 서비스는 **deferq/AMQP 의존이 전혀 없다** — 이벤트 소비는 상류(bourbon-agent)의 몫이고,
  topic-api는 persona 산출물을 받아 topic을 만드는 자리다.
- `query_phrases`는 영어 한정이며 프롬프트가 "카탈로그가 라벨링하는 방식의 1–3단어 canonical
  name, 수식어 절대 금지"를 강제한다. `unmatched_signals`(어떤 후보도 살아남지 못한 signal)는
  "카탈로그 갭을 드러내기 위해" 보관되지만 **파일에만 남고 서비스는 읽지 않는다.**

---

## §2 검색은 어떻게 이뤄지는가 (OpenSearch 없음, 검증됨)

검색이 두 단계로 쪼개져 있고, **①은 검색 엔진이 아니며 ②는 텍스트를 보지 않는다.**

```
자유 텍스트 ──①─→ topic_id ──②─→ 랭킹된 유저들
```

### 2.1 ① 텍스트 → 토픽: 인메모리 부분문자열 스캔

`topic/catalog/graph.py:find_by_name`이 전부다.

```python
needle = normalize_search_text(query)        # lower() + 공백 전부 제거
for item in self._topics.values():           # 2,605개 선형 순회 (dict 삽입 순)
    if item.status is not active: continue
    hay = [labels.ko, labels.en, labels.ja] + item.aliases    # 최대 53개
    if any(needle in normalize_search_text(t) for t in hay):
        found.append(item)
    if len(found) >= limit: break             # limit = SEARCH_MAX_NAME_MATCHES(20)
```

토크나이저·형태소 분석·stemming·점수·순위가 **전부 없다.** 시작 시 1회 로드한 카탈로그 전체를
메모리에 들고 `grep -i`를 돌린다(#17 전에는 60초 TTL 재적재였다 — §5.3).

작동하는 이유는 **Wikidata alias가 동의어 사전 역할을 하기 때문**이다. 실측: 그래프 2,605개에
**alias 66,349개**(토픽당 평균 25.5개). `programming language` 하나에 `computer language`,
`coding language`, `프로그래밍언어`, `컴퓨터 언어`, `プログラム言語`, `Proglang`, 오타인
`Programing language`까지 붙어 있다. 형태소 분석기가 할 일을 큐레이션된 목록이 대신한다.

**라벨·alias가 만들어지는 규칙** (rev 4에서 명시화 — `topic/catalog_import/structs.py`의
`topic_labels_from`·`topic_aliases_from`, 검증됨):

- `labels.ko/en/ja` = Wikidata label 그대로. **en은 엔티티 기본 label로 폴백**하므로 거의 항상
  존재하고, ko/ja는 빠질 수 있다.
- `aliases` = Wikidata alias 중 **ko/en/ja만**, 중복 제거, 원래 순서, **토픽당 50개 cap**,
  언어 구분 없이 평탄 저장(어느 언어의 alias였는지는 저장 후 알 수 없다).
- 검색 정규화는 소문자화+공백 제거뿐 — "Phase 1 has no morphological analysis"가 코드 주석에
  명시돼 있다.
- 라벨·alias는 `catalog edit` 단계에서 사람이 수정할 수 있다 — **규칙은 안정적이고 어휘는
  배포 단위로 움직인다.**

이 규칙이 곧 expansion의 레버다: "Wikidata가 그 개념을 부르는 이름"으로 질의를 깎아야
걸린다. §10-2의 R1–R7이 여기서 유도된다.

**결정적 비대칭 — 방향.** `needle in haystack`에서 needle이 질의, haystack이 라벨이다.
즉 **질의가 라벨의 부분문자열이어야 한다.**

- `커피` ⊂ `드립 커피` → 매칭
- `드립 커피 추출` ⊄ 어떤 라벨도 → **0건**

**질의가 길어질수록 매칭 확률이 0으로 간다.** extractor 프롬프트가 `query_phrases`를 1–3단어
canonical name으로 못 박는 진짜 이유가 이것이다. 검색 엔진이 없으니 **질의를 라벨 모양으로
미리 깎아서** 넣어야 한다.

**실측** (`find_by_name` 로직을 실제 그래프 2,605개 + alias 66,349개에 그대로 적용.
`TopicGraph`가 topic_id로 dedupe하므로 중복 qid 12건을 접은 뒤의 수치다. 부록 B로 재현 가능):

| 질의 | 총 매칭 | 앞 20개(=서비스가 실제로 보는 것) 관찰 |
|---|---|---|
| `커피` | 8 | coffee, instant coffee, cold brew, specialty coffee … 정상 |
| `드립 커피` | 1 | drip coffee |
| `핸드드립 커피 추출법` | **0** | 긴 질의는 전무 |
| `machine learning` | 5 | machine learning, explainable AI, supervised/unsupervised, ensemble |
| `머신러닝` | 1 | machine learning (**alias에 있다**) |
| `기계학습` | 4 | machine learning, reinforcement/supervised/unsupervised learning |
| `python` / `파이썬` | 1 / 1 | Python (한국어 alias 작동) |
| `위스키` | 2 | whisky, malt whisky |
| `양자역학` | 1 | quantum mechanics |
| `quantum` | 6 | **첫 결과가 `crossword`** — alias `"Quantum puzzle"` 때문 |
| `database` | 5 | **첫 결과가 `blockchain`** — alias에 `distributed database` 류가 있음 |
| `ai` | **560 (캡 도달)** | 앞 20개: isekai, cryptocurrency, marketing, accounting, decision theory, viral marketing … **인공지능이 없다** |
| `kubernetes` / `쿠버네티스` | 0 / 0 | 카탈로그에 개념 자체가 없음 |
| `dynamodb` | 0 | 없음 |
| `observability` / `관측가능성` | 0 / 0 | 없음 |

읽어야 할 두 가지:

1. **한국어 alias 커버리지는 예상보다 좋다.** `머신러닝`·`파이썬`·`양자역학`이 다 걸린다.
   한국어 질의가 못 쓸 수준은 아니다. 다만 영어 alias가 더 두꺼우므로 expansion은 영어가 유리하다.
2. **짧은 질의가 치명적이다.** `ai`는 560개를 매칭하고(부분문자열이므로 is**ai**, m**ai**l 등),
   20개 캡을 채운 뒤 **관련도 순이 아니라 그래프 보관 순서**로 자른다. 인공지능이 그 안에
   들어올지는 운이다. `MIN_NAME_QUERY=2`가 있지만 2자로는 부족하다.
   `find_by_name`은 "제공할 relevance 순서가 없다"고 README가 인정한다.

### 2.2 ② 토픽 → 유저: GSI + threshold 병합

여기엔 텍스트가 없다. rank-index 파티션 `{topic_id}#{tier}#0`이 score 내림차순으로 정렬돼
있고, **요청이 tier 집합을 명시한다**(rev 4): `visibility=public&visibility=friends` 반복
파라미터, 기본 public. #16부터 friends도 랭킹 가능 tier이며, private/hidden은 파라미터 enum에
스펠링 자체가 없다. 한 토픽이 tier 수만큼 파티션을 가지므로 `TopicIndexStream`이 파티션들을
점수 내림차순으로 병합해 **토픽당 스트림 1개**를 유지한다 — 파티션을 별도 스트림으로
threshold에 주면 bound가 합산되어(한 유저는 한 tier에만 있으므로 진짜 상한은 max) 조기 종료가
사실상 불가능해지기 때문이다(`topic/search/streams.py` docstring 명시).
**leaf와 rollup은 엔드포인트가 아니라 같은 서비스가 요청마다 고르는 두 전략이다**
(`topic/search/service.py`의 `if len(weights) == 1`).

```
질의 → topic_id 확정 → 서브트리 걷기 (max_depth=3, max_count=50)
  → 활성 자손 0            → leaf
  → 자손 있음 / 이름이 여러 토픽 매칭 → rollup
```

**leaf** (`topic/search/single.py`) — 파티션 하나가 후보 전체다. 상위 `limit`행을 읽고(score 0을
만나면 그 아래는 전부 0이므로 즉시 종료) 본문을 BatchGet 한 번으로 채운다. 라운드트립 2회,
`exhaustive=True`가 **항상** 보장된다(병합이 없으니 근사가 아니라 정답). decay 없음.

**rollup** (`topic/search/service.py:_rank_rollup` + `topic/search/threshold.py`) —
서브트리의 토픽마다 파티션이 따로 있으므로 정렬된 스트림 N개를 병합한다. 유저 점수는 가중 합:

```
weight = SEARCH_DEFAULT_DECAY(0.6) ^ 질의 토픽으로부터의 거리
유저 총점 = Σ weight[t] × score[유저, t]   for t ∈ 서브트리 ∩ 유저 보유
```

Fagin TA 계열 알고리즘:
1. 스트림의 `bound` = 아직 안 읽은 유저가 그 토픽에서 가질 수 있는 최대 점수(첫 읽기 전 ∞)
2. `T = Σ weight × bound` = 미발견 유저의 총점 상한
3. 확정된 k번째 점수가 `T`를 **엄격히** 넘으면 중단(등호에서 멈추면 tie-break가 뒤집을 수 있음)
4. 아니면 `T`에 가장 크게 기여하는 스트림에서 다음 페이지를 읽고 2로

그리고 비싼 단계가 하나 더 있다. 스트림은 "유저 U가 토픽 t에서 몇 점"만 알려주므로 총점을
알려면 **U의 파티션 전체를 다시 읽는다**(`resolve` → `list_for_user`). 이것이 rollup 비용의
대부분이다. **rev 4에서 이 읽기가 `ConsistentRead=False`로 바뀌었다** — 후보가 이미 강한
읽기가 불가능한 인덱스에서 왔으므로 강한 읽기는 최신성을 더하지 못하고 "서비스에서 가장 뜨거운
읽기의 비용만 2배"라는 근거가 주석에 있다. §6.3의 보호 강도 서술도 이에 맞춰 정정했다.

**중요한 방향성**: 서브트리 걷기는 **아래로만** 간다. 드립커피만 보유한 유저는 "커피" 질의에
나오지만, 커피만 보유한 유저는 "드립커피" 질의에 **나오지 않는다.** extractor가 넓은 토픽과
좁은 토픽에 동시에 붙이는 이유가 이것이고, 이는 **적재 계약의 핵심 항목**이다(§11-2).

**불완전성 3종 플래그** — 삼키면 안 된다:
- `exhaustive=false`: 읽기 예산이 먼저 소진돼 증명이 실패. 꼬리가 빠져 있을 수 있음
- `truncated_descendants`: depth/count 상한이 잘라낸 자손 수. 여러 루트면 상한이 아니라 **상한의 상한**
- `unranked_topics`: 이름이 매칭했으나 예산이 닿지 못한 루트 수

**응답은 설명 트리다 (#21·#23·#24, rev 4).** `items[]`의 각 유저가
`{user_id, score, matched[]}`이고 `matched`는 평면 리스트가 아니라 트리다:

- 노드 = `{topic, item, distance, contribution, children}`. 보유 토픽이 기여도(weight×score)
  내림차순으로 놓이고 `TOPIC_TREE_DEPTH=2` 기준 shown ancestor 아래로 접힌다.
- `distance`: **0 = 질의가 지명한 토픽, 양수 = 자손(decay 지수 그 자체), 음수 = 표시용 조상**
  (기여 0, 크기는 아래 노드까지의 hop 수).
- `contribution`의 합 = `score` — 총점이 응답만으로 검산된다.
- `item` = 그 토픽에 대한 유저의 저장 본문(score·visibility·descriptions·blocks·시각).
  **`blocks[]`에 `score_detail` 블록(facets·relation·confidence)이 합성돼 나온다**
  (`api/structs/user_topic.py:_blocks_of`) — §4.2의 걸림돌이 여기서 풀렸다.
- 유저가 아무것도 보유하지 않은 매치 토픽은 그 유저의 트리에서 빠진다(#23). 이름 검색이 20개
  토픽을 지명해도 각 유저의 `matched`에는 자기 총점을 설명하는 것만 남는다 — 같은 질의에 두
  유저가 서로 다른 topic 목록을 답받는 것이 정상이다.
- 불완전성 플래그의 wire 이름: `exhaustive` / `descendants_dropped` / `topics_dropped`
  (도메인의 truncated_descendants / unranked_topics).

토픽 검색(`GET /search/topics`)도 트리로 답한다(#22): 매치를 shown ancestor 아래 중첩하고
노드마다 **`is_match`**(true=질의가 매치한 토픽, false=걸어두기용 조상)를 실으며(#24),
`limit`은 매치 수만 센다. persona extraction 자신도 이 트리를 grounding 후보 조립에 쓴다.

**오너 확인(전언), 2026-08-24 (rev 5):** ⑴ `search/users`의 `item=null` 노드는 "그
유저(agent)가 그 토픽 아이템을 보유하지 않음"이다(트리 표시용 조상 또는 보유물이 아래에
있는 지명 토픽 — 위 목록의 서술과 일치). ⑵ 트리는 **root + depth 2 수준까지의 토픽으로
구성하고, 그 아래 토픽 보유는 rollup으로 접어 올려 준다.**

⑵는 코드·실물 아티팩트로 재검증했다(**검증됨** — rev 5.1, 서비스 자신의
`read_artifact`+`TopicGraph`+`build_tree`를 그대로 실행):

- 매치·보유 토픽 **자신은 깊이와 무관하게 항상 제 노드로 나온다** — `build_tree`가
  `ancestor_path[:depth-1] + [topic_id]`로 경로를 만들므로 잘리는 것은 조상 사슬뿐이다.
  실측: `intelligent dance music`(조상 3단 music→electronic music→electronic dance music)은
  depth=2에서 `[music → intelligent dance music]` — **중간 조상 2개가 생략되고 root 바로
  아래에 걸리며, 토픽 자신은 살아 있다.** 같은 root의 깊은 매치 2개는 root 노드를 공유한다.
  `shown_ancestry(depth=2)`는 `[(music, hops=3)]` — 표시 레벨이 접혀도 hop 거리는 원값이다.
- rollup은 **아래로만**: `descendants(AI)`는 ChatGPT를 distance 1(weight 0.6)로 포함하지만
  `descendants(ChatGPT)`는 자기 자신뿐이다(§2.2 방향성 재확인). 이 접기 규칙은
  `topic/catalog/flatten.py` 한 곳에 살고 랭킹·프로필 트리·카탈로그 detail이 공유한다.
- 조상 사슬 ≥2단인 토픽은 2,605개 중 **560개** — 접힘이 실제로 일어나는 범위.

추천 설계 함의: ⓐ 근거 표시의 계층 문맥은 2단(root→토픽)으로 평평해지므로 "어느 분야의
어느 세부인가"는 노드 위치가 아니라 `distance`로 복원한다. ⓑ 지명 토픽보다 깊은 보유는
라벨이 아니라 `distance>0` 자손 노드 + `contribution`으로 도착한다 — 우리 `matched_topics`
축약(§13-2)이 이 두 신호를 소비해야 한다.

**페이징이 없다.** 양쪽 경로가 같은 resume 계약을 못 내서 일단 뺐다(README 명시). 즉
top-`limit`(≤100) 밖은 존재하지 않는 것으로 취급해야 한다.

**leaf 경로의 stale 처리** — §6에서 프라이버시 문제로 다시 다룬다. 인덱스 행은 남았는데
본문의 visibility가 요청 tier 밖일 때, 낡은 본문 대신 **인덱스에서 유도한 stub**(행의
score·tier만)을 답한다(`single.py:_ranked`). 본문 필드는 보호되지만 `user_id`와 `score`는
나간다. rollup 경로는 본문 재확인에서 tier 밖 아이템을 걸러내므로 stub을 만들지 않는다 —
단 rev 4부터 그 재확인도 eventual이다(§6.3).

---

## §3 카탈로그의 실체 (실측)

정본은 `catalog_seeds/reviewed/*.yaml` 27개 파일이며 git에 커밋돼 있다. `build`가 topic_id를
qid에서 파생해 `catalog_dist/catalog.json`으로 재빌드하므로 **이 파일들이 곧 카탈로그다** —
#17 이후로는 서빙되는 형태(산출물)까지 git에 있어, 실측 스크립트와 서빙 데이터가 같은 커밋에서
대조된다(실제로 산출물 실측: topics 2,605 · edges 2,479 · 전부 active · dump 20260802 — §3의
시드 집계와 정확히 일치).

```
그룹 27  ·  채택 행 2,617  ·  고유 qid 2,605  ·  탈락 10,151  ·  pending 0
dump_version 20260802
깊이:  d0(seed) 170  ·  d1 2,180  ·  d2 267
판정자: 사람 1,818  ·  LLM 799
alias 총 66,694개 (토픽당 평균 25.5)
```

**탈락률 79.5%** (10,151 / 12,768). 카탈로그의 좁음은 Wikidata 커버리지가 아니라
`min_importance`·`max_generality`·`too_specific` 컷의 결과다.

행 2,617 vs 고유 qid 2,605의 차이는 **12개 qid가 두 그룹에 동시 채택**되었기 때문이다
(decision theory·game theory: business-money+science / blockchain: business-money+computing /
esports: games+sports / medical physics: health+science / musical·twist: music+performing-arts 등).
README의 "2605 topics"와 일치한다.

### 3.1 그룹별 분포

| 그룹 | 채택 | 탈락 | 그룹 | 채택 | 탈락 |
|---|---|---|---|---|---|
| health | **517** | 212 | food-drink | 52 | 721 |
| music | **444** | 235 | history | 42 | 461 |
| sports | 248 | 262 | mobility | 37 | 775 |
| places | 213 | 939 | business-money | 35 | 140 |
| society-politics | 204 | 165 | books | 32 | 242 |
| visual-arts | 159 | 149 | language-education | 29 | **1,033** |
| science | 98 | 98 | space | 15 | 131 |
| computing | 78 | **608** | fashion-beauty | 12 | 317 |
| philosophy-religion | 73 | 478 | comics-anime | 9 | 65 |
| games | 68 | 186 | architecture-design | 7 | 191 |
| performing-arts | 61 | 51 | internet-culture | 6 | 248 |
| military | 58 | **1,269** | knowledge-info | **5** | 39 |
| nature-environment | 58 | 486 | people | **1** | 31 |
| screen | 56 | 619 | | | |

health + music + sports = 1,209개로 **전체의 46%**. computing + knowledge-info +
business-money + language-education을 모두 합쳐 **147개**.

### 3.2 지식 도메인의 실제 내용

**computing (78개 전부)**
```
▸ artificial intelligence [24] — AI agent, ChatGPT, GitHub Copilot, LLaMA, Midjourney, Sora,
    Qwen, Grok, Manus, DALL-E, AlexNet, machine learning, NLP, RAG, GNN, reinforcement/
    supervised/unsupervised learning, ensemble learning, explainable AI, generative AI, GPT,
    machine translation, OpenAI Codex
▸ operating system [7] — Android, Windows, macOS, Unix, Palm OS, BlackBerry OS, RTOS
▸ database [2] — relational database, blockchain
▸ programming language [0]   ▸ software [0]   ▸ computer hardware [0]
▸ computer security [0]      ▸ robotics [0]
(언어 37개는 별도 부모: Python, Java, JavaScript, Rust, Go, C++, C#, TypeScript, SQL,
 Haskell, Clojure, Erlang, Scala, Swift, Ruby, PHP, Perl, Lua, COBOL, Fortran, ALGOL, ...)
```
없는 것: **cloud, AWS, Kubernetes, DevOps, distributed systems, API design, observability,
networking, compiler, data engineering, web/frontend/backend 전부.** 608개가 탈락했다.

**knowledge-info (5개, 전부 기관)**: library / archives / encyclopedia / museum / information.
지식 **영역**이 아니라 지식을 보관하는 **장소**다.

**science (98개, 반대로 촘촘)**: physics 19 / chemistry 23 / mathematics 23 / statistics 4 /
materials science 5 + quantum mechanics, biochemistry, thermodynamics. 학문 분류로는 쓸 만하다.

**language-education (29개)**: 12개가 자연어 이름(Arabic, Hebrew, Russian, Indonesian, Sioux…),
education은 자식 0. 탈락 1,033개.

**business-money (35개)**: economics 13 + marketing 6 + accounting 3 + cryptocurrency 2 +
finance 1. 실무 어휘(세무·조직·HR·프로덕트)는 없다.

전문성 어휘가 **원리적으로** 못 들어가는 게 아니다 — science와 AI가 촘촘한 것이 반례다.
**seed 선택의 결과**이므로 `groups.yaml` 수정으로 고칠 수 있다.

### 3.3 카탈로그에 없는 토픽은 어떻게 처리되나

3단 완충이 있다.

1. **근사 grounding (대부분 여기서 처리됨).** marking은 `exact`만이 아니라 `ancestor`(0.85)와
   `related`(0.6)를 허용하고, grounding이 검색 히트의 **조상과 한 단계 자식까지** 후보로 모은다.
   따라서 카탈로그에 없는 니치 관심사는 사라지지 않고 **상위 개념으로 흡수되며 점수만 할인**된다.
   `persona_seeds/user01.json`이 드립커피 88.7 + 커피 76.2를 **둘 다** 가진 것이 그 결과다.
   → **정밀도를 잃고 살아남는 것이 기본 동작이다.**
2. **아무것도 못 붙으면 `unmatched_signals`.** 파일에만 남고 서비스는 읽지 않는다. 조용한 손실.
3. **그 유저는 그 주제에 대해 검색에 존재하지 않는다.** GSI에 행이 없으므로 leaf든 rollup이든
   나오지 않고 **에러도 없다.**

카탈로그 확장 경로:

| 경로 | id | 성격 |
|---|---|---|
| seed 추가 → discover → review → **build → 커밋 → redeploy** | `uuid5(ns,"wikidata:{qid}")` **결정적** | 유일한 정규 경로. 재실행 안전, 반영 단위 = 배포 |
| `groups.yaml`의 `topic:` 블록 | `uuid5(ns,"group:{key}")` | **현재 선언한 그룹 없음** |
| ~~`POST /internal/topic/catalog/topics`~~ | ~~`uuid4` 랜덤~~ | **#17에서 제거** — 운영자 수동 생성·patch·parent 편집·merge 라우트 전부. 랜덤 id 경로도 함께 소멸 |

**없는 경로: 유저/에이전트가 토픽을 제안하는 길.** `TopicOrigin.user`에
"No route writes this any more: the user proposal endpoint is gone"이 남아 있다 —
있었고 **의도적으로 제거**됐다. #17이 운영자 라우트까지 제거하면서 이제 **카탈로그의 유일한
쓰기 경로는 git 커밋**이다. 확장은 전부 사람이 도는 오프라인 루프이고, 반영 단위는 배포다 —
우리 입장에서는 "카탈로그가 요청 사이에 변하지 않는다"가 사실상 보장된다(§13-8의 캐시 질문이
쉬워진다).

---

## §4 전문성 vs 관심 — 3층 분해

담당자 판단(2026-08-21): *"topic이 preference 쪽에서 추출되고 많이 정제된 카탈로그로
서빙되다보니 전문성 보다는 관심 도메인 정도의 분류라 다양한 축의 agent 추천에는 조금 한계가
있을 수 있을거 같기도 합니다만 첫 토픽기반 추천에는 적당할거 같아요"*

이 진단은 맞고, **세 층 모두에서** 그렇다. 층을 나누는 것이 중요한 이유는 **고칠 수 있는 층과
없는 층이 다르기 때문**이다.

| 층 | 상태 | 고칠 수 있나 |
|---|---|---|
| **어휘** | §3.1–3.2. 관심 도메인 분류. science·AI만 예외적으로 촘촘 | ✅ `groups.yaml` seed 확장. 코드 변경 0 |
| **점수 공식** | facets 5개 중 **4개가 관심·애착**(engagement/affinity/duration/recency), 전문성은 `knowledge` 하나. **등가중 평균**(`fmean`) × relation할인 × confidence | ✅ `score_detail`(구 score_inputs)에 원 facets가 남고, **rev 4부터 랭킹 응답에도 실린다**(§4.2). ⚠️ 단 현재 값은 dummy·필드/의미 변경 가능(오너 전언 — §11-18) |
| **근거 출처** | persona **자기 서술**. 프롬프트도 "`knowledge` = 문장이 드러내는 전문성의 깊이". 외부 검증(대화 근거·기여·타인 확인) 없음 | ❌ 구조적으로 없음 |

### 4.1 점수 공식 문제는 1차의 문제다

담당자는 이 한계를 "다양한 축"(=2차 need_type) 문제로 보았으나, **우리 1차 스코프가 이미
"가장 잘 아는 agent"이므로 축이 전문성이다.** 등가중 평균의 결과:

| | knowledge | engagement | affinity | duration | recency | score |
|---|---|---|---|---|---|---|
| 깊이 아는 사람 | **95** | 30 | 30 | 30 | 50 | **47** |
| 열심히 즐기는 사람 | 40 | 95 | 95 | 90 | 100 | **84** |

**애호가가 전문가를 거의 2배로 이긴다.** topic-api의 `score`를 정렬 키로 그대로 쓰면
**1차부터 어긋난다.**

### 4.2 해결책과 걸림돌

`ScoreInputs`는 원 facets를 그대로 보관하고, 설계 의도가 명시적이다 — *"점수는 하나의 숫자이고
그 자체로는 왜인지 말하지 않는다. 입력을 함께 실어 두는 것이 읽는 쪽이 값을 재계산하고
**이견을 낼 수 있게** 한다."* 따라서 우리는 그들의 scalar를 재해석하는 게 아니라
**원자료로 돌아가 우리 정렬 키를 만든다.**

~~걸림돌: `score_inputs`가 랭킹 응답에 없다(N+1)~~ — **rev 4에서 해소됐다.**
`score_inputs`는 `score_detail`로 개명됐고, 랭킹 응답의 `matched[].item.blocks[]`에
`score_detail` 블록(facets·relation·confidence)으로 합성돼 나온다
(`api/structs/user_topic.py:_blocks_of` — 전수 확인). owner당 추가 호출 없이 **검색 한 번으로
재가중 재료가 도착한다.** §11-3은 닫혔다. 단 이것은 재가중의 전제일 뿐이고, §9의 컷
한계(도착하지 못한 후보는 재가중이 구제 못 함)는 그대로다.

**새 걸림돌 — facets 계약이 미확정이다 (오너 확인(전언), 2026-08-24, rev 5).** 현재 facets
값은 **dummy data**이고, **필드 집합 자체가 바뀔 수 있으며 각 값의 의미도 바뀔 수 있다.**
따라서:

- 재료의 **운반 경로**(랭킹 응답의 score_detail 블록)는 확보됐지만, 재료의 **의미**는 아직
  계약이 아니다. §4.1의 knowledge/engagement 대비 계산은 "현 코드의 공식이 이런 성질"이라는
  분석으로는 유효하되, **그 필드들이 그 의미로 존속한다는 가정 위에 키 식을 잠그면 안 된다.**
- ordering 키 식(§13-3)의 확정은 **facets 계약 확정이 선행 조건**이다 → §11-18.
- 우리 어댑터는 facet 필드 이름에 하드바인딩하지 않는다: 모르는 facet은 무시하고, 기대한
  facet의 부재는 null 처우 규칙(§13-3)으로 흘려보내며, 키 계산은 교체 가능한 전략으로 둔다.
  (topic-api 쪽 `Facets`는 `extra="forbid"`라 필드 추가가 그들 쪽에서는 즉시 드러난다 —
  우리 쪽 계약 테스트는 wire 규율대로 실제 payload 고정본으로.)

---

## §5 성능·지연·비용 비교 — rev 14 계획 vs topic-api

### 5.1 측정 가정

**검증됨**: DynamoDB 모듈은 `PAY_PER_REQUEST`(`iac terraform/modules/dynamodb/main.tf:2`) —
읽기 증폭이 곧 달러. AOSS `bourbon-aoss-tokyo-dev`는 이미 존재하며 공유 그룹 `dev-aoss-tokyo`에
**min 2 indexing + 2 search OCU / max 16+16**(`iac terraform/env/dev/main.tf:352-376`), type SEARCH.
topic-api 상한: `SEARCH_MAX_GSI_ITEMS=20000`, `SEARCH_MAX_USER_QUERIES=2000`,
`SEARCH_MAX_DESCENDANTS=50`, `SEARCH_MAX_DEPTH=3`, `SEARCH_MAX_NAME_MATCHES=20`,
`_QUERY_CONCURRENCY=16`, `_STREAM_PAGE_FACTOR=4`. (`CATALOG_CACHE_TTL`은 #17에서 제거 —
카탈로그는 시작 시 1회 파일 로드.)
워커는 pod당 1개(`WEB_CONCURRENCY=limits.cpu=1000m`), prod HPA 2–5.

**가정**: user topic 아이템 ≈0.5KB, 유저당 topic 20개(파티션 ≈10KB), GSI KEYS_ONLY 행 ≈0.14KB,
강한 읽기 1 RCU=4KB / eventual=8KB. rev 14의 N·K는 문서가 "eval로 결정"으로 열어 뒀으므로
변형 4개 × top-50 → owner top-K=3 → 후보 ~180쌍으로 잡았다.

**미확인**: OCU/RCU 단가는 대략치. 정확한 청구는 Tokyo 요율 확인 필요.

### 5.2 지연

| 경로 | DDB 라운드트립 | LLM | p50 추정 | p99 성격 |
|---|---|---|---|---|
| topic-api **leaf** | **2** | 없음 | **10–25ms** | 안정. exact |
| topic-api **rollup** | 스트림 페이지 **순차** 20–250회 + resolve 웨이브 | 없음 | 250–450ms | **초 단위**(1.5–3s), 답은 `exhaustive=false` |
| rev 14 계획 | AOSS 1 + BatchGet 2단(chunk 병렬) | **요청당 판정 1회** | 40–80ms(검색부) **+ 300–1500ms(LLM)** | LLM 지배 |

rollup의 `top_k`는 **한 번에 한 스트림, 한 페이지씩 순차로** 읽는다. 스트림이 31개면 최소 31회
순차 왕복이고, threshold 수렴은 모든 스트림의 bound가 함께 내려가야 진행되므로 서브트리가
넓을수록 느려진다(주석도 "a wide descendant set converges slowly"로 인정).

→ **topic-api는 최악이 나쁘고 rev 14는 평균이 나쁘다.**

### 5.3 읽기 비용 (RCU/요청)

| | 전형 | 상한 |
|---|---|---|
| topic-api leaf | **≈3 RCU** | ~13 (limit 100) |
| topic-api rollup | ~630 RCU (스트림 20 · 후보 유저 200 가정) | **≈6,350 RCU** (GSI 20,000행 ≈350 + resolve 2,000×3) |
| rev 14 계획 | **≈60 RCU** (1단계 45 + 2단계 15) | ≈60 RCU (N·K로 구조적 고정) |

**leaf의 3 RCU는 우리가 상상했던 어떤 구조보다 싸다** — 이 비교의 가장 중요한 발견.

rev 4 정정: resolve가 eventual 읽기로 바뀌어(§2.2) rollup 상한의 resolve 항이 절반이 된다
(≈6,350 → ≈3,350 RCU). 구조 결론(rollup 상한이 크다)은 불변.

~~트래픽과 무관한 고정 읽기(60초 카탈로그 Scan ~313 RCU/워커/분 + 락 아래 블로킹 재적재의
p99 스파이크)~~ — **#17에서 통째로 소멸.** 카탈로그는 이미지 안 파일이라 시작 시 1회 읽고
끝이며, DynamoDB에는 user topic 테이블 요청만 남는다. 초판의 이 비용·스파이크 지적과 §11-13
(stale-while-revalidate 요청)은 구조 변경으로 해소됐다. 대신 성격이 하나 바뀐다: 카탈로그
freshness의 단위가 TTL(60초)에서 **배포**로 커졌다 — 토픽 편집·이미지 업로드가 응답에 닿으려면
redeploy가 필요하다(reload 라우트도 제거됨).

### 5.4 LLM 비용 — 결정적 축

| | LLM이 언제 도는가 | 요청당 토큰 | 규모 특성 |
|---|---|---|---|
| topic-api | **write-time**(persona 변경 시): signal 1 call + signal마다 marking 1 call ≈ 4–6 calls, 후보 40개 프롬프트 → 대략 20–40k input tokens | **0** | persona 변경 횟수 비례 |
| rev 14 | **read-time**(매 요청): 후보 ~60개 × 300토큰 ≈ **12–24k input tokens** | 12–24k | **질의 횟수 비례** |

persona가 한 번 바뀌는 사이 관련 질의가 Q회면 rev 14의 LLM 지출은 **Q배**다. Discovery는 읽기가
쓰기보다 훨씬 잦으므로 Q≫1이고, 상수배가 아니라 스케일 차이다.

**단, "read-time LLM 0"은 우리에게 선택지가 아니다.** topic-api가 read-time LLM을 안 쓸 수 있는
이유는 질의가 이미 카탈로그 어휘로 들어온다고 가정하기 때문이고, 그 정규화 부담을 write-time으로
옮겼다(§2.1). Discovery의 요청은 자유 서술이므로 **expansion 1회는 불가피**하다
(~500–1000 input tokens, 100–300ms). 현실적 하한은 "expansion 1회"이고, rev 14의 판정층은 그 위에
**선택적으로** 얹는 12–24k 토큰이다.

### 5.5 고정 인프라 비용

| | 증분 고정비 |
|---|---|
| topic-api | **0** (DDB 온디맨드만. 테이블·GSI는 iac 추가 필요하나 유휴 비용 없음) |
| rev 14 | AOSS 4 OCU 하한은 **이미 지출 중**(pensieve·bourbon 공유) → 인덱스 추가의 증분은 스토리지 + OCU 여유분. 진짜 증분은 **스트림 파이프라인**: OSIS면 최소 1 Ingestion OCU 상시, Lambda 컨슈머면 거의 0 |

rev 14에 유리한 정정 하나: AOSS 신설 비용을 우려했으나 컬렉션은 이미 있고 하한도 이미 낸다.
불리한 사실 하나: **Q1(OSIS vs Lambda)은 비용 축에서 답이 난다** — 상시 OCU를 사는 OSIS는
이 데이터량에 과하다.

### 5.6 확장 한계

- `find_by_name`은 **O(전체 토픽) 선형 스캔**이고 이벤트 루프 안에서 CPU를 쓴다. 2,605개에서는
  몇 ms지만 10만 규모면 질의당 100–400ms 블로킹이고 워커는 pod당 1개다. 매칭 0건 질의가 최악
  (전체 스캔). **여기가 AOSS가 실제로 필요해지는 지점이며, 색인 대상은 유저 아이템이 아니라
  카탈로그다**(정적, 하루 몇 번 변경 → 스트림 파이프라인 불필요).
- 20개 캡을 통과하는 순서가 관련도가 아니다(§2.1 `ai` 사례).
- 형태소 분석·동의어 확장 없음. decay는 **DAG 거리**만 알고 요청 의도를 모른다.

---

## §6 프라이버시 모델 — 노출 면적을 결정한다

### 6.1 정책 (오너 확인, 2026-08-21)

**유저 토픽 visibility의 기본값은 `private`이며, 이는 우리 서비스의 프라이버시 정책이다.
유저가 직접 public으로 올려야 한다.** 이것은 구현 기본값이 아니라 정책이다.

코드가 이를 강제하는 방식(검증됨):

1. 랭킹이 읽을 수 있는 tier는 `RANKED_TIERS = {public, friends}`뿐이고(#16 —
   `topic/visibility/tiers.py`), 그중에서도 **요청이 명시한 부분집합만** 읽는다(기본 public).
   private/hidden은 rank_key가 아예 안 써져 인덱스에 없다(§1.3의 sparse index).
2. score 주입(`put_score`)은 첫 쓰기에서 `visibility = if_not_exists(..., private)` — 주석:
   *"A topic the user has never configured must not become searchable by everyone."*
3. **주입 경로는 visibility를 쓸 수 없다.** `ScoreRequest`는 `{score, score_detail}`뿐이고
   internal 라우터 어디에도 visibility 쓰기가 없다(전수 확인). rev 4에서
   `score_updated_at`이 사라졌다 — computed-time 단조성 검사를 spec §8이 의도적으로 제거했고,
   주입은 무조건 도착 순서 승리(LWW)다.
4. 올릴 수 있는 건 `PATCH /me/topics/{id}` 하나이고 **edge-auth로 검증된 본인만** 부른다.
   internal에 `/me` 미러가 없다.
5. 반대로 `TopicSettingsPatch`는 `score`를 받지 않는다 — 유저 쓰기가 점수를 나를 수 없다.
   두 writer가 disjoint 속성만 건드리고 `updated_at`만 겹친다(LWW가 올바른 의미).

tier는 독립 플래그가 아니라 **계열**이다: `public ⊂ friends ⊂ private ⊂ hidden`.
`hidden`은 삭제 대신 치우는 것(삭제 라우트 없음)이며 `/me/topics`에만 나온다.
친구 관계는 이 서비스가 저장하지 않는다 — `friends`는 클라이언트가 보내는 라벨이다.
rev 4부터 friends가 **랭킹 가능 tier**가 됐고, "누가 어느 tier를 물을 자격이 있는가"는
topic-api가 판정하지 않는다(spec §7 — 호출자 몫). 우리에게는 관계 정보가 없으므로 추천
서빙은 public 단독으로 시작한다 → §10-9·§11-17.

### 6.2 결과

**의존이 우리 밖으로 나간다.** 필요한 API는 다 있다(`GET /me/topics`,
`PATCH /me/topics/{id}` `{"visibility":"public"}`). 없는 건 **그것을 호출하는 클라이언트
화면**이고, topic-api 레포에도 우리 레포에도 없다. → Discovery 출시가 앱 딜리버러블에 걸린다.

**비용**: `{topic_id}#public#0` 파티션이 희소해진다. 카탈로그와 점수가 완벽해도 토글한 유저가
임계 아래면 빈 결과다. **지배적 리스크가 카탈로그 어휘가 아니라 cold start로 바뀐다.**

**이득**: 유저가 **무엇을** 공개하기로 골랐는지가 그 자체로 신호다. "양자역학"을 공개한 사람은
"그 주제로 찾아와도 된다"는 의사를 표현한 것이고, 추천 표면이 원하는 것은 정확히
**아는 것 + 응할 의사**의 결합이다. facets에서 짜내려던 competence 신호보다 오히려 정직한 축이고,
후보 풀 자체가 이미 걸러진 상태로 온다.

**부수 효과**: 우리 응답의 `matched_topics`는 **대체로** 공개된 것만 담는다 — rev 14가
TOPICSEARCH#·visibility 재확인·TOCTOU에 많은 지면을 쓴 일을 GSI 파티션이 구조로 대신한다.
단 "구조적으로 보장"은 아니다: leaf 경로의 stub(§6.3)이 반례이고, 그것이 닫히기 전까지는
보장이 아니라 "짧은 창의 예외가 있는 기본 동작"이다(rev 7 정정 — 외부 리뷰가 §6.2와
§6.3의 자기모순을 지적).

### 6.3 leaf 경로의 구멍 (정책이므로 지적 대상)

rollup은 본문 재확인으로 보호된다 — `_ranked_in_subtree`가 테이블 읽기에서 tier를 다시
확인하므로 요청 tier 밖으로 바꾼 아이템은 총점에 기여하지 못하고 유저가 탈락한다. 단 rev
4에서 이 읽기가 eventual로 바뀌어(§2.2) 보호가 "강한 일관성 보장"에서 "테이블 복제 지연
수준의 짧은 창 허용"으로 약해졌다 — 인덱스 전파 지연보다 좁은 창이라 실질 차이는 작다.

leaf(`topic/search/single.py:_ranked`)는 다르다. 인덱스 행은 남았고 본문이 이미 요청 tier
밖일 때, 낡은 본문 대신 **인덱스에서 유도한 stub**을 답한다. 본문 필드(descriptions·blocks)는
보호되지만 **`user_id`와 `score`는 그대로 나간다.**

private이 단순 기본값이면 GSI 전파 지연 동안의 사소한 staleness다. 그러나 **공개가 유저의
명시적 행위인 정책**이라면 "이 유저가 이 토픽을 보유하고 점수가 S다"라는 **소속 사실 자체가
보호 대상**이다. 고치는 방법은 간단하다 — stub을 만들지 말고 그 행을 결과에서 제외
(rollup이 이미 그렇게 한다). → §11-4 (**rev 7에서 블로커 승격**)

소비자 쪽 임시 방어(rev 7): stub은 `created_at`/`updated_at`이 **null**로 나간다 — 세
writer 전부가 timestamps를 심으므로(검증됨) null은 인덱스 유래 stub의 강한 신호다. 단
모델은 nullable을 허용하고 테스트도 unstamped를 유효로 취급하므로 이것은 **계약이 아니라
휴리스틱**이다: 보안 보장은 topic-api 수정뿐이고, 소비자 필터는 그때까지의 fail-closed
방어이며 정상 legacy item 오탈락 가능성이 있어 telemetry를 동반해야 한다. 또 하나(rev 7):
철회 전파(GSI·rollup의 eventual read)에 **지연 상한 계약이 없다** — "짧을 것"은 예상이지
보장이 아니므로, 공개 철회의 즉시 반영이 제품 요구인지가 별도 기획 질문이다(§11-20).

### 6.4 서빙 가능성은 곱셈이다

```
서빙 가능성 = 카탈로그 커버리지 × 공개 밀도
              (질의→토픽 매칭률)   (그 토픽을 공개한 owner 수)
```

두 번째 항이 **현재 0**이다(prod 적재 호출자 없음, 토글 UI 없음). 따라서 지금 잴 수 있는 것은
첫 항뿐이고, 그것만으로 "1차에 적당한가"를 답할 수 없다. 대신 **출시 수용 기준을 지금
정의할 수 있다** → §12.

Alpha는 내부 대상이므로 **내부 코호트에게 토글을 요청하는 것이 정당한 부트스트랩**이다.

### 6.5 별도 위험: 데모 모드

`DEMO_SAMPLE_USERS=true`는 **검증된 caller id를 해시 스탠드인으로 대체**한다. 실데이터
환경에서 켜면 모든 호출자에게 남의 계정을 보여준다. 기본 off, k8s 미설정, README도 경고.
이 규율이 유지되는지 계속 확인해야 한다.

---

## §7 배포·운영 상태 (검증됨) — 지금은 dev에도 뜨지 않는다

| # | 갭 | 근거 | 소관 |
|---|---|---|---|
| 1 | **테이블·인덱스의 iac 부재** — 필요한 것: user-topic 테이블 1개 + **GSI 2개**(#16: `topic-rank-index`·`topic-holder-index`). rev 4 상태: topic-api 문서는 "테이블은 iac 소관, 인덱스 2개는 AWS 콘솔 수작업 — **완료**"로 기록(`docs/dynamodb-key-design.md`, 커밋 b974d4b·0085d47). 그러나 **iac origin/main `592e34c` 재grep에도 테이블 선언이 없고**, 콘솔 작업은 레포 어디서도 검증되지 않는다 — `scripts/dynamodb/create_tables.py`가 배포 인덱스의 유일한 명세라고 그들 스스로 기록. dev 실물 존재 여부는 **미확인** | topic-api 문서 + iac 재grep | 인프라 |
| 2 | **IRSA 권한 부족** — `bourbon-app`의 DynamoDB 문장은 `bourbon-agent` 테이블 ARN 1개 + `/index/*`로 한정이라 새 테이블 ARN 추가 필요. ~~`dynamodb:Scan` 부재~~는 #17로 **문제 아님**(카탈로그 Scan 소멸 — 기존 액션 목록으로 충분) | `iac terraform/modules/iam/service/service_roles.tf:116-132` | 인프라 |
| 3 | **게이트웨이 미등록** — bourbon-api dispatch에 `/api/svc/topic/` 블록 없음 → public 표면 외부 도달 불가. internal prefix(`/api/internal/svc/topic`)도 게이트웨이 IP gate 라우팅이 관례이나, 우리는 메시 내부에서 직접 호출하므로 어느 쪽도 우리 게이트가 아님 | bourbon-api origin/main `k8s/base/api-svc-dispatch.yaml` | bourbon-api |
| 4 | **prod 적재 경로 미구현** — 호출자의 정체는 확정됐다(persona→topic 파이프라인, §1.5). 미구현인 것: ⑴ bourbon-agent의 persona extractor 자체(`save_persona` 호출자 0건) ⑵ persona→topic 파이프라인이 어디서 무슨 트리거로 도는지. 현 CLI는 디스크에만 쓴다 | §1.5 | extractor 체인 |
| 5 | **internal `AuthorizationPolicy` 없음** — 메시 내 누구나 호출 가능 | README 명시(accepted risk) | topic-api |
| 6 | **공개 토글 UI 없음** — §6.2 | 두 레포 모두 부재 | 앱/클라이언트 |

우리는 internal을 호출하므로 3번은 우리 게이트가 아니다. **4번과 6번이 우리 출시의 실질
게이트**이고, 1·2번은 그보다 먼저 온다.

운영 특성(고장은 아니지만 알아야 할 것): 워커 pod당 1개 + CPU 바운드 `find_by_name`(§5.6),
rollup 상한이 큼(§5.3), 인덱스 키 누락 아이템이 조용히 사라짐(§1.3), 카탈로그·이미지 반영
단위가 배포(#17 — §5.3). dev 한정: docs가 prefix 아래로 이동해 게이트웨이 경유 + oauth2-proxy
SSO + edge-auth 이중 게이트를 받는다(#14) — 우리와는 무관, internal 미러의 docs는 여전히
port-forward 전용.

---

## §8 확정된 방향 — 축의 이전

### 8.1 결정: topic-api를 축(axis)으로 삼는다

**근거 두 개.** 순서가 중요하다 — 첫째가 담당자 근거이고 더 강하다.

1. **유저에게 보이는 라벨의 일치** (담당자, 2026-08-21). 유저는 자기 프로필에서 topic-api의
   라벨(ko/en/ja 큐레이션, 2단 트리, 이미지)을 본다. 추천 이유(`matched_topics`)가 우리가 따로
   뽑은 어휘로 나오면 **같은 개념이 화면에서 두 이름으로 존재**한다. 내부 구현 세부가 아니라
   제품 결함이고, 한번 노출되면 되돌리기 어렵다. 우리가 rev 12–13에서 잠근 용어 규율
   ("이름 ≠ 의미", 소유권은 생애주기로)을 제품 표면에 적용한 것과 같은 결론이다.
2. **공통 축 없이는 사람을 서로 순위 매길 수 없다.** 개방 어휘에서는 유저 A의 "커피 핸드드립"과
   B의 "드립 커피"가 다른 문자열이고, 비교하려면 read-time에 동의어를 해소해야 한다 —
   그것이 rev 14의 판정층이 필요했던 이유다. **rev 14의 read-time LLM은 정밀도를 위한 사치가
   아니라 개방 어휘를 택한 대가였다.** 카탈로그는 그 해소를 적재 시점에 사람 리뷰까지 붙여
   끝내므로 read-time LLM 없이 랭킹이 성립한다. 이것은 더 싼 것이 아니라 **문제를 더 잘 쪼갠 것**이다.

카탈로그가 추가로 주는 것: 동명이의 통제, 계층 → rollup/decay, 재추출을 넘어 안정적인 id,
`score_detail`로 감사 가능한 점수, popularity 항이 없는 순수 per-user facet 점수
(우리 reputation 원칙과 충돌 없음).

### 8.2 금지: 병렬 두 시스템

같은 페르소나 위에 두 extractor, 두 저장소, 두 랭킹 의미, 두 visibility 모델, 두 id 공간을
두는 것. 쓰기 비용이 두 배가 되고, 두 경로의 결과를 **합칠 수 없다**(카탈로그 경로의 scalar와
우리 경로의 LLM verdict는 비교 대상이 아니다). "둘 다"는 **비대칭적으로만** 성립한다 —
하나는 축, 하나는 보정.

### 8.3 3단 계획

**A (지금) — 순수 소비, 저장소 0.**
expansion(작은 LLM 1회) → `GET /api/internal/svc/topic/search/topics` → **구체 토픽 2–3개를
병렬 조회**(`/topics/{id}/users`) → 우리 후처리(self-exclusion, eligibility, cap,
`matched_topics` 조립, 실패 3분기). 목적은 기능이 아니라 **측정**(§12).
(id 리스트를 한 번에 받는 랭킹 라우트는 없다 — `SearchQuery.topic_ids`는 서비스 층에
존재하나 라우트는 이름 검색만 리스트 경로를 탄다. 그때까지 병합은 우리 RRF — §11-16.)

넓은 토픽 하나로 rollup을 부르는 것보다 낫다: 잎에 떨어지면 싸고(3 RCU×3) 지연이 평탄하며
(병렬 2 RTT) `exhaustive=True`가 보장되고, 어느 확장어가 맞았는지 귀속이 응답 단위로 남는다 —
rev 14 §3의 "변형별 `_msearch` 독립 검색 + RRF"와 정확히 같은 모양이다. 병합 규칙은 우리가 정한다.

**단, leaf/rollup은 우리가 고르는 게 아니다 (rev 2 정정).** 같은 라우트에서 서비스가 토픽의
서브트리를 보고 고른다(§2.2 — `if len(weights) == 1`). "구체적인" 토픽도 활성 자손이 있으면
rollup이 된다 — 실측: `machine learning`은 잎이지만 `database`는 자식 2개(blockchain,
relational database)로 rollup이다. 그러므로 위의 비용·지연 보장은 **확장어가 실제 잎에 떨어졌을
때만** 성립하고, 우리 규칙은 "잎 선호, rollup 응답도 정상 경로"다. 완화 근거: 깊이 분포상
d1이 2,180/2,617이고 d2가 267뿐이라 **구체 토픽의 대부분은 실제로 잎이다.** 사전 판별은
불가능에 가깝다 — detail의 `children`은 **level-1 토픽에만 채워지고 그 외에는 설계상 빈
배열**(`topic/catalog/flatten.py`: "Empty for a topic that is not level 1")이므로, d1 토픽이
d2 자식을 가져도 detail은 빈 children을 답하는데 rollup은 깊은 그래프를 걷는다. 사후 판별은
쉽다: 응답 `matched`에 `distance > 0`이 있으면 rollup이었다.

**B (측정이 부족하다고 말하면) — 우리 코드가 아니라 카탈로그를 늘린다.**
computing/science seed 확장 + `min_importance` 하향 제안. `groups.yaml` 한 파일이고 수혜자가
우리만이 아니다. **코드 없이 얻는 recall이 가장 싼 recall이다.**

**C (그래도 남는 갭에만) — 보정층 두 개.**
① **rerank(gate 아님)**: 이미 랭킹된 top-20에만 판정층. LLM ~6k 토큰, +200–400ms.
   rev 14 §1-⑪의 tiered judging 레버와 같은 취지이며 원안의 1/3 이하 비용.
② **unmatched 채널**: 카탈로그로 표현 안 되는 질의를 버리지 않고 기록 → seed 후보로 환류.
   정말 필요해지면 그때 보조 인덱스. 그 인덱스도 **유저 아이템이 아니라 "카탈로그로 못 잡힌
   관심사"만** 담으므로 스트림·epoch·TOCTOU는 여전히 불필요하다.

---

## §9 rev 14 처분 — 폐기 / 승계

| rev 14 항목 | 처분 | 이유 |
|---|---|---|
| §2 전용 테이블 + 아이템 5종 스키마 | **폐기** | 저장 주체가 topic-api |
| 3-item transaction · `publication_epoch` · `judge_revision` · `claim_digest` | **폐기** | 우리가 쓰지 않으므로 동시성 계약의 주체가 아님 |
| TOPICSEARCH# projection / 전역 discoverable 계약 | **폐기** | rank-index 파티션 `{topic_id}#public#0`이 같은 일을 함 |
| §4 2단계 both-strong BatchGet 계약 | **폐기** | 읽기 주체가 topic-api. rollup이 본문 재확인(rev 4부터 eventual — §6.3) |
| 스트림 색인 파이프라인 (Q1·Q2·Q9) | **폐기** | 색인할 우리 데이터가 없음 |
| extractor 협의 Q5·Q13·Q14 | **폐기** | topic 저장·projection의 협의 상대가 사라짐 — 저장은 topic-api 소관. extractor 체인과의 새 협의 항목은 §11이 대체 |
| AOSS 인덱스 신설 | **유예** | 카탈로그 2,605개 동안 정당화 안 됨. 필요해지면 **카탈로그만** 색인 |
| §1-⑪ relevance 판정층 | **승계, gate→rerank로 격하** | top-20 재정렬 |
| 실패 의미 3분기(422 / 200+empty / 503) + 오귀속 금지 | **승계** | topic-api는 매칭 0건도 `200 + 빈 items`로 답한다 → **우리가 구분해야 함** |
| ordering contract (gate→filter→tiebreak) | **승계, 재해석** | 아래 |
| self-exclusion · 즐겨찾기=tiebreak only · popularity prior 금지 | **승계** | topic-api에 self-exclusion 없음 |
| 판정 입력 텍스트 전부 비신뢰 취급 | **승계** | 카탈로그 description·유저 description 모두 대화/LLM 유래 |
| gate 3종 직교(maturity/safety/privacy) | **승계** | privacy는 §6이 구조로 보장, maturity 입력은 §11-6 미해결 |
| best-effort 입력 선언(rev 14 §1-①) | **승계 (주체 이전)** | 사슬이 여전히 deferq at-most-once로 시작하고 bourbon-agent ingest는 logged-and-dropped다(§1.5). 우리는 freshness를 가정하지 않고, gate 튜닝은 undercount-robust여야 한다 |

**ordering contract의 재해석 — 그리고 그 위의 정정.**
우리는 "scalar score 금지"를 잠갔고 topic-api는 scalar를 준다. 그 규율의 실질은 "gate를 점수로
사고팔지 말라"이며 여전히 유효하다. 그래서 형태는 `gate(우리) → 정렬 키 → 우리 결정적 tiebreak`.

**단, 그 정렬 키는 topic-api의 `score`가 아니다.** §4.1에서 보인 대로 그 점수는 관심 강도이고
우리 질문은 전문성이다. 따라서 **facets 원자료에서 우리 정렬 키를 우리가 만든다.**
(이 문서 작성 중 "그들의 score를 정렬 키로 쓴다"고 먼저 적었다가 §4.1의 계산으로 철회했다.
재설계는 철회된 쪽을 되살리지 말 것.)
→ **ordering 키의 소유권은 우리에게 있다.**

**그리고 재가중의 한계 — 컷은 그들의 점수로 일어난다 (rev 2 추가).** GSI 정렬 키가 `score`이고
(`ScanIndexForward=False`), 응답은 상위 `limit`(≤100)까지이며 페이징이 없다. knowledge 95짜리
전문가의 저장 score가 47이면, 그 토픽에 score가 더 높은 보유자가 100명 넘게 있을 때 **그
전문가는 우리 손에 도착하지 않는다.** 재가중은 도착한 것의 순서만 바꾼다. §12.3의 "재가중이
순위를 바꾸는지" 계측으로는 이 손실이 **보이지 않는다** — 컷 밖은 관측 밖이다. 선택지 셋:

- **(a) Alpha 수용 (권고)**: 항상 `limit=100`으로 받고 재가중. Alpha는 공개 밀도가 낮아(§6.4)
  토픽당 공개 보유자가 100에 닿을 가능성이 낮다. **만료 조건을 명시한다**: 토픽당 공개 보유자
  수가 100에 접근하면 이 가정이 깨진다 — §12.3의 컷 경계 계측이 만료를 알린다.
- **(b) topic-api에 expertise 접근 경로 요청**: 정렬 파라미터 또는 두 번째 정렬 GSI.
  rev 4에서 해소된 §11-3(응답에 재료 싣기)과는 크기가 다른 요청이므로 별도 항목(§11-15)이고,
  (a)의 측정이 필요를 증명한 뒤에 꺼낸다.
- **(c) 주입 점수 공식 변경**: 공식 소유권은 extractor 쪽이고 그 score는 그들 제품 UI
  (`/me/topics` 트리의 점수 표시)에도 쓰인다. 우리 사정으로 바꾸자기 어렵다 — 가능성만 기록.

정렬 키 자체의 하위 결정 두 개는 §13-3의 몫이다: **`score_detail`(구 score_inputs)이 null인
아이템의 처우**
(주입 전 아이템·breakdown 없는 주입이 실존한다 — 뒤로 보내면 주입이 늦은 전문가를 죽이고,
score로 대체하면 §4.1 문제가 그 아이템에만 되살아난다), 그리고 **`relation`의 처리**
(extractor는 `related`=인접 분야도 붙인다 — "가장 잘 아는"에게 related 보유는 전문성이 아니라
인접성 신호이므로 필터 또는 강한 할인. `score_detail.relation`이 원값으로 남아 있어 가능하다).

---

## §10 우리(agent-recommendation-api)가 소유하는 것

1. **어댑터 + 계약 테스트** — topic-api 응답 스키마 변화를 조용히 먹지 않도록.
   우리 wire-contract 규율(계약 테스트 payload를 consumer model에서 유도 금지)이 그대로 적용된다.
2. **expansion 규칙 — 라벨 생성 규칙(§2.1)에서 유도한 R1–R7 (rev 4 확장)**:
   - **R1 축소가 기본 방향.** 질의가 라벨보다 길면 0건(방향 비대칭)이므로 명사구를 추출해
     긴 형태부터 점진 축소한다(실측: 핸드드립커피추출법 0 → 드립커피 1 → 커피 8).
   - **R2 조사·활용 제거는 우리 몫.** 정규화는 공백·대소문자만 접는다 — "머신러닝으로"는
     라벨 "머신러닝"에 안 걸린다.
   - **R3 언어 병렬 프로브.** 언어별 label/alias 집합이 달라 결과가 다르다(실측: 머신러닝 1 /
     기계학습 4 / machine learning 5). ko·en·한자어 동의어를 모두 생성해 **qid 기준 union**.
   - **R4 Wikidata 정식 명칭으로 사상.** alias 사전은 Wikidata alias 한정 — expansion
     프롬프트에 "Wikidata 항목명처럼 써라"를 제약으로 넣는다. 카탈로그에 없는 개념은
     expansion으로 해결 불가 — seed 요청 채널(§8.3-B)로 보낸다.
   - **R5 짧은 needle 금지 + 캡 인지.** `ai`가 560건을 매칭하고 삽입 순 캡 20을 무관한
     것으로 채운다(§2.1). 최소 길이 기준(영문 4자+·한글 2자+ 수준)을 두고, **광역 프로브
     1회보다 정밀 프로브 여러 회**가 구조적으로 유리하다.
   - **R6 공백 변형은 생성하지 않는다.** 정규화가 흡수한다(드립 커피=드립커피).
   - **R7 grounding→선별→id 랭킹 분리.** `/search/topics`의 is_match 트리(인메모리, 저렴)로
     후보를 받고, 관련도 선별은 우리 2-tier entity linking(candidate-gen + LLM rerank)이,
     랭킹은 확정 id로 `/topics/{id}/users` fan-out + RRF가 맡는다(§8.3-A).
3. **실패 의미 3분기** — `/search/topics` 결과로 "토픽이 없다"(→422)와 "토픽은 있으나 공개
   보유자 0"(→200+empty)을 우리가 갈라야 한다. topic-api는 둘 다 200+빈 items로 답한다.
4. **ordering 키** — facets 기반 전문성 가중(§9). 단 facets 계약 확정(§11-18) 전에는 식을
   잠그지 않고, 어댑터는 facet 이름에 하드바인딩하지 않는다(§4.2).
5. **self-exclusion·제외 집합** — 우리 후처리로 확정(2026-08-24 결정, §11-5 철회).
   fan-out 100 대비 countable 제외 목록이라 정확성 손실 논거 소멸.
6. **eligibility (Q12)** — `AllowAllEligibilityProvider`는 여전히 stub. topic-api는 이것을 모른다.
7. **불완전성 플래그 로깅·게이트** — `exhaustive=false` / `unranked_topics>0` /
   `truncated_descendants>0`를 품질 저하로 다룬다.
8. **잎 선호 fan-out + 병합(RRF)** — §8.3-A. leaf 강제는 불가능하므로 rollup 응답도 정상 경로.
9. **tier 집합 결정** — friends가 랭킹 가능해졌고(#16) 자격 판정은 호출자 몫이다(spec §7).
   우리에게 관계 정보가 없으므로 **public 단독으로 시작**하고, friends 사용은 별도 제품
   결정으로 미룬다(§11-17).

---

## §11 열린 질문 (수요일 논의 안건, 우선순위 순)

| # | 질문 | 소관 | 성격 |
|---|---|---|---|
| 1 | **공개 토글 UI의 소유자와 일정.** 그리고 공개 대상에 LLM이 쓴 `descriptions`(그 유저에 대한 한 문장, rev 4부터 3언어)가 포함되는지. **유저 편집 경로는 rev 4에서 사라졌다** — `PATCH /me/topics`는 visibility만 받고 descriptions는 extraction 소유 속성이 됐다(#18·#20). 유저가 자기 서술을 고칠 수 없는 채 공개 여부만 고르는 구조가 제품 의도인지 확인 필요 | 앱 + 기획 | **블로커** |
| 2 | **넓은 토픽 + 좁은 토픽 동시 부착을 계약으로.** 서브트리 걷기는 아래로만 간다(§2.2) — "커피"만 붙은 유저는 "드립커피" 질의에 안 나온다. 지금은 프롬프트가 강제하나 **프롬프트는 계약이 아니다.** 놓치면 우리 코드로 복구 불가 | extractor | **비가역** |
| 3 | ~~`score_inputs`를 랭킹 응답에 추가~~ — **rev 4에서 해소.** `score_detail`로 개명돼 `matched[].item.blocks[]`에 블록으로 실린다(§4.2). N+1 소멸. 컷 문제(§11-15)는 별개로 남음 | ~~topic-api~~ | **해소** |
| 4 | **leaf 경로 stub이 `user_id`+`score`를 공개하는 문제**(§6.3). rev 4에서도 유지(stub이 행의 tier까지 명시하는 형태로 정리됐을 뿐 노출은 동일). 정책상 소속 사실도 보호 대상. **rev 7에서 블로커 승격**(외부 리뷰 수용): 유저가 토글할 수 있게 되는 순간 = 우리 출시 시점에 창이 열리므로 user-facing 출시 게이트에 연동. 소비자 임시 방어(timestamps-null 필터)는 §6.3 — 계약 아님 | topic-api | **블로커** |
| 5 | ~~self-exclusion / `exclude_user_ids`를 서버측 cap 앞에~~ — **철회, 우리 후처리로 확정(2026-08-24 결정).** 원 논거(limit=20에서 1명 빼면 20번째 후보가 안 옴)는 설계가 fan-out `limit=100`·최종 `max_results=3`으로 잡히며 실질 소멸했고, 제외 목록(requester+추후 room_members)은 countable이라 후처리 오버헤드가 무시 가능. 제외 집합 인터페이스는 설계 문서 S4 | ~~topic-api~~ | **철회** |
| 6 | **maturity gate의 입력.** 우리 gate 입력인 "근거 개수"가 topic-api에 없다. 대용은 `facets.knowledge` + `confidence` + `updated_at`(rev 4에서 `score_updated_at`은 속성째 삭제)인데 "얼마나 깊은가"와 "LLM이 얼마나 확신하나"는 다른 것이다. gate를 무엇 위에 세울지 지금 정해야 뒤집지 않는다 | 우리 + extractor | 중간 |
| 7 | **철회 경로.** 유저가 다시 private으로 내리면 GSI에서 빠지므로 절반은 정책이 해결한다. 남는 것은 "관심이 식었는데 유저가 안 내린 경우"를 extractor가 어떻게 다루는가(score 0 주입? `removed_topics` 반영?) | extractor | 중간 |
| 8 | **`find_by_name` 정렬 근거.** 20개 캡 통과 순서가 dict 삽입 순이다. exact label 일치 우선 + `importance` 내림차순만으로도 크게 달라진다. README도 "this service has none to give"로 인정 | topic-api | 중간 |
| 9 | **토큰 단위 매칭.** 질의가 라벨의 부분문자열이어야 하는 제약으로 긴 질의가 항상 0건이다. 질의를 공백으로 쪼개 하나라도 걸리면 후보로 두는 것만으로 recall이 오른다 | topic-api | 중간 |
| 10 | **페이징 복귀** — 현재 top-`limit`(≤100) 밖은 존재하지 않는 것으로 취급해야 한다 | topic-api | 낮음 |
| 11 | **`unmatched_signals` 노출** — 이미 "카탈로그 갭을 드러내기 위해" 만든 필드인데 파일에 갇혀 있다. seed 제안의 근거 데이터 | extractor | 낮음 |
| 12 | 배포 게이트 §7의 1·2·5 | 인프라 / topic-api | 배포 시점 |
| 13 | ~~카탈로그 캐시 stale-while-revalidate~~ — **#17에서 구조 변경으로 해소**(시작 시 1회 파일 로드, TTL·Scan·블로킹 재적재 자체가 소멸) | ~~topic-api~~ | **해소** |
| 14 | **persona→topic 추출의 입력 슬롯.** sharable만인지 private 포함인지(§1.5). private 포함이면 LLM이 쓴 per-topic `descriptions`가 private 서술의 뉘앙스를 실어 나를 수 있다 — §11-1의 description 공개 여부와 **같이** 결정해야 한다. 슬롯 텍스트(3필드)와 현 CLI 입력(풍부한 마크다운)의 밀도 차이로 facets 품질 재검증도 필요 | extractor + 기획 | 높음 |
| 15 | **expertise 접근 경로**(정렬 파라미터 또는 expertise용 두 번째 GSI) — §9 컷 문제의 (b)안. **(a)안의 컷 경계 계측이 필요를 증명한 뒤에** 꺼낸다 | topic-api | 측정 후 |
| 16 | **id 리스트 랭킹 라우트 (rev 4 신설 → rev 6에서 우선순위 하향).** `SearchQuery.topic_ids`는 서비스 층에 이미 리스트고 라우트만 없다. 그러나 재평가 결과 A단계에서는 **써도 안 쓸 라우트**: ⑴ 다중 id 병합 총점 = Σ weight×score라 그들 score(관심 편향)가 cross-topic 가중에 재유입 — RRF는 순위만 융합해 이를 차단 ⑵ 병합 후 top-100 컷이라 per-topic 100×N보다 후보 풀이 좁음 ⑶ 다중 id는 무조건 rollup 경로(threshold·예산·exhaustive 불확실) vs per-topic leaf는 2 RTT·exhaustive=True. **발동 조건**: 확정 topic 수 증가로 fan-out 비용이 실측 문제 될 때, 또는 expertise 정렬(§11-15) 이후 그들 병합 의미를 원하게 될 때 | topic-api | 조건부 (측정 후) |
| 17 | **friends tier 사용 여부 (rev 4 신설).** friends가 랭킹 가능해졌고 자격 판정은 호출자 몫(spec §7). "추천 서빙이 friends를 물어도 되는가"는 제품 결정이고 관계 정보가 우리에게 없다 — Alpha는 public 단독(§10-9) | 기획 + 우리 | 중간 |
| 18 | **facets 계약 확정 (rev 5 신설 — 오너 전언 2026-08-24).** 현재 facets는 dummy이고 **필드 집합·값 의미가 모두 변경될 수 있다.** 확정해야 할 것: ⑴ 최종 필드 집합과 각 필드의 의미(특히 전문성 축이 어느 필드에 남는가) ⑵ 실데이터 주입 시점 ⑶ 변경 통지 채널(우리 ordering 키 식이 이 계약에 결합된다 — §4.2·§13-3). **이 계약 확정 전에는 키 식을 잠그지 않는다** | extractor + topic-api | **높음 (키 식의 선행 조건)** |
| 19 | **랭킹 응답에 `strategy`(leaf\|rollup) 필드 (rev 7 신설).** 소비자의 경로 판별은 `distance>0` 관측뿐인데 이는 충분조건이라(root만 보유한 유저·빈 결과에서 판별 불가) 정확한 계측·비용 귀속이 안 된다. 응답 1필드 | topic-api | 낮음 |
| 20 | **공개 철회의 즉시성 요구 (rev 7 신설).** 철회 전파(GSI 제거·rollup eventual read)에 지연 상한 계약이 없다(§6.3). "철회가 즉시 반영돼야 하는가"가 제품 요구면 topic-api 쪽 별도 해결 필요, 아니면 "짧은 창 수용"을 정책으로 명문화 | 기획 + topic-api | 중간 |

1·2는 **extractor 계약이 열려 있는 지금만 싸게 들어간다.** 나중에 바꾸려면 재추출과 데이터
마이그레이션이다.

---

## §12 측정 계획

### 12.1 지금 잴 수 있는 것 — 카탈로그 커버리지

eval 코퍼스의 질의·앵커를 2,605개 카탈로그에 대조해 다음을 낸다:

- **exact 매칭률** — 질의가 토픽 라벨/alias에 직접 걸리는 비율
- **ancestor-only 매칭률** — 상위 개념으로만 흡수되는 비율(정밀도 손실을 안고 살아남는 경우)
- **전무율** — 어떤 토픽에도 안 걸리는 비율
- **캡 오염률** — 20개 캡에 걸리면서 상위 20개에 관련 토픽이 없는 비율(`ai` 유형)

이것이 "1차에 적당한가"를 감이 아니라 수치로 답한다. 재현 스크립트는 부록 B.

**코퍼스 선정 주의 (rev 2)**: 기존 eval 코퍼스의 질의·앵커는 memory-api 앵커 세계에서 설계됐다.
그대로 대조하면 "옛 시스템의 어휘가 새 카탈로그에 있는가"를 재게 된다. Discovery 실사용 질의
표본(또는 그에 가까운 재작성)을 별도로 정의하고, **무엇을 재는 코퍼스인지를 결과에 명시**한다.

### 12.2 아직 잴 수 없는 것 — 공개 밀도

prod 적재 호출자도 토글 UI도 없어 현재 0이다. 대신 **출시 수용 기준을 지금 정의한다**:

- 질의당 gate 통과 공개 owner **하한**(예: ≥3). 미달이면 200+empty로 정직하게 답하고
  노이즈를 서빙하지 않는다
- 그 하한에서 역산한 부트스트랩 규모: 내부 코호트 몇 명 × 몇 토픽

### 12.3 런타임 계측기 (A단계에서 반드시 넣을 것)

- expansion 결과의 `/search/topics` 0건 비율 = **카탈로그 커버리지 지표**
- 매칭됐으나 공개 보유자 0 비율 = **공개 밀도 지표**
- `exhaustive` / `unranked_topics` / `truncated_descendants` 분포
- 우리 ordering 키와 topic-api `score` 순위의 불일치도(전문성 재가중이 실제로 순위를 바꾸는지).
  **단 실데이터 주입 후에만 의미 있다** — 현재 facets는 dummy(§4.2, 오너 전언 2026-08-24)라
  dummy 위 측정은 공식의 성질이 아니라 dummy 생성기의 성질을 잰다
- **컷 경계 계측 (§9-(a)의 만료 감시)**: 토픽당 공개 보유자 수 분포, 그리고 `limit=100` 응답
  마지막 행 부근의 knowledge 분포 — 컷 밖 손실이 시작되는 순간을 잡는다

---

## §13 재설계가 답해야 할 질문 (Fable 입력)

이 문서는 사실과 결정을 담았고, **설계는 하지 않았다.** 새 설계가 답해야 하는 것:

1. **호출 형태.** expansion → `/search/topics` → leaf fan-out → 병합의 각 단계를 어떤 컴포넌트가
   소유하는가. 기존 `discovery/` 구조(grounding / ranking / recommendation 단계 분리)의 어디에
   매핑되는가. NeedType·stance 파이프라인은 삭제 대상이다.
2. **병합 규칙.** 여러 leaf 결과를 owner 단위로 합칠 때 RRF인가 다른 것인가. topic별 기여도를
   어떻게 `matched_topics`로 축약하는가(대표 topic 선택 규율 — rev 14가 ranking 단계로 잠근 것).
3. **ordering 키의 정확한 식.** **선행 조건: facets 계약 확정(§11-18) — 현재 필드·의미가
   미확정(dummy)이므로 그 전에는 식을 잠그지 않고, 어댑터는 facet 이름에 하드바인딩하지
   않는 교체 가능한 전략으로 설계한다(§4.2).** 그 위에서: facets에서 전문성 키를 어떻게 만드는가.
   `knowledge` 단독? 가중합? `confidence`를 곱하는가? **`relation=related`는 필터인가 할인인가?**
   **`score_detail`이 null인 아이템은 어디에 놓는가?** §9 컷 문제의 (a)/(b) 중 무엇으로
   시작하고 만료 조건은 무엇인가. 그리고 그 식이 **gate와 섞이지 않는다**는 것을 어떻게
   구조로 보장하는가.
4. **실패 3분기의 판정 지점.** `/search/topics` 0건 → 422를 어디서 판정하는가.
   expansion이 여러 변형을 냈고 일부만 0건일 때의 규칙.
5. **eligibility(Q12)의 결합 지점.** topic-api는 eligibility를 모른다. leaf 결과를 받은 뒤
   필터하면 cap이 깎인다(§11-5와 같은 문제). 서버측 파라미터가 없을 때의 차선책.
6. **rerank 진입 조건.** C단계 판정층을 언제 켜는가. 항상? 특정 신호에서만?
   그 신호를 무엇으로 측정하는가.
7. **어댑터 경계.** topic-api 응답 모델을 우리 도메인 타입으로 어디서 변환하는가.
   composition root 규율(real provider만)과 어떻게 맞추는가.
8. **캐시.** #17로 질문이 쉬워졌다: 카탈로그 변경의 반영 단위가 topic-api의 **배포**이므로
   요청 사이 변동이 사실상 없다. `/search/topics` 결과를 우리가 캐시한다면 TTL은 그들의 배포
   주기보다 짧으면 충분하다. 남는 결정: 캐시 키(질의 정규화 형태)와, 그들의 배포를 우리가
   감지할 신호가 필요한가(없어도 짧은 TTL로 족한가). 산출물의 `built_at`/`dump_version`은
   응답에 노출되지 않는다.
9. **rollup 수용 규칙.** 확장어가 잎이 아닐 때(자손 있는 토픽) rollup을 그대로 쓰는가, 자손
   잎으로 내려가 재질의하는가. 사전 판별은 사실상 불가(§8.3-A — detail `children`은 level-1
   전용)이므로 사후 판별(`matched`의 `distance > 0`)로 무엇을 다르게 처리하는가 —
   불완전성 플래그·비용 게이트가 rollup 응답에서만 켜진다.
10. **cold-start UX.** 공개 보유자가 임계(§12.2) 미달일 때 recommend가 무엇을 답하고,
   bourbon-agent의 recommend_agents tool이 그것을 유저에게 어떻게 말하는가(현 mock은 모든
   실패를 "unavailable"로 뭉갠다 — §1-⑩ 위반). 정직한 empty의 wire 표현.

---

## 부록 A — 근거 인덱스

`../bourbon-topic-api` (초판 HEAD `296723d` → rev 3 `107f5cd` → rev 4 HEAD `80c650f`):

| 주장 | 위치 |
|---|---|
| 표면별 라우터 마운트 (#19) | `api/depends/surfaces.py` (구 `role.py` — 삭제) |
| leaf 경로 · stub 처리 | `topic/search/single.py` |
| rollup · 서브트리 · 분기 | `topic/search/service.py` |
| threshold 알고리즘 | `topic/search/threshold.py` |
| 스트림 bound | `topic/search/streams.py` |
| `find_by_name` · normalize · descendants | `topic/catalog/graph.py` |
| 카탈로그 산출물 포맷·로더 (#17) | `topic/catalog/artifact.py` (`catalog_dist/catalog.json`) |
| 산출물 빌드·merge ledger 검증 (#17) | `topic/catalog_import/build.py` |
| merge 기록 / 아이템 이송 CLI (#17) | `cli/catalog_import/merge.py`, `topic/user_topics/migration.py` |
| 시작 시 1회 카탈로그 로드 (#17) | `api/depends/services.py:startup` |
| id 파생 규칙 (#17부터 전부 파생·랜덤 경로 제거) | `topic/catalog/ids.py` |
| ~~카탈로그 Scan·캐시~~ | ~~`topic/catalog/repository.py`·`cache.py`~~ — **#17에서 삭제** |
| 저장층: 3-writer 계약 · `put_score` · `put_extraction` · `patch_settings` · rank/holder 쿼리 (#18) | `topic/storage/user_topics.py` (구 `topic/user_topics/repository.py`) |
| rank_key 파생 · 인덱스 이름 (#16) | `topic/connectors/dynamodb/keys.py` |
| `RANKED_TIERS`({public, friends}) · tier 검증 | `topic/visibility/tiers.py` |
| 스트림 tier 병합 (#16) | `topic/search/streams.py:TopicIndexStream` |
| blocks · `ScoreDetailBlock` 합성 | `topic/user_topics/blocks.py`, `api/structs/user_topic.py:_blocks_of` |
| 라벨·alias 생성 규칙 | `topic/catalog_import/structs.py:topic_labels_from`·`topic_aliases_from` |
| tier·언어 파라미터 | `api/structs/params.py` |
| facets · `ScoreDetail`(구 ScoreInputs) · `Visibility` · `LocalizedText` | `topic/structs.py` |
| 점수 공식 | `topic/persona_topics/scoring.py` |
| 후보 조립(3패스 캡) | `topic/persona_topics/candidates.py` |
| 병합 · `removed_topics` · `extras` | `topic/persona_topics/merge.py` |
| 추출 구조체 · `unmatched_signals` | `topic/persona_topics/structs.py` |
| LLM 프롬프트(signals / marking) | `cli/persona_topics/stages.py` |
| 추출 오케스트레이션 | `cli/persona_topics/extract.py` |
| 랭킹 응답(matched 트리 · is_match) | `api/routers/search/structs.py` |
| score 주입·extraction 쓰기 라우트 (#18에서 users 아래 통합) | `api/routers/internal/users/router.py` (구 `internal/scores/` — 삭제) |
| ~~카탈로그 관리 라우트~~ | ~~`api/routers/internal/catalog/router.py`~~ — **#17에서 삭제** |
| 설정 기본값 | `topic/config.py` |
| 워커 수 · HPA | `k8s/overlays/*/deployment-patch.yaml`, `k8s/base/hpa.yaml` |

`../../iac` (origin/main `d364d3c`):

| 주장 | 위치 |
|---|---|
| DynamoDB 온디맨드 · GSI 정의 방식 | `terraform/modules/dynamodb/main.tf` |
| AOSS 컬렉션 그룹 · OCU 한도 | `terraform/env/dev/main.tf:352-376` |
| `bourbon-app` IRSA DynamoDB 권한 | `terraform/modules/iam/service/service_roles.tf:116-132` |
| 토픽 테이블 부재 | 전수 grep 결과 없음 (rev 4: origin/main `592e34c`에서 재확인 — 여전히 없음) |

`../bourbon-api` (origin/main `943b5f5`): `k8s/base/api-svc-dispatch.yaml` — `/api/svc/topic/` 미등록.
`../bourbon-agent` (HEAD `18fbcac`): topic-api 참조 0건. 페르소나는 `SHARABLE`/`PRIVATE` 2슬롯 ×
(bio/traits/preferences) 텍스트.

## 부록 B — 실측 재현

`bourbon-topic-api` 루트에서 `uv run --frozen python - <<'PY' ... PY`로 붙여 실행한다.
카탈로그 시드만 읽으므로 DB·네트워크가 필요 없다. `TopicGraph`가 topic_id로 dedupe하는 것을
같은 방식으로 재현하기 위해 qid 기준으로 접는다.

```python
import yaml
from pathlib import Path
from collections import Counter

def norm(v): return "".join(v.lower().split())      # normalize_search_text 와 동일

rows, seen, topics = [], set(), []
for p in sorted(Path("catalog_seeds/reviewed").glob("*.yaml")):
    d = yaml.safe_load(p.read_text())
    for c in (d.get("decided") or []):
        rows.append((d["group_key"], c["qid"], bool(c.get("include")),
                     c.get("distance"), c.get("decided_by")))
        if not c.get("include") or c["qid"] in seen: continue
        seen.add(c["qid"])
        l = c.get("labels") or {}
        topics.append((l.get("ko"), l.get("en"), l.get("ja"), c.get("aliases") or []))

kept = [r for r in rows if r[2]]
print(f"groups={len({r[0] for r in rows})} kept_rows={len(kept)} "
      f"unique_qid={len(seen)} dropped={len(rows)-len(kept)} "
      f"aliases={sum(len(t[3]) for t in topics)}")
print("depth:", Counter(r[3] for r in kept), " decided_by:", Counter(r[4] for r in kept))
print("per group:", Counter(r[0] for r in kept).most_common())

LIMIT = 20                                            # SEARCH_MAX_NAME_MATCHES
def find(q):
    n, hits, total = norm(q), [], 0
    for ko, en, ja, al in topics:                     # dict 삽입 순 = 그래프 순
        if any(n in norm(x) for x in [x for x in (ko, en, ja) if x] + al):
            total += 1
            if len(hits) < LIMIT: hits.append(en or ko or "?")
    return hits, total

for q in ["커피", "드립 커피", "핸드드립 커피 추출법", "machine learning", "머신러닝",
          "기계학습", "kubernetes", "ai", "quantum", "python", "dynamodb",
          "database", "위스키", "양자역학", "observability"]:
    h, t = find(q)
    print(f"{q:22} total={t:<5}{'CAP' if t > LIMIT else '   '}  first: {', '.join(h[:6])}")
```

§12.1의 커버리지 측정은 위 `find`에 eval 코퍼스의 질의 목록을 넣고, 결과를
exact / ancestor-only / 전무 / 캡 오염으로 분류하면 된다. ancestor-only 판정에는
부모 엣지가 필요하므로 `broader_qids`와 `placement`를 함께 읽어야 한다.

---

## 변경 이력

- **2026-08-21 초판** — `bourbon-topic-api` HEAD `296723d` 전수 분석. §2.1 표는 최초 작성 시
  추정값을 실측으로 제시한 오류를 발견해 실제 실행 결과로 교체했다(`머신러닝` 0→1,
  `machine learning` 3→5, `ai` 캡 20→총 560 및 상위 20개 전부 무관). 또한 첫 실측이
  리뷰 파일 행(2,617)을 순회해 중복 qid를 이중 계산했으므로, `TopicGraph`와 동일하게
  dedupe한 2,605개 기준으로 다시 측정했다(`ai` 562→560, `database` 6→5). §9의 ordering 키 항목도
  작성 중 "topic-api score를 정렬 키로" → "facets에서 우리가 만든다"로 철회·정정했다.
- **2026-08-21 rev 2** — 직접 재검토 + 오너 확인 반영. ⑴ **생산 사슬 확정**: deferq →
  bourbon-agent persona extractor(미구현 — `save_persona` 호출자 0건) → persona 슬롯 →
  topic-api 파이프라인(§1.5·§7-4). §0의 "전제 중 어느 것도 맞지 않는다"를 정정 — **입력 사슬
  전제는 맞았다.** ⑵ **재가중의 컷 한계**를 §9에 추가: 후보 컷이 그들 score로 일어나므로
  재가중은 도착한 것만 구제한다 — 선택지 3개((a) limit=100 수용+만료 조건 권고), 하위 결정
  2개(null fallback·relation)를 §13-3으로. ⑶ §8.3-A "leaf 조회" 표현 정정 — leaf/rollup은
  서비스가 고르고, 사전 판별은 불가(detail `children`은 level-1 전용 — flatten.py 실측),
  d1 2,180/d2 267이라 구체 토픽 대부분은 실제 잎. ⑷ §11-14(입력 슬롯 + description 뉘앙스)·
  §11-15(expertise 접근 경로)·§13-9(rollup 수용)·§13-10(cold-start UX) 추가, §12.1 코퍼스
  주의·§12.3 컷 경계 계측 추가. ⑸ best-effort 입력 선언을 §9 승계 목록에 추가(주체 이전).
- **2026-08-21 rev 3** — HEAD `107f5cd`(+5커밋) 반영. 핵심은 #17 **"카탈로그를 DynamoDB
  테이블에서 빌드 산출물로 전환"**: 카탈로그 테이블·Scan·60초 TTL 캐시·reload 라우트·internal
  카탈로그 관리 라우트·`uuid4` 랜덤 id 경로가 전부 삭제되고, `catalog_dist/catalog.json`
  (git 커밋·이미지 포함)을 시작 시 1회 로드한다. 편집·merge는 `build`/`merge`(파일) +
  `migrate-items`(라이브 테이블, dry-run 기본)로 갈라졌다. 이 문서에서 바뀐 것: §1 저장 구조,
  §3.3 확장 경로(유일한 쓰기 경로 = git 커밋), §5.3 고정 읽기·p99 스파이크 지적 **해소**,
  §7-1(필요 테이블 1개로 축소)·§7-2(`dynamodb:Scan` 요구 소멸), §11-13 **해소**, §13-8 캐시
  질문 완화(반영 단위 = 그들의 배포), 부록 A 경로 갱신. 초판의 수동 생성 토픽 중복 위험 지적도
  랜덤 id 경로와 함께 소멸. 그 외 #14(dev docs를 prefix 아래 SSO+edge-auth 이중 게이트로),
  #13(proxy 헤더 미들웨어), `574a774`(topic 응답 필드 순서 통일 — wire 계약 의미 변화 없음),
  `ecd4a1b`(dev 이미지 CDN 서빙 활성화). **persona_topics·검색·랭킹·visibility 로직은 5커밋
  전부에서 무변** — §2·§4·§5.2·§6·§8–§13의 분석·결정은 그대로 유효하고, 테스트는 942/50/0.
- **2026-08-24 rev 4** — HEAD `80c650f`(PR #16·#18–#25, 커밋 ~20개) 반영. 구조 변화 네 가지:
  ⑴ **인덱스 2분할(#16)**: `topic-score-index` → `topic-rank-index`(rank_key =
  `{topic_id}#{visibility}#{shard}`, sparse — ranked tier에서만 존재) + `topic-holder-index`
  (전수 보유자). `RANKED_TIER=public` 단독 → `RANKED_TIERS={public, friends}` 집합이 되고
  요청이 tier 부분집합을 명시한다. 저장층이 3-writer disjoint-속성 계약으로 재정리
  (`topic/storage/user_topics.py`). ⑵ **응답 재편(#18·#20–#24)**: `matched`가 설명
  트리(distance 부호·contribution 검산 가능·미보유 매치 제외)가 되고, `descriptions` 3언어화,
  `score_inputs`→`score_detail` 개명 + **랭킹 응답 blocks에 블록으로 노출** — §4.2 걸림돌·
  §11-3 해소, 우리 ordering 키 재료가 검색 한 번에 온다. topic 검색도 is_match 트리.
  ⑶ **internal 표면 통합(#19)**: SERVICE_ROLE 이중 워크로드 소멸, 한 워크로드가
  `/api/svc/topic` + `/api/internal/svc/topic` 두 prefix 서빙. ⑷ **resolve가 eventual로**:
  rollup 본문 재확인·leaf 본문 로드 모두 `ConsistentRead=False` — §5.3 상한 절반, §6.3 보호
  서술 정정. 이 문서에서 추가로: §2.1에 라벨·alias 생성 규칙 명시, §10-2를 그 규칙에서 유도한
  expansion 규칙 R1–R7로 확장, §10-9(tier 집합)·§11-16(id 리스트 랭킹 라우트)·§11-17(friends
  사용 여부) 신설, §7-1을 콘솔 수작업 인덱스 현황으로 갱신(iac `592e34c` 재grep — 테이블 선언
  여전히 없음, 콘솔 작업은 레포로 검증 불가). 그 외 #22가 persona extraction의 grounding을
  검색 트리 소비로 바꿨고, #25가 demo seed를 실제 persona 추출 경유로 바꿨다(분석 결론 무영향).
  `backfill_index_key.py`는 삭제됐다(§1.3 언급 제거 — 인덱스 명세는 `create_tables.py`가 유일).
  테스트 실측: **1208 passed / 86 skipped / 0 failed.** 검색 어휘층(`find_by_name`·normalize·
  카탈로그 시드)은 rev 4 구간에서도 무변 — §2.1 실측 표·§3 카탈로그 분석은 그대로 유효하다.
- **2026-08-24 rev 5** — 오너 전언 3건 반영(코드가 아니라 전언이므로 "오너 확인(전언)"으로
  표기). ⑴ **facets는 현재 dummy이고 필드 집합·값 의미가 모두 변경될 수 있다** → §4.2에 새
  걸림돌로 기록, §11-18(facets 계약 확정 — 키 식의 선행 조건) 신설, §13-3에 선행 조건 명시,
  §12.3의 재가중 계측에 "실데이터 주입 후에만 의미" 주의 추가. rev 4의 "재가중 재료 확보"
  결론은 **운반 경로 확보**로 좁혀 읽어야 한다 — 의미는 아직 계약이 아니다. ⑵ `search/users`의
  `item=null` = 그 유저가 그 토픽 아이템을 보유하지 않음 — rev 4의 코드 분석과 일치(§2.2에
  확인 기록). ⑶ 트리는 root + depth 2까지로 구성하고 이하 보유는 rollup으로 접어 올린다 —
  코드로 정밀화하면 매치·보유 토픽 자신은 항상 제 노드로 나오고(`build_tree`), depth 2가
  접는 것은 조상 사슬과 랭킹의 감쇠 합산이다(작성 중 "세밀도가 2로 캡"이라 먼저 적었다가
  build_tree 경로식 확인으로 정정). 추천 설계 함의를 §2.2에 기록: 계층 문맥은 distance로,
  깊은 보유는 distance>0 자손 노드 + contribution으로 복원한다.
- **2026-08-24 rev 7** — 외부 리뷰 수용분 반영. ⑴ **§11-4 블로커 승격**: leaf stub의
  user_id+score 노출은 유저가 토글 가능해지는 순간(=우리 출시)에 열리는 창이므로 user-facing
  출시 게이트에 연동. §6.2의 "구조적으로 공개된 것만 담는다"를 약화(§6.3과의 자기모순 정정).
  §6.3에 소비자 임시 방어(timestamps-null 휴리스틱 — 계약 아님·telemetry 동반)와 "철회 전파
  지연에 상한 계약 없음"을 추가. ⑵ §11-19(strategy 응답 필드, 낮음)·§11-20(철회 즉시성 기획
  질문, 중간) 신설. 설계 문서 rev 5(concept_group 계약 승격·fail-closed·owner→agent 변환
  등)와 동기.
- **2026-08-24 rev 6** — 협의·재평가 2건. ⑴ **§11-5 철회**: `exclude_user_ids` 서버측 요청을
  접고 우리 후처리로 확정(사용자 결정) — 설계가 fan-out 100·max_results 3으로 잡히며 cap 손실
  논거가 소멸했고 제외 목록은 countable. ⑵ **§11-16 우선순위 하향**: 다중 id 라우트는 그들
  score의 cross-topic 재유입·병합 후 컷·rollup 경로 강제라는 대가가 있어 A단계 per-topic
  fan-out + RRF가 우월 — 발동 조건 2개를 명시하고 "높음"에서 "조건부"로. (rev 4에서 이
  라우트의 가치를 과대평가했던 서술을 정정.)
- **2026-08-24 rev 5.1** — ⑶을 전언에서 **검증됨(실측)**으로 승격: 서비스 자신의 모듈
  (`read_artifact`+`TopicGraph`+`build_tree`+`shown_ancestry`+`descendants`)을 실물
  아티팩트에 실행. IDM(조상 3단) → depth=2에서 `[music → IDM]`(중간 조상 생략·토픽 생존),
  shown_ancestry hops=3(거리 원값 유지), descendants(AI)∋ChatGPT@1(weight 0.6) /
  descendants(ChatGPT)={자신}(하향 전용), 조상 ≥2단 토픽 560/2,605. §2.2에 실측 기록.
