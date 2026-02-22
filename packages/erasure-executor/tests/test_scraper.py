"""Tests for the scraper connector."""

from erasure_executor.connectors.scraper import extract_by_selectors, parse_page


SAMPLE_HTML = """
<!DOCTYPE html>
<html>
<head><title>Test Page</title><meta name="description" content="A test page"></head>
<body>
  <h1>Hello World</h1>
  <div class="results">
    <div class="result">
      <span class="name">Jane Doe</span>
      <span class="location">Chicago, IL</span>
      <a href="/profile/jane" class="link">View</a>
    </div>
    <div class="result">
      <span class="name">John Doe</span>
      <span class="location">Milwaukee, WI</span>
      <a href="/profile/john" class="link">View</a>
    </div>
  </div>
  <form action="/optout" method="POST">
    <input name="email" type="email" placeholder="Your email">
    <input name="url" type="text">
    <button type="submit">Submit</button>
  </form>
</body>
</html>
"""


def test_parse_page():
    result = parse_page(SAMPLE_HTML)
    assert result["title"] == "Test Page"
    assert result["meta_description"] == "A test page"
    assert "Hello World" in result["text_content"]
    assert len(result["links"]) == 2
    assert len(result["forms"]) == 1
    assert result["forms"][0]["action"] == "/optout"
    assert result["forms"][0]["method"] == "POST"


def test_extract_by_selectors_text():
    selectors = {"names": ".name", "locations": ".location"}
    result = extract_by_selectors(SAMPLE_HTML, selectors)
    assert result["names"] == ["Jane Doe", "John Doe"]
    assert result["locations"] == ["Chicago, IL", "Milwaukee, WI"]


def test_extract_by_selectors_attribute():
    selectors = {"links": ".link @href"}
    result = extract_by_selectors(SAMPLE_HTML, selectors)
    assert result["links"] == ["/profile/jane", "/profile/john"]


def test_extract_by_selectors_empty():
    selectors = {"nonexistent": ".does-not-exist"}
    result = extract_by_selectors(SAMPLE_HTML, selectors)
    assert result["nonexistent"] == []
