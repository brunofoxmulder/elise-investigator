# Changelog

## 0.2.0-dev.31

- **Élise Why reste inchangée** : elle conserve sa porte historique `POST /api/v1/investigate`. Aucun changement HACS ni redémarrage Home Assistant n'est requis pour ce jalon.
- `POST /api/v1/investigate` devient la **porte stable et rapide d'Assist** : elle consulte uniquement le journal causal local déjà enrichi.
- Si le journal ne contient pas de preuve correspondante, Investigator renvoie immédiatement **`indeterminate`** ; aucune enquête approfondie synchrone n'est lancée dans le dialogue Assist.
- L'objectif est de ne pas ajouter de latence perceptible : le travail causal coûteux est effectué en arrière-plan par l'enregistreur/enrichisseur avant la question utilisateur.
- L'enquête approfondie déterministe reste disponible séparément pour l'IHM manuelle via `POST /api/v1/investigate/deep`.
- `POST /api/v1/why` est conservé comme alias de compatibilité du chemin rapide, mais Élise Why dev.18 n'en dépend pas.
- La projection conversationnelle reste minimale et n'expose ni nom d'automatisation, ni trace, ni détail d'implémentation ; pour une action automatisée, seule la raison fonctionnelle prouvée est présentée.
- L'IHM indique explicitement **Assist : journal causal uniquement · enquête approfondie : manuelle** ; l'ancien réglage de fallback est conservé comme réglage hérité sans effet sur Assist en dev.31.
- La sélection du dernier vrai changement d'état introduite en dev.30 est conservée pour les investigations profondes manuelles et l'enrichissement causal.
- Invariants inchangés : moteur local, déterministe, strictement **lecture seule**, aucun LLM dans Investigator, aucun service Home Assistant mutateur.
- Candidate exacte : commit `126158992cd67d1cac813ac173bb3d930d4e8beb`, image privée `0.2.0-dev.31`, digest `sha256:f923c1a66f31fc2d7544a82be7ca34e2b8cfb3b467934a5ff467b00ac3498279`.

## 0.2.0-dev.30

- Corrige l’aiguillage découvert en recette dev.29 : **Assist / Élise Why ne passent plus directement par la grosse recherche historique**. Un nouvel endpoint structuré `POST /api/v1/why` consulte d’abord le journal causal.
- Si aucun événement correspondant n’est présent dans le journal, l’**enquête approfondie de secours** n’est lancée que si l’option correspondante est activée dans l’IHM.
- Corrige la sélection des événements récents : un vrai changement tel que **`off → on`** ou **`on → off`** est désormais prioritaire sur les mises à jour techniques ultérieures **`on → on`** ou **`off → off`** provoquées par des changements d’attributs.
- La **recherche manuelle** reste une enquête approfondie séparée et conserve les preuves structurées complètes ; sa réponse visible utilise désormais la raison fonctionnelle lorsqu’elle est prouvée, sans présenter le nom de l’automatisation comme cause principale.
- Le badge de verdict de la recherche manuelle est francisé : **Cause confirmée / probable / indéterminée**.
- La réponse destinée au LLM reste volontairement minimale : verdict, entité, événement/heure utiles, valeur éventuelle, raison fonctionnelle ou source directe prouvée. Les noms d’automatisations, traces et variables techniques restent internes à Investigator.
- Cette version était prévue pour fonctionner avec **Élise Why 0.2.0-dev.19** via `/api/v1/why` ; cette orientation a ensuite été abandonnée au profit de la porte stable `/api/v1/investigate` en dev.31, afin de figer Élise Why.
- Aucun service mutateur ni droit Home Assistant supplémentaire n’est ajouté ; Investigator reste strictement **lecture seule**.
- Image privée `0.2.0-dev.30` construite et vérifiée avant promotion de l’app de test.

## 0.2.0-dev.29

