"""Feature engineering for the song-similarity model.

Raw audio-feature columns come from the public TidyTuesday Spotify dataset
(see data/README.md). `key` is a pitch class (0-11) and is circular - key 11
(B) is musically adjacent to key 0 (C), so encoding it as a single ordinal
column makes a cosine/Euclidean model treat them as maximally distant
instead. It's encoded as (sin, cos) of its position on the 12-tone circle.

Feature sets are named variants rather than a fixed count - which columns
actually help is an empirical question, answered by evaluate.py.
"""
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

RAW_AUDIO_COLUMNS = [
    "danceability", "energy", "key", "loudness", "mode", "speechiness",
    "acousticness", "instrumentalness", "liveness", "valence", "tempo",
    "duration_ms",
]

FEATURE_VARIANTS = {
    "raw_key_with_duration": [
        "danceability", "energy", "key", "loudness", "mode", "speechiness",
        "acousticness", "instrumentalness", "liveness", "valence", "tempo",
        "duration_ms",
    ],
    "circular_key_with_duration": [
        "danceability", "energy", "key_sin", "key_cos", "loudness", "mode",
        "speechiness", "acousticness", "instrumentalness", "liveness",
        "valence", "tempo", "duration_ms",
    ],
    "circular_key_no_duration": [
        "danceability", "energy", "key_sin", "key_cos", "loudness", "mode",
        "speechiness", "acousticness", "instrumentalness", "liveness",
        "valence", "tempo",
    ],
    "raw_key_no_duration": [
        "danceability", "energy", "key", "loudness", "mode", "speechiness",
        "acousticness", "instrumentalness", "liveness", "valence", "tempo",
    ],
}

DEFAULT_VARIANT = "circular_key_with_duration"


def load_catalog(csv_path):
    """Load the raw playlist-track CSV and collapse it to one row per unique track.

    The source CSV is a playlist/track join table, so the same track can
    appear many times under different playlists (and occasionally different
    playlist_genre tags). Audio features are intrinsic to the track, so the
    first occurrence is kept; the genre label (used only for evaluation) is
    taken as the most frequent tag across that track's occurrences.
    """
    df = pd.read_csv(csv_path)
    df = df.dropna(subset=["track_name", "track_artist"])

    agg = {col: "first" for col in RAW_AUDIO_COLUMNS}
    agg["track_name"] = "first"
    agg["track_artist"] = "first"
    agg["playlist_genre"] = lambda s: s.mode().iat[0]

    catalog = df.groupby("track_id").agg(agg).reset_index()
    return catalog


def add_derived_columns(catalog):
    """Return a copy of `catalog` with the circular key encoding columns added."""
    catalog = catalog.copy()
    radians = catalog["key"].astype(float) * (2 * np.pi / 12)
    catalog["key_sin"] = np.sin(radians)
    catalog["key_cos"] = np.cos(radians)
    return catalog


def build_feature_matrix(catalog, variant=DEFAULT_VARIANT, scaler=None):
    """Build a standardized feature matrix for the given variant.

    If `scaler` is None, a new StandardScaler is fit on `catalog` and
    returned. Otherwise the provided (already-fit) scaler is reused, e.g.
    fit on a train split then applied to a held-out test split to avoid
    leaking test statistics into the normalization.
    """
    catalog = add_derived_columns(catalog)
    columns = FEATURE_VARIANTS[variant]
    raw = catalog[columns].to_numpy(dtype=float)

    if scaler is None:
        scaler = StandardScaler()
        X = scaler.fit_transform(raw)
    else:
        X = scaler.transform(raw)

    return X, scaler
