"""Buyer-prompt library: 50 prompts across discovery, comparison, constraints, integration, compliance, procurement."""

from typing import Any

# Categories and prompts (50 total)
BUYER_PROMPT_LIBRARY: list[dict[str, Any]] = [
    # Discovery (~10)
    {"id": "D1", "category": "discovery", "prompt": "What is this product and what category does it belong to?"},
    {"id": "D2", "category": "discovery", "prompt": "Who is this product for? Which buyer roles or personas does it target?"},
    {"id": "D3", "category": "discovery", "prompt": "What are the primary use cases or applications for this product?"},
    {"id": "D4", "category": "discovery", "prompt": "What are the main features and benefits?"},
    {"id": "D5", "category": "discovery", "prompt": "Give a short summary of what this product does and why someone would choose it."},
    {"id": "D6", "category": "discovery", "prompt": "What problem does this product solve?"},
    {"id": "D7", "category": "discovery", "prompt": "What are the key specifications or technical details?"},
    {"id": "D8", "category": "discovery", "prompt": "What makes this product different from a generic solution in this space?"},
    {"id": "D9", "category": "discovery", "prompt": "In what environments or conditions can this product be used?"},
    {"id": "D10", "category": "discovery", "prompt": "What is the product name and how would I find it in a catalog or search?"},
    # Comparison (~8)
    {"id": "C1", "category": "comparison", "prompt": "How does this compare to alternatives or competitors?"},
    {"id": "C2", "category": "comparison", "prompt": "What are the advantages of this product over similar offerings?"},
    {"id": "C3", "category": "comparison", "prompt": "What trade-offs or limitations should I consider when choosing this product?"},
    {"id": "C4", "category": "comparison", "prompt": "When would I choose this product over a competing solution?"},
    {"id": "C5", "category": "comparison", "prompt": "What unique selling points does this product have?"},
    {"id": "C6", "category": "comparison", "prompt": "How does this product differentiate itself in the market?"},
    {"id": "C7", "category": "comparison", "prompt": "What are the strengths and weaknesses of this product?"},
    {"id": "C8", "category": "comparison", "prompt": "Is this product best-in-class for any specific capability? Which one?"},
    # Constraints (~8)
    {"id": "X1", "category": "constraints", "prompt": "What are the limitations or constraints of this product?"},
    {"id": "X2", "category": "constraints", "prompt": "What requirements must be met to use this product (e.g. environment, power, space)?"},
    {"id": "X3", "category": "constraints", "prompt": "Are there any compatibility restrictions or prerequisites?"},
    {"id": "X4", "category": "constraints", "prompt": "What operating conditions or limits are specified?"},
    {"id": "X5", "category": "constraints", "prompt": "What is NOT supported or out of scope for this product?"},
    {"id": "X6", "category": "constraints", "prompt": "What are the maximum or minimum specified values for key parameters?"},
    {"id": "X7", "category": "constraints", "prompt": "Are there any known limitations or caveats I should be aware of?"},
    {"id": "X8", "category": "constraints", "prompt": "What environmental or regulatory constraints apply to deployment?"},
    # Integration (~8)
    {"id": "I1", "category": "integration", "prompt": "What integrations, interfaces, or APIs does this product support?"},
    {"id": "I2", "category": "integration", "prompt": "How does this product connect to other systems or equipment?"},
    {"id": "I3", "category": "integration", "prompt": "What connectivity options are available (e.g. protocols, ports, wireless)?"},
    {"id": "I4", "category": "integration", "prompt": "Can this product be integrated with our existing infrastructure? How?"},
    {"id": "I5", "category": "integration", "prompt": "What software or hardware interfaces does it support?"},
    {"id": "I6", "category": "integration", "prompt": "Is there an API or SDK for custom integration?"},
    {"id": "I7", "category": "integration", "prompt": "What data formats or protocols does it use for communication?"},
    {"id": "I8", "category": "integration", "prompt": "How do we get data in and out of this product?"},
    # Compliance (~8)
    {"id": "V1", "category": "compliance", "prompt": "What certifications or standards does this product meet?"},
    {"id": "V2", "category": "compliance", "prompt": "Is this product compliant with relevant industry or regulatory standards?"},
    {"id": "V3", "category": "compliance", "prompt": "What safety or quality certifications does it have?"},
    {"id": "V4", "category": "compliance", "prompt": "Does it meet environmental or sustainability requirements?"},
    {"id": "V5", "category": "compliance", "prompt": "What compliance documentation is available?"},
    {"id": "V6", "category": "compliance", "prompt": "Which regulatory frameworks does this product align with?"},
    {"id": "V7", "category": "compliance", "prompt": "Are there any export control or regional restrictions?"},
    {"id": "V8", "category": "compliance", "prompt": "What standards (ISO, IEC, etc.) does it conform to?"},
    # Procurement (~8)
    {"id": "P1", "category": "procurement", "prompt": "How much does it cost and what are the purchase options?"},
    {"id": "P2", "category": "procurement", "prompt": "What warranty or support is included?"},
    {"id": "P3", "category": "procurement", "prompt": "What are the delivery lead times or availability?"},
    {"id": "P4", "category": "procurement", "prompt": "What maintenance or calibration is required and who provides it?"},
    {"id": "P5", "category": "procurement", "prompt": "What support channels are available (e.g. documentation, support, training)?"},
    {"id": "P6", "category": "procurement", "prompt": "Are there subscription, license, or recurring cost options?"},
    {"id": "P7", "category": "procurement", "prompt": "What is the total cost of ownership or lifecycle cost?"},
    {"id": "P8", "category": "procurement", "prompt": "How do we order, configure, or get a quote for this product?"},
]


def get_prompt_set() -> list[dict[str, Any]]:
    """Return the full set of 50 buyer prompts with id and category."""
    return list(BUYER_PROMPT_LIBRARY)


def get_prompts_by_category() -> dict[str, list[dict[str, Any]]]:
    """Return prompts grouped by category."""
    by_cat: dict[str, list[dict[str, Any]]] = {}
    for p in BUYER_PROMPT_LIBRARY:
        by_cat.setdefault(p["category"], []).append(p)
    return by_cat
