'use client'

import { useState, useCallback, useEffect, useRef } from 'react'
import axios, { AxiosInstance } from 'axios'

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */
interface AuthSession {
  token: string
  username: string
  display_name: string
}

interface LLMOption {
  provider: string
  model: string
  label: string
}
const LLM_OPTIONS: LLMOption[] = [
  { provider: 'openai',    model: 'gpt-5.2',                    label: 'GPT-5.2 (OpenAI)' },
  { provider: 'openai',    model: 'gpt-4o',                     label: 'GPT-4o (OpenAI)' },
  { provider: 'openai',    model: 'gpt-4o-mini',                label: 'GPT-4o Mini (OpenAI)' },
  { provider: 'anthropic', model: 'claude-sonnet-4-20250514',   label: 'Claude Sonnet 4 (Anthropic)' },
  { provider: 'anthropic', model: 'claude-3-5-sonnet-20241022', label: 'Claude 3.5 Sonnet (Anthropic)' },
]

interface PreflightQuestion {
  field: string
  question: string
  why_needed: string
}
interface Preflight {
  product_name: string
  facts_found: number
  facts_expected: number
  missing_fields: string[]
  questions: PreflightQuestion[]
  can_generate: boolean
}
interface GenerateResult {
  project_id: string
  status: string
  preflight: Preflight
  files: Record<string, string>
  assumptions: string[]
  manifest_path: string
}

type Step = 'idle' | 'uploading' | 'generating' | 'done' | 'preflight_blocked'

