import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { getCertificates, getTenants, exportCertificates } from '../api/certificates'
import { CertificatesPage } from '../pages/CertificatesPage'
import { certificatePage, deferred, tenants } from './fixtures'
import type { CertificatePage } from '../types/certificates'

vi.mock('../api/certificates', () => ({ getCertificates: vi.fn(), getTenants: vi.fn(), exportCertificates: vi.fn() }))

beforeEach(() => {
  vi.mocked(getTenants).mockResolvedValue(tenants)
  vi.mocked(getCertificates).mockImplementation(async (query) => {
    const page = certificatePage(query.tenantId ?? 1, query.page)
    page.page_size = query.pageSize
    page.total_pages = Math.ceil(page.total / query.pageSize)
    page.records = page.records.map((row) => ({ ...row, status: query.status ?? row.status }))
    return page
  })
})

describe('certificate list', () => {
  it('shows loading until the API returns, then renders the record and detail link', async () => {
    const pending = deferred<CertificatePage>()
    vi.mocked(getCertificates).mockReturnValue(pending.promise)
    render(<CertificatesPage />)
    expect(await screen.findByText('Loading certificates…')).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    await act(async () => { pending.resolve(certificatePage()) })
    expect(await screen.findByRole('link', { name: 'View certificate SYDNEY-1' })).toHaveAttribute('href', '#certificates/1/101')
  })

  it('shows an explicit empty state without a table', async () => {
    vi.mocked(getCertificates).mockResolvedValue({ ...certificatePage(), records: [], total: 0, total_pages: 0 })
    render(<CertificatesPage />)
    expect(await screen.findByText('No certificates on this page')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('shows errors and successfully retries without changing tenant', async () => {
    vi.mocked(getCertificates).mockRejectedValueOnce(new Error('API unavailable'))
    const user = userEvent.setup()
    render(<CertificatesPage />)
    expect(await screen.findByRole('alert')).toHaveTextContent('API unavailable')
    await user.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByRole('link', { name: 'View certificate SYDNEY-1' })).toBeInTheDocument()
    expect(getCertificates).toHaveBeenLastCalledWith(expect.objectContaining({ tenantId: 1 }), expect.any(AbortSignal))
  })

  it('submits search and resets pagination from page two', async () => {
    const user = userEvent.setup()
    render(<CertificatesPage />)
    await screen.findByRole('link', { name: 'View certificate SYDNEY-1' })
    await user.click(screen.getByRole('button', { name: 'Next' }))
    await screen.findByRole('link', { name: 'View certificate SYDNEY-2' })
    await user.type(screen.getByLabelText('Learner name or serial number'), 'Sydney Learner 01{Enter}')
    await waitFor(() => expect(getCertificates).toHaveBeenLastCalledWith(
      expect.objectContaining({ search: 'Sydney Learner 01', page: 1, tenantId: 1 }), expect.any(AbortSignal)))
    await screen.findByRole('link', { name: 'View certificate SYDNEY-1' })
    await user.click(screen.getByRole('button', { name: 'Clear' }))
    await waitFor(() => expect(getCertificates).toHaveBeenLastCalledWith(expect.objectContaining({ search: '', page: 1 }), expect.any(AbortSignal)))
  })

  it('ignores a late Sydney response after switching to Perth, even if fetch ignores abort', async () => {
    const oldResponse = deferred<CertificatePage>()
    vi.mocked(getCertificates).mockImplementation((query) => query.tenantId === 1 ? oldResponse.promise : Promise.resolve(certificatePage(2)))
    const user = userEvent.setup()
    render(<CertificatesPage />)
    await waitFor(() => expect(getCertificates).toHaveBeenCalledWith(expect.objectContaining({ tenantId: 1 }), expect.any(AbortSignal)))
    const oldSignal = vi.mocked(getCertificates).mock.calls[0][1]
    await user.selectOptions(screen.getByLabelText('Tenant', { exact: true }), '2')
    expect(await screen.findByRole('link', { name: 'View certificate PERTH-1' })).toBeInTheDocument()
    expect(oldSignal.aborted).toBe(true)
    await act(async () => { oldResponse.resolve(certificatePage(1)) })
    expect(screen.queryByText('Sydney Learner 01')).not.toBeInTheDocument()
    expect(screen.getByText('Perth Learner 01')).toBeInTheDocument()
    expect(getCertificates).toHaveBeenLastCalledWith(expect.objectContaining({ tenantId: 2, page: 1 }), expect.any(AbortSignal))
  })

  it('toggles sorting and applies status/local-date filters with page reset', async () => {
    const user = userEvent.setup()
    render(<CertificatesPage />)
    await screen.findByRole('link', { name: 'View certificate SYDNEY-1' })
    await user.click(screen.getByRole('button', { name: 'Sort by learner' }))
    await waitFor(() => expect(getCertificates).toHaveBeenLastCalledWith(expect.objectContaining({ sortBy: 'learner_name', sortOrder: 'asc' }), expect.any(AbortSignal)))
    await screen.findByRole('table')
    await user.click(screen.getByRole('button', { name: 'Sort by learner' }))
    await waitFor(() => expect(getCertificates).toHaveBeenLastCalledWith(expect.objectContaining({ sortOrder: 'desc' }), expect.any(AbortSignal)))
    await user.selectOptions(screen.getByLabelText('Status', { exact: true }), 'revoked')
    await user.selectOptions(screen.getByLabelText('Date ordering'), 'issue_date')
    await waitFor(() => expect(getCertificates).toHaveBeenLastCalledWith(expect.objectContaining({ status: 'revoked', sortBy: 'issue_date', page: 1 }), expect.any(AbortSignal)))
  })

  it('passes applied tenant/search/status/sort conditions to export', async () => {
    vi.mocked(exportCertificates).mockRejectedValue(new Error('Test download rejection'))
    const user = userEvent.setup()
    render(<CertificatesPage />)
    await screen.findByRole('link', { name: 'View certificate SYDNEY-1' })
    await user.selectOptions(screen.getByLabelText('Tenant', { exact: true }), '2')
    await screen.findByRole('link', { name: 'View certificate PERTH-1' })
    await user.type(screen.getByLabelText('Learner name or serial number'), 'Perth Learner{Enter}')
    await user.selectOptions(screen.getByLabelText('Status', { exact: true }), 'revoked')
    await user.selectOptions(screen.getByLabelText('Date ordering'), 'issue_date')
    await user.click(screen.getByRole('button', { name: 'Export CSV' }))
    await screen.findByText('Test download rejection')
    expect(exportCertificates).toHaveBeenCalledWith(expect.objectContaining({
      tenantId: 2, search: 'Perth Learner', status: 'revoked', sortBy: 'issue_date', sortOrder: 'desc',
    }), expect.any(AbortSignal))
  })
})