- Ajout d’un **journal causal persistant local** sous SQLite : les changements significatifs d’entités Home Assistant sont enregistrés avant enrichissement causal, puis conservés pendant une durée glissante réglable.
- La durée de conservation est réglable directement dans l’IHM de **1 à 72 heures**, avec **12 heures par défaut**.
- Une case **« Enquête approfondie de secours »** permet d’activer ou désactiver l’ancien moteur d’enquête lorsque le journal causal ne contient pas d’événement correspondant.
- Pour les réponses conversationnelles, Investigator consulte désormais **le journal causal en priorité** avant de lancer une enquête profonde.
- Lorsqu’une action provient d’une automatisation, la réponse destinée à l’utilisateur privilégie la **raison fonctionnelle prouvée** ; le nom de l’automatisation et la trace restent des preuves internes.
- Lorsqu’une action est directe, la réponse peut indiquer **utilisateur** ; **Alexa** n’est mentionnée que si cette provenance est réellement prouvée.
- Le dernier déclencheur réellement exécuté est prioritaire lorsqu’il explique l’action. Un déclencheur générique comme `time_pattern` n’est pas présenté comme cause fonctionnelle ; les facteurs décisifs prouvés dans la même trace peuvent être utilisés à la place.
- Ajout de l’extraction conservatrice des facteurs runtime d’une valeur calculée, afin de pouvoir expliquer par exemple qu’une position de volet résulte de la **position du soleil et de la luminosité** lorsque la trace le prouve.
- Sortie vers le LLM volontairement minimale : entité, événement, heure, valeur éventuelle, raison ou source directe. Les traces complètes et variables techniques restent dans Investigator.
- Nouvelle carte IHM **« Journal causal · dev.29 »** : état du journal, nombre d’événements conservés, file d’enrichissement, causes enrichies, erreurs éventuelles, priorité du journal et rappel **Home Assistant : lecture seule**.
- L’IHM de **recherche manuelle** et la **Recherche MCP locale** sont conservées et restent séparées du journal causal.
- L’écoute `state_changed` utilise une connexion WebSocket dédiée et strictement en lecture seule. Aucun service Home Assistant mutateur n’est ajouté.
- Image privée `0.2.0-dev.29` construite et vérifiée avant promotion de l’app de test.

## 0.2.0-dev.16 → dev.28 — synthèse des jalons intermédiaires

- **dev.16** : consolidation de la résolution naturelle française et traitement plus cohérent des épisodes de mouvement des volets, sans modifier la politique de preuve.
- **dev.17 → dev.23** : construction et validation progressive du raccordement local en lecture seule entre Investigator et HA-MCP ; aucun LLM ajouté au moteur causal et aucun verdict Investigator renforcé par MCP.
- **dev.24** : synthèse MCP locale déterministe des états, historiques et pistes de configuration, avec `IA : non` et verdict causal Investigator inchangé.
- **dev.25** : validation du contrat live de `ha_get_automation_traces` à partir des métadonnées `tools/list`, sans appel de trace dans ce jalon.
- **dev.26** : exploration MCP bornée des traces candidates, limitée en nombre de candidats, d’exécutions et de détails, sans transformer la proximité temporelle en preuve causale.
- **dev.27** : ajout du bouton **Texte** pour copier localement un résumé lisible du diagnostic MCP, sans envoi automatique ni secret.
- **dev.28** : la carte **Recherche MCP locale** reçoit son propre sélecteur d’objet Home Assistant et devient indépendante du formulaire d’investigation manuelle.
- Sur toute cette séquence, les invariants restent inchangés : lecture seule Home Assistant, aucun service mutateur, aucun LLM dans le moteur causal, refus de deviner en cas d’ambiguïté.

## 0.2.0-dev.15

- Version volontairement limitée au diagnostic et à l’observabilité : aucun changement du moteur causal ni de la logique de résolution.
- Ajout d’un journal local persistant sous `/data/audit`, conservé 10 jours, plafonné en taille et nettoyé des secrets connus.
- Chaque demande reçoit un `request_id` et des étapes de suivi `received`, `resolved`, `event_selected`, `completed` ou `error`.
- Traçage du texte exact reçu, de la normalisation, des candidats et scores du résolveur, des filtres appliqués, de la requête réellement transmise au moteur, des événements History considérés et de l’événement finalement sélectionné.
- Traçage de la réponse exacte, de sa longueur, du statut HTTP et des durées par étape afin d’identifier les troncatures, erreurs de résolution et timeouts.
- Provenance factuelle des appels : `ingress_ui`, `api_ask`, `api_investigate` ou `unknown`, sans déduire abusivement qu’un appel API est forcément vocal.
- Nouvelle vue Ingress « Dernières demandes » avec filtres, détail d’une requête et exports JSONL/TXT pour diagnostic externe.
- Cas de tests ajoutés pour la résolution « lampe salle de bain » et pour la sélection d’un événement `closed` face à une ancienne ouverture.
- Régression générale, certification permanente, contrat de sécurité/lecture seule et smoke test conteneur validés.
- Image privée `0.2.0-dev.15` construite, publiée et vérifiée ; accès anonyme refusé.
- Lecture seule Home Assistant, Ingress, AppArmor et port externe 8099 inchangés.

