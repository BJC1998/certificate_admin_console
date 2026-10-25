import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { exportCertificates } from '../api/certificates'
import { ExportCSVButton } from '../components/ExportCSVButton'
import { deferred, query } from './fixtures'

const csv = 'Learner Name,Course Title,Serial Number,Issue Date\r\nPerth Learner,Safety,PERTH-1,2026-10-04T00:00:00+08:00\r\n'
function response() {
  return new Response(csv, { headers: { 'content-type': 'text/csv; charset=utf-8',
    'content-disposition': 'attachment; filename="certificates-perth-filtered.csv"',
    'content-length': String(new TextEncoder().encode(csv).byteLength) } })
}

beforeEach(() => {
  Object.defineProperty(URL, 'createObjectURL', { configurable: true, writable: true, value: vi.fn(() => 'blob:test-csv') })
  Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, writable: true, value: vi.fn() })
  // Capture the download intent; jsdom does not save files or run browser navigation.
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
})

describe('CSV export', () => {
  it('serializes selected tenant and current filters/sort, excluding page and page_size', async () => {
    const fetchMock = vi.fn().mockResolvedValue(response())
    vi.stubGlobal('fetch', fetchMock)
    const result = await exportCertificates(query, new AbortController().signal)
    const [address, options] = fetchMock.mock.calls[0]
    const url = new URL(address)
    expect(url.pathname).toBe('/api/tenants/2/certificates/export')
    expect(Object.fromEntries(url.searchParams)).toEqual({ search: 'Perth Learner', status: 'revoked', sort_by: 'issue_date', sort_order: 'asc' })
    expect(options.headers).toEqual({ 'X-Tenant-ID': '2' })
    expect(result.filename).toBe('certificates-perth-filtered.csv')
    expect(result.blob.size).toBe(new TextEncoder().encode(csv).byteLength)
  })

  it('disables duplicate export while pending and starts download with server filename', async () => {
    const pending = deferred<Response>()
    const fetchMock = vi.fn().mockReturnValue(pending.promise)
    vi.stubGlobal('fetch', fetchMock)
    const user = userEvent.setup()
    render(<ExportCSVButton query={query} disabled={false} />)
    await user.dblClick(screen.getByRole('button', { name: 'Export CSV' }))
    expect(screen.getByRole('button', { name: 'Preparing CSV…' })).toBeDisabled()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    await act(async () => { pending.resolve(response()) })
    expect(await screen.findByRole('status')).toHaveTextContent('Download started: certificates-perth-filtered.csv')
    expect(HTMLAnchorElement.prototype.click).toHaveBeenCalledTimes(1)
    const link = vi.mocked(HTMLAnchorElement.prototype.click).mock.instances[0]
    expect(link).toHaveAttribute('download', 'certificates-perth-filtered.csv')
  })

  it('shows download errors and retries without starting a failed download', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(new Response('Unavailable', { status: 503 })).mockResolvedValueOnce(response())
    vi.stubGlobal('fetch', fetchMock)
    const user = userEvent.setup()
    render(<ExportCSVButton query={query} disabled={false} />)
    await user.click(screen.getByRole('button', { name: 'Export CSV' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('HTTP 503')
    expect(HTMLAnchorElement.prototype.click).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Retry CSV export' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Download started:')
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('aborts an obsolete export and ignores its late response after unmount', async () => {
    const pending = deferred<Response>()
    const fetchMock = vi.fn().mockReturnValue(pending.promise)
    vi.stubGlobal('fetch', fetchMock)
    const user = userEvent.setup()
    const view = render(<ExportCSVButton query={query} disabled={false} />)
    await user.click(screen.getByRole('button', { name: 'Export CSV' }))
    const signal = fetchMock.mock.calls[0][1].signal as AbortSignal
    view.unmount()
    expect(signal.aborted).toBe(true)
    await act(async () => { pending.resolve(response()) })
    expect(HTMLAnchorElement.prototype.click).not.toHaveBeenCalled()
  })

  it.each([
    { name: 'wrong MIME type', create: () => new Response('{}', { headers: { 'content-type': 'application/json' } }), message: 'did not return a CSV' },
    { name: 'incomplete file', create: () => new Response(csv, { headers: { 'content-type': 'text/csv', 'content-length': '9999' } }), message: 'incomplete' },
  ])('rejects $name instead of accepting a corrupt download', async ({ create, message }) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(create()))
    await expect(exportCertificates(query, new AbortController().signal)).rejects.toThrow(message)
  })

  it('never exports without a selected tenant', async () => {
    render(<ExportCSVButton query={{ ...query, tenantId: null }} disabled />)
    expect(screen.getByRole('button', { name: 'Export CSV' })).toBeDisabled()
    await expect(exportCertificates({ ...query, tenantId: null }, new AbortController().signal)).rejects.toThrow('Select a tenant')
    await waitFor(() => expect(fetch).not.toHaveBeenCalled())
  })
})
