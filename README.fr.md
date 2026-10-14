# GPX2DASH

[![EN · English](https://img.shields.io/badge/EN-English-34334b?style=for-the-badge)](README.md)
[![FR · Français](https://img.shields.io/badge/FR-Fran%C3%A7ais-958bea?style=for-the-badge)](README.fr.md)
[![CI](https://github.com/nico579/gpx2dash/actions/workflows/ci.yml/badge.svg)](https://github.com/nico579/gpx2dash/actions/workflows/ci.yml)
[![Latest release](https://img.shields.io/github/v/release/nico579/gpx2dash)](https://github.com/nico579/gpx2dash/releases/latest)

**GPX2DASH transforme un dossier contenant des traces GPX en un fichier KML
regroupant les parcours avec leur dénivelé recalculé, et en un tableau de bord
HTML pour comparer les sorties et préparer leur accès.**

## Les deux fichiers générés

### Un KML regroupant les traces

Tous les GPX exploitables du dossier sont réunis dans **un seul fichier KML**,
visualisable dans le tableau de bord ou dans une application cartographique
compatible. Chaque fichier GPX
conserve sa propre trace et sa couleur ; les interruptions d'enregistrement
restent séparées.

Le nom de chaque trace indique la date ou le nom du fichier, le lieu de départ,
la distance, le **D+ recalculé** et la durée. Les données étendues du KML
conservent les valeurs exactes **D+/D−**, le modèle d'altitude utilisé, le
protocole de calcul et les raisons d'un éventuel repli vers une autre source.
Le recalcul est effectué avant la simplification du dessin, fixée à 10 m par
défaut avec `--tolerance`.

### Un tableau de bord HTML des traces

Le tableau contient **une ligne par fichier GPX** et neuf colonnes :

| Colonne | Contenu |
|---|---|
| Date | Date de la sortie |
| Lieu de départ de la trace | Commune la plus proche du premier point du GPX |
| Distance de la trace | Longueur du parcours, en kilomètres |
| Dénivelé | D+ et D− recalculés, en mètres |
| Durée de la trace | Temps en mouvement estimé, ou temps écoulé si nécessaire |
| Distance routière | Distance en voiture depuis l'origine choisie jusqu'au départ du GPX |
| Durée de route | Durée estimée du même trajet, sans trafic en temps réel |
| Goudron longé (OSM) | Kilomètres du parcours longeant une voie au revêtement bitumineux renseigné |
| Traces communes | Nombre d'autres GPX partageant au moins 100 m continus, avec une tolérance de 15 m ; cliquer pour ouvrir leur carte |

Les colonnes permettent le **tri** et des **filtres combinables** : `=`, `>`,
`<` ou `Entre`. Toutes les conditions actives doivent être satisfaites.
Par exemple : une trace de 10 à 20 km, avec moins de 600 m de D+ et à moins de
45 minutes de route. Les titres et les filtres restent visibles pendant le
défilement.

L'origine routière se choisit par **ville ou coordonnées** à la génération ;
la ville peut ensuite être changée dans le tableau. Cliquer sur le lien d'une
ligne affiche **l'itinéraire routier et la trace GPX sur la même carte**.
Le tableau propose aussi une recherche libre et le téléchargement du GPX original.

La mesure du goudron utilise les points du GPX original et les voies
OpenStreetMap obtenues par **Overpass**. Par défaut, une portion doit rester
à **15 m maximum** de l'axe de la voie et présenter un écart de direction de **30°**
au maximum. Les revêtements confirmés et incertains sont distingués ; la
colonne accepte les mêmes filtres que les autres.

Le HTML s'ouvre par **double-clic**, sans serveur web. La lecture, le tri et les
filtres fonctionnent hors connexion. Les trajets utilisent **OSRM** et la
recherche de villes **Photon**, sans clé API ni compte de facturation.
Internet sert à récupérer les données manquantes et à afficher le fond de carte.

## Comment le dénivelé est recalculé

Le moteur de calcul **gpx2elev**, installé depuis PyPI, applique la même méthode
à chaque trace pour obtenir le dénivelé positif **D+** et négatif **D−** :

1. **Préparer le parcours original.** Les coordonnées du GPX sont conservées,
   sans correction automatique de position. Chaque segment est traité
   séparément et rééchantillonné tous les **5 m** de distance horizontale,
   avec conservation de son dernier point.
2. **Obtenir un profil d'altitude complet.** Le moteur retient le premier
   modèle disponible couvrant **toutes les positions de la trace**, dans
   cet ordre : **IGN LiDAR HD → Mapterhorn → FABDEM 1.2 → Copernicus GLO-30 →
   SRTM90**. Un seul modèle est utilisé pour l'ensemble de la trace ; un
   profil incomplet entraîne le passage au modèle suivant.
3. **Lisser le profil.** Un filtre gaussien d'écart type **20 m de distance
   parcourue** atténue les petites fluctuations d'altitude. Le traitement des
   extrémités prolonge le profil pour limiter les effets de bord.
4. **Retenir les montées et descentes.** Une hystérésis de **2 m** valide
   les changements de sens : un retournement montée/descente, ou l'inverse,
   n'est retenu qu'après une variation d'au moins 2 m depuis l'extrême atteint.
   Les extrémités de chaque segment restent prises en compte.
5. **Additionner les variations retenues.** Les hausses donnent le D+ ;
   les baisses donnent le D−. Les résultats des segments sont additionnés,
   sans créer de dénivelé entre deux segments discontinus.

Si aucun modèle ne fournit un profil complet, le moteur applique le même
rééchantillonnage, lissage et seuil aux **altitudes GPX**, lorsqu'elles sont
complètes. Ce résultat est identifié comme **« GPX filtré (secours) »**.
Si aucune altitude exploitable n'est disponible, le dénivelé reste **inconnu**.

Le tableau et le KML utilisent les mêmes résultats, affichés au mètre près ;
les valeurs exactes et les comparaisons avec les altitudes GPX brutes et filtrées
sont conservées dans le cache et les données étendues du KML. Les fichiers GPX
sources sont seulement lus. Le protocole complet est décrit dans
[AGREG_DENIVELE.md](AGREG_DENIVELE.md).

Chaque trace n'est traitée qu'une fois. Ses résultats sont rangés sous
l'empreinte SHA-256 de son contenu : un renommage ou un déplacement ne la fait
pas retraiter. Sans `--from-cache`, seules les traces nouvelles ou modifiées sont
calculées, ainsi que celles qui n'avaient obtenu que les altitudes GPX filtrées,
et les données d'altitude manquantes sont téléchargées. Avec `--from-cache`, les
résultats en cache sont repris tels quels et une trace nouvelle utilise les
profils d'altitude déjà en cache, puis les altitudes GPX filtrées ;
**aucune donnée d'altitude n'est téléchargée**.

## Installer et lancer

Choisir **une seule méthode d'installation**. Le bundle autonome est recommandé
pour utiliser l'application. L'exécution des sources Python est une alternative
pour travailler sur le code. **Il ne faut pas lancer les deux commandes.**

### Option 1 : bundle autonome (recommandé)

Les [releases GitHub](https://github.com/nico579/gpx2dash/releases) proposent :

| Système | Archive |
|---|---|
| Windows x86_64 | `gpx2dash-windows-x86_64.zip` |
| Linux x86_64 | `gpx2dash-linux-x86_64.tar.gz` |
| macOS Apple Silicon | `gpx2dash-macos-arm64.tar.gz` |

Décompresser et conserver **tout le dossier `gpx2dash`**, y compris `_internal`.
Dans un terminal ouvert dans ce dossier, lancer une première génération
avec recalcul du dénivelé, routage et mesure du goudron :

~~~powershell
.\gpx2dash.exe "C:\chemin\vers\gpx" --asphalt --html tableau_bord.html --kml traces.kml --language fr
~~~

Remplacer `C:\chemin\vers\gpx` par le chemin réel de ton dossier GPX, puis
ouvrir **tableau_bord.html** dans ce dossier GPX par double-clic une fois la
commande terminée.
Sous Linux/macOS, utiliser `./gpx2dash`. Le bundle contient Python et ses
dépendances : aucune installation de Python n'est nécessaire.
Passer directement aux [commandes d'utilisation](#commandes-dutilisation),
sans suivre la section d'installation des sources.

Les archives sont **construites et testées sur les runners GitHub**, sur chaque
système, avec les mêmes dépendances verrouillées que les sources.
Le fichier `SHA256SUMS.txt` de la release permet de vérifier les téléchargements.

La commande récupère les données manquantes et les conserve en cache.
Pour une régénération sans téléchargement d'altitudes, ajouter `--from-cache`.

### Option 2 : exécution depuis les sources

Choisir cette méthode **à la place du bundle** pour exécuter ou modifier
le code Python. **Python 3.12** et Git sont nécessaires. Le moteur de dénivelé
est fourni dans le dépôt : aucun autre projet, Conda ou interface Qt n'est nécessaire.

Sous Windows, dans PowerShell :

~~~powershell
git clone https://github.com/nico579/gpx2dash.git
cd gpx2dash
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements.txt
~~~

Pour générer le même catalogue qu'avec le bundle, à partir de ton dossier GPX :

~~~powershell
.\.venv\Scripts\python.exe -X utf8 gpx2dash.py "C:\chemin\vers\gpx" --asphalt --html tableau_bord.html --kml traces.kml --language fr
~~~

Remplacer `C:\chemin\vers\gpx` par le chemin réel de ton dossier GPX.
Cette commande produit le même tableau et le même KML que celle du bundle.
Le script affiche sa progression. Double-cliquer ensuite sur **tableau_bord.html**
dans ce dossier GPX.

Sous Linux ou macOS, remplacer les commandes de l'environnement par :

~~~bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements.txt
.venv/bin/python gpx2dash.py "/chemin/vers/gpx" --asphalt --html tableau_bord.html --kml traces.kml --language fr
~~~

Avec les sources, essayer le script **sans appel réseau**, avec l'exemple synthétique fourni :

~~~powershell
.\.venv\Scripts\python.exe -X utf8 gpx2dash.py examples --from-cache --no-routing --html demonstration.html --kml demonstration.kml
~~~

Ouvrir **examples/demonstration.html**. Les colonnes routières et le goudron restent
inconnus tant que leurs données ne sont pas téléchargées.

Le dépôt contient le code et cet exemple synthétique. Les GPX personnels,
les caches, les captures et les fichiers HTML/KML générés sont exclus par
**.gitignore**.

## Commandes d'utilisation

Les exemples ci-dessous utilisent le **bundle Windows dans PowerShell**.
Pour une autre installation, remplacer uniquement le début de la commande :

| Installation | Début de la commande |
|---|---|
| Bundle Windows | `.\gpx2dash.exe` |
| Sources Windows | `.\.venv\Scripts\python.exe -X utf8 gpx2dash.py` |
| Bundle Linux/macOS | `./gpx2dash` |
| Sources Linux/macOS | `.venv/bin/python gpx2dash.py` |

Les paramètres restent identiques. Remplacer `C:\chemin\vers\gpx` par le
chemin de ton dossier GPX (adapté à ton système). Chaque exemple est une
opération indépendante, pas une suite d'étapes obligatoires.

- **--from-cache** évite tout téléchargement d'altitudes : il réutilise les
  statistiques valides, les profils locaux, puis les altitudes du GPX.
- **--cache-clear** vide d'abord le cache : chaque trace est retraitée et ses
  données retéléchargées. Sans lui, le cache ne se vide jamais.
- **--asphalt** récupère les données de revêtement OSM manquantes, avec Internet.
- Les trajets routiers manquants sont calculés par OSRM et conservés dans le cache.
- Pour utiliser les modèles de terrain IGN et les autres modèles, retirer
  **--from-cache** ; le premier traitement peut télécharger beaucoup de données.
- Pour régénérer ensuite avec les seules données locales, retirer **--asphalt**
  et ajouter **--no-routing**.

## Langue et en-têtes fixes

Le tableau propose **EN · English / FR · Français** en haut de page. Il adopte
la langue du navigateur (français pour un navigateur français, anglais sinon)
ou celle passée avec **`--language en` / `--language fr`**. Le dernier choix
est conservé dans le navigateur et prend priorité lors des ouvertures suivantes.
Les filtres et le tri sont conservés pendant un changement de langue.

Les **titres et la ligne de filtres restent fixes** pendant le défilement
vertical de la zone du tableau. Le défilement horizontal garde chaque titre
aligné avec sa colonne, sur ordinateur et mobile.

Les paramètres et l'aide `--help` sont en anglais. Les anciens paramètres
français, dont `--depuis-cache`, restent acceptés comme alias cachés.

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
dans le navigateur ; les résultats déjà calculés sont réutilisés sans nouvel appel.
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

## Traces communes

Le calcul compare les points GPX originaux, en mètres, sans téléchargement.
Une autre trace compte une seule fois si les deux parcours partagent au moins
**100 m continus** à **15 m maximum** l'un de l'autre, quel que soit le sens de
parcours. La trace elle-même est exclue. Les petits croisements et les portions
séparées par une interruption d'enregistrement ne sont pas additionnés.

Cliquer sur le nombre dans la colonne **Traces communes** ouvre la carte de la
trace sélectionnée et de ses traces communes. La trace sélectionnée est dessinée
plus épaisse et chaque parcours conserve sa couleur. Les traces communes sont
affichées même si des filtres du tableau les masquent.

La colonne permet le tri et les mêmes filtres numériques que les autres colonnes.
Les paramètres sont réglables avec `--overlap-tolerance METRES` et
`--overlap-min-length METRES`. Les comparaisons sont conservées dans
`.cache_gpx/traces_communes_v1.json` et réutilisées par empreinte du contenu GPX ;
un renommage ne les invalide pas. Retirer une trace du dossier la retire du
compteur et de la carte. `--cache-clear` efface aussi ces comparaisons.

## Kilomètres de goudron longé

La colonne **Goudron longé (OSM)** mesure les portions du GPX qui longent une
voie dont le revêtement bitumineux est renseigné dans OpenStreetMap. Elle
accepte les mêmes filtres **=**, **>**, **<** et **Entre**, en kilomètres, et
se combine avec les conditions de toutes les autres colonnes.

Pour effectuer le premier calcul, avec Internet :

~~~powershell
.\gpx2dash.exe "C:\chemin\vers\gpx" --from-cache --no-routing --asphalt --html tableau_bord.html --kml traces.kml
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
survol. **Relancer avec --asphalt reprend les traces manquantes** en conservant
les calculs réussis. Les erreurs temporaires du service déclenchent des
tentatives espacées, avec respect de l'attente annoncée par le serveur.

Pour modifier les tolérances :

~~~powershell
.\gpx2dash.exe "C:\chemin\vers\gpx" --from-cache --no-routing --asphalt --asphalt-tolerance 20 --asphalt-angle 30 --html tableau_bord.html
~~~

La marge accepte 1 à 50 mètres ; l'angle accepte 1 à 60 degrés. Les données
locales couvrent les changements de marge dans cet intervalle. Les mesures
et les voies OSM sont conservées jusqu'à **--cache-clear** dans
.cache_gpx/goudron_osm_v1.json et .cache_gpx/goudron_osm/.
Le cache distingue l'empreinte du GPX, les tolérances, le serveur et le
protocole de calcul. Sans **--asphalt**, seules les données locales sont
utilisées. La consultation, le tri et les filtres du HTML fonctionnent
ensuite hors connexion, sans serveur local.

Les voies sont obtenues par le service public **Overpass**, sans clé ni
facturation, par lots de traces proches et au moins trois secondes entre
les requêtes. Un lot trop lourd pour le serveur (délai ou taille dépassés)
est coupé en deux jusqu'à isoler la trace en cause : les autres traces
restent mesurées. Un autre service peut être choisi avec **--overpass-server**.
Ces distances restent des estimations : une route non renseignée, une erreur
GPS, une voie parallèle ou une superposition de pont peuvent changer
l'interprétation. Voir [la description OSM du revêtement](https://wiki.openstreetmap.org/wiki/Key:surface).

## Voir le KML agrégé dans le tableau

Cliquer sur **Carte du KML agrégé**, à côté de la recherche du catalogue.
La carte affiche tous les parcours avec **les mêmes couleurs que le KML** ;
les segments discontinus restent séparés.

Cocher **Traces filtrées uniquement** pour afficher les parcours qui satisfont
la recherche et les filtres du tableau. **Vue d'ensemble** recadre les traces
affichées. Un clic sur une trace ouvre sa fiche : date, lieu, distance,
dénivelé, durée, accès routier et goudron longé. La fiche permet de télécharger
le GPX original ou d'ouvrir **l'itinéraire routier et la trace**.

**Télécharger le KML complet** récupère le fichier généré, avec toutes ses traces,
même si la carte est filtrée. Conserver le KML à l'emplacement prévu pour ce lien.
Les géométries sont intégrées dans le HTML : la carte globale fonctionne en
ouverture directe, sans serveur local. Le fond de carte nécessite Internet ;
les tracés restent visibles si le fond ne se charge pas. L'ouverture de la carte
globale ne calcule aucun itinéraire routier.

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

Dans PowerShell, sans dossier indiqué :

~~~powershell
.\gpx2dash.exe
~~~

Pour traiter un autre dossier :

~~~powershell
.\gpx2dash.exe "C:\chemin\vers\gpx"
~~~

Sans dossier indiqué, le programme recherche les GPX dans le dossier de
l'exécutable (ou du script pour les sources). Un dossier différent peut être
fourni en premier argument :

~~~powershell
.\gpx2dash.exe "C:\chemin\vers\gpx" --html tableau_bord.html
~~~

La recherche est récursive : les sous-dossiers sont inclus, sauf les dossiers
`.cache_gpx` et le dossier de cache personnalisé. Les extensions .gpx et .GPX
sont reconnues. Le cache `.cache_gpx` et les fichiers KML et HTML sont créés
dans le dossier traité. Sans nom de sortie explicite, les fichiers portent le nom
du dossier suivi de l'horodatage : par exemple `gpx_20261013_223000.html`
et `gpx_20261013_223000.kml` pour un dossier `gpx`.
Les chemins relatifs passés à `--cache`, `--html` et `--kml` sont relatifs au
dossier traité ; les chemins absolus permettent de choisir un autre emplacement.
Ajouter `--asphalt` pour télécharger les données de goudron manquantes.
Le cache ne se vide jamais seul :
profils d'altitude et tuiles du MNT, mesures de goudron, voies OSM et trajets
sont conservés jusqu'à --cache-clear, qui n'efface que les fichiers créés par
gpx2dash dans ce dossier.

--from-cache reprend tous les résultats en cache, y compris ceux du dossier GPX,
si l'empreinte SHA-256 et le protocole de calcul correspondent. Une trace
nouvelle utilise les profils locaux ou les altitudes GPX, sans téléchargement
d'altitudes. Les fichiers GPX sont seulement lus. Les trajets OSRM peuvent être
calculés en ligne dans ce mode.

Pour définir une autre ville dès la génération :

~~~powershell
.\gpx2dash.exe "C:\chemin\vers\gpx" --from-cache --origin-city "Toulon, Var, France" --html tableau_bord.html
~~~

La ligne de commande retient le premier résultat Photon et affiche son libellé.
La sélection dans le HTML permet de choisir explicitement parmi les résultats.
Pour fixer des coordonnées exactes :

~~~powershell
.\gpx2dash.exe "C:\chemin\vers\gpx" --origin 43.1242 5.9280 --origin-name "Mon départ à Toulon"
~~~

Pour générer le tableau sans requête au service de routage :

~~~powershell
.\gpx2dash.exe "C:\chemin\vers\gpx" --from-cache --no-routing --html tableau_bord.html
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
deux appels. Le cache distingue serveur, origine et destination ; trajets et
absences de route y sont conservés jusqu'à --cache-clear.
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
.\gpx2dash.exe "C:\chemin\vers\gpx" --osrm-server "http://localhost:5000"
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

Les dépendances vérifiées sont listées dans **requirements.txt**. Le moteur
[gpx2elev](https://pypi.org/project/gpx2elev/) est installé depuis PyPI, à la
version qui y est figée ; son paquet de base n'installe pas Qt, et l'installation
ne dépend d'aucun dossier voisin.

Les calculs numériques du goudron utilisent **NumPy**, les transformations
natives de **PyProj** et l'index spatial natif de **Shapely**. Les voies d'un
même lot sont préparées une seule fois ;
le choix des voies proches est vectorisé. Conda n'est pas nécessaire ; le code
n'utilise pas de compilation JIT Numba actuellement.

## Développement : tests, CI et releases

Ces commandes concernent les contributeurs utilisant **l'installation depuis
les sources**, depuis le dossier du dépôt. Elles ne sont pas nécessaires
pour utiliser le bundle.

Contrôles hors réseau :

~~~powershell
.\.venv\Scripts\python.exe -X utf8 test_agreg_denivele.py
.\.venv\Scripts\python.exe -X utf8 test_tableau_bord.py
.\.venv\Scripts\python.exe -X utf8 test_goudron_osm.py
~~~

La CI teste les calculs, les caches et le rendu sur **Windows, Linux et macOS**.
Elle vérifie avec Chromium l'interface EN/FR, les filtres combinés, le routage,
le KML agrégé (couleurs, filtres, fiches et téléchargements en ouverture directe),
la carte et les en-têtes fixes sur ordinateur et mobile. Elle construit ensuite
les trois bundles et exécute chacun sur des GPX et des voies OSM synthétiques :
génération KML/HTML, processus parallèles, géocodeur et calcul natif du goudron.

Les tags `vX.Y.Z` lancent `release.yml`, qui réutilise ces mêmes tests et builds.
Les archives ne sont publiées que si tous les contrôles passent.
Aucun binaire construit localement n'est envoyé sur la release.

Pour les contrôles navigateur locaux :

~~~powershell
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements-dev.txt
.\.venv\Scripts\python.exe -X utf8 .qa/verifier_filtres.py --fixtures-only
.\.venv\Scripts\python.exe -X utf8 .qa/verifier_carte.py
.\.venv\Scripts\python.exe -X utf8 .qa/verifier_kml.py
.\.venv\Scripts\python.exe -X utf8 .qa/verifier_langues.py
~~~

Microsoft Edge est utilisé localement. Avec `GPX2DASH_BROWSER=chromium`,
installer `.\.venv\Scripts\python.exe -m playwright install chromium` et utiliser Chromium comme la CI.
`requirements.in` fixe les dépendances directes ; les verrous runtime, build et
dev incluent les dépendances transitives et leurs empreintes.


Les scripts .qa/visualiser_tableau.py, .qa/verifier_villes.py,
.qa/verifier_carte.py, .qa/verifier_filtres.py et .qa/verifier_catalogue.py vérifient les interactions
et le catalogue réel avec Playwright et Microsoft Edge.
.qa/verifier_carte_en_ligne.py vérifie aussi une vraie trace et OSRM, avec les tuiles simulées.
Les aperçus de développement utilisent .qa/serveur_preview.py ; ce serveur n'est pas requis pour consulter le HTML.
