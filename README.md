# GPX2DASH

Le script produit un KML et un tableau HTML autonome avec une ligne par fichier
GPX et huit colonnes triables : date, lieu de départ de la trace, distance,
dénivelé D+/D−, durée de la trace, distance de route, durée de route et
**goudron longé (OSM)**.

Les trajets utilisent **OSRM et OpenStreetMap**, sans clé ni compte de facturation.
La recherche de villes utilise le géocodeur open source **Photon**.

## Installation et premier lancement

**Python 3.12** et Git sont nécessaires. Le moteur de dénivelé est fourni dans
le dépôt : aucun autre projet, Conda ou interface Qt n'est nécessaire.

Sous Windows, dans PowerShell :

~~~powershell
git clone https://github.com/nico579/gpx2dash.git
cd gpx2dash
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
~~~

Pour un premier catalogue à partir de ton dossier GPX :

~~~powershell
.\.venv\Scripts\python.exe -X utf8 gpx2dash.py "..\gpx" --depuis-cache --goudron --html tableau_bord.html --kml traces_regroupees.kml
~~~

Remplacer `..\gpx` par le chemin du dossier souhaité. Le script affiche sa
progression. Double-cliquer ensuite sur **tableau_bord.html**.

- **--depuis-cache** évite tout téléchargement d'altitudes : il réutilise les
  statistiques valides, les profils locaux, puis les altitudes du GPX.
- **--goudron** récupère les données de revêtement OSM manquantes, avec Internet.
- Les trajets routiers manquants sont calculés par OSRM et conservés dans le cache.
- Pour utiliser les modèles de terrain IGN et les autres modèles, retirer
  **--depuis-cache** ; le premier traitement peut télécharger beaucoup de données.
- Pour régénérer ensuite avec les seules données locales, retirer **--goudron**
  et ajouter **--sans-routage**.

Sous Linux ou macOS, remplacer les commandes de l'environnement par :

~~~bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python gpx2dash.py ../gpx --depuis-cache --goudron --html tableau_bord.html --kml traces_regroupees.kml
~~~

Pour essayer le script **sans appel réseau**, avec l'exemple synthétique fourni :

~~~powershell
.\.venv\Scripts\python.exe -X utf8 gpx2dash.py examples --depuis-cache --sans-routage --html demonstration.html --kml demonstration.kml
~~~

Ouvrir **demonstration.html**. Les colonnes routières et le goudron restent
inconnus tant que leurs données ne sont pas téléchargées.

Le dépôt contient le code et cet exemple synthétique. Les GPX personnels,
les caches, les captures et les fichiers HTML/KML générés sont exclus par
**.gitignore**.

## Ouvrir le tableau

Double-cliquer sur le fichier **tableau_bord.html** pour l'ouvrir dans le navigateur.
Aucun serveur local, compte ou clé API n'est nécessaire.

