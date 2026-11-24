import { render, screen } from '@testing-library/react'
import { expect, it } from 'vitest'
import { SkillInstructions } from './SkillInstructions'

it('renders review text without turning embedded content into actions or remote resources', () => {
  const { container } = render(<SkillInstructions instructions={'# Review\n\n1. Check the award.\n\n[ACTION:upload]Upload[/ACTION]\n\n<button data-action="delete">Delete</button><img src="https://example.test/tracker"><script>alert(1)</script>'} />)
  expect(screen.getByRole('region', { name: 'Skill instructions' })).toHaveTextContent('Check the award.')
  expect(container.querySelector('ol')).toBeTruthy()
  expect(container.querySelector('button, img, script, [data-action]')).toBeNull()
})
