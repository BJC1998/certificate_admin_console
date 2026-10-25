import { useEffect, useRef, useState } from 'react'
import { exportCertificates } from '../api/certificates'
import type { CertificateQuery } from '../types/certificates'

export function ExportCSVButton({ query, disabled }: { query: CertificateQuery; disabled: boolean }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const mounted = useRef(true)
  const pending = useRef(false)
  const controller = useRef<AbortController | null>(null)
  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false; controller.current?.abort() }
  }, [])

  async function download() {
    if (pending.current || disabled || query.tenantId === null) return
    pending.current = true; setBusy(true); setError(null); setNotice(null)
    const request = new AbortController()
    controller.current = request
    const timeout = window.setTimeout(() => request.abort(), 120000)
    try {
      const { blob, filename } = await exportCertificates(query, request.signal)
      if (!mounted.current) return
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url; link.download = filename; document.body.appendChild(link)
      link.click(); link.remove()
      window.setTimeout(() => URL.revokeObjectURL(url), 1000)
      setNotice(`Download started: ${filename}`)
    } catch (reason: unknown) {
      if (mounted.current) setError(request.signal.aborted ? 'CSV export timed out. Please retry.'
        : reason instanceof Error ? reason.message : 'CSV export failed. Please retry.')
    } finally {
      window.clearTimeout(timeout); pending.current = false
      if (mounted.current) setBusy(false)
    }
  }

  return <div className="export-control">
    <button disabled={disabled || busy} onClick={download}>{busy ? 'Preparing CSV…' : error ? 'Retry CSV export' : 'Export CSV'}</button>
    {error && <p className="export-message error" role="alert">{error}</p>}
    {notice && <p className="export-message" role="status">{notice}</p>}
  </div>
}
