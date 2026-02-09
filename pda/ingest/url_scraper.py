"""URL scraping for product pages: fetch and extract main content with trafilatura."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import httpx
import trafilatura


def scrape_url(url: str, timeout: float = 15.0) -> str:
    """
    Fetch URL and return extracted main text (boilerplate removed).
    Raises on fetch or parse errors.
    """
    with httpx.Client(follow_redirects=True, timeout=timeout) as client:
        response = client.get(url)
        response.raise_for_status()
        html = response.text
    text = trafilatura.extract(html) or ""
    return text


@dataclass
class URLSection:
    """A section of URL content with heading path and text."""

    heading_path: str  # e.g. "Introduction / Features"
    section_title: str  # leaf heading
    text: str


@dataclass
class URLTable:
    """A table extracted from a URL page."""

    heading_path: str  # nearest heading context
    rows: list[list[str]] = field(default_factory=list)
    caption: str | None = None


def scrape_url_structured(url: str, timeout: float = 15.0) -> tuple[str, list[URLSection]]:
    """
    Fetch URL and extract main content with heading structure.
    Uses trafilatura with markdown output to preserve headings (nav/footer/scripts removed).
    Returns (raw_html, list of sections).
    """
    with httpx.Client(follow_redirects=True, timeout=timeout) as client:
        response = client.get(url)
        response.raise_for_status()
        html = response.text

    # Extract as markdown to preserve heading structure; trafilatura removes nav/footer/scripts
    markdown = trafilatura.extract(html, output_format="markdown") or ""

    sections = _parse_markdown_sections(markdown)
    return html, sections


def scrape_url_with_tables(
    url: str, timeout: float = 15.0,
) -> tuple[str, list[URLSection], list[URLTable]]:
    """
    Like ``scrape_url_structured`` but also extracts ``<table>`` elements
    from the raw HTML using BeautifulSoup.

    Returns (raw_html, sections, tables).
    """
    with httpx.Client(follow_redirects=True, timeout=timeout) as client:
        response = client.get(url)
        response.raise_for_status()
        html = response.text

    markdown = trafilatura.extract(html, output_format="markdown") or ""
    sections = _parse_markdown_sections(markdown)

    tables = _extract_html_tables(html)
    return html, sections, tables


def _extract_html_tables(html: str) -> list[URLTable]:
    """Parse ``<table>`` elements from raw HTML using BeautifulSoup."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return []  # bs4 optional; degrade gracefully

    soup = BeautifulSoup(html, "html.parser")
    results: list[URLTable] = []
    for table_el in soup.find_all("table"):
        # Nearest heading context
        heading_path = ""
        prev = table_el.find_previous(re.compile(r"^h[1-6]$"))
        if prev:
            heading_path = prev.get_text(strip=True)

        # Caption
        caption_el = table_el.find("caption")
        caption = caption_el.get_text(strip=True) if caption_el else None

        rows: list[list[str]] = []
        for tr in table_el.find_all("tr"):
            cells = tr.find_all(["th", "td"])
            rows.append([c.get_text(strip=True) for c in cells])

        if rows:
            results.append(URLTable(heading_path=heading_path, rows=rows, caption=caption))
    return results


def _parse_markdown_sections(markdown: str) -> list[URLSection]:
    """
    Parse markdown into sections by headings (# ## ### etc.).
    Returns list of (heading_path, section_title, text).
    """
    sections: list[URLSection] = []
    heading_stack: list[tuple[int, str]] = []  # (level, title)
    current_text: list[str] = []

    # Match markdown headings: # Title or ## Title
    heading_re = re.compile(r"^(#{1,6})\s+(.+)$")

    def flush_section():
        nonlocal current_text, heading_stack
        text = "\n\n".join(current_text).strip()
        if text:  # Only create section if we have content
            path = " / ".join(t for _, t in heading_stack) if heading_stack else ""
            title = heading_stack[-1][1] if heading_stack else ""
            sections.append(URLSection(heading_path=path, section_title=title, text=text))
        current_text = []

    for line in markdown.splitlines():
        m = heading_re.match(line.strip())
        if m:
            flush_section()
            level = len(m.group(1))
            title = m.group(2).strip()
            # Pop headings at same or deeper level
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, title))
            current_text = []
        else:
            if line.strip():
                current_text.append(line.rstrip())

    flush_section()  # Flush last section after loop

    # If no headings found, treat entire content as one section
    if not sections and markdown.strip():
        full_text = "\n\n".join(
            ln.rstrip() for ln in markdown.splitlines() if ln.strip()
        ).strip()
        if full_text:
            sections.append(
                URLSection(heading_path="", section_title="", text=full_text)
            )

    return sections
