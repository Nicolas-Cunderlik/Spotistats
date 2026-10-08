"""Spotify service wrapper - lazy init and safe calls."""
import logging
import os
import auth
from spotipy.oauth2 import SpotifyOauthError

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
        except SpotifyOauthError as e:
            if e.error == 'invalid_grant':
                # Refresh token expired/revoked: retrying the cached token will
                # never succeed. Drop it so the next poll re-runs the login flow.
                logger.warning("Spotify refresh token rejected (%s); clearing cached token", e.error_description)
                self._reset_auth()
            else:
                logger.exception("Spotify auth error")
            return None
        except Exception:
            logger.exception("Error fetching current playback")
            return None

    def _reset_auth(self):
        cache_path = getattr(self._client.auth_manager.cache_handler, 'cache_path', None)
        if cache_path and os.path.exists(cache_path):
            try:
                os.remove(cache_path)
            except OSError:
                logger.exception("Failed to remove token cache %s", cache_path)
        self._client = None

    def playback_item(self):
        state = self.current_playback()
        if not state:
            return None
        return state.get('item')
