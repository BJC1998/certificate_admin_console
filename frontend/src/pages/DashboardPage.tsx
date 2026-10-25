import { HealthStatus } from '../components/HealthStatus'

export function DashboardPage() {
  return (
    <>
      <header className="page-heading"><p className="eyebrow">WORKSPACE OVERVIEW</p><h1>Dashboard</h1>
        <p>Your workspace for managing course completion certificates.</p>
      </header>
      <HealthStatus />
      <section className="card" aria-labelledby="workspace-title">
        <p className="eyebrow">GETTING STARTED</p><h2 id="workspace-title">Workspace foundation</h2>
        <p>Browse certificates by tenant, search learner records, and review certificate status.</p>
        <div className="feature-grid">
          <a className="feature" href="#certificates"><span className="tag">AVAILABLE</span><h3>Certificates <span aria-hidden="true">↗</span></h3><p>Search and review certificates in your tenant workspace.</p></a>
          <a className="feature" href="#bulk-issue"><span className="tag">PLANNED</span><h3>Bulk Issue <span aria-hidden="true">↗</span></h3><p>A workspace for issuing course certificates in a batch.</p></a>
        </div>
      </section>
    </>
  )
}
