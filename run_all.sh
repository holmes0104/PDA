#!/usr/bin/env bash
# Run full PDA demo: ingest → factsheet → audit → content-pack → simulate → verify.
# From project root, with venv activated and .env configured.

set -e
cd "$(dirname "$0")"
SAMPLE=sample
PDF=$SAMPLE/brochure.pdf

if [ ! -f "$PDF" ]; then
  echo "Generating $PDF (requires reportlab)..."
  python scripts/generate_sample_brochure.py
fi

echo "=== 1. Ingest ==="
pda ingest --pdf "$PDF" --out "$SAMPLE"

echo "=== 2. Factsheet ==="
pda factsheet --project "$SAMPLE" --out "$SAMPLE/factsheet.json" --allow-unsafe

echo "=== 3. Audit ==="
pda audit "$PDF" --output "$SAMPLE/output" --allow-unsafe

echo "=== 4. Content-pack ==="
pda content-pack --project "$SAMPLE" --factsheet "$SAMPLE/factsheet.json" --audit "$SAMPLE/output/audit.json" --out "$SAMPLE/outputs" --allow-unsafe

echo "=== 5. Simulate ==="
pda simulate --project "$SAMPLE" --factsheet "$SAMPLE/factsheet.json" --variantA "$SAMPLE/outputs/product_page_outline.md" --out "$SAMPLE/outputs"

echo "=== 6. Verify ==="
pda verify --project "$SAMPLE" --factsheet "$SAMPLE/factsheet.json" --audit "$SAMPLE/output/audit.json" --out "$SAMPLE/outputs"

echo "Demo complete. See $SAMPLE/output and $SAMPLE/outputs."
