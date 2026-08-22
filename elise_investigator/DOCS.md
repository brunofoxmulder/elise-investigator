# Élise Investigator 0.1 bêta

Élise Investigator analyse les événements Home Assistant en **lecture seule**.

## Utilisation

Ouvrir l'interface de l'application puis saisir :

- `entity_id` obligatoire ;
- heure d'observation facultative ;
- valeur observée facultative ;
- attribut facultatif (ex. `temperature`) ;
- déclaration utilisateur facultative.

Le moteur cherche d'abord l'événement réel, puis Logbook/contexte, puis la trace exacte si une automation ou un script est identifié. La recherche inverse de configurations n'est utilisée qu'en secours.

## Niveaux de conclusion

- **confirmée** : preuve directe ou chaîne causale suffisamment établie ;
- **probable** : indices concordants mais un maillon manque ;
- **indéterminée** : preuves insuffisantes ou expirées.

## Sécurité

L'application n'a aucun accès au dossier `/config` de Home Assistant et n'implémente aucun appel vers `/api/services`, aucun événement sortant et aucune commande WebSocket mutatrice.

L'API directe sur le port 8099 est désactivée par défaut dans le mapping réseau. Si elle est exposée ultérieurement, elle exige `Authorization: Bearer <jeton>`. Le jeton est généré localement et affiché dans l'interface Ingress.

## Raccordement IA

Une IA ou une intégration peut appeler :

`POST /api/v1/investigate`

Corps minimal :

```json
{"entity_id":"light.exemple"}
```

Le résultat contient un `answer_text` directement exploitable par une IA, plus toutes les preuves structurées.

Le contrat machine est disponible à `/openapi.json`.

### Descripteur de tool IA

`GET /api/v1/ai-tool` renvoie un descripteur minimal (`name`, `description`, `input_schema`, endpoint) pour créer un outil de fonction côté IA sans réécrire le contrat à la main.
