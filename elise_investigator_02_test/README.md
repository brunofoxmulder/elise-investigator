# Élise Investigator 0.2 Test

Manifest public minimal pour tester la candidate privée `0.2.0-dev.17` sous Home Assistant OS.

- L'application de test utilise l'image privée isolée `ghcr.io/brunofoxmulder/elise-investigator-dev17-private:0.2.0-dev.17`.
- Architecture de test : `amd64` uniquement.
- Démarrage : manuel.
- Ingress activé.
- Port externe 8099 désactivé.
- Accès Home Assistant : API interne requise, application conçue en lecture seule.
- AppArmor activé.
- Dev.17 ajoute un prototype de console locale multi-outils : l'interface Investigator existante reste disponible et une section « Recherche MCP locale » peut interroger HA-MCP sans LLM.
- Le client MCP refuse de fonctionner si HA-MCP n'est pas lui-même en `read_only_mode` et applique en plus une allow-list locale d'outils déclarés `readOnlyHint=true`.
- Le chemin secret MCP reste côté backend et est retiré des réponses UI/API.
- Pour la découverte automatique de l'App HA-MCP et de son option `secret_path`, la candidate test demande `hassio_api: true` avec rôle `manager`; le code n'implémente que des lectures Supervisor explicitement autorisées (`/addons`, `/addons/<slug>/info`, `/network/info`) et aucun POST Supervisor.
- Première recette locale sans IA : état → historique → recherche des automatisations/scripts liés. Elle ne modifie aucun verdict Investigator.
- Le chemin réseau `Élise Investigator App → IP hôte HA:9583 → HA-MCP` reste à valider sur le terrain.
- L'image `0.2.0-dev.17` a été construite, publiée et vérifiée par GitHub Actions dans un package GHCR dédié au prototype, sans modifier le package privé historique.

Cette entrée est expérimentale. Le moteur source `main` reste sur la dev.16 ; seule l'entrée HAOS de test est promue vers la candidate dev.17 pour validation terrain.
