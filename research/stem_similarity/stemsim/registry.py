"""SQLite registry shared by all stages.

WAL mode lets every stage read while one writes, so a network stage and a
GPU stage can run side by side. Stages coordinate only through this file:
each one asks for rows whose inputs are ready and whose own output is
missing (stage_status), does the work, and records the outcome.

Stage outcomes:
  done         output written (`artifact` points at it)
  failed       tried and failed; retried on the next run unless the cause is permanent
  unavailable  can't be done with what we have (e.g. no audio source yet)
"""

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from . import config
from .schema import NormalizedDataset

DONE, FAILED, UNAVAILABLE = "done", "failed", "unavailable"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS datasets (
    name TEXT PRIMARY KEY, target TEXT, metric TEXT, license TEXT, url TEXT,
    ingested_at REAL, n_tracks INTEGER, n_judgments INTEGER
);
CREATE TABLE IF NOT EXISTS tracks (
    track_id TEXT PRIMARY KEY, audio_source TEXT NOT NULL, audio_ref TEXT NOT NULL DEFAULT '',
    title TEXT, artist TEXT, meta TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS memberships (
    dataset TEXT NOT NULL, track_id TEXT NOT NULL, local_id TEXT, clip_start REAL, clip_end REAL,
    PRIMARY KEY (dataset, track_id)
);
CREATE TABLE IF NOT EXISTS judgments (
    id INTEGER PRIMARY KEY, dataset TEXT NOT NULL, kind TEXT NOT NULL,
    a TEXT NOT NULL, b TEXT NOT NULL, c TEXT, value REAL, weight REAL, grp TEXT
);
CREATE INDEX IF NOT EXISTS judgments_dataset ON judgments (dataset);
CREATE TABLE IF NOT EXISTS stage_status (
    track_id TEXT NOT NULL, stage TEXT NOT NULL, state TEXT NOT NULL,
    detail TEXT, artifact TEXT, updated_at REAL,
    PRIMARY KEY (track_id, stage)
);
"""


class Registry:
    def __init__(self, data_dir=None):
        self.data_dir = Path(data_dir or config.DATA_DIR)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.data_dir / config.DB_FILE, timeout=60)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(_SCHEMA)

    def raw_dir(self, dataset):
        path = self.data_dir / "raw" / dataset
        path.mkdir(parents=True, exist_ok=True)
        return path

    def audio_dir(self, source):
        path = self.data_dir / "audio" / source
        path.mkdir(parents=True, exist_ok=True)
        return path

    @contextmanager
    def transaction(self):
        with self.conn:
            yield self.conn

    # --- datasets -----------------------------------------------------------

    def replace_dataset(self, adapter, normalized: NormalizedDataset):
        """Writes an adapter's normalized output. Idempotent: the dataset's
        memberships and judgments are replaced wholesale. Tracks are shared,
        so they're merged - known fields are never overwritten with blanks."""
        with self.transaction() as db:
            db.executemany(
                """INSERT INTO tracks (track_id, audio_source, audio_ref, title, artist, meta)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT (track_id) DO UPDATE SET
                     audio_ref = CASE WHEN excluded.audio_ref != '' THEN excluded.audio_ref ELSE audio_ref END,
                     title = COALESCE(title, excluded.title),
                     artist = COALESCE(artist, excluded.artist),
                     meta = json_patch(excluded.meta, meta)""",
                [
                    (t.track_id, t.audio_source, t.audio_ref, t.title, t.artist, json.dumps(t.meta))
                    for t in normalized.tracks
                ],
            )
            db.execute("DELETE FROM memberships WHERE dataset = ?", (adapter.name,))
            db.executemany(
                "INSERT OR REPLACE INTO memberships VALUES (?, ?, ?, ?, ?)",
                [(adapter.name, m.track_id, m.local_id, m.clip_start, m.clip_end) for m in normalized.members],
            )
            db.execute("DELETE FROM judgments WHERE dataset = ?", (adapter.name,))
            db.executemany(
                "INSERT INTO judgments (dataset, kind, a, b, c, value, weight, grp) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [(adapter.name, j.kind, j.a, j.b, j.c, j.value, j.weight, j.group) for j in normalized.judgments],
            )
            db.execute(
                "INSERT OR REPLACE INTO datasets VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    adapter.name,
                    adapter.target,
                    adapter.metric,
                    adapter.license,
                    adapter.url,
                    time.time(),
                    len(normalized.members),
                    len(normalized.judgments),
                ),
            )

    def dataset_tracks(self, dataset):
        return self.conn.execute(
            "SELECT t.* FROM tracks t JOIN memberships m USING (track_id) WHERE m.dataset = ? ORDER BY t.track_id",
            (dataset,),
        ).fetchall()

    # --- stage bookkeeping --------------------------------------------------

    def pending(self, stage, audio_source=None, dataset=None, retry_failed=True, limit=None):
        """Tracks with no final outcome for `stage` yet."""
        final = (DONE, UNAVAILABLE) if retry_failed else (DONE, UNAVAILABLE, FAILED)
        placeholders = ",".join("?" * len(final))
        sql = f"""SELECT t.* FROM tracks t
                  WHERE NOT EXISTS (SELECT 1 FROM stage_status s WHERE s.track_id = t.track_id
                                    AND s.stage = ? AND s.state IN ({placeholders}))"""  # noqa: S608 - placeholders only
        args = [stage, *final]
        if audio_source:
            sql += " AND t.audio_source = ?"
            args.append(audio_source)
        if dataset:
            sql += " AND EXISTS (SELECT 1 FROM memberships m WHERE m.track_id = t.track_id AND m.dataset = ?)"
            args.append(dataset)
        sql += " ORDER BY t.track_id"
        if limit:
            sql += " LIMIT ?"
            args.append(limit)
        return self.conn.execute(sql, args).fetchall()

    def set_status(self, track_id, stage, state, detail=None, artifact=None):
        with self.transaction() as db:
            db.execute(
                "INSERT OR REPLACE INTO stage_status VALUES (?, ?, ?, ?, ?, ?)",
                (track_id, stage, state, detail, artifact, time.time()),
            )

    def summary(self):
        """Per dataset: tracks, judgments, and how far each stage has got."""
        return self.conn.execute(
            """SELECT d.name, d.target, d.metric, d.n_tracks, d.n_judgments,
                      SUM(s.state = 'done') AS audio_done, SUM(s.state = 'failed') AS audio_failed,
                      SUM(s.state = 'unavailable') AS audio_unavailable
               FROM datasets d
               JOIN memberships m ON m.dataset = d.name
               LEFT JOIN stage_status s ON s.track_id = m.track_id AND s.stage = 'audio'
               GROUP BY d.name ORDER BY d.name"""
        ).fetchall()
