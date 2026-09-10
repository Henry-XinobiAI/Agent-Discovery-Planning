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

## 2. prod 워커 replicas

`worker/`(persona 동기화, `topics_updated` 발행)가 prod에서 LLM 프록시 문제로 0 replicas다(README). 우리 서비스가 prod에 나가는 시점에는 이 워커가 돌아야 한다 — 아니면 유저 topic이 바뀌어도 우리에게 힌트가 오지 않는다. 시점과 막혀 있는 부분을 알려 주시면 우리 배포 순서를 맞춘다.

## 3. 그대로 쓰는 것 (변경 요청 없음)

- `bourbon.topics_updated` (`user_id, topic_id, persona_revision, topic_revision`) — 힌트로 받고 재조회한다. 스냅샷을 이벤트에 싣는 요청은 하지 않는다.
- `GET /api/internal/svc/topic/users/{user_id}/topics?visibility=public&visibility=friends` — 타인 row 재조회. 응답 항목 중 우리가 읽는 필드는 `score, visibility, revision, updated_at, support, descriptions`다.
- 같은 route에 `visibility=public&visibility=friends&visibility=private` — 요청자 자신의 프로필(R22·R27). `hidden`은 요청하지 않는다.
- `GET /api/internal/svc/topic/search/topics` — 타입 ① free text → topic 확정(기존 코드).
- `data/catalog_dist/catalog.json` — 우리 이미지에 빌드 시 복사한다(R26). 카탈로그가 바뀌면 재배포한다. **그래프 route는 요청하지 않는다**(보류). 우리가 모르는 topic id가 응답에 오면 정확 일치만 적용하고 건수를 지표로 남긴다.

## 4. 확인 질문

1. §1 — 세 안 중 어느 것으로 가실지, 발행 지점을 `write_settings` 뒤로 잡은 것이 맞는지.
2. §2 — prod 워커가 도는 시점.
3. `catalog.json`이 바뀌는 주기·알림 방법(우리 재배포 트리거).
