"""Vérifie la carte combinée, les segments, l'origine et les erreurs, sans réseau."""
import base64
from pathlib import Path
import sys
from threading import Thread
from urllib.parse import parse_qs, unquote, urlsplit
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from serveur_preview import creer_serveur
from tableau_bord import generer_tableau_bord
from trajets_osrm import lien_osm
from playwright.sync_api import sync_playwright

root = Path(__file__).resolve().parent.parent
fixture = root / ".qa" / "carte_test.gpx"
fixture.write_text('<gpx><trk><trkseg><trkpt lat="43.295" lon="5.630"/><trkpt lat="43.300" lon="5.640"/></trkseg></trk></gpx>', encoding="utf-8")
results = [
    {"nom": "Trace de test avec deux segments", "ville": "Gémenos", "lat_lon_depart": [43.295, 5.63],
     "chemin_gpx": str(fixture), "segments": [[[5.63, 43.295], [5.64, 43.30], [5.635, 43.305]],
                                           [[5.66, 43.31], [5.665, 43.305]]]},
    {"nom": "Trace de test Brignoles", "ville": "Brignoles", "lat_lon_depart": [43.40, 6.061],
     "segments": [[[6.061, 43.40], [6.065, 43.41], [6.071, 43.415]]]},
    {"nom": "Trace de test Méounes", "ville": "Méounes", "lat_lon_depart": [43.268, 5.971],
     "segments": [[[5.971, 43.268], [5.97, 43.27], [5.975, 43.28]]]},
]
for result in results:
    result["itineraire_url"] = lien_osm(result["lat_lon_depart"])
output = generer_tableau_bord(results, root / ".qa" / "carte_exemple.html")
output.write_text(output.read_text(encoding="utf-8").replace(
    'name="referrer" content="strict-origin-when-cross-origin"',
    'name="referrer" content="no-referrer"'), encoding="utf-8")
png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")
server = creer_serveur(output, 0)
thread = Thread(target=lambda: server.serve_forever(poll_interval=.02), daemon=True)
thread.start()
base = f"http://127.0.0.1:{server.server_port}/"
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True, channel="msedge")
    page = browser.new_page(viewport={"width": 1440, "height": 1050})
    errors, route_requests, tile_requests = [], [], []
    mode = {"value": "ok", "tiles": "ok"}
    page.on("pageerror", lambda error: errors.append(str(error)))
    def tiles(route):
        assert not route.request.headers.get("referer"), route.request.headers
        tile_requests.append(route.request.url)
        if mode["tiles"] == "mixed" and len(tile_requests) % 2 == 0:
            route.fulfill(status=403, content_type="text/plain", body="Access blocked")
        else:
            route.fulfill(content_type="image/png", body=png)
    def routing(route):
        query = parse_qs(urlsplit(route.request.url).query)
        if "/table/" in route.request.url:
            size = len(query["destinations"][0].split(";"))
            route.fulfill(json={"code": "Ok", "distances": [[10000] * size], "durations": [[900] * size],
                               "sources": [{"distance": 5}], "destinations": [{"distance": 10}] * size})
            return
        route_requests.append(route.request.url)
        if mode["value"] == "error":
            route.fulfill(status=503, json={})
            return
        if mode["value"] == "pending":
            return
        assert query["geometries"] == ["geojson"] and query["overview"] == ["full"]
        coords = [[float(v) for v in point.split(",")]
                  for point in unquote(urlsplit(route.request.url).path).split("/")[-1].split(";")]
        route.fulfill(json={"code": "Ok", "routes": [{"distance": 44000, "duration": 2800,
                      "geometry": {"type": "LineString", "coordinates": [coords[0], [6.0, 43.31], coords[1]]}}],
                      "waypoints": [{"distance": 5}, {"distance": 10}]})
    page.route("https://*.tile.opentopomap.org/**", tiles)
    page.route("https://routing.openstreetmap.de/**", routing)
    page.route("https://photon.komoot.io/**", lambda route: route.fulfill(json={"features": [{
        "properties": {"name": "Hyères", "country": "France", "osm_value": "city"},
        "geometry": {"coordinates": [6.128, 43.119]}}]}))
    page.goto(base)
    assert not route_requests and not tile_requests
    def open_map(name):
        page.locator(f'tr[data-id="{name}"] .route-link').click()
        assert page.locator("#map-dialog").is_visible()
        page.wait_for_function("document.querySelector('#trace-map').dataset.road !== 'loading'")
    first = results[0]["nom"]
    open_map(first)
    assert page.locator("#map-title").inner_text() == first
    assert page.locator("#trace-map .gpx-path").count() == 1
    assert page.locator(".gpx-path").get_attribute("d").count("M") == 2
    assert page.locator("#trace-map .road-path").count() == 1
    assert len(page.context.pages) == 1
    download_url = page.locator("#map-download").get_attribute("href")
    assert download_url.startswith(base + "gpx/")
    assert page.request.get(download_url).body() == fixture.read_bytes()
    before = page.locator(".gpx-path").first.evaluate("path => path.getBoundingClientRect().width")
    page.locator("#map-trace").click()
    after = page.locator(".gpx-path").first.evaluate("path => path.getBoundingClientRect().width")
    assert after > before
    page.locator("#map-overview").click()
    page.locator("#map-close").click()
    assert not page.locator("#map-dialog").is_visible()
    assert page.evaluate("document.body.style.overflow") == ""
    open_map(first)
    assert len(route_requests) == 1
    page.keyboard.press("Escape")
    assert not page.locator("#map-dialog").is_visible()
    page.locator("#route-city").fill("Hyères")
    page.locator("#city-search").click()
    page.wait_for_function("!document.querySelector('#calculate-routes').disabled")
    page.locator("#calculate-routes").click()
    page.wait_for_function("!document.querySelector('#calculate-routes').disabled")
    open_map(first)
    assert page.locator("#trace-map").get_attribute("data-origin") == "43.119,6.128"
    assert "/6.128000,43.119000;" in route_requests[-1]
    assert "Hyères" in page.locator("#map-origin").inner_text()
    assert page.locator(".gpx-path").count() == 1 and page.locator(".road-path").count() == 1
    page.locator("#map-close").click()
    mode["value"] = "error"
    open_map(results[1]["nom"])
    assert page.locator(".gpx-path").count() == 1
    assert page.locator(".road-path").count() == 0
    assert "HTTP 503" in page.locator("#map-status").inner_text()
    page.locator("#map-close").click()
    mode["value"] = "pending"
    page.locator(f'tr[data-id="{results[2]["nom"]}"] .route-link').click()
    page.locator("#map-close").click()
    mode["value"] = "ok"
    page.set_viewport_size({"width": 390, "height": 844})
    open_map(first)
    assert page.locator(".road-path").count() == 1 and page.locator(".gpx-path").count() == 1
    box = page.locator("#map-dialog").bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= 390
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.locator("#map-close").click()
    mode["tiles"] = "mixed"
    page.goto(base)
    open_map(first)
    page.wait_for_function("document.querySelectorAll('.leaflet-tile').length > 0 && "
                           "[...document.querySelectorAll('.leaflet-tile')].every(tile => tile.complete)")
    assert page.locator("#map-tiles-note").is_visible()
    page.locator("#map-close").click()
    assert not errors, errors
    browser.close()
server.shutdown()
server.server_close()
thread.join()
print("Carte combinée OK : deux segments distincts, route, zooms, téléchargement, cache, changement de ville, échec, fermeture, mobile, fond OpenTopoMap chargé sans référent et erreurs de tuiles.")
