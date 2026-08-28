# Élise Investigator 0.2.0-dev.29 — journal causal

Statut : **développement intégré sur branche candidate, aucune promotion terrain**.

## Besoin fonctionnel validé

Élise Investigator doit conserver localement, pendant une durée glissante réglable, le dernier changement utile de chaque entité et la cause effectivement prouvée au moment de l'événement. Lors d'une question naturelle, Investigator doit d'abord répondre à partir de ce journal plutôt que de reconstruire toute la causalité à la demande.

Principes de réponse :

- action issue d'une automatisation : répondre par la **raison fonctionnelle** ; le nom de l'automatisation reste une preuve interne ;
- action directe : répondre `utilisateur`, ou `Alexa` uniquement si cette provenance est réellement prouvée ;
- dernier trigger effectif : prioritaire quand il explique réellement l'action ;
- trigger générique (`time_pattern`, etc.) : ne pas le présenter comme raison fonctionnelle ; analyser uniquement la même trace pour identifier la branche ou les entrées de décision prouvées ;
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

## Réglages IHM

Implémentés dans le wrapper dev.29 :

- `Durée du journal causal` : entier de 1 à 72 heures, défaut 12 h ;
- `Enquête approfondie si aucun événement n'est enregistré` : case à cocher ;
- état du worker : actif/arrêté, nombre d'événements, file d'enrichissement, enrichissements et échecs.

Les réglages sont conservés localement dans `/data/causal_settings.json` par remplacement atomique.

## Architecture retenue

### 1. Capture

Connexion WebSocket Home Assistant dédiée et **strictement en abonnement lecture seule** à `state_changed`.

Pourquoi cette option plutôt qu'un polling History :

- contexte de l'événement disponible immédiatement ;
- charge plus faible ;
- aucune fenêtre de polling pouvant manquer une transition courte ;
- meilleur rattachement aux contextes automation/script/utilisateur.

La classe `HAStateChangeStream` n'expose aucune commande WebSocket générique. Après authentification, elle n'émet que `subscribe_events` pour `state_changed`.

### 2. Filtrage des événements

Le flux `state_changed` peut contenir beaucoup d'updates d'attributs. Le recorder conserve :

- tous les vrais changements d'état principal ;
- un petit ensemble d'attributs de commande génériques par domaine quand ils changent réellement, notamment `cover.current_position` ;
- jamais un simple `last_updated` sans effet métier.

Le mécanisme reste générique Home Assistant et ne contient aucun Entity ID Maison Cognitive en dur.

Les capteurs sont enregistrés, mais ne lancent pas automatiquement une recherche causale inverse coûteuse à chaque mesure. L'enrichissement profond automatique est borné aux domaines contrôlables/visibles utiles (`light`, `switch`, `cover`, `climate`, etc.).

### 3. Écriture du journal avant enrichissement

Contrat de robustesse :

`state_changed -> normalisation -> INSERT SQLite -> file d'enrichissement`

L'effet observé est donc persistant **avant** toute recherche de cause. Une erreur, un timeout ou une file saturée peut laisser la cause `indeterminate`, mais ne doit pas faire perdre l'événement.

Le worker utilise une file bornée et deux enrichisseurs par défaut. En saturation, seul l'enrichissement est abandonné ; l'événement reste stocké.

### 4. Attribution de provenance

Ordre conservateur :

1. contexte direct prouvé (utilisateur) ;
2. Logbook/context pour automation/script ;
3. trace exacte de cette automation/script proche de l'événement ;
4. vérification que l'action exécutée vise réellement l'entité et correspond à l'effet ;
5. sinon `unknown` / `indeterminate`.

`Alexa` n'est jamais inféré d'un simple `user_id`. Le modèle sait porter `origin_type=alexa`, mais dev.29 ne l'émettra pas tant qu'une preuve terrain fiable ne sera pas définie.

### 5. Moteur causal d'enrichissement

Le moteur manuel dev.28 reste inchangé.

Le journal possède un **moteur d'enrichissement séparé**, dérivé de la lignée validée dev.16. Les modules suivants ont été réintroduits explicitement :

- `causal_utils.py` ;
- `condition_context.py` ;
- `action_effect_cause.py` ;
- `branch_decision_cause.py` ;
- `human_cause.py` ;
- `trigger_semantics.py` ;
- `human_explanation.py` ;
- `uncertainty_explanation.py` ;
- `v02_investigator.py`.

Ce moteur conserve notamment :

- matching sur **l'intervalle complet** d'une trace longue, pas seulement son heure de début ;
- priorité au `wait_for_trigger` qui libère réellement l'action ;
- décision locale `choose/default` quand elle est prouvée ;
- matching entre commande exécutée et effet observé ;
- épisode cohérent de mouvement d'un volet (`open -> closing -> closed`, etc.).

### 6. Cause fonctionnelle d'une valeur calculée

Nouveau module dev.29 : `runtime_decision.py`.

Problème traité : une automatisation peut être déclenchée périodiquement, alors que la valeur réellement commandée est calculée à partir du soleil, de la luminosité, de la température, etc. Le timer dit **quand le calcul a été réévalué**, pas **pourquoi la valeur a été choisie**.

Extraction conservatrice :

