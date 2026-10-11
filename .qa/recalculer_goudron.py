"""Reprend uniquement le goudron sur le catalogue local déjà vérifié."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from gpx2dash import VERSION_CACHE, extraire_et_reduire
from goudron_osm import ajouter_goudron_osm, SERVEUR_OVERPASS
from tableau_bord import generer_tableau_bord
from trajets_osrm import ajouter_trajets_osrm
from tqdm import tqdm

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser()
parser.add_argument("--serveur", default=SERVEUR_OVERPASS)
parser.add_argument("--marge", type=float, default=15)
args = parser.parse_args()
results = []
start = perf_counter()
for path in sorted((root.parent / "gpx").iterdir()):
    if path.suffix.lower() != ".gpx" or not path.is_file():
        continue
    cache = root / ".cache_gpx" / f"{path.stem}_tol10_{VERSION_CACHE}.json"
    fingerprint = hashlib.sha256(path.read_bytes()).hexdigest()
    try:
        result = json.loads(cache.read_text(encoding="utf-8"))
        assert result["empreinte_gpx"] == fingerprint
    except (OSError, ValueError, AssertionError, KeyError):
        result = extraire_et_reduire((str(path), 10, {
            "dossier_cache": str(root / ".cache_gpx"), "statistiques_cache": True,
            "altitudes_en_ligne": False,
        }))
    results.append(result)
print(f"Catalogue vérifié : {len(results)} traces en {perf_counter() - start:.2f} s.", flush=True)
with tqdm(total=len(results), desc="Goudron OSM", ncols=100) as bar:
    report = ajouter_goudron_osm(results, dossier_cache=root / ".cache_gpx", en_ligne=True,
                                marge=args.marge, serveur=args.serveur, progression=bar.update)
print("Bilan", report, flush=True)
ajouter_trajets_osrm(results, fichier_cache=root / ".cache_gpx" / "trajets_osrm_v1.json", en_ligne=False)
generer_tableau_bord(results, root / "tableau_bord.html", marge_goudron=args.marge)
print("Tableau actualisé.", flush=True)
