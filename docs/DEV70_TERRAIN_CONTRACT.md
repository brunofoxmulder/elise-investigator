# dev.70 — contrat de qualification terrain

Candidate `0.2.0-dev.70` issue de la recette terrain dev.69.

## Corrections ciblées

- conserver le vrai fait terminal `open` / `closed` tout en écartant les rafraîchissements successifs du même état lorsqu'une frontière fonctionnelle est visible dans Activity ;
- récupérer l'attribution portée par `opening` / `closing` dans le même épisode natif ;
- lorsque la trace exacte ne donne que le trigger technique `time_pattern`, préférer les conditions runtime prouvées de la branche exécutée qui contient la commande cible ;
- conserver trigger + condition de branche quand les deux sont conjointement nécessaires, notamment heures creuses + batterie basse ;
- conserver les sélecteurs dev.68 pour wait/delay/action finale.

## Bornes

Pas de graphe causal, pas de corrélation temporelle générale, pas de recherche large, pas d'entité sans lien structurel explicite. Fail closed si la preuve de branche est ambiguë, non supportée ou absente.

## Non-régressions obligatoires

Tineco OFF batterie >99,9 %, chargeur téléphone 2 OFF batterie >99 %, entrée OFF sans mouvement, lampes simples/manuelles, fermetures coucher du soleil et chaîne profonde lampe cuisine OFF ← ouverture volet ← conditions météo.

## Hors périmètre

Normalisation française des chaînes HA brutes, hiérarchisation cause principale / conditions de garde et fonction « depuis quand ? ».

## Packaging

Packaging exact terrain dev.62/dev.67/dev.69 : Dockerfile générique + `/run.sh` + `chmod 0755` + `CMD ["/run.sh"]`. Aucun launcher ou Dockerfile dédié à dev.70.

Dev.54 reste le fallback officiel.
