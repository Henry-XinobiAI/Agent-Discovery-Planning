# note 기반 agent-discovery-api — dev 배포 절차

> **2026-11-11에 끝났다.** 실제로 올린 것은 `deploy/2611` `31b2f8d`(phase 9와 이미지 내용 수정 #95까지)다. 해 보며 더한 것: pgvector는 관리 계정으로 안 돼 인프라가 설치했다(3-1). alembic은 `DATABASE_URL`이 dev를 가리키는지 `alembic current`·`heads`로 먼저 본다. 첫 이미지(`8460c6c`)에는 `cli/`가 빠지고 로컬 `data/`가 들어 있었다(#95의 allow-list `.dockerignore`로 고쳤다). 그 뒤의 배포는 §9부터다(phase 10, 2026-11-12에 끝났다. migration 기준 정리는 §10, main 배포와 인덱스 다시 만들기는 §11, 근거 없는 결과의 하한은 §12). **§1~§8은 그 첫 배포의 기록이다.** `room_turns`와 turn queue가 나오는 명령은 0016 뒤에는 그대로 돌리지 않는다.
>
> discovery `deploy/2611`(`e73f1f9`, phase 8 `cli rebuild-index` 포함)을 dev에 처음 올린다. dev는 지금 `60bf02f`(topic 기반), DB는 migration `0011`. prod는 DB도 배포도 없다.
> 되돌림은 없다(topic 시절 테이블을 지운다). 문제가 생기면 앞으로 고친다.
> 근거: discovery README(지금은 `docs/operations.md`. 옛 체인을 0015로 옮기는 절차는 거기서 빠졌다) "Database migrations"·"Rebuilding the note index in the cluster"·"Reloading the note index from a snapshot", 설계 §2-3·§10-2, `requests/infra.md`.

## 순서

1. 준비 → 2. 옛 api·worker 멈춤 → 3. DB를 0015로 → 4. 배포 → 5. 인덱스 채우기 → 6. 확인 → 7. 정리 → 8. 알리기

2부터 bourbon-agent가 `requests/bourbon-agent.md` §4를 배포할 때까지 추천은 "지금은 쓸 수 없다"로 답한다(받아들인 공백).

**명령 블록은 zsh에서 그대로 붙여 넣어도 되게 썼다.** 이 셸은 `interactivecomments`가 꺼져 있어서 줄 끝의 `# …`가 인자로 들어간다. 설명은 모두 따로 된 줄에 있다.

## 1. 준비

- `deploy/2611`로 옮겨서 pull한다(`e73f1f9`, tree가 깨끗해야 한다).
- bastion 터널을 연다(직접 만든 스크립트). DB는 로컬 **15432** → dev RDS 5432를 가정한다. 다른 포트면 아래 URL의 포트만 바꾼다. 7-2에서 Redis(DB 13)도 터널로 닿아야 한다.
- 로컬 compose: 빌드와 3-4의 비교에 쓴다. `init` 이미지가 오래됐으면 먼저 다시 빌드한다.

```bash
docker compose build --ssh default init
docker compose up -d --wait postgres init
```

- dev 관리 계정 URL. 비밀번호는 URL에 직접 쓰지 않고 인코딩한다. `psql`·`pg_dump`는 `PGPASSWORD`로 받는다(프로세스 목록에 안 보이게).

```bash
read -rs PGPASSWORD
export PGPASSWORD
ENC=$(python3 -c 'import os, urllib.parse as u; print(u.quote(os.environ["PGPASSWORD"], safe=""))')
export DEV_ADMIN_PG="postgresql://bourbon_agent_discovery_dbadmin@localhost:15432/bourbon_agent_discovery"
export DEV_ADMIN_URL="postgresql+asyncpg://bourbon_agent_discovery_dbadmin:${ENC}@localhost:15432/bourbon_agent_discovery"
unset ENC
psql "$DEV_ADMIN_PG" -Atc 'select version_num from alembic_version'
```

마지막 줄이 `0011`이면 된다. `.env`의 `DATABASE_URL`은 로컬 그대로 두고, dev는 명령마다 `DATABASE_URL="$DEV_ADMIN_URL"`로만 쓴다.

## 2. 옛 api·worker 멈춤

```bash
kubectl --context dev-tokyo-cluster -n dev scale deploy/bourbon-agent-discovery-api deploy/bourbon-agent-discovery-worker --replicas=0
kubectl --context dev-tokyo-cluster -n dev get pods
```

agent-discovery 파드가 다 없어진 뒤에 기준 숫자를 적는다. 3-5 뒤에 같아야 한다.

```bash
psql "$DEV_ADMIN_PG" -Atc 'select (select count(*) from departed_users), (select count(*) from room_turns)'
```

멈춘 동안의 `message_created`·`user_deactivated`는 queue에 쌓였다가 새 worker가 처리한다(listener 이름이 같다).

## 3. DB를 기준 migration 0015로

**3-1. pgvector.** 권한 오류면 멈추고 인프라에 부탁한다(`infra.md` §1-1).

```bash
psql "$DEV_ADMIN_PG" -c 'CREATE EXTENSION IF NOT EXISTS vector'
```

**3-2. 옛 chain으로 0014까지.** 0012~0014는 `df05ccb`에만 있다. 실패하면 전체가 되돌아가 0011 그대로다.

```bash
git worktree add ../discovery-old-chain df05ccb
(cd ../discovery-old-chain && DATABASE_URL="$DEV_ADMIN_URL" uv run alembic upgrade 0014)
git worktree remove --force ../discovery-old-chain
```

**3-3. 앱 계정 권한.**

```bash
psql "$DEV_ADMIN_PG" -c 'GRANT SELECT, INSERT, UPDATE, DELETE ON notes, tags, note_tags, cards, note_cards, decisions TO bourbon_agent_discovery_app' -c 'GRANT USAGE ON SEQUENCE tags_tag_id_seq TO bourbon_agent_discovery_app'
```

**3-4. 확인(읽기만).** 스키마는 그 자리에서 만든 일회용 DB와 비교한다. 출력이 `스키마 같음`이어야 한다.

```bash
docker compose exec -T postgres psql -U agent_discovery -d agent_discovery -c 'CREATE DATABASE baseline_reference'
docker compose exec -T postgres psql -U agent_discovery -d baseline_reference -c 'CREATE EXTENSION vector'
DATABASE_URL=postgresql+asyncpg://agent_discovery:agent_discovery@localhost:5432/baseline_reference uv run alembic upgrade head
diff <(pg_dump --schema-only --no-owner --no-privileges "$DEV_ADMIN_PG" | grep -v -E '^--|^$|^SET |set_config|alembic_version|restrict ') <(docker compose exec -T postgres pg_dump -U agent_discovery --schema-only --no-owner --no-privileges -d baseline_reference | grep -v -E '^--|^$|^SET |set_config|alembic_version|restrict ') && echo "스키마 같음"
docker compose exec -T postgres psql -U agent_discovery -d agent_discovery -c 'DROP DATABASE baseline_reference'
```

권한은 테이블 8개 × 권한 4개를 하나씩 본다. `has_table_privilege`에 여러 권한을 쉼표로 주면 하나만 있어도 `t`라서 따로 묻는다. 출력이 `0`이어야 한다(빠진 권한 수).

```bash
psql "$DEV_ADMIN_PG" -Atc "SELECT count(*) FILTER (WHERE NOT has_table_privilege('bourbon_agent_discovery_app', t, p)) FROM unnest(ARRAY['notes','tags','note_tags','cards','note_cards','decisions','room_turns','departed_users']) t, unnest(ARRAY['SELECT','INSERT','UPDATE','DELETE']) p"
```

차이나 빠진 권한이 있으면 여기서 멈춘다. stamp로 덮지 않는다.

**3-5. 기준점 표시.** `--purge`가 없으면 지금 코드가 `0014`를 몰라 실패한다.

```bash
DATABASE_URL="$DEV_ADMIN_URL" uv run alembic stamp --purge 0015
psql "$DEV_ADMIN_PG" -Atc 'select version_num from alembic_version'
psql "$DEV_ADMIN_PG" -Atc 'select (select count(*) from departed_users), (select count(*) from room_turns)'
```

`0015`, 그리고 2에서 적은 숫자와 같으면 된다.

## 4. 배포

```bash
k8s/scripts/deploy.sh dev
```

- dev는 확인을 묻지 않는다. "uncommitted changes"로 `[y/N]`을 물으면 멈추고 tree부터 정리한다.
- 마지막 줄이 `=== Deploy complete: … → dev ===`인지 보고 나서 api를 올린다. api Deployment에는 replicas가 없고 HPA는 0에서 움직이지 않아서, 배포만으로는 0개 그대로다. worker는 manifest의 1로 올라온다.
- `deploy.sh`는 kubectl 현재 context를 `dev-tokyo-cluster`로 바꾼다. 중간에 죽으면 `k8s/overlays/dev/kustomization.yaml`이 수정된 채 남을 수 있다(`git checkout --`로 되돌린다).

```bash
kubectl --context dev-tokyo-cluster -n dev scale deploy/bourbon-agent-discovery-api --replicas=1
kubectl --context dev-tokyo-cluster -n dev get pods
```

새 worker가 뜨면서 note queue 넷(`deferq.mark_pending_on_note_{created,updated,visibility_changed,deleted}`)이 생긴다. 인덱스는 비어 있다. worker는 시작할 때 backfill하지 않고, 주기 backfill은 목요일 00:00 UTC(한국 09:00)에 돈다.

## 5. 인덱스 채우기

둘 중 하나로 한다. 나중에 note-api가 note를 다시 쌓을 때도 같다.

- **5-A. 클러스터 안에서(권장, kubectl만).** 첫 배포는 인덱스가 어차피 비어 있어서, 채워지는 동안의 빈틈이 문제가 되지 않는다.
- **5-B. 스냅샷으로(빈틈 없이 바꿔야 할 때).** 노트북, 터널, 관리 계정, broker 콘솔이 필요하다.

### 5-A. 클러스터 안에서

Job은 worker의 이미지로 돈다. 먼저 `--dry-run`으로 Job의 이미지가 이번 배포의 태그(`e73f1f9`)인지 본다.

```bash
k8s/scripts/rebuild-index.sh dev --dry-run
k8s/scripts/rebuild-index.sh dev
```

- 스크립트가 worker를 멈추고 파드가 없어질 때까지 기다린 뒤, Job으로 인덱스 비우기 → note queue 넷 purge → 모든 유저의 note 표시를 하고, 출력을 보여 준 다음 worker를 다시 켠다. 어떻게 끝나든 worker는 다시 켜진다.
- DB가 0015가 아니거나 worker가 아직 돌고 있으면 아무것도 하지 않고 거부한다.
- 첫 실행에서 AMQP 계정에 purge 권한이 있는지가 처음 확인된다. 권한 오류로 실패하면 인덱스는 이미 비워진 상태다. 다시 돌리지 말고, 5-B의 5-2처럼 콘솔에서 note queue 넷을 비운 뒤 worker가 켜진 상태에서 아래의 `cli backfill`을 돌린다(다시 돌리면 같은 권한 오류에서 또 멈춘다).
- 채워지는 것을 본다. `pending`이 줄고 `ready`가 늘다가 멈추면 끝이다.

```bash
kubectl --context dev-tokyo-cluster -n dev exec deploy/bourbon-agent-discovery-worker -- python -m cli rebuild-index --status
```

- 목록을 읽지 못한 유저가 있어 Job이 실패했으면, worker가 켜진 상태에서 다시 표시한다.

```bash
kubectl --context dev-tokyo-cluster -n dev exec deploy/bourbon-agent-discovery-worker -- python -m cli backfill
```

### 5-B. 스냅샷으로

discovery `docs/operations.md` "Reloading the note index from a snapshot"과 같은 순서다.

**5-1. worker 멈춤.** 파드가 없어질 때까지 기다린다(종료 유예 90초). 그 전에 스냅샷을 찍으면, 그 사이 반영된 이벤트를 적재가 덮는다.

```bash
kubectl --context dev-tokyo-cluster -n dev scale deploy/bourbon-agent-discovery-worker --replicas=0
kubectl --context dev-tokyo-cluster -n dev get pods
```

**5-2. note queue 넷을 purge한다(RabbitMQ 콘솔).** `deferq.mark_pending_on_note_*` 넷만이다. 쌓인 이벤트는 다음 스냅샷에 다 들어 있다. 남겨 두면 적재 뒤에 다시 처리되며 note가 잠깐 검색에서 빠지거나 대량 삭제 방지 장치가 걸린다. `count_turn_on_message_created`와 `erase_on_user_deactivated`는 건드리지 않는다.

**5-3. 스냅샷.** dev note-api와 bourbon-api 포워딩을 알아서 열고 닫는다. 마지막 줄이 `complete: True`여야 한다.

```bash
uv run python -m cli snapshot
SNAP=$(ls -d data/dev_snapshots/2*/ | tail -1)
echo "$SNAP"
```

**5-4. 로컬 빌드.** LLM은 dev e3llm을 쓴다. 다른 터미널에서 포워딩을 켜 둔다. 로컬 e3llm이 :8000에 떠 있으면 먼저 끈다(`lsof -i :8000`).

```bash
kubectl --context dev-tokyo-cluster -n dev port-forward svc/e3llm-api 8000:80
```

```bash
LLM_PROXY_URL=http://localhost:8000 uv run python -m cli build "$SNAP" --forget-text
```

- 마지막 줄이 `…, 0 left for the worker`면 된다. 거의 전부 남았으면 LLM 연결 문제다. `--forget-text`가 본문을 지웠으니 5-3부터 다시 한다.
- 끝나면 e3llm 포워딩을 닫는다.

**5-5. dev 적재(관리 계정).** TRUNCATE와 sequence 이동은 앱 계정 권한 밖이라 관리 계정으로 한다. 첫 명령은 계획만 보여 준다. 대상이 `localhost:15432/bourbon_agent_discovery`인지 확인하고 `--confirm`을 붙인다. 한 transaction이라 실패하면 그대로다.

```bash
DATABASE_URL="$DEV_ADMIN_URL" uv run python -m cli load "$SNAP"
DATABASE_URL="$DEV_ADMIN_URL" uv run python -m cli load "$SNAP" --confirm
```

**5-6. worker 올림.** 5-1 이후 쌓인 이벤트를 처리한다.

```bash
kubectl --context dev-tokyo-cluster -n dev scale deploy/bourbon-agent-discovery-worker --replicas=1
kubectl --context dev-tokyo-cluster -n dev logs deploy/bourbon-agent-discovery-worker --tail=50
```

## 6. 확인

```bash
kubectl --context dev-tokyo-cluster -n dev get pods
psql "$DEV_ADMIN_PG" -c 'select state, count(*) from notes group by 1'
```

다른 터미널에서 api를 포워딩하고, 배포된 route에 실제로 묻는다. `--no-forward`는 api가 note-api를 직접 읽기 때문이다. requester는 스냅샷의 handle로 고르고, 노트를 쓴 사람이 아닌 사람으로 묻는다. dev `decisions`에 행이 남는다.

```bash
kubectl --context dev-tokyo-cluster -n dev port-forward svc/bourbon-agent-discovery-api 18082:80
```

```bash
curl -s localhost:18082/ready
uv run python -m cli ask --api http://localhost:18082 --no-forward
```

`/ready`가 `{"status":"ok"}`이고, 답에 사람이 나오고 `degraded`가 비어 있으면 된다.

## 7. 정리

**7-1. topic 시절 queue를 지운다(RabbitMQ 콘솔).** 듣는 곳이 없어 쌓이기만 한다(bourbon-api가 계속 발행한다). 같은 vhost에 다른 서비스의 `deferq.*`도 있으니 이름을 하나씩 확인한다.

- `deferq.arm_refresh_on_topics_updated`
- `deferq.arm_refresh_on_topic_visibility_changed`
- `deferq.mirror_friends_on_friendship_changed`
- `deferq.create_agent_on_user_registered`
- 있으면: `deferq.arm_refresh_on_user_topic_updated`, `deferq.arm_refresh_on_user_topic_settings_updated`

**7-2. Redis DB 13의 refresh task 예약을 지운다.** task 이름은 `agent_discovery.refresh_user_topics`이고, AMQP queue는 없다(Redis로만 돈다). 키는 `deferq:{time,args,ceil}:{agent_discovery.refresh_user_topics}`와 `deferq:run:*:{…}`다. 아래는 Redis가 로컬 16379로 터널돼 있을 때다. 먼저 본 뒤 지운다.

```bash
r() { docker run --rm redis:7 redis-cli -h host.docker.internal -p 16379 -n 13 "$@"; }
r --scan --pattern '*refresh_user_topics*'
r --scan --pattern '*refresh_user_topics*' | while read -r key; do r del "$key"; done
r --scan --pattern '*refresh_user_topics*'
```

**7-3. 로컬과 셸.** 적재를 마친 빌드 DB는 지운다. 스냅샷 디렉터리(`users.jsonl`만 남아 있다)도 `cli ask`에 안 쓸 거면 지운다.

```bash
docker compose exec -T postgres psql -U agent_discovery -d agent_discovery -Atc "select datname from pg_database where datname like 'agent_discovery_build_%'"
unset PGPASSWORD DEV_ADMIN_PG DEV_ADMIN_URL
```

터널과 포워딩을 닫는다.

## 8. 알리기

- **bourbon-agent:** 배포 완료, `/recommend/explicit` 없음. `requests/bourbon-agent.md` §4를 배포해 달라.
- **인프라:** dev DynamoDB 테이블 삭제(`infra.md` §2). queue 깊이 상한(§4)의 대상이 note queue 넷으로 바뀌었다.
- `implementation_progress.md`에 배포 커밋, 시각, 적재한 note 수, 확인 결과를 남긴다.

## 9. phase 10 배포 (2026-11-12, `deploy/2611` `a8fbbe0`)

> **2026-11-12에 끝났다.** 0015에서 0016으로 올렸고, 응답에 `already_talked`가 없고 `degraded`가 비어 있었다. 결정 로그는 `shown_penalty` 0.0, `shown_read` true였고, 두 번째 결정의 `shown_before`가 1씩 늘었다(배포 전 7일 안의 기록도 셌다). `EXPLAIN ANALYZE`는 0.122ms(`ix_decisions_requester_user_id` 인덱스 스캔)라 `agents.shown_read_seconds`는 0.3초로 둔다(설계 열린 항목 25를 닫았다). **9-5의 queue 삭제는 콘솔에 들어가지 못해 인프라에 맡긴다**(`requests/infra.md` §4(다)). 아래는 그 절차의 기록이다.

"이미 대화한 사람"을 "최근 보여 준 사람"으로 바꾸고, turn 세기와 `room_turns`를 지운다(설계 §6-3). migration 0016이 `room_turns`를 지운다. **순서가 중요하다:** 옛 worker나 옛 api가 남아 있을 때 0016을 돌리면, 없어진 테이블 때문에 그 pod가 실패한다. 그래서 배포 → 옛 pod 없음 확인 → queue 삭제 → 0016 순서다.

먼저 bastion 터널을 열고 §1의 관리 계정 블록을 다시 돌린다(7-3에서 변수를 지웠다). 그 블록의 마지막 줄은 이제 `0011`이 아니라 `0015`를 보여야 한다.

**9-1. dev가 0015인지 본다.**

```bash
DATABASE_URL="$DEV_ADMIN_URL" uv run alembic current
```

**9-2. dev의 설정 덮어쓰기를 본다.** API만 `{"agents": {"shown_penalty_on": false}}`를 읽는다(사람이 적어서 감점을 끈다).

```bash
kubectl kustomize k8s/overlays/dev | grep -A1 'settings.json'
```

**9-3. 배포한다.** `deploy/2611`로 옮겨 pull하고(`a8fbbe0`, tree가 깨끗해야 한다) 배포한다. 이번에는 api를 0으로 내리지 않았으니 따로 올릴 필요가 없다.

```bash
k8s/scripts/deploy.sh dev
```

**9-4. 옛 pod가 없고, turn queue의 consumer가 0인지 본다.**

```bash
kubectl --context dev-tokyo-cluster -n dev get pods -l 'app in (bourbon-agent-discovery-api, bourbon-agent-discovery-worker)' -o wide
```

RabbitMQ 콘솔의 Queues에서 `deferq.count_turn_on_message_created`의 Consumers가 0인지 본다.

**9-5. 그 queue를 지운다(콘솔에서 Delete).** purge가 아니라 delete다. purge한 queue는 binding이 남아 모든 `message_created`를 계속 모은다.

**9-6. 0016을 돌린다.**

```bash
DATABASE_URL="$DEV_ADMIN_URL" uv run alembic upgrade 0016
DATABASE_URL="$DEV_ADMIN_URL" uv run alembic current
```

**9-7. 확인한다.** `<user id>`는 dev에서 주제 추천을 받아 볼 유저 하나다. 아래 모두 같은 유저로 한다.

주제 추천을 두 번 부른다(다른 셸에서 port-forward).

```bash
kubectl --context dev-tokyo-cluster -n dev port-forward svc/bourbon-agent-discovery-api 18080:80
```

```bash
curl -s localhost:18080/api/internal/svc/agent-discovery/recommend/agents -H 'content-type: application/json' -d '{"user_id": "<user id>", "topic": "<주제>"}'
```

응답에 `already_talked`가 없고, 결정 로그에 새 필드가 있는지 본다. dev는 감점을 꺼서 `shown_penalty`는 0.0, `shown_read`는 true다. 두 번째 결정에서 첫 번째에 나온 사람의 `shown_before`는 첫 번째 결정의 값보다 1 크다(배포 전 7일 안의 기록도 세므로 1보다 클 수 있다).

```bash
psql "$DEV_ADMIN_PG" -c "SELECT made_at, body->'shown_penalty', body->'shown_read', jsonb_path_query_array(body, '$.shown[*].shown_before') FROM decisions WHERE route = 'agents' AND requester_user_id = '<user id>' ORDER BY made_at DESC LIMIT 2"
```

그다음 결정 로그 읽기가 빠른지 본다. 기록이 있는 유저로 재야 의미가 있다. 이 결과로 `agents.shown_read_seconds`(지금 0.3초)를 정한다(설계 열린 항목 25).

```bash
psql "$DEV_ADMIN_PG" -c "EXPLAIN ANALYZE SELECT elem->>'owner_user_id', count(*) FROM decisions, jsonb_array_elements(body->'shown') elem WHERE requester_user_id = '<user id>' AND route = 'agents' AND made_at >= now() - interval '7 days' GROUP BY 1"
```

**되돌리기:** `room_turns`가 필요한 옛 코드로 되돌려야 하면, 옛 0016(`room_turns`를 지우던 것)이 남아 있는 `a8fbbe0`에서 `downgrade 0015`를 돌리고 그 테이블에 앱 계정 권한을 다시 준다. 빈 `room_turns`가 생기고 `alembic_version`이 옛 코드의 head인 `0015`가 된다. **옛 코드를 배포하기 전에 한다.** 테이블이 없으면 옛 pod가 실패한다(위의 순서를 거꾸로). 지금 코드로는 하지 않는다. 0015가 없어 "Can't locate revision"으로 멈추고, **`downgrade base`는 스키마 전체를 지운다**(§10).

```bash
git worktree add ../discovery-a8fbbe0 a8fbbe0
(cd ../discovery-a8fbbe0 && DATABASE_URL="$DEV_ADMIN_URL" uv run alembic downgrade 0015)
git worktree remove --force ../discovery-a8fbbe0
psql "$DEV_ADMIN_PG" -c 'GRANT SELECT, INSERT, UPDATE, DELETE ON room_turns TO bourbon_agent_discovery_app'
```

옛 worker는 turn queue에 다시 붙는다. 인프라가 그 queue를 지웠으면 새로 만들고, 아직이면 그동안 쌓인 `message_created`를 처리한다(`agent_dm`이 아니면 바로 넘기므로 해는 없다). 다시 앞으로 갈 때는 DB가 `0015`라 지금 코드의 `alembic upgrade head`, `cli load`, `cli rebuild-index`가 모두 거부한다. 이 절의 순서대로 배포 → 옛 pod 없음 확인 → queue 삭제를 한 뒤, 9-6 자리에서 같은 `a8fbbe0` worktree로 `alembic upgrade 0016`을 돌린다(`room_turns`를 지우고 `0016`이 된다).

**9-8. 알리기.** 인프라에 `deferq.count_turn_on_message_created`를 지워 달라고, 그리고 queue 정책 대상에서 빼 달라고 부탁한다(`infra.md` §4(다)). 배포 커밋과 확인 결과는 이 절 머리에 남겼다.

## 10. migration 기준을 0016 하나로 (2026-11-12, discovery #97)

`0015`(기준)와 `room_turns`를 지우던 `0016`을 기준 하나로 합쳤다. id는 `0016` 그대로다. **dev에서 할 일은 없다.** dev의 `alembic_version`이 이미 `0016`이고, 스키마도 새 기준이 만드는 것과 같다. 로컬에서 옛 체인(0015→0016)과 새 기준으로 각각 만든 DB의 `pg_dump --schema-only`가 같았고, `0016`에서 만든 build도 그대로 `cli load`된다. 코드도 바뀌지 않아 다시 배포할 필요가 없다. `deploy/2611`은 다음 배포 때 함께 옮긴다.

- **지금 코드로 downgrade하면 스키마 전체가 지워진다**(`departed_users`, `decisions` 포함, 둘 다 다시 만들 수 없다). dev에서 돌리지 않는다. phase 10을 되돌리는 길은 §9 끝에 있다(`a8fbbe0`에서).
- 로컬 DB가 `0015` 이하이면 compose의 `init`이 "Can't locate revision"으로 멈춘다. 볼륨을 새로 만들고 build를 다시 적재한다(discovery `docs/operations.md`).
- 새 DB(prod 처음)는 빈 DB에 `vector` 확장, `alembic upgrade head`, 그 뒤 테이블 일곱과 `tags_tag_id_seq`에 앱 계정 권한이다(discovery `docs/operations.md`).
- discovery README는 이때 짧게 나뉘었다. 운영 절차는 discovery `docs/operations.md`에 있다. 옛 체인에서 0015로 옮기던 절차는 README에서 빠졌고, 이 문서 §3이 그 기록이다.

## 11. main 배포와 인덱스 다시 만들기 (2026-11-12, `deploy/2611` `80f411b`)

`note-discovery`가 main에 머지됐다(#98). `deploy/2611`을 main(`80f411b`)으로 옮겨 배포했다. 실행 코드는 `a8fbbe0`과 같고 migration은 없다(`alembic current`가 `0016 (head)`).

같은 날 note-api가 저장소를 비우고 모든 note를 다시 만들었다(백필). 그래서 discovery 인덱스도 클러스터 안에서 다시 만들었다(discovery `docs/operations.md` "Rebuilding the note index in the cluster").

```bash
k8s/scripts/rebuild-index.sh dev
kubectl --context dev-tokyo-cluster -n dev exec deploy/bourbon-agent-discovery-worker -- python -m cli rebuild-index --status
```

- 비운 것: note 37, tag 80, card 115, 결정 로그 24. note queue 넷에 남은 메시지는 0이었다(note-api 백필의 이벤트는 그 전에 worker가 처리했다).
- 유저 112명을 모두 읽어 note 166개를 표시했고, 몇 분 뒤 `ready 166`이 됐다. 같은 시각의 snapshot(`20261112T133049Z`)과 수가 같다.
- 두 route 모두 200, `degraded` 없음. 라이카 질문의 1위는 tag(주제 추천)와 tag + card `subject`(답할 사람 찾기)로 맞았고, 2·3위는 뜻만 가까운 사람과 note였다. 이것이 하한을 다시 잰 계기다(설계 §5-3, §6-2).

## 12. 근거 없는 결과의 하한 (2026-11-13, `deploy/2611` `890f62a`)

discovery #99(설계 §5-3, §6-2)를 올린다. `deploy/2611`을 main `890f62a`로 옮겼다. **migration과 백필이 필요 없다.** 근거(broad가 아닌 쿼리 tag, `subject` card)는 인덱스에 이미 있는 tag와 tag 넓이로 요청할 때 계산하고, 하한(`answer.meaning_floor` 0.64, `agents.meaning_floor` 0.60)은 설정값이다. dev의 설정 덮어쓰기(감점 off)는 그대로다.

**12-1. 배포하고, 두 deployment가 `890f62a`인지 본다.**

```bash
k8s/scripts/deploy.sh dev
kubectl --context dev-tokyo-cluster -n dev get deploy bourbon-agent-discovery-api bourbon-agent-discovery-worker -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.template.spec.containers[0].image}{"\n"}{end}'
```

**12-2. 두 route를 부른다(다른 셸에서 port-forward).** §11의 라이카 질문을 다시 보낸다. 뜻만 가까운 사람과 note가 빠지면 결과가 줄거나 비어 있을 수 있고(`no_matching_notes`), 그것이 정상이다.

```bash
kubectl --context dev-tokyo-cluster -n dev port-forward svc/bourbon-agent-discovery-api 18080:80
```

```bash
curl -sS -w '\nHTTP %{http_code}\n' localhost:18080/api/internal/svc/agent-discovery/recommend/agents -H 'content-type: application/json' -d '{"user_id": "<user id>", "topic": "라이카 카메라에 대해서"}'
curl -sS -w '\nHTTP %{http_code}\n' localhost:18080/api/internal/svc/agent-discovery/recommend/notes -H 'content-type: application/json' -d '{"user_id": "<user id>", "question": "라이카 Q2 써 본 사람 있어?"}'
```

**12-3. 결정 로그의 하한을 본다(터널과 관리 계정).** 주제 추천에는 `floor`가 새로 생기고, 답할 사람 찾기의 `floor.value`는 0.64다.

```bash
psql "$DEV_ADMIN_PG" -c "SELECT made_at, route, body->'floor' FROM decisions ORDER BY made_at DESC LIMIT 2"
```

