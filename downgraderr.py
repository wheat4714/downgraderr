import subprocess

# Define a dictionary with required packages and imported modules
dependencies = {
    'packages': ['requests', 'aiohttp'],
    'modules': ['json', 'os', 're', 'logging', 'asyncio', 'typing', 'aiohttp', 'datetime']
}

# Check and install required packages
for package in dependencies['packages']:
    try:
        __import__(package)
    except ImportError:
        print(f"{package} is not installed. Installing...")
        subprocess.check_call(['pip', 'install', package])
        print(f"{package} installed successfully.")

# Import required modules
for module in dependencies['modules']:
    globals()[module] = __import__(module)

# Import specific items from modules
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
DOWNGRADE_DAYS_THRESHOLD = config.get('DOWNGRADE_DAYS_THRESHOLD')
RATING_THRESHOLD_1080P = config.get('RATING_THRESHOLD_1080P')
RATING_THRESHOLD_4K = config.get('RATING_THRESHOLD_4K')
PROFILE_4k_GENRES = set(config.get('PROFILE_4k_GENRES', []))  # Convert to set
PROFILE_720p_GENRES = set(config.get('PROFILE_720p_GENRES', []))  # Convert to set
CACHE_DIR = config.get('CACHE_DIR')
EPISODE_THRESHOLD_1080P = config.get ('EPISODE_THRESHOLD_1080P')
EPISODE_THRESHOLD_4K = config.get ('EPISODE_THRESHOLD_4K')
PROFILE_1080P_GENRES = set(config.get('PROFILE_1080P_GENRES', []))  # Convert to set

# Constants for API endpoints
SONARR_API_URL = f"{config.get('SONARR_IP')}/api/v3"
TMDB_API_URL = "https://api.themoviedb.org/3"

# Retry settings
MAX_RETRIES = 3
RETRY_DELAY = 2  # in seconds

# Remove the year from the show title if present.
def strip_year_from_title(title: str) -> tuple[str, int]:
    match = re.search(r"\((\d{4})\)$", title)
    if match:
        year = int(match.group(1))
        title_cleaned = re.sub(r"\s*\(\d{4}\)$", "", title).strip()
        return title_cleaned, year
    return title, None

# Helper function to make HTTP requests with retries
async def fetch_with_retries(session, url, params=None, headers=None):
    for attempt in range(MAX_RETRIES):
        try:
            async with session.get(url, params=params, headers=headers) as response:
                response.raise_for_status()
                return await response.json()
        except (aiohttp.ClientError, aiohttp.ClientConnectionError) as e:
            logging.warning(f"Request failed ({e}), retrying in {RETRY_DELAY} seconds...")
            await asyncio.sleep(RETRY_DELAY)
    raise Exception(f"Failed to fetch data from {url} after {MAX_RETRIES} retries.")

# Fetch the TMDB rating for a given show title, using cached data if available.
async def get_tmdb_rating(session, show_title: str) -> float:
    show_title_cleaned, year = strip_year_from_title(show_title)
    cache_dir = os.path.join(CACHE_DIR)
    os.makedirs(cache_dir, exist_ok=True)
    
    params = {"api_key": TMDB_API_KEY, "query": show_title_cleaned}
    if year:
        params["first_air_date_year"] = year

    data = await fetch_with_retries(session, f"{TMDB_API_URL}/search/tv", params=params)

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
    
    show_data = await fetch_with_retries(session, f"{TMDB_API_URL}/tv/{show_id}", params={"api_key": TMDB_API_KEY})
    rating = show_data["vote_average"]
    
    # Cache the rating
    cache_data = {"rating": rating, "timestamp": datetime.now().isoformat()}
    with open(cache_file, "w") as f:
        json.dump(cache_data, f)
    
    return rating

# Fetch quality profiles from Sonarr.
async def get_profiles(session) -> List[Dict[str, Any]]:
    headers = {"X-Api-Key": API_KEY}
    profiles = await fetch_with_retries(session, f"{SONARR_API_URL}/qualityprofile", headers=headers)
    return profiles

# Get the profile ID for a given profile name.
def get_profile_id(profile_name: str, profiles: List[Dict[str, Any]]) -> int:
    for profile in profiles:
        if profile['name'].lower() == profile_name.lower():
            return profile['id']
    raise ValueError(f"Profile name '{profile_name}' not found")

# Fetch all shows from Sonarr.
async def get_shows(session) -> List[Dict[str, Any]]:
    headers = {"X-Api-Key": API_KEY}
    shows = await fetch_with_retries(session, f"{SONARR_API_URL}/series", headers=headers)
    return shows

