import requests
import json
import os
import re
import logging
from typing import List, Dict, Any
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def read_config(filename):
    with open(filename, 'r') as file:
        return json.load(file)

# Read configuration from file
config = read_config('config.json')

# Configuration variables
SONARR_IP = config.get('SONARR_IP')
API_KEY = config.get('API_KEY')
TMDB_API_KEY = config.get('TMDB_API_KEY')
PROFILE_4k_NAME = config.get('PROFILE_4k_NAME')
PROFILE_720p_NAME = config.get('PROFILE_720p_NAME')
PROFILE_1080p_NAME = config.get('PROFILE_1080p_NAME')
DAYS_THRESHOLD = config.get('DAYS_THRESHOLD')
RATING_THRESHOLD_1080P = config.get('RATING_THRESHOLD_1080P')
RATING_THRESHOLD_4K = config.get('RATING_THRESHOLD_4K')
PROFILE_4k_GENRES = set(config.get('PROFILE_4k_GENRES', []))  # Convert to set
PROFILE_720p_GENRES = set(config.get('PROFILE_720p_GENRES', []))  # Convert to set
CACHE_DIR = config.get('CACHE_DIR')
EPISODE_THRESHOLD_1080P = config.get ('EPISODE_THRESHOLD_1080P')

# Constants for API endpoints
SONARR_API_URL = f"{config.get('SONARR_IP')}/api/v3"
TMDB_API_URL = "https://api.themoviedb.org/3"

# Remove the year from the show title if present.
def strip_year_from_title(title: str) -> tuple[str, int]:
    match = re.search(r"\((\d{4})\)$", title)
    if match:
        year = int(match.group(1))
        title_cleaned = re.sub(r"\s*\(\d{4}\)$", "", title).strip()
        return title_cleaned, year
    return title, None

# Fetch the TMDB rating for a given show title, using cached data if available.
def get_tmdb_rating(show_title: str) -> float:
    show_title_cleaned, year = strip_year_from_title(show_title)
    cache_dir = os.path.join(CACHE_DIR, "tmdb_cache")
    os.makedirs(cache_dir, exist_ok=True)
    
    params = {"api_key": TMDB_API_KEY, "query": show_title_cleaned}
    if year:
        params["first_air_date_year"] = year

    response = requests.get(f"{TMDB_API_URL}/search/tv", params=params)
    response.raise_for_status()
    data = response.json()

    if data["total_results"] == 0:
        logging.warning(f"No results found for '{show_title_cleaned}' on TMDb.")
        return 0
    
    show_id = data["results"][0]["id"]
    cache_file = os.path.join(cache_dir, f"{show_id}.json")

    # Check if cached rating exists and is recent
    if os.path.exists(cache_file):
        with open(cache_file, "r") as f:
            cached_data = json.load(f)
            if "timestamp" in cached_data and "rating" in cached_data:
                timestamp = datetime.fromisoformat(cached_data["timestamp"])
                if datetime.now() - timestamp < timedelta(days=7):
                    logging.info(f"Using cached rating for TMDB ID '{show_id}'")
                    return float(cached_data["rating"])
    
    response = requests.get(f"{TMDB_API_URL}/tv/{show_id}", params={"api_key": TMDB_API_KEY})
    response.raise_for_status()
    show_data = response.json()
    rating = show_data["vote_average"]
    
    # Cache the rating
    cache_data = {"rating": rating, "timestamp": datetime.now().isoformat()}
    with open(cache_file, "w") as f:
        json.dump(cache_data, f)
    
    return rating

    
    # Cache the rating
    cache_data = {"rating": rating, "timestamp": datetime.now().isoformat()}
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(cache_file, "w") as f:
        json.dump(cache_data, f)
    
    return rating

# Fetch quality profiles from Sonarr.
def get_profiles() -> List[Dict[str, Any]]:
    headers = {"X-Api-Key": API_KEY}
    response = requests.get(f"{SONARR_API_URL}/qualityprofile", headers=headers)
    response.raise_for_status()
    return response.json()

# Get the profile ID for a given profile name.
def get_profile_id(profile_name: str, profiles: List[Dict[str, Any]]) -> int:
    for profile in profiles:
        if profile['name'].lower() == profile_name.lower():
            return profile['id']
    raise ValueError(f"Profile name '{profile_name}' not found")

