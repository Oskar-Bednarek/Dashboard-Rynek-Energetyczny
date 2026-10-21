from pathlib import Path
from playwright.sync_api import sync_playwright

# Input and output files
html_file = Path("dashboard.html").resolve()
pdf_file = Path("PEC-Legionowo-Dashboard.pdf").resolve()

if not html_file.exists():
    raise FileNotFoundError(f"HTML file not found: {html_file}")

with sync_playwright() as p:
    browser = p.chromium.launch()

    page = browser.new_page(
        viewport={"width": 1600, "height": 1000},
        device_scale_factor=1,
    )

    # Open the HTML dashboard
    page.goto(html_file.as_uri(), wait_until="networkidle")

    # Wait for fonts and JavaScript-generated charts
    page.evaluate("() => document.fonts.ready")
    page.wait_for_selector("svg.chart[data-values]")

    # Export the dashboard as a PDF
    page.pdf(
        path=str(pdf_file),
        format="A3",
        landscape=True,
        print_background=True,
        prefer_css_page_size=False,
        margin={
            "top": "5mm",
            "bottom": "5mm",
            "left": "5mm",
            "right": "5mm",
        },
        scale=1,
    )

    browser.close()

print(f"PDF created successfully: {pdf_file}")