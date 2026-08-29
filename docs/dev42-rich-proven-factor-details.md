# Dev.42 — détails structurés des facteurs déjà prouvés

## Objectif

Enrichir le premier facteur causal dev.41 avec des données déjà présentes dans la preuve sélectionnée, sans relire ni réinterpréter la trace Home Assistant et sans modifier `reason`.

## Contrat

À partir d'un `human_cause` déjà `proven=true`, dev.42 peut recopier dans `factors` :

- `relation` ;
- `value` ;
- `threshold` ;
- `unit` ;
- `duration`.

Le rôle reste `cause` uniquement parce que le moteur déterministe amont a déjà sélectionné cette cause. Dev.42 ne classe aucune nouvelle condition comme cause.

## Exemples

Une condition numérique prouvée fausse `actual=12451`, `above=45000` devient :

- `relation=not_above` ;
- `value=12451` ;
- `threshold=45000` ;
- unité éventuelle `lx`.

Un trigger d'état prouvé `off -> on` peut devenir `relation=changed_to`, `value=on`.

## Garde-fous

- cause non prouvée : rejetée ;
- condition numérique à deux bornes : la borne n'est choisie que si la valeur runtime permet de la déterminer sans ambiguïté ;
- les détails techniques complets restent privés dans la preuve interne ;
- `reason` n'est pas modifiée ;
- les `factors` déjà présents ne sont pas écrasés ;
- aucune modification Home Assistant ni automatisation.

Cette étape prépare les causes combinées futures, sans les implémenter encore.
