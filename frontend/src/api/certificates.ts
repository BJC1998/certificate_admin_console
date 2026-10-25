import { API_BASE_URL } from './health'
import type { CertificateDetail, CertificatePage, CertificateQuery, RevokeResponse, TenantOption } from '../types/certificates'

async function request(path: string, signal: AbortSignal, tenantId?: number, method: 'GET' | 'POST' = 'GET'): Promise<unknown> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    signal, method,
    headers: tenantId === undefined ? undefined : { 'X-Tenant-ID': String(tenantId) },
  })
  if (!response.ok) throw new Error(`The API returned HTTP ${response.status}. Please try again.`)
  return response.json()
}

function validateDetail(data: CertificateDetail, tenantId: number, certificateId: number): CertificateDetail {
  if (!data || data.tenant_id !== tenantId || data.id !== certificateId
      || !Number.isInteger(data.course_id) || !Number.isInteger(data.learner_id)
      || typeof data.learner_name !== 'string' || typeof data.course_title !== 'string'
      || typeof data.tenant_name !== 'string' || typeof data.tenant_timezone !== 'string'
      || typeof data.serial_number !== 'string' || typeof data.issued_at !== 'string'
      || !Number.isFinite(Date.parse(data.issued_at)) || !['valid', 'revoked'].includes(data.status)) {
    throw new Error('The API returned an invalid certificate detail response.')
  }
  return data
}

export async function getCertificate(tenantId: number, certificateId: number, signal: AbortSignal): Promise<CertificateDetail> {
  const data = await request(`/api/tenants/${tenantId}/certificates/${certificateId}`, signal, tenantId) as CertificateDetail
  return validateDetail(data, tenantId, certificateId)
}

export async function revokeCertificate(tenantId: number, certificateId: number, signal: AbortSignal): Promise<RevokeResponse> {
  const data = await request(`/api/tenants/${tenantId}/certificates/${certificateId}/revoke`, signal, tenantId, 'POST') as RevokeResponse
  if (!data || typeof data.changed !== 'boolean') throw new Error('The revocation response could not be confirmed.')
  validateDetail(data.certificate, tenantId, certificateId)
  if (data.certificate.status !== 'revoked') throw new Error('The revocation response could not be confirmed.')
  return data
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
  if (query.status) params.set('status', query.status)
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

export async function exportCertificates(query: CertificateQuery, signal: AbortSignal): Promise<{ blob: Blob; filename: string }> {
  if (query.tenantId === null) throw new Error('Select a tenant first.')
  // Page and page_size are deliberately excluded from the complete export request.
  const params = new URLSearchParams({ search: query.search, sort_by: query.sortBy, sort_order: query.sortOrder })
  if (query.status) params.set('status', query.status)
  const response = await fetch(`${API_BASE_URL}/api/tenants/${query.tenantId}/certificates/export?${params}`, {
    signal, headers: { 'X-Tenant-ID': String(query.tenantId) },
  })
  if (!response.ok) throw new Error(`CSV export returned HTTP ${response.status}. Please retry.`)
  if (!response.headers.get('content-type')?.startsWith('text/csv')) throw new Error('The API did not return a CSV file.')
  const blob = await response.blob()
  const length = response.headers.get('content-length')
  if (length !== null && blob.size !== Number(length)) throw new Error('The CSV download was incomplete. Please retry.')
  const filename = /filename="([a-zA-Z0-9_.-]+\.csv)"/.exec(response.headers.get('content-disposition') ?? '')?.[1]
    ?? `certificates-tenant-${query.tenantId}-${new Date().toISOString().replace(/[:.]/g, '-')}.csv`
  return { blob, filename }
}
