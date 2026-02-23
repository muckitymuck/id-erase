"""Search engine discovery for data broker listings.

Uses HTTP scraping of search engine results pages to find potential
data broker listings for a given person's name.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote_plus, urlparse

logger = logging.getLogger(__name__)

# Known data broker domains — used by the heuristic classifier
KNOWN_BROKER_DOMAINS: set[str] = {
    "spokeo.com",
    "beenverified.com",
    "intelius.com",
    "whitepages.com",
    "truepeoplesearch.com",
    "fastpeoplesearch.com",
    "peoplefinder.com",
    "familytreenow.com",
    "radaris.com",
    "acxiom.com",
    "mylife.com",
    "peekyou.com",
    "zabasearch.com",
    "pipl.com",
    "thatsthem.com",
    "ussearch.com",
    "instantcheckmate.com",
    "truthfinder.com",
    "clustrmaps.com",
    "nuwber.com",
    "publicrecordsnow.com",
    "cyberbackgroundchecks.com",
    "neighborwho.com",
    "addresses.com",
    "advancedbackgroundchecks.com",
    "anywho.com",
    "checkpeople.com",
    "publicdatacheck.com",
    "usphonebook.com",
    "voterrecords.com",
}

# URL patterns that indicate a people-search profile page
PROFILE_URL_PATTERNS: list[re.Pattern] = [
    re.compile(r"/people/[A-Z]", re.IGNORECASE),
    re.compile(r"/name/", re.IGNORECASE),
    re.compile(r"/person/", re.IGNORECASE),
    re.compile(r"/profile/", re.IGNORECASE),
    re.compile(r"/search\?.*name=", re.IGNORECASE),
    re.compile(r"/[A-Z][a-z]+-[A-Z][a-z]+/"),  # FirstName-LastName URL pattern
]

# Title/snippet patterns for people-search results
PEOPLE_SEARCH_PATTERNS: list[re.Pattern] = [
    re.compile(r"phone\s*(number|#)", re.IGNORECASE),
    re.compile(r"address(es)?.*history", re.IGNORECASE),
    re.compile(r"background\s*check", re.IGNORECASE),
    re.compile(r"public\s*records?", re.IGNORECASE),
    re.compile(r"people\s*search", re.IGNORECASE),
    re.compile(r"find\s*(people|person|anyone)", re.IGNORECASE),
    re.compile(r"age\s*\d{2}", re.IGNORECASE),
    re.compile(r"relatives|associates", re.IGNORECASE),
    re.compile(r"opt[\s-]*out", re.IGNORECASE),
    re.compile(r"remove\s*(my|your)?\s*(info|information|listing|data)", re.IGNORECASE),
]


@dataclass
class SearchResult:
    """A single search engine result."""
    url: str
    title: str
    snippet: str
    position: int


@dataclass
class ClassifiedResult:
    """A search result with broker classification."""
    url: str
    title: str
    snippet: str
    position: int
    domain: str
    is_known_broker: bool
    is_likely_broker: bool
    confidence: float
    signals: list[str] = field(default_factory=list)


def build_search_queries(full_name: str, city: str = "", state: str = "") -> list[str]:
    """Build search queries to find data broker listings for a person.

    Returns multiple query variations to maximize discovery coverage.
    """
    queries = []
    name = full_name.strip()
    if not name:
        return queries

    # Basic name search
    queries.append(f'"{name}"')

    # Name + location
    location_parts = []
    if city:
        location_parts.append(city.strip())
    if state:
        location_parts.append(state.strip())
    location = ", ".join(location_parts)

    if location:
        queries.append(f'"{name}" {location}')

    # Targeted searches
    queries.append(f'"{name}" public records')
    queries.append(f'"{name}" people search')

    if location:
        queries.append(f'"{name}" {location} address phone')

    return queries


def build_search_url(query: str, engine: str = "google", start: int = 0) -> str:
    """Build a search engine URL for the given query."""
    encoded = quote_plus(query)
    if engine == "bing":
        url = f"https://www.bing.com/search?q={encoded}"
        if start > 0:
            url += f"&first={start + 1}"
        return url
    # Default: Google
    url = f"https://www.google.com/search?q={encoded}&num=20"
    if start > 0:
        url += f"&start={start}"
    return url


def extract_domain(url: str) -> str:
    """Extract the registrable domain from a URL."""
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        # Strip www. prefix
        if hostname.startswith("www."):
            hostname = hostname[4:]
        return hostname.lower()
    except Exception:
        return ""


def classify_result(result: SearchResult) -> ClassifiedResult:
    """Classify a search result as a data broker listing or not.

    Uses a combination of:
    1. Known broker domain matching
    2. URL pattern matching
    3. Title/snippet keyword matching
    """
    domain = extract_domain(result.url)
    signals: list[str] = []
    score = 0.0

    # Signal 1: Known broker domain (strongest signal)
    is_known = domain in KNOWN_BROKER_DOMAINS
    if is_known:
        signals.append(f"known_broker_domain:{domain}")
        score += 0.7

    # Signal 2: URL pattern matching
    for pattern in PROFILE_URL_PATTERNS:
        if pattern.search(result.url):
            signals.append(f"profile_url_pattern:{pattern.pattern}")
            score += 0.15
            break  # Only count once

    # Signal 3: Title/snippet pattern matching
    text = f"{result.title} {result.snippet}"
    pattern_hits = 0
    for pattern in PEOPLE_SEARCH_PATTERNS:
        if pattern.search(text):
            signals.append(f"text_pattern:{pattern.pattern}")
            pattern_hits += 1
            if pattern_hits >= 3:
                break  # Cap at 3 text signals

    score += min(pattern_hits * 0.1, 0.3)

    # Cap at 1.0
    confidence = min(score, 1.0)
    is_likely = confidence >= 0.3

    return ClassifiedResult(
        url=result.url,
        title=result.title,
        snippet=result.snippet,
        position=result.position,
        domain=domain,
        is_known_broker=is_known,
        is_likely_broker=is_likely,
        confidence=confidence,
        signals=signals,
    )


def parse_search_results_from_html(html: str) -> list[SearchResult]:
    """Parse search results from a search engine results page HTML.

    Supports Google and Bing result page formats.
    Falls back to generic link extraction.
    """
    from erasure_executor.connectors.scraper import parse_page

    parsed = parse_page(html)
    links = parsed.get("links", [])

    results: list[SearchResult] = []
    seen_urls: set[str] = set()
    position = 0

    for link in links:
        if not isinstance(link, dict):
            continue
        url = link.get("href", "")
        text = link.get("text", "")

        if not url or not url.startswith("http"):
            continue

        # Skip search engine internal links
        domain = extract_domain(url)
        if domain in ("google.com", "bing.com", "google.co.uk", "webcache.googleusercontent.com"):
            continue
        if "/search?" in url or "/images/" in url or "/maps/" in url:
            continue

        if url in seen_urls:
            continue
        seen_urls.add(url)

        position += 1
        results.append(SearchResult(
            url=url,
            title=text[:200],
            snippet="",  # Snippet extraction is best-effort from surrounding text
            position=position,
        ))

    return results


def discover_brokers(
    search_results: list[SearchResult],
    known_broker_ids: set[str] | None = None,
) -> list[ClassifiedResult]:
    """Classify search results and return likely data broker listings.

    Args:
        search_results: Raw search results from a search engine.
        known_broker_ids: Set of broker IDs already in the catalog (for dedup).

    Returns:
        List of classified results sorted by confidence descending.
    """
    classified = [classify_result(r) for r in search_results]

    # Filter to likely brokers
    likely = [c for c in classified if c.is_likely_broker]

    # Sort by confidence descending, then position ascending
    likely.sort(key=lambda c: (-c.confidence, c.position))

    return likely
