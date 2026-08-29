# Dev.43 — causes combinées par conjonction trigger/condition

## But

Supporter une vraie cause combinée sans promouvoir automatiquement toutes les conditions vraies d'une automatisation.

Le cas de référence est l'automatisation **charge S23 sur chargeur téléphone heure creuse** du référentiel Maison Cognitive :

- trigger `binary_sensor.rte_tempo_heures_creuses -> on` ;
- trigger batterie `< 95 %` ;
- trigger batterie `> 99 %` ;
- condition globale heures creuses = `on` ;
- branche `choose` batterie `< 95 %` -> `switch.turn_on` ;
- branche `choose` batterie `> 99 %` -> `switch.turn_off`.

Pour l'allumage du chargeur, les deux faits fonctionnels nécessaires sont donc :

1. heures creuses actives ;
2. batterie sous 95 %.

## Règle conservatrice

Dev.43 ne transforme pas une condition vraie en cause simplement parce qu'elle est vraie.

Une condition peut entrer dans un ensemble de causes combinées seulement si :

1. elle est de type `state` ou `numeric_state` supporté ;
2. le même prédicat existe aussi parmi les triggers configurés de l'automatisation ;
3. sa trace runtime prouve qu'elle est vraie ;
4. pour une condition dans `choose`, la séquence de cette branche référence la cible de l'effet ;
5. au moins deux prédicats distincts satisfont toutes ces règles.

Cette règle vise le pattern HA courant où plusieurs triggers alternatifs servent à réévaluer une même conjonction métier. Elle exclut par défaut les simples gardes telles que « fenêtre fermée » ou « présence autorisée » lorsqu'elles ne sont pas également des triggers.

## Compatibilité

- `reason` reste inchangée ;
- dev.41/dev.42 restent le fallback à une seule cause ;
- les facteurs préexistants ne sont jamais remplacés ;
- les structures imbriquées ou ambiguës non supportées échouent sans inventer de cause ;
- aucune modification Home Assistant ni automatisation n'est nécessaire.

## Portée

Cette dev ajoute un premier pattern générique de causes combinées. Elle ne prétend pas interpréter toutes les structures possibles de Home Assistant. L'objectif est de faire évoluer Investigator par structures génériques réutilisables, pas par automatisation ou objet particulier.
