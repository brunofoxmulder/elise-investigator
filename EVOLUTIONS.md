# Élise Investigator — Bugs, observations et évolutions

Dernière mise à jour : 23 août 2026
Version de référence : `0.1.0-beta.16`

## Objectif du fichier

Ce document suit les bugs rencontrés, les limites observées sur le terrain et les évolutions envisagées pour Élise Investigator.

Il complète le `CHANGELOG.md` :
- le changelog décrit ce qui a été livré ;
- ce fichier conserve ce qui reste à étudier, tester ou développer.

Principe permanent : **Home Assistant comprend le langage ; Élise Investigator prouve la cause.**

## État actuel

- beta.16 validée sur plusieurs cas réels.
- Interface locale volontairement structurée : choix de l'entité + champs facultatifs.
- Moteur strictement en lecture seule.
- Niveaux de conclusion conservateurs : `confirmed`, `probable`, `indeterminate`.
- La preuve causale reste du ressort exclusif d'Investigator.
- Fonctionnalités gelées pendant une période d'observation terrain avant V1.

## Bugs corrigés / régressions traitées

### Démarrage et environnement HAOS

- Permissions AppArmor/S6 empêchant le démarrage.
- `ha_client` introuvable à l'exécution.
- `SUPERVISOR_TOKEN` absent dans le premier environnement de lancement.
- Routage Ingress renvoyant 404 à cause du double slash.

### Preuve causale

- Une simple référence de configuration pouvait être prise à tort pour une preuve d'exécution.
- Plusieurs automatisations candidates pouvaient conduire à une attribution trop affirmative.
- Correction : seule l'exécution réellement observée dans les traces peut servir de preuve forte ; plusieurs candidats exécutés donnent une conclusion indéterminée tant qu'aucun lien exclusif n'est établi.

### Historique Home Assistant

- Faux événement possible au début de la fenêtre History : un état déjà actif pouvait être interprété comme une transition `None → état`.
- Correction beta.10 : un état de bord de fenêtre n'est plus traité comme un événement prouvé.

### Compréhension locale en texte libre

- beta.12 a montré une régression de la compréhension libre malgré l'ajout de règles de désambiguïsation.
- Décision : ne pas développer un mini-NLP/LLM local dans Investigator.
- La compréhension naturelle reste confiée à l'agent conversationnel Home Assistant existant.

## Observations terrain à suivre

### Fenêtre temporelle par défaut

La fenêtre automatique actuelle est de 30 minutes.

Observation : elle peut être un peu courte pour une investigation réalisée après coup.

À évaluer sur plusieurs cas avant décision : 45 ou 60 minutes par défaut.

### Chaîne causale humaine et prouvée

La cause technique peut être correcte mais la formulation peut encore être trop centrée sur le nom de l'automatisation.

Objectif futur : expliquer, lorsque les preuves le permettent, la chaîne complète :

1. événement déclencheur réel ;
2. conditions/contexte vérifiés ;
3. automatisation ou script exécuté ;
4. effet observé sur l'entité.

Exemple attendu :

> Le volet du salon a été positionné à 80 % parce que la température extérieure était supérieure à 25 °C.

Règle : une condition n'est jamais présentée comme cause si la trace ne prouve pas qu'elle a participé à l'exécution concernée.

### Affichage du nom de l'automatisation

Évolution souhaitée : ajouter un choix utilisateur mémorisé permettant d'afficher ou non le nom de l'automatisation dans la réponse principale.

- Mode simple : explication naturelle uniquement.
- Mode détaillé : explication naturelle + nom de l'automatisation/script.
- Le nom technique reste toujours disponible dans les preuves structurées.

### Attribution des actions

Ne pas écrire « Élise a déplacé/allumé/fermé… » : l'application est en lecture seule et n'exécute aucune commande.

Préférer :

> Le volet a été positionné à 80 % parce que…

## Évolutions prévues / à étudier

### 1. Mini-intégration Home Assistant ↔ Investigator

But : permettre à l'agent conversationnel Home Assistant/OpenAI existant d'appeler Investigator pour les questions de type « pourquoi ? ».

Architecture cible :

`Utilisateur → Assist/Alexa/agent HA → outil Investigator → /api/v1/investigate → moteur causal → réponse HA`

Contraintes :
- ne pas créer un second LLM ;
- ne pas utiliser `/api/v1/ask` pour la preuve causale ;
- l'agent ne peut jamais renforcer un niveau de certitude renvoyé par Investigator ;
- aucune commande Home Assistant depuis Investigator.

### 2. Chaîne causale explicative

Étudier l'extraction fiable, à partir des traces HA, du déclencheur et des conditions réellement évaluées afin d'améliorer la réponse humaine sans réduire la rigueur de preuve.

### 3. Fenêtre temporelle

Décider après observation terrain si la fenêtre par défaut doit passer de 30 à 45/60 minutes.

### 4. Ergonomie de réponse

Ajouter le choix « afficher le nom de l'automatisation » sans toucher au moteur causal.

### 5. V1

Passage en V1 uniquement après plusieurs jours d'utilisation réelle sans régression significative et après revue des observations consignées ici.

## Points techniques à vérifier avant le pont conversationnel

- URL/DNS interne exact entre Home Assistant Core et l'app HAOS.
- Authentification de l'API interne.
- Régénération du jeton Investigator avant usage opérationnel du pont, l'ancien ayant déjà été exposé dans des captures/conversations de test.
- Maintien du port externe 8099 désactivé par défaut.
- Vérifier l'utilité résiduelle de l'ancienne intégration `elise-why` avant toute suppression.

## Règles de non-régression

- Lecture seule stricte.
- Pas de `/config` monté dans l'app.
- Pas de service HA mutateur.
- Configuration mentionnée ≠ exécution prouvée.
- Plusieurs candidats sans lien exclusif = `indeterminate`.
- Une condition est un contexte/filtre, pas automatiquement une cause.
- Un état présent au bord de la fenêtre History n'est pas un événement.
- L'IA conversationnelle ne peut pas inventer une cause ni augmenter la certitude fournie par Investigator.
