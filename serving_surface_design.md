# Agent 추천 API — 노출 표면(serving surface) 설계: internal-only + edge-auth 관례

> **문서 지위**: 설계 rev 3 (2026-08-24). 입력 = bourbon-api `docs/microservice-edge-auth.md`
> (관례 정본) + bourbon-topic-api의 레퍼런스 구현(2026-08-24 소스 확인) +
> `recommendation_pipeline_design.md` rev 5.3(파이프라인 정본 — 이 문서는 그 파이프라인이
> **어떤 표면 위에서 서빙되는가**만 소유한다).
>
> **전제 결정 (2026-08-24, 오너)**: ⑴ agent-recommendation-api는 **internal 표면만** 갖는다 —
> public `/api/svc/` 표면을 만들지 않는다. ⑵ 구현은 `project-template-python`에서 **신규로
> 시작**한다 — 기존 코드(현행 memory-api 체인 구현)는 편집 대상이 아니라 **참조원**이다.
> 이에 따라 `recommendation_pipeline_design.md` §7 처분표의 "유지/교체"는 "신규 구현으로
> 포팅한다/포팅하지 않는다"로 읽는다.
>
> **표기**: `검증됨`(소스 확인) / `결정`(이 문서 또는 오너가 확정) / `열린 결정`.

## §0 한 페이지 요약

```
bourbon-agent ──in-cluster 직행──▶ http://bourbon-agent-discovery-api/api/internal/svc/agent-discovery/recommend
                                     │  edge-auth 정책의 notPaths로 check skip
                                     │  (신원은 body requester_user_id — 헤더 아님)
우리 ──in-cluster 직행──▶ http://bourbon-topic-api/api/internal/svc/topic/...
                                     │
dev 진단(사람) ──office IP──▶ https://dev-bourbon.xinobi.net/api/internal/svc/agent-discovery/...
                                     (gateway edge gate 통과, dispatch registry 경유)
```

- 모든 라우트는 `INTERNAL_PREFIX = /api/internal/svc/agent-discovery` 아래. 예외는 root `/health` 하나.
- pod에 edge-auth label을 **붙인다** — public 라우트가 없어도.
- `x-user-id` 헤더는 이 서비스의 어떤 라우트도 읽지 않는다. 신원은 body의
  `requester_user_id`뿐.
- CORS·cookie·토큰 파싱 코드 = 0줄.

## §1 결정과 근거

### 1-1. internal-only (결정)

호출자는 bourbon-agent 하나이고, in-cluster 서비스라 bourbon access token이 없다 — 관례
문서의 "Routes for other services"(tokenless caller) 케이스 그 자체다. 사람 사용자가 직접
부르는 경로가 없으므로 public 표면은 존재 이유가 없다.

### 1-2. label은 그래도 붙인다 (결정)

public 라우트가 없어도 `bourbon.xinobi.ai/edge-auth: enabled`를 붙인다. 이유 둘:

