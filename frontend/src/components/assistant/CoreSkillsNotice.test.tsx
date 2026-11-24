import { render, screen } from '@testing-library/react'
import { expect, it } from 'vitest'
import type { CoreSkill } from '../../api/assistant'
import { CoreSkillsNotice } from './CoreSkillsNotice'

const skill = (over: Partial<CoreSkill>): CoreSkill => ({
  uuid: 's1', title: 'Award review', status: 'ok', usable: true, problem: null,
  when_to_use: 'Reviewing an award', version: 'v1', instructions: null, ...over,
})

it('announces an edited core Skill and links to the review', () => {
  render(<CoreSkillsNotice error="" page={{ max: 5, skills: [skill({ status: 'changed', usable: false, problem: 'Edited.' })] }} />)
  expect(screen.getByRole('status')).toHaveTextContent('1 core Skill is paused')
  expect(screen.getByRole('link', { name: 'Review in Assistant settings' })).toHaveAttribute('href', '/assistant#assistant-core-skills')
})

it('stays quiet about a Skill that belongs to another team', () => {
  const { container } = render(<CoreSkillsNotice error="" page={{ max: 5, skills: [skill({ status: 'other_team', usable: false, problem: 'Another team.' })] }} />)
  expect(container).toBeEmptyDOMElement()
})
