# dev.65 — packaging-only candidate

- Logic causal identical to dev.63/dev.64.
- Version Home Assistant: `0.2.0-dev.65`.
- Entrypoint dédié : `main_dev65.py`.
- Launcher dédié : `run_dev65.sh`.
- Dockerfile dédié : `Dockerfile.dev65`.
- Lancement : `/usr/bin/with-contenv bashio /run_dev65.sh`.
- Objectif : corriger le packaging et utiliser une vraie version suivante reconnue par Home Assistant.
- Aucun changement causal.
- Dev.54 reste le fallback officiel.
