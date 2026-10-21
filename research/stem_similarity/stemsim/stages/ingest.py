"""Stage: dataset -> registry. Runs an adapter's fetch (raw files, maybe
network) then normalize (raw -> common model) and replaces that dataset's
rows in the registry. Safe to re-run; incremental datasets (Last.fm) grow."""

import logging

from ..datasets import get_adapter

logger = logging.getLogger(__name__)


def ingest(registry, name, fetch=True, adapter_options=None, **fetch_options):
    adapter = get_adapter(name, **(adapter_options or {}))
    if fetch:
        adapter.fetch(registry, **fetch_options)
    normalized = adapter.normalize(registry)
    registry.replace_dataset(adapter, normalized)
    logger.info("%s: %d tracks, %d judgments", name, len(normalized.members), len(normalized.judgments))
    return normalized
