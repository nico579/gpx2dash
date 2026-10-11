"""Contrôle du tri sur le catalogue réel généré."""
from pathlib import Path
from threading import Thread
from playwright.sync_api import sync_playwright
from serveur_preview import creer_serveur

root = Path(__file__).resolve().parent.parent
server = creer_serveur(root / "tableau_bord.html", 0)
thread = Thread(target=lambda: server.serve_forever(poll_interval=.02), daemon=True)
thread.start()
try:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, channel="msedge")
        page = browser.new_page(viewport={"width": 1440, "height": 1050})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(f"http://127.0.0.1:{server.server_address[1]}/tableau_bord.html")
        expected = len([p for p in (root.parent / "gpx").iterdir()
                        if p.is_file() and p.suffix.lower() == ".gpx"])
        assert page.locator("tbody tr").count() == expected
        assert page.locator("thead th").count() == 8
        for column in range(8):
            for ascending in (True, False):
                page.locator(f'button[data-column="{column}"]').click()
                header = page.locator("thead th").nth(column)
                assert header.get_attribute("aria-sort") == ("ascending" if ascending else "descending")
                values = page.locator("tbody tr").evaluate_all(
                    "(rows, column) => rows.map(row => row.cells[column].dataset.sort)", column)
                known = [value for value in values if value != ""]
                assert values == known + [""] * (expected - len(known))
                if column >= 2:
                    numbers = [float(value) for value in known]
                    assert numbers == sorted(numbers, reverse=not ascending)
                if column == 0:
                    assert known == sorted(known, reverse=not ascending)
                if column == 1:
                    assert page.evaluate("""({known, ascending}) => {
                        const collator = new Intl.Collator('fr', {sensitivity:'base', numeric:true});
                        return known.every((v, i) => i === 0 ||
                            (ascending ? collator.compare(known[i - 1], v) <= 0 :
                                         collator.compare(known[i - 1], v) >= 0));
                    }""", {"known": known, "ascending": ascending})
        page.locator("#search").fill("Garéoult")
        assert page.locator("tbody tr:visible").count() > 0
        page.locator("#search").fill("")
        page.screenshot(path=str(root / ".qa" / "catalogue_reel.png"), full_page=False)
        issue_count = page.locator("tbody .error").count()
        maps_count = page.locator("tbody .route-link").count()
        goudron = page.locator("tbody tr").evaluate_all(
            "(rows) => rows.filter(r => Number(r.cells[7].dataset.sort) > 0).length")
        assert goudron > 0
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert not errors, errors
        browser.close()
finally:
    server.shutdown()
    thread.join(timeout=2)
    server.server_close()
print(f"Catalogue : {expected} lignes, 8 colonnes triables dans les deux sens, "
      f"{goudron} portions de goudron repérées, {maps_count} liens OpenStreetMap, "
      f"{issue_count} fichiers illisibles.")
