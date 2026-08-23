# Élise Investigator 0.2 Test

Manifest public minimal pour tester la candidate privée `0.2.0-dev.9` sous Home Assistant OS.

- Aucun code Python de la 0.2 n'est publié dans ce dossier.
- L'application utilise l'image privée `ghcr.io/brunofoxmulder/elise-investigator-private:0.2.0-dev.9`.
- Architecture de test : `amd64` uniquement.
- Démarrage : manuel.
- Ingress activé.
- Port externe 8099 désactivé.
- Accès Home Assistant : API interne requise, application conçue en lecture seule.
- AppArmor activé.
- L'interface contient un bouton `Log` qui copie un diagnostic technique nettoyé pour analyse ; rien n'est envoyé automatiquement.

Cette entrée est expérimentale et destinée aux essais contrôlés avant toute promotion de la 0.2.
