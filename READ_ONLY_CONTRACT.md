# Contrat lecture seule – bêta 0.1

Le code de production n'expose volontairement aucune primitive générique d'écriture Home Assistant.

REST autorisé :
- états (GET uniquement) ;
- historique ;
- Logbook ;
- lecture des configurations automation/script/scene ;
- configuration générale.

WebSocket autorisé :
- registre d'entités (get/list) ;
- trace/list ;
- trace/get ;
- trace/contexts.

Sont absents du code : appels de services, set_state, fire_event, modification du registre, modification des automatisations/scripts/scènes, accès Docker/Supervisor étendu et montage du dossier Home Assistant `/config`.
