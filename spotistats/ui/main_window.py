"""Main GUI for Spotistats using services and worker threads for network tasks."""
import logging
from PyQt5.QtCore import Qt, QTimer, QEvent
from PyQt5.QtGui import QIcon, QPixmap, QFont, QPainter, QBrush, QColor, QFontDatabase
from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout, QFrame, QHBoxLayout, QApplication

from ..utils.logging_config import configure_logging
from ..services.spotify_service import SpotifyService
from ..services.ai_service import AIService
from ..services.similarity_service import SimilarityService
from ..workers.network_worker import FetchDataWorker
from ..services import spotify_window_service
from .title_bar import TitleBar, TITLE_BAR_HEIGHT
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

# Docking is event-driven (WinEventHook on Spotify's window); this slow poll
# only finds Spotify after it launches and acts as a safety net.
DOCK_POLL_MS = 1000

# Height of the main content below the title bar; the window may be taller
# (padded to match Spotify) but never shorter
CONTENT_HEIGHT = 564

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
        # Frameless so the custom TitleBar can stay black when unfocused. No
        # minimise: the window's visibility follows Spotify's, so a separate
        # minimised state would only drift out of sync - close it instead.
        # (Without WS_MINIMIZEBOX, the taskbar button and Win+M can't minimise
        # it either.)
        self.setWindowFlags(Qt.FramelessWindowHint)
        # Docking shows/hides us as Spotify appears and disappears - that must
        # never pull focus away from Spotify
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        # Width is fixed; height grows to match Spotify's (see _dock_to_spotify),
        # with the content as the floor - extra height is black padding below it
        self.setFixedWidth(300)
        self.setMinimumHeight(CONTENT_HEIGHT + TITLE_BAR_HEIGHT)
        self.resize(300, CONTENT_HEIGHT + TITLE_BAR_HEIGHT)
        self.setStyleSheet("background-color: black;")

        # UI elements
        self.layout = QVBoxLayout()
        self.title_frame = QFrame()
        self.stats_frame = QFrame()
        self.ai_label_frame = QFrame()
        self.similar_label_frame = QFrame()

        self.title_frame.setFixedHeight(100)
        self.ai_label_frame.setFixedWidth(128)
        self.similar_label_frame.setFixedWidth(128)

        self.title_frame.setStyleSheet("background-color: #141414; border-radius: 10px;")
        self.stats_frame.setStyleSheet("background-color: #141414; border-radius: 10px;")
        self.ai_label_frame.setStyleSheet("background-color: #292929; border-radius: 8px;")
        self.similar_label_frame.setStyleSheet("background-color: #292929; border-radius: 8px;")

        self.title_layout = QVBoxLayout()
        self.body_layout = QVBoxLayout()
        self.body_stats_layout = QHBoxLayout()

        self.title_label = QLabel("SPOTISTATS")
        self.ai_label = QLabel("AI Suggestions loading...")
        self.similar_label = QLabel("Similar Tracks loading...")

        self.album_cover_label = QLabel(self)
        self.album_cover_label.setPixmap(QPixmap(260, 260))
        # connect click to show fullscreen
        self.album_cover_label.mousePressEvent = self._album_clicked

        title_font_id = QFontDatabase.addApplicationFont("KdamThmorPro-Regular.ttf")
        font_families = QFontDatabase.applicationFontFamilies(title_font_id)
        if font_families:
            iceberg_font = QFont(font_families[0], 30)
            self.title_label.setFont(iceberg_font)
            self.ai_label.setFont(QFont(font_families[0], 10))
            self.similar_label.setFont(QFont(font_families[0], 10))

        self.title_label.setStyleSheet("color: white;")
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
        self.body_layout.addWidget(self.album_cover_label, alignment=Qt.AlignCenter)

        self.title_layout.setAlignment(Qt.AlignCenter)

        self.ai_label.setAlignment(Qt.AlignCenter)
        self.similar_label.setAlignment(Qt.AlignCenter)

        self.title_frame.setLayout(self.title_layout)
        self.stats_frame.setLayout(self.body_layout)

        self.layout.addWidget(self.title_frame)
        self.layout.addSpacing(6)
        self.layout.addWidget(self.stats_frame)
        # Nested under the title bar, so it no longer gets the style's
        # top-level margins automatically
        self.layout.setContentsMargins(9, 9, 9, 9)
        self.layout.setSpacing(0)  # gaps come from the explicit addSpacing calls

        root_layout = QVBoxLayout()
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(TitleBar(self, "Spotistats", 'SpotifyAppLogo.png'))
        # Fixed-height container so the content keeps its exact layout and any
        # extra window height lands in the stretch below as black padding
        content = QWidget()
        content.setLayout(self.layout)
        content.setFixedHeight(CONTENT_HEIGHT)
        root_layout.addWidget(content)
        root_layout.addStretch(1)
        self.setLayout(root_layout)

        # Services
        self.spotify_service = SpotifyService()
        self.ai_service = AIService()
        self.similarity_service = SimilarityService()

        # State
        self.last_song_id = None
        self.current_worker = None
        self._workers = []  # keeps superseded workers alive until they finish
        self._idle_streak = 0

        # Timer - interval adapts based on playback state (see check_playback)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_playback)
        self.timer.start(POLL_MS_ACTIVE)

        # Docking - follows the Spotify window so this looks like part of it
        self._spotify_hwnd = None
        self._spotify_hook = None
        self.dock_timer = QTimer(self)
        self.dock_timer.timeout.connect(self._dock_to_spotify)
        self.dock_timer.start(DOCK_POLL_MS)

        # Initial check
        self.check_playback()

    def _dock_to_spotify(self):
        try:
            hwnd = self._spotify_hwnd
            if hwnd is None or not spotify_window_service.is_window_valid(hwnd):
                hwnd = spotify_window_service.find_spotify_window()
                self._set_spotify_window(hwnd)

            if hwnd is None or spotify_window_service.is_minimized(hwnd):
                self._hide_docked()
                return

            rect = spotify_window_service.get_visible_rect(hwnd)
            if rect is None:
                self._hide_docked()
                return

            # Win32 works in physical pixels; Qt sizes are logical
            dpr = self.devicePixelRatioF()
            width = round(self.width() * dpr)
            min_height = round(self.minimumHeight() * dpr)
            left, top, _right, bottom = rect
            # Match Spotify's height, but never shrink below our content - if
            # Spotify is shorter we simply extend past its bottom edge
            bounds = (left - width, top, width, max(bottom - top, min_height))

            own_hwnd = int(self.winId())
            spotify_window_service.set_window_bounds(own_hwnd, *bounds)

            if not self.isVisible():
                self.show()

            if spotify_window_service.get_foreground_window() == hwnd:
                spotify_window_service.bring_to_top(own_hwnd)
            elif self.isActiveWindow():
                spotify_window_service.place_below(hwnd, own_hwnd)
        except Exception:
            logger.exception("Failed to dock to Spotify window")

    def _set_spotify_window(self, hwnd):
        if self._spotify_hook is not None and self._spotify_hook.hwnd != hwnd:
            self._spotify_hook.unhook()
            self._spotify_hook = None
        self._spotify_hwnd = hwnd
        if hwnd is not None and self._spotify_hook is None:
            self._spotify_hook = spotify_window_service.WindowEventHook(hwnd, self._on_spotify_event)

    def _on_spotify_event(self, event):
        ws = spotify_window_service
        if event == ws.EVENT_SYSTEM_MINIMIZESTART:
            self._hide_docked()  # hide now rather than after the minimise animation
        elif event in (ws.EVENT_OBJECT_DESTROY, ws.EVENT_OBJECT_HIDE):
            self._set_spotify_window(None)
            self._hide_docked()
        else:
            self._dock_to_spotify()

    def changeEvent(self, event):
        if event.type() == QEvent.ActivationChange and self.isActiveWindow():
            # Keep the pair together in z-order: when we're activated, pull
            # Spotify up to sit directly beneath us (Spotify's own activation is
            # handled by its EVENT_SYSTEM_FOREGROUND hook, which raises us)
            self._pull_spotify_below()
        super().changeEvent(event)

    def _pull_spotify_below(self):
        if self._spotify_hwnd is None or not self.isActiveWindow():
            return
        try:
            spotify_window_service.place_below(self._spotify_hwnd, int(self.winId()))
        except Exception:
            logger.exception("Failed to sync z-order with Spotify")

    def _hide_docked(self):
        if self.isVisible():
            self.hide()

    def closeEvent(self, event):
        # Closing is how the user exits. Stop the timers explicitly - closing
        # only hides the window, so a still-running dock timer would re-show it
        # if anything (e.g. the fullscreen cover) kept the app alive.
        self.dock_timer.stop()
        self.timer.stop()
        if self._spotify_hook is not None:
            self._spotify_hook.unhook()
            self._spotify_hook = None
        super().closeEvent(event)
        QApplication.quit()

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
                    self.timer.setInterval(POLL_MS_IDLE)
                    self._show_idle()
                return

            self._idle_streak = 0
            track_id = item.get('id')
            is_playing = state.get('is_playing', False)

            # Recomputed every poll (not just on change) so the wait keeps
            # shrinking as a track nears its end instead of staying fixed.
            self.timer.setInterval(self._next_interval(state, item, is_playing))

            # Only refetch album/AI/similar on an actual track change - a
            # pause/resume of the same track shouldn't redo that work.
            if track_id == self.last_song_id:
                return

            self.last_song_id = track_id
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
        self.ai_label.setText("AI Chord Suggestions\n\n-\n-\n-")
        self.similar_label.setText("Similar Tracks\n\n-\n-\n-")

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
