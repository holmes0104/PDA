"""Tests for deterministic audit checks."""

import pytest

from pda.audit.deterministic_checks import (
    CheckResult,
    check_acronym_list,
    check_model_naming_consistency,
    check_required_sections,
    check_unit_consistency,
    run_deterministic_checks,
)
from pda.schemas.models import ChunkSource, DocumentChunk, FactValue, ProductFactSheet


def _make_chunk(text: str, heading: str = "", chunk_id: str = "c0") -> DocumentChunk:
    return DocumentChunk(
        chunk_id=chunk_id,
        source_type=ChunkSource.PDF,
        source_file="test.pdf",
        page_number=1,
        section_heading=heading,
        text=text,
        token_count=len(text) // 4,
    )


class TestRequiredSections:

    def test_all_sections_present(self):
        chunks = [
            _make_chunk("Product overview and description.", heading="Overview", chunk_id="c0"),
            _make_chunk("Installation steps: mount the bracket.", heading="Installation", chunk_id="c1"),
            _make_chunk("Troubleshooting: if error E01 appears.", heading="Troubleshooting", chunk_id="c2"),
            _make_chunk("Technical data: specifications table.", heading="Technical Data", chunk_id="c3"),
        ]
        result = check_required_sections(chunks)
        assert result.score >= 8
        assert "4/4" in result.details

    def test_missing_sections(self):
        chunks = [_make_chunk("Product overview only.", heading="Overview", chunk_id="c0")]
        result = check_required_sections(chunks)
        assert result.score < 10
        assert len(result.recommendations) >= 1

    def test_no_chunks(self):
        result = check_required_sections([])
        assert result.score == 0


class TestAcronymList:

    def test_acronym_section_present(self):
        chunks = [
            _make_chunk("RH = Relative Humidity. MTBF = Mean Time...", heading="Acronyms", chunk_id="c0"),
        ]
        result = check_acronym_list(chunks)
        assert result.score == 10

    def test_glossary_section(self):
        chunks = [_make_chunk("Terms defined here.", heading="Glossary", chunk_id="c0")]
        result = check_acronym_list(chunks)
        assert result.score == 10

    def test_no_acronym_section(self):
        chunks = [_make_chunk("Just product text.", heading="Features", chunk_id="c0")]
        result = check_acronym_list(chunks)
        assert result.score == 0
        assert len(result.recommendations) >= 1


class TestModelNaming:

    def test_consistent_naming(self):
        chunks = [
            _make_chunk("The HMT330 transmitter is designed for...", chunk_id="c0"),
            _make_chunk("The HMT330 provides high accuracy...", chunk_id="c1"),
        ]
        result = check_model_naming_consistency(chunks)
        assert result.score >= 7

    def test_no_model_found(self):
        chunks = [_make_chunk("This product is great.", chunk_id="c0")]
        result = check_model_naming_consistency(chunks)
        assert result.score == 5  # neutral


class TestUnitConsistency:

    def test_consistent_units(self):
        chunks = [_make_chunk("Temperature: 25 °C. Weight: 350 g.", chunk_id="c0")]
        result = check_unit_consistency(chunks)
        assert result.score >= 5

    def test_mixed_temperature_units(self):
        chunks = [_make_chunk("Range: -40 to +80 °C. Also rated at 176 °F.", chunk_id="c0")]
        result = check_unit_consistency(chunks)
        assert result.score < 10

    def test_bare_number_specs(self):
        sheet = ProductFactSheet(
            specifications={
                "Weight": FactValue(value="350", confidence="HIGH", evidence=[]),
            }
        )
        chunks = [_make_chunk("Weight: 350.", chunk_id="c0")]
        result = check_unit_consistency(chunks, fact_sheet=sheet)
        assert result.score < 10


class TestRunAll:

    def test_run_all_returns_list(self):
        chunks = [_make_chunk("Overview of the product.", heading="Overview", chunk_id="c0")]
        results = run_deterministic_checks(chunks)
        assert len(results) == 4
        for r in results:
            assert isinstance(r, CheckResult)
            assert 0 <= r.score <= 10
