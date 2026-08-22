# État de la bêta 0.1.0-beta.1

## Inclus

- App Home Assistant OS (amd64/aarch64), installation depuis un dépôt d'Apps.
- Interface Ingress adaptée téléphone.
- API structurée `POST /api/v1/investigate`.
- OpenAPI + descripteur de tool IA.
- Résolution registre/unique_id.
- Historique, Logbook, contexte.
- Traces automation/script natives.
- Recherche inverse bornée et seulement en secours.
- Gestion des changements d'état, changements d'attribut, indisponibilité/retour.
- Causes multiples possibles, rétention de traces, déclaration utilisateur distincte.
- API directe protégée par jeton et port non exposé par défaut.
- Contrat strictement lecture seule.

## Vérifications réalisées hors Home Assistant

- Compilation Python : OK.
- YAML : OK.
- Tests unitaires de règles critiques : OK.
- Démarrage HTTP local : OK.
- Interface : OK.
- OpenAPI : OK.
- Contrôle statique d'absence de primitives HA mutatrices : OK.

## À valider sur le N100

- Construction du conteneur par Supervisor.
- Authentification via `SUPERVISOR_TOKEN`.
- Lecture réelle History / Logbook / entity registry.
- Lecture réelle `trace/list` / `trace/get` avec les droits de l'App.
- Exactitude sur notre corpus de cas Home Assistant réels.
- Comportement Ingress exact sur HAOS 2026.8.2.

Ces points nécessitent l'installation réelle de la bêta ; aucun changement Home Assistant n'a été effectué pendant la fabrication du paquet.
