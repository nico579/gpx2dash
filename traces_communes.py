"""Comparaison locale des portions GPX, indépendante du routage et du goudron."""
import hashlib
import json
import math
from pathlib import Path

from goudron_osm import segments_originaux
from trajets_osrm import ecrire_json

MARGE_COMMUNE = 15.0
LONGUEUR_COMMUNE = 100.0
FICHIER_CACHE_COMMUN = "traces_communes_v1.json"
PROTOCOL_COMMUN = "original-utm-continuous-symmetric-v1"


def parametres_valides(marge, longueur):
    if not math.isfinite(marge) or not 1 <= marge <= 100:
        raise ValueError("Overlap tolerance must be between 1 and 100 metres.")
    if not math.isfinite(longueur) or longueur <= 0:
        raise ValueError("Minimum shared length must be positive and finite.")


def _plus_longue_portion(geometrie):
    if geometrie.geom_type in ("LineString", "LinearRing"):
        return geometrie.length
    return max((_plus_longue_portion(g) for g in getattr(geometrie, "geoms", [])), default=0.)


def mesurer_portion_commune(lignes_a, lignes_b, marge=MARGE_COMMUNE, *, voisinages=None):
    """Longueur continue dans les deux traces, en mètres ; jamais de pont entre segments."""
    import shapely

    if voisinages is None:
        voisinages = [shapely.union_all([ligne.buffer(marge, cap_style="flat") for ligne in lignes])
                      for lignes in (lignes_a, lignes_b)]

    def longueur(lignes, voisinage):
        return max((_plus_longue_portion(shapely.line_merge(ligne.intersection(voisinage)))
                    for ligne in lignes), default=0.)

    return min(longueur(lignes_a, voisinages[1]), longueur(lignes_b, voisinages[0]))


