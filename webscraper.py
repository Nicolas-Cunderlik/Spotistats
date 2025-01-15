from bs4 import BeautifulSoup
import requests

def get_tunebat_data(song_id):
    """
    Returns the key, BPM, and energy of a song from Tunebat.

    Args:
        song_name: The name of the song.

    Returns:
        A dictionary containing the key, BPM, and energy of the song.
    """
    url = f"https://tunebat.com/Info/_/{song_id}"
    result = requests.get(url)
    soup = BeautifulSoup(result.content, "html.parser")