"""Main GUI for Spotistats using services and worker threads for network tasks."""
import logging
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QIcon, QPixmap, QFont, QPainter, QBrush, QColor, QFontDatabase
from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout, QFrame, QHBoxLayout, QApplication

from ..utils.logging_config import configure_logging
from ..services.spotify_service import SpotifyService
from ..services.ai_service import AIService
from ..services.similarity_service import SimilarityService
from ..workers.network_worker import FetchDataWorker
from .marquee_label import MarqueeLabel
from MiscUtil import FullscreenImageWindow

configure_logging()
logger = logging.getLogger(__name__)

# Poll cadence (ms). While playing we use a relaxed baseline (catches manual
# pause/skip/seek) but shrink the wait to land right on the track's end, so
# changes still feel instant without polling every second for no reason.
POLL_MS_ACTIVE = 5000
POLL_MS_IDLE = 4000
POLL_MS_MIN = 500
# Consecutive empty polls tolerated before treating playback as stopped, so a
# single transient API hiccup doesn't flash the UI to "No song playing."
IDLE_GRACE_POLLS = 3

class ClickableLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        from PyQt5.QtCore import pyqtSignal
        self.setCursor(Qt.PointingHandCursor)
    def mousePressEvent(self, event):
        from PyQt5.QtCore import Qt
        if event.button() == Qt.LeftButton:
            try:
                self.clicked.emit()
            except Exception:
                pass
    clicked = None

class SpotifyApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Spotistats")
        self.setWindowIcon(QIcon('SpotifyAppLogo.png'))
        self.setGeometry(50, 50, 300, 600)
        self.setFixedSize(300, 650)
        self.setStyleSheet("background-color: black;")

        # UI elements
        self.layout = QVBoxLayout()
        self.title_frame = QFrame()
        self.stats_frame = QFrame()
        self.song_name_and_artist_frame = QFrame()
        self.ai_label_frame = QFrame()
        self.similar_label_frame = QFrame()

        self.title_frame.setFixedHeight(100)
        self.song_name_and_artist_frame.setFixedHeight(80)
        self.ai_label_frame.setFixedWidth(128)
        self.similar_label_frame.setFixedWidth(128)

        self.title_frame.setStyleSheet("background-color: #141414; border-radius: 10px;")
        self.stats_frame.setStyleSheet("background-color: #141414; border-radius: 10px;")
        self.ai_label_frame.setStyleSheet("background-color: #292929; border-radius: 8px;")
        self.similar_label_frame.setStyleSheet("background-color: #292929; border-radius: 8px;")

        self.title_layout = QVBoxLayout()
        self.body_layout = QVBoxLayout()
        self.body_stats_layout = QHBoxLayout()
        self.song_name_and_artist_layout = QVBoxLayout()

        self.title_label = QLabel("SPOTISTATS")
        self.ai_label = QLabel("AI Suggestions loading...")
        self.similar_label = QLabel("Similar Tracks loading...")

        self.album_cover_label = QLabel(self)
        self.album_cover_label.setPixmap(QPixmap(260, 260))
        # connect click to show fullscreen
        self.album_cover_label.mousePressEvent = self._album_clicked

        self.song_name_label = MarqueeLabel("Song name loading...")
        self.artist_label = MarqueeLabel("Artist name loading...")

        title_font_id = QFontDatabase.addApplicationFont("KdamThmorPro-Regular.ttf")
        font_families = QFontDatabase.applicationFontFamilies(title_font_id)
        if font_families:
            iceberg_font = QFont(font_families[0], 30)
            self.title_label.setFont(iceberg_font)
            self.ai_label.setFont(QFont(font_families[0], 10))
            self.similar_label.setFont(QFont(font_families[0], 10))

        self.title_label.setStyleSheet("color: white;")
        self.song_name_label.setStyleSheet("color: white; font-size: 24px;")
        self.artist_label.setStyleSheet("color: #AAAAAA; font-size: 20px;")
        self.ai_label.setStyleSheet("color: white; font-size: 10px;")
        self.similar_label.setStyleSheet("color: white; font-size: 10px;")
        self.ai_label.setWordWrap(True)
        self.similar_label.setWordWrap(True)

        self.title_layout.addWidget(self.title_label)

        # ai and similar-tracks frames
        self.ai_label_layout = QVBoxLayout()
        self.ai_label_layout.addWidget(self.ai_label)
        self.ai_label_frame.setLayout(self.ai_label_layout)

        self.similar_label_layout = QVBoxLayout()
        self.similar_label_layout.addWidget(self.similar_label)
        self.similar_label_frame.setLayout(self.similar_label_layout)

        self.body_stats_layout.addWidget(self.ai_label_frame)
        self.body_stats_layout.addSpacing(4)
        self.body_stats_layout.addWidget(self.similar_label_frame)

        self.body_layout.addLayout(self.body_stats_layout)
        self.body_layout.addSpacing(6)
        self.body_layout.addWidget(self.album_cover_label)
        self.song_name_and_artist_layout.addWidget(self.song_name_label)
        self.song_name_and_artist_layout.addWidget(self.artist_label)

        self.title_layout.setAlignment(Qt.AlignCenter)
        self.song_name_and_artist_layout.setAlignment(Qt.AlignCenter)

        self.song_name_label.setAlignment(Qt.AlignCenter)
        self.artist_label.setAlignment(Qt.AlignCenter)
        self.ai_label.setAlignment(Qt.AlignCenter)
        self.similar_label.setAlignment(Qt.AlignCenter)

        self.title_frame.setLayout(self.title_layout)
        self.stats_frame.setLayout(self.body_layout)
        self.song_name_and_artist_frame.setLayout(self.song_name_and_artist_layout)

        self.layout.addWidget(self.title_frame)
        self.layout.addSpacing(6)
        self.layout.addWidget(self.stats_frame)
        self.layout.addSpacing(6)
        self.layout.addWidget(self.song_name_and_artist_frame)

        self.setLayout(self.layout)

        # Services
        self.spotify_service = SpotifyService()
        self.ai_service = AIService()
        self.similarity_service = SimilarityService()

        # State
        self.last_song_id = None
        self.song_playing = False
        self.current_worker = None
        self._workers = []  # keeps superseded workers alive until they finish
        self._idle_streak = 0

        # Timer - interval adapts based on playback state (see check_playback)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_playback)
        self.timer.start(POLL_MS_ACTIVE)

        # Initial check
        self.check_playback()

    def _album_clicked(self, event):
        if event.button() == Qt.LeftButton:
            try:
                self.showFullScreenCover()
            except Exception:
                logger.exception("Error showing fullscreen cover")

    def check_playback(self):
        try:
            state = self.spotify_service.current_playback()
            item = state.get('item') if state else None

            if not item:
                self._idle_streak += 1
                if self._idle_streak >= IDLE_GRACE_POLLS and self.last_song_id is not None:
                    self.last_song_id = None
                    self.song_playing = False
                    self.timer.setInterval(POLL_MS_IDLE)
                    self._show_idle()
                return

            self._idle_streak = 0
            track_id = item.get('id')
            is_playing = state.get('is_playing', False)
            track_changed = track_id != self.last_song_id
            play_changed = is_playing != self.song_playing

            # Recomputed every poll (not just on change) so the wait keeps
            # shrinking as a track nears its end instead of staying fixed.
            self.timer.setInterval(self._next_interval(state, item, is_playing))

            if not track_changed and not play_changed:
                return

            self.last_song_id = track_id
            self.song_playing = is_playing
            self.updateSongLabel(item, is_playing)

            # Only refetch album/AI/similar on an actual track change - a
            # pause/resume of the same track shouldn't redo that work.
            if track_changed:
                self.ai_label.setText("AI Suggestions loading...")
                self.similar_label.setText("Similar Tracks loading...")
                self.start_worker(item)

        except Exception:
            logger.exception("check_playback failed")
            self.timer.setInterval(POLL_MS_IDLE)

    def _next_interval(self, state, item, is_playing):
        if not is_playing:
            return POLL_MS_IDLE
        duration_ms = item.get('duration_ms')
        progress_ms = state.get('progress_ms')
        if duration_ms is None or progress_ms is None:
            return POLL_MS_ACTIVE
        remaining_ms = duration_ms - progress_ms
        return max(min(POLL_MS_ACTIVE, remaining_ms + 250), POLL_MS_MIN)

    def _show_idle(self):
        self.song_name_label.setText("No song playing.")
        self.artist_label.setText("- - - - -")
        self.ai_label.setText("AI Chord Suggestions\n\n-\n-\n-")
        self.similar_label.setText("Similar Tracks\n\n-\n-\n-")

    def updateSongLabel(self, track, is_playing=True):
        track_name = track.get('name', 'Unknown')
        artist = ", ".join(a.get('name') for a in track.get('artists', []))
        self.song_name_label.setText(f"{track_name}")
        self.artist_label.setText(f"{artist}" if is_playing else f"{artist} (Paused)")

    def start_worker(self, track):
        # QThread.terminate() is unsafe if a worker is blocked in a network
        # call, so a superseded worker is left to finish in the background;
        # self._workers keeps it alive, and the sender checks below discard
        # its results once it's no longer self.current_worker.
        try:
            worker = FetchDataWorker(track, self.ai_service, self.similarity_service)
            worker.album_bytes.connect(self.on_album_bytes)
            worker.ai_ready.connect(self.on_ai_ready)
            worker.similar_ready.connect(self.on_similar_ready)
            worker.error.connect(self.on_worker_error)
            worker.finished.connect(lambda: self._workers.remove(worker))
            self._workers.append(worker)
            self.current_worker = worker
            worker.start()
        except Exception:
            logger.exception("Failed to start FetchDataWorker")

    def on_album_bytes(self, data: bytes):
        if self.sender() is not self.current_worker:
            return
        try:
            pixmap = QPixmap()
            pixmap.loadFromData(data)
            pixmap = pixmap.scaled(260, 260, Qt.KeepAspectRatio, Qt.SmoothTransformation)

            # Rounded pixmap
            rounded = QPixmap(260, 260)
            rounded.fill(QColor("transparent"))
            painter = QPainter(rounded)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setBrush(QBrush(pixmap))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(0, 0, 260, 260, 8, 8)
            painter.end()

            self.album_cover_label.setPixmap(rounded)
            self.album_cover_label.setVisible(True)
        except Exception:
            logger.exception("Failed to render album image")

    def on_ai_ready(self, chords):
        if self.sender() is not self.current_worker:
            return
        try:
            if not chords:
                self.ai_label.setText("AI Chord Suggestions\n\n-\n-\n-")
                return
            while len(chords) < 3:
                chords.append("-")
            self.ai_label.setText(f"AI Chord Suggestions\n\n{chords[0]}\n{chords[1]}\n{chords[2]}")
        except Exception:
            logger.exception("Failed to update AI label")

    def on_similar_ready(self, similar):
        if self.sender() is not self.current_worker:
            return
        try:
            if not similar:
                self.similar_label.setText("Similar Tracks\n\nNot enough data\nfor this track")
                return
            lines = [f"{s['track_name']} - {s['track_artist']}" for s in similar]
            self.similar_label.setText("Similar Tracks\n\n" + "\n".join(lines))
        except Exception:
            logger.exception("Failed to update similar tracks label")

    def on_worker_error(self, msg):
        logger.error("Worker error: %s", msg)

    def showFullScreenCover(self):
        try:
            state = self.spotify_service.current_playback()
            if not state:
                return
            track = state.get('item')
            if not track:
                return
            album_cover_url = track['album']['images'][0]['url']
            import requests
            resp = requests.get(album_cover_url, timeout=8)
            resp.raise_for_status()
            data = resp.content
            self.fullscreen_window = FullscreenImageWindow(data)
            self.fullscreen_window.show()
        except Exception:
            logger.exception("Failed to show fullscreen cover")

if __name__ == '__main__':
    import sys
    app = QApplication(sys.argv)
    w = SpotifyApp()
    w.show()
    sys.exit(app.exec_())
