"""Aperçu fictif et contrôle des interactions dans un navigateur."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tableau_bord import generer_tableau_bord
from trajets_osrm import lien_osm
from playwright.sync_api import sync_playwright

folder = Path(__file__).resolve().parent
results = [
    {"nom": "2026-10-04_Sainte-Baume", "date": "2026-10-04", "ville": "Gémenos",
     "lat_lon_depart": (43.295, 5.630), "distance_m": 22325, "denivele_pos": 735,
     "denivele_neg": 736, "duree_s": 14160, "distance_route_m": 42300, "duree_route_s": 2600},
    {"nom": "2026-09-28_Les-crêtes", "date": "2026-09-28", "ville": "Brignoles",
     "lat_lon_depart": (43.400, 6.061), "distance_m": 8400, "denivele_pos": 310,
     "denivele_neg": 305, "duree_s": 7620},
    {"nom": "2026-09-15_Forêt-de-Morières", "date": "2026-09-15", "ville": "Méounes-lès-Montrieux",
     "lat_lon_depart": (43.268, 5.971), "distance_m": 14600, "denivele_pos": 560,
     "denivele_neg": 560, "duree_s": 11280, "distance_route_m": 16800, "duree_route_s": 1320},
    {"nom": "Trace_sans_horodatage", "ville": "Garéoult", "lat_lon_depart": (43.329, 6.045),
     "distance_m": 5000, "denivele_pos": None, "duree_s": None},
]
for result in results:
    result["itineraire_url"] = lien_osm(result["lat_lon_depart"])
    lat, lon = result["lat_lon_depart"]
    result["segments"] = [[[lon, lat], [lon + .01, lat + .02], [lon + .03, lat + .01],
                           [lon + .02, lat - .01], [lon, lat]]]
output = generer_tableau_bord(results, folder / "tableau_bord_exemple.html")
html = output.read_text(encoding="utf-8").replace(
    "GPX2DASH · Mes itinéraires", "GPX2DASH · Aperçu avec des données fictives")
output.write_text(html, encoding="utf-8")
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True, channel="msedge")
    page = browser.new_page(viewport={"width": 1440, "height": 1050}, device_scale_factor=1)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(output.as_uri())
    assert page.locator("tbody tr").count() == 4
    page.locator("#search").fill("gemenos")
    assert page.locator("tbody tr:visible").count() == 1
    assert "Sainte-Baume" in page.locator("tbody tr:visible").inner_text()
    page.locator("#search").fill("impossible")
    assert page.locator("#no-results").is_visible()
    page.locator("#search").fill("")
    page.locator('button[data-column="2"]').click()
    assert page.locator("tbody tr").first.locator("td").nth(2).inner_text() == "5,0 km"
    page.locator('button[data-column="2"]').click()
    assert page.locator("tbody tr").first.locator("td").nth(2).inner_text() == "22,3 km"
    page.locator('button[data-column="5"]').click()
    assert page.locator("tbody tr").first.locator("td").nth(5).inner_text() == "16,8 km"
    assert page.locator("tbody tr").last.locator("td").nth(5).inner_text() == "—"
    page.locator('button[data-column="5"]').click()
    assert page.locator("tbody tr").first.locator("td").nth(5).inner_text() == "42,3 km"
    assert page.locator("tbody tr").last.locator("td").nth(5).inner_text() == "—"
    page.locator('button[data-column="0"]').click()
    page.locator('button[data-column="0"]').click()
    page.screenshot(path=str(folder / "tableau_bord_desktop.png"), full_page=True)
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.screenshot(path=str(folder / "tableau_bord_mobile.png"), full_page=True)
    assert not errors, errors
    browser.close()
print("Visualisation et interactions OK : recherche, tris numériques, valeurs inconnues, affichage mobile.")
