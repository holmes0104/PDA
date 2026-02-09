"""Content-role tagger: classify each chunk as *buyer*-relevant or *operational* noise.

Buyer-relevant signals
~~~~~~~~~~~~~~~~~~~~~~
* What the product **is** (name, category, description)
* What it **measures / does** (capabilities, applications, use-cases)
* Key **performance limits** (specs with units, accuracy, range)
* **Configuration options** that affect product selection
* Differentiators, certifications, compatibility

Operational noise
~~~~~~~~~~~~~~~~~
* Installation / mounting steps
* Calibration / commissioning procedures
* Wiring diagrams / electrical hookup
* Error / fault codes and troubleshooting
* Safety warnings and regulatory boilerplate
* Multilingual duplicates of the above

The tagger is deterministic (regex / heuristic) and adapts its thresholds
based on the ``DocumentClassification`` so that a pure installation guide
still surfaces any buyer-relevant nuggets rather than blanking everything.
"""

from __future__ import annotations

import re

from pda.schemas.models import (
    ContentRole,
    DocumentChunk,
    DocumentClassification,
    DocumentType,
)

# ---------------------------------------------------------------------------
# Operational-noise patterns  (any match → lean operational)
# ---------------------------------------------------------------------------

_INSTALLATION_RE = re.compile(
    r"(?i)\b(install(ation|ing)?|mount(ing)?|attach(ing|ment)?"
    r"|fasten|tighten\s+to|torque\s+to\s+\d"
    r"|bolt|screw|bracket|DIN[\s-]rail"
    r"|connect\s+(the|to|cable|wire)|disconnect"
    r"|remove\s+the\s+(cover|cap|screw|bolt)"
    r"|assemble|disassemble)\b",
)

_CALIBRATION_RE = re.compile(
    r"(?i)\b(calibrat(e|ion|ing)|zero[\s-]?point|span\s+adjust"
    r"|commission(ing)?|factory\s+reset|adjust\s+offset"
    r"|reference\s+gas|trim|self[\s-]?diagnostic"
    r"|initializ(e|ation)|warm[\s-]?up\s+time)\b",
)

_WIRING_RE = re.compile(
    r"(?i)\b(wir(e|ing)\s+diagram|terminal\s+block|pin(out|[-\s]?assignment)"
    r"|conductor|shielded\s+cable|AWG|gauge\s+wire"
    r"|junction\s+box|ground(ing)?|earth(ing)?"
    r"|power\s+supply\s+connection|voltage\s+drop"
    r"|loop\s+resistance|cable\s+gland)\b",
)

_ERROR_CODE_RE = re.compile(
    r"(?i)\b(err(?:or)?\s*(?:code)?[\s:_-]*(?:\d+|[A-Z]{1,4}\d+))"
    r"|\bfault\s*(?:code)?[\s:_-]*\d+"
    r"|\bE\d{3,4}\b"
    r"|\balarm\s*(?:code)?[\s:_-]*\d+"
    r"|\btroubleshoot(ing)?\b"
    r"|\bdiagnostic\s+message\b",
)

_SAFETY_RE = re.compile(
    r"(?i)\b(warning\s*[:\!]|caution\s*[:\!]|danger\s*[:\!]"
    r"|do\s+not\s+(open|remove|operate|touch)"
    r"|risk\s+of\s+(electric\s+shock|explosion|injury|fire)"
    r"|protective\s+equipment|safety\s+glasses"
    r"|hard\s+hat|lockout[\s/]tagout"
    r"|intrinsic(ally)?\s+safe|ATEX|IECEx"
    r"|hazardous\s+(area|location|zone))\b",
)

_MULTILINGUAL_RE = re.compile(
    r"(?i)\b(siehe\s+seite|siehe\s+kapitel|betriebsanleitung|Inbetriebnahme"
    r"|voir\s+page|voir\s+chapitre|mise\s+en\s+service"
    r"|véase\s+página|manual\s+de\s+instrucciones"
    r"|取扱説明書|参照|설명서)\b",
)

# ---------------------------------------------------------------------------
# Buyer-relevant patterns  (any match → lean buyer)
# ---------------------------------------------------------------------------

_PRODUCT_IDENTITY_RE = re.compile(
    r"(?i)\b(product\s+name|model\s+number|order(ing)?\s+code"
    r"|part\s+number|sku|product\s+line"
    r"|overview|introduction|about\s+this\s+product)\b",
)

_CAPABILITY_RE = re.compile(
    r"(?i)\b(measur(e|es|ing|ement)|monitor(s|ing)?"
    r"|detect(s|ion)?|analyz(e|es|ing)"
    r"|capabilit(y|ies)|application(s)?"
    r"|use[\s-]?case|suitable\s+for|designed\s+for"
    r"|ideal\s+for|intended\s+for)\b",
)

