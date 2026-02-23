"""Tests for search engine discovery and broker classification."""
from __future__ import annotations

from erasure_executor.discovery.search import (
    KNOWN_BROKER_DOMAINS,
    SearchResult,
    build_search_queries,
    build_search_url,
    classify_result,
    discover_brokers,
    extract_domain,
)


class TestBuildSearchQueries:
    def test_name_only(self):
        queries = build_search_queries("Jane Doe")
        assert len(queries) >= 2
        assert '"Jane Doe"' in queries[0]

    def test_name_with_location(self):
        queries = build_search_queries("Jane Doe", "Chicago", "IL")
        location_query = [q for q in queries if "Chicago" in q]
        assert len(location_query) >= 1

    def test_empty_name_returns_empty(self):
        assert build_search_queries("") == []

    def test_includes_public_records_query(self):
        queries = build_search_queries("Jane Doe")
        pr_queries = [q for q in queries if "public records" in q]
        assert len(pr_queries) >= 1

    def test_includes_people_search_query(self):
        queries = build_search_queries("Jane Doe")
        ps_queries = [q for q in queries if "people search" in q]
        assert len(ps_queries) >= 1


class TestBuildSearchUrl:
    def test_google_default(self):
        url = build_search_url("Jane Doe")
        assert "google.com/search" in url
        assert "Jane+Doe" in url or "Jane%20Doe" in url

    def test_bing(self):
        url = build_search_url("Jane Doe", engine="bing")
        assert "bing.com/search" in url

    def test_google_pagination(self):
        url = build_search_url("Jane Doe", start=20)
        assert "start=20" in url

    def test_bing_pagination(self):
        url = build_search_url("Jane Doe", engine="bing", start=10)
        assert "first=11" in url


class TestExtractDomain:
    def test_simple_url(self):
        assert extract_domain("https://www.spokeo.com/people/Jane-Doe") == "spokeo.com"

    def test_strips_www(self):
        assert extract_domain("https://www.example.com/path") == "example.com"

    def test_no_www(self):
        assert extract_domain("https://spokeo.com/") == "spokeo.com"

    def test_invalid_url(self):
        assert extract_domain("not a url") == ""

    def test_subdomain(self):
        assert extract_domain("https://search.example.com/") == "search.example.com"


class TestClassifyResult:
    def test_known_broker_high_confidence(self):
        result = SearchResult(
            url="https://www.spokeo.com/people/Jane-Doe/Chicago-IL",
            title="Jane Doe - Spokeo",
            snippet="View phone number, address, and more",
            position=1,
        )
        cr = classify_result(result)
        assert cr.is_known_broker is True
        assert cr.is_likely_broker is True
        assert cr.confidence >= 0.7
        assert cr.domain == "spokeo.com"

    def test_known_broker_with_url_pattern(self):
        result = SearchResult(
            url="https://www.beenverified.com/people/Jane-Doe/",
            title="Jane Doe Background Check",
            snippet="Background check and public records",
            position=2,
        )
        cr = classify_result(result)
        assert cr.is_known_broker is True
        assert cr.confidence >= 0.7

    def test_unknown_domain_with_signals(self):
        result = SearchResult(
            url="https://www.newpeoplesearch.com/person/Jane-Doe",
            title="Jane Doe - People Search",
            snippet="Find phone number, address history, background check",
            position=3,
        )
        cr = classify_result(result)
        assert cr.is_known_broker is False
        assert cr.is_likely_broker is True
        assert cr.confidence >= 0.3
        assert len(cr.signals) >= 1

    def test_unrelated_result_low_confidence(self):
        result = SearchResult(
            url="https://www.linkedin.com/in/janedoe",
            title="Jane Doe - Software Engineer",
            snippet="View Jane Doe's profile on LinkedIn",
            position=5,
        )
        cr = classify_result(result)
        assert cr.is_known_broker is False
        assert cr.confidence < 0.3

    def test_confidence_capped_at_1(self):
        # Known broker + URL pattern + multiple text patterns
        result = SearchResult(
            url="https://www.spokeo.com/people/Jane-Doe",
            title="Jane Doe People Search - Phone Number Address Background Check",
            snippet="Find people, phone number, address history, public records, background check, relatives",
            position=1,
        )
        cr = classify_result(result)
        assert cr.confidence <= 1.0

    def test_text_patterns_contribute(self):
        result = SearchResult(
            url="https://unknown-broker.com/search?name=jane",
            title="Jane Doe - Public Records and Phone Number",
            snippet="Background check results with address history",
            position=1,
        )
        cr = classify_result(result)
        assert len(cr.signals) >= 2


class TestDiscoverBrokers:
    def test_filters_to_likely(self):
        results = [
            SearchResult(url="https://www.spokeo.com/Jane-Doe", title="Spokeo", snippet="", position=1),
            SearchResult(url="https://www.linkedin.com/janedoe", title="LinkedIn", snippet="", position=2),
        ]
        discovered = discover_brokers(results)
        domains = [d.domain for d in discovered]
        assert "spokeo.com" in domains
        assert "linkedin.com" not in domains

    def test_sorted_by_confidence(self):
        results = [
            SearchResult(url="https://unknown.com/person/Jane", title="People Search Phone", snippet="background check", position=1),
            SearchResult(url="https://www.spokeo.com/Jane-Doe", title="Spokeo", snippet="", position=2),
        ]
        discovered = discover_brokers(results)
        assert len(discovered) >= 1
        # Known broker should be first (higher confidence)
        assert discovered[0].domain == "spokeo.com"

    def test_empty_results(self):
        assert discover_brokers([]) == []


class TestKnownBrokerDomains:
    def test_has_core_brokers(self):
        assert "spokeo.com" in KNOWN_BROKER_DOMAINS
        assert "beenverified.com" in KNOWN_BROKER_DOMAINS
        assert "whitepages.com" in KNOWN_BROKER_DOMAINS

    def test_minimum_count(self):
        assert len(KNOWN_BROKER_DOMAINS) >= 20