## 0.2.0-dev.14

- Désambiguïsation conversationnelle par domaine Home Assistant, sans LLM ni alias Maison Cognitive.
- Les entités techniques `update.*` ne concurrencent plus les objets domestiques lors d'une recherche par nom naturel ; elles restent accessibles si leur `entity_id` est donné explicitement.
- Les mots génériques d'objet servent de filtre de domaine lorsque cela lève une ambiguïté : lampe/lumière/éclairage → `light`, volet/store/rideau → `cover`, prise/interrupteur → `switch`, clim/climatisation → `climate`.
- Cas terrain corrigés : « prise de l'aspirateur » sélectionne `switch.prise_aspirateur` plutôt que l'entité `update.*` homonyme ; même règle pour la brosse à dents.
- Si `climate.salon` et `light.salon` portent tous deux le nom « Salon », « lampe du salon » sélectionne `light.salon` et « clim du salon » sélectionne `climate.salon` ; « salon » seul reste volontairement ambigu.
- Les doublons réels à l'intérieur d'un même domaine restent en erreur d'ambiguïté : Investigator ne devine pas.
- Régression générale, certification permanente, contrat de sécurité/lecture seule et smoke test conteneur validés.
- Image privée `0.2.0-dev.14` construite, publiée et vérifiée ; accès anonyme refusé.
- Aucun changement du moteur causal, des niveaux `confirmed/probable/indeterminate`, des droits Home Assistant, d'Ingress, d'AppArmor ni du port externe 8099.

## 0.2.0-dev.13

- Résolution conversationnelle française rendue plus naturelle sans LLM ni alias Maison Cognitive.
- Les mots grammaticaux (`le`, `la`, `de`, `du`, `des`, etc.) sont neutralisés pour comparer la question au `friendly_name` Home Assistant tout en conservant l’ordre des mots.
- Exemples couverts : « volet du salon » → « Volet salon », « lampe du salon » → « Lampe salon », « prise de la télé » → « Prise télé », « chargeur du téléphone » → « Chargeur téléphone ».
- Si l’objet Home Assistant est simplement « Frigo », « prise du frigo » peut résoudre « Frigo » lorsqu’aucun objet plus spécifique et non ambigu ne correspond.
- Les noms plus spécifiques sont prioritaires ; les vrais doublons restent en erreur d’ambiguïté au lieu d’être devinés.
- Régression générale, certification permanente, contrat de sécurité/lecture seule et smoke test conteneur validés.
- Image privée `0.2.0-dev.13` construite, publiée et vérifiée ; accès anonyme refusé.
- Aucun changement du moteur causal, des niveaux `confirmed/probable/indeterminate`, des droits Home Assistant, d’Ingress, d’AppArmor ni du port externe 8099.

## 0.2.0-dev.12

- La cause humaine peut désormais provenir d'une décision locale `choose/default` prouvée par la trace, au lieu de reprendre systématiquement le déclencheur initial de l'automatisation.
- Cas aspirateur : après 2 minutes, si la condition de puissance `> 1 W` est fausse et que la valeur observée est `0 W`, la coupure est expliquée par cette décision locale ; le passage en heures creuses reste le déclencheur initial, pas la cause humaine de l'extinction deux minutes plus tard.
- Le moteur reste conservateur : une décision locale ne supplante le trigger initial que si la branche exécutée, sa condition et l'action correspondant à l'effet sont reliées sans ambiguïté par la trace d'exécution.
- Correction générique des libellés sans accent : `Fenetre` est reconnu comme fenêtre même lorsque Home Assistant expose un `device_class: door` plus générique.
- Priorité causale conservée : `wait_for_trigger` directement lié à l'effet, puis décision locale `choose/default`, puis déclencheur initial prouvé.
- Les formulations ne prétendent pas distinguer ce que la preuve ne distingue pas : une puissance quasi nulle peut correspondre à une batterie chargée ou à un appareil non branché.
- Ajout de `CERT-014` et `CERT-015` ; banc permanent porté à 15 cas.
- Régression générale, certification, contrat de sécurité/lecture seule et smoke test conteneur validés.
- Image privée `0.2.0-dev.12` construite, publiée et vérifiée ; accès anonyme refusé.
- Lecture seule, Ingress, AppArmor et port externe 8099 inchangés.

