# Gorse feedback 의미론 — 무엇을 보내면 무엇이 일어나는가

> **결론**: Gorse는 feedback 타입의 의미를 정해 주지 않는다. `positive`·`read`·`negative` 세 버킷
> 설정이 전부이고, 그 해석은 **적재 시점이 아니라 재계산 시점**에 붙는다. 그래서 **의미론은 나중에
> 바꿀 수 있는 결정**이고, 원본을 우리가 갖고 있는 한 소급해서 다시 정할 수 있다(§5).
>
> 그러나 **서빙 쪽 부작용은 버킷과 무관하게 걸린다.** 어떤 타입이든 feedback row가 하나라도 있으면
> 그 item은 그 requester의 추천에서 **영구히 빠진다**(§2). 이것이 기본값이고, "추천으로 만나 써 본
> 상대도 다시 추천될 수 있어야 한다"는 우리 요구와 정면으로 충돌한다. 레버는 `enable_replacement`
> 하나뿐이며, 그 레버는 **감쇠 상수만 주고 시간 축을 주지 않는다**(2-4).
>
> 여기서 규율 넷이 나온다.
> **① 의미가 애매한 이벤트는 Gorse에 보내지 않는다** — "어느 버킷에도 안 넣기"는 중립이 아니라
> 조용한 제외다(6-1).
> **② `negative`는 "다시 보여주지 마라"에만 쓴다** — replacement로도 돌아오지 않는다(2-5).
> **③ 이진 판단은 `Value`와 식으로 미룬다** — 임계값은 나중에 소급 변경된다(6-2).
> **④ `auto_insert_*`를 끄고, 프로젝션을 재실행 가능한 pass로 만든다** — 켜 두면 Gorse가 우리
> 카탈로그 경계를 넘어 실체를 만들고, 그냥 끄면 순서 경합에서 조용히 유실된다(§7).
>
> **문서 지위**: 조사 자료. 채택·기각은 설계 문서가 소유한다.
> [`gorse.md` §7-5](gorse.md)가 "Gorse는 이 이름의 의미를 대신 정해 주지 않는다"에서 멈춘 지점의
> 다음을 채우고, [`inbound_event_contract.md` §3-4](../inbound_event_contract.md)가 정할 프로젝션 규칙의
> 근거가 된다. **이 문서는 어떤 이벤트가 positive인지 정하지 않는다** — 정할 때 무엇을 알고 정해야
> 하는지만 적는다.
>
> **증거 등급**: `문서`(v0.5.11 **소스 직접 확인** — 파일:줄 표기, 재현은 §9) · `실측`(인용, 원본은
> [`gorse.md` §11](gorse.md)) · `판단` · `열린 항목`.
> ⚠ **소스 독해이지 실행 검증이 아니다.** `gorse.md` §11의 실측과 등급이 다르다. 채택 전 §8의 F5·F8은 컨테이너로
> 확인해야 한다.

---

## 1. 세 버킷과 그 정확한 효과

### 1-1 버킷은 이름 목록이 아니라 **식**이다

```go
// common/expression/expression.go:55
type FeedbackTypeExpression struct {
    FeedbackType string
    ExprType     // None | Less | LessOrEqual | Greater | GreaterOrEqual
    Value        float64
}
func (f *FeedbackTypeExpression) Match(feedbackType string, value float64) bool  // :156
```

기본 `config.toml`의 `positive_feedback_types = ["star","like","read>=3"]`가 그 예다. `read>=3`은
**타입이 `read`이면서 `Value >= 3`**을 뜻한다.

`판단` **이것이 애매함을 다루는 1차 도구다.** 이진 판단("깊이 몇부터 positive인가")을 계약에
새기지 않고 연속값으로 적재한 뒤, 임계값을 config에서 나중에 정할 수 있다. 임계값 변경은 §5의
경로로 **소급 적용**된다.

> ⚠ **`negative_feedback_types`는 배포되는 `config.toml` 템플릿에 없다.** `config.go:249`에는 있고
> 주석이 `// negative feedback type (highest priority)`다. 템플릿만 읽으면 버킷이 둘인 줄 안다.

| 필드 | 위치 |
|---|---|
| `positive_feedback_types` | `config/config.go:248` |
| `negative_feedback_types` | `config/config.go:249` — **템플릿 누락** |
| `read_feedback_types` | `config/config.go:250` |
| `positive_feedback_ttl` | `config/config.go:251` |

