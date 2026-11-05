# Conservation de l’image de référence RC14

Décision de Bruno le 5 novembre 2026 : conserver une image RC14 pour préparer un retour arrière.

- Image source : `ghcr.io/brunofoxmulder/elise-investigator-v2-rc14-private:0.3.0-rc.14`.
- Copie distincte, publique : `ghcr.io/brunofoxmulder/elise-investigator-rc14-retour-20261105:0.3.0-rc.14`.
- Empreinte OCI des deux images : `sha256:5b5b937d7884a80cef0944ad0d3ba564c60e4d940d1a81d1d6c81e430b051fdd`.
- Vérification GitHub Actions 41944925435 : copie de l’index et des manifests, empreinte identique, téléchargement par empreinte et contrôle de la version interne `0.3.0-rc.14` réussis.
- Les deux copies sont hébergées sur le même compte GitHub : elles ne constituent pas deux sauvegardes indépendantes de ce service.
- Il s’agit de la référence publiée ; l’empreinte de l’image réellement installée dans Home Assistant n’a pas été observée.
- La restauration de l’application et de ses données n’a pas été testée. Une sauvegarde récente et l’accord explicite de Bruno restent nécessaires avant toute intervention dans Home Assistant.
