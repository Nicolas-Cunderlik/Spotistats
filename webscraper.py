from bs4 import BeautifulSoup
import requests
import cloudscraper

def get_tunebat_data(track_id):
    """
    Returns the key, BPM, and energy of a song from Tunebat.

    Args:
        Content of the Tunebat page for the song.

    Returns:
        A dictionary containing the key, BPM, and energy of the song.
    """
    scraper = cloudscraper.create_scraper()
    url = f"https://tunebat.com/Info/_/{track_id}"
    result = scraper.get(url)
    soup = BeautifulSoup(result.content, "html.parser")
    stats = soup.find_all("h3", class_="ant-typography")