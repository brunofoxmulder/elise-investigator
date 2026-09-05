# Changelog

## 0.2.0-dev.56 — causalité native Logbook

- Base exacte : dev.55 terrain figée au commit `16e3a911e8268aac4b76d074f88299c4c8324732`.
- Conserve l'apport dev.55 sur les interruptions techniques `unknown` / `unavailable` et la sélection du dernier vrai changement fonctionnel.
- Exploite désormais `context_source` puis `context_message` déjà fournis par le Logbook lorsque Home Assistant confirme une automation/script mais que l'enrichissement ciblé laisserait autrement `reason=null`.
- Les formes natives `state of ...`, `numeric state of ...` et `device of ...` sont rendues en cause de premier niveau sans inventer la valeur d'état, le seuil, la branche ni une temporisation absente de la preuve native.
- Les triggers périodiques ou purement techniques (`time_pattern`, démarrage Home Assistant, etc.) ne sont pas promus artificiellement en raison fonctionnelle.
- Les chemins existants de trace ciblée sont conservés pour l'approfondissement : `wait_for_trigger`, temporisation précise, branche `choose/default`, condition exécutée, variable runtime, cible calculée ou facteurs combinés.
- Cas terrain prioritaires : prise aspirateur et prise brosse à dents ; non-régression obligatoire : chargeur téléphone 2, lampe entrée, volet salon et commande utilisateur directe.
- Qualification : compilation PASS, tests unitaires + digital twin PASS, garde-fous lecture seule PASS, image privée amd64 construite et manifeste vérifié.
- Image candidate : `ghcr.io/brunofoxmulder/elise-investigator-dev56-private:0.2.0-dev.56`.

## 0.2.0-dev.55 — filtrage fonctionnel des interruptions de disponibilité

- Base exacte : dev.54 validée ; la branche figée `dev54-fallback-stable` reste le repli officiel.
- Apport principal : filtre fonctionnel générique pour `light`, `switch`, `input_boolean`, `fan` et `humidifier` afin que `on/off → unavailable → unknown → même état` soit traité comme une interruption de disponibilité, pas comme un nouveau changement fonctionnel.
- Si l'objet revient dans un état fonctionnel différent après indisponibilité, le changement reste `indeterminate` : Investigator n'invente ni l'instant ni la cause pendant la coupure.
- Une récupération sans état fonctionnel antérieur connu après redémarrage reste fail-closed.
- Une perte de disponibilité casse un épisode brightness en cours afin de ne pas propager une ancienne cause au-delà d'une discontinuité technique.
- Les épisodes covers `opening/closing → open/closed`, les épisodes brightness et la reconnaissance HA Voice `assist_satellite.*` de dev.54 restent conservés.
- La promotion de `context_source/context_message` comme cause native de premier niveau n'appartient pas à dev.55 ; elle est apportée par dev.56.
- Qualification dev.55 : 225/225 tests PASS, compilation PASS, garde-fous lecture seule PASS.
- Image : `ghcr.io/brunofoxmulder/elise-investigator-dev55-private:0.2.0-dev.55`.

## 0.2.0-dev.54 — référence terrain et version de repli

- Ajout limité : reconnaissance d'une commande directe Home Assistant Voice `assist_satellite.*` comme origine générique `user` lorsqu'une lignée de Context la prouve.
- Une automation ou un script déjà prouvé reste prioritaire et n'est jamais relabellisé `user`.
- Aucune proximité temporelle seule n'est utilisée comme preuve HA Voice.
- Logique lumière off↔on, épisodes brightness et épisodes covers conservés.
- Qualification dev.54 : 215/215 tests PASS, HA Voice PASS, commande utilisateur existante PASS, lumière off↔on PASS, volets PASS, lecture seule PASS.
- Image : `ghcr.io/brunofoxmulder/elise-investigator-dev54-private:0.2.0-dev.54`.
- Branche de secours figée : `dev54-fallback-stable` au commit `8fc625217dbc0284496ad435a2ea8d9e7fee46b9`.
- Règle de rollback : tout incident significatif sur une dev supérieure doit permettre un retour exact à cette dev.54 avant nouvelle correction.

## Historique antérieur

Les évolutions antérieures restent conservées dans l'historique Git du projet. Cette vue met en tête les versions directement utiles à la lignée dev.54 → dev.55 → dev.56.
