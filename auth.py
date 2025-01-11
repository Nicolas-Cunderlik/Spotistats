import spotipy
from spotipy.oauth2 import SpotifyOAuth

SPOTIPY_CLIENT_ID = "1c44785dc48c495c9cf8d3dea314c26f"
SPOTIPY_CLIENT_SECRET = "2f083954a51944a785abdb2d99a2455d"
SPOTIPY_REDIRECT_URI = "http://localhost:4000/callback"

# Spotify authentication and client setup
def get_spotify_client():
    """
    Returns a Spotify client object for interacting with the Spotify API.

    The client will use the client ID, client secret, and redirect URI
    specified by the SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET, and
    SPOTIPY_REDIRECT_URI environment variables, respectively.

    The client will use the "user-read-playback-state" scope, allowing
    it to read the user's currently playing track.

    Returns:
        A Spotify client object.
    """
    scope = "user-read-playback-state"
    sp_oauth = SpotifyOAuth(client_id=SPOTIPY_CLIENT_ID,
                        client_secret=SPOTIPY_CLIENT_SECRET,
                        redirect_uri=SPOTIPY_REDIRECT_URI,
                        scope=scope)
    return spotipy.Spotify(auth_manager=sp_oauth)