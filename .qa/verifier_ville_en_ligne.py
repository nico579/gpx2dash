"""Contrôle en ligne du choix de Toulon sur quatre traces de démonstration."""
from pathlib import Path
from playwright.sync_api import sync_playwright

root = Path(__file__).resolve().parent.parent
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True, channel="msedge")
    page = browser.new_page(viewport={"width": 1440, "height": 1050})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto((root / ".qa" / "tableau_bord_exemple.html").as_uri())
    page.locator("#route-city").fill("Toulon, France")
    page.locator("#city-search").click()
    page.wait_for_function("!document.querySelector('#city-search').disabled", timeout=40000)
    options = page.locator("#city-results option").all_text_contents()
    assert options, page.locator("#route-status").inner_text()
    index = next(i for i, label in enumerate(options) if label.startswith("Toulon,") and "France" in label)
    page.locator("#city-results").select_option(str(index))
    before = page.locator("tbody tr").evaluate_all("rows => rows.map(row => row.cells[5].dataset.sort)")
    page.locator("#calculate-routes").click()
    page.wait_for_function("!document.querySelector('#calculate-routes').disabled", timeout=60000)
    assert "Toulon" in page.locator(".origin").inner_text(), page.locator("#route-status").inner_text()
    after = page.locator("tbody tr").evaluate_all("rows => rows.map(row => row.cells[5].dataset.sort)")
    assert before != after
    assert all(value and float(value) > 0 for value in after), page.locator("#route-status").inner_text()
    assert page.locator("#routes-count").inner_text() == "4 / 4"
    page.locator('button[data-column="5"]').click()
    sorted_values = page.locator("tbody tr").evaluate_all("rows => rows.map(row => Number(row.cells[5].dataset.sort))")
    assert sorted_values == sorted(sorted_values)
    page.screenshot(path=str(root / ".qa" / "depart_toulon.png"), full_page=True)
    message = page.locator("#route-status").inner_text()
    assert not errors, errors
    browser.close()
print("Photon et OSRM en ligne depuis le HTML local :", message)
