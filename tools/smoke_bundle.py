"""Exercise the actual executable: resources, multiprocessing, offline elevation, routing cache and asphalt geometry."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import gpx2elev
from goudron_osm import SERVEUR_OVERPASS
from gpx2dash import VERSION_CACHE
from trajets_osrm import cle_trajet
from version import VERSION

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("executable", nargs="?")
    args = parser.parse_args()
    command = [str(Path(args.executable).resolve())] if args.executable else [sys.executable, str(Path(__file__).resolve().parent.parent / "gpx2dash.py")]
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    def run(arguments, cwd, launch=None):
        result = subprocess.run((launch or command) + arguments, cwd=cwd, env=env, text=True, encoding="utf-8",
                                errors="replace", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180)
        if result.returncode:
            raise AssertionError(result.stdout)
        return result.stdout
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        folder = root / "gpx"
        folder.mkdir()
        cache = folder / "archives" / ".cache_gpx"
        (cache / "goudron_osm").mkdir(parents=True)
        nested = folder / "2026" / "janvier"
        nested.mkdir(parents=True)
        for excluded in (folder / ".cache_gpx", nested / ".cache_gpx", cache):
            (excluded / "nested").mkdir(parents=True, exist_ok=True)
            (excluded / "nested" / "ignored.GPX").write_text("invalid cached GPX", encoding="utf-8")
        timestamp = datetime.now(timezone.utc).isoformat()
        manifest = {"version": 1, "mesures": {}, "sources": {}}
        routes = {}
        originals = {}
        for index in range(2):
            lat = 43.3293 + index * .00005
            filename = (folder if index == 0 else nested) / f"2026-01-0{index + 1}.GPX"
            points = "".join(f'<trkpt lat="{lat}" lon="{lon}"><ele>{330 + i * 5}</ele><time>2026-01-01T08:0{i}:00Z</time></trkpt>'
                             for i, lon in enumerate((6.0458, 6.0470, 6.0483)))
            raw = ('<gpx version="1.1" creator="synthetic CI fixture"><trk><trkseg>' + points + '</trkseg></trk></gpx>').encode()
            filename.write_bytes(raw)
            originals[filename] = raw
            fingerprint = hashlib.sha256(raw).hexdigest()
            snapshot = fingerprint + ".json"
            document = {"osm3s": {"timestamp_osm_base": timestamp}, "elements": [{
                "type": "way", "id": index + 1, "tags": {"highway": "residential", "surface": "asphalt"},
                "geometry": [{"lon": 6.0457, "lat": lat}, {"lon": 6.0484, "lat": lat}]}]}
            (cache / "goudron_osm" / snapshot).write_text(json.dumps(document), encoding="utf-8")
            manifest["sources"][SERVEUR_OVERPASS + "|" + fingerprint] = {
                "fichier": snapshot, "goudron_date": timestamp, "rayon": 100, "tolerance_geometrie": 10}
            routes[cle_trajet((lat, 6.0458))] = {
                "distance_route_m": 10000, "duree_route_s": 900, "date_route": timestamp, "route_cacheable": True}
        (cache / "goudron_osm_v1.json").write_text(json.dumps(manifest), encoding="utf-8")
        (cache / "trajets_osrm_v1.json").write_text(json.dumps({"version": 1, "routes": routes}), encoding="utf-8")
        assert "--from-cache" in run(["--help"], root)
        assert VERSION in run(["--version"], root)
        for language in ("en", "fr"):
            html = root / f"{language}.html"
            kml = root / f"{language}.kml"
            run([str(folder), "--from-cache", "--no-routing", "--cache", str(cache),
                 "--language", language, "--html", str(html), "--kml", str(kml)], root)
            content = html.read_text(encoding="utf-8")
            start = content.index('type="application/json">') + len('type="application/json">')
            data = json.loads(content[start:content.index("</script>", start)])
            assert data["language"] == language and len(data["traces"]) == 2
            assert data["kml"] == kml.name
            assert data["overlapTolerance"] == 15 and data["overlapMinLength"] == 100
            assert all(trace["sharedIds"] == [other["id"] for other in data["traces"] if other != trace]
                       for trace in data["traces"])
            assert content.count('class="shared-tracks-link"') == 2
            assert all(trace["color"].startswith("#") and len(trace["color"]) == 7 for trace in data["traces"])
            assert 'id="map-catalogue"' in content and 'id="map-only-visible"' in content
            assert 'id="language"' in content and "position: sticky" in content
            assert kml.is_file() and "MultiGeometry" in kml.read_text(encoding="utf-8")
            # One entry per GPX content; asphalt depends on its parameters and keeps its own manifest.
            statistics = [json.loads(p.read_text(encoding="utf-8")) for p in cache.glob(f"*_{VERSION_CACHE}.json")]
            assert len(statistics) == 2
            for stat in statistics:
                assert stat["distance_m"] > 190 and stat["denivele_pos"] is not None
                assert stat["ville"] and stat["version_gpx2elev"] == gpx2elev.__version__
            measures = list(json.loads((cache / "goudron_osm_v1.json").read_text(encoding="utf-8"))["mesures"].values())
            assert len(measures) == 2
            for measure in measures:
                assert measure["distance_goudron_m"] > 190, measure
                assert measure["goudron_incertain_m"] == 0
            assert "10,0 km" in content
        assert all(path.read_bytes() == raw for path, raw in originals.items())
        # Relative overrides and defaults belong to the input folder, even from a different cwd.
        run([folder.name, "--from-cache", "--no-routing", "--cache", "archives/.cache_gpx",
             "--html", "outputs/relative.html", "--kml", "outputs/relative.kml"], root)
        assert (folder / "outputs/relative.html").is_file()
        assert (folder / "outputs/relative.kml").is_file()
        run([folder.name, "--from-cache", "--no-routing"], root)
        dashboards = list(folder.glob(f"{folder.name}_*.html"))
        assert len(dashboards) == 1
        assert dashboards[0].with_suffix(".kml").is_file()
        assert len(list((folder / ".cache_gpx").glob(f"*_{VERSION_CACHE}.json"))) == 2
        assert not (root / ".cache_gpx").exists()
        # Launch without a folder from elsewhere: the executable/script directory owns everything.
        application = root / "application"
        application.mkdir()
        if args.executable:
            executable = Path(command[0])
            shutil.copy2(executable, application / executable.name)
            shutil.copytree(executable.parent / "_internal", application / "_internal", symlinks=True)
            launch = [str(application / executable.name)]
        else:
            script = Path(command[1])
            shutil.copy2(script, application / script.name)
            env["PYTHONPATH"] = str(script.parent) + os.pathsep + env.get("PYTHONPATH", "")
            launch = [sys.executable, str(application / script.name)]
        for path, raw in originals.items():
            target = application / "tracks" / "nested" / path.name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        ignored = application / ".cache_gpx" / "ignored.gpx"
        ignored.parent.mkdir()
        ignored.write_text("invalid cached GPX", encoding="utf-8")
        run(["--from-cache", "--no-routing"], root, launch)
        dashboards = list(application.glob("application_*.html"))
        assert len(dashboards) == 1 and dashboards[0].with_suffix(".kml").is_file()
        assert len(list(ignored.parent.glob(f"*_{VERSION_CACHE}.json"))) == 2
        assert not (root / ".cache_gpx").exists()
    print("Executable smoke passed: EN/FR, recursive GPX, excluded caches, folder-relative paths, GPX unchanged, KML/HTML, spawn workers, geocoder and native geometry.")


if __name__ == "__main__":
    main()
