import { useEffect, useRef } from 'react'

export function RevokeConfirmation({ serial, learner, busy, onCancel, onConfirm }: {
  serial: string; learner: string; busy: boolean; onCancel: () => void; onConfirm: () => void
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const element = dialog.current
    element?.showModal()
    return () => element?.close()
  }, [])

  return <dialog ref={dialog} className="revoke-dialog" aria-labelledby="revoke-dialog-title" aria-describedby="revoke-dialog-description"
    onCancel={(event) => { event.preventDefault(); if (!busy) onCancel() }}>
    <h2 id="revoke-dialog-title">Revoke this certificate?</h2>
    <p id="revoke-dialog-description">Revoke certificate <strong>{serial}</strong> for {learner}? Its original issue record will be preserved. It cannot be reissued through Bulk Issue.</p>
    <div className="dialog-actions"><button autoFocus disabled={busy} onClick={onCancel}>Cancel</button>
      <button className="danger-button" disabled={busy} onClick={onConfirm}>{busy ? 'Revoking…' : 'Confirm revocation'}</button></div>
    {busy && <p className="safe-retry-note" role="status">Saving revocation and its audit record…</p>}
  </dialog>
}
