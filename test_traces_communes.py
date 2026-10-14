"""Portions continues, tolérance, segments séparés, relations et cache."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pyproj import Transformer
from shapely.geometry import LineString

from traces_communes import (FICHIER_CACHE_COMMUN, ajouter_traces_communes,
                            mesurer_portion_commune, parametres_valides)


def ligne(*points):
    return LineString(points)


class GeometryTests(unittest.TestCase):
    def test_partial_shared_portion_and_reverse_direction(self):
        a = [ligne((0, 0), (1000, 0))]
        b = [ligne((800, 0), (200, 0))]
        self.assertAlmostEqual(mesurer_portion_commune(a, b), 600)
        self.assertAlmostEqual(mesurer_portion_commune(b, a), 600)

    def test_tolerance_in_metres(self):
        a = [ligne((0, 0), (1000, 0))]
        for offset, expected in ((14.9, 1000), (15, 1000), (15.1, 0)):
            with self.subTest(offset=offset):
                self.assertAlmostEqual(mesurer_portion_commune(a, [ligne((0, offset), (1000, offset))]), expected)

    def test_crossing_is_not_a_hundred_metre_common_portion(self):
        shared = mesurer_portion_commune([ligne((-500, 0), (500, 0))],
                                        [ligne((0, -500), (0, 500))])
        self.assertAlmostEqual(shared, 30)
        self.assertLess(shared, 100)

    def test_disconnected_segments_are_not_joined_or_added(self):
        a = [ligne((0, 0), (60, 0)), ligne((1000, 0), (1060, 0))]
        b = [ligne((0, 0), (1060, 0))]
        self.assertAlmostEqual(mesurer_portion_commune(a, b), 60)

    def test_repeated_pass_does_not_multiply_common_length(self):
        a = [ligne((0, 0), (60, 0), (0, 0), (60, 0), (0, 0))]
        b = [ligne((0, 0), (60, 0))]
        self.assertAlmostEqual(mesurer_portion_commune(a, b), 60)


class CacheTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.inverse = Transformer.from_crs(32632, 4326, always_xy=True)

    def trace(self, name, points):
        coordinates = [list(self.inverse.transform(260000 + x, 4800000 + y)) for x, y in points]
        xml = '<gpx><trk><trkseg>' + ''.join(
            f'<trkpt lon="{lon}" lat="{lat}"/>' for lon, lat in coordinates) + '</trkseg></trk></gpx>'
        raw = xml.encode("utf-8")
        path = self.root / (name + ".gpx")
        path.write_bytes(raw)
        return {"nom": name, "chemin_gpx": str(path), "empreinte_gpx": hashlib.sha256(raw).hexdigest(),
                "segments": [coordinates]}

    def compute(self, traces, **parameters):
        return ajouter_traces_communes(traces, dossier_cache=self.root / ".cache_gpx", **parameters)

    def test_counts_direct_neighbours_once_and_excludes_self(self):
        traces = [self.trace("a", [(0, 0), (1000, 0)]),
                  self.trace("b", [(200, 5), (800, 5)]),
                  self.trace("c", [(0, -8), (400, -8)]),
                  self.trace("crossing", [(500, -500), (500, 500)]),
                  self.trace("remote", [(0, 1000), (1000, 1000)])]
        self.compute(traces)
        self.assertEqual(traces[0]["traces_communes"], ["b", "c"])
        self.assertEqual(traces[0]["nombre_traces_communes"], 2)
        self.assertEqual(traces[1]["traces_communes"], ["a", "c"])
        self.assertEqual(traces[3]["nombre_traces_communes"], 0)
        self.assertEqual(traces[4]["nombre_traces_communes"], 0)

    def test_cache_survives_rename_restricts_to_current_files_and_reuses_lengths(self):
        a = self.trace("a", [(0, 0), (1000, 0)])
        b = self.trace("b", [(100, 5), (900, 5)])
        first = self.compute([a, b])
        self.assertEqual(first["calcules"], 1)
        b["nom"] = "renamed"
        with patch("traces_communes.segments_originaux", side_effect=AssertionError("GPX parsed again")):
            second = self.compute([a, b], longueur=900)
        self.assertEqual(second["cache"], 1)
        self.assertEqual(a["nombre_traces_communes"], 0)
        with patch("traces_communes.segments_originaux", side_effect=AssertionError):
            self.compute([a, b])
        self.assertEqual(a["traces_communes"], ["renamed"])
        self.compute([a])
        self.assertEqual(a["traces_communes"], [])
        self.assertEqual(a["nombre_traces_communes"], 0)

    def test_changed_content_and_tolerance_are_recomputed(self):
        a = self.trace("a", [(0, 0), (1000, 0)])
        b = self.trace("b", [(0, 14), (1000, 14)])
        self.compute([a, b])
        self.assertEqual(a["nombre_traces_communes"], 1)
        self.compute([a, b], marge=10)
        self.assertEqual(a["nombre_traces_communes"], 0)
        changed = self.trace("b", [(0, 40), (1000, 40)])
        self.compute([a, changed])
        self.assertEqual(a["nombre_traces_communes"], 0)

    def test_failed_comparison_remains_unknown_and_is_not_cached(self):
        a = self.trace("a", [(0, 0), (1000, 0)])
        b = self.trace("b", [(0, 5), (1000, 5)])
        Path(b["chemin_gpx"]).write_bytes(b"changed during run")
        result = self.compute([a, b])
        self.assertEqual(result["erreurs"], 1)
        self.assertNotIn("nombre_traces_communes", a)
        self.assertIn("changé", b["erreur_traces_communes"])
        self.assertFalse((self.root / ".cache_gpx" / FICHIER_CACHE_COMMUN).exists())

    def test_malformed_cache_does_not_create_false_zero(self):
        a = self.trace("a", [(0, 0), (1000, 0)])
        b = self.trace("b", [(0, 5), (1000, 5)])
        self.compute([a, b])
        path = self.root / ".cache_gpx" / FICHIER_CACHE_COMMUN
        content = json.loads(path.read_text(encoding="utf-8"))
        content["paires"] = {k: "invalid" for k in content["paires"]}
        path.write_text(json.dumps(content), encoding="utf-8")
        self.assertEqual(self.compute([a, b])["calcules"], 1)
        self.assertEqual(a["nombre_traces_communes"], 1)

    def test_invalid_parameters(self):
        for margin, minimum in ((0, 100), (float("nan"), 100), (15, 0), (15, float("inf"))):
            with self.subTest(margin=margin, minimum=minimum), self.assertRaises(ValueError):
                parametres_valides(margin, minimum)


if __name__ == "__main__":
    unittest.main()
