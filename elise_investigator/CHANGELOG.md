# Changelog

## 0.1.0-beta.11

- Ajout d'un **mode conversationnel** : l'utilisateur peut écrire une question naturelle telle que « Élise, pourquoi la lampe de la salle de bain vient de s'allumer ? ».
- Ajout de l'endpoint lecture seule `POST /api/v1/ask`, qui résout prudemment le nom convivial de l'objet, interprète une valeur d'état simple et une heure approximative éventuelle, puis transmet une requête structurée au moteur causal existant.
- La résolution d'objet privilégie les `entity_id` explicites et les noms conviviaux complets ; un rapprochement par mots n'est utilisé qu'en secours. En cas d'ambiguïté, la version refuse de deviner et retourne les candidats.
- Interprétation de quelques formulations utiles : allumage/extinction, ouverture/fermeture, modes clim `cool`, `heat`, `off`, `auto`, `dry`, `fan_only`, heure « vers 22h05 », « hier vers 18h », date `22/08`, ou « il y a 10 minutes ».
- Une formulation « vient de… » sans heure reste volontairement sans timestamp artificiel afin de laisser Investigator chercher le dernier événement réel dans sa fenêtre normale.
- Ajout dans l'interface d'un bloc **« Demander à Élise »** au-dessus du mode précis. Le formulaire structuré historique reste disponible sans modification de son contrat.
- Ajout d'un bouton utilisateur **« Écouter la réponse »** lorsque la synthèse vocale du navigateur est disponible. Aucun son n'est envoyé au serveur par cette fonction ; elle ne déclenche qu'une lecture de la réponse déjà affichée côté navigateur.
- Ajout d'un descripteur machine `GET /api/v1/conversation-tool` et documentation OpenAPI de `/api/v1/ask` pour préparer le raccordement ultérieur à une IA conversationnelle/voix.
- Ajout de tests unitaires dédiés à la résolution naturelle d'entité, aux états et aux heures approximatives.
- La politique causale beta.10 reste inchangée, hormis l'alignement du numéro de version interne sur beta.11.
- Aucun nouveau privilège Home Assistant, aucun appel de service mutateur, aucun accès à `/config`, aucun changement AppArmor/Ingress et aucun port supplémentaire.

## 0.1.0-beta.10

- Correction d'un faux événement `None → état` observé quand l'API History renvoie l'état déjà actif exactement au début de la fenêtre examinée.
- Sans heure observée explicite, un premier état sans état précédent et horodaté au bord de la fenêtre n'est plus traité comme une transition causale.
- Dans ce cas, le verdict reste `indeterminate`, le type d'événement devient `window_boundary_state` et la réponse indique que l'objet était déjà dans cet état au début de la période examinée.
- Les candidats de recherche inverse, traces et entrées Logbook calculés autour de ce faux timestamp sont retirés du résultat pour éviter toute attribution causale artificielle.
- La preuve History est conservée comme preuve de support d'un état de bord, et non comme preuve directe d'une transition.
- Une heure observée fournie explicitement par l'utilisateur n'est pas affectée par cette règle.
- Ajout de tests de régression pour le cas lampe télé et pour la protection du cas avec heure observée explicite.
- Le diagnostic copié utilise désormais la version remontée par le moteur, afin d'éviter les écarts de version interface/moteur.
- Aucun changement des permissions Home Assistant, d'Ingress, d'AppArmor, des ports exposés ou du contrat strictement lecture seule.

## 0.1.0-beta.9

- Ajout d'un bouton **« Copier le diagnostic pour Élise »** pour les verdicts `probable` et `indeterminate` uniquement.
- La copie est strictement déclenchée par l'utilisateur : aucun envoi automatique, aucun stockage serveur et aucun appel réseau supplémentaire.
- Le texte copié contient l'objet sélectionné, l'`entity_id`, la requête d'investigation, le verdict, le texte de réponse et les preuves structurées nécessaires à une analyse externe.
- Ajout d'une redaction défensive des clés sensibles (`token`, `authorization`, `secret`, `password`, clés API / access tokens) et des chaînes `Bearer ...` avant copie dans le presse-papiers.
- Le jeton de connexion affiché dans l'interface n'est jamais inclus dans le diagnostic copié.
- Fallback de copie compatible avec les WebView ne disposant pas de `navigator.clipboard`.
- Aucun changement du moteur causal, des permissions Home Assistant, d'Ingress, d'AppArmor, des ports ou du contrat lecture seule.

## 0.1.0-beta.8

- Amélioration ergonomique mobile : remplacement de la saisie brute d'`entity_id` par un sélecteur d'objets Home Assistant intégré.
- Recherche instantanée par nom convivial, `entity_id` ou domaine ; la liste affiche le nom, l'identifiant technique et l'état courant.
- Ajout d'un historique local des six derniers objets sélectionnés pour accélérer les investigations répétées.
- L'utilisateur peut toujours saisir un `entity_id` exact ; un nom convivial exact et unique est également résolu automatiquement.
- Ajout de l'endpoint lecture seule `GET /api/v1/entities`, alimenté uniquement par `GET /states` via le client Home Assistant existant.
- Aucun nouveau privilège Home Assistant, aucun service d'action, aucun accès à `/config`, aucun changement AppArmor/Ingress et aucun port supplémentaire.
- La politique de preuve causale de beta.7 reste inchangée.

