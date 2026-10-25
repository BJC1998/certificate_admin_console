import { useEffect, useState } from 'react'
import { API_BASE_URL, getHealth } from '../api/health'
import type { ConnectionState } from '../types/health'

export function HealthStatus() {
  const [connection, setConnection] = useState<ConnectionState>({ status: 'checking' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    let active = true
    const timeout = window.setTimeout(() => controller.abort(), 8000)
    setConnection({ status: 'checking' })

    getHealth(controller.signal)
      .then(() => {
        if (active) setConnection({ status: 'connected' })
      })
      .catch((error: unknown) => {
        if (active) {
          setConnection({
            status: 'error',
            message: controller.signal.aborted
              ? 'The health check timed out. Check that the backend is running.'
              : error instanceof Error ? error.message : 'Could not connect to the backend.',
          })
        }
      })
      .finally(() => window.clearTimeout(timeout))

    return () => {
      active = false
      window.clearTimeout(timeout)
      controller.abort()
    }
  }, [attempt])

  const label = connection.status === 'connected' ? 'Connected'
    : connection.status === 'checking' ? 'Checking connection…' : 'Connection unavailable'

  return (
    <section className="card health-card" aria-labelledby="health-title">
      <div className="card-heading">
        <div><p className="eyebrow">SERVICE STATUS</p><h2 id="health-title">Backend connection</h2></div>
        <span className={`status ${connection.status}`} role="status" aria-live="polite">{label}</span>
      </div>
      <p>The console checks the API when this page opens. Recheck to refresh its status.</p>
      <code>{API_BASE_URL}/health</code>
      {connection.status === 'error' && <p className="error" role="alert">{connection.message}</p>}
      <div className="card-footer">
        <span>Application health · GET /health</span>
        <button disabled={connection.status === 'checking'} onClick={() => setAttempt((value) => value + 1)}>
          Recheck connection
        </button>
      </div>
    </section>
  )
}
