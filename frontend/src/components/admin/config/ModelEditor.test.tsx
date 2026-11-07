import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createRef } from 'react'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { ModelEditor, type ModelEditorHandle } from './ModelEditor'
import type { SystemConfigData } from '../../../api/admin'

// ---------------------------------------------------------------------------
// The Available Models panel, tested in isolation — which is the point of
// extracting it from ConfigTab (plan 013). Covers its own save path, its
// id-addressed writes (plan 011), and the imperative first-run hook the setup
// checklist uses.
// ---------------------------------------------------------------------------

const mockAddModel = vi.fn()
const mockUpdateModel = vi.fn()
const mockDeleteModel = vi.fn()
const mockSetDefaultModel = vi.fn()
const mockTestModel = vi.fn()
const mockProbeModel = vi.fn()
const mockSetLongDocumentModel = vi.fn()
const mockProbeSavedWindow = vi.fn()

vi.mock('../../../api/admin', () => ({
  addModel: (...a: unknown[]) => mockAddModel(...a),
  updateModel: (...a: unknown[]) => mockUpdateModel(...a),
  deleteModel: (...a: unknown[]) => mockDeleteModel(...a),
  setDefaultModel: (...a: unknown[]) => mockSetDefaultModel(...a),
  testModel: (...a: unknown[]) => mockTestModel(...a),
  probeModel: (...a: unknown[]) => mockProbeModel(...a),
  setLongDocumentModel: (...a: unknown[]) => mockSetLongDocumentModel(...a),
  probeSavedModelContextWindow: (...a: unknown[]) => mockProbeSavedWindow(...a),
}))

const mockConfirm = vi.fn()

vi.mock('../../shared/useConfirm', () => ({
  useConfirm: () => mockConfirm,
}))

type ModelList = SystemConfigData['available_models']

const MODELS: ModelList = [
  // Tag deliberately differs from the OpenAI preset's default tag ('openai'):
  // names and tags are one unique namespace (see modelIdentity.ts), so a
  // fixture holding the preset's tag would make every wizard-add collide.
  { id: 'model-alpha', name: 'gpt-4o', tag: 'gpt4o', external: true, thinking: false, api_protocol: 'openai', endpoint: 'https://api.openai.com/v1', context_window: 128000 },
  { id: 'model-beta', name: 'llama3.1', tag: 'ollama', external: false, thinking: false, api_protocol: 'ollama', endpoint: 'http://localhost:11434/v1', context_window: 32768 },
]

const onConfigPatch = vi.fn()
const onReadinessChange = vi.fn()
const onError = vi.fn()

function renderPanel(models: ModelList = MODELS, ref?: React.Ref<ModelEditorHandle>, longDocumentModel = '') {
  return render(
    <ModelEditor
      ref={ref}
      models={models}
      defaultModel="gpt-4o"
      longDocumentModel={longDocumentModel}
      onConfigPatch={onConfigPatch}
      onReadinessChange={onReadinessChange}
      error={null}
      onError={onError}
    />,
  )
}

beforeEach(() => {
  mockAddModel.mockReset()
  mockUpdateModel.mockReset()
  mockDeleteModel.mockReset().mockResolvedValue({ status: 'ok' })
  mockSetDefaultModel.mockReset().mockResolvedValue({ status: 'ok', default_model: '' })
  mockTestModel.mockReset().mockResolvedValue({ ok: true, checks: [], summary: 'Connected' })
  mockProbeModel.mockReset()
  mockSetLongDocumentModel.mockReset().mockResolvedValue({ status: 'ok', long_document_model: '' })
  mockConfirm.mockReset().mockResolvedValue(true)
  onConfigPatch.mockReset()
  onReadinessChange.mockReset()
  onError.mockReset()
})

describe('ModelEditor — list', () => {
  it('renders each model with its tag and marks the default', () => {
    renderPanel()

    // Scoped to the list's own name spans: model names also appear as <option>
    // values in the long-document-model picker below the list.
    expect(screen.getByText('gpt-4o', { selector: 'span' })).toBeInTheDocument()
    expect(screen.getByText('llama3.1', { selector: 'span' })).toBeInTheDocument()
    expect(screen.getByText('Default')).toBeInTheDocument()
    expect(screen.getByTitle('Remove as default')).toBeInTheDocument()
  })

  it('renders an empty state with no models', () => {
    renderPanel([])

    expect(screen.getByText('No models configured.')).toBeInTheDocument()
  })
})

