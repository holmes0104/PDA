# Sample output (stub)

This folder describes the **shape** of pipeline outputs. Real outputs are written to `sample/output` and `sample/outputs` when you run the demo.

## Typical outputs

| Step       | Location        | Files |
|-----------|-----------------|--------|
| Ingest    | `sample/`       | chunks.jsonl, raw_extraction/ |
| Factsheet | `sample/`       | factsheet.json, factsheet_provenance.json, chroma_data/ |
| Audit     | `sample/output/`| report.md, report.html, audit.json, verifier_report.md |
| Content pack | `sample/outputs/` | product_page_outline.md, faq.md, comparison.md, jsonld_product_skeleton.json |
| Simulate  | `sample/outputs/` | prompts.json, simulator_results_A.json, simulator_diff.md (if variant B used) |
| Verify    | (inside audit/content-pack or) `sample/outputs/verifier_report.md` |

Run the full pipeline with:

```bash
./run_all.sh
# or: make demo
```
