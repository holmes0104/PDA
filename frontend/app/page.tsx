'use client'

import { useState, useCallback, useEffect, useRef } from 'react'
import Link from 'next/link'
import axios, { AxiosInstance } from 'axios'

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */
interface IngestResult {
  project_id: string
  chunks_count: number
}
interface FactsheetResult {
  factsheet_path: string
  provenance_path: string
  verifier_report_path: string
}
interface AuditResult {
  report_md_path: string
  report_html_path: string
  audit_json_path: string
  verifier_report_path: string
}
type Step = 'idle' | 'uploading' | 'factsheet' | 'auditing' | 'done'
type ContentTab = 'audit' | 'drafts'
type ContentJobStatus = 'idle' | 'queued' | 'running' | 'succeeded' | 'failed'

interface ContentDrafts {
  landing_page: {
    problem_statement: string
    solution_overview: string
    benefits: { headline: string; description: string; is_factual: boolean }[]
    how_it_works: string
    specs_explained: { spec_name: string; spec_value: string; unit: string; plain_language: string }[]
    call_to_action: string
  }
  faq: { question: string; answer: string; is_factual: boolean }[]
  use_case_pages: { title: string; slug: string; is_suggested: boolean; problem_context: string; solution_fit: string; benefits: string[]; implementation_notes: string }[]
  comparisons: { title: string; best_for: string[]; not_ideal_for: string[]; dimensions: { dimension: string; this_product: string; generic_alternative: string }[] }[]
  seo: { title_tag: string; meta_description: string; headings: { tag: string; text: string }[]; product_jsonld: Record<string, unknown> }
}

interface AuthSession {
  token: string
  username: string
  display_name: string
}

/* ------------------------------------------------------------------ */
/*  LLM model options                                                  */
/* ------------------------------------------------------------------ */
interface LLMOption {
  provider: string
  model: string
  label: string
}
const LLM_OPTIONS: LLMOption[] = [
  { provider: 'openai',    model: 'gpt-5.2',                       label: 'GPT-5.2 (OpenAI)' },
  { provider: 'openai',    model: 'gpt-4o',                        label: 'GPT-4o (OpenAI)' },
  { provider: 'openai',    model: 'gpt-4o-mini',                   label: 'GPT-4o Mini (OpenAI)' },
  { provider: 'openai',    model: 'gpt-4-turbo',                   label: 'GPT-4 Turbo (OpenAI)' },
  { provider: 'openai',    model: 'o3-mini',                       label: 'o3-mini (OpenAI)' },
  { provider: 'anthropic', model: 'claude-sonnet-4-20250514',      label: 'Claude Sonnet 4 (Anthropic)' },
  { provider: 'anthropic', model: 'claude-3-5-sonnet-20241022',    label: 'Claude 3.5 Sonnet (Anthropic)' },
  { provider: 'anthropic', model: 'claude-3-5-haiku-20241022',     label: 'Claude 3.5 Haiku (Anthropic)' },
  { provider: 'anthropic', model: 'claude-3-opus-20240229',        label: 'Claude 3 Opus (Anthropic)' },
]

/* ================================================================== */
/*  Login Screen                                                       */
/* ================================================================== */
function LoginScreen({ onLogin }: { onLogin: (s: AuthSession) => void }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!username || !password) return
    setError(''); setLoading(true)

    try {
      const res = await axios.post(`${API_BASE}/api/auth/login`, { username, password })
      const session: AuthSession = res.data
      // Persist to sessionStorage so refresh keeps you logged in
      sessionStorage.setItem('pda_session', JSON.stringify(session))
      onLogin(session)
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="login-page">
      <div className="login-card">
        <div className="login-brand">
          <h1>PDA</h1>
          <p className="login-subtitle">LLM-Ready Product Content Generator</p>
          <p className="login-vaisala">Designed for <strong>Vaisala</strong></p>
        </div>

        <form onSubmit={handleSubmit} className="login-form">
          <label className="label" htmlFor="username">Username</label>
          <input
            id="username"
            type="text"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            disabled={loading}
            className="text-input"
            placeholder="Enter username"
            autoFocus
          />

          <label className="label" htmlFor="password" style={{ marginTop: '0.75rem' }}>Password</label>
          <input
            id="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={loading}
            className="text-input"
            placeholder="Enter password"
          />

          {error && <div className="alert alert-error" style={{ marginTop: '0.75rem' }}>{error}</div>}

          <button type="submit" disabled={!username || !password || loading} className="btn btn-primary btn-lg login-btn">
            {loading ? 'Signing in...' : 'Sign In'}
          </button>
        </form>

        <p className="login-footer-text">
          By Thanh Nguyen (Holmes)
        </p>
      </div>
    </main>
  )
}

