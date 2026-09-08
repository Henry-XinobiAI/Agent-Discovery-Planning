"""Load the same synthetic conversation log into Gorse (plan A, service form) with the same
leave-one-out split as cf_eval.py, then evaluate GET /api/recommend/{user} against the held-out
partner. Run with `load` first, `eval` after the fit has completed (see docker logs)."""

import argparse
import datetime as dt
import json
import sys
import time

import numpy as np
import requests

p = argparse.ArgumentParser()
p.add_argument("mode", choices=["load", "eval"])
p.add_argument("pop", nargs="?", default="pop100k.npz")
p.add_argument("--eval-users", type=int, default=5000)
p.add_argument("--gorse", default="http://127.0.0.1:18088")
a = p.parse_args()
d = np.load(a.pop)
rng = np.random.default_rng(1)  # identical sequence to cf_eval.py
U = len(d["primary"])
disc = d["discoverable"]
actor, owner = d["conv_actor"], d["conv_owner"]

pairs, counts = np.unique(np.stack([actor, owner], axis=1), axis=0, return_counts=True)
n_partners = np.bincount(pairs[:, 0], minlength=U)
eligible = np.flatnonzero(n_partners >= 2)
eval_users = rng.choice(eligible, min(a.eval_users, len(eligible)), replace=False)
holdout, by_user = {}, {}
for idx, (u, o) in enumerate(pairs):
    by_user.setdefault(u, []).append(idx)
mask = np.ones(len(pairs), bool)
for u in eval_users:
    idx = by_user[u][rng.integers(len(by_user[u]))]
    holdout[u] = pairs[idx, 1]
    mask[idx] = False

S = requests.Session()
S.headers["Accept-Encoding"] = "gzip"
base = dt.datetime(2026, 9, 8, tzinfo=dt.UTC)


def post(path, rows, batch=5000):
    t = time.time()
    for i in range(0, len(rows), batch):
        r = S.post(f"{a.gorse}{path}", json=rows[i:i + batch], timeout=300)
        if r.status_code != 200:
            print(path, r.status_code, r.text[:200]); sys.exit(1)
    print(f"{path}: {len(rows)} rows in {time.time()-t:.1f}s", flush=True)


if a.mode == "load":
    ts = (base - dt.timedelta(days=100)).isoformat()
    post("/api/users", [{"UserId": f"u{i}"} for i in range(U)])
    post("/api/items", [{"ItemId": f"u{i}", "IsHidden": bool(not disc[i]), "Timestamp": ts,
                         "Categories": [], "Labels": {}} for i in range(U)])
    fb = []
    tr = pairs[mask]
    days = rng.integers(0, 90, len(tr))
    for (u, o), dd in zip(tr.tolist(), days.tolist()):
        fb.append({"FeedbackType": "talked", "UserId": f"u{u}", "ItemId": f"u{o}",
                   "Timestamp": (base - dt.timedelta(days=int(dd))).isoformat()})
    post("/api/feedback", fb)
    print("train pairs", len(tr), "eval users", len(eval_users))
else:
    N = 10
    hits, ndcg, lat, empty, errors, first_err = 0, 0.0, [], 0, 0, None
    for u in eval_users.tolist():
        t = time.perf_counter()
        r = S.get(f"{a.gorse}/api/recommend/u{u}?n={N}", timeout=30)
        lat.append((time.perf_counter() - t) * 1000)
        if r.status_code != 200 or not r.text.lstrip().startswith("["):
            errors += 1
            first_err = first_err or f"u{u} HTTP {r.status_code}: {r.text[:200]}"
            items = []
        else:
            items = r.json() or []
        if not items:
            empty += 1
        rec = [int(x[1:]) for x in items]
        if f"u{holdout[u]}" in items:
            hits += 1
            ndcg += 1 / np.log2(rec.index(holdout[u]) + 2)
    n = len(eval_users)
    lat = np.array(lat)
    print(f"Gorse /api/recommend n={N}: HR@10={hits/n:.4f} NDCG@10={ndcg/n:.4f} empty={empty} errors={errors} "
          f"latency p50={np.percentile(lat,50):.1f}ms p95={np.percentile(lat,95):.1f}ms max={lat.max():.0f}ms")
    if first_err:
        print("first error:", first_err)
