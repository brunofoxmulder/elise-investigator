# Élise Investigator 0.2 Test

Manifest public minimal pour tester la candidate privée `0.2.0-dev.29` sous Home Assistant OS.

- Image privée : `ghcr.io/brunofoxmulder/elise-investigator-dev29-private:0.2.0-dev.29`.
- Architecture : `amd64` uniquement.
- Démarrage : manuel.
- Ingress activé.
- Port externe 8099 désactivé.
- Accès Home Assistant : API interne, application strictement en lecture seule.
- AppArmor activé.

## Dev.29 — journal causal persistant

Dev.29 conserve l'investigation manuelle et la Recherche MCP locale de dev.28. Elle ajoute un journal causal local persistant alimenté par les événements `state_changed` de Home Assistant.

Le flux conversationnel consulte d'abord ce journal. Pour une action automatique, la réponse doit privilégier la raison fonctionnelle prouvée ; le nom de l'automatisation et sa trace restent des preuves internes. Pour une action directe, la source utilisateur est restituée ; Alexa n'est nommée que si cette provenance est réellement prouvée.

L'IHM expose la durée de conservation du journal (1 à 72 h), l'activation de l'enquête approfondie de secours et l'état du worker causal. L'événement est persisté avant enrichissement afin qu'une erreur d'analyse ne fasse pas perdre le changement observé.

Le moteur causal reste déterministe, sans LLM et sans service Home Assistant mutateur. Les niveaux `confirmed`, `probable` et `indeterminate` restent inchangés.

Cette entrée est expérimentale. La mise à jour de l'app de test doit rester manuelle pendant la validation terrain.
