# Changelog

## 0.3.0-rc.12 — déclencheur retrouvé après projection exacte de la commande

- Corrige les ON immédiats dont la source automation est reconnue mais la raison reste vide lorsque l'action exécutée n'a pas de `result.params`.
- La chaîne causale était construite avant la projection RC11 ; RC12 conserve toute cause déjà résolue, puis complète seulement la chaîne manquante après reconnaissance d'une commande exécutée unique.
- Le déclencheur reste celui de la trace runtime. Les délais et attentes antérieurs gardent leur rôle de barrière ; une attente ultérieure ne remplace pas la cause du ON.
- Priorité `result.params`, chemin runtime exact, résolution registry, refus de `device_id` seul, preuves brutes et chaîne d'origine conservés.
- Projection RC11, sélection des traces, resolver default/delay, renderer, âge des événements et dev.54 inchangés.
- Qualification : 413/413 tests PASS ; CI et construction/publication/vérification du manifeste de l'image privée amd64 PASS.
- Candidate : commit `295c86c536a46fac82c8db46b70b4697bd6471b0`, PR #86 non fusionnée.
- Image : `ghcr.io/brunofoxmulder/elise-investigator-v2-rc12-private:0.3.0-rc.12`.
- Promotion sur Test autorisée par Bruno le 15/09/2026. Installation manuelle et validation terrain encore requises ; aucun changement HA automatique.
- Recette : ON naturels des prises aspirateur et brosse à dents, leurs OFF et conservation des autres chemins validés.

## 0.3.0-rc.11 — projection exacte des device actions sans `result.params`

- Base exacte : RC10 terrain, sans modification du resolver default/delay RC9 ni du renderer.
- Cause racine confirmée : l'étape réellement exécutée `action/2/default/0` de l'automatisation Charge aspirateur ne contient pas `result.params`; RC10 retrouvait bien la configuration `action`, mais ne projetait pas la device action de ce nœud vers la commande normalisée attendue par le resolver.
- Règle RC11 : conserver `result.params` en priorité lorsqu'il existe ; sinon lire exclusivement la configuration située au même chemin runtime exécuté, sans recherche libre ni corrélation temporelle permissive.
- Mapping device action confirmé : la valeur opaque `entity_id` de l'action est l'ID de l'entrée du registre d'entités Home Assistant ; elle doit se résoudre exactement vers l'`entity_id` canonique de l'événement.
- La projection vérifie aussi le `device_id` et le domaine attendus ; une égalité sur le seul `device_id` est explicitement refusée afin de ne pas confondre, notamment, `switch.prise_aspirateur` avec `switch.prise_aspirateur_child_lock`.
- Tests ajoutés : absence de `result.params`, priorité de `result.params`, child lock, `wait_for_trigger`, délai adjacent, commande de service, device action et scénario bout en bout aspirateur OFF.
- Non-régressions explicites : volets, lumières, Tineco, commandes manuelles, âge de l'événement et firewall provider.
- Qualification : 375/375 tests PASS ; sélection ciblée 61/61 PASS ; compilation, image privée amd64 et manifeste PASS.
- Image candidate : `ghcr.io/brunofoxmulder/elise-investigator-v2-rc11-private:0.3.0-rc.11`.
- Validation terrain encore requise avant toute promotion hors canal Test. Dev.54 reste le fallback stable intact.

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