## 0.2.0-dev.11

- Refactorisation interne sans changement fonctionnel attendu.
- Mutualisation des utilitaires causaux utilisés par l'analyse des traces et la restitution humaine afin d'éviter plusieurs implémentations divergentes.
- Réutilisation d'un seul index en mémoire des états Home Assistant pendant une enquête pour enrichir les conditions et la cause humaine.
- Les 13 cas du banc permanent de certification restent inchangés et validés.
- Régression générale, certification permanente, contrat de sécurité/lecture seule et smoke test conteneur validés.
- Image privée `0.2.0-dev.11` construite et vérifiée ; accès anonyme toujours refusé.
- Aucun changement des règles de certitude, de la fenêtre adaptative, de l'interface fonctionnelle, d'Ingress, d'AppArmor ou des droits Home Assistant.

## 0.2.0-dev.10

- La cause humaine est désormais dérivée du déclencheur Home Assistant prouvé au lieu d'afficher seulement le nom de l'automatisation.
- Prise en charge générique des déclencheurs solaires avec décalage : coucher/lever du soleil, avant ou après l'événement.
- Cas attendu : « Le volet salon s'est fermé parce que le soleil s'est couché il y a 45 minutes. »
- Prise en charge générique des déclencheurs `device` d'ouverture/fermeture : la cause humaine vient du changement réellement observé sur le contact.
- Cas attendu : « Le volet salon s'est ouvert parce que la fenêtre a été ouverte. »
- Les conditions de permission/sécurité restent du contexte et ne deviennent pas artificiellement la cause.
- La priorité action-locale de `wait_for_trigger` est conservée pour éviter toute régression des cas mouvement/absence de mouvement.
- Nouveaux cas permanents `CERT-012` et `CERT-013` ; banc permanent porté à 13 cas.
- Bouton `Log`, lecture seule, Ingress, AppArmor et port externe 8099 inchangés.

## 0.2.0-dev.9

- Correction du cas réel où une même exécution contient plusieurs commandes sur le même objet : la commande retenue doit correspondre de manière unique à l'effet observé.
- Exemple certifié : pour une lampe `on → off`, `light.turn_off` est sélectionnée plutôt que le `light.turn_on` exécuté plus tôt dans la même automatisation.
- Une fois la commande sélectionnée, Investigator remonte au `wait_for_trigger` terminé immédiatement avant cette commande pour produire la cause humaine.
- Cas salle de bain attendu en Simple : « Lampe salle de bain s'est éteinte parce qu'il n'y avait plus de mouvement. »
- Le format Home Assistant réel de durée `total_seconds: 300` est rapproché de la règle configurée `00:05:00`, ce qui conserve « 5 minutes » en mode Détaillé.
- Nouveau cas permanent `CERT-011` pour empêcher cette régression.
- Bouton `Log`, lecture seule, Ingress, AppArmor et port externe 8099 inchangés.

## 0.2.0-dev.8

- Correction du rapprochement temporel des traces longues : une exécution est maintenant rapprochée de l'effet observé sur son intervalle réel `start → finish`, et non uniquement sur son heure de départ.
- Le garde-fou reste conservateur : si l'heure de fin n'est pas disponible, le comportement antérieur basé sur le début de trace est conservé.
- Cas de non-régression ajouté à partir du test terrain salle de bain : automatisation démarrée environ 9 minutes avant l'extinction mais terminée au moment de l'effet.
- Ajout d'un bouton `Log` dans l'interface : il copie le diagnostic technique nettoyé pour analyse, sans envoi automatique et avec retrait des secrets connus.
- Lecture seule, Ingress, AppArmor et port externe 8099 inchangés.

## 0.2.0-dev.7

- Cause humaine désormais liée à l'action observée lorsque la trace le prouve, au lieu de reprendre systématiquement le déclencheur initial de l'automatisation.
- Premier cas certifié : extinction après fin d'un `wait_for_trigger` d'absence de mouvement.
- Mode Simple : cause humaine courte.
- Mode Détaillé : cause + règle utile + automatisation/script confirmé.
- Moteur toujours strictement en lecture seule ; aucune modification des droits HAOS.

## 0.2.0-dev.6

- Première candidate de test HAOS distribuée depuis une image GHCR privée.
- Code source 0.2 absent du manifeste public.
- Slug séparé de beta.16 pour permettre un essai côte à côte.
- Démarrage manuel, Ingress activé, port externe 8099 désactivé, AppArmor activé.
