**Disclaimer**

This project is under heavy development. Use it at your own risk.

**Introduction**

This project is a collection of scripts designed to assign quality profiles to sonarr/radarr based on set criteria. The scripts support many different conditions, all of which are user-configurable.

**Problems solved**
- Comedy/Family shows, old shows, shows with thousands of episodes do not eat up all the space in the server.
- Action/Sci-Fi is grabbed at the highest quality setting to ensure it gets the quality it deserves
- Once a show is no longer needed in 4K because it's finished, it automatically downgrades to 1080P to save space.

**Installation instructions**
1. Rename template_radarr_config.json to config_radarr.json and template_sonarr_config.json to config.json.
2. Add your Radarr and Sonarr URLs, API keys, and TMDB API key to the config files
3. Configure your conditions and run the script

**To do**
- Lidarr script
- Plex conditions
- Package as Docker container to run as a node
- Write instructions to integrate using native radarr/sonarr scripting support
- Make the profiles into a list instead of hardcoded profile1,2,3
- Rewrite all the elseifs to use switches instead, to improve scaling and flexibility with a configurable number of profiles

