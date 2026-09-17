# bourbon-topic-api 요청서 — visibility 변경 이벤트와 prod 워커

> 코드 읽은 기준: topic-api main `cae7fd8`(2026-09-08), persona 동기화·이벤트 쪽 2026-09-10. 결정: R22·R27(조회 범위), R26(카탈로그 route는 **보류** — 요청하지 않는다), R48(visibility 변경 신호는 필요만 적고 형태는 topic-api가 정한다), 이벤트 정의서 §2-2.

## 1. visibility 변경 신호 — 필요와 이유, 형태는 topic-api가 정해 주시면 된다

**문제**: 유저가 topic을 비공개로 돌리는 경로(`PATCH /me/topics/{topic_id}`, `api/routers/me_topics/router.py` `patch_my_topic` → `write_topic_settings` → `write_settings`)는 api 프로세스에서 처리되고, 그 프로세스에는 AMQP 연결이 없어 아무것도 발행하지 않는다. 우리는 topic이 비공개가 되면 그 row를 지워야 하는데, 지금은 다음 persona 동기화(`topics_updated`)까지 추천에 남고, 대화를 하지 않는 유저에게는 그 "다음"이 오지 않는다. **비공개 전환이 이 경로로만 일어나므로 우리에게 가장 중요한 신호다.**

**필요한 것**: 유저가 topic의 visibility를 바꾸면 `user_id`(가능하면 `topic_id`)가 담긴 이벤트 하나. 새 visibility 값은 필요 없다 — 우리는 어차피 내부 route로 재조회한다.

**형태는 topic-api가 정해 주시면 된다.** 플랫폼의 이벤트 추가 기준("판정 기준이 명확하고 소비자가 여럿인 것만 새 타입으로")을 알고 있어, 특정 타입을 요구하지 않는다. 보이는 길은 셋이고 우리 처리는 어느 쪽이든 같다(유저 단위 debounce → 재조회 1회).

1. 기존 `bourbon.topics_updated`를 settings 쓰기에서도 발행. payload는 이미 `user_id, topic_id, topic_revision`을 갖는다. `persona_revision`은 우리가 읽지 않는 필드라 어떻게 하실지는 topic-api의 몫이다.
2. 마지막 추출 기록의 `persona_revision`을 그대로 실어 1과 같이 발행 — 스키마 변경 없이.
3. 새 타입(예 `bourbon.user_topic_settings_updated` `{user_id, topic_id, topic_revision}`).

**의견**: 기준에 비추면 1이 가장 가깝다고 본다 — "그 유저의 topic 상태가 바뀌었다"는 뜻에 이름도 맞고, 소비자가 늘어날 때 타입이 하나라 편하다. 다만 지금 이벤트 정의가 "persona 동기화가 움직인 topic"으로 되어 있어 정의를 넓히는 일이라, 결정은 topic-api에 있다.

**전제 작업**(어느 안이든): api 프로세스에 AMQP 연결. 워커의 `worker/amqp.py`를 api lifespan에도 붙이는 일이고, 설정 `DEFERQ_AMQP_URL`은 이미 있다(현재 "worker only"). 발행자만 필요하고 소비자는 필요 없다. best-effort 발행으로, 브로커가 없어도 patch는 성공해야 한다(발행 실패는 경고만).

**우리 처리**: `topics_updated`와 같은 유저 단위 debounce → 내부 route 재조회 1회. 답이 오기 전까지 우리 미러는 3의 이름을 임시로 쓴다.

## 1-1. 답이 왔다 (2026-09-13, #68·#69) — 3안, 그리고 예상 밖의 선물 하나

> §1은 보낸 그대로 남긴다(README "쓰는 규칙"). 아래가 받은 것이다.

**받은 것**: `bourbon.topic_visibility_changed` `{user_id, topic_id: str \| None}`. 셋 중 **3안**이고, api 프로세스에 AMQP가 붙었다. 발행 지점은 우리가 적었던 `patch_my_topic` 하나가 아니라 **다섯** — `/me/topics` 단건·bulk, 내부 PATCH, topic 삭제, 계정 삭제 — 이고 계정 삭제는 `topic_id` 없이 한 건으로 온다. 우리 처리는 적어 둔 그대로다: `user_id`만 꺼내 유저 단위 debounce → 재조회 1회. 미러의 `topic_id`는 optional로 받는다.

