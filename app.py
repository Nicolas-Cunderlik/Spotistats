import sys
from PyQt5.QtCore import * 
from PyQt5.QtGui import * 
from PyQt5.QtWidgets import *
import pywinstyles.py_win_style
from auth import get_spotify_client
import requests

class SpotifyApp(QWidget):
    def __init__(self):
        """
        Initializes the SpotifyApp window with title and geometry settings, 
        sets up the layout and widgets for displaying song information and stats, 
        initializes the Spotify client, and starts a timer to periodically update 
        the song information every 2.5 seconds.
        """
        super().__init__()
        self.setWindowTitle("Spotistats")
        
        self.setWindowIcon(QIcon('SpotifyAppLogo.png'))
        self.setGeometry(100, 100, 400, 800)
        self.setStyleSheet("background-color: #000000;")
        # Layout and widgets
        self.layout = QVBoxLayout()

        self.top_frame = QFrame()

        self.title_frame = QFrame()
        self.title_frame.setStyleSheet("background-color: #141414; border-radius: 10px;")
        self.title_frame.setContentsMargins(20, 20, 20, 20)
        self.label_layout = QVBoxLayout()

        self.song_label = QLabel("Song: Loading...")
        self.stats_label = QLabel("Stats: Loading...")
        self.song_label.setStyleSheet("color: #FFFFFF;")
        self.stats_label.setStyleSheet("color: #FFFFFF;")

        self.label_layout.addWidget(self.song_label)
        self.label_layout.addWidget(self.stats_label)
        self.title_frame.setLayout(self.label_layout)

        self.layout.addWidget(self.title_frame)

        self.setLayout(self.layout)
        # Spotify Client
        self.spotify = get_spotify_client()
        # Timer to update song info
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_song_info)
        self.timer.start(1000)  # Check every second
        self.update_song_info()  # Initial fetch

    def update_song_info(self):
        """
        Updates the song and stats labels with the current song's name,
        artist, tempo, energy, and danceability. If no song is currently
        playing, or if there is an error fetching the song info, updates
        the labels with an appropriate message.

        This function is called every 2.5 seconds using a QTimer.
        """
        try:
            current_track = self.spotify.current_playback()
            if current_track and current_track['is_playing']:
                track = current_track['item']
                track_name = track['name']
                artist = ", ".join(artist['name'] for artist in track['artists'])
                # Update labels
                self.song_label.setText(f"Song: {track_name} by {artist}")
                # Fetch album cover
                album_cover_url = track['album']['images'][0]['url']
                if hasattr(self, 'album_cover'):
                    # Update existing album cover
                    pixmap = QPixmap()
                    pixmap.loadFromData(requests.get(album_cover_url).content)
                    self.album_cover.setPixmap(pixmap.scaled(260, 260, Qt.KeepAspectRatio))
                else:
                    # Create new album cover QLabel
                    self.album_cover = QLabel()
                    pixmap = QPixmap()
                    pixmap.loadFromData(requests.get(album_cover_url).content)
                    self.album_cover.setPixmap(pixmap.scaled(260, 260, Qt.KeepAspectRatio))
                    self.layout.addWidget(self.album_cover)
                self.layout.setAlignment(self.album_cover, Qt.AlignCenter)
            # Remove song data if no song is playing
            else:
                self.song_label.setText("No song is currently playing.")
                self.stats_label.setText("")
                if hasattr(self, 'album_cover'):
                    self.layout.removeWidget(self.album_cover)
                    self.album_cover.deleteLater()
                    del self.album_cover
        except Exception as e:
            self.song_label.setText("Error fetching song info.")
            self.stats_label.setText(str(e))

# Main application loop
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SpotifyApp()
    pywinstyles.apply_style(window, "dark")
    window.show()
    sys.exit(app.exec_())