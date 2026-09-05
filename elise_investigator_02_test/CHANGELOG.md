# Changelog

## 0.2.0-dev.55

- Base exacte : dev.54 validée ; la branche figée `dev54-fallback-stable` reste le repli officiel.
- Le chemin causal nominal privilégie désormais les primitives natives Home Assistant déjà capturées par Investigator : Context, `automation_triggered`, `call_service` et Logbook.
- Nouveau filtre fonctionnel générique pour `light`, `switch`, `input_boolean`, `fan` et `humidifier` : une séquence `on/off → unavailable → unknown → même état` est traitée comme une interruption de disponibilité et non comme un nouveau changement fonctionnel.
- Si l’objet revient dans un état fonctionnel différent après une indisponibilité, le changement est conservé mais reste `indeterminate` : Investigator n’invente ni l’instant ni la cause pendant l’interruption.
- Une récupération après redémarrage de l’App sans état fonctionnel antérieur connu est ignorée comme événement causal (fail-closed).
- Une perte de disponibilité casse explicitement un épisode brightness en cours afin d’éviter de propager une cause au-delà d’une discontinuité technique.
- Les épisodes covers `opening/closing → open/closed`, les épisodes brightness de dev.46 et la reconnaissance HA Voice `assist_satellite.*` de dev.54 restent conservés.
- La trace devient un approfondissement ciblé lorsqu’une automation ou un script est déjà identifié ; la recherche inverse historique reste hors du chemin conversationnel normal.
- Le journal SQLite reste la mémoire causale persistante lorsque les preuves natives ou les traces ne sont plus disponibles.
- Le runtime expose la stratégie `native_ha_first_functional_memory` et les compteurs de transitions techniques filtrées.
- Qualification avant terrain : 225/225 tests PASS, compilation PASS, garde-fous lecture seule PASS.
- Image candidate : `ghcr.io/brunofoxmulder/elise-investigator-dev55-private:0.2.0-dev.55`.

## 0.2.0-dev.54 — référence terrain et version de repli

- Base reconstruite depuis la lignée stable dev.46 sans réintroduire les régressions dev.47–dev.53.
- Ajout limité : reconnaissance d’une commande directe Home Assistant Voice `assist_satellite.*` comme origine générique `user` lorsqu’une lignée de Context la prouve.
- Une automation ou un script déjà prouvé reste prioritaire et n’est jamais relabellisé `user`.
- Aucune proximité temporelle seule n’est utilisée comme preuve HA Voice.
- Logique lumière off↔on, épisodes brightness dev.46 et épisodes covers conservés.
- Qualification dev.54 : 215/215 tests PASS, HA Voice PASS, commande utilisateur existante PASS, lumière off↔on PASS, volets PASS, lecture seule PASS.
- Image candidate : `ghcr.io/brunofoxmulder/elise-investigator-dev54-private:0.2.0-dev.54`.
- Branche de secours figée : `dev54-fallback-stable` au commit `8fc625217dbc0284496ad435a2ea8d9e7fee46b9`.
- Règle de rollback : tout incident significatif sur une dev supérieure doit permettre un retour exact à cette dev.54 avant nouvelle correction.

## Historique antérieur

Les évolutions dev.38 et antérieures restent conservées dans l’historique Git du projet. La présente vue met en tête les versions actuellement pertinentes pour la recette dev.55 et le rollback dev.54.
