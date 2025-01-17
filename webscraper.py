"""
Filename: webscraper.py
Author: Nicolas Cunderlik
Date: 2025
Description: Web scraping tools for extracting song data from Tunebat.

Copyright © 2025 Nicolas Cunderlik. All Rights Reserved.

This source code is the property of the author/owner and is protected under
copyright law. Unauthorized copying, modification, distribution, or any use
of this file, in part or in full, without prior written permission from the
author/owner, is strictly prohibited.

For inquiries, contact: nicolas7cunderlik@gmail.com
"""

from bs4 import BeautifulSoup
import requests
from auth import *

def get_tunebat_data(track_id):
    """
    Returns the key, BPM, and energy of a song from Tunebat.

    Args:
        Content of the Tunebat page for the song.

    Returns:
        A dictionary containing the key, BPM, and energy of the song.
    """
    dynamic_url = f"{BASE_URL}{track_id}"
    scraperapi_url = f"http://api.scraperapi.com?api_key={SCRAPER_API_KEY}&url={dynamic_url}"
    response = requests.get(scraperapi_url)
    if response.status_code == 200:
        soup = BeautifulSoup(response.content, "html.parser")
        stats = soup.find_all("h3", class_="ant-typography")
        return stats
    else:
        print(f"Error: Unable to fetch data. Status code: {response.status_code}")
        return None