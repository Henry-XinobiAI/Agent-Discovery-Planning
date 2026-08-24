# Agent 추천 API — 노출 표면(serving surface) 설계: internal-only + edge-auth 관례

> **구현 상태 (rev 3.3, 2026-08-24)**: §3 델타와 §4 이디엄이 새 repo
> `bourbon-agent-discovery-api`에 **반영됨** — `4176b0a`(k8s: label·vs 삭제·docs 게이트
> retarget·API_TOKENS 제거), `05ec707`(app: `INTERNAL_PREFIX` 마운트·surfaces 명부·bearer
> 토큰 층 삭제·surface 테스트 4종), `d861b5f`(§4-5 표면 밖 관례 정합: configmap·빈 secret·
> ErrorResponse·테스트 배치·잔차). §7 열린 결정은 **전부 해소** — dispatch 등록 PR도
> 준비됐고(bourbon-api `0eb55b6`) 순서 제약이 없다는 판단까지 §7-④에 기록했다. 미구현으로
> 남은 것은 §4-2 항목 2(클라이언트 prefix 등가 단정)와 §4-5의 `EnvSettings` 보류 2건뿐이다.
> 이 문서는 여전히 "무엇을 왜 그렇게 하는가"의 정본이고, 구현 상태는 이 블록만 갱신한다.

> **문서 지위**: 설계 rev 3.3 (2026-08-24). 입력 = bourbon-api `docs/microservice-edge-auth.md`
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
| docs | `INTERNAL_PREFIX` 아래, dev-only. 게이트 = gateway IP 게이트 + oauth2-proxy SSO 이중(§7-② 해소) |

## §3 template 대비 델타 (관례 문서 step 1–5의 internal-only 적용)

관례 문서는 public 표면 기준으로 쓰여 있다. internal-only에서 각 step은:

| step | 관례 문서 | 우리 |
|---|---|---|
| 1. label | 붙인다 | **동일** — topic-api처럼 label 옆에 사유 주석("removing the label makes every route unauthenticated") |
| 2. 호스트/vs 삭제 | per-service host 삭제, docs용 oauth2-proxy 유지 | 동일하게 vs 없음. oauth2-proxy는 유지·retarget(§7-② 해소) |
| 3. dispatch 등록 | `/api/svc/agent-discovery/` 블록 | **internal 블록 1개만** PR(`/api/internal/svc/agent-discovery/`) — topic-api는 두 블록(bourbon-api `k8s/base/api-svc-dispatch.yaml:16,24` 검증됨), 우리는 하나. **Service 포트는 `name: http` 필수** — 무명 포트는 plain TCP 취급이라 L7 정책(namespace fence 포함)이 아예 안 돈다 |
| 4. prefix 마운트 | `API_PREFIX` | `INTERNAL_PREFIX`만. docs URL도 그 아래 dev-only |
| 5. CORS | bourbon-api ConfigMap에서 origin 목록 | **전부 생략** — 브라우저 호출자 없음. ConfigMap 참조·preflight 미들웨어 순서 규칙 모두 해당 없음 |
| (6). template의 bearer 층 | 관례 문서에 없음 | **삭제** — template은 `API_TOKENS` env + `verify_token` dependency + `/dev/verify` 라우트를 들고 온다(rev 3.1에서 확인). 토큰 검사는 edge의 일이고, 앱 안의 두 번째 인증 체계는 **관리되지 않는 인증 표면**이다. secret·양 overlay의 env·`AuthorizationError`까지 함께 제거해야 pod가 뜬다(secret만 지우면 env 참조가 남아 기동 실패) |

파생 효과: CORS가 빠지면서 관례 문서의 미들웨어 순서 제약("CORSMiddleware가 최외곽")이
사라진다 — 미들웨어 스택은 request_id·proxy-headers류만 남아 단순해진다.

**template이 이미 만족하던 것 (rev 3.1 확인)**: Service 포트 `name: http`(사유 주석까지
포함), CORS 미들웨어 부재. `project-template-python`이 관례 반영 후 판이라 step 3·5의 델타는
"고칠 것"이 아니라 "이미 그렇게 되어 있음"이었다.

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
   (rev 3.1: repo에 아직 그 클라이언트가 없어 **보류** — 테스트 파일 docstring에 도입 시점을
   명기해 뒀다. 클라이언트가 생기는 커밋에서 함께 추가한다.)
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

