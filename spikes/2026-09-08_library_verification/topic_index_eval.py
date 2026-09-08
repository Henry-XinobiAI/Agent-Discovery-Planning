"""Type ①② check: coverage-first ordering with a per-requester friends filter, on OpenSearch
(plan A candidate) and PostgreSQL inverted index (plan B), same data, same 2000 queries.

Correctness is judged against a numpy reference computed from the population file:
  - friends-tier row shown to a non-friend        -> must be 0
  - coverage inversion inside the returned top-20  -> must be 0
  - agent returned that does not hold the topics   -> must be 0
Then p50/p95 latency for 1-3 topic queries (type ①) and single-topic queries (type ②).
"""

import argparse
import json
import time

import numpy as np
import psycopg
import requests

p = argparse.ArgumentParser()
p.add_argument("pop", nargs="?", default="pop.npz")
p.add_argument("--queries", type=int, default=2000)
p.add_argument("--skip-load", action="store_true")
a = p.parse_args()
d = np.load(a.pop)
rng = np.random.default_rng(2)
U = len(d["primary"])
primary, ctp = d["primary"], d["cluster_topic_p"]
tu, tid, tier, score = d["topic_user"], d["topic_id"], d["topic_tier"], d["topic_score"]
fsrc, fdst, fptr = d["friend_src"], d["friend_dst"], d["friend_ptr"]
open_mask = (tier == 1) | (tier == 2)
ou, ot, otier, osc = tu[open_mask], tid[open_mask], tier[open_mask], score[open_mask]
ow = 1 + osc / 101.0 / 3  # per-row weight in [1, 4/3): k matched topics score in [k, k+k/3), k<=3, so ranges never overlap
print(f"open rows={len(ou)} agents with open rows={len(np.unique(ou))}")

PG = "postgresql://rv:rv@localhost:55432/rv"
OS = "http://127.0.0.1:9200"
TOP = 20
# urllib3 2.x advertises zstd/br; OpenSearch 2.19's netty encoder throws on it and the response
# never arrives (see report). Pin gzip.
requests = requests.Session()
requests.headers["Accept-Encoding"] = "gzip"
import functools, builtins  # noqa: E402
print = functools.partial(builtins.print, flush=True)


def friends_of(u):
    return fdst[fptr[u]:fptr[u + 1]]


# ---------------------------------------------------------------- reference (numpy)
by_topic = {}
order = np.argsort(ot, kind="stable")
bounds = np.searchsorted(ot[order], np.arange(3004))
for t in range(3003):
    sl = order[bounds[t]:bounds[t + 1]]
    by_topic[t] = (ou[sl], otier[sl], ow[sl])


def reference(u, topics):
    fr = set(friends_of(u).tolist())
    cov, w = {}, {}
    for t in topics:
        agents, tiers, ws = by_topic[t]
        for ag, ti, wi in zip(agents.tolist(), tiers.tolist(), ws.tolist()):
            if ag == u or (ti == 2 and ag not in fr):
                continue
            cov[ag] = cov.get(ag, 0) + 1
            w[ag] = w.get(ag, 0.0) + wi
    ranked = sorted(cov, key=lambda ag: (-cov[ag], -w[ag], ag))
    return ranked[:TOP], cov, w, fr


# ---------------------------------------------------------------- load
if not a.skip_load:
    t0 = time.time()
    with psycopg.connect(PG, autocommit=True) as conn:
        conn.execute("DROP TABLE IF EXISTS open_rows")
        conn.execute("CREATE TABLE open_rows (agent_id int, topic_id int, tier smallint, w real)")
        with conn.cursor().copy("COPY open_rows (agent_id, topic_id, tier, w) FROM STDIN") as cp:
            for row in zip(ou.tolist(), ot.tolist(), otier.tolist(), ow.tolist()):
                cp.write_row(row)
        conn.execute("CREATE INDEX ON open_rows (topic_id) INCLUDE (agent_id, tier, w)")
        conn.execute("ANALYZE open_rows")
    print(f"PG loaded in {time.time()-t0:.1f}s")

    t0 = time.time()
    requests.delete(f"{OS}/agents")
    requests.put(f"{OS}/agents", json={
        "settings": {"number_of_shards": 1, "number_of_replicas": 0, "refresh_interval": "-1"},
        "mappings": {"properties": {
            "owner": {"type": "integer"},
            "topics": {"type": "nested", "properties": {
                "id": {"type": "keyword"}, "tier": {"type": "keyword"}, "w": {"type": "float"}}},
        }},
    }).raise_for_status()
    agents = np.unique(ou)
    o2 = np.argsort(ou, kind="stable")
    ab = np.searchsorted(ou[o2], np.concatenate([agents, [U]]))
    buf, n = [], 0
    for k, ag in enumerate(agents.tolist()):
        sl = o2[ab[k]:ab[k + 1]]
        doc = {"owner": ag, "topics": [
            {"id": str(t), "tier": "public" if ti == 1 else "friends", "w": float(wi)}
            for t, ti, wi in zip(ot[sl].tolist(), otier[sl].tolist(), ow[sl].tolist())]}
        buf.append(json.dumps({"index": {"_index": "agents", "_id": str(ag)}}))
        buf.append(json.dumps(doc))
        if len(buf) >= 10000:
            r = requests.post(f"{OS}/_bulk", data="\n".join(buf) + "\n",
                              headers={"Content-Type": "application/x-ndjson"})
            r.raise_for_status(); assert not r.json()["errors"]; buf = []
    if buf:
        r = requests.post(f"{OS}/_bulk", data="\n".join(buf) + "\n",
                          headers={"Content-Type": "application/x-ndjson"})
        r.raise_for_status(); assert not r.json()["errors"]
    requests.put(f"{OS}/agents/_settings", json={"index": {"refresh_interval": "1s"}})
    requests.post(f"{OS}/agents/_refresh")
    requests.post(f"{OS}/agents/_forcemerge?max_num_segments=1")
    print(f"OS loaded {len(agents)} docs in {time.time()-t0:.1f}s")
    print("OS store:", requests.get(f"{OS}/_cat/indices/agents?h=docs.count,store.size&format=json").json())
    with psycopg.connect(PG) as conn:
        print("PG size:", conn.execute("SELECT pg_size_pretty(pg_total_relation_size('open_rows'))").fetchone())


