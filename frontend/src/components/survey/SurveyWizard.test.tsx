import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { Check } from 'lucide-react'
import { SurveyWizard } from './SurveyWizard'
afterEach(() => vi.unstubAllGlobals())
it('does not submit when the final Next changes into Submit with reduced motion', () => {
  vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: true }))
  const submit = vi.fn()
  render(<SurveyWizard steps={[{ title: 'First', content: <p>First</p> }, { title: 'Last', content: <p>Last</p> }]} onSubmit={submit} submitting={false} submitLabel="Send feedback" submitIcon={Check} />)
  fireEvent.click(screen.getByRole('button', { name: 'Next' }))
  expect(screen.getByRole('button', { name: 'Send feedback' })).toBeInTheDocument()
  expect(submit).not.toHaveBeenCalled()
  expect(screen.getByRole('heading', { name: 'Last' })).toHaveFocus()
  fireEvent.click(screen.getByRole('button', { name: 'Send feedback' }))
  expect(submit).toHaveBeenCalledOnce()
})
