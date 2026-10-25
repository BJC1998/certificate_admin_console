import { useEffect, useState } from 'react'
import { DashboardPage } from './pages/DashboardPage'
import { CertificatesPage } from './pages/CertificatesPage'
import { BulkIssuePage } from './pages/BulkIssuePage'
import { CertificateDetailPage } from './pages/CertificateDetailPage'

const navigation = [
  { id: 'dashboard', label: 'Dashboard', icon: '◫' },
  { id: 'certificates', label: 'Certificates', icon: '▤' },
  { id: 'bulk-issue', label: 'Bulk Issue', icon: '⊞' },
] as const

function currentPage() {
  const page = window.location.hash.slice(1)
  const detail = /^certificates\/([1-9]\d*)\/([1-9]\d*)$/.exec(page)
  if (detail && Number.isSafeInteger(Number(detail[1])) && Number.isSafeInteger(Number(detail[2]))) return page
  return navigation.some((item) => item.id === page) ? page : 'dashboard'
}

export default function App() {
  const [page, setPage] = useState(currentPage)
  const [selectedTenantId, setSelectedTenantId] = useState<number | null>(null)
  const detail = /^certificates\/(\d+)\/(\d+)$/.exec(page)
  useEffect(() => {
    const onHashChange = () => setPage(currentPage())
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  return (
    <div className="app-shell">
      <a href="#main" className="skip-link" onClick={(event) => {
        event.preventDefault()
        document.getElementById('main')?.focus()
      }}>Skip to content</a>
      <aside className="sidebar">
        <a href="#dashboard" className="brand"><span className="brand-mark" aria-hidden="true">O</span><span>OCEAN AI LABS<small>Certificate Admin Console</small></span></a>
        <p className="nav-label">WORKSPACE</p>
        <nav aria-label="Main navigation">{navigation.map((item) => (
          <a key={item.id} href={`#${item.id}`} className={page === item.id || (detail && item.id === 'certificates') ? 'nav-item active' : 'nav-item'} aria-current={page === item.id || (detail && item.id === 'certificates') ? 'page' : undefined}>
            <span aria-hidden="true">{item.icon}</span>{item.label}
          </a>
        ))}</nav>
        <div className="sidebar-footer"><span className="environment-dot" /> Local development<small>Demo certificate workspace</small></div>
      </aside>
      <div className="main-shell">
        <div className="topbar"><span>Certificate Admin Console</span><span className="environment-label">DEVELOPMENT</span></div>
        <main id="main" tabIndex={-1}>
          {detail ? <CertificateDetailPage key={`${detail[1]}:${detail[2]}`} tenantId={Number(detail[1])} certificateId={Number(detail[2])} onTenantChange={setSelectedTenantId} />
            : page === 'dashboard' ? <DashboardPage /> : page === 'certificates'
            ? <CertificatesPage initialTenantId={selectedTenantId} onTenantChange={setSelectedTenantId} />
            : <BulkIssuePage initialTenantId={selectedTenantId} onTenantChange={setSelectedTenantId} />}
        </main>
        <footer className="app-footer">Ocean AI Labs · Certificate administration</footer>
      </div>
    </div>
  )
}
