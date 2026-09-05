# Élise Investigator 0.2 Test

Canal HAOS expérimental pour la recette terrain de `0.2.0-dev.55`.

- Image candidate : `ghcr.io/brunofoxmulder/elise-investigator-dev55-private:0.2.0-dev.55`.
- Architecture : `amd64` uniquement.
- Démarrage : manuel.
- Ingress activé.
- Port externe 8099 désactivé.
- Accès Home Assistant : API interne requise, application conçue en lecture seule.
- AppArmor activé.
- Dev.55 conserve la lignée fonctionnelle validée jusqu'à dev.54 (covers, brightness, HA Voice) et ajoute le filtrage des séquences techniques `unavailable/unknown`.
- Chemin causal nominal : primitives natives Home Assistant et Logbook ciblé d'abord ; trace ciblée seulement pour approfondir ; journal persistant comme mémoire/fallback.
- La recherche inverse historique reste réservée au diagnostic profond explicite.
- Dev.54 reste le point de repli officiel via `dev54-fallback-stable` au commit `8fc625217dbc0284496ad435a2ea8d9e7fee46b9`.
- PR dev.55 : #53, conservée en brouillon jusqu'à validation terrain explicite.

Cette entrée Test ne doit pas être considérée comme stable avant recette Maison Cognitive complète.
