import sys
from PyQt5.QtCore import * 
from PyQt5.QtGui import * 
from PyQt5.QtWidgets import *
import pywinstyles.py_win_style
from auth import *
import requests

class SpotifyApp(QWidget):
    def __init__(self):
        """
        Initializes the SpotifyApp window with title and geometry settings, 
        sets up the layout and widgets for displaying song information and stats, 
        initializes the Spotify client, and starts a timer to periodically update 
        the song information every 2 seconds.
        """
        super().__init__()

        self.setWindowTitle("Spotistats")
        self.setWindowIcon(QIcon('SpotifyAppLogo.png'))
        self.setGeometry(100, 100, 400, 800)
        self.setStyleSheet("background-color: #000000;")

        # Layout and widgets
        self.layout = QVBoxLayout()

        self.title_frame = QFrame()
        self.title_frame.setFixedHeight(100)
        self.stats_frame = QFrame()
        self.album_cover_frame = QFrame()

        self.title_frame.setStyleSheet("background-color: #141414; border-radius: 10px;")
        self.stats_frame.setStyleSheet("background-color: #141414; border-radius: 10px;")
        self.album_cover_frame.setStyleSheet("background-color: #141414; border-radius: 10px;")
        
        self.title_layout = QVBoxLayout()
        self.stats_layout = QVBoxLayout()
        self.album_cover_layout = QVBoxLayout()

        self.title_label = QLabel("SPOTISTATS")
        self.song_label = QLabel("Song: Loading...")
        self.stats_label = QLabel("Stats: Loading...")

        title_font_id = QFontDatabase.addApplicationFont("KdamThmorPro-Regular.ttf")
        font_families = QFontDatabase.applicationFontFamilies(title_font_id)
        iceberg_font = QFont(font_families[0], 30)
        self.title_label.setFont(iceberg_font)

        self.title_label.setStyleSheet("color: #FFFFFF;")
        self.song_label.setStyleSheet("color: #FFFFFF;")
        self.stats_label.setStyleSheet("color: #FFFFFF;")

        self.title_layout.addWidget(self.title_label)
        self.stats_layout.addWidget(self.song_label)
        self.stats_layout.addWidget(self.stats_label)

        self.album_cover = QLabel() # FIXME: make this image scale
        self.album_cover.setPixmap(QPixmap(260, 260))

        self.title_layout.setAlignment(Qt.AlignCenter)
        self.album_cover_layout.addWidget(self.album_cover)
        self.album_cover_layout.setAlignment(self.album_cover, Qt.AlignCenter)

        self.title_frame.setLayout(self.title_layout)
        self.stats_frame.setLayout(self.stats_layout)
        self.album_cover_frame.setLayout(self.album_cover_layout)

        self.layout.addWidget(self.title_frame)
        self.layout.addSpacing(6)
        self.layout.addWidget(self.stats_frame)
        self.layout.addSpacing(6)
        self.layout.addWidget(self.album_cover_frame)

        self.setLayout(self.layout)

        # Necessary clients
        self.spotify = get_spotify_client()
        self.openai = get_openai_client()
        self.run()

    def update_song_info(self):
        """
        Updates the song and stats labels with the current song's name,
        artist, tempo, energy, and danceability. If no song is currently
        playing, or if there is an error fetching the song info, updates
        the labels with an appropriate message.

        This function is called every second using a QTimer.
        """
        if not self.spotify or not self.openai or not self.track_changed():
            return
        try:
            current_track = self.get_playback_state()
            if self.track_playing():
                print("Updating song info...")
                track = current_track['item']
                self.update_song_label_spotify(track)
                self.update_album_cover_label_spotify(track)
                self.update_stats_label_openAI(track)
            # Remove song data if no song is playing
            else:
                self.song_label.setText("No song is currently playing.")
                self.stats_label.setText("No song data available.")
                if hasattr(self, 'album_cover'):
                    self.album_cover.setVisible(False)
            self.update_status()
        except Exception as e:
            self.song_label.setText("Error fetching song info.")

    def update_song_label_spotify(self, track):
        """
        Updates the song label with the current song's name and artist.
        """
        track_name = track['name']
        artist = ", ".join(artist['name'] for artist in track['artists'])
        self.song_label.setText(f"Song: {track_name} by {artist}")
        self.song_label.setWordWrap(True)
        max_title_width = int(self.width() * 0.75)
        self.song_label.setMaximumWidth(max_title_width)

    def update_album_cover_label_spotify(self, track):
        """
        Updates the album cover whenever update_song_info is called. TODO: make this a separate thread
        """
        # Fetch album cover
        album_cover_url = track['album']['images'][0]['url']
        pixmap = QPixmap()
        pixmap.loadFromData(requests.get(album_cover_url).content)
        self.album_cover.setPixmap(pixmap.scaled(260, 260, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.album_cover.setVisible(True)

    def update_stats_label_openAI(self, track):
        """
        Updates the stats label with an AI overview of the song's tempo and bpm.
        """
        track_name = track['name']
        artist = ", ".join(artist['name'] for artist in track['artists'])
        response = self.openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "developer", "content": "You are a music expert who provides accurate song information from Spotify and Tunebat as a space-separated list."},
                      {"role": "user", "content": f"what is the key and bpm of {track_name} by {artist}? provide your response in exactly the same format as the following, with no additional response text: Cmaj 100bpm"}],
            max_tokens=10
        )
        self.stats_label.setText(response.choices[0].message.content)

    def update_status(self):
        """ 
        Updates the status of the song playing.
        """
        if self.track_playing():
            current_track = self.get_playback_state()
            self.last_song_id = current_track['item']['id']
            self.song_playing = True
        else:
            self.last_song_id = 0
            self.song_playing = False

    def track_playing(self):
        """
        Returns True if a track is currently playing, False otherwise.
        """
        current_track = self.get_playback_state()
        return current_track and current_track['is_playing']
    
    def track_changed(self):
        """
        Checks if the current playback state has changed.

        Returns:
            True if the playback state has changed, False otherwise.
        """
        current_track = self.get_playback_state()
        if current_track and current_track['is_playing'] != self.song_playing:
            return True
        else:
            current_song_id = current_track['item']['id']
            return current_song_id != self.last_song_id
        
    def get_playback_state(self):
        """
        Returns the current playback state of the Spotify client.

        Returns:
            The current playback state of the Spotify client.
        """
        return get_spotify_client().current_playback()
    
    def run(self):
        """
        Primary playback loop. Runs using two QTimer objects to periodically update the song information, with separate timers for the Spotify and OpenAI APIs.
        """
        # Variables to track changes in playback state
        self.last_song_id = 0
        self.song_playing = False

        # Timer to update song info
        self.spotifyAPI_timer = QTimer()
        self.spotifyAPI_timer.timeout.connect(self.update_song_info)
        self.spotifyAPI_timer.start(2000) # Call Spotify API every 2 seconds
        self.update_song_info() # Initial fetch

# Main application loop
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SpotifyApp()
    pywinstyles.apply_style(window, "dark")
    window.show()
    sys.exit(app.exec_())