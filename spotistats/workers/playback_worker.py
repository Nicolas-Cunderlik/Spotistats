"""Worker thread for playback control, so a slow Spotify request never blocks the UI."""
import logging
from PyQt5.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)


class PlayTrackWorker(QThread):
    succeeded = pyqtSignal(str, str)  # track_id, outcome ("played" / "opened")
    failed = pyqtSignal(str)          # track_id

    def __init__(self, spotify_service, track_id, fallback_device_id=None, parent=None):
        super().__init__(parent)
        self.spotify_service = spotify_service
        self.track_id = track_id
        self.fallback_device_id = fallback_device_id

    def run(self):
        try:
            outcome = self.spotify_service.play_track(self.track_id, self.fallback_device_id)
            self.succeeded.emit(self.track_id, outcome)
        except Exception:
            logger.exception("Failed to play track %s", self.track_id)
            self.failed.emit(self.track_id)
