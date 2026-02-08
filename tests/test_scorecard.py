"""Tests for scorecard deterministic checks and build_scorecard."""

import pytest
from pda.audit.scorecard import (
    build_scorecard,
    check_completeness,
    check_consistency,
    check_freshness,
    check_schema_readiness,
    check_spec_precision,
    check_structural_clarity,
)
from pda.schemas.models import ChunkSource, DocumentChunk, FactValue, ProductFactSheet


def test_check_completeness_empty():
    sheet = ProductFactSheet()
    assert check_completeness(sheet) == 0


def test_check_completeness_full():
    sheet = ProductFactSheet(
        product_name=FactValue(value="X", confidence="HIGH", evidence=[]),
        manufacturer=FactValue(value="Y", confidence="HIGH", evidence=[]),
        model_number=FactValue(value="Z", confidence="HIGH", evidence=[]),
        category=FactValue(value="Cat", confidence="HIGH", evidence=[]),
        short_description=FactValue(value="Desc", confidence="HIGH", evidence=[]),
        key_features=[FactValue(value="F1", confidence="HIGH", evidence=[])],
        specifications={"Weight": FactValue(value="2 kg", confidence="HIGH", evidence=[])},
        use_cases=[FactValue(value="U1", confidence="HIGH", evidence=[])],
        target_audience=FactValue(value="B2B", confidence="HIGH", evidence=[]),
        pricing=FactValue(value="99", confidence="HIGH", evidence=[]),
        certifications=[FactValue(value="CE", confidence="HIGH", evidence=[])],
        compatibility=[FactValue(value="Win", confidence="HIGH", evidence=[])],
        warranty=FactValue(value="1y", confidence="HIGH", evidence=[]),
        support_info=FactValue(value="Email", confidence="HIGH", evidence=[]),
    )
    assert check_completeness(sheet) == 10


def test_check_structural_clarity_empty():
    assert check_structural_clarity([]) == 0


def test_check_structural_clarity_with_headings():
    chunks = [
        DocumentChunk(
            chunk_id="pdf-p1-c0",
            source_type=ChunkSource.PDF,
            source_file="x.pdf",
            page_number=1,
            section_heading="Features",
            text="Some text.",
            token_count=400,
        ),
    ]
    score = check_structural_clarity(chunks)
    assert 0 <= score <= 10


def test_check_spec_precision_empty_specs():
    sheet = ProductFactSheet()
    assert check_spec_precision(sheet) == 5


def test_check_spec_precision_with_units():
    sheet = ProductFactSheet(
        specifications={
            "Weight": FactValue(value="2.5 kg", confidence="HIGH", evidence=[]),
            "Size": FactValue(value="10 x 20 cm", confidence="HIGH", evidence=[]),
        }
    )
    assert check_spec_precision(sheet) >= 5


def test_check_schema_readiness_no_url():
    assert check_schema_readiness(None) == 5


def test_check_consistency():
    sheet = ProductFactSheet(
        specifications={
            "A": FactValue(value="1", confidence="HIGH", evidence=[]),
            "B": FactValue(value="2", confidence="HIGH", evidence=[]),
        }
    )
    chunks = [DocumentChunk(chunk_id="c1", source_type=ChunkSource.PDF, source_file="x.pdf", text="x", token_count=10)]
    assert check_consistency(sheet, chunks) in (7, 10)


def test_check_freshness_empty():
    assert check_freshness([]) == 0


def test_check_freshness_with_date():
    chunks = [
        DocumentChunk(chunk_id="c1", source_type=ChunkSource.PDF, source_file="x.pdf", text="Updated 2024. Version 2.0.", token_count=20),
    ]
    assert check_freshness(chunks) >= 3


def test_build_scorecard_returns_scorecard():
    sheet = ProductFactSheet(product_name=FactValue(value="Test", confidence="HIGH", evidence=[]))
    chunks = [
        DocumentChunk(chunk_id="c1", source_type=ChunkSource.PDF, source_file="x.pdf", page_number=1, text="Content.", token_count=50),
    ]
    card = build_scorecard(sheet, chunks)
    assert card.overall_score >= 0
    assert card.grade in ("A", "B", "C", "D", "F")
    assert len(card.dimensions) >= 1