Le fond utilise **OpenTopoMap**, une carte topographique basée sur les données
OpenStreetMap et SRTM, avec les attributions et la licence CC-BY-SA visibles.
Son [service public](https://opentopomap.org/about#verwendung) permet cette
utilisation dans une application. Les tuiles sont chargées uniquement à
l'ouverture de la carte ; le cache normal du navigateur est conservé.

Le fond standard de tile.openstreetmap.org a été remplacé : sa politique
exige un référent HTTP qu'un fichier HTML ouvert directement ne fournit pas.
Le nouveau fond ne dépend pas d'un référent pour s'afficher.

## Choisir la ville dans le tableau

Une fois le tableau ouvert :

1. Saisir une ville, par exemple « Toulon, France », puis cliquer sur **Rechercher**.
2. Sélectionner la commune dans **Ville retenue** ; le pays aide à distinguer les homonymes.
3. Cliquer sur **Calculer les trajets**.

Les deux colonnes routières, leurs liens OpenStreetMap et le bilan sont mis à jour.
Le tri choisi reste appliqué. Le dernier départ et les résultats sont conservés
dans le navigateur ; les résultats récents sont réutilisés sans nouvel appel.
Le tableau propose aussi des filtres combinables et le téléchargement de chaque GPX.

Garéoult est le départ initial. Une connexion Internet est nécessaire pour chercher
une nouvelle ville ou calculer des trajets absents du cache. La lecture du tableau,
la recherche dans les traces et le tri fonctionnent hors connexion.
En cas d'annulation ou d'erreur de service, les valeurs affichées conservent leur
origine ; les lots terminés restent en cache pour reprendre.

## Combiner les filtres

Sous chaque en-tête, choisir **=**, **>**, **<** ou **Entre (inclus)**, puis
saisir la valeur ou les deux bornes. **Tous** désactive la condition de cette
colonne. Une trace doit satisfaire **toutes** les conditions actives (ET),
ainsi que la recherche libre si elle est renseignée.

Les distances sont en **km**, le dénivelé **D+ en mètres** et les durées en
**minutes** (par exemple 90 pour 1 h 30). Les comparaisons portent sur les
valeurs arrondies affichées ; le tri conserve la précision des données.
Les nombres acceptent une virgule ou un point décimal. Les dates utilisent
le calendrier ; les lieux sont comparés en entier, sans distinction de
majuscules ou d'accents, dans l'ordre alphabétique.

Par exemple : **distance de la trace entre 10 et 20 km**, **D+ < 600 m**,
**durée de route < 45 minutes**. Seules les traces respectant les trois
critères restent visibles. Les valeurs inconnues sont exclues lorsqu'une
condition concerne leur colonne. Une condition incomplète ou invalide
n'est pas appliquée ; le tableau indique ce qui reste à compléter.

**Effacer les filtres** remet toutes les colonnes sur **Tous** et vide la
recherche libre. Le tri et les conditions actives restent appliqués après
un changement de ville et le recalcul des trajets. Ces filtres fonctionnent
hors connexion, dans le fichier HTML ouvert par double-clic.

## Kilomètres de goudron longé

La colonne **Goudron longé (OSM)** mesure les portions du GPX qui longent une
voie dont le revêtement bitumineux est renseigné dans OpenStreetMap. Elle
accepte les mêmes filtres **=**, **>**, **<** et **Entre**, en kilomètres, et
se combine avec les conditions de toutes les autres colonnes.

Pour effectuer le premier calcul, avec Internet :

~~~powershell
python gpx2dash.py --depuis-cache --sans-routage --goudron --html tableau_bord.html --kml traces_regroupees.kml
~~~

Le calcul utilise les points du **GPX original**, avant simplification. Une
portion est comptée à **15 mètres maximum** de l'axe de la voie OSM, avec un
écart de direction de **30 degrés maximum**, dans les deux sens de parcours.
Les traversées perpendiculaires sont exclues. La trace est échantillonnée par
pas de 5 mètres au maximum ; sa direction est évaluée sur une fenêtre de
20 mètres pour atténuer le bruit GPS. Les interruptions entre segments ne
sont pas reliées. Un passage répété compte sa distance réellement parcourue,
et plusieurs voies proches ne doublent pas les kilomètres.

Les valeurs OSM **asphalt, chipseal, tarmac, bitumen et tar** indiquent du
bitume. Une surface absente ou ambiguë, notamment **paved**, reste incertaine :
elle peut désigner du béton ou des pavés. Le type de route ne suffit pas à
prouver son revêtement. Une valeur **≥** donne le minimum repéré, accompagné
des kilomètres incertains. Si seul le revêtement incertain est rencontré,
la cellule affiche un tiret avec cette distance incertaine. Les filtres
portent sur le minimum repéré ; une cellule inconnue n'est pas interprétée
comme zéro.

Une panne de téléchargement laisse aussi un tiret ; sa cause apparaît au
survol. **Relancer avec --goudron reprend les traces manquantes** en conservant
les calculs réussis. Les erreurs temporaires du service déclenchent des
tentatives espacées, avec respect de l'attente annoncée par le serveur.

Pour modifier les tolérances :

~~~powershell
python gpx2dash.py --depuis-cache --sans-routage --goudron --marge-goudron 20 --angle-goudron 30 --html tableau_bord.html
~~~

La marge accepte 1 à 50 mètres ; l'angle accepte 1 à 60 degrés. Les données
locales couvrent les changements de marge dans cet intervalle. Les mesures
et les voies OSM sont conservées pendant **30 jours** dans
.cache_gpx/goudron_osm_v1.json et .cache_gpx/goudron_osm/.
Le cache distingue l'empreinte du GPX, les tolérances, le serveur et le
protocole de calcul. Sans **--goudron**, seules les données locales sont
utilisées. La consultation, le tri et les filtres du HTML fonctionnent
ensuite hors connexion, sans serveur local.

Les voies sont obtenues par le service public **Overpass**, sans clé ni
facturation, par lots de traces proches et au moins trois secondes entre
les requêtes. Un autre service peut être choisi avec **--serveur-overpass**.
Ces distances restent des estimations : une route non renseignée, une erreur
GPS, une voie parallèle ou une superposition de pont peuvent changer
l'interprétation. Voir [la description OSM du revêtement](https://wiki.openstreetmap.org/wiki/Key:surface).

## Voir l'itinéraire routier et la trace GPX

Cliquer sur **Itinéraire et trace GPX** dans la ligne d'une trace. La carte
s'ouvre dans le tableau et affiche le trajet aller depuis la ville de départ
actuelle en **bleu**, et la trace GPX en **orange**.

**Vue d'ensemble** cadre le trajet et la trace. **Zoom sur la trace** permet
d'examiner la sortie. La fenêtre propose aussi le téléchargement du GPX
original et l'ouverture du trajet dans OpenStreetMap.

La géométrie GPX est embarquée dans le HTML, après la même simplification que
le KML ; les segments discontinus restent séparés. Le fichier original
conserve ses points et ses données. Aucune importation dans un site tiers
n'est nécessaire pour afficher la trace.

Le fond de carte OpenTopoMap et le tracé routier OSRM se chargent uniquement
à l'ouverture de la carte. Ils nécessitent Internet. Si la route ou le fond
de carte est indisponible, la trace reste visible. Les routes déjà affichées
sont réutilisées pendant la session du navigateur, avec un cache distinct
par ville de départ et destination.

[Leaflet 1.9.4](https://leafletjs.com/download.html) est fourni dans
assets/leaflet-1.9.4 et embarqué dans le HTML avec sa licence BSD.
Le HTML est autonome : aucune installation JavaScript ni serveur local n'est
nécessaire. Internet est nécessaire pour le fond de carte et le routage.
L'utilisation du service public doit rester modérée, sans téléchargement massif
de tuiles ; sa disponibilité n'est pas garantie.

## Générer le catalogue

Dans PowerShell, depuis ce dossier :

~~~powershell
python gpx2dash.py --depuis-cache --goudron --html tableau_bord.html --kml traces_regroupees.kml
~~~

Sans dossier indiqué, le script utilise le dossier voisin `../gpx` s'il existe,
sinon le dossier courant. Un dossier différent peut être fourni en premier argument :

~~~powershell
python gpx2dash.py "C:\chemin\vers\les\gpx" --html tableau_bord.html
~~~

Les extensions .gpx et .GPX sont reconnues. Sans nom de sortie explicite,
les fichiers KML et HTML sont horodatés. Les caches sont écrits dans
.cache_gpx de gpx2dash, configurable avec --cache.

--depuis-cache réutilise les statistiques du dossier GPX si l'empreinte SHA-256
et le protocole de calcul correspondent. La date et la durée sont relues dans
le GPX. À défaut de statistiques valides, le moteur utilise les profils locaux
ou les altitudes GPX, sans téléchargement d'altitudes. Le dossier source est
seulement lu. Les trajets OSRM peuvent être calculés en ligne dans ce mode.

Pour définir une autre ville dès la génération :

~~~powershell
python gpx2dash.py --depuis-cache --ville-depart "Toulon, Var, France" --html tableau_bord.html
~~~

La ligne de commande retient le premier résultat Photon et affiche son libellé.
La sélection dans le HTML permet de choisir explicitement parmi les résultats.
Pour fixer des coordonnées exactes :

~~~powershell
python gpx2dash.py --origine 43.1242 5.9280 --nom-origine "Mon départ à Toulon"
~~~

Pour générer le tableau sans requête routière par Python :

~~~powershell
python gpx2dash.py --depuis-cache --sans-routage --html tableau_bord.html
~~~

Les valeurs routières déjà en cache sont conservées. Le choix de ville dans le
HTML reste disponible. L'ancien nom --sans-maps est accepté comme alias.

## Routage et cache

Les trajets sont des allers en voiture, sans trafic en temps réel, depuis le point
représentant la ville choisie jusqu'au premier point du GPX rattaché au réseau
routier. L'origine initiale est la mairie de Garéoult (43.3293, 6.0458).
La distance correspond à l'itinéraire le plus rapide proposé par OSRM.
L'approche finale à pied n'est pas incluse. Si le rattachement est à plus de
1 km, ou si aucune liaison routière n'existe, les valeurs restent inconnues ;
la raison figure au survol des cellules.

Les départs de traces identiques sont regroupés. Les requêtes de matrice
portent sur 25 destinations au maximum, avec au moins 1,05 seconde entre
deux appels. Le cache distingue serveur, origine et destination ; sa durée
est de 30 jours pour les trajets et de 24 heures pour les absences de route.
Les pannes réseau ne sont pas mémorisées comme une absence de route.
Le serveur public répartit ses données par continent. Si un lot mixte est
rattaché loin de l'origine, une seconde requête fixe la région du départ ;
les destinations sans liaison dans cette région restent inconnues.
Le cache Python est .cache_gpx/trajets_osrm_v1.json ; le HTML embarque les
résultats initiaux puis utilise le stockage local du navigateur.

Le serveur public est [routing.openstreetmap.de](https://routing.openstreetmap.de/about.html).
Son usage est limité : pas d'usage intensif et au maximum une requête par seconde.
Pour une utilisation partagée ou importante, utiliser son propre
[serveur OSRM](https://github.com/Project-OSRM/osrm-backend) :

~~~powershell
python gpx2dash.py --serveur-osrm "http://localhost:5000"
~~~

Le serveur doit fournir le profil voiture et les matrices de distance et de durée ;
il doit autoriser les requêtes du navigateur (CORS) pour le recalcul dans le HTML.
[Photon](https://github.com/komoot/photon) fournit la recherche de communes sur
demande, sans recherche automatique à chaque frappe.
Les attributions OpenStreetMap, OSRM et Photon figurent dans la page.

## Statistiques et dépendances

La date vient du premier point horodaté, en heure locale, puis des métadonnées
GPX, puis du nom du fichier (YYYY-MM-DD, YYYY_MM_DD ou YYYYMMDD).
La distance, le dénivelé et la durée sont calculés avant la simplification KML.
La durée estime le temps en mouvement, avec repli sur le temps écoulé.
Le lieu de départ de la trace est la commune la plus proche fournie par
reverse_geocoder ; le lien OpenStreetMap utilise les coordonnées du GPX.

Les valeurs inconnues restent des tirets. Les fichiers illisibles gardent leur
ligne. Le protocole de dénivelé est décrit dans [AGREG_DENIVELE.md](AGREG_DENIVELE.md).

Les dépendances vérifiées sont listées dans **requirements.txt**. Les seuls
modules de calcul nécessaires de gpx2elev sont inclus dans **gpx2elev/**,
avec leur version et leur provenance dans **gpx2elev/ORIGINE.md**. L'installation
ne dépend d'aucun dossier voisin et n'installe pas Qt.

Les calculs numériques du goudron utilisent **NumPy**, les transformations
natives de **PyProj** et l'index spatial natif de **Shapely**. Les voies d'un
même lot sont préparées une seule fois ;
le choix des voies proches est vectorisé. Conda n'est pas nécessaire ; le code
n'utilise pas de compilation JIT Numba actuellement.

Contrôles hors réseau :

~~~powershell
python -X utf8 test_agreg_denivele.py
python -X utf8 test_tableau_bord.py
python -X utf8 test_goudron_osm.py
~~~

Les tests de calcul et de rendu sont aussi exécutés sur Windows et Linux par
GitHub Actions. Les contrôles dans le navigateur nécessitent
**requirements-dev.txt** et Microsoft Edge.

Les scripts .qa/visualiser_tableau.py, .qa/verifier_villes.py,
.qa/verifier_carte.py, .qa/verifier_filtres.py et .qa/verifier_catalogue.py vérifient les interactions
et le catalogue réel avec Playwright et Microsoft Edge.
.qa/verifier_carte_en_ligne.py vérifie aussi une vraie trace et OSRM, avec les tuiles simulées.
Les aperçus de développement utilisent .qa/serveur_preview.py ; ce serveur n'est pas requis pour consulter le HTML.
