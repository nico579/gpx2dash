"""Longueur de trace parallèle au goudron OSM : proximité, direction et cache.

Les surfaces absentes ou ambiguës restent incertaines. Aucun revêtement n'est
déduit de la catégorie de route. Le calcul ne dépend pas de l'origine routière.
"""
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
import math
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from trajets_osrm import USER_AGENT, ecrire_json, serveur_valide

SERVEUR_OVERPASS = "https://overpass-api.de/api/interpreter"
PROTOCOL_GOUDRON = "goudron-osm-v1-5m-direction10m"
MARGE_GOUDRON = 15.0
ANGLE_GOUDRON = 30.0
PAS_M = 5.0
DUREE_CACHE_S = 30 * 86400
SURFACES_GOUDRON = {"asphalt", "chipseal", "tarmac", "bitumen", "tar"}
SURFACES_AUTRES = {
    "unpaved", "compacted", "fine_gravel", "gravel", "pebblestone",
    "ground", "dirt", "earth", "grass", "mud", "sand", "wood", "metal",
    "sett", "cobblestone", "unhewn_cobblestone", "rock", "stone", "clay",
    "snow", "ice", "woodchips", "plastic", "rubber", "artificial_turf",
    "grass_paver", "brick", "bricks", "shells", "concrete", "paving_stones",
}
VOIES_EXCLUES = {"construction", "proposed", "platform", "steps", "elevator", "bus_stop"}
CHAMPS_GOUDRON = (
    "distance_goudron_m", "goudron_incertain_m", "goudron_longueur_m",
    "goudron_marge_m", "goudron_angle_deg", "goudron_pas_m",
    "goudron_date_osm", "goudron_date", "goudron_protocole", "erreur_goudron",
)


def parametres_valides(marge, angle):
    if not math.isfinite(marge) or not 1 <= marge <= 50:
        raise ValueError("La marge goudron doit être comprise entre 1 et 50 mètres.")
    if not math.isfinite(angle) or not 1 <= angle <= 60:
        raise ValueError("L'angle goudron doit être compris entre 1 et 60 degrés.")


def categorie_surface(tags):
    surface = str(tags.get("surface", "")).strip().lower()
    if surface in SURFACES_GOUDRON:
        return 0
    if surface in SURFACES_AUTRES or surface.startswith(("concrete:", "paving_stones:")):
        return 2
    # paved, sealed, mixed et les valeurs inconnues ne prouvent pas du bitume.
    return 1


def segments_originaux(brut):
    import gpxpy
    try:
        texte = brut.decode("utf-8-sig")
    except UnicodeDecodeError:
        texte = brut.decode("latin-1")
    gpx = gpxpy.parse(texte)
    sources = [segment.points for track in gpx.tracks for segment in track.segments]
    sources.extend(route.points for route in gpx.routes)
    segments = []
    for points in sources:
        segment = [[float(p.longitude), float(p.latitude)] for p in points]
        if len(segment) >= 2:
            if not all(math.isfinite(lon) and math.isfinite(lat) and
                       abs(lon) <= 180 and abs(lat) <= 90 for lon, lat in segment):
                raise ValueError("Coordonnées GPX invalides pour le calcul du goudron.")
            segments.append(segment)
    if not segments:
        raise ValueError("Aucun segment GPX utilisable pour le goudron.")
    return segments



class _VoiesOSM:
    """Prépare les limites des voies une fois par document OSM partagé."""

    def __init__(self, voies):
        import numpy as np
        self.voies, cadres = [], []
        for voie in voies:
            points = np.asarray([[p["lon"], p["lat"]] for p in voie["geometry"]], dtype=float)
            if len(points) < 2:
                continue
            self.voies.append(voie)
            cadres.append((points[:, 0].min(), points[:, 1].min(),
                           points[:, 0].max(), points[:, 1].max()))
        self.cadres = np.asarray(cadres, dtype=float).reshape(-1, 4)

    def proches(self, lon_min, lat_min, lon_max, lat_max):
        import numpy as np
        b = self.cadres
        indices = np.flatnonzero((b[:, 2] >= lon_min) & (b[:, 0] <= lon_max) &
                                 (b[:, 3] >= lat_min) & (b[:, 1] <= lat_max))
        return [self.voies[i] for i in indices]

