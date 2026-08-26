# Dev.26 — plan de test

## CI

- compilation Python ;
- suite historique ;
- tests spécifiques de bornage des traces ;
- vérification qu'aucune variable volumineuse n'est conservée dans la sortie compacte ;
- vérification du maintien de `causal_verdict=null`.

## Terrain — non autorisé par défaut

Le terrain ne commence qu'après CI + image vertes et Go explicite séparé.

Question de référence proposée : `Pourquoi le volet salon est fermé ?`

Attendus :

- bandeau exploration bornée lecture seule ;
- outil traces utilisé uniquement pendant la recherche ;
- 6 candidats maximum ;
- 1 détail maximum ;
- sélection temporelle explicitement non causale ;
- IA non ;
- verdict Investigator inchangé.