### 4-5. 표면 밖 이디엄 정합 (rev 3.2 — topic-api 1:1 대조 결과)

표면 구조는 §4-1~4-4로 일치했고, **public 표면 유무로 설명되지 않는 차이 4건**을 topic-api
쪽으로 맞췄다(코드 `d861b5f`). 여기 기록하는 이유는 이것들이 "표면"은 아니지만 **같은 관례
체계의 일부**이고, 나중에 물리면 계약을 이미 굳힌 뒤가 되기 때문이다.

| 차이 | topic-api | 우리 결정 |
|---|---|---|
| 앱 설정 그릇 | base `configmap.yaml` + 스테이지별 patch + `envFrom` | **동일하게 도입**. 미리 준비가 아니라 **결함 수정**이었다 — `LOG_LEVEL` 코드 기본값이 DEBUG인데 k8s가 아무 값도 안 줘서 양 스테이지가 DEBUG JSON 로그로 뜰 상태였다. 스테이지별 키(upstream URL·모델명)는 생길 때 patch 추가 |
| secret | 파일을 **비워서 유지** + "왜 자격증명이 없는지" 주석 | 동일. 삭제하면 그 사유가 기록되지 않고, LLM provider 키가 필요해지는 순간 되살릴 파일이다 |
| 에러 envelope | `ErrorResponse`(`extra="forbid"`) + 앱에 `responses={"4XX","5XX"}` 선언 | 동일 + **한 칸 더**: 그쪽은 envelope이 `error_code: str`(필수)인데 `AppError` 기본값이 `None`이라 코드 없는 raise가 핸들러 안에서 검증 실패하는 잠재 구멍이 있다(현재 그런 raise는 없음). 우리는 `AppError`의 기본 코드를 실제 값으로 채워 그 구멍을 없앴다. 우리 wire는 422 `grounding_failed`·503을 계약으로 갖기 때문에 타입 있는 envelope이 그쪽보다 더 중요하다 |
| 테스트 배치 | `tests/integration/routers/internal/` + 그 conftest docstring에 "No x-user-id header anywhere" 규약 | 동일하게 이전. **규약이 디렉토리 단위로 사는 구조**가 요점 — `/recommend`의 fake들이 들어올 자리이기도 하다 |

**보류(의도적)**: 코드 쪽 `EnvSettings` 베이스(pydantic·`extra="forbid"`·`from_env`)는
topic-api·bourbon-agent 공통 관례지만, **서브클래스가 0개인 지금 넣으면 사용자가 없는
프레임워크**다 → 첫 설정 항목(topic-api base URL)이 생기는 커밋에서 함께 도입한다. 그때
ConfigMap 키 이름은 그 클래스의 필드명과 **정확히** 일치해야 한다(topic-api 주석의 함정:
오타는 조용히 코드 기본값으로 폴백).

**정리한 잔차**: template의 `log_invalid_response` 미들웨어 제거(핸들러가 이미 남긴 4xx/5xx를
한 번 더 기록하고, 예외가 없는 응답에도 `exc_info=True`를 붙였다 — topic-api에도 없다),
logger 이름을 전 모듈 `__name__`으로 통일, lifespan의 무의미한 `global logger` 재바인딩 제거.
**포팅 안 함**: topic-api의 OpenAPI 예제 설치(`api/docs/openapi.py` + `examples.json`) —
실제 라우트가 생긴 뒤에 판단.

