from __future__ import annotations

from bs4 import BeautifulSoup


def parse_page(html: str) -> dict:
    """Parse an HTML page and extract general structural data."""
    soup = BeautifulSoup(html, "lxml")

    title = soup.title.string.strip() if soup.title and soup.title.string else None

    m = soup.find("meta", attrs={"name": "description"})
    meta_description = str(m.get("content", "")).strip() if m else None

    return {
        "title": title,
        "meta_description": meta_description,
        "text_content": soup.get_text(" ", strip=True)[:50000],
        "links": [
            {"href": a.get("href", ""), "text": a.get_text(" ", strip=True)}
            for a in soup.find_all("a", href=True)
        ],
        "forms": [
            {
                "action": form.get("action", ""),
                "method": form.get("method", "GET").upper(),
                "inputs": [
                    {
                        "name": inp.get("name", ""),
                        "type": inp.get("type", "text"),
                        "id": inp.get("id", ""),
                    }
                    for inp in form.find_all(["input", "select", "textarea"])
                    if inp.get("name")
                ],
            }
            for form in soup.find_all("form")
        ],
    }


def extract_by_selectors(html: str, selectors: dict) -> dict:
    """Extract data from HTML using CSS selectors.

    Selector format:
      - ".class-name"        -> text content
      - ".class-name @href"  -> attribute value
    """
    soup = BeautifulSoup(html, "lxml")
    results = {}

    for key, selector in selectors.items():
        if " @" in selector:
            css, attr = selector.rsplit(" @", 1)
            elements = soup.select(css)
            results[key] = [el.get(attr.strip(), "") for el in elements]
        else:
            elements = soup.select(selector)
            results[key] = [el.get_text(" ", strip=True) for el in elements]

    return results
