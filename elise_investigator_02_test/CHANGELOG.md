# Changelog

## 0.2.0-dev.7

- Cause humaine désormais liée à l'action observée lorsque la trace le prouve, au lieu de reprendre systématiquement le déclencheur initial de l'automatisation.
- Premier cas certifié : extinction après fin d'un `wait_for_trigger` d'absence de mouvement.
- Mode Simple : cause humaine courte.
- Mode Détaillé : cause + règle utile + automatisation/script confirmé.
- Moteur toujours strictement en lecture seule ; aucune modification des droits HAOS.

## 0.2.0-dev.6

- Première candidate de test HAOS distribuée depuis une image GHCR privée.
- Code source 0.2 absent du manifeste public.
- Slug séparé de beta.16 pour permettre un essai côte à côte.
- Démarrage manuel, Ingress activé, port externe 8099 désactivé, AppArmor activé.
