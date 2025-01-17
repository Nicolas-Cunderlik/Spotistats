"""
Filename: app.py
Author: Nicolas Cunderlik
Date: 2025
Description: A PyQt5 application for displaying song information and statistics from Spotify and Tunebat.

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
        self.setStyleSheet("background-color: #000000;")

        # Layout and widgets
        self.layout = QVBoxLayout()

        # Frames
        self.title_frame = QFrame()
        self.stats_frame = QFrame()
        self.song_name_and_artist_frame = QFrame()
        
        # Fixed heights
        self.title_frame.setFixedHeight(100)
        self.song_name_and_artist_frame.setFixedHeight(80)

        # Set frame styles for title and stats
        self.title_frame.setStyleSheet("background-color: #141414; border-radius: 10px;")
        self.stats_frame.setStyleSheet("background-color: #141414; border-radius: 10px;")
        
        self.title_layout = QVBoxLayout()
        self.body_layout = QVBoxLayout()
        self.body_stats_layout = QHBoxLayout() # Goes inside body_layout
        self.song_name_and_artist_layout = QVBoxLayout()

        self.title_label = QLabel("SPOTISTATS")
        self.stats_label = QLabel("Stats loading...")
        self.ai_label = QLabel("AI Suggestions loading...")
        self.album_cover_label = QLabel() # FIXME: make this image scale
        self.album_cover_label.setPixmap(QPixmap(260, 260))
        self.song_name_label = QLabel("Song name loading...")
        self.artist_label = QLabel("Artist name loading...")

        title_font_id = QFontDatabase.addApplicationFont("KdamThmorPro-Regular.ttf")
        font_families = QFontDatabase.applicationFontFamilies(title_font_id)
        iceberg_font = QFont(font_families[0], 30)
        self.title_label.setFont(iceberg_font)

        self.title_label.setStyleSheet("color: #FFFFFF;")
        self.song_name_label.setStyleSheet("color: #FFFFFF; font-size: 24px;")
        self.artist_label.setStyleSheet("color: #AAAAAA; font-size: 20px;")
        self.stats_label.setStyleSheet("color: #FFFFFF;")
        self.ai_label.setStyleSheet("color: #FFFFFF;")

        self.title_layout.addWidget(self.title_label)
        self.body_stats_layout.addWidget(self.stats_label)
        self.body_stats_layout.addWidget(self.ai_label)
        self.body_layout.addLayout(self.body_stats_layout)
        self.body_layout.addSpacing(6)
        self.body_layout.addWidget(self.album_cover_label)
        self.song_name_and_artist_layout.addWidget(self.song_name_label)
        self.song_name_and_artist_layout.addWidget(self.artist_label)

        self.title_layout.setAlignment(Qt.AlignCenter)
        self.song_name_and_artist_layout.setAlignment(Qt.AlignCenter)

        self.song_name_label.setAlignment(Qt.AlignCenter)
        self.artist_label.setAlignment(Qt.AlignCenter)

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
            current_track = self.get_current_playback()
            if self.track_playing():
                print("Updating song info...")
                track = current_track['item']
                self.update_song_label_spotify(track)
                self.update_album_cover_label_spotify(track)
                self.update_stats_label_bs4(track)
            # Remove song data if no song is playing
            else:
                self.artist_label.setText("- - - - -")
                self.song_name_label.setText("No song playing.")
                self.stats_label.setText("- - - - -")
                if hasattr(self, 'album_cover'):
                    self.album_cover_label.setVisible(False)
            self.update_status()
        except Exception as e:
            self.artist_label.setText(str(e))

    def update_song_label_spotify(self, track):
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

    def update_album_cover_label_spotify(self, track):
        """
        Updates the album cover whenever update_song_info is called. TODO: make this a separate thread
        """
        # Fetch album cover
        album_cover_url = track['album']['images'][0]['url']
        pixmap = QPixmap()
        pixmap.loadFromData(requests.get(album_cover_url).content)
        self.album_cover_label.setPixmap(pixmap.scaled(260, 260, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.album_cover_label.setVisible(True)

    def update_stats_label_bs4(self, track):
        """
        Updates the stats label with scraped statistics from TuneBat. TODO: make this a separate thread
        """
        #NOTE: Not many API credits! Need to find alternative to TuneBat if this is ever going to go anywhere
        current_song_id = track['id']
        stats = get_tunebat_data(current_song_id)
        key = stats[1].text # Key is the second element in the list
        bpm = stats[3].text # BPM is the fourth element in the list
        self.stats_label.setText(f"Key: {key} | BPM: {bpm}")
        

    #def update_suggestions_label_openai(self, track):
    #    """
    #    Updates the suggestions label with an AI-generated suggestion for the song.
    #    """
    #    track_name = track['name']
    #    artist = ", ".join(artist['name'] for artist in track['artists'])
    #    response = self.openai.chat.completions.create(
    #        model="gpt-4o-mini",
    #        messages=[{"role": "developer", "content": "You are a music expert who provides accurate song information from Spotify and Tunebat as a space-separated list."},
    #                  {"role": "user", "content": f"what is the key and bpm of {track_name} by {artist}? provide your response in exactly the same format as the following, with no additional response text: Cmaj 100bpm"}],
    #        max_tokens=10
    #    )
    #    self.stats_label.setText(response.choices[0].message.content)

    def update_status(self):
        """ 
        Updates the status of the song playing.
        """
        if self.track_playing():
            current_track = self.get_current_playback()
            self.last_song_id = current_track['item']['id']
            self.song_playing = True
        else:
            self.last_song_id = 0
            self.song_playing = False

    def track_playing(self):
        """
        Returns True if a track is currently playing, False otherwise.
        """
        current_track = self.get_current_playback()
        return current_track and current_track['is_playing']
    
    def track_changed(self):
        """
        Checks if the current playback state has changed.

        Returns:
            True if the playback state has changed, False otherwise.
        """
        current_track = self.get_current_playback()
        if current_track and current_track['is_playing'] != self.song_playing:
            return True
        elif current_track:
            current_song_id = current_track['item']['id']
            return current_song_id != self.last_song_id
        else:
            return False
        
    def get_current_playback(self):
        """
        Returns the current playback state of the Spotify client.

        Returns:
            The current playback state of the Spotify client.
        """
        return self.spotify.current_playback()
    
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
        self.spotifyAPI_timer.start(1000) # Update every second if new song playing
        self.update_song_info() # Initial fetch

# Main application loop
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SpotifyApp()
    pywinstyles.apply_style(window, "dark")
    window.show()
    sys.exit(app.exec_())