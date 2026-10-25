import type { IssueSummary } from '../types/issuance'

const reasons: Record<string, string> = {
  certificate_and_audit_committed: 'Certificate and audit saved',
  already_issued: 'Certificate already exists', previously_revoked: 'Previously revoked; kept unchanged',
  enrollment_incomplete: 'Enrollment is not completed', enrollment_no_longer_available: 'Enrollment is no longer available',
  database_busy_retry_safe: 'Database busy; safe to retry', database_error_retry_safe: 'Database error; safe to retry',
  database_integrity_error_retry_safe: 'Certificate and audit rolled back; safe to retry',
}

export function IssuanceResults({ result }: { result: IssueSummary }) {
  return (
    <section className="card certificate-card" aria-labelledby="issuance-results-title">
      <div className="register-heading"><div><h2 id="issuance-results-title">Issuance results</h2><p>{result.total} enrolled learners checked in this request</p></div></div>
      <div className="issue-summary" role="status" aria-live="polite">
        <div><strong>{result.issued}</strong><span>Issued</span></div><div><strong>{result.skipped}</strong><span>Skipped</span></div><div><strong>{result.failed}</strong><span>Failed</span></div>
      </div>
      {result.total === 0 ? <div className="feedback"><h3>No enrolled learners</h3><p>This course has no enrollments to process.</p></div>
      : <div className="table-scroll" tabIndex={0} role="region" aria-label="Per-learner issuance results">
        <table className="certificate-table"><caption className="sr-only">Individual certificate issuance outcomes</caption>
          <thead><tr><th scope="col">Learner</th><th scope="col">Outcome</th><th scope="col">Reason</th><th scope="col">Serial number</th></tr></thead>
          <tbody>{result.results.map((row) => <tr key={row.learner_id}><td className="learner-cell">{row.learner_name}</td>
            <td><span className={`certificate-status ${row.outcome}`}>{row.outcome}</span></td><td>{reasons[row.reason] ?? row.reason}</td><td className="serial-cell">{row.serial_number ?? '—'}</td></tr>)}</tbody>
        </table>
      </div>}
    </section>
  )
}
