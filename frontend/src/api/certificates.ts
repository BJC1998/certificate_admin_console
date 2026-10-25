import { API_BASE_URL } from './health'
import type { CertificatePage, CertificateQuery, TenantOption } from '../types/certificates'

async function request(path: string, signal: AbortSignal, tenantId?: number): Promise<unknown> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    signal,
    headers: tenantId === undefined ? undefined : { 'X-Tenant-ID': String(tenantId) },
  })
  if (!response.ok) throw new Error(`The API returned HTTP ${response.status}. Please try again.`)
  return response.json()
}

export async function getTenants(signal: AbortSignal): Promise<TenantOption[]> {
  const data = await request('/api/tenants', signal)
  if (!Array.isArray(data) || !data.every((item: TenantOption) =>
    item && Number.isInteger(item.id) && typeof item.name === 'string' && typeof item.timezone === 'string')) {
    throw new Error('The API returned an invalid tenant directory.')
  }
  return data
}

export async function getCertificates(query: CertificateQuery, signal: AbortSignal): Promise<CertificatePage> {
  if (query.tenantId === null) throw new Error('Select a tenant first.')
  const params = new URLSearchParams({ search: query.search, page: String(query.page),
    page_size: String(query.pageSize), sort_by: query.sortBy, sort_order: query.sortOrder })
  const data = await request(`/api/tenants/${query.tenantId}/certificates?${params}`, signal, query.tenantId) as CertificatePage
  if (!data || data.tenant_id !== query.tenantId || !Array.isArray(data.records)
      || !Number.isInteger(data.total) || !Number.isInteger(data.total_pages)
      || data.page !== query.page || data.page_size !== query.pageSize || typeof data.tenant_timezone !== 'string'
      || !data.records.every((row) => row.tenant_id === query.tenantId && Number.isInteger(row.id)
        && typeof row.learner_name === 'string' && typeof row.course_title === 'string'
        && typeof row.serial_number === 'string' && typeof row.issued_at === 'string'
        && Number.isFinite(Date.parse(row.issued_at)) && ['valid', 'revoked'].includes(row.status))) {
    throw new Error('The API returned an invalid certificate response.')
  }
  return data
}