describe('ModelEditor — save path', () => {
  it('adds a model through the provider wizard, then tests it by returned id', async () => {
    mockAddModel.mockResolvedValue({
      status: 'ok',
      models: [...MODELS, { id: 'model-gamma', name: 'gpt-4o-mini', tag: 'openai', external: true, thinking: false }],
    })

    renderPanel()
    fireEvent.click(screen.getByRole('button', { name: /Add Model/ }))

    // Step 1 — pick a provider; its preset fills in the technical fields.
    fireEvent.click(screen.getByRole('button', { name: /OpenAI GPT models from the OpenAI API\./ }))
    // Step 2 — a name, and the context window: OpenAI's API doesn't report
    // one, so the admin enters it from the model card.
    fireEvent.change(screen.getByLabelText('Model name'), { target: { value: 'gpt-4o-mini' } })
    fireEvent.change(screen.getByLabelText('Context window (tokens)'), { target: { value: '128000' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save & test connection' }))

    await waitFor(() => expect(mockAddModel).toHaveBeenCalledTimes(1))
    expect(mockAddModel).toHaveBeenCalledWith(expect.objectContaining({
      name: 'gpt-4o-mini',
      tag: 'openai',
      api_protocol: 'openai',
      endpoint: 'https://api.openai.com/v1',
      external: true,
      context_window: 128000,
      context_window_source: 'entered',
    }))

    // The new list is handed back to the parent, and the connection test runs
    // against the id the backend just returned.
    await waitFor(() => expect(onConfigPatch).toHaveBeenCalledTimes(1))
    const patch = onConfigPatch.mock.calls[0][0] as Record<string, unknown>
    expect((patch.available_models as ModelList).map(m => m.id)).toEqual(['model-alpha', 'model-beta', 'model-gamma'])
    expect('default_model' in patch).toBe(false)
    await waitFor(() => expect(mockTestModel).toHaveBeenCalledWith('model-gamma'))
    expect(onReadinessChange).toHaveBeenCalled()
  })

  it('blocks a save whose name or tag collides with another model, before any request', async () => {
    renderPanel()
    fireEvent.click(screen.getByRole('button', { name: /Add Model/ }))
    // The OpenAI preset fixes tag 'openai'; name it after model-alpha's tag
    // to collide on the name→tag axis instead — either axis must block.
    fireEvent.click(screen.getByRole('button', { name: /OpenAI GPT models from the OpenAI API\./ }))
    fireEvent.change(screen.getByLabelText('Model name'), { target: { value: 'gpt4o' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save & test connection' }))

    await waitFor(() => expect(onError).toHaveBeenCalled())
    expect(String(onError.mock.calls.at(-1)?.[0])).toMatch(/already used/)
    expect(mockAddModel).not.toHaveBeenCalled()
  })

  it('updates an existing model by its stable id, not its position (plan 011)', async () => {
    mockUpdateModel.mockResolvedValue({ status: 'ok', models: MODELS })

    renderPanel()
    fireEvent.click(screen.getAllByTitle('Edit model')[1])
    fireEvent.click(screen.getByRole('button', { name: 'Save & test connection' }))

    await waitFor(() => expect(mockUpdateModel).toHaveBeenCalledTimes(1))
    expect(mockUpdateModel.mock.calls[0][0]).toBe('model-beta')
    expect(mockUpdateModel.mock.calls[0][1]).toEqual(expect.objectContaining({ name: 'llama3.1', tag: 'ollama' }))
  })

  it('refuses to save a model with no name and reports it upward', async () => {
    renderPanel()
    fireEvent.click(screen.getByRole('button', { name: /Add Model/ }))
    fireEvent.click(screen.getByRole('button', { name: /OpenAI GPT models from the OpenAI API\./ }))
    fireEvent.click(screen.getByRole('button', { name: 'Save & test connection' }))

    await waitFor(() => expect(onError).toHaveBeenCalledWith('Enter a model name'))
    expect(mockAddModel).not.toHaveBeenCalled()
  })
})

// ---------------------------------------------------------------------------
// Wrong-record race: delete + edit are both reachable at once. Editing a
// model must never resolve to whatever record now happens to occupy that
// row's old position after another delete reshuffles the list — it must
// track the model actually being edited, by id, or refuse the save.
// ---------------------------------------------------------------------------

describe('ModelEditor — edit survives a concurrent delete (wrong-record race)', () => {
  const THREE: ModelList = [
    { id: 'model-alpha', name: 'gpt-4o', tag: 'openai', external: true, thinking: false, api_protocol: 'openai', endpoint: 'https://api.openai.com/v1', context_window: 128000 },
    { id: 'model-beta', name: 'llama3.1', tag: 'ollama', external: false, thinking: false, api_protocol: 'ollama', endpoint: 'http://localhost:11434/v1', context_window: 32768 },
    { id: 'model-gamma', name: 'qwen3', tag: 'vllm', external: false, thinking: false, api_protocol: 'vllm', endpoint: 'http://localhost:8000/v1', context_window: 32768 },
  ]

  it('reshuffle: still updates the originally-edited model, never the one that slid into its old slot', async () => {
    mockUpdateModel.mockResolvedValue({ status: 'ok', models: [THREE[1], THREE[2]] })

    const { rerender } = renderPanel(THREE)

    // Open the edit form on row 1 — model-beta ("llama3.1").
    fireEvent.click(screen.getAllByTitle('Edit model')[1])
    expect(screen.getByLabelText('Model name')).toHaveValue('llama3.1')

    // Another admin deletes row 0 (model-alpha) while this form is still
    // open. Row 1 in the new list is now model-gamma ("qwen3") — an
    // index-based lookup at save time would silently target that instead.
    rerender(
      <ModelEditor
        models={[THREE[1], THREE[2]]}
        defaultModel="gpt-4o"
        onConfigPatch={onConfigPatch}
        onReadinessChange={onReadinessChange}
        error={null}
        onError={onError}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Save & test connection' }))

    await waitFor(() => expect(mockUpdateModel).toHaveBeenCalledTimes(1))
    // Must be the model the admin actually opened — never the one that
    // reshuffled into its old list position.
    expect(mockUpdateModel.mock.calls[0][0]).toBe('model-beta')
    expect(mockUpdateModel.mock.calls[0][0]).not.toBe('model-gamma')
  })

  it('deletion of the edited model itself: refuses the save instead of guessing', async () => {
    const { rerender } = renderPanel(THREE)

    // Open the edit form on row 1 — model-beta.
    fireEvent.click(screen.getAllByTitle('Edit model')[1])
    expect(screen.getByLabelText('Model name')).toHaveValue('llama3.1')

    // model-beta itself gets deleted by someone else while the form is open.
    rerender(
      <ModelEditor
        models={[THREE[0], THREE[2]]}
        defaultModel="gpt-4o"
        onConfigPatch={onConfigPatch}
        onReadinessChange={onReadinessChange}
        error={null}
        onError={onError}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Save & test connection' }))

    await waitFor(() => expect(onError).toHaveBeenCalledWith('Could not find the model to update — refresh and try again.'))
    expect(mockUpdateModel).not.toHaveBeenCalled()
  })
})


describe('ModelEditor — long-document model', () => {
  // A grant proposal arrives as one file. When it doesn't fit the chosen
  // model, the planner trims the middle and the answer comes from part of the
  // document. Nominating a bigger model is how an admin prevents that — but it
  // has to be an explicit choice, so there is a control for it.

  it('nominates a model to use when a document does not fit', async () => {
    renderPanel()
    fireEvent.change(screen.getByLabelText(/Long-document model/i), {
      target: { value: 'llama3.1' },
    })
    await waitFor(() => expect(mockSetLongDocumentModel).toHaveBeenCalledWith('llama3.1'))
  })

  it('can be cleared, which turns routing off', async () => {
    renderPanel(MODELS, undefined, 'llama3.1')
    fireEvent.change(screen.getByLabelText(/Long-document model/i), { target: { value: '' } })
    await waitFor(() => expect(mockSetLongDocumentModel).toHaveBeenCalledWith(''))
  })

  it('offers every configured model as a choice', () => {
    renderPanel()
    const select = screen.getByLabelText(/Long-document model/i) as HTMLSelectElement
    const values = Array.from(select.options).map(o => o.value)
    expect(values).toContain('gpt-4o')
    expect(values).toContain('llama3.1')
  })
})

describe('ModelEditor — sampling temperature', () => {
  // Temperature is the one sampling control the product never sent, so the
  // same question on the same document could return a different answer.
  // Nothing here is useful unless the value actually reaches the save call.

  it('sends the temperature an admin typed', async () => {
    mockUpdateModel.mockResolvedValue({ status: 'ok', models: MODELS })

    renderPanel()
    fireEvent.click(screen.getAllByTitle('Edit model')[1])
    fireEvent.change(screen.getByLabelText(/Temperature/i), { target: { value: '0.2' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save & test connection' }))

    await waitFor(() => expect(mockUpdateModel).toHaveBeenCalledTimes(1))
    expect(mockUpdateModel.mock.calls[0][1]).toEqual(
      expect.objectContaining({ temperature: 0.2 }),
    )
  })

  it('sends 0 rather than dropping it as empty', async () => {
    // 0 is the deterministic setting — the entire reason for the field. A
    // `value || undefined` guard would silently discard it.
    mockUpdateModel.mockResolvedValue({ status: 'ok', models: MODELS })

    renderPanel()
    fireEvent.click(screen.getAllByTitle('Edit model')[1])
    fireEvent.change(screen.getByLabelText(/Temperature/i), { target: { value: '0' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save & test connection' }))

    await waitFor(() => expect(mockUpdateModel).toHaveBeenCalledTimes(1))
    expect(mockUpdateModel.mock.calls[0][1]).toEqual(
      expect.objectContaining({ temperature: 0 }),
    )
  })

  it('sends null when the field is left blank, so the provider default applies', async () => {
    mockUpdateModel.mockResolvedValue({ status: 'ok', models: MODELS })

    renderPanel()
    fireEvent.click(screen.getAllByTitle('Edit model')[1])
    fireEvent.change(screen.getByLabelText(/Temperature/i), { target: { value: '' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save & test connection' }))

    await waitFor(() => expect(mockUpdateModel).toHaveBeenCalledTimes(1))
    expect(mockUpdateModel.mock.calls[0][1]).toEqual(
      expect.objectContaining({ temperature: null }),
    )
  })
})

describe('ModelEditor — delete and default', () => {
  it('deletes by id and hands the parent the remaining list', async () => {
    renderPanel()
    fireEvent.click(screen.getAllByTitle('Delete model')[1])

    await waitFor(() => expect(mockDeleteModel).toHaveBeenCalledWith('model-beta'))
    await waitFor(() => expect(onConfigPatch).toHaveBeenCalledTimes(1))
    const patch = onConfigPatch.mock.calls[0][0] as Record<string, unknown>
    expect((patch.available_models as ModelList).map(m => m.id)).toEqual(['model-alpha'])
    expect(onReadinessChange).toHaveBeenCalled()
  })

  it('does not delete when the confirmation is declined', async () => {
    mockConfirm.mockResolvedValue(false)
    renderPanel()
    fireEvent.click(screen.getAllByTitle('Delete model')[1])

    await waitFor(() => expect(mockConfirm).toHaveBeenCalled())
    expect(mockDeleteModel).not.toHaveBeenCalled()
    expect(onConfigPatch).not.toHaveBeenCalled()
  })

  it('toggles the default model off when the current default is clicked', async () => {
    renderPanel()
    fireEvent.click(screen.getByTitle('Remove as default'))

    await waitFor(() => expect(mockSetDefaultModel).toHaveBeenCalledWith(''))
    expect(onConfigPatch).toHaveBeenCalledWith({ default_model: '' })
  })
})

describe('ModelEditor — first-run wizard hook', () => {
  it('opens the wizard when the setup checklist asks and no model exists', () => {
    const ref = createRef<ModelEditorHandle>()
    renderPanel([], ref)

    expect(screen.queryByText('Add a model')).not.toBeInTheDocument()
    act(() => ref.current?.openFirstRunWizard())
    expect(screen.getByText('Add a model')).toBeInTheDocument()
  })

  it('leaves the panel alone when models already exist', () => {
    const ref = createRef<ModelEditorHandle>()
    renderPanel(MODELS, ref)

    act(() => ref.current?.openFirstRunWizard())
    expect(screen.queryByText('Add a model')).not.toBeInTheDocument()
  })

  it('does not clobber an open draft', () => {
    const ref = createRef<ModelEditorHandle>()
    renderPanel([], ref)

    fireEvent.click(screen.getByRole('button', { name: /Add Model/ }))
    fireEvent.click(screen.getByRole('button', { name: /OpenAI GPT models from the OpenAI API\./ }))
    fireEvent.change(screen.getByLabelText('Model name'), { target: { value: 'half-typed' } })

    act(() => ref.current?.openFirstRunWizard())
    expect(screen.getByLabelText('Model name')).toHaveValue('half-typed')
  })
})


// Every context budget depends on the window, so it is detected from the
// server or entered, never defaulted (ticket: a 1M-class model on dev was
// budgeted as 65,536 tokens and cut a spreadsheet on the first question).
describe('ModelEditor — context window', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockAddModel.mockResolvedValue({ status: 'ok', models: [...MODELS, { id: 'model-new', name: 'gpt-oss-120b', tag: 'openai', external: true, thinking: false }] })
    mockTestModel.mockResolvedValue({ ok: true, checks: [], summary: 'ok' })
  })

  function openOpenAiForm(name: string) {
    renderPanel()
    fireEvent.click(screen.getByRole('button', { name: /Add Model/ }))
    fireEvent.click(screen.getByRole('button', { name: /OpenAI GPT models from the OpenAI API\./ }))
    fireEvent.change(screen.getByLabelText('Model name'), { target: { value: name } })
  }

  it('starts empty and fills in the window the server reports, without a click', async () => {
    mockProbeModel.mockResolvedValue({ context_window: 131072, source: 'vllm_max_model_len', detail: null, raw: null })
    openOpenAiForm('gpt-oss-120b')
    const field = screen.getByLabelText('Context window (tokens)') as HTMLInputElement
    expect(field.value).toBe('')
    await waitFor(() => expect(field.value).toBe('131072'), { timeout: 3000 })
    expect(screen.getByText(/Detected 131,072 tokens from the server/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Save & test connection' }))
    await waitFor(() => expect(mockAddModel).toHaveBeenCalledWith(expect.objectContaining({ context_window: 131072, context_window_source: 'detected' })))
  })

  it('refuses to save without a window when the server reports none', async () => {
    mockProbeModel.mockResolvedValue({ context_window: null, source: 'openai_no_field', detail: 'No context length reported.', raw: null })
    openOpenAiForm('gpt-4o-mini')
    fireEvent.click(screen.getByRole('button', { name: 'Save & test connection' }))
    await waitFor(() => expect(onError).toHaveBeenCalledWith(expect.stringMatching(/Enter the model's context window/)))
    expect(mockAddModel).not.toHaveBeenCalled()
  })

  it('asks before replacing a window the admin typed', async () => {
    mockProbeModel.mockResolvedValue({ context_window: 65536, source: 'vllm_max_model_len', detail: null, raw: null })
    openOpenAiForm('kimi-k3')
    const field = screen.getByLabelText('Context window (tokens)') as HTMLInputElement
    fireEvent.change(field, { target: { value: '131072' } })
    await waitFor(() => expect(screen.getByText(/The server reports 65,536 tokens; you entered 131,072/)).toBeInTheDocument(), { timeout: 3000 })
    expect(field.value).toBe('131072')
    fireEvent.click(screen.getByRole('button', { name: 'Use 65,536' }))
    expect(field.value).toBe('65536')
  })

  it('flags a saved model whose window was never confirmed, and checks it in one click', async () => {
    const legacy = { ...MODELS[0], context_window_status: 'unconfirmed' as const }
    const fixed = { ...legacy, context_window: 128000, context_window_source: 'detected' as const, context_window_status: 'detected' as const }
    mockProbeSavedWindow.mockResolvedValue({ probe: { context_window: 128000, source: 'openrouter_context_length', detail: null, raw: null }, applied: true, entered_differs: false, models: [fixed, MODELS[1]] })
    renderPanel([legacy, MODELS[1]])
    expect(screen.getByText('Context window not confirmed (128,000)')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: "Check gpt-4o's context window with its server" }))
    await waitFor(() => expect(mockProbeSavedWindow).toHaveBeenCalledWith('model-alpha', false))
    expect(await screen.findByText('Detected 128,000 tokens from the server.')).toBeInTheDocument()
    expect(onConfigPatch).toHaveBeenCalledWith({ available_models: [fixed, MODELS[1]] })
  })
})
