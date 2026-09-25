"""
Mizani Africa official-source discovery.

The current Mizani website mainly exposes an older archive, while newer releases
may first appear on the pollster's official social channels. This extractor
therefore monitors the official website conservatively and only returns recent
(2025-2027) election/presidential items. Social-only releases remain manual
review items until a direct post URL and methodology can be verified.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

MIZANI_HOME = "https://www.mizaniafrica.com/"
REQUEST_TIMEOUT = 30

HEADERS = {
    "User-Agent": (
        "KenyaPollsTracker/1.2 "
        "(primary-source polling monitor; contact: repository owner)"
    )
}

RELEVANT_TERMS = [
    "presidential",
    "president",
    "2027",
    "election",
    "poll",
    "preference",
    "candidate",
    "aspirant",
]

RECENT_YEAR_TERMS = ["2025", "2026", "2027"]


@dataclass
class DiscoveredSource:
    pollster: str
    title: str
    page_url: str
    pdf_url: Optional[str]
    published_date: Optional[str]


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _is_mizani_url(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return False
    return host in {"mizaniafrica.com", "www.mizaniafrica.com"}


def _is_pdf(url: str) -> bool:
    return urlparse(url).path.lower().endswith(".pdf")


def _looks_relevant(title: str, url: str) -> bool:
    combined = f"{title} {url}".lower()
    return (
        any(term in combined for term in RELEVANT_TERMS)
        and any(year in combined for year in RECENT_YEAR_TERMS)
    )


def discover_sources() -> List[Dict]:
    response = requests.get(MIZANI_HOME, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    discovered: Dict[str, DiscoveredSource] = {}

    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "").strip()
        if not href:
            continue

        url = urljoin(MIZANI_HOME, href).split("#")[0]
        if not _is_mizani_url(url):
            continue

        title = _clean(anchor.get_text(" ", strip=True)) or "Mizani Africa poll release"
        if not _looks_relevant(title, url):
            continue

        source = DiscoveredSource(
            pollster="Mizani Africa",
            title=title,
            page_url=MIZANI_HOME if _is_pdf(url) else url,
            pdf_url=url if _is_pdf(url) else None,
            published_date=None,
        )
        discovered[url] = source

    return [asdict(source) for source in discovered.values()]
