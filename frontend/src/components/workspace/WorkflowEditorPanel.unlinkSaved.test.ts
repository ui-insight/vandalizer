import { describe, expect, it } from 'vitest'
import { unlinkSavedItem } from './WorkflowEditorPanel'

// Support ticket: unlinking a saved prompt dropped the link and the text with
// it, leaving a named Prompt step with no instruction at all. Unlink is meant
// to detach into an editable copy.
describe('unlinkSavedItem', () => {
  it('keeps the prompt text the step was running', () => {
    const next = unlinkSavedItem(
      { name: 'Summarize award', saved_prompt_uuid: 'p-1' },
      'saved_prompt_uuid', 'prompt',
      'Summarize the award notice in three bullets.',
    )

    expect(next.saved_prompt_uuid).toBeUndefined()
    expect(next.prompt).toBe('Summarize the award notice in three bullets.')
    // The name is the step's own; unlinking is not a rename.
    expect(next.name).toBe('Summarize award')
  })

  it('keeps the formatter template the same way', () => {
    const next = unlinkSavedItem(
      { name: 'Memo', saved_formatter_uuid: 'f-1' },
      'saved_formatter_uuid', 'format_template',
      '# {{title}}\n\n{{body}}',
    )

    expect(next.saved_formatter_uuid).toBeUndefined()
    expect(next.format_template).toBe('# {{title}}\n\n{{body}}')
  })

  it('writes nothing when the saved item has no content', () => {
    const next = unlinkSavedItem(
      { name: 'Empty', saved_prompt_uuid: 'p-1' }, 'saved_prompt_uuid', 'prompt', '',
    )

    expect(next.saved_prompt_uuid).toBeUndefined()
    expect('prompt' in next).toBe(false)
  })

  it('does not mutate the step it was given', () => {
    const data = { name: 'Summarize', saved_prompt_uuid: 'p-1' }
    unlinkSavedItem(data, 'saved_prompt_uuid', 'prompt', 'Do the thing.')

    expect(data.saved_prompt_uuid).toBe('p-1')
  })
})
