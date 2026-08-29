# Dev.40 — contrat de facteurs causaux structurés

## But

Rendre Élise Investigator plus stable face aux évolutions d'automatisations Home Assistant.

Investigator doit rester responsable de la preuve causale. La couche de langage peut reformuler uniquement les causes déjà établies. Une métadonnée métier peut améliorer le vocabulaire, mais ne constitue jamais une preuve.

## Pipeline cible

`trace HA exécutée -> preuve interne -> facteurs structurés -> frontière publique minimale -> formulation langage`

La forme précise d'une automatisation (nom, entity_id, seuil, horaire, objet ciblé) ne doit pas devenir une dépendance du langage ni imposer un patch spécifique à cette automatisation.

## Contrat d'un facteur

Un facteur structuré contient au minimum :

- `kind` : nature générique du fait (`state`, `numeric_state`, `time`, `sun`, etc.) ;
- `role` : `cause`, `precondition` ou `guard` ;
- `proven` : preuve déterministe obtenue ou non.

Il peut aussi contenir des données descriptives stables :

- `label` ;
- `relation` ;
- `value` ;
- `threshold` ;
- `unit` ;
- `duration` ;
- `business_label` facultatif.

Les références techniques (`entity_id`, source automation/script, trace_run_id, trace_path, déclencheur brut, configuration brute) peuvent être conservées en interne mais ne traversent pas la frontière vers la couche de langage.

## Rôles

### cause

Facteur fonctionnel nécessaire à l'action et prouvé par le chemin réellement exécuté. Il peut être exposé à la couche de langage.

### precondition

Contexte nécessaire pour qu'une branche soit valide mais qui n'est pas, à lui seul, la raison fonctionnelle à annoncer. Il reste interne par défaut.

### guard

Contrainte de sécurité ou d'autorisation. Elle reste interne par défaut et ne doit jamais être promue automatiquement en cause utilisateur.

## Plusieurs causes

Une liste peut contenir plusieurs facteurs `role=cause` lorsque plusieurs faits sont réellement nécessaires et prouvés.

Exemple charge téléphone :

- heures creuses actives ;
- batterie sous le seuil ;
- commande de prise exécutée.

Les deux premiers facteurs peuvent être exposés comme causes. La commande reste la preuve de l'effet, pas une cause supplémentaire.

## Métadonnée métier

`business_label` est facultatif.

Exemple : une condition de luminosité prouvée peut recevoir `business_label="protection solaire non nécessaire"`.

Règles :

1. une métadonnée n'établit jamais la causalité ;
2. une métadonnée sur un facteur non prouvé n'est jamais exposée ;
3. sans métadonnée, le facteur générique reste exploitable ;
4. modifier une métadonnée ne doit pas nécessiter de modifier Investigator.

## Frontière LLM

La couche de langage reçoit uniquement les facteurs :

- `proven=true` ;
- `role=cause`.

Les préconditions, gardes et facteurs non prouvés sont volontairement masqués pour empêcher le LLM de décider lui-même ce qui constitue une cause.

## Compatibilité

Le champ `reason` historique reste valide pour les causes simples déjà supportées. Dev.40 ne demande aucune migration SQLite : `factors_json` existe déjà dans `CausalRecord`.

L'introduction des facteurs structurés doit être additive. Tant qu'aucun producteur ne renseigne ces nouveaux facteurs, le comportement dev.39/dev.38 reste inchangé.

## Hors périmètre de cette première étape

Cette étape définit le contrat et ses garde-fous. Elle ne modifie pas encore les extracteurs de traces pour produire automatiquement des causes combinées et ne change aucune automatisation Home Assistant.