def mesurer_goudron(segments, voies, *, marge=MARGE_GOUDRON, angle=ANGLE_GOUDRON):
    """Distance géodésique réelle, affectée par pas <= 5 m, sans joindre les segments."""
    import numpy as np
    import shapely
    from pyproj import Geod, Transformer
    parametres_valides(marge, angle)
    usable = [np.asarray(segment, dtype=float) for segment in segments if len(segment) >= 2]
    if not usable:
        raise ValueError("Trace vide ou coordonnées invalides.")
    coords = np.concatenate(usable)
    if not len(coords) or not np.isfinite(coords).all():
        raise ValueError("Trace vide ou coordonnées invalides.")
    centre_lat = float(coords[:, 1].mean())
    radians = np.radians(coords[:, 0])
    centre_lon = math.degrees(math.atan2(float(np.sin(radians).mean()), float(np.cos(radians).mean())))
    proj = Transformer.from_crs(
        "EPSG:4326", f"+proj=aeqd +lat_0={centre_lat} +lon_0={centre_lon} +datum=WGS84 +units=m",
        always_xy=True,
    )
    geod = Geod(ellps="WGS84")
    lat_min, lat_max = float(coords[:, 1].min()), float(coords[:, 1].max())
    lon_min, lon_max = float(coords[:, 0].min()), float(coords[:, 0].max())
    pad_lat = (marge + 20) / 110000
    pad_lon = pad_lat / max(.01, math.cos(math.radians(centre_lat)))
    if isinstance(voies, _VoiesOSM):
        voies = voies.proches(lon_min - pad_lon, lat_min - pad_lat,
                              lon_max + pad_lon, lat_max + pad_lat)
    roads, vectors, categories = [], [], []
    for voie in voies:
        tags = voie.get("tags", {})
        if not tags.get("highway") or tags.get("highway") in VOIES_EXCLUES or tags.get("area") == "yes":
            continue
        points = np.asarray([[p["lon"], p["lat"]] for p in voie["geometry"]], dtype=float)
        if len(points) < 2:
            continue
        if (points[:, 1].max() < lat_min - pad_lat or points[:, 1].min() > lat_max + pad_lat or
                points[:, 0].max() < lon_min - pad_lon or points[:, 0].min() > lon_max + pad_lon):
            continue
        xs, ys = proj.transform(points[:, 0], points[:, 1])
        projected = np.column_stack([xs, ys])
        deltas = np.diff(projected, axis=0)
        lengths = np.linalg.norm(deltas, axis=1)
        valid = np.isfinite(lengths) & (lengths > .001)
        if not valid.any():
            continue
        lines = np.stack([projected[:-1][valid], projected[1:][valid]], axis=1)
        roads.extend(shapely.linestrings(lines))
        vectors.extend(deltas[valid] / lengths[valid, None])
        categories.extend([categorie_surface(tags)] * int(valid.sum()))
    tree = shapely.STRtree(roads) if roads else None
    vectors, categories = np.asarray(vectors), np.asarray(categories, dtype=int)
    limite_angle = math.cos(math.radians(angle))
    goudron = incertain = longueur = 0.0
    for segment in segments:
        if len(segment) < 2:
            continue
        points = np.asarray(segment, dtype=float)
        _, _, distances = geod.inv(points[:-1, 0].tolist(), points[:-1, 1].tolist(), points[1:, 0].tolist(), points[1:, 1].tolist())
        distances = np.asarray(distances)
        if not np.isfinite(distances).all():
            raise ValueError("Distance géodésique invalide.")
        abscisse = np.concatenate(([0.], np.cumsum(distances)))
        length = float(abscisse[-1])
        if length <= 0:
            continue
        if length / PAS_M > 2_000_000:
            raise ValueError("Segment trop long pour le calcul du goudron.")
        longueur += length
        if tree is None:
            continue
        xs, ys = proj.transform(points[:, 0], points[:, 1])
        # Les points consécutifs identiques ne doivent pas fausser l'interpolation.
        keep = np.concatenate(([True], np.diff(abscisse) > 0))
        abscisse, xs, ys = abscisse[keep], np.asarray(xs)[keep], np.asarray(ys)[keep]
        bornes = np.minimum(np.arange(0., length + PAS_M, PAS_M), length)
        poids = np.diff(bornes)
        milieu = (bornes[:-1] + bornes[1:]) / 2
        samples = shapely.points(np.interp(milieu, abscisse, xs), np.interp(milieu, abscisse, ys))
        # Direction sur une fenêtre de 20 m, pour atténuer le bruit GPS.
        avant, apres = np.maximum(0, milieu - 10), np.minimum(length, milieu + 10)
        directions = np.column_stack([
            np.interp(apres, abscisse, xs) - np.interp(avant, abscisse, xs),
            np.interp(apres, abscisse, ys) - np.interp(avant, abscisse, ys),
        ])
        normes = np.linalg.norm(directions, axis=1)
        directions /= np.maximum(normes[:, None], .000001)
        on_goudron, on_incertain = np.zeros(len(milieu), dtype=bool), np.zeros(len(milieu), dtype=bool)
        # Le traitement par blocs borne la mémoire dans les zones urbaines denses.
        for debut in range(0, len(milieu), 20000):
            pairs = tree.query(samples[debut:debut + 20000], predicate="dwithin", distance=marge)
            if pairs.shape[1] == 0:
                continue
            si, ri = pairs[0] + debut, pairs[1]
            alignes = np.abs(np.sum(directions[si] * vectors[ri], axis=1)) >= limite_angle
            si, ri = si[alignes], ri[alignes]
            on_goudron[si[categories[ri] == 0]] = True
            on_incertain[si[categories[ri] == 1]] = True
        # Deux voies ou deux chaussées proches ne doublent jamais les kilomètres.
        goudron += float(poids[on_goudron].sum())
        incertain += float(poids[on_incertain & ~on_goudron].sum())
    return {
        "distance_goudron_m": round(goudron, 3), "goudron_incertain_m": round(incertain, 3),
        "goudron_longueur_m": round(longueur, 3), "goudron_marge_m": marge,
        "goudron_angle_deg": angle, "goudron_pas_m": PAS_M, "goudron_protocole": PROTOCOL_GOUDRON,
    }


