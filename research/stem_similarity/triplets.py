"""Builds the queue of ABX triplets the listener rates (plan section 3.4).

Triplet types:
  stem_disagree  A is among X's nearest neighbors by one stem, B by another.
                 The answer says which stem matters more - the most
                 informative type.
  near_far       A among X's nearest by the full mix, B random. Anchor.
  random         A and B random. Calibration against selection bias.
  stem_only      Played as isolated stems: A near X by that stem, B moderately
                 far. Measures each stem embedding's perceptual reliability.
  repeat         An earlier triplet again with A/B swapped - self-consistency.

Candidates never share X's artist (that would make it trivial), and a stem
that is silent in X (see SILENT_DB) is never used to pick neighbors.
"""

import json
import random

import numpy as np
import pandas as pd

SILENT_DB = -45.0  # stem RMS below this is treated as absent
TOP_K = 5  # "nearest neighbor" pool size
MID_RANKS = (15, 50)  # "moderately far" pool for stem_only B
MIX = {"stem_disagree": 0.45, "near_far": 0.25, "random": 0.15, "stem_only": 0.15}
REPEAT_FRACTION = 0.10
REPEAT_MIN_GAP = 20


def cosine_matrices(emb):
    """emb (n, stems, d) -> (stems, n, n) cosine similarity."""
    unit = emb / np.linalg.norm(emb, axis=-1, keepdims=True).clip(1e-9)
    return np.einsum("isd,jsd->sij", unit, unit)


def build_queue(songs, npz, n_triplets=400, seed=0):
    rng = random.Random(seed)
    stems = list(npz["stems"])
    ok = npz["ok"]
    sims = cosine_matrices(npz["emb_excerpt"])
    audible = npz["rms_excerpt"] > SILENT_DB  # (n, stems)
    artists = songs["track_artist"].str.lower().str.strip().to_numpy()
    valid = np.flatnonzero(ok)
    part_stems = [s for s in stems if s != "mix"]

    def ranked(x, stem):
        s = stems.index(stem)
        order = np.argsort(-sims[s, x])
        return [int(j) for j in order if j != x and ok[j] and artists[j] != artists[x] and audible[j, s]]

    def make(kind):
        x = int(rng.choice(valid))
        if kind == "stem_disagree":
            options = [s for s in part_stems if audible[x, stems.index(s)]]
            if len(options) < 2:
                return None
            s1, s2 = rng.sample(options, 2)
            a = rng.choice(ranked(x, s1)[:TOP_K])
            pool = [j for j in ranked(x, s2)[:TOP_K] if j != a]
            if not pool:
                return None
            return dict(kind=kind, x=x, a=a, b=rng.choice(pool), play="mix", stems=[s1, s2])
        if kind == "near_far":
            a = rng.choice(ranked(x, "mix")[:TOP_K])
            b = rng.choice([j for j in valid if j not in (x, a) and artists[j] != artists[x]])
            return dict(kind=kind, x=x, a=int(a), b=int(b), play="mix", stems=["mix"])
        if kind == "random":
            a, b = rng.sample([int(j) for j in valid if j != x and artists[j] != artists[x]], 2)
            return dict(kind=kind, x=x, a=a, b=b, play="mix", stems=[])
        if kind == "stem_only":
            options = [s for s in part_stems if audible[x, stems.index(s)]]
            stem = rng.choice(options)
            order = ranked(x, stem)
            a = rng.choice(order[:TOP_K])
            b = rng.choice(order[MID_RANKS[0] : MID_RANKS[1]])
            return dict(kind=kind, x=x, a=a, b=b, play=stem, stems=[stem])
        raise ValueError(kind)

    n_fresh = int(n_triplets * (1 - REPEAT_FRACTION))
    kinds = rng.choices(list(MIX), weights=list(MIX.values()), k=n_fresh)
    queue = []
    for kind in kinds:
        for _ in range(20):
            try:
                t = make(kind)
            except IndexError:  # a neighbor pool came up empty for this X
                t = None
            if t:
                break
        if t:
            if rng.random() < 0.5:  # A/B position carries no information
                t["a"], t["b"] = t["b"], t["a"]
                t["stems"] = t["stems"][::-1] if kind == "stem_disagree" else t["stems"]
                t["near"] = "b" if kind in ("near_far", "stem_only") else None
            else:
                t["near"] = "a" if kind in ("near_far", "stem_only") else None
            queue.append(t)

    for i, t in enumerate(queue):
        t["id"] = i
    n_repeats = n_triplets - len(queue)
    for k, source in enumerate(sorted(rng.sample(range(len(queue) - REPEAT_MIN_GAP), n_repeats))):
        orig = next(t for t in queue if t["id"] == source)
        rep = dict(
            orig,
            id=len(kinds) + k,
            kind="repeat",
            repeat_of=source,
            a=orig["b"],
            b=orig["a"],
            stems=orig["stems"][::-1],
            near={"a": "b", "b": "a"}.get(orig.get("near")),
        )
        pos = queue.index(orig)
        queue.insert(rng.randint(pos + REPEAT_MIN_GAP, len(queue)), rep)

    track_ids = songs["track_id"].tolist()
    for t in queue:
        for key in ("x", "a", "b"):
            t[key] = track_ids[t[key]]
    return queue


def write_queue(path, queue):
    with open(path, "w", encoding="utf-8") as f:
        for t in queue:
            f.write(json.dumps(t) + "\n")


def load_jsonl(path):
    try:
        with open(path, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
    except FileNotFoundError:
        return []


if __name__ == "__main__":
    from pathlib import Path

    here = Path(__file__).resolve().parent
    songs = pd.read_csv(here / "pilot_songs.csv")
    npz = np.load(here / "embeddings" / "pilot_embeddings.npz", allow_pickle=True)
    queue = build_queue(songs, npz)
    write_queue(here / "triplet_queue.jsonl", queue)
    print(pd.Series([t["kind"] for t in queue]).value_counts().to_string())
