import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { getCertificate, revokeCertificate } from '../api/certificates'
import { CertificateDetailPage } from '../pages/CertificateDetailPage'
import type { CertificateDetail, RevokeResponse } from '../types/certificates'
import { deferred, detail } from './fixtures'

vi.mock('../api/certificates', () => ({ getCertificate: vi.fn(), revokeCertificate: vi.fn() }))

beforeEach(() => { vi.mocked(getCertificate).mockResolvedValue(detail) })
function mount() { return render(<CertificateDetailPage tenantId={1} certificateId={1} onTenantChange={vi.fn()} />) }

describe('certificate detail and revocation', () => {
  it('shows loading and required fields with an explicit tenant-local issue date', async () => {
    const pending = deferred<CertificateDetail>()
    vi.mocked(getCertificate).mockReturnValue(pending.promise)
    mount()
    expect(screen.getByText('Loading certificate…')).toBeInTheDocument()
    await act(async () => { pending.resolve(detail) })
    expect(await screen.findByText(detail.serial_number)).toBeInTheDocument()
    expect(screen.getByText(detail.learner_name)).toBeInTheDocument()
    expect(screen.getByText(detail.course_title)).toBeInTheDocument()
    expect(screen.getByText('27 September 2026 at 01:30:00')).toHaveAttribute('datetime', detail.issued_at)
    expect(screen.getByText(/Australia\/Sydney · 2026-09-27T01:30:00\+10:00/)).toBeInTheDocument()
  })

  it('requires confirmation and cancellation sends no mutation', async () => {
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByRole('button', { name: 'Revoke certificate' }))
    const dialog = screen.getByRole('dialog', { name: 'Revoke this certificate?' })
    expect(within(dialog).getByText(detail.serial_number)).toBeInTheDocument()
    expect(revokeCertificate).not.toHaveBeenCalled()
    await user.click(within(dialog).getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Revoke certificate' })).toBeEnabled()
    expect(revokeCertificate).not.toHaveBeenCalled()
  })

  it('confirms once, disables controls in flight and retains details after revocation', async () => {
    const pending = deferred<RevokeResponse>()
    vi.mocked(revokeCertificate).mockReturnValue(pending.promise)
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByRole('button', { name: 'Revoke certificate' }))
    await user.dblClick(screen.getByRole('button', { name: 'Confirm revocation' }))
    expect(revokeCertificate).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('button', { name: 'Revoking…' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled()
    await act(async () => { pending.resolve({ certificate: { ...detail, status: 'revoked' }, changed: true }) })
    expect(await screen.findByRole('heading', { name: 'This certificate has been revoked' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Revoke certificate' })).not.toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.getByText(detail.serial_number)).toBeInTheDocument()
    expect(screen.getByText('27 September 2026 at 01:30:00')).toHaveAttribute('datetime', detail.issued_at)
    expect(revokeCertificate).toHaveBeenCalledWith(1, 1, expect.any(AbortSignal))
  })

  it('shows a detail error and retries the read', async () => {
    vi.mocked(getCertificate).mockRejectedValueOnce(new Error('HTTP 404'))
    const user = userEvent.setup()
    mount()
    expect(await screen.findByRole('alert')).toHaveTextContent('HTTP 404')
    await user.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByText(detail.serial_number)).toBeInTheDocument()
    expect(getCertificate).toHaveBeenCalledTimes(2)
  })

  it('reloads actual status after an unconfirmed revoke response', async () => {
    vi.mocked(revokeCertificate).mockRejectedValue(new TypeError('Response lost'))
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByRole('button', { name: 'Revoke certificate' }))
    await user.click(screen.getByRole('button', { name: 'Confirm revocation' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('The server may already have revoked this certificate')
    vi.mocked(getCertificate).mockResolvedValue({ ...detail, status: 'revoked' })
    await user.click(screen.getByRole('button', { name: 'Reload certificate' }))
    await screen.findByRole('heading', { name: 'This certificate has been revoked' })
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument())
    expect(revokeCertificate).toHaveBeenCalledTimes(1)
  })
})
