# AudioSync Batch V3 — Diagnostic par lot

## Ajouts

- Bouton **Analyser toutes les vidéos** : inventaire des pistes et comparaison des horodatages de début.
- Comparaison des durées des pistes audio et vidéo, recherche de silence audio initial dans les 60 premières secondes via FFmpeg.
- Diagnostic affiché dans la liste pour chaque fichier, détail au clic, et export CSV avec les observations.
- Détection des pistes audio multiples ; aucune correction automatique sans preuve.
- Fonctions V2 préservées : sélection des pistes, test MKV de 15 secondes, retard/avance manuels, correction par lots sans réencodage.

## Limite essentielle

La différence entre les premiers horodatages audio/vidéo **ne prouve pas** la synchronisation des dialogues. Le silence non plus. Cette version **n'invente donc pas** un décalage automatiquement. Une analyse du mouvement des lèvres couplée à la voix nécessitera un module de synchronisation audiovisuelle spécifique avec tests de fiabilité, et peut échouer pour les animés, hors-champ, doublages ou scènes sans dialogue. Un décalage variable exige une approche différente.

## Installation et compilation

Fournir `ffmpeg.exe` et `ffprobe.exe` à côté de `AudioSync-Batch.exe` (ou dans PATH). Documentation : https://ffmpeg.org/download.html. GitHub Actions compile l'application Windows (Python 3.12 + PyInstaller) et publie l'artefact EXE. Aucune vidéo originale n'est modifiée.
