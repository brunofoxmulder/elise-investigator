# RC13 — Conservation des preuves exactes

## Décision et périmètre

Le 16 septembre 2026, le choix de conserver les preuves dans Investigator a été
validé. La préparation de cette candidate est autorisée ; sa promotion vers le
canal Test et son installation Home Assistant restent à valider séparément.

Base exacte : RC12 `295c86c536a46fac82c8db46b70b4697bd6471b0`, PR #86.
RC12 est la version installée ; dev54-fallback-stable reste intacte.

## Défaut démontré

Sur une même ouverture solaire, la cause complète était retrouvée à +49 minutes,
puis perdue à +55 minutes. L'automatisation s'exécute toutes les dix minutes et HA
conserve ses cinq dernières traces. Le journal conserve le mouvement et sa source,
mais la trace qui expliquait ce mouvement sort de la liste. RC12 refait alors la
recherche et ne restitue plus la cause précédemment prouvée.

Les tests de cette PR utilisent des scénarios synthétiques/anonymisés, jamais des
exports bruts du domicile. Le défaut est reproduit par le vrai reader RC12.

## Comportement de la candidate

- Réutilisation du fichier SQLite et de sa connexion déjà détenus par Investigator.
  Nouvelle table isolée `exact_proofs_rc13` ; les anciennes tables restent intactes.
- Conservation de la cause structurée, de la commande exacte, de son instant
  d'exécution, de la référence de trace et des faits évalués par RC12, notamment
  les valeurs d'entrée du calcul solaire. Pas de copie intégrale des configurations.
- Le journal HA continue de sélectionner l'événement. La mémoire peut uniquement
  compléter la cause de cet événement exact, jamais choisir un événement plus ancien.
- Identité : entité, instant HA normalisé, effet, attribut, source et origine,
  instant/état du mouvement porteur et contextes HA disponibles. Les noms affichés
  et les valeurs actuelles des capteurs ne servent pas d'identité.
- Seules les réponses `ha_logbook+exact_trace` confirmées et accompagnées d'une
  preuve structurée sont admissibles. Le rattachement de la commande au mouvement
  exige également un instant d'action unique, antérieur au mouvement de 0 à 5 s,
  et des contextes compatibles lorsqu'ils sont disponibles. Ce garde-fou peut
  refuser la mémorisation d'un appareil plus lent ; il ne change pas sa réponse live.
- Une preuve fraîche reste prioritaire. Une réponse sans cause ne remplace jamais
  une preuve. Deux preuves contradictoires pour la même identité bloquent sa réutilisation.
- La provenance d'une relecture est `ha_logbook+retained_exact_trace` ; l'âge reste
  celui de l'événement HA, pas celui de la question ou de la sauvegarde.

## Collecte sans question préalable

Le flux d'événements existant est observé, sans ouvrir une nouvelle connexion.
Un changement d'état fonctionnel d'un objet pilotable programme une lecture
RC12 ciblée. Pour un volet, la collecte attend `open`/`closed` et ignore les mises
à jour de position pendant le mouvement. Les états techniques, les capteurs,
les attributs seuls et les contrôles d'automatisation sans mouvement sont ignorés.

La collecte lit le journal jusqu'à l'instant exact de l'événement, puis vérifie
l'identité du résultat. Une question ultérieure peut également sauvegarder une
preuve obtenue en direct.

Limites de charge : un consommateur, 128 événements maximum en attente,
déduplication exacte, quatre tentatives espacées de 1/3/10/30 s, délai maximal
de 10 s par tentative. Les attentes de publication du journal ne bloquent pas
les autres événements. Débordements, échecs et abandons sont comptabilisés.
Arrêt propre du consommateur avant fermeture de la base.

## Conservation et limites explicites

- La durée suit le réglage existant d'Investigator (code : 12 h par défaut,
  configurable de 1 à 72 h). Aucune valeur de réglage utilisateur n'est modifiée.
- Expiration calculée depuis l'événement, sans prolongation par les questions.
- Maximum : 2 048 preuves, 32 Kio par preuve ; aucune preuve n'est tronquée.
  Si le plafond est atteint, les plus anciennes sont retirées avant leur échéance.
- Contrôle d'intégrité SHA-256 du contenu mémorisé ; ce n'est pas une signature
  contre une modification malveillante de la base.
- La collecte ne peut pas récupérer une trace déjà disparue avant son démarrage,
  ni garantir la capture pendant un arrêt, une saturation ou un retard HA important.
- Le journal HA reste requis pour sélectionner l'événement à expliquer. Aucun
  résultat n'est inventé si le journal ou la preuve exacte manque.
- Une panne de l'archive n'empêche pas la réponse live ; elle est signalée par un
  compteur et un message technique sans détails de la preuve.

État de collecte : endpoint GET `/api/v1/proofs/status`, protégé par le même
chemin d'accès que les autres endpoints. Aucune primitive d'écriture HA ajoutée.

## Validation

Base : 413 tests PASS. Candidate : 471 tests PASS, compilation et vérification
du diff. Les 58 tests supplémentaires incluent la rotation des cinq traces,
le redémarrage de la base, la collecte avant toute question, le retard du journal,
la conservation des valeurs solaires, deux événements de même état final,
les contextes incompatibles, une trace ancienne de la même source, la rétention,
les conflits, la corruption, les limites de taille/file, les timeouts, une panne
disque et le cycle démarrage/arrêt. Des contrats RC11/RC12 existants sont rejoués
avec le reader RC13. Le resolver et le renderer RC12 sont réutilisés.

Recette terrain après autorisation : vérifier démarrage et état de collecte,
laisser un volet bouger naturellement sans l'interroger immédiatement, attendre
la rotation de ses traces, puis vérifier événement/cause/provenance. Refaire après
un redémarrage de l'App et avec un autre mouvement. Continuer les cas prises,
lampes et barrières temporelles déjà validés. Aucun mouvement forcé nécessaire.

## Livraison et retour arrière

La candidate conserve le Dockerfile générique éprouvé, inchangé, qui copie
`run.sh` vers `/run.sh`, applique `chmod 0755` et lance `CMD ["/run.sh"]`.
Seul le module Python lancé par `run.sh` et la version du manifeste source
avancent vers RC13 sur cette branche. Aucun Dockerfile ou launcher dédié n'est
ajouté, conformément à DEC-ELISE-017 et INC-ELISE-PACK-20260909.
Le workflow d'image est dédié à la branche candidate. Le manifeste installé
`elise_investigator_02_test`, main et la branche RC12 ne sont pas modifiés.
La PR reste brouillon et cible la branche RC12.

La préparation GitHub ne déploie rien dans HA. Avant promotion : CI verte, image
vérifiée, puis validation explicite. En cas de retour à RC12, la table additive
reste ignorée par l'ancien code et n'altère pas ses tables de mémoire.
