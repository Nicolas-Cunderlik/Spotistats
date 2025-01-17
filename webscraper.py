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

BASE_URL = "https://www.tunebat.com/Info/_/"

def get_tunebat_data(track_id):
    """
    Returns the key, BPM, and energy of a song from Tunebat.

    Args:
        Content of the Tunebat page for the song.

    Returns:
        A dictionary containing the key, BPM, and energy of the song.
    """
    # Construct the dynamic URL
    dynamic_url = f"{BASE_URL}{track_id}"
    
    # Pass the URL through ScraperAPI
    scraperapi_url = f"http://api.scraperapi.com?api_key={SCRAPER_API_KEY}&url={dynamic_url}"
    
    # Fetch the page content
    response = requests.get(scraperapi_url)
    
    # Check if the response is successful
    if response.status_code == 200:
        soup = BeautifulSoup(response.content, "html.parser")
        
        # Example: Extract song stats (replace with actual logic for your target content)
        stats = soup.find_all("h3", class_="ant-typography")
        print(stats)
        return stats
    else:
        print(f"Error: Unable to fetch data. Status code: {response.status_code}")
        return None