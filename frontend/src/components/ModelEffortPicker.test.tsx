import { render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { ModelEffortPicker } from './ModelEffortPicker'

it('leads with the friendly tag and keeps the model id secondary (#1014 item 47)', () => {
  // Production's shape: name is the provider id, tag is the admin's label.
  const models = [{ name: 'openai/gpt-oss-120b', tag: 'VandalAI-Fast', external: false, thinking: true, speed: 'fast' }] as React.ComponentProps<typeof ModelEffortPicker>['models']
  render(<ModelEffortPicker models={models} selectedModel="VandalAI-Fast" onChange={vi.fn()} />)
  const option = screen.getByRole('radio', { name: 'VandalAI-Fast' })
  const label = option.querySelector('span[style*="font-weight: 700"]')!
  expect(label.firstChild).toHaveTextContent('VandalAI-Fast')
  expect(label.querySelector('span')).toHaveTextContent('openai/gpt-oss-120b')
})
