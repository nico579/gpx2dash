"""Browser regression for the aggregated KML map, directly from file://."""
import base64
import json
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from couleurs_traces import couleur_kml
from tableau_bord import generer_tableau_bord
from trajets_osrm import lien_osm
from playwright.sync_api import sync_playwright
import simplekml

png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")
root = Path(__file__).resolve().parent
with tempfile.TemporaryDirectory() as directory:
    folder = Path(directory)
    original = folder / "example track.gpx"
    original.write_text('<gpx><trk><trkseg><trkpt lat="43.32" lon="6.02"/><trkpt lat="43.325" lon="6.03"/></trkseg></trk></gpx>', encoding="utf-8")
    names = ["Track with two segments", "Second track", "Third track", '<img src=x onerror=alert(1)>']
    segments = [
        [[[6.02, 43.32], [6.03, 43.325]], [[6.035, 43.33], [6.04, 43.335]]],
        [[[6.10, 43.34], [6.11, 43.345]]],
        [[[6.05, 43.25], [6.06, 43.26]]],
        [[[6.13, 43.27], [6.14, 43.28]]],
    ]
    results = []
    kml = simplekml.Kml()
    for index, (name, geometry) in enumerate(zip(names, segments)):
        lon, lat = geometry[0][0]
        result = {
            "nom": name, "date": "2026-10-04", "ville": "Garéoult",
            "distance_m": [10000, 15000, 25000, 30000][index],
            "denivele_pos": 50 + index * 100, "denivele_neg": 40 + index * 100,
            "duree_s": 1800 + index * 600, "distance_route_m": 20000, "duree_route_s": 1800,
            "distance_goudron_m": 100 + index * 100, "goudron_incertain_m": 0,
            "lat_lon_depart": [lat, lon], "segments": geometry, "chemin_gpx": str(original),
            "itineraire_url": lien_osm((lat, lon)),
            "traces_communes": [names[j] for j in ((1, 2), (0,), (0,), ())[index]],
            "nombre_traces_communes": [2, 1, 1, 0][index],
        }
        results.append(result)
        track = kml.newmultigeometry(name=name)
        track.style.linestyle.color = couleur_kml(name)
        for segment in geometry:
            track.newlinestring(coords=segment)
    results.extend([{"nom": "Position only", "lat_lon_depart": [43.3, 6.0]},
                    {"nom": "Unreadable GPX", "erreur": "Invalid GPX"}])
    kml_path = folder / "all tracks.kml"
    kml.save(kml_path)
    output = generer_tableau_bord(results, folder / "dashboard.html", fichier_kml=kml_path)
    content = output.read_text(encoding="utf-8")
    payload = json.loads(content.split('type="application/json">', 1)[1].split("</script>", 1)[0])
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True,
            channel=None if os.environ.get("GPX2DASH_BROWSER") == "chromium" else "msedge")
        context = browser.new_context(locale="en-GB", accept_downloads=True, viewport={"width": 1440, "height": 1050})
        page = context.new_page()
        def popup_title():
            # Leaflet removes the previous popup after its fade animation.
            page.wait_for_function("document.querySelectorAll('.map-popup h3').length === 1")
            return page.locator(".map-popup h3").inner_text()
        errors, routes, tiles, alerts = [], [], [], []
        tile_mode = {"fail": False}
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("dialog", lambda dialog: (alerts.append(dialog.message), dialog.dismiss()))
        page.route("https://**/*", lambda route: route.abort())
        def tile_response(route):
            tiles.append(route.request.url)
            route.fulfill(status=403 if tile_mode["fail"] else 200,
                content_type="text/plain" if tile_mode["fail"] else "image/png",
                body="Blocked" if tile_mode["fail"] else png)
        def road_response(route):
            routes.append(route.request.url)
            route.fulfill(json={
                "code": "Ok", "routes": [{"distance": 20000, "duration": 1800,
                    "geometry": {"type": "LineString", "coordinates": [[6.0458, 43.3293], [6.02, 43.32]]}}],
                "waypoints": [{"distance": 0}, {"distance": 0}],
            })
        page.route("https://*.tile.opentopomap.org/**", tile_response)
        page.route("https://routing.openstreetmap.de/**", road_response)
        page.goto(output.as_uri())
        assert not routes and not tiles
        assert page.locator("#map-catalogue").inner_text() == "Aggregated KML map"
        page.locator("#map-catalogue").click()
        assert page.locator("#map-dialog").is_visible()
        assert page.locator("#map-title").inner_text() == "Aggregated KML"
        assert page.locator("#trace-map").get_attribute("data-mode") == "catalogue"
        assert page.locator("#trace-map").get_attribute("data-catalogue-count") == "4"
        assert page.locator(".catalogue-path").count() == 4
        assert page.locator(".catalogue-path").first.get_attribute("d").count("M") == 2
        assert page.locator(".road-path").count() == 0 and not routes
        colors = page.locator(".catalogue-path").evaluate_all("paths => Object.fromEntries(paths.map(p => [p.dataset.traceId, p.getAttribute('stroke')]))")
        assert colors == {trace["id"]: trace["color"] for trace in payload["traces"] if trace["segments"]}
        assert page.locator("#map-kml").is_visible()
        assert not page.locator("#map-download").is_visible()
        assert not page.locator("#map-osm").is_visible()
        assert not page.locator("#map-trace").is_visible()
        with page.expect_download() as event:
            page.locator("#map-kml").click()
        assert event.value.suggested_filename == kml_path.name
        assert Path(event.value.path()).read_bytes() == kml_path.read_bytes()
        page.locator(".catalogue-path").first.press("Enter")
        assert popup_title() == names[0]
        assert page.locator(".map-popup dt").count() == 9
        assert "10.0 km" in page.locator(".map-popup").inner_text()
        with page.expect_download() as event:
            page.locator(".map-popup a[download]").click()
        assert Path(event.value.path()).read_bytes() == original.read_bytes()
        page.locator("#language").evaluate("el => {el.value='fr'; el.dispatchEvent(new Event('change'));}")
        assert page.locator("#map-title").inner_text() == "KML agrégé"
        assert "4 / 4 trace(s)" in page.locator("#map-status").inner_text()
        assert popup_title() == names[0]
        assert "10,0 km" in page.locator(".map-popup").inner_text()
        assert page.locator("#map-only-visible").is_visible()
        page.screenshot(path=str(root / "kml_desktop.png"))
        page.locator(".map-popup button").click()
        page.wait_for_function("document.querySelector('#trace-map').dataset.road === 'ready'")
        assert len(routes) == 1
        assert page.locator("#trace-map").get_attribute("data-mode") == "trace"
        assert page.locator(".gpx-path").count() == 1 and page.locator(".road-path").count() == 1
        assert page.locator(".catalogue-path").count() == 0
        assert not page.locator("#map-filter-control").is_visible()
        assert not page.locator("#map-kml").is_visible()
        page.keyboard.press("Escape")
        assert not page.locator("#map-dialog").is_visible()
        assert page.evaluate("document.body.style.overflow") == ""
        page.locator("#filter-2-op").select_option(">")
        page.locator("#filter-2-value").fill("20")
        page.locator("#map-catalogue").click()
        assert page.locator(".catalogue-path").count() == 4
        page.locator("#map-only-visible").check()
        assert page.locator(".catalogue-path").count() == 2
        assert set(page.locator(".catalogue-path").evaluate_all("paths => paths.map(p => p.dataset.traceId)")) == set(names[2:])
        page.locator(".catalogue-path").last.press("Enter")
        assert popup_title() == names[3]
        assert page.locator(".map-popup img").count() == 0 and not alerts
        page.locator("#filter-2-value").evaluate("el => {el.value='99'; el.dispatchEvent(new Event('input'));}")
        assert page.locator(".catalogue-path").count() == 0
        assert page.locator("#trace-map").get_attribute("data-catalogue-count") == "0"
        assert "Aucune trace" in page.locator("#map-status").inner_text()
        page.locator("#map-only-visible").uncheck()
        assert page.locator(".catalogue-path").count() == 4
        page.locator("#map-overview").click()
        assert len(routes) == 1
        page.locator("#map-close").click()
        page.locator("#reset-filters").click()
        # Shared maps include the selected track and its direct neighbours, even if hidden by table filters.
        page.locator("#filter-8-op").select_option(">")
        page.locator("#filter-8-value").fill("0")
        page.locator("#filter-2-op").select_option(">")
        page.locator("#filter-2-value").fill("20")
        page.locator('tr[data-id="Third track"] .shared-tracks-link').click()
        assert page.locator("#map-dialog").is_visible()
        assert page.locator("#trace-map").get_attribute("data-mode") == "shared"
        assert page.locator("#map-title").inner_text() == "Traces communes : Third track"
        assert set(page.locator(".catalogue-path").evaluate_all("paths => paths.map(p => p.dataset.traceId)")) == {names[0], names[2]}
        widths = page.locator(".catalogue-path").evaluate_all("paths => Object.fromEntries(paths.map(p => [p.dataset.traceId, Number(p.getAttribute('stroke-width'))]))")
        assert widths[names[2]] > widths[names[0]]
        assert page.locator("#map-trace").is_visible()
        assert not page.locator("#map-filter-control").is_visible()
        assert not page.locator("#map-kml").is_visible()
        assert not page.locator("#map-osm").is_visible()
        assert len(routes) == 1
        page.locator("#map-trace").click()
        page.locator("#map-overview").click()
        page.locator("#language").evaluate("el => {el.value='en'; el.dispatchEvent(new Event('change'));}")
        assert page.locator("#map-title").inner_text() == "Shared tracks: Third track"
        assert "15 m" in page.locator("#map-status").inner_text()
        assert "100 m" in page.locator("#map-status").inner_text()
        page.locator("#filter-2-value").evaluate("el => {el.value='99'; el.dispatchEvent(new Event('input'));}")
        assert page.locator(".catalogue-path").count() == 2
        page.screenshot(path=str(root / "traces_communes_desktop.png"))
        page.keyboard.press("Escape")
        assert not page.locator("#map-dialog").is_visible()
        page.locator("#reset-filters").click()
        page.set_viewport_size({"width": 390, "height": 844})
        page.locator("#language").select_option("en")
        page.locator("#map-catalogue").click()
        page.locator(".catalogue-path").first.press("Enter")
        assert popup_title() == names[0]
        assert page.locator("#map-title").inner_text() == "Aggregated KML"
        box = page.locator("#map-dialog").bounding_box()
        assert box["x"] >= 0 and box["x"] + box["width"] <= 390
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        zoom = page.locator(".leaflet-control-zoom").bounding_box()
        heading = page.locator(".map-popup h3").bounding_box()
        assert zoom["y"] >= heading["y"] + heading["height"]
        page.screenshot(path=str(root / "kml_mobile.png"))
        page.locator("#map-close").click()
        tile_mode["fail"] = True
        page.reload()
        page.locator("#map-catalogue").click()
        page.wait_for_function("document.querySelector('#map-tiles-note').hidden === false")
        assert page.locator(".catalogue-path").count() == 4
        assert len(routes) == 1
        page.locator("#map-close").click()
        empty = generer_tableau_bord([], folder / "empty.html")
        page.goto(empty.as_uri())
        assert page.locator("#map-catalogue").is_disabled()
        assert not errors and not alerts, (errors, alerts)
        browser.close()
print("Maps OK: file://, shared-track clicks, direct neighbours despite filters, EN/FR, shared colours, KML/GPX downloads, route transition, mobile and tile failure.")