/* ================================================================== */
/*  Minimal Landing (post-login home)                                  */
/* ================================================================== */
function MinimalLanding({
  session,
  onLogout,
  onShowAudit,
}: {
  session: AuthSession
  onLogout: () => void
  onShowAudit: () => void
}) {
  return (
    <main className="page">
      <header className="header">
        <div className="header-top-bar">
          <span className="header-user">
            Signed in as <strong>{session.display_name}</strong>
          </span>
          <button onClick={onLogout} className="btn btn-ghost btn-sm">Sign Out</button>
        </div>
        <h1>PDA</h1>
        <p className="subtitle">LLM-Ready Product Content Generator</p>
        <p className="tagline">
          Upload a product PDF brochure and generate LLM-ready content packs — structured
          fact sheet, canonical answers, FAQ, selection guidance, and use-case pages.
        </p>
        <div style={{ marginTop: '1rem' }}>
          <Link href="/content-pack" className="btn btn-green btn-lg">
            Content Pack Generator
          </Link>
        </div>
        <p className="header-vaisala" style={{ marginTop: '1.5rem' }}>
          <button
            type="button"
            onClick={onShowAudit}
            className="btn btn-ghost btn-sm"
            style={{ fontSize: '0.875rem', color: 'var(--muted)', padding: '0.25rem 0.5rem' }}
          >
            Legacy audit pipeline
          </button>
        </p>
        <p className="header-vaisala">Designed for <strong>Vaisala</strong> by Thanh Nguyen (Holmes)</p>
      </header>
      <footer className="footer">
        PDA &middot; Designed for Vaisala by Thanh Nguyen (Holmes) &middot; API&nbsp;
        <a href={`${API_BASE}/api/docs`} target="_blank" rel="noopener noreferrer">docs</a>
      </footer>
    </main>
  )
}

