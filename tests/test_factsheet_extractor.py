"""Tests for Product Fact Sheet extraction: schema, evidence validation, extraction flow."""

import json
from pathlib import Path

import pytest

from pda.schemas.factsheet_schema import (
    ProductFactSheet,
    KeySpec,
    Constraint,
    Differentiator,
)
from pda.extract.factsheet_extractor import (
    extract_product_fact_sheet,
    require_evidence_for_non_not_found,
    _parse_json,
    _validate_fact_sheet,
    _build_provenance,
)


# --- Schema and validation ---


def test_factsheet_schema_roundtrip():
    sheet = ProductFactSheet(
        product_name="Widget X",
        product_category="Sensors",
        primary_use_cases=["Monitoring", "Control"],
        target_buyer_roles=["Engineer", "Procurement"],
        key_specs=[
            KeySpec(name="Weight", value="2.5", unit="kg", conditions="", evidence_chunk_ids=["pdf-p1-c0"]),
        ],
        constraints=[
            Constraint(statement="Max temp 40°C", evidence_chunk_ids=["pdf-p2-c1"]),
        ],
        differentiators=[
            Differentiator(statement="IP67 rated", evidence_chunk_ids=["pdf-p1-c2"]),
        ],
        certifications_standards=["CE", "FCC"],
        integrations_interfaces=["REST API", "Modbus"],
        maintenance_calibration=["Annual calibration"],
        source_coverage_summary="Brochure pages 1–5",
    )
    data = sheet.model_dump()
    assert data["product_name"] == "Widget X"
    assert data["key_specs"][0]["evidence_chunk_ids"] == ["pdf-p1-c0"]
    assert data["constraints"][0]["evidence_chunk_ids"] == ["pdf-p2-c1"]
    assert data["differentiators"][0]["evidence_chunk_ids"] == ["pdf-p1-c2"]
    # Rebuild from dict
    sheet2 = ProductFactSheet.model_validate(data)
    assert sheet2.product_name == sheet.product_name
    assert len(sheet2.key_specs) == 1 and sheet2.key_specs[0].evidence_chunk_ids == ["pdf-p1-c0"]


def test_require_evidence_for_non_not_found_valid():
    """Every non-NOT_FOUND item has evidence_chunk_ids."""
    sheet = ProductFactSheet(
        product_name="X",
        product_category="Y",
        key_specs=[
            KeySpec(name="A", value="1", unit="", conditions="", evidence_chunk_ids=["c1"]),
        ],
        constraints=[
            Constraint(statement="Limit.", evidence_chunk_ids=["c2"]),
        ],
        differentiators=[
            Differentiator(statement="Unique.", evidence_chunk_ids=["c3"]),
        ],
    )
    violations = require_evidence_for_non_not_found(sheet)
    assert violations == []


def test_require_evidence_for_non_not_found_key_spec_missing_evidence():
    """key_spec with name/value but empty evidence_chunk_ids should violate."""
    sheet = ProductFactSheet(
        product_name="NOT_FOUND",
        product_category="NOT_FOUND",
        key_specs=[
            KeySpec(name="Weight", value="2.5", unit="kg", conditions="", evidence_chunk_ids=[]),
        ],
        constraints=[],
        differentiators=[],
    )
    violations = require_evidence_for_non_not_found(sheet)
    assert any("key_specs" in v for v in violations)


def test_require_evidence_for_non_not_found_constraint_missing_evidence():
    """constraint with statement but empty evidence_chunk_ids should violate."""
    sheet = ProductFactSheet(
        product_name="NOT_FOUND",
        product_category="NOT_FOUND",
        key_specs=[],
        constraints=[
            Constraint(statement="Max 40°C", evidence_chunk_ids=[]),
        ],
        differentiators=[],
    )
    violations = require_evidence_for_non_not_found(sheet)
    assert any("constraints" in v for v in violations)


def test_require_evidence_for_non_not_found_differentiator_missing_evidence():
    """differentiator with statement but empty evidence_chunk_ids should violate."""
    sheet = ProductFactSheet(
        product_name="NOT_FOUND",
        product_category="NOT_FOUND",
        key_specs=[],
        constraints=[],
        differentiators=[
            Differentiator(statement="IP67", evidence_chunk_ids=[]),
        ],
    )
    violations = require_evidence_for_non_not_found(sheet)
    assert any("differentiators" in v for v in violations)


def test_require_evidence_empty_items_ok():
    """Empty key_spec (no name/value) or empty statement is not required to have evidence."""
    sheet = ProductFactSheet(
        product_name="NOT_FOUND",
        product_category="NOT_FOUND",
        key_specs=[
            KeySpec(name="", value="", unit="", conditions="", evidence_chunk_ids=[]),
        ],
        constraints=[
            Constraint(statement="", evidence_chunk_ids=[]),
        ],
        differentiators=[],
    )
    violations = require_evidence_for_non_not_found(sheet)
    assert violations == []


