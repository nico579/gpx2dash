"""Régénère le HTML depuis les statistiques vérifiées, en reprenant les routes manquantes."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from gpx2dash import extraire_et_reduire
from tableau_bord import generer_tableau_bord
from trajets_osrm import ajouter_trajets_osrm, ecrire_json, lire_cache
from tqdm import tqdm

root = Path(__file__).resolve().parent.parent
cache_file = root / ".cache_gpx" / "trajets_osrm_v1.json"
cache = lire_cache(cache_file)
# Recalcul ponctuel des anciens résultats négatifs après correction du choix de région.
cache = {key: route for key, route in cache.items() if not route.get("erreur_route")}
ecrire_json(cache_file, {"version": 1, "routes": cache})
results = []
for gpx in sorted((root.parent / "gpx").iterdir()):
    if not gpx.is_file() or gpx.suffix.lower() != ".gpx":
        continue
    # Reprise du cache indexé sur le contenu, sans téléchargement d'altitudes.
    results.append(extraire_et_reduire((str(gpx), 10, {
        "dossier_cache": str(root / ".cache_gpx"), "statistiques_cache": True,
        "altitudes_en_ligne": False,
    })))
with tqdm(total=len(results), desc="Reprise OSRM", ncols=100) as progress:
    report = ajouter_trajets_osrm(results, fichier_cache=cache_file, progression=progress.update)
generer_tableau_bord(results, root / "tableau_bord.html")
known = sum("distance_route_m" in result for result in results)
errors = sum("erreur" in result for result in results)
print(f"Catalogue régénéré : {len(results)} lignes, {known} trajets connus, {errors} traces inutilisables. {report}")
