"""Pilot step 5: sanity checks on the stem embeddings before any rating.

  - silent-stem rate per stem (how often gating kicks in)
  - hubness: skewness of the k-occurrence distribution (how often each song
    appears in others' top-k). Near 0 is healthy; strongly positive means a
    few "hub" songs are everyone's neighbor
  - mix vs stem agreement: how much the stems' neighbor lists overlap the
    mix's (if every stem agreed with the mix, stems would add nothing)
  - a few neighbor lists to listen to

Run: research/stem_similarity/.venv/Scripts/python research/stem_similarity/sanity.py
"""

from pathlib import Path

import numpy as np
import pandas as pd
import triplets
from scipy.stats import skew

HERE = Path(__file__).resolve().parent
K = 5


def top_k(sim, k=K):
    sim = sim.copy()
    np.fill_diagonal(sim, -np.inf)
    return np.argsort(-sim, axis=1)[:, :k]


def main():
    songs = pd.read_csv(HERE / "pilot_songs.csv")
    npz = np.load(HERE / "embeddings" / "pilot_embeddings.npz", allow_pickle=True)
    stems = list(npz["stems"])
    ok = npz["ok"]
    print(f"{ok.sum()}/{len(ok)} songs embedded\n")
    emb, rms = npz["emb_excerpt"][ok], npz["rms_excerpt"][ok]
    songs = songs[ok].reset_index(drop=True)
    audible = rms > triplets.SILENT_DB
    sims = triplets.cosine_matrices(emb)

    print(f"{'stem':8s} {'silent':>7s} {'median dB':>10s} {'hub skew':>9s} {'max k-occ':>10s} {'overlap w/ mix':>15s}")
    mix_nn = top_k(sims[0])
    for s, name in enumerate(stems):
        nn = top_k(np.where(audible[:, s][None, :], sims[s], -np.inf) if s else sims[s])
        k_occ = np.bincount(nn.ravel(), minlength=len(songs))
        overlap = np.mean([len(set(a) & set(b)) / K for a, b in zip(nn, mix_nn, strict=True)])
        print(
            f"{name:8s} {1 - audible[:, s].mean():7.1%} {np.median(rms[:, s]):10.1f} "
            f"{skew(k_occ):9.2f} {k_occ.max():10d} {overlap:15.1%}"
        )

    label = songs.track_name.str.slice(0, 32) + " - " + songs.track_artist.str.slice(0, 20)
    rng = np.random.default_rng(1)
    for i in rng.choice(len(songs), 3, replace=False):
        print(f"\nX = {label[i]}  [{songs.playlist_subgenre[i]}]")
        for s, name in enumerate(stems):
            if not audible[i, s]:
                print(f"  {name:7s} (silent)")
                continue
            nn = top_k(sims[s], 3)[i]
            print(f"  {name:7s} " + " | ".join(label[j] for j in nn))


if __name__ == "__main__":
    main()
