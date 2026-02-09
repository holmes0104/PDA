"""Tests for content pack schemas and citation resolution."""

import pytest

from pda.schemas.content_pack_schemas import (
    Citation,
    ContentPack,
    ContentPackItem,
    Tone,
)


class TestContentPackSchemas:

    def test_citation_model(self):
        c = Citation(
            chunk_id="pdf-p1-c0",
            source_ref="test.pdf",
            page_num=1,
            section_title="Overview",
            excerpt="The product is...",
        )
        assert c.chunk_id == "pdf-p1-c0"
        assert c.page_num == 1

    def test_content_pack_item(self):
        item = ContentPackItem(
            item_id="faq-1",
            question="What is this?",
            body="It is a sensor [pdf-p1-c0].",
            citations=[
                Citation(chunk_id="pdf-p1-c0", source_ref="test.pdf"),
            ],
            tone=Tone.TECHNICAL,
        )
        assert item.question == "What is this?"
        assert len(item.citations) == 1

    def test_content_pack_model(self):
        pack = ContentPack(
            pack_type="faq",
            tone=Tone.HYBRID,
            items=[
                ContentPackItem(item_id="faq-1", body="Answer."),
            ],
        )
        assert pack.pack_type == "faq"
        assert pack.tone == Tone.HYBRID
        assert len(pack.items) == 1

    def test_tone_enum(self):
        assert Tone.TECHNICAL.value == "technical"
        assert Tone.MARKETING.value == "marketing"
        assert Tone.HYBRID.value == "hybrid"

    def test_content_pack_serialization(self):
        pack = ContentPack(
            pack_type="snippets",
            tone=Tone.TECHNICAL,
            items=[
                ContentPackItem(
                    item_id="s1",
                    question="What?",
                    body="Answer [pdf-p1-c0].",
                    citations=[Citation(chunk_id="pdf-p1-c0")],
                ),
            ],
        )
        data = pack.model_dump(mode="json")
        assert data["pack_type"] == "snippets"
        assert data["items"][0]["citations"][0]["chunk_id"] == "pdf-p1-c0"
