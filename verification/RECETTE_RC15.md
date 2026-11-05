# RC15 — Proposition de recette, sans installation

La candidate modifie la reconnaissance d'alias des questions directes. Les demandes
vocales via Élise Why résolvent séparément leur cible par Home Assistant. Les deux
chemins doivent être testés ; le moteur causal et les règles des volets ne sont pas
modifiés.

## Préparation avant toute intervention

- Vérifier qu'une sauvegarde récente, complète et restaurable est disponible, avec
  sa clé. Vérifier son contenu : application, données et configuration nécessaires.
- Comparer le manifeste RC14 actuellement proposé sur le dépôt avec
  `rc14_reference_manifest.yaml` ; ne pas remplacer une version qui aurait changé.
- Le manifeste `proposed_rc15_manifest.yaml` est une proposition non déployée : sa
  version Supervisor, le tag OCI, l'étiquette de l'image et la version annoncée par
  l'application sont alignés sur `0.3.0-rc.15`.
- Vérifier les empreintes des images RC14 et RC15, la visibilité de l'image RC15 et
  l'architecture amd64 avant de prendre une décision.
- Vérifier le mécanisme réel de retour à RC14 avec Supervisor et l'étendue de la
  restauration ; une sauvegarde peut annuler des données plus récentes.

## Recette après validation explicite et installation

1. Vérifier démarrage, journaux, accès et collecte ; relever la latence des demandes.
2. Tester les questions directes avec les noms habituels, un alias existant et une
   demande ambiguë ; aucun alias n'est à créer sans validation spécifique.
3. Tester le chemin vocal Élise Why et les explications ON/OFF, notamment brosse à
   dents et aspirateur, au rythme des événements naturels.
4. Contrôler la conservation des résultats et les cas volets précédemment validés.
5. Si une anomalie apparaît, suspendre la recette, conserver les éléments utiles et
   décider avec Bruno du retour ou du maintien en observation.

Les essais isolés 2026.10.4/2026.11.0 ne démontrent pas le fonctionnement complet
sur le NUC, ni de la chaîne vocale réelle. Aucun changement de Home Assistant n'est
autorisé par ce document.
