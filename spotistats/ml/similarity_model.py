"""Loads the artifacts produced by train.py and serves nearest-neighbor lookups.

Lookups are by Spotify track ID against the static training catalog - there is
no live feature extraction, since Spotify's audio-features endpoint is
restricted for this app. A track not present in the catalog has no vector to
query with, so callers should treat an empty result as "not enough data" and
not as "no similar tracks exist".
"""
import os
import joblib
import pandas as pd

ARTIFACT_DIR = os.path.join(os.path.dirname(__file__), "artifacts")


class SimilarityModel:
    def __init__(self, artifact_dir=ARTIFACT_DIR):
        self.index = joblib.load(os.path.join(artifact_dir, "index.joblib"))
        self.X = joblib.load(os.path.join(artifact_dir, "features.joblib"))
        meta = pd.read_csv(os.path.join(artifact_dir, "track_meta.csv"))
        self.track_ids = meta["track_id"].tolist()
        self.track_names = meta["track_name"].tolist()
        self.track_artists = meta["track_artist"].tolist()
        self._row_by_id = {track_id: i for i, track_id in enumerate(self.track_ids)}

    def has_track(self, track_id):
        return track_id in self._row_by_id

    def find_similar(self, track_id, k=3):
        row = self._row_by_id.get(track_id)
        if row is None:
            return []

        distances, indices = self.index.kneighbors(self.X[row:row + 1], n_neighbors=k + 1)

        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if self.track_ids[idx] == track_id:
                continue
            results.append({
                "track_id": self.track_ids[idx],
                "track_name": self.track_names[idx],
                "track_artist": self.track_artists[idx],
                "similarity": 1 - dist,
            })
            if len(results) == k:
                break
        return results
