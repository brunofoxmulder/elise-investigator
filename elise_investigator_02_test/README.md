# Élise Investigator 0.2 Test

Manifest public minimal pour tester la candidate privée `0.2.0-dev.15` sous Home Assistant OS.

- Aucun code Python de la 0.2 n'est publié dans ce dossier.
- L'application utilise l'image privée `ghcr.io/brunofoxmulder/elise-investigator-private:0.2.0-dev.15`.
- Architecture de test : `amd64` uniquement.
- Démarrage : manuel.
- Ingress activé.
- Port externe 8099 désactivé.
- Accès Home Assistant : API interne requise, application conçue en lecture seule.
- AppArmor activé.
- Dev.15 ajoute uniquement l'observabilité : journal local glissant 10 jours sous `/data/audit`, `request_id`, étapes de traitement, détail de résolution et de sélection d'événement, vue « Dernières demandes » et exports JSONL/TXT.
- Aucun changement du moteur causal, de la politique de preuve ni des droits Home Assistant.

Cette entrée est expérimentale et destinée aux essais contrôlés avant toute promotion de la 0.2.
