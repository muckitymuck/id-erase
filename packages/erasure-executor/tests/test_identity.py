"""Tests for identity matching engine."""

from erasure_executor.matching.identity import (
    age_matches,
    heuristic_match,
    location_matches,
    names_match,
    normalize_name,
    phone_matches,
    relatives_match,
)


# ---------------------------------------------------------------------------
# Name normalization
# ---------------------------------------------------------------------------

def test_normalize_name_basic():
    assert normalize_name("John Smith") == "john smith"


def test_normalize_name_suffix():
    assert normalize_name("John Smith Jr.") == "john smith"
    assert normalize_name("Robert Jones III") == "robert jones"
    assert normalize_name("Jane Doe Sr") == "jane doe"


def test_normalize_name_whitespace():
    assert normalize_name("  John   A   Smith  ") == "john a smith"


# ---------------------------------------------------------------------------
# Name matching
# ---------------------------------------------------------------------------

def test_names_match_exact():
    match, score = names_match("John Smith", "john smith")
    assert match is True
    assert score == 1.0


def test_names_match_suffix_variation():
    match, score = names_match("John Smith Jr.", "John Smith")
    assert match is True
    assert score >= 0.9


def test_names_match_middle_initial():
    match, score = names_match("John A Smith", "John Smith")
    assert match is True
    assert score >= 0.65


def test_names_match_first_initial():
    match, score = names_match("J Smith", "John Smith")
    assert match is True
    assert score >= 0.6


def test_names_match_reorder():
    match, score = names_match("Smith, John", "John Smith")
    assert match is True
    assert score >= 0.85


def test_names_no_match():
    match, score = names_match("Jane Williams", "Robert Johnson")
    assert match is False
    assert score < 0.5


def test_names_match_common_typo():
    match, score = names_match("Jonh Smith", "John Smith")
    assert match is True
    assert score >= 0.7


# ---------------------------------------------------------------------------
# Location matching
# ---------------------------------------------------------------------------

def test_location_exact_match():
    addrs = [{"city": "Chicago", "state": "IL", "current": True}]
    match, score = location_matches("Chicago, IL", addrs)
    assert match is True
    assert score == 1.0


def test_location_full_state_name():
    addrs = [{"city": "Chicago", "state": "Illinois", "current": False}]
    match, score = location_matches("Chicago, IL", addrs)
    assert match is True
    assert score >= 0.8


def test_location_wrong_city():
    addrs = [{"city": "Milwaukee", "state": "WI", "current": True}]
    match, score = location_matches("Chicago, IL", addrs)
    assert match is False


def test_location_former_address():
    addrs = [
        {"city": "Denver", "state": "CO", "current": True},
        {"city": "Chicago", "state": "IL", "current": False},
    ]
    match, score = location_matches("Chicago, IL", addrs)
    assert match is True
    assert score >= 0.8  # Former address, slightly lower


def test_location_empty():
    match, score = location_matches("", [])
    assert match is False
    assert score == 0.0


# ---------------------------------------------------------------------------
# Age matching
# ---------------------------------------------------------------------------

def test_age_exact():
    # Person born 1990-06-15, today would be 35 (in 2026)
    match, score = age_matches(35, "1990-06-15")
    assert match is True
    assert score >= 0.8


def test_age_within_tolerance():
    match, score = age_matches(36, "1990-06-15", tolerance=2)
    assert match is True
    assert score >= 0.7


def test_age_outside_tolerance():
    match, score = age_matches(50, "1990-06-15", tolerance=2)
    assert match is False


def test_age_none_inputs():
    match, score = age_matches(None, None)
    assert match is False


# ---------------------------------------------------------------------------
# Phone matching
# ---------------------------------------------------------------------------

def test_phone_exact():
    phones = [{"number": "312-555-1234", "type": "mobile"}]
    match, score = phone_matches("3125551234", phones)
    assert match is True
    assert score == 1.0


