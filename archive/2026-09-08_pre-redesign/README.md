# 2026-09-08 이전 문서 — 아카이브

2026-09-08 오너가 제품 설명을 새로 하면서 **이전 문서들이 내려놓은 결정과 제약을 전제하지 않기로** 했고, 새 설계에 혼란을 주지 않도록 여기로 전부 옮겼다. 새 문서는 저장소 루트의 `agent_discovery_redesign.md`부터다.

**이 안의 결정은 유효하지 않다.** `decisions.md`(D01–D26)의 결정, `recsys_opensource/`의 Gorse 채택과 저장 계획, `recommendation_*_design.md`의 파이프라인·스코어링 설계, `inbound_event_contract.md`의 이벤트 제안은 모두 재판단 대상이다.

**사실과 실측은 남는다.** 참고할 때는 결정이 아니라 측정치와 코드 독해만 가져간다.

| 파일 | 남는 가치 |
|---|---|
| `recsys_opensource/gorse.md`, `storage_sizing.md` | Gorse v0.5.11 실측(재계산 시간, RAM, cache 크기), 도쿄 리전 단가(EC2, ElastiCache, RDS, DynamoDB, OpenSearch, DocumentDB) |
| `recsys_build_vs_adopt.md` | 오픈소스 recsys 후보들의 장단점 비교, 지연 추정. 결론(우리 인덱스 권고)은 새 비교(§6)로 대체 |
| `topic_api_analysis.md` | topic-api 코드 독해(2026-08-25 기준, 이후 변경 있음) |
| `inbound_event_contract.md` | 이벤트 설계 원칙 넷(전체 집합+revision, 원천값, 귀속 키, topic id 재작성 금지) — `agent_discovery_events.md` §1이 이어받았다 |
| `recommendation_pipeline_design.md`, `recommendation_scoring_design.md` | 6단계 파이프라인 정의, 422/503 구분 규칙 — 새 계약 §3-3·§4가 이어받았다 |
| `superpowers_specs/` | 이전 구현의 설계 스펙(stance, grounding). 코드에 남은 부분을 읽을 때 |
| `temp` | 이전 서비스 동작 요약 메모 |
| `README_original.md`, `HOW_TO_READ.md`, `decisions.md` | 아카이브 직전의 문서 지도·읽는 순서·결정 레지스터(D01–D26). 무엇이 어디 있었는지 찾을 때 |
