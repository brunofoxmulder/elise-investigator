# Dev.26 — source officielle HA-MCP

Référence relue avant implémentation : `homeassistant-ai/ha-mcp`, tag `v8.3.0`, fichier `src/ha_mcp/tools/tools_traces.py`.

Points utilisés par dev.26 :

- `ha_get_automation_traces` est annoté `readOnlyHint=true`, `idempotentHint=true`, `openWorldHint=false` ;
- liste récente sans `run_id` ;
- détail ciblé avec `run_id` ;
- pagination par `limit`, `offset`, `order` ;
- réduction du détail par `sections` ;
- `deduplicate=true` disponible pour limiter la répétition des variables.

La source officielle reste la référence pour le contrat technique. Le probe dev.25 a confirmé que le serveur HA-MCP réellement connecté expose le même contrat de lecture seule.
