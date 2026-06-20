"""Worker thread to fetch album image bytes, AI chord suggestions, and similar tracks.
Emits raw bytes for the UI thread to convert to QPixmap (QPixmap isn't thread-safe everywhere).
"""
import logging
from PyQt5.QtCore import QThread, pyqtSignal
import requests

logger = logging.getLogger(__name__)

class FetchDataWorker(QThread):
    album_bytes = pyqtSignal(bytes)
    ai_ready = pyqtSignal(list)
    similar_ready = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, spotify_track, ai_service, similarity_service, parent=None):
        super().__init__(parent)
        self.track = spotify_track
        self.ai_service = ai_service
        self.similarity_service = similarity_service

    def run(self):
        try:
            if not self.track:
                return

            # Album art
            try:
                album_cover_url = self.track['album']['images'][0]['url']
                resp = requests.get(album_cover_url, timeout=8)
                resp.raise_for_status()
                self.album_bytes.emit(resp.content)
            except Exception:
                logger.exception("Failed to fetch album image")

            # AI suggestions
            try:
                if self.ai_service:
                    track_name = self.track.get('name', 'Unknown')
                    artist = ", ".join(a.get('name') for a in self.track.get('artists', []))
                    chords = self.ai_service.get_chord_suggestions(track_name, artist)
                    self.ai_ready.emit(chords)
            except Exception:
                logger.exception("Failed to fetch AI suggestions")

            # Similar tracks
            try:
                if self.similarity_service:
                    track_id = self.track.get('id')
                    similar = self.similarity_service.find_similar(track_id, k=3)
                    self.similar_ready.emit(similar)
            except Exception:
                logger.exception("Failed to fetch similar tracks")

        except Exception as e:
            logger.exception("Unhandled error in FetchDataWorker")
            self.error.emit(str(e))
