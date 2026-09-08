"""Mini synthetic population following Agent-Discovery-Planning/synthetic_population_spec.md §2-§3.

Simplifications (documented in the report): topic catalog is 3003 synthetic ids in 54 groups
instead of the real catalog file; user ids are integers (agent == owner index); no event stream,
only the final state plus the conversation log, which is all the CF and index tests need.
"""

import argparse
import time

import numpy as np

p = argparse.ArgumentParser()
p.add_argument("--U", type=int, default=100_000)
p.add_argument("--seed", type=int, default=20260908)
p.add_argument("--lam", type=float, default=3.0, help="conversation_rate (Poisson lambda per user)")
p.add_argument("--out", default="pop.npz")
a = p.parse_args()
rng = np.random.default_rng(a.seed)
t0 = time.time()

U, K, T, G = a.U, 60, 3003, 54

# ---- 3-1 clusters and topic preferences -------------------------------------------------
grp_w = 1 / np.arange(1, G + 1) ** 0.8
topic_group = rng.choice(G, size=T, p=grp_w / grp_w.sum())
group_members = [np.flatnonzero(topic_group == g) for g in range(G)]

cluster_topic_p = np.zeros((K, T))
for k in range(K):
    n_primary = rng.integers(1, 4)
    prim = rng.choice(G, n_primary, replace=False)
    w_prim = rng.uniform(0.6, 0.8)
    gp = np.zeros(G)
    gp[prim] = w_prim / n_primary
    rest = np.setdiff1d(np.arange(G), prim)
    gp[rest] = (1 - w_prim) * rng.dirichlet(np.ones(len(rest)))
    tp = np.zeros(T)
    for g in range(G):
        idx = group_members[g]
        if len(idx) == 0:
            continue
        z = 1 / (rng.permutation(len(idx)) + 1) ** 1.0
        tp[idx] = gp[g] * z / z.sum()
    cluster_topic_p[k] = tp / tp.sum()

cs = 1 / np.arange(1, K + 1) ** 1.1
primary = rng.choice(K, size=U, p=cs / cs.sum())
related = np.array([rng.choice(np.setdiff1d(np.arange(K), [k]), 2, replace=False) for k in range(K)])
n_sec = rng.choice([0, 1, 2], size=U, p=[0.5, 0.35, 0.15])
secondary = -np.ones((U, 2), dtype=np.int64)
for i in range(U):
    n = n_sec[i]
    if n == 0:
        continue
    pool = related[primary[i]] if rng.random() < 0.8 else np.setdiff1d(np.arange(K), [primary[i]])
    secondary[i, :n] = rng.choice(pool, n, replace=False)

affinity = np.full((K, K), 0.05)
for k in range(K):
    affinity[k, related[k]] = 0.5
    affinity[k, k] = 1.0
affinity = np.clip(affinity + rng.normal(0, 0.1, (K, K)), 0.01, None)

# ---- 3-2 users and topics ------------------------------------------------------------------
n_topics = np.clip(np.round(rng.lognormal(np.log(8), 0.7, U)).astype(int), 1, 60)
rows_u, rows_t = [], []
uniform_p = np.full(T, 1 / T)
for i in range(U):
    n = n_topics[i]
    pref = cluster_topic_p[primary[i]].copy()
    secs = secondary[i][secondary[i] >= 0]
    if len(secs):
        pref = 0.7 * pref + 0.3 * cluster_topic_p[secs].mean(axis=0)
    n_off = rng.binomial(n, 0.15)
    picks = rng.choice(T, n - n_off, replace=False, p=pref)
    if n_off:
        picks = np.union1d(picks, rng.choice(T, n_off, replace=False))
    rows_u.append(np.full(len(picks), i))
    rows_t.append(picks)
