"""Adaptateur vers le moteur gpx2elev, sans interface graphique.

Le moteur est le paquet gpx2elev publié sur PyPI ; son installation de base
n'entraîne pas Qt.
"""
import gpx2elev
from gpx2elev.core import PROTOCOL, compute, parse_gpx, prepare
from gpx2elev.providers import MissingCoverage, Repository

VERSION_GPX2ELEV = gpx2elev.__version__
# Contenu que gpxpy lit mais que le moteur refuse : plus de 20 Mo, de 250 000 points
# ou de 300 000 positions à 5 m (environ 1 500 km). La trace reste sur la carte et
# dans le KML, sans dénivelé. Le refus ne dépend que du contenu et de la version du
# moteur : il n'est retenté qu'avec une autre version de gpx2elev.
SOURCE_REFUSEE = "HORS_LIMITES"
MODELE_REFUSE = "Trace hors des limites du moteur de dénivelé"


class TraceRefusee(ValueError):
    """Le moteur refuse ce contenu à la lecture ou à l'échantillonnage à 5 m."""


def calculer_denivele(brut, dossier_cache, *, online=True, reader=None):
    """Un modèle complet pour toute la trace ; jamais de trous interpolés.

    Le GPX filtré n'est utilisé que si aucun modèle ne fournit le profil.
    Sans altitudes GPX complètes, le dénivelé reste explicitement inconnu.
    """
    try:
        prepared = prepare(parse_gpx(brut))
    except ValueError as exc:
        raise TraceRefusee(str(exc)) from exc
    repository = Repository(dossier_cache, reader=reader)
    erreur = None
    series = None
    try:
        try:
            series = repository.obtain(prepared.coordinates, online=online)
        except MissingCoverage as exc:
            erreur = str(exc)
        # Le profil nul sert seulement à obtenir les statistiques GPX communes.
        computed = compute(prepared, series.values if series else [0.0] * prepared.sample_count)
    finally:
        # Pas de repository.close() : il élague les profils et les tuiles du MNT
        # au-delà d'une taille. gpx2dash ne vide son cache que sur --cache-clear.
        repository.http.close()
    gain = computed.gain if series else computed.gpx_filtered
    def valeurs(value):
        return {"Dplus_m": value.up, "Dmoins_m": value.down} if value is not None else None
    return {
        "denivele_pos": round(gain.up) if gain is not None else None,
        "denivele_neg": round(gain.down) if gain is not None else None,
        "denivele_exact": valeurs(gain),
        "source_denivele": series.source.name if series else ("GPX" if gain else "INCONNU"),
        "modele": series.source.label if series else ("GPX filtré (secours)" if gain else "Indisponible"),
        "distance_m": prepared.length,
        "gpx_somme_brute": valeurs(computed.gpx_raw),
        "gpx_filtre": valeurs(computed.gpx_filtered),
        "protocole": PROTOCOL,
        "version_gpx2elev": VERSION_GPX2ELEV,
        "positions_5m": prepared.sample_count,
        "replis": [{"modele": s.label, "raison": r} for s, r in series.fallbacks] if series else [],
        "erreur_modeles": erreur,
    }


def statistiques_refusees(raison, distance_m):
    """Mêmes clés que calculer_denivele() : la distance seule, sans dénivelé."""
    return {
        "denivele_pos": None,
        "denivele_neg": None,
        "denivele_exact": None,
        "source_denivele": SOURCE_REFUSEE,
        "modele": MODELE_REFUSE,
        "distance_m": distance_m,
        "gpx_somme_brute": None,
        "gpx_filtre": None,
        "protocole": PROTOCOL,
        "version_gpx2elev": VERSION_GPX2ELEV,
        "positions_5m": None,
        "replis": [],
        "erreur_modeles": raison,
    }
