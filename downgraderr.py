import subprocess

# Define a dictionary with required packages and imported modules
dependencies = {
    'packages': ['requests', 'aiohttp', 'python-dateutil'],
    'modules': ['json', 'os', 're', 'logging', 'asyncio', 'typing', 'aiohttp', 'sqlite3', 'datetime', 'dateutil.parser']
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
from typing import List, Dict, Any, Tuple
from datetime import datetime, timedelta
from dateutil.parser import parse as parse_date

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
PROFILE_4K_NAME = config.get('PROFILE_4K_NAME')
PROFILE_720p_NAME = config.get('PROFILE_720p_NAME')
PROFILE_1080p_NAME = config.get('PROFILE_1080p_NAME')
DOWNGRADE_DAYS_THRESHOLD = config.get('DOWNGRADE_DAYS_THRESHOLD')
RATING_THRESHOLD_1080P = config.get('RATING_THRESHOLD_1080P')
RATING_THRESHOLD_4K = config.get('RATING_THRESHOLD_4K')
PROFILE_4K_GENRES = set(config.get('PROFILE_4K_GENRES', []))  # Convert to set
PROFILE_720P_GENRES = set(config.get('PROFILE_720P_GENRES', []))  # Convert to set
CACHE_DIR = config.get('CACHE_DIR')
EPISODE_THRESHOLD_1080P = config.get('EPISODE_THRESHOLD_1080P')
EPISODE_THRESHOLD_720P = config.get('EPISODE_THRESHOLD_720P')
EPISODE_THRESHOLD_4K = config.get('EPISODE_THRESHOLD_4K')
PROFILE_1080P_GENRES = set(config.get('PROFILE_1080P_GENRES', []))  # Convert to set
YEAR_THRESHOLD_4K = config.get('YEAR_THRESHOLD_4K')  # Year threshold for 4K
YEAR_THRESHOLD_1080P = config.get('YEAR_THRESHOLD_1080P')  # Year threshold for 1080p
YEAR_THRESHOLD_720P = config.get('YEAR_THRESHOLD_720P')  # Year threshold for 720p
CONDITIONS = config.get('CONDITIONS', {})

print(f"RATING_THRESHOLD_4K: {RATING_THRESHOLD_4K}")
print(f"RATING_THRESHOLD_1080P: {RATING_THRESHOLD_1080P}")
print(f"EPISODE_THRESHOLD_4K: {EPISODE_THRESHOLD_4K}")
print(f"EPISODE_THRESHOLD_1080P: {EPISODE_THRESHOLD_1080P}")
print(f"PROFILE_4K_GENRES: {PROFILE_4K_GENRES}")
print(f"PROFILE_720P_GENRES: {PROFILE_720P_GENRES}")
print(f"PROFILE_1080P_GENRES: {PROFILE_1080P_GENRES}")


# Constants for API endpoints
SONARR_API_URL = f"{config.get('SONARR_IP')}/api/v3"
TMDB_API_URL = "https://api.themoviedb.org/3"

# Retry settings
MAX_RETRIES = 3
RETRY_DELAY = 2  # in seconds

# Remove the year from the show title if present, and return the year.
def strip_year_from_title(title: str) -> Tuple[str, int]:
    match = re.search(r"\((\d{4})\)$", title)
    if match:
        year = int(match.group(1))
        title_cleaned = re.sub(r"\s*\(\d{4}\)$", "", title).strip()
        return title_cleaned, year
    return title, None

# Create or connect to the database
conn = sqlite3.connect('ratings.db')
c = conn.cursor()

# Create the table if it doesn't exist
c.execute('''CREATE TABLE IF NOT EXISTS ratings
             (id INTEGER PRIMARY KEY, tmdb_id INTEGER, rating REAL, timestamp TEXT)''')

# Helper function to make HTTP requests with retries
async def fetch_with_retries(session, url, params=None, headers=None):
    for attempt in range(MAX_RETRIES):
        try:
            async with session.get(url, params=params, headers=headers) as response:
                response.raise_for_status()
                return await response.json()
        except (aiohttp.ClientError, aiohttp.ClientConnectionError, aiohttp.ClientPayloadError) as e:
            logging.warning(f"Request failed ({e}), retrying in {RETRY_DELAY} seconds...")
            await asyncio.sleep(RETRY_DELAY)
    raise Exception(f"Failed to fetch data from {url} after {MAX_RETRIES} retries.")

# Fetch the TMDB rating for a given show title, using cached data if available.
async def get_tmdb_rating(session, show_title: str) -> float:
    show_title_cleaned, year = strip_year_from_title(show_title)
    
    params = {"api_key": TMDB_API_KEY, "query": show_title_cleaned}
    if year:
        params["first_air_date_year"] = year

    data = await fetch_with_retries(session, f"{TMDB_API_URL}/search/tv", params=params)

    if data["total_results"] == 0:
        logging.warning(f"No results found for '{show_title_cleaned}' on TMDb.")
        return 0
    
    show_id = data["results"][0]["id"]

    # Check if cached rating exists and is recent
    c.execute("SELECT rating, timestamp FROM ratings WHERE tmdb_id = ?", (show_id,))
    cached_data = c.fetchone()
    if cached_data:
        rating, timestamp_str = cached_data
        timestamp = datetime.fromisoformat(timestamp_str)
        if datetime.now() - timestamp < timedelta(days=7):
            logging.info(f"Using cached rating for TMDB ID '{show_id}'")
            return rating
    
    # Fetch rating from TMDB API
    show_data = await fetch_with_retries(session, f"{TMDB_API_URL}/tv/{show_id}", params={"api_key": TMDB_API_KEY})
    rating = show_data["vote_average"]
    
    # Cache the rating
    timestamp_str = datetime.now().isoformat()
    c.execute("INSERT OR REPLACE INTO ratings (tmdb_id, rating, timestamp) VALUES (?, ?, ?)", (show_id, rating, timestamp_str))
    conn.commit()
    
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
    total_episodes = sum(season['statistics']['episodeCount'] for season in data['seasons'] if 'statistics' in season)
    return total_episodes

# Fetch the last airing year for a given show.
async def get_last_airing_year(session, show_id: int) -> int:
    headers = {"X-Api-Key": API_KEY}
    data = await fetch_with_retries(session, f"{SONARR_API_URL}/series/{show_id}", headers=headers)
    last_airing = data.get("previousAiring")
    if last_airing:
        last_airing_year = datetime.strptime(last_airing, "%Y-%m-%dT%H:%M:%SZ").year
        return last_airing_year
    return 0

def determine_profile_id(status: str, tmdb_rating: float, last_airing_date: datetime, genres: List[str], num_episodes: int, threshold_date: datetime, last_airing_year: int, profile_4k_id: int, profile_1080p_id: int, profile_720p_id: int) -> int:
    genres_set = set(genres)
    status_lower = status.lower()

    match status_lower, tmdb_rating, last_airing_date, num_episodes, last_airing_year, genres_set:
        case 'ended', rating, date, episodes, year, genres if (condition := build_condition('4k', tmdb_rating)) and eval(condition):
            logging.info(f"Assigning 4K profile for show with status '{status}', rating {rating}, last airing date {date}, {episodes} episodes, last airing year {year}, and genres {genres}")
            logging.info(f"Condition evaluated: {condition}")
            return profile_4k_id
        case 'continuing', rating, _, episodes, year, genres if (condition := build_condition('4k', tmdb_rating)) and eval(condition):
            logging.info(f"Assigning 4K profile for show with status '{status}', rating {rating}, {episodes} episodes, last airing year {year}, and genres {genres}")
            logging.info(f"Condition evaluated: {condition}")
            return profile_4k_id
        case 'ended', _, _, episodes, year, genres if (condition := build_condition('1080p', tmdb_rating)) and eval(condition):
            logging.info(f"Assigning 1080p profile for show with status '{status}', {episodes} episodes, last airing year {year}, and genres {genres}")
            logging.info(f"Condition evaluated: {condition}")
            return profile_1080p_id
        case 'continuing', rating, _, episodes, year, genres if (condition := build_condition('1080p', tmdb_rating)) and eval(condition):
            logging.info(f"Assigning 1080p profile for show with status '{status}', rating {rating}, {episodes} episodes, last airing year {year}, and genres {genres}")
            logging.info(f"Condition evaluated: {condition}")
            return profile_1080p_id
        case _, rating, _, episodes, year, genres if (condition := build_condition('720p', tmdb_rating)) and eval(condition):
            logging.info(f"Assigning 720p profile for show with rating {rating}, {episodes} episodes, last airing year {year}, and genres {genres}")
            logging.info(f"Condition evaluated: {condition}")
            return profile_720p_id
        case _:
            logging.info(f"Assigning default 1080p profile for show with status '{status}', rating {tmdb_rating}, last airing date {last_airing_date}, {num_episodes} episodes, last airing year {last_airing_year}, and genres {genres}")
            return profile_1080p_id

def build_condition(profile_name, rating, episodes, year, status_lower):
    conditions = []
    profile_conditions = CONDITIONS.get(profile_name, {})

    if profile_conditions.get('USE_RATING', False):
        if profile_name == '720p':
            rating_threshold = getattr(globals(), 'RATING_THRESHOLD_720P', 0)
            rating_condition = f"rating >= {rating_threshold}"
        else:
            rating_condition = f"rating >= RATING_THRESHOLD_{profile_name.upper()}"
        conditions.append(rating_condition)
        logging.info(f"Rating condition for {profile_name}: {rating_condition}")

    if profile_conditions.get('USE_EPISODES', False):
        episode_condition = f"episodes < EPISODE_THRESHOLD_{profile_name.upper()}"
        conditions.append(episode_condition)
        logging.info(f"Episode condition for {profile_name}: {episode_condition}")

    if profile_conditions.get('USE_YEAR', False):
        year_condition = f"year >= YEAR_THRESHOLD_{profile_name.upper()}"
        conditions.append(year_condition)
        logging.info(f"Year condition for {profile_name}: {year_condition}")

    if profile_conditions.get('USE_GENRES', False):
        genre_condition = f"any(genre in PROFILE_{profile_name.upper()}_GENRES for genre in genres_set)"
        conditions.append(genre_condition)
        logging.info(f"Genre condition for {profile_name}: {genre_condition}")

    if profile_conditions.get('USE_CONTINUING', False):
        continuing_condition = f"status_lower == 'continuing'"
        conditions.append(continuing_condition)
        logging.info(f"Continuing condition for {profile_name}: {continuing_condition}")

    condition_str = " and ".join(conditions)
    logging.info(f"Condition string for {profile_name}: {condition_str}")
    return condition_str

def determine_profile_id(status, tmdb_rating, last_airing_date, genres_set, num_episodes, last_airing_year, profile_4k_id, profile_1080p_id, profile_720p_id, rating, episodes, year):
    status_lower = status.lower()
    for profile_name in ['4k', '1080p', '720p']:
        condition = build_condition(profile_name, rating, episodes, year, status_lower)
        if condition:
            if eval(condition):
                logging.info(f"Assigning {profile_name} profile for show with status '{status}', rating {tmdb_rating}, last airing date {last_airing_date}, {num_episodes} episodes, last airing year {last_airing_year}, and genres {genres_set}")
                logging.info(f"Condition evaluated: {condition}")
                return locals()[f'profile_{profile_name}_id']
    logging.info(f"Assigning default 1080p profile for show with status '{status}', rating {tmdb_rating}, last airing date {last_airing_date}, {num_episodes} episodes, last airing year {last_airing_year}, and genres {genres_set}")
    return profile_1080p_id


    
async def process_show(session, show, threshold_date, profile_ids, year_threshold_4k, year_threshold_1080p):
    last_airing = show.get("previousAiring")
    show_title = show['title']
    tmdb_rating = await get_tmdb_rating(session, show_title)
    genres = await get_genres(session, show['id'])
    status = show['status']
    show_id = show['id']
    num_episodes = await get_number_of_episodes(session, show_id)
    last_airing_year = await get_last_airing_year(session, show_id)
    
    if last_airing:
        last_airing_date = datetime.strptime(last_airing, "%Y-%m-%dT%H:%M:%SZ")
    else:
        last_airing_date = datetime.min

    profile_id = determine_profile_id(status, tmdb_rating, last_airing_date, genres, num_episodes, last_airing_year, *profile_ids, tmdb_rating, num_episodes, last_airing_year)
    logging.info(f"Updating show '{show_title}' (ID: {show['id']}) to profile ID {profile_id}")
    await update_profile(session, show['id'], profile_id)  

async def main():
    async with aiohttp.ClientSession() as session:
        profiles = await get_profiles(session)
        profile_ids = (
            get_profile_id(PROFILE_4K_NAME, profiles),
            get_profile_id(PROFILE_1080p_NAME, profiles),
            get_profile_id(PROFILE_720p_NAME, profiles),
        )
        
        shows = await get_shows(session)
        threshold_date = datetime.now() - timedelta(days=DOWNGRADE_DAYS_THRESHOLD)
        
        tasks = [process_show(session, show, threshold_date, profile_ids, YEAR_THRESHOLD_4K, YEAR_THRESHOLD_1080P) for show in shows]
        await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())
