# requester self-exclusion 설계 (Phase 10 turn-on gate)

- **상태**: **설계 확정 / 구현·검수 미완**. Phase 10 real-edge turn-on gate 4건 중 하나에 대한 **설계 결정만**
  닫으며, [2026-07-24 phase10 real-edge contract slice](2026-07-24-phase10-real-edge-contract-slice-design.md)
  **§9의 self-exclusion 항목 (1)~(4)를 대체**한다. 그 spec의 §9 항목과 이 문서가 어긋나면 **이 문서가 맞다**.
- **★ 이 문서는 gate를 닫지 않는다.** 호출자 합의는 **외부 계약의 불확실성**을 해소할 뿐이다. **운영상의
  self-exclusion gate는** ⓐ Discovery 구현 ⓑ 호출자 적용 ⓒ 비프로덕션 acceptance가 "requester identity가
  실제로 전달되고 실제로 제외된다"를 증명한 뒤에야 닫힌다. 이 셋 중 하나라도 없으면 gate는 열려 있다.
- **범위**: `/recommend`가 **요청자 본인의 agent를 후보에서 제외**하도록 요청 계약·배선 계약·drop 위치·
  audit 표현·에러 계약·진단 계약을 확정한다. 요청자 정체성의 **무결성 검증은 범위 밖**이다(§3).
