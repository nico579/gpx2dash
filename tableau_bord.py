"""Construction d'un tableau HTML autonome, avec recherche, tri et filtres combinés."""
from datetime import date, datetime
from html import escape
import json
import math
import os
from pathlib import Path
import re
from urllib.parse import quote

from couleurs_traces import couleur_html
from goudron_osm import MARGE_GOUDRON, ANGLE_GOUDRON
from trajets_osrm import DEPART_GAREOULT, SERVEUR_OSRM, GEOCODEUR, CHAMPS_ROUTE, cle_trajet, coordonnees
from traces_communes import MARGE_COMMUNE, LONGUEUR_COMMUNE


def extraire_date(gpx, nom_trace):
    """Premier point horodaté (heure locale), puis métadonnées, puis nom du fichier."""
    points = (point for track in gpx.tracks for segment in track.segments for point in segment.points)
    for point in points:
        if point.time is not None:
            instant = point.time
            return (instant.astimezone() if instant.tzinfo is not None else instant).date().isoformat()
    for route in gpx.routes:
        for point in route.points:
            if point.time is not None:
                instant = point.time
                return (instant.astimezone() if instant.tzinfo is not None else instant).date().isoformat()
    if gpx.time is not None:
        instant = gpx.time
        return (instant.astimezone() if instant.tzinfo is not None else instant).date().isoformat()
    return date_du_nom(nom_trace)


def date_du_nom(nom):
    for correspondance in re.finditer(r"(?<!\d)(\d{4})[-_]?(\d{2})[-_]?(\d{2})(?!\d)", nom):
        try:
            return date(*map(int, correspondance.groups())).isoformat()
        except ValueError:
            continue
    return None


def _nombre(valeur):
    if isinstance(valeur, bool) or valeur is None:
        return None
    try:
        nombre = float(valeur)
        return nombre if math.isfinite(nombre) and nombre >= 0 else None
    except (TypeError, ValueError):
        return None


def _distance(valeur):
    nombre = _nombre(valeur)
    return "—" if nombre is None else f"{nombre / 1000:.1f}".replace(".", ",") + " km"


def _duree(valeur):
    nombre = _nombre(valeur)
    if nombre is None:
        return "—"
    heures, minutes = divmod(int(nombre / 60 + .5), 60)
    return f"{heures} h {minutes:02d}" if heures else f"{minutes} min"


def _cellule(valeur, contenu, classe="numeric", titre="", *, unite_filtre=None):
    valeur_tri = "" if valeur is None else str(valeur)
    # Comparer la valeur affichée, en conservant la précision originale pour le tri.
    valeur_filtre = valeur_tri
    if valeur is not None:
        if unite_filtre == "km":
            valeur_filtre = f"{valeur / 1000:.1f}"
        elif unite_filtre == "min":
            valeur_filtre = str(int(valeur / 60 + .5))
        elif unite_filtre == "m":
            valeur_filtre = f"{valeur:.0f}"
    return (f'<td class="{classe}" data-sort="{escape(valeur_tri, quote=True)}"'
            f' data-filter="{escape(valeur_filtre, quote=True)}"'
            f' title="{escape(titre, quote=True)}">{contenu}</td>')



