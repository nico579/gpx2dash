"""Contrôles géométriques, surfaces et caches sans appels réseau."""
import hashlib
import json
import re
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from pyproj import Geod, Transformer

from goudron_osm import (ClientOverpass, ajouter_goudron_osm, categorie_surface,
                         mesurer_goudron, segments_originaux, _requete, _VoiesOSM)
from tableau_bord import generer_tableau_bord


PROJ = Transformer.from_crs("+proj=aeqd +lat_0=43.3 +lon_0=6 +datum=WGS84 +units=m",
                            "EPSG:4326", always_xy=True)


def segment(*points):
    return [list(PROJ.transform(x, y)) for x, y in points]


def voie(points, surface="asphalt", ident=1):
    tags = {"highway": "residential"}
    if surface is not None:
        tags["surface"] = surface
    return {"type": "way", "id": ident, "tags": tags,
            "geometry": [{"lon": lon, "lat": lat} for lon, lat in points]}


def response(roads):
    return {"elements": roads, "osm3s": {"timestamp_osm_base": "2026-10-11T12:00:00Z"}}


class GeometryTests(unittest.TestCase):
    def setUp(self):
        self.road = voie(segment((0, 0), (1000, 0)))

    def test_distance_tolerance_and_reverse_direction(self):
        for pts in [((0, 10), (1000, 10)), ((1000, 10), (0, 10))]:
            result = mesurer_goudron([segment(*pts)], [self.road])
            self.assertAlmostEqual(result["distance_goudron_m"], 1000, delta=1)
        outside = mesurer_goudron([segment((0, 20), (1000, 20))], [self.road])
        self.assertEqual(outside["distance_goudron_m"], 0)
        wider = mesurer_goudron([segment((0, 20), (1000, 20))], [self.road], marge=25)
        self.assertAlmostEqual(wider["distance_goudron_m"], 1000, delta=1)
        for distance, matched in [(14.9, True), (15.1, False)]:
            result = mesurer_goudron([segment((0, distance), (1000, distance))], [self.road])
            self.assertEqual(result["distance_goudron_m"] > 990, matched)

    def test_crossing_and_angle_limit(self):
        import math
        perpendicular = mesurer_goudron([segment((500, -100), (500, 100))], [self.road])
        self.assertEqual(perpendicular["distance_goudron_m"], 0)
        for angle, matches in [(28, True), (35, False)]:
            end = (500 + 100 * math.cos(math.radians(angle)), 100 * math.sin(math.radians(angle)))
            result = mesurer_goudron([segment((500, 0), end)], [self.road])
            self.assertEqual(result["distance_goudron_m"] > 0, matches)

    def test_segments_repeated_passes_and_duplicate_roads(self):
        separated = mesurer_goudron([segment((0, 0), (100, 0)), segment((900, 0), (1000, 0))], [self.road])
        self.assertAlmostEqual(separated["distance_goudron_m"], 200, delta=1)
        backtrack = mesurer_goudron([segment((0, 0), (1000, 0), (0, 0))], [self.road, self.road])
        self.assertAlmostEqual(backtrack["distance_goudron_m"], 2000, delta=1)

    def test_surface_never_inferred_from_highway(self):
        for surface in ("asphalt", "chipseal", "bitumen"):
            self.assertEqual(categorie_surface({"surface": surface}), 0)
        for surface in ("paved", "sealed", None, "asphalt;gravel"):
            self.assertEqual(categorie_surface({"surface": surface or "", "highway": "primary"}), 1)
        for surface in ("concrete", "gravel", "paving_stones", "concrete:lanes"):
            self.assertEqual(categorie_surface({"surface": surface}), 2)
        unknown = mesurer_goudron([segment((0, 0), (1000, 0))],
                                  [voie(segment((0, 0), (1000, 0)), surface=None)])
        self.assertEqual(unknown["distance_goudron_m"], 0)
        self.assertAlmostEqual(unknown["goudron_incertain_m"], 1000, delta=1)

    def test_mixed_surface_and_excluded_area(self):
        roads = [voie(segment((0, 0), (500, 0)), ident=1),
                 voie(segment((500, 0), (1000, 0)), surface=None, ident=2)]
        result = mesurer_goudron([segment((0, 0), (1000, 0))], roads)
        self.assertAlmostEqual(result["distance_goudron_m"], 500, delta=20)
        self.assertAlmostEqual(result["goudron_incertain_m"], 500, delta=20)
        self.assertAlmostEqual(result["distance_goudron_m"] + result["goudron_incertain_m"], 1000, delta=1)
        area = {**self.road, "tags": {**self.road["tags"], "area": "yes"}}
        self.assertEqual(mesurer_goudron([segment((0, 0), (1000, 0))], [area])["distance_goudron_m"], 0)

    def test_spatial_prefilter_retains_road_crossing_trace_extent(self):
        roads = [voie(segment((-1000, 0), (2000, 0))),
                 voie(segment((0, 500), (1000, 500)), surface=None, ident=2)]
        trace = [segment((0, 10), (1000, 10))]
        indexed = mesurer_goudron(trace, _VoiesOSM(roads))
        self.assertAlmostEqual(indexed["distance_goudron_m"], 1000, delta=1)
        self.assertEqual(indexed, mesurer_goudron(trace, roads))
        empty = mesurer_goudron(trace, _VoiesOSM([]))
        self.assertEqual(empty["distance_goudron_m"], 0)
        self.assertAlmostEqual(empty["goudron_longueur_m"], 1000, delta=1)

    def test_query_covers_long_edge_and_tolerance(self):
        trace = {"segments": [segment((0, 0), (20000, 0))]}
        query = _requete([trace], 100)
        circles = [(int(r), float(lat), float(lon)) for r, lat, lon in
                   re.findall(r"around:(\d+),(-?[\d.]+),(-?[\d.]+)", query)]
        self.assertGreater(len(circles), 1)
        self.assertTrue(all(radius <= 5000 for radius, _, _ in circles))
        geod = Geod(ellps="WGS84")
        for x in range(0, 20001, 500):
            for y in (-99, 0, 99):
                lon, lat = PROJ.transform(x, y)
                self.assertTrue(any(
                    geod.inv(lon, lat, centre_lon, centre_lat)[2] <= radius
                    for radius, centre_lat, centre_lon in circles
                ), (x, y))
        with self.assertRaises(ValueError):
            _requete([{"segments": []}], 100)

    def test_original_gpx_routes_and_segments_remain_separate(self):
        raw = b'<gpx><trk><trkseg><trkpt lat="43" lon="6"/><trkpt lat="43" lon="6.01"/></trkseg><trkseg><trkpt lat="44" lon="7"/><trkpt lat="44" lon="7.01"/></trkseg></trk><rte><rtept lat="45" lon="8"/><rtept lat="45" lon="8.01"/></rte></gpx>'
        self.assertEqual(len(segments_originaux(raw)), 3)
        with self.assertRaises(ValueError):
            mesurer_goudron([], [self.road])


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "test.gpx"
        self.points = segment((0, 10), (1000, 10))
        self._write_gpx(self.points)
        self.road = voie(segment((0, 0), (1000, 0)))

    def _write_gpx(self, points):
        raw = "<gpx><trk><trkseg>" + "".join(f'<trkpt lat="{lat}" lon="{lon}"/>' for lon, lat in points) + "</trkseg></trk></gpx>"
        self.path.write_text(raw, encoding="utf-8")

    def trace(self):
        return {"nom": "test", "chemin_gpx": str(self.path),
                "empreinte_gpx": hashlib.sha256(self.path.read_bytes()).hexdigest(),
                "segments": [self.points], "lat_lon_depart": self.points[0][::-1]}

    def test_cached_measure_parameter_recalculation_and_changed_source(self):
        with patch.object(ClientOverpass, "telecharger", return_value=response([self.road])) as download:
            first = self.trace()
            result = ajouter_goudron_osm([first], dossier_cache=self.root, en_ligne=True)
            self.assertEqual(result["calcules"], 1)
            download.assert_called_once()
            second = self.trace()
            result = ajouter_goudron_osm([second], dossier_cache=self.root, en_ligne=False)
            self.assertEqual(result["cache"], 1)
            self.assertEqual(first["distance_goudron_m"], second["distance_goudron_m"])
            changed = self.trace()
            result = ajouter_goudron_osm([changed], dossier_cache=self.root, en_ligne=False, marge=5)
            self.assertEqual(result["calcules"], 1)
            self.assertEqual(changed["distance_goudron_m"], 0)
            download.assert_called_once()
            self.points = segment((0, 10), (750, 10))
            self._write_gpx(self.points)
            third = self.trace()
            ajouter_goudron_osm([third], dossier_cache=self.root, en_ligne=True)
            self.assertEqual(download.call_count, 2)
            self.assertAlmostEqual(third["distance_goudron_m"], 750, delta=1)

    def test_offline_or_service_failure_has_no_fake_zero(self):
        with patch.object(ClientOverpass, "telecharger", side_effect=ValueError("Service occupé")) as download:
            offline = self.trace()
            ajouter_goudron_osm([offline], dossier_cache=self.root, en_ligne=False)
            download.assert_not_called()
            self.assertNotIn("distance_goudron_m", offline)
            online = self.trace()
            ajouter_goudron_osm([online], dossier_cache=self.root, en_ligne=True)
            self.assertNotIn("distance_goudron_m", online)
            cache = json.loads((self.root / "goudron_osm_v1.json").read_text(encoding="utf-8"))
            self.assertEqual(cache["mesures"], {})
        with patch.object(ClientOverpass, "telecharger", return_value=response([self.road])):
            resumed = self.trace()
            ajouter_goudron_osm([resumed], dossier_cache=self.root, en_ligne=True)
            self.assertGreater(resumed["distance_goudron_m"], 990)

    def test_overpass_partial_response_rejected(self):
        with patch("goudron_osm.urlopen") as opener:
            opener.return_value.__enter__.return_value.read.return_value = json.dumps({
                "elements": [], "remark": "runtime error: Query timed out"}).encode("utf-8")
            with self.assertRaisesRegex(ValueError, "incomplète"):
                ClientOverpass().telecharger("query")

    def test_overpass_waits_and_retries_after_rate_limit(self):
        success = MagicMock()
        success.__enter__.return_value.read.return_value = json.dumps(response([self.road])).encode("utf-8")
        failure = HTTPError("https://example.org", 429, "Busy", {"Retry-After": "45"}, None)
        with patch("goudron_osm.urlopen", side_effect=[failure, success]), \
                patch("goudron_osm.time.sleep") as sleep, \
                patch("goudron_osm.time.monotonic", return_value=0):
            client = ClientOverpass()
            self.assertEqual(client.telecharger("query")["elements"], [self.road])
            self.assertEqual(client.appels, 2)
            self.assertIn(unittest.mock.call(45), sleep.call_args_list)

    def test_overpass_retries_are_bounded(self):
        failure = HTTPError("https://example.org", 429, "Busy", {}, None)
        with patch("goudron_osm.urlopen", side_effect=failure), \
                patch("goudron_osm.time.sleep") as sleep, \
                patch("goudron_osm.time.monotonic", return_value=0):
            client = ClientOverpass()
            with self.assertRaisesRegex(ValueError, "HTTP 429"):
                client.telecharger("query")
            self.assertEqual(client.appels, 4)
            waits = [args[0][0] for args in sleep.call_args_list if args[0][0] > 3]
            self.assertEqual(waits, [30, 60, 120])
        long_wait = HTTPError("https://example.org", 429, "Busy", {"Retry-After": "3600"}, None)
        with patch("goudron_osm.urlopen", side_effect=long_wait), \
                patch("goudron_osm.time.sleep") as sleep:
            with self.assertRaisesRegex(ValueError, "HTTP 429"):
                ClientOverpass().telecharger("query")
            sleep.assert_not_called()

    def test_expired_or_malformed_cache_cannot_hide_missing_data(self):
        with patch.object(ClientOverpass, "telecharger", return_value=response([self.road])):
            ajouter_goudron_osm([self.trace()], dossier_cache=self.root, en_ligne=True)
        path = self.root / "goudron_osm_v1.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        for record in list(data["mesures"].values()) + list(data["sources"].values()):
            record["goudron_date"] = "2000-01-01T00:00:00+00:00"
        path.write_text(json.dumps(data), encoding="utf-8")
        trace = self.trace()
        ajouter_goudron_osm([trace], dossier_cache=self.root, en_ligne=False)
        self.assertNotIn("distance_goudron_m", trace)
        path.write_text("invalid", encoding="utf-8")
        ajouter_goudron_osm([self.trace()], dossier_cache=self.root, en_ligne=False)

    def test_html_unknown_surface_and_lower_bound(self):
        results = [
            {"nom": "unknown", "distance_goudron_m": 0, "goudron_incertain_m": 1000},
            {"nom": "mixed", "distance_goudron_m": 1234, "goudron_incertain_m": 2000},
            {"nom": "none", "distance_goudron_m": 0, "goudron_incertain_m": 0},
        ]
        html = generer_tableau_bord(results, self.root / "test.html").read_text(encoding="utf-8")
        from test_tableau_bord import Table
        rows = {result[0]: result for result in Table(html).rows}
        self.assertTrue(any("≥ 1,2 km" in row[7] for row in rows.values()))
        self.assertTrue(any("—1,0 km incertains" in row[7] for row in rows.values()))
        self.assertTrue(any(row[7] == "0,0 km" for row in rows.values()))
        self.assertIn("15 m", html)
        self.assertIn("30°", html)


if __name__ == "__main__":
    unittest.main()
