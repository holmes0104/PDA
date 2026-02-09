# PDA — LLM-Ready Product Content Generator

Upload a product PDF brochure / datasheet / fact sheet and generate **publishable, AI-answerable product content packages** — canonical answer blocks, themed FAQ, selection guidance, and grounded use-case pages.

| Layer | Stack | Deploy target |
|-------|-------|---------------|
| Frontend | Next.js 15 (React 18, TypeScript) | **Vercel** |
| Backend | FastAPI + Python 3.11 | **Render** (Docker, persistent disk) |
| Vector DB | ChromaDB (on-disk) | Render persistent disk at `/data/chroma` |
| LLM | OpenAI (`gpt-4o`) or Anthropic | API key in env |

---

## Repository layout

```
/
├── backend/          # FastAPI routes + server entry
│   ├── main.py       # App factory, CORS, rate limiter, health
│   ├── run.py        # Uvicorn launcher (reads PORT)
│   └── routes/       # ingest, factsheet, content_pack, audit, simulate, verify, downloads
├── frontend/         # Next.js app (Vercel-ready)
│   ├── app/          # App Router pages + global CSS
│   │   ├── page.tsx            # Main dashboard
│   │   └── content-pack/       # Content Pack Generator page
│   │       └── page.tsx
│   ├── Dockerfile
│   └── next.config.js
├── pda/              # Core Python library (schemas, LLM, ingest, content pack…)
│   ├── content_pack/           # Content pack generators
│   │   ├── llm_ready_pack.py   # Main orchestrator: preflight + 4 output types + export
│   │   └── rag_generator.py    # Legacy RAG generator
│   ├── schemas/
│   │   ├── llm_ready_pack.py   # Schemas for all outputs + manifest
│   │   └── content_pack_schemas.py
│   ├── extract/                # Fact sheet extraction
│   ├── ingest/                 # PDF parsing, URL scraping, chunking
│   └── store/                  # Vector store abstraction (Chroma + pgvector)
├── prompts/          # Jinja2 prompt templates
├── rubrics/          # YAML scoring rubrics
├── tests/            # Pytest test suite
├── Dockerfile.backend
├── docker-compose.yml
├── requirements.txt
├── pyproject.toml
└── .env.example
```

---

## Core outputs

The **Content Pack Generator** produces four grounded output types:

1. **Canonical Answer Blocks** (10–25): 2–4 sentence answers to common buyer questions, each with `best_for`, `not_suitable_when`, and source citations.
2. **Product-page FAQ** (20–40): Grouped by themes (selection, installation, accuracy/specs, environment limits, compatibility/integration, maintenance/calibration, troubleshooting). Every answer cites at least one source chunk.
3. **Selection Guidance**: "Choose this product if…" decision criteria, variant comparison table (when data exists), decision tree, and explicit "Missing info" items.
4. **Use-case Pages** (3–8): Problem context → requirements → why this product fits → implementation notes → FAQs. All claims grounded in extracted facts.

A lightweight **preflight** step automatically detects missing/ambiguous facts and either asks 3–7 targeted questions or labels outputs as assumption-based.

All outputs are exported as **Markdown files + JSON manifest** with full citation traceability (chunk_id + source metadata).

---

## Quick start — local development

### Prerequisites

- Python 3.11+
- Node.js 18+ / npm
- An OpenAI API key (or Anthropic key)

### 1. Backend

```bash
# From repo root
python -m venv .venv
# Windows: .venv\Scripts\activate  |  macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
pip install -e .

# Create .env from the template
cp .env.example .env
# Edit .env → set OPENAI_API_KEY

# Run (default port 8000)
python -m backend.run
# or: uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

Health check: <http://localhost:8000/health>
API docs: <http://localhost:8000/api/docs>

### 2. Frontend

```bash
cd frontend
npm install
npm run dev          # http://localhost:3000
```

The frontend reads `NEXT_PUBLIC_API_BASE_URL` (defaults to `http://localhost:8000`).

### 3. Generate a Content Pack

1. Open <http://localhost:3000/content-pack>.
2. Upload a product PDF and optionally enter a URL.
3. Select tone (Technical / Buyer / Hybrid) and LLM model.
4. Click **Generate Content Pack**.
5. If preflight detects missing fields, answer the questions or click **Generate Anyway**.
6. Download the Markdown + JSON export bundle.

### 4. Docker Compose (optional)

```bash
cp .env.example .env   # fill in keys
docker compose up --build
```

Backend → `localhost:8000`, Frontend → `localhost:3000`.

---

## Running tests

```bash
pip install -e ".[dev]"   # or: pip install reportlab pytest
pytest tests/ -v
```

Tests generate synthetic PDFs at runtime using `reportlab` — no binary fixtures are committed.

To generate example output bundles (not committed):

```bash
# After running a content pack generation, outputs are in:
# data/projects/{project_id}/content_pack/
```

