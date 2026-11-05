"""The page in a real browser: a zip, a zip with several addons, a folder, both languages, a phone, no console errors.

Needs Playwright with Chromium (pip install playwright && playwright install chromium); skipped otherwise.
"""

import shutil
import zipfile
from pathlib import Path

import pytest

pw = pytest.importorskip("playwright.sync_api")

ROOT = Path(__file__).resolve().parents[1]
FIX = Path(__file__).parent / "fixtures"
PAGE = ROOT / "dist" / "index.html"


def zip_folder(folder: Path, dest: Path) -> Path:
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(folder.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(folder.parent).as_posix())
    return dest


@pytest.fixture(scope="module")
def browser():
    if not PAGE.is_file():
        pytest.skip("run tools/build_web.py first")
    with pw.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as e:  # noqa: BLE001
            pytest.skip(f"chromium not available: {e}")
        yield b
        b.close()


@pytest.fixture
def page(browser):
    pg = browser.new_page(viewport={"width": 1100, "height": 900})
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    pg.goto(PAGE.as_uri())
    pg.wait_for_selector("#report .stamp")
    pg.errors = errors
    yield pg
    assert not pg.errors, pg.errors
    pg.close()


def test_example_renders_with_forever_line(page):
    assert page.locator("#report .forever").count() == 1
    assert "forever" in page.locator("#report .forever b").inner_text().lower()


def test_single_zip_classic_build(page, tmp_path):
    page.set_input_files("#file", str(zip_folder(FIX / "ClassicOnly", tmp_path / "ClassicOnly.zip")))
    page.wait_for_selector("#report .fv-outdated")
    assert "11509" in page.locator("#report .forever span").inner_text()
    assert page.locator("#report .stamp").count() == 1


def test_multi_zip_shows_a_table(page, tmp_path):
    page.set_input_files("#file", str(zip_folder(FIX / "AddOnsFolder", tmp_path / "AddOnsFolder.zip")))
    page.wait_for_selector("#report table.audit")
    rows = page.locator("#report table.audit tbody tr")
    assert rows.count() == 5
    assert "Evil" in rows.nth(0).inner_text() and "Peligroso" in rows.nth(0).inner_text()
    assert page.locator("#report section.sub").count() == 5
    assert "peligroso" in page.locator("#report .stamp").first.inner_text().lower()
    rows.nth(2).click()  # jumps to the detail; must not throw
    # English
    page.click('.lang button[data-lang="en"]')
    page.wait_for_function(
        "document.querySelector('#report table.audit') && document.querySelector('#report table.audit').innerText.includes('Not a Forever build')"
    )
    assert "dangerous" in page.locator("#report .stamp").first.inner_text().lower()
    page.click('.lang button[data-lang="es"]')


def test_folder_input(page):
    page.set_input_files("#folder", str(FIX / "AddOnsFolder"))
    page.wait_for_selector("#report table.audit")
    assert page.locator("#report table.audit tbody tr").count() == 5
    assert "Forever no lo va a listar" in page.locator("#report table.audit").inner_text()


def test_single_folder_input_is_one_report(page):
    page.set_input_files("#folder", str(FIX / "Clean"))
    page.wait_for_selector("#report .fv-loads")
    assert page.locator("#report table.audit").count() == 0


def test_phone_width_has_no_horizontal_scroll(browser, tmp_path):
    pg = browser.new_page(viewport={"width": 375, "height": 800})
    pg.goto(PAGE.as_uri())
    pg.wait_for_selector("#report .stamp")
    pg.set_input_files("#file", str(zip_folder(FIX / "AddOnsFolder", tmp_path / "AddOnsFolder.zip")))
    pg.wait_for_selector("#report table.audit")
    pg.wait_for_timeout(600)  # the stamp lands with a short scale animation; measure after it
    assert pg.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
    pg.close()


def test_folder_without_addons_says_so(page, tmp_path):
    d = tmp_path / "Nada"
    d.mkdir()
    (d / "readme.txt").write_text("x")
    page.set_input_files("#folder", str(d))
    page.wait_for_selector("#report .error")
    assert ".toc" in page.locator("#report .error").inner_text()


def test_screenshot_for_docs(browser, tmp_path):
    if shutil.which("node") is None:
        pytest.skip("node")
    pg = browser.new_page(viewport={"width": 1100, "height": 900}, device_scale_factor=2)
    pg.goto(PAGE.as_uri())
    pg.set_input_files("#file", str(zip_folder(FIX / "AddOnsFolder", tmp_path / "AddOnsFolder.zip")))
    pg.wait_for_selector("#report table.audit")
    pg.locator("#report").screenshot(path=str(tmp_path / "audit.png"))
    assert (tmp_path / "audit.png").stat().st_size > 1000
    pg.close()