/* ================================================================== */
/*  Content Pack Page                                                   */
/* ================================================================== */
function ContentPackApp({ session, onLogout }: { session: AuthSession; onLogout: () => void }) {
  const [file, setFile] = useState<File | null>(null)
  const [productUrl, setProductUrl] = useState('')
  const [projectId, setProjectId] = useState<string | null>(null)
  const [chunksCount, setChunksCount] = useState(0)
  const [selectedLLM, setSelectedLLM] = useState(0)
  const [tone, setTone] = useState<'technical' | 'buyer' | 'hybrid'>('technical')

  const [step, setStep] = useState<Step>('idle')
  const [progress, setProgress] = useState(0)
  const [statusMsg, setStatusMsg] = useState('')
  const [error, setError] = useState('')

  const [result, setResult] = useState<GenerateResult | null>(null)

  /* ── Authenticated axios instance ─────────────────────────────── */
  const apiRef = useRef<AxiosInstance | null>(null)
  if (!apiRef.current) {
    apiRef.current = axios.create({
      baseURL: API_BASE,
      headers: { Authorization: `Bearer ${session.token}` },
    })
    apiRef.current.interceptors.response.use(
      (r) => r,
      (err) => {
        if (err?.response?.status === 401) onLogout()
        return Promise.reject(err)
      },
    )
  }
  const api = apiRef.current!
  const llm = LLM_OPTIONS[selectedLLM]

  const reset = () => {
    setFile(null); setProductUrl(''); setProjectId(null); setChunksCount(0)
    setStep('idle'); setProgress(0); setStatusMsg(''); setError('')
    setResult(null)
  }

  /* ---- Upload ---------------------------------------------------- */
  const handleUpload = async () => {
    if (!file) return
    setError(''); setStep('uploading'); setProgress(10)
    setStatusMsg('Uploading and ingesting PDF...')

    try {
      const formData = new FormData()
      formData.append('pdf', file)
      if (productUrl.trim()) formData.append('url', productUrl.trim())

      const res = await api.post('/api/ingest', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (e) => {
          if (e.total) setProgress(Math.round((e.loaded / e.total) * 25))
        },
      })

      setProjectId(res.data.project_id)
      setChunksCount(res.data.chunks_count)
      setProgress(25)
      setStatusMsg(`Uploaded — ${res.data.chunks_count} chunks extracted. Ready to generate.`)
      setStep('idle')
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || 'Upload failed')
      setStep('idle'); setProgress(0)
    }
  }

  /* ---- Generate Content Pack ------------------------------------- */
  const handleGenerate = async (proceedWithAssumptions = false) => {
    if (!projectId) return
    setError(''); setStep('generating')
    setProgress(proceedWithAssumptions ? 35 : 30)
    setStatusMsg('Generating LLM-ready content pack (this may take 2-5 min)...')

    try {
      const res = await api.post('/api/generate_content_pack', {
        project_id: projectId,
        tone,
        llm_provider: llm.provider,
        llm_model: llm.model,
        proceed_with_assumptions: proceedWithAssumptions,
      }, {
        timeout: 600000, // 10 minutes timeout
      })

      const data: GenerateResult = res.data

      if (data.status === 'preflight_blocked') {
        setResult(data)
        setStep('preflight_blocked')
        setProgress(30)
        setStatusMsg('Preflight detected missing critical fields. Please review the questions below.')
        return
      }

      setResult(data)
      setProgress(100)
      setStep('done')
      setStatusMsg('Content pack generated! Download your files below.')
    } catch (err: any) {
      const detail = err?.response?.data?.detail || err.message || ''
      const status = err?.response?.status

      if (status === 402 || detail.toLowerCase().includes('quota')) {
        setError(`API quota issue: ${detail}`)
      } else {
        setError(detail || 'Content pack generation failed.')
      }
      setStep('idle')
    }
  }

  /* ---- Download -------------------------------------------------- */
  const downloadFile = useCallback((fileType: string) => {
    if (!projectId) return
    api.get(`/api/download/${projectId}/${fileType}`, { responseType: 'blob' })
      .then((res) => {
        const blob = new Blob([res.data], { type: res.headers['content-type'] })
        const url = window.URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        const cd = res.headers['content-disposition']
        const match = cd?.match(/filename="?(.+?)"?$/)
        a.download = match ? match[1] : `${fileType}.${res.headers['content-type']?.split('/')[1] || 'bin'}`
        document.body.appendChild(a)
        a.click()
        a.remove()
        window.URL.revokeObjectURL(url)
      })
      .catch((err: any) => {
        setError(err?.response?.data?.detail || 'Download failed')
      })
  }, [projectId, api])

  const busy = step === 'uploading' || step === 'generating'

  /* ================================================================ */
  /*  Render                                                          */
  /* ================================================================ */
  return (
    <main className="page">
      {/* ── Header ─────────────────────────────────────────────── */}
      <header className="header">
        <div className="header-top-bar">
          <span className="header-user">
            Signed in as <strong>{session.display_name}</strong>
          </span>
          <a href="/" className="btn btn-ghost btn-sm" style={{ marginRight: '0.5rem' }}>Dashboard</a>
          <button onClick={onLogout} className="btn btn-ghost btn-sm">Sign Out</button>
        </div>
        <h1>Content Pack Generator</h1>
        <p className="subtitle">LLM-Ready Product Content</p>
        <p className="tagline">
          Upload a product PDF and generate publishable, AI-answerable content packages &mdash;
          canonical answers, FAQ, selection guidance, and use-case pages.
        </p>
        <p className="header-vaisala">Designed for <strong>Vaisala</strong> by Thanh Nguyen (Holmes)</p>
      </header>

      {/* ── Getting Started ────────────────────────────────────── */}
      {step === 'idle' && !projectId && (
        <section className="card demo-card">
          <h2>How it works</h2>
          <ol>
            <li>Upload a product PDF (datasheet, brochure, or fact sheet).</li>
            <li>Select a tone: <strong>Technical</strong>, <strong>Buyer</strong>, or <strong>Hybrid</strong>.</li>
            <li><strong>Generate Content Pack</strong> — the LLM produces grounded, citable content.</li>
            <li>Download Markdown files + JSON manifest as an export bundle.</li>
          </ol>
        </section>
      )}

      {/* ── Upload Card ────────────────────────────────────────── */}
      <section className="card">
        <h2>1. Upload Source Material</h2>

        <label className="label">PDF (required, max 50 MB)</label>
        <input
          type="file"
          accept=".pdf"
          onChange={(e) => { setFile(e.target.files?.[0] || null); setError('') }}
          disabled={busy}
          className="file-input"
        />

        <label className="label" style={{ marginTop: '0.75rem' }}>Product Page URL (optional)</label>
        <input
          type="url"
          placeholder="https://example.com/product"
          value={productUrl}
          onChange={(e) => setProductUrl(e.target.value)}
          disabled={busy}
          className="text-input"
        />

        <div style={{ display: 'flex', gap: '1rem', marginTop: '0.75rem', flexWrap: 'wrap' }}>
          <div style={{ flex: 1, minWidth: '180px' }}>
            <label className="label">LLM Model</label>
            <select
              value={selectedLLM}
              onChange={(e) => setSelectedLLM(Number(e.target.value))}
              disabled={busy}
              className="select-input"
            >
              {LLM_OPTIONS.map((opt, i) => (
                <option key={`${opt.provider}-${opt.model}`} value={i}>{opt.label}</option>
              ))}
            </select>
          </div>
          <div style={{ flex: 1, minWidth: '180px' }}>
            <label className="label">Tone</label>
            <select
              value={tone}
              onChange={(e) => setTone(e.target.value as 'technical' | 'buyer' | 'hybrid')}
              disabled={busy}
              className="select-input"
            >
              <option value="technical">Technical</option>
              <option value="buyer">Buyer</option>
              <option value="hybrid">Hybrid</option>
            </select>
          </div>
        </div>

        <button onClick={handleUpload} disabled={!file || busy} className="btn btn-primary" style={{ marginTop: '1rem' }}>
          {step === 'uploading' ? 'Uploading...' : 'Upload PDF'}
        </button>
        {projectId && (
          <button onClick={reset} className="btn btn-ghost" style={{ marginLeft: '0.75rem', marginTop: '1rem' }}>
            Start Over
          </button>
        )}
      </section>

      {/* ── Progress Bar ───────────────────────────────────────── */}
      {(busy || step === 'done' || step === 'preflight_blocked') && (
        <div className="progress-wrapper">
          <div className="progress-bar" style={{ width: `${progress}%` }} />
          <span className="progress-label">{progress}%</span>
        </div>
      )}

      {/* ── Status / Error ─────────────────────────────────────── */}
      {statusMsg && !error && (
        <div className={`alert ${step === 'done' ? 'alert-success' : 'alert-info'}`}>{statusMsg}</div>
      )}
      {error && <div className="alert alert-error">{error}</div>}

      {/* ── Generate Card ──────────────────────────────────────── */}
      {projectId && step !== 'done' && step !== 'preflight_blocked' && (
        <section className="card">
          <h2>2. Generate Content Pack</h2>
          <p className="small-text">
            Project: <code>{projectId}</code> — {chunksCount} chunks
            &nbsp;&middot;&nbsp; LLM: <strong>{llm.label}</strong>
            &nbsp;&middot;&nbsp; Tone: <strong>{tone}</strong>
          </p>
          <button
            onClick={() => handleGenerate(false)}
            disabled={busy}
            className="btn btn-green"
            style={{ marginTop: '0.5rem' }}
          >
            {step === 'generating' ? 'Generating...' : 'Generate Content Pack'}
          </button>
        </section>
      )}

      {/* ── Preflight Blocked ──────────────────────────────────── */}
      {step === 'preflight_blocked' && result?.preflight && (
        <section className="card card-amber">
          <h2>Preflight: Missing Critical Fields</h2>
          <p className="small-text">
            Found {result.preflight.facts_found} / {result.preflight.facts_expected} expected fields.
            Product: <strong>{result.preflight.product_name || '(unknown)'}</strong>
          </p>
          {result.preflight.questions.length > 0 && (
            <>
              <h3>Questions to resolve:</h3>
              <ol style={{ marginTop: '0.5rem' }}>
                {result.preflight.questions.map((q, i) => (
                  <li key={i} style={{ marginBottom: '0.5rem' }}>
                    <strong>{q.question}</strong>
                    <br />
                    <span className="small-text">Field: {q.field} — {q.why_needed}</span>
                  </li>
                ))}
              </ol>
            </>
          )}
          <div className="btn-row" style={{ marginTop: '1rem' }}>
            <button
              onClick={() => handleGenerate(true)}
              disabled={busy}
              className="btn btn-amber"
            >
              Generate Anyway (with assumptions)
            </button>
            <button onClick={reset} className="btn btn-ghost">Start Over</button>
          </div>
        </section>
      )}

      {/* ── Downloads ──────────────────────────────────────────── */}
      {step === 'done' && result && (
        <section className="card card-green">
          <h2>Content Pack Ready</h2>
          {result.assumptions.length > 0 && (
            <div className="alert alert-info" style={{ marginBottom: '1rem' }}>
              <strong>Assumptions made:</strong>
              <ul style={{ marginTop: '0.25rem', paddingLeft: '1.25rem' }}>
                {result.assumptions.map((a, i) => <li key={i}>{a}</li>)}
              </ul>
            </div>
          )}
          <div className="btn-row">
            <button onClick={() => downloadFile('canonical_answers')} className="btn btn-primary">
              Canonical Answers (MD)
            </button>
            <button onClick={() => downloadFile('content_pack_faq')} className="btn btn-green">
              FAQ (MD)
            </button>
            <button onClick={() => downloadFile('selection_guidance')} className="btn btn-teal">
              Selection Guidance (MD)
            </button>
            <button onClick={() => downloadFile('content_pack_json')} className="btn btn-secondary">
              Full Pack (JSON)
            </button>
            <button onClick={() => downloadFile('content_pack_manifest')} className="btn btn-amber">
              Manifest (JSON)
            </button>
          </div>
          <p className="small-text" style={{ marginTop: '0.75rem' }}>
            Use-case pages are included in the full JSON pack and also available as individual Markdown files in the project directory.
          </p>
        </section>
      )}

      {/* ── Footer ─────────────────────────────────────────────── */}
      <footer className="footer">
        PDA &middot; Designed for Vaisala by Thanh Nguyen (Holmes) &middot; API&nbsp;
        <a href={`${API_BASE}/api/docs`} target="_blank" rel="noopener noreferrer">docs</a>
      </footer>
    </main>
  )
}

