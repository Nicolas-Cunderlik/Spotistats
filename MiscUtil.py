"""
Filename: MiscUtil.py
Author: Nicolas Cunderlik
Date: 2025
Description: Miscellaneous utility functions and classes for the application.

Copyright © 2025 Nicolas Cunderlik. All Rights Reserved.

This source code is the property of the author/owner and is protected under
copyright law. Unauthorized copying, modification, distribution, or any use
of this file, in part or in full, without prior written permission from the
author/owner, is strictly prohibited.

For inquiries, contact: nicolas7cunderlik@gmail.com
"""

from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap

class FullscreenImageWindow(QWidget):
    def __init__(self, data):
        super().__init__()
        
        # Set up the fullscreen window
        self.setWindowFlags(Qt.FramelessWindowHint) # Remove window decorations
        self.setStyleSheet("background-color: black;")
        self.showFullScreen()

        # Create a label to display the image
        self.image_label = QLabel(self)
        pixmap = QPixmap()
        pixmap.loadFromData(data)
        self.image_label.setPixmap(pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.image_label.setAlignment(Qt.AlignCenter)

        # Set layout
        layout = QVBoxLayout(self)
        layout.addWidget(self.image_label)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Escape, Qt.Key_Space):
            self.close() # Close the fullscreen window

class ClickableLabel(QLabel):

    def __init__(self, parent=None):
        super().__init__(parent)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()

    clicked = pyqtSignal() # Custom signal

class FullscreenImageWindow(QWidget):
    def __init__(self, data):
        super().__init__()
        
        # Set up the fullscreen window
        self.setWindowFlags(Qt.FramelessWindowHint) # Remove window decorations
        self.setStyleSheet("background-color: black;")
        self.showFullScreen()

        # Create a label to display the image
        self.image_label = QLabel(self)
        pixmap = QPixmap()
        pixmap.loadFromData(data)
        self.image_label.setPixmap(pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.image_label.setAlignment(Qt.AlignCenter)

        # Set layout
        layout = QVBoxLayout(self)
        layout.addWidget(self.image_label)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Escape, Qt.Key_Space):
            self.close() # Close the fullscreen window

