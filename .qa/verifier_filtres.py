"""Vérifie les opérateurs des huit colonnes, leur combinaison et le recalcul OSRM."""
import os
from pathlib import Path
import sys
from threading import Thread
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from serveur_preview import creer_serveur
from tableau_bord import generer_tableau_bord
from playwright.sync_api import sync_playwright

root = Path(__file__).resolve().parent.parent
names = {"A": "Matin", "B": "Longue sortie", "C": "Petite boucle",
         "D": "Ancienne sortie", "E": "Données absentes", "F": "Zéro"}
results = [
    {"nom": names["A"], "date": "2026-10-04", "ville": "Garéoult",
     "distance_m": 12349, "denivele_pos": 500.5, "denivele_neg": 600,
     "duree_s": 5432, "distance_route_m": 38951, "duree_route_s": 2341},
    {"nom": names["B"], "date": "2026-10-05", "ville": "Toulon",
     "distance_m": 20010, "denivele_pos": 650.2, "duree_s": 7200,
     "distance_route_m": 90000, "duree_route_s": 5700},
    {"nom": names["C"], "date": "2026-10-03", "ville": "Hyères",
     "distance_m": 6500, "denivele_pos": 120, "duree_s": 1800,
     "distance_route_m": 15400, "duree_route_s": 900},
    {"nom": names["D"], "date": "2026-09-30", "ville": "Garéoult",
     "distance_m": 12300, "denivele_pos": 600, "duree_s": 5390,
     "distance_route_m": 38900, "duree_route_s": 2400},
    {"nom": names["E"]},
    {"nom": names["F"], "date": "2026-10-04", "ville": "Brignoles",
     "distance_m": 0, "denivele_pos": 0, "duree_s": 0,
     "distance_route_m": 0, "duree_route_s": 0},
]
for i, result in enumerate(results):
    result["lat_lon_depart"] = [43.30 + i / 100, 6.0 + i / 100]
    result["distance_goudron_m"] = [2432, 4010, 500, 700, 0, 0][i]
    result["goudron_incertain_m"] = [1200, 0, 0, 0, 1000, 0][i]

cases = [
    [(0, "=", "2026-10-04", None, "AF"), (0, ">", "2026-10-04", None, "B"),
     (0, "<", "2026-10-04", None, "CD"), (0, "between", "2026-10-03", "2026-10-05", "ABCF")],
    [(1, "=", " GAREOULT ", None, "AD"), (1, ">", "hyeres", None, "B"),
     (1, "<", "hyères", None, "ADF"), (1, "between", "gareoult", "HYERES", "ACD")],
    [(2, "=", "12,3", None, "AD"), (2, ">", "12.3", None, "B"),
     (2, "<", "12.3", None, "CF"), (2, "between", "6,5", "12.3", "ACD")],
    [(3, "=", "500", None, "A"), (3, ">", "500", None, "BD"),
     (3, "<", "500", None, "CF"), (3, "between", "120", "600", "ACD")],
    [(4, "=", "90", None, "D"), (4, ">", "90", None, "AB"),
     (4, "<", "90", None, "CF"), (4, "between", "30", "90", "CD")],
    [(5, "=", "39", None, "A"), (5, ">", "39", None, "B"),
     (5, "<", "39", None, "CDF"), (5, "between", "15,4", "39", "ACD")],
    [(6, "=", "39", None, "A"), (6, ">", "39", None, "BD"),
     (6, "<", "39", None, "CF"), (6, "between", "15", "39", "AC")],
    [(7, "=", "2,4", None, "A"), (7, ">", "2.4", None, "B"),
     (7, "<", "2.4", None, "CDF"), (7, "between", "0.5", "2,4", "ACD")],
]

def start_server(path):
    server = creer_serveur(path, 0)
    thread = Thread(target=lambda: server.serve_forever(poll_interval=.02), daemon=True)
    thread.start()
    return server, thread, f"http://127.0.0.1:{server.server_port}/"

def stop_server(server, thread):
    server.shutdown()
    thread.join(timeout=2)
    server.server_close()

