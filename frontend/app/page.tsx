'use client'

import { useState, useCallback } from 'react'
import axios from 'axios'

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

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */
export default function Home() {
  const [file, setFile] = useState<File | null>(null)
  const [productUrl, setProductUrl] = useState('')
  const [projectId, setProjectId] = useState<string | null>(null)

  const [step, setStep] = useState<Step>('idle')
  const [progress, setProgress] = useState(0)       // 0-100
  const [statusMsg, setStatusMsg] = useState('')
  const [error, setError] = useState('')

  const [ingest, setIngest] = useState<IngestResult | null>(null)
  const [factsheet, setFactsheet] = useState<FactsheetResult | null>(null)
  const [audit, setAudit] = useState<AuditResult | null>(null)

  /* helpers */
  const reset = () => {
    setFile(null); setProductUrl(''); setProjectId(null)
    setStep('idle'); setProgress(0); setStatusMsg(''); setError('')
    setIngest(null); setFactsheet(null); setAudit(null)
  }

  const downloadFile = useCallback((fileType: string) => {
    if (!projectId) return
    window.open(`${API_BASE}/api/download/${projectId}/${fileType}`, '_blank')
  }, [projectId])

  /* ---- Upload ---------------------------------------------------- */
  const handleUpload = async () => {
    if (!file) return
    setError(''); setStep('uploading'); setProgress(10)
    setStatusMsg('Uploading PDF...')

    try {
      const formData = new FormData()
      formData.append('pdf', file)
      if (productUrl.trim()) formData.append('url', productUrl.trim())

      const res = await axios.post(`${API_BASE}/api/ingest`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (e) => {
          if (e.total) setProgress(Math.round((e.loaded / e.total) * 30))
        },
      })

      setProjectId(res.data.project_id)
      setIngest(res.data)
      setProgress(30)
      setStatusMsg(`Uploaded — ${res.data.chunks_count} chunks extracted.`)
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || 'Upload failed')
      setStep('idle'); setProgress(0)
    }
  }

  /* ---- Factsheet ------------------------------------------------- */
  const handleFactsheet = async () => {
    if (!projectId) return
    setError(''); setStep('factsheet'); setProgress(40)
    setStatusMsg('Extracting product fact sheet (LLM call)...')

    try {
      const res = await axios.post(`${API_BASE}/api/factsheet`, { project_id: projectId })
      setFactsheet(res.data)
      setProgress(60)
      setStatusMsg('Fact sheet extracted.')
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || 'Factsheet extraction failed')
      setStep('idle')
    }
  }

  /* ---- Audit ----------------------------------------------------- */
  const handleAudit = async () => {
    if (!projectId) return
    setError(''); setStep('auditing'); setProgress(70)
    setStatusMsg('Running full audit (this may take 1-3 min)...')

    try {
      const res = await axios.post(`${API_BASE}/api/audit`, {
        project_id: projectId,
        allow_unsafe: false,
      })
      setAudit(res.data)
      setProgress(100); setStep('done')
      setStatusMsg('Audit complete! Download your reports below.')
    } catch (err: any) {
      const detail = err?.response?.data?.detail || ''
      if (detail.includes('blocked issues') || detail.includes('Verifier')) {
        // retry with allow_unsafe
        try {
          const res2 = await axios.post(`${API_BASE}/api/audit`, {
            project_id: projectId,
            allow_unsafe: true,
          })
          setAudit(res2.data)
          setProgress(100); setStep('done')
          setStatusMsg('Audit complete (verifier warnings present). Download below.')
        } catch {
          setError(detail || 'Audit failed on retry')
          setStep('idle')
        }
      } else {
        setError(detail || err.message || 'Audit failed')
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
        <h1>PDA</h1>
        <p className="subtitle">Product Discoverability Auditor</p>
        <p className="tagline">
          Upload a product PDF brochure and receive a full LLM-readiness audit — structured
          fact sheet, scorecard, gap analysis, and an LLM-friendly content pack.
        </p>
      </header>

      {/* ── Demo Banner ────────────────────────────────────────── */}
      {step === 'idle' && !ingest && (
        <section className="card demo-card">
          <h2>Demo Mode</h2>
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
            <li>Download your HTML / Markdown / JSON reports.</li>
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
          <p className="small-text">Project: <code>{ingest.project_id}</code> — {ingest.chunks_count} chunks</p>
          <div className="btn-row">
            <button
              onClick={handleFactsheet}
              disabled={busy || !!factsheet}
              className={`btn ${factsheet ? 'btn-done' : 'btn-green'}`}
            >
              {factsheet ? 'Factsheet Extracted' : 'Extract Factsheet'}
            </button>
            <button
              onClick={handleAudit}
              disabled={busy || !factsheet || !!audit}
              className={`btn ${audit ? 'btn-done' : 'btn-amber'}`}
            >
              {audit ? 'Audit Complete' : 'Run Audit'}
            </button>
          </div>
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

      {/* ── Audit Downloads ────────────────────────────────────── */}
      {audit && (
        <section className="card card-amber">
          <h2>Audit Reports</h2>
          <div className="btn-row">
            <button onClick={() => downloadFile('report_html')} className="btn btn-primary btn-lg">HTML Report</button>
            <button onClick={() => downloadFile('report_md')} className="btn btn-secondary">Markdown Report</button>
            <button onClick={() => downloadFile('audit_json')} className="btn btn-teal">Audit Data (JSON)</button>
            <button onClick={() => downloadFile('verifier_report')} className="btn btn-amber">Verifier Report</button>
          </div>
        </section>
      )}

      {/* ── Footer ─────────────────────────────────────────────── */}
      <footer className="footer">
        PDA &middot; Built with Next.js + FastAPI &middot; API&nbsp;
        <a href={`${API_BASE}/api/docs`} target="_blank" rel="noopener noreferrer">docs</a>
      </footer>
    </main>
  )
}
