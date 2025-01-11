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

        self.stats_frame = QFrame()
        self.stats_frame.setStyleSheet("background-color: #141414; border-radius: 10px;")
        self.stats_frame.setContentsMargins(20, 20, 20, 20)

        self.album_cover_frame = QFrame()
        self.album_cover_frame.setStyleSheet("background-color: #141414; border-radius: 10px;")
        self.album_cover_frame.setContentsMargins(20, 20, 20, 20)
        
        self.stats_layout = QVBoxLayout()
        self.album_cover_layout = QVBoxLayout()

        self.song_label = QLabel("Song: Loading...")
        self.stats_label = QLabel("Stats: Loading...")
        self.song_label.setStyleSheet("color: #FFFFFF;")
        self.stats_label.setStyleSheet("color: #FFFFFF;")

        self.stats_layout.addWidget(self.song_label)
        self.stats_layout.addWidget(self.stats_label)

        self.album_cover = QLabel()
        self.album_cover.setPixmap(QPixmap(260, 260))

        self.album_cover_layout.addWidget(self.album_cover)
        self.album_cover_layout.setAlignment(self.album_cover, Qt.AlignCenter)

        self.stats_frame.setLayout(self.stats_layout)
        self.album_cover_frame.setLayout(self.album_cover_layout)

        self.layout.addWidget(self.stats_frame)
        self.layout.addSpacing(6)
        self.layout.addWidget(self.album_cover_frame)

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

        This function is called every second using a QTimer.
        """
        try:
            current_track = self.spotify.current_playback()
            if current_track and current_track['is_playing']:
                track = current_track['item']
                track_name = track['name']
                artist = ", ".join(artist['name'] for artist in track['artists'])
                # Update labels
                self.song_label.setText(f"Song: {track_name} by {artist}")
                self.song_label.setWordWrap(True)
                max_width = int(self.width() * 0.75)
                self.song_label.setMaximumWidth(max_width)
                self.update_album_cover(track)
            # Remove song data if no song is playing
            else:
                self.song_label.setText("No song is currently playing.")
                self.stats_label.setText("No stats are available if no song is playing.")
                if hasattr(self, 'album_cover'):
                    self.album_cover.setVisible(False)
        except Exception as e:
            self.song_label.setText("Error fetching song info.")
            self.stats_label.setText(str(e))

    def update_album_cover(self, track):
        """
        Updates the album cover whenever update_song_info is called. TODO: make this a separate thread
        """
        # Fetch album cover
        album_cover_url = track['album']['images'][0]['url']
        pixmap = QPixmap()
        pixmap.loadFromData(requests.get(album_cover_url).content)
        self.album_cover.setPixmap(pixmap.scaled(260, 260, Qt.KeepAspectRatio))
        self.album_cover.setVisible(True)

# Main application loop
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SpotifyApp()
    pywinstyles.apply_style(window, "dark")
    window.show()
    sys.exit(app.exec_())