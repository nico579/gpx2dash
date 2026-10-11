"""Vérifie le choix de ville, le recalcul, le cache et les échecs dans Edge, sans réseau."""
import json
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit
from playwright.sync_api import sync_playwright

root = Path(__file__).resolve().parent.parent
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True, channel="msedge")
    page = browser.new_page(viewport={"width": 1440, "height": 1050})
    errors, requests = [], []
    mode = {"value": "wrong-region"}
    page.on("pageerror", lambda error: errors.append(str(error)))
    def cities(route):
        name = "Hyères" if "Hy" in unquote(route.request.url) else "Toulon"
        position = [6.128, 43.119] if name == "Hyères" else [5.93, 43.12]
        features = [{"properties": {"name": name, "country": "France", "osm_value": "city"},
                     "geometry": {"coordinates": position}}]
        features.append({"properties": {"name": name, "country": "Canada", "osm_value": "village"},
                         "geometry": {"coordinates": [-73, 45]}})
        route.fulfill(json={"features": features})
    def matrix(route):
        requests.append(route.request.url)
        if mode["value"] == "error":
            route.fulfill(status=503, json={"message": "Service unavailable"})
            return
        if mode["value"] == "pending":
            return
        coordinates = unquote(urlsplit(route.request.url).path).split("/")[-1].split(";")
        origin = [float(v) for v in coordinates[0].split(",")]
        size = len(parse_qs(urlsplit(route.request.url).query)["destinations"][0].split(";"))
        scale = 10000 if origin[0] < 6 else 20000
        distances = [scale + i * 1000 for i in range(size)]
        distances[-1] = None
        source_distance = 5000000 if mode["value"] == "wrong-region" else 5
        if mode["value"] == "wrong-region":
            mode["value"] = "ok"
        route.fulfill(json={"code": "Ok", "distances": [distances],
                           "durations": [[v / 10 if v is not None else None for v in distances]],
                           "sources": [{"distance": source_distance}], "destinations": [{"distance": 10} for _ in distances]})
    page.route("https://photon.komoot.io/**", cities)
    page.route("https://routing.openstreetmap.de/**", matrix)
    page.goto((root / ".qa" / "tableau_bord_exemple.html").as_uri())
    page.locator('button[data-column="5"]').click()
    def snapshot():
        return page.locator("tbody tr").evaluate_all("""rows => rows.map(row => ({
            id: row.dataset.id, distance: row.cells[5].dataset.sort, duration: row.cells[6].dataset.sort,
            link: row.querySelector(".route-link")?.href
        }))""")
    def choose(query):
        page.locator("#route-city").fill(query)
        assert page.locator("#calculate-routes").is_disabled()
        page.locator("#city-search").click()
        page.wait_for_function("document.querySelector('#city-results').options.length === 2")
        page.locator("#city-results").select_option("0")
        assert "France" in page.locator("#city-results option:checked").inner_text()
    def calculate():
        page.locator("#calculate-routes").click()
        page.wait_for_function("!document.querySelector('#calculate-routes').disabled")
    choose("Toulon")
    calculate()
    assert page.locator(".origin").inner_text().endswith("Toulon, France")
    assert len(requests) == 2
    fallback = unquote(urlsplit(requests[-1]).path).split("/")[-1].split(";")
    assert len(fallback) == 9 and fallback[-4:] == [fallback[0]] * 4
    first = snapshot()
    assert all("43.120000%2C5.930000" in row["link"] for row in first)
    values = [float(row["distance"]) for row in first if row["distance"]]
    assert values == sorted(values) and len(values) == 3
    assert first[-1]["distance"] == "" and first[-1]["duration"] == ""
    assert page.locator("#routes-count").inner_text() == "3 / 4"
    choose("Hyères")
    calculate()
    second = snapshot()
    assert first != second
    assert page.locator(".origin").inner_text().endswith("Hyères, France")
    assert all("43.119000%2C6.128000" in row["link"] for row in second)
    requests_before = len(requests)
    page.reload()
    assert len(requests) == requests_before
    assert sorted(snapshot(), key=lambda row: row["id"]) == sorted(second, key=lambda row: row["id"])
    assert page.locator(".origin").inner_text().endswith("Hyères, France")
    choose("Toulon")
    calculate()
    assert len(requests) == requests_before
    assert page.locator(".origin").inner_text().endswith("Toulon, France")
    choose("Marseille")
    # Coordonnées distinctes afin de vérifier un échec sans réutiliser Toulon.
    page.evaluate("""() => {
       const select = document.querySelector('#city-results');
       select.value = '1';
    }""")
    before_failure = snapshot()
    mode["value"] = "error"
    calculate()
    assert snapshot() == before_failure
    assert "HTTP 503" in page.locator("#route-status").inner_text()
    assert page.locator(".origin").inner_text().endswith("Toulon, France")
    mode["value"] = "pending"
    page.locator("#calculate-routes").click()
    page.wait_for_function("!document.querySelector('#cancel-routes').hidden")
    page.locator("#cancel-routes").click()
    page.wait_for_function("!document.querySelector('#calculate-routes').disabled")
    assert snapshot() == before_failure
    assert "annulé" in page.locator("#route-status").inner_text()
    assert not errors, errors
    browser.close()
print("Choix de ville OK : désambiguïsation, deux origines, tris conservés, cache après réouverture, erreur et annulation.")
