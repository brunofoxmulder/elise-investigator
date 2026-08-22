# Élise Investigator – Home Assistant App

Dépôt de la bêta **Élise Investigator Core 0.1**.

Objectif : expliquer en lecture seule pourquoi une entité Home Assistant a changé d'état ou d'attribut, en privilégiant les preuves réelles : historique, Logbook, contextes et traces d'automatisations/scripts.

## Installation utilisateur

Une fois ce dépôt publié sur GitHub :

1. Home Assistant → Paramètres → Applications → Magasin des applications.
2. Ajouter l'URL du dépôt.
3. Installer **Élise Investigator**.
4. Démarrer l'application.
5. Ouvrir son interface Web.

La bêta ne monte pas `/config`, ne lit pas `secrets.yaml` et n'implémente aucun appel de service Home Assistant.

## API IA

L'API principale est `POST /api/v1/investigate`.
Le schéma OpenAPI est disponible sous `/openapi.json`.

L'accès via Ingress est authentifié par Home Assistant. Un accès direct au port réseau est protégé par un jeton généré localement dans `/data` et visible uniquement depuis l'interface Ingress.
