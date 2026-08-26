# Dev.26 — revue d'architecture

## Faits

- Dev.25 a validé en terrain le contrat live de `ha_get_automation_traces` avec `readOnlyHint=true`.
- HA-MCP 8.3.0 expose un mode liste récent et un mode détail par `run_id`.
- Le détail peut devenir volumineux ; il doit être filtré et compacté.

## Options comparées

### A — charger toutes les traces de tous les candidats

Simple à coder mais trop coûteux, bruyant et difficile à maintenir. Rejeté.

### B — moteur adaptatif avancé dès maintenant

Plus puissant mais trop complexe pour un premier jalon et risqué vis-à-vis de la frontière causale. Rejeté.

### C — exploration bornée multi-étapes

Retenue : courte liste de candidats, courte liste de traces par candidat, un seul détail temporellement proche, aucune promotion en preuve causale.

## Décision

Dev.26 implémente l'option C.

## Invariants

- lecture seule stricte ;
- aucun LLM ;
- aucune commande Home Assistant ;
- aucune modification de `confirmed/probable/indeterminate` ;
- proximité temporelle explicitement non causale ;
- bornes fixes et testées ;
- sortie compacte sans snapshots de variables.
