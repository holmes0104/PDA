# PDA — Product Discoverability Auditor

Upload a product PDF brochure and receive a full **LLM-readiness audit**: structured fact sheet, scorecard, gap analysis, buyer-prompt simulation, and an LLM-friendly content pack.

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
│   └── routes/       # ingest, factsheet, audit, simulate, verify, downloads
├── frontend/         # Next.js app (Vercel-ready)
│   ├── app/          # App Router pages + global CSS
│   ├── Dockerfile    # Standalone Next.js image
│   └── next.config.js
├── pda/              # Core Python library (schemas, LLM, ingest, audit…)
├── prompts/          # Jinja2 prompt templates
├── rubrics/          # YAML scoring rubrics
├── Dockerfile.backend
├── docker-compose.yml
├── requirements.txt
├── pyproject.toml
└── .env.example
```

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

### 3. Docker Compose (optional)

```bash
cp .env.example .env   # fill in keys
docker compose up --build
```

Backend → `localhost:8000`, Frontend → `localhost:3000`.

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
   ```

   > Render automatically injects `PORT`; the Dockerfile picks it up.

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
- [ ] Upload a test PDF and run the full pipeline
- [ ] Verify reports download correctly

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
| `MAX_UPLOAD_BYTES` | Backend | `52428800` | Max PDF upload size (50 MB) |
| `NEXT_PUBLIC_API_BASE_URL` | Frontend | `http://localhost:8000` | Backend URL visible to browser |

---

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check (Render probe) |
| GET | `/api/health` | Health check (aliased) |
| GET | `/api/docs` | Swagger UI |
| POST | `/api/ingest` | Upload PDF + optional URL |
| POST | `/api/factsheet` | Extract product fact sheet |
| POST | `/api/audit` | Run full audit pipeline |
| POST | `/api/simulate` | Buyer-prompt A/B simulation |
| POST | `/api/verify` | Verify factsheet + audit |
| GET | `/api/download/{project_id}/{file_type}` | Download report files |

---

## Architecture notes

- **Data persistence:** All project data, ChromaDB indexes, and uploads live under `PDA_DATA_DIR`. On Render this is a persistent disk mounted at `/data` so data survives re-deploys.
- **Rate limiting:** A simple in-memory sliding-window limiter (30 req/60 s per IP for mutating endpoints) protects the API.
- **File upload limit:** Defaults to 50 MB; configurable via `MAX_UPLOAD_BYTES`.
- **CORS:** Locked down to the origins listed in `CORS_ORIGINS`. Add your Vercel URL there.
- **Secrets:** `OPENAI_API_KEY` is only used server-side. The frontend never sees it.

---

## License

MIT
