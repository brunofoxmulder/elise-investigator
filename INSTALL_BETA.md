# Installation bêta – objectif « le plus simple possible »

Le paquet est structuré comme un **dépôt d'Apps Home Assistant**.

## Méthode retenue pour le test réel

Publier ce dossier racine dans un dépôt Git accessible par Home Assistant, puis :

1. Home Assistant → Paramètres → Applications → Magasin des applications.
2. Menu des dépôts → coller l'URL du dépôt.
3. Ouvrir **Élise Investigator**.
4. Installer.
5. Démarrer.
6. Activer « Afficher dans la barre latérale » si Home Assistant ne le fait pas automatiquement.
7. Ouvrir l'interface et saisir un `entity_id`.

Aucune autre configuration n'est requise pour le premier test.

Le port 8099 reste **non exposé par défaut**. L'interface Ingress fonctionne sans l'ouvrir. On ne l'activera que lors du raccordement d'une IA externe au réseau local.