1. **잘못 마운트된 라우트의 무인증 노출을 막는다**(rev 3에서 축소 서술 — "완전한
   fail-closed"가 아니다). 공유 정책의 notPaths는 `/api/internal/svc/` 아래만 check를
   skip한다. internal prefix **밖**으로 실수 마운트된 라우트는 (label이 있으면) token을
   요구해 **무토큰 호출자에게만** unreachable이 된다 — 정상 access token을 가진 사용자는
   check를 통과해 도달할 수 있고, 이 서비스는 x-user-id를 의도적으로 읽지 않으므로 그가
   body에 실은 임의 `requester_user_id`가 그대로 신원이 된다(§1-3 threat model). 즉 label이
   막는 것은 정확히 "unauthenticated 노출"까지이고, **오마운트 자체를 막는 시행층은
   surface-boundary 테스트다**(§4-2). label이 없으면 워크로드 전체가 무검사라 실수가
   조용히 노출된다.
2. **namespace fence의 opt-in이다.** `authz-internal-svc`(타 namespace in-mesh 호출자
   거부)는 labelled workload에만 적용된다(검증됨 — 관례 문서 "The namespace fence" 절).
   현행 dev 배포에서 bearer를 제거하며(K4, 코드repo PR #46) 안전층 ①이 네트워크 경계
   단독이 됐는데, 이 fence가 그 자리를 **공유 정책이라는 명명된 시행층**으로 채운다.

### 1-3. 신원 채널 = body, 헤더 금지 (결정)

internal prefix에서는 check가 skip되어 `x-user-id`가 **미검증인 채** 통과한다(관례 문서:
"A skipped request keeps the caller's own x-user-id, unverified: no route under the prefix
may read one"). 따라서:

- 이 서비스는 **`x-user-id`를 읽는 dependency를 아예 갖지 않는다.** topic-api의
  `api/depends/identity.py`(`ViewerId`)는 public 표면 전용 장치라 **포팅하지 않는다** —
  이런 모듈이 repo에 존재하지 않는 것이 곧 규율이다.
- requester 신원은 wire body의 `requester_user_id`뿐이다(파이프라인 설계 §2 S0). 신뢰
  근거 = namespace fence(§1-2) + bourbon-agent handler가 task payload에서 채운다는 그쪽
  규율(모델 공급 신원 비신뢰). 관례 문서의 "server-to-server auth has no answer yet"
  선언은 이 조합이 현존 최선임을 확인해 준다(구 B2 종결 판단과 일치 —
  `archive/bourbon_api_discovery_open_requests.md`).

**threat model (rev 3 — 외부 리뷰 수용: 시행 범위를 실제보다 강하게 쓰지 않는다):**

- body의 `requester_user_id`는 "검증된 사용자 신원"이 아니라 **"허용된 내부 호출자가
  주장한 신원"**이다. 이 값을 검증하는 층은 어디에도 없다.
- **namespace fence는 namespace 경계이지 bourbon-agent 인증이 아니다.** 실제 정책
  (bourbon-api `k8s/overlays/dev/authz-internal-svc.yaml`, 검증됨)은 DENY +
  `notNamespaces: ["dev"]` — dev namespace **안의 모든 workload가 통과**한다. 같은
  namespace의 다른 서비스가 임의 신원으로 호출하는 것을 막는 층은 없다.
- **bourbon-agent 단독 호출을 실제로 보장하려면 service account/principal 기반
  AuthorizationPolicy가 추가로 필요하다.** 지금은 도입하지 않는다(허용된 호출자가 하나뿐인
  단계에서 얻는 것이 없음) — 다만 **명명된 업그레이드 경로**로 기록한다: 호출자가 늘거나,
  requester 신원의 용도가 self-exclusion을 넘어 권한·노출 판단에 쓰이게 되는 순간이
  도입 시점이다.
- 이 구도에서 **surface-boundary 테스트(§4-2)는 편의 테스트가 아니라 핵심 보안
  시행층이다** — 오마운트를 막는 것은 정책이 아니라 이 테스트다.

### 1-4. 신규 template 구현 (오너 결정)

`project-template-python`에서 새로 시작한다. 기존 코드는 참조원이다 — 파이프라인 설계 §7
처분표에서 "유지"로 분류된 모듈(`self_exclusion.py`, `identity_uuid5.py` 등)은 **신규
구현으로 포팅할 대상**이고, "삭제"로 분류된 것(stance 파이프라인 등)은 **포팅하지 않는
것**으로 실현된다 — 신규 구현에서는 삭제 패스가 필요 없다.

### 1-5. 이름 (2026-08-24 오너 확정 — §7-①·③ 해소)

- **Git repo / 배포 서비스명 = `bourbon-agent-discovery-api`** — `project-template-python`
  기반의 **새 repo**로 시작한다(§7-③도 이 결정으로 해소).
- dispatch `<name>` = **`agent-discovery`** → prefix `/api/internal/svc/agent-discovery`.
- Python package = `agent_discovery`.
- endpoint = `POST /recommend` 유지 — 호출자 계약(bourbon-agent `recommend_agents`)의 것.
  서비스명과 라우트명이 다른 것은 topic-api와 같은 정상 패턴이다.
- 기존 `bourbon-agent-recommendation-api`는 전환 완료까지 가동 후 archive. 이름이 달라
  **공존(k8s Service·dispatch 충돌 없음)·컷오버(bourbon-agent client URL 교체 한 번)·롤백
  (URL 원복)**이 리네임 없이 성립한다 — `-v2` 접미도, canonical 이름 이관 댄스도 불필요.
- **용어 주의**: repo 이름의 "discovery"는 업계 우산 의미다 — 사용자가 몰랐던 agent를 알게
  되는 경험 전체(search+recommendation+browse)를 가리킨다. 파이프라인 어휘의 **Discovery
  단계**(Recommendation 단계와 직교)와는 **같은 단어·다른 주어**이므로, 문서에서 단계를
  말할 때는 항상 "Discovery 단계"로 풀어 쓴다.

## §2 표면 계약

| 항목 | 값 |
|---|---|
| prefix | `INTERNAL_PREFIX = "/api/internal/svc/agent-discovery"` (§1-5 확정) |
| 라우트 마운트 | 전 라우터를 `include_router(router, prefix=INTERNAL_PREFIX)` — **rewrite 금지**(절대 URL이 전부 깨진다, 관례 문서 step 4) |
| health | root `/health` — kubelet이 pod 직행, prefix 밖의 유일한 라우트 |
| public 표면 | 없음. `/api/svc/agent-discovery` 아래 라우트 0개를 테스트로 단정(§4-2) |
| 호출 URL (bourbon-agent → 우리) | `http://bourbon-agent-discovery-api/api/internal/svc/agent-discovery/recommend` — in-cluster 직행. gateway 경유는 hop만 추가(registry는 gateway 트래픽만 라우팅) |
| 호출 URL (우리 → topic-api) | `http://bourbon-topic-api/api/internal/svc/topic/...` — 같은 원리로 직행. 파이프라인 설계 §6의 base URL 계약 |
| dev 진단 경로 | `https://dev-bourbon.xinobi.net/api/internal/svc/agent-discovery/...` — office IP만 edge gate 통과(dev). **e2e-recommend CLI가 in-process라 못 타는 인증·HTTP 층을 실제로 타는 acceptance 지점** |
| 신원 | body `requester_user_id` 단독. `x-user-id` 금지(§1-3) |
| docs | `INTERNAL_PREFIX` 아래, dev-only (§7-② 게이트 형태 미정) |

## §3 template 대비 델타 (관례 문서 step 1–5의 internal-only 적용)

관례 문서는 public 표면 기준으로 쓰여 있다. internal-only에서 각 step은:

| step | 관례 문서 | 우리 |
|---|---|---|
| 1. label | 붙인다 | **동일** — topic-api처럼 label 옆에 사유 주석("removing the label makes every route unauthenticated") |
| 2. 호스트/vs 삭제 | per-service host 삭제, docs용 oauth2-proxy 유지 | 동일하게 vs 없음. oauth2-proxy는 §7-② |
| 3. dispatch 등록 | `/api/svc/agent-discovery/` 블록 | **internal 블록 1개만** PR(`/api/internal/svc/agent-discovery/`) — topic-api는 두 블록(bourbon-api `k8s/base/api-svc-dispatch.yaml:16,24` 검증됨), 우리는 하나. **Service 포트는 `name: http` 필수** — 무명 포트는 plain TCP 취급이라 L7 정책(namespace fence 포함)이 아예 안 돈다 |
| 4. prefix 마운트 | `API_PREFIX` | `INTERNAL_PREFIX`만. docs URL도 그 아래 dev-only |
| 5. CORS | bourbon-api ConfigMap에서 origin 목록 | **전부 생략** — 브라우저 호출자 없음. ConfigMap 참조·preflight 미들웨어 순서 규칙 모두 해당 없음 |

파생 효과: CORS가 빠지면서 관례 문서의 미들웨어 순서 제약("CORSMiddleware가 최외곽")이
사라진다 — 미들웨어 스택은 request_id·proxy-headers류만 남아 단순해진다.

## §4 topic-api에서 차용하는 이디엄 (레퍼런스 구현, 소스 검증됨)

### 4-1. 상수 + 신뢰 근거 주석

`api/main.py`의 `INTERNAL_PREFIX` 선언부에 topic-api `api/main.py:35-39`의 문장 구조를
그대로 쓴다: 이 prefix 아래는 check가 skip되고, x-user-id는 호출자가 보낸 그대로이며,
**어떤 internal 라우트도 그것을 읽지 않는다**. 같은 규율 문장을 각 internal 라우터 모듈
docstring에도 반복한다(topic-api `api/routers/internal/topics/router.py:3-5` 관례).

### 4-2. 라우터 명부 + surface boundary 테스트

topic-api `api/depends/surfaces.py`의 교리 — "an endpoint in the wrong list is a security
decision gone wrong" — 를 승계하되, 표면이 하나라 명부는 internal 리스트 하나로 퇴화한다.
테스트는 `tests/.../test_surface_boundary.py`(topic-api 동명 파일의 우리 버전):

1. `INTERNAL_PREFIX.startswith("/api/internal/svc/")` — 공유 정책·edge gate가 매칭하는
   모양 그 자체를 단정.
2. **클라이언트 쪽 prefix 상수가 앱과 일치** — topic-api는 자기 CLI로 이걸 하는데, 우리는
   e2e/진단 CLI와(가능하면 bourbon-agent client 계약 테스트와도) 같은 단정을 건다.
3. 모든 `api.routers.*` 라우트가 `INTERNAL_PREFIX` 아래(예외: health).
4. `/api/svc/` 아래 라우트 **0개** — internal-only의 단정형.

이 테스트 묶음은 §1-3 threat model이 기대는 **유일한 오마운트 방지층**이다(rev 3) —
정책(label·fence)은 오마운트를 막지 못하고 노출 형태만 바꾼다. topic-api surfaces.py의
"security decision gone wrong"이 여기서는 문자 그대로다.

### 4-3. "신원은 헤더에 없다" 테스트

topic-api internal 테스트 디렉토리의 규약("No x-user-id header anywhere in this
directory's requests") + 명시 테스트(`test_internal_search_takes_no_caller_identity`)를
승계한다. 우리 버전은 한 발 더: **`x-user-id`를 보내도 응답·decision log 어디에도 영향이
없고, 신원은 body `requester_user_id`뿐**임을 고정한다.

### 4-4. 기타

- root health 테스트(topic-api `tests/integration/test_root_routes.py`).
- k8s label 사유 주석(§3 step 1).
- (참고) topic-api internal 응답이 단일 언어가 아니라 **언어 맵**인 이유 = "caller identity
  없음 → 언어 선호를 모름". 파이프라인 설계 S6의 ko·en 라벨 병기 결정과 같은 뿌리다.

## §5 포팅하지 않는 것

| topic-api의 것 | 이유 |
|---|---|
| `api/depends/identity.py` (`ViewerId`, `get_user_id`) | public 표면 전용 — 검증된 x-user-id를 읽는 장치. 우리에겐 그 헤더가 검증되는 표면이 없다(§1-3) |
| CORS 일체 (`_load_cors_origins`·ConfigMap env·preflight 순서 규칙) | 브라우저 호출자 없음(§3 step 5) |
| public↔internal mirror 구조·`surface_tags`의 표면 분리 | 표면이 하나 |
| oauth2-proxy의 public docs 경로 | docs가 internal prefix 아래로 감(§7-②) |

## §6 실패 의미와의 상호작용

- **in-cluster 직행 경로에는 401/403/registry-404가 존재하지 않는다.** 파이프라인 설계
  §4의 422/503 3분기가 wire에 그대로 노출된다 — 충돌 없음. bourbon-agent client는
  connection-level 실패(스케일 0 등)를 추가로 다뤄야 한다.
- **gateway 진단 경로에서만** 이 층의 의미가 덧붙는다: 503(authorizer 장애 **또는** ready
  pod 0), 404("No service is registered at this path" = dispatch 미등록). 진단 시 오독 주의.
- edge-auth 체계는 fail-closed(bourbon-api 불통이면 labelled workload 전체 불통)지만,
  **internal prefix는 check를 안 타므로 우리 hot path는 bourbon-api 가용성에 의존하지
  않는다** — 추천 경로의 의존은 topic-api뿐이라는 파이프라인 설계 §6 그림이 유지된다.

## §7 열린 결정

| # | 항목 | 내용 |
|---|---|---|
| ① | ~~`<name>`~~ | **해소(2026-08-24, §1-5)** — repo/서비스명 `bourbon-agent-discovery-api`, `<name>` = `agent-discovery`, package `agent_discovery` |
| ② | dev docs 게이트 | internal prefix 아래 docs는 dev에서 edge gate(office IP)가 이미 막는다. 기존 `authz-oauth2-proxy.yaml`을 internal 경로로 retarget해 SSO 이중 게이트로 둘지, 제거할지. **권고 = 유지·retarget**: dev host는 public이고(관례 문서의 httpbin 경고와 같은 이유), IP 허용 목록 하나에 기대지 않는다 |
| ③ | ~~신규 구현의 그릇~~ | **해소(2026-08-24, §1-5)** — 새 repo scaffold. 기존 repo는 전환 완료까지 가동하는 참조용 동결, 삭제 패스 없음 |
| ④ | dispatch PR 시점 | 등록은 bourbon-api 배포를 타므로(관례 문서 step 3), dev 첫 배포 전에 PR이 머지·배포돼 있어야 gateway 진단 경로가 열린다 |

## 변경 이력

- **2026-08-24 rev 3** — 외부 리뷰 수용: 신뢰 경계를 실제 시행 범위로 축소 서술.
  ⑴ §1-2의 "fail-closed"를 "무인증 노출 차단"으로 좁힘 — 토큰 보유 사용자는 오마운트
  라우트에 도달해 임의 body 신원을 주장할 수 있다. ⑵ §1-3에 threat model 신설: body 신원 =
  허용된 내부 호출자의 **주장** 신원, fence = namespace 경계(dev namespace 내 전 workload
  통과 — 정책 소스 검증), principal 기반 정책은 명명된 업그레이드 경로(도입 시점 정의),
  surface-boundary 테스트 = 핵심 보안 시행층. ⑶ §4-2에 테스트의 시행층 지위 명기.
  recommendation_pipeline_design.md rev 5.5와 동기.
- **2026-08-24 rev 2** — §7-①·③ 해소(오너 확정): repo = **`bourbon-agent-discovery-api`**
  (새 repo scaffold), `<name>` = `agent-discovery`, package = `agent_discovery`, endpoint =
  `/recommend` 유지, 기존 repo는 전환 후 archive. §1-5 신설(공존·컷오버 근거 + "discovery"
  용어의 우산 의미 vs Discovery 단계 구분 명시), 본문 `<name>` placeholder 전부 실명으로 치환.
- **2026-08-24 rev 1** — 최초 작성. 입력 = bourbon-api `docs/microservice-edge-auth.md` +
  topic-api 레퍼런스 구현 소스 확인(main.py 표면 상수·surfaces 명부·surface boundary
  테스트·identity dependency·k8s label/port·dispatch 두 블록) + 오너 결정 2건(internal-only,
  신규 template 구현). 현행 repo와의 갭(root 마운트·무명 포트·label 부재)은 §3에 반영 —
  단 신규 구현 전제라 "고칠 목록"이 아니라 "template에서 처음부터 이렇게 만든다"로 읽는다.
