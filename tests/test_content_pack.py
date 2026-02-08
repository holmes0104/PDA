"""Tests for content pack generator."""

import pytest
from pda.content_pack.generator import generate_content_pack
from pda.schemas.models import FactValue, ProductFactSheet


def test_generate_content_pack_empty_sheet():
    pack = generate_content_pack(ProductFactSheet())
    assert "faq_pack" in pack
    assert "page_outline" in pack
    assert "comparison_bullets" in pack
    assert "constraints" in pack
    assert "schema_org_skeleton" in pack
    assert "schema_org_json" in pack
    assert len(pack["page_outline"]) >= 5


def test_generate_content_pack_with_facts():
    sheet = ProductFactSheet(
        product_name=FactValue(value="Widget Pro", confidence="HIGH", evidence=[]),
        short_description=FactValue(value="A great widget.", confidence="HIGH", evidence=[]),
        key_features=[FactValue(value="Fast", confidence="HIGH", evidence=[])],
    )
    pack = generate_content_pack(sheet)
    assert any("Widget" in str(faq.get("q", "") + str(faq.get("a", ""))) for faq in pack["faq_pack"])
    assert pack["schema_org_skeleton"].get("name") == "Widget Pro"
