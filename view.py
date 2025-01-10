# TODO: delegate app window to this file

import sys
from PyQt5.QtCore import * 
from PyQt5.QtGui import * 
from PyQt5.QtWidgets import *
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Spotify Stats")
        self.setGeometry(200, 200, 500, 300)
        self.setWindowIcon(QIcon('SpotifyAppLogo.png'))
        self.initUI()
        self.show()

    def initUI(self):
        central_widget = QWidget();
        self.setCentralWidget(central_widget)
        

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())