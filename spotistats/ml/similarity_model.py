"""Loads the artifacts produced by train.py and serves nearest-neighbor lookups.

Lookups are by Spotify track ID against the static training catalog - there is
no live feature extraction, since Spotify's audio-features endpoint is
restricted for this app. A track not present in the catalog has no vector to
query with, so callers should treat an empty result as "not enough data" and
not as "no similar tracks exist".

The catalog is deduplicated at training time (dedup.py). Lookups re-check
results with the same rules as a redundant guard, so a copy that slips through
is still never shown - but it's logged as a leak, since it means the training
dedup missed something and should be fixed there.
"""
import logging
import os
import joblib
import pandas as pd

from . import dedup

logger = logging.getLogger(__name__)

ARTIFACT_DIR = os.path.join(os.path.dirname(__file__), "artifacts")

# Extra neighbors fetched beyond k so the duplicate filter can drop some and
# still return k results. Leaks should be rare, so a small margin suffices.
DUPLICATE_MARGIN = 5


class SimilarityModel:
    def __init__(self, artifact_dir=ARTIFACT_DIR):
        self.index = joblib.load(os.path.join(artifact_dir, "index.joblib"))
        self.X = joblib.load(os.path.join(artifact_dir, "features.joblib"))
        meta = pd.read_csv(os.path.join(artifact_dir, "track_meta.csv"))
        self.track_ids = meta["track_id"].tolist()
        self.track_names = meta["track_name"].tolist()
        self.track_artists = meta["track_artist"].tolist()
        self._row_by_id = {track_id: i for i, track_id in enumerate(self.track_ids)}
        # Every copy of a deduplicated song resolves to its canonical row.
        # (Artifacts from before dedup have no alias column.)
        if "alias_track_ids" in meta:
            for i, aliases in enumerate(meta["alias_track_ids"]):
                for alias in str(aliases).split(";"):
                    self._row_by_id.setdefault(alias, i)

    def has_track(self, track_id):
        return track_id in self._row_by_id

    def find_similar(self, track_id, k=3):
        row = self._row_by_id.get(track_id)
        if row is None:
            return []

        n_neighbors = min(k + 1 + DUPLICATE_MARGIN, len(self.track_ids))
        distances, indices = self.index.kneighbors(self.X[row:row + 1], n_neighbors=n_neighbors)

        picked_rows = []
        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx == row:
                continue  # the query itself - expected, always its own nearest neighbor
            duplicate_of = next(
                (other for other in [row] + picked_rows if self._is_duplicate(idx, other)), None
            )
            if duplicate_of is not None:
                logger.warning(
                    "Dedup leak: '%s' by %s (%s) duplicates '%s' by %s (%s) - filtered at "
                    "lookup, but the training catalog should have merged them",
                    self.track_names[idx], self.track_artists[idx], self.track_ids[idx],
                    self.track_names[duplicate_of], self.track_artists[duplicate_of],
                    self.track_ids[duplicate_of],
                )
                continue
            picked_rows.append(idx)
            results.append({
                "track_id": self.track_ids[idx],
                "track_name": self.track_names[idx],
                "track_artist": self.track_artists[idx],
                "similarity": 1 - dist,
            })
            if len(results) == k:
                break
        return results

    def _is_duplicate(self, row_a, row_b):
        return dedup.is_duplicate(
            self.track_names[row_a], self.track_artists[row_a],
            self.track_names[row_b], self.track_artists[row_b],
            self.X[row_a], self.X[row_b],
        )
