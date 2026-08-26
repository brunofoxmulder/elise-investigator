# Dev.26 — exploration bornée des traces HA-MCP

Checkpoint d’architecture après validation terrain de dev.25.

## Objet

Prouver qu’Élise Investigator peut exploiter `ha_get_automation_traces` en lecture seule de manière bornée et lisible, sans transformer cette exploration MCP en second moteur causal.

Dev.26 conserve :

- le moteur causal Investigator existant inchangé ;
- la synthèse MCP locale déterministe de dev.24 ;
- le contrôle du contrat live et `readOnlyHint=true` de dev.25 ;
- l’absence totale de LLM dans le moteur MCP local.

## Contrat HA-MCP vérifié

La source officielle HA-MCP 8.3.0 confirme deux modes :

1. liste récente sans `run_id` ;
2. détail d’une exécution avec `run_id`.

Le contrat accepte notamment `limit`, `offset`, `order`, `deduplicate`, `detailed` et `sections`. Dev.26 utilise uniquement les modes lecture suivants :

- liste : `limit=3`, `offset=0`, `order=newest` ;
- détail : `deduplicate=true`, `detailed=false`, `sections=trigger,conditions,actions,error`.

## Parcours dev.26

`état/historique/search dev.24 → candidats configuration → listes de traces → sélection temporelle → un détail compact maximum → synthèse locale`

Bornes fixes du jalon :

- 6 candidats automation/script maximum ;
- 3 traces récentes maximum par candidat ;
- une fenêtre de proximité de 30 minutes autour du dernier événement History observé ;
- 1 détail maximum ;
- 12 conditions maximum conservées dans la sortie compacte ;
- 20 actions maximum conservées ;
- snapshots `variables` supprimés de la sortie dev.26.

## Politique de sélection

La trace détaillée est choisie uniquement par proximité entre le `timestamp` de la trace listée et le dernier événement History observé.

Cette sélection est explicitement marquée :

`selection_is_causal_proof = false`

Une proximité temporelle n’est jamais interprétée comme une preuve causale. Elle sert uniquement à choisir une exécution à examiner.

## Frontière de preuve

Dev.26 doit toujours renvoyer :

- `causal_verdict = null` ;
- `investigator_status_unchanged = true` ;
- `uses_llm = false` ;
- `read_only = true`.

Le verdict `confirmed / probable / indeterminate` reste exclusivement produit par Investigator.

## Garde-fous d’appel

Aucun appel de trace n’est effectué si :

- aucun événement History horodaté n’est disponible ;
- aucun candidat automation/script n’est trouvé ;
- `ha_get_automation_traces` n’est pas exposé avec `annotations.readOnlyHint=true`.

`MCPProtocolSession.call_tool()` conserve par ailleurs le double verrou déjà existant : allow-list Investigator + `readOnlyHint=true` du serveur live.

## Maîtrise de la taille

Le détail officiel HA-MCP peut contenir des variables volumineuses. Dev.26 demande `deduplicate=true`, puis compacte immédiatement la réponse :

- conservation du trigger ;
- conservation limitée des résultats de conditions ;
- conservation limitée de la structure/résultat des actions ;
- suppression des snapshots de variables dans la sortie de l’app.

Le but est de conserver la structure d’exécution utile sans injecter des centaines de kilo-octets dans l’interface ou une future couche conversationnelle.

## Tests attendus

La suite dev.26 vérifie au minimum :

- sélection d’une seule trace temporellement proche ;
- un seul appel de détail ;
- 6 candidats maximum ;
- `limit=3` sur chaque liste ;
- aucun appel sans ancrage History ;
- aucun appel si le tool live n’est pas déclaré read-only ;
- compactage des actions et suppression des variables ;
- `causal_verdict=null` et `investigator_status_unchanged=true` après exploration.

## Critère terrain futur

Après CI et image privée vertes, et uniquement après Go explicite de Bruno :

1. mettre à jour manuellement l’app de test vers `0.2.0-dev.26` ;
2. poser une question causale connue, par exemple sur le volet salon ;
3. vérifier l’affichage `MCP LOCAL · EXPLORATION BORNÉE · LECTURE SEULE` ;
4. vérifier le nombre de candidats interrogés et qu’un détail maximum est chargé ;
5. vérifier `sélection temporelle = preuve causale : non` ;
6. vérifier `IA : non` et `Verdict causal Investigator : inchangé`.

Aucune modification de Home Assistant, Alexa, Maison Élise, Assist ou Élise Why ne fait partie de dev.26.