### 1-2 학습 데이터셋에서의 라벨

`master/tasks.go`가 CTR 데이터셋을 조립하는 자리가 의미론의 전부다.

```go
// :701  insert explicit negative feedback (highest priority)
Target = append(Target, -1)
// :711  insert positive feedback
Target = append(Target,  1)
// :720  insert read feedback (implicit negative)      ← 주석 원문
Target = append(Target, -1)
```

우선순위는 **negative > positive > read**이고, 각 단계가 앞 집합을 skip한다(`:535`, `:636`).
따라서 한 `(user, item)` 쌍은 **정확히 하나의 라벨**을 받는다.

★ **`read`는 "이미 봤으니 빼기"가 아니라 학습에서 `-1`이다.** 노출됐는데 전환되지 않은 것을 부정
예제로 쓰는 것이고, [`README.md` §4](README.md)의 "노출은 positive가 아니라 선택 기회와 평가
분모"가 여기서 기계적으로 구현되어 있다. 우리 `exposed`가 **실제 렌더**를 뜻할 때만 맞는 의미이며,
그렇지 않으면 잘못된 부정이 학습에 들어간다(2-6의 `write-back-type` 참고).

버킷에 없는 타입은 세 스캔이 `WithFeedbackTypes(...)`로 필터하므로 **학습에서는 라벨이 붙지 않는다.**
서빙에서는 다르다 — §2.

### 1-3 어느 recommender가 feedback을 읽는가

| recommender | feedback 사용 |
|---|---|
| `collaborative` (mf) | 예 — 항상 |
| `ranker` (`fm` / `llm`) | 예 — 1-2의 CTR 데이터셋 |
| `item-to-item` `type="users"` | 예 |
| `user-to-user` `type="items"` | 예 |
| `non-personalized` | 예 — 식에서 이름을 직접 참조: `count(feedback, .FeedbackType == 'star')` |
| **`item-to-item` `type="tags"`** | **아니오** |

★ 마지막 행이 [`gorse.md` §11-2 경로 C](gorse.md)(라벨별 개별 쿼리 + 가중 합산)이고 `D07`이
surface 1의 후보 생성을 여기 맡긴다. **이 경로의 스코어링은 feedback을 읽지 않는다.**

> ⚠ **정정(2026-09-03).** 이 자리에 "surface 1은 feedback을 전혀 읽지 않는다"고 단정했는데 절반만
> 맞다. **스코어링은** 읽지 않지만, 이웃 조회에 `?user-id=`를 넘기면 **서빙 단계에서 feedback 기반
> 제외가 걸린다**(`server/rest.go:500`, 파라미터 설명 그대로 `"Remove read items of a user"` ·
> `gorse.md` §11-5 실측).

`결정` **surface 1의 이웃 쿼리에 `?user-id=`를 넘기지 않는다.** 그 파라미터는 선택이고, 재추천 정책은
우리 것이므로(`D18` · §8 `FBK-F1`) Gorse에 그 판단을 넘길 이유가 없다. 넘기지 않으면 위 단정이
참이 된다.

`판단` 그 전제 위에서 순서가 나온다 — surface 1을 먼저 세우는 동안 feedback **의미론**을 미뤄도 surface 1의
품질이 볼모가 되지 않는다. 다만 **이벤트를 쌓는 것은 미루면 안 된다**(`D15`·§3-C8).

---

## 2. 서빙에서의 제외 — 기본값은 영구 제외다

### 2-1 코드

```go
// logics/recommend.go:59
userFeedback, _ := dataClient.GetUserFeedback(ctx, userId, new(time.Now()))
for _, feedback := range userFeedback {
    // :66  Negative feedback items should always be excluded (highest priority)
    if Match(config.DataSource.NegativeFeedbackTypes, feedback.FeedbackType, feedback.Value) {
        excludeSet.Add(feedback.ItemId)
    } else if !config.Replacement.EnableReplacement || !online {
        // :70  Other feedback items are excluded unless replacement is enabled
        excludeSet.Add(feedback.ItemId)
    }
}
```

### 2-2 걸리는 범위가 넓다 — 두 가지 이유로

