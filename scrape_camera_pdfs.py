#!/usr/bin/env python
"""
scrape_camera_pdf.py
====================
Scarica i bollettini PDF della Commissione Vigilanza RAI (leg. 17-19).

Uso
----
    python scrape_camera_pdf.py --start 2013 --end 2025 --debug

Dipendenze
-----------
pip install requests beautifulsoup4 python-slugify tqdm
"""

from __future__ import annotations
import argparse
import datetime as dt
import logging
import re
import sys
from pathlib import Path
from typing import Iterable, List
from urllib.parse import urljoin, parse_qs
import hashlib
from concurrent.futures import ThreadPoolExecutor
import time

import requests
from bs4 import BeautifulSoup, Tag
from slugify import slugify
from tqdm import tqdm

# ───────────────────── Configurazione generica ─────────────────────── #

COMMISSIONE    = "vigilanza radiotelevisiva"
COMMISSIONE_ID = 21                       # usato solo nell'URL
COMMISSIONE_SLUG = slugify(COMMISSIONE, separator="_")   # vigilanza_radiotelevisiva
LEGISLATURES = [17, 18, 19]                # default, can be overridden by CLI
VIEW_PARAM     = "f"                      # layout "in ordine cronologico"

BASE_URL_TEMPLATE = (
    "https://www.camera.it/leg{leg}/{page}"
    "?commissione={cid}&annomese={ym}&view=f"
)
PAGE_ID = "210"  # fixed page id in the URL you captured

OUT_DIR = Path(f"resoconti_{COMMISSIONE_SLUG}")

DATE_RE = re.compile(r"data(\d{8})")      # es. data20230629 → 20230629

# ─────────────────────── Funzioni di utilità ───────────────────────── #

def setup_logging(debug: bool = False) -> None:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="[%(asctime)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # Add error file handler
    error_handler = logging.FileHandler("errors.log")
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s', "%Y-%m-%d %H:%M:%S"))
    logging.getLogger().addHandler(error_handler)

def month_iter(start_year: int, end_year: int) -> Iterable[str]:
    """Genera YYYYMM da gennaio start_year a dicembre end_year (inclusi)."""
    for anno in range(start_year, end_year + 1):
        for mese in range(1, 13):
            yield f"{anno}{mese:02d}"

def fetch_month_html(sess: requests.Session, leg: int, yyyymm: str) -> str | None:
    url = BASE_URL_TEMPLATE.format(
        leg=leg,
        page=PAGE_ID,
        cid=COMMISSIONE_ID,
        ym=yyyymm,
    )
    resp = sess.get(url, timeout=30)
    if resp.status_code == 200:
        return resp.text
    if resp.status_code == 404:            # mese non presente
        logging.debug(f"{url} → 404")
        return None
    resp.raise_for_status()                # solleva altri errori

def extract_pdf_links(html: str, base: str) -> List[str]:
    """Ritorna tutti i link PDF ("Scarica Pdf")."""
    soup = BeautifulSoup(html, "html.parser")
    links: List[str] = []
    for a in soup.find_all("a", href=True):
        if not isinstance(a, Tag):
            continue  # skip if not a real tag
        text = a.get_text(strip=True).lower()
        if "scarica pdf" in text:
            href = a.get("href")
            if isinstance(href, str):
                links.append(urljoin(base, href))
    return links

def extract_date_from_url(pdf_url: str) -> str:
    # Try filename first
    raw_name = Path(pdf_url).name
    match = re.search(r"data(\\d{8})", raw_name)
    if match:
        return match.group(1)
    # Fallback: try the full URL
    match = re.search(r"data(\\d{8})", pdf_url)
    if match:
        return match.group(1)
    return "sconosciuto"

def extract_date_from_query(filename: str) -> str | None:
    # Only try if it looks like a query string
    if "anno=" in filename and "mese=" in filename and "giorno=" in filename:
        params = parse_qs(filename)
        year = params.get("anno", [""])[0]
        month = params.get("mese", [""])[0]
        day = params.get("giorno", [""])[0]
        if year and month and day:
            return f"{year}{month.zfill(2)}{day.zfill(2)}"
    return None

def infer_filename(pdf_url: str, leg: int) -> str:
    """
    Costruisce un nome file:
    2023-06-29_leg19_vigilanza_radiotelevisiva_bollettino.pdf
    """
    raw_name = Path(pdf_url).name
    date_part = DATE_RE.search(raw_name)
    da = date_part.group(1) if date_part else None
    if not da:
        # Try extracting from query string
        da = extract_date_from_query(raw_name)
    if not da:
        logging.warning(f"Could not extract date from filename: '{raw_name}' (URL: {pdf_url})")
        da = "sconosciuto"
    try:
        iso = dt.datetime.strptime(da, "%Y%m%d").date().isoformat()
    except ValueError:
        iso = da
    url_hash = hashlib.md5(pdf_url.encode()).hexdigest()[:8]
    return f"{iso}_leg{leg}_{COMMISSIONE_SLUG}_{url_hash}.pdf"

