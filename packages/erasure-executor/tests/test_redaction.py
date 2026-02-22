"""Tests for PII log redaction."""

import logging

from erasure_executor.logging import RedactingFilter


def test_redacts_phone_numbers():
    f = RedactingFilter()
    record = logging.LogRecord("test", logging.INFO, "", 0, "Call 312-555-1234 now", (), None)
    f.filter(record)
    assert "[PHONE-REDACTED]" in record.msg
    assert "312-555-1234" not in record.msg


def test_redacts_email():
    f = RedactingFilter()
    record = logging.LogRecord("test", logging.INFO, "", 0, "Email jane@example.com", (), None)
    f.filter(record)
    assert "[EMAIL-REDACTED]" in record.msg
    assert "jane@example.com" not in record.msg


def test_redacts_ssn():
    f = RedactingFilter()
    record = logging.LogRecord("test", logging.INFO, "", 0, "SSN: 123-45-6789", (), None)
    f.filter(record)
    assert "[SSN-REDACTED]" in record.msg
    assert "123-45-6789" not in record.msg


def test_redacts_zip():
    f = RedactingFilter()
    record = logging.LogRecord("test", logging.INFO, "", 0, "ZIP: 60601", (), None)
    f.filter(record)
    assert "[ZIP-REDACTED]" in record.msg
    assert "60601" not in record.msg


def test_redacts_custom_terms():
    f = RedactingFilter(additional_terms=["Jane Doe", "123 Main St"])
    record = logging.LogRecord("test", logging.INFO, "", 0, "Found Jane Doe at 123 Main St", (), None)
    f.filter(record)
    assert "Jane Doe" not in record.msg
    assert "123 Main St" not in record.msg
    assert "[PII-REDACTED]" in record.msg


def test_ignores_short_terms():
    f = RedactingFilter(additional_terms=["IL"])  # Too short (2 chars)
    record = logging.LogRecord("test", logging.INFO, "", 0, "State: IL", (), None)
    f.filter(record)
    assert "IL" in record.msg  # Not redacted because len <= 2


def test_set_additional_terms():
    f = RedactingFilter()
    f.set_additional_terms(["Secret Name"])
    record = logging.LogRecord("test", logging.INFO, "", 0, "User is Secret Name", (), None)
    f.filter(record)
    assert "Secret Name" not in record.msg
