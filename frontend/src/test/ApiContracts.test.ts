import { describe, expect, it, vi } from 'vitest'
import { getCertificate, getCertificates, revokeCertificate } from '../api/certificates'
import { getCourses, issueCertificates } from '../api/issuance'
import { certificatePage, detail, issueSummary, query } from './fixtures'

describe('real API clients with isolated fetch responses', () => {
  it('sends list filters/pagination and matching selected tenant header', async () => {
    const fetchMock = vi.fn().mockResolvedValue(Response.json(certificatePage(2, 2)))
    vi.stubGlobal('fetch', fetchMock)
    const result = await getCertificates({ ...query, page: 2 }, new AbortController().signal)
    const [address, options] = fetchMock.mock.calls[0]
    const url = new URL(address)
    expect(url.pathname).toBe('/api/tenants/2/certificates')
    expect(Object.fromEntries(url.searchParams)).toEqual({ search: 'Perth Learner', status: 'revoked',
      page: '2', page_size: '10', sort_by: 'issue_date', sort_order: 'asc' })
    expect(options.headers).toEqual({ 'X-Tenant-ID': '2' })
    expect(result.tenant_id).toBe(2)
  })

  it.each(['response tenant', 'record tenant'])('rejects an unexpected %s instead of displaying foreign records', async (mismatch) => {
    const payload = certificatePage(1)
    if (mismatch === 'response tenant') payload.tenant_id = 2
    else payload.records[0].tenant_id = 2
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json(payload)))
    await expect(getCertificates({ ...query, tenantId: 1, page: 1 }, new AbortController().signal)).rejects.toThrow('invalid certificate response')
  })

  it('uses tenant-scoped detail/revoke routes and requires a confirmed revoked response', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(Response.json(detail))
      .mockResolvedValueOnce(Response.json({ certificate: { ...detail, status: 'revoked' }, changed: true }))
    vi.stubGlobal('fetch', fetchMock)
    const signal = new AbortController().signal
    expect(await getCertificate(1, 1, signal)).toEqual(detail)
    expect((await revokeCertificate(1, 1, signal)).certificate.status).toBe('revoked')
    expect(new URL(fetchMock.mock.calls[0][0]).pathname).toBe('/api/tenants/1/certificates/1')
    expect(fetchMock.mock.calls[0][1]).toEqual(expect.objectContaining({ method: 'GET', headers: { 'X-Tenant-ID': '1' }, signal }))
    expect(new URL(fetchMock.mock.calls[1][0]).pathname).toBe('/api/tenants/1/certificates/1/revoke')
    expect(fetchMock.mock.calls[1][1]).toEqual(expect.objectContaining({ method: 'POST', headers: { 'X-Tenant-ID': '1' }, signal }))
    fetchMock.mockResolvedValueOnce(Response.json({ certificate: detail, changed: true }))
    await expect(revokeCertificate(1, 1, signal)).rejects.toThrow('could not be confirmed')
  })

  it('sends the selected course issuance request and validates returned count consistency', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(Response.json(issueSummary))
      .mockResolvedValueOnce(Response.json({ ...issueSummary, issued: 999 }))
    vi.stubGlobal('fetch', fetchMock)
    expect(await issueCertificates(1, 10, new AbortController().signal)).toEqual(issueSummary)
    const [address, options] = fetchMock.mock.calls[0]
    expect(new URL(address).pathname).toBe('/api/tenants/1/courses/10/issue')
    expect(options).toEqual(expect.objectContaining({ method: 'POST', headers: { 'X-Tenant-ID': '1' } }))
    expect(options.body).toBeUndefined()
    await expect(issueCertificates(1, 10, new AbortController().signal)).rejects.toThrow('could not be validated')
  })

  it('rejects a foreign tenant course response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json([{ id: 20, tenant_id: 2, title: 'Foreign course' }])))
    await expect(getCourses(1, new AbortController().signal)).rejects.toThrow('invalid course list')
  })
})
