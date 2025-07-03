# Camera PDF Scraper

This script (`scrape_camera_pdfs.py`) automates the downloading of all commission meeting PDFs from the Italian Chamber of Deputies (camera.it) for a specified commission and date range, with robust classification and parallel download support.

## What It Does
- **Dynamically discovers available years and months** for each legislature by scraping the official site, so it only downloads periods that actually exist.
- **Fetches** the list of available commission meeting PDFs for each valid month and year.
- **Parses** each month's page to find links to downloadable PDF files (specifically those labeled "scarica PDF").
- **Classifies** each PDF as either a stenographic report (`stenografici`), a bulletin (`bollettini`), or `other` based on the URL and query parameters.
- **Downloads** each PDF into a structured folder hierarchy: `output/legXX/{stenografici,bollettini,other}/YEAR/`.
- **Skips** already-downloaded files to avoid duplicates.
- **Downloads in parallel** (6 at a time) for speed.
- **Logs** progress and errors, with optional debug output and a separate `errors.log` file for errors only.

## Usage

```bash
python scrape_camera_pdfs.py --out pdfs [--debug] [--legislatures 17,18,19]
```

- `--out`: Output directory for PDFs. Default: `./pdfs`
- `--debug`: Enable verbose debug logging (optional)
- `--legislatures`: Comma-separated list of legislatures to scrape (e.g., `17,18,19`). Default: 19

Example:
```bash
python scrape_camera_pdfs.py --out my_pdfs --legislatures 17,18,19 --debug
```

## Requirements
- Python 3.8+
- [requests](https://pypi.org/project/requests/)
- [beautifulsoup4](https://pypi.org/project/beautifulsoup4/)
- [python-slugify](https://pypi.org/project/python-slugify/)
- [tqdm](https://pypi.org/project/tqdm/)

Install dependencies with:
```bash
pip install requests beautifulsoup4 python-slugify tqdm
```

## How It Works
- The script scrapes the main page for each legislature to discover which years and months are available.
- For each valid month, it fetches the HTML and looks for anchor tags with text containing "scarica PDF".
- Each PDF link is classified as `stenografici`, `bollettini`, or `other` based on the URL and query parameters.
- Files are saved in a folder structure like: `pdfs/leg18/stenografici/2022/2022-08-02_leg18_vigilanza_radiotelevisiva_xxxxxxxx.pdf`
- Downloads are performed in parallel (6 at a time) for efficiency.
- Errors (404s, connection issues, etc.) are logged to `errors.log`.
- Progress is shown with a `tqdm` progress bar for each month.

## Customization
- The commission and default legislatures are set at the top of the script (`COMMISSIONE_ID`, `LEGISLATURES`).
- If you need a different commission, adjust these values accordingly.
- The script is tailored for the structure of camera.it as of 2025. If the site changes, you may need to update the PDF link extraction or classification logic.

## Notes
- The script is robust to missing months (404s are skipped and logged).
- Only links with the text "scarica PDF" are downloaded. If the site changes this label, you may need to update the script.
- The script is intended for public, non-commercial use.
- Large numbers of parallel downloads may be rate-limited by the server; adjust `max_workers` in the script if needed.