def get_pdf_type(pdf_url: str) -> str:
    logging.debug(f"Classifying PDF URL: {pdf_url}")
    if not isinstance(pdf_url, str):
        logging.debug("Classified as other (not a string)")
        return "other"
    if "stenografici" in pdf_url or "tipoDoc=stenografico_pdf" in pdf_url:
        logging.debug("Classified as stenografici")
        return "stenografici"
    if "bollettini" in pdf_url or ("tipoDoc=pdf" in pdf_url and "sezione=bollettini" in pdf_url):
        logging.debug("Classified as bollettini")
        return "bollettini"
    logging.debug("Classified as other")
    return "other"

def download_pdf(sess: requests.Session, url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with sess.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

def get_available_years_and_months(legislature_url: str) -> dict:
    resp = requests.get(legislature_url)
    soup = BeautifulSoup(resp.text, "html.parser")
    years = {}
    for year_li in soup.select("ul.anni > li"):
        year_a = year_li.find("a")
        if not year_a:
            continue
        try:
            year = int(year_a.text.strip())
        except Exception:
            continue
        months = []
        for month_a in year_li.select("ul.mesi a"):
            month_id = month_a.get("id", "")
            if isinstance(month_id, str) and ".mese." in month_id:
                try:
                    month = int(month_id.split(".mese.")[1])
                    months.append(month)
                except Exception:
                    continue
        years[year] = months
    return years

def download_pdf_task(args, retries=2):
    session, pdf_url, dest_path = args
    for attempt in range(retries + 1):
        try:
            download_pdf(session, pdf_url, dest_path)
            return (pdf_url, True, None)
        except Exception as e:
            if attempt < retries:
                time.sleep(2)  # wait before retrying
                continue
            return (pdf_url, False, str(e))

# ──────────────────────────── Main CLI ─────────────────────────────── #

def main(argv: List[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Scrape Camera PDFs.")
    parser.add_argument("--start", type=int, default=2013,
                        help="first year (inclusive)")
    parser.add_argument("--end",   type=int, default=dt.date.today().year,
                        help="last year (inclusive)")
    parser.add_argument("--out",   type=Path, default=OUT_DIR,
                        help="output directory (default ./pdfs)")
    parser.add_argument("--legislatures", type=str, default=None,
                        help="Comma-separated list of legislatures (e.g. 18,19,20). Default: 19")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args(argv)

    # Parse legislatures
    if args.legislatures:
        legislatures = [int(x) for x in args.legislatures.split(",") if x.strip()]
    else:
        legislatures = LEGISLATURES

    setup_logging(args.debug)
    logging.info(f"Starting scrape: {args.start} to {args.end}, legislatures: {legislatures}, output: {args.out}")

    session = requests.Session()

    for leg in legislatures:
        logging.info(f"Processing legislature {leg}")
        # Build the main page URL for the legislature
        main_url = f"https://www.camera.it/leg{leg}/210"
        available = get_available_years_and_months(main_url)
        all_year_months = [(year, month) for year, months in available.items() for month in months]
        for year, month in tqdm(all_year_months, desc=f"Leg {leg} Months", unit="month"):
            yyyymm = f"{year}{month:02d}"
            base_url = BASE_URL_TEMPLATE.format(
                leg=leg,
                page=PAGE_ID,
                cid=COMMISSIONE_ID,
                ym="{ym}"
            )
            url = base_url.format(ym=yyyymm)
            html = fetch_month_html(session, leg, yyyymm) if base_url == url else session.get(url, timeout=30).text
            if not html:
                logging.debug(f"No HTML for {yyyymm} in legislature {leg}, skipping.")
                continue
            base = session.headers.get("Referer", "https://www.camera.it/")
            if isinstance(base, bytes):
                base = base.decode("utf-8")
            pdfs = extract_pdf_links(html, base=base)
            if not pdfs:
                continue
            tasks = []
            for pdf_url in pdfs:
                logging.debug(f"Processing PDF URL: {pdf_url}")
                filename = infer_filename(pdf_url, leg)
                pdf_type = get_pdf_type(pdf_url)
                if pdf_type not in ("stenografici", "bollettini"):
                    pdf_type = "other"
                year_folder = args.out / f"leg{leg}" / pdf_type / filename[:4]
                dest_path = year_folder / filename
                if dest_path.exists():
                    logging.info(f"Already downloaded: {dest_path}")
                    continue
                tasks.append((session, pdf_url, dest_path))
            if tasks:
                with ThreadPoolExecutor(max_workers=6) as executor:
                    for pdf_url, success, error in tqdm(executor.map(download_pdf_task, tasks), total=len(tasks), desc=f"Downloading PDFs for {yyyymm}"):
                        if not success:
                            logging.error(f"!! Failed {pdf_url}: {error}")
    logging.info("Done.")

if __name__ == "__main__":
    main()
