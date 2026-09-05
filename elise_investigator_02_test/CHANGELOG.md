# Changelog

## 0.2.0-dev.56 — causalité native Logbook — préparation

- Base : dev.55 après validation de son filtrage fonctionnel `unknown` / `unavailable`.
- Objectif ciblé : exploiter en priorité la causalité native déjà fournie par Home Assistant dans le Logbook (`context_event_type`, `context_domain`, `context_service`, `context_name`, `context_message`, `context_source`, `context_entity_id`, `context_user_id`).
- Corriger le cas observé où Home Assistant confirme `origin_type=automation` et fournit la source causale native, mais Investigator conserve `reason=null` parce que la trace ne produit pas de raison sémantique.
- `context_source` / `context_message` doivent pouvoir fournir une cause native de premier niveau lorsque l'événement fonctionnel et l'automation sont prouvés, sans inventer de détail absent de Home Assistant.
- La trace reste disponible uniquement pour approfondir ce que le Logbook ne décrit pas : temporisation précise, `wait_for_trigger`, branche `choose/default`, condition réellement exécutée, variable runtime, cible calculée ou facteurs combinés.
- Le journal causal persistant reste un fallback lorsque la preuve native a disparu ; la corrélation/recherche inverse reste un dernier recours.
- Cas terrain de référence pour la recette : prise aspirateur, prise brosse à dents, chargeur téléphone 2, lampe entrée, volet salon et commande utilisateur directe.
- Aucun merge ni déploiement Home Assistant tant que la recette dev.56 n'est pas explicitement validée.

## 0.2.0-dev.55 — filtrage des interruptions techniques de disponibilité

- Base exacte : dev.54 validée, commit `8fc625217dbc0284496ad435a2ea8d9e7fee46b9`.
- Dev.54 est le repli officiel via la branche figée `dev54-fallback-stable` ; aucun changement dev.55 ne doit être reporté sur cette branche.
- Apport principal : sélection du dernier changement fonctionnel réel pour les domaines binaires contrôlables, afin que les pertes de disponibilité ne masquent plus l'événement causal utile.
- Nouveau filtre fonctionnel générique pour `light`, `switch`, `input_boolean`, `fan` et `humidifier` : `on/off → unavailable → unknown → même état` est traité comme une interruption de disponibilité, pas comme un nouveau changement fonctionnel.
- Si l'objet revient dans un état fonctionnel différent de celui qui précédait l'indisponibilité, le changement est conservé mais reste `indeterminate` : l'instant et la cause pendant l'interruption ne sont pas inventés.
- Une récupération après redémarrage de l'App sans état fonctionnel antérieur connu est ignorée comme événement causal : comportement fail-closed.
- Une perte de disponibilité casse explicitement un épisode brightness en cours afin d'éviter de propager une cause au-delà d'une discontinuité technique.
- Les épisodes covers `opening/closing → open/closed`, les épisodes brightness hérités et la reconnaissance HA Voice `assist_satellite.*` de dev.54 restent inchangés.
- Le statut runtime expose la stratégie `native_ha_first_functional_memory`, les compteurs de transitions techniques filtrées et confirme `legacy_reverse_search_normal_path=false`.
- Tests dev.55 : `ON → unavailable → unknown → ON`, équivalent OFF, retour dans un état différent, récupération sans ancrage, non-régression cover et contrat d'architecture.
- La promotion de `context_source/context_message` du Logbook comme cause native de premier niveau n'appartient pas au périmètre fonctionnel de dev.55 : ce travail est réservé à dev.56.
- Aucun service Home Assistant mutateur ajouté.

## 0.2.0-dev.54 — référence terrain et version de repli

- Ajout unique : reconnaissance d'une commande directe Home Assistant Voice `assist_satellite.*` comme origine générique `user` lorsqu'une lignée de Context la prouve.
- Une automation ou un script déjà prouvé reste prioritaire et n'est jamais relabellisé `user`.
- Aucune proximité temporelle seule n'est utilisée comme preuve HA Voice.
- Logique lumière off↔on, épisodes brightness et épisodes covers conservés.
- Suite de qualification dev.54 : 215/215 tests PASS, tests HA Voice PASS, commande utilisateur existante PASS, lumière off↔on PASS, volets PASS, lecture seule PASS.
- Image candidate : `ghcr.io/brunofoxmulder/elise-investigator-dev54-private:0.2.0-dev.54`.
- Branche historique : `dev54-assist-satellite-user-origin`.
- Branche de secours figée : `dev54-fallback-stable` au commit `8fc625217dbc0284496ad435a2ea8d9e7fee46b9`.
- Règle de rollback : tout incident significatif sur une dev supérieure doit permettre un retour exact à cette dev.54 avant nouvelle correction.

## Historique antérieur

Les entrées dev.15 et antérieures restent disponibles dans l'historique Git du changelog. Cette synthèse conserve ici les versions directement utiles à la lignée dev.54 → dev.55 → dev.56.
