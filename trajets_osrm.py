"""Calculs OSRM/OpenStreetMap sans clé, par lots, avec cache et limite de débit."""
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

DEPART_GAREOULT = (43.3293, 6.0458)  # mairie, latitude / longitude
SERVEUR_OSRM = "https://routing.openstreetmap.de/routed-car"
GEOCODEUR = "https://photon.komoot.io/api/"
USER_AGENT = "gpx2dash/1.0 (personal GPX dashboard)"
CHAMPS_ROUTE = ("distance_route_m", "duree_route_s", "date_route", "erreur_route",
                "distance_acces_m", "route_cacheable")


def coordonnees(position):
    latitude, longitude = map(float, position)
    if not (math.isfinite(latitude) and math.isfinite(longitude)
            and -90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError("Coordonnées invalides.")
    return round(latitude, 6), round(longitude, 6)


def serveur_valide(serveur):
    serveur = serveur.rstrip("/")
    url = urlsplit(serveur)
    if url.scheme not in ("http", "https") or not url.netloc or url.query or url.fragment:
        raise ValueError("URL du serveur OSRM invalide.")
    return serveur


def cle_trajet(destination, origine=DEPART_GAREOULT, serveur=SERVEUR_OSRM):
    lat, lon = coordonnees(destination)
    lat0, lon0 = coordonnees(origine)
    return f"{serveur_valide(serveur)}|{lat0:.6f},{lon0:.6f}|{lat:.6f},{lon:.6f}"


def lien_osm(destination, origine=DEPART_GAREOULT):
    lat, lon = coordonnees(destination)
    lat0, lon0 = coordonnees(origine)
    return "https://www.openstreetmap.org/directions?" + urlencode({
        "engine": "fossgis_osrm_car", "route": f"{lat0:.6f},{lon0:.6f};{lat:.6f},{lon:.6f}",
    })


def ecrire_json(path, donnees):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".part", delete=False) as fichier:
        temporaire = Path(fichier.name)
        fichier.write(json.dumps(donnees, ensure_ascii=False, allow_nan=False).encode("utf-8"))
    try:
        os.replace(temporaire, path)
    finally:
        temporaire.unlink(missing_ok=True)


def lire_cache(path):
    try:
        donnees = json.loads(Path(path).read_text(encoding="utf-8")) if path else {}
        return donnees["routes"] if donnees.get("version") == 1 and isinstance(donnees.get("routes"), dict) else {}
    except (OSError, ValueError, TypeError, AttributeError):
        return {}


def cache_valide(route):
    # Pas d'expiration : un trajet, ou une erreur durable, reste valable.
    # Seul --cache-clear vide le cache.
    try:
        datetime.fromisoformat(route["date_route"])
        if route.get("erreur_route"):
            return route.get("route_cacheable") is True
        return all(not isinstance(route[cle], bool) and math.isfinite(route[cle]) and route[cle] >= 0
                   for cle in ("distance_route_m", "duree_route_s"))
    except (ValueError, KeyError, TypeError):
        return False


class ErreurOSRM(ValueError):
    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code


class ClientOSRM:
    def __init__(self, origine=DEPART_GAREOULT, serveur=SERVEUR_OSRM):
        self.origine, self.serveur = coordonnees(origine), serveur_valide(serveur)
        self.dernier_appel = None
        self.appels = 0

    def matrice(self, destinations, origine_prioritaire=False):
        positions = [self.origine] + [coordonnees(p) for p in destinations]
        # Le proxy FOSSGIS choisit le continent majoritaire parmi les coordonnées.
        # Si nécessaire, des origines supplémentaires fixent le continent du départ ;
        # elles ne sont ni sources ni destinations de la matrice demandée.
        if origine_prioritaire:
            positions.extend([self.origine] * len(destinations))
        coords = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in positions)
        url = f"{self.serveur}/table/v1/driving/{coords}?" + urlencode({
            "sources": "0", "destinations": ";".join(str(i) for i in range(1, len(destinations) + 1)),
            "annotations": "distance,duration", "generate_hints": "false",
        })
        if self.dernier_appel is not None:
            time.sleep(max(0, 1.05 - (time.monotonic() - self.dernier_appel)))
        self.dernier_appel = time.monotonic()
        self.appels += 1
        try:
            with urlopen(Request(url, headers={"User-Agent": USER_AGENT}), timeout=25) as response:
                data = json.loads(response.read(2 * 1024 * 1024))
        except HTTPError as exc:
            if exc.code == 429:
                raise ErreurOSRM("OSRM : service occupé (HTTP 429). Réessayez dans quelques instants.", "serveur") from exc
            if exc.code == 400:
                try:
                    data = json.loads(exc.read())
                except ValueError:
                    raise ErreurOSRM("OSRM : requête refusée.", "HTTP400") from exc
            else:
                raise ErreurOSRM(f"OSRM : serveur indisponible (HTTP {exc.code}).", "serveur") from exc
        except (URLError, OSError) as exc:
            raise ErreurOSRM("OSRM : réseau indisponible ou délai dépassé.", "serveur") from exc
        except ValueError as exc:
            raise ErreurOSRM("OSRM : réponse illisible.", "serveur") from exc
        try:
            if data.get("code") != "Ok":
                raise ErreurOSRM("OSRM : aucun point routier ou itinéraire trouvé.", data.get("code"))
            distances, durees = data["distances"][0], data["durations"][0]
            points = data["destinations"]
            if not (len(distances) == len(durees) == len(points) == len(destinations)):
                raise ErreurOSRM("OSRM : réponse incomplète.", "serveur")
            acces_origine = data["sources"][0].get("distance", 0)
            if acces_origine > 1000 and not origine_prioritaire:
                return self.matrice(destinations, origine_prioritaire=True)
            releve = datetime.now(timezone.utc).isoformat()
            routes = []
            for distance, duree, point in zip(distances, durees, points):
                route = {"date_route": releve, "route_cacheable": True}
                if acces_origine > 1000:
                    route["erreur_route"] = "La ville de départ est à plus de 1 km du réseau routier."
                elif distance is None or duree is None:
                    route["erreur_route"] = "Aucune liaison routière depuis la ville de départ."
                elif any(isinstance(v, bool) or not isinstance(v, (int, float))
                         or not math.isfinite(v) or v < 0 for v in (distance, duree)):
                    raise ErreurOSRM("OSRM : distance ou durée invalide.", "serveur")
                elif point.get("distance", 0) > 1000:
                    route["erreur_route"] = "Aucune liaison routière trouvée à proximité du départ de la trace (rayon de 1 km)."
                else:
                    route.update(distance_route_m=float(distance), duree_route_s=float(duree),
                                 distance_acces_m=point.get("distance", 0))
                routes.append(route)
            return routes
        except (KeyError, TypeError, IndexError, AttributeError) as exc:
            raise ErreurOSRM("OSRM : réponse incomplète.", "serveur") from exc

    def calculer(self, destinations):
        try:
            return self.matrice(destinations)
        except ErreurOSRM as exc:
            if exc.code == "NoSegment" and len(destinations) > 1:
                milieu = len(destinations) // 2
                return self.calculer(destinations[:milieu]) + self.calculer(destinations[milieu:])
            if exc.code in ("NoSegment", "NoRoute", "NoTable"):
                return [{"erreur_route": str(exc), "date_route": datetime.now(timezone.utc).isoformat(),
                         "route_cacheable": True} for _ in destinations]
            raise


