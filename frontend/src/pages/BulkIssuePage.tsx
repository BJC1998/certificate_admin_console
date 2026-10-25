import { useEffect, useRef, useState } from 'react'
import { getCertificates, getTenants } from '../api/certificates'
import { getCourses, issueCertificates } from '../api/issuance'
import { IssuanceResults } from '../components/IssuanceResults'
import type { LoadState, TenantOption } from '../types/certificates'
import type { CourseOption, IssueSummary } from '../types/issuance'

export function BulkIssuePage({ initialTenantId, onTenantChange }: {
  initialTenantId: number | null; onTenantChange: (id: number | null) => void
}) {
  const [tenants, setTenants] = useState<LoadState<TenantOption[]>>({ status: 'loading' })
  const [tenantId, setTenantId] = useState(initialTenantId)
  const [tenantAttempt, setTenantAttempt] = useState(0)
  const [courses, setCourses] = useState<{ tenantId: number | null; state: LoadState<CourseOption[]> }>({ tenantId: null, state: { status: 'loading' } })
  const [courseId, setCourseId] = useState<number | null>(null)
  const [courseAttempt, setCourseAttempt] = useState(0)
  const [busy, setBusy] = useState(false)
  const [phase, setPhase] = useState('Processing enrolled learners…')
  const [result, setResult] = useState<IssueSummary | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [register, setRegister] = useState<LoadState<number> | null>(null)
  const submitting = useRef(false)
  const mounted = useRef(true)
  const activeRequest = useRef<AbortController | null>(null)

  useEffect(() => { mounted.current = true; return () => { mounted.current = false; activeRequest.current?.abort() } }, [])

  useEffect(() => {
    let active = true
    const controller = new AbortController()
    const timeout = window.setTimeout(() => controller.abort(), 10000)
    setTenants({ status: 'loading' })
    getTenants(controller.signal).then((data) => {
      if (!active) return
      setTenants({ status: 'success', data })
      const selected = data.some((row) => row.id === initialTenantId) ? initialTenantId : data[0]?.id ?? null
      setTenantId(selected)
      onTenantChange(selected)
    }).catch((reason: unknown) => {
      if (active) setTenants({ status: 'error', message: reason instanceof Error ? reason.message : 'Could not load tenants.' })
    }).finally(() => window.clearTimeout(timeout))
    return () => { active = false; controller.abort(); window.clearTimeout(timeout) }
  }, [tenantAttempt])

  useEffect(() => {
    if (tenantId === null) return
    let active = true
    const controller = new AbortController()
    const timeout = window.setTimeout(() => controller.abort(), 10000)
    setCourses({ tenantId, state: { status: 'loading' } })
    getCourses(tenantId, controller.signal).then((data) => {
      if (active) { setCourses({ tenantId, state: { status: 'success', data } }); setCourseId(data[0]?.id ?? null) }
    }).catch((reason: unknown) => {
      if (active) setCourses({ tenantId, state: { status: 'error', message: reason instanceof Error ? reason.message : 'Could not load courses.' } })
    }).finally(() => window.clearTimeout(timeout))
    return () => { active = false; controller.abort(); window.clearTimeout(timeout) }
  }, [tenantId, courseAttempt])

  const courseState: LoadState<CourseOption[]> = courses.tenantId === tenantId ? courses.state : { status: 'loading' }
  const tenant = tenants.status === 'success' ? tenants.data.find((row) => row.id === tenantId) : undefined
  const course = courseState.status === 'success' ? courseState.data.find((row) => row.id === courseId) : undefined
  const canIssue = !busy && tenant && course && tenants.status === 'success'

  function clearResult() { setResult(null); setError(null); setRegister(null) }

  async function refreshRegister(id: number) {
    setRegister({ status: 'loading' })
    const controller = new AbortController()
    activeRequest.current = controller
    const timeout = window.setTimeout(() => controller.abort(), 10000)
    try {
      const page = await getCertificates({ tenantId: id, page: 1, pageSize: 1, search: '', sortBy: 'issued_at', sortOrder: 'desc' }, controller.signal)
      if (mounted.current) setRegister({ status: 'success', data: page.total })
    } catch {
      if (mounted.current) setRegister({ status: 'error', message: 'The issuance response was received, but the certificate register could not be refreshed. Open Certificates to reload it.' })
    } finally { window.clearTimeout(timeout) }
  }

  async function issue() {
    // Synchronous guard also protects the interval before React renders the disabled button.
    if (submitting.current || !canIssue || tenantId === null || courseId === null) return
    submitting.current = true
    setBusy(true); clearResult(); setPhase('Processing enrolled learners…')
    const controller = new AbortController()
    activeRequest.current = controller
    const timeout = window.setTimeout(() => controller.abort(), 60000)
    try {
      const summary = await issueCertificates(tenantId, courseId, controller.signal)
      window.clearTimeout(timeout)
      if (!mounted.current) return
      setResult(summary)
      setPhase('Refreshing certificate register…')
      await refreshRegister(tenantId)
    } catch (reason: unknown) {
      if (mounted.current) setError(controller.signal.aborted ? 'The request timed out before a response was confirmed.'
        : reason instanceof Error ? reason.message : 'The response could not be confirmed.')
    } finally {
      window.clearTimeout(timeout)
      submitting.current = false
      if (mounted.current) setBusy(false)
    }
  }

  return (
    <>
      <header className="page-heading certificate-heading"><div><p className="eyebrow">CERTIFICATE WORKSPACE</p><h1>Bulk Issue</h1><p>Issue completion certificates for a course in one action.</p></div></header>
      <p className="demo-context">Demo tenant selection · issuance actor is demo-admin-{tenantId ?? 'tenant'} · no authentication</p>
      <section className="card" aria-labelledby="issue-title"><h2 id="issue-title">Select a course</h2>
        <p>Only completed enrollments receive a new certificate. Existing certificates, including revoked certificates, are always skipped.</p>
        <div className="bulk-controls">
          <div className="tenant-control"><label htmlFor="issue-tenant">Tenant</label><select id="issue-tenant" value={tenantId ?? ''}
            disabled={busy || tenants.status !== 'success' || !tenants.data.length} onChange={(event) => {
              const selected = Number(event.target.value); setTenantId(selected); onTenantChange(selected); setCourseId(null); clearResult()
            }}>
            {tenants.status === 'success' && tenants.data.length ? tenants.data.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)
              : <option value="">{tenants.status === 'loading' ? 'Loading tenants…' : 'No tenants available'}</option>}</select></div>
          <div className="tenant-control course-control"><label htmlFor="issue-course">Course</label><select id="issue-course" value={courseId ?? ''}
            disabled={busy || courseState.status !== 'success' || !courseState.data.length} onChange={(event) => { setCourseId(Number(event.target.value)); clearResult() }}>
            {courseState.status === 'success' && courseState.data.length ? courseState.data.map((row) => <option key={row.id} value={row.id}>{row.title}</option>)
              : <option value="">{courseState.status === 'loading' ? 'Loading courses…' : 'No courses available'}</option>}</select></div>
          <button className="primary-button" disabled={!canIssue} onClick={issue}>Bulk Issue</button>
        </div>
        {tenants.status === 'error' && <div className="error" role="alert"><p>{tenants.message}</p><button onClick={() => setTenantAttempt((value) => value + 1)}>Retry loading tenants</button></div>}
        {tenants.status === 'success' && !tenants.data.length && <p role="status">No tenants available. Initialize and seed the demo database.</p>}
        {tenantId !== null && courseState.status === 'error' && <div className="error" role="alert"><p>{courseState.message}</p><button onClick={() => setCourseAttempt((value) => value + 1)}>Retry loading courses</button></div>}
        {courseState.status === 'success' && !courseState.data.length && <p role="status">This tenant has no courses to issue certificates for.</p>}
        <p className="safe-retry-note">Each learner is committed separately. Leaving this page or losing the connection does not undo committed work. Repeating the operation safely skips certificates already issued.</p>
        {busy && <div className="processing-note" role="status" aria-live="polite"><span className="loading-ring" aria-hidden="true" /><span>{phase} Please wait.</span></div>}
        {error && <div className="issue-error" role="alert"><h3>Issuance response not confirmed</h3><p>{error}</p>
          <p>The server may already have processed some or all learners. A safe retry will skip committed certificates and try the remaining eligible learners.</p>
          <button disabled={busy} onClick={issue}>Safe retry</button></div>}
        {result && !busy && result.failed > 0 && <div className="issue-error"><p>{result.failed} learner operations failed. Successful certificates remain saved.</p><button onClick={issue}>Retry safely</button></div>}
        {register?.status === 'success' && <p className="register-refresh" role="status">Certificate register refreshed: {register.data} records for {tenant?.name}. <a href="#certificates">View certificates →</a></p>}
        {register?.status === 'error' && <p className="error" role="alert">{register.message} <a href="#certificates">View certificates →</a></p>}
      </section>
      {result && <IssuanceResults result={result} />}
    </>
  )
}
