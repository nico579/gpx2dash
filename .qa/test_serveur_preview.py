"""Vérifie l'ouverture HTTP locale et les téléchargements GPX du catalogue."""
from http.client import HTTPConnection
from pathlib import Path
import tempfile
import sys
from threading import Thread
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from serveur_preview import LiensGPX, creer_serveur, main, serveur_existant
from tableau_bord import generer_tableau_bord


class ServeurLocalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.gpx = root / "source" / "été #&.GPX"
        self.gpx.parent.mkdir()
        self.gpx.write_bytes(b'<gpx><trk><name>Original</name></trk></gpx>')
        self.tableau = root / "sortie" / "tableau test.html"
        self.resultat = {"nom": "Une trace", "chemin_gpx": str(self.gpx)}
        generer_tableau_bord([self.resultat], self.tableau)
        self.serveur = creer_serveur(self.tableau, 0)
        self.thread = Thread(target=lambda: self.serveur.serve_forever(poll_interval=.02), daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.serveur.server_port}"

    def tearDown(self):
        self.serveur.shutdown()
        self.serveur.server_close()
        self.thread.join()
        self.temp.cleanup()

    def lire(self, chemin="/"):
        return urlopen(self.base + chemin, timeout=2)

    def lien_gpx(self):
        with self.lire() as response:
            html = response.read().decode("utf-8")
        parser = LiensGPX(self.tableau)
        parser.feed(self.tableau.read_text(encoding="utf-8"))
        lien = next(iter(parser.fichiers))
        self.assertIn(f'href="{lien}" download', html)
        return lien

    def test_html_et_referent(self):
        with self.lire() as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers["Content-Type"], "text/html; charset=utf-8")
            self.assertEqual(response.headers["Referrer-Policy"], "strict-origin-when-cross-origin")
            html = response.read().decode("utf-8")
            self.assertIn('name="referrer" content="strict-origin-when-cross-origin"', html)
            self.assertIn("Une trace", html)

    def test_gpx_original_hors_du_dossier_html(self):
        lien = self.lien_gpx()
        with self.lire(lien) as response:
            self.assertEqual(response.read(), self.gpx.read_bytes())
            self.assertEqual(response.headers["Content-Type"], "application/gpx+xml")
            self.assertIn("filename*=UTF-8''", response.headers["Content-Disposition"])
        connection = HTTPConnection("127.0.0.1", self.serveur.server_port, timeout=2)
        try:
            connection.request("HEAD", lien)
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(int(response.getheader("Content-Length")), self.gpx.stat().st_size)
            self.assertEqual(response.read(), b"")
        finally:
            connection.close()

    def test_pas_de_fichiers_hors_catalogue(self):
        (self.tableau.parent / "prive.txt").write_text("confidentiel", encoding="utf-8")
        for chemin in ("/prive.txt", "/.cache_gpx/", "/source/",
                       "/gpx/../source/ete.gpx", "/gpx/%2e%2e/prive.txt",
                       "/ouvrir_tableau.py"):
            with self.subTest(chemin=chemin):
                with self.assertRaises(HTTPError) as error:
                    self.lire(chemin)
                self.assertEqual(error.exception.code, 404)
                error.exception.close()

    def test_rechargement_du_tableau_sans_redemarrage(self):
        premier_lien = self.lien_gpx()
        generer_tableau_bord([self.resultat, {"nom": "Nouvelle trace"}], self.tableau)
        with self.lire() as response:
            self.assertIn("Nouvelle trace", response.read().decode("utf-8"))
        self.assertEqual(self.lien_gpx(), premier_lien)

    def test_detection_du_serveur_pour_le_meme_tableau(self):
        self.assertTrue(serveur_existant(self.tableau, self.serveur.server_port))
        self.assertFalse(serveur_existant(self.tableau.with_name("autre.html"), self.serveur.server_port))

    def test_port_windows_reserve(self):
        faux_serveur = Mock(server_port=8766)
        with patch("serveur_preview.serveur_existant", return_value=False), \
             patch("serveur_preview.creer_serveur", side_effect=[
                 PermissionError(13, "Port réservé par Windows"), faux_serveur]) as creation:
            main([str(self.tableau), "--sans-navigateur"])
        self.assertEqual(creation.call_args.args[1], 8766)
        faux_serveur.server_close.assert_called_once()

    def test_hote_local_uniquement(self):
        connection = HTTPConnection("127.0.0.1", self.serveur.server_port, timeout=2)
        try:
            connection.request("GET", "/", headers={"Host": "autre-site.example"})
            response = connection.getresponse()
            self.assertEqual(response.status, 400)
            response.read()
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
