"""The adapter contract. Adding a dataset = one subclass + one line in
datasets/__init__.py; nothing downstream changes.

  fetch(registry, **options)  Get the raw files into registry.raw_dir(name).
                              Dataset-specific, may use the network, may be
                              incremental (Last.fm crawls a little more each
                              run). Must be safe to re-run.
  normalize(registry)         Raw files -> NormalizedDataset (schema.py). Pure:
                              reads only raw_dir (plus the registry, for
                              datasets built on another's tracks), no network,
                              so it's unit-testable from fixture files.
"""

import time
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from typing import ClassVar

from .. import config
from ..schema import NormalizedDataset


class DatasetAdapter(ABC):
    name: ClassVar[str]
    target: ClassVar[str]  # schema.PERCEPTUAL / BEHAVIORAL / SEEDS
    metric: ClassVar[str | None]  # schema.TRIPLET_AGREEMENT / SPEARMAN / NDCG
    license: ClassVar[str]
    url: ClassVar[str]

    def fetch(self, registry, **options):  # noqa: B027 - datasets with no raw files skip it
        """Download raw files. Default: nothing to fetch."""

    @abstractmethod
    def normalize(self, registry) -> NormalizedDataset: ...


class RateLimiter:
    """At most `per_second` calls per second, spaced evenly."""

    def __init__(self, per_second):
        self.interval = 1.0 / per_second
        self._next = 0.0

    def wait(self):
        now = time.monotonic()
        if now < self._next:
            time.sleep(self._next - now)
        self._next = max(now, self._next) + self.interval


def http_get(url, params=None, limiter=None):
    """GET with the project user agent and timeout; returns the body bytes."""
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    if limiter:
        limiter.wait()
    request = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT})
    with urllib.request.urlopen(request, timeout=config.HTTP_TIMEOUT_S) as response:
        return response.read()


def download(url, path, chunk_bytes=1 << 20, progress=None):
    """Streams `url` to `path` via a .part file, resuming a partial .part with
    an HTTP Range request; no-op if `path` already exists. Safe for multi-GB files."""
    if path.exists():
        return path
    tmp = path.with_suffix(path.suffix + ".part")
    have = tmp.stat().st_size if tmp.exists() else 0
    headers = {"User-Agent": config.USER_AGENT}
    if have:
        headers["Range"] = f"bytes={have}-"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=config.HTTP_TIMEOUT_S) as response:
        resumed = response.status == 206
        total = int(response.headers.get("Content-Length", 0)) + (have if resumed else 0)
        with open(tmp, "ab" if resumed else "wb") as out:
            done = have if resumed else 0
            while chunk := response.read(chunk_bytes):
                out.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
    tmp.replace(path)
    return path