def _cellule_goudron(resultat):
    distance = _nombre(resultat.get("distance_goudron_m"))
    incertain = _nombre(resultat.get("goudron_incertain_m")) or 0
    contenu = _distance(distance)
    titre = resultat.get("erreur_goudron") or (
        f"Voies OSM bitumineuses longées à {resultat.get('goudron_marge_m', MARGE_GOUDRON):g} m maximum ; "
        f"écart de direction ≤ {resultat.get('goudron_angle_deg', ANGLE_GOUDRON):g}°. "
        "Asphalt, chipseal, tarmac, bitumen ou tar ; aucune déduction à partir du type de route."
    )
    if incertain:
        # Zéro confirmé avec un revêtement incertain ne signifie pas zéro goudron.
        if distance == 0:
            distance, contenu = None, "—"
        elif distance is not None:
            contenu = "≥ " + contenu
        contenu += f'<span class="detail">{_distance(incertain)} incertains</span>'
        titre += " Revêtement absent ou ambigu sur les kilomètres incertains. Le filtre porte sur le minimum repéré."
    if resultat.get("goudron_date_osm"):
        titre += " Données OSM du " + str(resultat["goudron_date_osm"]) + "."
    return _cellule(distance, contenu, "numeric goudron", titre=titre, unite_filtre="km").replace(
        '<td ', f'<td data-osm-date="{escape(str(resultat.get("goudron_date_osm") or ""), quote=True)}"'
        f' data-error="{escape(str(resultat.get("erreur_goudron") or ""), quote=True)}" ', 1)


def _lien_fichier(chemin, dossier_sortie):
    try:
        relatif = os.path.relpath(Path(chemin).resolve(), dossier_sortie)
        return quote(relatif.replace("\\", "/"), safe="/")
    except ValueError:
        return Path(chemin).resolve().as_uri()


def _cellule_traces_communes(resultat):
    nombre = _nombre(resultat.get("nombre_traces_communes"))
    erreur = resultat.get("erreur_traces_communes") or ("Comparaison non calculée." if nombre is None else "")
    contenu = "—" if nombre is None else str(int(nombre))
    if nombre and resultat.get("traces_communes") and resultat.get("segments"):
        contenu = (f'<button type="button" class="shared-tracks-link" aria-haspopup="dialog"'
                   f' aria-controls="map-dialog" aria-label="Afficher la trace et ses traces communes"'
                   f' data-i18n-aria-label="Afficher la trace et ses traces communes">{contenu}</button>')
    titre = erreur or (f"Autres traces partageant au moins {resultat.get('superposition_min_m', LONGUEUR_COMMUNE):g} m "
                      f"continus, à {resultat.get('superposition_marge_m', MARGE_COMMUNE):g} m maximum. "
                      "La trace elle-même n'est pas comptée. Cliquer pour afficher les parcours communs.")
    return _cellule(nombre, contenu, "numeric shared-tracks", titre=titre).replace(
        '<td ', f'<td data-error="{escape(str(erreur), quote=True)}" ', 1)


def _segments_carte(resultat):
    """Coordonnées lon/lat, sans relier les interruptions du GPX."""
    segments = []
    for segment in resultat.get("segments", []):
        try:
            points = [[round(float(lon), 6), round(float(lat), 6)] for lon, lat in segment]
            if len(points) >= 2 and all(math.isfinite(lon) and math.isfinite(lat)
                                       and abs(lon) <= 180 and abs(lat) <= 90 for lon, lat in points):
                segments.append(points)
        except (TypeError, ValueError):
            continue
    return segments


