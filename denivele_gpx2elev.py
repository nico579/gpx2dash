"""Adaptateur vers le moteur gpx2elev, sans interface graphique.

Le moteur est le paquet gpx2elev publié sur PyPI ; son installation de base
n'entraîne pas Qt.
"""
import gpx2elev
from gpx2elev.core import PROTOCOL, compute, parse_gpx, prepare
from gpx2elev.providers import MissingCoverage, Repository


def calculer_denivele(brut, dossier_cache, *, online=True, reader=None):
    """Un modèle complet pour toute la trace ; jamais de trous interpolés.

    Le GPX filtré n'est utilisé que si aucun modèle ne fournit le profil.
    Sans altitudes GPX complètes, le dénivelé reste explicitement inconnu.
    """
    prepared = prepare(parse_gpx(brut))
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
        "version_gpx2elev": gpx2elev.__version__,
        "positions_5m": prepared.sample_count,
        "replis": [{"modele": s.label, "raison": r} for s, r in series.fallbacks] if series else [],
        "erreur_modeles": erreur,
    }
