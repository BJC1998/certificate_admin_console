import { useEffect, useState } from 'react'
import { DashboardPage } from './pages/DashboardPage'
import { PlaceholderPage } from './pages/PlaceholderPage'

const navigation = [
  { id: 'dashboard', label: 'Dashboard', icon: '◫' },
  { id: 'certificates', label: 'Certificates', icon: '▤' },
  { id: 'bulk-issue', label: 'Bulk Issue', icon: '⊞' },
] as const

function currentPage() {
  const page = window.location.hash.slice(1)
  return navigation.some((item) => item.id === page) ? page : 'dashboard'
}

export default function App() {
  const [page, setPage] = useState(currentPage)
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
          <a key={item.id} href={`#${item.id}`} className={page === item.id ? 'nav-item active' : 'nav-item'} aria-current={page === item.id ? 'page' : undefined}>
            <span aria-hidden="true">{item.icon}</span>{item.label}
          </a>
        ))}</nav>
        <div className="sidebar-footer"><span className="environment-dot" /> Local development<small>Step 1 · Project foundation</small></div>
      </aside>
      <div className="main-shell">
        <div className="topbar"><span>Certificate Admin Console</span><span className="environment-label">DEVELOPMENT</span></div>
        <main id="main" tabIndex={-1}>
          {page === 'dashboard' ? <DashboardPage /> : <PlaceholderPage title={page === 'certificates' ? 'Certificates' : 'Bulk Issue'} />}
        </main>
        <footer className="app-footer">Ocean AI Labs · Certificate administration</footer>
      </div>
    </div>
  )
}