---

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check (Render probe) |
| GET | `/api/health` | Health check (aliased) |
| GET | `/api/docs` | Swagger UI |
| POST | `/api/ingest` | Upload PDF + optional URL |
| POST | `/api/factsheet` | Extract product fact sheet |
| POST | `/api/generate_content_pack` | **Generate LLM-ready content pack** |
| POST | `/api/audit` | Run full audit pipeline |
| POST | `/api/simulate` | Buyer-prompt A/B simulation |
| POST | `/api/verify` | Verify factsheet + audit |
| GET | `/api/download/{project_id}/{file_type}` | Download report files |

### `/api/generate_content_pack` — request body

```json
{
  "project_id": "uuid",
  "tone": "technical",
  "llm_provider": "openai",
  "llm_model": "gpt-4o",
  "proceed_with_assumptions": false
}
```

Response includes preflight status, generated file paths, and any assumptions made.

---

## Deployment

### Backend → Render

1. **Create a new Web Service** on [Render](https://render.com).
2. Connect your GitHub/GitLab repo.
3. Settings:
   | Field | Value |
   |-------|-------|
   | Environment | Docker |
   | Dockerfile Path | `Dockerfile.backend` |
   | Docker Context | `.` (repo root) |
   | Instance type | Starter or above |
4. **Add a Persistent Disk:**
   | Field | Value |
   |-------|-------|
   | Name | pda-data |
   | Mount Path | `/data` |
   | Size | 1 GB (increase if needed) |
5. **Environment variables** (Settings → Environment):

   ```
   OPENAI_API_KEY=sk-...
   PDA_LLM_PROVIDER=openai
   PDA_EMBEDDING_MODEL=openai
   PDA_DATA_DIR=/data
   CORS_ORIGINS=https://your-app.vercel.app
   # Or use regex to allow all Vercel URLs (production + previews):
   CORS_ORIGIN_REGEX=https://.*\.vercel\.app
   ```

   > Render automatically injects `PORT`; the Dockerfile picks it up. If you use `CORS_ORIGIN_REGEX`, you can omit explicit Vercel URLs from `CORS_ORIGINS`.

6. Deploy. The health check is at `/health`.

### Frontend → Vercel

1. **Import project** on [Vercel](https://vercel.com).
2. Set **Root Directory** to `frontend`.
3. Framework preset: **Next.js** (auto-detected).
4. **Environment variable:**

   ```
   NEXT_PUBLIC_API_BASE_URL=https://your-backend.onrender.com
   ```

5. Deploy. Vercel will run `npm install && npm run build` automatically.

### Post-deploy checklist

- [ ] Backend `/health` returns `{"status":"ok", ...}`
- [ ] Frontend can reach the backend (no CORS errors in console)
- [ ] Upload a test PDF and generate a content pack
- [ ] Verify content pack files download correctly

---

## Environment variables reference

| Variable | Where | Default | Description |
|----------|-------|---------|-------------|
| `OPENAI_API_KEY` | Backend | — | OpenAI API key (never sent to client) |
| `ANTHROPIC_API_KEY` | Backend | — | Anthropic key (if using that provider) |
| `PDA_LLM_PROVIDER` | Backend | `openai` | `openai` or `anthropic` |
| `PDA_EMBEDDING_MODEL` | Backend | `openai` | `openai` or `sentence-transformers` |
| `PDA_DATA_DIR` | Backend | `./data` | Data root. Set to `/data` on Render |
| `PORT` | Backend | `8000` | Server port (Render injects this) |
| `CORS_ORIGINS` | Backend | `http://localhost:3000,...` | Comma-separated allowed origins |
| `CORS_ORIGIN_REGEX` | Backend | — | Regex for origins (e.g. `https://.*\.vercel\.app`) |
| `MAX_UPLOAD_BYTES` | Backend | `52428800` | Max PDF upload size (50 MB) |
| `NEXT_PUBLIC_API_BASE_URL` | Frontend | `http://localhost:8000` | Backend URL visible to browser |

---

## Architecture notes

- **Data persistence:** All project data, ChromaDB indexes, and uploads live under `PDA_DATA_DIR`. On Render this is a persistent disk mounted at `/data` so data survives re-deploys.
- **Rate limiting:** A simple in-memory sliding-window limiter (30 req/60 s per IP for mutating endpoints) protects the API.
- **File upload limit:** Defaults to 50 MB; configurable via `MAX_UPLOAD_BYTES`.
- **CORS:** Locked down to `CORS_ORIGINS`. Set `CORS_ORIGIN_REGEX=https://.*\.vercel\.app` to allow all Vercel deployments.
- **Secrets:** `OPENAI_API_KEY` is only used server-side. The frontend never sees it.
- **Traceability:** Every generated section includes citations to source chunks (chunk_id + location metadata).

---

## License

MIT
