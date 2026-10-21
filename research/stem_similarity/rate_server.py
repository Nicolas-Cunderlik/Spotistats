"""Local ABX rating app (plan section 3). Serves rate.html, the excerpt clips
and the triplet queue; appends every answer to ratings.jsonl.

Song names stay hidden while rating (knowing the artist biases the answer)
and are revealed for the previous triplet after it's submitted.

Run: research/stem_similarity/.venv/Scripts/python research/stem_similarity/rate_server.py
Then open http://localhost:8765
"""

import json
import mimetypes
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np
import pandas as pd
import triplets

HERE = Path(__file__).resolve().parent
CLIP_DIR = HERE / "audio" / "clips"
QUEUE_PATH = HERE / "triplet_queue.jsonl"
RATINGS_PATH = HERE / "ratings.jsonl"
PORT = 8765

songs = pd.read_csv(HERE / "pilot_songs.csv").set_index("track_id")
if not QUEUE_PATH.exists():
    npz = np.load(HERE / "embeddings" / "pilot_embeddings.npz", allow_pickle=True)
    triplets.write_queue(QUEUE_PATH, triplets.build_queue(songs.reset_index(), npz))
queue = triplets.load_jsonl(QUEUE_PATH)


def song_info(track_id):
    s = songs.loc[track_id]
    return {
        "name": s.track_name,
        "artist": s.track_artist,
        "year": None if pd.isna(s.release_year) else int(s.release_year),
    }


def next_triplet():
    done = {r["id"] for r in triplets.load_jsonl(RATINGS_PATH)}
    remaining = [t for t in queue if t["id"] not in done]
    if not remaining:
        return {"done": True, "rated": len(done), "total": len(queue)}
    t = remaining[0]
    clip = lambda tid: f"/clips/{tid}_{t['play']}.ogg"  # noqa: E731
    return {
        "id": t["id"],
        "play": t["play"],
        "rated": len(done),
        "total": len(queue),
        "clips": {"x": clip(t["x"]), "a": clip(t["a"]), "b": clip(t["b"])},
    }


def stats():
    ratings = {r["id"]: r for r in triplets.load_jsonl(RATINGS_PATH)}
    by_id = {t["id"]: t for t in queue}
    pairs = [
        (r, ratings.get(by_id[r["id"]]["repeat_of"])) for r in ratings.values() if by_id[r["id"]]["kind"] == "repeat"
    ]
    # A repeat swaps A/B, so a consistent answer flips the letter
    flip = {"a": "b", "b": "a", "tie": "tie"}
    pairs = [(r, o) for r, o in pairs if o]
    consistent = sum(flip[o["choice"]] == r["choice"] for r, o in pairs)
    return {"rated": len(ratings), "repeats_checked": len(pairs), "consistent": consistent}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, body, ctype="application/json", status=200):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            return self._send((HERE / "rate.html").read_bytes(), "text/html; charset=utf-8")
        if self.path == "/api/next":
            return self._send(next_triplet())
        if self.path == "/api/stats":
            return self._send(stats())
        if self.path.startswith("/clips/"):
            path = (CLIP_DIR / Path(self.path).name).resolve()
            if path.parent == CLIP_DIR.resolve() and path.exists():
                return self._send(path.read_bytes(), mimetypes.guess_type(path.name)[0] or "audio/ogg")
        self._send({"error": "not found"}, status=404)

    def do_POST(self):
        if self.path != "/api/rate":
            return self._send({"error": "not found"}, status=404)
        data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        t = next(t for t in queue if t["id"] == data["id"])
        if data["choice"] not in ("a", "b", "tie"):
            return self._send({"error": "bad choice"}, status=400)
        record = {
            "id": t["id"],
            "kind": t["kind"],
            "x": t["x"],
            "a": t["a"],
            "b": t["b"],
            "play": t["play"],
            "stems": t["stems"],
            "near": t.get("near"),
            "choice": data["choice"],
            "tags": data.get("tags", []),
            "note": data.get("note", ""),
            "listen_ms": data.get("listen_ms"),
            "switches": data.get("switches"),
            "rated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        with open(RATINGS_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
        reveal = {k: song_info(t[k]) for k in ("x", "a", "b")}
        self._send({"ok": True, "reveal": reveal, "choice": data["choice"]})


if __name__ == "__main__":
    print(f"Rating app on http://localhost:{PORT}  ({len(queue)} triplets in queue)")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
