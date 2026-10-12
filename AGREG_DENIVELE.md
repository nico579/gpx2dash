# Calcul du dénivelé d'gpx2dash.py

`gpx2dash.py` utilise le moteur de calcul gpx2elev, installé depuis
[PyPI](https://pypi.org/project/gpx2elev/) à la version figée dans
`requirements.txt`, sans interface Qt. Les dépendances de l'ensemble du script
figurent dans `requirements.txt`.

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

Chaque trace n'est traitée qu'une fois. Ses résultats sont rangés dans
`.cache_gpx` sous l'empreinte SHA-256 de son contenu (entrées v7) : un renommage
ou un déplacement ne la fait pas retraiter, et les anciennes entrées v6, nommées
d'après la trace, sont migrées une fois sans recalcul. Les profils du moteur sont
conservés dans `.cache_gpx/gpx2elev` avec empreinte des coordonnées et
configuration du modèle. Le cache ne se vide jamais seul : seul
**--cache-clear** l'efface.

Sans **--depuis-cache**, un dénivelé déjà obtenu d'un modèle d'altitude est
repris tel quel ; seules les traces nouvelles ou modifiées, et celles qui
n'avaient obtenu que les altitudes GPX filtrées, sont calculées. Avec
**--depuis-cache**, tout ce qui est en cache est repris, et une trace nouvelle
utilise les profils locaux ou les altitudes GPX, sans téléchargement
d'altitudes. Quatre processus maximum limitent les appels réseau et la
consommation mémoire.

Exécuter `python gpx2dash.py chemin/vers/gpx --html tableau_bord.html` depuis
le projet. Le premier calcul complet peut télécharger des données et prendre
du temps. Les commandes de démarrage et les options sont décrites dans le README.

Contrôles hors réseau : `python -X utf8 test_agreg_denivele.py`, dont un
traitement dans un vrai processus. La référence personnelle optionnelle est
ignorée lorsque ses fichiers ne sont pas disponibles.