**① 타입을 가리지 않는다.** `GetUserFeedback`은 가변인자로 타입을 받지만
(`storage/data/database.go:267`) 이 호출부는 넘기지 않는다. **버킷에 넣지 않은 타입도 포함해 전부**
순회한다.

**② 시간 하한이 없다.** `endTime`만 `now`이고 시작 시각이 없다. 학습 스캔에 걸리는
`positive_feedback_ttl`(§4)이 **여기에는 적용되지 않는다.** 즉 제외 집합은 사용자 생애 전체에 걸쳐
단조 증가한다.

`판단` 두 번째가 특히 크다. replacement를 끄고 운영하면 **활동적인 사용자일수록 추천 가능한
후보가 줄어드는 구조**이고, 우리처럼 후보가 사람인 서비스에서는 이것이 곧 "오래 쓴 사람에게
아무도 추천되지 않음"으로 나타난다.

### 2-3 `enable_replacement`의 정확한 동작

```toml
[recommend.replacement]
enable_replacement = true
positive_replacement_decay = 0.8   # positive 이력이 있는 후보
read_replacement_decay     = 0.6   # read 이력만 있는 후보
```

| 경로 | `online` | 제외되는 것 (replacement ON) |
|---|---|---|
| `/api/recommend/{user-id}` | `true` (`server/rest.go:890`) | **negative만** |
| 사전계산 파이프라인 | `false` (`worker/pipeline.go:154`) | 여전히 전부 |

offline이 뺀 것을 같은 파이프라인이 되돌려 넣는다:

```text
후보 생성 (과거 이력 제외 — 후보 예산을 과거 item이 먹지 않게)
   ↓
addReplacementCandidates   worker/pipeline.go:216   ← 랭킹 "전"에 후보로 재삽입
   ↓
ranker
   ↓
applyReplacementDecay      worker/pipeline.go:253   ← 랭킹 "후"에 Score *= decay
```

주석이 순서의 이유를 밝힌다 — 랭킹 전에 넣어야 LLM ranker까지 함께 정렬할 수 있고(`:213`),
감쇠는 랭킹 후에 적용해야 가중치가 ranker의 순서를 우회하지 못한다(`:251`).

★ **모양이 우리 요구와 맞는다: "다시 나오되, 처음보다는 뒤에."** 완전 배제도 무한 반복도 아니다.
`0.8`/`0.6`은 기본값일 뿐 우리가 정할 값이다.

> ⚠ **재삽입과 감쇠는 `ranker.type != "none"`일 때만 돈다**(`:215`, `:252`). ranker를 쓰지 않으면
> online에서 negative만 제외되고 과거 이력 후보가 **감쇠 없이 원점수 그대로** 돌아온다. 즉
> `enable_replacement`는 ranker와 한 쌍의 결정이다.

### 2-4 감쇠는 상수배이지 시간 함수가 아니다

`applyReplacementDecay`는 `Score *= decay`뿐이고 feedback의 `Timestamp`를 보지 않는다
(`worker/pipeline.go:588` 이하).

★ **"어제 대화한 상대"와 "석 달 전에 대화한 상대"를 Gorse는 구분하지 못한다.**

`판단` 재추천 간격(cooldown)과 시간 감쇠가 필요하면 **우리 rerank가 소유해야 한다.**
[`README.md` §9](README.md)의 "도구와 무관하게 우리가 계속 소유할 것" 표에 한 줄이 추가되는
항목이다. Gorse의 replacement는 "되돌아올 수 있게 만드는 스위치"까지고, "언제 얼마나"는 주지 않는다.

### 2-5 `negative`는 replacement로도 돌아오지 않는다

2-1의 첫 분기가 `EnableReplacement`와 무관하다. 주석 그대로 `highest priority`이고 **영구 제외**다.

★ **그러므로 우리 제품에서 `negative`의 의미는 "별로였다"가 아니라 "다시 보여주지 마라"다.**

`판단` [`inbound_event_contract.md` §3-4](../inbound_event_contract.md)의 퍼널에 있는
`requery.other_agent`(같은 질문을 다른 사람에게 다시 물어봄)를 negative로 프로젝션하면 그
`(requester, agent)` 조합이 영구히 죽는다. **직관적으로 가장 negative처럼 보이는 항목이 가장 넣으면
안 되는 항목**이라는 점에서 실제로 걸리기 쉬운 함정이다.

### 2-6 `write-back-type`은 모든 결과에 row를 쓴다