topic_user = np.concatenate(rows_u)
topic_id = np.concatenate(rows_t)
R = len(topic_user)
topic_score = rng.beta(5, 2, R) * 100
opener = rng.random(U) < 0.6
# tier codes: 0 private, 1 public, 2 friends, 3 hidden
topic_tier = np.where(
    opener[topic_user],
    rng.choice([1, 2, 0, 3], size=R, p=[0.4, 0.2, 0.35, 0.05]),
    0,
)
has_public = np.zeros(U, bool)
has_public[topic_user[topic_tier == 1]] = True
discoverable = has_public ^ (rng.random(U) < 0.02)

# ---- 3-3 friends ------------------------------------------------------------------------
deg = np.clip(np.round(rng.lognormal(np.log(25), 0.9, U)).astype(int), 1, 5000)
cluster_members = [np.flatnonzero(primary == k) for k in range(K)]
src, dst = [], []
for i in range(U):
    d = deg[i]
    same = cluster_members[primary[i]]
    n_same = min(rng.binomial(d, 0.7), len(same) - 1)
    a1 = rng.choice(same, n_same, replace=False) if n_same > 0 else np.empty(0, int)
    a2 = rng.integers(0, U, d - n_same)
    picks = np.concatenate([a1, a2])
    picks = picks[picks != i]
    src.append(np.full(len(picks), i))
    dst.append(picks)
e = np.stack([np.concatenate(src), np.concatenate(dst)])
e = np.unique(np.sort(e, axis=0), axis=1)  # undirected, dedup
friend_src = np.concatenate([e[0], e[1]])
friend_dst = np.concatenate([e[1], e[0]])
order = np.argsort(friend_src, kind="stable")
friend_src, friend_dst = friend_src[order], friend_dst[order]
friend_ptr = np.searchsorted(friend_src, np.arange(U + 1))

# ---- 3-4 conversations (CF truth) ----------------------------------------------------------
pop = np.where(discoverable, rng.pareto(2.0, U) + 1.0, 0.0)
disc_by_cluster = [np.flatnonzero(discoverable & (primary == k)) for k in range(K)]
cum_by_cluster = [np.cumsum(pop[idx]) for idx in disc_by_cluster]
popmass = np.array([c[-1] if len(c) else 0.0 for c in cum_by_cluster])
n_conv = rng.poisson(a.lam, U)
conv_actor, conv_owner, conv_turns, conv_reopened = [], [], [], []
for i in range(U):
    partners: list[int] = []
    for _ in range(n_conv[i]):
        if partners and rng.random() < 0.3:
            owner = partners[rng.integers(len(partners))]
            reopened = True
        else:
            w = affinity[primary[i]] * popmass
            j = rng.choice(K, p=w / w.sum())
            idx = disc_by_cluster[j]
            owner = int(idx[np.searchsorted(cum_by_cluster[j], rng.random() * cum_by_cluster[j][-1])])
            if owner == i:
                continue
            reopened = owner in partners
            if not reopened:
                partners.append(owner)
        conv_actor.append(i)
        conv_owner.append(owner)
        conv_turns.append(min(rng.geometric(0.25), 60))
        conv_reopened.append(reopened)

np.savez_compressed(
    a.out,
    primary=primary, secondary=secondary, affinity=affinity, cluster_topic_p=cluster_topic_p,
    topic_user=topic_user, topic_id=topic_id, topic_tier=topic_tier, topic_score=topic_score,
    discoverable=discoverable, friend_src=friend_src, friend_dst=friend_dst, friend_ptr=friend_ptr,
    pop=pop, conv_actor=np.array(conv_actor), conv_owner=np.array(conv_owner),
    conv_turns=np.array(conv_turns), conv_reopened=np.array(conv_reopened),
)
open_rows = int(((topic_tier == 1) | (topic_tier == 2)).sum())
print(
    f"U={U} topics_rows={R} open_rows={open_rows} discoverable={discoverable.sum()} "
    f"friend_edges_undirected={e.shape[1]} mean_deg={friend_ptr[-1]/U:.1f} "
    f"conversations={len(conv_actor)} distinct_pairs={len(set(zip(conv_actor, conv_owner)))} "
    f"users_with_0_conv={(n_conv==0).sum()} took={time.time()-t0:.1f}s"
)
