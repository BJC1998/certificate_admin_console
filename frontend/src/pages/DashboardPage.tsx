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
        <p>The application shell is ready. Certificate management and bulk issuance will be added in later steps.</p>
        <div className="feature-grid">
          <a className="feature" href="#certificates"><span className="tag">PLANNED</span><h3>Certificates <span aria-hidden="true">↗</span></h3><p>A dedicated place to review and manage certificates.</p></a>
          <a className="feature" href="#bulk-issue"><span className="tag">PLANNED</span><h3>Bulk Issue <span aria-hidden="true">↗</span></h3><p>A workspace for issuing course certificates in a batch.</p></a>
        </div>
      </section>
    </>
  )
}
