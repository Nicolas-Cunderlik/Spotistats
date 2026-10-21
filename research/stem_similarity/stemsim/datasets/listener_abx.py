"""The project author's own ABX ratings (rate_server.py -> ratings.jsonl).

A music producer's judgments: X/A/B 10 s excerpts, "which sounds more like
X?", with reason tags and free-text notes ("same sort of bass", "similar
thumpy kick"). Few, but the only judgments here that are per-stem, explained,
and from someone who listens for sound selection rather than genre.

Normalization:
  - choice a -> triplet (X, A, B); choice b -> (X, B, A). "Can't tell" is
    skipped (in practice it also flagged unusable clips, e.g. dialogue only).
  - facet: "overall" for full-mix triplets; the stem's name ("drums",
    "bass", ...) for isolated-stem ones.
  - meta: reason tags, the note, the triplet's design type and timing, kept
    for analysis (e.g. turning notes into per-stem judgments later).

Tracks are what the listener actually heard: the pilot's Deezer previews
(audio/<spotify id>.mp3), seconds 10-20. Some pilot matches were a different
version than the catalog song (e.g. a remix) - the judgment is still valid for
the audio heard, so those tracks stay separate ("pilot:" ids) and are only
linked to the catalog song in meta, flagged when the version differs.
"""

import csv
import json
import shutil

from .. import config
from ..schema import (
    OVERALL,
    PERCEPTUAL,
    TRIPLET,
    TRIPLET_AGREEMENT,
    Judgment,
    Membership,
    NormalizedDataset,
    Track,
    song_track_id,
)
from .base import DatasetAdapter

RATINGS = "ratings.jsonl"
PILOT_SONGS = "pilot_songs.csv"
EXCERPT = (10.0, 20.0)  # embed_stems.EXCERPT - the window rate_server played


class ListenerAbx(DatasetAdapter):
    name = "listener_abx"
    target = PERCEPTUAL
    metric = TRIPLET_AGREEMENT
    license = "Project author's own ratings"
    url = "research/stem_similarity/rate_server.py"

    def fetch(self, registry, **_):
        """Snapshots the live ratings file, so normalize reads only raw_dir."""
        raw = registry.raw_dir(self.name)
        for name in (RATINGS, PILOT_SONGS):
            shutil.copyfile(config.ROOT / name, raw / name)

    def normalize(self, registry):
        from ..stages.audio import same_recording  # stages import datasets; avoid a cycle at import time

        raw = registry.raw_dir(self.name)
        with open(raw / PILOT_SONGS, newline="", encoding="utf-8") as f:
            songs = {row["track_id"]: row for row in csv.DictReader(f)}
        with open(raw / RATINGS, encoding="utf-8") as f:
            ratings = [json.loads(line) for line in f if line.strip()]

        out = NormalizedDataset()
        heard = set()
        for r in ratings:
            if r["choice"] not in ("a", "b"):
                continue
            closer, farther = (r["a"], r["b"]) if r["choice"] == "a" else (r["b"], r["a"])
            out.judgments.append(
                Judgment(
                    TRIPLET,
                    f"pilot:{r['x']}",
                    f"pilot:{closer}",
                    f"pilot:{farther}",
                    facet=OVERALL if r["play"] == "mix" else r["play"],
                    meta={
                        "reasons": r.get("tags", []),
                        "note": r.get("note", ""),
                        "design": r["kind"],
                        "rating_id": r["id"],
                        "rated_at": r.get("rated_at"),
                        "listen_ms": r.get("listen_ms"),
                    },
                )
            )
            heard |= {r["x"], r["a"], r["b"]}

        for spotify_id in sorted(heard):
            song = songs[spotify_id]
            out.tracks.append(
                Track(
                    f"pilot:{spotify_id}",
                    "pilot",
                    audio_ref=f"audio/{spotify_id}.mp3",
                    title=song["track_name"],
                    artist=song["track_artist"],
                    meta={
                        "catalog_track": song_track_id(song["track_name"], song["track_artist"]),
                        "deezer_title": song["deezer_title"],
                        "version_differs": not same_recording(song["track_name"], song["deezer_title"]),
                    },
                )
            )
            out.members.append(Membership(f"pilot:{spotify_id}", spotify_id, *EXCERPT))
        return out
