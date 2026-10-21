"""Dataset adapters, by name. To add a dataset: subclass DatasetAdapter in a
new module here (see base.py for the contract) and register it below."""

from .ccmsim import CCMSim
from .lastfm import LastFm
from .magnatagatune import MagnaTagATune
from .spotify_catalog import SpotifyCatalog

ADAPTERS = {adapter.name: adapter for adapter in (SpotifyCatalog, MagnaTagATune, CCMSim, LastFm)}


def get_adapter(name, **options):
    try:
        return ADAPTERS[name](**options)
    except KeyError:
        raise SystemExit(f"Unknown dataset {name!r}; known: {', '.join(ADAPTERS)}") from None