def generer_tableau_bord(resultats, fichier_sortie, *, libelle_origine="Mairie de Garéoult",
                         origine_route=DEPART_GAREOULT, serveur_osrm=SERVEUR_OSRM,
                         marge_goudron=MARGE_GOUDRON, angle_goudron=ANGLE_GOUDRON, langue=None,
                         fichier_kml=None, marge_commune=MARGE_COMMUNE,
                         longueur_commune=LONGUEUR_COMMUNE):
    """Une ligne par fichier ; recherche, tri et filtres locaux, routage sur demande."""
    if langue not in (None, "en", "fr"):
        raise ValueError("Language must be en or fr.")
    sortie = Path(fichier_sortie).resolve()
    lignes = []
    valides = [res for res in resultats if "erreur" not in res]
    tries = sorted(resultats, key=lambda res: (res.get("date") or date_du_nom(res.get("nom", "")) or "",
                                               res.get("nom", "")), reverse=True)
    for res in tries:
        nom = str(res.get("nom", "Trace"))
        jour = res.get("date") or date_du_nom(nom)
        try:
            date_affichee = date.fromisoformat(jour).strftime("%d/%m/%Y") if jour else "Date inconnue"
        except (TypeError, ValueError):
            jour, date_affichee = None, "Date inconnue"
        nom_affiche = escape(nom)
        if res.get("chemin_gpx"):
            lien = _lien_fichier(res["chemin_gpx"], sortie.parent)
            nom_affiche = f'<a href="{escape(lien, quote=True)}" download>{nom_affiche}</a>'
        contenu_date = f'<span class="date">{date_affichee}</span><span class="trace-name">{nom_affiche}</span>'
        ville = str(res.get("ville") or "Lieu inconnu")
        titre_lieu = str(res.get("erreur") or "")
        if "erreur" in res:
            lieu = f'<span class="error" data-row-i18n="Trace illisible">Trace illisible</span><span class="detail">{escape(str(res["erreur"]))}</span>'
        else:
            lieu = escape(ville) if res.get("ville") else '<span data-row-i18n="Lieu inconnu">Lieu inconnu</span>'
            if res.get("lat_lon_depart"):
                latitude, longitude = res["lat_lon_depart"]
                titre_lieu = f"{latitude:.5f}, {longitude:.5f}"
                lieu += f'<span class="detail">{latitude:.5f}, {longitude:.5f}</span>'
            if res.get("itineraire_url"):
                carte = bool(_segments_carte(res))
                attributs_carte = ' aria-haspopup="dialog" aria-controls="map-dialog"' if carte else ""
                libelle_lien = "Itinéraire et trace GPX" if carte else "Itinéraire OpenStreetMap ↗"
                lieu += (f'<a class="route-link"{attributs_carte} href="{escape(res["itineraire_url"], quote=True)}"'
                         f' target="_blank" rel="noopener noreferrer" data-row-i18n="{libelle_lien}">{libelle_lien}</a>')
        plus, moins = _nombre(res.get("denivele_pos")), _nombre(res.get("denivele_neg"))
        denivele = "—" if plus is None else f'+{plus:,.0f} m'.replace(",", " ")
        if moins is not None:
            denivele += f'<span class="detail">−{moins:,.0f} m</span>'.replace(",", " ")
        titre_route = res.get("erreur_route", "")
        if res.get("date_route") and not titre_route:
            titre_route = f'OSRM, relevé le {res["date_route"]}. Sans trafic en temps réel.'
        cellules = [
            _cellule(jour, contenu_date, "trace", titre=nom),
            _cellule(ville if res.get("ville") and "erreur" not in res else None, lieu, "place", titre=titre_lieu),
            _cellule(_nombre(res.get("distance_m")), _distance(res.get("distance_m")), unite_filtre="km"),
            _cellule(plus, denivele, titre=str(res.get("modele") or "Dénivelé inconnu"), unite_filtre="m"),
            _cellule(_nombre(res.get("duree_s")), _duree(res.get("duree_s")), unite_filtre="min"),
            _cellule(_nombre(res.get("distance_route_m")), _distance(res.get("distance_route_m")), titre=titre_route, unite_filtre="km"),
            _cellule(_nombre(res.get("duree_route_s")), _duree(res.get("duree_route_s")), titre=titre_route, unite_filtre="min"),
            _cellule_goudron(res),
            _cellule_traces_communes(res),
        ]
        lignes.append(f'<tr data-id="{escape(nom, quote=True)}"'
                      f' data-uncertain="{_nombre(res.get("goudron_incertain_m")) or 0}">' + "".join(cellules) + '</tr>')
    routes_connues = sum(_nombre(res.get("distance_route_m")) is not None
                        and _nombre(res.get("duree_route_s")) is not None for res in valides)
    erreurs = len(resultats) - len(valides)
    note = ("Trajets aller en voiture calculés par OSRM, sans trafic en temps réel, "
            "jusqu’à la route accessible la plus proche du départ. L’approche à pied n’est pas incluse.")
    manquants = len(valides) - routes_connues
    if manquants:
        note += f" {manquants} trajet(s) non renseigné(s) ; la raison apparaît au survol des cellules."
    if erreurs:
        note += f" {erreurs} fichier(s) GPX illisible(s), signalé(s) dans le tableau."
    total_distance = sum(_nombre(res.get("distance_m")) or 0 for res in valides)
    total_denivele = sum(_nombre(res.get("denivele_pos")) or 0 for res in valides)
    traces, cache = [], {}
    for res in valides:
        try:
            position = coordonnees(res["lat_lon_depart"])
        except (KeyError, TypeError, ValueError):
            continue
        nom = str(res.get("nom", "Trace"))
        traces.append({"id": nom, "position": position, "segments": _segments_carte(res),
                       "color": couleur_html(nom), "sharedIds": res.get("traces_communes", [])})
        if res.get("date_route"):
            cache[cle_trajet(position, origine_route, serveur_osrm)] = {
                cle: res[cle] for cle in CHAMPS_ROUTE if cle in res
            }
    donnees = json.dumps({
        "language": langue, "asphaltTolerance": marge_goudron, "asphaltAngle": angle_goudron,
        "overlapTolerance": marge_commune, "overlapMinLength": longueur_commune,
        "kml": _lien_fichier(fichier_kml, sortie.parent) if fichier_kml else None,
        "totalDistance": total_distance, "totalAscent": total_denivele, "errors": erreurs,
        "generated": datetime.now().astimezone().isoformat(),
        "origine": {"libelle": libelle_origine, "position": coordonnees(origine_route)},
        "serveur": serveur_osrm.rstrip("/"), "geocodeur": GEOCODEUR,
        "traces": traces, "cache": cache, "nombre_valides": len(valides),
    }, ensure_ascii=False, allow_nan=False, separators=(",", ":")).replace("<", "\\u003c")
    template = Path(__file__).with_name("tableau_bord_template.html").read_text(encoding="utf-8")
    ressources = Path(__file__).parent
    leaflet = ressources / "assets" / "leaflet-1.9.4"
    bibliotheque = re.sub(r"//# sourceMappingURL=.*", "", (leaflet / "leaflet.js").read_text(encoding="utf-8"))
    bibliotheque = "/*\n" + (leaflet / "LICENSE").read_text(encoding="utf-8") + "\n*/\n" + bibliotheque
    valeurs = {
        "MARGEGOUDRON": f"{marge_goudron:g}",
        "ANGLEGOUDRON": f"{angle_goudron:g}",
        "MARGECOMMUNE": f"{marge_commune:g}",
        "LONGUEURCOMMUNE": f"{longueur_commune:g}",
        "ORIGINE": escape(libelle_origine),
        "VILLE": escape("Garéoult" if libelle_origine == "Mairie de Garéoult" else libelle_origine, quote=True),
        "DONNEES": donnees,
        "LEAFLETSTYLE": (leaflet / "leaflet.css").read_text(encoding="utf-8"),
        "SCRIPT": "\n".join([bibliotheque,
                             (ressources / "dashboard_i18n.js").read_text(encoding="utf-8"),
                             (ressources / "carte_trace.js").read_text(encoding="utf-8"),
                             (ressources / "tableau_bord.js").read_text(encoding="utf-8")]),
        "GENERATION": datetime.now().strftime("%d/%m/%Y à %H:%M"),
        "NOMBRE": str(len(resultats)),
        "DISTANCE": _distance(total_distance),
        "DENIVELE": f"{total_denivele:,.0f} m".replace(",", " "),
        "ROUTES": f"{routes_connues} / {len(valides)}",
        "NOTE": escape(note),
        "LIGNES": "\n".join(lignes),
    }
    # Une seule passe : le nom d'une trace peut contenir une marque du template.
    contenu = re.sub(r"@@([A-Z]+)@@", lambda match: valeurs[match.group(1)], template)
    sortie.parent.mkdir(parents=True, exist_ok=True)
    sortie.write_text(contenu, encoding="utf-8")
    return sortie