`server/rest.go:909` 이하 — 추천 응답을 만든 뒤 **반환한 모든 item에 대해** feedback을 적재한다.
`Timestamp: startTime.Add(writeBackDelay)`(`:919`)로 **미래 시각**을 넣고, 모든 스캔이
`WithEndTime(now)`이므로 그 시각이 지나기 전에는 보이지 않는다. 이것이 `write-back-delay`의 구현이다.

⚠ 이 기능을 켜면 **추천된 모든 item에 row가 생긴다.** replacement가 꺼져 있으면 2-1에 의해 한 번
추천된 것은 전부 영구 제외된다. `gorse.md` §6-1은 rev 1에서 이것을 "편의 기능"으로만 적었다 — rev 2에서 이 문서의 발견을
반영해 "반환한 모든 item에 row를 쓴다"로 고쳤다.

---

## 3. 적재 의미론 — `POST`와 `PUT`이 다른 것 네 개

```text
POST /api/feedback   →  insertFeedback(overwrite=false)   server/rest.go:336
PUT  /api/feedback   →  insertFeedback(overwrite=true)    server/rest.go:343
```

충돌 키는 **`(feedback_type, user_id, item_id)`**이고, `overwrite=false`의 upsert가 이렇다
(`storage/data/sql.go:1663` 이하, MySQL 기준):

| 열 | `POST` (누적) | `PUT` (덮어쓰기) |
|---|---|---|
| `value` | `value + VALUES(value)` | 덮어씀 |
| `time_stamp` | **`LEAST(time_stamp, VALUES(time_stamp))`** | 덮어씀 |
| `updated` | `GREATEST(updated, VALUES(updated))` | 덮어씀 |
| `comment` | 덮어씀 | 덮어씀 |

★ **`POST`로 반복 적재하면 `Timestamp`가 최초 발생 시각에 고정된다.** Gorse가 최근성에 쓰는 값은
`time_stamp`이므로(§4의 TTL 스캔, CTR 데이터셋의 `Timestamps`), 관계가 오래 지속될수록 그 row는
**계속 오래된 것으로 보인다.** `positive_feedback_ttl`을 켜면 마지막 상호작용이 아니라 **첫
상호작용 기준으로** 창 밖으로 나간다.

`판단` 그래서 [`gorse.md` §7-3](gorse.md)이 열어 둔 "POST냐 PUT이냐"는 단순한 집계 방식 선택이 아니다. **누적 카운트를
원하면 POST, 최근성을 원하면 PUT**이고, 둘 다 원하면 타입을 나누어야 한다.

두 가지 부수 사실:

- **Gorse는 이벤트 이력을 갖지 않는다.** PK가 위 3-튜플이므로 한 쌍당 한 행이고, 사건 순서를 Gorse
  에서 복원할 수 없다. [`inbound_event_contract.md` §3-4](../inbound_event_contract.md)의 "Gorse에
  보내는 것은 프로젝션이고 원본이 아니다"가 스키마 수준에서 강제된다.
- **ClickHouse backend만 다르다.** upsert 없이 `tx.Create(rows)`로 append한다(`sql.go:1628`, `:1644`).
  이 문서의 3장 전체가 ClickHouse에서는 성립하지 않는다 → §8 F8.

---

## 4. 시간과 관련된 설정들

| 설정 | 무엇을 자르나 | 주의 |
|---|---|---|
| `positive_feedback_ttl` (일) | 학습 스캔의 **시작 시각 필터** (`master/tasks.go:308`, `WithBeginTime`) | **삭제가 아니다.** 이름과 달리 negative·read 스캔에도 함께 걸린다. §2의 제외 집합에는 **적용되지 않는다** |
| `[recommend] cache_expire` (기본 `72h`) | 이웃·추천 캐시의 재계산 주기 | `실측` 신선도를 지배하는 값 — `gorse.md` §11-4 (M3) |
| `[server] cache_expire` (기본 `10s`) | 서버측 응답 캐시 | 위와 다른 값이다 |
| `[recommend] context_size` (기본 `100`) | online 추천이 참조하는 **최근 feedback 개수** | LLM ranker의 컨텍스트도 여기서 잘린다(`worker/pipeline.go:496` — positive만 채운다) |
| `active_user_ttl` | 비활성 사용자에 대한 추천 캐시 생성 중단 | `storage_sizing.md` §8의 `U_active`와 같은 축 |
| `write-back-delay` (쿼리 파라미터) | write-back row가 보이기 시작하는 시각 | 2-6 |

