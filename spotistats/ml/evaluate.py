"""Evaluation: holds out a stratified test split and measures how well kNN
retrieval recovers genre as a proxy for "are the neighbors actually similar".

Compares the named feature variants from features.py so feature selection is
driven by measured accuracy, not an assumed feature count.

Run: python -m spotistats.ml.evaluate
"""
import os
from collections import Counter

from sklearn.model_selection import train_test_split
from sklearn.neighbors import NearestNeighbors

from . import features

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
CSV_PATH = os.path.join(DATA_DIR, "spotify_songs.csv")

K_VALUES = (1, 3, 5)


def evaluate_variant(catalog, variant, k_values=K_VALUES, seed=42):
    train_df, test_df = train_test_split(
        catalog, test_size=0.2, random_state=seed, stratify=catalog["playlist_genre"]
    )

    X_train, scaler = features.build_feature_matrix(train_df, variant=variant)
    X_test, _ = features.build_feature_matrix(test_df, variant=variant, scaler=scaler)

    max_k = max(k_values)
    nn = NearestNeighbors(n_neighbors=max_k, metric="cosine")
    nn.fit(X_train)

    train_genres = train_df["playlist_genre"].to_numpy()
    test_genres = test_df["playlist_genre"].to_numpy()

    _, indices = nn.kneighbors(X_test)

    results = {}
    for k in k_values:
        correct = 0
        for i, neighbor_idx in enumerate(indices[:, :k]):
            predicted = Counter(train_genres[neighbor_idx]).most_common(1)[0][0]
            if predicted == test_genres[i]:
                correct += 1
        results[k] = correct / len(test_df)
    return results


def main():
    catalog = features.load_catalog(CSV_PATH)
    print(f"Catalog: {len(catalog)} unique tracks across {catalog['playlist_genre'].nunique()} genres")
    print(f"Genre baseline (always predict most common genre): "
          f"{catalog['playlist_genre'].value_counts(normalize=True).iloc[0]:.3f}\n")

    for variant in features.FEATURE_VARIANTS:
        results = evaluate_variant(catalog, variant)
        scores = ", ".join(f"top-{k}={acc:.3f}" for k, acc in results.items())
        print(f"{variant:30s} {scores}")


if __name__ == "__main__":
    main()
