"""Browser regression: standalone file, EN/FR, state preservation and sticky headings/filter rows."""
import base64
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tableau_bord import generer_tableau_bord
from trajets_osrm import lien_osm
from playwright.sync_api import sync_playwright

with tempfile.TemporaryDirectory() as directory:
    output = Path(directory) / "dashboard.html"
    results = [{
        "nom": f"Track {i:03d}", "date": "2026-10-04", "ville": "Garéoult",
        "distance_m": 12349 + i * 200, "denivele_pos": 500 + i, "denivele_neg": 450,
        "duree_s": 5432 + i * 60, "distance_route_m": 38951 + i * 300,
        "duree_route_s": 2341 + i * 60, "distance_goudron_m": 2432 + i * 20,
        "goudron_incertain_m": 1200, "lat_lon_depart": [43.3293, 6.0458],
        "segments": [[[6.0458, 43.3293], [6.048, 43.33]]],
        "itineraire_url": lien_osm((43.3293, 6.0458)),
    } for i in range(140)]
    generer_tableau_bord(results, output)
    png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True,
            channel=None if os.environ.get("GPX2DASH_BROWSER") == "chromium" else "msedge")
        context = browser.new_context(locale="en-GB", viewport={"width": 1440, "height": 1050})
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("https://*.tile.opentopomap.org/**", lambda route: route.fulfill(content_type="image/png", body=png))
        page.route("https://routing.openstreetmap.de/**", lambda route: route.fulfill(json={
            "code": "Ok", "routes": [{"distance": 44000, "duration": 2800,
                "geometry": {"type": "LineString", "coordinates": [[6.0458, 43.3293], [6.048, 43.33]]}}],
            "waypoints": [{"distance": 0}, {"distance": 0}]}))
        page.goto(output.as_uri())
        assert page.locator("html").get_attribute("lang") == "en"
        assert page.locator("h1").inner_text() == "Track dashboard"
        assert page.locator("#filter-7-op option").last.inner_text() == "Between"
        assert page.locator('tr[data-id="Track 000"] td').nth(2).inner_text() == "12.3 km"
        def condition(column, operator, value, upper=None):
            page.locator(f"#filter-{column}-op").select_option(operator)
            page.locator(f"#filter-{column}-value").fill(value)
            if upper is not None:
                page.locator(f"#filter-{column}-upper").fill(upper)
        def visible_rows():
            return page.evaluate("""() => {
                const area = document.querySelector('.table-scroll').getBoundingClientRect();
                const head = document.querySelector('thead').getBoundingClientRect();
                return [...document.querySelectorAll('tbody tr:not([hidden])')].filter(row => {
                    const box = row.getBoundingClientRect();
                    return box.top >= Math.max(area.top, head.bottom) - 1
                        && box.bottom <= Math.min(area.bottom, innerHeight) + 1;
                }).length;
            }""")
        for width, height in ((1280, 720), (1366, 768), (390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            for language in ("fr", "en"):
                page.locator("#language").select_option(language)
                page.evaluate("scrollTo(0, 0)")
                assert visible_rows() >= 10, (width, height, language, visible_rows())
                condition(2, "between", "0", "100")
                page.evaluate("scrollTo(0, 0); document.querySelector('.table-scroll').scrollTop = 0")
                if width == 390 and language == "fr":
                    page.screenshot(path=str(Path(__file__).resolve().parent / "density_mobile.png"))
                assert visible_rows() >= 10, (
                    width, height, language, "between", visible_rows(),
                    page.locator("header").bounding_box(), page.locator(".stats").bounding_box(),
                    page.locator(".table-scroll").bounding_box(), page.locator("thead").bounding_box(),
                    page.locator("tbody tr").nth(9).bounding_box())
                page.locator("#reset-filters").click()
        page.set_viewport_size({"width": 1440, "height": 1050})
        condition(2, "between", "12,3", "14")
        condition(3, "<", "506")
        condition(7, ">", "2")
        page.locator('thead button[data-column="2"]').click()
        ids = page.locator("tbody tr:not([hidden])").evaluate_all("rows => rows.map(row => row.dataset.id)")
        assert len(ids) == 6
        page.locator("#language").select_option("fr")
        assert page.locator("html").get_attribute("lang") == "fr"
        assert page.locator("h1").inner_text() == "Tableau de bord des traces"
        assert page.locator('tr[data-id="Track 000"] td').nth(2).inner_text() == "12,3 km"
        assert page.locator("tbody tr:not([hidden])").evaluate_all("rows => rows.map(row => row.dataset.id)") == ids
        assert page.locator("#filter-2-value").input_value() == "12,3"
        assert page.locator("#filters-status").inner_text() == "3 conditions actives."
        page.reload()
        assert page.locator("html").get_attribute("lang") == "fr"
        page.locator("#language").select_option("en")
        page.locator('tr[data-id="Track 000"] .route-link').click()
        page.wait_for_function("document.querySelector('#trace-map').dataset.road === 'ready'")
        assert "Driving route: 44.0 km" in page.locator("#map-status").inner_text()
        page.locator("#language").evaluate("el => {el.value='fr'; el.dispatchEvent(new Event('change'));}")
        assert page.locator("#map-title").inner_text() == "Track 000"
        assert "Trajet routier : 44,0 km" in page.locator("#map-status").inner_text()
        assert page.locator("#map-close").inner_text() == "Fermer"
        page.locator("#map-close").click()
        for width in (1440, 390):
            page.set_viewport_size({"width": width, "height": 1050 if width == 1440 else 844})
            for language in ("fr", "en"):
                page.locator("#language").select_option(language)
                # A two-bound filter increases the sticky header height naturally.
                condition(2, "between", "0", "100")
                scroll = page.locator(".table-scroll")
                scroll.scroll_into_view_if_needed()
                scroll.evaluate("el => {el.scrollTop = 100; el.scrollLeft = 0}")
                page.wait_for_timeout(60)
                before = page.locator("thead").bounding_box()
                scroll.evaluate("el => {el.scrollTop = 900}")
                page.wait_for_timeout(60)
                after = page.locator("thead").bounding_box()
                assert abs(before["y"] - after["y"]) < 1, (before, after)
                assert page.locator("#column-filters").bounding_box()["y"] >= after["y"]
                scroll.evaluate("el => {el.scrollLeft = 350}")
                page.wait_for_timeout(60)
                alignment = page.evaluate("""() => {
                    const head = document.querySelector('thead th:nth-child(3)').getBoundingClientRect();
                    const body = document.querySelector('tbody td:nth-child(3)').getBoundingClientRect();
                    return [Math.abs(head.x - body.x), Math.abs(head.width - body.width)];
                }""")
                assert max(alignment) < 1, alignment
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                screenshot = Path(__file__).resolve().parent / ("headers_mobile.png" if width == 390 else "headers_desktop.png")
                page.screenshot(path=str(screenshot))
                page.locator("#reset-filters").click()
        assert not errors, errors
        # A separate context follows the CLI's explicit initial language.
        generer_tableau_bord(results[:1], output, langue="fr")
        fresh = browser.new_context(locale="en-GB")
        fresh_page = fresh.new_page()
        fresh_page.goto(output.as_uri())
        assert fresh_page.locator("html").get_attribute("lang") == "fr"
        fresh.close()
        browser.close()
print("EN/FR, file://, preference persistence, active filters/sorting, map translations, sticky titles and filters, horizontal alignment, mobile: OK")
