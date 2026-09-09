# Dev.69 — contrat de qualification terrain

Dev.69 est la candidate consolidée après la recette naturelle dev.67. Elle ne crée aucune nouvelle couche causale : elle réutilise la logique bornée dev.68 et fige les enseignements terrain comme non-régressions.

À corriger / retester en priorité :
- prise aspirateur OFF : ne pas retomber sur le trigger initial heures creuses lorsque l'action finale est libérée par une attente, un seuil ou un délai prouvé ;
- prise brosse à dents OFF : même famille action finale/différée ;
- chargeur téléphone 2 ON : conserver heures creuses + batterie basse lorsque les deux sont prouvées nécessaires ;
- volet salon ouverture : une condition fonctionnelle de branche prouvée doit battre le time pattern technique.

PASS dev.67 à préserver : Tineco OFF batterie >99,9 %, chargeur téléphone OFF batterie >99 %, entrée OFF sans mouvement, lampes simples/manuelles, volets coucher du soleil, chaîne lampe cuisine OFF ← ouverture volets ← conditions météo.

PARTIAL de présentation volontairement hors correctif causal : raw Activity `triggered by state...`, conditions de garde récitées avec la cause principale, traduction naturelle heures creuses. Ces points ne doivent pas être mélangés avec la correction causale.

Packaging obligatoire : contrat exact dev.62/dev.67 (`Dockerfile` générique, `/run.sh`, `CMD ["/run.sh"]`). Aucun launcher ou Dockerfile dédié dev69.

Dev.54 reste le fallback officiel.
