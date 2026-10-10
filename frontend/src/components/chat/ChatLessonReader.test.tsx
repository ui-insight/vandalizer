import { beforeEach, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ChatLessonReader } from './ChatLessonReader'
import { ChatModuleLessons } from './ChatModuleLessons'
import { MODULES } from '../certification/modules'
import corrections from '../certification/editorialCorrections.json'

const state = vi.hoisted(() => ({ value: null as unknown, save: vi.fn(), refresh: vi.fn(), open: vi.fn() }))
vi.mock('../../contexts/CertificationPanelContext', () => ({ useCertificationPanelOptional: () => state.value }))
const lessons = [
  { id: 'module.alpha', revision: 1, title: 'Same title', content: 'First immutable lesson.', objective: 'First objective.', variant: 'concept' },
  { id: 'module.beta', revision: 1, title: 'Same title', content: 'Second immutable lesson.', variant: 'concept' },
  { id: 'module.gamma', revision: 1, title: 'Final lesson', content: 'Third immutable lesson.', variant: 'concept' },
]
const identity = { enrollment_id: 'enrollment-a', course_version: '5.0-draft', manifest_sha256: 'a'.repeat(64) }
const content = { ...identity, module_id: 'module', module_title: 'Module', lesson_id: lessons[0].id, lesson_revision: 1, lesson_number: 1, lesson_count: 3, ...lessons[0] }
function context() {
  return { progress: { ...identity, modules: { module: { learning_position: { lesson_id: lessons[1].id } } } },
    course: { ...identity, modules: [{ id: 'module', lessons }] }, savePosition: state.save, refresh: state.refresh, openPanel: state.open }
}
beforeEach(() => { vi.clearAllMocks(); localStorage.clear(); state.save.mockResolvedValue(undefined); state.value = context() })

it('corrects a preserved historical card without an active course, new payload metadata or a write', () => {
  state.value = null
  const notice = corrections.notices[0]
  render(<ChatLessonReader content={{ ...content, manifest_sha256: notice.manifest_sha256,
    lesson_id: notice.lesson_ids[0], content: 'Preserved historical lesson body.' }} />)
  expect(screen.getByRole('complementary', { name: notice.title })).toBeInTheDocument()
  expect(screen.getByText('Preserved historical lesson body.')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Save my place' })).not.toBeInTheDocument()
  expect(state.save).not.toHaveBeenCalled()
})

it('does not attach historical corrections to a different package with the same lesson ID', () => {
  state.value = null
  const notice = corrections.notices[0]
  render(<ChatLessonReader content={{ ...content, manifest_sha256: 'f'.repeat(64), lesson_id: notice.lesson_ids[0] }} />)
  expect(screen.queryByRole('complementary', { name: notice.title })).not.toBeInTheDocument()
})

it('does not attach a late text match to a different unversioned historical lesson', async () => {
  state.value = null
  const notice = corrections.notices[0]
  let finish!: (value: ArrayBuffer) => void
  const digest = vi.fn().mockImplementationOnce(() => new Promise<ArrayBuffer>(resolve => { finish = resolve }))
    .mockResolvedValue(new Uint8Array(32).buffer)
  vi.stubGlobal('crypto', { subtle: { digest } })
  try {
    const historical = { ...content, enrollment_id: undefined, manifest_sha256: undefined, lesson_id: undefined }
    const { rerender } = render(<ChatLessonReader content={historical} />)
    rerender(<ChatLessonReader content={{ ...historical, content: 'A different preserved body.' }} />)
    finish(Uint8Array.from(notice.unversioned_content_sha256[0].match(/../g)!, byte => parseInt(byte, 16)).buffer)
    await waitFor(() => expect(digest).toHaveBeenCalledTimes(2))
    expect(screen.queryByRole('complementary', { name: notice.title })).not.toBeInTheDocument()
    expect(screen.getByText('A different preserved body.')).toBeInTheDocument()
  } finally { vi.unstubAllGlobals() }
})

it('starts module teaching directly and returns to the saved stable lesson', () => {
  render(<ChatModuleLessons content={{ ...identity, module_id: 'module' }} />)
  fireEvent.click(screen.getByRole('button', { name: 'Start the lessons (3)' }))
  expect(screen.getByText('First immutable lesson.')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Return to saved lesson' }))
  expect(screen.getByText('Second immutable lesson.')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Close lessons' }))
  expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
  expect(state.save).not.toHaveBeenCalled()
})

it('does not start teaching from a module card with mismatched course bytes', () => {
  render(<ChatModuleLessons content={{ ...identity, module_id: 'module', manifest_sha256: 'old' }} />)
  expect(screen.queryByRole('button', { name: 'Start the lessons (3)' })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Open lessons in learning panel' }))
  expect(state.open).toHaveBeenCalledOnce()
})

it('navigates by stable ID with duplicate titles and focuses the new lesson without saving', () => {
  render(<ChatLessonReader content={content} />)
  expect(screen.getByRole('button', { name: 'Previous lesson' })).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: 'Next lesson' }))
  expect(screen.getByText('Second immutable lesson.')).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: 'Same title' })).toHaveFocus()
  expect(screen.queryByText('First objective.')).not.toBeInTheDocument()
  fireEvent.change(screen.getByRole('combobox'), { target: { value: lessons[2].id } })
  expect(screen.getByText('Third immutable lesson.')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Next lesson' })).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: 'Return to saved lesson' }))
  expect(screen.getByRole('combobox')).toHaveValue(lessons[1].id)
  fireEvent.click(screen.getByRole('button', { name: 'Previous lesson' }))
  expect(screen.getByText('First immutable lesson.')).toBeInTheDocument()
  expect(state.save).not.toHaveBeenCalled()
})

