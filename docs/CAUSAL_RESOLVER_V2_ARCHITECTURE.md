# Élise Investigator — Causal Resolver V2

## Statut

Branche d’architecture uniquement. Aucun déploiement Home Assistant. Aucune promotion terrain.

Base : `dev73-native-reason-firewall`.

Objectif : remplacer l’empilement de politiques causales successives par une décision unique centrée sur **l’action exacte qui a produit l’effet observé**.

## Constats terrain dev.73

PASS observés :
- commande utilisateur directe ;
- Tineco : trigger d’état correctement remonté ;
- lampe salon : trigger solaire correctement remonté ;
- extinction entrée : `wait_for_trigger` correctement remonté.

KO observés :
- allumage entrée : automatisation trouvée, `reason = null` ;
- allumage salle de bain : automatisation trouvée, `reason = null` ;
- allumage hotte : automatisation trouvée, `reason = null` ;
- extinction salle de bain / hotte : automatisation trouvée, `reason = null` ;
- volet salon sur gestion solaire/périodique : automatisation trouvée, `reason = null`.

## Défauts structurels identifiés

### 1. Barrière temporelle globale au lieu d’être relative à l’action cible

La logique dev.71 bloque le fallback vers le trigger initial dès qu’un `delay`, `wait_for_trigger` ou `wait_template` exécuté existe quelque part dans la trace.

C’est faux pour une séquence :

`mouvement -> allumage -> wait_for_trigger -> extinction`

Le wait situé **après** l’allumage ne doit jamais invalider le mouvement comme cause de l’allumage.

Règle V2 : une barrière temporelle n’influence l’explication que si elle se situe sur le chemin exécuté **avant la commande cible**.

### 2. Sélection de trace basée sur l’heure de début avec coupure fixe à 300 s

Une automatisation peut démarrer puis produire l’effet cible plusieurs minutes plus tard. Une distance entre début de trace et événement n’est donc pas une preuve suffisante pour accepter ou rejeter la trace.

Règle V2 : rattacher une trace à l’effet par la **commande exécutée sur l’entité cible** et, lorsque disponible, son timestamp runtime. La proximité du démarrage de la trace devient un simple critère de recherche, jamais une preuve causale finale.

### 3. Sémantique de trigger incomplète

`time_pattern` peut être un trigger prouvé mais ne possède pas de rendu humain générique dans le renderer actuel.

Règle V2 : tout trigger HA accepté comme preuve par le résolveur doit avoir soit un rendu humain générique, soit produire une réponse explicitement indéterminée ; jamais `null` silencieux après preuve.

### 4. Plusieurs couches écrivent et réécrivent `reason`

Activity, source hints, exact trace, enrichers successifs puis firewall peuvent tous modifier la raison finale.

Règle V2 : les lecteurs collectent les faits et preuves. **Un seul résolveur causal** choisit la cause sémantique finale. **Un seul renderer** transforme cette cause en texte utilisateur.

## Politique de preuve V2

Ordre strict :

1. Identifier le fait observé.
2. Identifier l’origine native HA : user / automation / script / unknown.
3. Pour automation/script, identifier une trace contenant la commande runtime qui produit exactement l’effet cible.
4. Identifier la commande cible unique.
5. Chercher une cause locale prouvée située avant cette commande sur le chemin exécuté :
   - `wait_for_trigger` terminé ;
   - timeout ;
   - `delay` écoulé ;
   - décision locale de branche lorsque sa sémantique explique directement l’action.
6. À défaut de cause locale, utiliser le trigger initial runtime prouvé.
7. Les conditions `state` ordinaires restent des guards et ne sont pas ajoutées à la phrase causale.
8. Une conjonction n’est conservée que lorsqu’elle possède une sémantique causale explicitement supportée et prouvée, notamment les seuils `numeric_state` déjà validés.
9. Une barrière située après la commande cible est ignorée pour l’explication de cette commande.
10. Si la preuve est insuffisante : fail closed. Attribution à l’automatisation possible, mais aucune fausse cause.

## Invariants à préserver

- strictement lecture seule ;
- aucune connaissance codée spécifique Maison Cognitive ;
- aucun graphe causal ;
- aucune corrélation temporelle large ;
- gestion `unknown` / `unavailable` conservée ;
- épisodes cover `opening -> open` et `closing -> closed` conservés ;
- commandes utilisateur conservées ;
- causes conjointes prouvées type heures creuses + batterie basse conservées ;
- aucune phrase native fournisseur `triggered by ...` exposée à l’utilisateur.

## Matrice obligatoire avant toute candidate terrain

1. Présence ON : `mouvement -> light.turn_on -> wait` => cause mouvement.
2. Présence OFF : `mouvement -> ... -> wait_for_trigger off for N -> light.turn_off` => cause absence après attente.
3. Même scénario avec attente 5 minutes => aucune dépendance à une fenêtre fixe de 300 s.
4. Tineco / trigger state simple => trigger state.
5. Trigger solaire => sémantique solaire.
6. Trigger `time_pattern` => sémantique périodique générique.
7. Volet avec commande positionnelle => rattachement à la commande exacte.
8. Commande utilisateur => user.
9. Action différée => cause locale delay/wait, jamais trigger initial recyclé.
10. Guards state => non promus.
11. Cause conjointe state + numeric_state prouvée => conservée.
12. `unknown/unavailable` => ne masque pas le dernier vrai changement fonctionnel.

Aucune image HAOS et aucune promotion du canal Test ne seront produites avant PASS de cette matrice.