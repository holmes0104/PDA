"""Stage 3 — fact extraction from chunks to ProductFactSheet."""

from pda.extract.fact_extractor import extract_fact_sheet
from pda.extract.factsheet_extractor import extract_product_fact_sheet, require_evidence_for_non_not_found

__all__ = ["extract_fact_sheet", "extract_product_fact_sheet", "require_evidence_for_non_not_found"]