it('uses authored order and identities even when the original numeric position is different', () => {
  state.value = { ...context(), course: { ...identity, modules: [{ id: 'module', lessons: [lessons[2], lessons[0], lessons[1]] }] } }
  render(<ChatLessonReader content={content} />)
  expect(screen.getByText('Lesson 2/3 · Module')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Previous lesson' }))
  expect(screen.getByText('Third immutable lesson.')).toBeInTheDocument()
})

it('saves only the explicitly selected stable ID and blocks duplicate saves while pending', async () => {
  let resolve!: () => void
  state.save.mockReturnValue(new Promise<void>(done => { resolve = done }))
  render(<ChatLessonReader content={content} />)
  fireEvent.click(screen.getByRole('button', { name: 'Next lesson' }))
  fireEvent.click(screen.getByRole('button', { name: 'Save my place' }))
  fireEvent.click(screen.getByRole('button', { name: 'Save my place' }))
  expect(state.save).toHaveBeenCalledExactlyOnceWith('module', 'module.beta')
  expect(screen.getByRole('combobox')).toBeDisabled()
  resolve()
  await screen.findByText('Place saved across devices.')
})

it('keeps reading after a failed save and refreshes without retrying the write', async () => {
  state.save.mockRejectedValue(new Error('conflict'))
  render(<ChatLessonReader content={content} />)
  fireEvent.click(screen.getByRole('button', { name: 'Next lesson' }))
  fireEvent.click(screen.getByRole('button', { name: 'Save my place' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Refresh progress' }))
  expect(state.refresh).toHaveBeenCalledOnce()
  expect(state.save).toHaveBeenCalledOnce()
  expect(screen.getByText('Second immutable lesson.')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Return to saved lesson' }))
  expect(screen.getByRole('combobox')).toHaveValue('module.beta')
})

it.each(['enrollment', 'manifest', 'revision', 'missing_id', 'duplicate_id', 'changed_content'])('leaves historical teaching readable without guessing its identity: %s', change => {
  const saved = { ...content }
  if (change === 'enrollment') saved.enrollment_id = 'older'
  if (change === 'manifest') saved.manifest_sha256 = 'b'.repeat(64)
  if (change === 'revision') saved.lesson_revision = 2
  if (change === 'missing_id') saved.lesson_id = ''
  if (change === 'changed_content') saved.content = 'Historical original content.'
  if (change === 'duplicate_id') state.value = { ...context(), course: { ...identity, modules: [{ id: 'module', lessons: [lessons[0], lessons[0]] }] } }
  render(<ChatLessonReader content={saved} />)
  expect(screen.getByText(saved.content)).toBeInTheDocument()
  expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Open learning panel' }))
  expect(state.open).toHaveBeenCalledOnce()
  expect(state.save).not.toHaveBeenCalled()
})

it('removes navigation immediately when course selection changes', () => {
  const { rerender } = render(<ChatLessonReader content={content} />)
  fireEvent.click(screen.getByRole('button', { name: 'Next lesson' }))
  state.value = { ...context(), progress: { enrollment_id: 'another', modules: {} } }
  rerender(<ChatLessonReader content={content} />)
  expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
  expect(screen.getByText(content.content)).toBeInTheDocument()
})

it('preserves legacy browser positions and never calls the enrolled position endpoint', async () => {
  const module = MODULES[0], lesson = module.lessons[0]
  localStorage.setItem(`cert-lesson::${module.id}`, '2')
  state.value = { ...context(), progress: { modules: {} }, course: null }
  render(<ChatLessonReader content={{ module_id: module.id, module_title: module.title, ...lesson, lesson_id: lesson.id, lesson_revision: lesson.revision, lesson_number: 1, lesson_count: module.lessons.length }} />)
  fireEvent.click(screen.getByRole('button', { name: 'Return to saved lesson' }))
  expect(screen.getByRole('combobox')).toHaveValue(module.lessons[2].id)
  fireEvent.click(screen.getByRole('button', { name: 'Next lesson' }))
  fireEvent.click(screen.getByRole('button', { name: 'Save my place' }))
  await waitFor(() => expect(localStorage.getItem(`cert-lesson::${module.id}`)).toBe('3'))
  expect(state.save).not.toHaveBeenCalled()
})

it('honors a read-only card boundary even when lesson identity otherwise matches', () => {
  render(<ChatLessonReader content={content} readOnly />)
  expect(screen.getByText(content.content)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Save my place' })).not.toBeInTheDocument()
  expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
  expect(state.save).not.toHaveBeenCalled()
})