## 0.1.0-beta.7

- Correction de la logique de preuve causale après le premier test fonctionnel réel sur le volet salon.
- Une simple mention de l'entité dans la configuration contenue dans une trace n'est plus considérée comme une action exécutée : seule la branche runtime `trace` est examinée pour prouver une action vers la cible.
- Lorsque plusieurs exécutions proches ont réellement ciblé la même entité, le verdict devient désormais `indeterminate` avec des candidats documentés au lieu de `confirmed`.
- Les traces ambiguës restent conservées comme preuves de support, mais ne sont plus présentées comme attribution causale directe.
- Le texte de réponse évite désormais la contradiction « cause confirmée » / « aucune cause système établie » dans ce cas.
- Aucun changement des permissions Home Assistant, d'Ingress, d'AppArmor, de `/config` ou des ports exposés.
- Version interne du moteur/policy alignée sur `0.1.0-beta.7`.

## 0.1.0-beta.6

- Correction de compatibilité de l'entrée Web UI Ingress après validation du démarrage complet de la beta.5 sur HAOS.
- La beta.5 restait en cours d'exécution mais l'ouverture de l'interface renvoyait `404: Not Found`.
- Les routes HTTP connues disposent désormais d'un alias à double slash initial (`//...`) afin de tolérer un chemin Ingress comportant un slash supplémentaire, sans ajouter de route générique ni masquer les erreurs API.
- La route d'accueil journalise le chemin d'alias réellement utilisé afin de confirmer le diagnostic lors du test HAOS.
- Aucun changement du moteur causal, des autorisations Home Assistant, d'AppArmor ou des ports exposés.
- Version interne de l'API alignée sur `0.1.0-beta.6`.

## 0.1.0-beta.5

- Correction de l'accès au jeton Supervisor après validation du runtime Python en beta.4.
- `run.sh` utilise désormais le shebang officiel Home Assistant `#!/usr/bin/with-contenv bashio` afin de transmettre les variables d'environnement Supervisor au processus Python.
- Le profil AppArmor autorise explicitement l'exécution de Bashio via `/usr/lib/bashio/**` sans désactiver AppArmor.
- `homeassistant_api: true` reste inchangé ; aucun accès Supervisor supplémentaire (`hassio_api`) n'est ajouté.
- Aucun changement du moteur causal, aucun accès à `/config`, aucun service Home Assistant mutateur et aucun port externe activé.
- Version interne de l'API alignée sur `0.1.0-beta.5`.

## 0.1.0-beta.4

- Correction du démarrage Python après validation du bootstrap S6/AppArmor de la beta.3.
- `WORKDIR /app` et `PYTHONPATH=/app` sont désormais explicites dans l'image.
- `run.sh` démarre depuis `/app` avant de lancer `main.py`.
- Le profil AppArmor autorise explicitement la lecture du répertoire `/app/` en plus de ses fichiers.
- Aucun changement du moteur causal, aucun accès à `/config`, aucun service Home Assistant mutateur et aucun port externe activé.
- Version interne de l'API alignée sur `0.1.0-beta.4`.

## 0.1.0-beta.3

- Correction du démarrage sous AppArmor avec l'image de base Home Assistant et S6-Overlay.
- Ajout des chemins S6 requis (`/run/{s6,s6-rc*,service}`, `/package`, `/command`, scripts d'initialisation `/etc/...`) sans désactiver AppArmor.
- `/init`, les exécutables système nécessaires et `run.sh` reçoivent explicitement les droits de lecture/exécution requis au bootstrap.
- Aucun nouveau montage Home Assistant, aucun accès à `/config`, aucun service d'action et aucun changement du moteur causal.
- Version interne de l'API alignée sur `0.1.0-beta.3`.

## 0.1.0-beta.2

- Correction de compatibilité Supervisor : suppression de `watchdog: true`, invalide dans la configuration d'une app Home Assistant.
- Aucun changement fonctionnel du moteur d'investigation, de l'interface Ingress ni de l'API.
- Le watchdog Supervisor reste volontairement désactivé jusqu'à l'ajout éventuel d'un véritable endpoint de santé.

## 0.1.0-beta.1

- Première bêta installable.
- Interface Ingress Home Assistant.
- API JSON `POST /api/v1/investigate`.
- Schéma OpenAPI pour raccordement d'une IA conversationnelle.
- Résolution d'entité via registre et `unique_id` quand disponible.
- Historique + Logbook comme preuves prioritaires.
- Lecture des traces natives `trace/list` / `trace/get`.
- Recherche inverse d'automatisations/scripts/scènes en dernier recours.
- Distinction état principal / attribut / disponibilité.
- Distinction commande prouvée / changement d'état observé.
- Classement confirmé / probable / indéterminé.
- Aucun appel de service Home Assistant et aucun montage de `/config`.
