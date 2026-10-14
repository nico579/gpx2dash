"""Contrôles du tableau HTML et des trajets OSRM, sans accès réseau réel."""
from contextlib import chdir
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from io import BytesIO
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

import gpxpy
import gpx2dash
from tableau_bord import date_du_nom, extraire_date, generer_tableau_bord
from trajets_osrm import (ClientOSRM, ErreurOSRM, ajouter_trajets_osrm,
                          cache_valide, chercher_villes, cle_trajet, ecrire_json, lien_osm)


class Table(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.rows, self.links, self.tags = [], [], []
        self.in_body, self.current, self.cell = False, None, None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        attrs = dict(attrs)
        if tag == "a":
            self.links.append(attrs.get("href"))
        if tag == "tbody":
            self.in_body = True
        if self.in_body and tag == "tr":
            self.current = []
        if self.in_body and tag == "td":
            self.cell = ""

    def handle_data(self, data):
        if self.cell is not None:
            self.cell += data

    def handle_endtag(self, tag):
        if tag == "td" and self.cell is not None:
            self.current.append(self.cell)
            self.cell = None
        if tag == "tr" and self.current is not None:
            self.rows.append(self.current)
            self.current = None
        if tag == "tbody":
            self.in_body = False


class CLITests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.application = self.root / "application"
        self.terminal = self.root / "terminal"
        self.tracks = self.root / "traces GPX"
        for folder in (self.application, self.terminal, self.tracks, self.root / "gpx"):
            folder.mkdir()

    def assert_default_paths(self, generate, folder):
        self.assertEqual(generate.call_args.args[0], str(folder))
        kml = Path(generate.call_args.args[1])
        html = Path(generate.call_args.kwargs["fichier_html"])
        self.assertEqual(kml.parent, folder)
        self.assertEqual(html.parent, folder)
        self.assertRegex(kml.name, rf"^{re.escape(folder.name)}_\d{{8}}_\d{{6}}\.kml$")
        self.assertEqual(html.stem, kml.stem)
        self.assertEqual(html.suffix, ".html")
        self.assertEqual(generate.call_args.kwargs["dossier_cache"], str(folder / ".cache_gpx"))

    def test_no_folder_uses_executable_or_script_directory(self):
        for frozen in (False, True):
            with self.subTest(frozen=frozen), chdir(self.terminal), \
                    patch.object(gpx2dash.sys, "frozen", frozen, create=True), \
                    patch.object(gpx2dash.sys, "executable", str(self.application / "gpx2dash.exe")), \
                    patch.object(gpx2dash, "__file__", str(self.application / "gpx2dash.py")), \
                    patch("sys.argv", ["gpx2dash"]), \
                    patch.object(gpx2dash, "fusionner_gpx_vers_kml_parallele") as generate:
                gpx2dash.main()
            self.assert_default_paths(generate, self.application)

    def test_explicit_folder_owns_default_cache_and_outputs(self):
        for argument in (str(self.tracks), "../traces GPX"):
            with self.subTest(folder=argument), chdir(self.terminal), \
                    patch("sys.argv", ["gpx2dash", argument]), \
                    patch.object(gpx2dash, "fusionner_gpx_vers_kml_parallele") as generate:
                gpx2dash.main()
            self.assert_default_paths(generate, self.tracks)

    def test_relative_and_absolute_cache_and_output_overrides(self):
        for absolute in (False, True):
            paths = [Path("cache perso"), Path("sorties/traces.kml"), Path("sorties/tableau.html")]
            if absolute:
                paths = [self.root / "ailleurs" / path for path in paths]
            cache, kml, html = map(str, paths)
            with self.subTest(absolute=absolute), chdir(self.terminal), \
                    patch("sys.argv", ["gpx2dash", "../traces GPX", "--cache", cache,
                                       "--kml", kml, "--html", html]), \
                    patch.object(gpx2dash, "fusionner_gpx_vers_kml_parallele") as generate:
                gpx2dash.main()
            self.assertEqual(generate.call_args.args, (str(self.tracks), str(self.tracks / paths[1])))
            self.assertEqual(generate.call_args.kwargs["fichier_html"], str(self.tracks / paths[2]))
            self.assertEqual(generate.call_args.kwargs["dossier_cache"], str(self.tracks / paths[0]))


class DashboardTests(unittest.TestCase):
    def test_dates_from_track_route_metadata_and_name(self):
        track = gpxpy.parse('<gpx><trk><trkseg><trkpt lat="43" lon="6"><time>2026-10-04T10:00:00Z</time></trkpt></trkseg></trk></gpx>')
        self.assertEqual(extraire_date(track, "2000-01-01"), "2026-10-04")
        route = gpxpy.parse('<gpx><rte><rtept lat="43" lon="6"><time>2026-10-05T10:00:00Z</time></rtept></rte></gpx>')
        self.assertEqual(extraire_date(route, "2000-01-01"), "2026-10-05")
        metadata = gpxpy.gpx.GPX()
        metadata.time = datetime(2026, 10, 6, 10, tzinfo=timezone.utc)
        self.assertEqual(extraire_date(metadata, "2000-01-01"), "2026-10-06")
        self.assertEqual(extraire_date(gpxpy.gpx.GPX(), "sortie_20261007_100000"), "2026-10-07")
        self.assertIsNone(date_du_nom("2026-02-31"))
        self.assertIsNone(date_du_nom("trace_sans_date"))

    def test_duration_for_timestamped_route(self):
        route = gpxpy.parse('<gpx><rte><rtept lat="43" lon="6"><time>2026-10-04T10:00:00Z</time></rtept><rtept lat="43" lon="6.001"><time>2026-10-04T11:00:00Z</time></rtept></rte></gpx>')
        self.assertEqual(gpx2dash._calc_duree(route), 3600)
        self.assertIsNone(gpx2dash._calc_duree(gpxpy.gpx.GPX()))

    def test_cache_source_fingerprint_protocol_and_output_directory(self):
        from denivele_gpx2elev import PROTOCOL, calculer_denivele
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            path = folder / "trace.gpx"
            raw = b'<gpx><trk><trkseg><trkpt lat="43" lon="6"><ele>100</ele></trkpt><trkpt lat="43" lon="6.001"><ele>110</ele></trkpt></trkseg></trk></gpx>'
            path.write_bytes(raw)
            source = folder / "source-cache"
            target = folder / "target-cache"
            source.mkdir()
            with patch.object(gpx2dash, "calculer_denivele",
                              side_effect=lambda raw, cache: calculer_denivele(raw, cache, online=False)):
                original = gpx2dash.extraire_et_reduire((str(path), 10))
            cache = source / Path(original["chemin_cache"]).name
            cache.write_text(json.dumps(original), encoding="utf-8")
            before = cache.stat().st_mtime_ns
            options = {"cache_source": str(source), "dossier_cache": str(target),
                       "statistiques_cache": True, "altitudes_en_ligne": False}
            with patch.object(gpx2dash, "calculer_denivele") as compute:
                cached = gpx2dash.extraire_et_reduire((str(path), 10, options))
            compute.assert_not_called()
            self.assertTrue(cached["statistiques_cache"])
            self.assertEqual(cached["distance_m"], original["distance_m"])
            self.assertEqual(Path(cached["chemin_cache"]).parent, target)
            self.assertEqual(cache.stat().st_mtime_ns, before)
            path.write_bytes(raw.replace(b"110", b"120"))
            with patch.object(gpx2dash, "calculer_denivele", return_value=original) as compute:
                changed = gpx2dash.extraire_et_reduire((str(path), 10, options))
            self.assertFalse(changed["statistiques_cache"])
            self.assertEqual(compute.call_args.kwargs, {"online": False})
            path.write_bytes(raw)
            original["protocole"] = PROTOCOL + "-old"
            cache.write_text(json.dumps(original), encoding="utf-8")
            with patch.object(gpx2dash, "calculer_denivele", return_value=original) as compute:
                changed_protocol = gpx2dash.extraire_et_reduire((str(path), 10, options))
            self.assertFalse(changed_protocol["statistiques_cache"])
            compute.assert_called_once()

    def test_date_is_extracted_before_simplification(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "2000-01-01.gpx"
            path.write_text('<gpx><trk><trkseg><trkpt lat="43" lon="6"/><trkpt lat="43" lon="6.001"><time>2026-10-04T10:00:00Z</time></trkpt><trkpt lat="43" lon="6.002"/></trkseg></trk></gpx>', encoding="utf-8")
            with patch.object(gpx2dash, "calculer_denivele", return_value={"distance_m": 160, "modele": "Test"}):
                result = gpx2dash.extraire_et_reduire((str(path), 10))
        self.assertEqual(result["date"], "2026-10-04")
        self.assertEqual(len(result["segments"][0]), 2)

    def test_rows_unknown_values_and_escaping(self):
        results = [
            {"nom": '2026-10-04_<script>alert(1)</script>', "date": "2026-10-04",
             "ville": '<img src=x onerror=alert(1)>', "distance_m": 22325, "denivele_pos": 735,
             "denivele_neg": 736, "duree_s": 14160, "distance_route_m": 42100, "duree_route_s": 2220,
             "itineraire_url": lien_osm((43.5, 6.2))},
            {"nom": "trace_sans_date", "ville": "Lieu inconnu", "distance_m": 0,
             "denivele_pos": None, "duree_s": None},
            {"nom": "2026-10-05_invalide", "erreur": "GPX <illisible>"},
        ]
        with tempfile.TemporaryDirectory() as directory:
            output = generer_tableau_bord(results, Path(directory) / "dashboard.html")
            html = output.read_text(encoding="utf-8")
        table = Table(html)
        self.assertEqual(len(table.rows), 3)
        self.assertTrue(all(len(row) == 9 for row in table.rows))
        self.assertIn("Trace illisible", table.rows[0][1])
        self.assertIn("22,3 km", table.rows[1][2])
        self.assertIn("+735 m", table.rows[1][3])
        self.assertEqual(table.rows[1][4], "3 h 56")
        self.assertEqual(table.rows[1][5], "42,1 km")
        self.assertEqual(table.rows[1][6], "37 min")
        self.assertEqual(table.rows[2][2], "0,0 km")
        self.assertEqual(table.rows[2][3:7], ["—"] * 4)
        self.assertNotIn("img", table.tags)
        self.assertEqual(table.tags.count("script"), 2)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertNotIn("@@LIGNES@@", html)

    def test_embedded_map_preserves_separate_segments_and_longitude_latitude(self):
        segments = [[[6.1, 43.1], [6.12, 43.12]], [[6.3, 43.3], [6.32, 43.32]]]
        results = [{"nom": "trace_deux_segments", "lat_lon_depart": (43.1, 6.1), "segments": segments,
                    "itineraire_url": lien_osm((43.1, 6.1))}]
        with tempfile.TemporaryDirectory() as directory:
            output = generer_tableau_bord(results, Path(directory) / "out.html")
            html = output.read_text(encoding="utf-8")
        start = html.index('type="application/json">') + len('type="application/json">')
        payload = json.loads(html[start:html.index("</script>", start)])
        self.assertEqual(payload["traces"][0]["segments"], segments)
        self.assertEqual(payload["traces"][0]["position"], [43.1, 6.1])
        self.assertIn('aria-controls="map-dialog"', html)
        self.assertIn("Itinéraire et trace GPX", html)
        self.assertIn("Leaflet", html)
        self.assertNotIn('src="https://unpkg.com', html)
        self.assertEqual(results[0]["segments"], segments)

    def test_empty_dashboard(self):
        with tempfile.TemporaryDirectory() as directory:
            output = generer_tableau_bord([], Path(directory) / "empty.html")
            self.assertEqual(len(Table(output.read_text(encoding="utf-8")).rows), 0)

    def test_same_filename_in_subfolders_keeps_both_traces_on_map(self):
        import concurrent.futures
        import reverse_geocoder
        from denivele_gpx2elev import calculer_denivele
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            for name, lat in (("nord", 44), ("sud", 43)):
                subfolder = folder / name
                subfolder.mkdir()
                (subfolder / "trace.gpx").write_text(
                    f'<gpx><trk><trkseg><trkpt lat="{lat}" lon="6"><ele>100</ele></trkpt>'
                    f'<trkpt lat="{lat}" lon="6.001"><ele>110</ele></trkpt></trkseg></trk></gpx>',
                    encoding="utf-8")
            with patch.object(gpx2dash, "calculer_denivele",
                              side_effect=lambda raw, cache: calculer_denivele(raw, cache, online=False)), \
                    patch.object(gpx2dash.concurrent.futures, "ProcessPoolExecutor", concurrent.futures.ThreadPoolExecutor), \
                    patch.object(reverse_geocoder, "search", return_value=[{"name": "Test"}] * 2):
                results = gpx2dash.fusionner_gpx_vers_kml_parallele(
                    folder, folder / "out.kml", routes_en_ligne=False)
            self.assertEqual({result["nom"] for result in results}, {"nord/trace", "sud/trace"})
            html = (folder / "out.html").read_text(encoding="utf-8")
            start = html.index('type="application/json">') + len('type="application/json">')
            payload = json.loads(html[start:html.index("</script>", start)])
            self.assertEqual({trace["id"] for trace in payload["traces"]}, {"nord/trace", "sud/trace"})

    def test_full_kml_and_html_pipeline_without_network(self):
        import concurrent.futures
        import reverse_geocoder
        from denivele_gpx2elev import calculer_denivele
        def offline(raw, cache):
            return calculer_denivele(raw, cache, online=False)
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            nested = folder / "2026" / "automne"
            nested.mkdir(parents=True)
            (nested / "2026-10-04.GPX").write_text('<gpx><trk><trkseg><trkpt lat="43" lon="6"><ele>100</ele></trkpt><trkpt lat="43" lon="6.001"><ele>110</ele></trkpt></trkseg></trk></gpx>', encoding="utf-8")
            (folder / "2026-10-05.gpx").write_text("invalid GPX", encoding="utf-8")
            cache = folder / "archives" / "cache perso"
            for excluded in (folder / ".cache_gpx", nested / ".cache_gpx", cache):
                (excluded / "sous-dossier").mkdir(parents=True)
                (excluded / "sous-dossier" / "ignore.GPX").write_text("invalid cached GPX", encoding="utf-8")
            with patch.object(gpx2dash, "calculer_denivele", offline), \
                    patch.object(gpx2dash.concurrent.futures, "ProcessPoolExecutor", concurrent.futures.ThreadPoolExecutor), \
                    patch.object(reverse_geocoder, "search", return_value=[{"name": "Test"}]):
                gpx2dash.fusionner_gpx_vers_kml_parallele(directory, folder / "out.kml",
                                                       dossier_cache=cache, routes_en_ligne=False)
            self.assertTrue((folder / "out.kml").is_file())
            html = (folder / "out.html").read_text(encoding="utf-8")
            table = Table(html)
            start = html.index('type="application/json">') + len('type="application/json">')
            payload = json.loads(html[start:html.index("</script>", start)])
            self.assertEqual(payload["kml"], "out.kml")
            self.assertIn('id="map-catalogue"', html)
            from xml.etree import ElementTree as ET
            document = ET.parse(folder / "out.kml")
            ns = {"k": "http://www.opengis.net/kml/2.2"}
            kml_color = document.find(".//k:LineStyle/k:color", ns).text
            html_color = payload["traces"][0]["color"].lstrip("#")
            self.assertEqual(kml_color, "ff" + html_color[4:6] + html_color[2:4] + html_color[:2])
            self.assertEqual(len(table.rows), 2)
            self.assertEqual(len(list(cache.glob(f"*_{gpx2dash.VERSION_CACHE}.json"))), 2)
            self.assertEqual(payload["traces"][0]["id"], "2026-10-04")
            self.assertTrue(any(link.startswith("https://www.openstreetmap.org/directions?") for link in table.links))


class OSRMTests(unittest.TestCase):
    @staticmethod
    def response(distances, durations=None):
        return {"code": "Ok", "distances": [distances], "durations": [durations or [600] * len(distances)],
                "destinations": [{"distance": 10} for _ in distances], "sources": [{"distance": 5}]}

    def test_links_origin_and_api_coordinate_order(self):
        origin = (43.12, 5.93)
        query = parse_qs(urlsplit(lien_osm((43.5, 6.2), origin)).query)
        self.assertEqual(query["route"], ["43.120000,5.930000;43.500000,6.200000"])
        self.assertEqual(query["engine"], ["fossgis_osrm_car"])
        with patch("trajets_osrm.urlopen", return_value=BytesIO(json.dumps(self.response([42100], [2220.5])).encode())) as fetch:
            result = ClientOSRM(origin).matrice([(43.5, 6.2)])
        request = fetch.call_args.args[0]
        self.assertIn("/5.930000,43.120000;6.200000,43.500000?", request.full_url)
        query = parse_qs(urlsplit(request.full_url).query)
        self.assertEqual(query["sources"], ["0"])
        self.assertEqual(query["destinations"], ["1"])
        self.assertEqual(query["annotations"], ["distance,duration"])
        self.assertIn("gpx2dash", request.get_header("User-agent"))
        self.assertEqual(result[0]["distance_route_m"], 42100)
        self.assertEqual(result[0]["duree_route_s"], 2220.5)

    def test_batches_deduplicate_and_cache_is_specific_to_origin(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "routes.json"
            results = [{"lat_lon_depart": (43.5 + i / 10000, 6.2)} for i in range(30)]
            results.append({"lat_lon_depart": (43.5, 6.2)})
            def compute(positions):
                return [{"distance_route_m": 5000, "duree_route_s": 600,
                         "date_route": datetime.now(timezone.utc).isoformat(), "route_cacheable": True} for _ in positions]
            with patch.object(ClientOSRM, "calculer", side_effect=compute) as fetch:
                ajouter_trajets_osrm(results, fichier_cache=path)
            self.assertEqual([len(call.args[0]) for call in fetch.call_args_list], [25, 5])
            self.assertTrue(all(result["distance_route_m"] == 5000 for result in results))
            with patch.object(ClientOSRM, "calculer") as fetch:
                report = ajouter_trajets_osrm(results, fichier_cache=path, en_ligne=False)
            fetch.assert_not_called()
            self.assertEqual(report["traces_cache"], 31)
            ajouter_trajets_osrm(results, origine=(43.12, 5.93), fichier_cache=path, en_ligne=False)
            self.assertTrue(all("distance_route_m" not in result for result in results))
            self.assertTrue(all("43.120000" in result["itineraire_url"] for result in results))

    def test_cache_never_expires_server_and_origin(self):
        now = datetime.now(timezone.utc)
        route = {"distance_route_m": 1, "duree_route_s": 2, "date_route": now.isoformat()}
        self.assertTrue(cache_valide(route))
        for date in (now - timedelta(days=3650), now + timedelta(days=1)):
            self.assertTrue(cache_valide({**route, "date_route": date.isoformat()}))
        self.assertFalse(cache_valide({**route, "date_route": "pas une date"}))
        self.assertFalse(cache_valide({**route, "distance_route_m": float("nan")}))
        error = {"erreur_route": "No route", "route_cacheable": True, "date_route": now.isoformat()}
        self.assertTrue(cache_valide(error))
        self.assertTrue(cache_valide({**error, "date_route": (now - timedelta(days=2)).isoformat()}))
        self.assertFalse(cache_valide({**error, "route_cacheable": False}))
        self.assertNotEqual(cle_trajet((43, 6)), cle_trajet((43, 6), (43.1, 6)))
        self.assertNotEqual(cle_trajet((43, 6)), cle_trajet((43, 6), serveur="http://localhost:5000"))

    def test_cached_errors_do_not_hide_valid_routes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "routes.json"
            ecrire_json(path, {"version": 1, "routes": {
                cle_trajet((43.5, 6.2)): {"erreur_route": "Aucune route", "route_cacheable": True,
                                         "date_route": datetime.now(timezone.utc).isoformat()}}})
            results = [{"lat_lon_depart": (43.5, 6.2)}, {"lat_lon_depart": (43.6, 6.3)}]
            with patch.object(ClientOSRM, "calculer", return_value=[{
                    "distance_route_m": 12000, "duree_route_s": 600,
                    "date_route": datetime.now(timezone.utc).isoformat(), "route_cacheable": True}]) as fetch:
                ajouter_trajets_osrm(results, fichier_cache=path)
            fetch.assert_called_once_with([(43.6, 6.3)])
            self.assertEqual(results[0]["erreur_route"], "Aucune route")
            self.assertEqual(results[1]["distance_route_m"], 12000)

    def test_null_or_remote_road_remains_unknown(self):
        response = self.response([None, 100, 200], [None, 60, 120])
        response["destinations"][1]["distance"] = 1100
        with patch("trajets_osrm.urlopen", side_effect=lambda *a, **kw: BytesIO(json.dumps(response).encode())):
            routes = ClientOSRM().matrice([(43.5, 6.2)] * 3)
        self.assertTrue(all("distance_route_m" not in r for r in routes[:2]))
        self.assertEqual(routes[2]["distance_route_m"], 200)
        response["sources"][0]["distance"] = 2000
        with patch("trajets_osrm.urlopen", side_effect=lambda *a, **kw: BytesIO(json.dumps(response).encode())):
            routes = ClientOSRM().matrice([(43.5, 6.2)] * 3)
        self.assertTrue(all("erreur_route" in r and "distance_route_m" not in r for r in routes))

    def test_mixed_continents_do_not_discard_local_destinations(self):
        wrong = self.response([100, 200])
        wrong["sources"][0]["distance"] = 7000000
        correct = self.response([100, 200])
        correct["destinations"][1]["distance"] = 7000000
        with patch("trajets_osrm.urlopen", side_effect=[BytesIO(json.dumps(wrong).encode()),
                                                       BytesIO(json.dumps(correct).encode())]) as fetch, \
                patch("trajets_osrm.time.sleep"):
            routes = ClientOSRM().matrice([(43.5, 6.2), (51.2, -115.8)])
        self.assertEqual(routes[0]["distance_route_m"], 100)
        self.assertNotIn("distance_route_m", routes[1])
        self.assertEqual(fetch.call_count, 2)
        url = urlsplit(fetch.call_args.args[0].full_url)
        positions = url.path.split("/")[-1].split(";")
        self.assertEqual(len(positions), 5)
        self.assertEqual(positions[-2:], [positions[0], positions[0]])
        self.assertEqual(parse_qs(url.query)["destinations"], ["1;2"])

    def test_network_failure_stops_and_is_not_cached(self):
        results = [{"lat_lon_depart": (43.5 + i / 10000, 6.2)} for i in range(30)]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "routes.json"
            with patch("trajets_osrm.urlopen", side_effect=HTTPError("https://osrm", 503, "Unavailable", {}, None)) as fetch:
                ajouter_trajets_osrm(results, fichier_cache=path)
            self.assertEqual(fetch.call_count, 1)
            self.assertTrue(all("itineraire_url" in r and "erreur_route" in r for r in results))
            self.assertEqual(json.loads(path.read_text())["routes"], {})

    def test_bad_coordinate_in_batch_is_isolated(self):
        bad = (43.7, 6.7)
        def matrix(positions):
            if bad in positions:
                raise ErreurOSRM("No segment", "NoSegment")
            return [{"distance_route_m": 100, "duree_route_s": 10} for _ in positions]
        with patch.object(ClientOSRM, "matrice", side_effect=matrix):
            routes = ClientOSRM().calculer([(43.5, 6.2), bad, (43.6, 6.3)])
        self.assertEqual(routes[0]["distance_route_m"], 100)
        self.assertIn("erreur_route", routes[1])
        self.assertEqual(routes[2]["distance_route_m"], 100)

    def test_rate_limit_and_incomplete_responses(self):
        with patch("trajets_osrm.urlopen", side_effect=lambda *a, **kw: BytesIO(json.dumps(self.response([100])).encode())), \
                patch("trajets_osrm.time.monotonic", return_value=0), patch("trajets_osrm.time.sleep") as sleep:
            client = ClientOSRM()
            client.matrice([(43.5, 6.2)])
            client.matrice([(43.6, 6.3)])
            sleep.assert_called_once_with(1.05)
        for response in ({}, {"code": "Ok"}, self.response([float("nan")]), self.response([100, 200])):
            with self.subTest(response=response), patch("trajets_osrm.urlopen", return_value=BytesIO(json.dumps(response).encode())):
                with self.assertRaises(ErreurOSRM):
                    ClientOSRM().matrice([(43.5, 6.2)])

    def test_city_lookup_filters_places_and_preserves_coordinates(self):
        town = {"properties": {"name": "Toulon", "state": "Provence-Alpes-Côte d’Azur", "country": "France", "osm_value": "city"},
                "geometry": {"coordinates": [5.93, 43.12]}}
        poi = {"properties": {"name": "Toulon shop", "osm_value": "shop"}, "geometry": {"coordinates": [6, 43]}}
        with patch("trajets_osrm.urlopen", return_value=BytesIO(json.dumps({"features": [town, town, poi]}).encode())) as fetch:
            cities = chercher_villes("Toulon")
        self.assertEqual(len(cities), 1)
        self.assertEqual(cities[0]["position"], (43.12, 5.93))
        self.assertIn("France", cities[0]["libelle"])
        self.assertEqual(parse_qs(urlsplit(fetch.call_args.args[0].full_url).query)["q"], ["Toulon"])

    def test_embedded_json_cannot_close_the_script_element(self):
        name = '</script><img src=x onerror=alert(1)>'
        with tempfile.TemporaryDirectory() as directory:
            path = generer_tableau_bord([{"nom": name, "lat_lon_depart": (43.5, 6.2)}],
                                       Path(directory) / "out.html", libelle_origine=name)
            html = path.read_text(encoding="utf-8")
        self.assertNotIn("<img", html)
        self.assertEqual(Table(html).tags.count("script"), 2)
        start = html.index('type="application/json">') + len('type="application/json">')
        payload = json.loads(html[start:html.index("</script>", start)])
        self.assertEqual(payload["origine"]["libelle"], name)
        self.assertEqual(payload["traces"][0]["id"], name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
