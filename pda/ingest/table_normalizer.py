"""Normalize raw tables into structured TableSpec / SpecRow objects."""

from __future__ import annotations

import re
from typing import Any

from pda.schemas.ingestion_chunks import SpecRow, TableSpec

# Common unit patterns
_UNIT_RE = re.compile(
    r"\b(mm|cm|m|km|in|ft|µm|nm|"
    r"mg|g|kg|lb|oz|"
    r"mL|L|gal|"
    r"Pa|kPa|MPa|bar|psi|atm|"
    r"°C|°F|K|"
    r"V|mV|kV|A|mA|W|kW|MW|"
    r"Hz|kHz|MHz|GHz|"
    r"Ω|kΩ|MΩ|"
    r"dB|dBm|"
    r"s|ms|µs|min|h|"
    r"B|KB|MB|GB|TB|"
    r"lux|cd|lm|"
    r"rpm|RH|%)\b",
    re.IGNORECASE,
)

# Heuristic header-name patterns that hint "this is a spec table"
_SPEC_HEADER_HINTS = {"parameter", "property", "specification", "spec", "characteristic",
                      "feature", "attribute", "name", "item", "description"}
_VALUE_HEADER_HINTS = {"value", "rating", "range", "typical", "min", "max", "nominal"}


def _clean(cell: Any) -> str:
    """Coerce a cell to a stripped string."""
    if cell is None:
        return ""
    return str(cell).strip()


def normalize_table(
    raw_rows: list[list[Any]],
    caption: str | None = None,
) -> TableSpec:
    """
    Convert raw table rows (list-of-lists from pdfplumber or BeautifulSoup)
    into a structured ``TableSpec``.

    The first non-empty row is treated as the header unless it looks like data.
    """
    if not raw_rows:
        return TableSpec(caption=caption)

    # Clean all cells
    cleaned = [[_clean(c) for c in row] for row in raw_rows]

    # Drop completely empty rows
    cleaned = [row for row in cleaned if any(c for c in row)]
    if not cleaned:
        return TableSpec(caption=caption)

    # Detect header: first row that has no purely-numeric cells
    header_row = cleaned[0]
    data_rows = cleaned[1:]

    # Determine if this looks like a spec table
    header_lower = {h.lower() for h in header_row}
    is_spec = bool(header_lower & _SPEC_HEADER_HINTS) and bool(header_lower & (_VALUE_HEADER_HINTS | _SPEC_HEADER_HINTS))

    kind: str = "spec" if is_spec else "generic"

    return TableSpec(
        headers=header_row,
        rows=data_rows,
        caption=caption,
        kind=kind,  # type: ignore[arg-type]
    )


def extract_spec_rows(table: TableSpec) -> list[SpecRow]:
    """
    If the table looks like a spec table (``kind == 'spec'``), attempt to
    map columns to name / value / unit / conditions.

    Falls back to ``col-0 = name, col-1 = value`` if columns can't be mapped.
    """
    if not table.rows or not table.headers:
        return []

    headers_lower = [h.lower() for h in table.headers]

    # Try to find column indices
    name_idx = _find_col(headers_lower, {"name", "parameter", "property", "spec",
                                          "specification", "characteristic", "feature",
                                          "attribute", "item", "description"})
    value_idx = _find_col(headers_lower, {"value", "rating", "range", "typical",
                                           "nominal", "result"})
    unit_idx = _find_col(headers_lower, {"unit", "units", "uom"})
    cond_idx = _find_col(headers_lower, {"condition", "conditions", "notes", "remark",
                                          "remarks", "test condition", "comment"})

    # Fallback: first two columns
    if name_idx is None:
        name_idx = 0
    if value_idx is None:
        value_idx = 1 if len(table.headers) > 1 else 0

    rows: list[SpecRow] = []
    for data_row in table.rows:
        name = data_row[name_idx] if name_idx < len(data_row) else ""
        raw_value = data_row[value_idx] if value_idx < len(data_row) else ""
        unit = data_row[unit_idx] if unit_idx is not None and unit_idx < len(data_row) else ""
        cond = data_row[cond_idx] if cond_idx is not None and cond_idx < len(data_row) else ""

        # If no explicit unit column, try to split unit from value
        if not unit:
            raw_value, unit = _split_unit(raw_value)

        if name or raw_value:
            rows.append(SpecRow(name=name, value=raw_value, unit=unit, conditions=cond))

    return rows


def table_to_text_summary(table: TableSpec) -> str:
    """
    Produce a short textual summary of a table suitable for embedding.
    """
    parts: list[str] = []
    if table.caption:
        parts.append(f"Table: {table.caption}")
    if table.headers:
        parts.append("Columns: " + " | ".join(table.headers))
    for row in table.rows[:10]:  # cap for embedding length
        parts.append(" | ".join(row))
    if len(table.rows) > 10:
        parts.append(f"... ({len(table.rows)} rows total)")
    return "\n".join(parts)


# ── helpers ──────────────────────────────────────────────────────────────


def _find_col(headers: list[str], hints: set[str]) -> int | None:
    for i, h in enumerate(headers):
        if h in hints:
            return i
        # partial match
        for hint in hints:
            if hint in h:
                return i
    return None


def _split_unit(value: str) -> tuple[str, str]:
    """Try to split a trailing unit from a numeric value string."""
    m = _UNIT_RE.search(value)
    if m:
        unit = m.group(0)
        numeric_part = value[: m.start()].strip()
        rest = value[m.end() :].strip()
        if numeric_part:
            return numeric_part + (" " + rest if rest else ""), unit
    return value, ""
