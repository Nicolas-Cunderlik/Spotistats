"""Entry point for the refactored Spotistats app.
Run with: python run.py
"""
import sys
import logging
import pywinstyles
from PyQt5.QtWidgets import QApplication
from spotistats.ui.main_window import SpotifyApp

# logging is configured by spotistats.utils.logging_config on import
logger = logging.getLogger(__name__)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = SpotifyApp()
    pywinstyles.apply_style(window, "dark")
    window.show()
    logger.info("Spotistats started")
    sys.exit(app.exec_())
