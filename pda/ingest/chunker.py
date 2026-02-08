"""Text chunking into DocumentChunks with recursive character splitter and section heading detection."""

from langchain_text_splitters import RecursiveCharacterTextSplitter

from pda.schemas.models import ChunkSource, DocumentChunk, IngestionChunk

# Defaults: ~500 chars ~= ~125 tokens; overlap for context
DEFAULT_CHUNK_SIZE = 500
DEFAULT_CHUNK_OVERLAP = 80
DEFAULT_MAX_CHARS = 1500  # max chars per chunk when splitting by paragraph


def _approx_tokens(text: str) -> int:
    """Rough token count (chars / 4)."""
    return max(1, len(text) // 4)


def _detect_section_heading(text_before_chunk: str) -> str | None:
    """
    Heuristic: last line that looks like a heading (short, no period, possibly caps).
    """
    lines = [ln.strip() for ln in text_before_chunk.splitlines() if ln.strip()]
    for line in reversed(lines[-5:]):  # last 5 non-empty lines
        if len(line) < 80 and not line.endswith(".") and len(line) > 0:
            # Skip lines that are clearly body (many lowercase)
            if line[0].isupper() or line.isupper():
                return line
    return None


def chunk_document(
    pages: list[tuple[int, str]],
    source_file: str,
    source_type: ChunkSource = ChunkSource.PDF,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[DocumentChunk]:
    """
    Split page text into DocumentChunks with stable IDs and optional section headings.

    pages: list of (page_number, text) from parse_pdf or URL-equivalent (page_number can be 0 for URL).
    source_file: filename or URL.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    chunks: list[DocumentChunk] = []
    global_offset = 0
    prefix = "pdf" if source_type == ChunkSource.PDF else "url"
    for page_num, page_text in pages:
        if not page_text.strip():
            global_offset += len(page_text) + 1
            continue
        splits = splitter.split_text(page_text)
        page_char_start = 0
        for i, piece in enumerate(splits):
            chunk_id = f"{prefix}-p{page_num}-c{i}"
            start = global_offset + page_char_start
            end = start + len(piece)
            # Section heading: text before this chunk on the same page
            text_before = page_text[: page_text.find(piece)] if piece in page_text else ""
            section_heading = _detect_section_heading(text_before)
            ch = DocumentChunk(
                chunk_id=chunk_id,
                source_type=source_type,
                source_file=source_file,
                page_number=page_num if source_type == ChunkSource.PDF else None,
                section_heading=section_heading,
                text=piece,
                char_offset_start=start,
                char_offset_end=end,
                token_count=_approx_tokens(piece),
                metadata={},
            )
            chunks.append(ch)
            page_char_start += len(piece)
        global_offset += len(page_text) + 1
    return chunks


def chunk_single_text(
    text: str,
    source_file: str,
    source_type: ChunkSource = ChunkSource.URL,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[DocumentChunk]:
    """Convenience: chunk a single blob (e.g. from URL) as one logical page."""
    return chunk_document(
        [(0, text)],
        source_file=source_file,
        source_type=source_type,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )


def chunk_url_sections(
    sections: list[tuple[str, str, str]] | list,
    source_ref: str,
    max_chars: int = DEFAULT_MAX_CHARS,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[IngestionChunk]:
    """
    Chunk URL content by sections. Prefer heading-based: each section is a chunk
    unless it exceeds max_chars, then split by paragraphs.
    sections: list of (heading_path, section_title, text) or URLSection objects.
    Returns IngestionChunk list with stable chunk_ids.
    """
    result: list[IngestionChunk] = []
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    for s_idx, sec in enumerate(sections):
        if hasattr(sec, "heading_path"):
            heading_path, section_title, text = sec.heading_path, sec.section_title, sec.text
        else:
            heading_path, section_title, text = sec[0], sec[1], sec[2]
        text = text.strip()
        if not text:
            continue  # Skip empty sections
        if len(text) <= max_chars:
            # Single chunk per section
            chunk_id = f"url-s{s_idx}-c0"
            result.append(
                IngestionChunk(
                    chunk_id=chunk_id,
                    source_type="url",
                    source_ref=source_ref,
                    page_num=None,
                    heading_path=heading_path or None,
                    section_title=section_title or None,
                    text=text,
                )
            )
        else:
            # Split by paragraphs
            splits = splitter.split_text(text)
            for c_idx, piece in enumerate(splits):
                if not piece.strip():
                    continue
                chunk_id = f"url-s{s_idx}-c{c_idx}"
                result.append(
                    IngestionChunk(
                        chunk_id=chunk_id,
                        source_type="url",
                        source_ref=source_ref,
                        page_num=None,
                        heading_path=heading_path or None,
                        section_title=section_title or None,
                        text=piece,
                    )
                )
    return result


def document_chunks_to_ingestion(
    chunks: list[DocumentChunk],
) -> list[IngestionChunk]:
    """Convert DocumentChunks (PDF) to IngestionChunk format."""
    result: list[IngestionChunk] = []
    for ch in chunks:
        if not ch.text.strip():
            continue  # Skip empty chunks
        result.append(
            IngestionChunk(
                chunk_id=ch.chunk_id,
                source_type=ch.source_type.value,
                source_ref=ch.source_file,
                page_num=ch.page_number,
                heading_path=ch.heading_path,
                section_title=ch.section_heading or None,
                text=ch.text,
            )
        )
    return result