1. une seule commande exécutée doit correspondre exactement à l'effet observé (ex. `cover.set_cover_position = 40`) ;
2. une variable runtime doit avoir exactement cette valeur cible ;
3. cette variable doit correspondre à une variable configurée de l'automatisation ;
4. le graphe de dépendances de cette variable est construit à partir de ses expressions ;
5. seules les entrées externes prouvées (`states(...)` / `state_attr(...)`) sont retenues ;
6. les dépendances directes de la valeur finale sont préférées aux dépendances transitoires ;
7. si plusieurs commandes correspondent ou si le lien est ambigu, aucune raison fonctionnelle n'est produite.

Exemple jumeau numérique salon : une cible finale `position_corrigee=40`, calculée directement à partir d'azimut, élévation et luminosité et indirectement d'une position de base, produit la raison générique :

> le calcul automatique de cette valeur tenait compte de la position du soleil et de la luminosité

Cette formulation prouve une **dépendance de décision**. Elle ne prétend pas qu'un facteur donné a franchi à lui seul un seuil décisif si la trace ne le permet pas.

### 7. Stockage

SQLite local sous `/data/causal_journal.sqlite3`, appartenant à Investigator.

Table compacte indexée par `entity_id + event_time`. On stocke :

- entité + nom ;
- heure ;
- changement (`before`, `after`, attribut éventuel) ;
- origine ;
- raison fonctionnelle compacte ;
- trigger/facteurs utiles ;
- niveau de certitude ;
- références de preuve (`trace_run_id`, chemin), pas la trace brute complète.

SQLite est en WAL avec transactions. La même ligne est mise à jour après enrichissement ; aucun doublon « effet brut / effet enrichi » n'est créé.

Purge automatique selon la durée choisie.

### 8. Réponse à une question

Flux normal implémenté :

`question -> résolution entité/indices -> journal causal -> réponse`

Le journal respecte les indices explicites de valeur, attribut et heure. Une valeur demandée qui n'existe pas dans le journal n'est jamais ignorée pour retourner arbitrairement le dernier événement.

Si aucune entrée ne correspond :

- option secours activée : moteur d'enquête approfondie actuel ;
- option secours désactivée : réponse courte indiquant qu'aucun événement enregistré ne permet de conclure.

L'IHM d'investigation manuelle et `POST /api/v1/investigate` restent sur le moteur dev.28 existant.

### 9. Contrat LLM minimal

Exemples :

```json
{"entity":"Lampe entrée","event":"turned_off","time":"2026-08-28T08:38:53+00:00","confidence":"confirmed","value":"off","reason":"il n'y avait plus de mouvement"}
```

```json
{"entity":"Lampe salon","event":"turned_on","time":"2026-08-28T10:03:18+00:00","confidence":"confirmed","value":"on","source":"Alexa"}
```

Le payload LLM ne contient jamais : configuration d'automatisation, trace brute, Entity ID de l'automatisation, variables techniques complètes, endpoint MCP, jetons ou secrets.

## Tests et garde-fous

La suite dev.29 couvre notamment :

- persistance et réouverture SQLite ;
- purge 1–72 h ;
- mise à jour atomique d'une ligne après enrichissement ;
- recherche ciblée par valeur/heure ;
- projection LLM minimale ;
- normalisation des `state_changed` ;
- abonnement WebSocket lecture seule ;
- enregistrement avant enrichissement ;
- politique de charge (capteurs sans enquête inverse systématique) ;
- cause mouvement ;
- refus d'inventer une raison à partir d'un `time_pattern` ;
- réponse fonctionnelle sans nom d'automatisation ;
- routage `journal d'abord / fallback optionnel` ;
- extraction générique soleil/lux d'une valeur calculée ;
- rejet des commandes ambiguës ;
- matching d'une action dans une trace longue ;
- tests statiques interdisant les appels HA mutateurs dans les nouveaux modules.

## Lignée source — point de vigilance

L'image terrain dev.28 est construite directement depuis `dev28-mcp-independent-picker`. Les raffinements causaux dev.9–dev.16 existaient dans le worktree privé Maison Cognitive mais n'étaient pas tous présents dans l'arbre public dev.28. Dev.29 les a donc réconciliés explicitement dans sa branche candidate au lieu de supposer qu'ils existaient dans le code public.

## Risques restant à valider sur le terrain

- forme exacte des variables runtime dans les traces réelles Home Assistant : le jumeau numérique est validé, mais l'extraction soleil/lux doit être confirmée sur une vraie trace du volet salon ;
- charge réelle des enrichissements sur une journée : worker borné et métriques présents, réglage éventuel après mesure ;
- `trace_run_id` : référence interne à confirmer contre la forme exacte des traces live ;
- provenance Alexa : volontairement non implémentée tant qu'une preuve déterministe n'est pas disponible ;
- variantes Jinja autres que `states('...')` / `state_attr('...')` : elles échouent actuellement de façon conservatrice plutôt que d'être devinées.

## Prochain passage

1. CI complète sur le head dev.29 ;
2. build d'une image candidate privée dev.29 ;
3. **aucune installation HA sans Go explicite** ;
4. terrain lecture seule : démarrage, charge, persistance, lampe mouvement, volet salon position calculée, fallback on/off ;
5. seulement après PASS terrain : décision de promotion.
