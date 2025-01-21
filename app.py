"""
Filename: app.py
Author: Nicolas Cunderlik
Date: 2025
Description: A PyQt5 application for displaying song information and statistics from Spotify.

Copyright © 2025 Nicolas Cunderlik. All Rights Reserved.

This source code is the property of the author/owner and is protected under
copyright law. Unauthorized copying, modification, distribution, or any use
of this file, in part or in full, without prior written permission from the
author/owner, is strictly prohibited.

For inquiries, contact: nicolas7cunderlik@gmail.com
"""

import sys
from PyQt5.QtCore import * 
from PyQt5.QtGui import * 
from PyQt5.QtWidgets import *
import pywinstyles.py_win_style
import requests

from auth import *
from webscraper import *
from miscutil import *

class SpotifyApp(QWidget):
    def __init__(self):
        """
        Initializes the SpotifyApp window with title and geometry settings, 
        sets up the layout and widgets for displaying song information and stats, 
        initializes the Spotify client, and starts a timer to periodically update 
        the song information every 2 seconds.
        """
        super().__init__()

        # Window base settings
        self.setWindowTitle("Spotistats")
        self.setWindowIcon(QIcon('SpotifyAppLogo.png'))
        self.setGeometry(50, 50, 300, 600)
        self.setFixedSize(300, 650) # TODO: Maybe make this resizable?
        self.setStyleSheet("background-color: black;")

        # Layout and widgets
        self.layout = QVBoxLayout()

        # Frames
        self.title_frame = QFrame()
        self.stats_frame = QFrame()
        self.song_name_and_artist_frame = QFrame()
        self.stats_label_frame = QFrame()
        self.ai_label_frame = QFrame()
        
        # Fixed heights
        self.title_frame.setFixedHeight(100)
        self.song_name_and_artist_frame.setFixedHeight(80)
        self.stats_label_frame.setFixedWidth(70)
        self.ai_label_frame.setFixedWidth(180)

        # Set frame styles for title and stats
        self.title_frame.setStyleSheet("background-color: #141414; border-radius: 10px;")
        self.stats_frame.setStyleSheet("background-color: #141414; border-radius: 10px;")
        self.stats_label_frame.setStyleSheet("background-color: #292929; border-radius: 8px;")
        self.ai_label_frame.setStyleSheet("background-color: #292929; border-radius: 8px;")
        
        self.title_layout = QVBoxLayout()
        self.body_layout = QVBoxLayout()
        self.body_stats_layout = QHBoxLayout() # Changed to QVBoxLayout to stack the labels vertically
        self.song_name_and_artist_layout = QVBoxLayout()

        self.title_label = QLabel("SPOTISTATS")
        self.stats_label = QLabel("Stats loading...")
        self.ai_label = QLabel("AI Suggestions loading...")

        self.album_cover_label = ClickableLabel(self)
        self.album_cover_label.setPixmap(QPixmap(260, 260))
        self.album_cover_label.clicked.connect(self.showFullScreenCover)

        self.song_name_label = QLabel("Song name loading...")
        self.artist_label = QLabel("Artist name loading...")

        title_font_id = QFontDatabase.addApplicationFont("KdamThmorPro-Regular.ttf")
        font_families = QFontDatabase.applicationFontFamilies(title_font_id)
        iceberg_font = QFont(font_families[0], 30)
        self.title_label.setFont(iceberg_font)
        self.stats_label.setFont(QFont(font_families[0], 12))
        self.ai_label.setFont(QFont(font_families[0], 12))

        self.title_label.setStyleSheet("color: white;")
        self.song_name_label.setStyleSheet("color: white; font-size: 24px;")
        self.artist_label.setStyleSheet("color: #AAAAAA; font-size: 20px;")
        self.stats_label.setStyleSheet("color: white; font-size: 12px;")
        self.ai_label.setStyleSheet("color: white; font-size: 12px;")

        self.title_layout.addWidget(self.title_label)
        
        # Add stats_label and ai_label to their respective frames
        self.stats_label_layout = QVBoxLayout()
        self.stats_label_layout.addWidget(self.stats_label)
        self.stats_label_frame.setLayout(self.stats_label_layout)
        
        self.ai_label_layout = QVBoxLayout()
        self.ai_label_layout.addWidget(self.ai_label)
        self.ai_label_frame.setLayout(self.ai_label_layout)
        
        # Add the frames to the body_stats_layout
        self.body_stats_layout.addWidget(self.stats_label_frame)
        self.body_stats_layout.addSpacing(4)
        self.body_stats_layout.addWidget(self.ai_label_frame)
        
        self.body_layout.addLayout(self.body_stats_layout)
        self.body_layout.addSpacing(6)
        self.body_layout.addWidget(self.album_cover_label)
        self.song_name_and_artist_layout.addWidget(self.song_name_label)
        self.song_name_and_artist_layout.addWidget(self.artist_label)

        self.title_layout.setAlignment(Qt.AlignCenter)
        self.song_name_and_artist_layout.setAlignment(Qt.AlignCenter)

        self.song_name_label.setAlignment(Qt.AlignCenter)
        self.artist_label.setAlignment(Qt.AlignCenter)
        self.stats_label.setAlignment(Qt.AlignCenter)
        self.ai_label.setAlignment(Qt.AlignCenter)

        self.title_frame.setLayout(self.title_layout)
        self.stats_frame.setLayout(self.body_layout)
        self.song_name_and_artist_frame.setLayout(self.song_name_and_artist_layout)

        self.layout.addWidget(self.title_frame)
        self.layout.addSpacing(6)
        self.layout.addWidget(self.stats_frame)
        self.layout.addSpacing(6)
        self.layout.addWidget(self.song_name_and_artist_frame)

        self.setLayout(self.layout)

        # Necessary clients
        self.spotify = getSpotifyClient()
        self.openai = getOpenAIClient()
        self.run()

    def updateSongInfo(self):
        """
        Updates the song and stats labels with the current song's name,
        artist, tempo, energy, and danceability. If no song is currently
        playing, or if there is an error fetching the song info, updates
        the labels with an appropriate message.

        This function is called every second using a QTimer.
        """
        if not self.spotify or not self.openai or not self.trackChanged():
            return
        try:
            current_track = self.getCurrentPlayback()
            if self.trackPlaying():
                print("Updating song info...")
                track = current_track['item']
                self.updateSongLabel(track)
                self.updateAlbumCoverLabel(track)
                self.updateStatsLabel(track)
                self.updateSuggestionsLabel(track)
            # Remove song data if no song is playing
            else:
                self.artist_label.setText("- - - - -")
                self.song_name_label.setText("No song playing.")
                self.stats_label.setText("- - - - -")
                self.ai_label.setText("AI Suggestions loading...")
                if hasattr(self, 'album_cover'):
                    self.album_cover_label.setVisible(False)
            self.updateStatus()
        except Exception as e:
            self.artist_label.setText(str(e))

    def updateSongLabel(self, track):
        """
        Updates the song label with the current song's name and artist.
        """
        # Set label text
        track_name = track['name']
        artist = ", ".join(artist['name'] for artist in track['artists']) # This just reeks of AI lmao
        self.song_name_label.setText(f"{track_name}")
        self.artist_label.setText(f"{artist}")

        # Wrap text and set maximum width
        max_title_width = int(self.width() * 0.95)
        self.artist_label.setMaximumWidth(max_title_width)
        self.song_name_label.setMaximumWidth(max_title_width)

        # Set text alignment
        self.artist_label.setAlignment(Qt.AlignCenter)
        self.song_name_label.setAlignment(Qt.AlignCenter)

    def updateAlbumCoverLabel(self, track):
        """
        Updates the album cover whenever update_song_info is called. TODO: make this a separate thread
        """
        # Fetch album cover
        album_cover_url = track['album']['images'][0]['url']
        pixmap = QPixmap(260, 260)
        pixmap.loadFromData(requests.get(album_cover_url).content)
        pixmap = pixmap.scaled(260, 260, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        
        # Create rounding for the pixmap
        rounded = QPixmap(260, 260)
        rounded.fill(QColor("transparent"))
        
        # Draw rounded rectangle
        painter = QPainter(rounded)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(pixmap))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(0, 0, 260, 260, 8, 8)
        painter.end()
        
        self.album_cover_label.setPixmap(rounded)
        self.album_cover_label.setVisible(True)

    def updateStatsLabel(self, track):
        """
        Updates the stats label with web-scraped song statistics. TODO: make this a separate thread
        """
        #NOTE: Not many API credits! Need to find alternative if this is ever going to go anywhere
        current_song_id = track['id']
        stats = scrapeSongData(current_song_id)
        key = stats[1].text # Key is the second element in the list
        bpm = stats[3].text # BPM is the fourth element in the list
        self.stats_label.setText(f"KEY\n{key}\n\nBPM\n{bpm}")
        
    def updateSuggestionsLabel(self, track):
        """
        Updates the suggestions label with AI-generated sound design suggestions for the song.
        """
        track_name = track['name']
        artist = ", ".join(artist['name'] for artist in track['artists'])
        stats = scrapeSongData(track['id'])
        key = stats[1].text # Key is the second element in the list
        bpm = stats[3].text # BPM is the fourth element in the list
        response = self.openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "developer", "content": "You are a music expert who provides accurate sound design suggestions to imitate to vibe of songs."},
                      {"role": "user", "content": f"Given the song '{track_name}' by {artist}, with key {key} and BPM {bpm}, generate three chord progressions, using the following format, that would imitate the vibe of the song (your output will be parsed at each underscore). Do not provide any additional information/words: Cmaj-Fmaj-Gmaj7-Amaj, Dsus-Gmin-Amaj11-Bmin, Fmaj-Gmaj7-Asus-Bbmaj"}],
            max_tokens=50
        )
        chord_progressions = response.choices[0].message.content.split(", ")
        self.ai_label.setText(f"AI Chord Suggestions\n\n{chord_progressions[0]}\n{chord_progressions[1]}\n{chord_progressions[2]}")

    def showFullScreenCover(self):
        # Show a fullscreen window with the larger image
        track = self.getCurrentPlayback()['item']
        album_cover_url = track['album']['images'][0]['url']
        data = requests.get(album_cover_url).content
        self.fullscreen_window = FullscreenImageWindow(data)
        self.fullscreen_window.show()

    def updateStatus(self):
        """ 
        Updates the status of the song playing.
        """
        if self.trackPlaying():
            current_track = self.getCurrentPlayback()
            self.last_song_id = current_track['item']['id']
            self.song_playing = True
        else:
            self.last_song_id = 0
            self.song_playing = False

    def trackPlaying(self):
        """
        Returns True if a track is currently playing, False otherwise.
        """
        current_track = self.getCurrentPlayback()
        return current_track and current_track['is_playing']
    
    def trackChanged(self):
        """
        Checks if the current playback state has changed.

        Returns:
        True if the playback state has changed, False otherwise.
        """
        current_track = self.getCurrentPlayback()
        if current_track and current_track['is_playing'] != self.song_playing:
            return True
        elif current_track:
            current_song_id = current_track['item']['id']
            return current_song_id != self.last_song_id
        else:
            return False
        
    def getCurrentPlayback(self):
        """
        Gets the current playback state of the Spotify client.

        Returns:
        The current playback state of the Spotify client.
        """
        return self.spotify.current_playback()
    
    def run(self):
        """
        Primary playback loop. Runs using a QTimer to update the song information every second, only if needed.
        """
        # Variables to track changes in playback state
        self.last_song_id = 0
        self.song_playing = False

        # Timer to update song info
        self.spotifyAPI_timer = QTimer()
        self.spotifyAPI_timer.timeout.connect(self.updateSongInfo)
        self.spotifyAPI_timer.start(1000) # Update every second if new song playing
        self.updateSongInfo() # Initial fetch

# Main application loop
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SpotifyApp()
    pywinstyles.apply_style(window, "dark")
    window.show()
    sys.exit(app.exec_())