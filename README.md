# AudioSync Batch V4 — Correction audio par saison

## Principales améliorations

- Détection des saisons dans les noms d'épisodes de type `S01E01` et `Season 2` / `Saison 2`.
- Préréglage **S01 : retard audio +8700 ms**, issu du test manuel réalisé dans VLC. Il s'agit d'une mesure de l'utilisateur, **pas** d'un résultat de l'analyse automatique.
- Les autres saisons n'ont **aucun réglage automatique** : les mesurer puis cliquer sur « Enregistrer le réglage pour cette saison ».
- Bouton « Corriger la saison sélectionnée » : ne traite pas les autres saisons par erreur.
- Export MKV vers un **sous-dossier par saison**, préservation des originaux, des sous-titres et des pistes sélectionnées. Copie des flux (`-c copy`), sans réencodage.
- Extrait test de 30 s pour inspection avant conversion du lot.
- Diagnostic des horodatages et analyse des premiers silences déjà présents en V3.

## Important pour le test

Avec +8700 ms, le début du fichier corrigé peut être silencieux environ 8,7 s : la piste audio est volontairement retardée sur la chronologie. Évaluer la synchronisation **sur un dialogue après ce délai** et lors des sauts de lecture. Le lecteur VLC doit avoir son réglage manuel remis à **0,000 s** lors du contrôle du fichier corrigé.

Un blanc après déplacement dans VLC n'est pas à lui seul une preuve de fichier corrompu. La V4 ne fournit pas de mesure automatique de synchronisation labiale; les horodatages et silences ne permettent pas de la calculer avec certitude. Un décalage variable ne pourra pas être corrigé avec une seule valeur constante.

## Windows

L'action GitHub produit `AudioSync-Batch-Windows-v4` contenant `AudioSync-Batch.exe`.
Installer FFmpeg et FFprobe ou placer `ffmpeg.exe` et `ffprobe.exe` dans le dossier de l'EXE. Télécharger depuis https://ffmpeg.org/download.html.

## Termux

Depuis le dépôt local existant `~/audiosync_batch`, utiliser le ZIP de mise à jour puis :

`bash ~/memo-depot/mise-a-jour.sh audiosync_batch "AudioSync Batch V4 - correction par saison"`

`gh run watch -R janintibo-art/audiosync-batch`

Le ZIP de mise à jour ne contient que les fichiers modifiés et conserve le dossier racine `audiosync_batch/`.
