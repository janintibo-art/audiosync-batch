# AudioSync Batch V5 — Estimation audiovisuelle expérimentale

## Nouveautés

- Bouton **Estimer décalage image/son** pour l’épisode sélectionné : analyse jusqu’à 90 secondes en basse définition avec FFmpeg et NumPy.
- Corrélation des changements d’images avec les attaques sonores ; contrôle de cohérence entre les deux moitiés analysées.
- Si aucun pic cohérent : **Indéterminé**, sans suggestion de correction.
- Si un pic cohérent apparaît : **Piste expérimentale**, indiquée en millisecondes avec un score non probabiliste.
- Bouton **Copier la suggestion** pour tester un extrait ; **aucun enregistrement de saison ni conversion automatique**.
- Les préréglages et la correction par saison de la V4 sont conservés : **S01 +8700 ms** mesurés dans VLC, autres saisons à vérifier.
- Fichiers originaux conservés, sortie MKV, vidéo copiée sans réencodage, sous-titres préservés.

## Limites essentielles

**Ce n’est PAS une analyse des mouvements des lèvres.** Une piste sonore doublée, un générique musical ou un montage animé peuvent produire de faux indices. Le « score » n’est **pas** un pourcentage de fiabilité. Ne pas corriger une saison sans comparer un extrait test dans VLC avec décalage manuel remis à zéro.

Une piste « indéterminée » est normale pour de nombreux épisodes. L’analyse technique des horodatages de la V4 demeure distincte de l’estimation audiovisuelle. La V5 n’est pas une détection fiable d’une dérive progressive.

## Windows / GitHub Actions

Le workflow installe PyInstaller et NumPy, puis construit l’artefact `AudioSync-Batch-Windows-v5` avec `AudioSync-Batch.exe`.

**FFmpeg et FFprobe restent nécessaires sur le PC :** installer et ajouter au PATH, ou placer `ffmpeg.exe` et `ffprobe.exe` à côté de `AudioSync-Batch.exe`. Source officielle : https://ffmpeg.org/download.html

## Mise à jour depuis Termux

Le ZIP contient uniquement `audiosync_batch/app.py`, `audiosync_batch/README.md` et `audiosync_batch/.github/workflows/windows.yml`.

`bash ~/memo-depot/mise-a-jour.sh audiosync_batch "AudioSync Batch V5 - estimation image son"`

`gh run watch -R janintibo-art/audiosync-batch`
