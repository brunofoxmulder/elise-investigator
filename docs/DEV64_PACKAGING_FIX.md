# Dev.64 packaging repair

Dev.64 keeps the causal logic of dev.63 and fixes only the Home Assistant App launch path.

The runtime now uses a dedicated `run_dev64.sh` invoked explicitly through `/usr/bin/with-contenv bashio`, then starts `main_dev64.py` on port 8099. This avoids the previous direct-Python launch that lost `SUPERVISOR_TOKEN`, and avoids executing the launcher file directly, which produced `Permission denied` on terrain.

The publisher first builds a local amd64 image and verifies the launcher, `with-contenv` wrapper and container command before publishing the private terrain image.

Maintenance build exposed to Home Assistant: `0.2.0-dev.64.1`.
