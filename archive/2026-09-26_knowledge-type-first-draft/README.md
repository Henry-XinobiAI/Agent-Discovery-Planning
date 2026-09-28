# 2026-09-26 새 추천 타입의 첫 초안 — 아카이브

`personal-knowledge-agent-recommendation.md`(2026-09-18 ~ 09-21)는 새 추천 타입(타입 ④ 후보)의 첫 초안이다. memory-api personal build의 결과를 topic에 조인해 근거로 썼다. 2026-09-26 구조를 `new-type/knowledge-agent-recommendation.md`가 대체했다 — 근거를 새 서비스 `bourbon-lived-knowledge-api`의 경험 기록(메시지 단위, 보낸 사람 기준, 요약문, 원문 없음)으로 두고, 사람이 필요한 질문만 추천한다.

**이 안의 설계는 유효하지 않다.** 소스 B(personal build 파생본), `topic_qid_map` 조인, 폴링 루프, `consultable`·authorship을 선행 조건으로 둔 적재 계획은 새 문서가 대체했다.

**남는 것은 코드 독해와 문제 정리다.**

| 부분 | 남는 가치 |
|---|---|
| §3-2 | memory-api-v2 personal build의 코드 독해(2026-09-15 `6c0ae52` 기준) — 빌드 단계, QID가 붙는 레이어, cross-owner route, manifest, 인증·동의 부재 |
| §3-3 | topic-api의 persona 추출·`score_detail`·카탈로그 계층 독해(2026-09-19 `ae09a28` 기준) |
| §7-2 | 카탈로그 topic과 memory-api 엔티티의 QID가 같은 dump를 쓰지만 서로 다른 그래프라는 점, `POST /knowledge/expand`의 한도 |
| §10-2 | authorship 문제(한 사용자의 memory에 든 다른 사람의 말)의 두 입장과 provenance 기준 네 갈래 분류 — 새 문서는 보낸 사람 기준 저장으로 대부분 풀었다 |
| §11 | 타입 ① 실측을 기준으로 한 지연 시간 추정표 |
