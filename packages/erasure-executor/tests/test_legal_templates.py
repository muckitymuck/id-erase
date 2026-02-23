"""Tests for CCPA and GDPR legal letter templates."""
from __future__ import annotations

from erasure_executor.legal.templates import (
    AVAILABLE_TEMPLATES,
    render_letter,
    _format_address_block,
)


SAMPLE_PROFILE = {
    "full_name": "Jane A. Doe",
    "aliases": ["Jane Doe", "J. Doe"],
    "date_of_birth": "1985-03-15",
    "email_addresses": ["jane.doe@example.com"],
    "phone_numbers": [{"number": "555-123-4567", "type": "mobile"}],
    "addresses": [
        {
            "street": "123 Main St",
            "city": "Chicago",
            "state": "IL",
            "zip": "60601",
            "current": True,
        },
        {
            "street": "456 Oak Ave",
            "city": "Springfield",
            "state": "IL",
            "zip": "62701",
            "current": False,
        },
    ],
}


class TestAvailableTemplates:
    def test_ccpa_available(self):
        assert "ccpa_deletion" in AVAILABLE_TEMPLATES

    def test_gdpr_available(self):
        assert "gdpr_erasure" in AVAILABLE_TEMPLATES

    def test_exactly_two_templates(self):
        assert len(AVAILABLE_TEMPLATES) == 2


class TestRenderCCPA:
    def test_renders_full_name(self):
        letter = render_letter("ccpa_deletion", SAMPLE_PROFILE, "Spokeo")
        assert "Jane A. Doe" in letter.body

    def test_renders_broker_name(self):
        letter = render_letter("ccpa_deletion", SAMPLE_PROFILE, "Spokeo")
        assert "Spokeo" in letter.body

    def test_renders_ccpa_reference(self):
        letter = render_letter("ccpa_deletion", SAMPLE_PROFILE, "Spokeo")
        assert "California Consumer Privacy Act" in letter.body
        assert "1798.100" in letter.body

    def test_renders_email(self):
        letter = render_letter("ccpa_deletion", SAMPLE_PROFILE, "Spokeo")
        assert "jane.doe@example.com" in letter.body

    def test_renders_aliases(self):
        letter = render_letter("ccpa_deletion", SAMPLE_PROFILE, "Spokeo")
        assert "Jane Doe" in letter.body
        assert "J. Doe" in letter.body

    def test_renders_dob(self):
        letter = render_letter("ccpa_deletion", SAMPLE_PROFILE, "Spokeo")
        assert "1985-03-15" in letter.body

    def test_renders_phone(self):
        letter = render_letter("ccpa_deletion", SAMPLE_PROFILE, "Spokeo")
        assert "555-123-4567" in letter.body

    def test_renders_address(self):
        letter = render_letter("ccpa_deletion", SAMPLE_PROFILE, "Spokeo")
        assert "123 Main St" in letter.body
        assert "Chicago" in letter.body

    def test_subject_contains_name(self):
        letter = render_letter("ccpa_deletion", SAMPLE_PROFILE, "Spokeo")
        assert "CCPA" in letter.subject
        assert "Jane A. Doe" in letter.subject

    def test_letter_metadata(self):
        letter = render_letter("ccpa_deletion", SAMPLE_PROFILE, "Spokeo", "123 Corporate Blvd")
        assert letter.template_id == "ccpa_deletion"
        assert letter.recipient_name == "Spokeo"
        assert letter.recipient_address == "123 Corporate Blvd"


class TestRenderGDPR:
    def test_renders_gdpr_reference(self):
        letter = render_letter("gdpr_erasure", SAMPLE_PROFILE, "Radaris")
        assert "Article 17" in letter.body
        assert "General Data Protection Regulation" in letter.body

    def test_renders_full_name(self):
        letter = render_letter("gdpr_erasure", SAMPLE_PROFILE, "Radaris")
        assert "Jane A. Doe" in letter.body

    def test_subject_contains_gdpr(self):
        letter = render_letter("gdpr_erasure", SAMPLE_PROFILE, "Radaris")
        assert "GDPR" in letter.subject

    def test_renders_data_protection_officer(self):
        letter = render_letter("gdpr_erasure", SAMPLE_PROFILE, "Radaris")
        assert "Data Protection Officer" in letter.body


class TestEdgeCases:
    def test_unknown_template_raises(self):
        import pytest
        with pytest.raises(ValueError, match="Unknown template"):
            render_letter("unknown", SAMPLE_PROFILE, "Spokeo")

    def test_minimal_profile(self):
        minimal = {"full_name": "John Smith"}
        letter = render_letter("ccpa_deletion", minimal, "Spokeo")
        assert "John Smith" in letter.body

    def test_no_aliases(self):
        profile = {"full_name": "John Smith", "email_addresses": ["j@example.com"]}
        letter = render_letter("ccpa_deletion", profile, "Spokeo")
        assert "Also known as" not in letter.body

    def test_no_dob(self):
        profile = {"full_name": "John Smith"}
        letter = render_letter("ccpa_deletion", profile, "Spokeo")
        assert "Date of Birth" not in letter.body

    def test_empty_broker_address(self):
        letter = render_letter("ccpa_deletion", SAMPLE_PROFILE, "Spokeo")
        assert "[Address Not Available]" in letter.body


class TestFormatAddressBlock:
    def test_empty_list(self):
        assert _format_address_block([]) == ""

    def test_single_address(self):
        result = _format_address_block([{"street": "123 Main", "city": "Chicago", "state": "IL"}])
        assert "123 Main" in result
        assert "Chicago" in result

    def test_multiple_addresses(self):
        result = _format_address_block([
            {"city": "Chicago", "state": "IL"},
            {"city": "New York", "state": "NY"},
        ])
        assert "Chicago" in result
        assert "New York" in result
