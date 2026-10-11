import os
import re
import argparse
import multiprocessing
import sys
from version import VERSION
import gpxpy
import simplekml
from datetime import datetime
import concurrent.futures
from tqdm import tqdm
import json
import hashlib
from collections import Counter
from pathlib import Path

from couleurs_traces import couleur_kml as couleur_stable
from denivele_gpx2elev import PROTOCOL, calculer_denivele
from gpx2elev.providers import atomic_write
from tableau_bord import date_du_nom, extraire_date, generer_tableau_bord
from goudron_osm import (MARGE_GOUDRON, ANGLE_GOUDRON, SERVEUR_OVERPASS,
                         ajouter_goudron_osm, parametres_valides)
from trajets_osrm import (DEPART_GAREOULT, SERVEUR_OSRM, ajouter_trajets_osrm,
                          chercher_villes, coordonnees, serveur_valide)

DOSSIER_CACHE = ".cache_gpx"
VERSION_CACHE = "v6-gpx2elev"

def nettoyer_heure_du_nom(nom):
    # Retire l'heure HH-MM-SS (ou HH:MM:SS, HHMMSS) qui suit une date YYYY-MM-DD (ou YYYYMMDD).
    # Ne touche pas à la date elle-même.
    nom = re.sub(
        r'(\d{4}[-_]?\d{2}[-_]?\d{2})[T_ \-]\d{2}[-:_]?\d{2}[-:_]?\d{2}',
        r'\1',
        nom,
    )
    return nom

def formater_duree(secondes):
    if secondes is None or secondes <= 0:
        return "0min"
    total_min = int(round(secondes / 60))
    h, m = divmod(total_min, 60)
    if h > 0:
        return f"{h}h{m:02d}"
    return f"{m}min"

def formater_distance(metres):
    if not metres:
        return "0km"
    return f"{metres / 1000:.1f}km"

def _calc_duree(gpx):
    # Temps en mouvement (pauses exclues) ; repli sur le temps écoulé
    # premier -> dernier point si les données de vitesse sont inexploitables.
    duree_s = None
    try:
        # L'altitude GPS bruitée ne doit pas gonfler les vitesses (distance 3D).
        copie = gpx.clone()
        for track in copie.tracks:
            for segment in track.segments:
                for point in segment.points:
                    point.elevation = None
        mouvement = copie.get_moving_data()
        if mouvement is not None and mouvement.moving_time:
            duree_s = mouvement.moving_time
    except Exception:
        pass
    if duree_s is None:
        bornes = gpx.get_time_bounds()
        if bornes.start_time is not None and bornes.end_time is not None:
            duree_s = (bornes.end_time - bornes.start_time).total_seconds()
        else:
            # gpxpy ne prend pas les rtept en compte dans get_time_bounds().
            instants = [point.time.timestamp() for route in gpx.routes
                        for point in route.points if point.time is not None]
            if len(instants) >= 2:
                duree_s = max(instants) - min(instants)
    return duree_s

def extraire_et_reduire(args):
    chemin_fichier, tolerance_m = args[:2]
    options = args[2] if len(args) > 2 else {}
    nom_trace = Path(chemin_fichier).stem
    identite = {'nom': nom_trace, 'chemin_gpx': str(Path(chemin_fichier).resolve()),
                'date': date_du_nom(nom_trace)}
    dossier_cache = Path(options.get("dossier_cache") or Path(chemin_fichier).parent / DOSSIER_CACHE)
    nom_cache = f"{nom_trace}_tol{tolerance_m}_{VERSION_CACHE}.json"
    fichier_cache = dossier_cache / nom_cache
    candidats = [fichier_cache]
    if options.get("cache_source"):
        candidats.append(Path(options["cache_source"]) / nom_cache)
    try:
        brut = Path(chemin_fichier).read_bytes()
        try:
            texte = brut.decode('utf-8-sig')
        except UnicodeDecodeError:
            texte = brut.decode('latin-1')
        gpx = gpxpy.parse(texte)
        empreinte = hashlib.sha256(brut).hexdigest()
        donnees_cache = {}
        for candidat in candidats:
            try:
                donnees = json.loads(candidat.read_text(encoding='utf-8'))
                if isinstance(donnees, dict) and donnees.get('empreinte_gpx') == empreinte:
                    donnees_cache = donnees
                    break
            except (OSError, ValueError):
                continue
        cles_stats = ('denivele_pos', 'denivele_neg', 'denivele_exact', 'source_denivele',
                      'modele', 'distance_m', 'gpx_somme_brute', 'gpx_filtre', 'protocole',
                      'version_gpx2elev', 'positions_5m', 'replis', 'erreur_modeles')
        reutilise = (options.get("statistiques_cache", False)
                     and donnees_cache.get("protocole") == PROTOCOL
                     and all(cle in donnees_cache for cle in cles_stats))
        if reutilise:
            stats = {cle: donnees_cache[cle] for cle in cles_stats}
        elif options.get("altitudes_en_ligne", True):
            stats = calculer_denivele(brut, dossier_cache / 'gpx2elev')
        else:
            stats = calculer_denivele(brut, dossier_cache / 'gpx2elev', online=False)
    except Exception as e:
        return {**identite, 'erreur': f"Échec lecture ou calcul : {e}"}

    # Date et durée sont toujours extraites avant la simplification.
    duree_s = _calc_duree(gpx)
    date_trace = extraire_date(gpx, nom_trace)
    gpx.simplify(max_distance=tolerance_m)
    segments = []
    for track in gpx.tracks:
        for segment in track.segments:
            points = [[point.longitude, point.latitude] for point in segment.points]
            if len(points) >= 2:
                segments.append(points)
    for route in gpx.routes:
        points = [[point.longitude, point.latitude] for point in route.points]
        if len(points) >= 2:
            segments.append(points)
    if not segments:
        return {**identite, 'erreur': "Aucune donnée de tracé."}
    lon_depart, lat_depart = segments[0][0]
    resultat = {
        **identite, 'date': date_trace, 'chemin_cache': str(fichier_cache),
        'segments': segments, 'lat_lon_depart': (lat_depart, lon_depart),
        **stats, 'empreinte_gpx': empreinte, 'duree_s': duree_s,
        'statistiques_cache': bool(reutilise),
    }
    if donnees_cache.get('ville') is not None:
        resultat['ville'] = donnees_cache['ville']
    return resultat

