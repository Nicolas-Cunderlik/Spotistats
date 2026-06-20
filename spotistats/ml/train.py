"""Offline training: builds the song-similarity NearestNeighbors index over the
full track catalog and persists it for the live app to load.

Run: python -m spotistats.ml.train
"""
import os
import joblib
from sklearn.neighbors import NearestNeighbors

from . import features

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
ARTIFACT_DIR = os.path.join(os.path.dirname(__file__), "artifacts")
CSV_PATH = os.path.join(DATA_DIR, "spotify_songs.csv")

N_NEIGHBORS = 4  # 3 similar tracks + the query track itself, which is always its own nearest neighbor


def train(variant=features.DEFAULT_VARIANT):
    catalog = features.load_catalog(CSV_PATH)
    X, scaler = features.build_feature_matrix(catalog, variant=variant)

    index = NearestNeighbors(n_neighbors=N_NEIGHBORS, metric="cosine")
    index.fit(X)

    os.makedirs(ARTIFACT_DIR, exist_ok=True)
    joblib.dump(scaler, os.path.join(ARTIFACT_DIR, "scaler.joblib"))
    joblib.dump(index, os.path.join(ARTIFACT_DIR, "index.joblib"))
    joblib.dump(X, os.path.join(ARTIFACT_DIR, "features.joblib"))
    joblib.dump(variant, os.path.join(ARTIFACT_DIR, "variant.joblib"))
    catalog[["track_id", "track_name", "track_artist"]].to_csv(
        os.path.join(ARTIFACT_DIR, "track_meta.csv"), index=False
    )

    print(f"Trained on {len(catalog)} unique tracks using variant '{variant}'")
    print(f"Artifacts written to {ARTIFACT_DIR}")


if __name__ == "__main__":
    train()