# Fetch detailed series information from Sonarr.
async def get_series(session, series_id: int) -> Dict[str, Any]:
    headers = {"X-Api-Key": API_KEY}
    series = await fetch_with_retries(session, f"{SONARR_API_URL}/series/{series_id}", headers=headers)
    return series

# Update the quality profile for a given series.
async def update_profile(session, series_id: int, profile_id: int) -> Dict[str, Any]:
    series_data = await get_series(session, series_id)
    series_data['qualityProfileId'] = profile_id
    headers = {"X-Api-Key": API_KEY}
    async with session.put(f"{SONARR_API_URL}/series/{series_id}", headers=headers, json=series_data) as response:
        updated_series = await response.json()
    return updated_series

# Fetch genres for a given series.
async def get_genres(session, series_id: int) -> List[str]:
    headers = {"X-Api-Key": API_KEY}
    series_data = await fetch_with_retries(session, f"{SONARR_API_URL}/series/{series_id}", headers=headers)
    return series_data.get("genres", [])

# Fetch the total number of episodes for a given show.
async def get_number_of_episodes(session, show_id: int) -> int:
    headers = {"X-Api-Key": API_KEY}
    data = await fetch_with_retries(session, f"{SONARR_API_URL}/series/{show_id}", headers=headers)
    total_episodes = sum(season['statistics']['episodeCount'] for season in data['seasons'])
    return total_episodes

def determine_profile_id(status: str, tmdb_rating: float, last_airing_date: datetime, genres: List[str], num_episodes: int, threshold_date: datetime, profile_4k_id: int, profile_1080p_id: int, profile_720p_id: int) -> int:
    genres_set = set(genres)
    if (status.lower() == 'ended' and 
        tmdb_rating >= RATING_THRESHOLD_1080P and 
        num_episodes < EPISODE_THRESHOLD_1080P and
        (PROFILE_1080P_GENRES.intersection(genres_set) or PROFILE_4k_GENRES.intersection(genres_set))):
        return profile_1080p_id
    elif (status.lower() == 'ended' and 
          last_airing_date > threshold_date and
          num_episodes < EPISODE_THRESHOLD_1080P and          
          (PROFILE_1080P_GENRES.intersection(genres_set) or PROFILE_4k_GENRES.intersection(genres_set))):
        return profile_1080p_id
    elif (status.lower() == 'continuing' and 
          tmdb_rating >= RATING_THRESHOLD_4K and
          num_episodes < EPISODE_THRESHOLD_4K and
          PROFILE_4k_GENRES.intersection(genres_set)):
        return profile_4k_id
    elif (status.lower() == 'continuing' and 
          tmdb_rating >= RATING_THRESHOLD_1080P and
          num_episodes < EPISODE_THRESHOLD_1080P and
          (PROFILE_1080P_GENRES.intersection(genres_set) or PROFILE_4k_GENRES.intersection(genres_set))):
        return profile_1080p_id
    elif (tmdb_rating <= RATING_THRESHOLD_1080P or
          num_episodes > EPISODE_THRESHOLD_1080P or
          PROFILE_720p_GENRES.intersection(genres_set)):     
        return profile_720p_id
    else:
        return profile_1080p_id  # Default to profile 1080p if no other condition is met
    
async def process_show(session, show, threshold_date, profile_ids):
    last_airing = show.get("previousAiring")
    show_title = show['title']
    tmdb_rating = await get_tmdb_rating(session, show_title)
    genres = await get_genres(session, show['id'])
    status = show['status']
    show_id = show['id']
    num_episodes = await get_number_of_episodes(session, show_id)
    
    if last_airing:
        last_airing_date = datetime.strptime(last_airing, "%Y-%m-%dT%H:%M:%SZ")
    else:
        last_airing_date = datetime.min

    profile_id = determine_profile_id(status, tmdb_rating, last_airing_date, genres, num_episodes, threshold_date, *profile_ids)
    logging.info(f"Updating show '{show_title}' (ID: {show['id']}) to profile ID {profile_id}")
    await update_profile(session, show['id'], profile_id)    

async def main():
    async with aiohttp.ClientSession() as session:
        profiles = await get_profiles(session)
        profile_ids = (
            get_profile_id(PROFILE_4k_NAME, profiles),
            get_profile_id(PROFILE_1080p_NAME, profiles),
            get_profile_id(PROFILE_720p_NAME, profiles),
        )
        
        shows = await get_shows(session)
        threshold_date = datetime.now() - timedelta(days=DOWNGRADE_DAYS_THRESHOLD)
        
        tasks = [process_show(session, show, threshold_date, profile_ids) for show in shows]
        await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())
