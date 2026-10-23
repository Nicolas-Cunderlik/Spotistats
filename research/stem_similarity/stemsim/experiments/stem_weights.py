"""Experiment: do per-stem similarities, weighted by human judgments, agree
with people more than the mix alone - or the app's current model?

    python -m stemsim.experiments.stem_weights [--run-name NAME] [--l2 1.0] [--folds 5]

Read-only: uses the registry and embeddings, writes only an MLflow run.

Setup
- Fit sets (k-fold CV): dim_sim, magnatagatune. Folds are grouped by the
  triple of songs, so MagnaTagATune's two orderings of one triple never
  straddle a fold. Every fit-set triplet is scored out-of-fold.
- Held out entirely (never fitted on): listener_abx - overall and per-stem
  facets - and ccmsim (pairs, Spearman). The final weights are fit on all
  fit-set data and applied to these.
- Each song is embedded on the window its dataset's raters heard (membership
  clip) when there is one, else the full audio.
- Per channel (mix, drums, bass, vocals, other): cosine similarity, z-scored
  per channel over random audible pairs so channels share a scale. Silence
  gating: a stem silent in exactly one song scores -1 (one has bass, the other
  doesn't); silent in both scores 0 (no evidence either way).
- A triplet (anchor a, positive b, negative c) becomes d = zsim(a,b) - zsim(a,c)
  per channel; a model agrees when its score w.d > 0 (ties count half).
- Weights: non-negative logistic regression, L2, no intercept.

Baselines: random (0.5), mix only, equal weights, each stem alone, and the
app's current model (Spotify features + genre embedding) - on listener_abx
only, the one dataset whose songs have Spotify features.
"""

import argparse
import json
import logging

import mlflow
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import spearmanr
from sklearn.model_selection import GroupKFold

from .. import tracking
from ..registry import Registry
from ..stages.embed import STAGE as EMBED_STAGE

logger = logging.getLogger(__name__)

CHANNELS = ("mix", "drums", "bass", "vocals", "other")
SILENT_DB = -45.0
FIT_SETS = ("dim_sim", "magnatagatune")
HELD_OUT_TRIPLETS = ("listener_abx",)
HELD_OUT_PAIRS = ("ccmsim",)
Z_SAMPLE_PAIRS = 20_000
BOOTSTRAP = 2_000
SEED = 0


class Vectors:
    """Unit-normalized embeddings + audibility per (track, window), loaded lazily."""

    def __init__(self, registry):
        self.registry = registry
        self._files = {}

    def get(self, track_id, window=None):
        if track_id not in self._files:
            out = self.registry.output(track_id, EMBED_STAGE)
            self._files[track_id] = None if out is None else dict(np.load(out[0]))
        data = self._files[track_id]
        if data is None:
            return None
        index = 0  # full audio
        if window is not None:
            for k, (start, _end) in enumerate(data["windows"]):
                if k and abs(start - window[0]) < 0.05:
                    index = k
        emb = data["emb"][index]
        emb = emb / np.linalg.norm(emb, axis=1, keepdims=True).clip(1e-9)
        return emb, data["rms_db"][index] > SILENT_DB


def channel_stats(vectors, rng):
    """Mean/std of cosine per channel over random pairs of audible channels."""
    loaded = [v for v in (vectors.get(t) for t in list(vectors._files)) if v is not None]
    i, j = rng.integers(0, len(loaded), (2, Z_SAMPLE_PAIRS))
    mean, std = np.zeros(len(CHANNELS)), np.ones(len(CHANNELS))
    for c in range(len(CHANNELS)):
        sims = [
            float(loaded[x][0][c] @ loaded[y][0][c])
            for x, y in zip(i, j, strict=True)
            if x != y and loaded[x][1][c] and loaded[y][1][c]
        ]
        mean[c], std[c] = np.mean(sims), np.std(sims) + 1e-9
    return mean, std


def zsim(x, y, mean, std):
    (ex, ax), (ey, ay) = x, y
    z = (np.einsum("cd,cd->c", ex, ey) - mean) / std
    return np.where(ax & ay, z, np.where(ax ^ ay, -1.0, 0.0))