_PERFORMANCE_RE = re.compile(
    r"(?i)\b(accuracy|precision|resolution|repeatability"
    r"|response\s+time|range|span|sensitivity"
    r"|drift|stability|linearity|output\s+signal"
    r"|operating\s+(range|temperature|pressure|humidity)"
    r"|measurement\s+range|detection\s+limit)\b",
)

_CONFIG_RE = re.compile(
    r"(?i)\b(configur(e|ation|able)|option(s|al)?"
    r"|select(ion|able)?|variant|model\s+option"
    r"|available\s+(in|with)|ordering\s+guide"
    r"|accessory|accessories|probe\s+type|sensor\s+type"
    r"|communication\s+protocol|interface\s+option)\b",
)

_MARKETING_RE = re.compile(
    r"(?i)\b(benefit|advantage|feature(s)?|key\s+feature"
    r"|highlights?|differentiator|unique|innovative"
    r"|leading|best[\s-]in[\s-]class|world[\s-]class"
    r"|cost[\s-]effective|roi|total\s+cost\s+of\s+ownership"
    r"|competitive|outperform|superior)\b",
)

_CERTIFICATION_RE = re.compile(
    r"(?i)\b(certif(y|ied|ication)|approv(al|ed)|comply|compliance"
    r"|standard(s)?|CE\s+mark|UL\s+list|CSA|FM\s+approv"
    r"|ISO\s+\d{4,5}|IEC\s+\d{4,5}|NIST|SIL\s+\d"
    r"|IP\d{2}|NEMA\s+\d)\b",
)


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def _count_matches(pattern: re.Pattern, text: str) -> int:
    return len(pattern.findall(text))


def _operational_score(text: str) -> float:
    """Higher value → more likely operational content (0-1 scale)."""
    n = max(len(text.split()), 1)
    raw = (
        _count_matches(_INSTALLATION_RE, text) * 3.0
        + _count_matches(_CALIBRATION_RE, text) * 3.0
        + _count_matches(_WIRING_RE, text) * 4.0
        + _count_matches(_ERROR_CODE_RE, text) * 3.5
        + _count_matches(_SAFETY_RE, text) * 2.5
        + _count_matches(_MULTILINGUAL_RE, text) * 2.0
    )
    # Normalize by word count so long chunks aren't penalized
    return min(1.0, raw / max(n * 0.15, 1.0))


def _buyer_score(text: str) -> float:
    """Higher value → more likely buyer-relevant content (0-1 scale)."""
    n = max(len(text.split()), 1)
    raw = (
        _count_matches(_PRODUCT_IDENTITY_RE, text) * 3.0
        + _count_matches(_CAPABILITY_RE, text) * 2.5
        + _count_matches(_PERFORMANCE_RE, text) * 2.5
        + _count_matches(_CONFIG_RE, text) * 2.0
        + _count_matches(_MARKETING_RE, text) * 2.0
        + _count_matches(_CERTIFICATION_RE, text) * 1.5
    )
    return min(1.0, raw / max(n * 0.15, 1.0))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def tag_chunks(
    chunks: list[DocumentChunk],
    classification: DocumentClassification | None = None,
) -> list[DocumentChunk]:
    """Tag each chunk with ``content_role`` = buyer | operational.

    The *classification* shifts the decision threshold so that:
    * In a marketing document, most content defaults to **buyer** unless
      clearly operational (e.g. a safety warning page appended at the end).
    * In an installation guide, most content defaults to **operational**
      unless it clearly conveys buyer-relevant specs or capabilities.
    * Mixed documents use balanced thresholds.

    Chunks are modified **in place** and also returned for convenience.
    """
    if not chunks:
        return chunks

    doc_type = classification.document_type if classification else DocumentType.MIXED

    # Threshold: how much the operational score must *exceed* the buyer score
    # for the chunk to be tagged operational.  Positive → bias toward buyer.
    bias: float = {
        DocumentType.PRODUCT_MARKETING: 0.15,       # strongly favour buyer
        DocumentType.MIXED: 0.0,                     # balanced
        DocumentType.TECHNICAL_MANUAL: -0.05,        # slightly favour operational
        DocumentType.INSTALLATION_CALIBRATION: -0.10, # favour operational
    }.get(doc_type, 0.0)

    for chunk in chunks:
        b = _buyer_score(chunk.text)
        o = _operational_score(chunk.text)

        # Decision: operational wins only if it exceeds buyer by more than the bias
        if o > b + bias:
            chunk.content_role = ContentRole.OPERATIONAL
        else:
            chunk.content_role = ContentRole.BUYER

    return chunks


def buyer_chunks(chunks: list[DocumentChunk]) -> list[DocumentChunk]:
    """Convenience filter: return only buyer-tagged chunks."""
    return [c for c in chunks if c.content_role == ContentRole.BUYER]


def operational_chunks(chunks: list[DocumentChunk]) -> list[DocumentChunk]:
    """Convenience filter: return only operational-tagged chunks."""
    return [c for c in chunks if c.content_role == ContentRole.OPERATIONAL]
