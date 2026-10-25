export interface CourseOption { id: number; tenant_id: number; title: string }
export interface LearnerOutcome {
  learner_id: number
  learner_name: string
  outcome: 'issued' | 'skipped' | 'failed'
  reason: string
  certificate_id: number | null
  serial_number: string | null
}
export interface IssueSummary {
  tenant_id: number
  course_id: number
  total: number
  issued: number
  skipped: number
  failed: number
  results: LearnerOutcome[]
}