def load_judgments(registry, dataset):
    windows = {
        row["track_id"]: (row["clip_start"], row["clip_end"])
        for row in registry.conn.execute(
            "SELECT track_id, clip_start, clip_end FROM memberships WHERE dataset = ? AND clip_start IS NOT NULL",
            (dataset,),
        )
    }
    rows = registry.conn.execute(
        "SELECT kind, a, b, c, value, weight, facet, meta FROM judgments WHERE dataset = ?", (dataset,)
    ).fetchall()
    return rows, windows


def features(vectors, rows, windows, stats):
    """Triplet rows -> (D, kept rows). Rows missing any embedding are dropped."""
    D, kept = [], []
    for row in rows:
        vs = [vectors.get(t, windows.get(t)) for t in (row["a"], row["b"], row["c"])]
        if any(v is None for v in vs):
            continue
        D.append(zsim(vs[0], vs[1], *stats) - zsim(vs[0], vs[2], *stats))
        kept.append(row)
    return np.array(D).reshape(-1, len(CHANNELS)), kept


def fit_weights(D, l2):
    """Non-negative w maximizing mean log sigmoid(D.w) - every row is oriented
    so the human-chosen song is the positive."""

    def loss(w):
        m = D @ w
        return np.logaddexp(0, -m).mean() + l2 * (w @ w) / len(D)

    def grad(w):
        m = D @ w
        return -(D * (1 / (1 + np.exp(m)))[:, None]).mean(0) + 2 * l2 * w / len(D)

    return minimize(loss, np.full(D.shape[1], 0.2), jac=grad, method="L-BFGS-B", bounds=[(0, None)] * D.shape[1]).x


def agreement(scores):
    return float(np.mean((scores > 0) + 0.5 * (scores == 0)))


def bootstrap_ci(scores, rng):
    values = [agreement(rng.choice(scores, len(scores))) for _ in range(BOOTSTRAP)]
    return np.percentile(values, [2.5, 97.5])


def fixed_models(D):
    out = {"mix only": D[:, 0], "equal weights": D.mean(1)}
    out.update({f"{c} only": D[:, k] for k, c in enumerate(CHANNELS) if c != "mix"})
    return out