def _recent(record):
    try:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(record["goudron_date"])).total_seconds()
        return 0 <= age < DUREE_CACHE_S
    except (ValueError, TypeError, KeyError, AttributeError):
        return False


def _lire_json(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _valider_voies(data):
    if data.get("remark") or not isinstance(data.get("elements"), list):
        raise ValueError("Overpass : réponse incomplète ; calcul du goudron non effectué.")
    for voie in data["elements"]:
        if not isinstance(voie, dict):
            raise ValueError("Overpass : élément invalide.")
        if voie.get("type") != "way":
            continue
        if not isinstance(voie.get("tags"), dict) or not isinstance(voie.get("geometry"), list):
            raise ValueError("Overpass : géométrie de voie manquante.")
        for p in voie["geometry"]:
            if not isinstance(p, dict) or any(not isinstance(p.get(k), (int, float)) or
                    not math.isfinite(p[k]) or abs(p[k]) > bound for k, bound in (("lat", 90), ("lon", 180))):
                raise ValueError("Overpass : coordonnées invalides.")
    return [v for v in data["elements"] if v.get("type") == "way"]


class ClientOverpass:
    def __init__(self, serveur=SERVEUR_OVERPASS):
        self.serveur = serveur_valide(serveur)
        self.dernier_appel = None
        self.appels = 0

    def telecharger(self, query):
        request = Request(self.serveur, data=urlencode({"data": query}).encode("utf-8"),
                          headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        for tentative in range(4):
            if self.dernier_appel is not None:
                time.sleep(max(0., 3.0 - (time.monotonic() - self.dernier_appel)))
            self.appels += 1
            attente = None
            try:
                with urlopen(request, timeout=55) as response:
                    raw = response.read(32 * 1024 * 1024 + 1)
                if len(raw) > 32 * 1024 * 1024:
                    raise ValueError("Overpass : réponse trop volumineuse.")
                data = json.loads(raw)
                _valider_voies(data)
                return data
            except HTTPError as exc:
                erreur = f"Overpass indisponible (HTTP {exc.code}). Relancez avec --asphalt pour reprendre."
                if exc.code in (429, 502, 503, 504) and tentative < 3:
                    attente = 30 * (2 ** tentative) if exc.code == 429 else 10 * (2 ** tentative)
                    retry_after = exc.headers.get("Retry-After") if exc.headers else None
                    if retry_after:
                        try:
                            attente = max(attente, float(retry_after))
                        except ValueError:
                            try:
                                date_retry = parsedate_to_datetime(retry_after)
                                attente = max(attente, (date_retry - datetime.now(timezone.utc)).total_seconds())
                            except (ValueError, TypeError, OverflowError):
                                pass
                    if not math.isfinite(attente) or attente > 600:
                        attente = None
                if attente is None:
                    raise ValueError(erreur) from exc
            except (URLError, OSError) as exc:
                erreur = "Overpass : réseau indisponible ou délai dépassé. Relancez avec --asphalt."
                if tentative >= 1:
                    raise ValueError(erreur) from exc
                attente = 10
            except (json.JSONDecodeError, AttributeError, TypeError) as exc:
                raise ValueError("Overpass : réponse illisible.") from exc
            finally:
                self.dernier_appel = time.monotonic()
            print(f"Overpass temporairement indisponible : reprise dans {attente:.0f} s.", flush=True)
            time.sleep(attente)


def _requete(lot, rayon):
    # Des cercles locaux évitent de tester des milliers de sommets côté Overpass.
    # Chaque portion est couverte intégralement, y compris les voies qui la
    # traversent sans avoir de nœud OSM à l'intérieur de sa boîte englobante.
    from pyproj import Geod
    geod = Geod(ellps="WGS84")
    circles = set()
    for trace in lot:
        pending = [segment for segment in trace.get("segments", []) if len(segment) >= 2]
        while pending:
            part = pending.pop()
            lons, lats = zip(*part)
            centre_lat = (min(lats) + max(lats)) / 2
            centre_lon = math.degrees(math.atan2(sum(math.sin(math.radians(v)) for v in lons),
                                                sum(math.cos(math.radians(v)) for v in lons)))
            _, _, distances = geod.inv([centre_lon] * len(part), [centre_lat] * len(part), list(lons), list(lats))
            radius = int(math.ceil(max(distances) + rayon + 1))
            if radius > 5000:
                if len(part) == 2:
                    midpoint = list(geod.npts(*part[0], *part[1], 1)[0])
                    pending.extend([[part[0], midpoint], [midpoint, part[1]]])
                else:
                    middle = len(part) // 2
                    pending.extend([part[:middle + 1], part[middle:]])
            else:
                circles.add((round(centre_lat, 6), round(centre_lon, 6), radius))
    if not circles:
        raise ValueError("Géométrie de recherche du goudron absente.")
    clauses = [
        f'way["highway"]["area"!="yes"](around:{radius},{lat:.6f},{lon:.6f});'
        for lat, lon, radius in sorted(circles)
    ]
    return '[out:json][timeout:40][maxsize:67108864];(' + "".join(clauses) + ");out geom;"


def ajouter_goudron_osm(resultats, *, dossier_cache, en_ligne=False, marge=MARGE_GOUDRON,
                        angle=ANGLE_GOUDRON, tolerance_geometrie=10, serveur=SERVEUR_OVERPASS,
                        progression=None):
    """Les succès sont conservés par empreinte GPX, paramètres, serveur et protocole."""
    parametres_valides(marge, angle)
    serveur = serveur_valide(serveur)
    dossier = Path(dossier_cache)
    dossier.mkdir(parents=True, exist_ok=True)
    manifest_path = dossier / "goudron_osm_v1.json"
    manifest = _lire_json(manifest_path)
    if manifest.get("version") != 1:
        manifest = {"version": 1, "mesures": {}, "sources": {}}
    for name in ("mesures", "sources"):
        if not isinstance(manifest.get(name), dict):
            manifest[name] = {}
    client = ClientOverpass(serveur)
    bilan = {"calcules": 0, "cache": 0, "appels": 0, "erreurs": 0, "erreur_cache": None}
    documents = {}
    missing = []

    def finir(trace, mesure):
        for champ in CHAMPS_GOUDRON:
            trace.pop(champ, None)
        trace.update(mesure)
        if progression:
            progression(1)

    def enregistrer():
        try:
            ecrire_json(manifest_path, manifest)
        except OSError as exc:
            bilan["erreur_cache"] = str(exc)

    def calculer(trace, source_key, mesure_key, snapshot):
        document = documents.get(snapshot["fichier"])
        if document is None:
            data = _lire_json(dossier / "goudron_osm" / snapshot["fichier"])
            document = (data, _VoiesOSM(_valider_voies(data)))
            documents[snapshot["fichier"]] = document
        data, voies = document
        brut = Path(trace["chemin_gpx"]).read_bytes()
        if hashlib.sha256(brut).hexdigest() != trace["empreinte_gpx"]:
            raise ValueError("Le GPX a changé pendant le calcul ; régénérez le tableau.")
        mesure = mesurer_goudron(segments_originaux(brut), voies, marge=marge, angle=angle)
        mesure.update(goudron_date_osm=data.get("osm3s", {}).get("timestamp_osm_base"),
                      goudron_date=snapshot["goudron_date"])
        manifest["mesures"][mesure_key] = mesure
        manifest["sources"][source_key] = snapshot
        bilan["calcules"] += 1
        finir(trace, mesure)

    for trace in resultats:
        if "erreur" in trace:
            if progression:
                progression(1)
            continue
        fingerprint = trace.get("empreinte_gpx")
        if not fingerprint or not trace.get("chemin_gpx"):
            bilan["erreurs"] += 1
            finir(trace, {"erreur_goudron": "GPX original ou empreinte absente ; goudron non calculé."})
            continue
        source_key = serveur + "|" + fingerprint
        mesure_key = source_key + f"|{marge:g}|{angle:g}|{PROTOCOL_GOUDRON}"
        mesure = manifest["mesures"].get(mesure_key, {})
        champs = ("distance_goudron_m", "goudron_incertain_m", "goudron_longueur_m")
        if (_recent(mesure) and isinstance(mesure, dict) and
                all(isinstance(mesure.get(c), (int, float)) and not isinstance(mesure[c], bool)
                    and math.isfinite(mesure[c]) and mesure[c] >= 0 for c in champs)):
            bilan["cache"] += 1
            finir(trace, {c: mesure[c] for c in CHAMPS_GOUDRON if c in mesure})
            continue
        snapshot = manifest["sources"].get(source_key, {})
        fichier = snapshot.get("fichier", "") if isinstance(snapshot, dict) else ""
        # Des noms de fichiers générés, jamais des chemins arbitraires du manifeste.
        safe_name = isinstance(fichier, str) and len(fichier) == 69 and fichier.endswith(".json") and all(c in "0123456789abcdef" for c in fichier[:64])
        if (_recent(snapshot) and safe_name and isinstance(snapshot.get("rayon"), (int, float)) and
                isinstance(snapshot.get("tolerance_geometrie"), (int, float)) and
                snapshot["rayon"] >= marge + snapshot["tolerance_geometrie"] + 5 and
                (dossier / "goudron_osm" / fichier).is_file()):
            try:
                calculer(trace, source_key, mesure_key, snapshot)
                continue
            except (ValueError, OSError, KeyError, TypeError):
                # Un document corrompu est rechargé, jamais interprété comme zéro.
                pass
        if en_ligne:
            missing.append((trace, source_key, mesure_key))
        else:
            bilan["erreurs"] += 1
            finir(trace, {"erreur_goudron": "Goudron non calculé : lancer gpx2dash.py avec --asphalt (Internet requis)."})
    # Regrouper les traces proches limite les doublons de voies dans les réponses.
    missing.sort(key=lambda item: tuple(round(v, 1) for v in item[0]["lat_lon_depart"]))
    lots, lot, count = [], [], 0
    for item in missing:
        size = sum(len(s) for s in item[0].get("segments", []))
        if lot and (len(lot) >= 20 or count + size > 3500):
            lots.append(lot)
            lot, count = [], 0
        lot.append(item)
        count += size
    if lot:
        lots.append(lot)
    erreur_service = None
    rayon = int(math.ceil((50 + tolerance_geometrie + 5) / 100) * 100)
    for lot in lots:
        try:
            if erreur_service:
                raise ValueError(erreur_service)
            query = _requete([item[0] for item in lot], rayon)
            digest = hashlib.sha256((serveur + "|" + query).encode("utf-8")).hexdigest()
            fichier = digest + ".json"
            path = dossier / "goudron_osm" / fichier
            snapshot = {"fichier": fichier, "rayon": rayon, "tolerance_geometrie": tolerance_geometrie,
                        "goudron_date": datetime.now(timezone.utc).isoformat()}
            data = client.telecharger(query)
            ecrire_json(path, data)
            documents[fichier] = (data, _VoiesOSM(_valider_voies(data)))
        except (ValueError, OSError) as exc:
            erreur_service = str(exc)
            for trace, _, _ in lot:
                bilan["erreurs"] += 1
                finir(trace, {"erreur_goudron": erreur_service})
            continue
        for trace, source_key, mesure_key in lot:
            try:
                calculer(trace, source_key, mesure_key, snapshot)
            except (ValueError, OSError, KeyError, TypeError) as exc:
                bilan["erreurs"] += 1
                finir(trace, {"erreur_goudron": str(exc)})
        enregistrer()
        # Les documents sont lus par lot pour ne pas garder toutes les régions en RAM.
        documents.clear()
    enregistrer()
    bilan["appels"] = client.appels
    return bilan
