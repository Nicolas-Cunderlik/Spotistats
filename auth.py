import spotipy
from openai import OpenAI
from spotipy.oauth2 import SpotifyOAuth

# Sensitive information
auth_vars = {}
with open("venv/auth.env", 'r') as file:
    for line in file:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, value = line.split('=', 1)
        auth_vars[key.strip()] = value.strip()
        
SPOTIPY_CLIENT_ID = auth_vars.get('SPOTIPY_CLIENT_ID')
SPOTIPY_CLIENT_SECRET = auth_vars.get('SPOTIPY_CLIENT_SECRET')
SPOTIPY_REDIRECT_URI = auth_vars.get('SPOTIPY_REDIRECT_URI')
OPENAI_API_KEY = auth_vars.get('OPENAI_API_KEY')

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

def get_openai_client():
    """
    Returns the OpenAI client from the environment variable API_KEY.

    Returns:
        The OpenAI API key as a string.
    """
    return OpenAI(
        api_key=OPENAI_API_KEY
    )

