# Changelog

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