# ---------------------------------------------------------------- queries
def gen_queries(n, ntopics_p):
    qs = []
    for _ in range(n):
        u = int(rng.integers(U))
        k = rng.choice([1, 2, 3], p=ntopics_p)
        topics = rng.choice(3003, k, replace=False, p=ctp[primary[u]]).tolist()
        qs.append((u, topics))
    return qs


PG_SQL = """
SELECT agent_id, count(*) AS cov, sum(w) AS s
FROM open_rows
WHERE topic_id = ANY(%s) AND agent_id <> %s
  AND (tier = 1 OR (tier = 2 AND agent_id = ANY(%s)))
GROUP BY agent_id
ORDER BY cov DESC, s DESC, agent_id
LIMIT %s
"""


def pg_query(cur, u, topics):
    cur.execute(PG_SQL, (topics, u, friends_of(u).tolist(), TOP))
    return [(r[0], r[1]) for r in cur.fetchall()]


def os_body(u, topics):
    fr = friends_of(u).tolist()
    should = []
    for t in topics:
        def nested(tier):
            return {"nested": {"path": "topics", "score_mode": "max", "query": {"function_score": {
                "query": {"bool": {"filter": [{"term": {"topics.id": str(t)}}, {"term": {"topics.tier": tier}}]}},
                "field_value_factor": {"field": "topics.w", "missing": 0}, "boost_mode": "replace"}}}}
        should.append({"bool": {"should": [
            nested("public"),
            {"bool": {"filter": [{"terms": {"owner": fr}}], "must": [nested("friends")]}},
        ], "minimum_should_match": 1}})
    return {"size": TOP, "_source": ["owner"], "track_total_hits": False,
            "query": {"bool": {"should": should, "minimum_should_match": 1,
                               "must_not": [{"term": {"owner": u}}]}}}


def os_query(sess, u, topics):
    r = sess.post(f"{OS}/agents/_search", json=os_body(u, topics))
    r.raise_for_status()
    return [(h["_source"]["owner"], int(np.floor(h["_score"] + 1e-6))) for h in r.json()["hits"]["hits"]]


def check(name, results, queries):
    friend_viol = cov_inv = wrong_hold = 0
    overlap = []
    for (u, topics), res in zip(queries, results):
        ref, cov, w, fr = reference(u, topics)
        last = 99
        for ag, c in res:
            if ag not in cov or cov[ag] != c:
                wrong_hold += 1
            if c > last:
                cov_inv += 1
            last = c
            # any friends-tier row of this agent among the query topics, when u is not a friend?
            if ag not in fr:
                for t in topics:
                    agents, tiers, _ = by_topic[t]
                    m = (agents == ag) & (tiers == 2)
                    if m.any():
                        # allowed only if the agent also had a public row counted; coverage
                        # equality above already proves the friends row was not counted.
                        pass
        # friends violation: counted coverage exceeds what public+friend rows allow
        overlap.append(len(set(ag for ag, _ in res) & set(ref)) / max(1, len(ref)))
        if any(cov.get(ag, 0) != c for ag, c in res):
            friend_viol += 1
    print(f"{name}: friends/leak violations={friend_viol} coverage_inversions={cov_inv} "
          f"wrong_holdings={wrong_hold} mean_top{TOP}_overlap_with_reference={np.mean(overlap):.4f}")


def timed(fn, queries):
    lat = []
    out = []
    for u, topics in queries:
        t = time.perf_counter()
        out.append(fn(u, topics))
        lat.append((time.perf_counter() - t) * 1000)
    lat = np.array(lat)
    return out, f"p50={np.percentile(lat,50):.1f}ms p95={np.percentile(lat,95):.1f}ms max={lat.max():.0f}ms"


q1 = gen_queries(a.queries, [0.5, 0.35, 0.15])   # type ①
q2 = gen_queries(a.queries // 2, [1.0, 0, 0])   # type ② one section
hot = np.argsort(-np.bincount(ot, minlength=3003))[:20]
q_hot = [(int(rng.integers(U)), [int(rng.choice(hot))]) for _ in range(200)]

with psycopg.connect(PG) as conn, conn.cursor() as cur:
    sess = requests
    for _ in range(50):  # warm up both
        pg_query(cur, *q1[0]); os_query(sess, *q1[0])
    for label, qs in [("type① 1-3 topics", q1), ("type② 1 topic", q2), ("hot topics", q_hot)]:
        r_pg, l_pg = timed(lambda u, t: pg_query(cur, u, t), qs)
        r_os, l_os = timed(lambda u, t: os_query(sess, u, t), qs)
        print(f"\n[{label}] n={len(qs)}  PG {l_pg}  |  OS {l_os}")
        check("  PG", r_pg, qs)
        check("  OS", r_os, qs)
        same = np.mean([[c for _, c in x] == [c for _, c in y] for x, y in zip(r_pg, r_os)])
        print(f"  coverage sequence identical PG vs OS: {same:.4f}")
