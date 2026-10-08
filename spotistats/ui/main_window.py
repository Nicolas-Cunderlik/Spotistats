"""Main GUI for Spotistats using services and worker threads for network tasks."""
import logging
import os
import re
from PyQt5.QtCore import Qt, QTimer, QEvent
from PyQt5.QtGui import QIcon, QPixmap, QFont, QPainter, QBrush, QColor, QFontDatabase
from PyQt5.QtWidgets import (QWidget, QLabel, QVBoxLayout, QFrame, QHBoxLayout, QApplication,
                             QPlainTextEdit, QPushButton)

from ..utils.logging_config import configure_logging
from ..services.spotify_service import SpotifyService
from ..services.ai_service import AIService
from ..services.similarity_service import SimilarityService
from ..workers.network_worker import FetchDataWorker
from ..workers.playback_worker import PlayTrackWorker
from ..services import spotify_window_service
from .title_bar import TitleBar, TITLE_BAR_HEIGHT
from .clickable_list import ClickableListBox
from ..music.midi import progression_to_midi
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
# After a click-to-play, how long to wait before re-polling - long enough for
# Spotify to report the new track as current
PLAY_REFRESH_DELAY_MS = 700

# Docking is event-driven (WinEventHook on Spotify's window); this slow poll
# only finds Spotify after it launches and acts as a safety net.
DOCK_POLL_MS = 1000

# Width shared by the album cover and the boxes beneath it
CARD_WIDTH = 260
# Black margin around the content. None on the right: Spotify's window, docked
# against that edge, already has its own black padding on its left.
CONTENT_MARGIN = 9
WINDOW_WIDTH = 291  # 282px content frames + left margin only
ANALYTICS_BOX_WIDTH = (CARD_WIDTH - 4) // 2
ANALYTICS_BOX_HEIGHT = 150

_FEEDBACK_INPUT_STYLE = """
QPlainTextEdit {
    background-color: #141414; color: white; border: none; border-radius: 6px;
    padding: 4px; font-size: 11px;
}
"""
_FEEDBACK_BUTTON_STYLE = """
QPushButton {
    background-color: #3a3a3a; color: #B3B3B3; border: none; border-radius: 6px;
    font-family: "Segoe MDL2 Assets"; font-size: 14px;
}
QPushButton:hover { background-color: #4a4a4a; color: white; }
QPushButton:pressed { background-color: #555555; }
"""

MIDI_DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "Downloads")


def _safe_filename(name, max_length=120):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name).strip(" .")
    return name[:max_length] or "progression"


