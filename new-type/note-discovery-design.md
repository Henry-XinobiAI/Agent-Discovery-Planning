# note 기반 agent discovery 설계안 (v1: 주제 추천, 답할 사람 찾기)

> 상태: **설계안 초안, 결정 아님.** 오너가 2026-11-06에 정한 범위와 선택(아래 "출발점")을 바탕으로 쓴다.
> 근거:
> - `new-type/ami-note-direction-notes.md`(이하 메모)
> - `new-type/ami-note-retrieval-experiment.md`(이하 실험 문서)
> - 실험 코드(로컬 브랜치 `exp/ami-note-retrieval`의 `experiments/ami-note-retrieval/`)
> - note-api의 현재 상태는 [`references/bourbon-note-api.md`](../references/bourbon-note-api.md)(이하 reference). note-api `feat/note-audience-policy` `d84ef04` 기준이다.
>
> 이 문서가 메모와 다르면 이 문서가 우선한다. 메모는 논의 기록으로 남긴다. `new-type/knowledge-agent-recommendation.md`와 `new-type/shout-to-people.md`는 topic과 lived-knowledge 전제라서 따르지 않는다. 가져다 쓴 것은 본문에 글로 적는다.
> 검토 과정에서 바뀐 것은 맨 아래 "검토 기록"에 있다.

## 출발점 (2026-11-06 오너)

- **bourbon-topic-api는 서비스에서 없어진다.** topic, topic 점수·성숙도, topic 공개 범위, topic 카탈로그가 모두 사라진다.
- **lived-knowledge도 없어진다.** 모든 재료는 note다.
- **응답의 재료는 public note뿐이다.** note의 공개 범위는 public ↔ private로 바뀔 수 있다. discovery가 응답을 만들 때는 public인 것만 쓴다.
- discovery는 note-api의 note 이벤트(`note_created`, `note_updated`, `note_visibility_changed`, `note_deleted`)를 받아 인덱스를 맞춘다. tag와 embedding을 만들고, note에 연결된 entity를 정리해 저장한다.
- **원본(본문, 제목)은 갖지 않는다.** discovery는 embedding, tag, card 연결 같은 파생 데이터만 갖는다. 응답에 실을 note 내용은 요청할 때 note-api에서 **여러 개를 한 번에 읽는다.** 요청당 note-api 호출은 1번(드물게 2번)이다. 나중에 사본을 갖게 될 수 있게 열어 둔다(§2-0, §12-1).
- **먼저 서비스할 것은 둘이다.**
  1. **주제 추천:** 어떤 주제로 이야기할 agent를 찾을 때 가장 맞는 agent를 추천한다.
  2. **답할 사람 찾기:** 어떤 질문에 답할 수 있는 다른 agent를 찾는다. 메모의 추천 흐름에서 shout를 뺀 부분이다.
- **shout는 이번 범위가 아니다.** 다만 나중에 같은 인덱스를 쓸 수 있게 둔다(§12).
- **note-api가 이미 주는 것은 다시 만들지 않는다.** 꼭 필요한데 없는 것은 note-api에 요청해 추가한다(§11).
- 오너 선택
  - topic 카탈로그는 **완전히 뺀다.** system tag는 discovery의 등록된 tag 하나로 간다.
  - 지금의 topic 기반 기능은 **모두 지우고 새 route로 바꾼다.** `/recommend`, `/recommend/explicit`, `/discover/by-topic`, `/discover/for-you`가 대상이다. for-you를 잇는 기능은 나중에 따로 설계한다.
  - **entity를 v1에 넣는다.** 다만 entity는 discovery가 새로 뽑지 않고 note-api의 공유 card를 쓴다(§2-5). 메모 §12-3, §12-5는 note-api의 card를 고려하지 않고 쓴 것이다.
