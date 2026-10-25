import { useEffect, useState } from 'react'
import { getCertificates } from '../api/certificates'
import type { CertificatePage, CertificateQuery, LoadState } from '../types/certificates'

export function useCertificates(query: CertificateQuery) {
  const key = JSON.stringify(query)
  const [attempt, setAttempt] = useState(0)
  const [result, setResult] = useState<{ key: string; state: LoadState<CertificatePage> }>({ key, state: { status: 'loading' } })

  useEffect(() => {
    if (query.tenantId === null) return
    let active = true
    const controller = new AbortController()
    const timeout = window.setTimeout(() => controller.abort(), 10000)
    setResult({ key, state: { status: 'loading' } })
    getCertificates(query, controller.signal)
      .then((data) => { if (active) setResult({ key, state: { status: 'success', data } }) })
      .catch((error: unknown) => {
        if (active) setResult({ key, state: { status: 'error', message: controller.signal.aborted
          ? 'The request timed out. Please try again.'
          : error instanceof Error ? error.message : 'Could not reach the API.' } })
      })
      .finally(() => window.clearTimeout(timeout))
    return () => { active = false; window.clearTimeout(timeout); controller.abort() }
    // key contains every query field; callers may create a new object on each render.
  }, [key, attempt])

  // Hide old tenant/search rows immediately, before the new effect runs.
  const state: LoadState<CertificatePage> = result.key === key ? result.state : { status: 'loading' }
  return { state, retry: () => setAttempt((value) => value + 1) }
}
