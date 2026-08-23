# Changelog

## 0.2.0-dev.8

- Correction du rapprochement temporel des traces longues : une exécution est maintenant rapprochée de l'effet observé sur son intervalle réel `start → finish`, et non uniquement sur son heure de départ.
- Le garde-fou reste conservateur : si l'heure de fin n'est pas disponible, le comportement antérieur basé sur le début de trace est conservé.
- Cas de non-régression ajouté à partir du test terrain salle de bain : automatisation démarrée environ 9 minutes avant l'extinction mais terminée au moment de l'effet.
- Ajout d'un bouton `Log` dans l'interface : il copie le diagnostic technique nettoyé pour analyse, sans envoi automatique et avec retrait des secrets connus.
- Lecture seule, Ingress, AppArmor et port externe 8099 inchangés.

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