/* ================================================================== */
/*  FAQ Accordion                                                       */
/* ================================================================== */
function FAQAccordion({ items }: { items: { question: string; answer: string; is_factual?: boolean }[] }) {
  const [open, setOpen] = useState<number | null>(null)
  return (
    <div style={{ marginTop: '0.5rem' }}>
      {items.map((item, i) => (
        <div key={i} style={{ border: '1px solid var(--border-light)', borderRadius: 6, marginBottom: '0.5rem', overflow: 'hidden' }}>
          <button
            type="button"
            onClick={() => setOpen(open === i ? null : i)}
            style={{ width: '100%', padding: '0.6rem 0.75rem', textAlign: 'left', background: open === i ? 'var(--thunder-blue-light)' : 'transparent', border: 'none', cursor: 'pointer', fontWeight: 500, fontSize: '0.9rem' }}
          >
            {open === i ? '▾' : '▸'} {item.question}
          </button>
          {open === i && (
            <div style={{ padding: '0.6rem 0.75rem', borderTop: '1px solid var(--border-light)', fontSize: '0.9rem', color: 'var(--muted)' }}>
              {item.answer}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

/* ================================================================== */
/*  Main App (post-login) — full audit pipeline                        */
/* ================================================================== */
function AppDashboard({
  session,
  onLogout,
  onBackToHome,
}: {
  session: AuthSession
  onLogout: () => void
  onBackToHome?: () => void
}) {
  const [file, setFile] = useState<File | null>(null)
  const [productUrl, setProductUrl] = useState('')
  const [projectId, setProjectId] = useState<string | null>(null)
  const [selectedLLM, setSelectedLLM] = useState(0) // index into LLM_OPTIONS

  const [step, setStep] = useState<Step>('idle')
  const [progress, setProgress] = useState(0)       // 0-100
  const [statusMsg, setStatusMsg] = useState('')
  const [error, setError] = useState('')

  const [ingest, setIngest] = useState<IngestResult | null>(null)
  const [factsheet, setFactsheet] = useState<FactsheetResult | null>(null)
  const [audit, setAudit] = useState<AuditResult | null>(null)
  const [pdfGenerating, setPdfGenerating] = useState(false)

  const [contentTab, setContentTab] = useState<ContentTab>('audit')
  const [contentDrafts, setContentDrafts] = useState<ContentDrafts | null>(null)
  const [contentJobId, setContentJobId] = useState<string | null>(null)
  const [contentStatus, setContentStatus] = useState<ContentJobStatus>('idle')
  const [contentProgress, setContentProgress] = useState(0)
  const [contentError, setContentError] = useState('')

  /* ── Authenticated axios instance ─────────────────────────────── */
  const apiRef = useRef<AxiosInstance | null>(null)
  if (!apiRef.current) {
    apiRef.current = axios.create({
      baseURL: API_BASE,
      headers: { Authorization: `Bearer ${session.token}` },
    })
    // Intercept 401s to auto-logout
    apiRef.current.interceptors.response.use(
      (r) => r,
      (err) => {
        if (err?.response?.status === 401) onLogout()
        return Promise.reject(err)
      },
    )
  }
  const api = apiRef.current!

  /* helpers */
  const llm = LLM_OPTIONS[selectedLLM]

  const reset = () => {
    setFile(null); setProductUrl(''); setProjectId(null)
    setStep('idle'); setProgress(0); setStatusMsg(''); setError('')
    setIngest(null); setFactsheet(null); setAudit(null)
    setContentDrafts(null); setContentJobId(null); setContentStatus('idle'); setContentError(''); setContentTab('audit')
  }

  const downloadFile = useCallback((fileType: string) => {
    if (!projectId) return
    // For downloads we need auth — open via a constructed blob URL
    api.get(`/api/download/${projectId}/${fileType}`, { responseType: 'blob' })
      .then((res) => {
        const blob = new Blob([res.data], { type: res.headers['content-type'] })
        const url = window.URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        // Try to get filename from content-disposition or use fileType
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

  const handleDownloadPdf = useCallback(async () => {
    if (!projectId) return
    setPdfGenerating(true)
    try {
      // Generate PDF first
      await api.post(`/api/download/${projectId}/generate_pdf`)
      // Then download it
      const res = await api.get(`/api/download/${projectId}/report_pdf`, { responseType: 'blob' })
      const blob = new Blob([res.data], { type: 'application/pdf' })
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'report.pdf'
      document.body.appendChild(a)
      a.click()
      a.remove()
      window.URL.revokeObjectURL(url)
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'PDF generation failed')
    } finally {
      setPdfGenerating(false)
    }
  }, [projectId, api])

  /* ---- Content generation (async) --------------------------------- */
  const handleGenerateContent = useCallback(async () => {
    if (!projectId) return
    setContentError('')
    setContentStatus('queued')
    try {
      const res = await api.post(`/api/products/${projectId}/generate-content`, {
        tone: 'neutral',
        length: 'medium',
        audience: 'ops_manager',
      })
      if (res.data.drafts) {
        setContentDrafts(res.data.drafts)
        setContentStatus('succeeded')
        setContentTab('drafts')
      } else {
        setContentJobId(res.data.job_id)
        setContentStatus(res.data.status === 'running' ? 'running' : 'queued')
      }
    } catch (err: any) {
      setContentError(err?.response?.data?.detail || 'Failed to start generation')
      setContentStatus('failed')
    }
  }, [projectId, api])

  useEffect(() => {
    if (!contentJobId || !(contentStatus === 'queued' || contentStatus === 'running')) return
    const interval = setInterval(async () => {
      try {
        const res = await api.get(`/api/generation-jobs/${contentJobId}`)
        const st = res.data.status
        setContentProgress(res.data.progress || 0)
        if (st === 'succeeded' && res.data.drafts) {
          setContentDrafts(res.data.drafts)
          setContentStatus('succeeded')
          setContentError('')
          setContentTab('drafts')
        } else if (st === 'failed') {
          setContentStatus('failed')
          setContentError(res.data.error_message || 'Generation failed')
        } else {
          setContentStatus(st === 'running' ? 'running' : 'queued')
        }
      } catch { /* keep polling */ }
    }, 2000)
    return () => clearInterval(interval)
  }, [contentJobId, contentStatus, api])

  const loadExistingDrafts = useCallback(async () => {
    if (!projectId) return
    try {
      const res = await api.get(`/api/products/${projectId}/content-drafts`)
      setContentDrafts(res.data)
      setContentStatus('succeeded')
    } catch {
      /* no drafts yet */
    }
  }, [projectId, api])

  useEffect(() => {
    if (projectId && !contentDrafts && contentStatus === 'idle') loadExistingDrafts()
  }, [projectId, loadExistingDrafts, contentDrafts, contentStatus])

  const downloadContentJson = useCallback(async () => {
    if (!projectId || !contentDrafts) return
    const blob = new Blob([JSON.stringify({ drafts: contentDrafts }, null, 2)], { type: 'application/json' })
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `content-${projectId}.json`
    document.body.appendChild(a)
    a.click()
    a.remove()
    window.URL.revokeObjectURL(url)
  }, [projectId, contentDrafts])

  const downloadContentZip = useCallback(async () => {
    if (!projectId) return
    try {
      const res = await api.get(`/api/products/${projectId}/exports/content`, { params: { format: 'zip' }, responseType: 'blob' })
      const blob = new Blob([res.data], { type: 'application/zip' })
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `content-${projectId}.zip`
      document.body.appendChild(a)
      a.click()
      a.remove()
      window.URL.revokeObjectURL(url)
    } catch (err: any) {
      setContentError(err?.response?.data?.detail || 'Download failed')
    }
  }, [projectId, api])

  /* ---- Upload ---------------------------------------------------- */
  const handleUpload = async () => {
    if (!file) return
    setError(''); setStep('uploading'); setProgress(10)
    setStatusMsg('Uploading PDF...')

    try {
      const formData = new FormData()
      formData.append('pdf', file)
      if (productUrl.trim()) formData.append('url', productUrl.trim())

      const res = await api.post('/api/ingest', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (e) => {
          if (e.total) setProgress(Math.round((e.loaded / e.total) * 30))
        },
      })

      setProjectId(res.data.project_id)
      setIngest(res.data)
      setProgress(30)
      setStatusMsg(`Uploaded — ${res.data.chunks_count} chunks extracted.`)
      setStep('idle')
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || 'Upload failed')
      setStep('idle'); setProgress(0)
    }
  }

  /* ---- Factsheet ------------------------------------------------- */
  const handleFactsheet = async () => {
    if (!projectId) return
    setError(''); setStep('factsheet'); setProgress(40)
    setStatusMsg(`Extracting product fact sheet via ${llm.label}...`)

    try {
      const res = await api.post('/api/factsheet', {
        project_id: projectId,
        llm_provider: llm.provider,
        llm_model: llm.model,
      })
      setFactsheet(res.data)
      setProgress(60)
      setStatusMsg('Fact sheet extracted.')
      setStep('idle')
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || 'Factsheet extraction failed')
      setStep('idle')
    }
  }

  /* ---- Audit ----------------------------------------------------- */
  const handleAudit = async () => {
    if (!projectId) return
    setError(''); setStep('auditing'); setProgress(70)
    setStatusMsg(`Running full audit via ${llm.label} (this may take 1-3 min)...`)

    try {
      const res = await api.post('/api/audit', {
        project_id: projectId,
        allow_unsafe: false,
        llm_provider: llm.provider,
        llm_model: llm.model,
      }, {
        timeout: 300000, // 5 minutes timeout for long-running audit
      })
      setAudit(res.data)
      setProgress(100); setStep('done')
      setStatusMsg('Audit complete! Download your reports below.')
    } catch (err: any) {
      console.error('Audit error:', err)
      const detail = err?.response?.data?.detail || err?.message || ''
      const status = err?.response?.status
      
      // Handle CORS errors
      if (err?.code === 'ERR_NETWORK' || err?.message?.includes('CORS')) {
        setError('Network error: Cannot connect to backend. Make sure the backend server is running on port 8000.')
        setStep('idle')
        return
      }
      
      // Handle payment/quota errors
      if (status === 402 || detail.toLowerCase().includes('quota') || detail.toLowerCase().includes('payment')) {
        setError(`Payment/Quota Error: ${detail || 'API quota exceeded or payment required. Please check your OpenAI billing.'}`)
        setStep('idle')
        return
      }
      
      // Handle verifier blocked issues - retry with allow_unsafe
      if (detail.includes('blocked issues') || detail.includes('Verifier')) {
        setStatusMsg('Retrying with allow_unsafe=true...')
        try {
          const res2 = await api.post('/api/audit', {
            project_id: projectId,
            allow_unsafe: true,
            llm_provider: llm.provider,
            llm_model: llm.model,
          }, {
            timeout: 300000,
          })
          setAudit(res2.data)
          setProgress(100); setStep('done')
          setStatusMsg('Audit complete (verifier warnings present). Download below.')
        } catch (err2: any) {
          const detail2 = err2?.response?.data?.detail || err2?.message || ''
          setError(detail2 || detail || 'Audit failed on retry')
          setStep('idle')
        }
      } else {
        setError(detail || err.message || 'Audit failed. Check console for details.')
        setStep('idle')
      }
    }
  }

  /* ================================================================ */
  /*  Render                                                          */
  /* ================================================================ */
  const busy = step !== 'idle' && step !== 'done'

  return (
    <main className="page">
      {/* ── Header ─────────────────────────────────────────────── */}
      <header className="header">
        <div className="header-top-bar">
          <span className="header-user">
            Signed in as <strong>{session.display_name}</strong>
          </span>
          {onBackToHome && (
            <button onClick={onBackToHome} className="btn btn-ghost btn-sm" style={{ marginRight: '0.5rem' }}>
              ← Back to home
            </button>
          )}
          <button onClick={onLogout} className="btn btn-ghost btn-sm">Sign Out</button>
        </div>
        <h1>PDA</h1>
        <p className="subtitle">LLM-Ready Product Content Generator</p>
        <p className="tagline">
          Upload a product PDF brochure and generate LLM-ready content packs — structured
          fact sheet, canonical answers, FAQ, selection guidance, and use-case pages.
        </p>
        <div style={{ marginTop: '0.75rem' }}>
          <Link href="/content-pack" className="btn btn-green btn-sm">
            Content Pack Generator
          </Link>
        </div>
        <p className="header-vaisala">Designed for <strong>Vaisala</strong> by Thanh Nguyen (Holmes)</p>
      </header>

      {/* ── Demo Banner ────────────────────────────────────────── */}
      {step === 'idle' && !ingest && (
        <section className="card demo-card">
          <h2>Getting Started</h2>
          <p>
            Don&apos;t have a PDF handy? Use any public product brochure PDF — for example
            download a sample from{' '}
            <a
              href="https://www.w3.org/WAI/WCAG21/Techniques/pdf/img/table-word.pdf"
              target="_blank"
              rel="noopener noreferrer"
            >
              W3C sample PDF
            </a>{' '}
            or grab a product data sheet from your favourite vendor.
          </p>
          <h3>How it works</h3>
          <ol>
            <li>Upload a product PDF (max 50 MB).</li>
            <li><strong>Extract Factsheet</strong> — the LLM pulls structured product facts.</li>
            <li><strong>Run Audit</strong> — scorecard, gap analysis, content pack, and buyer-prompt simulation.</li>
            <li>Download your HTML / Markdown / PDF / JSON reports.</li>
          </ol>
        </section>
      )}

      {/* ── Upload Card ────────────────────────────────────────── */}
      <section className="card">
        <h2>1. Upload Source Material</h2>

        <label className="label">PDF Brochure (required, max 50 MB)</label>
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

        {/* ── LLM Model Selector ──────────────────────────────── */}
        <label className="label" style={{ marginTop: '0.75rem' }}>LLM Model</label>
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
        <p className="hint-text">
          Requires a valid API key for the selected provider in server <code>.env</code>.
        </p>

        <button onClick={handleUpload} disabled={!file || busy} className="btn btn-primary" style={{ marginTop: '1rem' }}>
          {step === 'uploading' ? 'Uploading...' : 'Upload PDF'}
        </button>

        {ingest && (
          <button onClick={reset} className="btn btn-ghost" style={{ marginLeft: '0.75rem', marginTop: '1rem' }}>
            Start Over
          </button>
        )}
      </section>

      {/* ── Progress Bar ───────────────────────────────────────── */}
      {(busy || step === 'done') && (
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

      {/* ── Pipeline Steps ─────────────────────────────────────── */}
      {ingest && (
        <section className="card">
          <h2>2. Pipeline Steps</h2>
          <p className="small-text">
            Project: <code>{ingest.project_id}</code> — {ingest.chunks_count} chunks
            &nbsp;&middot;&nbsp; LLM: <strong>{llm.label}</strong>
          </p>
          <div className="btn-row">
            <button
              onClick={handleFactsheet}
              disabled={busy || !!factsheet}
              className={`btn ${factsheet ? 'btn-done' : 'btn-green'}`}
            >
              {factsheet ? 'Factsheet Extracted' : step === 'factsheet' ? 'Extracting...' : 'Extract Factsheet'}
            </button>
            <button
              onClick={handleAudit}
              disabled={busy || !factsheet || !!audit}
              className={`btn ${audit ? 'btn-done' : 'btn-amber'}`}
            >
              {audit ? 'Audit Complete' : step === 'auditing' ? 'Auditing...' : 'Run Audit'}
            </button>
            <button
              onClick={handleGenerateContent}
              disabled={busy || contentStatus === 'queued' || contentStatus === 'running'}
              className={`btn ${contentDrafts ? 'btn-done' : 'btn-teal'}`}
            >
              {contentStatus === 'queued' || contentStatus === 'running'
                ? `Generating… ${contentProgress}%`
                : contentDrafts
                  ? 'Content ready'
                  : 'Generate content'}
            </button>
          </div>
          {(contentStatus === 'queued' || contentStatus === 'running') && (
            <div className="progress-wrapper" style={{ marginTop: '0.5rem' }}>
              <div className="progress-bar" style={{ width: `${contentProgress}%` }} />
              <span className="progress-label">{contentProgress}%</span>
            </div>
          )}
          {contentError && (
            <div className="alert alert-error" style={{ marginTop: '0.5rem' }}>{contentError}</div>
          )}
        </section>
      )}

      {/* ── Factsheet Downloads ────────────────────────────────── */}
      {factsheet && (
        <section className="card card-green">
          <h2>Factsheet Extracted</h2>
          <div className="btn-row">
            <button onClick={() => downloadFile('factsheet')} className="btn btn-green">Factsheet (JSON)</button>
            <button onClick={() => downloadFile('factsheet_provenance')} className="btn btn-teal">Provenance (JSON)</button>
            <button onClick={() => downloadFile('verifier_report')} className="btn btn-amber">Verifier Report</button>
          </div>
        </section>
      )}

      {/* ── Audit Reports & Content Drafts (tabs) ───────────────── */}
      {(audit || contentDrafts) && (
        <section className="card">
          {(audit && contentDrafts) && (
            <div className="btn-row" style={{ marginBottom: '1rem', borderBottom: '1px solid var(--border-light)', paddingBottom: '0.5rem' }}>
              <button
                onClick={() => setContentTab('audit')}
                className="btn btn-ghost btn-sm"
                style={contentTab === 'audit' ? { background: 'var(--thunder-blue-light)', color: 'var(--thunder-blue)' } : {}}
              >
                Audit Reports
              </button>
              <button
                onClick={() => setContentTab('drafts')}
                className="btn btn-ghost btn-sm"
                style={contentTab === 'drafts' ? { background: 'var(--misty-green-light)', color: 'var(--success-text)' } : {}}
              >
                Content Drafts
              </button>
            </div>
          )}

          {((audit && contentDrafts && contentTab === 'audit') || (audit && !contentDrafts)) && (
            <>
              <h2>Audit Reports</h2>
              <div className="btn-row">
                <button onClick={() => downloadFile('report_html')} className="btn btn-primary btn-lg">HTML Report</button>
                <button onClick={handleDownloadPdf} disabled={pdfGenerating} className="btn btn-red btn-lg">
                  {pdfGenerating ? 'Generating PDF...' : 'PDF Report'}
                </button>
                <button onClick={() => downloadFile('report_md')} className="btn btn-secondary">Markdown Report</button>
                <button onClick={() => downloadFile('audit_json')} className="btn btn-teal">Audit Data (JSON)</button>
                <button onClick={() => downloadFile('verifier_report')} className="btn btn-amber">Verifier Report</button>
              </div>
            </>
          )}

          {((contentDrafts && contentTab === 'drafts') || (contentDrafts && !audit)) && (
            <>
              <h2>Content Drafts</h2>
              <div className="btn-row" style={{ marginBottom: '1rem' }}>
                <button onClick={downloadContentJson} className="btn btn-secondary">Download JSON</button>
                <button onClick={downloadContentZip} className="btn btn-teal">Download ZIP</button>
              </div>

              {/* Landing page */}
              <div style={{ marginBottom: '1.5rem' }}>
                <h3>Landing Page</h3>
                {contentDrafts.landing_page.problem_statement && (
                  <div style={{ marginTop: '0.5rem' }}>
                    <p style={{ fontWeight: 500, color: 'var(--thunder-blue)' }}>Problem</p>
                    <p className="small-text" style={{ marginTop: '0.25rem' }}>{contentDrafts.landing_page.problem_statement}</p>
                  </div>
                )}
                {contentDrafts.landing_page.solution_overview && (
                  <div style={{ marginTop: '0.75rem' }}>
                    <p style={{ fontWeight: 500, color: 'var(--thunder-blue)' }}>Solution</p>
                    <p className="small-text" style={{ marginTop: '0.25rem' }}>{contentDrafts.landing_page.solution_overview}</p>
                  </div>
                )}
                {contentDrafts.landing_page.benefits?.length > 0 && (
                  <div style={{ marginTop: '0.75rem' }}>
                    <p style={{ fontWeight: 500, color: 'var(--thunder-blue)' }}>Benefits</p>
                    <ul style={{ marginTop: '0.25rem', paddingLeft: '1.25rem' }}>
                      {contentDrafts.landing_page.benefits.map((b, i) => (
                        <li key={i} style={{ marginBottom: '0.5rem' }}>
                          <strong>{b.headline}</strong> — {b.description}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {contentDrafts.landing_page.how_it_works && (
                  <div style={{ marginTop: '0.75rem' }}>
                    <p style={{ fontWeight: 500, color: 'var(--thunder-blue)' }}>How It Works</p>
                    <p className="small-text" style={{ marginTop: '0.25rem' }}>{contentDrafts.landing_page.how_it_works}</p>
                  </div>
                )}
                {contentDrafts.landing_page.specs_explained?.length > 0 && (
                  <div style={{ marginTop: '0.75rem' }}>
                    <p style={{ fontWeight: 500, color: 'var(--thunder-blue)' }}>Specs</p>
                    <ul style={{ marginTop: '0.25rem', paddingLeft: '1.25rem' }}>
                      {contentDrafts.landing_page.specs_explained.map((s, i) => (
                        <li key={i} style={{ marginBottom: '0.5rem' }}>
                          <strong>{s.spec_name}:</strong> {s.spec_value} {s.unit} — {s.plain_language}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>

              {/* FAQ accordion */}
              {contentDrafts.faq?.length > 0 && (
                <div style={{ marginBottom: '1.5rem' }}>
                  <h3>FAQ</h3>
                  <FAQAccordion items={contentDrafts.faq} />
                </div>
              )}

              {/* Use case pages */}
              {contentDrafts.use_case_pages?.length > 0 && (
                <div style={{ marginBottom: '1.5rem' }}>
                  <h3>Use Case Pages</h3>
                  <ul style={{ listStyle: 'none', paddingLeft: 0 }}>
                    {contentDrafts.use_case_pages.map((u, i) => (
                      <li key={i} style={{ marginBottom: '0.5rem', padding: '0.5rem', background: 'var(--thunder-blue-light)', borderRadius: 6 }}>
                        <span style={{ fontWeight: 500 }}>{u.is_suggested ? '[Suggested] ' : ''}{u.title}</span>
                        {u.problem_context && <p className="small-text" style={{ marginTop: '0.25rem', marginBottom: 0 }}>{u.problem_context.slice(0, 120)}…</p>}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Comparisons */}
              {contentDrafts.comparisons?.length > 0 && (
                <div style={{ marginBottom: '1.5rem' }}>
                  <h3>Comparisons</h3>
                  <ul style={{ listStyle: 'none', paddingLeft: 0 }}>
                    {contentDrafts.comparisons.map((c, i) => (
                      <li key={i} style={{ marginBottom: '0.5rem', padding: '0.5rem', background: 'var(--thunder-blue-light)', borderRadius: 6 }}>
                        <span style={{ fontWeight: 500 }}>{c.title}</span>
                        {c.best_for?.length > 0 && <p className="small-text" style={{ marginTop: '0.25rem', marginBottom: 0 }}>Best for: {c.best_for.slice(0, 2).join('; ')}</p>}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* SEO preview */}
              {contentDrafts.seo && (
                <div style={{ marginBottom: 0 }}>
                  <h3>SEO Preview</h3>
                  <div style={{ marginTop: '0.5rem', padding: '0.75rem', background: 'var(--bg)', borderRadius: 6, fontSize: '0.85rem' }}>
                    {contentDrafts.seo.title_tag && (
                      <p style={{ color: 'var(--thunder-blue)', fontWeight: 500, marginBottom: '0.25rem' }}>{contentDrafts.seo.title_tag}</p>
                    )}
                    {contentDrafts.seo.meta_description && (
                      <p style={{ color: 'var(--muted)', marginBottom: 0 }}>{contentDrafts.seo.meta_description}</p>
                    )}
                    {contentDrafts.seo.headings?.length > 0 && (
                      <p className="small-text" style={{ marginTop: '0.5rem', marginBottom: 0 }}>
                        H1/H2: {contentDrafts.seo.headings.map(h => h.text).join(' → ')}
                      </p>
                    )}
                  </div>
                </div>
              )}
            </>
          )}

          {contentTab === 'drafts' && !contentDrafts && (
            <p className="small-text">No content drafts yet. Click &quot;Generate content&quot; above.</p>
          )}
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
/*  Root Component — Auth Gate                                         */
/* ================================================================== */
export default function Home() {
  const [session, setSession] = useState<AuthSession | null>(null)
  const [mounted, setMounted] = useState(false)
  const [showAuditPipeline, setShowAuditPipeline] = useState(false)

  // Wait for client-side mount before rendering to avoid hydration
  // mismatches caused by browser extensions (e.g. password managers
  // injecting data-sharid attributes onto form inputs).
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
    // Try to revoke on server (best-effort)
    if (session?.token) {
      axios.post(`${API_BASE}/api/auth/logout`, {}, {
        headers: { Authorization: `Bearer ${session.token}` },
      }).catch(() => {})
    }
    sessionStorage.removeItem('pda_session')
    setSession(null)
  }, [session])

  // Show nothing until client-side JS has mounted — prevents hydration
  // mismatches from browser extensions that mutate SSR'd form attributes.
  if (!mounted) {
    return (
      <main className="login-page">
        <div className="login-card">
          <div className="login-brand">
            <h1>PDA</h1>
            <p className="login-subtitle">LLM-Ready Product Content Generator</p>
            <p className="login-vaisala">Designed for <strong>Vaisala</strong></p>
          </div>
        </div>
      </main>
    )
  }

  if (!session) {
    return <LoginScreen onLogin={setSession} />
  }

  // Show minimal landing by default; "Legacy audit pipeline" reveals full audit UI
  if (!showAuditPipeline) {
    return (
      <MinimalLanding
        session={session}
        onLogout={handleLogout}
        onShowAudit={() => setShowAuditPipeline(true)}
      />
    )
  }
  return (
    <AppDashboard
      session={session}
      onLogout={handleLogout}
      onBackToHome={() => setShowAuditPipeline(false)}
    />
  )
}
