"""Tests for broker catalog loader."""

import tempfile
from pathlib import Path

import pytest

from erasure_executor.catalog import BrokerCatalog, BrokerEntry


VALID_CATALOG = """
brokers:
  - id: spokeo
    name: Spokeo
    category: people-search
    removal_method: web_form_with_email_verify
    difficulty: easy
    plan_file: brokers/spokeo.yaml
    recheck_days: 30
    notes: "Standard opt-out"
  - id: acxiom
    name: Acxiom
    category: marketing-data
    removal_method: web_form
    difficulty: medium
    plan_file: brokers/acxiom.yaml
    recheck_days: 90
    notes: "Marketing data broker"
"""


def _write_yaml(content: str) -> Path:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    f.write(content)
    f.close()
    return Path(f.name)


def test_load_valid_catalog():
    path = _write_yaml(VALID_CATALOG)
    catalog = BrokerCatalog.load(path)
    assert len(catalog) == 2
    assert "spokeo" in catalog
    assert "acxiom" in catalog

    spokeo = catalog.get("spokeo")
    assert isinstance(spokeo, BrokerEntry)
    assert spokeo.name == "Spokeo"
    assert spokeo.difficulty == "easy"
    assert spokeo.recheck_days == 30
    path.unlink()


def test_catalog_all_and_ids():
    path = _write_yaml(VALID_CATALOG)
    catalog = BrokerCatalog.load(path)
    assert set(catalog.ids()) == {"spokeo", "acxiom"}
    assert len(catalog.all()) == 2
    path.unlink()


def test_catalog_get_missing():
    path = _write_yaml(VALID_CATALOG)
    catalog = BrokerCatalog.load(path)
    assert catalog.get("nonexistent") is None
    path.unlink()


def test_catalog_invalid_category():
    bad = """
brokers:
  - id: test
    name: Test
    category: invalid-category
    removal_method: web_form
    difficulty: easy
    recheck_days: 30
"""
    path = _write_yaml(bad)
    with pytest.raises(ValueError, match="invalid category"):
        BrokerCatalog.load(path)
    path.unlink()


def test_catalog_invalid_difficulty():
    bad = """
brokers:
  - id: test
    name: Test
    category: people-search
    removal_method: web_form
    difficulty: impossible
    recheck_days: 30
"""
    path = _write_yaml(bad)
    with pytest.raises(ValueError, match="invalid difficulty"):
        BrokerCatalog.load(path)
    path.unlink()


def test_catalog_duplicate_id():
    bad = """
brokers:
  - id: dupe
    name: First
    category: people-search
    removal_method: web_form
    difficulty: easy
    recheck_days: 30
  - id: dupe
    name: Second
    category: people-search
    removal_method: web_form
    difficulty: easy
    recheck_days: 30
"""
    path = _write_yaml(bad)
    with pytest.raises(ValueError, match="Duplicate broker id"):
        BrokerCatalog.load(path)
    path.unlink()


def test_catalog_missing_brokers_key():
    bad = "some_other_key: true"
    path = _write_yaml(bad)
    with pytest.raises(ValueError, match="must contain a 'brokers' list"):
        BrokerCatalog.load(path)
    path.unlink()


def test_load_real_catalog():
    """Test loading the actual project catalog file."""
    catalog_path = Path(__file__).parent.parent.parent.parent / "broker-catalog" / "catalog.yaml"
    if catalog_path.exists():
        catalog = BrokerCatalog.load(catalog_path)
        assert len(catalog) >= 10
        assert "spokeo" in catalog
