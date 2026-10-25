import { useEffect, useRef, useState } from 'react'
import { getCertificate, revokeCertificate } from '../api/certificates'
import { RevokeConfirmation } from '../components/RevokeConfirmation'
import type { CertificateDetail, LoadState } from '../types/certificates'

export function CertificateDetailPage({ tenantId, certificateId, onTenantChange }: {
  tenantId: number; certificateId: number; onTenantChange: (id: number | null) => void
}) {
  const key = `${tenantId}:${certificateId}`
  const [result, setResult] = useState<{ key: string; state: LoadState<CertificateDetail> }>({ key, state: { status: 'loading' } })
  const [attempt, setAttempt] = useState(0)
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [mutationError, setMutationError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const mounted = useRef(true)
  const submitting = useRef(false)
  const mutation = useRef<AbortController | null>(null)

  useEffect(() => { mounted.current = true; return () => { mounted.current = false; mutation.current?.abort() } }, [])
  useEffect(() => {
    let active = true
    const controller = new AbortController()
    const timeout = window.setTimeout(() => controller.abort(), 10000)
    setResult({ key, state: { status: 'loading' } })
    getCertificate(tenantId, certificateId, controller.signal).then((data) => {
      if (active) { setResult({ key, state: { status: 'success', data } }); onTenantChange(tenantId); setMutationError(null) }
    }).catch((reason: unknown) => {
      if (active) setResult({ key, state: { status: 'error', message: controller.signal.aborted ? 'The detail request timed out.'
        : reason instanceof Error ? reason.message : 'Could not load this certificate.' } })
    }).finally(() => window.clearTimeout(timeout))
    return () => { active = false; controller.abort(); window.clearTimeout(timeout) }
  }, [tenantId, certificateId, key, attempt, onTenantChange])

  const state: LoadState<CertificateDetail> = result.key === key ? result.state : { status: 'loading' }

  async function confirmRevoke() {
    if (submitting.current || !confirming || state.status !== 'success' || state.data.status !== 'valid') return
    submitting.current = true; setBusy(true); setMutationError(null); setNotice(null)
    const controller = new AbortController()
    mutation.current = controller
    const timeout = window.setTimeout(() => controller.abort(), 30000)
    try {
      const response = await revokeCertificate(tenantId, certificateId, controller.signal)
      if (mounted.current) {
        setResult({ key, state: { status: 'success', data: response.certificate } })
        setNotice(response.changed ? 'Certificate revoked. The original certificate and audit history have been preserved.'
          : 'This certificate was already revoked. No additional revocation entry was created.')
      }
    } catch (reason: unknown) {
      if (mounted.current) setMutationError(`${reason instanceof Error ? reason.message : 'No response was confirmed.'} The server may already have revoked this certificate. Reload its status before retrying; repeated revocation is safe.`)
    } finally {
      window.clearTimeout(timeout); submitting.current = false
      if (mounted.current) { setBusy(false); setConfirming(false) }
    }
  }

  return <>
    <a className="text-link detail-back" href="#certificates">← Back to certificates</a>
    <header className="page-heading"><p className="eyebrow">CERTIFICATE WORKSPACE</p><h1>Certificate details</h1><p>Review the original issue record and current certificate status.</p></header>
    {state.status === 'loading' ? <section className="card feedback" role="status"><span className="loading-ring" aria-hidden="true" /><h2>Loading certificate…</h2></section>
    : state.status === 'error' ? <section className="card feedback" role="alert"><h2>Could not load certificate</h2><p>{state.message}</p><p>The record may be unavailable in the selected tenant.</p><button onClick={() => setAttempt((value) => value + 1)}>Retry</button></section>
    : <>
      <p className="demo-context">{state.data.tenant_name} · Demo tenant selection, not authentication</p>
      {notice && <p className="success-notice" role="status">{notice}</p>}
      {mutationError && <div className="issue-error" role="alert"><h2>Revocation response not confirmed</h2><p>{mutationError}</p><button disabled={busy} onClick={() => setAttempt((value) => value + 1)}>Reload certificate</button></div>}
      <section className="card" aria-labelledby="certificate-record-title">
        <div className="card-heading"><h2 id="certificate-record-title">Certificate record</h2><span className={`certificate-status ${state.data.status}`}>{state.data.status === 'valid' ? 'Valid' : 'Revoked'}</span></div>
        <dl className="detail-grid">
          <div><dt>Serial number</dt><dd className="detail-serial">{state.data.serial_number}</dd></div>
          <div><dt>Learner</dt><dd>{state.data.learner_name}</dd></div>
          <div><dt>Course</dt><dd>{state.data.course_title}</dd></div>
          <div><dt>Tenant</dt><dd>{state.data.tenant_name}</dd></div>
          <div><dt>Issue date</dt><dd><time dateTime={state.data.issued_at}>{new Intl.DateTimeFormat('en-AU', {
            timeZone: state.data.tenant_timezone, year: 'numeric', month: 'long', day: '2-digit',
            hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
          }).format(new Date(state.data.issued_at))}</time><small>{state.data.tenant_timezone} · {state.data.issued_at}</small></dd></div>
          <div><dt>Status</dt><dd>{state.data.status === 'valid' ? 'Valid' : 'Revoked'}</dd></div>
        </dl>
      </section>
      {state.data.status === 'valid' ? <section className="card revoke-section"><div><h2>Revoke certificate</h2><p>Mark this certificate as revoked. The serial number, original issue date and historical record remain unchanged.</p></div>
        <button className="danger-button" disabled={busy} onClick={() => setConfirming(true)}>Revoke certificate</button></section>
      : <section className="card"><h2>This certificate has been revoked</h2><p>The original record remains available here. Bulk Issue will skip this certificate and cannot recreate or reactivate it.</p></section>}
      {confirming && state.data.status === 'valid' && <RevokeConfirmation serial={state.data.serial_number} learner={state.data.learner_name} busy={busy}
        onCancel={() => { if (!submitting.current) setConfirming(false) }} onConfirm={confirmRevoke} />}
    </>}
  </>
}
