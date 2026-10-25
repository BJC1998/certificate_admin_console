export interface TenantOption { id: number; name: string; timezone: string }
export type SortField = 'learner_name' | 'course_title' | 'serial_number' | 'issued_at' | 'issue_date' | 'status'
export type SortOrder = 'asc' | 'desc'
export interface CertificateQuery {
  tenantId: number | null
  search: string
  status?: 'valid' | 'revoked'
  page: number
  pageSize: number
  sortBy: SortField
  sortOrder: SortOrder
}
export interface CertificateRecord {
  id: number
  tenant_id: number
  learner_name: string
  course_title: string
  serial_number: string
  issued_at: string
  status: 'valid' | 'revoked'
}
export interface CertificatePage {
  records: CertificateRecord[]
  total: number
  page: number
  page_size: number
  total_pages: number
  tenant_id: number
  tenant_timezone: string
}
export interface CertificateDetail extends CertificateRecord {
  learner_id: number
  course_id: number
  tenant_name: string
  tenant_timezone: string
}
export interface RevokeResponse { certificate: CertificateDetail; changed: boolean }
export type LoadState<T> = { status: 'loading' } | { status: 'error'; message: string } | { status: 'success'; data: T }
