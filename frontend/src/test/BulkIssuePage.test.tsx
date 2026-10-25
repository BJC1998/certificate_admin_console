import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { getCertificates, getTenants } from '../api/certificates'
import { getCourses, issueCertificates } from '../api/issuance'
import { BulkIssuePage } from '../pages/BulkIssuePage'
import type { IssueSummary } from '../types/issuance'
import { certificatePage, deferred, issueSummary, tenants } from './fixtures'

vi.mock('../api/certificates', () => ({ getTenants: vi.fn(), getCertificates: vi.fn() }))
vi.mock('../api/issuance', () => ({ getCourses: vi.fn(), issueCertificates: vi.fn() }))

beforeEach(() => {
  vi.mocked(getTenants).mockResolvedValue(tenants)
  vi.mocked(getCourses).mockImplementation(async (tenantId) => [{ id: tenantId * 10, tenant_id: tenantId, title: `${tenantId === 1 ? 'Sydney' : 'Perth'} Safety` }])
  vi.mocked(getCertificates).mockResolvedValue(certificatePage())
})

describe('bulk issuance', () => {
  it('disables duplicate submission and selectors while pending, then displays all outcome categories and refreshes records', async () => {
    const pending = deferred<IssueSummary>()
    vi.mocked(issueCertificates).mockReturnValue(pending.promise)
    const user = userEvent.setup()
    render(<BulkIssuePage initialTenantId={null} onTenantChange={vi.fn()} />)
    await screen.findByRole('option', { name: 'Sydney Safety' })
    const button = screen.getByRole('button', { name: 'Bulk Issue' })
    await user.dblClick(button)
    expect(issueCertificates).toHaveBeenCalledTimes(1)
    expect(button).toBeDisabled()
    expect(screen.getByLabelText('Tenant', { exact: true })).toBeDisabled()
    expect(screen.getByLabelText('Course', { exact: true })).toBeDisabled()
    expect(screen.getByRole('status')).toHaveTextContent('Processing enrolled learners')
    expect(screen.getByRole('status')).not.toHaveTextContent('%')
    await act(async () => { pending.resolve(issueSummary) })
    const results = await screen.findByRole('region', { name: 'Issuance results' })
    expect(within(results).getByRole('status')).toHaveTextContent(/2\s*Issued/)
    expect(within(results).getByRole('status')).toHaveTextContent(/3\s*Skipped/)
    expect(within(results).getByRole('status')).toHaveTextContent(/1\s*Failed/)
    expect(within(results).getAllByRole('row')).toHaveLength(7)
    expect(within(results).getByText('Previously revoked; kept unchanged')).toBeInTheDocument()
    expect(within(results).getByText('Enrollment is not completed')).toBeInTheDocument()
    expect(within(results).getByText('Database busy; safe to retry')).toBeInTheDocument()
    expect(await screen.findByText(/Certificate register refreshed: 21 records for Sydney/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry safely' })).toBeEnabled()
    expect(issueCertificates).toHaveBeenCalledWith(1, 10, expect.any(AbortSignal))
  })

  it('explains unknown network outcomes and safely retries the same course', async () => {
    vi.mocked(issueCertificates).mockRejectedValueOnce(new TypeError('Network lost')).mockResolvedValue({
      ...issueSummary, issued: 0, skipped: 6, failed: 0,
      results: issueSummary.results.map((row) => ({ ...row, outcome: 'skipped', reason: 'already_issued' })),
    })
    const user = userEvent.setup()
    render(<BulkIssuePage initialTenantId={1} onTenantChange={vi.fn()} />)
    await screen.findByRole('option', { name: 'Sydney Safety' })
    await user.click(screen.getByRole('button', { name: 'Bulk Issue' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('The server may already have processed some or all learners')
    await user.click(screen.getByRole('button', { name: 'Safe retry' }))
    const results = await screen.findByRole('region', { name: 'Issuance results' })
    expect(within(results).getByRole('status')).toHaveTextContent(/0\s*Issued/)
    await waitFor(() => expect(screen.queryByText('Network lost')).not.toBeInTheDocument())
    expect(issueCertificates).toHaveBeenCalledTimes(2)
    expect(vi.mocked(issueCertificates).mock.calls.map((args) => args.slice(0, 2))).toEqual([[1, 10], [1, 10]])
  })

  it('loads only the newly selected tenant courses before allowing issuance', async () => {
    const user = userEvent.setup()
    render(<BulkIssuePage initialTenantId={1} onTenantChange={vi.fn()} />)
    await screen.findByRole('option', { name: 'Sydney Safety' })
    await user.selectOptions(screen.getByLabelText('Tenant', { exact: true }), '2')
    expect(await screen.findByRole('option', { name: 'Perth Safety' })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'Sydney Safety' })).not.toBeInTheDocument()
    vi.mocked(issueCertificates).mockRejectedValue(new Error('Expected test stop'))
    await user.click(screen.getByRole('button', { name: 'Bulk Issue' }))
    await screen.findByRole('alert')
    expect(issueCertificates).toHaveBeenCalledWith(2, 20, expect.any(AbortSignal))
  })
})