# --- Parse and validate ---


def test_parse_json_strips_code_fence():
    raw = '```json\n{"product_name": "X"}\n```'
    data = _parse_json(raw)
    assert data["product_name"] == "X"


def test_validate_fact_sheet_normalizes():
    data = {
        "product_name": "Test",
        "product_category": "Cat",
        "primary_use_cases": ["a", "b"],
        "target_buyer_roles": [],
        "key_specs": [
            {"name": "N", "value": "V", "unit": "U", "conditions": "C", "evidence_chunk_ids": ["id1"]},
        ],
        "constraints": [{"statement": "S", "evidence_chunk_ids": ["id2"]}],
        "differentiators": [],
        "certifications_standards": [],
        "integrations_interfaces": [],
        "maintenance_calibration": [],
        "source_coverage_summary": "Summary",
    }
    sheet = _validate_fact_sheet(data)
    assert sheet.product_name == "Test"
    assert sheet.primary_use_cases == ["a", "b"]
    assert len(sheet.key_specs) == 1 and sheet.key_specs[0].evidence_chunk_ids == ["id1"]
    assert len(sheet.constraints) == 1 and sheet.constraints[0].evidence_chunk_ids == ["id2"]


def test_build_provenance():
    sheet = ProductFactSheet(
        product_name="X",
        product_category="Y",
        key_specs=[
            KeySpec(name="A", value="1", unit="", conditions="", evidence_chunk_ids=["c1", "c2"]),
        ],
        constraints=[Constraint(statement="S", evidence_chunk_ids=["c2"])],
        differentiators=[],
    )
    prov = _build_provenance(sheet)
    assert "key_specs" in prov
    assert "c1" in prov["key_specs"] and "c2" in prov["key_specs"]
    assert "constraints" in prov and "c2" in prov["constraints"]
    assert "product_name" in prov


# --- Extraction with mock store and LLM ---


class MockStore:
    def __init__(self, chunks):
        self._chunks = {c["chunk_id"]: c for c in chunks}

    def query(self, query_text: str, n_results: int = 10, where=None):
        return list(self._chunks.values())


def test_extract_product_fact_sheet_valid_json():
    """Extraction returns valid ProductFactSheet and provenance when LLM returns valid JSON."""
    chunks = [
        {"chunk_id": "pdf-p1-c0", "text": "Product Alpha. Category: Sensors. Use cases: monitoring."},
    ]
    store = MockStore(chunks)
    valid_json = json.dumps({
        "product_name": "Product Alpha",
        "product_category": "Sensors",
        "primary_use_cases": ["monitoring"],
        "target_buyer_roles": [],
        "key_specs": [],
        "constraints": [],
        "differentiators": [],
        "certifications_standards": [],
        "integrations_interfaces": [],
        "maintenance_calibration": [],
        "source_coverage_summary": "NOT_FOUND",
    })

    class MockLLM:
        def complete(self, prompt: str) -> str:
            return valid_json

    sheet, provenance = extract_product_fact_sheet(store, MockLLM())
    assert sheet.product_name == "Product Alpha"
    assert sheet.product_category == "Sensors"
    assert "product_name" in provenance
    assert "key_specs" in provenance


def test_extract_product_fact_sheet_retry_on_invalid_json():
    """Invalid JSON is retried with fix prompt (max 2 attempts)."""
    chunks = [{"chunk_id": "pdf-p1-c0", "text": "Product Beta."}]
    store = MockStore(chunks)
    valid_json = json.dumps({
        "product_name": "Product Beta",
        "product_category": "NOT_FOUND",
        "primary_use_cases": [],
        "target_buyer_roles": [],
        "key_specs": [],
        "constraints": [],
        "differentiators": [],
        "certifications_standards": [],
        "integrations_interfaces": [],
        "maintenance_calibration": [],
        "source_coverage_summary": "NOT_FOUND",
    })
    call_count = [0]

    class MockLLM:
        def complete(self, prompt: str) -> str:
            call_count[0] += 1
            if call_count[0] == 1:
                return "not valid json at all {{{"
            return valid_json

    sheet, _ = extract_product_fact_sheet(store, MockLLM(), max_retries=2)
    assert sheet.product_name == "Product Beta"
    assert call_count[0] == 2


def test_extract_product_fact_sheet_raises_after_max_retries():
    """Raises after max retries if JSON never valid."""
    chunks = [{"chunk_id": "pdf-p1-c0", "text": "x"}]
    store = MockStore(chunks)

    class MockLLM:
        def complete(self, prompt: str) -> str:
            return "still not json {{{"

    with pytest.raises(ValueError, match="Could not produce valid"):
        extract_product_fact_sheet(store, MockLLM(), max_retries=1)