---

## 5. 변경을 흡수하는 방식 — 추가·제거·개명

### 5-1 타입 추가는 소급된다

1. 타입 자체는 자유 문자열이므로 스키마 변경이 없다. `auto_insert_user`/`auto_insert_item`이 기본
   `true`라 미등록 user/item도 함께 생성된다.
2. 버킷 배정은 config 편집이다. recommender가 자기 config로 `Hash()`를 만들어 digest를 캐시에
   기록하고, `needUpdateItemToItem`(`master/tasks.go:824`)이 digest 불일치를 보면
   **`cache_expire`를 기다리지 않고 재계산**한다(`:844`). user-to-user는
   `needUpdateUserToUser`(`:931`)가 같은 일을 한다(`:941` 읽기 · `:948` 비교).

   ⚠ **`Hash()`에 feedback 식이 들어가는 것은 조건부다.** `ItemToItemConfig.Hash`는
   `if config.Type == "users"`일 때만, `UserToUserConfig.Hash`는 `if config.Type == "items"`일 때만
   positive·negative 식을 섞는다(`config/config.go:293`·`:319`). 무조건인 것은
   `CollaborativeConfig.Hash`(`:343`)뿐이다. 즉 **feedback을 읽는 변종의 digest만 버킷 변경에
   반응한다** — 1-3 표와 정합적이고(읽지 않는 변종은 재계산할 이유가 없다), surface 1이 쓰는
   item-to-item `type="tags"`는 애초에 이 축과 무관하다.
3. `실측` **증분 갱신이 없다**(`gorse.md` §11-4). 여기서는 이것이 장점이 된다 — 다음 전면 재계산이
   그 타입의 **과거 row 전부**를 읽는다.

★ **규율: 버킷을 정하지 못한 타입이라도 원본 스트림에는 지금부터 쌓는다.** row는 싸고, 해석은
나중에 공짜로 바뀐다. **단 Gorse에 보내는 것은 다른 문제다 — 6-1.**

### 5-2 "사라진다"의 네 가지 뜻

| 무엇 | 기전 | 되돌릴 수 있나 |
|---|---|---|
| 버킷에서 뺌 | config. row는 남고 해석만 사라짐 | **예** — digest 변경 → 재계산 |
| `positive_feedback_ttl` | 학습 스캔의 시작 시각 필터일 뿐 | **예** — 학습 창의 문제 |
| 타입 개명 | 옛 row는 옛 이름으로 남음. 두 이름을 버킷에 같이 두거나 projection worker 재실행 | 예 — store가 파생물이므로(`gorse.md` §8-1) |
| `user.deleted` 전파 | 실제 row 삭제 (`inbound_event_contract.md` §3-3의 네 전파처 중 하나) | **아니오** |

---

## 6. 우리에게 남는 규율

### 6-1 애매한 이벤트는 Gorse에 보내지 않는다

"의미를 모르겠으니 일단 보내고 어느 버킷에도 안 넣는다"가 가장 자연스러운 선택인데, **틀린다.**

| | 버킷 미지정 타입의 실제 효과 |
|---|---|
| 학습 | 중립 맞음 (1-2) |
| **서빙** | **중립 아님** — 2-1의 else-if가 버킷과 무관하게 제외시킨다 |

replacement를 켜도 구제되지 않는다. offline 후보 생성에서 빠지는데,
`addReplacementCandidates`는 **positive 또는 read인 것만** 되돌리기 때문이다
(`worker/pipeline.go:555`–`:559`). 결과적으로 사전계산 목록에서 조용히 사라지고 돌아오지 않는다.

★ **규율: Gorse에는 "지금 의미를 아는 것"만 프로젝션한다.** 우회가 아니라
[`inbound_event_contract.md` §3-4](../inbound_event_contract.md)가 이미 정한 구조 그대로다 —
원본은 우리 스트림에 있고 Gorse에 가는 것은 프로젝션이다. 5-1 덕분에 **늦게 프로젝션하는 데 드는 비용이
없다.**

### 6-2 이진 판단은 `Value`와 식으로 미룬다

