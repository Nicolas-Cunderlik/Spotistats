"""Configure structured logging for the application."""
import logging
from logging import StreamHandler, FileHandler, Formatter
from .. import config

def configure_logging():
    root = logging.getLogger()
    if root.handlers:
        return  # already configured

    root.setLevel(logging.DEBUG)

    fmt = Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    ch = StreamHandler()
    ch.setLevel(logging.DEBUG)
    ch.setFormatter(fmt)
    root.addHandler(ch)

    fh = FileHandler(config.LOG_FILE)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    root.addHandler(fh)

    # Third-party DEBUG output is noisy; spotipy/urllib3's includes the client secret (Basic auth
    # header) and refresh tokens - never let those reach the log.
    for name in ("spotipy", "urllib3", "openai", "httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.INFO)

# Auto-configure on import for convenience
configure_logging()
