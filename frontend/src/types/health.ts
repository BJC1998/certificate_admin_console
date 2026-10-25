export interface HealthResponse {
  status: 'ok'
}

export type ConnectionState =
  | { status: 'checking' }
  | { status: 'connected' }
  | { status: 'error'; message: string }
