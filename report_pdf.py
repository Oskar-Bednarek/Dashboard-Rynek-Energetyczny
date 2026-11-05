"""Render the self-contained dashboard with Chromium's actual print layout."""
from functools import lru_cache
import shutil


class PdfGenerationError(RuntimeError):
    pass


@lru_cache(maxsize=4)
def generate_report_pdf(html: str) -> bytes:
    """Cache identical exports; no network requests or local file URLs needed."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            executable = shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome")
            options = {"executable_path": executable} if executable else {}
            browser = playwright.chromium.launch(headless=True, **options)
            try:
                context = browser.new_context(viewport={"width": 1123, "height": 794}, device_scale_factor=2)
                # The report embeds its JS and data. PDF export never fetches external content.
                context.route("**/*", lambda route: route.abort())
                page = context.new_page()
                page.emulate_media(media="print")
                page.set_content(html, wait_until="load", timeout=30000)
                page.wait_for_selector("#dashboard .market-card", timeout=15000)
                page.evaluate("document.fonts.ready")
                page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
                errors = page.locator(".error")
                if errors.count() and errors.first.is_visible():
                    raise PdfGenerationError("Nie udało się wyrenderować danych dashboardu.")
                return page.pdf(prefer_css_page_size=True, print_background=True, display_header_footer=False)
            finally:
                browser.close()
    except PdfGenerationError:
        raise
    except Exception as error:
        raise PdfGenerationError(
            "Nie udało się wygenerować PDF. Sprawdź instalację Playwright i Chromium na serwerze. "
            "Raport HTML nadal można pobrać."
        ) from error
