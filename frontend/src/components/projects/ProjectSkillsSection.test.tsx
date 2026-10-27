import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, expect, it, vi } from 'vitest'
import { ProjectSkillsSection } from './ProjectSkillsSection'
import * as api from '../../api/projects'
import { listSearchSets } from '../../api/extractions'

vi.mock('../../api/projects', () => ({ listProjectPins: vi.fn(), addProjectPin: vi.fn(), removeProjectPin: vi.fn(), setProjectDefaultSkill: vi.fn() }))
vi.mock('../../api/extractions', () => ({ listSearchSets: vi.fn() }))
const changed = vi.fn()
const setup = (canManage = true) => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><ProjectSkillsSection projectUuid="p1" defaultSkillUuid="s1" canManage={canManage} onChange={changed} /></QueryClientProvider>)
beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(api.listProjectPins).mockResolvedValue([{ pin_type: 'skill', target_id: 's1', name: 'Award review' }])
  vi.mocked(listSearchSets).mockResolvedValue([{ uuid: 's2', title: 'Summarize', set_type: 'prompt' }, { uuid: 'e1', title: 'Extract', set_type: 'extraction' }] as Awaited<ReturnType<typeof listSearchSets>>)
})
it('offers explicit activation and saves a default change only after clicking Save', async () => {
  setup()
  expect(await screen.findByRole('link', { name: 'Use in chat' })).toHaveAttribute('href', '/?project=p1&skill=s1')
  expect(screen.getByText('Default')).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('Default Skill'), { target: { value: '' } })
  expect(api.setProjectDefaultSkill).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Save default Skill' }))
  await waitFor(() => expect(api.setProjectDefaultSkill).toHaveBeenCalledWith('p1', null))
  expect(changed).toHaveBeenCalled()
})
it('pins only Skills and retains a failed selection for retry', async () => {
  setup()
  fireEvent.click(screen.getByRole('button', { name: 'Pin a Skill' }))
  expect(await screen.findByRole('button', { name: 'Pin Summarize' })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Pin Extract' })).not.toBeInTheDocument()
  vi.mocked(api.addProjectPin).mockRejectedValueOnce(new Error('No longer accessible'))
  fireEvent.click(screen.getByRole('button', { name: 'Pin Summarize' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('No longer accessible')
  expect(api.addProjectPin).toHaveBeenCalledWith('p1', { pin_type: 'skill', target_id: 's2' })
  expect(api.setProjectDefaultSkill).not.toHaveBeenCalled()
})
it('allows viewers to use accessible pins without exposing management controls', async () => {
  setup(false)
  await screen.findByRole('link', { name: 'Use in chat' })
  expect(screen.queryByRole('button', { name: 'Pin a Skill' })).not.toBeInTheDocument()
  expect(screen.queryByLabelText('Default Skill')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Unpin Award review' })).not.toBeInTheDocument()
})
