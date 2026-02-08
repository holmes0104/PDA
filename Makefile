# PDA — LLM Product Discoverability Auditor
# Cross-platform dev workflow

.PHONY: dev demo install sample-pdf backend frontend

# Start both backend and frontend
dev: install
	@echo "Starting backend and frontend..."
	@make backend & make frontend & wait

# Start backend only
backend:
	@echo "Starting FastAPI backend on http://localhost:8000"
	@cd backend && uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Start frontend only
frontend:
	@echo "Starting Next.js frontend on http://localhost:3000"
	@cd frontend && npm run dev

# Install Python dependencies
install:
	pip install -e .

# Install frontend dependencies
install-frontend:
	cd frontend && npm install

# CLI demo (requires venv activated and .env configured)
demo: sample-pdf
	pda ingest --pdf sample/brochure.pdf --out sample
	pda factsheet --project sample --out sample/factsheet.json --allow-unsafe
	pda audit sample/brochure.pdf --output sample/output --allow-unsafe
	pda content-pack --project sample --factsheet sample/factsheet.json --audit sample/output/audit.json --out sample/outputs --allow-unsafe
	pda simulate --project sample --factsheet sample/factsheet.json --variantA sample/outputs/product_page_outline.md --out sample/outputs
	pda verify --project sample --factsheet sample/factsheet.json --audit sample/output/audit.json --out sample/outputs
	@echo "Demo complete. See sample/output and sample/outputs."

sample-pdf:
	@test -f sample/brochure.pdf || python scripts/generate_sample_brochure.py
