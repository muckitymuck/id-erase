"""Identity matching engine for comparing broker listings against PII profiles.

Two-stage approach:
1. Heuristic scoring: weighted field comparison producing a confidence score
2. LLM verification: for borderline cases (configurable threshold range)
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from rapidfuzz import fuzz

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Name normalization
# ---------------------------------------------------------------------------

_SUFFIXES = re.compile(
    r"\b(jr\.?|sr\.?|ii|iii|iv|v|esq\.?|phd|md|dds|dvm)\b",
    re.IGNORECASE,
)
_WHITESPACE = re.compile(r"\s+")


def normalize_name(name: str) -> str:
    """Lowercase, strip suffixes (Jr/Sr/III), collapse whitespace."""
    n = name.lower().strip()
    n = _SUFFIXES.sub("", n)
    n = n.replace(",", " ").replace(".", " ")
    n = _WHITESPACE.sub(" ", n).strip()
    return n


def _name_parts(name: str) -> list[str]:
    """Split a normalized name into parts."""
    return [p for p in name.split() if p]


def names_match(a: str, b: str) -> tuple[bool, float]:
    """Compare two names. Returns (match, score).

    Score meaning:
    - 1.0: exact match after normalization
    - 0.8-0.99: fuzzy match (Levenshtein / token sort)
    - 0.5-0.79: partial match (first+last match, middle differs)
    - 0.0: no match
    """
    na = normalize_name(a)
    nb = normalize_name(b)

    if na == nb:
        return True, 1.0

    # Token sort ratio handles reordering: "John A Smith" vs "Smith John A"
    token_score = fuzz.token_sort_ratio(na, nb) / 100.0
    if token_score >= 0.92:
        return True, token_score

    # Check first+last name match (ignoring middle name/initial)
    pa = _name_parts(na)
    pb = _name_parts(nb)
    if len(pa) >= 2 and len(pb) >= 2:
        # Compare first and last
        first_match = fuzz.ratio(pa[0], pb[0]) / 100.0 >= 0.85
        last_match = fuzz.ratio(pa[-1], pb[-1]) / 100.0 >= 0.85
        if first_match and last_match:
            return True, 0.75

    # Single initial match: "J Smith" matches "John Smith"
    if len(pa) >= 2 and len(pb) >= 2:
        if (len(pa[0]) == 1 and pb[0].startswith(pa[0])) or (len(pb[0]) == 1 and pa[0].startswith(pb[0])):
            if fuzz.ratio(pa[-1], pb[-1]) / 100.0 >= 0.85:
                return True, 0.65

    if token_score >= 0.70:
        return True, token_score * 0.8  # Discount low fuzzy matches

    return False, token_score


# ---------------------------------------------------------------------------
# Location matching
# ---------------------------------------------------------------------------

def _normalize_state(state: str) -> str:
    """Normalize state to uppercase abbreviation."""
    s = state.strip().upper()
    # Common full names to abbreviations
    _state_map = {
        "ALABAMA": "AL", "ALASKA": "AK", "ARIZONA": "AZ", "ARKANSAS": "AR",
        "CALIFORNIA": "CA", "COLORADO": "CO", "CONNECTICUT": "CT", "DELAWARE": "DE",
        "FLORIDA": "FL", "GEORGIA": "GA", "HAWAII": "HI", "IDAHO": "ID",
        "ILLINOIS": "IL", "INDIANA": "IN", "IOWA": "IA", "KANSAS": "KS",
        "KENTUCKY": "KY", "LOUISIANA": "LA", "MAINE": "ME", "MARYLAND": "MD",
        "MASSACHUSETTS": "MA", "MICHIGAN": "MI", "MINNESOTA": "MN", "MISSISSIPPI": "MS",
        "MISSOURI": "MO", "MONTANA": "MT", "NEBRASKA": "NE", "NEVADA": "NV",
        "NEW HAMPSHIRE": "NH", "NEW JERSEY": "NJ", "NEW MEXICO": "NM", "NEW YORK": "NY",
        "NORTH CAROLINA": "NC", "NORTH DAKOTA": "ND", "OHIO": "OH", "OKLAHOMA": "OK",
        "OREGON": "OR", "PENNSYLVANIA": "PA", "RHODE ISLAND": "RI",
        "SOUTH CAROLINA": "SC", "SOUTH DAKOTA": "SD", "TENNESSEE": "TN", "TEXAS": "TX",
        "UTAH": "UT", "VERMONT": "VT", "VIRGINIA": "VA", "WASHINGTON": "WA",
        "WEST VIRGINIA": "WV", "WISCONSIN": "WI", "WYOMING": "WY",
        "DISTRICT OF COLUMBIA": "DC",
    }
    return _state_map.get(s, s)


def location_matches(listing_location: str, profile_addresses: list[dict[str, Any]]) -> tuple[bool, float]:
    """Compare a listing location string against profile addresses.

    Listing location is typically "City, ST" format from broker sites.
    Returns (match, score).
    """
    if not listing_location or not profile_addresses:
        return False, 0.0

    # Parse "City, ST" or "City, State"
    parts = [p.strip() for p in listing_location.split(",")]
    listing_city = parts[0].lower() if parts else ""
    listing_state = _normalize_state(parts[1]) if len(parts) > 1 else ""

    best_score = 0.0
    for addr in profile_addresses:
        addr_city = str(addr.get("city", "")).lower()
        addr_state = _normalize_state(str(addr.get("state", "")))

        if not addr_city:
            continue

        city_score = fuzz.ratio(listing_city, addr_city) / 100.0
        state_match = listing_state == addr_state if listing_state and addr_state else True

        if city_score >= 0.90 and state_match:
            score = 1.0 if addr.get("current") else 0.85
            best_score = max(best_score, score)
        elif city_score >= 0.90:
            # City matches but state doesn't
            best_score = max(best_score, 0.3)
        elif state_match and listing_state:
            # Same state but different city
            best_score = max(best_score, 0.15)

    return best_score >= 0.5, best_score


# ---------------------------------------------------------------------------
# Age matching
# ---------------------------------------------------------------------------

def age_matches(listing_age: int | str | None, date_of_birth: str | None, tolerance: int = 2) -> tuple[bool, float]:
    """Compare listing age against calculated age from DOB.

    Returns (match, score).
    """
    if listing_age is None or date_of_birth is None:
        return False, 0.0

    try:
        listing_age_int = int(listing_age)
    except (ValueError, TypeError):
        return False, 0.0

    try:
        dob = datetime.strptime(date_of_birth, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return False, 0.0

    today = date.today()
    calculated_age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

    diff = abs(calculated_age - listing_age_int)
    if diff == 0:
        return True, 1.0
    if diff <= tolerance:
        return True, 1.0 - (diff * 0.1)
    return False, max(0.0, 1.0 - (diff * 0.15))


# ---------------------------------------------------------------------------
# Phone matching
# ---------------------------------------------------------------------------

_PHONE_DIGITS = re.compile(r"\D")


def _normalize_phone(phone: str) -> str:
    digits = _PHONE_DIGITS.sub("", phone)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits


def phone_matches(listing_phone: str | None, profile_phones: list[dict[str, Any]]) -> tuple[bool, float]:
    """Compare a phone number from a listing against profile phones."""
    if not listing_phone or not profile_phones:
        return False, 0.0

    norm_listing = _normalize_phone(listing_phone)
    if len(norm_listing) < 7:
        return False, 0.0

    for p in profile_phones:
        norm_profile = _normalize_phone(str(p.get("number", "")))
        if norm_listing == norm_profile:
            return True, 1.0
        # Last 7 digits match (area code might differ)
        if len(norm_listing) >= 7 and len(norm_profile) >= 7:
            if norm_listing[-7:] == norm_profile[-7:]:
                return True, 0.7

    return False, 0.0


# ---------------------------------------------------------------------------
# Relatives matching
# ---------------------------------------------------------------------------

def relatives_match(listing_relatives: list[str], profile_relatives: list[str]) -> tuple[bool, float]:
    """Check if any listing relatives match profile relatives."""
    if not listing_relatives or not profile_relatives:
        return False, 0.0

    norm_listing = {normalize_name(r) for r in listing_relatives if r.strip()}
    norm_profile = {normalize_name(r) for r in profile_relatives if r.strip()}

    matches = 0
    for lr in norm_listing:
        for pr in norm_profile:
            match, score = names_match(lr, pr)
            if match and score >= 0.7:
                matches += 1
                break

    if matches == 0:
        return False, 0.0

    # Score based on proportion of profile relatives found
    score = min(1.0, matches / max(len(norm_profile), 1))
    return True, score


# ---------------------------------------------------------------------------
# Heuristic scoring
# ---------------------------------------------------------------------------

# Weights for combining field scores
FIELD_WEIGHTS = {
    "name": 0.35,
    "location": 0.25,
    "age": 0.15,
    "phone": 0.10,
    "relatives": 0.15,
}


@dataclass
class MatchResult:
    """Result of matching a listing against a profile."""
    listing_data: dict[str, Any]
    confidence: float
    matched_fields: dict[str, float]
    needs_llm_verify: bool = False
    llm_verified: bool | None = None
    llm_confidence: float | None = None


def heuristic_match(
    listing: dict[str, Any],
    profile: dict[str, Any],
    weights: dict[str, float] | None = None,
) -> MatchResult:
    """Score a listing against a profile using weighted field comparison.

    Args:
        listing: Extracted data from a broker listing. Expected keys:
            name, location, age, phone, relatives (all optional)
        profile: Decrypted PII profile data. Expected keys:
            full_name, aliases, addresses, date_of_birth, phone_numbers, relatives
        weights: Optional custom weights (defaults to FIELD_WEIGHTS)

    Returns:
        MatchResult with confidence score and field breakdown
    """
    w = weights or FIELD_WEIGHTS
    matched_fields: dict[str, float] = {}
    weighted_sum = 0.0
    total_weight = 0.0

    # --- Name ---
    listing_name = listing.get("name", "")
    if listing_name:
        best_name_score = 0.0
        names_to_check = [profile.get("full_name", "")] + profile.get("aliases", [])
        for pname in names_to_check:
            if pname:
                _, score = names_match(listing_name, pname)
                best_name_score = max(best_name_score, score)
        matched_fields["name"] = best_name_score
        weighted_sum += best_name_score * w.get("name", 0)
        total_weight += w.get("name", 0)

    # --- Location ---
    listing_location = listing.get("location", "")
    if listing_location and profile.get("addresses"):
        addrs = profile["addresses"]
        if isinstance(addrs, list) and addrs:
            addr_dicts = []
            for a in addrs:
                if isinstance(a, dict):
                    addr_dicts.append(a)
            _, loc_score = location_matches(listing_location, addr_dicts)
            matched_fields["location"] = loc_score
            weighted_sum += loc_score * w.get("location", 0)
            total_weight += w.get("location", 0)

    # --- Age ---
    listing_age = listing.get("age")
    dob = profile.get("date_of_birth")
    if listing_age is not None and dob:
        _, age_score = age_matches(listing_age, dob)
        matched_fields["age"] = age_score
        weighted_sum += age_score * w.get("age", 0)
        total_weight += w.get("age", 0)

    # --- Phone ---
    listing_phone = listing.get("phone")
    if listing_phone and profile.get("phone_numbers"):
        phones = profile["phone_numbers"]
        if isinstance(phones, list) and phones:
            _, phone_score = phone_matches(listing_phone, phones)
            matched_fields["phone"] = phone_score
            weighted_sum += phone_score * w.get("phone", 0)
            total_weight += w.get("phone", 0)

    # --- Relatives ---
    listing_relatives = listing.get("relatives", [])
    if listing_relatives and profile.get("relatives"):
        _, rel_score = relatives_match(listing_relatives, profile["relatives"])
        matched_fields["relatives"] = rel_score
        weighted_sum += rel_score * w.get("relatives", 0)
        total_weight += w.get("relatives", 0)

    # Calculate final confidence
    confidence = weighted_sum / total_weight if total_weight > 0 else 0.0

    # Determine if LLM verification needed (borderline range)
    needs_llm = 0.4 <= confidence <= 0.8

    return MatchResult(
        listing_data=listing,
        confidence=round(confidence, 4),
        matched_fields=matched_fields,
        needs_llm_verify=needs_llm,
    )
