"""Contrôles hors réseau du calcul et de l'intégration KML."""
import concurrent.futures
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

import numpy as np
import gpxpy
import gpx2dash as agreg
from denivele_gpx2elev import calculer_denivele
from gpx2elev.core import distances, parse_gpx, prepare
from gpx2elev.providers import Source


def fixture(elevations=(0, 10, 20), route=False):
    point = 'rtept' if route else 'trkpt'
    points = ''.join(f'<{point} lat="45" lon="{5 + i*.001}">' +
                     (f'<ele>{z}</ele>' if z is not None else '') +
                     f'</{point}>' for i, z in enumerate(elevations))
    body = f'<rte>{points}</rte>' if route else f'<trk><trkseg>{points}</trkseg></trk>'
    return f'<gpx version="1.1" creator="test">{body}</gpx>'.encode()


class Reader:
    def __init__(self, fail_ign=False, fail_all=False):
        self.calls = []
        self.fail_ign, self.fail_all = fail_ign, fail_all

    def read(self, source, coordinates, progress):
        self.calls.append(source)
        if self.fail_all or (self.fail_ign and source == Source.IGN):
            # Incomplete terrain must trigger a complete-model fallback.
            return np.full(len(coordinates), np.nan)
        return 100 + distances(coordinates) * .1


class ElevationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_ramp_and_cached_profile(self):
        raw = fixture()
        reader = Reader()
        result = calculer_denivele(raw, self.directory, reader=reader)
        length = prepare(parse_gpx(raw)).length
        self.assertAlmostEqual(result['denivele_exact']['Dplus_m'], length*.1, places=6)
        self.assertEqual(result['source_denivele'], 'IGN')
        cached = calculer_denivele(raw, self.directory, online=False)
        self.assertEqual(cached['denivele_exact'], result['denivele_exact'])
        self.assertEqual(result['gpx_somme_brute']['Dplus_m'], 20)

    def test_whole_trace_fallback_ranking(self):
        reader = Reader(fail_ign=True)
        result = calculer_denivele(fixture(), self.directory, reader=reader)
        self.assertEqual(reader.calls, [Source.IGN, Source.MAPTERHORN])
        self.assertEqual(result['source_denivele'], 'MAPTERHORN')
        self.assertEqual(result['replis'][0]['modele'], 'IGN LiDAR HD')

    def test_all_models_fail_explicit_gpx_fallback(self):
        reader = Reader(fail_all=True)
        result = calculer_denivele(fixture(), self.directory, reader=reader)
        self.assertEqual(reader.calls, list(Source))
        self.assertEqual(result['source_denivele'], 'GPX')
        self.assertAlmostEqual(result['denivele_exact']['Dplus_m'], 20, places=6)
        self.assertIsNotNone(result['erreur_modeles'])

    def test_missing_gpx_elevation_is_unknown_not_zero(self):
        result = calculer_denivele(fixture((None, 10, 20)), self.directory,
                                  reader=Reader(fail_all=True))
        self.assertIsNone(result['denivele_pos'])
        self.assertIsNone(result['gpx_somme_brute'])
        self.assertEqual(result['source_denivele'], 'INCONNU')

    def test_disconnected_segments_no_artificial_climb(self):
        raw = b'<gpx><trk><trkseg><trkpt lat="45" lon="5"><ele>0</ele></trkpt><trkpt lat="45" lon="5.001"><ele>10</ele></trkpt></trkseg><trkseg><trkpt lat="46" lon="6"><ele>1000</ele></trkpt><trkpt lat="46" lon="6.001"><ele>1005</ele></trkpt></trkseg></trk></gpx>'
        result = calculer_denivele(raw, self.directory, online=False)
        self.assertAlmostEqual(result['denivele_exact']['Dplus_m'], 15, places=6)
        self.assertLess(result['distance_m'], 200)

    def test_stats_do_not_mutate_original_points(self):
        gpx = gpxpy.parse(fixture((0, 10000, 0)).decode())
        before = gpx.to_xml()
        agreg._calc_duree(gpx)
        self.assertEqual(gpx.to_xml(), before)

    def test_elevation_noise_while_stopped_is_not_moving_time(self):
        # 10 min à 6 km/h, puis 10 min d'arrêt où l'altitude GPS oscille de 20 m.
        points = ([(5 + i * .00127, 100) for i in range(11)] +
                  [(5 + 10 * .00127, 100 + 20 * (i % 2)) for i in range(1, 11)])
        body = ''.join(f'<trkpt lat="45" lon="{lon}"><ele>{z}</ele><time>2026-01-01T10:{i:02d}:00Z</time></trkpt>'
                       for i, (lon, z) in enumerate(points))
        gpx = gpxpy.parse(f'<gpx version="1.1" creator="test"><trk><trkseg>{body}</trkseg></trk></gpx>')
        before = gpx.to_xml()
        self.assertEqual(agreg._calc_duree(gpx), 600)
        self.assertEqual(gpx.to_xml(), before)

    def test_cache_name_same_for_default_and_typed_tolerance(self):
        # argparse garde le défaut entier (10) mais lit « --tolerance 10 » comme 10.0.
        path = self.directory / 'tolerance.gpx'
        path.write_bytes(fixture())
        with patch.object(agreg, 'calculer_denivele', return_value={}):
            noms = {Path(agreg.extraire_et_reduire((str(path), t))['chemin_cache']).name for t in (10, 10.0)}
        self.assertEqual(noms, {f'tolerance_tol10_{agreg.VERSION_CACHE}.json'})

    def test_windows_worker_and_changed_input(self):
        path = self.directory / 'worker.gpx'
        raw = fixture()
        path.write_bytes(raw)
        cache = self.directory / agreg.DOSSIER_CACHE / 'gpx2elev'
        calculer_denivele(raw, cache, reader=Reader())
        # Le vrai processus Windows réimporte l'adaptateur et retrouve le profil.
        with concurrent.futures.ProcessPoolExecutor(max_workers=1) as executor:
            result = executor.submit(agreg.extraire_et_reduire, (str(path), 10)).result(timeout=30)
        self.assertNotIn('erreur', result)
        self.assertEqual(result['source_denivele'], 'IGN')
        result['ville'] = 'Ancienne ville'
        Path(result['chemin_cache']).write_text(json.dumps(result), encoding='utf-8')
        # Modification des altitudes avec les mêmes XY : terrain en cache valide,
        # statistiques GPX recalculées et géocodage ancien non réutilisé.
        path.write_bytes(fixture((0, 20, 40)))
        changed = agreg.extraire_et_reduire((str(path), 10))
        self.assertEqual(changed['gpx_somme_brute']['Dplus_m'], 40)
        self.assertNotIn('ville', changed)

    def test_kml_route_and_unknown_value(self):
        import reverse_geocoder
        path = self.directory / 'route.gpx'
        path.write_bytes(fixture((None, None, None), route=True))
        def offline(raw, cache):
            return calculer_denivele(raw, cache, online=False)
        output = self.directory / 'output.kml'
        with patch.object(agreg, 'calculer_denivele', offline), \
                patch.object(agreg.concurrent.futures, 'ProcessPoolExecutor', concurrent.futures.ThreadPoolExecutor), \
                patch.object(reverse_geocoder, 'search', return_value=[{'name': 'Test'}]):
            agreg.fusionner_gpx_vers_kml_parallele(str(self.directory), str(output), routes_en_ligne=False)
        root = ET.parse(output).getroot()
        ns = {'k': 'http://www.opengis.net/kml/2.2'}
        self.assertEqual(len(root.findall('.//k:LineString', ns)), 1)
        self.assertIn('_D+?_', root.find('.//k:Placemark/k:name', ns).text)
        cache = next((self.directory / agreg.DOSSIER_CACHE).glob('route_tol*_v6-gpx2elev.json'))
        self.assertIsNone(json.loads(cache.read_text(encoding='utf-8'))['denivele_pos'])

    def test_real_reference_and_aggregator(self):
        desktop = Path(__file__).resolve().parent.parent / 'gpxmnt/android/desktop'
        source = Path(__file__).parent / '2026-10-04_10-30.gpx'
        cache = desktop / 'qa/reference-cache'
        if not source.exists() or not cache.exists():
            self.skipTest('Référence personnelle absente')
        result = calculer_denivele(source.read_bytes(), cache, online=False)
        self.assertEqual(result['source_denivele'], 'IGN')
        self.assertAlmostEqual(result['denivele_exact']['Dplus_m'], 735.1285660253573, places=7)
        self.assertAlmostEqual(result['denivele_exact']['Dmoins_m'], 735.1495651743335, places=7)
        self.assertAlmostEqual(result['gpx_somme_brute']['Dplus_m'], 3380.71, places=6)
        self.assertAlmostEqual(result['gpx_filtre']['Dplus_m'], 1165.4629988478032, places=7)
        copy = self.directory / source.name
        shutil.copyfile(source, copy)
        with patch.object(agreg, 'calculer_denivele', return_value=result):
            reduced = agreg.extraire_et_reduire((str(copy), 10))
        self.assertNotIn('erreur', reduced)
        self.assertEqual(reduced['denivele_pos'], 735)
        self.assertAlmostEqual(reduced['distance_m'], 22325.61987711584, places=6)
        (self.directory / 'validation_reference.json').write_text(json.dumps(result, indent=2), encoding='utf-8')


if __name__ == '__main__':
    unittest.main(verbosity=2)
