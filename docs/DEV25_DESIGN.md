# Dev.25 — probe du contrat live `ha_get_automation_traces`

Checkpoint d’architecture après validation terrain de dev.24.

## Objet

Valider sur le HA-MCP réellement connecté à Maison Cognitive le contrat MCP exposé pour `ha_get_automation_traces` avant de concevoir l’exploration multi-étapes par traces.

Dev.25 n’explore aucune trace. Il inspecte uniquement les métadonnées déjà renvoyées par `tools/list` lors du handshake MCP.

## Frontière de sécurité

- lecture seule stricte ;
- transport local in-process dev.23 conservé ;
- synthèse déterministe dev.24 conservée sans changement fonctionnel ;
- aucun LLM ;
- aucun appel `tools/call` vers `ha_get_automation_traces` ;
- aucun verdict causal MCP ;
- `causal_verdict = null` et `investigator_status_unchanged = true` restent inchangés ;
- aucune modification du Bridge, Alexa, Assist, Élise Why ou Home Assistant.

## Données exposées par le probe

Pour `ha_get_automation_traces`, l’interface affiche uniquement :

- `inputSchema` reçu du serveur MCP live ;
- `annotations` reçues du serveur MCP live.

Le probe ajoute explicitement :

- `contract_only = true` ;
- `tool_called = false` ;
- `trace_probe_mode = tools_list_metadata_only`.

Les descriptions longues et autres métadonnées non nécessaires ne sont pas exposées par ce jalon.

## Garde-fous automatiques

Le contrat n’est accepté que si :

1. `ha_get_automation_traces` reste dans l’allow-list locale Investigator ;
2. l’outil est effectivement présent dans le `tools/list` live ;
3. ses annotations déclarent `readOnlyHint = true`.

Sinon le probe signale l’écart et refuse de considérer le contrat comme validé.

## Tests de non-régression

La suite dev.25 vérifie notamment :

- extraction limitée au schéma et aux annotations ;
- refus d’un outil traces non déclaré lecture seule ;
- refus d’un outil absent ;
- `status()` ne déclenche aucun appel d’outil ;
- la recette de recherche héritée de dev.24 appelle toujours uniquement `ha_get_state`, `ha_get_history` et `ha_search` ;
- `ha_get_automation_traces` provoque un échec immédiat du test s’il est appelé par erreur ;
- le verdict causal reste inchangé.

## Distribution privée

La branche de travail est `dev25-mcp-trace-contract-probe`. La PR reste brouillon et est basée sur dev.24 afin que la revue ne montre que l’incrément dev.25. Le manifeste de test référence l’image privée `ghcr.io/brunofoxmulder/elise-investigator-dev25-private:0.2.0-dev.25`. Aucun merge vers `main` n’est prévu à ce stade.

## Critère terrain

Après CI et image privée validées, une installation manuelle ne sera proposée que sur Go explicite de Bruno.

Le test terrain attendu sera uniquement : ouvrir l’interface et déplier « Contrat live ha_get_automation_traces ». La preuve recherchée est le `inputSchema` réel et `annotations.readOnlyHint = true`, avec mention « outil traces appelé : non ».

Ce n’est qu’après cette preuve que l’architecture de l’exploration dev.26 pourra être figée : candidats courts → liste de traces → sélection temporelle → détail ciblé, sans laisser MCP devenir une autorité causale.
