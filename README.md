# downgraderr

**Disclaimer**

This project is under heavy development. Use it at your own risk.

**Introduction**

This project is a collection of scripts designed to assign quality profiles to sonarr/radarr based on set criteria. The scripts support many different conditions, all of which are user-configurable.

**Problems solved**
- Comedy/Family shows, old shows, shows with thousands of episodes do not eat up all the space in the server.
- Action/Sci-Fi is grabbed at the highest quality setting to ensure it gets the quality it deserves
- Once a show is no longer needed in 4K because it's finished, it automatically downgrades to 1080P to save space.

**To do**
- Lidarr script
- Plex conditions
- Package as Docker container to run as a node
- Write instructions to integrate using native radarr/sonarr scripting support