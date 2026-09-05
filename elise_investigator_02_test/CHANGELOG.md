# Changelog

## 0.2.0-dev.55 — candidate de refactoring natif HA, non déployée

- Base exacte : dev.54 validée, commit `8fc625217dbc0284496ad435a2ea8d9e7fee46b9`.
- Dev.54 est désormais le repli officiel via la branche figée `dev54-fallback-stable` ; aucun changement dev.55 ne doit être reporté sur cette branche.
- Architecture confirmée : le chemin normal privilégie les primitives natives Home Assistant déjà capturées par Investigator (`Context`, `automation_triggered`, `call_service`, Logbook), puis une trace ciblée uniquement pour approfondir la raison fonctionnelle ; le journal SQLite reste la mémoire persistante.
- La recherche inverse historique des automatisations/configurations ne fait pas partie du chemin conversationnel normal et reste réservée au diagnostic profond/fallback explicite.
- Nouveau filtre fonctionnel générique pour `light`, `switch`, `input_boolean`, `fan` et `humidifier` : `on/off → unavailable → unknown → même état` est traité comme une interruption de disponibilité, pas comme un nouveau changement fonctionnel.
- Si l’objet revient dans un état fonctionnel différent de celui qui précédait l’indisponibilité, le changement est conservé mais reste `indeterminate` : l’instant et la cause pendant l’interruption ne sont pas inventés.
- Une récupération après redémarrage de l’App sans état fonctionnel antérieur connu est ignorée comme événement causal : comportement fail-closed.
- Une perte de disponibilité casse explicitement un épisode brightness en cours afin d’éviter de propager une cause au-delà d’une discontinuité technique.
- Les épisodes covers `opening/closing → open/closed`, les épisodes brightness dev.46 et la reconnaissance HA Voice `assist_satellite.*` de dev.54 restent inchangés.
- Le statut runtime expose désormais la stratégie `native_ha_first_functional_memory`, les compteurs de transitions techniques filtrées et confirme `legacy_reverse_search_normal_path=false`.
- Nouveaux tests dev.55 : `ON → unavailable → unknown → ON`, équivalent OFF, retour dans un état différent, récupération sans ancrage, non-régression cover et contrat d’architecture.
- Aucun service Home Assistant mutateur ajouté. Aucun déploiement ou mise à jour Home Assistant effectué par cette branche.

## 0.2.0-dev.54 — référence terrain et version de repli

- Base reconstruite depuis la lignée stable dev.46, sans réintroduire les régressions dev.47–dev.53.
- Ajout unique : reconnaissance d’une commande directe Home Assistant Voice `assist_satellite.*` comme origine générique `user` lorsqu’une lignée de Context la prouve.
- Une automation ou un script déjà prouvé reste prioritaire et n’est jamais relabellisé `user`.
- Aucune proximité temporelle seule n’est utilisée comme preuve HA Voice.
- Logique lumière off↔on, épisodes brightness dev.46 et épisodes covers conservés.
- Suite de qualification dev.54 : 215/215 tests PASS, tests HA Voice PASS, commande utilisateur existante PASS, lumière off↔on PASS, volets PASS, lecture seule PASS.
- Image candidate : `ghcr.io/brunofoxmulder/elise-investigator-dev54-private:0.2.0-dev.54`.
- Branche historique : `dev54-assist-satellite-user-origin`.
- Branche de secours figée : `dev54-fallback-stable` au commit `8fc625217dbc0284496ad435a2ea8d9e7fee46b9`.
- Règle de rollback : tout incident significatif sur une dev supérieure doit permettre un retour exact à cette dev.54 avant nouvelle correction.

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