def fusionner_gpx_vers_kml_parallele(dossier_entree, fichier_sortie, tolerance_m=10, epaisseur=3,
                                    *, fichier_html=None, routes_en_ligne=True,
                                    origine_route=DEPART_GAREOULT, libelle_origine="Mairie de Garéoult",
                                    dossier_cache=None, statistiques_cache=False, serveur_osrm=SERVEUR_OSRM,
                                    goudron_en_ligne=False, marge_goudron=MARGE_GOUDRON,
                                    angle_goudron=ANGLE_GOUDRON, serveur_overpass=SERVEUR_OVERPASS,
                                    langue=None):
    """Produit le KML et son tableau HTML, à partir des mêmes statistiques GPX."""
    # Import local et pas en tête de fichier : sous Windows chaque worker du
    # ProcessPoolExecutor ré-importe le module (spawn), or seul le processus
    # principal se sert du géocodeur (scipy derrière, import coûteux).
    import reverse_geocoder as rg

    fichiers_gpx = sorted(str(fichier) for fichier in Path(dossier_entree).iterdir()
                          if fichier.is_file() and fichier.suffix.lower() == '.gpx')
    if not fichiers_gpx:
        print("Erreur : Aucun fichier GPX trouvé.")
        return

    dossier_cache = Path(dossier_cache or Path(dossier_entree) / DOSSIER_CACHE)
    dossier_cache.mkdir(parents=True, exist_ok=True)
    options = {
        "dossier_cache": str(dossier_cache),
        "cache_source": str(Path(dossier_entree) / DOSSIER_CACHE) if statistiques_cache else None,
        "statistiques_cache": statistiques_cache,
        "altitudes_en_ligne": not statistiques_cache,
    }
    taches = [(f, tolerance_m, options) for f in fichiers_gpx]

    # Limite les appels réseau simultanés et la mémoire des lecteurs raster.
    with concurrent.futures.ProcessPoolExecutor(max_workers=min(4, os.cpu_count() or 1)) as executeur:
        resultats = list(tqdm(
                    executeur.map(extraire_et_reduire, taches, chunksize=1),
            total=len(taches),
            desc="Parsing GPX & simplification",
            ncols=100
        ))

    print("\nIdentification des villes...")
    coords_a_chercher = []
    indices_a_chercher = []

    for i, res in enumerate(resultats):
        if 'erreur' not in res and 'ville' not in res:
            coords_a_chercher.append(res['lat_lon_depart'])
            indices_a_chercher.append(i)

    if coords_a_chercher:
        villes_trouvees = rg.search(coords_a_chercher, verbose=False)
        for index, geo in zip(indices_a_chercher, villes_trouvees):
            resultats[index]['ville'] = geo['name']

    print("Mesure des portions longées près du goudron OSM...")
    with tqdm(total=len(resultats), desc="Goudron OSM / cache", ncols=100) as barre:
        bilan_goudron = ajouter_goudron_osm(
            resultats, dossier_cache=dossier_cache, en_ligne=goudron_en_ligne,
            marge=marge_goudron, angle=angle_goudron, tolerance_geometrie=tolerance_m,
            serveur=serveur_overpass, progression=barre.update,
        )
    print(f"Goudron : {bilan_goudron['cache']} traces depuis le cache, "
          f"{bilan_goudron['calcules']} calculées, {bilan_goudron['appels']} requêtes par lots, "
          f"{bilan_goudron['erreurs']} non calculées.")
    if bilan_goudron["erreur_cache"]:
        print("Cache goudron non enregistré : " + bilan_goudron["erreur_cache"])

    for res in resultats:
        if 'erreur' not in res:
            try:
                atomic_write(res['chemin_cache'], json.dumps(res, ensure_ascii=False).encode('utf-8'))
            except OSError as exc:
                print(f"[{res['nom']}] Cache non enregistré : {exc}")

    print("Compilation du fichier KML...")
    kml = simplekml.Kml()
    traces_ajoutees = 0

    for res in resultats:
        if 'erreur' in res:
            print(f"[{res['nom']}] {res['erreur']}")
            continue

        nom_sans_heure = nettoyer_heure_du_nom(res['nom'])
        denivele = res.get('denivele_pos')
        denivele_str = f"{denivele}m" if denivele is not None else "?"
        duree_str = formater_duree(res.get('duree_s'))
        distance_str = formater_distance(res.get('distance_m'))
        ville = res.get('ville', '?')
        nom_complet = f"{nom_sans_heure}_{ville}_{distance_str}_D+{denivele_str}_{duree_str}"

        # Une LineString par segment GPX, regroupées dans une MultiGeometry :
        # évite le trait droit parasite entre segments (pause d'enregistrement).
        trace = kml.newmultigeometry(name=nom_complet)
        for cle in ('modele', 'protocole', 'denivele_exact', 'gpx_somme_brute',
                    'gpx_filtre', 'replis', 'erreur_modeles', 'distance_goudron_m',
                    'goudron_incertain_m', 'goudron_marge_m', 'goudron_angle_deg'):
            trace.extendeddata.newdata(cle, json.dumps(res.get(cle), ensure_ascii=False))
        for segment in res['segments']:
            trace.newlinestring(coords=segment)
        trace.style.linestyle.color = couleur_stable(res['nom'])
        trace.style.linestyle.width = epaisseur
        traces_ajoutees += 1

    sources = Counter(res['modele'] for res in resultats if 'erreur' not in res)
    print("D+ estimé (5 m / sigma 20 m / hystérésis 2 m) : " +
          ', '.join(f"{modele} : {nombre}" for modele, nombre in sources.items()))

    kml_enregistre = False
    try:
        kml.save(fichier_sortie)
        kml_enregistre = True
        print(f"\nSuccès. {traces_ajoutees}/{len(fichiers_gpx)} traces intégrées dans : {fichier_sortie}")
    except Exception as e:
        print(f"Erreur KML : {e}")

    print("Trajets OSRM depuis " + libelle_origine + "...")
    with tqdm(total=len(resultats), desc="Trajets OSRM / cache", ncols=100) as barre:
        bilan_routes = ajouter_trajets_osrm(
            resultats, origine=origine_route, serveur=serveur_osrm,
            fichier_cache=dossier_cache / "trajets_osrm_v1.json",
            en_ligne=routes_en_ligne, progression=barre.update,
        )
    print(f"OSRM : {bilan_routes['traces_cache']} traces depuis le cache, "
          f"{bilan_routes['appels']} requêtes par lots.")
    if bilan_routes["erreur_cache"]:
        print("Cache routier non enregistré : " + bilan_routes["erreur_cache"])
    fichier_html = fichier_html or str(Path(fichier_sortie).with_suffix(".html"))
    try:
        generer_tableau_bord(resultats, fichier_html, libelle_origine=libelle_origine,
                             origine_route=origine_route, serveur_osrm=serveur_osrm,
                             marge_goudron=marge_goudron, angle_goudron=angle_goudron, langue=langue,
                             fichier_kml=fichier_sortie if kml_enregistre else None)
        print(f"Tableau de bord HTML : {fichier_html} ({len(resultats)} traces)")
    except OSError as e:
        print(f"Erreur HTML : {e}")
    erreurs_routes = Counter(res['erreur_route'] for res in resultats if res.get('erreur_route'))
    for erreur, nombre in erreurs_routes.items():
        print(f"Trajets ({nombre}) : {erreur}")
    return resultats