output = generer_tableau_bord(results, root / ".qa" / "filtres_exemple.html")
server, thread, base = start_server(output)
try:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, channel=None if os.environ.get("GPX2DASH_BROWSER") == "chromium" else "msedge")
        page = browser.new_page(locale="fr-FR", viewport={"width": 1600, "height": 1180})
        errors, requests = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        def routing(route):
            requests.append(route.request.url)
            size = len(parse_qs(urlsplit(route.request.url).query)["destinations"][0].split(";"))
            route.fulfill(json={"code": "Ok", "distances": [[10051] * size], "durations": [[901] * size],
                                "sources": [{"distance": 0}], "destinations": [{"distance": 0}] * size})
        page.route("https://routing.openstreetmap.de/**", routing)
        page.route("https://photon.komoot.io/**", lambda route: route.fulfill(json={"features": [{
            "properties": {"name": "Hyères", "country": "France", "osm_value": "city"},
            "geometry": {"coordinates": [6.128, 43.119]}}]}))
        page.goto(base)
        assert page.locator("#column-filters select").count() == 8
        assert page.locator("#filter-0-value").get_attribute("type") == "date"
        assert page.locator("#filter-2-value").get_attribute("inputmode") == "decimal"
        def reset():
            if page.locator("#reset-filters").is_enabled():
                page.locator("#reset-filters").click()
        def set_condition(index, operator, lower, upper=None):
            page.locator(f"#filter-{index}-op").select_option(operator)
            if lower is not None:
                page.locator(f"#filter-{index}-value").fill(lower)
            if upper is not None:
                page.locator(f"#filter-{index}-upper").fill(upper)
        def visible():
            return page.locator("#traces tbody tr:not([hidden])").evaluate_all("rows => rows.map(row => row.dataset.id)")
        def expect(letters):
            actual = set(visible())
            expected = {names[letter] for letter in letters}
            assert actual == expected, (actual, expected, page.locator("#filters-status").inner_text())
            assert page.locator("#visible-count").inner_text() == f"{len(expected)} / 6 trace(s)"
            assert page.locator("#no-results").is_visible() == (not expected)
        expect("ABCDEF")
        for column in cases:
            for index, operator, lower, upper, expected in column:
                reset()
                set_condition(index, operator, lower, upper)
                expect(expected)
        for index in range(2, 8):
            reset()
            set_condition(index, "=", "0")
            expect("F")
        reset()
        for index, operator, lower, upper in [
            (0, "between", "2026-10-01", "2026-10-04"),
            (1, ">", "brignoles", None), (2, "between", "10", "15"),
            (3, "<", "600", None), (4, ">", "90", None),
            (5, "<", "50", None), (6, "between", "30", "40"), (7, "<", "3", None),
        ]:
            set_condition(index, operator, lower, upper)
        expect("A")
        assert "8 conditions actives." in page.locator("#filters-status").inner_text()
        page.locator("#search").fill("GAREOULT")
        expect("A")
        page.locator("#search").fill("Toulon")
        expect("")
        reset()
        expect("ABCDEF")
        assert not page.locator("#reset-filters").is_enabled()
        assert page.locator("#search").input_value() == ""
        assert page.locator("#column-filters input:enabled").count() == 0
        set_condition(2, "between", "6", "20")
        page.locator('thead button[data-column="2"]').click()
        assert visible() == [names[k] for k in "CDAB"]
        page.locator('thead button[data-column="2"]').click()
        assert visible() == [names[k] for k in "BADC"]
        reset()
        set_condition(2, "between", "10")
        expect("ABCDEF")
        assert "à compléter" in page.locator("#filters-status").inner_text()
        page.locator("#filter-2-upper").fill("5")
        expect("ABCDEF")
        assert page.locator("#filter-2-error").inner_text() == "Bornes inversées."
        assert page.locator("#filter-2-upper").get_attribute("aria-invalid") == "true"
        page.locator("#filter-2-upper").fill("15")
        expect("AD")
        assert page.locator("#filter-2-upper").get_attribute("aria-invalid") is None
        page.locator("#filter-2-value").fill("pas un nombre")
        expect("ABCDEF")
        assert "invalide" in page.locator("#filters-status").inner_text()
        assert page.locator("#filter-2-value").get_attribute("aria-invalid") == "true"
        set_condition(2, "=", "12,3")
        expect("AD")
        assert not page.locator("#filter-2-upper").is_visible()
        assert page.locator("#filter-2-upper").is_disabled()
        page.locator("#filter-2-op").select_option("")
        expect("ABCDEF")
        assert page.locator("#filter-2-value").is_disabled()
        reset()
        set_condition(3, "<", "1 000")
        expect("ABCDF")
        reset()
        set_condition(0, "=", "10000-01-01")
        expect("ABCDEF")
        assert page.locator("#filter-0-value").get_attribute("aria-invalid") == "true"
        reset()
        set_condition(5, "<", "20")
        set_condition(6, "<", "20")
        expect("CF")
        page.locator("#route-city").fill("Hyères")
        page.locator("#city-search").click()
        page.wait_for_function("!document.querySelector('#calculate-routes').disabled")
        page.locator("#calculate-routes").click()
        page.wait_for_function("!document.querySelector('#calculate-routes').disabled")
        expect("ABCDEF")
        assert len(requests) == 1
        assert "Hyères" in page.locator(".origin").inner_text()
        assert page.locator('thead th[aria-sort="descending"] button').get_attribute("data-column") == "2"
        set_condition(5, "=", "10,1")
        set_condition(6, "=", "15")
        expect("ABCDEF")
        assert page.locator("#traces tbody tr").first.locator("td").nth(5).get_attribute("data-filter") == "10.1"
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        assert page.locator(".table-scroll").evaluate("el => el.scrollWidth > el.clientWidth")
        page.locator("#column-filters").scroll_into_view_if_needed()
        page.screenshot(path=str(root / ".qa" / "filtres_mobile.png"))
        assert not errors, errors
        browser.close()
    print("OK : 32 combinaisons colonne/opérateur, bornes inclusives, valeurs inconnues et nulles, "
          "arrondis, virgules, filtres ET et recherche, tri, validation, remise à zéro, "
          "recalcul routier et mobile.")
