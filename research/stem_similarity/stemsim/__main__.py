"""Command line for the pipeline. Run from research/stem_similarity with its venv:

  python -m stemsim datasets                         list adapters
  python -m stemsim ingest spotify_catalog           register the app's catalog (seeds)
  python -m stemsim ingest magnatagatune [--with-audio]
  python -m stemsim ingest ccmsim [--all-cultures]
  python -m stemsim ingest lastfm [--limit 500]      crawl 500 more seeds, then re-normalize
  python -m stemsim audio [--source deezer] [--dataset lastfm] [--limit 1000]
  python -m stemsim status                           per-dataset progress

Every command is safe to re-run and to run alongside the others.
"""

import argparse
import logging
import sys

from .datasets import ADAPTERS
from .registry import Registry
from .stages import audio, ingest

_last_reported = [0]


def _progress(done, total):
    """Prints download progress each time another 256 MB has arrived."""
    if done < _last_reported[0]:  # a new file started
        _last_reported[0] = 0
    if done - _last_reported[0] >= 256 << 20 or done == total:
        _last_reported[0] = done
        print(f"  {done / 1e9:.2f} / {total / 1e9:.2f} GB", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m stemsim", description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("datasets", help="list dataset adapters")
    p = commands.add_parser("ingest", help="fetch + normalize a dataset into the registry")
    p.add_argument("dataset", choices=sorted(ADAPTERS))
    p.add_argument("--no-fetch", action="store_true", help="re-normalize cached raw files only")
    p.add_argument("--with-audio", action="store_true", help="magnatagatune: also download the 3.3 GB audio")
    p.add_argument("--all-cultures", action="store_true", help="ccmsim: keep all nine source datasets")
    p.add_argument("--limit", type=int, default=200, help="lastfm: seeds to crawl this run")
    p = commands.add_parser("audio", help="fetch/extract audio for pending tracks")
    p.add_argument("--source")
    p.add_argument("--dataset")
    p.add_argument("--limit", type=int)
    commands.add_parser("status", help="per-dataset progress")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    registry = Registry()

    if args.command == "datasets":
        for name, adapter in ADAPTERS.items():
            print(f"{name:16s} {adapter.target:11s} {adapter.metric or '-':18s} {adapter.url}")
    elif args.command == "ingest":
        options = {"cultures": None} if args.all_cultures else {}
        ingest.ingest(
            registry,
            args.dataset,
            fetch=not args.no_fetch,
            adapter_options=options,
            with_audio=args.with_audio,
            limit=args.limit,
            progress=_progress,
        )
    elif args.command == "audio":
        print(audio.run(registry, source=args.source, dataset=args.dataset, limit=args.limit))
    elif args.command == "status":
        print(
            f"{'dataset':16s} {'target':11s} {'metric':18s} {'tracks':>7s} {'judgm.':>7s} "
            f"{'audio ok':>9s} {'failed':>7s} {'unavail.':>9s}"
        )
        for row in registry.summary():
            print(
                f"{row['name']:16s} {row['target']:11s} {row['metric'] or '-':18s} {row['n_tracks']:7d} "
                f"{row['n_judgments']:7d} {row['audio_done'] or 0:9d} {row['audio_failed'] or 0:7d} "
                f"{row['audio_unavailable'] or 0:9d}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