- **★ stage는 일반, 정책은 하나**: 이 슬라이스가 만드는 것은 **requester-scoped pre-gate exclusion stage**
  이고, 오늘 그 위에 올라가는 정책은 **self-exclusion 하나뿐**이다. 향후 정책(예: 사용자가 "다시 만나고 싶지
  않다"로 표시한 agent — 이미 Alpha reserved인 negative `UserPreferenceProvider` 신호)은 **새 형태를 만들지
  않고 이 stage에 정책을 하나 더 등록**한다. 일반화의 두 경계는 §6.3.
- **범위 밖**: `API_TOKENS`의 `name:secret` 매핑(호출자별 토큰·로그 귀속)은 **별도 backlog**다. 이 슬라이스에
  섞지 않는다 — 섞으면 self-exclusion이 인증 리팩터링에 인질로 잡힌다. (**정정 2026-08-11**: bearer가 미부착이
  됐으므로 이 backlog는 "토큰 형태 개선"이 아니다 — §11 참조. 범위 밖이라는 결론은 그대로다.) **두 번째 정책의 provider·집행 규칙도
  범위 밖**이다(§6.3 — 자리만 만들고 내용은 그때 설계한다).

---

## 1. 왜 지금인가 — turn-on gate 1의 축소

phase10 spec §9 (1)/(205)는 requester identity 필드를 미뤘다. 근거는 *"클라이언트 입력이 인증 identity처럼
오용될 위험"* 이었고, 해소 조건은 *"upstream 인증 identity 계약 확정"* 이었다.

**2026-08-05 오너 확인으로 그 전제가 바뀌었다**: 이 API는 클라이언트가 직접 호출할 수 없다. 호출자는 백엔드
컴포넌트뿐이고(moderator runtime / agent runtime — planning README §5의 모드 A·모드 B), **Alpha·Open Beta
기간 공개 ingress가 없다**. 따라서 `requester_owner_id`는 클라이언트 입력이 아니라 **신뢰된 호출자의 actor
claim**이고, 요청에 얹는 것이 적합하다.

**turn-on gate 1의 성격이 바뀐다**: "bourbon-api가 identity 신뢰 전달 메커니즘을 **설계**할 때까지 대기"
(미지의 외부 설계 의존) → **"호출자들이 §10의 문장대로 필드를 채운다"**(알려진 계약의 적용). 축소이지
**해소가 아니다** — 합의문이 있어도 구현·적용·검수 전까지 gate는 열려 있다(헤더 ★).

---

## 2. 확정된 결정 요약

| # | 결정 | 근거 |
|---|---|---|
| D1 | **검증·resolve는 linker/retriever I/O 이전(`bind`, 순차), 제외 판정은 ②↔③ 사이**(순회=파이프라인) | §6.1 |
| D2 | 요청 필드 = `Query.requester_owner_id: UUID \| None` **top-level typed** | §4 |
| D3 | 정책은 **항상 주입**(`Enforcing` / `Noop`), `\| None` 아님 | §5.1 |
| D4 | 정책 선택 축 = **`REAL_EDGE_ENABLED`** (stage 아님); 가드는 nominal `ExclusionMode`로 판별 | §5.2 |
| D5 | resolver·exact-resolution 검증을 **composition root에서 공유** | §5.3 |
| D6 | pre-gate 전용 타입 (`PreGateDropReason` / `PreGateDisposition` / `PreGateExclusionResult`) | §6.2 |
| D7 | `DecisionLog.record()`가 **pre-gate 처분을 결과 하나로** 받는다 (pool 포함) | §7.2 |
| D8 | `candidate_pool` 정본 = **retrieval 원본 순서의 `EdgeHit` 전체** | §7.2 |
| D9 | 단일 진실원 = **`PreGateExclusionResult` 하나**(`policies` + `dispositions` 두 ordered component) | §6.2 · §7.3 |
| D10 | 에러 3분할 — malformed 422 / 조건부 누락 422 / resolver 계약 위반 503 | §8 |
| D11 | real-edge e2e는 `--requester-owner-id` **필수**, 안전 우회 플래그를 만들지 않는다 | §9 |
| D12 | **stage는 정책 시퀀스**(오늘 1개, 첫 non-None 우선); 집행 규칙은 정책마다 선언, **removal-only** | §6.3 |

---

## 3. 신뢰 모델 — 이 API가 검증하는 것과 하지 않는 것

`/recommend`는 외부 클라이언트에 직접 노출되지 않는 **내부 서비스 API**다. 인증된 moderator/agent runtime이
자신이 **이미 인증한 요청자**의 owner_id를 `requester_owner_id`로 전달하며, recommendation-api는 이 actor
claim을 **신뢰한다**.

> ### ⚠️ 정정(2026-08-11) — bearer가 없어졌다. 아래 두 단락은 **폐기된 서술**이다
>
> 이 절은 원래 *"현 shared bearer 인증(`verify_token` → `API_TOKENS`)은 **내부 호출자 집합의 구성원임만**
> 검증하고, claim과 사용자 세션의 결합은 검증하지 않는다"* 로 시작하고, **"bearer token이 증명하는 것 =
> 허용된 내부 호출자 집합 중 하나가 요청했다. 그뿐이다"** 를 명시했다. 그 bearer는 **부착돼 있지 않다**
> (코드 `a693af3` / 기록 [`impl/07`](../../../impl/07-composition-api-cli.md) §API layer). 오너 결정이며,
> 형제 서비스(bourbon-memory-api·e3llm-api)도 같은 형태다.
>
> **이 정정이 바꾸지 않는 것**: self-exclusion의 신원 근거. 이 API가 쓰는 신원은 **처음부터** 요청 본문의
> `requester_owner_id`(호출자 주장 값)였고 bearer는 그것을 증명한 적이 **없다**. 위 "증명하지 못하는 것"
> 목록 세 줄은 **그대로 유효하다** — 오히려 bearer 제거로 그 목록이 정직해졌다.
>
> **이 정정이 실제로 바꾸는 것**: 아래 "안전성 2층" 중 ①의 절반이 없어졌다. ①은 이제 **네트워크 경계
> 단독**이다. 그러니 *"토큰을 없애도 잃는 것이 없다"* 고 쓰면 **과장**이다 — 한 층은 진짜로 사라졌다.
> 다만 그 층은 얇았다: **6개 레포에서 동일한 단일 값**이고 **git에 커밋돼 있었고** 회전된 적이 없다.
> 그것이 구분한 것은 "우리 배포 안 / 밖"이고, 그건 네트워크 경계가 이미 하는 일이다. **호출자들 사이는
> 아무것도 구분하지 않았다.**
>
> **따라서 ①의 전부가 된 그 경계는 이제 주석이 아니라 테스트가 지킨다**: ClusterIP 전용 · ingress 계열
> 매니페스트 부재(dormant 파일까지 금지) · overlay가 만드는 리소스 신원 고정 — 셋 다 코드repo
> `tests/test_k8s_manifests.py`. 여기에 "헤더 없는 `/recommend`가 200"을 고정하는 테스트가 짝으로 붙는다.
> **공개 노출이 승인되면 인증은 그 변경의 일부이지 후속 과제가 아니다.**

**증명하지 못하는 것**(bearer가 있던 시절에도, 없는 지금도): 어느 컴포넌트가 호출했는가 · 그 컴포넌트가
특정 owner를 대리할 권한이 있는가 · `requester_owner_id`가 실제 대화의 요청자와 일치하는가.

### fail-loud가 보호하는 범위

| 상황 | 현재 가능한 방어 |
|---|---|
| 필드 누락 (enforcing 정책) | 요청 거부 (422 `requester_identity_required`) |
| UUID 형식 오류 | 스키마 검증 422 |
| resolver 결과 누락·초과·invalid·collision | fail-loud (503 `unresolved_owner_identity`) |
| **다른 사용자의 유효한 owner ID 전달** | **recommendation-api에서 판별 불가** |
| **실제 요청자와 다른 owner ID 전달** | **recommendation-api에서 판별 불가** |

따라서 안전성의 근거는 **2층**이다:

1. ~~네트워크 경계 + shared secret~~ → **네트워크 경계**로 호출자를 내부 서비스로 제한한다
   (**정정 2026-08-11**: shared secret 절반이 없어졌다 — 위 정정 박스 참조. 남은 것은 경계 하나이고,
   그 경계는 매니페스트 가드로 검사된다).
2. moderator/agent runtime이 **인증된 actor로부터 값을 파생한다**는 upstream 계약(§10).

**fail-loud는 그 2층 위의 completeness guard**다 — identity **전달 누락**을 막지만, **유효하지만 틀린 값**은
막지 못한다. "fail-loud가 유일한 안전장치"라는 표현은 과하므로 쓰지 않는다.

---

## 4. 요청 계약

```python
class Query(ApiModel):
    ...
    requester_owner_id: UUID | None = None   # 신뢰된 호출자의 on_behalf_of claim
```

**반드시 별도 top-level 필드로 유지한다**:

- `eligibility_context`(범용 dict)에 **숨기지 않는다** — 보안 의미를 가진 값이 타입 없는 자루에 들어가면
  스키마·OpenAPI·테스트 어디서도 강제되지 않는다. 두 필드는 목적도 다르다(호출 맥락 ≠ 행위자).
- `context_messages`(대화 body)에서 **추출하지 않는다**.
- 같은 production resolver로 `requester_owner_id → requester_agent_id`를 얻고, **agent space에서**
  `edge.agent_id == requester_agent_id`로 비교한다.
- edge의 `memory_owner_id`와 **직접 비교하지 않는다** — 그 필드는 evidence routing 전용이다
  (phase10 spec §2.3). 두 용도를 섞지 않는다.

**optional로 두는 이유**는 mock/eval/diagnostic이 같은 `Query`를 공유하기 때문이며, **enforcing 정책에서는
반드시 요구한다**(§5.2). 장기적으로 "`/recommend` 호출은 환경과 무관하게 항상 특정 사용자를 대신한다"는 제품
계약까지 확정되면 wire schema에서 required로 올리는 편이 단순하지만, **지금은 변경 범위를 줄이는 쪽을 택한다**.

`NormalizedQuery`에는 싣지 않는다. 파이프라인이 `Query`에서 직접 읽어 `bind`에 넘기고(§6.1), 그 이후로는
확정된 `BoundExclusion`만 흐른다 — linker·gate·ranker·serving은 요청자를 알 필요가 없고,
`NormalizedQuery`에 실으면 그 넷 전부에 요청자 정체성이 도달 가능해진다. 도달 범위를 좁게 유지한다.

---

## 5. 배선 계약

### 5.1 정책은 항상 주입된다 (`| None` 금지), 그리고 2단계다

```python
class PreGateExclusionPolicy(Protocol):
    """요청 전제를 먼저 확정한다. linker/retriever I/O보다 앞에서, 등록 순서대로 호출된다 (§6.1)."""

    @property
    def reason(self) -> PreGateDropReason: ...  # 이 정책이 내는 유일한 drop 사유 (로그 키, §7.3)

    @property
    def mode(self) -> ExclusionMode: ...        # startup guard가 읽는 nominal capability (§5.2)

    async def bind(self, requester_owner_id: UUID | None) -> BoundExclusion: ...


class BoundExclusion(Protocol):
    """확정된 요청자에 대한 **per-hit 판정만** 제공한다. 순수 sync — I/O 없음."""

    @property
    def applied(self) -> bool: ...

    def excludes(self, hit: EdgeHit) -> bool: ...
```

정책이 **자기 `reason`을 선언**하므로 `bool` 판정만으로 충분하다 — 사유는 stage가 정책에서 읽는다.
자유 문자열이 아니라 `PreGateDropReason` 멤버이므로 로그 어휘도 닫힌다(§6.2).

오늘 등록되는 정책은 **self-exclusion 하나**이고, 둘 다 `reason`은 `REQUESTER_SELF`다:

- `EnforcingSelfExclusion(resolver)` — `bind`에서 요청자 필수성 검증 + owner→agent resolve를 **모두** 끝낸다.
  `excludes`는 이미 확정된 `requester_agent_id`와의 비교뿐이라 실패할 여지가 없다. `applied=True`.
- `NoopSelfExclusion()` — `bind`는 아무것도 요구하지 않고, `excludes`는 항상 `False`, `applied=False`.

**★ 정책은 pool을 받지도, 만들지도 않는다.** `apply(hits) -> Result`였다면 정책이 리스트를 통째로
반환하므로 `[Disposition(A), Disposition(A)]`(B 유실 + A 복제)나 순서가 뒤바뀐 결과를 **반환할 수 있고**,
`candidate_pool`까지 그 결과에서 파생되므로 **원래 retrieval 결과가 audit log에서 사라진다**. per-hit
판정만 노출하면 정책에게 그럴 권한 자체가 없다 — 리스트 구성은 파이프라인 소유다(§6.1).

**왜 2단계인가**: `bind`와 per-hit 판정이 한 호출이면 검증이 retrieval **뒤**로 밀린다. 그러면 requester가
누락된 요청이라도 grounding이나 retrieval이 먼저 실패할 때 422 대신 `grounding_failed`(422) 또는
`upstream_unavailable`(503)이 나가고 — **"real edge에서 requester는 필수"라는 요청 전제의 오류 우선순위가
upstream 상태에 따라 달라진다.** 요청 전제 위반은 upstream 상태와 무관하게 항상 같은 답을 내야 한다.

async/sync 분할은 코드베이스의 기존 패턴과 같다: I/O를 하는 쪽만 async, 결정 코어는 sync.

**정책을 `| None`으로 두지 않는다.** 이 코드베이스의 기존 관례(`stance_evaluator=None`,
`reason_generator=None`)와 다른데, **그 차이가 정당한 이유**를 계약에 남긴다: 기존 optional collaborator들은
부재 시 **안전한 쪽**으로 떨어진다(명시적 침묵 / 결정적 reason 문자열). self-exclusion의 부재 기본값은
**요청자 자신을 추천하는 것**이다. 비대칭이 패턴 차이의 근거다. optional로 두면 composition 실수 하나가
안전 정책을 조용히 끈다.

### 5.2 선택 축은 stage가 아니라 `REAL_EDGE_ENABLED`

| `REAL_EDGE_ENABLED` | 정책 |
|---|---|
| OFF | `NoopSelfExclusion` |
| ON | `EnforcingSelfExclusion` |

**stage는 관여하지 않는다.** self-exclusion이 필요한 이유는 "production"이라는 이름 때문이 아니라
**real candidate가 요청자 자신을 포함할 수 있기 때문**이다. 축을 stage로 잡으면 dev/진단 stage의 real-edge
실행에서 Noop이 되어 **e2e가 self-exclusion을 영원히 검증하지 못한다** — 지금 `cli/e2e/report.py:211`이
`self_exclusion_enforced: false`를 하드코딩해 둔 구멍이 stage만 바뀐 채 남는다.

이 축의 귀결:

- dev/진단 real run이 **실제 serving 경로와 같은 정책**을 실행한다.
- production promotion 전에 같은 코드가 이미 실측된다.
- stage별 동작 차이가 없다 — e2e 보고서의 `applied=true`가 serving과 동일한 의미다.

**startup guard = 정책 배선 불변식 (양방향)**:

> `REQUESTER_SELF` 정책은 **플래그와 무관하게 항상 정확히 하나** 존재하고, 그 mode가 위 표와 일치한다.
> `ON → ENFORCING` · `OFF → NOOP`. 어긋나면 startup 실패.

**OFF에서도 존재를 강제하는 이유**는 D3("항상 주입")과 §7.3(미적용 정책도 로그에 행을 갖는다)이 실제
계약이 되려면 그래야 하기 때문이다. OFF에서 정책이 통째로 빠지면 **동작은 우연히 Noop과 같지만 audit
의미가 다르다**:

| 로그 | 뜻 |
|---|---|
| `{requester_self, applied=false, excluded_edges=0}` | 정책이 **의식적으로 비활성화**됨 |
| 행 자체가 없음 | **배선이 사라짐** |

사고 조사 때 이 둘을 구별할 수 없으면 "self-exclusion이 왜 안 돌았는가"에 답할 수 없다.

**"정확히 하나"로 쓰는 이유**: stage를 여러 정책이 공유하므로 "주입된 정책이 enforcing인가"로는 부족하고,
"하나 이상"으로 쓰면 같은 사유를 선언한 Noop이 함께 등록돼 있어도 통과한다.

**등록 순서도 배선에서 고정한다**: `exclusions[0].reason is REQUESTER_SELF`. §6.3의 "안전 불변식이 선호보다
먼저"는 오늘 문서상의 규율일 뿐이므로, 나중에 preference 정책이 self 앞에 잘못 등록되면 **둘 다 해당하는
edge의 사유가 preference로 기록된다** — 제거는 되지만 **safety 정책이 발동했다는 audit 증거가 가려진다.**
first-match precedence(§6.1)와는 별개의 검사이므로 테스트도 따로 둔다.

**stage를 보지 않는다** — production stage + 플래그 OFF + Noop은 오늘의 **정상 구성**이므로 "production에
Noop이면 실패"로 쓰면 지금 프로덕션이 못 뜬다.

**"enforcing인지"는 nominal mode로 판별한다** — concrete class `isinstance`가 아니다. 구조적 타입에 정체성
검사를 얹는 것은 맞지 않으므로, **mode를 Protocol의 명시적 capability로 만든다**(§5.1):

```python
class ExclusionMode(StrEnum):
    NOOP = "noop"
    ENFORCING = "enforcing"
```

가드는 **정책 자신의 `.mode`를 읽는다** — `EdgeWiring`에 mode를 별도 필드로 두지 않는다.

**★ 왜 별도 필드가 아닌가**: policy와 mode를 독립된 두 값으로 받으면 `NoopSelfExclusion` + `ENFORCING`
조합이 **가드를 통과한다**. 그런데 이 가드가 막으려는 대상이 정확히 그것(테스트 override, 새 DI 지점)이므로,
"composition root가 둘을 함께 만든다"는 **규율만으로는 가드가 배선 실수를 검출하지 못한다**. mode가 정책
자신의 선언이면 그 조합이 애초에 표현되지 않는다.

이 가드는 **악의적 구현을 검증하는 장치가 아니라 조립 실수를 막는 장치**이므로, 정책이 스스로 선언하는
nominal capability로 충분하다.

위 표만 지키면 이 가드는 동어반복이다. 그럼에도 두는 이유는 **표가 깨질 미래의 경로**를 막기 위해서다:
테스트 override, DI 주입 지점 추가, 또는 플래그를 우회하는 새 조립 함수. 안전 정책은 "지금 배선이 맞다"가
아니라 "틀린 배선으로는 뜨지 못한다"로 지켜야 한다.

`api.main._reject_real_edge_in_production()`(production+real-edge를 거부하는 **promotion 가드**)과는
**별개의 가드**다. 그쪽은 turn-on 시 삭제되지만 이쪽은 영구다 — promotion 커밋이 둘을 헷갈리지 않도록
이름과 테스트를 분리한다.

### 5.3 resolver와 exact-resolution 검증을 공유한다

phase10 spec §9 (2)의 **"candidate와 동일한 production resolver"** 계약을 문자 그대로 지킨다. 오늘
`build_edge_wiring()`은 `DerivedOwnerIdentityResolver()`를 **자기 안에서 생성**하므로(`api/depends/pipeline.py:101`)
공유가 불가능하다. resolver는 이제 **소비자가 셋**이다:

1. `IdentityResolvingEdgeProvider` (edge projection)
2. `EnforcingSelfExclusion` (신규)
3. e2e preflight — 현재 `personal_agent_id()`를 **직접** 호출한다(`cli/e2e/preflight.py:206`). 오늘은 값이
   우연히 일치하지만, 지켜야 할 불변식은 *"같은 함수가 우연히 같은 값을 냄"*이 아니라 **셋이 같은 resolver
   dependency를 쓴다**는 것이다.

따라서 `build_edge_wiring()`의 4-tuple을 6-tuple로 늘리지 않고 이름 있는 결과 타입으로 바꾼다:

```python
@dataclass(frozen=True)
class EdgeWiring:
    edge_provider: MemoryEdgeProvider | None
    eligibility_provider: EligibilityProvider | None
    exclusions: tuple[PreGateExclusionPolicy, ...]   # 오늘은 self-exclusion 하나 (§6.3); mode는 각자 선언
    identity_resolver: OwnerIdentityResolver | None
    edge_version: str | None
    eligibility_version: str | None
```

**exact-resolution 검증도 공유한다.** 현재 그 규칙은 `IdentityResolvingEdgeProvider.get_edges`에
**인라인**으로 있다(`discovery/providers/identity_edge.py:68-93`). self-exclusion이 이를 복사하면
missing/extra/invalid/collision 분류·count-only 로깅·식별자 비노출 규율이 두 곳에서 갈린다:

```python
class IdentityResolutionOperation(StrEnum):
    EDGE_PROJECTION = "owner_identity_resolution_failed"
    REQUESTER = "requester_identity_resolution_failed"


async def resolve_exact(
    resolver: OwnerIdentityResolver, owner_ids: list[UUID], *, operation: IdentityResolutionOperation
) -> Mapping[UUID, str]: ...
```

- 두 호출자가 같은 helper를 쓰면 에러 분류가 한 곳에 고정된다.
- **`operation`을 평문 `str`로 두지 않는다** — 로그 어휘가 조용히 갈라진다(오타·동의어). enum으로 닫는 것이
  이 helper가 지키려는 fail-loud 규율과 일관된다. **어느 값도 식별자를 남기지 않는다** — count와 bucket만.
- **duplicate-owner 검사는 helper에 넣지 않는다.** 그것은 projection source의 계약 위반이라
  `EdgeProjectionError`이고 resolution 실패가 아니다(`identity_edge.py:67`). requester는 owner가
  하나뿐이라 애초에 중복이 불가능하다.
- 단일 requester resolve에도 **전부 검사한다**: 요청 key 정확히 하나 · 결과 key 정확히 일치 · agent id가
  non-blank str · 누락/초과/invalid 거부. collision은 단일 owner에서 성립 불가하므로 `collision=False`.

### 5.4 identity 검증은 결과에 종속되지 않는다

`bind`가 retrieval보다 앞에 있으므로(§6.1) 이 성질은 **구조적으로 보장된다** — 후보가 몇 개든, grounding이
성공하든, 검증은 이미 끝나 있다. 방어하려는 실패 모드를 명시해 둔다: "후보가 없으니 identity가 없어도 된다"
또는 "grounding이 실패했으니 검증까지 갈 필요 없다"는 분기가 생기면 **required identity 계약이 요청 결과에
따라 달라지고**, resolver 장애가 빈 pool이나 grounding 실패에 가려진다.

---

## 6. 파이프라인 위치와 타입

### 6.1 두 위치 — 검증은 맨 앞, 제외는 ②retrieve ↔ ③gate 사이

```
ⓠ normalize_query(query)                     # 요청 형태 검증 (proposition)
   ↓
bound = [await p.bind(query.requester_owner_id) for p in self._exclusions]   # 등록 순서, 순차
   ↓                                         # ★ linker/retriever I/O 전에 모든 bind 완료
① linker.ground(...)                          #   grounding
② retriever.retrieve(...)  → all EdgeHit      #   edge 조회
   ↓
result = PreGateExclusionResult(               # ★ 리스트를 만드는 주체는 파이프라인이다
    policies=tuple(
        ExclusionPolicyState(reason=p.reason, applied=b.applied)
        for p, b in zip(self._exclusions, bound, strict=True)   # 등록 순서, 미적용 포함
    ),
    dispositions=[
        PreGateDisposition(hit=hit, drop_reason=_first_reason(self._exclusions, bound, hit))
        for hit in hits                       # 순회원이 retrieval 결과 그 자체
    ],
)
   ├─ drop_reason is None ──→ ③ Gate → stance shortlist/judge → ④ Ranker → ⑤ serve
   └─ 전체 dispositions ────→ ⑥ decision log (pool + drop 행 + 정책별 applied/count)
```

`_first_reason`은 등록 순서대로 물어 **첫 `excludes(hit) is True`인 정책의 `reason`**을 돌려주고, 없으면
`None`이다 — Gate의 `_need_agnostic_drop`이 쓰는 것과 같은 precedence 관용구다(§6.3).

**★ `bind`는 등록 순서대로 순차 실행한다 — `gather()`로 병렬화하지 않는다.** self-exclusion이 첫 번째이므로
**requester 누락(422)이 뒤 정책의 provider 장애보다 먼저 결정**돼야 한다. 병렬화하면 어느 실패가 먼저
관측되는지가 타이밍에 좌우되고, §5.1이 세운 "요청 전제 위반의 답은 흔들리지 않는다"가 그대로 깨진다.
정책이 몇 개 안 되고 전부 pre-I/O 근처라 병렬화 이득도 없다. 회귀로 잠근다(§12).

**"모든 upstream I/O 이전"이 아니라 "linker/retriever I/O 이전"이다.** `bind` 자체가 async resolver를
호출하고, 향후 preference 정책은 provider I/O를 할 수 있다. 지키는 성질은 *"추천 substrate를 건드리기 전에
요청 전제가 확정된다"*이지 *"아무 I/O도 없다"*가 아니다.

**★ 순회를 파이프라인이 소유한다.** 이 comprehension의 순회원이 `hits` 자신이므로 다음이 **코드 형태에서
바로 따라온다** — 정책의 협조나 사후 검사가 아니다:

- hit마다 disposition이 **정확히 하나** (유실·복제 불가)
- **retrieval 순서 유지**
- 정책은 **제외 여부만** 결정하고 pool을 재작성할 수 없다

정책이 `apply(hits) -> Result`로 리스트를 반환했다면 이 셋은 정책 경계에서
`[d.hit for d in result.dispositions] != hits`를 검사해 fail-loud하는 수밖에 없고, 그건 "구조적으로 참"이
아니라 **"exact 검사로 지키는 불변식"**이다. 검사할 것이 남지 않는 쪽을 택한다. 정책이 늘어도 이 성질은
그대로다 — 순회는 언제나 stage가 소유한다.

**`bind`가 맨 앞인 이유**는 §5.1에 있다 — 요청 전제 위반의 답이 upstream 상태에 흔들리면 안 된다.
`normalize_query`와의 순서는 **normalize 먼저**로 고정한다: 둘 다 순수·pre-I/O라 우선순위가 결정적이고,
둘 다 잘못된 요청은 `invalid_need`를 받는다(임의 선택이 아니라 고정된 계약이라는 점이 중요하다).

**제외 판정이 gate 앞인 이유** — 이 위치가 성립시키는 것:

- 제외된 agent의 **eligibility/persona를 아예 조회하지 않는다** — Gate가 그 agent를 보지 못한다.
- 제외된 agent의 **statement 검색과 stance judge 호출을 하지 않는다** — phase10 spec §9 (3)의
  "반드시 stance search 이전" 요구를 만족하고, 향후 정책에도 같은 절약이 그대로 적용된다.
- Gate의 불변식 **`Candidate ⇔ Eligibility 있음`을 보존**한다.
- self-exclusion이 **eligibility 정책과 분리**된다 — 요청자 정체성 필터는 need-agnostic gate가 아니다.
- Retriever와 edge provider는 requester context를 **몰라도 된다** — phase10 spec §9 (2)의
  "requester context를 받을 수 있는 별도 orchestration 경계" 요구와 정합한다.
- `candidate_pool`에는 retrieval이 **실제 발견한 self edge가 남는다**(§7.2).

**기각한 대안 — Gate 내부 phase-0 필터**(phase10 spec §9 (3)이 언급한 쪽): Gate가 identity resolver와
requester context까지 알게 되고, eligibility 없는 drop을 `GateResult.dropped: list[Candidate]`에 억지로
넣어야 한다 — spec이 피하려던 계약 변경을 Gate 안으로 들여오는 셈이다.

### 6.2 pre-gate disposition 전용 타입

```python
class PreGateDropReason(StrEnum):
    """이 stage가 낼 수 있는 사유의 닫힌 어휘. 정책 하나가 정확히 하나를 소유한다."""

    REQUESTER_SELF = "requester_self"
    # 향후: REQUESTER_BLOCKED = "requester_blocked"  (§6.3)


class PreGateDisposition(StrictBaseModel):
    hit: EdgeHit
    drop_reason: PreGateDropReason | None      # None = Gate로 넘어간다


class ExclusionPolicyState(StrictBaseModel):
    reason: PreGateDropReason      # 정책의 식별자이자 이 정책이 내는 유일한 drop 사유
    applied: bool                  # 이 요청에서 실제로 돌았는가


class PreGateExclusionResult(StrictBaseModel):
    """exclusion 사실의 **단일 진실원** — 서로 다른 사실을 소유하는 두 ordered component (§7.3):

    - ``policies``     : 등록·순서·적용 사실의 정본
    - ``dispositions`` : retrieval pool과 edge별 처분의 정본

    파이프라인이 조립한다 (§6.1) — 정책은 per-hit 판정만 준다.
    """

    policies: tuple[ExclusionPolicyState, ...]   # 등록 순서, **미적용 정책 포함**
    dispositions: list[PreGateDisposition]       # retrieval 원본 순서, 입력 hit 전체

    @model_validator(mode="after")
    def _consistent_policy_set(self) -> PreGateExclusionResult:
        # ① reason은 정책 식별자다 — guard·precedence·집계가 전부 이걸 키로 쓰므로 중복은 그 셋을
        #    동시에 모호하게 만든다.
        reasons = [p.reason for p in self.policies]
        if len(reasons) != len(set(reasons)):
            raise ValueError(f"duplicate pre-gate exclusion policy reason: {sorted(reasons)}")
        # ② 적용하지 않은(또는 등록조차 안 된) 정책이 무언가를 뺄 수는 없다. 모순된 audit 상태는
        #    모델이 거부한다 — 테스트에만 맡기면 잘못된 조합이 잠깐이라도 존재할 수 있다.
        applied = {p.reason for p in self.policies if p.applied}
        used = {d.drop_reason for d in self.dispositions if d.drop_reason is not None}
        if orphans := used - applied:
            raise ValueError(f"dispositions carry drop reasons from unapplied policies: {sorted(orphans)}")
        return self
```

**★ `applied: bool` 하나도, `frozenset[reason]`도 아닌 이유.** 정책이 둘 이상이면 "적용됐다"가 한 비트로
표현되지 않는다 — self-exclusion은 켜졌는데 차단목록 provider는 죽어서 안 돌았다면 `applied=True`는
**거짓말**이다. 그렇다고 적용된 사유의 집합만 담으면 **"등록조차 안 된 정책"과 "등록됐지만 미적용"을 구별
하지 못하고 등록 순서도 잃는다.** 그러면 §7.3이 요구하는 "미적용 정책도 로그에 행을 갖는다"를 만족시키려고
`record()`가 정책 목록을 **또 다른 입력으로** 받아야 하고, 그 순간 "입력 하나에서 전부 파생"이 깨진다.
등록된 정책 전체를 상태와 함께 순서대로 담으면 그 외부 입력이 사라진다.

**reason의 유일성**은 위 validator 외에 **composition root에서도** 강제한다 — 조립 시점에 터지는 편이
요청 처리 중에 터지는 것보다 낫다. 같은 `REQUESTER_SELF`를 선언하는 Noop과 Enforcing이 동시에 등록되면
guard가 어느 쪽을 검사할지, `excluded_edges`가 누구 것인지 모두 모호해진다.

**★ `(kept, dropped)` 두 리스트로 나누지 않는 이유**: 두 리스트는 "합쳐서 입력과 같다"를 **검사해야만**
보장되고, retrieval 순서도 잃는다. disposition 하나가 hit 하나를 감싸고 **그 리스트를 파이프라인이 순회로
만들면**(§6.1) 유실·복제·순서 뒤바뀜이 코드 형태에서 배제된다. 그리고 §7이 필요로 하는 네 가지가 전부 이 한
값에서 나온다:

| 필요한 것 | 파생 |
|---|---|
| `candidate_pool` (retrieval 원본 순서) | `[d.hit for d in dispositions]` |
| Gate 입력 | `[d.hit for d in dispositions if d.drop_reason is None]` |
| pre-gate drop 행 | `d.drop_reason is not None`인 것들 |
| 등록된 정책과 그 순서 | `policies` |
| 정책별 `applied` | `policies[i].applied` |
| 정책별 `excluded_edges` | `dispositions`의 사유별 개수 |

**남는 계약**:

| 불변식 | 지키는 방법 |
|---|---|
| 입력 hit 전체를 입력 순서 그대로 감싼다 | **파이프라인 순회**(§6.1) — 검사 없음 |
| 적용되지 않은 정책의 사유가 disposition에 없다 | **모델 validator** — 잘못된 상태가 생성 불가 |
| 정책 `reason`이 유일하다 | **모델 validator + composition root** |
| `bind`가 등록 순서대로 순차 실행된다 | 파이프라인 코드 형태 + 회귀(§12) |
| Enforcing은 `applied=True`, Noop은 `applied=False` | 정책 단위 테스트 |

- `(kept, excluded: list[EdgeHit])`처럼 **bare tuple로 반환하지 않는다** — drop reason이 타입에 없으면
  하류 코드가 **위치에 기대어** `"requester_self"`를 하드코딩한다.
- 값이 현재 하나뿐이어도 **StrEnum**으로 둔다: 정책의 출력 vocabulary가 닫히고, 오타가 막히고, 향후 pre-gate
  정책이 추가돼도 자연스럽게 확장된다. 코드베이스 선례와도 일치한다(`StanceSilenceReason`, `AnchorVia`,
  `StancePosition`). 최종 `DropEntry.reason: str`로 내려갈 때 `.value`로 낮춘다.
- **전체 drop reason을 하나의 거대 enum으로 통합하지 않는다.** gate/ranking reason은 현재 `Candidate`
  mutation 계약(`Candidate.drop_reason`)이고, pre-gate disposition만 별도 생명주기를 갖는다.
- `applied`는 정책이 스스로 보고한다 — 호출부가 정책 종류를 보고 추론하면 §7.3의 마커가 배선과 어긋날 수 있다.

### 6.3 stage의 일반화 경계 — 무엇을 공유하고 무엇을 공유하지 않는가

이 stage는 **requester-scoped pre-gate exclusion**이고, self-exclusion은 그 위의 **첫 정책**일 뿐이다.
두 번째 정책은 이미 예고돼 있다: 사용자가 "이 agent는 다시 만나고 싶지 않다"로 표시한 negative preference —
Alpha에서 **reserved로 결정된 별도 `UserPreferenceProvider` 신호**(출처는 bourbon-api 예상)다. 그때 새
파이프라인 단계·새 로그 블록·새 disposition 타입을 만들지 않고 **정책 하나를 등록**한다.

**공유하는 것** (stage의 자산):

- `PreGateDisposition` · `PreGateExclusionResult` · `PreGateDropReason` 어휘
- 파이프라인 순회와 그로부터 나오는 세 성질(§6.1)
- decision log의 pool·drop 행·정책별 집계 파생 경로(§7)
- gate·stance judge 이전이라는 **비용 절약 위치**

**공유하지 않는 것** (정책이 각자 선언):

- **집행 의미.** self-exclusion은 **안전 불변식**이라 identity 누락에 fail-loud한다(§8). 선호 기반 정책은
  provider 장애 시 요청을 죽여야 하는지가 **전혀 다른 질문**이고, 그 답은 그 정책의 설계에서 정한다.
  하나로 뭉치면 "requester 누락"이 여러 선택 신호 중 하나로 **희석된다**.
- **provider·설정·집행 규칙.** 정책마다 자기 것을 갖는다. 다만 **`bind` 인터페이스는 지금 넓히지 않는다** —
  예정된 차단 선호도 `requester_owner_id`만으로 충분하다. **추가 요청 필드가 필요해지는 정책이 생기면 그때
  typed bind context 확장을 별도로 설계한다**(지금 추측으로 넓히면 쓰이지 않는 일반성만 남는다).
- **mode 축.** self-exclusion의 Enforcing/Noop 축은 `REAL_EDGE_ENABLED`다(§5.2). 다른 정책의 축은 그
  정책의 것이다. startup guard가 **사유로 정책을 특정해** 검사하는 이유가 이것이다(§5.2).

**★ 이 stage는 removal-only다.** 후보를 **빼는** 신호만 여기 살 수 있다. 즐겨찾기처럼 후보를 **승격**하는
선호는 여기 오면 안 된다 — pre-gate는 eligibility·maturity·discoverable 이전이라 승격 신호를 여기 두면
**게이트를 건너뛴다**(기존 "선호는 gate 우회 금지" 결정과 정합). 제거는 노출 위험을 만들지 않으므로 안전하다.
승격은 ranking 단계의 tie-break로 남는다.

**정책 precedence**: 등록 순서대로 물어 첫 `True`가 사유를 정한다(§6.1의 `_first_reason`). Gate의
`_need_agnostic_drop`이 "가장 강한 노출 게이트 먼저"로 precedence를 두는 것과 같은 규율이다.
**self-exclusion이 항상 먼저**이며 — 이건 문서상의 권고가 아니라 **composition root가 검사하는 배선
불변식**이다(`exclusions[0].reason is REQUESTER_SELF`, §5.2). 안전 불변식이 선호보다 앞선다.

---

## 7. decision log 계약

### 7.1 spec §9 (3)의 전제 정정

phase10 spec §9 (3)은 *"eligibility 이전 drop을 현재 Candidate 기반 drop 계약으로는 기록할 수 없다"*고 썼다.
결론(별도 표현이 필요하다)은 맞지만 **층을 혼동했다**. 정확히는:

> Eligibility 이전 drop은 현재 **Candidate 기반 `DecisionLog.record()` 매퍼 API**로는 표현할 수 없지만,
> **직렬화 스키마인 `PoolEntry`와 `DropEntry`는 이미 `EdgeHit`만으로 구성할 수 있다.** 따라서 `GateResult`를
> 변경하지 않고, **pre-gate edge disposition 입력을 `DecisionLog`에 추가**한다.

| 타입 | 필드 | `Eligibility` 필요? |
|---|---|---|
| `PoolEntry` (`structs/decision_log.py:79`) | `agent_id, anchor_id, via, via_qid` | 아니오 — 전부 `EdgeHit`에 있음 |
| `DropEntry` (`structs/decision_log.py:88`) | `agent_id, anchor_id, reason` | 아니오 — 전부 `EdgeHit`에 있음 |

Candidate에 묶인 것은 **매퍼의 인자**뿐이다(`decision_log.py:69`의 `record()` 시그니처, `_pool_entry`/
`_drop_entry`). 따라서 "별도 audit 경로 **vs** `GateResult` 계약 변경"은 실제 선택지가 아니었다.

### 7.2 `record()` 입력 — pre-gate는 한 덩어리, candidate는 별개

느슨한 `Candidate | EdgeHit` union을 매퍼 전체에 퍼뜨리는 대신 입력을 나눈다:

```python
def record(
    *,
    normalized: NormalizedQuery,
    grounding: GroundingResult,
    pre_gate: PreGateExclusionResult,         # pool + pre-gate 처분 + 적용 사실 (§6.2 표대로 파생)
    candidate_dropped: list[Candidate],       # gate + shortlist + ranking
    ranked: list[Candidate],
    recommendation: Recommendation,
) -> DecisionLogRecord: ...
```

이 형태가 성립시키는 것: pool이 **진짜 pre-gate retrieval 결과**가 되고 · pre-gate drop이 eligibility를
요구하지 않고 · 기존 Candidate drop의 `drop_reason is required` loud-fail(`decision_log.py:166`)이 그대로
유지된다.

**★ `candidate_pool`을 별도 인자로 받지 않는다.** 받으면 "이 pool과 저 처분이 같은 retrieval에서 왔는가"를
**검사해야** 하는데, 길이 비교로는 *길이만 같고 내용이 다른* 입력을 못 잡고 multiset 비교로 올려도 결국
**검사로 지키는 불변식**일 뿐이다. `PreGateExclusionResult.dispositions` 하나에서 pool을 파생하면 **어긋날
두 입력이 애초에 없다** — 검사할 것이 남지 않는 쪽이 검사를 강화하는 쪽보다 낫다.

pre-gate 처분을 drop 리스트와 집계 블록으로 **나눠 받지 않는** 이유도 같다(§7.3).

**wire `dropped` 배열 순서**: pre-gate drop 행 먼저, 그다음 candidate drop 행. 실제 발생 순서와 일치한다.

**★ 기존 동작 변경 — `candidate_pool` 행 순서.** 오늘은 `gated.survivors + gated.dropped`(`pipeline.py:151`)
라서 **생존자 먼저, 탈락자 나중**이다. `list[EdgeHit]`로 바꾸면 **retrieval 원본 순서**가 된다. 이는 필드의
문서화된 의미(`eval/metrics.py:264` — *"Recall is a retrieval signal, so it reads the pre-gate
`candidate_pool`"*)에 **더 맞으므로 받아들인다**. 영향 범위를 확인했다:

- **eval baseline 무영향** — `eval/gates.py:117`이 직렬화하는 것은 `MetricReport`이지 decision log가 아니다.
- **지표 무영향** — `eval/metrics.py:276`이 pool을 set comprehension으로 읽는다.
- **깨지는 것** — 단위 테스트 단언 1줄(`tests/test_decision_log.py:430`, `pool = survivors + drops`)과
  e2e 리포트 §9 나열 순서(외관). 그 단언은 **`pool preserves retrieval order`로 바꾼다**.

### 7.3 safety block — `applied`는 drop과 별개로 필요하지만, **입력은 하나여야 한다**

`requester_self` drop이 **있으면** 정책이 발동했음이 증명된다. 그러나 drop이 **없다**는 사실은 다음 둘을
구별하지 못한다: ⓐ 정책이 정상 적용됐지만 self edge가 없었음 · ⓑ 정책이 아예 배선되지 않았음. 따라서 적용
사실 자체를 기록한다 — **정책마다 한 행씩**:

```python
class ExclusionPolicyLog(StrictBaseModel):
    reason: PreGateDropReason      # 어느 정책에 대한 행인가
    applied: bool
    excluded_edges: int = Field(ge=0)


class DecisionLogRecord(StrictBaseModel):
    ...
    pre_gate_exclusions: list[ExclusionPolicyLog]   # 등록된 정책 전부, 등록 순서
```

**등록된 정책은 하나도 빠짐없이 행을 갖는다** — `applied=false`인 정책도 포함한다. 그래야 "이 배포에 정책이
둘 등록됐고 그중 하나만 돌았다"가 로그만으로 읽힌다. 오늘은 `[{requester_self, applied, N}]` 한 행이다.
등록 목록과 순서는 **`PreGateExclusionResult.policies`가 이미 담고 있으므로**(§6.2) 외부 입력이 필요 없다.

**★ 이 블록과 pre-gate drop 행을 `record()`가 따로 받으면 안 된다.** 두 입력이 독립이면 호출자가
`excluded_edges=1` + drop 0개를, 또는 `applied=False` + `requester_self` drop을 넘길 수 있고 — **진단
로그가 자기모순**에 빠진다. 안전 정책의 감사 기록에서 이건 특히 나쁘다: 사고 조사 때 어느 쪽을 믿어야 할지
알 수 없다.

따라서 `record()`는 `PreGateExclusionResult` **하나만** 받고 전부 내부에서 파생한다:

```python
# record() 내부 — 전부 파생이지 입력이 아니다
dropped_hits = [d for d in pre_gate.dispositions if d.drop_reason is not None]
counts = Counter(d.drop_reason for d in dropped_hits)

candidate_pool=[_pool_entry_from_hit(d.hit) for d in pre_gate.dispositions],   # retrieval 순서
dropped=[_pre_gate_drop_entry(d) for d in dropped_hits] + [_drop_entry(c) for c in candidate_dropped],
pre_gate_exclusions=[
    ExclusionPolicyLog(reason=p.reason, applied=p.applied, excluded_edges=counts[p.reason])
    for p in pre_gate.policies           # 등록 순서, 미적용 포함 — 전부 이 한 입력에서 나온다
],
```

**단일 진실원은 `PreGateExclusionResult` 하나다.** `policies`는 **등록·순서·적용 사실**의 정본이고,
`dispositions`는 **retrieval pool과 edge별 처분**의 정본이다. 로그는 이 두 ordered component에서만
파생한다. 이는 이중 진실원이 아니라 — **서로 다른 사실을 소유하는 한 aggregate의 두 필드**이고, 둘의 정합은
모델 validator가 지킨다(§6.2). 규율도, 호출자 간 합의도 아니고 **구조**다.

| 상황 | 기록 |
|---|---|
| Noop / mock / eval | `applied=false, excluded_edges=0` |
| Enforcing 적용, self edge 없음 | `applied=true, excluded_edges=0` |
| Enforcing 적용, 실제 제외 | `applied=true, excluded_edges=N` |

- **`LoggedQuery`에 넣지 않는다** — "요청이 무엇이었나"와 "정책이 무엇을 했나"는 다른 사실이다.
- **requester agent id는 기록하지 않는다.** 제외된 agent id는 어차피 `DropEntry`에 남지만, 별도 requester
  identity 필드를 추가하면 로그의 개인정보 의미가 강해진다. `applied` + 개수로 운영 진단 목적은 충족된다.
- 순수 추가 필드이므로 baseline 무영향이다(§7.2).

---

## 8. 에러 계약 — 세 경우를 분리한다

| 경우 | 결과 |
|---|---|
| malformed UUID | Pydantic 스키마 검증 **422** |
| enforcing 정책 + 필드 누락 | 신규 도메인 에러 `requester_identity_required` → **422** |
| resolver 계약 위반 (누락/초과/invalid/collision) | 기존 `UnresolvedOwnerIdentityError` → **503** |

- 세 번째는 **새 에러를 만들지 않는다** — `discovery/errors.py`의 `UnresolvedOwnerIdentityError`가 이미
  `missing/extra/collision/invalid` 진단 필드를 갖고 `api/errors.py:37`에서 503으로 매핑되며, 메시지에 owner
  id를 흘리지 않는 규율까지 문서화돼 있다. 단일 owner이므로 `collision=False`로 넘긴다.
- 두 번째가 422인 이유: 내부 호출자가 **필수 요청 필드를 빠뜨린 것**이므로 요청 측 문제다. resolver나
  identity infrastructure가 계약을 못 지킨 경우(503)와 의미가 다르다.
- 새 코드도 `api/errors.py`의 `_STATUS_BY_CODE` + `register_domain_error_handlers` 두 곳에 등록한다.

---

## 9. e2e 진단 계약

**`--requester-owner-id`를 real-edge 실행에서 필수로 만든다.** `_check_options` 단계에서 막는다:

```
REAL_EDGE_ENABLED=true + --requester-owner-id 없음
→ operator-correctable usage/precondition → exit 2
```

CLI 검사는 **친절한 조기 오류**이고, enforcing 정책의 같은 조건 검사가 **실제 불변식**이다. 둘 다 있어야 한다
(CLI를 우회해 파이프라인을 직접 호출하는 경로가 있으므로). 일반 `/recommend`에서는 같은 누락이
`requester_identity_required` 422로 나간다.

**안전 우회 플래그(`--allow-missing-requester` 등)를 만들지 않는다.** 만들면: 안전 정책을 끄는 운영 플래그가
영구 API가 되고 · acceptance run이 실제 production 후보 경로와 달라지고 · 옵션을 켠 채 실행한 보고서가 정상
진단처럼 남고 · `applied=false`를 사람이 놓치면 self-exclusion을 검증했다고 오독한다.

**리포트 정직화**: `cli/e2e/report.py:211`의 하드코딩된 `self_exclusion_enforced: false`를 decision log의
`pre_gate_exclusions` 행에서 읽은 값으로 바꾼다. 정책별 `applied`와 `excluded_edges`를 그대로 노출하고,
"drop이 없음"을 "검증됨"으로 렌더링하지 않는다.

**대가(수용)**: 아직 돌지 않은 **실배포 real run 1회**에 인자가 하나 는다. 이는 비용이 아니라 **진단 전제의
명문화**다 — 플래그를 빼먹은 run이 "self-exclusion 검증됨"으로 오독될 여지가 사라진다.

---

## 10. upstream 계약 — 호출자가 지켜야 할 문장

> **호출자는 외부 요청 body의 owner ID를 그대로 중계하지 않는다. 자신이 인증·인가한 session/event actor에서
> `requester_owner_id`를 파생한다.**

내부 API라고 해도 최종 사용자 입력이 backend를 통해 **간접 전달**될 수 있으므로 이 문장이 계약의 핵심이다.
§3의 2층 신뢰 모델에서 **2층 전체가 이 문장에 걸려 있다**. (**2026-08-11 이후 더 그렇다** — ①이 shared
secret을 잃고 네트워크 경계 단독이 됐으므로, 이 문장은 두 층 중 *검사 가능한 쪽*이 아니라 *합의에 의존하는
쪽* 전부를 홀로 지탱한다. 호출자 적용 확인이 왜 gate인지의 근거가 그만큼 세졌다.)

**호출자 합의가 닫는 것과 닫지 않는 것을 구분한다.** 합의는 **외부 계약의 불확실성**을 해소한다 — "누가
어떤 값을 어떻게 파생해 보내는가"가 정해진다. **운영상의 gate는 그것으로 닫히지 않는다.** 남은 조건 셋:

| 조건 | 증명 방법 |
|---|---|
| ⓐ Discovery 구현 | §12 테스트 계약 전부 green |
| ⓑ 호출자 적용 | moderator/agent runtime이 실제로 필드를 채워 호출 |
| ⓒ 비프로덕션 acceptance | real-edge 진단 run에서 `applied=true`와 실제 제외를 관측(§9) |

셋 다 없이 "gate 1이 닫혔다"고 쓰면 **turn-on gate 목록이 실제보다 앞서간다** — 그 목록의 유일한 쓸모는
정직함이므로 앞서가는 순간 쓸모가 없어진다.

---

## 11. 이 슬라이스가 닫지 않는 것

- **유효하지만 틀린 owner ID** — 현 인증 구조로 판별 불가(§3). upstream trust 계약이 담당한다.
- **호출자 귀속** — 로그가 "어느 컴포넌트가 호출했는지"를 남기지 못한다. **별도 backlog**이며 이 슬라이스에
  섞지 않는다. **정정(2026-08-11)**: 원인 서술이 바뀌었다. 이전에는 *"`API_TOKENS`가 `name:secret` 매핑이
  아니어서"* 였는데, 이제 bearer 자체가 미부착이므로 **토큰 형태를 고쳐서 닫히는 항목이 아니다.** 귀속이
  필요해지면 그것은 인증 재도입이거나 별도의 호출자 식별 수단(예: mesh 신원)이며, **어느 쪽이든 이 항목이
  아니라 그 결정의 일부**다.
- **phantom agent 정책** — resolve된 requester agent가 실제로 존재하지 않는 경우(fail-loud vs silent
  exclusion)는 여전히 미결이며 phase10 spec §9의 별도 항목이다.
- **owner당 복수 personal agent** — 현 canonical 계약은 결정적 1:1이므로 분기가 아니다(phase10 spec §9 (2)).
  지원하게 되면 resolver 출력과 self-exclusion 입도를 함께 재설계해야 한다.
- **나머지 turn-on gate 3건** — producer-side pin(B1), memory-api R1–R6, phantom agent. 이 슬라이스는
  gate 1만 다루며, **그 gate에 필요한 설계 결정만** 닫는다(§10 표의 ⓐⓑⓒ 미완).
- **production turn-on 자체** — `_reject_real_edge_in_production()` 제거는 gate 4건이 **전부** 닫힌 뒤의
  별도 커밋이다. 이 문서는 그 커밋의 선행 조건 하나를 준비할 뿐이다.

---

## 12. 테스트 계약

**정책 단위 — `bind`**
- enforcing + requester 누락 → `requester_identity_required`.
- enforcing + resolver가 빈/초과/blank/non-str 매핑 반환 → `UnresolvedOwnerIdentityError`, 로그에
  **식별자 없음**(count와 bucket만).
- noop + requester 누락 → 정상 bind (아무것도 요구하지 않음).

**정책 단위 — `excludes` / `applied` / `reason` (§5.1)**
- enforcing + requester 자신의 edge → `True`; 그 외 → `False`. 두 변형 모두 `reason is REQUESTER_SELF`.
- **`EnforcingSelfExclusion.applied is True`, `NoopSelfExclusion.applied is False`** — 항상.
- noop → 어떤 hit에도 `False`, requester를 bind해도 마찬가지.
- `EnforcingSelfExclusion.mode is ENFORCING`, `NoopSelfExclusion.mode is NOOP` — 가드가 읽는 값이 정책
  자신의 선언임을 고정한다(§5.2).

**모델 불변식 (§6.2)**
- 적용되지 않은(또는 등록조차 안 된) 정책의 사유를 가진 disposition → 생성 자체가 `ValueError`.
- 같은 `reason`을 선언한 정책 2개 → 생성 자체가 `ValueError`. composition root에서도 같은 검사가 돈다.

**파이프라인 조립 (§6.1)**
- `dispositions`가 `hits`를 **전부·한 번씩·같은 순서로** 감싼다 — 순회가 코드 형태라 별도 검사가 없으므로,
  회귀로 이 성질을 고정한다(파이프라인이 다시 정책에 리스트 생성을 맡기면 깨진다).
- enforcing + self edge 존재 → 그 edge만 `REQUESTER_SELF`, 나머지 `None`.
- enforcing + self edge 없음 → drop 0개, **`policies=[{REQUESTER_SELF, applied=True}]`** (§7.3의 핵심 구별).
- **정책 2개(fake) 등록 → 등록 순서대로 첫 `True`가 사유를 정하고, 미적용 정책도 `policies`에 남는다**(§6.3).
  오늘 배포에는 정책이 하나뿐이지만 stage의 일반성은 지금 고정한다.
- **`bind`는 등록 순서대로 순차** — 첫 정책이 `bind`에서 raise하면 **뒤 정책의 `bind`가 호출되지 않는다**
  (fake 정책 2개로 확인). 이게 깨지면 requester 누락(422)이 preference provider 장애에 가려질 수 있다.

**★ 오류 우선순위 (P1 — §5.1/§6.1)**
- **requester 누락 + linker·retriever도 실패하도록 구성** → `requester_identity_required` **422가 나가고
  두 provider가 한 번도 호출되지 않는다.** 빈 hits 테스트만으로는 이 우선순위가 보장되지 않으므로 별도로
  고정한다.
- resolver 실패 + 같은 구성 → **503이 나가고** 역시 upstream 호출 0회.

**파이프라인 통합**
- self 제외된 agent에 대해 **eligibility·persona provider가 호출되지 않는다**(spy provider로 확인).
- for/against 요청에서 self 제외된 agent에 대해 **stance 검색·judge가 호출되지 않는다**.
- decision log: self edge가 `candidate_pool`에는 **남고** `dropped`에 `requester_self`로 있다.
- `candidate_pool`이 **retrieval 순서**를 보존한다(기존 단언 교체, §7.2).
- 정책 행의 `excluded_edges`가 `dropped`의 그 사유 행 수와, `candidate_pool` 길이가 `dispositions` 길이와
  **항상 일치**한다 — 단일 입력에서 파생되므로 구조적으로 참이지만, 누군가 다시 갈래를 늘리면 깨지므로
  회귀로 잡는다(§7.2 · §7.3).
- **등록된 정책은 `applied=false`여도 로그에 행이 있다**(§7.3).

**배선 — 양방향 불변식 (§5.2)**

| `REAL_EDGE_ENABLED` | `REQUESTER_SELF` 정책 | 결과 |
|---|---|---|
| ON | Enforcing 하나 | **정상 부팅** |
| OFF | Noop 하나 | **정상 부팅** (오늘의 프로덕션 구성) |
| ON | Noop | startup 실패 |
| ON | 없음 (다른 정책만 등록) | startup 실패 |
| OFF | 없음 | startup 실패 — audit에서 "의식적 비활성화"와 "배선 소멸"이 구별돼야 한다 |
| OFF | Enforcing | startup 실패 |
| 무관 | 같은 사유 2개(Noop+Enforcing) | 조립 시점 실패 ("정확히 하나") |

- **`exclusions[0].reason is REQUESTER_SELF`** — self 정책이 첫 번째임을 배선에서 확인한다. §6.1의 fake
  정책 precedence 테스트와 **별개**다: 그쪽은 "첫 `True`가 이긴다", 이쪽은 "self가 그 첫 자리에 있다".
- 위 표의 판정은 **stage와 무관**하다 — production stage에서도 플래그 OFF + Noop이면 정상 부팅한다
  (가드 과잉차단 회귀).
- edge projection·self-exclusion·e2e preflight가 **같은 resolver 인스턴스**를 받는다.
- `resolve_exact`의 두 호출자가 같은 실패 분류·로그 규율을 쓴다(`IdentityResolutionOperation`만 다름).

**e2e CLI**
- real edge ON + `--requester-owner-id` 없음 → **exit 2**, 리포트 생성 안 함.
- 리포트의 self-exclusion 상태가 decision log `pre_gate_exclusions`에서 나오고 하드코딩이 남아 있지 않다.

**회귀**
- eval gate EXIT 0, baseline byte-identical (§7.2에서 근거 확인).

---

## 13. phase10 spec에 반영할 정정

[2026-07-24-phase10-real-edge-contract-slice-design.md](2026-07-24-phase10-real-edge-contract-slice-design.md)
§9의 self-exclusion 항목을 다음과 같이 고친다. **구현과 함께가 아니라 이 spec 확정 시점에** 고친다 — 그래야
두 문서가 동시에 참이다.

- **(1)** "신뢰된 upstream만 설정 가능한 identity context" → §3의 구체적 신뢰 모델로 교체. 추상적 "외부 입력
  오용 위험"을 배포 구조에 맞는 계약으로 대체한다.
- **(2)** agent space 비교·`memory_owner_id` 미사용·1:1 매핑 근거는 **그대로 유지**하고, "동일한 production
  resolver" 요구를 §5.3의 **공유 resolver + `resolve_exact` 계약**으로 구체화한다(오늘은
  `build_edge_wiring()`이 resolver를 자기 안에서 생성해 공유가 불가능하다는 사실을 함께 적는다).
- **(3)** "현재 Candidate 기반 drop 계약으로는 기록할 수 없다" → §7.1의 층 구분 문장으로 교체.
- **(4)** "fail-loud" → 유지하되 **completeness guard**로 범위를 좁힌다(§3). "유일한 안전장치"라는 표현을
  쓰지 않는다.
- **(205)** "dormant slice에서는 구현하지 않고 계약만 기록" → 이 문서를 가리킨다.

**★ 상태 표기는 `unimplemented` → `closed`가 아니라 `design resolved; implementation/acceptance pending`
으로 바꾼다.** 바로 closed로 쓰면 §10 표의 ⓐⓑⓒ가 없는데도 turn-on gate 목록이 닫힌 것처럼 읽힌다.
gate 자체는 §10의 셋이 증명된 뒤 **별도 커밋**으로 닫는다 — 그 커밋이 "gate 1 통과" 기록이다
(phase10 spec이 promotion 가드 제거를 다루는 방식과 같은 규율).