**차이지만 우리가 맞는 것**: `serviceAccountName: bourbon-app`(그쪽은 DynamoDB·S3 IRSA용,
우리는 AWS SDK 의존 자체가 없다 — `pyproject.toml` 확인), 그리고 §4-2의 "health가 prefix 밖
유일 라우트" 단정(public 라우트가 밖에 있는 topic-api에서는 쓸 수 없는 형태다).

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
| ② | ~~dev docs 게이트~~ | **해소(2026-08-24, rev 3.1 — 권고대로 구현)**: `authz-oauth2-proxy.yaml`을 `dev-bourbon.xinobi.net` + internal prefix 아래 docs 4경로로 retarget해 유지(`4176b0a`). dev host는 public이므로 IP 허용 목록 하나에 기대지 않는다 |
| ③ | ~~신규 구현의 그릇~~ | **해소(2026-08-24, §1-5)** — 새 repo scaffold. 기존 repo는 전환 완료까지 가동하는 참조용 동결, 삭제 패스 없음 |
| ④ | ~~dispatch PR 시점~~ | **해소(2026-08-24, rev 3.3 — 오너 판단): 순서 제약 없음.** 등록 PR은 준비됨(bourbon-api `feat/dispatch-agent-discovery`, `0eb55b6` — internal 블록 1개, 404 fallback 위). 적용은 머지가 아니라 **bourbon-api의 다음 `deploy.sh <stage>`**를 탄다(자동 배포 워크플로 없음 — 검증됨). ⑴ 우리 워크로드가 없어도 안전하다: 그 prefix는 지금도 fallback 404를 받고, 등록 후 워크로드가 없으면 **404 대신 503**(Envoy에 upstream cluster 없음)이 될 뿐 다른 라우트에 영향 없다 — 단 진단 시 503의 의미가 "authorizer 불통/ready pod 0"에 "Service 부재"까지 겹친다는 점 주의. ⑵ 우리 dev 배포도 서두를 필요 없다: gateway 경로의 유일한 소비자는 진단하는 사람이고, 열어볼 값이 생기는 시점은 `/recommend` 구현 후다(지금 배포하면 health·echo만 확인된다). **별도 선행 조건**: 첫 배포 전 ECR 저장소 `bourbon/agent-discovery-api` 존재 확인(`deploy.sh`가 그 경로로 push) |

## 변경 이력

- **2026-08-24 rev 3.3** — §7-④ 해소(오너 판단): **순서 제약 없음**. 등록 PR은 준비됨
  (bourbon-api `feat/dispatch-agent-discovery` `0eb55b6`), 적용은 머지가 아니라 그쪽
  `deploy.sh <stage>`를 탄다(자동 배포 워크플로 부재 — 검증됨). 워크로드 없이 등록해도
  안전하나 그 prefix가 404→**503**으로 바뀐다(503 의미가 하나 더 겹침). 우리 dev 배포도
  `/recommend` 이후로 미룬다 — gateway 경로의 소비자는 진단하는 사람뿐이므로 지금 열면
  health·echo만 확인된다. 첫 배포의 실제 선행 조건은 ECR 저장소 존재 확인으로 이관.
- **2026-08-24 rev 3.2** — bourbon-topic-api와 1:1 대조(§4-5 신설, 코드 `d861b5f`).
  표면 구조는 일치했고, public 표면 유무로 설명되지 않는 차이 4건을 그쪽으로 맞췄다:
  ConfigMap+`envFrom`(★`LOG_LEVEL` 기본 DEBUG가 k8s에 미설정 — 준비가 아니라 결함
  수정이었다)·빈 secret 유지(사유 기록)·`ErrorResponse` envelope(그쪽의 `error_code`
  None 구멍은 막고)·internal 테스트 디렉토리(규약이 conftest에 사는 구조). 잔차 3건 정리
  (`log_invalid_response` 제거·logger `__name__` 통일·`global logger` 제거), `EnvSettings`
  베이스는 첫 설정 항목까지 보류, OpenAPI 예제 설치는 미포팅.
- **2026-08-24 rev 3.1** — 새 repo `bourbon-agent-discovery-api`에 §3·§4 구현 반영
  (`4176b0a`·`05ec707`). ⑴ 머리말에 구현 상태 블록 신설(이후 상태 갱신은 그 블록만).
  ⑵ §7-② 해소 — docs 게이트는 권고대로 유지·retarget. ⑶ §3에 델타 (6) 추가 — template이
  들고 오는 bearer 층(`API_TOKENS`·`verify_token`·`/dev/verify`)은 **삭제**가 결정이며,
  secret·양 overlay env·`AuthorizationError`까지 함께 지워야 기동한다. ⑷ §3에 "template이
  이미 만족하던 것"(포트 `name: http`, CORS 부재) 명기 — 기존 repo 기준으로 잡았던 갭 2건은
  실제로는 존재하지 않았다. ⑸ §4-2 항목 2(클라이언트 prefix 등가 단정)는 클라이언트 부재로
  보류 상태임을 명기. 남은 열린 결정은 §7-④ 하나.
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