/* ================================================================== */
/*  Root — Auth Gate (reuse session from main app)                     */
/* ================================================================== */
export default function ContentPackPage() {
  const [session, setSession] = useState<AuthSession | null>(null)
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
    try {
      const stored = sessionStorage.getItem('pda_session')
      if (stored) {
        const parsed = JSON.parse(stored) as AuthSession
        if (parsed?.token) setSession(parsed)
      }
    } catch { /* ignore */ }
  }, [])

  const handleLogout = useCallback(() => {
    if (session?.token) {
      axios.post(`${API_BASE}/api/auth/logout`, {}, {
        headers: { Authorization: `Bearer ${session.token}` },
      }).catch(() => {})
    }
    sessionStorage.removeItem('pda_session')
    setSession(null)
  }, [session])

  if (!mounted) {
    return (
      <main className="login-page">
        <div className="login-card">
          <div className="login-brand">
            <h1>PDA</h1>
            <p className="login-subtitle">Content Pack Generator</p>
          </div>
        </div>
      </main>
    )
  }

  if (!session) {
    // Redirect to login on the main page
    if (typeof window !== 'undefined') {
      window.location.href = '/'
    }
    return (
      <main className="page">
        <p>Redirecting to login...</p>
      </main>
    )
  }

  return <ContentPackApp session={session} onLogout={handleLogout} />
}
