# Élise Investigator — dev.30

Date: 2026-08-28

## Constat terrain

Après installation de dev.29, une question Assist telle que « Pourquoi la lampe du salon est allumée ? » pouvait répondre `indeterminate` alors que l’allumage datait de moins de cinq minutes.

Deux défauts distincts ont été confirmés dans le code :

1. Élise Why 0.2.0-dev.18 appelait encore `POST /api/v1/investigate`, donc la voie Assist contournait le journal causal dev.29.
2. La recherche approfondie pouvait sélectionner une mise à jour technique `on -> on` plus récente au lieu du vrai changement `off -> on`, puis chercher Logbook/traces autour du mauvais instant.

## Décision dev.30

### Voie Assist / LLM

Nouvel endpoint structuré `POST /api/v1/why` :

`Assist -> Élise Why -> /api/v1/why -> journal causal -> enquête approfondie optionnelle`

Le journal reste prioritaire. L’enquête approfondie n’est lancée que si aucun événement correspondant n’est enregistré et si `deep_fallback` est activé.

La projection LLM est minimale : verdict, entité, événement/heure utiles, valeur éventuelle, raison fonctionnelle ou source directe prouvée. Les noms d’automatisations, traces et variables techniques restent internes à Investigator.

### Recherche manuelle

`POST /api/v1/investigate` reste la porte de l’IHM manuelle et conserve les preuves structurées complètes.

La sélection d’événement privilégie désormais le dernier changement effectif de la valeur étudiée. Exemple : `off -> on` est retenu avant les mises à jour ultérieures `on -> on` provoquées par des changements d’attributs.

La réponse visible utilise la restitution causale humaine ; le nom de l’automatisation reste dans les preuves. Le badge de verdict est affiché en français.

## Invariants

- Home Assistant reste strictement en lecture seule pour Investigator.
- Aucun service mutateur n’est ajouté.
- Les verdicts `confirmed`, `probable`, `indeterminate` ne sont jamais renforcés par le LLM.
- dev.29 reste disponible comme rollback.
- Élise Why dev.19 est le raccordement compagnon attendu pour utiliser `/api/v1/why`.
