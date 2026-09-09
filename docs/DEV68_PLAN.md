# dev.68 — cause locale de l’action, sans casser les PASS dev.67

## Terrain dev.67 validé

PASS à préserver impérativement :
- lampes automatiques simples et commandes manuelles ;
- fermetures volets au coucher du soleil ;
- Tineco OFF sur batterie > 99,9 % ;
- chargeur téléphone OFF sur batterie > 99 % ;
- lampe cuisine OFF avec remontée des trois conditions météo de l’ouverture des volets.

## Défauts ciblés

1. Une action finale peut encore reprendre le trigger initial de l’automatisation au lieu de la cause locale de l’action : aspirateur OFF, brosse à dents OFF, volet salon ouvert sur `time pattern`.
2. Une action peut perdre une condition conjointement nécessaire : chargeur téléphone 2 ON = heures creuses + batterie basse.
3. Les textes bruts `triggered by ...` sont un défaut de présentation distinct ; ils ne sont pas corrigés dans dev.68.
4. La fonction « depuis quand ? » reste un chantier séparé.

## Correction dev.68

Architecture inchangée : Activity HA -> attribution native -> trace exacte de cette exécution si nécessaire. Aucun graphe, aucune corrélation temporelle générale, aucune recherche causale large.

La trace exacte ajoute seulement trois formes bornées :
- `wait_for_trigger` terminé immédiatement avant l’action cible, même s’il n’existe qu’une seule commande sur la cible ;
- `delay` exécuté immédiatement avant l’action cible ;
- trigger de départ + conditions top-level toutes prouvées vraies, lorsqu’elles sont conjointement nécessaires à l’unique action cible.

Les sélecteurs dev.67 restent prioritaires et sont conservés. En cas d’ambiguïté, échec fermé : ne rien inventer.

## Packaging

Ne pas réutiliser les launchers dédiés dev.63-dev.66. dev.68 doit utiliser le packaging exact qui a démarré sur HAOS en dev.62/dev.67 : Dockerfile générique, `/run.sh`, `chmod 0755 /run.sh`, `CMD ["/run.sh"]`, shebang `#!/usr/bin/with-contenv bashio`.

Dev.54 reste le fallback officiel.