**`consistent=true`(#69)가 특히 고맙다.** 우리 재조회는 그 쓰기 신호를 받고 도는 데다 결과로 그 유저의 row를 **통째로 교체**하므로, 약한 읽기가 "바꾸기 전" 스냅샷을 한 번 돌려주면 **방금 숨긴 row를 우리가 되살려 저장한다** — 그리고 다음 재조회까지 남는다. 우리 쪽 불변식 1이 조용히 깨지는 사실상 유일한 경로였고, 적어 주신 이유("a missed public-to-private move, left cached, is an exposure and not merely staleness")가 정확히 그것이다. 재조회에만 켜고(R56), 요청 경로의 요청자 프로필 조회는 약한 읽기 그대로 둔다 — 그쪽은 남의 노출을 정하지 않고 응답 지연에 직접 올라탄다.

**dev에 실제로 켜져 있는 것까지 확인했다(2026-09-17).** 코드가 들어왔다는 것과 그 배포가 그것을 읽는다는 것은 다른 사실이고, FastAPI는 선언되지 않은 쿼리 파라미터를 조용히 무시하므로 **우리가 보내고 있다는 것만으로는 켜졌다는 증거가 되지 않는다** — 무시되는 동안에도 요청은 200으로 성공한다. dev 게이트웨이에 직접 물어 갈랐다: `consistent=notabool`은 **422**로 거절되고 아무 이름이나 붙인 파라미터는 200으로 통과한다. 선언돼 있고 파싱한다는 뜻이다. 이 확인은 dev에 한정된다 — prod는 §2와 같은 시점 문제다.

**revision이 없는 것은 알고 받는다.** 발행 지점마다 payload 모양을 하나로 두려는 선택으로 이해했고(삭제 경로에는 실을 revision이 남아 있지 않다), 우리가 쓰려던 "재조회가 이벤트보다 낡으면 한 번 더"는 `consistent=true`가 더 곧게 대신한다. 이 건으로 요청할 것은 없다.

**알려 드릴 것 하나**: bulk patch가 **첫 발행 실패 뒤 그 요청의 나머지 행을 건너뛰는** 것으로 읽었다(`announcing`이 false로 내려간 뒤 그 요청 안에서 복구되지 않는다). 브로커가 잠깐 흔들리면 그 요청에서 움직인 나머지 topic들은 신호 없이 남고, 우리 쪽에서는 비공개 전환이 다음 `topics_updated`까지 늦는다 — 대화하지 않는 유저에게는 그 "다음"이 오지 않는다. 한 요청에 발행 타임아웃이 여러 번 쌓이지 않게 하려는 의도라면 그대로 두셔도 된다. 다만 "그 요청에서 한 건이라도 실패했으면 유저 단위로 `topic_id` 없는 한 건" 같은 보정이 싸게 된다면, 우리에게는 그쪽이 확실히 낫다.

## 2. prod 워커 replicas

`worker/`(persona 동기화, `topics_updated` 발행)가 prod에서 LLM 프록시 문제로 0 replicas다(README). 우리 서비스가 prod에 나가는 시점에는 이 워커가 돌아야 한다 — 아니면 유저 topic이 바뀌어도 우리에게 힌트가 오지 않는다. 시점과 막혀 있는 부분을 알려 주시면 우리 배포 순서를 맞춘다.

## 3. 그대로 쓰는 것 (변경 요청 없음)

- `bourbon.topics_updated` (`user_id, topic_id, persona_revision, topic_revision`) — 힌트로 받고 재조회한다. 스냅샷을 이벤트에 싣는 요청은 하지 않는다.
- `GET /api/internal/svc/topic/users/{user_id}/topics?visibility=public&visibility=friends&consistent=true` — 타인 row 재조회. 응답 항목 중 우리가 읽는 필드는 `score, visibility, revision, updated_at, support, descriptions`다. `consistent`는 #69로 생긴 것이고 이 읽기에만 켠다(§1-1).
- 같은 route에 `visibility=public&visibility=friends&visibility=private` — 요청자 자신의 프로필(R22·R27). `hidden`은 요청하지 않는다.
- `GET /api/internal/svc/topic/search/topics` — 타입 ① free text → topic 확정(기존 코드).
- `data/catalog_dist/catalog.json` — 우리 이미지에 빌드 시 복사한다(R26). 카탈로그가 바뀌면 재배포한다. **그래프 route는 요청하지 않는다**(보류). 우리가 모르는 topic id가 응답에 오면 정확 일치만 적용하고 건수를 지표로 남긴다.

## 4. 확인 질문

1. ~~§1 — 세 안 중 어느 것으로 가실지, 발행 지점을 `write_settings` 뒤로 잡은 것이 맞는지.~~ **답 있음**(#68·#69, §1-1). 남은 것은 §1-1 끝의 bulk 발행 건 하나이고, 요청이 아니라 알림이다.
2. §2 — prod 워커가 도는 시점.
3. `catalog.json`이 바뀌는 주기·알림 방법(우리 재배포 트리거).
