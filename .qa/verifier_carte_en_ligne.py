"""Vérifie une vraie trace et OSRM ; les tuiles sont simulées pour limiter les appels."""
import base64
from pathlib import Path
import sys
from threading import Thread
from playwright.sync_api import sync_playwright

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
from serveur_preview import creer_serveur
server = creer_serveur(root / "tableau_bord.html", 0)
thread = Thread(target=lambda: server.serve_forever(poll_interval=.02), daemon=True)
thread.start()
png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True, channel="msedge")
    page = browser.new_page(viewport={"width": 1440, "height": 1050})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.route("https://*.tile.opentopomap.org/**", lambda route: route.fulfill(content_type="image/png", body=png))
    page.goto(f"http://127.0.0.1:{server.server_port}/")
    selected = page.evaluate("""() => {
        const data = JSON.parse(document.querySelector('#dashboard-data').textContent);
        const origin = data.origine.position.map(v => v.toFixed(6)).join(',');
        return data.traces.find(trace => {
            const key = data.serveur + '|' + origin + '|' + trace.position.map(v => v.toFixed(6)).join(',');
            const route = data.cache[key];
            return trace.segments.length && route?.distance_route_m > 5000 && route.distance_route_m < 60000;
        }).id;
    }""")
    assert page.locator("tbody tr").count() == 743
    assert page.locator('.route-link[aria-haspopup="dialog"]').count() == 741
    page.locator("tr").filter(has=page.locator('.trace-name', has_text=selected)).locator(".route-link").click()
    page.wait_for_function("document.querySelector('#trace-map').dataset.road !== 'loading'", timeout=40000)
    assert page.locator("#trace-map").get_attribute("data-road") == "ready", page.locator("#map-status").inner_text()
    assert page.locator(".gpx-path").count() == 1 and page.locator(".road-path").count() == 1
    page.wait_for_function("""() => [...document.querySelectorAll('.leaflet-tile')].filter(
        tile => tile.complete && tile.naturalWidth === 1).length >= 3""", timeout=25000)
    page.screenshot(path=str(root / ".qa" / "carte_reelle_desktop.png"), full_page=False)
    page.locator("#map-trace").click()
    page.screenshot(path=str(root / ".qa" / "carte_reelle_zoom.png"), full_page=False)
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.screenshot(path=str(root / ".qa" / "carte_reelle_mobile.png"), full_page=False)
    message = page.locator("#map-status").inner_text()
    assert not errors, errors
    browser.close()
server.shutdown()
server.server_close()
thread.join()
print("Route en ligne OK (tuiles simulées) :", selected, "·", message)
