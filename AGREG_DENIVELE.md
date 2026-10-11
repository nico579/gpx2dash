# Calcul du dénivelé d'gpx2dash.py

`gpx2dash.py` utilise les modules de calcul de gpx2elev, version 0.3.6,
fournis dans `gpx2elev/`, sans interface Qt. Leur provenance et leurs empreintes
sont conservées dans [gpx2elev/ORIGINE.md](gpx2elev/ORIGINE.md).
Les dépendances de l'ensemble du script figurent dans `requirements.txt`.

## Protocole

- Coordonnées originales, sans correction XY automatique ni suppression de points.
- Rééchantillonnage spatial à 5 m, indépendamment pour chaque segment.
- Un seul modèle couvrant toute la trace : IGN LiDAR HD, puis Mapterhorn,
  FABDEM 1.2, Copernicus GLO-30, SRTM90, dans cet ordre.
- Gaussienne d'écart type 20 m et hystérésis de 2 m, avec les conventions
  d'extrémité de gpx2elev.
- Si tous les modèles échouent : GPX filtré, explicitement identifié comme
  secours. Sans altitudes GPX complètes, affichage `D+?` plutôt que zéro.

La simplification de 10 m sert uniquement au dessin KML. Les altitudes
GPX ne sont plus modifiées avant les statistiques. Le temps en mouvement
reste une estimation gpxpy, calculée avec des distances horizontales.

Les résultats exacts D+/D−, la source, les raisons des replis et les deux
calculs GPX (somme brute et filtrée) figurent dans le JSON et les données
étendues du KML. Le nom de la trace conserve un D+ arrondi au mètre.

## Cache et lancement

Les anciens caches JSON v5 sont ignorés. Les profils du moteur sont conservés
dans `.cache_gpx/gpx2elev` avec empreinte des coordonnées et configuration du modèle.
Les statistiques JSON v6 peuvent être réutilisées avec **--depuis-cache** lorsque
l'empreinte SHA-256 du GPX et le protocole correspondent ; la date et la durée
sont relues dans le fichier. Si ces statistiques sont absentes, les profils
locaux ou les altitudes GPX sont utilisés, sans téléchargement d'altitudes.

Sans **--depuis-cache**, les statistiques sont recalculées et les modèles
prioritaires sont retentés, même après un précédent repli. Quatre processus
maximum limitent les appels réseau et la consommation mémoire.

Exécuter `python gpx2dash.py chemin/vers/gpx --html tableau_bord.html` depuis
le projet. Le premier calcul complet peut télécharger des données et prendre
du temps. Les commandes de démarrage et les options sont décrites dans le README.

Contrôles hors réseau : `python -X utf8 test_agreg_denivele.py`, dont un
traitement dans un vrai processus. La référence personnelle optionnelle est
ignorée lorsque ses fichiers ne sont pas disponibles.