`conversation.depth_reached`처럼 "몇부터가 positive인가"가 안 정해진 것은, 깊이를 `Value`에 싣고
`positive_feedback_types = ["depth_reached>=N"]`로 둔다. **`N`은 나중에 바꿔도 재계산으로
소급된다**(1-1, 5-1).

단 **적재 시점은 버킷에 넣기로 정한 뒤**여야 한다. 미지정 상태로 먼저 보내면 6-1이 걸린다.
높은 임계값(`>=999`)으로 무력화하는 우회도 소용없다 — 제외는 `Match`와 무관하게 걸린다.

### 6-3 `negative`의 정의를 좁게 유지한다

2-5에 따라 명시적 거부에만 쓴다. `not_interested`, 차단 같은 것. 퍼널의 나머지는 positive 아니면
read 아니면 **보내지 않음**이다.

> ⚠ **이것은 이 문서의 권고이고 결정이 아니다.** 무엇을 `negative`에 넣을지는 열려 있다
> (`decisions.md` `C10` · 아래 `FBK-F2`). 정할 때까지 `negative_feedback_types = []`이며,
> 그 상태에서도 §6-1의 규율은 그대로 유효하다 — **보내지 않는 것이 기본값**이다.

### 6-4 우리 config가 갖게 될 모양 (초안, 결정값 아님)

```toml
[recommend.replacement]
enable_replacement = true            # 제품 요구가 강제한다 (§2)
positive_replacement_decay = 0.8     # 튜닝 대상 — 시간 축은 없다 (2-4)
read_replacement_decay     = 0.6

[recommend.data_source]
positive_feedback_types = ["conversation_started", "depth_reached>=N"]
read_feedback_types     = ["exposed"]
negative_feedback_types = []         # 명시적 거부에만. 영구 제외 (2-5)

[recommend.ranker]
type = "fm"                          # replacement가 이것을 요구한다 (2-3)
```

---

## 7. 자격 없는 agent·user에 대한 feedback

> 이 절의 **Item = surface 2의 agent**(`ItemId = personal_agent_id`, `D03`)다. surface 1 전용 인스턴스(`D22`)는 user·feedback을
> 받지 않고 item도 `agent_id#top_topic_id`(`D24`)라 이 절의 feedback 논의가 닿지 않는다.

### 7-1 `auto_insert`는 양날이고, 기본값이 켜져 있다

```toml
[server]
auto_insert_user = true    # 기본값
auto_insert_item = true    # 기본값
```

feedback을 POST하면 모르는 user/item을 **자동으로 만든다.** 만들어지는 Item은
`Labels: "null"`, `Categories: "null"`이고 `IsHidden`은 Go zero value라 **`false` — 즉시 추천
가능한 상태**다 (`storage/data/sql.go:1600`). ClickHouse 백엔드만 같은 자리에서 `"[]"`를 쓴다
(`:1586`) — 값이 다를 뿐 "즉시 추천 가능"은 같다.

끄면 반대쪽 실패가 있다. 모르는 item의 feedback은 **조용히 버려지고**(`sql.go:1614`), 응답은
쓴 개수가 아니라 **보낸 개수**를 돌려준다:

```go
Ok(response, Success{RowAffected: len(feedback)})   // server/rest.go:1615
```

⚠ **200 OK에 `RowAffected: 1`인데 한 줄도 안 쓰인 경우를 호출자가 구분할 수 없다.**

### 7-2 한 스위치로 뭉뚱그려지는 네 경우

| # | 상황 | feedback은 유효한가 | Gorse Item |
|---|---|---|---|
| (a) | catalogue 이벤트가 아직 도착하지 않음 (순서 경합) | **유효** | 곧 생길 예정 |
| (b) | 공개 topic 없음 | 유효 — 사건은 실제로 일어났다 | **의도적으로 없음** |
| (c) | suspended | 유효 — 정지 전에 일어난 일 | 있음, 추천에서만 제외 |
| (d) | deleted | 역사적 사실이나 보존하면 안 됨 | 제거 대상 |

`auto_insert`를 켜면 넷 다 유령 Item을 만들고, 끄면 넷 다 조용히 버린다. **(a)는 유실이고
(b)는 [`README.md` §5](README.md)가 닫아 둔 구멍이 다시 열리는 것**이므로 둘 다 틀렸다.

### 7-3 권고

**① `auto_insert_item = false`, `auto_insert_user = false`로 고정한다.**