def ajouter_traces_communes(resultats, *, dossier_cache, marge=MARGE_COMMUNE,
                           longueur=LONGUEUR_COMMUNE, tolerance_geometrie=10, progression=None):
    """Compte chaque autre fichier une fois ; cache les mesures par contenu et marge."""
    import numpy as np
    import shapely
    from pyproj import Transformer

    parametres_valides(marge, longueur)
    path = Path(dossier_cache) / FICHIER_CACHE_COMMUN
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        manifest = {}
    if (not isinstance(manifest, dict) or manifest.get("protocole") != PROTOCOL_COMMUN
            or not isinstance(manifest.get("paires"), dict)):
        manifest = {"protocole": PROTOCOL_COMMUN, "paires": {}}
    bilan = {"calcules": 0, "cache": 0, "erreurs": 0, "erreur_cache": None}
    valides, cadres, centres = [], [], []
    for trace in resultats:
        trace.pop("nombre_traces_communes", None)
        trace.pop("erreur_traces_communes", None)
        trace["traces_communes"] = []
        trace.update(superposition_marge_m=marge, superposition_min_m=longueur)
        if "erreur" in trace:
            if progression:
                progression(1)
            continue
        try:
            points = np.asarray([p for s in trace.get("segments", []) for p in s], dtype=float)
            if (points.ndim != 2 or points.shape[1] != 2 or len(points) < 2
                    or not np.isfinite(points).all() or (np.abs(points[:, 0]) > 180).any()
                    or (np.abs(points[:, 1]) > 90).any()):
                raise ValueError("Coordonnées GPX absentes ou invalides.")
            cadres.append(shapely.MultiLineString([s for s in trace["segments"] if len(s) >= 2]))
            radians = np.radians(points[:, 0])
            lon = math.degrees(math.atan2(float(np.sin(radians).mean()), float(np.cos(radians).mean())))
            centres.append((lon, float(points[:, 1].mean())))
            valides.append(trace)
        except (TypeError, ValueError, IndexError) as exc:
            trace["erreur_traces_communes"] = str(exc)
            bilan["erreurs"] += 1
            if progression:
                progression(1)
    index = shapely.STRtree(cadres)
    originaux, projections, geometries, relations = {}, {}, {}, [set() for _ in valides]

    def projeter(i, crs):
        trace = valides[i]
        empreinte = trace.get("empreinte_gpx")
        identite = empreinte or trace.get("chemin_gpx")
        if (identite, crs) in geometries:
            return geometries[identite, crs]
        if identite not in originaux:
            brut = Path(trace["chemin_gpx"]).read_bytes()
            if empreinte and hashlib.sha256(brut).hexdigest() != empreinte:
                raise ValueError("Le GPX a changé pendant le calcul ; régénérez le tableau.")
            originaux[identite] = segments_originaux(brut)
        if crs not in projections:
            projections[crs] = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
        lignes = []
        for segment in originaux[identite]:
            points = np.asarray(segment, dtype=float)
            x, y = projections[crs].transform(points[:, 0], points[:, 1])
            xy = np.column_stack([x, y])
            if not np.isfinite(xy).all():
                raise ValueError("Projection des coordonnées GPX impossible.")
            ligne = shapely.LineString(xy)
            if ligne.length > 0:
                lignes.append(ligne)
        voisinage = shapely.union_all([ligne.buffer(marge, cap_style="flat") for ligne in lignes])
        geometries[identite, crs] = (lignes, voisinage)
        return lignes, voisinage

    for i, trace in enumerate(valides):
        lon_min, lat_min, lon_max, lat_max = cadres[i].bounds
        # Les cadres simplifiés servent seulement à sélectionner les candidats.
        # La comparaison précise utilise les points originaux, en mètres.
        pad_lat = (marge + 2 * tolerance_geometrie) / 100000
        pad_lon = pad_lat / max(.001, math.cos(math.radians(max(abs(lat_min), abs(lat_max)))))
        candidats = set()
        for decalage in (-360, 0, 360):
            from shapely.affinity import translate
            zone = translate(cadres[i], xoff=decalage) if decalage else cadres[i]
            candidats.update(int(j) for j in index.query(zone, predicate="dwithin", distance=pad_lon) if j > i)
        for j in sorted(candidats):
            autre = valides[j]
            empreintes = sorted((trace.get("empreinte_gpx") or "", autre.get("empreinte_gpx") or ""))
            cle = "|".join(empreintes) + f"|{marge:g}"
            mesure = manifest["paires"].get(cle) if all(empreintes) else None
            if (isinstance(mesure, (int, float)) and not isinstance(mesure, bool)
                    and math.isfinite(mesure) and mesure >= 0):
                bilan["cache"] += 1
            else:
                try:
                    reference = i if empreintes[0] == trace.get("empreinte_gpx") else j
                    lon, lat = centres[reference]
                    if -80 <= lat <= 84:
                        zone = min(60, max(1, int((lon + 180) / 6) + 1))
                        crs = f"EPSG:{(32600 if lat >= 0 else 32700) + zone}"
                    else:
                        crs = f"+proj=aeqd +lat_0={lat} +lon_0={lon} +datum=WGS84 +units=m"
                    lignes_a, voisinage_a = projeter(i, crs)
                    lignes_b, voisinage_b = projeter(j, crs)
                    mesure = mesurer_portion_commune(lignes_a, lignes_b, marge,
                                                    voisinages=(voisinage_a, voisinage_b))
                    if all(empreintes):
                        manifest["paires"][cle] = mesure
                    bilan["calcules"] += 1
                except (OSError, ValueError, KeyError, TypeError, shapely.GEOSException) as exc:
                    trace["erreur_traces_communes"] = autre["erreur_traces_communes"] = str(exc)
                    bilan["erreurs"] += 1
                    continue
            if mesure >= longueur:
                relations[i].add(j)
                relations[j].add(i)
        if progression:
            progression(1)
    for trace, voisins in zip(valides, relations):
        trace["traces_communes"] = sorted(valides[j]["nom"] for j in voisins)
        if not trace.get("erreur_traces_communes"):
            trace["nombre_traces_communes"] = len(voisins)
    if bilan["calcules"]:
        try:
            ecrire_json(path, manifest)
        except OSError as exc:
            bilan["erreur_cache"] = str(exc)
    return bilan