def _unique_path(directory, filename):
    """`filename` in `directory`, with " (2)", " (3)"... appended if taken."""
    stem, ext = os.path.splitext(filename)
    path, n = os.path.join(directory, filename), 2
    while os.path.exists(path):
        path, n = os.path.join(directory, f"{stem} ({n}){ext}"), n + 1
    return path


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
        # (minimum height is set from the content's natural height, below)
        self.setFixedWidth(WINDOW_WIDTH)
        self.setStyleSheet("""
            QWidget { background-color: black; }
            QToolTip { color: white; background-color: #282828; border: 1px solid #3a3a3a; padding: 4px; }
        """)

        # UI elements
        self.layout = QVBoxLayout()
        self.title_frame = QFrame()
        self.stats_frame = QFrame()

        # 93 rather than 100, with a 2px bottom margin below: the title font's
        # descent is large (22px vs 46px ascent) and all-caps text never uses
        # it, so centring the line box left the lettering 8px above centre.
        # (Leaves 30px above the lettering and 31px below - the extra pixel
        # was judged by eye on the real app.)
        self.title_frame.setFixedHeight(93)

        self.title_frame.setStyleSheet("background-color: #141414; border-radius: 10px;")
        self.stats_frame.setStyleSheet("background-color: #141414; border-radius: 10px;")

        self.title_layout = QVBoxLayout()
        self.body_layout = QVBoxLayout()
        self.body_stats_layout = QHBoxLayout()

        self.title_label = QLabel("SPOTISTATS")

        self.album_cover_label = QLabel(self)
        self.album_cover_label.setPixmap(QPixmap(260, 260))
        # connect click to show fullscreen
        self.album_cover_label.mousePressEvent = self._album_clicked

        title_font_id = QFontDatabase.addApplicationFont("KdamThmorPro-Regular.ttf")
        font_families = QFontDatabase.applicationFontFamilies(title_font_id)
        if font_families:
            iceberg_font = QFont(font_families[0], 30)
            self.title_label.setFont(iceberg_font)

        self.title_label.setStyleSheet("color: white;")

        self.title_layout.addWidget(self.title_label)

        # ai and similar-tracks frames
        font_family = font_families[0] if font_families else None
        self.chord_box = ClickableListBox(
            "AI Chord Suggestions", font_family, ANALYTICS_BOX_WIDTH, ANALYTICS_BOX_HEIGHT
        )
        self.chord_box.item_clicked.connect(self._download_progression)

        self.similar_tracks = ClickableListBox(
            "Similar Tracks", font_family, ANALYTICS_BOX_WIDTH, ANALYTICS_BOX_HEIGHT
        )
        self.similar_tracks.item_clicked.connect(self._play_track)

        # Exactly CARD_WIDTH wide and centred, flush with the cover above
        self.body_stats_layout.setSpacing(0)
        self.body_stats_layout.addStretch(1)
        self.body_stats_layout.addWidget(self.chord_box)
        self.body_stats_layout.addSpacing(4)
        self.body_stats_layout.addWidget(self.similar_tracks)
        self.body_stats_layout.addStretch(1)

        self.feedback_frame = self._build_feedback_box(font_families[0] if font_families else None)

        # Cover on top, then the analytics boxes, then feedback on those results
        self.body_layout.setSpacing(8)
        self.body_layout.addWidget(self.album_cover_label, alignment=Qt.AlignCenter)
        self.body_layout.addLayout(self.body_stats_layout)
        self.body_layout.addWidget(self.feedback_frame, alignment=Qt.AlignCenter)

        self.title_layout.setAlignment(Qt.AlignCenter)


        self.title_layout.setContentsMargins(9, 9, 9, 2)
        self.title_frame.setLayout(self.title_layout)
        self.stats_frame.setLayout(self.body_layout)

        self.layout.addWidget(self.title_frame)
        self.layout.addSpacing(6)
        self.layout.addWidget(self.stats_frame)
        # Nested under the title bar, so it no longer gets the style's
        # top-level margins automatically
        # No top margin: the title frame sits directly under the title bar
        self.layout.setContentsMargins(CONTENT_MARGIN, 0, 0, CONTENT_MARGIN)
        self.layout.setSpacing(0)  # gaps come from the explicit addSpacing calls

        root_layout = QVBoxLayout()
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(TitleBar(self, 'SpotifyAppLogo.png'))
        # Fixed-height container (at the content's natural height) so the
        # content keeps its exact layout and any extra window height lands in
        # the stretch below as black padding
        content = QWidget()
        content.setLayout(self.layout)
        content.setFixedHeight(content.sizeHint().height())
        root_layout.addWidget(content)
        root_layout.addStretch(1)
        self.setLayout(root_layout)
        self.setMinimumHeight(content.height() + TITLE_BAR_HEIGHT)
        self.resize(WINDOW_WIDTH, self.minimumHeight())

        # Services
        self.spotify_service = SpotifyService()
        self.ai_service = AIService()
        self.similarity_service = SimilarityService()

        # State
        self.last_song_id = None
        self.current_worker = None
        self._workers = []  # keeps superseded workers alive until they finish
        self._idle_streak = 0
        self._play_worker = None
        self._chord_suggestions = None  # ChordSuggestions for _chord_track, once ready
        self._chord_track = None
        self._last_device_id = None  # fallback target when Spotify has no active device

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

    def _build_feedback_box(self, font_family):
        """Feedback on the current recommendations: optional free text, then
        thumbs up/down. Not wired yet - the thumbs will be the submit trigger
        and the text optional extra context (see feedback design notes)."""
        frame = QFrame()
        frame.setFixedWidth(CARD_WIDTH)
        frame.setStyleSheet("background-color: #292929; border-radius: 8px;")

        title = QLabel("Rate These Suggestions")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: white; font-size: 10px;")
        if font_family:
            title.setFont(QFont(font_family, 10))

        self.feedback_input = QPlainTextEdit()
        self.feedback_input.setPlaceholderText("Optional: what was off, or spot on?")
        self.feedback_input.setFixedHeight(52)
        self.feedback_input.setStyleSheet(_FEEDBACK_INPUT_STYLE)

        # Segoe MDL2 Assets glyphs: Like / Dislike
        self.feedback_up_btn = QPushButton("")
        self.feedback_down_btn = QPushButton("")
        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        for btn, tip in ((self.feedback_up_btn, "Good suggestions"),
                         (self.feedback_down_btn, "Poor suggestions")):
            btn.setFixedHeight(30)
            btn.setToolTip(tip)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFocusPolicy(Qt.NoFocus)
            btn.setStyleSheet(_FEEDBACK_BUTTON_STYLE)
            buttons.addWidget(btn)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        layout.addWidget(title)
        layout.addWidget(self.feedback_input)
        layout.addLayout(buttons)
        return frame

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
            if state and state.get('device'):
                self._last_device_id = state['device'].get('id') or self._last_device_id

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
            self.chord_box.set_loading()
            self.similar_tracks.set_loading()
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
        self.chord_box.set_idle()
        self.similar_tracks.set_idle()

    def start_worker(self, track):
        # QThread.terminate() is unsafe if a worker is blocked in a network
        # call, so a superseded worker is left to finish in the background;
        # self._workers keeps it alive, and the sender checks below discard
        # its results once it's no longer self.current_worker.
        try:
            self._chord_suggestions, self._chord_track = None, track
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

    def on_ai_ready(self, suggestions):
        if self.sender() is not self.current_worker:
            return
        try:
            self._chord_suggestions = suggestions
            if suggestions is None:
                self.chord_box.set_placeholders(["Unavailable for", "this track"])
                return
            items = []
            for i, progression in enumerate(suggestions.progressions):
                symbols = " - ".join(chord.symbol for chord in progression.chords)
                bars = sum(c.duration_beats for c in progression.chords) / progression.beats_per_bar
                tooltip = (f"Click to download MIDI\n{progression.title}\n"
                           f"{progression.key} · {progression.tempo_bpm} BPM · "
                           f"{progression.beats_per_bar}/4 · {bars:g} bars\n{symbols}")
                items.append((i, symbols, tooltip))
            self.chord_box.set_items(items)
        except Exception:
            logger.exception("Failed to update chord suggestions")

    def on_similar_ready(self, similar):
        if self.sender() is not self.current_worker:
            return
        try:
            if not similar:
                self.similar_tracks.set_placeholders(["Not enough data", "for this track"])
                return
            self.similar_tracks.set_items([
                (t["track_id"], f"{t['track_name']} - {t['track_artist']}",
                 f"Click to play now\n{t['track_name']} - {t['track_artist']}")
                for t in similar
            ])
        except Exception:
            logger.exception("Failed to update similar tracks")

    def _play_track(self, track_id):
        # One request at a time - ignore clicks while the last is in flight
        if self._play_worker is not None and self._play_worker.isRunning():
            return
        worker = PlayTrackWorker(self.spotify_service, track_id, self._last_device_id, parent=self)
        worker.succeeded.connect(self._on_play_succeeded)
        worker.failed.connect(lambda tid: self.similar_tracks.flash(tid, "Couldn't play this track"))
        self._play_worker = worker
        worker.start()

    def _download_progression(self, index):
        suggestions, track = self._chord_suggestions, self._chord_track
        if suggestions is None or track is None:
            return
        progression = suggestions.progressions[index]
        try:
            artist = ", ".join(a.get('name') for a in track.get('artists', []))
            stem = f"{artist} - {track.get('name', 'Unknown')} - {index + 1} {progression.title}"
            path = _unique_path(MIDI_DOWNLOAD_DIR, _safe_filename(stem) + ".mid")
            os.makedirs(MIDI_DOWNLOAD_DIR, exist_ok=True)
            with open(path, "wb") as f:
                f.write(progression_to_midi(progression))
            logger.info("Saved MIDI to %s", path)
            self.chord_box.flash(index, "Saved to Downloads")
        except Exception:
            logger.exception("Failed to save MIDI")
            self.chord_box.flash(index, "Couldn't save MIDI")

    def _on_play_succeeded(self, track_id, outcome):
        logger.info("Similar track %s %s", track_id, outcome)
        # Poll shortly instead of waiting out the current interval (up to
        # POLL_MS_ACTIVE), so the cover/chords/similar tracks follow the click
        QTimer.singleShot(PLAY_REFRESH_DELAY_MS, self.check_playback)

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
