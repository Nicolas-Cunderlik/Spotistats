"""Spotify service wrapper - lazy init and safe calls."""
import logging
import auth

logger = logging.getLogger(__name__)

class SpotifyService:
    def __init__(self):
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            try:
                self._client = auth.getSpotifyClient()
            except Exception:
                logger.exception("Failed to initialize Spotify client")
                self._client = None

    def current_playback(self):
        self._ensure_client()
        if not self._client:
            return None
        try:
            return self._client.current_playback()
        except Exception:
            logger.exception("Error fetching current playback")
            return None

    def playback_item(self):
        state = self.current_playback()
        if not state:
            return None
        return state.get('item')