def ajouter_trajets_osrm(resultats, *, origine=DEPART_GAREOULT, serveur=SERVEUR_OSRM,
                         fichier_cache=None, en_ligne=True, progression=None):
    cache = lire_cache(fichier_cache)
    client = ClientOSRM(origine, serveur)
    groupes, faits, erreur_cache = {}, 0, None
    for resultat in resultats:
        if "erreur" in resultat:
            if progression:
                progression(1)
            continue
        for champ in CHAMPS_ROUTE:
            resultat.pop(champ, None)
        try:
            destination = coordonnees(resultat["lat_lon_depart"])
            resultat["itineraire_url"] = lien_osm(destination, origine)
            cle = cle_trajet(destination, origine, serveur)
            groupes.setdefault(cle, (destination, []))[1].append(resultat)
        except (ValueError, TypeError, KeyError):
            resultat["erreur_route"] = "Coordonnées du départ invalides."
            if progression:
                progression(1)
    manquants = []
    for cle, (destination, traces) in groupes.items():
        if cache_valide(cache.get(cle, {})):
            for trace in traces:
                trace.update({k: v for k, v in cache[cle].items() if k in CHAMPS_ROUTE})
            if progression:
                progression(len(traces))
            faits += len(traces)
        elif en_ligne:
            manquants.append((cle, destination, traces))
        else:
            for trace in traces:
                trace["erreur_route"] = "Trajet absent du cache hors connexion."
            if progression:
                progression(len(traces))
    erreur_globale = None
    for debut in range(0, len(manquants), 25):
        lot = manquants[debut:debut + 25]
        try:
            if erreur_globale:
                raise ErreurOSRM(erreur_globale)
            routes = client.calculer([item[1] for item in lot])
        except ErreurOSRM as exc:
            erreur_globale = str(exc)
            routes = [{"erreur_route": erreur_globale} for _ in lot]
        for (cle, destination, traces), route in zip(lot, routes):
            if route.get("route_cacheable"):
                cache[cle] = route
            for trace in traces:
                trace.update(route)
            if progression:
                progression(len(traces))
        if fichier_cache:
            try:
                ecrire_json(fichier_cache, {"version": 1, "routes": cache})
            except OSError as exc:
                erreur_cache = str(exc)
    return {"appels": client.appels, "traces_cache": faits, "erreur_cache": erreur_cache}


def chercher_villes(recherche):
    """Recherche explicite Photon : communes et villages, jamais une adresse arbitraire."""
    recherche = recherche.strip()
    if not 2 <= len(recherche) <= 160:
        raise ValueError("Saisissez une ville (2 à 160 caractères).")
    url = GEOCODEUR + "?" + urlencode({"q": recherche, "limit": 8, "lang": "fr", "osm_tag": "place"})
    try:
        with urlopen(Request(url, headers={"User-Agent": USER_AGENT}), timeout=20) as response:
            data = json.loads(response.read(1024 * 1024))
        villes, deja = [], set()
        for feature in data["features"]:
            props = feature["properties"]
            if props.get("osm_value") not in ("city", "town", "village", "hamlet", "municipality"):
                continue
            lon, lat = feature["geometry"]["coordinates"]
            position = coordonnees((lat, lon))
            if position in deja:
                continue
            deja.add(position)
            libelle = ", ".join(str(props[k]) for k in ("name", "postcode", "state", "country") if props.get(k))
            villes.append({"libelle": libelle, "position": position})
        return villes
    except (OSError, URLError, ValueError, KeyError, TypeError) as exc:
        raise ValueError("Recherche des villes indisponible. Réessayez ou utilisez --origine LAT LON.") from exc
