import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, beforeEach, vi } from 'vitest'

// jsdom does not implement native modal/top-layer/focus-trap behavior.
// Only the DOM open/close contract is shimmed; real-browser checks remain separate.
if (!HTMLDialogElement.prototype.showModal) {
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', '') }
}
if (!HTMLDialogElement.prototype.close) {
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open') }
}

beforeEach(() => {
  // A missing mock must fail locally, never contact a running developer API.
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Unexpected unmocked fetch in test')))
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.useRealTimers()
  window.history.replaceState(null, '', '/')
})
