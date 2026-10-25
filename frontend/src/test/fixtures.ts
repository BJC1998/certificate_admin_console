import type { CertificateDetail, CertificatePage, CertificateQuery, TenantOption } from '../types/certificates'
import type { IssueSummary } from '../types/issuance'

export const tenants: TenantOption[] = [
  { id: 1, name: 'Sydney', timezone: 'Australia/Sydney' },
  { id: 2, name: 'Perth', timezone: 'Australia/Perth' },
]

export function certificatePage(tenantId = 1, page = 1): CertificatePage {
  const name = tenantId === 1 ? 'Sydney' : 'Perth'
  return { tenant_id: tenantId, tenant_timezone: tenantId === 1 ? 'Australia/Sydney' : 'Australia/Perth',
    total: 21, page, page_size: 10, total_pages: 3, records: [{ id: tenantId * 100 + page,
      tenant_id: tenantId, learner_name: `${name} Learner 01`, course_title: 'Safety',
      serial_number: `${name.toUpperCase()}-${page}`, issued_at: '2026-09-27T01:30:00+10:00', status: 'valid' }] }
}

export const detail: CertificateDetail = {
  id: 1, tenant_id: 1, tenant_name: 'Sydney', tenant_timezone: 'Australia/Sydney',
  learner_id: 1, learner_name: 'Sydney Learner 01', course_id: 10, course_title: 'Safety',
  serial_number: 'SYDNEY-DETAIL-001', issued_at: '2026-09-27T01:30:00+10:00', status: 'valid',
}

export const query: CertificateQuery = {
  tenantId: 2, search: 'Perth Learner', status: 'revoked', page: 5, pageSize: 10,
  sortBy: 'issue_date', sortOrder: 'asc',
}

export const issueSummary: IssueSummary = {
  tenant_id: 1, course_id: 10, total: 6, issued: 2, skipped: 3, failed: 1,
  results: [
    { learner_id: 1, learner_name: 'New learner A', outcome: 'issued', reason: 'certificate_and_audit_committed', certificate_id: 101, serial_number: 'NEW-A' },
    { learner_id: 2, learner_name: 'New learner B', outcome: 'issued', reason: 'certificate_and_audit_committed', certificate_id: 102, serial_number: 'NEW-B' },
    { learner_id: 3, learner_name: 'Existing learner', outcome: 'skipped', reason: 'already_issued', certificate_id: 103, serial_number: 'EXISTING' },
    { learner_id: 4, learner_name: 'Revoked learner', outcome: 'skipped', reason: 'previously_revoked', certificate_id: 104, serial_number: 'REVOKED' },
    { learner_id: 5, learner_name: 'Incomplete learner', outcome: 'skipped', reason: 'enrollment_incomplete', certificate_id: null, serial_number: null },
    { learner_id: 6, learner_name: 'Failed learner', outcome: 'failed', reason: 'database_busy_retry_safe', certificate_id: null, serial_number: null },
  ],
}

export function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