def test_phone_with_country_code():
    phones = [{"number": "312-555-1234", "type": "mobile"}]
    match, score = phone_matches("+1 (312) 555-1234", phones)
    assert match is True
    assert score == 1.0


def test_phone_no_match():
    phones = [{"number": "312-555-1234", "type": "mobile"}]
    match, score = phone_matches("773-555-9999", phones)
    assert match is False


def test_phone_empty():
    match, score = phone_matches(None, [])
    assert match is False


# ---------------------------------------------------------------------------
# Relatives matching
# ---------------------------------------------------------------------------

def test_relatives_overlap():
    listing = ["Mary Smith", "Robert Smith"]
    profile = ["Mary Smith", "David Smith", "Robert Smith Jr"]
    match, score = relatives_match(listing, profile)
    assert match is True
    assert score > 0.0


def test_relatives_no_overlap():
    listing = ["Alice Jones"]
    profile = ["Bob Williams"]
    match, score = relatives_match(listing, profile)
    assert match is False


def test_relatives_empty():
    match, score = relatives_match([], [])
    assert match is False


# ---------------------------------------------------------------------------
# Heuristic matching (full)
# ---------------------------------------------------------------------------

def test_heuristic_strong_match():
    listing = {
        "name": "Jane Doe",
        "location": "Chicago, IL",
        "age": 35,
    }
    profile = {
        "full_name": "Jane Doe",
        "aliases": [],
        "date_of_birth": "1990-06-15",
        "addresses": [{"city": "Chicago", "state": "IL", "current": True}],
        "phone_numbers": [],
        "relatives": [],
    }
    result = heuristic_match(listing, profile)
    assert result.confidence >= 0.8
    assert result.matched_fields["name"] >= 0.9


def test_heuristic_name_only():
    listing = {"name": "John Smith"}
    profile = {
        "full_name": "John Smith",
        "aliases": [],
        "addresses": [],
        "phone_numbers": [],
        "relatives": [],
    }
    result = heuristic_match(listing, profile)
    assert result.confidence >= 0.8  # Name match is 35% weight but with 100% score, full weight


def test_heuristic_common_name_different_location():
    listing = {
        "name": "John Smith",
        "location": "Seattle, WA",
    }
    profile = {
        "full_name": "John Smith",
        "aliases": [],
        "addresses": [{"city": "Chicago", "state": "IL", "current": True}],
        "phone_numbers": [],
        "relatives": [],
    }
    result = heuristic_match(listing, profile)
    # Name matches but location doesn't — lower confidence
    assert result.confidence < 0.8


def test_heuristic_alias_match():
    listing = {"name": "Johnny Smith"}
    profile = {
        "full_name": "John Smith",
        "aliases": ["Johnny Smith"],
        "addresses": [],
        "phone_numbers": [],
        "relatives": [],
    }
    result = heuristic_match(listing, profile)
    assert result.confidence >= 0.8  # Alias exact match


def test_heuristic_no_match():
    listing = {
        "name": "Robert Williams",
        "location": "Miami, FL",
        "age": 55,
    }
    profile = {
        "full_name": "Jane Doe",
        "aliases": [],
        "date_of_birth": "1990-01-01",
        "addresses": [{"city": "Chicago", "state": "IL", "current": True}],
        "phone_numbers": [],
        "relatives": [],
    }
    result = heuristic_match(listing, profile)
    assert result.confidence < 0.3


def test_heuristic_borderline_needs_llm():
    listing = {
        "name": "J Smith",
        "location": "Chicago, IL",
    }
    profile = {
        "full_name": "John Smith",
        "aliases": [],
        "addresses": [{"city": "Chicago", "state": "IL", "current": True}],
        "phone_numbers": [],
        "relatives": [],
    }
    result = heuristic_match(listing, profile)
    # Partial name match + good location — borderline
    assert 0.3 <= result.confidence <= 0.9