Gorse가 우리 카탈로그 경계를 넘어 실체를 만들지 못하게 한다. `README.md` §5의 "가장 강한 보호는 받지 않는
것"이 이 설정 한 줄에 걸려 있다. `auto_insert_user`도 함께 꺼야 한다 — [`gorse.md`
§8-3](gorse.md)이 "unknown requester를 가짜 평균 user로 기록하지 않음"으로 정해 둔 것을 기본값이
정확히 위반한다.

**② Gorse에 "있느냐"고 묻지 않는다.**

물어도 답을 주지 않고(7-1), 읽기로 검증하면 왕복이 배가 된다.

★ **프로젝션 워커는 자기가 무엇을 프로젝션했는지 이미 안다.** Gorse는 이 질문의 진실 출처가 아니다.

**③ 프로젝션을 forward-write가 아니라 우리 store에 대한 재실행 가능한 pass로 만든다.**

```text
행동 이벤트 → 우리 store에 append (조건 없이)
                    ↓
            프로젝션 pass (재실행 가능)
                    ↓
     Item이 있는 것만 Gorse Feedback으로
```

(a)에서 프로젝션이 스킵되어도 **유실이 아니다** — row는 우리 store에 있고, catalogue 이벤트가 도착한
뒤 pass를 다시 돌리면 잡힌다. **deferq에 재시도가 없다는 제약이 여기서 무해해지고, 재시도 큐를
따로 만들 필요가 없다.**

[`gorse.md` §8-1](gorse.md)의 "projection worker를 다시 실행해 재구축할 수 있어야 한다"와 같은
요구다. 다만 그 요구가 **우리 이벤트 store에 "시간 범위 replay"를 강제한다**는 것은 아직 어디에도
적혀 있지 않다 → §8 F9.

**④ 케이스별 처리**

| 상황 | 우리 store | Gorse 프로젝션 |
|---|---|---|
| (a) 경합 | append | **스킵.** 다음 pass가 잡는다 |
| (b) 공개 topic 없음 | append | **스킵.** 나중에 공개되면 그때 소급 프로젝션된다(§5-1) |
| (c) suspended | append | **프로젝션한다.** Item을 `IsHidden=true`로 두면 추천에서만 빠지고 이력은 살아 있어, 복귀가 콜드 스타트로 돌아가지 않는다 |
| (d) deleted | append — 사건은 사실이다 | **프로젝션하지 않고 기존 row도 정리**([`inbound_event_contract.md` §3-3](../inbound_event_contract.md)) |

(b)가 가장 미묘하고, 스킵이 맞다. 공개 topic이 없는 사람을 Gorse에 넣는 것의 문제는 그 사람이
추천 가능해지는 것이 아니라 **그 사람에 대한 사실이 우리 인덱스에 존재하게 되는 것**이다. `README.md` §5의
논지가 정확히 그것이다.

**⑤ 삭제는 row 삭제로 끝나지 않는다.**

feedback row를 지워도 학습된 가중치는 다음 재학습까지 남는다.
`recsys_adoption_discussion.md` §7-1이 "주간 재학습이면 삭제 요청이 모델 안에서 일주일 산다"로
이미 지적한 축이다.

★ **삭제 SLA는 row 삭제 시각이 아니라 재학습 완료 시각으로 정의되어야 한다** → §8 F10.

### 7-4 감수하는 손실

(b)·(d)를 스킵하면 **requester 쪽 신호도 함께 잃는다.** "이 사람이 이런 상대와 대화했다"는
requester의 취향에 대한 정보인데, 상대가 인덱스에 없으면 CF에 기여하지 못한다.

우리 store에는 남으므로 나중에 다른 축(예: topic 단위 집계)으로 쓸 수 있고, 손실은 Gorse 프로젝션에
한정된다. `판단` **의도적으로 감수하는 것으로 적어 두면 되고, 사고로 잃는 것과는 다르다.**

---

## 8. `열린 항목`

**ID 접두사는 `FBK-`다**(`decisions.md` §5) — `F1`이 `facets_ownership_split_discussion.md`와 겹쳤다.

