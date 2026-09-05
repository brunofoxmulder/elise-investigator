# Élise Investigator dev.55 — architecture native Home Assistant d'abord

## Statut

Dev.55 part du commit dev.54 validé `8fc625217dbc0284496ad435a2ea8d9e7fee46b9`.
La branche `dev54-fallback-stable` est le point de repli officiel et ne doit recevoir aucune évolution dev.55+.

Aucune écriture Home Assistant n'est ajoutée. Aucun déploiement terrain n'est implicite dans cette branche.

## Principe

Investigator ne doit plus reconstruire ce que Home Assistant sait déjà.

Chemin normal cible :

`événement fonctionnel → Context natif HA → Logbook → source automation/script/user → trace ciblée seulement si un approfondissement est nécessaire → journal persistant`.

Le moteur historique de recherche inverse et de corrélation temporelle reste disponible uniquement sur la voie de diagnostic profond explicite. Il n'appartient pas au chemin conversationnel normal.

## Cartographie dev.55

- `causal_events.py` : **CONSERVER / SIMPLIFIER**. Les Context `id`, `parent_id`, `user_id` restent des primitives natives utiles.
- mémoire événementielle dev.34–dev.54 : **CONSERVER**. Elle suit déjà `automation_triggered → call_service → state_changed` sans recherche inverse.
- Logbook ciblé `targeted_memory_enricher_*` : **CONSERVER / PROMOUVOIR**. Le Logbook identifie la source avant toute lecture de trace.
- trace ciblée : **CONSERVER COMME APPROFONDISSEMENT** pour `wait_for_trigger`, conditions, branches, actions et décisions runtime.
- journal SQLite : **CONSERVER COMME MÉMOIRE PERSISTANTE / FALLBACK**.
- épisodes cover `opening/closing → open/closed` : **CONSERVER**.
- épisodes brightness dev.46 : **CONSERVER**.
- origine HA Voice dev.54 : **CONSERVER**.
- `_reverse_search()` / scan de configurations : **FALLBACK UNIQUEMENT** sur la voie profonde explicite.

## Sélection fonctionnelle dev.55

Pour les domaines binaires contrôlables (`light`, `switch`, `input_boolean`, `fan`, `humidifier`) :

- `off → on` et `on → off` restent des changements fonctionnels ;
- `on → unavailable → unknown → on` ne crée aucun nouveau changement fonctionnel ;
- `off → unavailable → unknown → off` ne crée aucun nouveau changement fonctionnel ;
- si l'état retrouvé diffère de l'état fonctionnel précédant l'interruption, Investigator conserve le changement mais le marque `indeterminate` : la maison a changé pendant l'indisponibilité, mais ni l'instant exact ni la cause ne sont prouvés ;
- si l'App redémarre pendant l'indisponibilité et ne connaît pas l'état fonctionnel précédent, la récupération est ignorée comme événement causal : fail-closed.

Les covers ne passent pas par ce filtre binaire : leur causalité reste fondée sur l'épisode fonctionnel de mouvement.

## Politique de preuve

- Logbook peut suffire pour confirmer une source système.
- `context.id/parent_id` renforce la preuve mais n'est jamais obligatoire à lui seul.
- `context_user_id` confirme une origine utilisateur générique ; le canal précis n'est nommé que si une preuve supplémentaire existe.
- HA Voice `assist_satellite.*` conserve la logique dev.54 fondée sur une lignée de Context, sans proximité temporelle comme preuve.
- une trace ne crée pas une source à partir de rien : elle approfondit une source déjà ciblée ou sert dans le fallback profond.
- configuration mentionnée ≠ exécution prouvée.
- plusieurs candidats sans lien exclusif = `indeterminate`.

## Non-régression obligatoire

1. lampe entrée : mouvement → automation → lumière ;
2. salle de bain ON ;
3. salle de bain OFF après attente ;
4. volets salon/terrasse, ancrage `opening/closing` ;
5. prise brosse à dents ;
6. commande IHM ;
7. HA Voice ;
8. séquences `unavailable/unknown` ;
9. brightness progressive dev.46 ;
10. absence de preuve native ;
11. lecture seule stricte.

## Rollback

En cas d'incident ou de régression sur dev.55 ou toute version supérieure : retour à `dev54-fallback-stable`, commit `8fc625217dbc0284496ad435a2ea8d9e7fee46b9`, puis diagnostic avant toute nouvelle évolution.
