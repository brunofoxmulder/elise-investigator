# Dev.34 — Mémoire consciente du LLM

## Intention

Dev.34 simplifie le chemin conversationnel d'Élise Investigator : il ne reconstruit plus la cause de chaque changement par une enquête profonde en arrière-plan. Investigator conserve une mémoire locale courte des changements utiles, puis répond directement à partir de cette mémoire.

La philosophie produit est : **mémoriser ce qui compte, retrouver vite, répondre simplement**.

## Contrat utilisateur

- Mémoire locale : **12 heures par défaut**, réglable de 1 à 72 heures.
- IHM Investigator conservée pour interroger la mémoire.
- Assist / Élise Why continue d'utiliser `POST /api/v1/investigate`.
- Le champ `status` est conservé uniquement pour compatibilité avec Élise Why dev.18 et vaut `confirmed` dans cette dev.
- Dev.34 ne calcule aucun niveau de certitude et n'utilise pas `probable` / `indeterminate` pour décider de la réponse.
- Si la cause n'est pas disponible, la réponse est exactement : **« Je n'ai pas trouvé la cause. »**
- Le journal diagnostic entrée/sortie permet de voir la demande reçue et la réponse produite. Il ne participe pas au raisonnement.

## Souvenir utile

Un souvenir conserve l'essentiel :

- objet ;
- avant → après ;
- cause fonctionnelle quand elle est disponible ;
- origine de la commande quand elle est disponible ;
- date/heure ;
- références techniques minimales nécessaires au diagnostic.

Le nom technique d'une automatisation reste une preuve interne. Une réponse normale à une action automatique privilégie la raison fonctionnelle. Une action directe privilégie l'origine de la commande.

## Chemin normal

Le chemin visé est événementiel et léger :

`automation_triggered -> call_service -> state_changed -> mémoire SQLite -> question -> réponse`

Seul un changement réel d'un objet utile crée un souvenir persistant. Une automatisation qui se déclenche ou s'évalue sans produire de changement d'objet ne remplit pas la mémoire.

Les événements `call_service` et `automation_triggered` servent de contexte causal éphémère et sont rapprochés de l'effet grâce aux contextes Home Assistant et à une fenêtre temporelle bornée. Le flux `state_changed` reste la base factuelle obligatoire.

## Charge et sûreté

- Pas de file d'enrichissement dans le chemin dev.34.
- Pas d'investigation profonde lancée pour chaque sous-changement.
- Pas de recherche Logbook/History/Trace dans le worker normal.
- SQLite reste local à l'App.
- Home Assistant reste strictement en lecture seule depuis Investigator.
- L'endpoint profond reste disponible séparément pour le diagnostic de développement, mais n'est utilisé ni par Assist ni par l'IHM normale dev.34.

## Limite volontaire de la dev

Home Assistant peut refuser à certains profils WebSocket l'abonnement à des événements internes tels que `call_service` ou `automation_triggered`. Dev.34 considère ces abonnements comme optionnels : la mémoire factuelle `state_changed` continue de fonctionner et la cause reste absente lorsqu'elle ne peut pas être reliée. Le terrain dira si le jeton Supervisor de l'App permet ces abonnements.

Un déclencheur générique de type `time_pattern` n'est pas présenté comme raison fonctionnelle. Dans ce cas, tant qu'une raison plus précise n'est pas mémorisée, Investigator répond « Je n'ai pas trouvé la cause. » plutôt que d'inventer une explication.

## Hors périmètre

- Aucun dashboard d'activité.
- Aucun score de confiance.
- Aucune distinction IHM / voix / Alexa sans preuve Home Assistant suffisante.
- Aucune modification de Home Assistant.
- Aucun changement d'Élise Why dev.18 dans cette dev.