| # | 항목 | 성격 |
|---|---|---|
| **F1** | 재추천 정책의 소유자와 형태 — 감쇠 상수(Gorse)로 충분한가, cooldown·시간 감쇠(우리 rerank)가 필요한가 | 제품 결정. 2-4 |
| **F2** | `negative`에 무엇을 넣을 것인가. 현재 후보로는 **공집합**일 수 있다 | 제품 결정. 2-5 |
| **F3** | `depth_reached`의 `Value` 정의와 임계값 `N` | 상류와 함께. 6-2 |
| **F4** | `exposed`가 실제 렌더를 뜻하는가 — frontend 계약 | 미확정. 1-2·2-6 |
| **F5** | **config 핫리로드 여부 미확인.** 버킷 변경이 재시작을 요구하는가 | 컨테이너 확인 필요. `gorse.md` §11-1 M5가 인접 함정을 이미 기록 |
| **F6** | `POST`/`PUT` 선택 — `gorse.md` §7-3이 열어 둔 것을 event contract가 닫아야 한다 | §3이 근거를 추가함 |
| **F7** | 제외 집합이 시간 하한 없이 자라는 것(2-2)이 우리 규모에서 언제 문제가 되는가 | 측정. `storage_sizing.md` §8의 `U_active`와 같은 축 |
| **F8** | backend를 ClickHouse로 두는 선택지 — §3 전체가 달라진다 | `storage_sizing.md` §5의 후보에 없던 축 |
| **F9** | 우리 이벤트 store가 **시간 범위 replay**를 지원해야 한다 — §7-3 ③의 전제이자 `gorse.md` §8-1의 재구축 요구가 함의하는 것. `docs/recsys-intent.md`가 고른 DynamoDB의 키 설계가 여기 걸린다 | 설계. 미기재 |
| **F10** | 삭제 SLA를 **재학습 완료 시각**으로 정의 — row 삭제만으로는 모델 안에 남는다 | 제품·운영 결정. §7-3 ⑤ |

---

## 9. 재현

v0.5.11 태그의 소스를 직접 읽었다.

> ⚠ **줄번호는 `v0.5.11` 기준이다.** 사내 클론(`recsys/gorse`)은 `master`를 가리키고 있고
> v0.5.11은 그 조상이 아니다 — 인용된 9개 파일 중 8개가 그 사이에 바뀌었다(`server/rest.go`는
> 1834→2163줄). 워킹트리 파일을 그냥 열면 줄번호가 어긋나므로 `git show v0.5.11:<file>`로 읽는다.

확인 명령:

```bash
V=v0.5.11
B=https://raw.githubusercontent.com/gorse-io/gorse/$V
for f in config/config.go config/config.toml common/expression/expression.go \
         master/tasks.go worker/pipeline.go logics/recommend.go \
         server/rest.go storage/data/database.go storage/data/sql.go; do
  curl -sSO --output-dir . "$B/$f"
done
```

인용한 자리:

| 주장 | 위치 |
|---|---|
| 세 버킷 필드 · negative가 템플릿에 없음 | `config/config.go:248-251` · `config/config.toml:162-169` |
| 버킷은 식이다 | `common/expression/expression.go:55`, `:156` |
| 라벨 −1 / +1 / −1과 우선순위 | `master/tasks.go:701`, `:711`, `:720`, `:535`, `:636` |
| 어떤 타입이든 제외 · 시간 하한 없음 | `logics/recommend.go:59`, `:66`, `:70` · `storage/data/database.go:267` |
| online/offline 구분 | `server/rest.go:890` · `worker/pipeline.go:154` |
| 재삽입 전 · 감쇠 후, ranker 게이트 | `worker/pipeline.go:213`, `:215`, `:216`, `:251`, `:253`, `:555` |
| POST 누적과 `LEAST(time_stamp)` | `server/rest.go:336`, `:343` · `storage/data/sql.go:1663-1672` |
| write-back이 모든 결과에 row를 씀 | `server/rest.go:909-919` |
| digest 불일치 시 즉시 재계산 (조건부 Hash) | `master/tasks.go:824`, `:844`, `:931`, `:948` · `config/config.go:293`, `:319`, `:343` |
| TTL이 스캔 필터임 | `master/tasks.go:308` |
| `auto_insert`가 만드는 Item의 모양 | `storage/data/sql.go:1600-1610` |
| 모르는 item의 feedback이 조용히 버려짐 | `storage/data/sql.go:1614-1624` |
| `RowAffected`가 쓴 개수가 아니라 보낸 개수 | `server/rest.go:1615` |
