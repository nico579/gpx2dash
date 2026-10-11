"""Ouvre le tableau via HTTP local pour le fond OpenStreetMap et les GPX."""
import argparse
from hashlib import sha256
from html import escape
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import shutil
from threading import Lock
from urllib.error import URLError
from urllib.parse import quote, urljoin, urlsplit
from urllib.request import url2pathname, urlopen
import webbrowser

HOTE = "127.0.0.1"
PORT = 8765


class LiensGPX(HTMLParser):
    """Expose uniquement les fichiers GPX explicitement liés par le tableau."""

    def __init__(self, tableau):
        super().__init__()
        self.base = tableau.as_uri()
        self.remplacements = {}
        self.fichiers = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag != "a" or "download" not in attrs or not attrs.get("href"):
            return
        url = urlsplit(urljoin(self.base, attrs["href"]))
        if url.scheme != "file" or url.netloc not in ("", "localhost"):
            return
        fichier = Path(url2pathname(url.path)).resolve()
        if fichier.suffix.lower() != ".gpx":
            return
        identifiant = sha256(str(fichier).encode("utf-8")).hexdigest()[:16]
        lien = "/gpx/" + identifiant + "/" + quote(fichier.name, safe="")
        self.fichiers[lien] = fichier
        balise = self.get_starttag_text()
        self.remplacements[balise] = re.sub(
            r'\bhref="[^"]*"', lambda _: 'href="' + escape(lien, quote=True) + '"', balise, count=1)


class TableauHTTP:
    def __init__(self, tableau):
        self.tableau = Path(tableau).resolve()
        self.identifiant = sha256(str(self.tableau).encode("utf-8")).hexdigest()
        self.verrou = Lock()
        self.signature = None
        self.contenu = b""
        self.fichiers = {}
        self.lire()

    def lire(self):
        with self.verrou:
            stat = self.tableau.stat()
            signature = (stat.st_mtime_ns, stat.st_size)
            if signature != self.signature:
                html = self.tableau.read_text(encoding="utf-8")
                parser = LiensGPX(self.tableau)
                parser.feed(html)
                html = re.sub(r'<a\b[^>]*\bdownload\b[^>]*>',
                              lambda match: parser.remplacements.get(match.group(), match.group()), html)
                self.contenu = html.encode("utf-8")
                self.fichiers = parser.fichiers
                self.signature = signature
            return self.contenu, self.fichiers


def creer_serveur(tableau, port=PORT):
    catalogue = TableauHTTP(tableau)

    class Gestionnaire(BaseHTTPRequestHandler):
        server_version = "GPX2DASH/1.0"
        sys_version = ""

        def log_message(self, format, *args):
            pass

        def do_HEAD(self):
            self.repondre(False)

        def do_GET(self):
            self.repondre(True)

        def entetes(self, taille, type_contenu, *, telechargement=None):
            self.send_response(200)
            self.send_header("Content-Type", type_contenu)
            self.send_header("Content-Length", str(taille))
            self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
            self.send_header("X-Content-Type-Options", "nosniff")
            if telechargement:
                self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" +
                                 quote(telechargement, safe=""))
            else:
                self.send_header("Cache-Control", "no-cache")
            self.end_headers()

        def repondre(self, corps):
            if urlsplit("//" + self.headers.get("Host", "")).hostname not in (HOTE, "localhost"):
                self.send_error(400)
                return
            chemin = urlsplit(self.path).path
            if chemin == "/_gpx2dash":
                contenu = json.dumps({"application": "gpx2dash", "tableau": catalogue.identifiant}).encode()
                self.entetes(len(contenu), "application/json")
                if corps:
                    self.wfile.write(contenu)
                return
            if chemin == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
                return
            try:
                contenu, fichiers = catalogue.lire()
                if chemin in ("/", "/" + quote(catalogue.tableau.name, safe="")):
                    self.entetes(len(contenu), "text/html; charset=utf-8")
                    if corps:
                        self.wfile.write(contenu)
                    return
                fichier = fichiers.get(chemin)
                if fichier is None:
                    self.send_error(404)
                    return
                with fichier.open("rb") as flux:
                    self.entetes(fichier.stat().st_size, "application/gpx+xml",
                                 telechargement=fichier.name)
                    if corps:
                        shutil.copyfileobj(flux, self.wfile)
            except (FileNotFoundError, IsADirectoryError, PermissionError):
                self.send_error(404)

    return ThreadingHTTPServer((HOTE, port), Gestionnaire)


def serveur_existant(tableau, port):
    try:
        with urlopen(f"http://{HOTE}:{port}/_gpx2dash", timeout=.5) as response:
            etat = json.load(response)
        identifiant = sha256(str(Path(tableau).resolve()).encode("utf-8")).hexdigest()
        return etat.get("application") == "gpx2dash" and etat.get("tableau") == identifiant
    except (URLError, TimeoutError, OSError, ValueError, AttributeError):
        return False


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tableau", nargs="?", type=Path,
                        default=Path(__file__).resolve().parent.parent / "tableau_bord.html")
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--sans-navigateur", action="store_true")
    args = parser.parse_args(argv)
    if not args.tableau.is_file():
        parser.error(f"Tableau introuvable : {args.tableau}. Générez d'abord le HTML avec gpx2dash.py.")
    if not 1 <= args.port <= 65535:
        parser.error("Le port doit être compris entre 1 et 65535.")
    serveur = None
    for port in range(args.port, min(args.port + 10, 65536)):
        if serveur_existant(args.tableau, port):
            adresse = f"http://{HOTE}:{port}/"
            print(f"Tableau déjà ouvert : {adresse}")
            if not args.sans_navigateur:
                webbrowser.open(adresse)
            return
        try:
            serveur = creer_serveur(args.tableau, port)
            break
        except OSError as error:
            if error.errno not in (13, 48, 98, 10013, 10048):
                raise
    if serveur is None:
        parser.error("Aucun port local disponible ; choisissez un autre --port.")
    adresse = f"http://{HOTE}:{serveur.server_port}/"
    print(f"Tableau : {adresse}", flush=True)
    print("Gardez cette fenêtre ouverte. Ctrl+C pour arrêter.", flush=True)
    if not args.sans_navigateur:
        webbrowser.open(adresse)
    try:
        serveur.serve_forever(poll_interval=.25)
    except KeyboardInterrupt:
        print("\nTableau fermé.")
    finally:
        serveur.server_close()


if __name__ == "__main__":
    main()
