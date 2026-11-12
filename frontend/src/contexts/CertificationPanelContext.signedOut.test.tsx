import { render } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { AuthContext } from './AuthContext'
import { CertificationPanelProvider } from './CertificationPanelContext'

// Support ticket: the provider wraps the public landing page and asked for
// certification progress there, which 401'd for a logged-out visitor.
const useCertification = vi.hoisted(() => vi.fn())
vi.mock('../hooks/useCertification', () => ({ useCertification }))

beforeEach(() => {
  useCertification.mockReset().mockReturnValue({ progress: null, course: null, loading: false })
})

const withAuth = (user: unknown) => render(
  <AuthContext.Provider value={{ user } as never}>
    <CertificationPanelProvider><span /></CertificationPanelProvider>
  </AuthContext.Provider>,
)

it('does not load certification progress for a logged-out visitor', () => {
  withAuth(null)
  expect(useCertification).toHaveBeenLastCalledWith(false)
})

it('loads it once someone is signed in', () => {
  withAuth({ user_id: 'u1' })
  expect(useCertification).toHaveBeenLastCalledWith(true)
})

it('loads it where no auth provider is mounted', () => {
  render(<CertificationPanelProvider><span /></CertificationPanelProvider>)
  expect(useCertification).toHaveBeenLastCalledWith(true)
})
