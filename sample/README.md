# Sample project for PDA demo

This folder is used by the end-to-end demo (`run_all.sh` / `make demo` / `run_demo.ps1`).

## Brochure

- **brochure.pdf** — Minimal sample PDF (project-owned, no external license).
- If missing, generate it from the project root:
  ```bash
  python scripts/generate_sample_brochure.py
  ```
  Requires: `pip install reportlab`

## After running the demo

The pipeline creates:

- **chunks.jsonl**, **raw_extraction/** — from `pda ingest`
- **chroma_data/** — vector index from `pda factsheet`
- **factsheet.json**, **factsheet_provenance.json** — product fact sheet
- **output/** — audit report (report.md, report.html, audit.json, verifier_report.md)
- **outputs/** — content pack (product_page_outline.md, faq.md, comparison.md, jsonld_product_skeleton.json), simulator results, prompts.json

See project **README.md** for full command reference.
