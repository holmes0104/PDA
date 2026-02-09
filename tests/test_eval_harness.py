"""Tests for the eval harness: YAML loading, result writing, dashboard generation."""

import tempfile
from pathlib import Path

import pytest
import yaml

from pda.eval.harness import (
    EvalPrompt,
    EvalResult,
    _deterministic_citation_coverage,
    _write_csv,
    _write_dashboard,
    _write_json,
    load_prompts,
)


class TestLoadPrompts:

    def test_load_prompts_from_yaml(self, tmp_path):
        data = {
            "prompts": [
                {"id": "p1", "category": "specs", "prompt": "What are the specs?"},
                {"id": "p2", "category": "overview", "prompt": "What is the product?"},
            ]
        }
        yaml_path = tmp_path / "prompts.yaml"
        yaml_path.write_text(yaml.dump(data), encoding="utf-8")

        prompts = load_prompts(yaml_path)
        assert len(prompts) == 2
        assert prompts[0].id == "p1"
        assert prompts[0].category == "specs"
        assert prompts[1].prompt == "What is the product?"

    def test_load_prompts_flat_list(self, tmp_path):
        data = [
            {"id": "q1", "prompt": "Question one?"},
            {"id": "q2", "prompt": "Question two?", "must_cover": ["point A"]},
        ]
        yaml_path = tmp_path / "prompts.yaml"
        yaml_path.write_text(yaml.dump(data), encoding="utf-8")

        prompts = load_prompts(yaml_path)
        assert len(prompts) == 2
        assert prompts[1].must_cover == ["point A"]

    def test_load_prompts_missing_file(self):
        with pytest.raises(FileNotFoundError):
            load_prompts("/nonexistent/path.yaml")


class TestCitationCoverage:

    def test_all_sentences_cited(self):
        answer = "The weight is 2.5 kg [pdf-p1-c0]. The range is wide [pdf-p1-c1]"
        score = _deterministic_citation_coverage(answer, ["pdf-p1-c0", "pdf-p1-c1"])
        assert score == 1.0  # both sentences have citations

    def test_no_citations(self):
        answer = "The product weighs 2.5 kg. The range is wide."
        score = _deterministic_citation_coverage(answer, ["pdf-p1-c0"])
        assert score == 0.0

    def test_partial_citations(self):
        answer = "Weight is 2.5 kg [pdf-p1-c0]. Range is wide."
        score = _deterministic_citation_coverage(answer, ["pdf-p1-c0"])
        assert 0.0 < score < 1.0

    def test_empty_answer(self):
        assert _deterministic_citation_coverage("", []) == 0.0


class TestOutputWriters:

    def _make_results(self) -> list[EvalResult]:
        r1 = EvalResult()
        r1.prompt_id = "p1"
        r1.category = "specs"
        r1.prompt_text = "What are the specs?"
        r1.answer = "Weight: 2.5 kg [pdf-p1-c0]"
        r1.cited_chunk_ids = ["pdf-p1-c0"]
        r1.completeness = 8
        r1.correctness = 9
        r1.citation_coverage = 7
        r1.rationale = "Good answer."

        r2 = EvalResult()
        r2.prompt_id = "p2"
        r2.category = "overview"
        r2.prompt_text = "What is the product?"
        r2.answer = "It is a sensor."
        r2.cited_chunk_ids = []
        r2.completeness = 5
        r2.correctness = 6
        r2.citation_coverage = 2
        r2.rationale = "Lacking citations."
        return [r1, r2]

    def test_write_json(self, tmp_path):
        results = self._make_results()
        path = tmp_path / "results.json"
        _write_json(results, path)
        assert path.exists()
        import json
        data = json.loads(path.read_text(encoding="utf-8"))
        assert len(data) == 2
        assert data[0]["prompt_id"] == "p1"

    def test_write_csv(self, tmp_path):
        results = self._make_results()
        path = tmp_path / "results.csv"
        _write_csv(results, path)
        assert path.exists()
        lines = path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 3  # header + 2 rows

    def test_write_dashboard(self, tmp_path):
        results = self._make_results()
        path = tmp_path / "dashboard.html"
        _write_dashboard(results, path)
        assert path.exists()
        html = path.read_text(encoding="utf-8")
        assert "PDA Evaluation Dashboard" in html
        assert "specs" in html
        assert "overview" in html

    def test_write_empty_dashboard(self, tmp_path):
        path = tmp_path / "dashboard.html"
        _write_dashboard([], path)
        assert path.exists()
        assert "No results" in path.read_text(encoding="utf-8")