def main():
    parser = argparse.ArgumentParser(description="Combine GPX tracks into a KML and a standalone bilingual HTML dashboard.")
    base = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    sibling = base.parent / "gpx"
    parser.add_argument("folder", nargs="?", default=str(sibling) if sibling.is_dir() else ".",
                        help="GPX folder (default: sibling gpx folder, otherwise current directory).")
    parser.add_argument("--version", action="version", version=f"gpx2dash {VERSION}")
    parser.add_argument("--cache", default=str((Path.cwd() if getattr(sys, "frozen", False) else base) / DOSSIER_CACHE),
                        help="Working cache folder.")
    parser.add_argument("--from-cache", action="store_true",
                        help="Reuse verified statistics; use local elevation data or filtered GPX if absent. No elevation downloads.")
    parser.add_argument("--kml", help="Output KML file.")
    parser.add_argument("--html", help="Output HTML dashboard file.")
    parser.add_argument("--no-routing", action="store_true", help="Use the routing cache only; no OSRM requests from Python.")
    parser.add_argument("--osrm-server", default=SERVEUR_OSRM, help="OSRM driving server URL.")
    parser.add_argument("--asphalt", action="store_true", help="Download nearby OSM roads to measure asphalt alongside tracks; otherwise use cache only.")
    parser.add_argument("--asphalt-tolerance", type=float, default=MARGE_GOUDRON, metavar="METRES",
                        help="Maximum distance to the OSM road axis (1-50 m, default: 15).")
    parser.add_argument("--asphalt-angle", type=float, default=ANGLE_GOUDRON, metavar="DEGREES",
                        help="Maximum direction difference, either direction (1-60 degrees, default: 30).")
    parser.add_argument("--overpass-server", default=SERVEUR_OVERPASS, help="Overpass API URL for road surfaces.")
    parser.add_argument("--origin-city", help="Find the initial driving origin with Photon.")
    parser.add_argument("--origin", nargs=2, type=float, metavar=("LAT", "LON"), default=DEPART_GAREOULT,
                        help="Driving origin (default: Gareoult town hall).")
    parser.add_argument("--origin-name", default="Mairie de Garéoult", help="Driving origin label.")
    parser.add_argument("--tolerance", type=float, default=10, help="KML/map simplification in metres (default: 10).")
    parser.add_argument("--line-width", type=float, default=5, help="KML line width (default: 5).")
    parser.add_argument("--language", choices=("en", "fr"), help="Initial dashboard language (default: browser language).")
    # Hidden aliases keep existing commands working, without duplicating the English help.
    for old, dest, kw in [
        ("--depuis-cache", "from_cache", {"action": "store_true"}),
        ("--sans-routage", "no_routing", {"action": "store_true"}),
        ("--sans-maps", "no_routing", {"action": "store_true"}),
        ("--serveur-osrm", "osrm_server", {}),
        ("--goudron", "asphalt", {"action": "store_true"}),
        ("--marge-goudron", "asphalt_tolerance", {"type": float}),
        ("--angle-goudron", "asphalt_angle", {"type": float}),
        ("--serveur-overpass", "overpass_server", {}),
        ("--ville-depart", "origin_city", {}),
        ("--origine", "origin", {"nargs": 2, "type": float}),
        ("--nom-origine", "origin_name", {}),
        ("--epaisseur", "line_width", {"type": float}),
    ]:
        parser.add_argument(old, dest=dest, help=argparse.SUPPRESS, default=argparse.SUPPRESS, **kw)
    args = parser.parse_args()
    if not Path(args.folder).is_dir():
        parser.error("The GPX folder does not exist.")
    try:
        args.origin = coordonnees(args.origin)
        args.osrm_server = serveur_valide(args.osrm_server)
        args.overpass_server = serveur_valide(args.overpass_server)
        parametres_valides(args.asphalt_tolerance, args.asphalt_angle)
        if args.origin_city:
            cities = chercher_villes(args.origin_city)
            if not cities:
                parser.error("No city found. Specify the region or country.")
            args.origin = cities[0]["position"]
            args.origin_name = cities[0]["libelle"]
            print("Driving origin: " + args.origin_name)
    except ValueError as exc:
        parser.error(str(exc))
    if not (0 < args.tolerance < float("inf") and 0 < args.line_width < float("inf")):
        parser.error("Tolerance and line width must be positive and finite.")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    kml = args.kml or f"tracks_{timestamp}.kml"
    html = args.html or f"dashboard_{timestamp}.html"
    if Path(kml).resolve() == Path(html).resolve():
        parser.error("KML and HTML outputs must be different files.")
    Path(kml).resolve().parent.mkdir(parents=True, exist_ok=True)
    fusionner_gpx_vers_kml_parallele(
        args.folder, kml, tolerance_m=args.tolerance, epaisseur=args.line_width,
        fichier_html=html, routes_en_ligne=not args.no_routing,
        origine_route=tuple(args.origin), libelle_origine=args.origin_name,
        dossier_cache=args.cache, statistiques_cache=args.from_cache, serveur_osrm=args.osrm_server,
        goudron_en_ligne=args.asphalt, marge_goudron=args.asphalt_tolerance,
        angle_goudron=args.asphalt_angle, serveur_overpass=args.overpass_server, langue=args.language,
    )


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