- 오너 결정(2026-11-06, 설계안 #162 뒤)
  - **topic-api는 지금부터 없다고 보고 작업한다.** 옛 route와의 공존이나 되돌리기는 고려하지 않는다(§10-2).
  - **private이 된 note의 파생 데이터는 지우지 않고 공개 범위로 거른다.** 다시 public이 될 때 다시 만드는 비용을 쓰지 않기 위해서다(§2-2).
  - **note-api 공유 card의 이름 사본을 discovery에 둔다**(§2-5).
  - **"public note만"은 내용과 사람에는 즉시, 순위에는 이벤트 처리 시간 안(보통 몇 초, 최악 15분)에 지킨다**(§7-3).
  - **짧은 주제 문장 질문 세트를 새로 만들어 판정한다**(§6-4).
  - **pgvector는 dev에서 켤 수 있다.** prod는 인프라 세팅이 아직이고 나중에 한다(§3-1).

---

## 0. 한눈에

```text
[note-api] --note_created / note_updated / note_visibility_changed / note_deleted-->
   [listener]     mark_pending (공개 범위 변경·삭제면 그 자리에서 검색에서 뺀다)
   [sync loop]    가져가기(lease) → trusted 여러 개 조회(100개씩)로 상태와 본문을 읽는다(본문은 저장하지 않는다)
                     public  → embedding·분석을 만들어 파생 데이터만 저장
                     private → 검색에서 뺀다(파생 데이터는 남긴다)
                     없음    → row를 지운다
   [resync loop]  가진 key를 주기적으로 trusted 조회해 놓친 변경을 잡는다 (mark_pending)

[bourbon-agent] --주제 / 질문--> [API] 쿼리 분석(tag + 고유명사 → card) + 쿼리 embedding
                                  ├ 주제 추천: 검색 가능한 note가 있는 모든 owner의 사람 점수 → 상위 사람
                                  └ 답할 사람 찾기: tag가 맞는 note 먼저, 그다음 나머지 후보 → 상위 note
                                  → note-api 여러 개 public 조회 1번으로 내용 읽기
                                     (private·삭제·탈퇴는 여기서 빠지고, 빠진 사람과 note는 응답에 없다)
                                  → 응답
```

- **discovery에는 파생 데이터만 있다.** embedding, 등록된 tag, card 연결과 역할, 본문 hash, `version`, 공개 범위다. 본문과 제목은 저장하지 않는다(메모 §13-4의 2).
- **적재는 서비스용 trusted 조회로, 응답은 agent용 public 읽기로 한다.** note-api가 정한 쓰임 그대로다. trusted 조회의 내용은 파생 데이터를 만드는 데만 쓰고, 응답에는 요청할 때 public 읽기로 확인한 것만 싣는다.
- **응답에 실리는 note 내용과 사람은 그 요청에서 public으로 확인된 note에서만 나온다.** note-api가 읽는 순간 public이 아닌 것과 탈퇴 유저의 것을 거른다(§7-3).
- **검색과 사람 점수는 discovery의 파생 데이터로 한다.** 여기에 쓰이는 note는 `searchable` flag가 참인 것뿐이다. 공개 범위 변경·삭제 신호가 오면 그 자리에서 내리고, public을 확인한 처리만 올린다(§2-2).
- **entity는 note-api의 공유 card다.** discovery는 card의 종류와 note에서의 역할만 더한다(§2-5).
- **두 기능은 같은 인덱스와 같은 쿼리 분석을 쓴다.** 주제 추천은 사람을 줄 세우고(실험처럼 모든 owner를 본다), 답할 사람 찾기는 note를 줄 세운다(메모 §9-1).
- **답은 bourbon-agent가 쓴다.** discovery는 근거 note와 그 owner를 넘긴다(메모 §9-2, §10-1).
- **요청 경로의 외부 호출:** 쿼리 분석의 LLM 한 번, embedding 한 번, note-api 여러 개 public 조회 한 번(드물게 두 번).
- **순위는 실험에서 잰 방식을 그대로 쓴다.** 실험에 없던 가산과 경로는 뒤에 붙이거나 0에서 시작하고, 잰 뒤에 켠다(§5, §6-2).
- **저장소는 PostgreSQL 하나다.** DynamoDB는 이번에 뺀다(§3-4).

---

## 1. 용어

| 용어 | 뜻 |
|---|---|
| note | bourbon-note-api가 갖는 ami의 note. discovery는 `(owner_user_id, note_id)`로 가리킨다 |
| owner | note를 쓴 유저. 추천되는 사람이다 |
| 파생 데이터 | discovery가 note 본문에서 만들어 저장하는 것. embedding, 등록된 tag, card 연결과 역할, 본문 hash다. 본문 자체는 아니다 |
| 검색 가능(`searchable`) | 그 note의 파생 데이터를 검색과 사람 점수에 써도 되는지. trusted 조회로 public을 확인했고, 그 뒤에 공개 범위 변경·삭제 신호가 오지 않았을 때만 참이다 |
| trusted 조회 | note-api의 서비스용 읽기(`trusted/`). private note도 `visibility`와 함께 돌려준다. discovery는 적재, 주기적 다시 맞추기, backfill에 쓴다. 그 내용은 파생 데이터를 만드는 데만 쓰고 저장하지도 응답에 쓰지도 않는다 |
| public 읽기 | note-api의 agent용 읽기를 `visibility=public`으로 부르는 것. public note의 공유 필드만 오고, private·삭제·탈퇴 유저의 note는 빠지거나 404다(reference §3-1). 요청 경로와 `needs_public_check` 확인에 쓴다. 단건 route는 지금 있고, 여러 개 route(`POST /notes/lookup`)는 note-api가 1차로 받아들였다(§11의 R2) |
| 등록된 tag | discovery가 note에 붙이는 system tag. 영어 키, 고정된 한국어 표시 이름, 넓이(specific/mid/broad), 한 줄 정의를 가진다. 목록에서 먼저 고르고, 없을 때만 새로 만든다(메모 §4-2, §12-5) |
| card | note-api card ledger의 항목. note-api는 element라고도 부른다. 공유 card(`scope: public`)는 유저를 넘어 하나로 합쳐진 대상이고, 이름 여러 개(입력된 표기 + 영어 이름)와 웹 출처의 사실을 갖는다(§2-5) |
| entity | discovery에서 card 중 고유명사인 것. 장소, 상품, 가게·회사·브랜드·팀, 작품, 인물, 행사다. 일반 종류나 활동을 가리키는 card는 entity로 쓰지 않는다 |
| card 역할 | note 안에서 card의 역할. `subject`는 그 대상이 note의 주제이고, `mention`은 지나가듯 나온 것이다(메모 §12-3) |
| 분석 | note 하나에 등록된 tag를 붙이고 card 역할을 정하는 LLM 단계 |
| 쿼리 | 두 route에 들어오는 주제 문장이나 질문. DB 조회는 "DB 쿼리"라고 따로 부른다 |
| 쿼리 분석 | 쿼리에 등록된 tag를 고르고, 고유명사를 card에 맞추고, embedding을 만드는 단계. 두 기능이 같이 쓴다 |
| 다시 맞추기 | note 하나를 note-api에서 다시 읽어 discovery의 파생 데이터를 그 상태에 맞추는 처리. 이벤트 종류와 상관없이 하나다(메모 §13-2) |

---

## 2. 적재: note를 인덱스로

### 2-0. 원본을 discovery에 둘 것인가

**판단(2026-11-06 오너): 원본은 두지 않는다.** discovery는 파생 데이터만 갖고, 응답에 실을 note 내용은 요청할 때 note-api에서 여러 개를 한 번에 읽는다. 메모 §13-4의 2와 같은 방향이다. 다만 나중에 사본을 갖게 될 수 있게 열어 둔다(§12-1).

**본문이 필요한 곳 (실험에서 본 것)**

| 어디서 | 얼마나 | 사본 없이 |
|---|---|---|
| 답할 사람 찾기의 답 재료 | 요청마다 note 최대 8개의 본문. 한 문단 note 전체로 답이 충분했고, 요약만 있을 때는 재지 않았다(실험 문서 §4, §5) | 여러 개 public 조회 1번 |
| 주제 추천의 "왜 이 사람인지" | 요청마다 사람 3~5명 × note 제목 1~3개(메모 §11-3) | 여러 개 public 조회 1번 |
| 나중의 shout 재순위 | 후보 20명 × 본문 3개와 제목 전부(유저당 10개면 약 200개). 제목만 읽힌 재순위는 0과 구분되지 않았고, 본문을 읽힌 재순위는 주 지표를 올렸다(실험 문서 §6, §7, §17) | 여러 개 public 조회 2번. shout는 비동기다 |
| 분석·embedding을 다시 만들 때 | public note 전체. tag 체계와 프롬프트는 실험 동안 여러 번 바뀌었다(메모 §12-4) | trusted 여러 개 조회로 100개씩 다시 읽는다. 드문 배치다 |

후보 찾기에는 본문이 필요 없다. 키워드 검색(BM25)은 늘 섞으면 오히려 나빴고, 고유명사는 card가 맡는다(실험 문서 §2).

**두 안의 비교**

| | A. 사본을 둔다 | B. 파생 데이터만 두고 요청할 때 읽는다 (이 안) |
|---|---|---|
| 요청당 note-api 호출 | 0번 | 1번(드물게 2번). 여러 개 public 조회(§11의 R2)가 있을 때다 |
| 지연 | 쿼리 분석뿐 | 호출 1번에 p50 약 20~40ms, p95 약 50~100ms가 더해진다(어림, 재지 않았다, §7-6). 쿼리 분석 LLM(초 단위)에 비하면 몇 %다 |
| 응답 내용의 공개 범위 | discovery의 flag와 다시 맞추기 주기가 지킨다. 신호가 새면 최대 그 주기만큼 private이 된 내용이 나갈 수 있다 | **note-api가 읽는 순간 지킨다.** private으로 바꾼 note의 내용은 바로 응답에서 빠진다 |
| discovery에 남는 평문 | public note의 본문 | 없다 |
| 지울 곳 | 사본도 지워야 한다 | 파생 데이터만 |
| 가용성 | note-api가 멈춰도 응답한다 | note-api가 멈추면 빈 결과로 응답한다(§7-6) |
| 다시 만들기(reindex) | 사본에서 만든다 | note-api를 다시 읽는다 |
| 설계의 크기 | 사본 쓰기와 삭제, 노출 시간 관리가 더해진다 | 작다 |

**B를 택하는 이유:** 여러 개 조회가 있으면 호출은 요청당 1번이고, 늘어나는 지연은 LLM에 비해 작다. 대신 응답 내용의 공개 범위를 note-api가 직접 지키고, discovery에 평문이 남지 않는다.

**B가 남기는 것:**
- 검색과 사람 점수는 discovery의 파생 데이터로 하므로, 그쪽의 공개 범위는 discovery가 지킨다(`searchable`, §2-2). 이 경로로 남을 수 있는 것은 note 내용이 아니라 순위 신호다. 응답에 싣는 사람, note, 이유는 그 요청에서 public으로 확인된 note에서만 나온다(§8의 불변식 2).
- note-api가 느리거나 멈추면 응답이 빈다.
- 실제 note는 여러 page다. 한 page는 한글 약 500자가 목표다(note-api writer의 기준이며 넘을 수도 있다). 실험은 한 문단 note였다. 그래서 응답에 싣는 note당 글자 수에 상한을 두고(§7-1), note 하나를 embedding 하나로 두는 것이 긴 note에서도 괜찮은지 dev에서 잰다(§9).

### 2-1. 받는 이벤트

| 이벤트 | 보내는 곳 | listener |
|---|---|---|
| `bourbon.note_created` `{user_id, note_id, version}` | note-api, 발행 중 | `mark_pending(hide=false)` |
| `bourbon.note_updated` `{user_id, note_id, version}` | note-api. **dev(`deploy/2611`, PR #33 초안)에서 이미 발행 중이다** | `mark_pending(hide=true)`. dev의 note-api는 내용 수정뿐 아니라 공개 범위 변경과 철회(withdrawn)도 이 이벤트로 낸다(README: "present means show it, absent means hide it"). 무엇이 바뀌었는지 payload로 알 수 없으므로, 다시 읽어 public이 확인될 때까지 숨긴다. 내용만 고친 note는 다시 맞추기가 끝나는 몇 초 동안 검색에서 빠진다 |
| `bourbon.note_visibility_changed` `{user_id, note_id, version}` | note-api, 합의만 됨 | `mark_pending(hide=true)`. 다시 읽어 public이 확인돼야 다시 올라간다 |
| `bourbon.note_deleted` `{user_id, note_id}` | note-api, 합의만 됨 | `mark_pending(hide=true)` |
| `bourbon.user_deactivated` | bourbon-api | 그 유저를 지우고 `departed_users`에 남긴다(§2-6) |
| `bourbon.message_created` | bourbon-api | `room_turns`만 센다. "이미 대화한 사람"에 쓴다(§6-3) |

- **네 note 이벤트는 같은 다시 맞추기로 처리한다.** 다른 것은 그 자리에서 검색에서 빼는지(`hide`)뿐이다. 어느 이벤트든 최신 상태를 다시 읽어 맞추므로, 중복되거나 순서가 바뀌어 와도 결과는 마지막 상태가 된다.
- note-api `main`(`3fee423`)은 `note_created`만 정의한다. dev에 떠 있는 `deploy/2611`(PR #33 초안)은 `note_updated`도 발행한다. `note_visibility_changed`, `note_deleted`는 README에만 있다. discovery는 README의 payload대로 mirror를 두고, 지금처럼 느슨하게 받는다.
- **철회(withdrawn):** PR #33에서는 note가 철회될 수 있고, 철회된 note는 trusted 조회를 포함한 모든 읽기에서 빠진다. 같은 id로 다시 돌아올 수도 있다. discovery에게는 "없음"과 같다(§2-2). 돌아오면 `note_updated`가 와서 처음 온 note처럼 다시 만든다.
- 이 세 이벤트는 note-api에 수정·공개 범위 변경·삭제 기능이 생길 때 함께 발행된다(reference §6). deferq queue는 discovery가 listener를 등록할 때 생기므로, **note-api가 발행을 시작하기 전에** discovery를 배포해야 이벤트를 잃지 않는다.
- listener는 지금 코드의 재시도 묶음(`worker/flows.retrying`)으로 감싼다. deferq는 listener가 실패한 이벤트를 버리므로, DB가 잠깐 흔들려도 숨기기가 빠지지 않게 한다.
- **네 note listener와 `message_created` listener(`count_turn_on_message_created`)의 함수 이름은 바꾸지 않는다.** deferq는 queue 이름을 listener 함수 이름으로 정한다. 이름을 바꾸면 옛 queue가 남아 이벤트를 조용히 모은다. 바꿔야 하면 옛 queue를 비우고 지운다.
- `bourbon.user_registered` listener와 `agents` 테이블은 지운다(§3-2).
- 지우는 listener: `bourbon.topics_updated`, `bourbon.topic_visibility_changed`, `bourbon.friendship_changed`. 지운 listener의 queue도 함께 지운다.

### 2-2. 다시 맞추기

deferq는 재전달과 DLQ가 없다. 그래서 실패할 수 있는 일보다 **먼저 `pending`을 쓴다.** 모든 쓰기는 아래 둘 중 하나를 거친다.

**`mark_pending(owner_user_id, note_id, hide, version)`: 표시만 하는 쓰기.** listener, 주기적 다시 맞추기, backfill, 요청 경로(§5-5)가 모두 이것만 부른다. 한 트랜잭션에서 한다.
- `refuse_departed`로 탈퇴 여부를 본다. 지금 코드의 advisory lock 방식 그대로라, 동시에 도는 탈퇴 처리와 순서가 맞춰진다.
- row가 없으면 만든다(`state = pending`, `searchable = false`).
- row가 있으면 `generation`을 1 올린다. `processing`이 아니면 `state = pending`으로 돌린다. `processing`이면 state는 그대로 둔다. 처리 중인 쪽의 마지막 쓰기가 `generation`이 바뀐 것을 보고 다시 돈다.
- `version`이 있으면 `wanted_version = max(coalesce(wanted_version, 0), version)`으로 둔다.
- `hide`면 `searchable = false`로 둔다.
- 요청 경로에서 부를 때는(§5-5) `needs_public_check = true`도 둔다. 아래 4에서 쓴다.
- 이미 있는 row의 `owner_user_id`와 다르면 쓰지 않고 경고를 남긴다. note는 `(owner_user_id, note_id)`로 가리키지만 PK는 `note_id`다.

**sync loop: 실제 처리.**

1. **가져가기(claim):** 몇 초마다, 짧은 트랜잭션에서 `FOR UPDATE SKIP LOCKED`로 처리할 row를 최대 100개 고른다. 대상은 `pending`, 재시도 시각이 된 `failed`, lease가 끝난 `processing`이다. 고른 row를 `state = processing`, `claim_id = <가져갈 때마다 새로 만든 uuid>`, `lease_until = 지금 + sync.lease`로 바꾸고, 그때의 `generation`을 기억한다. 트랜잭션은 바로 닫는다.
   - `claim_id`는 프로세스 id가 아니라 가져갈 때마다 새로 만든다. 같은 프로세스가 lease가 끝난 자기 row를 다시 가져가도, 멈춰 있던 앞의 처리가 늦게 쓰지 못하게 하기 위해서다.
   - 읽기, embedding, LLM 호출은 트랜잭션도 lock도 없이 한다. DB 연결을 붙잡고 기다리지 않는다.
   - `sync.lease`는 한 묶음 처리의 최악 시간(읽기 + embedding + 분석의 마감 시간 합)보다 길게 둔다. 초안 5분이다.
   - deferq task를 따로 예약하지 않는다. 처리하는 곳이 둘이면 서로를 모르고, deferq 예약은 Redis에 있어서 failover 때 사라질 수 있다. 몇 초의 polling 지연은 note가 만들어지는 시간(writer의 분할 대기 최대 30분, Draft는 며칠)에 비해 보이지 않는다.
2. **trusted 여러 개 조회.** 가져간 row들을 `trusted/notes/lookup`(1~100개)으로 한 번에 읽는다. note-api 이벤트 계약(README)이 consumer에게 정해 준 읽기다. 결과는 note마다 셋 중 하나다.
   - **public:** 결과에 있고 `visibility = public`이다. 3으로 간다.
   - **private:** 결과에 있고 `visibility = private`이다.
   - **없음:** 200 응답에서 그 쌍이 빠졌다. 삭제됐거나 철회됐다. trusted 조회는 private을 빼지 않으므로 private이 여기에 섞이지는 않는다. client는 trusted 경로를 상수로 두고, 응답 모양(`StoredNote`, `visibility` 있음)을 계약 테스트로 확인한다. R2의 agent용 `POST /notes/lookup`은 private을 빼고 돌려주므로, 적재가 실수로 그 경로를 쓰면 private을 "없음"으로 읽게 된다(reference §2-2).
   - 5xx와 연결 실패는 묶음 전체를 `failed`로 두고 대기를 늘려 가며 재시도한다. 삭제의 근거가 아니다. 계속 500이면 묶음을 반으로 나눠 읽을 수 없는 note를 찾는다(reference §2-3).
   - **삭제 급증 차단:** note-api가 테이블을 비우거나 다른 환경을 가리킬 때 모든 note를 지우는 일을 막는다. 다만 한 유저가 note를 한꺼번에 지우거나 탈퇴하는 정상적인 경우에는 걸리지 않아야 하고, 걸려도 다른 note의 처리를 멈추면 안 된다.
     - **세는 단위:** 묶음 하나가 아니라 최근 `sync.mass_delete_window`(초안 1시간) 동안 "없음"으로 판정된 note 전체다. 그 수가 `max(20, 전체 row의 5%)`를 넘고, 그 note들의 owner가 `sync.mass_delete_min_owners`(초안 5)명 이상일 때만 걸린다. 한두 명의 유저에 몰린 삭제는 그 유저의 일괄 삭제나 탈퇴로 보고 그대로 지운다.
     - **걸리면:** 지우기만 보류한다. 그 note들은 이미 검색에서 빠진 상태(`searchable = false`)로 남고, 다른 note의 처리는 계속된다. 경고를 올린다.
     - **풀기:** 사람이 원인을 확인한 뒤 `cli sync release-deletes`로 보류된 지우기를 진행하거나, `cli sync discard-deletes`로 버리고 다시 맞추기를 건다.
     - note-api가 저장 형식을 바꾸며 옛 테이블을 비우는 배포(reference §9)에서는 이 차단이 걸리는 것이 정상이다. 확인하고 진행한 뒤 backfill을 돌린다(§2-3).
   - trusted 조회는 탈퇴 유저의 note도 돌려준다(reference §7). 그래서 탈퇴 이벤트를 놓쳤으면, note-api가 유저 데이터를 지우기 전까지 그 유저의 note가 public으로 읽혀 검색에 들어올 수 있다. 응답에는 나가지 않는다. 요청할 때 public 읽기가 탈퇴 유저를 거르기 때문이다. 4의 `needs_public_check`가 그 note가 검색을 오가는 것을 막는다.
3. **파생 데이터 만들기(public일 때만. `content_hash`는 public과 private 모두 이 방법으로 계산한다).** 읽은 본문은 이 처리 안에서만 쓰고 저장하지 않는다. 무엇을 다시 할지는 hash로 정한다.
   - 본문 hash(`content_hash`)는 `title`, 각 page의 `text`, `experienced`로 만든다.
   - `embedded_hash`가 `content_hash`와 다르거나 `embedding_spec`이 지금과 다르면 embedding을 만든다. e3llm `POST /v1/embeddings`, `gemini-embedding-001`, 768차원, `input_type=document`다(실험 문서 §2). 입력은 제목과 본문이다.
   - `analyzed_hash`가 `content_hash`와 다르거나, `public_element_ids`가 바뀌었거나, `analysis_spec`이 지금과 다르면 분석을 한다.
     - 분석 전에 note의 card 이름을 note-api에서 읽어 `cards`를 맞춘다. 이름은 쌓이므로 그 note가 가리키는 card는 매번 다시 읽는다. 이 읽기는 note-api가 1차로 받아들인 `POST /trusted/cards/lookup`(R1)으로 한다. 응답의 card `version`이 저장된 것과 같으면 이름을 다시 쓰지 않는다.
     - 분석은 LLM 한 번으로 등록된 tag와 card 역할을 함께 정한다(§2-4, §2-5). 처음 보는 card는 종류도 이때 정한다.
     - 새 tag 등록은 다음 쓰기 전에 따로 끝낸다(§2-4).
   - 모두 같으면 아무것도 만들지 않는다.
4. **쓰기:** note마다 조건부 UPDATE 한 번으로 한다.

   ```sql
   UPDATE notes SET ...
    WHERE note_id = :id AND state = 'processing'
      AND claim_id = :claim AND generation = :g
      AND coalesce(wanted_version, 0) <= :read_version   -- public, private일 때. 없음에는 이 조건이 없다
   ```

   - 같은 트랜잭션에서 먼저 탈퇴 여부를 본다(`refuse_departed`와 같은 lock). 탈퇴했으면 예외로 트랜잭션을 되돌리지 않고, 같은 트랜잭션에서 그 note row를 지우고 끝낸다.
   - **`needs_public_check`가 선 row**는 trusted 조회가 public이라고 해도 바로 `searchable`을 올리지 않는다. 요청 중 public 읽기에서 빠졌던 note라서다(§5-5). 그 note 하나를 public 읽기로 확인한다(R2가 생기면 `POST /notes/lookup`에 넣는다. 응답의 `not_found`는 없음·private·탈퇴 중을 가리지 않으므로, 여기서는 "public이 아니다"로만 읽는다). 있으면 표시를 지우고 올린다. 없으면 숨긴 채 `failed`로 두고 대기를 늘려 다시 확인한다. 탈퇴 이벤트를 놓친 유저의 note가 note-api의 삭제를 기다리는 동안 이 상태에 머문다.
   - 조건 확인과 쓰기가 한 문장이라, listener의 `mark_pending`이 사이에 끼면 PostgreSQL이 바뀐 row에 대해 조건을 다시 보고 쓰지 않는다. 그래서 처리 중에 온 숨기기를 옛 읽기가 덮지 못한다.
   - 한 row도 바뀌지 않으면 이유를 다시 읽어 갈린다.
     - row가 없으면(탈퇴 처리가 지웠다) 아무것도 하지 않는다.
   - "없음"으로 row를 지우는 DELETE도 같은 조건(`state = 'processing' AND claim_id = :claim AND generation = :g`)을 건다. 지우는 쪽과 표시하는 쪽이 같은 규칙을 따르게 하기 위해서다.
     - `generation`이 바뀌었으면 그 사이에 새 신호가 온 것이다. `pending`으로 돌린다(`claim_id`가 내 것일 때만).
     - `wanted_version`이 읽은 `version`보다 크면 note-api가 아직 그 변경을 보여 주지 않는 것이다. note-api 읽기는 강한 일관성이고 이벤트는 저장 뒤에 나가므로(reference §6) 드물다. `failed`로 두고 대기를 늘려 다시 읽는다.
     - `claim_id`가 내 것이 아니면 다른 처리가 맡았다. 아무것도 하지 않는다.

   | 읽은 결과 | 쓰는 것 | `searchable` | 끝난 상태 |
   |---|---|---|---|
   | public | `version`, `visibility`, `content_hash`, `public_element_ids`, 3에서 만든 embedding·tag·card 역할과 그 hash | 참. 단, embedding이 있어야 검색에 나온다(§5-1) | `ready`(3이 일부 실패했으면 `failed`와 대기) |
   | private | `version`, `visibility`, `content_hash`. **파생 데이터는 그대로 둔다**(embedding, tag, card 역할, 그 hash). 새로 만들지도 않는다 | 거짓 | `ready` |
   | 없음 | **row를 지운다** | — | — |

   - **private이 되어도 파생 데이터는 남기고 `searchable`로 거른다**(메모 §13-4의 3, 2026-11-06 오너 결정). 다시 public이 될 때 embedding과 분석을 다시 만드는 비용을 쓰지 않기 위해서다. 그 대신 메모 §13-4의 3이 붙인 조건을 지킨다.
     - **남에게 영향을 주는 계산은 모두 public note만 본다.** 후보, 사람 점수(tag 수, idf, z-score, 가까운 note), 이유(`matched_tags`), 쿼리 card 맞추기가 모두 그렇다. 이 조건은 §5-1 한 곳에 두고 모든 검색이 거친다.
     - **private note는 등록된 tag를 새로 만들지 않는다.** private인 동안은 분석하지 않는다(§2-4).
     - **private인 동안 내용이 바뀌어도 LLM은 쓰지 않는다.** 메모는 "private인 동안에도 수정 이벤트를 처리해 낡은 embedding이 남지 않게 한다"였다. 여기서는 수정 이벤트를 받아 `content_hash`만 새로 적는다(trusted 조회에서 바로 계산되고 LLM이 필요 없다). 다시 public이 되면 3의 hash 비교가 `embedded_hash`, `analyzed_hash`와 달라진 것을 보고 그때 다시 만든다. 다시 만드는 도중이거나 실패해도, hash가 맞지 않는 파생 데이터는 쓰이지 않는다(§5-1의 신선도 조건). 그래서 낡은 파생 데이터가 검색에 쓰이는 일도, private 내용을 분석하는 일도 없다. 내용과 spec이 그대로면 LLM 호출 없이 `searchable`만 올라간다.
     - 지워지거나 탈퇴하면 파생 데이터도 함께 지운다.
   - 없음은 row째 지운다. tombstone을 두지 않는다. 늦게 끝난 처리는 `claim_id`와 `generation`으로 막히고(쓸 row가 없다), 늦게 온 이벤트는 row를 다시 만들어도 다음 읽기에서 다시 지워진다.

**부분 실패:**

| 실패한 곳 | 처리 |
|---|---|
| embedding이나 분석 | 성공한 쪽은 쓰고 `state = failed`, `next_attempt_at`을 둔다. 다음 처리는 hash로 남은 쪽만 다시 한다(본문은 다시 읽는다). 그동안 hash가 `content_hash`와 맞지 않는 쪽은 쓰이지 않는다(§5-1). embedding이 옛것이면 그 note는 검색에 나오지 않고, 분석이 옛것이면 tag 없는 note(4층)로만 나오며 그 tag는 점수와 `matched_tags`에 쓰이지 않는다. 수정으로 지운 내용의 tag나 embedding이 남아 쓰이지 않게 하기 위해서다 |
| 분석 응답 일부가 잘못됨 | tag와 card 역할을 따로 검증한다. 역할이 잘못되면 그 note의 card를 모두 `mention`으로 두고 `analysis_partial = true`로 남긴다. §9에서 그 비율을 센다. tag가 잘못되면 분석 실패로 본다 |
| 재시도가 상한(`sync.max_attempts`)을 넘음 | 경고 지표를 올리고 대기를 길게 둔 채 계속 시도한다 |

**note-api는 지금 note를 바꾸지 않는다.** `version`은 늘 1이고 `visibility`는 늘 public이다(reference §5). 그래도 위의 처리는 지금 다 넣는다. 수정·공개 범위 변경·삭제가 생길 때 discovery를 다시 설계하지 않아도 되게 하기 위해서다.

### 2-3. 누락 메우기

| 무엇을 놓치나 | 메우는 방법 |
|---|---|
| 처리 중 실패 | sync loop가 `failed`를 지수 대기로 다시 가져간다 |
| 끝내 오지 않은 수정·공개 범위 변경·삭제 이벤트, 끝내 처리되지 못한 listener | **주기적 다시 맞추기(resync loop)**, 그리고 요청 경로의 감지(§5-5) |
| 한 번도 받지 못한 생성 | **backfill** |
| embedding·분석 방식 변경 | `cli reindex`가 `embedding_spec`이나 `analysis_spec`이 지금과 다른 **public** note를 `pending`으로 돌린다. sync loop가 trusted 여러 개 조회로 다시 읽어 만든다. private note는 다시 public이 될 때 spec을 비교해 맞춘다. "reindex가 끝났는지"도 public note만 센다 |

**주기적 다시 맞추기:**
- `state = ready`인 row의 key를 trusted 여러 개 조회로 100개씩 읽는다. `version`과 `visibility`만 보고 내용은 쓰지 않는다. 처리 중이거나 처리를 기다리는 row는 건너뛴다. 아직 저장된 값이 없어서 매번 다르다고 보고 다시 처리를 걸게 되기 때문이다(backfill 중에 특히 크다).
- 다르면 `mark_pending`을 부른다. private이거나 결과에서 빠졌으면 `hide=true`로 부른다. 그래서 검색에서 빼는 일은 다시 맞추기를 기다리지 않고 그 자리에서 된다.
- 결과에서 빠진 note는 `hide=true`로 표시만 한다. 지우는 것은 sync loop이고, 2의 삭제 급증 차단이 거기서 걸린다.
- 묶음이 500이면 반으로 나눠 문제 note를 찾는다(reference §2-3).
- 주기는 `sync.resync_interval`, 초안 15분이다. note 1만 개면 15분마다 여러 개 조회 100번이다. note-api는 이때마다 note를 복호화한다. 규모가 커지면 상태만 돌려주는 가벼운 조회를 요청한다(§12-2).
- 응답 내용의 공개 범위는 요청할 때 note-api가 지키므로, 이 주기는 note 내용이 아니라 순위 신호가 늦게 빠지는 시간이다(§7-3).

**backfill:**
- 유저 목록은 bourbon-api의 내부 user 목록(`GET /api/internal/users?after=&limit=`, 전체 유저 keyset 열거, 탈퇴 유저는 없음)으로 얻는다. note-api에는 유저 목록이 없다.
- 유저마다 `trusted/users/{id}/notes` 목록을 cursor로 끝까지 읽어, **discovery에 없는 note id에만** `mark_pending(hide=false)`를 부른다. 처리는 sync loop가 한다. 쓰는 길이 하나라야 lease와 조건부 UPDATE가 지켜진다.
- backfill은 언제든 다시 돌릴 수 있다. 처음 채울 때 말고도 `sync.backfill_interval`(초안 주 1회)로 돈다. 한 번도 받지 못한 생성과, 잘못 지워진 note(row가 없어 주기적 다시 맞추기가 보지 못한다)를 이것으로 되찾는다. 이미 있는 note는 건드리지 않으니 비용은 유저마다 목록 조회뿐이다.
- note-api가 마지막으로 저장 형식을 바꾼 배포 뒤에 돌린다. 그 전 note는 note-api가 지운다(reference §9).

### 2-4. 등록된 tag

메모 §12-1, §12-5와 실험 문서 §1을 따른다. 카탈로그 topic은 없다.

- **note당 3~6개를 붙인다.** 넓이를 섞어 붙인다(구체적 → 넓은). 넓이는 tag가 처음 등록될 때 정하고 고정한다.
- **목록에서 먼저 고르고, 정말 없을 때만 새로 제안한다.** 자유 생성은 tag 종류가 4.5배였고, 한 번만 쓰인 tag가 66%였다(실험 문서 §1).
- **키는 영어 소문자다.** 한국어 표시 이름은 처음 등록할 때 만들어 고정한다. 한국 고유 개념은 로마자 키(`jeonse`)를 쓴다.
- **고유명사는 tag로 붙이지 않는다.** 상품·브랜드·가게·장소 이름은 card가 맡는다. 메모 §12-5에서 열어 둔 tag와 entity의 경계를 이렇게 정하자는 안이다.
  - 이름 tag를 빼도 답하기는 그대로였다(실험 문서 §14).
  - 이름 tag가 채우던 shout "작게" 단계는 이번 범위가 아니다.
- **새 tag 등록:**
  1. 표기 정규화(대소문자, 공백, 하이픈, 악센트)로 같은 키를 찾는다.
  2. 없으면 이름 embedding으로 가까운 tag 몇 개를 뽑고, 같은 것인지 LLM이 정의를 보고 판정한다. 모르면 다르다고 본다.
  3. 다르면 등록한다. 등록은 짧은 트랜잭션에서 전역 advisory lock(트랜잭션 단위)을 잡고, 정규화된 키가 그 사이 생겼는지만 다시 본 뒤 `INSERT … ON CONFLICT`로 넣는다.
  - 1과 2(embedding과 LLM)는 lock 밖에서 한다. lock 안에서 LLM을 기다리면 backfill이 그 시간만큼 한 줄로 선다. 대가로, 동시에 처리된 두 note가 같은 개념을 서로 다른 키로 등록하는 일이 드물게 생긴다. 그런 tag는 나중에 `merged_into`로 합친다(열린 항목 3).
  - 등록 트랜잭션을 note 쓰기와 나누는 것은, 전역 lock과 탈퇴 처리의 유저 lock을 한 트랜잭션에서 함께 잡지 않기 위해서다.
- **private note는 분석하지 않는다(§2-2).** 그래서 private에서만 나온 말이 공유 tag 목록에 생기는 일은, 분석 도중 private이 된 드문 경우뿐이다. 그때는 조건부 쓰기가 실패해 그 note의 tag 연결은 저장되지 않고, 등록된 tag만 목록에 남는다.
- **프롬프트의 tag 목록 순서**는 사용 횟수로 정하지 않는다(키 순서). 사용 횟수로 정하게 되면 그 횟수는 검색 가능한 note만으로 센다(메모 §13-4의 3).
- **프롬프트에 보여줄 목록:** 목록 전체를 넣는다. note 분석과 쿼리 분석이 모두 그렇다.
  - 목록이 커질 때 쓸 방식(가까운 k개만, 넓은 tag를 함께)은 실험에서 통과한 것이 없다(실험 문서 §11, §16).
  - 실험에서는 note 1천 개에 tag 415개가 생겼다(다시 돌린 것은 444개). 목록이 `analysis.tag_prompt_max`(초안 1,500개)에 닿으면 경고를 올리되 목록 전체를 계속 넣는다. 비용과 쿼리 분석 지연이 늘 뿐 품질은 그대로라서 backfill을 막지 않는다. 그 전에 "k 키우기"를 재서 정한다. 열린 항목 2.

### 2-5. entity: note-api의 공유 card

**note-api가 이미 하는 것**(note-api 코드, `writer/judge`, `writer/kb`):
- writer의 judge 호출이 note가 될 대화에서 이름을 뽑는다. 대상은 물건, 장소, 작품, 캐릭터, 공인, 활동이다. 표기는 메시지에 쓰인 그대로다. 이름의 종류는 내보내지 않는다.
- 공유 card로 맞추는 순서는 이렇다.
  1. 표기 정규화(NFKC, 공백, casefold)로 정확히 같은 이름을 찾는다. 있으면 LLM 판정 없이 그 card로 간다.
  2. 없으면 웹 검색과 card 후보 몇 개(`WRITER_ELEMENT_CARD_CANDIDATES`)를 LLM이 보고 같은 대상인지 판정한다.
  3. 같으면 그 card에 이름을 더하고, 아니면 새 card를 만든다. 새 card의 이름은 입력된 표기와 웹에서 확인한 영어 이름이다.
- note에는 공유 card id가 찾은 순서대로 `public_element_ids`에 모두 실린다. 개인 card(`element_ids`에만 있다)는 쓰지 않는다.
- 공유 card는 지워지지 않고 합쳐지지도 않는다. card id는 한번 생기면 그대로다(note-api 1차 답변, 2026-11-06). 이름은 늘어나기만 하고, 사실(facts)은 다시 채워지며 바뀌고 그때 card의 `version`이 오른다. card가 바뀌었다는 이벤트는 없다. discovery는 note를 처리할 때 읽은 `version`으로 비교한다.
- 1의 규칙 때문에 `java`처럼 뜻이 여럿인 이름은 note-api에서 card 하나로 합쳐진다. discovery는 그대로 받는다. card 정밀도의 한계다.

메모 §12-3, §12-5가 discovery에서 하자고 한 일의 대부분이 여기 있다. 정규화, 같은 대상 판정, 다른 언어 표기의 별칭이다. 그래서 discovery는 entity를 새로 뽑지 않는다.

**discovery가 더하는 것:**

| 무엇 | 언제 | 어떻게 |
|---|---|---|
| card 종류 | card를 처음 볼 때 한 번 | 분석 호출에서 이름과 사실을 보고 `place`/`product`/`org`/`work`/`person`/`event`/`generic` 중 하나로 정한다. 캐릭터는 `work`, 팀은 `org`로 둔다. `generic`(일반 종류, 활동)은 entity로 쓰지 않는다. note-api의 공유 card에는 `whisky` 같은 종류도 섞여 있어서다 |
| card 역할 | note를 분석할 때 | 그 note의 card 이름 목록을 함께 주고 `subject`/`mention`을 정하게 한다 |

- **card 이름과 종류는 discovery가 사본으로 둔다(`cards`, 2026-11-06 오너 결정).** note 본문이 아니라 note-api의 공유 card 목록이다.
  - **종류는 원래 discovery의 것이다.** discovery가 정한 값이라 discovery에 있어야 한다. 사본이 되는 것은 이름뿐이다.
  - **품질:** 쿼리의 고유명사는 이름이 정확히 같은 card에만 맞춘다(§4). 사본이 없으면 요청마다 note-api의 card 검색(`trusted/cards/search`)을 불러야 한다. 이 검색은 이름과 사실을 함께 찾는 키워드 검색이라 엉뚱한 card가 첫 결과로 올 수 있다(검토에서 확인했다). 정확 일치를 하려면 결국 이름이 discovery에 있어야 한다.
  - **성능:** 사본이 있으면 DB 조회 한 번이다. 없으면 요청 경로에 고유명사마다 note-api 호출이 더해진다.
  - **없으면 추천을 못 하는가:** 아니다. 두 route는 card 없이 tag와 벡터로 동작한다. 다만 고유명사가 들어간 질문("성수동 ○○ 카페 가 본 사람")에서 가장 강한 신호를 잃는다(메모 §12-3).
  - 범위는 좁게 둔다. 이름만 두고 사실은 두지 않으며, discovery가 본 note가 가리키는 card만 둔다.
- **거주지 누출:** 글쓴이가 사는 곳은 프롬프트로 막지 못했다(메모 §12-3). 역할 프롬프트에서 "글쓴이의 거주지·생활권은 `mention`"으로 둔다.
- **식별 정보:** `place`, `org`, `person`의 이름은 discovery가 만드는 설명 필드에 싣지 않는다(§8).
- **card 이름 읽기가 필요하다.** 역할을 정하려면 card id가 아니라 이름이 필요하다. 쿼리의 고유명사를 card에 맞추는 데도 이름이 필요하다(§4). 지금 note-api에는 card를 id로 읽는 route가 없고 공유 card 검색(`POST /trusted/cards/search`)만 있다. 여러 개를 id로 읽는 route(`POST /trusted/cards/lookup`)를 요청했고 note-api가 1차로 받아들였다(§11의 R1). 개인 card id를 보내면 `missing`에 들어간다.
  - R1이 생기기 전에는 card 연결만 저장하고 종류와 역할은 비워 둔다. card 경로도 꺼 둔다(종류를 모르면 `generic`을 거를 수 없다).
  - 두 route는 card 없이도 tag와 벡터로 동작한다. 그래서 R1이 서비스 시작을 막지 않는다.
  - R1이 생기면 `analysis_spec`을 올리고 `cli reindex`로 분석을 다시 돈다.
- entity가 잘 맞는지, 거주지가 얼마나 새는지는 재지 않았다(실험 계획 E 미실행). v1을 dev에 올린 뒤 dev note로 잰다(§9). 그때까지 card는 후보를 뒤에 더하는 데만 쓰고 순위 가산은 0이다(§5-2, §5-3).

### 2-6. 탈퇴

- `bourbon.user_deactivated`를 받으면 한 트랜잭션에서 그 유저의 `notes`, `note_tags`, `note_cards`를 지우고 `departed_users`에 남긴다. 지금 `storage/erasure.py`의 lock과 순서를 그대로 쓴다.
- `room_turns`는 room 단위라 사람을 담지 않는다. 지금처럼 둔다.
- **note-api의 빈틈:** 탈퇴 직후 늦게 저장된 note에 `note_created`가 올 수 있고, trusted 조회는 탈퇴 유저의 note도 돌려준다(reference §7). 그래서 discovery는 모든 쓰기에서 탈퇴 여부를 본다.
- **탈퇴 이벤트를 놓친 경우:** deferq는 listener가 실패한 이벤트를 버린다. 그러면 `departed_users`가 비어 있다.
  - 응답에는 나가지 않는다. 요청할 때 public 읽기가 탈퇴 유저의 note를 거르고, 확인된 note가 없는 사람은 응답에 없다(§5-5).
  - 파생 데이터는 note-api가 유저 데이터를 지운 뒤 다음 주기적 다시 맞추기에서 지워진다. note-api의 수동 삭제(`DELETE /trusted/users/{id}`)도 이벤트를 내지 않으니 같은 길로 지워진다.
- 모든 검색 쿼리는 `departed_users`도 거른다(§5-1).
- **등록된 tag와 card는 지우지 않는다.** 공유 목록이라서다. note-api도 공유 card를 지우지 않는다.

### 2-7. 비용 (실험 기준)

| 작업 | 모델 | 대략 |
|---|---|---|
| note embedding | `gemini-embedding-001` | note당 수백 토큰 |
| note 분석(tag + card 역할·종류) | `gemini-3.5-flash` low | note당 입력 약 4~6천 토큰. tag 목록이 커지면 함께 커진다 |
| 새 tag 판정 | `gemini-3.5-flash-lite` low | 새로 등록할 때만 |
| 쿼리 분석 | `gemini-3.5-flash-lite` low | 요청당 입력 약 3~4천 토큰. tag 목록이 커지면 함께 커진다 |

- 지금 discovery 설정에는 LLM 모델이 하나(`google/gemini-3.1-flash-lite`)뿐이다. 용도별 모델 설정(`llm.note_analysis_model` 등)을 레지스터에 더한다.
- card 역할과 종류를 정하는 몫은 실험에 없던 것이다. 위 note 분석 값에 어림으로 더했다.
- **요청 비용:** 요청 수 × 쿼리 분석 한 번(입력 약 3~4천 토큰)이다. 달마다의 비용은 bourbon-agent가 두 route를 부르는 빈도에 달려 있어서, 전환(§10-2의 4) 전에 그 빈도를 받아 계산한다.
- **첫 backfill:** 비용은 note 수 × (note 분석 + embedding)이다. 시간은 note 수 ÷ 동시 처리 수(`sync.concurrency`, 초안 8) × note당 약 5~10초다.
  - 예: note 1만 개면 약 2~3.5시간, 입력 약 5천만 토큰이다.
  - note-api writer는 지금 dev에서만 켜져 있다. prod에는 아직 note가 없다(note-api `k8s/overlays`). dev note 수는 backfill 전에 센다.

---

## 3. 저장

### 3-1. 새 테이블 (PostgreSQL)

| 테이블 | 열 | 메모 |
|---|---|---|
| `notes` | 처리: `note_id` PK, `owner_user_id`, `state`(pending/processing/failed/ready), `generation`, `claim_id`, `lease_until`, `wanted_version`, `attempts`, `next_attempt_at`, `last_error` | 처리 큐와 인덱스를 한 row에 둔다. 본문과 제목은 없다. 지워진 note는 row가 없다 |
| | 상태: `version`, `visibility`, `searchable`, `needs_public_check` | `searchable`이 검색과 사람 점수에 쓸 수 있는지다. `needs_public_check`는 요청 중 public 읽기에서 빠졌던 note라 다시 올리기 전에 public 읽기로 확인해야 한다는 표시다 |
| | 파생: `public_element_ids`, `content_hash`, `embedding`, `embedded_hash`, `embedding_spec`, `analyzed_hash`, `analysis_spec`, `analysis_partial` | private이어도 남는다. `searchable`로 거른다. 무엇을 다시 할지는 hash와 spec으로 정한다 |
| `tags` | `tag_id` PK, `key` unique, `label_ko`, `definition`, `breadth`, `name_embedding`, `merged_into`, `created_at` | 등록된 tag 목록 |
| `note_tags` | `(note_id, tag_id)` | private이어도 남는다 |
| `cards` | `card_id` PK(note-api id), `names text[]`, `names_norm text[]`, `kind`, `card_version`, `fetched_at` | note-api 공유 card의 이름 사본과 discovery가 정한 종류. 사실은 저장하지 않는다 |
| `note_cards` | `(note_id, card_id)`, `role`(subject/mention, R1 전에는 비어 있다), `position` | private이어도 남는다 |

- `language`, `conversation_ended_at` 같은 note 메타데이터는 저장하지 않는다. v1 순위에 쓰지 않고, 응답에는 요청할 때 읽은 값을 싣는다. 최근성을 순위에 넣게 되면(§5-4) 그때 더한다.
- `names_norm`은 note-api와 같은 정규화(NFKC, 공백 묶기, casefold, `writer/kb/names.py`의 `normalize_name`)를 거친 이름이다. 쿼리의 고유명사와 정확히 맞출 때 쓴다(§4). note-api는 이 규칙을 계약으로 두기로 했다(1차 답변). 저장된 이름 검색 키가 이 규칙으로 만들어져 있어 바꾸려면 데이터 마이그레이션이 필요한, 바꾸기 어려운 규칙이다.

**벡터 저장과 검색:**
- 1안은 pgvector다. `vector(768)` 열을 쓰고, 처음에는 정확 검색으로 한다. 규모가 커지면 HNSW와 iterative scan으로 `searchable` 필터와 함께 쓴다.
- pgvector를 쓸 수 없으면 2안으로 간다. `real[]` 열에 저장하고, API 프로세스에서 cosine을 계산한다. 주제 추천은 요청마다 모든 note를 보므로(§6-2), 2안에서는 embedding을 프로세스 메모리에 올려 두고 바뀐 것만 다시 읽는다. note 1만 개 × 768차원이면 약 30MB라 v1 규모에서는 충분하다. 실험도 정확 검색이었다.
- **dev는 pgvector를 켤 수 있다(2026-11-06 오너).** 1안으로 간다. prod는 인프라 세팅이 아직이고 나중에 한다. prod에서도 켤 수 있는지는 그때 확인한다(열린 항목 1). 코드는 벡터 검색을 한 모듈 뒤에 두어, prod에서 안 되면 2안으로 바꿔 끼울 수 있게 한다.

### 3-2. 남기는 테이블

| 테이블 | 쓰는 곳 |
|---|---|
| `room_turns` | 이미 대화한 사람(§6-3). 지금 보존 sweep은 `interactions`가 없는 `room_turns`를 7일 뒤 지운다(`room_turns.orphan_ttl_days`, `storage/retention.py`). `interactions`를 지우면 모든 row가 그 대상이 되어 "이미 대화함"이 일주일 만에 잊힌다. 그래서 이 규칙을 지우고, `last_turn_at` 뒤 `room_turns.retention_days`(초안 365일)가 지나면 지운다. `interactions`를 지우는 §10-2의 1단계 PR에서 함께 바꾼다 |
| `departed_users` | 탈퇴 확인 |

`agents`는 지운다. agent id는 `identity.personal_agent_id(owner)`로 계산되고, 검색 조건에도 쓰이지 않는다. 함께 `bourbon.user_registered` listener도 지운다.

### 3-3. 지우는 테이블

- PostgreSQL: `visible_topic_rows`, `catalog_edges`, `catalog_snapshots`, `friends`, `popularity`, `attributions`, `interactions`, `population_stats`, `agents`
- DynamoDB 테이블 전체(§3-4)

지우는 순서는 §10에 있다.

### 3-4. DynamoDB를 빼고 결정 로그를 PostgreSQL로

- DynamoDB에는 이벤트 로그(`EVT#`), 결정 로그(`REC#`), CF 후보, 예측 방 인덱스, CF gate가 있다. §10-2의 1단계에서 모두 지운다.
- **이벤트 로그는 지운다.** 재생과 합성 모집단 보정에 쓰던 것이다. note 이벤트의 재생은 `notes.state`와 backfill이 맡는다.
- **결정 로그는 PostgreSQL `decisions` 테이블(jsonb)로 옮긴다.** 보존 sweep에 새 규칙을 더해 지운다(옛 결정 로그 기간 규칙은 `attributions`와 함께 없어진다). 보존 기간은 열린 항목 12다. 읽기에서 빠진 note의 id(그 순간 private이었을 수 있다)도 남으므로 짧게 둔다.
- 그러면 aioboto3, DynamoDB 테이블, 쓰고 나서 탈퇴를 확인하던 처리가 없어진다. IAM은 공유 role(`bourbon-app`)이라 role은 그대로 두고, discovery 테이블에 대한 권한만 뺀다. 메모 §9-3의 "저장소 하나"다.
- 옛 이벤트 로그와 결정 로그는 내보내지 않고 테이블째 지운다. 새 구조에서 쓸 곳이 없다. 내보내야 하면 1단계 전에 오너가 정한다(열린 항목 20).
- DynamoDB는 옛 route와 함께 §10-2의 1단계에서 지운다. `decisions` 테이블은 2단계의 새 테이블과 함께 만든다.

---

## 4. 쿼리 분석 (두 기능 공통)

입력은 주제 문장이나 질문 하나다. bourbon-agent가 "그거", "이번 신상" 같은 지칭을 구체적인 이름으로 채워 보낸다고 본다. 요청 경로에서 웹 검색은 하지 않는다.

- **embedding:** 주제나 질문 문장만 embedding한다. `context`는 넣지 않는다. 맥락이 길면 쿼리의 뜻이 흐려진다. `input_type=query`이고, note와 같은 spec이다.
- **LLM 한 번(`gemini-3.5-flash-lite` low).** 입력은 쿼리와 `context`다. 하는 일은 둘이다.
  - 등록된 tag를 **목록 안에서만** 고른다. 여러 개를 골라 OR로 쓴다. 새 tag는 만들지 않는다.
  - 쿼리에 나온 고유명사를 표기 그대로 뽑는다.
- **고유명사를 card에 맞추기.** discovery의 `cards` 사본만으로, LLM 없이 한다. R1 전에는 card 경로가 꺼져 있으니 하지 않는다(§2-5).
  - 표기를 정규화해 `cards.names_norm`에서 정확히 같은 이름을 찾는다.
  - 조사는 쿼리의 표기 쪽에서만 뗀다. 등록된 이름과 가장 길게 맞는 형태를 고른다(`제주에서` → `제주`). 저장된 이름에서는 떼지 않는다(`독도`).
  - card에는 원래 표기와 영어 이름이 함께 있어서 `Jeju`로 물어도 `제주` card가 맞는다.
  - 맞는 card가 검색 가능한 note에 연결돼 있지 않으면 쓰지 않는다.
  - 맞는 것이 없으면 card 없이 간다. 메모 §12-5는 여기에 후보 찾기와 LLM 판정을 두었다. 요청 경로의 호출을 늘리지 않으려고 정확 일치만 쓴다. card 이름은 note를 적재할 때마다 다시 읽어 쌓이므로(§2-2의 3), 사본이 오래돼서 놓치는 일은 적다. 놓치는 비율은 §9의 표기 변경 질문으로 잰다.
  - note-api는 이름을 "메시지에 쓰인 그대로" 저장해서, 조사가 붙은 이름이 있을 수 있다. 얼마나 되는지 §9에서 본다.
- embedding과 LLM은 동시에 부른다.
- **실패:**
  - LLM이 실패하면 embedding만으로 검색하고 `degraded`에 `query_analysis_unavailable`을 단다.
  - embedding이 실패하면 503이다. 순위의 중심이라 tag만으로는 품질이 크게 떨어진다(tag만 쓰면 hit@5 0.748, 실험 문서 §2).

---

## 5. 후보 고르기와 읽기 (두 기능 공통)

### 5-1. 검색 가능한 note

모든 검색용 DB 쿼리에 같은 조건을 건다(§8의 불변식 1).

- `searchable = true`
- `embedding`이 있고 지금 내용과 맞다(`embedded_hash = content_hash`). 모든 경로가 cosine으로 순서를 매기고 사람 점수도 cosine을 쓰기 때문이다. 막 들어왔거나 embedding이 옛것인 note는 다음 처리가 끝날 때까지 나오지 않는다.
- **tag와 card 역할은 지금 내용과 맞을 때만 쓴다(`analyzed_hash = content_hash`).** 맞지 않으면 그 note는 tag가 없는 note로 다룬다(§5-2의 4층). tag 층, card 층, 사람 점수의 tag 수와 idf, `matched_tags`, 쿼리 card 맞추기가 모두 이 조건을 따른다.
- owner가 `departed_users`에 없다.
- owner가 요청자도, `exclude_user_ids`(같은 방에 있는 사람 등)에 든 사람도 아니다. 내 ami가 답할 수 있는지는 bourbon-agent가 본다(메모 §10-1).
  - 답할 사람 찾기는 이 조건을 후보를 고를 때 건다. 실험도 질문한 사람의 note를 순위 전에 뺐다.
  - 주제 추천은 사람 점수(idf, z-score)를 검색 가능한 모든 owner로 계산한 뒤에 요청자와 `exclude_user_ids`를 뺀다. 실험이 그렇게 계산했고(§6-2), 요청마다 idf와 z-score가 흔들리지 않게 하기 위해서다.

이 조건은 한 곳(검색용 note 뷰나 쿼리 함수)에만 두고, 모든 경로가 그것을 거친다.

### 5-2. 답할 사람 찾기의 순서

주제 추천은 후보 note를 모으지 않고 모든 owner를 본다(§6-2). 아래는 답할 사람 찾기다. **실험의 순서(실험 코드 `retrieval.py`의 `filter_emb`)를 그대로 따르고, 실험에 없던 경로는 그 뒤에 붙인다.**

| 층 | 조건 | 층 안의 순서 |
|---|---|---|
| 1. tag | 쿼리 tag 중 하나라도 붙은 note | 쿼리 embedding과의 cosine |
| 2. 벡터 폴백 | 1층이 20개 미만일 때만. 1층에 없는 나머지 note | cosine |
| 3. card | 쿼리 card(종류가 `generic`이 아닌 것)가 연결됐는데 위에 없는 note | 역할(`subject` 먼저), 그다음 cosine |
| 4. 미분석 | 분석이 아직 없거나 지금 내용과 맞지 않아 tag를 쓸 수 없는 note | cosine |

- 1·2층이 실험에서 잰 방식이다. 결과는 embedding만 쓴 것과 hit@5가 거의 같았고(0.982 대 0.991) 후보는 1/10로 줄었다(실험 문서 §2). 1층이 20개 이상이면 tag가 없는 note는 나오지 않는다. 실험도 그랬다.
- 3·4층은 실험에 없던 것이라 위의 순서를 밀어내지 않게 뒤에 둔다. card가 맞는 note를 앞으로 올릴지는 dev에서 card의 기여를 잰 뒤 정한다(§5-3).
- 1층을 늘 벡터와 섞을지(폴백 조건 없이)는 dev 규모를 보고 정한다. 열린 항목 4.
- **키워드 검색(BM25)은 쓰지 않는다.**
  - 실험에서 BM25를 늘 섞으면 모호한 질문의 recall이 떨어졌다(0.81 → 0.64, 실험 문서 §2).
  - 고유명사는 card가 맡는다. 다른 언어로 쓰인 note는 embedding이 받는다(`gemini-embedding-001`은 다국어다).
  - note-api의 키워드 검색(`others_public`, ko/en/ja 번역 포함)도 부르지 않는다. 다른 언어 note를 놓치는 일이 dev에서 보이면 다시 본다.

### 5-3. 가산

```text
note_score = cosine(note, query)
           + w_card_subject · [쿼리 card가 subject로 연결됨]
           + w_card_mention · [쿼리 card가 mention으로만 연결됨]
           + w_tag · (겹친 쿼리 tag 수 / 쿼리 tag 수)
```

- **v1의 가중치는 모두 0이다.** 실험에서 잰 것은 위 1·2층의 cosine 순서다. 가산은 오프라인 CLI(tag)와 dev(card)에서 나빠지지 않는 것을 확인한 뒤 켠다. 가중치는 설정 레지스터에 둔다(`rank.note.*`).
- 점수 임계값은 두지 않는다. 순위로만 쓴다. 답할 수 있는지는 bourbon-agent가 판단한다.

### 5-4. 최근성

같은 사람의 옛 note와 새 note가 다를 수 있다(메모 §3-1). v1은 순위에 최근성을 넣지 않는다. 응답에 `conversation_ended_at`을 실어(요청할 때 읽은 값) bourbon-agent가 답을 쓸 때 최근 것을 앞세우게 한다. 근거 없는 감쇠 상수를 넣지 않기 위해서다.

### 5-5. 요청할 때 note-api에서 읽기

**순서**
- 후보 고르기와 점수 계산은 한 읽기 트랜잭션(같은 스냅샷)에서 하고, 결과 순위를 메모리에 둔다. note-api 읽기는 그 뒤에 트랜잭션 밖에서 한다.
- 응답에 필요한 수보다 넉넉히(각 route에 적은 수) **여러 개 public 조회 1번**으로 읽는다(§11의 R2, `POST /notes/lookup`). 응답은 `{notes: [{user_id, note}], not_found: [{user_id, note_id}]}`이고 요청 순서대로 온다. 결과에 있는 것만으로 응답을 채운다.
- `not_found`는 이유를 나누지 않는다. 없음, 철회, private, 탈퇴 중, 복호화 실패가 모두 여기에 든다(private이 있다는 사실을 드러내지 않으려는 note-api의 원칙). discovery는 모두 "지금 응답에 쓸 수 없다"로 다룬다. 복호화 실패는 note-api가 건너뛰고 로그만 남기므로 요청 전체가 실패하지 않는다.
- 결과로 모자라면 메모리의 순위에서 다음 것들을 골라 **1번만** 더 읽는다. 그래도 모자라면 있는 만큼 답한다.

**결과에 없는 note**
- 결과에 없다는 것은 private, 삭제, 탈퇴 중 하나다. 그 요청에서 버린다. 그 note만 확인된 사람은 응답에 없다.
- 응답을 보낸 뒤 그 note마다 `mark_pending(hide=true)`를 부른다. 이벤트가 새서 아직 검색에 남아 있던 note가 여기서 빠진다. 다시 맞추기가 public을 확인하면 다시 올라간다. 한 번 빠진 note는 다음 요청부터 후보에 없으니 같은 note로 쓰기가 몰리지 않는다.
- **비정상 판단:** 한 번의 읽기에서 `note_api.miss_alert_min`(초안 10)개 이상 빠지고 그 비율이 `note_api.miss_alert_ratio`(초안 50%)를 넘으면, note-api나 설정이 잘못됐을 가능성이 크다. 이때는 `mark_pending`을 부르지 않고 읽기 실패로 다룬다(§7-6). note-api가 빈 결과를 주는 동안 요청마다 인덱스를 비워 가는 일을 막기 위해서다.
  - 빠진 수가 그보다 적으면 비율과 상관없이 늘 검색에서 뺀다. 몇 사람이 note를 private으로 돌린 정상적인 경우에, 같은 note가 매 요청 위로 올라와 결과를 비우는 일을 막기 위해서다.
  - 이 판단이 짧은 시간에 여러 번 걸리면 경고를 올린다.

**결과에 있는 note**
- 읽은 `version`이 discovery의 `version`보다 크면, discovery가 아직 그 변경을 모른다(이벤트가 새거나 늦었다). 내용은 그대로 싣되 그 note의 tag는 `matched_tags`에 쓰지 않는다. 그리고 응답을 보낸 뒤 `mark_pending(hide=false, version=읽은 version)`을 부른다. 이벤트가 샌 수정도 여기서 잡힌다. discovery가 변경을 이미 알지만 파생 데이터가 아직 옛것인 경우는 §5-1의 hash 조건이 막는다.

**R2 전**
- 단건 public 읽기를 동시에 부른다. 동시 수는 `note_api.read_concurrency`(초안 8)로 묶는다.
- 주제 추천은 사람마다 가장 가까운 note 1개만 읽는다(§6-1). 단건 읽기 수를 사람 수로 줄이기 위해서다.

**마감 시간**
- note-api 읽기는 route 전체 마감 시간에서 남은 시간을 쓴다(§7-6). 따로 고정 마감을 두지 않는다. 쿼리 분석이 길어진 요청에서 둘을 더해 마감을 넘기지 않게 하기 위해서다.

---

## 6. 주제 추천

### 6-1. route

`POST /api/internal/svc/agent-discovery/recommend/subject`. 이름은 bourbon-agent와 정한다.

**요청:**

| 필드 | 뜻 |
|---|---|
| `user_id` | 요청자 |
| `subject` | 이야기하고 싶은 주제. 짧은 말이든 문장이든 된다 |
| `context` | 선택. 대화 맥락 요약. 쿼리 분석의 LLM에만 쓴다 |
| `exclude_user_ids` | 선택. 이미 같은 방에 있는 사람 등 |
| `max_results` | 1~20, 기본 3 |

**응답:**

```json
{
  "contract_version": "...",
  "recommendation_id": "...",
  "agents": [
    {
      "agent_id": "...",
      "owner_user_id": "...",
      "position": 1,
      "matched_tags": [{"key": "peaty whisky", "label": "피트 위스키"}],
      "notes": [{"note_id": "...", "title": "..."}],
      "already_talked": false
    }
  ],
  "empty": false,
  "empty_reason": null,
  "degraded": []
}
```

- 사람 점수(§6-2)로 상위 `max_results + rank.subject.read_buffer`(초안 +2)명을 고르고, 그 사람들의 쿼리와 가장 가까운 note 최대 3개씩을 여러 개 public 조회 1번으로 읽는다(최대 22명 × 3 = 66개, 한 번에 읽는 100개 안).
- **확인된 note가 하나도 없는 사람은 빼고**, 순위에서 다음 사람으로 채운다(§5-5).
- `notes`는 그 읽기에 있는 note의 id와 제목이다.
- `matched_tags`는 그 읽기에 있는 note에 붙은 tag 중 쿼리 tag와 겹치는 것이다(§5-5의 version 비교로 옛 tag는 뺀다). 순위는 파생 데이터로 정했지만, 응답에 드러나는 사람과 이유는 방금 public으로 확인된 note에서만 나온다. "왜 이 사람인지"는 이것과 `notes`의 제목으로 만든다(메모 §11-3). card 이름은 싣지 않는다(§8).
- agent 하나의 모양(`agent_id`, `owner_user_id`, `position`, `matched_tags`, `notes`)은 답할 사람 찾기의 `owners`와 같은 타입으로 둔다. bourbon-agent client는 타입 하나로 읽는다.

### 6-2. 사람 점수

**실험에서 잰 점수를 그대로 쓴다**(실험 문서 §6의 "tag + embedding 결합", 실험 코드 `ami_note/shout.py`의 `tag_score`, `emb_score`, `base_rankings`).

1. **tag 점수:** 쿼리 tag마다 `넓이 가중치 × idf(tag) × log(1 + 그 사람의 note 중 그 tag가 붙은 수)`를 더한다.
   - 넓이 가중치는 specific 3, mid 2, broad 1이다(실험 코드 `retrieval.py`의 `BREADTH_WEIGHT`).
   - `idf(tag) = log(전체 사람 수 / 그 tag를 쓴 사람 수) + 1`.
2. **가까운 note 유사도:** 그 사람의 **모든** 검색 가능한 note 중 쿼리와 가장 가까운 3개의 cosine 평균.
3. 두 값을 각각 z-score로 바꿔 더한다. 실험은 전체 유저 100명에 대해 z-score를 내고, 그 뒤에 질문한 사람을 뺐다. v1도 검색 가능한 note가 있는 모든 owner에 대해 내고, 그 뒤에 요청자와 `exclude_user_ids`를 뺀다(§5-1). z-score를 낼 사람이 3명보다 적으면 가까운 note 유사도 순서로 둔다.
   - **비용:** 요청마다 검색 가능한 모든 note와 cosine을 계산하는 전체 scan이다. owner별 상위 3개는 벡터 인덱스(HNSW)로 뽑을 수 없다. note 1만 개(768차원)면 수 ms~수십 ms라 v1 규모에서는 괜찮다. 규모가 커질 때 가장 먼저 깨지는 곳이다. 그때는 tag·벡터 경로로 후보 owner를 좁히고, 좁혔을 때의 차이를 잰다.
4. 이미 대화한 사람을 감점한다(§6-3).

- 계산의 모든 입력(사람 수, tag를 쓴 사람 수, note 수, 가까운 note)은 검색 가능한 note만으로 센다(§8).
- card 일치는 v1 사람 점수에 넣지 않는다. 실험에 없던 항이라 dev에서 잰 뒤 넣는다.
- **note가 적은 사람이 밀린다.** 이 점수로 note 1개인 직접 경험자는 상위 5명에 13%만 들었다(실험 문서 §12, 재순위 전부터). 실험 문서는 "선정 점수가 note 수를 타는 것으로 보인다"고 적었다. 완화책(note embedding 중심, 개수를 정규화한 top-k 등)은 아직 재지 않았다.
  - 실험 문서 §6에서 note embedding 중심(centroid)은 첫 판정(`gpt-5.5`) 라벨로 "관련 경험 + 관심" p@5가 결합과 같았고(0.84) 직접 경험자 hit@10이 가장 좋았다(0.65). 기준 라벨(Gemini)로는 다시 잰다.
  - **출시 전 확인:** 오프라인 CLI로 H-10과 H-mix 세트에서 완화책을 기준 라벨로 재고, 나빠지지 않는 것이 있으면 그것으로 바꾼다. 열린 항목 5.
- 한 사람이 여러 note로 잡혀도 사람은 하나다(메모 §3-1).

### 6-3. 이미 대화한 사람

- "대화해 보세요" 추천에서는 이미 대화한 사람을 **빼지 않고 내린다**(메모 §8-5).
- **판정:** 요청자가 그 사람의 agent와 대화한 방 id는 계산할 수 있다(`identity.agent_dm_room_id(요청자, personal_agent_id(owner))`). 그 방이 `room_turns`에 있으면 대화한 것이다.
  - `room_turns`는 `message_created`가 agent DM의 유저 메시지마다 센다. 추천한 방만이 아니다.
  - 후보 전체의 방 id를 계산해 DB 조회 한 번으로 본다.
- 대화했으면 `rank.subject.already_talked_penalty`를 뺀다. 감점 크기는 실험에 없으니 dev에서 정한다.
- 응답에 `already_talked`를 실어 화면이 "다시 이야기해 보기"처럼 보여줄 수 있게 한다.
- 지금 `interactions`는 discovery가 추천한 방만 기록한다(`worker/conversations.py`). 그래서 이 판정에는 쓰지 않고 지운다.

### 6-4. 빈 결과와 출시 기준

- 검색 가능한 후보가 없거나, 읽기에서 모두 빠졌으면 `agents: []`, `empty: true`, `empty_reason: "no_matching_notes"`다. 답할 사람 찾기도 같다.
- **출시 기준(초안):** 두 가지를 거친다.
  1. **같은 계산인지:** 실험의 tag와 embedding을 그대로 넣어 운영 코드의 사람 순위가 실험 코드와 같은지 본다. 결정적인 테스트다.
  2. **새 프롬프트가 나빠지지 않는지:** tag와 card 역할을 함께 정하는 운영 프롬프트로 합성 note를 다시 분석해, 실험의 사람 찾기 질문 95개를 기준 라벨(Gemini, 실험 문서 §17)로 잰다. "관련 경험 + 관심" p@5(주 지표)와 직접 경험자 hit@5(보호 지표)를 실험의 결합 점수와 질문 단위로 짝지은 bootstrap으로 비교한다(실험 문서 §7의 방식).
     - 허용선은 실험이 정한 −0.05를 기준 라벨의 크기에 맞춘다. 기준 라벨로는 p@5의 바탕이 약 0.40으로 첫 판정 라벨(약 0.84)의 절반이라, p@5 하한은 −0.025로 둔다. 직접 경험자 hit@5는 두 라벨이 잘 맞으므로 −0.05 그대로 둔다.
     - **이 허용선을 쓰기 전에 검정력을 확인한다.** 기준 라벨에서 짝지은 신뢰구간 폭은 ±0.03 정도라(실험 문서 §17의 TR−R이 [−0.057, +0.006]), 차이가 없는 변경도 −0.025를 못 넘을 수 있다. 실험에서 같은 방식으로 tag를 두 번 붙인 결과(R과 gfull2, 실험 문서 §11)를 이 기준에 넣어 통과하는지 먼저 본다. 통과하지 못하면 −0.05로 두고 그 이유를 적는다.
     - **라벨이 없는 쌍:** 새 프롬프트로 상위 5명이 바뀌면 판정된 적 없는 (질문, 사람) 쌍이 생긴다. 실험 문서 §17처럼 같은 판정 모델과 같은 방식으로 더 판정한 뒤에 센다. 판정 없이 음성으로 세지 않는다. 판정 비용은 그 쌍의 수만큼이다.
- **짧은 주제 문장으로 된 새 질문 세트를 만든다(2026-11-06 오너 승인).** 주제 추천은 짧은 주제가 주 입력인데 실험 질문은 문장이라서다. 실험의 사람 찾기 질문과 같은 방식(같은 합성 유저, 같은 판정 모델과 기준 라벨)으로 판정하고, 위 2의 기준에 함께 넣는다. 이 세트에는 실험의 비교 대상 값이 없으므로, 같은 세트에서 실험 코드의 결합 점수를 먼저 돌려 바탕으로 쓴다.
  - **만드는 방법(초안):** 실험의 합성 유저 100명의 관심 분야와 숨은 경험을 바탕으로 짧은 주제 50개를 만든다. tag에서 만들면 tag가 맞는 사람이 유리해지므로 tag는 쓰지 않는다.
  - **판정:** 실험 코드와 운영 코드 각각의 상위 10명을 모아(pool) 같은 판정 모델과 기준으로 판정한다. 직접 경험 라벨은 합성 유저의 숨은 경험에서 온다(실험 문서와 같다).
  - **기준:** 95개와 따로 잰다. 허용선은 이 세트의 바탕 값으로 다시 정하고, 위의 검정력 확인(R과 gfull2)도 이 세트에서 다시 한다.
  - 실험 코드와 합성 세트는 로컬 브랜치(`exp/ami-note-retrieval`)에만 있다. 구현하는 사람이 쓸 수 있게 옮길 곳을 정한다(열린 항목 23).

---

## 7. 답할 사람 찾기

### 7-1. route

`POST /api/internal/svc/agent-discovery/recommend/answerers`. 이름은 bourbon-agent와 정한다.

**요청:**

| 필드 | 뜻 |
|---|---|
| `user_id` | 요청자 |
| `question` | 질문. 지칭은 bourbon-agent가 채운다 |
| `context` | 선택 |
| `exclude_user_ids` | 선택 |
| `max_notes` | 1~12, 기본 8(실험 문서 §4의 상위 8개) |

**응답:**

```json
{
  "contract_version": "...",
  "recommendation_id": "...",
  "notes": [
    {
      "note_id": "...",
      "owner_user_id": "...",
      "agent_id": "...",
      "position": 1,
      "version": 3,
      "title": "...",
      "pages": ["..."],
      "truncated": false,
      "experienced": true,
      "language": "ko",
      "conversation_ended_at": "..."
    }
  ],
  "owners": [{"agent_id": "...", "owner_user_id": "...", "position": 1, "matched_tags": [], "notes": [{"note_id": "...", "title": "..."}]}],
  "empty": false,
  "empty_reason": null,
  "degraded": []
}
```

- `notes`는 답의 재료다. 내용은 그 요청에서 note-api public 읽기로 가져온 것이다. bourbon-agent의 모델이 이 note로 답을 쓰고 **실제로 인용한 note**를 고른다. 인용한 note의 owner가 함께 추천할 사람이다(메모 §9-2).
- note 하나의 `pages`는 합쳐서 `answer.note_max_chars`(초안 3,000자)까지만 싣는다. 넘으면 `truncated: true`다. 실험은 한 문단 note였고, 긴 note 8개를 그대로 넘긴 적은 없다.
- `owners`는 `notes`를 owner로 묶은 것이다. 답을 쓰지 못했을 때 "이 분들과 이야기해 보세요"에 쓴다(메모 §0의 2단계). 순서는 각자의 가장 높은 note 순서다. 모양은 주제 추천의 agent와 같다(`already_talked`만 없다). `matched_tags`는 그 요청에서 읽기에 있는 note의 것만 쓴다.
- `version`은 bourbon-agent가 나중에 그 note를 직접 다시 볼 때 같은 내용인지 확인하는 데 쓸 수 있다.

### 7-2. 순서

1. 쿼리 분석(§4), 순서 매기기(§5-2).
2. **한 사람의 note는 최대 `rank.answer.per_owner_max`(초안 3)개까지만 넣는다.** 한 사람이 근거를 다 차지하면 답이 한 사람의 경험에 갇힌다. 실험에는 없던 제한이다.
3. 위에서부터 `max_notes`의 2배(기본 16개, 최대 24개)를 여러 개 public 조회 1번으로 읽고(§5-5), 결과에 있는 것으로 `max_notes`개를 채운다.

**출시 기준:**
- 같은 계산인지: 실험의 tag와 embedding을 넣어 운영 코드의 1·2층 순서가 실험 코드(`filter_emb`)와 같은지 본다.
- 나빠지지 않는지: 실험의 답하기 질문 337개(답 있는 것)로 운영 프롬프트와 한 사람당 상한을 넣은 hit@5·recall@10을 잰다. 답하기의 정답은 note 단위라 프롬프트가 바뀌어도 새 판정이 필요 없다. 실험의 "tag 필터 → embedding + 폴백"(0.982, 0.866, 실험 문서 §2)과 짝지은 bootstrap 하한이 −0.02 이상(실험의 답하기 허용선)이면 dev에 낸다.

### 7-3. 공개 범위

| 무엇이 | 언제 빠지나 |
|---|---|
| **응답에 실리는 note 내용**(제목, 본문) | **private으로 바꾸는 즉시.** 요청할 때마다 note-api가 public인지 확인하고 돌려준다 |
| **응답에 실리는 사람**과 이유(`matched_tags`) | 즉시. 그 요청에서 확인된 note가 있는 사람만, 그 note의 tag로만 싣는다 |
| 순위에 끼치는 영향(그 note의 tag·embedding이 사람 점수와 후보에 들어가는 것) | 보통 몇 초(이벤트 → listener). 이벤트가 새거나 listener가 실패하면 다음 주기적 다시 맞추기(초안 15분)나, 그 note가 요청 중 읽기에서 빠질 때까지 |

- 마지막 줄은 내용이 아니라 순위다. 예를 들어 private으로 돌린 note 때문에 그 사람이 조금 더 위에 오를 수 있다. 다만 그 사람이 응답에 나오려면 다른 public note가 그 요청에서 확인돼야 하고, 드러나는 이유도 그 public note의 것뿐이다.
- 오너가 이 범위를 받아들였다(2026-11-06). "응답의 재료는 public note뿐"을 내용과 사람에는 즉시, 순위에는 위의 시간 안에 지킨다.
- bourbon-agent가 이미 받아 간 내용은 discovery가 거둘 수 없다. 그래서 받은 내용을 오래 두지 말라고 요구한다(§7-5).

### 7-4. 재순위는 v1에 없다

- 본문을 읽히는 재순위(B1·B3·B4)는 shout 대상 선정에서 잰 것이고, 어느 것을 쓸지는 아직 정하는 중이다(메모 §11-3, §12-6, 실험 문서 §17). 요청 한 번에 수 초~20초가 든다. 동기 요청인 두 기능에는 무겁다.
- 답할 사람 찾기에서는 bourbon-agent가 답을 써 보며 다시 고른다. 재순위의 몫을 이미 그쪽이 하는 셈이다.
- 주제 추천에 재순위를 넣을지는 v1을 dev에서 써 본 뒤 정한다. 열린 항목 8. 넣게 되면 본문은 여러 개 public 조회로 읽는다.

### 7-5. bourbon-agent에 전할 요구

- 답에 쓰지 않은 note의 owner를 "답에 쓰였다"고 소개하지 않는다.
- 근거 밖 일반론이 섞이지 않게 한다. 모호한 질문과 두 note를 합치는 질문에서 13~19%의 답에 일반론이 섞였다(실험 문서 §4). 문장마다 인용을 달거나, "다른 분들의 경험"과 "ami의 의견"을 나눠 보여준다(메모 §11-4).
- 받은 note 내용은 그 답을 쓰는 데만 쓰고 따로 저장하지 않는다. 대화 기록에 남는 답 문장은 예외다.
- 빈 결과(`empty: true`)와 `degraded`를 받으면 "지금은 찾지 못했다"고 말한다. 다시 부르지 않는다.
- 실제로 인용한 note id를 discovery에 돌려줄 길을 나중에 연다. 인용 횟수는 note 품질 신호가 된다(메모 §9-6). v1에는 없다. 열린 항목 9.

### 7-6. 지연과 degraded

- **목표(초안):** 두 route 모두 p95 2.5초. 쿼리 분석 LLM이 대부분이고, note-api 읽기 1번과 DB 조회가 더해진다.
- **note-api 읽기 1번의 어림:** public 읽기는 note-api 안에서 위치(pointer) 읽기, note 읽기, 탈퇴 확인을 차례로 하는 DynamoDB 강한 일관성 읽기 2~3번이다(`notes/shown.py`, `notes/originals.py`). 복호화는 프로세스 안의 HKDF·AES-GCM이라 작다. p50 20~40ms, p95 50~100ms로 어림한다. DynamoDB가 일부 key를 돌려주지 않으면 50~150ms 대기를 두고 다시 읽으므로 꼬리가 늘 수 있다. 주제 추천은 긴 note 66개를 받을 수 있어서 더 길 수 있다. dev에서 잰다(열린 항목 15).
- **마감 시간:** route 전체 마감 `recommend.deadline`(초안 3초)을 새로 둔다. 지금 설정의 `RECOMMEND_DEADLINE_SECONDS`(20초)는 옛 route의 것이다. 쿼리 분석이 마감 안에 끝나지 않으면 503이다.
- **note-api 읽기가 실패하거나, 마감을 넘거나, 비정상으로 판단되면(§5-5):** 확인된 note가 없으니 사람도 싣지 않는다. 두 route 모두 `empty: true`, `degraded`에 `note_read_unavailable`이다. 파생 데이터로만 고른 사람을 내보내면, 그 사이 private이 되거나 탈퇴한 사람이 섞일 수 있어서다.
- **`degraded`는 알림이다.** bourbon-agent는 받은 결과를 그대로 쓴다. 다시 부르지 않는다. v1의 값은 `query_analysis_unavailable`, `note_read_unavailable` 둘이다.
- 요청자별 호출 상한은 두지 않는다. 내부 route이고 부르는 쪽이 bourbon-agent 하나다.

---

## 8. 지키는 것 (불변식)

1. **검색과 사람 점수는 검색 가능한 note의, 지금 내용과 맞는 파생 데이터만 본다.**
   - 후보와 사람 점수의 모든 입력이 그렇다.
   - 모든 검색용 DB 쿼리가 §5-1의 한 곳을 거친다. 조건이 빠지면 실패하는 테스트를 둔다(메모 §13-4의 3).
2. **응답에 드러나는 것(note 내용, 사람, `matched_tags`)은 그 요청에서 note-api public 읽기로 확인된 note에서만 나온다.** 확인된 note가 없으면 응답이 빈다.
3. **discovery는 note 본문과 제목을 저장하지 않는다.** trusted 조회의 내용도 저장하지 않는다. private이 된 note의 파생 데이터는 남지만 검색, 점수, 응답 어디에도 쓰이지 않는다.
4. **`searchable`은 public을 확인한 처리만 올린다.** 올리는 쓰기는 `claim_id`, `generation`, `wanted_version`을 한 번에 확인하는 조건부 UPDATE다. 공개 범위 변경·삭제 신호, 주기적 다시 맞추기의 불일치, 요청 중 읽기에서 빠진 것은 받는 즉시 내린다.
5. **탈퇴한 유저의 데이터는 쓰지 않고 내보내지도 않는다.** 모든 쓰기가 `refuse_departed`를 거치고, 모든 검색 쿼리가 `departed_users`를 거른다.
6. **지운 note는 늦게 끝난 처리로 되살아나지 않는다.** 쓰기는 lease를 가진 처리만, 가져간 뒤 새 신호가 없을 때만 할 수 있다.
7. **private note는 분석하지 않는다.** 내용이 바뀌어도 hash만 적는다. 그래서 등록된 tag가 private note에서 새로 생기지 않는다(분석 도중 private이 된 경우는 예외, §2-4).
8. **`place`, `org`, `person` card의 이름은 discovery가 만드는 설명 필드(`matched_tags` 등)에 싣지 않는다.** note 본문이나 제목에 그 이름이 있는 것은 owner가 공개한 글이라 그대로 둔다.
9. **요청자 자신과 `exclude_user_ids`는 결과에 나오지 않는다.**

---

## 9. 평가와 확인

**오프라인:**
- 실험의 합성 세트(note 1,000개, 질문 400개 + 사람 찾기 95개, 정답 라벨)를 운영 코드 경로로 다시 돌리는 CLI를 둔다. 합성 세트는 로컬에만 있다. note 내용을 읽는 곳은 한 interface 뒤에 있으니(§12-1), 합성 note를 내주는 가짜 구현을 끼워 돌린다.
- 두 route의 출시 기준(§6-4, §7-2)을 잰다. 같은 계산인지 보는 결정적 테스트와, 새 프롬프트가 나빠지지 않는지 보는 bootstrap 비교다.
- 한 사람당 note 상한(§7-2)과 tag 가산(§5-3)이 답하기를 떨어뜨리지 않는지 본다.
- note가 적은 사람의 완화책(§6-2)을 잰다.
- 합성 note에는 card가 없고 미분석 note도 없다. 그래서 3·4층과 card는 dev에서 잰다.

**동작 확인(테스트):**
- 공개 범위 변경 신호가 처리 중인 다시 맞추기와 겹치면 `searchable`이 다시 올라가지 않는다(조건부 UPDATE가 0 row).
- 같은 프로세스가 lease가 끝난 자기 row를 다시 가져가도, 앞의 처리가 늦게 쓰지 못한다(`claim_id`).
- 삭제 확인 뒤에 늦게 끝난 처리가 row를 되살리지 않는다. 탈퇴 처리가 row를 지운 뒤의 쓰기는 아무것도 하지 않는다.
- private이 되면 파생 데이터는 남지만 어느 검색과 점수에도 나오지 않는다. 내용 그대로 다시 public이 되면 LLM 호출 없이 다시 검색된다. private인 동안 내용이 바뀌었으면 다시 public이 될 때 다시 만든다.
- 주기적 다시 맞추기가 private을 보면 바로 검색에서 뺀다.
- 여러 유저에 걸쳐 삭제가 급증하면 지우기가 보류되고(이미 숨겨진 채로) 다른 note의 처리는 계속된다. 한 유저에 몰린 삭제는 그대로 지워진다.
- 요청 중 읽기에서 빠졌던 note는 trusted 조회만으로 다시 올라가지 않는다(`needs_public_check`).
- 주기적 다시 맞추기는 처리 중인 row를 건드리지 않는다.
- 주제 추천의 사람 점수는 요청자와 `exclude_user_ids`를 빼기 전에 계산한다.
- 요청 중 public 읽기에서 빠진 note는 응답에 없고, 검색에서도 빠진다. 빠진 수와 비율이 모두 비정상이면 검색에서 빼지 않고 빈 결과로 응답한다. 몇 개만 빠지면 늘 뺀다.
- 확인된 note가 없는 사람은 응답에 없다. `matched_tags`는 읽기에 있는 note의 tag만으로 만들고, version이 앞선 note의 tag는 쓰지 않는다.
- note-api 읽기가 실패하면 빈 결과와 `note_read_unavailable`로 응답한다.
- backfill도 `wanted_version`보다 낮은 읽기로 `searchable`을 올리지 못한다.
- 모든 검색 쿼리가 §5-1을 거친다.

**dev:** backfill 뒤의 실제 note로 잰다.
- 유저당 public note 수, note 길이 분포, 쿼리당 후보 수, tag 층이 20개 미만인 비율
- 긴 note(여러 page)에서 note 하나를 embedding 하나로 두는 것과 page마다 두는 것의 차이
- 새 tag가 생기는 속도, 한 번만 쓰인 tag 비율, tag 목록 크기에 따른 쿼리 분석 지연
- card 종류 분포, `generic` 비율, 쿼리 고유명사가 card에 맞는 비율. 표기를 바꾼 질문(제주/Jeju, 스벅/스타벅스)과 언급만 있는 함정 질문을 dev note에서 만들어 잰다(실험 계획 E-1의 일부)
- 3·4층과 card 가산의 기여(§5-2, §5-3, §6-2)
- `place` card가 거주지로 새는 사례. 표본을 사람이 본다
- 요청 중 public 읽기에서 빠지는 비율, version이 앞선 note의 비율, 주기적 다시 맞추기가 찾아낸 불일치 수(0이 아니면 이벤트가 새고 있다는 뜻이다)
- note-api 읽기의 지연(p50, p95)과 응답 전체 지연, LLM 비용

**결정 로그:** 요청마다 `decisions`에 남긴다. 쿼리 tag·card, 층별 후보 수, 최종 순위와 점수 구성, 읽기에서 빠진 note다. note 내용은 남기지 않고 id와 `version`만 남긴다.

---

## 10. 지우는 것과 순서

### 10-1. 지우는 코드

| 무엇 | 위치 |
|---|---|
| topic-api client와 mock | `agent_discovery/providers/topic_api/`, `scripts/topic_api_mock.py`, `data/topic_api_mock/`, `TopicApiSettings` |
| 네 pipeline | `pipelines/topic_recommend.py`, `explicit_recommend.py`, `by_topic.py`, for-you |
| topic 전제 stage와 discovery 모듈 | `stages/`(expansion, grounding, retrieval, merge, ordering), `discovery/topic_index.py`, `content.py`, `popularity.py`, `cf.py`, `shuffle.py`, `cursor.py` |
| CF | `agent_discovery/cf/`, worker의 CF fit·sweep·gate loop, 인기도·모집단 통계 loop |
| 카탈로그 | `data/catalog_dist/`, `scripts/sync_catalog.py`, `load_catalog.py` |
| route | 내부 `/recommend`, `/recommend/explicit`, 공개 `/discover/*`, `/recommendations/opened`, `/recommendations/shown` |
| listener | `topics_updated`, `topic_visibility_changed`, `friendship_changed`, `user_registered`, 사용자 topic refresh task. `message_created`는 `room_turns`만 남기고 예측 방·attribution 부분을 지운다 |
| DynamoDB | `storage/` DynamoDB 모듈, 이벤트 로그, 예측 방 인덱스 |
| 합성 모집단 | `synthetic/`, `cli validate`, `cli seed`의 topic 부분. 10만 합성 모집단은 topic 공개 전제라 새 구조를 검증할 수 없다(메모 §9-7) |

남기는 것: LLM transport(`providers/llm/`), 설정 레지스터, 탈퇴 처리(`departed.py`, `erasure.py`), 보존 sweep(`room_turns` 규칙은 §3-2대로 바꾼다), `identity.py`.

### 10-2. 순서

topic-api는 지금부터 없다고 보고 작업한다(2026-11-06 오너). 그래서 옛 기능과 새 기능을 함께 두는 기간을 두지 않고, 지우기를 먼저 한다.

1. **지우기.** §10-1의 코드와 옛 route, listener를 지운다. 남기는 코드도 같은 PR에서 고친다. 지울 것에 기대고 있어서다.
   - `storage/erasure.py`: `visible_topic_rows`, `friends`, `attributions`, `interactions`, `agents`, 인기도 지우기를 뺀다. 탈퇴 기록(`departed_users`)만 남기고, note 쪽 지우기는 2단계에서 더한다.
   - `worker/deactivation.py`: DynamoDB의 CF 후보 지우기를 뺀다.
   - `worker/conversations.py`(`message_created`): `room_turns` 세기만 남기고 예측 방, `interactions`, attribution을 뺀다. listener 함수 이름은 그대로 둔다(§2-1).
   - `worker/journal.py`의 `record`(모든 listener가 DynamoDB 이벤트 로그에 쓴다)와 `worker/retry.py`의 DynamoDB 오류 분류를 뺀다.
   - 보존 sweep: `friends`, `attributions` 규칙을 빼고, `room_turns` 규칙을 §3-2대로 바꾼다.
   - 아무것도 import하지 않아 테스트로는 안 보이는 `scripts/`(`create_dynamodb_table.py`, `disposable.py`, `fetch_dev_snapshot.py`, `load_dev.py`, `seed_local*.py`, `try_recommend.py`, 카탈로그 스크립트)와 `cli/publish.py`, `cli/recommend.py`도 지우거나 고친다.
   - **migration과 배포 순서:** 옛 테이블을 지우는 migration(0012)은 **새 worker가 뜬 뒤에** 돌린다. 옛 worker가 아직 이벤트를 받는 중에 테이블이 없어지면, 탈퇴 처리 트랜잭션이 통째로 되돌아가 탈퇴 기록까지 잃는다(deferq는 다시 보내지 않는다). 그래서 "코드 배포 → 확인 → migration"으로 한다.
   - **deferq queue 정리:** 지운 listener의 queue를 지운다. `topics_updated`, `topic_visibility_changed`, `friendship_changed`, `user_registered`의 queue와, `worker/user_topics.py`에 적혀 있는 예전 이름의 queue, 사용자 topic refresh task의 queue와 Redis 예약이다. bourbon-api는 `friendship_changed`, `user_registered`를 계속 발행하므로, queue를 지우지 않으면 끝없이 쌓인다. 배포 직후 broker에서 지운다.
   - **bourbon-agent:** 지금 bourbon-agent는 `/recommend/explicit`를 부른다(bourbon-agent `api_internal_client/agent_discovery.py`). 이 route도 topic-api의 검색(grounding)을 거치므로 topic-api가 없으면 503이다. 지운 뒤에는 404가 된다. bourbon-agent의 tool은 200이 아니면 "지금은 추천을 쓸 수 없다"로 끝낸다. 4단계까지 이 상태가 이어진다. dev에서 topic-api가 실제로 꺼져 있는지와, 그동안 bourbon-agent가 tool을 끌지는 오너가 정한다(열린 항목 21).
   - 공개 `/discover/*`와 `/recommendations/opened|shown`은 클라이언트가 부르는지 먼저 확인한다(열린 항목 11). bourbon-agent와 bourbon-api에는 부르는 곳이 없다.
   - DynamoDB는 이때 함께 지운다(§3-4). 결정 로그는 2단계부터 PostgreSQL `decisions`에 쓴다. 1단계와 2단계 사이에는 route가 없어서 결정 로그가 필요 없다.
2. **적재.**
   - note-api client(trusted 조회, card), 새 테이블(migration 0013, `decisions` 포함), 네 note 이벤트 listener, sync loop, resync loop, backfill·reindex CLI를 만든다. route는 아직 없다.
   - **pgvector:** extension은 superuser 권한이 필요해서 migration이 아니라 인프라가 dev DB에 만든다. migration은 extension이 있는지 확인하고 없으면 멈춘다. prod에서 못 켜게 되면 `real[]`로 바꾸는 migration을 따로 둔다(§3-1의 2안). 2안은 스키마가 달라서 interface 뒤의 구현만 바꾸는 것으로 끝나지 않는다.
   - dev의 note-api는 이미 `note_updated`를 발행한다. listener가 뜨기 전의 이벤트는 사라지지만 backfill과 주기적 다시 맞추기가 메운다.
   - dev에 올려 인덱스가 차는 것을 본다. note-api가 수정·공개 범위 변경·삭제 이벤트를 발행하기 전에 listener가 떠 있어야 한다(§2-1).
   - 적재는 note-api의 지금 route만으로 된다. R2를 기다리지 않는다.
3. **쿼리 분석과 답할 사람 찾기 route.** 오프라인 평가 CLI도 이때 만든다. 여러 개 조회(R2)가 늦으면 단건 읽기로 시작한다(§5-5). 이어서 **주제 추천 route**를 만든다. 둘 다 출시 기준(§6-4, §7-2)을 거친다.
4. **bourbon-agent 전환.** 새 두 route로 옮긴다. 트리거 시점과 방식은 bourbon-agent의 일이다. 전환 전에 bourbon-agent가 두 route를 부르는 빈도를 받아 요청 비용을 계산한다(§2-7).

- **문제가 보이면** 옛 route로 되돌아갈 곳은 없다. 새 route의 설정(층, 가산, 감점)으로 고친다.
- **note-api 의존:** note-api의 `trusted/` 경로 이동과 agent용 route는 `main`에 들어갔다(2026-11-06, `3fee423`. 코드는 reference가 읽은 `d84ef04`와 같다). discovery는 이 경로를 쓴다.
  - **같은 경로가 뜻만 바뀌었다.** 옛 `main`의 `/api/internal/svc/note/users/{u}/notes/{n}`은 서비스용(private 포함)이었고, 지금은 agent용(private은 404)이다(reference §0의 1). discovery client는 지금 경로만 쓰고, 실제 note 하나로 두 경로를 확인하는 계약 테스트를 둔다.
  - note-api의 prod 배포는 OpenSearch 컬렉션 URL이 정해져야 한다(note-api `k8s/overlays/prod`). discovery의 prod 적재도 그 뒤다.

---

## 11. note-api에 요청할 것

| # | 무엇 | 왜 | 언제 | 없으면 |
|---|---|---|---|---|
| R1 | **공유 card를 id로 여러 개 읽는 route.** **1차 답변(2026-11-06): 받아들임.** `POST /trusted/cards/lookup {card_ids}`(1~100개), 응답 `{cards: [{id, names, facts, version}], missing: [ids]}`. 이름 정규화(NFKC → 공백 묶기 → casefold)는 계약으로 둔다. card id는 합쳐지거나 사라지지 않는다. card 변경 이벤트는 없고 `version`으로 비교한다. 개인 card는 주지 않는다(`missing`) | card 이름이 있어야 note 안의 역할과 card 종류를 정할 수 있다. 쿼리의 고유명사를 card에 맞추는 데도 필요하다(§2-5, §4) | card 경로를 켜기 전. 서비스 시작은 막지 않는다 | card 연결만 저장하고 card 경로는 꺼 둔다(§2-5) |
| R2 | **agent용 public 읽기의 여러 개 조회.** **1차 답변(2026-11-06): 받아들임.** `POST /notes/lookup {notes: [{user_id, note_id}]}`, agent용 쪽에 두고 늘 public만 준다. 응답 `{notes: [{user_id, note: SharedNote}], not_found: [{user_id, note_id}]}`, 요청 순서, 중복은 한 번. `not_found`는 이유를 나누지 않는다(없음·private·탈퇴 중·복호화 실패). 복호화 실패는 건너뛰고 로그만 남긴다. 탈퇴 확인은 note 읽기와 동시에 한다. 제목만 주는 선택은 보류(응답 크기가 문제가 될 때 다시). route docstring에 discovery도 부른다고 적는다 | 요청마다 응답에 실을 note를 한 번에 읽는다(§5-5). `needs_public_check` 확인도 이것으로 한다(§2-2) | 답할 사람 찾기 route 뒤라도 된다 | 단건 public 읽기를 동시에 부른다. 답할 사람 찾기는 요청당 16~24번, 주제 추천은 사람마다 1개로 줄여 최대 22번이 된다 |
| R3 | 수정·공개 범위 변경·삭제 이벤트를 그 기능과 함께 발행하는 것. **1차 답변(2026-11-06): 합의대로.** 저장이 끝난 뒤 발행하고, 공개 범위를 바꿀 때도 `version`을 올린다 | discovery는 listener를 먼저 띄운다 | 그 기능이 생길 때 | 주기적 다시 맞추기(15분)와 요청 경로의 감지가 순위 쪽을 따라간다. 응답 내용은 영향이 없다 |
| R4 | 일정. **1차 답변(2026-11-06):** `trusted/` 이동은 `main`에 들어갔다(`3fee423`). prod에서 writer를 켜는 일정과 마지막 저장 형식 변경 시점은 note-api가 정할 수 없어 오너가 답한다. dev 배포 전 테이블 비우기 말고 예정된 저장 형식 변경은 없다. prod 배포는 OpenSearch 컬렉션 URL이 정해져야 한다. trusted 조회에 탈퇴 표시를 붙이는 선택 요청은 note-api가 하지 않기로 권했다(trusted는 저장된 그대로를 주는 곳이고, `needs_public_check`는 R2가 대신한다). 받아들인다 | backfill과 prod 적재의 시점이 여기에 걸린다 | prod 적재 전 | — |

요청하지 않기로 한 것:
- **note에 card 역할이나 종류를 붙여 달라는 것.** discovery의 검색 사정으로 계속 바뀔 판단이다. 메모 §12-4의 "tag는 discovery가 붙이고 관리한다"와 같은 이유다. judge는 이름의 종류를 내보내지 않는다.
- **card로 note를 찾는 기능.** note-api 안에 내부 쿼리(`element_body`)가 있지만 route는 아니다. discovery는 `note_cards`로 직접 찾는다.
- **embedding.** note-api는 embedding을 갖지 않는다. 검색 품질과 함께 바뀔 것이라 discovery가 갖는다.
- **바뀐 note만 읽는 길(변경 목록).** 응답 내용은 요청할 때 note-api가 지키므로, 순위 쪽 신호가 늦게 빠지는 것만 남는다. 지금은 15분 주기와 요청 경로의 감지로 충분하다고 본다. 사본을 갖게 되면(§12-1) 그때 요청한다.

---

## 12. 나중에 붙일 것 (이번 범위 밖)

### 12-1. 사본을 갖게 될 때

v1은 원본을 두지 않는다. 아래 경우에는 public note의 사본을 discovery에 두는 쪽을 다시 본다.
- note-api 읽기의 지연이나 실패가 응답에 눈에 띄게 영향을 줄 때(§9의 dev 측정)
- shout 재순위처럼 요청 한 번에 읽을 본문이 많아질 때
- 오너가 "요청마다 note-api를 부르지 않는다"를 다시 요구할 때

**그때 덧붙이기만 하면 되게 지금 둘 것:**
- **note 내용을 읽는 곳을 한 interface 뒤에 둔다.** 예: `NoteContents.read_public(refs) -> PublicRead(found, missing)`. 돌려주는 것은 discovery가 정한 모양이다(note-api의 `SharedNote`를 그대로 쓰지 않는다). v1 구현은 note-api 여러 개 public 조회다. 사본을 두면 DB에서 읽는 구현으로 바꾼다. 두 route와 오프라인 CLI는 이 interface만 쓰고, 빠진 것(`missing`)의 처리(§5-5)도 interface 위에서 한다.
- **적재 쓰기(§2-2의 4)에 사본 열만 더하면 된다.** 적재는 이미 trusted 조회로 본문을 읽는다. 사본에는 public 읽기와 같은 공유 필드만 담는다. `notes` row에 열을 더하는 migration 하나와 `cli reindex`로 채운다.
- **`searchable`, `generation`, lease, 조건부 UPDATE는 그대로 쓴다.** 사본이 생기면 `searchable`이 응답 내용까지 지키게 된다. 그때는 이벤트가 새는 경우의 노출 시간을 줄이려고 note-api에 변경 목록을 요청한다(§11에서 지금 요청하지 않은 것).
- **private이 되면 사본은 지운다.** 파생 데이터와 달리 사본은 본문 자체라 남기지 않는다. §2-2의 private 쓰기에 사본 지우기만 더하면 된다.

### 12-2. 그 밖

- **shout:** 같은 인덱스와 사람 점수(§6-2)를 쓰고, 재순위와 shout 범위를 더한다. 재순위가 읽을 본문은 여러 개 public 조회로 읽는다(후보 20명이면 2번 남짓). 범위를 넓히는 축은 등록된 tag의 넓이다(메모 §12-1).
- **for-you를 잇는 기능:** 공개 discover 화면을 note 기반으로 다시 만든다.
- **인용 피드백, 대화 이력 목록 이벤트, 유저 tag:** note 품질 신호와 사람 신호다(메모 §9-6, §8-2, §8-1).
- **가벼운 상태 조회:** 주기적 다시 맞추기는 지금 note를 통째로 읽는다. 규모가 커지면(note 10만 개면 15분마다 복호화 1,000번) note-api에 `version`과 `visibility`만 돌려주는 조회를 요청한다. 둘 다 note-api에 평문으로 저장된 값이다.

---

## 13. 열린 항목

| # | 무엇 | 누가 | 언제 |
|---|---|---|---|
| 1 | prod RDS에서 pgvector extension을 켤 수 있는지. 안 되면 §3-1의 2안(dev는 켤 수 있다, 2026-11-06) | 인프라 | prod 인프라 세팅 때 |
| 2 | 등록된 tag 목록이 커질 때 프롬프트에 보여줄 방식("k 키우기" 등) | discovery | 목록이 `analysis.tag_prompt_max`에 닿기 전 |
| 3 | 이미 등록된 tag끼리 합치는 작업 | discovery | v1 뒤 |
| 4 | 1층을 늘 벡터와 섞을지, 20개 미만일 때만 폴백할지 | discovery | dev 규모를 본 뒤 |
| 5 | note가 적은 사람의 완화책(centroid, 개수 정규화) | discovery | 출시 전 오프라인(H-10, H-mix) |
| 6 | §11의 R1~R4 최종 답(1차 답변은 받았다, 2026-11-06). R4의 prod writer 일정과 저장 형식 변경 시점은 오너가 답한다 | note-api, 오너 | 표의 "언제" |
| 7 | card 종류를 discovery가 정하는 방식이 맞는지(`generic` 걸러내기 포함), card를 앞으로 올리는 가산의 크기 | discovery | dev |
| 8 | 주제 추천에 LLM 재순위를 넣을지 | 오너 | dev 사용 뒤 |
| 9 | bourbon-agent가 인용한 note id를 돌려주는 방법 | bourbon-agent | v1 뒤 |
| 10 | 두 route의 이름과 필드 | bourbon-agent | route 구현 전 |
| 11 | 공개 `/discover/*`, `/recommendations/opened|shown`을 지금 부르는 클라이언트(앱)가 있는지 | 클라이언트 | 지우기(§10-2의 1) 전 |
| 12 | `decisions`, `room_turns`의 보존 기간 | discovery | 적재 단계 |
| 13 | ~~private이 된 note의 파생 데이터를 지울지~~ → 정해짐(2026-11-06): 남기고 공개 범위로 거른다(§2-2) | — | — |
| 14 | deferq queue와 메시지가 broker 재시작 뒤에도 남는지 | discovery | 적재 단계 |
| 15 | note-api 읽기의 실제 지연(dev, 클러스터 안에서) | discovery | 답할 사람 찾기 route 전 |
| 16 | ~~card 이름 사본을 둘지~~ → 정해짐(2026-11-06): 둔다(§2-5) | — | — |
| 17 | ~~짧은 주제 문장 질문 세트~~ → 정해짐(2026-11-06): 만들어 출시 기준에 넣는다(§6-4) | — | — |
| 18 | ~~"public note만"을 지키는 범위~~ → 정해짐(2026-11-06): 받아들인다(§7-3) | — | — |
| 19 | ~~topic-api를 끄는 시점~~ → 정해짐(2026-11-06): 지금부터 없다고 본다(§10-2) | — | — |
| 20 | 옛 DynamoDB 이벤트 로그와 결정 로그를 내보낼지(기본은 내보내지 않고 지운다) | 오너 | 지우기 전 |
| 21 | dev에서 topic-api가 실제로 꺼져 있는지, 지우기부터 bourbon-agent 전환까지 bourbon-agent의 추천 tool을 끌지 | 오너 | 지우기 전 |
| 22 | private으로 오래 머무는 note의 파생 데이터를 얼마나 둘지(지금은 public이 되거나 지워질 때까지) | 오너 | v1 뒤 |
| 23 | 짧은 주제 문장 세트의 크기, 만드는 방법, 판정 깊이(§6-4) | discovery, 오너 | 주제 추천 출시 전 |

---

## 검토 기록

**2026-11-07, 오너 결정·note-api 1차 답변 반영분을 셋이 검토(새 Fable, 새 Opus, 작성자)하고 바뀐 것**
- dev의 note-api(`deploy/2611`, PR #33 초안)는 이미 `note_updated`를 내고, 그 안에 공개 범위 변경과 철회도 담는다. 그래서 `note_updated`도 받는 즉시 숨긴다. 철회된 note는 "없음"과 같이 다룬다(§2-1, §2-2).
- 파생 데이터는 지금 내용과 hash가 맞을 때만 쓴다. private 동안 바뀌었다가 다시 public이 된 note나, 수정 뒤 분석이 실패한 note의 옛 tag가 `matched_tags`에 나오던 틈을 막았다(§5-1, §2-2).
- "지우기 먼저"에서 남기는 코드도 같은 PR에서 고쳐야 하는 곳(탈퇴 처리, `message_created`, 이벤트 로그, 재시도, 보존 sweep, scripts)과, migration은 새 worker가 뜬 뒤에 돌리는 순서, deferq queue 정리를 적었다(§10-2).
- bourbon-agent가 지금 부르는 것은 `/recommend/explicit`다(§10-2).
- pgvector extension은 인프라가 만들고, 2안은 스키마가 다르다는 것을 적었다(§10-2).
- reindex는 public note만 다시 건다(§2-3). IAM은 공유 role이라 권한만 뺀다(§3-4).
- 짧은 주제 문장 세트의 만드는 방법, 판정, 기준을 적었다(§6-4).
- 열린 항목 20~23을 더했다.

**2026-11-06, note-api 1차 답변으로 바뀐 것**
- R1(card 여러 개 조회)과 R2(public note 여러 개 조회)의 경로와 응답 모양을 적었다. 이름 정규화가 계약이 되고, card id는 합쳐지거나 사라지지 않으며, card 변경은 `version`으로 비교한다(§2-2, §2-5, §3-1, §5-5, §11).
- R2의 `not_found`는 이유를 나누지 않는다. discovery는 모두 "지금 쓸 수 없다"로 다룬다(§5-5). `needs_public_check` 확인도 R2로 한다(§2-2).
- 제목만 주는 선택과 trusted 조회의 탈퇴 표시는 하지 않는다(§11).
- note-api의 `trusted/` 이동이 `main`에 들어갔다(`3fee423`). prod는 OpenSearch 컬렉션 URL을 기다린다(§10-2).
- 최종 구현 계획이 아니라 1차 답변이다.

**2026-11-06, 오너 결정으로 바뀐 것 (#162 뒤)**
- private이 된 note의 파생 데이터를 지우지 않고 `searchable`로 거른다. 메모 §13-4의 3과 같은 방향이다. 그 조건 중 "private인 동안에도 수정 이벤트를 처리한다"는, LLM 없이 `content_hash`만 적고 다시 public이 될 때 hash 비교로 다시 만드는 것으로 바꿨다(§2-2).
- note-api 공유 card의 이름 사본을 둔다. 품질(정확 일치)과 성능(요청마다 note-api를 부르지 않음) 모두에 효과가 있다(§2-5).
- 짧은 주제 문장 질문 세트를 만들어 주제 추천의 출시 기준에 넣는다(§6-4).
- "public note만"을 내용과 사람에는 즉시, 순위에는 이벤트 처리 시간 안에 지키는 것을 받아들였다(§7-3).
- topic-api는 지금부터 없다고 본다. 지우기를 맨 앞으로 옮기고 되돌리기를 뺐다(§10-2).
- dev는 pgvector를 쓴다. prod는 인프라 세팅 때 확인한다(§3-1, 열린 항목 1).

**2026-11-06, 사본 없는 안의 확인 검토로 더 바뀐 것**
- 삭제 급증 차단을 묶음 단위에서 "최근 1시간, 전체의 5%, 5명 이상의 owner"로 바꾸고, 걸리면 sync loop 전체가 아니라 지우기만 보류한다. 한 유저의 일괄 삭제나 탈퇴, note-api의 테이블 비우기에서 모든 처리가 멈추던 문제를 고쳤다. 푸는 CLI를 두었다(§2-2).
- 요청 경로의 비정상 판단에 최소 개수(10개)를 더했다. 몇 사람이 private으로 돌린 것만으로 결과가 비지 않게 했다(§5-5).
- 요청 중 읽기에서 빠졌던 note는 `needs_public_check`로 표시하고, trusted 조회만으로 다시 올리지 않는다. 탈퇴 이벤트를 놓친 유저의 note가 검색을 오가는 것을 막는다(§2-2).
- 주기적 다시 맞추기는 `ready` row만 본다. backfill 중에 처리 중인 row를 계속 다시 걸던 낭비를 막는다(§2-3).
- backfill을 discovery에 없는 note에만 걸고 주 1회 다시 돈다. 잘못 지워진 note도 이것으로 되찾는다(§2-3). 지우는 DELETE에도 같은 조건을 건다. 탈퇴 확인은 트랜잭션을 되돌리지 않고 같은 트랜잭션에서 지운다(§2-2).
- 주제 추천의 사람 점수는 요청자와 `exclude_user_ids`를 빼기 전에 계산한다. 실험과 같아야 "같은 계산인지" 테스트가 통과한다(§5-1, §6-2).
- 출시 기준에 검정력 확인(R과 gfull2로 −0.025가 통과하는지)과, 라벨이 없는 쌍을 더 판정한 뒤 센다는 규칙을 더했다(§6-4).
- R4에 trusted 조회의 탈퇴 표시를 선택 요청으로 더했다(§11). → note-api 1차 답변에서 하지 않기로 했다(R2가 대신한다).

**2026-11-06, 사본 없는 안을 셋이 다시 검토(새 Fable, 새 Opus, 작성자)하고 바뀐 것**
- 적재를 agent용 public 읽기가 아니라 trusted 여러 개 조회로 한다. note-api가 정한 쓰임(서비스는 trusted, 답은 public)과 맞고, `not_shown` 상태와 그 차단, 적재의 R2 의존이 없어졌다(§2-2).
- 삭제 급증 차단을 적재와 주기적 다시 맞추기에 두고, 요청 경로에는 빠진 비율이 비정상이면 검색에서 빼지 않고 실패로 다루는 판단을 두었다(§2-2, §5-5).
- note-api 읽기가 실패하면 파생 데이터로만 고른 사람도 내보내지 않고 빈 결과로 답한다(§7-6).
- 요청 중 읽은 `version`이 앞서 있으면 그 note의 tag를 이유에 쓰지 않고 다시 맞추기를 건다. 이벤트가 샌 수정도 여기서 잡힌다(§5-5).
- private이 되면 파생 데이터를 모두 지운다. 지워진 note는 row째 지운다(tombstone 없음)(§2-2).
- `claim_id`를 가져갈 때마다 새로 만든다(§2-2).
- 답할 사람 찾기의 순서를 실험의 층 순서(tag 층 → 20개 미만이면 폴백)로 되돌리고, card와 미분석은 그 뒤에 붙였다(§5-2).
- 출시 기준을 "같은 계산인지"(결정적 테스트)와 "새 프롬프트가 나빠지지 않는지"(기준 라벨 bootstrap)로 나누고, 기준 라벨의 크기에 맞춰 p@5 허용선을 −0.025로 했다. 새 주제 문장 세트는 출시 기준에서 뺐다(§6-4, §7-2).
- note-api 읽기는 남은 마감 시간을 쓰고, route 마감 시간을 새로 둔다(§5-5, §7-6). R2 전 주제 추천은 사람마다 note 1개만 읽는다.
- R2에 찾은 것/못 찾은 것 구분, 읽을 수 없는 note 건너뛰기, 지연 줄이기, 제목만 받기를 함께 담았다(§11). discovery가 agent용 route를 불러도 되는 것은 오너가 확인했다(2026-11-06).
- `language`, `conversation_ended_at`을 저장하지 않는다(§3-1). card 종류에 `event`를 더하고 팀은 `org`로 둔다(§2-5). 2안의 메모리 캐시, 쿼리 분석이 tag 목록 크기를 따라 커지는 것, 요청 비용 계산을 적었다.
- 사실 고침: 실험의 z-score는 100명 전체에 대해 냈다, 실험의 tag는 415개(다시 돌린 것은 444개)다, centroid 수치는 첫 판정 라벨의 것이다.
- 오너 확인 항목을 더했다: card 이름 사본(16), 새 질문 세트(17), "public만"을 지키는 범위(18), topic-api 끄는 시점(19).

**2026-11-06, 오너 결정으로 바뀐 것 (사본 없이)**
- 원본(본문)을 discovery에 두지 않는다. 응답에 실을 note 내용은 요청할 때 note-api 여러 개 public 조회 1번으로 읽는다(§2-0, §5-5).
- 사본을 나중에 갖게 될 수 있게 note 내용을 읽는 곳을 한 interface 뒤에 두고 덧붙일 자리를 적었다(§12-1).
- `servable`을 `searchable`로 바꿨다. 이제 응답 내용이 아니라 검색과 사람 점수에 쓸지를 정한다(§2-2).

**2026-11-06, 그 전의 검토(Fable 1·2차, 셋이 함께 한 검토, 확인 검토)로 바뀐 것** (사본을 두던 안에 대한 검토. 지금도 남는 것)
- `generation`과 조건부 UPDATE, `mark_pending` 하나로 모든 표시를 한다(§2-2).
- 사람 점수를 실험에서 잰 점수(넓이 × idf × log(1 + 수), 모든 note의 상위 3개, 전체 owner z-score)로 되돌렸다. 그 전 검토 기록의 "근거 없는 `log(1+n)`을 뺐다"는 틀린 판단이었다(§6-2).
- "이미 대화한 사람"을 `room_turns`와 계산한 방 id로 판정하고, `room_turns`의 7일 규칙을 바꾼다(§6-3, §3-2).
- deferq task 대신 sync loop, advisory lock 대신 lease를 쓴다. tag 등록의 LLM 판정은 전역 lock 밖에서 한다(§2-2, §2-4).
- pgvector를 쓸 수 없을 때의 2안(§3-1), DynamoDB 제거(§3-4), `agents` 제거(§3-2), card 경로의 `generic` 제외와 R1 전 card 경로 끄기(§2-5), listener 이름 고정(§2-1)을 적었다.
- backfill 유저 목록은 bourbon-api의 내부 user 목록으로 얻는다(§2-3).
- 사실 고침: judge 대상에 캐릭터가 있다, `public_element_ids`는 98개 상한이 없다(98은 link item 상한), page 500자는 목표치다, `element_body`는 route가 아니다, 세 이벤트는 note-api 코드에 아직 정의가 없다.

**2026-11-06, note-api 기능 전수 확인으로 바뀐 것**
- entity를 discovery가 뽑지 않는다. note-api의 공유 card(`public_element_ids`)를 쓰고, 종류와 역할만 discovery가 정한다(§2-5).
- note-api 키워드 검색(`others_public`)은 쓰지 않는 이유를 적었다(§5-2).
