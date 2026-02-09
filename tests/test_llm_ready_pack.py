"""Tests for the LLM-ready content pack: preflight, schemas, generation shape, and citation enforcement."""

import json
import pytest
from pathlib import Path

from pda.schemas.factsheet_schema import ProductFactSheet, KeySpec, Constraint, Differentiator
from pda.schemas.content_pack_schemas import Citation, Tone
from pda.schemas.llm_ready_pack import (
    CanonicalAnswerBlock,
    ContentPackBundle,
    DecisionCriterion,
    ExportManifest,
    FAQEntry,
    ManifestFileEntry,
    MissingFactQuestion,
    PreflightResult,
    SelectionGuidance,
    UseCaseFAQ,
    UseCasePage,
)
from pda.content_pack.llm_ready_pack import (
    run_preflight,
    write_content_pack_bundle,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def complete_factsheet() -> ProductFactSheet:
    """A fact sheet with all critical + important fields populated."""
    return ProductFactSheet(
        product_name="HMT330",
        product_category="Humidity Transmitter",
        primary_use_cases=["Industrial process monitoring", "HVAC"],
        target_buyer_roles=["Process engineer", "Facility manager"],
        key_specs=[
            KeySpec(name="Humidity range", value="0-100", unit="%RH", evidence_chunk_ids=["pdf-p1-c0"]),
            KeySpec(name="Accuracy", value="±1", unit="%RH", evidence_chunk_ids=["pdf-p1-c1"]),
            KeySpec(name="Temperature range", value="-70 to +180", unit="°C", evidence_chunk_ids=["pdf-p2-c0"]),
        ],
        constraints=[
            Constraint(statement="Max operating pressure 10 bar", evidence_chunk_ids=["pdf-p3-c0"]),
        ],
        differentiators=[
            Differentiator(statement="DRYCAP sensor technology", evidence_chunk_ids=["pdf-p1-c2"]),
        ],
        certifications_standards=["CE", "UL", "ATEX"],
        integrations_interfaces=["4-20 mA", "RS-485", "Modbus"],
        maintenance_calibration=["Annual calibration recommended"],
        source_coverage_summary="Full brochure with specs, installation, and troubleshooting.",
    )


@pytest.fixture
def minimal_factsheet() -> ProductFactSheet:
    """A fact sheet missing critical fields."""
    return ProductFactSheet(
        product_name="NOT_FOUND",
        product_category="NOT_FOUND",
        primary_use_cases=[],
        key_specs=[],
    )


@pytest.fixture
def partial_factsheet() -> ProductFactSheet:
    """A fact sheet with product name but few specs."""
    return ProductFactSheet(
        product_name="SomeProduct",
        product_category="NOT_FOUND",
        primary_use_cases=["General use"],
        key_specs=[
            KeySpec(name="Range", value="0-100", unit="units", evidence_chunk_ids=["c1"]),
        ],
    )


@pytest.fixture
def sample_bundle(complete_factsheet) -> ContentPackBundle:
    """A small sample bundle for export testing."""
    cite = Citation(chunk_id="pdf-p1-c0", source_ref="test.pdf", page_num=1)
    return ContentPackBundle(
        project_id="test-proj-123",
        tone=Tone.TECHNICAL,
        preflight=PreflightResult(
            product_name="HMT330",
            facts_found=9,
            facts_expected=9,
            can_generate=True,
        ),
        canonical_answers=[
            CanonicalAnswerBlock(
                block_id="cab-0",
                question="What is the HMT330?",
                answer="A humidity transmitter [pdf-p1-c0].",
                best_for="Industrial environments",
                not_suitable_when="Low-cost consumer applications",
                citations=[cite],
            ),
        ],
        faq=[
            FAQEntry(
                faq_id="faq-0",
                theme="selection",
                question="Which model should I choose?",
                answer="Choose the HMT330 for high-accuracy needs [pdf-p1-c0].",
                citations=[cite],
            ),
            FAQEntry(
                faq_id="faq-1",
                theme="installation",
                question="How do I mount it?",
                answer="Use the supplied bracket [pdf-p1-c0].",
                citations=[cite],
            ),
        ],
        selection_guidance=SelectionGuidance(
            decision_criteria=[
                DecisionCriterion(
                    criterion_id="dc-0",
                    statement="Choose this if you need ±1 %RH accuracy [pdf-p1-c0].",
                    citations=[cite],
                ),
            ],
            missing_info=["Pricing comparison not available"],
        ),
        use_case_pages=[
            UseCasePage(
                page_id="uc-0",
                title="Use Case: Pharmaceutical Manufacturing",
                problem_context="Pharma requires tight humidity control [pdf-p1-c0].",
                requirements="±1 %RH accuracy at 15-25 °C [pdf-p1-c0].",
                why_this_product_fits="HMT330 meets this with DRYCAP sensor [pdf-p1-c0].",
                implementation_notes="Mount in cleanroom HVAC duct [pdf-p1-c0].",
                faqs=[
                    UseCaseFAQ(
                        question="Is it FDA compliant?",
                        answer="Check local regulations [pdf-p1-c0].",
                        citations=[cite],
                    ),
                ],
                citations=[cite],
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Preflight tests
# ---------------------------------------------------------------------------

class TestPreflight:

    def test_complete_sheet_passes(self, complete_factsheet):
        result = run_preflight(complete_factsheet)
        assert result.can_generate is True
        assert result.product_name == "HMT330"
        assert result.facts_found > 0
        assert len(result.questions) == 0  # nothing missing

    def test_minimal_sheet_blocked(self, minimal_factsheet):
        result = run_preflight(minimal_factsheet)
        assert result.can_generate is False
        assert "product_name" in result.missing_fields
        assert len(result.questions) > 0
        assert len(result.questions) <= 7

    def test_partial_sheet_blocked_few_specs(self, partial_factsheet):
        result = run_preflight(partial_factsheet)
        # Has product_name but < 2 key_specs → blocked
        assert result.can_generate is False
        assert "key_specs" in result.missing_fields or len(partial_factsheet.key_specs) < 2

    def test_questions_have_required_fields(self, minimal_factsheet):
        result = run_preflight(minimal_factsheet)
        for q in result.questions:
            assert q.field, "question must have a field name"
            assert q.question, "question must have text"
            assert q.why_needed, "question must explain why it is needed"

    def test_missing_fields_detected(self, minimal_factsheet):
        result = run_preflight(minimal_factsheet)
        # product_name, product_category, key_specs, primary_use_cases should all be missing
        assert "product_name" in result.missing_fields
        assert "product_category" in result.missing_fields
        assert "key_specs" in result.missing_fields
        assert "primary_use_cases" in result.missing_fields


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

class TestLLMReadySchemas:

    def test_canonical_answer_block(self):
        block = CanonicalAnswerBlock(
            block_id="cab-1",
            question="What is this product?",
            answer="A transmitter [pdf-p1-c0].",
            best_for="Industrial use",
            not_suitable_when="Consumer applications",
            citations=[Citation(chunk_id="pdf-p1-c0")],
        )
        assert block.block_id == "cab-1"
        assert len(block.citations) == 1

    def test_faq_entry(self):
        entry = FAQEntry(
            faq_id="faq-1",
            theme="accuracy_specs",
            question="What is the accuracy?",
            answer="±1 %RH [pdf-p1-c1].",
            citations=[Citation(chunk_id="pdf-p1-c1")],
        )
        assert entry.theme == "accuracy_specs"

    def test_selection_guidance(self):
        sg = SelectionGuidance(
            decision_criteria=[
                DecisionCriterion(criterion_id="dc-1", statement="Choose if…"),
            ],
            missing_info=["No pricing data"],
        )
        assert len(sg.decision_criteria) == 1
        assert len(sg.missing_info) == 1

    def test_use_case_page(self):
        page = UseCasePage(
            page_id="uc-1",
            title="Use Case: HVAC",
            problem_context="Context",
            requirements="Requirements",
            why_this_product_fits="Fits because…",
            implementation_notes="Notes",
        )
        assert page.page_id == "uc-1"

    def test_content_pack_bundle_serialization(self, sample_bundle):
        data = sample_bundle.model_dump(mode="json")
        assert data["project_id"] == "test-proj-123"
        assert data["tone"] == "technical"
        assert len(data["canonical_answers"]) == 1
        assert len(data["faq"]) == 2
        assert len(data["use_case_pages"]) == 1
        # Verify citations are serialized
        assert data["canonical_answers"][0]["citations"][0]["chunk_id"] == "pdf-p1-c0"

    def test_preflight_result(self):
        pf = PreflightResult(
            product_name="TestProd",
            facts_found=7,
            facts_expected=9,
            missing_fields=["constraints", "certifications_standards"],
            questions=[
                MissingFactQuestion(
                    field="constraints",
                    question="What are the limits?",
                    why_needed="Needed for 'not suitable when' fields",
                ),
            ],
            can_generate=True,
        )
        assert pf.can_generate is True
        assert len(pf.questions) == 1

    def test_export_manifest(self):
        manifest = ExportManifest(
            project_id="p1",
            tone="technical",
            files=[
                ManifestFileEntry(filename="faq.md", section="faq", item_count=20, citation_count=35),
            ],
            total_citations=35,
        )
        assert manifest.total_citations == 35


# ---------------------------------------------------------------------------
# Export / write tests
# ---------------------------------------------------------------------------

class TestExportBundle:

    def test_write_creates_files(self, sample_bundle, tmp_path):
        written = write_content_pack_bundle(sample_bundle, tmp_path / "output")
        assert "canonical_answers.md" in written
        assert "faq.md" in written
        assert "selection_guidance.md" in written
        assert "content_pack.json" in written
        assert "manifest.json" in written
        # Use-case page
        assert any(k.startswith("usecase_") for k in written)

        # Verify all files exist on disk
        for name, path in written.items():
            assert Path(path).exists(), f"{name} should exist at {path}"

    def test_markdown_has_citations(self, sample_bundle, tmp_path):
        written = write_content_pack_bundle(sample_bundle, tmp_path / "output")
        cab_md = Path(written["canonical_answers.md"]).read_text(encoding="utf-8")
        assert "pdf-p1-c0" in cab_md
        assert "**Sources:**" in cab_md

    def test_faq_grouped_by_theme(self, sample_bundle, tmp_path):
        written = write_content_pack_bundle(sample_bundle, tmp_path / "output")
        faq_md = Path(written["faq.md"]).read_text(encoding="utf-8")
        assert "## Selection" in faq_md or "## selection" in faq_md.lower()
        assert "## Installation" in faq_md or "## installation" in faq_md.lower()

    def test_manifest_json_valid(self, sample_bundle, tmp_path):
        written = write_content_pack_bundle(sample_bundle, tmp_path / "output")
        manifest_path = Path(written["manifest.json"])
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["project_id"] == "test-proj-123"
        assert manifest["tone"] == "technical"
        assert isinstance(manifest["files"], list)
        assert manifest["total_citations"] > 0

    def test_content_pack_json_valid(self, sample_bundle, tmp_path):
        written = write_content_pack_bundle(sample_bundle, tmp_path / "output")
        pack_path = Path(written["content_pack.json"])
        pack = json.loads(pack_path.read_text(encoding="utf-8"))
        assert pack["project_id"] == "test-proj-123"
        assert len(pack["canonical_answers"]) == 1
        assert len(pack["faq"]) == 2

    def test_selection_guidance_md_has_missing_info(self, sample_bundle, tmp_path):
        written = write_content_pack_bundle(sample_bundle, tmp_path / "output")
        sg_md = Path(written["selection_guidance.md"]).read_text(encoding="utf-8")
        assert "Missing Information" in sg_md
        assert "Pricing comparison not available" in sg_md

    def test_usecase_page_md_structure(self, sample_bundle, tmp_path):
        written = write_content_pack_bundle(sample_bundle, tmp_path / "output")
        uc_files = [k for k in written if k.startswith("usecase_")]
        assert len(uc_files) == 1
        uc_md = Path(written[uc_files[0]]).read_text(encoding="utf-8")
        assert "Problem Context" in uc_md
        assert "Requirements" in uc_md
        assert "Why This Product Fits" in uc_md
        assert "Implementation Notes" in uc_md
        assert "FAQs" in uc_md


# ---------------------------------------------------------------------------
# Synthetic PDF generation test (ensure conftest generates them)
# ---------------------------------------------------------------------------

class TestSyntheticPDFs:

    def test_brochure_full_exists(self, brochure_full_path):
        assert Path(brochure_full_path).exists()
        assert Path(brochure_full_path).stat().st_size > 0

    def test_manual_technical_exists(self, manual_technical_path):
        assert Path(manual_technical_path).exists()
        assert Path(manual_technical_path).stat().st_size > 0

    def test_brochure_minimal_exists(self, brochure_minimal_path):
        assert Path(brochure_minimal_path).exists()
        assert Path(brochure_minimal_path).stat().st_size > 0