# Fetch all shows from Sonarr.
def get_shows() -> List[Dict[str, Any]]:
    headers = {"X-Api-Key": API_KEY}
    response = requests.get(f"{SONARR_API_URL}/series", headers=headers)
    response.raise_for_status()
    return response.json()

# Fetch detailed series information from Sonarr.
def get_series(series_id: int) -> Dict[str, Any]:
    headers = {"X-Api-Key": API_KEY}
    response = requests.get(f"{SONARR_API_URL}/series/{series_id}", headers=headers)
    response.raise_for_status()
    return response.json()

# Update the quality profile for a given series.
def update_profile(series_id: int, profile_id: int) -> Dict[str, Any]:
    series_data = get_series(series_id)
    series_data['qualityProfileId'] = profile_id
    headers = {"X-Api-Key": API_KEY}
    response = requests.put(f"{SONARR_API_URL}/series/{series_id}", headers=headers, json=series_data)
    response.raise_for_status()
    return response.json()

# Fetch genres for a given series.
def get_genres(series_id: int) -> List[str]:
    headers = {"X-Api-Key": API_KEY}
    response = requests.get(f"{SONARR_IP}/api/v3/series/{series_id}", headers=headers)
    response.raise_for_status()
    series_data = response.json()
    return series_data.get("genres", [])

# Fetch the total number of episodes for a given show.
def get_number_of_episodes(show_id: int) -> int:
    headers = {"X-Api-Key": API_KEY}
    response = requests.get(f"{SONARR_API_URL}/series/{show_id}", headers=headers)
    response.raise_for_status()
    data = response.json()
    total_episodes = sum(season['statistics']['episodeCount'] for season in data['seasons'])
    return total_episodes

def determine_profile_id(status: str, tmdb_rating: float, last_airing_date: datetime, genres: List[str], num_episodes: int, threshold_date: datetime, profile_4k_id: int, profile_1080p_id: int, profile_720p_id: int) -> int:
    genres_set = set(genres)
    if (status.lower() == 'ended' and 
        tmdb_rating >= RATING_THRESHOLD_1080P and 
        num_episodes < EPISODE_THRESHOLD_1080P and
        PROFILE_4k_GENRES.intersection(genres_set)):
        return profile_1080p_id
    elif (status.lower() == 'ended' and 
          last_airing_date > threshold_date and
          PROFILE_4k_GENRES.intersection(genres_set)):
        return profile_1080p_id
    elif (status.lower() == 'continuing' and 
          tmdb_rating >= RATING_THRESHOLD_4K and
          PROFILE_4k_GENRES.intersection(genres_set)):
        return profile_4k_id
    elif (status.lower() == 'continuing' and 
          tmdb_rating >= RATING_THRESHOLD_1080P and
          num_episodes < EPISODE_THRESHOLD_1080P and
          PROFILE_4k_GENRES.intersection(genres_set)):
        return profile_1080p_id
    elif ((last_airing_date > threshold_date and status.lower() == 'ended') or 
          tmdb_rating < RATING_THRESHOLD_1080P or 
          (PROFILE_720p_GENRES.intersection(genres_set) and not PROFILE_4k_GENRES.intersection(genres_set))):
        return profile_720p_id
    else:
        return profile_720p_id  # Default to profile 720p if no other condition is met

def main():
    profiles = get_profiles()
    profile_4k_id = get_profile_id(PROFILE_4k_NAME, profiles)
    profile_720p_id = get_profile_id(PROFILE_720p_NAME, profiles)
    profile_1080p_id = get_profile_id(PROFILE_1080p_NAME, profiles)
    
    shows = get_shows()
    threshold_date = datetime.now() - timedelta(days=DAYS_THRESHOLD)

    for show in shows:
        last_airing = show.get("previousAiring")
        show_title = show['title']
        tmdb_rating = get_tmdb_rating(show_title)
        genres = get_genres(show['id'])
        status = show['status']
        show_id = show['id']
        num_episodes = get_number_of_episodes(show_id)
        
        if last_airing:
            last_airing_date = datetime.strptime(last_airing, "%Y-%m-%dT%H:%M:%SZ")
        else:
            last_airing_date = datetime.min

        profile_id = determine_profile_id(status, tmdb_rating, last_airing_date, genres, num_episodes, threshold_date, profile_4k_id, profile_1080p_id, profile_720p_id)

        logging.info(f"Updating show '{show_title}' (ID: {show['id']}) to profile ID {profile_id}")
        update_profile(show['id'], profile_id)

if __name__ == "__main__":
    main()
