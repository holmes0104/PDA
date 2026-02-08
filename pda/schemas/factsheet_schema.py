"""Strict JSON schema for Product Fact Sheet extraction (retrieval-based)."""

from pydantic import BaseModel, Field


class KeySpec(BaseModel):
    """One key specification with optional unit, conditions, and evidence."""

    name: str = ""
    value: str = ""
    unit: str = ""
    conditions: str = ""
    evidence_chunk_ids: list[str] = Field(default_factory=list)


class Constraint(BaseModel):
    """A constraint or limitation with evidence."""

    statement: str = ""
    evidence_chunk_ids: list[str] = Field(default_factory=list)


class Differentiator(BaseModel):
    """A differentiator or unique selling point with evidence."""

    statement: str = ""
    evidence_chunk_ids: list[str] = Field(default_factory=list)


class ProductFactSheet(BaseModel):
    """
    Strict product fact sheet with required fields.
    Use "NOT_FOUND" and empty evidence for unsupported fields.
    """

    product_name: str = "NOT_FOUND"
    product_category: str = "NOT_FOUND"
    primary_use_cases: list[str] = Field(default_factory=list)
    target_buyer_roles: list[str] = Field(default_factory=list)
    key_specs: list[KeySpec] = Field(default_factory=list)
    constraints: list[Constraint] = Field(default_factory=list)
    differentiators: list[Differentiator] = Field(default_factory=list)
    certifications_standards: list[str] = Field(default_factory=list)
    integrations_interfaces: list[str] = Field(default_factory=list)
    maintenance_calibration: list[str] = Field(default_factory=list)
    source_coverage_summary: str = "NOT_FOUND"
