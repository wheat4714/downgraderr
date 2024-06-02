import subprocess

# Define a dictionary with required packages and imported modules
dependencies = {
    'packages': ['requests', 'aiohttp', 'python-dateutil'],
    'modules': ['json', 'os', 're', 'logging', 'asyncio', 'typing', 'aiohttp', 'datetime', 'dateutil.parser']
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
from dateutil.parser import parse as parse_date  # Add this line

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def read_config(filename):
    with open(filename, 'r') as file:
        return json.load(file)

# Read configuration from file
config = read_config('config_radarr.json')

# Configuration variables
RADARR_IP = config.get('RADARR_IP')
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
PROFILE_1080P_GENRES = set(config.get('PROFILE_1080P_GENRES', []))  # Convert to set
CACHE_DIR = config.get('CACHE_DIR')
YEAR_THRESHOLD_4K = config.get('YEAR_THRESHOLD_4K')  # Year threshold for 4K
YEAR_THRESHOLD_1080P = config.get('YEAR_THRESHOLD_1080P')  # Year threshold for 1080p

# Constants for API endpoints
RADARR_API_URL = f"{config.get('RADARR_IP')}/api/v3"
TMDB_API_URL = "https://api.themoviedb.org/3"

# Retry settings
MAX_RETRIES = 3
RETRY_DELAY = 2  # in seconds

# Remove the year from the movie title if present, and return the year.
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

# Fetch the TMDB rating for a given movie title, using cached data if available.
async def get_tmdb_rating(session, movie_title: str) -> float:
    movie_title_cleaned, year = strip_year_from_title(movie_title)
    cache_dir = os.path.join(CACHE_DIR, "tmdb_cache")
    os.makedirs(cache_dir, exist_ok=True)
    
    params = {"api_key": TMDB_API_KEY, "query": movie_title_cleaned}
    if year:
        params["year"] = year

    data = await fetch_with_retries(session, f"{TMDB_API_URL}/search/movie", params=params)

    if data["total_results"] == 0:
        logging.warning(f"No results found for '{movie_title_cleaned}' on TMDb.")
        return 0
    
    movie_id = data["results"][0]["id"]
    cache_file = os.path.join(cache_dir, f"{movie_id}.json")

    # Check if cached rating exists and is recent
    if os.path.exists(cache_file):
        with open(cache_file, "r") as f:
            cached_data = json.load(f)
            if "timestamp" in cached_data and "rating" in cached_data:
                timestamp = datetime.fromisoformat(cached_data["timestamp"])
                if datetime.now() - timestamp < timedelta(days=7):
                    logging.info(f"Using cached rating for TMDB ID '{movie_id}'")
                    return float(cached_data["rating"])
    
    movie_data = await fetch_with_retries(session, f"{TMDB_API_URL}/movie/{movie_id}", params={"api_key": TMDB_API_KEY})
    rating = movie_data["vote_average"]
    
    # Cache the rating
    cache_data = {"rating": rating, "timestamp": datetime.now().isoformat()}
    with open(cache_file, "w") as f:
        json.dump(cache_data, f)
    
    return rating

# Fetch quality profiles from Radarr.
async def get_profiles(session) -> List[Dict[str, Any]]:
    headers = {"X-Api-Key": API_KEY}
    profiles = await fetch_with_retries(session, f"{RADARR_API_URL}/qualityProfile", headers=headers)
    return profiles

# Get the profile ID for a given profile name.
def get_profile_id(profile_name: str, profiles: List[Dict[str, Any]]) -> int:
    for profile in profiles:
        if profile['name'].lower() == profile_name.lower():
            return profile['id']
    raise ValueError(f"Profile name '{profile_name}' not found")

# Fetch all movies from Radarr.
async def get_movies(session) -> List[Dict[str, Any]]:
    headers = {"X-Api-Key": API_KEY}
    movies = await fetch_with_retries(session, f"{RADARR_API_URL}/movie", headers=headers)
    return movies

# Fetch detailed movie information from Radarr.
async def get_movie(session, movie_id: int) -> Dict[str, Any]:
    headers = {"X-Api-Key": API_KEY}
    movie = await fetch_with_retries(session, f"{RADARR_API_URL}/movie/{movie_id}", headers=headers)
    return movie

# Update the quality profile for a given movie.
async def update_profile(session, movie_id: int, profile_id: int) -> Dict[str, Any]:
    movie_data = await get_movie(session, movie_id)
    movie_data['qualityProfileId'] = profile_id
    headers = {"X-Api-Key": API_KEY}
    async with session.put(f"{RADARR_API_URL}/movie/{movie_id}", headers=headers, json=movie_data) as response:
        updated_movie = await response.json()
    return updated_movie

# Fetch genres for a given movie.
async def get_genres(session, movie_id: int) -> List[str]:
    headers = {"X-Api-Key": API_KEY}
    movie_data = await fetch_with_retries(session, f"{RADARR_API_URL}/movie/{movie_id}", headers=headers)
    return movie_data.get("genres", [])

# Fetch the release year for a given movie.
async def get_release_year(session, movie_id: int) -> int:
    headers = {"X-Api-Key": API_KEY}
    movie_data = await fetch_with_retries(session, f"{RADARR_API_URL}/movie/{movie_id}", headers=headers)
    release_date = movie_data.get("inCinemas")
    if release_date:
        release_year = parse_date(release_date).year
        return release_year
    return 0

def determine_profile_id(status: str, tmdb_rating: float, release_date: datetime, genres: List[str], last_airing_year: int, year_threshold_4k: int, year_threshold_1080p: int, profile_4k_id: int, profile_1080p_id: int, profile_720p_id: int) -> int:
    genres_set = set(genres)

    if (tmdb_rating >= RATING_THRESHOLD_4K and 
        last_airing_year >= YEAR_THRESHOLD_4K and
        PROFILE_4k_GENRES.intersection(genres_set)):
        return profile_4k_id
    
    if (tmdb_rating >= RATING_THRESHOLD_1080P and
        last_airing_year >= YEAR_THRESHOLD_1080P and
        (PROFILE_1080P_GENRES.intersection(genres_set) or PROFILE_4k_GENRES.intersection(genres_set))):
        return profile_1080p_id
    
    if (tmdb_rating < RATING_THRESHOLD_1080P or
        last_airing_year < YEAR_THRESHOLD_1080P or
        PROFILE_720p_GENRES.intersection(genres_set)):     
        return profile_720p_id
    
    return profile_1080p_id  # Default to profile 1080p if no other condition is met

async def process_movie(session, movie, profile_ids, year_threshold_4k, year_threshold_1080p):
    movie_title = movie['title']
    tmdb_rating = await get_tmdb_rating(session, movie_title)
    genres = await get_genres(session, movie['id'])
    status = movie['status']
    movie_id = movie['id']
    release_year = await get_release_year(session, movie_id)
    
    if movie.get("inCinemas"):
        release_date = parse_date(movie["inCinemas"])
    else:
        release_date = datetime.min

    profile_id = determine_profile_id(status, tmdb_rating, release_date, genres, release_year, year_threshold_4k, year_threshold_1080p, *profile_ids)
    logging.info(f"Updating movie '{movie_title}' (ID: {movie['id']}) to profile ID {profile_id}")
    await update_profile(session, movie['id'], profile_id)    

async def main():
    async with aiohttp.ClientSession() as session:
        profiles = await get_profiles(session)
        profile_ids = (
            get_profile_id(PROFILE_4k_NAME, profiles),
            get_profile_id(PROFILE_1080p_NAME, profiles),
            get_profile_id(PROFILE_720p_NAME, profiles),
        )
        
        movies = await get_movies(session)
        
        tasks = [process_movie(session, movie, profile_ids, YEAR_THRESHOLD_4K, YEAR_THRESHOLD_1080P) for movie in movies]
        await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())
