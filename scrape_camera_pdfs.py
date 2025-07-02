"""
scrape_camera_pdfs.py
=====================
Grab all commission PDFs month-by-month from camera.it.

Usage
-----

    python scrape_camera_pdfs.py --start 2020 --end 2025 --out pdfs

Notes
-----
• Requires: requests, beautifulsoup4, python-slugify, tqdm
• Tested against: https://www.camera.it/210?commissione=21&annomese=202306&view=f
  Adjust BASE_URL if your commission or path differs.
"""

from __future__ import annotations
import argparse
import datetime as dt
import os
import re
import sys
from pathlib import Path
from typing import Iterable, List
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag
from bs4.element import Tag
from slugify import slugify
from tqdm import tqdm
import logging

# ─────────────────────────── Configuration ──────────────────────────── #

COMMISSION_ID = 21                 # 21 = Commissione vigilanza RAI (from your page)
LEGISLATURE   = 19                 # adjust if you're targeting a different legislature

BASE_URL = (
    "https://www.camera.it/leg{leg}/{page}"
    "?commissione={cid}&annomese={ym}&view=f"
).format(
    leg=LEGISLATURE,
    page="210",                    # fixed page id in the URL you captured
    cid=COMMISSION_ID,
    ym="{ym}"                      # keep placeholder for .format later
)

OUT_DIR = Path("pdfs")             # overridden by CLI --out

PDF_HREF_RE = re.compile(r"\.pdf$", re.I)
DATE_RE     = re.compile(r"data(\d{8})")  # dataYYYYMMDD inside the filename


# ─────────────────────────── Core functions ─────────────────────────── #

def setup_logging(debug: bool = False):
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format='[%(asctime)s] %(levelname)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )


def month_iter(start_year: int, end_year: int) -> Iterable[str]:
    """Yield YYYYMM strings from Jan `start_year` to Dec `end_year` inclusive."""
    for year in range(start_year, end_year + 1):
        for month in range(1, 13):
            yyyymm = f"{year}{month:02d}"
            logging.debug(f"Yielding month: {yyyymm}")
            yield yyyymm


def fetch_month_html(session: requests.Session, yyyymm: str) -> str | None:
    url = BASE_URL.format(ym=yyyymm)
    logging.debug(f"Fetching HTML for {yyyymm} from {url}")
    resp = session.get(url, timeout=30)
    if resp.status_code == 200:
        logging.info(f"Fetched HTML for {yyyymm}")
        return resp.text
    elif resp.status_code == 404:
        logging.warning(f"No data for {yyyymm} (404)")
        return None               # month not available
    else:
        logging.error(f"Failed to fetch {url}: {resp.status_code}")
        resp.raise_for_status()


def extract_pdf_links(html: str, base: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        if not isinstance(a, Tag):
            continue  # skip if not a real tag

        text = a.get_text(strip=True).lower()
        if "scarica pdf" in text:
            href = a.get("href")
            if isinstance(href, str):
                links.append(urljoin(base, href))
    return links


def infer_filename(pdf_url: str) -> str:
    """Create a descriptive filename using date & commission slug."""
    fname = Path(pdf_url).name       # e.g. leg19.bol0136.data20230629.com21.pdf
    date_match = DATE_RE.search(fname)
    date_part  = date_match.group(1) if date_match else "unknown"
    try:
        date_fmt = dt.datetime.strptime(date_part, "%Y%m%d").date().isoformat()
    except ValueError:
        date_fmt = date_part
    commission_slug = slugify(f"commission_{COMMISSION_ID}")
    filename = f"{date_fmt}_{commission_slug}.pdf"
    logging.debug(f"Inferred filename '{filename}' from URL '{pdf_url}'")
    return filename


def download_pdf(session: requests.Session, url: str, dest: Path) -> None:
    logging.info(f"Downloading PDF: {url} -> {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with session.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
    logging.info(f"Downloaded PDF to {dest}")


# ────────────────────────────── CLI flow ────────────────────────────── #

def main(argv: List[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Scrape Camera PDFs.")
    parser.add_argument("--start", type=int, default=2020,
                        help="first year (inclusive)")
    parser.add_argument("--end",   type=int, default=dt.date.today().year,
                        help="last year (inclusive)")
    parser.add_argument("--out",   type=Path, default=OUT_DIR,
                        help="output directory (default ./pdfs)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args(argv)

    setup_logging(args.debug)
    logging.info(f"Starting scrape: {args.start} to {args.end}, output: {args.out}")

    session = requests.Session()
    all_months = list(month_iter(args.start, args.end))

    for ym in tqdm(all_months, desc="Months", unit="month"):
        html = fetch_month_html(session, ym)
        if not html:
            logging.debug(f"No HTML for {ym}, skipping.")
            continue                       # 404 or empty
        base = session.headers.get("Referer", "https://www.camera.it/")
        if isinstance(base, bytes):
            base = base.decode("utf-8")
        pdfs = extract_pdf_links(html, base=base)
        for pdf_url in pdfs:
            filename = infer_filename(pdf_url)
            year_folder = args.out / filename[:4]   # 2023/...
            dest_path  = year_folder / filename
            if dest_path.exists():
                logging.info(f"Already downloaded: {dest_path}")
                continue                   # already downloaded
            try:
                download_pdf(session, pdf_url, dest_path)
            except Exception as e:
                logging.error(f"!! Failed {pdf_url}: {e}")

    logging.info("Done.")


if __name__ == "__main__":                # pragma: no cover
    main()
