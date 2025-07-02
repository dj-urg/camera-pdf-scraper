# Camera PDF Scraper

This script (`scrape_camera_pdfs.py`) automates the downloading of all commission meeting PDFs from the Italian Chamber of Deputies (camera.it) for a specified commission and date range.

## What It Does
- **Fetches** the list of available commission meeting PDFs month-by-month from the camera.it website.
- **Parses** each month's page to find links to downloadable PDF files (specifically those labeled "scarica PDF").
- **Downloads** each PDF into a structured folder hierarchy by year.
- **Skips** already-downloaded files to avoid duplicates.
- **Logs** progress and errors, with optional debug output.

## Usage

```bash
python scrape_camera_pdfs.py --start 2020 --end 2025 --out pdfs [--debug]
```

- `--start`: First year to scrape (inclusive). Default: 2020
- `--end`: Last year to scrape (inclusive). Default: current year
- `--out`: Output directory for PDFs. Default: `./pdfs`
- `--debug`: Enable verbose debug logging (optional)

Example:
```bash
python scrape_camera_pdfs.py --start 2022 --end 2023 --out my_pdfs --debug
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
- The script constructs URLs for each month in the specified range for the configured commission.
- It fetches the HTML for each month and looks for anchor tags with text containing "scarica PDF".
- For each found PDF link, it generates a filename based on the date and commission, and saves the file in a year-based subfolder.
- If a file already exists, it is skipped.
- All progress and errors are logged to the console.

## Customization
- The commission and legislature are set at the top of the script (`COMMISSION_ID`, `LEGISLATURE`).
- If you need a different commission, adjust these values accordingly.
- The script is currently tailored for the structure of camera.it as of 2023. If the site changes, you may need to update the PDF link extraction logic.

## Notes
- The script is robust to missing months (404s are skipped).
- Only links with the text "scarica PDF" are downloaded. If the site changes this label, you may need to update the script.
- The script is intended for public, non-commercial use.

## License
MIT License 