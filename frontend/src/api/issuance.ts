import { API_BASE_URL } from './health'
import type { CourseOption, IssueSummary } from '../types/issuance'

export async function getCourses(tenantId: number, signal: AbortSignal): Promise<CourseOption[]> {
  const response = await fetch(`${API_BASE_URL}/api/tenants/${tenantId}/courses`, {
    signal, headers: { 'X-Tenant-ID': String(tenantId) },
  })
  if (!response.ok) throw new Error(`Course request returned HTTP ${response.status}.`)
  const data = await response.json() as CourseOption[]
  if (!Array.isArray(data) || !data.every((row) => row && row.tenant_id === tenantId && Number.isInteger(row.id) && typeof row.title === 'string')) {
    throw new Error('The API returned an invalid course list.')
  }
  return data
}

export async function issueCertificates(tenantId: number, courseId: number, signal: AbortSignal): Promise<IssueSummary> {
  const response = await fetch(`${API_BASE_URL}/api/tenants/${tenantId}/courses/${courseId}/issue`, {
    method: 'POST', signal, headers: { 'X-Tenant-ID': String(tenantId) },
  })
  if (!response.ok) throw new Error(`Issuance request returned HTTP ${response.status}.`)
  const data = await response.json() as IssueSummary
  if (!data || data.tenant_id !== tenantId || data.course_id !== courseId || !Array.isArray(data.results)
      || ![data.total, data.issued, data.skipped, data.failed].every((value) => Number.isInteger(value) && value >= 0)
      || data.results.length !== data.total || data.issued + data.skipped + data.failed !== data.total
      || !data.results.every((row) => row && Number.isInteger(row.learner_id) && typeof row.learner_name === 'string'
        && ['issued', 'skipped', 'failed'].includes(row.outcome) && typeof row.reason === 'string')
      || ['issued', 'skipped', 'failed'].some((outcome) => data.results.filter((row) => row.outcome === outcome).length !== data[outcome as 'issued' | 'skipped' | 'failed'])) {
    throw new Error('The issuance response could not be validated.')
  }
  return data
}
