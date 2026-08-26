# Dev.24 — synthèse locale déterministe au-dessus de MCP

Checkpoint d’architecture avant implémentation.

## Options comparées

1. **Synthèse locale déterministe sur la recette MCP actuelle** : conserve l’autonomie sans cloud, reste simple et testable, transforme les données brutes en faits lisibles sans créer de verdict causal.
2. **Exploration locale multi-étapes avec traces** : plus riche causalement, mais ajoute immédiatement de la complexité de sélection/corrélation et un risque de surinterprétation.
3. **LLM + MCP** : meilleur potentiel d’exploration adaptative, mais doit rester optionnel et ne peut pas devenir la base de fonctionnement local.

## Décision pour le prochain incrément terrain

Commencer par l’option 1. Dev.24 doit :
- rester 100 % locale, sans LLM et strictement lecture seule ;
- convertir `ha_get_state`, `ha_get_history` et `ha_search` en une synthèse française lisible ;
- séparer explicitement **faits observés** et **pistes de configuration** ;
- ne jamais produire `confirmed`, `probable` ou `indeterminate` à la place du moteur causal Investigator ;
- déclarer `causal_verdict: null` et `investigator_status_unchanged: true` ;
- garder les résultats MCP bruts disponibles dans un volet de détail ;
- ne pas modifier le Bridge, Alexa, Assist ni les commandes.

Une exploration adaptative par traces ou LLM sera évaluée seulement après validation terrain de cette couche de synthèse.
