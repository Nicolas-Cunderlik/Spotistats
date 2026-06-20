"""Fetches the public Spotify audio-features dataset used to train the
song-similarity model.

Source: the #TidyTuesday project's "Spotify Songs" dataset (2020-01-21),
originally pulled from Spotify's audio-features endpoint via the spotifyr
package by Kaylin Pavlik. ~28k unique tracks across 6 genres, CC0-licensed.
https://github.com/rfordatascience/tidytuesday/tree/master/data/2020/2020-01-21

Run: python -m spotistats.ml.data.download_dataset
"""
import os
import requests

URL = "https://raw.githubusercontent.com/rfordatascience/tidytuesday/master/data/2020/2020-01-21/spotify_songs.csv"
OUT_PATH = os.path.join(os.path.dirname(__file__), "spotify_songs.csv")


def download():
    resp = requests.get(URL, timeout=30)
    resp.raise_for_status()
    with open(OUT_PATH, "wb") as f:
        f.write(resp.content)
    print(f"Saved dataset to {OUT_PATH} ({len(resp.content)} bytes)")


if __name__ == "__main__":
    download()
