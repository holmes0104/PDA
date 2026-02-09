'use client'

import { useState, useCallback, useEffect, useRef } from 'react'
import Link from 'next/link'
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

type PipelineStage = '' | 'queued' | 'ingest' | 'factsheet' | 'audit' | 'content' | 'done'
type PipelineStatus = 'idle' | 'uploading' | 'running' | 'succeeded' | 'failed'

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

/* ------------------------------------------------------------------ */
/*  Stage labels for the progress stepper                              */
/* ------------------------------------------------------------------ */
const STAGE_LABELS: Record<string, string> = {
  queued:     'Queued',
  ingest:     'Parsing PDF',
  factsheet:  'Extracting Facts',
  audit:      'Quality Audit',
  content:    'Generating Content',
  done:       'Complete',
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
/*  Pipeline Stepper — visual stage indicator                           */
/* ================================================================== */
const STAGES: PipelineStage[] = ['ingest', 'factsheet', 'audit', 'content', 'done']

function PipelineStepper({ currentStage, hasFactsheet, hasAudit, hasContent }: {
  currentStage: PipelineStage
  hasFactsheet: boolean
  hasAudit: boolean
  hasContent: boolean
}) {
  const stageIdx = STAGES.indexOf(currentStage)

  const isDone = (s: PipelineStage) => {
    if (s === 'ingest') return stageIdx > 0
    if (s === 'factsheet') return hasFactsheet && stageIdx > 1
    if (s === 'audit') return hasAudit && stageIdx > 2
    if (s === 'content') return hasContent
    if (s === 'done') return currentStage === 'done'
    return false
  }
  const isActive = (s: PipelineStage) => s === currentStage

  return (
    <div style={{ display: 'flex', gap: '0.25rem', margin: '1rem 0', flexWrap: 'wrap' }}>
      {STAGES.map((s) => (
        <div
          key={s}
          style={{
            flex: 1,
            minWidth: '80px',
            padding: '0.5rem 0.25rem',
            textAlign: 'center',
            fontSize: '0.75rem',
            fontWeight: isActive(s) ? 700 : 500,
            borderRadius: 6,
            background: isDone(s)
              ? 'var(--misty-green-light, #d1fae5)'
              : isActive(s)
                ? 'var(--thunder-blue-light, #dbeafe)'
                : 'var(--bg, #f3f4f6)',
            color: isDone(s)
              ? 'var(--success-text, #065f46)'
              : isActive(s)
                ? 'var(--thunder-blue, #1d4ed8)'
                : 'var(--muted, #6b7280)',
            border: isActive(s) ? '2px solid var(--thunder-blue, #1d4ed8)' : '1px solid var(--border-light, #e5e7eb)',
            transition: 'all 0.3s ease',
          }}
        >
          {isDone(s) ? '✓ ' : isActive(s) ? '● ' : ''}{STAGE_LABELS[s] || s}
        </div>
      ))}
    </div>
  )
}

/* ================================================================== */
/*  Content Pack Page — single-upload, full pipeline                    */
/* ================================================================== */
function ContentPackApp({ session, onLogout }: { session: AuthSession; onLogout: () => void }) {
  const [file, setFile] = useState<File | null>(null)
  const [productUrl, setProductUrl] = useState('')
  const [selectedLLM, setSelectedLLM] = useState(0)
  const [tone, setTone] = useState<'neutral' | 'technical' | 'marketing'>('neutral')
  const [audience, setAudience] = useState<'engineer' | 'procurement' | 'ops_manager'>('ops_manager')

  const [pipelineStatus, setPipelineStatus] = useState<PipelineStatus>('idle')
  const [jobId, setJobId] = useState<string | null>(null)
  const [projectId, setProjectId] = useState<string | null>(null)
  const [progress, setProgress] = useState(0)
  const [stage, setStage] = useState<PipelineStage>('')
  const [stageDetail, setStageDetail] = useState('')
  const [error, setError] = useState('')

  const [hasFactsheet, setHasFactsheet] = useState(false)
  const [hasAudit, setHasAudit] = useState(false)
  const [hasContent, setHasContent] = useState(false)
  const [contentDrafts, setContentDrafts] = useState<ContentDrafts | null>(null)

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
    setFile(null); setProductUrl('')
    setPipelineStatus('idle'); setJobId(null); setProjectId(null)
    setProgress(0); setStage(''); setStageDetail(''); setError('')
    setHasFactsheet(false); setHasAudit(false); setHasContent(false)
    setContentDrafts(null)
  }

  /* ---- Start Pipeline ---------------------------------------------- */
  const handleStart = async () => {
    if (!file) return
    setError('')
    setPipelineStatus('uploading')
    setProgress(2)
    setStageDetail('Uploading PDF…')

    try {
      const formData = new FormData()
      formData.append('pdf', file)
      if (productUrl.trim()) formData.append('url', productUrl.trim())
      formData.append('llm_provider', llm.provider)
      formData.append('llm_model', llm.model)
      formData.append('tone', tone)
      formData.append('audience', audience)

      const res = await api.post('/api/pipeline', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (e) => {
          if (e.total) setProgress(Math.round((e.loaded / e.total) * 4))
        },
      })

      setJobId(res.data.job_id)
      setProjectId(res.data.project_id)
      setPipelineStatus('running')
      setStage('queued')
      setStageDetail('Pipeline job queued…')
    } catch (err: any) {
      const detail = err?.response?.data?.detail || err.message || 'Failed to start pipeline'
      setError(detail)
      setPipelineStatus('failed')
    }
  }

  /* ---- Poll for job status ---------------------------------------- */
  useEffect(() => {
    if (!jobId || pipelineStatus !== 'running') return
    const interval = setInterval(async () => {
      try {
        const res = await api.get(`/api/pipeline-jobs/${jobId}`)
        const d = res.data

        setProgress(d.progress || 0)
        setStage(d.stage || '')
        setStageDetail(d.stage_detail || '')
        setHasFactsheet(d.has_factsheet || false)
        setHasAudit(d.has_audit || false)
        setHasContent(d.has_content || false)

        if (d.status === 'succeeded') {
          setPipelineStatus('succeeded')
          if (d.drafts) setContentDrafts(d.drafts as ContentDrafts)
        } else if (d.status === 'failed') {
          setPipelineStatus('failed')
          setError(d.error_message || 'Pipeline failed.')
        }
      } catch {
        /* keep polling on fetch error */
      }
    }, 2500)
    return () => clearInterval(interval)
  }, [jobId, pipelineStatus, api])

  /* ---- Downloads --------------------------------------------------- */
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

  const downloadContentZip = useCallback(async () => {
    if (!projectId) return
    try {
      const res = await api.get(`/api/products/${projectId}/exports/content`, {
        params: { format: 'zip' },
        responseType: 'blob',
      })
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
      setError(err?.response?.data?.detail || 'Download failed')
    }
  }, [projectId, api])

  const downloadContentJson = useCallback(async () => {
    if (!contentDrafts) return
    const blob = new Blob([JSON.stringify({ drafts: contentDrafts }, null, 2)], { type: 'application/json' })
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `content-${projectId || 'drafts'}.json`
    document.body.appendChild(a)
    a.click()
    a.remove()
    window.URL.revokeObjectURL(url)
  }, [projectId, contentDrafts])

  const busy = pipelineStatus === 'uploading' || pipelineStatus === 'running'

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
          <Link href="/" className="btn btn-ghost btn-sm" style={{ marginRight: '0.5rem' }}>Dashboard</Link>
          <button onClick={onLogout} className="btn btn-ghost btn-sm">Sign Out</button>
        </div>
        <h1>Content Pack Generator</h1>
        <p className="subtitle">LLM-Ready Product Content</p>
        <p className="tagline">
          Upload a product PDF and the system automatically extracts facts, runs a quality audit,
          and generates publishable content &mdash; all in one step.
        </p>
        <p className="header-vaisala">Designed for <strong>Vaisala</strong> by Thanh Nguyen (Holmes)</p>
      </header>

      {/* ── Getting Started ────────────────────────────────────── */}
      {pipelineStatus === 'idle' && (
        <section className="card demo-card">
          <h2>How it works</h2>
          <ol>
            <li>Upload a product PDF (datasheet, brochure, or fact sheet).</li>
            <li>The system <strong>automatically</strong> runs: Extract &rarr; Facts &rarr; Audit &rarr; Content Drafts.</li>
            <li>Watch the progress, then download your finished content pack.</li>
          </ol>
        </section>
      )}

      {/* ── Upload Card ────────────────────────────────────────── */}
      <section className="card">
        <h2>Upload &amp; Generate</h2>

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
          <div style={{ flex: 1, minWidth: '120px' }}>
            <label className="label">Tone</label>
            <select value={tone} onChange={(e) => setTone(e.target.value as any)} disabled={busy} className="select-input">
              <option value="neutral">Neutral</option>
              <option value="technical">Technical</option>
              <option value="marketing">Marketing</option>
            </select>
          </div>
          <div style={{ flex: 1, minWidth: '120px' }}>
            <label className="label">Audience</label>
            <select value={audience} onChange={(e) => setAudience(e.target.value as any)} disabled={busy} className="select-input">
              <option value="ops_manager">Ops Manager</option>
              <option value="engineer">Engineer</option>
              <option value="procurement">Procurement</option>
            </select>
          </div>
        </div>

        <div style={{ display: 'flex', gap: '0.75rem', marginTop: '1rem', alignItems: 'center' }}>
          <button onClick={handleStart} disabled={!file || busy} className="btn btn-primary btn-lg">
            {pipelineStatus === 'uploading' ? 'Uploading…' : pipelineStatus === 'running' ? 'Running…' : 'Upload & Generate'}
          </button>
          {(pipelineStatus === 'succeeded' || pipelineStatus === 'failed') && (
            <button onClick={reset} className="btn btn-ghost">Start Over</button>
          )}
        </div>
      </section>

      {/* ── Pipeline Progress ──────────────────────────────────── */}
      {busy && stage && (
        <PipelineStepper currentStage={stage} hasFactsheet={hasFactsheet} hasAudit={hasAudit} hasContent={hasContent} />
      )}

      {(busy || pipelineStatus === 'succeeded') && (
        <div className="progress-wrapper">
          <div className="progress-bar" style={{ width: `${progress}%` }} />
          <span className="progress-label">{progress}%</span>
        </div>
      )}

      {stageDetail && !error && (
        <div className={`alert ${pipelineStatus === 'succeeded' ? 'alert-success' : 'alert-info'}`}>
          {stageDetail}
        </div>
      )}
      {error && <div className="alert alert-error">{error}</div>}

      {/* ── Completed stepper (when done) ──────────────────────── */}
      {pipelineStatus === 'succeeded' && stage === 'done' && (
        <PipelineStepper currentStage="done" hasFactsheet={true} hasAudit={true} hasContent={true} />
      )}

      {/* ── Downloads — Factsheet ─────────────────────────────── */}
      {hasFactsheet && (pipelineStatus === 'succeeded' || pipelineStatus === 'running') && (
        <section className="card card-green">
          <h2>Factsheet</h2>
          <div className="btn-row">
            <button onClick={() => downloadFile('factsheet')} className="btn btn-green btn-sm">Factsheet (JSON)</button>
            <button onClick={() => downloadFile('factsheet_provenance')} className="btn btn-teal btn-sm">Provenance (JSON)</button>
            <button onClick={() => downloadFile('verifier_report')} className="btn btn-amber btn-sm">Verifier Report</button>
          </div>
        </section>
      )}

      {/* ── Downloads — Audit Reports ─────────────────────────── */}
      {hasAudit && (pipelineStatus === 'succeeded' || pipelineStatus === 'running') && (
        <section className="card">
          <h2>Audit Reports</h2>
          <div className="btn-row">
            <button onClick={() => downloadFile('report_html')} className="btn btn-primary btn-sm">HTML Report</button>
            <button onClick={() => downloadFile('report_md')} className="btn btn-secondary btn-sm">Markdown Report</button>
            <button onClick={() => downloadFile('audit_json')} className="btn btn-teal btn-sm">Audit Data (JSON)</button>
          </div>
        </section>
      )}

      {/* ── Content Drafts (rendered inline) ──────────────────── */}
      {contentDrafts && pipelineStatus === 'succeeded' && (
        <section className="card card-green">
          <h2>Content Drafts</h2>
          <div className="btn-row" style={{ marginBottom: '1rem' }}>
            <button onClick={downloadContentJson} className="btn btn-secondary btn-sm">Download JSON</button>
            <button onClick={downloadContentZip} className="btn btn-teal btn-sm">Download ZIP</button>
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
                    {u.problem_context && <p className="small-text" style={{ marginTop: '0.25rem', marginBottom: 0 }}>{u.problem_context.slice(0, 150)}…</p>}
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
