import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

vi.mock('../../api/assistant', () => ({ getCoreSkills: vi.fn(), setCoreSkills: vi.fn() }))
vi.mock('../../api/extractions', () => ({ listSearchSets: vi.fn() }))

import { CoreSkillsSection } from './CoreSkillsSection'
import { getCoreSkills, setCoreSkills } from '../../api/assistant'
import { listSearchSets } from '../../api/extractions'

const award = { uuid: 's1', title: 'Award review', when_to_use: 'Reviewing a new award notice', usable: true, problem: null }
const librarySkill = (uuid: string, title: string, when?: string) => ({
  uuid, title, set_type: 'prompt', extraction_config: when ? { when_to_use: when } : {},
})

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(getCoreSkills).mockResolvedValue({ skills: [award], max: 5 })
  vi.mocked(setCoreSkills).mockResolvedValue({ skills: [award], max: 5 })
  vi.mocked(listSearchSets).mockResolvedValue([
    librarySkill('s1', 'Award review', 'Reviewing a new award notice'),
    librarySkill('s2', 'Subaward intake', 'Checking a subaward against intake'),
    librarySkill('s3', 'House tone'),
    { uuid: 'x1', title: 'Budget fields', set_type: 'extraction', extraction_config: {} },
  ] as unknown as Awaited<ReturnType<typeof listSearchSets>>)
})

describe('CoreSkillsSection', () => {
  it('adds a Skill that has a When to use line, after the ones already kept', async () => {
    render(<CoreSkillsSection />)
    fireEvent.click(await screen.findByRole('button', { name: 'Add a core Skill' }))
    fireEvent.click(await screen.findByRole('button', { name: /Subaward intake/ }))
    await waitFor(() => expect(setCoreSkills).toHaveBeenCalledWith(['s1', 's2']))
    // Already a core Skill, and not a Skill at all: neither is offered.
    expect(screen.queryByRole('button', { name: /Budget fields/ })).toBeNull()
  })

  it('will not add a Skill without a When to use line and says how to fix it', async () => {
    render(<CoreSkillsSection />)
    fireEvent.click(await screen.findByRole('button', { name: 'Add a core Skill' }))
    const tone = await screen.findByRole('button', { name: /House tone/ })
    expect(tone).toBeDisabled()
    expect(tone.textContent).toContain('No When to use line yet')
  })

  it('removes a Skill and shows why one is not being used', async () => {
    vi.mocked(getCoreSkills).mockResolvedValue({
      skills: [award, { uuid: 'gone', title: null, when_to_use: '', usable: false, problem: 'Skill not found or no longer accessible' }],
      max: 5,
    })
    render(<CoreSkillsSection />)
    expect(await screen.findByText(/Chat is not using this Skill\. Skill not found or no longer accessible/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Remove Award review from core Skills' }))
    await waitFor(() => expect(setCoreSkills).toHaveBeenCalledWith(['gone']))
  })

  it('stops offering more at the limit and shows the server message when a save is refused', async () => {
    vi.mocked(getCoreSkills).mockResolvedValue({ skills: [award], max: 1 })
    const { unmount } = render(<CoreSkillsSection />)
    expect(await screen.findByRole('button', { name: 'Add a core Skill' })).toBeDisabled()
    unmount()

    vi.mocked(getCoreSkills).mockResolvedValue({ skills: [award], max: 5 })
    vi.mocked(setCoreSkills).mockRejectedValue(new Error('Add a When to use line to "Subaward intake" in the Library first, so chat knows when to use it.'))
    render(<CoreSkillsSection />)
    fireEvent.click(await screen.findByRole('button', { name: 'Add a core Skill' }))
    fireEvent.click(await screen.findByRole('button', { name: /Subaward intake/ }))
    expect(await screen.findByText(/Add a When to use line to "Subaward intake"/)).toBeTruthy()
  })
})
