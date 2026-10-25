import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { getTenants } from '../api/certificates'
import { CertificateTable } from '../components/CertificateTable'
import { useCertificates } from '../hooks/useCertificates'
import type { CertificateQuery, LoadState, SortField, TenantOption } from '../types/certificates'

export function CertificatesPage({ initialTenantId = null, onTenantChange }: {
  initialTenantId?: number | null; onTenantChange?: (id: number | null) => void
}) {
  const [tenants, setTenants] = useState<LoadState<TenantOption[]>>({ status: 'loading' })
  const [tenantAttempt, setTenantAttempt] = useState(0)
  const [draft, setDraft] = useState('')
  const [query, setQuery] = useState<CertificateQuery>({ tenantId: initialTenantId, search: '', page: 1, pageSize: 10, sortBy: 'issued_at', sortOrder: 'desc' })
  const { state, retry } = useCertificates(query)

  useEffect(() => {
    let active = true
    const controller = new AbortController()
    const timeout = window.setTimeout(() => controller.abort(), 10000)
    setTenants({ status: 'loading' })
    getTenants(controller.signal).then((data) => {
      if (active) {
        setTenants({ status: 'success', data })
        const selected = data.some((item) => item.id === initialTenantId) ? initialTenantId : data[0]?.id ?? null
        setQuery((previous) => ({ ...previous, tenantId: selected, page: 1 }))
        onTenantChange?.(selected)
      }
    }).catch((error: unknown) => {
      if (active) setTenants({ status: 'error', message: controller.signal.aborted ? 'The tenant request timed out.'
        : error instanceof Error ? error.message : 'Could not load tenants.' })
    }).finally(() => window.clearTimeout(timeout))
    return () => { active = false; window.clearTimeout(timeout); controller.abort() }
  }, [tenantAttempt])

  const selectedTenant = tenants.status === 'success' ? tenants.data.find((item) => item.id === query.tenantId) : undefined
  function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setQuery((previous) => ({ ...previous, search: draft.trim(), page: 1 }))
  }
  function sort(field: SortField) {
    setQuery((previous) => ({ ...previous, page: 1, sortBy: field,
      sortOrder: previous.sortBy === field && previous.sortOrder === 'asc' ? 'desc' : 'asc' }))
  }
  function clearSearch() {
    setDraft('')
    setQuery((previous) => ({ ...previous, search: '', page: 1 }))
  }

  return (
    <>
      <header className="page-heading certificate-heading">
        <div><p className="eyebrow">CERTIFICATE WORKSPACE</p><h1>Certificates</h1><p>Review course completion records for your selected tenant.</p></div>
        <div className="tenant-control"><label htmlFor="tenant">Tenant</label>
          <select id="tenant" value={query.tenantId ?? ''} disabled={tenants.status !== 'success' || !tenants.data.length}
            onChange={(event) => { const selected = Number(event.target.value); setQuery((previous) => ({ ...previous, tenantId: selected, page: 1 })); onTenantChange?.(selected) }}>
            {tenants.status === 'success' && tenants.data.length
              ? tenants.data.map((tenant) => <option key={tenant.id} value={tenant.id}>{tenant.name}</option>)
              : <option value="">{tenants.status === 'loading' ? 'Loading tenants…' : 'No tenant available'}</option>}
          </select>
        </div>
      </header>
      <p className="demo-context">Demo tenant selection · no authentication or membership checks</p>
      {tenants.status === 'error' ? <section className="card feedback" role="alert"><h2>Could not load tenants</h2><p>{tenants.message}</p>
        <button onClick={() => setTenantAttempt((value) => value + 1)}>Retry</button></section>
      : tenants.status === 'success' && !tenants.data.length ? <section className="card feedback"><h2>No tenants available</h2><p>Initialize and seed the demo database to get started.</p></section>
      : <section className="card certificate-card" aria-labelledby="register-title">
        <div className="register-heading"><div><h2 id="register-title">Certificate register</h2><p>{selectedTenant ? `${selectedTenant.name} · Dates in ${selectedTenant.timezone}` : 'Loading tenant information…'}</p></div>
          {state.status === 'success' && <span className="record-count">{state.data.total} {state.data.total === 1 ? 'record' : 'records'}</span>}
        </div>
        <form className="search-toolbar" onSubmit={search} role="search">
          <div className="search-field"><label htmlFor="certificate-search">Learner name or serial number</label>
            <input id="certificate-search" type="search" placeholder="Search certificates…" maxLength={200} value={draft} onChange={(event) => setDraft(event.target.value)} /></div>
          <button type="submit" disabled={query.tenantId === null}>Search</button>
          {(draft || query.search) && <button type="button" onClick={clearSearch}>Clear</button>}
          <div className="page-size-control"><label htmlFor="page-size">Rows per page</label><select id="page-size" value={query.pageSize}
            onChange={(event) => setQuery((previous) => ({ ...previous, pageSize: Number(event.target.value), page: 1 }))}>
            {[10, 25, 50, 100].map((size) => <option key={size} value={size}>{size}</option>)}</select></div>
        </form>
        {state.status === 'loading' ? <div className="feedback" role="status" aria-live="polite"><span className="loading-ring" aria-hidden="true" /><h3>Loading certificates…</h3><p>Fetching records for the selected tenant.</p></div>
        : state.status === 'error' ? <div className="feedback" role="alert"><h3>Could not load certificates</h3><p>{state.message}</p><button onClick={retry}>Retry</button></div>
        : <>
          {!state.data.records.length ? <div className="feedback" role="status"><h3>{query.search ? 'No matching certificates' : 'No certificates on this page'}</h3>
            <p>{query.search ? `No results for “${query.search}” in ${selectedTenant?.name}. Try another name or serial number.` : 'This tenant has no records on the requested page.'}</p>
            {query.search && <button onClick={clearSearch}>Clear search</button>}</div>
          : <CertificateTable data={state.data} sortBy={query.sortBy} sortOrder={query.sortOrder} onSort={sort} />}
          <nav className="pagination" aria-label="Certificate pagination">
            <span role="status" aria-live="polite">{!state.data.records.length ? `0 of ${state.data.total} records on this page` : `${(state.data.page - 1) * state.data.page_size + 1}–${(state.data.page - 1) * state.data.page_size + state.data.records.length} of ${state.data.total}`}</span>
            <div><button disabled={query.page <= 1} onClick={() => setQuery((previous) => ({ ...previous, page: previous.page - 1 }))}>Previous</button>
              <span>{state.data.total_pages ? `Page ${query.page} of ${state.data.total_pages}` : 'No pages'}</span>
              <button disabled={query.page >= state.data.total_pages} onClick={() => setQuery((previous) => ({ ...previous, page: previous.page + 1 }))}>Next</button></div>
          </nav>
        </>}
      </section>}
    </>
  )
}
