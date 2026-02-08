"""Generate LLM-friendly content pack: FAQ, outline, comparison bullets, constraints, schema.org JSON-LD."""

import json
from typing import Any

from pda.schemas.models import ProductFactSheet

NOT_FOUND = "NOT_FOUND"


def _val(fv: Any) -> Any:
    if fv is None:
        return None
    v = getattr(fv, "value", fv)
    if v is None or (isinstance(v, str) and v.strip().upper() == NOT_FOUND):
        return None
    return v


def generate_content_pack(fact_sheet: ProductFactSheet) -> dict[str, Any]:
    """
    Return a dict with: faq_pack, page_outline, comparison_bullets, constraints, schema_org_skeleton.
    """
    faq_pack: list[dict[str, str]] = []
    name = _val(fact_sheet.product_name)
    if name:
        faq_pack.append({"q": "What is this product?", "a": str(name)})
    desc = _val(fact_sheet.short_description)
    if desc:
        faq_pack.append({"q": "What does it do?", "a": str(desc)[:500]})
    audience = _val(fact_sheet.target_audience)
    if audience:
        faq_pack.append({"q": "Who is it for?", "a": str(audience)})
    price = _val(fact_sheet.pricing)
    if price:
        faq_pack.append({"q": "What does it cost?", "a": str(price)})
    warranty = _val(fact_sheet.warranty)
    if warranty:
        faq_pack.append({"q": "What warranty is included?", "a": str(warranty)})
    support = _val(fact_sheet.support_info)
    if support:
        faq_pack.append({"q": "How do I get support?", "a": str(support)})
    for fv in fact_sheet.key_features or []:
        v = _val(fv)
        if v:
            faq_pack.append({"q": "What are the key features?", "a": str(v)[:300]})
            break

    page_outline = [
        "Product name and tagline",
        "Short description",
        "Key features",
        "Specifications",
        "Use cases / applications",
        "Target audience",
        "Pricing and offers",
        "Certifications and compliance",
        "Compatibility",
        "Warranty and support",
    ]

    comparison_bullets: list[str] = []
    if name:
        comparison_bullets.append(f"Product: {name}")
    if fact_sheet.key_features:
        for fv in fact_sheet.key_features[:5]:
            v = _val(fv)
            if v:
                comparison_bullets.append(f"• {v}" if not str(v).startswith("•") else str(v))
    if fact_sheet.specifications:
        for k, fv in list(fact_sheet.specifications.items())[:5]:
            v = _val(fv)
            if v:
                comparison_bullets.append(f"{k}: {v}")

    constraints: list[str] = []
    for fv in fact_sheet.compatibility or []:
        v = _val(fv)
        if v:
            constraints.append(str(v))
    if fact_sheet.certifications:
        for fv in fact_sheet.certifications:
            v = _val(fv)
            if v:
                constraints.append(f"Certification: {v}")

    schema_org_skeleton = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": _val(fact_sheet.product_name) or "",
        "description": _val(fact_sheet.short_description) or "",
        "brand": {"@type": "Brand", "name": _val(fact_sheet.manufacturer) or ""},
        "sku": _val(fact_sheet.model_number) or "",
        "category": _val(fact_sheet.category) or "",
        "offers": {"@type": "Offer", "price": _val(fact_sheet.pricing) or ""},
    }

    return {
        "faq_pack": faq_pack,
        "page_outline": page_outline,
        "comparison_bullets": comparison_bullets,
        "constraints": constraints,
        "schema_org_skeleton": schema_org_skeleton,
        "schema_org_json": json.dumps(schema_org_skeleton, indent=2),
    }
