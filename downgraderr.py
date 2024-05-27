import requests
import json
import os
from datetime import datetime, timedelta

# User-configurable values
SONARR_IP = ""  # Sonarr IP address
API_KEY = ""  # Sonarr API key
TMDB_API_KEY = ""  # TMDb API key
PROFILE_1_NAME = "upgraded"  # Profile name for profile 1
PROFILE_2_NAME = "downgraded"  # Profile name for profile 2
DAYS_THRESHOLD = 60  # Number of days to check for the last airing date
RATING_THRESHOLD = 5  # Rating threshold for applying profiles
PROFILE_1_GENRES = ["Drama", "Crime", "Documentary"]  # Genres for profile 1
PROFILE_2_GENRES = ["Comedy", "Animation"]  # Genres for profile 2
CACHE_DIR = "ratings_cache"  # Directory to store cached ratings

def get_tmdb_rating(show_title):
    cache_file = os.path.join(CACHE_DIR, f"{show_title}.json")
    
    # Check if cached rating exists and is recent
    if os.path.exists(cache_file):
        with open(cache_file, "r") as f:
            data = json.load(f)
            if "timestamp" in data and "rating" in data:
                timestamp = datetime.fromisoformat(data["timestamp"])
                if datetime.now() - timestamp < timedelta(days=7):
                    print(f"Using cached rating for '{show_title}'")
                    return float(data["rating"])
    
    url = f"https://api.themoviedb.org/3/search/tv"
    params = {"api_key": TMDB_API_KEY, "query": show_title}
    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()
    if data["total_results"] == 0:
        print(f"No results found for '{show_title}' on TMDb.")
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

def main():
    profiles = get_profiles()
    profile_1_id = get_profile_id(PROFILE_1_NAME, profiles)
    profile_2_id = get_profile_id(PROFILE_2_NAME, profiles)
    shows = get_shows()
    threshold_date = datetime.now() - timedelta(days=DAYS_THRESHOLD)

    for show in shows:
        last_airing = show.get("previousAiring")
        show_title = show['title']
        tmdb_rating = get_tmdb_rating(show_title)
        genres = get_genres(show['id'])

        if last_airing:
            last_airing_date = datetime.strptime(last_airing, "%Y-%m-%dT%H:%M:%SZ")

            # Check if profile 1 genres match and last airing date matches threshold date
            if any(genre in genres for genre in PROFILE_1_GENRES) and last_airing_date > threshold_date:
                profile_id = profile_1_id
            else:
                # Default to profile 2
                profile_id = profile_2_id
        else:
            # Default to profile 2
            profile_id = profile_2_id

        print(f"Updating show '{show_title}' (ID: {show['id']}) to profile ID {profile_id}")
        update_profile(show['id'], profile_id)


if __name__ == "__main__":
    main()
