"""A QLabel that scrolls its text horizontally when it overflows the
available width, instead of letting Qt silently clip it."""
from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QPainter
from PyQt5.QtWidgets import QLabel


class MarqueeLabel(QLabel):
    SPEED_PX = 1
    INTERVAL_MS = 30
    PAUSE_MS = 1500
    GAP_PX = 40

    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._full_text = ""
        self._offset = 0
        self._scrolling = False
        self._timer = QTimer(self)
        self._timer.setInterval(self.INTERVAL_MS)
        self._timer.timeout.connect(self._advance)
        self.setText(text)

    def setText(self, text):
        self._full_text = text
        self._offset = 0
        super().setText(text)
        self._restart_scroll_check()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._restart_scroll_check()

    def _text_width(self):
        return self.fontMetrics().horizontalAdvance(self._full_text)

    def _restart_scroll_check(self):
        needs_scroll = self.width() > 0 and self._text_width() > self.width()
        if needs_scroll and not self._scrolling:
            self._scrolling = True
            self._offset = 0
            # Brief pause so the start of the text is readable before it scrolls.
            QTimer.singleShot(self.PAUSE_MS, self._maybe_start_timer)
        elif not needs_scroll and self._scrolling:
            self._scrolling = False
            self._timer.stop()
            self._offset = 0
            self.update()

    def _maybe_start_timer(self):
        # Text may have changed (and stopped overflowing) during the pause.
        if self._scrolling:
            self._timer.start()

    def _advance(self):
        loop_width = self._text_width() + self.GAP_PX
        if loop_width <= 0:
            return
        self._offset = (self._offset + self.SPEED_PX) % loop_width
        self.update()

    def paintEvent(self, event):
        if not self._scrolling:
            super().paintEvent(event)
            return
        painter = QPainter(self)
        painter.setClipRect(self.rect())
        painter.setFont(self.font())
        painter.setPen(self.palette().color(self.foregroundRole()))
        metrics = self.fontMetrics()
        loop_width = self._text_width() + self.GAP_PX
        y = (self.height() + metrics.ascent() - metrics.descent()) // 2
        x = -self._offset
        while x < self.width():
            painter.drawText(x, y, self._full_text)
            x += loop_width
