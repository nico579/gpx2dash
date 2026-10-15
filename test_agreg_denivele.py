"""Contrôles hors réseau du calcul et de l'intégration KML."""
import concurrent.futures
import json
from pathlib import Path
import re
import shutil
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

import numpy as np
import gpxpy
import requests
import gpx2dash as agreg
from denivele_gpx2elev import MODELE_REFUSE, SOURCE_REFUSEE, calculer_denivele
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

    def _traiter_avec_modele(self, path, tolerance=10):
        def dem(brut, cache):
            return calculer_denivele(brut, cache, reader=Reader())
        with patch.object(agreg, 'calculer_denivele', dem):
            return agreg.extraire_et_reduire((str(path), tolerance))

    def test_processed_trace_survives_rename_without_reprocessing(self):
        path = self.directory / 'avant.gpx'
        path.write_bytes(fixture())
        first = self._traiter_avec_modele(path)
        first['ville'] = 'Test'
        agreg.ecrire_cache_trace(first)
        renamed = path.rename(self.directory / '2026-01-02_apres.gpx')
        with patch.object(agreg, 'calculer_denivele', side_effect=AssertionError), \
                patch.object(agreg.gpxpy, 'parse', side_effect=AssertionError):
            again = agreg.extraire_et_reduire((str(renamed), 10, {'cache_seulement': True}))
        self.assertTrue(again['cache_a_jour'])
        # La date tirée du nom suit le fichier ; le reste vient du contenu.
        self.assertEqual((again['nom'], again['date'], again['ville']), ('2026-01-02_apres', '2026-01-02', 'Test'))
        self.assertEqual(again['denivele_exact'], first['denivele_exact'])

    def test_new_tolerance_resimplifies_without_recomputing_elevation(self):
        path = self.directory / 'tolerance.gpx'
        path.write_bytes(fixture())
        first = self._traiter_avec_modele(path)
        agreg.ecrire_cache_trace(first)
        with patch.object(agreg, 'calculer_denivele', side_effect=AssertionError):
            fine = agreg.extraire_et_reduire((str(path), 5))
            with patch.object(agreg.gpxpy, 'parse', side_effect=AssertionError):
                # argparse garde le défaut entier (10) mais lit « --tolerance 10 » comme 10.0.
                typed = agreg.extraire_et_reduire((str(path), 10.0))
        self.assertEqual(set(fine['segments_par_tolerance']), {'10', '5'})
        self.assertEqual(fine['chemin_cache'], first['chemin_cache'])
        self.assertEqual(typed['segments'], first['segments'])

    def test_gps_fallback_is_retried_except_with_from_cache(self):
        path = self.directory / 'secours.gpx'
        path.write_bytes(fixture())
        with patch.object(agreg, 'calculer_denivele', lambda brut, cache: calculer_denivele(brut, cache, online=False)):
            first = agreg.extraire_et_reduire((str(path), 10))
        self.assertEqual(first['source_denivele'], 'GPX')
        agreg.ecrire_cache_trace(first)
        with patch.object(agreg, 'calculer_denivele', return_value=first) as compute:
            agreg.extraire_et_reduire((str(path), 10))
            compute.assert_called_once()
            agreg.extraire_et_reduire((str(path), 10, {'statistiques_cache': True, 'altitudes_en_ligne': False}))
            compute.assert_called_once()

    def test_transient_fallback_is_retried_until_the_better_model_answers(self):
        busy = requests.Response()
        busy.status_code = 503

        class Panne(Reader):
            ign_en_panne = True

            def read(self, source, coordinates, progress):
                if source == Source.IGN and self.ign_en_panne:
                    self.calls.append(source)
                    raise requests.HTTPError("503 Server Error", response=busy)
                return super().read(source, coordinates, progress)

        lecteur = Panne()
        def dem(brut, cache, **options):
            return calculer_denivele(brut, cache, reader=lecteur, **options)
        path = self.directory / 'panne.gpx'
        path.write_bytes(fixture())
        with patch.object(agreg, 'calculer_denivele', dem):
            first = agreg.extraire_et_reduire((str(path), 10))
            self.assertEqual((first['source_denivele'], first['replis_passagers']), ('MAPTERHORN', ['IGN']))
            agreg.ecrire_cache_trace(first)
            # Toujours en panne : le repli en cache sert, l'IGN reste à retenter.
            again = agreg.extraire_et_reduire((str(path), 10))
            self.assertEqual((again['source_denivele'], again['replis_passagers']), ('MAPTERHORN', ['IGN']))
        # --from-cache reprend le repli tel quel, sans réseau.
        with patch.object(agreg, 'calculer_denivele', side_effect=AssertionError):
            offline = agreg.extraire_et_reduire((str(path), 10, {'statistiques_cache': True, 'altitudes_en_ligne': False,
                                                                  'cache_seulement': True}))
            self.assertEqual(offline['source_denivele'], 'MAPTERHORN')
        lecteur.ign_en_panne = False
        with patch.object(agreg, 'calculer_denivele', dem):
            healed = agreg.extraire_et_reduire((str(path), 10))
        self.assertEqual((healed['source_denivele'], healed['replis_passagers']), ('IGN', []))
        agreg.ecrire_cache_trace(healed)
        with patch.object(agreg, 'calculer_denivele', side_effect=AssertionError):
            self.assertEqual(agreg.extraire_et_reduire((str(path), 10, {'cache_seulement': True}))['source_denivele'], 'IGN')

    def test_legacy_named_entry_is_migrated_without_recomputing_elevation(self):
        path = self.directory / 'ancienne.gpx'
        path.write_bytes(fixture())
        legacy = {k: v for k, v in self._traiter_avec_modele(path).items()
                  if k not in ('date_gpx', 'segments_par_tolerance', 'cache_a_jour')}
        legacy['ville'] = 'Ancienne'
        cache = self.directory / agreg.DOSSIER_CACHE
        (cache / f'ancienne_tol10_{agreg.ANCIENNE_VERSION_CACHE}.json').write_text(json.dumps(legacy), encoding='utf-8')
        with patch.object(agreg, 'calculer_denivele', side_effect=AssertionError):
            migrated = agreg.extraire_et_reduire((str(path), 10))
        self.assertFalse(migrated['cache_a_jour'])
        self.assertEqual(migrated['ville'], 'Ancienne')
        self.assertEqual(Path(migrated['chemin_cache']).name, f"{migrated['empreinte_gpx']}_{agreg.VERSION_CACHE}.json")

    def test_invalid_content_is_kept_as_an_error(self):
        path = self.directory / 'illisible.gpx'
        path.write_bytes(b'pas un GPX')
        first = agreg.extraire_et_reduire((str(path), 10))
        self.assertTrue(first['erreur_definitive'])
        agreg.ecrire_cache_trace(first)
        with patch.object(agreg.gpxpy, 'parse', side_effect=AssertionError):
            again = agreg.extraire_et_reduire((str(path), 10, {'cache_seulement': True}))
        self.assertEqual(again['erreur'], first['erreur'])

    LATITUDES_TRAVERSEE = (50, 42.5, 35)

    def _traversee(self):
        """Environ 1 670 km : lisible par gpxpy, au-delà des 300 000 positions à 5 m du moteur."""
        path = self.directory / '2026-07-01_traversee.gpx'
        points = ''.join(f'<trkpt lat="{lat}" lon="0.5"><ele>100</ele></trkpt>' for lat in self.LATITUDES_TRAVERSEE)
        path.write_text(f'<gpx version="1.1" creator="test"><trk><trkseg>{points}</trkseg></trk></gpx>',
                        encoding='utf-8')
        return path

    def test_trace_refused_by_the_engine_keeps_its_geometry(self):
        path = self._traversee()
        with patch.object(agreg, 'calculer_denivele', lambda brut, cache: calculer_denivele(brut, cache, online=False)):
            first = agreg.extraire_et_reduire((str(path), 10))
        self.assertNotIn('erreur', first)
        self.assertEqual((first['source_denivele'], first['denivele_pos']), (SOURCE_REFUSEE, None))
        self.assertIn('Trace trop longue', first['erreur_modeles'])
        attendu = distances(np.array([[lat, .5] for lat in self.LATITUDES_TRAVERSEE]))[-1]
        self.assertAlmostEqual(first['distance_m'], float(attendu))
        self.assertTrue(first['segments'])
        agreg.ecrire_cache_trace(first)
        # Le refus ne dépend que du contenu et de la version du moteur : il est repris
        # du cache, puis retenté avec une autre version, qui pourrait accepter la trace.
        with patch.object(agreg, 'calculer_denivele', side_effect=AssertionError):
            again = agreg.extraire_et_reduire((str(path), 10, {'cache_seulement': True}))
        self.assertEqual((again['source_denivele'], again['distance_m']), (SOURCE_REFUSEE, first['distance_m']))
        with patch.object(agreg, 'VERSION_GPX2ELEV', '99.0.0'):
            self.assertIsNone(agreg.extraire_et_reduire((str(path), 10, {'cache_seulement': True})))

    def test_refused_trace_reaches_kml_and_dashboard(self):
        import reverse_geocoder
        self._traversee()
        output = self.directory / 'output.kml'
        with patch.object(agreg, 'calculer_denivele', lambda brut, cache: calculer_denivele(brut, cache, online=False)), \
                patch.object(agreg.concurrent.futures, 'ProcessPoolExecutor', concurrent.futures.ThreadPoolExecutor), \
                patch.object(reverse_geocoder, 'search', return_value=[{'name': 'Test'}]):
            resultats = agreg.fusionner_gpx_vers_kml_parallele(str(self.directory), str(output), routes_en_ligne=False)
        self.assertNotIn('erreur', resultats[0])
        ns = {'k': 'http://www.opengis.net/kml/2.2'}
        noms = [n.text for n in ET.parse(output).getroot().findall('.//k:Placemark/k:name', ns)]
        self.assertEqual(len(noms), 1)
        self.assertIn('_D+?_', noms[0])
        html = output.with_suffix('.html').read_text(encoding='utf-8')
        self.assertNotIn('data-row-i18n="Trace illisible"', html)
        self.assertIn(f'title="{MODELE_REFUSE}"', html)

    def test_elevation_cache_is_never_trimmed(self):
        with patch('gpx2elev.providers.trim_cache') as trim:
            calculer_denivele(fixture(), self.directory / 'gpx2elev', reader=Reader())
        trim.assert_not_called()

    def test_cache_clear_removes_only_gpx2dash_files(self):
        cache = self.directory / 'cache'
        for name in ('gpx2elev/tiles/t.webp', 'gpx2elev/profiles/p.profile', 'goudron_osm/a.json',
                     'goudron_osm_v1.json', 'trajets_osrm_v1.json', agreg.FICHIER_CACHE_COMMUN,
                     f'{"0" * 64}_{agreg.VERSION_CACHE}.json',
                     f'trace_tol10_{agreg.ANCIENNE_VERSION_CACHE}.json', 'tmp1234.part', 'notes.txt', 'trace.gpx'):
            (cache / name).parent.mkdir(parents=True, exist_ok=True)
            (cache / name).write_text('x', encoding='utf-8')
        self.assertEqual(agreg.vider_cache(cache), 8)
        self.assertEqual(sorted(p.name for p in cache.iterdir()), ['notes.txt', 'trace.gpx'])

    def test_cache_clear_cannot_be_combined_with_from_cache(self):
        with patch('sys.argv', ['gpx2dash.py', str(self.directory), '--cache-clear', '--from-cache']), \
                patch('sys.stderr'), self.assertRaises(SystemExit):
            agreg.main()

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
        cache = next((self.directory / agreg.DOSSIER_CACHE).glob(f'*_{agreg.VERSION_CACHE}.json'))
        self.assertIsNone(json.loads(cache.read_text(encoding='utf-8'))['denivele_pos'])

    def test_second_run_starts_no_worker_and_reads_no_gpx(self):
        import reverse_geocoder
        (self.directory / 'a.gpx').write_bytes(fixture())
        output = self.directory / 'output.kml'
        def dem(brut, cache):
            return calculer_denivele(brut, cache, reader=Reader())
        with patch.object(agreg, 'calculer_denivele', dem), \
                patch.object(agreg.concurrent.futures, 'ProcessPoolExecutor', concurrent.futures.ThreadPoolExecutor), \
                patch.object(reverse_geocoder, 'search', return_value=[{'name': 'Test'}]):
            agreg.fusionner_gpx_vers_kml_parallele(str(self.directory), str(output), routes_en_ligne=False)
        first = output.read_bytes()
        with patch.object(agreg, 'calculer_denivele', side_effect=AssertionError), \
                patch.object(agreg.gpxpy, 'parse', side_effect=AssertionError), \
                patch.object(agreg.concurrent.futures, 'ProcessPoolExecutor', side_effect=AssertionError), \
                patch.object(reverse_geocoder, 'search', side_effect=AssertionError):
            agreg.fusionner_gpx_vers_kml_parallele(str(self.directory), str(output), routes_en_ligne=False)
        # simplekml numérote ses éléments par processus : seuls ces numéros diffèrent.
        def sans_ids(kml):
            return re.sub(rb'(id="|#)\d+', rb'\1', kml)
        self.assertEqual(sans_ids(output.read_bytes()), sans_ids(first))

    def test_trace_cache_survives_an_interrupted_network_phase(self):
        import reverse_geocoder
        (self.directory / 'a.gpx').write_bytes(fixture())
        output = self.directory / 'output.kml'
        def dem(brut, cache):
            return calculer_denivele(brut, cache, reader=Reader())
        # Ctrl+C pendant une longue attente d'Overpass : le travail des traces reste acquis.
        with patch.object(agreg, 'calculer_denivele', dem), \
                patch.object(agreg.concurrent.futures, 'ProcessPoolExecutor', concurrent.futures.ThreadPoolExecutor), \
                patch.object(reverse_geocoder, 'search', return_value=[{'name': 'Test'}]), \
                patch.object(agreg, 'ajouter_goudron_osm', side_effect=KeyboardInterrupt), \
                self.assertRaises(KeyboardInterrupt):
            agreg.fusionner_gpx_vers_kml_parallele(str(self.directory), str(output), routes_en_ligne=False)
        cache = next((self.directory / agreg.DOSSIER_CACHE).glob(f'*_{agreg.VERSION_CACHE}.json'))
        entree = json.loads(cache.read_text(encoding='utf-8'))
        self.assertEqual((entree['ville'], entree['source_denivele']), ('Test', 'IGN'))

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
