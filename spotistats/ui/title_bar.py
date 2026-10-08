"""Custom title bar - replaces the native one, which on Windows 10 turns grey
whenever the window loses focus (the caption colour API is Windows 11 only)."""
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QWidget, QLabel, QHBoxLayout, QPushButton

TITLE_BAR_HEIGHT = 30

_BUTTON_STYLE = """
QPushButton {{
    background-color: transparent; color: white; border: none;
    font-family: "Segoe MDL2 Assets"; font-size: 10px;
}}
QPushButton:hover {{ background-color: {hover}; }}
QPushButton:pressed {{ background-color: {pressed}; }}
"""

class TitleBar(QWidget):
    def __init__(self, window, title, icon_path):
        super().__init__(window)
        self._window = window
        self.setFixedHeight(TITLE_BAR_HEIGHT)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("background-color: black;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 0, 0)
        layout.setSpacing(6)

        icon = QLabel()
        icon.setPixmap(QPixmap(icon_path).scaled(16, 16, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        title_label = QLabel(title)
        title_label.setStyleSheet("color: white; font-size: 12px;")

        # Segoe MDL2 Assets glyph: ChromeClose
        close_btn = self._button("\uE8BB", "#e81123", "#f1707a")
        close_btn.clicked.connect(window.close)

        layout.addWidget(icon)
        layout.addWidget(title_label)
        layout.addStretch()
        layout.addWidget(close_btn)

    def _button(self, glyph, hover, pressed):
        btn = QPushButton(glyph)
        btn.setFixedSize(46, TITLE_BAR_HEIGHT)
        btn.setFocusPolicy(Qt.NoFocus)
        btn.setStyleSheet(_BUTTON_STYLE.format(hover=hover, pressed=pressed))
        return btn
