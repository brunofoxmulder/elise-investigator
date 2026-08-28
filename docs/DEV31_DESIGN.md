# Élise Investigator dev.31 — porte stable pour Assist

Date : 2026-08-28

## Décision

Élise Why reste figée. Son endpoint historique `POST /api/v1/investigate` devient le contrat stable côté Investigator.

La route `POST /api/v1/investigate` :

- consulte uniquement le journal causal local ;
- retourne immédiatement un résultat compact `confirmed`, `probable` ou `indeterminate` ;
- ne lance jamais une enquête approfondie synchrone ;
- conserve `entity_id` dans toutes les réponses 200 pour rester compatible avec le validateur Élise Why ;
- n'expose ni nom d'automatisation, ni trace, ni détail d'implémentation ;
- reste strictement en lecture seule.

## Séparation des usages

- Assist / Élise Why : `POST /api/v1/investigate` — chemin rapide et stable.
- Compatibilité future : `POST /api/v1/why` — alias du même chemin rapide.
- IHM manuelle : `POST /api/v1/investigate/deep` — enquête déterministe approfondie avec preuves structurées.
- `POST /api/v1/ask` : résolution naturelle locale puis même politique journal-only.

## Pourquoi

La priorité est de ne pas ralentir les dialogues Assist et d'éviter les mises à jour fréquentes de l'intégration HACS Élise Why, qui peuvent nécessiter un redémarrage Home Assistant.

L'enregistreur causal effectue la capture et l'enrichissement en arrière-plan. Le coût de recherche doit être payé avant la question utilisateur, pas pendant le dialogue.

## Contrat de sécurité

Aucun service Home Assistant mutateur n'est ajouté. Aucun LLM n'entre dans le moteur causal. Investigator reste local, déterministe et lecture seule. Une absence de preuve retourne `indeterminate` sans recherche bloquante ni cause inventée.
