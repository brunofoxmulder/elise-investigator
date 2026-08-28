# Élise Investigator 0.2.0-dev.29 — journal causal

Statut : **conception + développement en cours**. Aucune promotion terrain.

## Besoin fonctionnel validé

Élise Investigator doit conserver localement, pendant une durée glissante réglable, le dernier changement utile de chaque entité et la cause effectivement prouvée au moment de l'événement. Lors d'une question naturelle, Investigator doit d'abord répondre à partir de ce journal plutôt que de reconstruire toute la causalité à la demande.

Principes de réponse :

- action issue d'une automatisation : répondre par la **raison fonctionnelle** ; le nom de l'automatisation reste une preuve interne ;
- action directe : répondre `utilisateur`, ou `Alexa` uniquement si cette provenance est réellement prouvée ;
- dernier trigger effectif : prioritaire quand il explique réellement l'action ;
- trigger générique (`time_pattern`, etc.) : ne pas le présenter comme raison fonctionnelle ; analyser uniquement la même trace pour identifier la branche/facteur décisif ;
- ambiguïté : ne jamais choisir une cause par simple proximité temporelle ;
- LLM : ne reçoit qu'une projection minimale des faits déjà établis.

## Invariants

- lecture seule stricte vis-à-vis de Home Assistant ;
- aucun LLM dans le moteur causal ;
- aucune modification d'automatisation, script, entité, dashboard ou intégration HA ;
- conservation de l'IHM actuelle d'investigation manuelle ;
- conservation du moteur d'enquête approfondie comme secours optionnel ;
- `confirmed / probable / indeterminate` restent les niveaux de certitude ;
- le journal causal ne peut jamais augmenter une certitude au-delà de la preuve capturée.

## Réglages prévus dans l'IHM

- `Durée du journal causal` : entier de 1 à 72 heures, défaut 12 h ;
- `Enquête approfondie si aucun événement n'est enregistré` : case à cocher ;
- indication de provenance de la réponse pendant la phase de test : `journal causal` ou `enquête approfondie`.

## Architecture retenue

### 1. Capture

Connexion WebSocket Home Assistant dédiée et **strictement en abonnement lecture seule** à `state_changed`.

Pourquoi cette option plutôt qu'un polling History :

- contexte de l'événement disponible immédiatement ;
- charge plus faible ;
- aucune fenêtre de polling pouvant manquer une transition courte ;
- meilleur rattachement aux contextes automation/script/utilisateur.

La méthode de souscription sera dédiée : aucun WebSocket générique ne sera exposé au moteur.

### 2. Filtrage des événements

Le flux `state_changed` peut contenir beaucoup d'updates d'attributs. Le recorder conserve :

- tous les vrais changements d'état principal ;
- un petit ensemble d'attributs de commande génériques par domaine quand ils changent réellement (ex. `cover.current_position`) ;
- jamais un simple `last_updated` sans effet métier.

Le mécanisme doit rester générique Home Assistant et ne contenir aucun Entity ID Maison Cognitive en dur.

### 3. Attribution de provenance

Ordre conservateur :

1. contexte direct prouvé (utilisateur ou source spécifique) ;
2. Logbook/context pour automation/script ;
3. trace exacte de cette automation/script proche de l'événement ;
4. vérification que l'action exécutée vise réellement l'entité et correspond à l'effet ;
5. sinon `unknown` / `indeterminate`.

`Alexa` ne sera jamais inféré d'un simple `user_id`. Il faudra une preuve de provenance terrain exploitable avant d'émettre ce libellé.

### 4. Cause fonctionnelle

Les extracteurs déterministes déjà développés dans la lignée privée 0.2 (`human_cause`, `trigger_semantics`, `branch_decision_cause`, `action_effect_cause`) sont la référence à réutiliser/porter. Ils séparent notamment :

- trigger initial ;
- `wait_for_trigger` qui libère réellement une action ;
- décision `choose/default` ;
- action exécutée ;
- cause humaine exprimable sans citer le mécanisme d'automatisation.

Dev.29 ne doit pas réinventer ces règles dans le stockage.

### 5. Stockage

SQLite local sous `/data`, dans un fichier appartenant à Investigator.

Table compacte indexée par `entity_id + event_time`. On stocke :

- entité + nom ;
- heure ;
- changement (`before`, `after`, attribut éventuel) ;
- origine ;
- raison fonctionnelle compacte ;
- trigger/facteurs utiles ;
- niveau de certitude ;
- références de preuve (`trace_run_id`, chemin), pas la trace brute complète.

Purge automatique selon la durée choisie. WAL + transactions SQLite pour résister aux redémarrages.

### 6. Réponse à une question

Flux normal :

`question -> résolution entité -> dernier événement causal -> réponse`

Si aucune entrée n'existe :

- option secours activée : moteur d'enquête approfondie actuel ;
- option secours désactivée : réponse courte indiquant qu'aucun événement enregistré ne permet de conclure.

L'IHM d'investigation manuelle reste disponible pour lancer explicitement une enquête historique/ciblée.

### 7. Contrat LLM minimal

Exemples :

```json
{"entity":"Lampe entrée","event":"turned_off","time":"2026-08-28T08:38:53+00:00","value":"off","reason":"il n'y avait plus de mouvement"}
```

```json
{"entity":"Lampe salon","event":"turned_on","time":"2026-08-28T10:03:18+00:00","value":"on","source":"Alexa"}
```

Le payload LLM ne contient jamais : configuration d'automatisation, trace brute, Entity ID de l'automatisation, variables techniques complètes, endpoint MCP, jetons ou secrets.

## Lignée source — point de vigilance

L'image terrain dev.28 est construite directement depuis `dev28-mcp-independent-picker`. Les raffinements causaux dev.9–dev.16 existent dans le worktree privé Maison Cognitive mais ne sont pas tous présents dans l'arbre public dev.28. Dev.29 doit donc **réconcilier les couches causales explicitement** avant de les utiliser, plutôt que supposer que le code public contient déjà toute la lignée 0.2.

## Découpage de développement

1. stockage persistant + purge + contrat LLM minimal ;
2. souscription `state_changed` read-only + normalisation des événements ;
3. attribution source automation/script/utilisateur ;
4. port/réutilisation des extracteurs de cause fonctionnelle ;
5. recorder-first pour l'API conversationnelle ;
6. options IHM + affichage source ;
7. tests jumeau numérique, sécurité lecture seule, redémarrage/persistance ;
8. image candidate et terrain uniquement après Go explicite.
