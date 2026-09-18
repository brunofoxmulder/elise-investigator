# RC14 — Origine native des commandes Assist

## Périmètre

Correctif ciblé du lecteur Logbook, basé sur RC13
`fbd7e1566c50cc91bafe103335e64f9c10f70cf9`.
La collecte, la mémoire des preuves, le resolver et le renderer RC13 sont réutilisés.

## Défaut et règle

Home Assistant peut attribuer directement le changement d'état d'un appareil à
un `context_entity_id` du domaine `assist_satellite`, avec
`context_state: listening`. RC13 ignorait cette attribution lorsque
`context_user_id` était absent : `origin_type: unknown`, `cause_found: false`.

RC14 accepte cette preuve native comme une origine **utilisateur générique**.
La réponse existante « commande utilisateur Home Assistant » est conservée.
Ce résultat identifie l'origine de la commande, pas la personne qui parle.

La priorité reste : automation, script, contexte utilisateur authentifié,
puis attribution native à un satellite en écoute. Une source absente, un nom
ressemblant à un satellite, une phase `processing`/`responding` isolée ou un
événement vocal seulement proche dans le temps ne constituent pas cette preuve.
Le fait expliqué, son instant et son état restent sélectionnés par le journal HA.
Le correctif est indépendant de l'entité et du fournisseur vocal.

Il ne reconstruit pas le contexte perdu par une intégration. Si HA n'a pas
conservé l'attribution native, l'origine peut rester inconnue.

## Vérification

Le défaut a été reproduit avec le vrai lecteur RC13 sur des fixtures anonymisées.
Les neuf nouveaux tests de causalité couvrent ON/OFF, différents domaines,
priorité automation/script, utilisateur authentifié, preuves insuffisantes,
absence de corrélation temporelle et conservation des données brutes.
Trois tests de packaging vérifient la version et le cycle de collecte partagé.
La suite complète attendue compte **483 tests** ; la CI doit être verte avant
promotion du canal Test.

Le workflow construit l'image amd64 avec le Dockerfile générique inchangé,
inspecte son manifeste, puis importe le code depuis l'image publiée par digest
pour vérifier version, lanceur et règle vocale. Ces contrôles ne remplacent pas
la recette sur Home Assistant OS.

## Livraison et recette

- Candidate : `candidate-v2-rc14-native-assist-origin`, version `0.3.0-rc.14`.
- Image : `ghcr.io/brunofoxmulder/elise-investigator-v2-rc14-private:0.3.0-rc.14`.
- Lanceur générique `run.sh` vers `main_v2_rc14.py`, sans Dockerfile spécifique.
- Promotion séparée du seul manifeste `elise_investigator_02_test/config.yaml`
  sur `main`, après les contrôles image. Aucune fusion de la branche candidate.
- Installation manuelle sur le canal Test, puis contrôle du démarrage, de la
  version et de la collecte. Refaire une commande vocale autorisée ON/OFF et
  interroger le dernier changement exact : origine `user` attendue seulement
  si son entrée Logbook porte la preuve native décrite ci-dessus.
- Continuer les observations naturelles automation/script et conservation des
  preuves, sans déclenchement artificiel ni modification des automatismes.
- RC13 et son image restent disponibles pour revenir au manifeste précédent ;
  le fallback dev54 est conservé. Pas de migration du schéma SQLite en RC14.

Ce document ne contient que des données génériques. La validation terrain doit
être consignée séparément après installation ; elle n'est pas présumée acquise.
