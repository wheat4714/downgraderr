import requests
import json
import os
import re
from datetime import datetime, timedelta
import json

def read_config(filename):
    with open(filename, 'r') as file:
        return json.load(file)

config = read_config('config.json')

SONARR_IP = config.get('SONARR_IP')
API_KEY = config.get('API_KEY')
TMDB_API_KEY = config.get('TMDB_API_KEY')
PROFILE_4k_NAME = config.get('PROFILE_4k_NAME')
PROFILE_720p_NAME = config.get('PROFILE_720p_NAME')
PROFILE_1080p_NAME = config.get('PROFILE_1080p_NAME')
DAYS_THRESHOLD = config.get('DAYS_THRESHOLD')
RATING_THRESHOLD_1080P = config.get('RATING_THRESHOLD_1080P')
RATING_THRESHOLD_4K = config.get('RATING_THRESHOLD_4K')
PROFILE_4k_GENRES = config.get('PROFILE_4k_GENRES')
PROFILE_720p_GENRES = config.get('PROFILE_720p_GENRES')
CACHE_DIR = config.get('CACHE_DIR')
EPISODE_THRESHOLD_1080P = config.get ('EPISODE_THRESHOLD_1080P')

def strip_year_from_title(title):
    return re.sub(r"\s*\(\d{4}\)$", "", title).strip()

def get_tmdb_rating(show_title):
    show_title_cleaned = strip_year_from_title(show_title)
    cache_file = os.path.join(CACHE_DIR, f"{show_title_cleaned}.json")
    
    # Check if cached rating exists and is recent
    if os.path.exists(cache_file):
        with open(cache_file, "r") as f:
            data = json.load(f)
            if "timestamp" in data and "rating" in data:
                timestamp = datetime.fromisoformat(data["timestamp"])
                if datetime.now() - timestamp < timedelta(days=7):
                    print(f"Using cached rating for '{show_title_cleaned}'")
                    return float(data["rating"])
    
    url = f"https://api.themoviedb.org/3/search/tv"
    params = {"api_key": TMDB_API_KEY, "query": show_title_cleaned}
    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()

    if data["total_results"] == 0:
        print(f"No results found for '{show_title_cleaned}' on TMDb.")
        return 0
    
    show_id = data["results"][0]["id"]
    url = f"https://api.themoviedb.org/3/tv/{show_id}"
    params = {"api_key": TMDB_API_KEY}
    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()
    rating = data["vote_average"]
    
    # Cache the rating
    cache_data = {"rating": rating, "timestamp": datetime.now().isoformat()}
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(cache_file, "w") as f:
        json.dump(cache_data, f)
    
    return rating


def get_profiles():
    url = f"{SONARR_IP}/api/v3/qualityprofile"
    headers = {"X-Api-Key": API_KEY}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()

def get_profile_id(profile_name, profiles):
    for profile in profiles:
        if profile['name'].lower() == profile_name.lower():
            return profile['id']
    raise ValueError(f"Profile name '{profile_name}' not found")

def get_shows():
    url = f"{SONARR_IP}/api/v3/series"
    headers = {"X-Api-Key": API_KEY}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()

def get_series(series_id):
    url = f"{SONARR_IP}/api/v3/series/{series_id}"
    headers = {"X-Api-Key": API_KEY}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()

def update_profile(series_id, profile_id):
    # Get the full series data
    series_data = get_series(series_id)
    # Update the quality profile ID
    series_data['qualityProfileId'] = profile_id
    
    url = f"{SONARR_IP}/api/v3/series/{series_id}"
    headers = {"X-Api-Key": API_KEY}
    response = requests.put(url, headers=headers, json=series_data)
    response.raise_for_status()
    return response.json()

def get_genres(series_id):
    url = f"{SONARR_IP}/api/v3/series/{series_id}"
    headers = {"X-Api-Key": API_KEY}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    series_data = response.json()
    return series_data.get("genres", [])

# Function to query Sonarr API and get the number of episodes for a show
def get_number_of_episodes(show_id):
    sonarr_url = f"{SONARR_IP}/api/v3/series/{show_id}"
    headers = {"X-Api-Key": API_KEY}

    response = requests.get(sonarr_url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        total_episodes = sum(season['statistics']['episodeCount'] for season in data['seasons'])
        return total_episodes
    else:
        # Handle error response
        print("Error:", response.text)  # Print error response for debugging
        return None

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
        show_id = show['id']  # Assuming 'id' in shows corresponds to Sonarr's show ID
        num_episodes = get_number_of_episodes(show_id)
        
        if last_airing:
            last_airing_date = datetime.strptime(last_airing, "%Y-%m-%dT%H:%M:%SZ")
        else:
            last_airing_date = datetime.min  # Set to min date if no last airing date

    # Determine profile based on conditions
        if (status.lower() == 'ended' and 
              tmdb_rating >= RATING_THRESHOLD_1080P and 
              num_episodes < EPISODE_THRESHOLD_1080P and
              any(genre in genres for genre in PROFILE_4k_GENRES)):
            profile_id = profile_1080p_id
        elif (status.lower() == 'ended' and 
              last_airing_date > threshold_date and
              any(genre in genres for genre in PROFILE_4k_GENRES)):
            profile_id = profile_1080p_id
        elif (status.lower() == 'continuing' and 
              tmdb_rating >= RATING_THRESHOLD_4K and
              any(genre in genres for genre in PROFILE_4k_GENRES)):
            profile_id = profile_4k_id
        elif (status.lower() == 'continuing' and 
              tmdb_rating >= RATING_THRESHOLD_1080P and
              num_episodes < EPISODE_THRESHOLD_1080P and
              any(genre in genres for genre in PROFILE_4k_GENRES)):
            profile_id = profile_1080p_id
        elif ((last_airing_date > threshold_date and status.lower() == 'ended') or 
              tmdb_rating < RATING_THRESHOLD_1080P or 
              (any(genre in genres for genre in PROFILE_720p_GENRES) and not any(genre in genres for genre in PROFILE_4k_GENRES))):
            profile_id = profile_720p_id
        else:
            profile_id = profile_720p_id  # Default to profile 2 if no other condition is met

        print(f"Updating show '{show_title}' (ID: {show['id']}) to profile ID {profile_id}")
        update_profile(show['id'], profile_id)

if __name__ == "__main__":
    main()