def app_model_scores(rows):
    """Current app similarity (Spotify features + genre embedding) for pilot tracks."""
    from spotistats.ml.similarity_model import SimilarityModel

    model = SimilarityModel()
    Z = model.Z / np.linalg.norm(model.Z, axis=1, keepdims=True)
    scores = []
    for row in rows:
        ids = [model._row_by_id.get(t.split(":", 1)[1]) for t in (row["a"], row["b"], row["c"])]
        scores.append(np.nan if None in ids else float(Z[ids[0]] @ Z[ids[1]] - Z[ids[0]] @ Z[ids[2]]))
    return np.array(scores)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--run-name", default="stem-weights")
    parser.add_argument("--l2", type=float, default=1.0)
    parser.add_argument("--folds", type=int, default=5)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    registry = Registry()
    rng = np.random.default_rng(SEED)
    vectors = Vectors(registry)
    data = {name: load_judgments(registry, name) for name in (*FIT_SETS, *HELD_OUT_TRIPLETS, *HELD_OUT_PAIRS)}
    for rows, windows in data.values():  # load every needed vector first, so z-stats see them all
        for row in rows:
            for t in (row["a"], row["b"], row["c"]):
                if t:
                    vectors.get(t, windows.get(t))
    stats = channel_stats(vectors, rng)

    results = []  # (dataset, subset, model, n, agreement, lo, hi)

    # --- fit sets: out-of-fold scores
    fit_D, fit_rows, fit_names = [], [], []
    for name in FIT_SETS:
        rows, windows = data[name]
        D, kept = features(vectors, [r for r in rows if r["kind"] == "triplet"], windows, stats)
        fit_D.append(D)
        fit_rows += kept
        fit_names += [name] * len(kept)
        logger.info("%s: %d of %d triplets have all three songs embedded", name, len(kept), len(rows))
    D = np.vstack(fit_D)
    names = np.array(fit_names)
    # Stable group ids (Python's hash() is randomized per process, which would reshuffle folds)
    groups = pd.factorize(pd.Series(["|".join(sorted((r["a"], r["b"], r["c"]))) for r in fit_rows]))[0]
    oof = np.zeros(len(D))
    fold_weights = []
    for train, test in GroupKFold(n_splits=args.folds).split(D, groups=groups):
        w = fit_weights(D[train], args.l2)
        fold_weights.append(w)
        oof[test] = D[test] @ w
    clean = np.array([json.loads(r["meta"]).get("clean", False) for r in fit_rows])
    for name in FIT_SETS:
        for subset, mask in (("all", names == name), ("clean", (names == name) & clean)):
            if subset == "clean" and name != "dim_sim":
                continue
            scored = {"fitted (out-of-fold)": oof[mask], **fixed_models(D[mask])}
            for model, s in scored.items():
                results.append((name, subset, model, int(mask.sum()), agreement(s), np.nan, np.nan))

    # --- final weights, applied to held-out sets
    w_final = fit_weights(D, args.l2)
    for name in HELD_OUT_TRIPLETS:
        rows, windows = data[name]
        H, kept = features(vectors, rows, windows, stats)
        facets = np.array([r["facet"] for r in kept])
        app = app_model_scores(kept)
        for facet in sorted(set(facets)):
            mask = facets == facet
            scored = {"fitted": H[mask] @ w_final, **fixed_models(H[mask])}
            if facet == "overall":
                scored["app model (current)"] = app[mask][~np.isnan(app[mask])]
            for model, s in scored.items():
                lo, hi = bootstrap_ci(s, rng) if len(s) else (np.nan, np.nan)
                results.append((name, facet, model, len(s), agreement(s) if len(s) else np.nan, lo, hi))
    for name in HELD_OUT_PAIRS:
        rows, windows = data[name]
        pairs = [
            (vectors.get(r["a"], windows.get(r["a"])), vectors.get(r["b"], windows.get(r["b"])), r["value"])
            for r in rows
            if r["kind"] == "pair"
        ]
        pairs = [(x, y, v) for x, y, v in pairs if x is not None and y is not None]
        if len(pairs) >= 3:
            S = np.array([zsim(x, y, *stats) for x, y, _ in pairs])
            human = np.array([v for _, _, v in pairs])
            for model, s in {"fitted": S @ w_final, "mix only": S[:, 0], "equal weights": S.mean(1)}.items():
                results.append(
                    (name, "pairs (spearman)", model, len(pairs), float(spearmanr(s, human)[0]), np.nan, np.nan)
                )

    table = pd.DataFrame(results, columns=["dataset", "subset", "model", "n", "agreement", "ci_low", "ci_high"])
    weights = {
        "final": dict(zip(CHANNELS, map(float, w_final), strict=True)),
        "fold_mean": dict(zip(CHANNELS, map(float, np.mean(fold_weights, 0)), strict=True)),
        "fold_std": dict(zip(CHANNELS, map(float, np.std(fold_weights, 0)), strict=True)),
        "z_mean": dict(zip(CHANNELS, map(float, stats[0]), strict=True)),
        "z_std": dict(zip(CHANNELS, map(float, stats[1]), strict=True)),
    }

    params = {
        "l2": args.l2,
        "folds": args.folds,
        "silent_db": SILENT_DB,
        "embedding": EMBED_STAGE,
        "fit_sets": ",".join(FIT_SETS),
        "held_out": ",".join((*HELD_OUT_TRIPLETS, *HELD_OUT_PAIRS)),
    }
    with tracking.run("stem-weights", args.run_name, registry, EMBED_STAGE, params):
        for row in table.itertuples():
            key = f"{row.dataset}.{row.subset}.{row.model}".replace(" ", "_").replace("(", "").replace(")", "")
            if not np.isnan(row.agreement):
                mlflow.log_metric(key, row.agreement)
        for channel, value in weights["final"].items():
            mlflow.log_metric(f"weight.{channel}", value)
        mlflow.log_text(table.to_csv(index=False), "results.csv")
        mlflow.log_dict(weights, "weights.json")

    pd.set_option("display.width", 160)
    print(table.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    print("\nweights (final):", {k: round(v, 3) for k, v in weights["final"].items()})
    print(
        "weights (fold mean ± std):",
        {c: f"{weights['fold_mean'][c]:.2f}±{weights['fold_std'][c]:.2f}" for c in CHANNELS},
    )


if __name__ == "__main__":
    main()
