"""Type ③ CF check: can implicit ALS (plan A, library form) and a home-made item-neighbour model
(plan B) recover the planted affinity structure from the synthetic conversation log?

Protocol: leave-one-out on users with >= 2 distinct partners. Train on the rest. HR@10 / NDCG@10
of the held-out partner among discoverable agents, train-seen excluded. Baselines: popularity
only, and the oracle (the generator's own truth affinity[cluster(u)][cluster(owner)] * pop).
"""

import argparse
import resource
import sys
import time

import numpy as np
import scipy.sparse as sp

p = argparse.ArgumentParser()
p.add_argument("pop", nargs="?", default="pop.npz")
p.add_argument("--factors", type=int, default=64)
p.add_argument("--iters", type=int, default=15)
p.add_argument("--eval-users", type=int, default=5000)
a = p.parse_args()
d = np.load(a.pop)
rng = np.random.default_rng(1)

U = len(d["primary"])
primary, affinity, pop, disc = d["primary"], d["affinity"], d["pop"], d["discoverable"]
actor, owner = d["conv_actor"], d["conv_owner"]

# distinct (actor, owner) pairs with counts = confidence
pairs, counts = np.unique(np.stack([actor, owner], axis=1), axis=0, return_counts=True)
n_partners = np.bincount(pairs[:, 0], minlength=U)
eligible = np.flatnonzero(n_partners >= 2)
eval_users = rng.choice(eligible, min(a.eval_users, len(eligible)), replace=False)
print(f"U={U} distinct_pairs={len(pairs)} users_with>=2_partners={len(eligible)} "
      f"users_with_0_conv={(np.bincount(actor, minlength=U)==0).sum()} eval_users={len(eval_users)}")

# hold out one random pair per eval user
holdout = {}
by_user = {}
for idx, (u, o) in enumerate(pairs):
    by_user.setdefault(u, []).append(idx)
mask = np.ones(len(pairs), bool)
for u in eval_users:
    idx = by_user[u][rng.integers(len(by_user[u]))]
    holdout[u] = pairs[idx, 1]
    mask[idx] = False
train = sp.csr_matrix((counts[mask].astype(np.float32), (pairs[mask, 0], pairs[mask, 1])), shape=(U, U))
print(f"train nnz={train.nnz} density={train.nnz/(U*U):.2e}")

N = 10
item_ok = disc.copy()  # only discoverable agents may be recommended


oracle_top = {}


def metrics(name, rank_fn, extra=""):
    """HR/NDCG against the held-out partner, plus spec §4's recall@10 against the truth list
    (oracle top-10 for that user), plus what share of the user's own cluster the top-10 hits."""
    hits, ndcg, truth_recall, same_cluster = 0, 0.0, 0.0, 0.0
    t = time.time()
    for u in eval_users:
        top = rank_fn(u)
        pos = np.flatnonzero(top == holdout[u])
        if len(pos):
            hits += 1
            ndcg += 1 / np.log2(pos[0] + 2)
        if u in oracle_top:
            truth_recall += len(set(top.tolist()) & oracle_top[u]) / N
        same_cluster += (primary[top] == primary[u]).mean()
    n = len(eval_users)
    print(f"{name:<22} HR@{N}={hits/n:.4f}  NDCG@{N}={ndcg/n:.4f}  recall@{N}_vs_truth={truth_recall/n:.4f}  "
          f"same_cluster={same_cluster/n:.3f}  ({time.time()-t:.1f}s){extra}", flush=True)


def topn(scores, u):
    s = scores.astype(np.float64, copy=True)
    s[~item_ok] = -np.inf
    s[u] = -np.inf
    s[train[u].indices] = -np.inf
    idx = np.argpartition(-s, N)[:N]
    return idx[np.argsort(-s[idx])]


# --- oracle (truth) -----------------------------------------------------------------------
for u in eval_users:
    oracle_top[u] = set(topn(affinity[primary[u]][primary] * pop, u).tolist())
metrics("oracle affinity*pop", lambda u: topn(affinity[primary[u]][primary] * pop, u))

# --- popularity ---------------------------------------------------------------------------
pop_train = np.asarray(train.sum(axis=0)).ravel()
metrics("popularity", lambda u: topn(pop_train, u))
metrics("random", lambda u: topn(rng.random(U), u))

# --- plan B: item-item cosine neighbours from co-occurrence -------------------------------
t = time.time()
Xn = train.copy()
Xn.data = np.ones_like(Xn.data)
col_norm = np.sqrt(np.asarray(Xn.sum(axis=0)).ravel())
inv = np.divide(1.0, col_norm, out=np.zeros_like(col_norm), where=col_norm > 0)
Xn = Xn @ sp.diags(inv)
S = (Xn.T @ Xn).tocsr()
S.setdiag(0)
S.eliminate_zeros()
build_s = time.time() - t
metrics("B item-cosine kNN", lambda u: topn(np.asarray((train[u] @ S).todense()).ravel(), u),
        extra=f"  build={build_s:.1f}s S.nnz={S.nnz}")
# raw co-occurrence counts (no normalisation): "people who talked to your agents also talked to"
Xb = train.copy(); Xb.data = np.ones_like(Xb.data)
C = (Xb.T @ Xb).tocsr(); C.setdiag(0); C.eliminate_zeros()
metrics("B item co-occur raw", lambda u: topn(np.asarray((Xb[u] @ C).todense()).ravel(), u))
# co-occurrence with popularity fallback: raw counts + small popularity term breaks the zero ties
cnt = np.asarray(Xb.sum(axis=0)).ravel()
metrics("B co-occur + pop tiebrk", lambda u: topn(np.asarray((Xb[u] @ C).todense()).ravel() + 1e-3 * cnt, u))

# --- plan A (library form): implicit ALS --------------------------------------------------
import implicit  # noqa: E402
from implicit.als import AlternatingLeastSquares  # noqa: E402

for factors, reg, alpha in [(a.factors, 0.05, 1.0), (16, 0.5, 1.0), (16, 0.5, 10.0), (64, 5.0, 10.0)]:
    rss0 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20
    t = time.time()
    model = AlternatingLeastSquares(factors=factors, regularization=reg, alpha=alpha, iterations=a.iters,
                                    use_gpu=False, random_state=0, calculate_training_loss=False)
    model.fit(train, show_progress=False)
    fit_s = time.time() - t
    rss1 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20
    metrics(f"A ALS f{factors} r{reg} a{alpha}", lambda u: topn(model.item_factors @ model.user_factors[u], u),
            extra=f"  fit={fit_s:.1f}s maxrss {rss0:.0f}->{rss1:.0f}MB")
print(f"implicit {implicit.__version__}")

# ALS + popularity hybrid (what the ranker would do): rank-normalised sum
def hybrid(u):
    s1 = model.item_factors @ model.user_factors[u]
    s1 = (s1 - s1.mean()) / (s1.std() + 1e-9)
    s2 = np.log1p(pop_train)
    s2 = (s2 - s2.mean()) / (s2.std() + 1e-9)
    return topn(s1 + s2, u)
metrics("A ALS + popularity", hybrid)

sys.stdout.flush()
