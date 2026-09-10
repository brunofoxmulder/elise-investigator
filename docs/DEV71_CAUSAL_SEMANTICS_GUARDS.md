# dev.71 — garde-fous de sémantique causale

Candidate `0.2.0-dev.71`, issue de dev.70 après échec terrain sur trois défauts génériques de restitution causale.

## Objectif strict

Corriger uniquement trois classes de défauts déjà prouvées, sans réécrire le moteur causal :

1. une indication native Home Assistant telle que `triggered by state of ...` reste une preuve/provider hint et ne peut jamais devenir la réponse causale finale brute ;
2. une condition/guard exécutée et vraie ne devient pas automatiquement la cause principale ; une conjonction reste autorisée lorsque le trigger `state` ou `numeric_state` et la condition sont tous deux prouvés et conjointement nécessaires ;
3. un trigger initial ne peut pas être recyclé comme cause d'une action différée lorsque la trace exacte prouve qu'une barrière temporelle locale (`delay`, `wait_for_trigger`, timeout, `wait_template`) a été franchie avant cette action.

## Implémentation bornée

- `activity_reader_dev71.py` supprime uniquement la restitution finale du reason code `ha_2026_9_activity_source_hint` pour les origines automation/script ; l'indice natif reste disponible comme preuve/trigger.
- `targeted_memory_enricher_dev71.py` conserve les sélecteurs structurels dev.68/dev.70 mais interdit la promotion autonome des conditions de branche. Les conditions de branche ne peuvent enrichir qu'un trigger de départ `state`/`numeric_state` prouvé.
- `trace_action_local_dev71.py` ajoute la résolution d'une barrière `delay` ou `wait_for_trigger` immédiatement adjacente à l'unique commande cible, y compris dans une séquence imbriquée. Aucun intervalle temporel arbitraire n'est recherché.
- Si une barrière temporelle exécutée est visible mais qu'aucune sémantique locale assez forte ne permet d'expliquer l'action, dev.71 échoue fermé plutôt que de retomber sur le trigger initial.

## Invariants préservés

- aucun graphe causal ;
- aucune corrélation temporelle large ;
- aucune connaissance d'entités ou d'automatisations Maison Cognitive dans le moteur ;
- traitement `unavailable/unknown` inchangé ;
- épisodes fonctionnels cover/volets dev.70 inchangés ;
- sélecteurs wait/delay et causes déjà validées dev.67 → dev.70 conservés ;
- lecture seule inchangée.

## Packaging HAOS

Le packaging reste celui prouvé terrain dev.62/dev.67 : Dockerfile générique, `COPY run.sh /run.sh`, `chmod 0755`, `CMD ["/run.sh"]`, et `run.sh` avec `#!/usr/bin/with-contenv bashio`. Seule la cible Python passe à `main_dev71.py`. Aucun `run_dev71.sh` et aucun `Dockerfile.dev71`.

## Tests dev.71

Les tests ciblés couvrent :

- suppression de la réponse brute Activity `triggered by ...` ;
- non-promotion d'un guard de branche en cause principale ;
- conservation d'une cause conjointe trigger `state` + condition prouvée ;
- `delay` imbriqué immédiatement avant la commande cible ;
- blocage du recyclage du trigger initial après `wait_template` exécuté ;
- présence intacte du fallback officiel dev.54 ;
- contrat packaging générique étendu à dev.71.

La suite complète `unittest discover` reste obligatoire afin de rejouer toutes les non-régressions historiques, notamment dev.67 → dev.70.

## Qualification

CI et publication d'image ne prouvent pas le fonctionnement HAOS terrain. Après PASS CI/publish, la candidate reste non validée tant que Bruno n'a pas explicitement décidé d'effectuer la recette terrain : démarrage App HAOS + Ingress, puis cas FAIL/PARTIAL ciblés, puis PASS historiques.

## Retour sûr

Le retour sûr officiel reste **0.2.0-dev.54** et n'est ni modifié ni promu par dev.71.