finally:
    stop_server(server, thread)

if "--fixtures-only" in sys.argv:
    raise SystemExit(0)

# Vérification et aperçu du vrai catalogue, sans appel réseau.
server, thread, base = start_server(root / "tableau_bord.html")
try:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, channel=None if os.environ.get("GPX2DASH_BROWSER") == "chromium" else "msedge")
        page = browser.new_page(locale="fr-FR", viewport={"width": 1600, "height": 1180})
        errors, network = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        def no_network(route):
            network.append(route.request.url)
            route.abort()
        page.route("https://**/*", no_network)
        page.goto(base)
        total = page.locator("#traces tbody tr").count()
        assert total == 743, total
        page.locator("#filter-2-op").select_option("between")
        page.locator("#filter-2-value").fill("10")
        page.locator("#filter-2-upper").fill("20")
        page.locator("#filter-3-op").select_option("<")
        page.locator("#filter-3-value").fill("600")
        page.locator("#filter-6-op").select_option("<")
        page.locator("#filter-6-value").fill("45")
        data = page.locator("#traces tbody tr").evaluate_all("""rows => rows.map(row =>
            ({hidden: row.hidden, values: [2, 3, 6].map(i => row.cells[i].dataset.filter)}))""")
        expected_count = sum(all(v != "" for v in row["values"]) and
                             10 <= float(row["values"][0]) <= 20 and float(row["values"][1]) < 600 and
                             float(row["values"][2]) < 45 for row in data)
        visible_count = sum(not row["hidden"] for row in data)
        assert 0 < visible_count == expected_count < total, (visible_count, expected_count)
        assert page.locator("#visible-count").inner_text() == f"{visible_count} / {total} trace(s)"
        page.screenshot(path=str(root / ".qa" / "filtres_catalogue.png"))
        page.locator("#reset-filters").click()
        page.locator("#filter-7-op").select_option(">")
        page.locator("#filter-7-value").fill("0")
        positive = page.locator("#traces tbody tr:not([hidden])").count()
        assert positive > 0, "Le vrai catalogue doit comporter des portions de goudron calculées."
        page.locator('thead button[data-column="7"]').click()
        values = page.locator("#traces tbody tr:not([hidden])").evaluate_all(
            "rows => rows.map(row => Number(row.cells[7].dataset.sort))")
        assert values == sorted(values)
        page.screenshot(path=str(root / ".qa" / "goudron_catalogue.png"))
        assert not network, network
        assert not errors, errors
        browser.close()
    print(f"OK : catalogue réel de {total} traces ; {visible_count} respectent les trois conditions. "
          "Aucun accès Internet pour les filtres.")
finally:
    stop_server(server, thread)
