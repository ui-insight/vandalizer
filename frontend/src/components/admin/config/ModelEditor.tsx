import { useImperativeHandle, useState, type Ref } from 'react'
import {
  Cpu, Plus, Trash2, Pencil, RefreshCw,
  CheckCircle2, XCircle, ChevronDown, ChevronUp, Play, AlertCircle, Star,
} from 'lucide-react'
import { useConfirm } from '../../shared/useConfirm'
import {
  addModel, updateModel, deleteModel, setDefaultModel, testModel, probeModel,
} from '../../../api/admin'
import type { ModelTestResult, SystemConfigData } from '../../../api/admin'
import { ModelCharacterBars } from '../../ModelEffortPicker'
import { getModelIdentityError } from '../../../utils/modelIdentity'
import type { ModelInfo } from '../../../types/workflow'
import { sectionStyle, sectionHeaderStyle, sectionBodyStyle, labelStyle, inputStyle, checkStyle } from './styles'

// ──────────────────────────────────────────
// Model connectivity diagnostics
// ──────────────────────────────────────────

// Renders the step-by-step result of a model "Test" — on success, why the
// hook-up is healthy (protocol, endpoint, latency, tokens, the actual reply);
// on failure, a classified error with a plain-English cause and suggested fix.
function ModelTestDiagnostics({ result }: { result: ModelTestResult }) {
  const [showRaw, setShowRaw] = useState(false)
  const accent = result.ok ? '#16a34a' : '#dc2626'
  return (
    <div style={{
      padding: '12px 16px', fontSize: 13,
      background: result.ok ? '#f0fdf4' : '#fef2f2',
      border: '1px solid', borderTop: 'none',
      borderColor: result.ok ? '#bbf7d0' : '#fecaca',
      borderRadius: '0 0 var(--ui-radius, 12px) var(--ui-radius, 12px)',
    }}>
      <div style={{ fontWeight: 600, color: result.ok ? '#166534' : '#991b1b', marginBottom: 10 }}>
        {result.summary}
      </div>

      {/* Step-by-step checks */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
        {result.checks.map((c, idx) => (
          <div key={idx} style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
            {c.ok
              ? <CheckCircle2 size={15} style={{ color: '#16a34a', flexShrink: 0, marginTop: 1 }} />
              : <XCircle size={15} style={{ color: '#dc2626', flexShrink: 0, marginTop: 1 }} />}
            <span style={{ color: '#374151' }}>
              <span style={{ fontWeight: 600 }}>{c.label}:</span> {c.detail}
            </span>
          </div>
        ))}
      </div>

      {/* Success facts */}
      {result.ok && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 12 }}>
          {result.protocol && <DiagFact label="Protocol" value={result.protocol} />}
          {result.endpoint && <DiagFact label="Endpoint" value={result.endpoint} mono />}
          {typeof result.latency_ms === 'number' && <DiagFact label="Latency" value={`${result.latency_ms} ms`} />}
          {result.tokens?.total != null && <DiagFact label="Tokens" value={String(result.tokens.total)} />}
        </div>
      )}
      {result.ok && result.response_preview && (
        <div style={{ marginTop: 10, padding: '8px 10px', background: '#fff', border: '1px solid #d1fae5', borderRadius: 8, fontFamily: 'ui-monospace, monospace', fontSize: 12, color: '#374151' }}>
          <span style={{ color: '#9ca3af' }}>reply:</span> {result.response_preview}
        </div>
      )}

      {/* Failure guidance */}
      {!result.ok && result.error && (
        <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
            <AlertCircle size={15} style={{ color: accent, flexShrink: 0, marginTop: 1 }} />
            <div>
              <div style={{ fontWeight: 600, color: '#991b1b' }}>{result.error.title}</div>
              <div style={{ color: '#374151', marginTop: 2 }}>{result.error.why}</div>
            </div>
          </div>
          <div style={{ padding: '8px 10px', background: '#fff', border: '1px solid #fecaca', borderRadius: 8, color: '#374151' }}>
            <span style={{ fontWeight: 600, color: '#b91c1c' }}>Try this: </span>{result.error.fix}
          </div>
          {result.error.raw && (
            <div>
              <button
                onClick={() => setShowRaw(v => !v)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#6b7280', fontSize: 12, padding: 0, display: 'inline-flex', alignItems: 'center', gap: 4 }}
              >
                {showRaw ? <ChevronUp size={12} /> : <ChevronDown size={12} />} {showRaw ? 'Hide' : 'Show'} raw provider error
              </button>
              {showRaw && (
                <pre style={{ marginTop: 6, padding: '8px 10px', background: '#1f2937', color: '#f9fafb', borderRadius: 8, fontSize: 11, overflowX: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                  {result.error.raw}
                </pre>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function DiagFact({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '2px 8px', background: '#fff', border: '1px solid #e5e7eb', borderRadius: 9999, fontSize: 12 }}>
      <span style={{ color: '#9ca3af', fontWeight: 600 }}>{label}</span>
      <span style={{ color: '#374151', fontFamily: mono ? 'ui-monospace, monospace' : undefined }}>{value}</span>
    </span>
  )
}

// ──────────────────────────────────────────
// Model editor
// ──────────────────────────────────────────

// The editable shape of a single LLM model config row.
type ModelDraft = {
  name: string
  tag: string
  external: boolean
  thinking: boolean
  endpoint: string
  api_protocol: string
  api_key: string
  speed: string
  tier: string
  privacy: string
  supports_structured: boolean
  multimodal: boolean
  supports_pdf: boolean
  context_window: number
  // Optional per-model overrides. 0 = unset (backend uses system default /
  // computed value).
  request_timeout_seconds: number
  response_reserve_tokens: number
}

const EMPTY_MODEL_DRAFT: ModelDraft = {
  name: '', tag: '', external: false, thinking: false, endpoint: '', api_protocol: '', api_key: '',
  speed: '', tier: '', privacy: '', supports_structured: true, multimodal: false, supports_pdf: false,
  context_window: 128000, request_timeout_seconds: 0, response_reserve_tokens: 0,
}

// Provider presets power the "Add a Model" wizard. Selecting one fills in the
// technical fields (protocol, endpoint, external/privacy flags, sensible
// capability defaults) so admins only supply a model name and, for hosted APIs,
// a key. `apply` is merged into the draft; everything stays editable under
// "Advanced settings".
type ModelProviderPreset = {
  id: string
  label: string
  blurb: string
  needsKey: boolean
  needsEndpoint: boolean
  keyPlaceholder?: string
  keyHelp?: string
  namePlaceholder: string
  nameSuggestions?: string[]
  endpointPlaceholder?: string
  apply: Partial<ModelDraft>
}

const MODEL_PROVIDERS: ModelProviderPreset[] = [
  {
    id: 'google',
    label: 'Google (Gemini)',
    blurb: "Gemini models via Google AI Studio. Native integration — just a model name and key.",
    needsKey: true,
    needsEndpoint: false,
    keyPlaceholder: 'AIza… (AI Studio API key)',
    keyHelp: 'Create a key at aistudio.google.com → API keys.',
    namePlaceholder: 'gemini-2.5-flash',
    nameSuggestions: ['gemini-2.5-flash', 'gemini-2.5-pro'],
    apply: { api_protocol: 'google', external: true, privacy: 'external', endpoint: '', tag: 'google', multimodal: true, supports_pdf: true, context_window: 1048576 },
  },
  {
    id: 'openai',
    label: 'OpenAI',
    blurb: 'GPT models from the OpenAI API.',
    needsKey: true,
    needsEndpoint: false,
    keyPlaceholder: 'sk-…',
    namePlaceholder: 'gpt-4o',
    nameSuggestions: ['gpt-4o', 'gpt-4o-mini'],
    apply: { api_protocol: 'openai', external: true, privacy: 'external', endpoint: 'https://api.openai.com/v1', tag: 'openai', multimodal: true },
  },
  {
    id: 'anthropic',
    label: 'Anthropic (Claude)',
    blurb: 'Claude models via the native Anthropic API.',
    needsKey: true,
    needsEndpoint: false,
    keyPlaceholder: 'sk-ant-…',
    namePlaceholder: 'claude-…',
    apply: { api_protocol: 'anthropic', external: true, privacy: 'external', endpoint: '', tag: 'anthropic', multimodal: true },
  },
  {
    id: 'openrouter',
    label: 'OpenRouter',
    blurb: 'Any model routed through OpenRouter.',
    needsKey: true,
    needsEndpoint: false,
    keyPlaceholder: 'sk-or-…',
    namePlaceholder: 'anthropic/claude-…',
    apply: { api_protocol: 'openrouter', external: true, privacy: 'external', endpoint: '', tag: 'openrouter' },
  },
  {
    id: 'ollama',
    label: 'Ollama (self-hosted)',
    blurb: 'A model served locally by Ollama.',
    needsKey: false,
    needsEndpoint: true,
    namePlaceholder: 'llama3.1',
    nameSuggestions: ['llama3.1', 'mistral'],
    endpointPlaceholder: 'http://localhost:11434/v1',
    apply: { api_protocol: 'ollama', external: false, privacy: 'internal', endpoint: 'http://localhost:11434/v1', tag: 'ollama' },
  },
  {
    id: 'vllm',
    label: 'vLLM (self-hosted)',
    blurb: 'A model served by your own vLLM instance.',
    needsKey: false,
    needsEndpoint: true,
    namePlaceholder: 'qwen3',
    nameSuggestions: ['qwen3'],
    endpointPlaceholder: 'http://localhost:8000/v1',
    apply: { api_protocol: 'vllm', external: false, privacy: 'internal', endpoint: '', tag: 'vllm' },
  },
  {
    id: 'custom',
    label: 'Custom / OpenAI-compatible',
    blurb: 'Any other OpenAI-compatible endpoint. Full manual control.',
    needsKey: true,
    needsEndpoint: true,
    keyPlaceholder: 'API key (if required)',
    namePlaceholder: 'model name',
    endpointPlaceholder: 'https://…/v1',
    apply: { api_protocol: 'openai', external: true, privacy: 'external', endpoint: '', tag: 'custom' },
  },
]

// Best-effort match of an existing saved model back to a provider preset, so the
// Edit flow lands on the right guided fields.
function inferProviderId(m: { api_protocol?: string; external?: boolean; endpoint?: string }): string {
  const proto = (m.api_protocol || '').toLowerCase()
  if (proto === 'google') return 'google'
  if (proto === 'anthropic') return 'anthropic'
  if (proto === 'openrouter') return 'openrouter'
  if (proto === 'ollama') return 'ollama'
  if (proto === 'vllm') return 'vllm'
  if (proto === 'openai' && (m.endpoint || '').includes('api.openai.com')) return 'openai'
  return 'custom'
}

type ModelList = SystemConfigData['available_models']

/** Imperative surface the setup checklist needs — see `openFirstRunWizard`. */
export interface ModelEditorHandle {
  /** First-run: drop the admin straight into the guided wizard when the
   *  checklist sends them here and there is no model yet. No-op if a model
   *  exists or the form is already open (which would discard their draft). */
  openFirstRunWizard: () => void
}

export interface ModelEditorProps {
  models: ModelList
  defaultModel: string
  /** Merge a model-list / default-model change back into the parent's config. */
  onConfigPatch: (patch: { available_models?: ModelList; default_model?: string }) => void
  /** Re-grade the setup checklist after a change that can affect readiness. */
  onReadinessChange: () => void
  /** The tab-level error banner is shared with the parent; the wizard also
   *  renders it inline, so the message is passed in as well as out. */
  error: string | null
  onError: (message: string | null) => void
  ref?: Ref<ModelEditorHandle>
}

export function ModelEditor({
  models, defaultModel, onConfigPatch, onReadinessChange, error, onError, ref,
}: ModelEditorProps) {
  const confirm = useConfirm()

  const [modelTesting, setModelTesting] = useState<number | null>(null)
  // Keyed by model id (not list index/position) so a delete can never
  // misattribute another model's "Connected"/"Failed" badge to this one —
  // removing an entry removes exactly its own key, with nothing to reindex.
  const [modelTestResults, setModelTestResults] = useState<Record<string, ModelTestResult>>({})
  const [expandedModelTest, setExpandedModelTest] = useState<string | null>(null)

  // Add/edit model form
  const [showModelForm, setShowModelForm] = useState(false)
  // Holds the id of the model being edited (never a list index/position) —
  // delete and edit are both reachable at once, so resolving "which model is
  // this form for" from a position would drift the moment another delete
  // reshuffles the list out from under an open form. See handleSaveModel.
  const [editingModelId, setEditingModelId] = useState<string | null>(null)
  const [savingModel, setSavingModel] = useState(false)
  const [newModel, setNewModel] = useState<ModelDraft>({ ...EMPTY_MODEL_DRAFT })
  const [probingContext, setProbingContext] = useState(false)
  const [probeResult, setProbeResult] = useState<{ ok: boolean; message: string } | null>(null)
  // Add-a-Model wizard: step 1 = pick provider, step 2 = configure + save + test.
  const [wizardStep, setWizardStep] = useState<1 | 2>(1)
  const [wizardProviderId, setWizardProviderId] = useState<string | null>(null)
  const [modelTest, setModelTest] = useState<ModelTestResult | null>(null)
  const [wizardTesting, setWizardTesting] = useState(false)

  const handleProbeContextWindow = async () => {
    setProbingContext(true)
    setProbeResult(null)
    try {
      const existingModelId = editingModelId
      const result = await probeModel({
        name: newModel.name,
        endpoint: newModel.endpoint,
        api_protocol: newModel.api_protocol,
        api_key: newModel.api_key,
        existing_model_id: existingModelId,
      })
      if (result.context_window && result.context_window > 0) {
        setNewModel(prev => ({ ...prev, context_window: result.context_window as number }))
        setProbeResult({ ok: true, message: `Detected ${result.context_window.toLocaleString()} tokens (${result.source}).` })
      } else {
        setProbeResult({ ok: false, message: result.detail || `No context length reported (${result.source}).` })
      }
    } catch (e) {
      setProbeResult({ ok: false, message: e instanceof Error ? e.message : 'Probe failed' })
    } finally {
      setProbingContext(false)
    }
  }

  // Open the wizard fresh for a new model (provider-picker step).
  const openAddModelWizard = () => {
    setNewModel({ ...EMPTY_MODEL_DRAFT })
    setProbeResult(null)
    setModelTest(null)
    setWizardProviderId(null)
    setWizardStep(1)
    setEditingModelId(null)
    onError(null)
    setShowModelForm(true)
  }

  useImperativeHandle(ref, () => ({
    openFirstRunWizard: () => {
      if (models.length > 0 || showModelForm) return
      openAddModelWizard()
    },
  }))

  const closeModelForm = () => {
    setNewModel({ ...EMPTY_MODEL_DRAFT })
    setProbeResult(null)
    setModelTest(null)
    setWizardProviderId(null)
    setWizardStep(1)
    setShowModelForm(false)
    setEditingModelId(null)
    onError(null)
  }

  // Wizard step 1 → 2: apply the provider's preset onto a clean draft. Starting
  // from EMPTY (keeping only a model name the admin may have typed) prevents a
  // previously-picked provider's flags — e.g. Google's 1M context window — from
  // leaking in when they switch providers via "Change".
  const selectProvider = (p: ModelProviderPreset) => {
    setWizardProviderId(p.id)
    setNewModel(prev => ({ ...EMPTY_MODEL_DRAFT, name: prev.name, ...p.apply }))
    setProbeResult(null)
    setModelTest(null)
    onError(null)
    setWizardStep(2)
  }

  const handleSaveModel = async () => {
    if (!newModel.name.trim()) {
      onError('Enter a model name')
      return
    }
    if (!newModel.tag.trim()) {
      onError('A tag is required (set one under Advanced settings)')
      return
    }
    // Names and tags are one namespace: a collision makes a user's saved model
    // selector resolve to whichever model comes first. The backend rejects this
    // with a 409; warn here so the admin sees it before submitting.
    const identityError = getModelIdentityError(
      newModel.name, newModel.tag, models,
      editingModelId !== null ? models.findIndex(m => m.id === editingModelId) : null,
    )
    if (identityError) {
      onError(identityError)
      return
    }
    setSavingModel(true)
    onError(null)
    setModelTest(null)
    try {
      let res
      // Snapshot which ids exist *before* the write, so a newly-added model
      // can be identified by set difference afterward — never by assuming
      // the backend appends it at the end of the response's list.
      const priorIds = new Set(models.map(m => m.id))
      if (editingModelId !== null) {
        const modelId = editingModelId
        // The held id may no longer be in the list — e.g. another admin (or
        // this admin, in another tab) deleted it while this form was open.
        // Refuse rather than silently resolving to whatever now sits at some
        // stale position.
        if (!models.some(m => m.id === modelId)) {
          onError('Could not find the model to update — refresh and try again.')
          setSavingModel(false)
          return
        }
        res = await updateModel(modelId, newModel)
      } else {
        res = await addModel(newModel)
      }
      const resDefault = (res as { default_model?: string }).default_model
      onConfigPatch({
        available_models: res.models,
        ...(resDefault !== undefined ? { default_model: resDefault } : {}),
      })

      // Resolve which model we just saved, by id — for an edit we already
      // hold that id; for a new model, it's whichever id in the response
      // wasn't present before the call.
      const savedModelId = editingModelId !== null
        ? editingModelId
        : res.models.find(m => !priorIds.has(m.id))?.id

      if (!savedModelId) {
        const count = res.models.length
        onError(`Model saved, but the response didn't let us identify which one to test (received ${count} model${count === 1 ? '' : 's'}, none new). Refresh and test it from the list.`)
        setEditingModelId(null)
        onReadinessChange()
        return
      }

      // The model is now saved — subsequent edits/tests target its id.
      setEditingModelId(savedModelId)
      onReadinessChange()
      // Auto-run a connection test so the admin gets a clear pass/fail without
      // having to know where the test button lives. The test-model route is
      // id-addressed.
      setWizardTesting(true)
      try {
        const t = await testModel(savedModelId)
        setModelTest(t)
      } catch (e) {
        setModelTest({
          ok: false,
          checks: [],
          summary: 'Saved, but the connection test could not run.',
          error: { category: 'client', title: 'Test request failed', why: e instanceof Error ? e.message : 'Unknown error', fix: 'The model is saved. Re-run the test from the model list, or check your network.', raw: '' },
        })
      } finally {
        setWizardTesting(false)
      }
    } catch (e) {
      onError(e instanceof Error ? e.message : 'Failed to save model')
    } finally {
      setSavingModel(false)
    }
  }

  const handleEditModel = (index: number) => {
    const m = models[index]
    if (!m) return
    setNewModel({
      name: m.name,
      tag: m.tag,
      external: m.external,
      thinking: m.thinking,
      endpoint: m.endpoint || '',
      api_protocol: m.api_protocol || '',
      api_key: m.api_key || '',
      speed: m.speed || '',
      tier: m.tier || '',
      privacy: m.privacy || '',
      supports_structured: m.supports_structured !== false,
      multimodal: !!m.multimodal,
      supports_pdf: !!m.supports_pdf,
      context_window: typeof m.context_window === 'number' && m.context_window > 0 ? m.context_window : 128000,
      request_timeout_seconds: typeof m.request_timeout_seconds === 'number' && m.request_timeout_seconds > 0 ? m.request_timeout_seconds : 0,
      response_reserve_tokens: typeof m.response_reserve_tokens === 'number' && m.response_reserve_tokens > 0 ? m.response_reserve_tokens : 0,
    })
    setProbeResult(null)
    setModelTest(null)
    setWizardProviderId(inferProviderId(m))
    setWizardStep(2)          // edit skips the provider picker
    setEditingModelId(m.id)
    setShowModelForm(true)
  }

  const handleDeleteModel = async (index: number) => {
    const model = models[index]
    const ok = await confirm({
      title: 'Delete model?',
      message: (
        <>
          Are you sure you want to delete the model <strong>{model?.name || 'this model'}</strong>? Workflows and chats configured to use it will fail until reconfigured.
        </>
      ),
      confirmLabel: 'Delete',
      destructive: true,
    })
    if (!ok) return
    if (!model?.id) {
      onError('Could not find the model to delete — refresh and try again.')
      return
    }
    try {
      const res = await deleteModel(model.id)
      const remaining = [...models]
      remaining.splice(index, 1)
      onConfigPatch({
        available_models: remaining,
        ...(res.default_model !== undefined ? { default_model: res.default_model } : {}),
      })
      // Dropping a model can clear the only configured LLM — re-grade setup.
      setModelTestResults(prev => { const next = { ...prev }; delete next[model.id]; return next })
      onReadinessChange()
    } catch (e) {
      onError(e instanceof Error ? e.message : 'Failed to delete model')
    }
  }

  const handleSetDefaultModel = async (name: string) => {
    try {
      // Toggle off if clicking the current default.
      const next = defaultModel === name ? '' : name
      const res = await setDefaultModel(next)
      onConfigPatch({ default_model: res.default_model })
      onReadinessChange()
    } catch (e) {
      onError(e instanceof Error ? e.message : 'Failed to set default model')
    }
  }

  const handleTestModel = async (index: number) => {
    // The test-model backend route is now id-addressed, same as the model
    // PUT/DELETE routes — a list-position shift between load and request
    // (e.g. another admin's delete) can no longer make this test run
    // against, and badge as "Connected", a different model. `index` is only
    // used here to key the row's local spinner state and to resolve the id.
    const modelId = models[index]?.id
    if (!modelId) return
    setModelTesting(index)
    setModelTestResults(prev => { const next = { ...prev }; delete next[modelId]; return next })
    try {
      const res = await testModel(modelId)
      setModelTestResults(prev => ({ ...prev, [modelId]: res }))
      // Auto-expand so the admin sees the breakdown — especially on failure.
      setExpandedModelTest(modelId)
      // A successful test means readiness may have changed.
      if (res.ok) onReadinessChange()
    } catch (e) {
      // Transport-level failure (network/permission) — synthesize a result.
      const message = e instanceof Error ? e.message : 'Test failed'
      setModelTestResults(prev => ({
        ...prev,
        [modelId]: {
          ok: false,
          checks: [{ label: 'Request', ok: false, detail: message }],
          summary: message,
          error: { category: 'transport', title: 'Could not run the test', why: message, fix: 'Check that you are still signed in as an admin and the backend is reachable.', raw: message },
        },
      }))
      setExpandedModelTest(modelId)
    } finally {
      setModelTesting(null)
    }
  }

  return (
    <div id="cfg-models" style={sectionStyle}>
      <div style={sectionHeaderStyle}>
        <Cpu size={18} color="#6b7280" /> Available Models
        <div style={{ flex: 1 }} />
        <button
          onClick={() => { if (showModelForm) { closeModelForm() } else { openAddModelWizard() } }}
          style={{
            display: 'flex', alignItems: 'center', gap: 4, padding: '6px 12px',
            borderRadius: 'var(--ui-radius, 12px)', border: '1px solid #d1d5db',
            fontSize: 13, fontWeight: 500, cursor: 'pointer', background: '#fff',
          }}
        >
          <Plus size={14} /> Add Model
        </button>
      </div>
      <div style={sectionBodyStyle}>
        {models && models.length > 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {models.map((m, i) => {
              const test = modelTestResults[m.id]
              const expanded = expandedModelTest === m.id
              return (
              <div key={i} style={{ display: 'flex', flexDirection: 'column' }}>
              <div style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                padding: '10px 16px',
                background: test ? (test.ok ? '#f0fdf4' : '#fef2f2') : '#f9fafb',
                borderRadius: expanded ? 'var(--ui-radius, 12px) var(--ui-radius, 12px) 0 0' : 'var(--ui-radius, 12px)',
                border: '1px solid',
                borderColor: test ? (test.ok ? '#bbf7d0' : '#fecaca') : '#e5e7eb',
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                  {/* Identity & capability badges */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                    <span style={{ fontSize: 14, fontWeight: 600, color: '#111' }}>{m.name}</span>
                    <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 9999, background: '#f3f4f6', color: '#6b7280', fontWeight: 600 }}>{m.tag}</span>
                    {defaultModel === m.name && (
                      <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 9999, background: '#fef9c3', color: '#854d0e', fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                        <Star size={11} fill="currentColor" /> Default
                      </span>
                    )}
                    {m.external && (
                      <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 9999, background: '#fef3c7', color: '#92400e', fontWeight: 600 }}>External</span>
                    )}
                    {m.thinking && (
                      <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 9999, background: '#dbeafe', color: '#1e40af', fontWeight: 600 }}>Thinking</span>
                    )}
                    {m.multimodal && (
                      <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 9999, background: '#ede9fe', color: '#5b21b6', fontWeight: 600 }}>Multimodal</span>
                    )}
                    {m.supports_pdf && (
                      <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 9999, background: '#fce7f3', color: '#9d174d', fontWeight: 600 }}>PDF Input</span>
                    )}
                    {m.api_protocol && (
                      <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 9999, background: '#e0e7ff', color: '#3730a3', fontWeight: 600 }}>{m.api_protocol}</span>
                    )}
                    {m.api_key && (
                      <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 9999, background: '#d1fae5', color: '#065f46', fontWeight: 600 }}>API Key ✓</span>
                    )}
                    {m.endpoint && (
                      <span style={{ fontSize: 11, color: '#9ca3af', fontFamily: 'ui-monospace, monospace' }}>{m.endpoint}</span>
                    )}
                  </div>
                  {/* Characteristic bars (replaces speed / tier / privacy pills) */}
                  <ModelCharacterBars model={m as ModelInfo} />
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                  {test && (
                    <button
                      onClick={() => setExpandedModelTest(expanded ? null : m.id)}
                      style={{
                        display: 'inline-flex', alignItems: 'center', gap: 4, marginRight: 4,
                        padding: '3px 8px', borderRadius: 9999, cursor: 'pointer', border: '1px solid',
                        borderColor: test.ok ? '#86efac' : '#fca5a5',
                        background: test.ok ? '#dcfce7' : '#fee2e2',
                        color: test.ok ? '#166534' : '#991b1b', fontSize: 12, fontWeight: 600,
                      }}
                      title={expanded ? 'Hide details' : 'Show details'}
                    >
                      {test.ok ? <CheckCircle2 size={13} /> : <XCircle size={13} />}
                      <span style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {test.ok ? 'Connected' : (test.error?.title || 'Failed')}
                      </span>
                      {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                    </button>
                  )}
                  <button
                    onClick={() => handleSetDefaultModel(m.name)}
                    style={{
                      background: 'none', border: 'none', cursor: 'pointer',
                      color: defaultModel === m.name ? '#ca8a04' : '#9ca3af',
                      padding: 4,
                    }}
                    title={defaultModel === m.name ? 'Remove as default' : 'Set as default model'}
                  >
                    <Star size={16} fill={defaultModel === m.name ? 'currentColor' : 'none'} />
                  </button>
                  <button
                    onClick={() => handleTestModel(i)}
                    disabled={modelTesting === i}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', color: modelTesting === i ? '#9ca3af' : '#6b7280', padding: 4 }}
                    title={modelTesting === i ? 'Testing...' : 'Test model'}
                  >
                    {modelTesting === i ? <RefreshCw size={16} className="animate-spin" /> : <Play size={16} />}
                  </button>
                  <button
                    onClick={() => handleEditModel(i)}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#6b7280', padding: 4 }}
                    title="Edit model"
                  >
                    <Pencil size={16} />
                  </button>
                  <button
                    onClick={() => handleDeleteModel(i)}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#ef4444', padding: 4 }}
                    title="Delete model"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              </div>
              {expanded && test && <ModelTestDiagnostics result={test} />}
              </div>
              )
            })}
          </div>
        ) : (
          <div style={{ fontSize: 13, color: '#6b7280' }}>No models configured.</div>
        )}

        {showModelForm && (() => {
          const prov = MODEL_PROVIDERS.find(p => p.id === wizardProviderId) ?? null
          const isEditing = editingModelId !== null
          const needsKey = prov?.needsKey ?? true
          const needsEndpoint = prov?.needsEndpoint ?? false
          const secondaryBtn = {
            padding: '8px 16px', borderRadius: 'var(--ui-radius, 12px)', border: '1px solid #d1d5db',
            background: '#fff', fontSize: 13, cursor: 'pointer',
          } as const
          const primaryBtn = {
            padding: '8px 16px', borderRadius: 'var(--ui-radius, 12px)', border: 'none',
            background: 'var(--highlight-color, #eab308)', color: 'var(--highlight-text-color, #000)',
            fontSize: 13, fontWeight: 600, cursor: 'pointer',
          } as const
          const checkboxLabel = { display: 'flex', alignItems: 'center', fontSize: 14, cursor: 'pointer' } as const
          return (
          <div style={{ marginTop: 16, padding: 16, background: '#f9fafb', borderRadius: 'var(--ui-radius, 12px)', border: '1px solid #e5e7eb' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
              <div style={{ fontSize: 13, fontWeight: 600 }}>{isEditing ? 'Edit model' : 'Add a model'}</div>
              {!isEditing && (
                <div style={{ fontSize: 12, color: '#6b7280' }}>
                  {wizardStep === 1 ? 'Step 1 of 2 · Choose a provider' : 'Step 2 of 2 · Configure'}
                </div>
              )}
            </div>

            {/* STEP 1 — provider picker (new models only) */}
            {wizardStep === 1 && !isEditing && (
              <>
                <div style={{ fontSize: 13, color: '#6b7280', marginBottom: 12 }}>
                  Choose where this model runs — we&rsquo;ll fill in the technical settings for you.
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                  {MODEL_PROVIDERS.map(p => (
                    <button
                      key={p.id}
                      type="button"
                      onClick={() => selectProvider(p)}
                      style={{ textAlign: 'left', padding: '12px 14px', borderRadius: 'var(--ui-radius, 12px)', border: '1px solid #e5e7eb', background: '#fff', cursor: 'pointer' }}
                    >
                      <div style={{ fontSize: 14, fontWeight: 600, color: '#111827' }}>{p.label}</div>
                      <div style={{ fontSize: 12, color: '#6b7280', marginTop: 3 }}>{p.blurb}</div>
                    </button>
                  ))}
                </div>
                <div style={{ marginTop: 14 }}>
                  <button onClick={closeModelForm} style={secondaryBtn}>Cancel</button>
                </div>
              </>
            )}

            {/* STEP 2 — configure, save, test */}
            {wizardStep === 2 && (
              <>
                {prov && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
                    <span style={{ fontSize: 12, padding: '3px 10px', borderRadius: 999, background: '#eef2ff', color: '#3730a3', fontWeight: 600 }}>{prov.label}</span>
                    {!isEditing && (
                      <button type="button" onClick={() => { setWizardStep(1); setModelTest(null) }} style={{ fontSize: 12, color: '#4f46e5', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>Change</button>
                    )}
                  </div>
                )}

                {/* Guided fields */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  <div>
                    <label htmlFor="admin-model-name" style={labelStyle}>Model name</label>
                    <input id="admin-model-name" value={newModel.name} onChange={e => { const v = e.target.value; setNewModel(prev => ({ ...prev, name: v })) }} placeholder={prov?.namePlaceholder ?? 'model name'} style={inputStyle} />
                    {prov?.nameSuggestions && prov.nameSuggestions.length > 0 && (
                      <div style={{ display: 'flex', gap: 6, marginTop: 6, flexWrap: 'wrap' }}>
                        {prov.nameSuggestions.map(s => (
                          <button key={s} type="button" onClick={() => setNewModel(prev => ({ ...prev, name: s }))} style={{ fontSize: 12, padding: '3px 10px', borderRadius: 999, border: '1px solid #d1d5db', background: '#fff', cursor: 'pointer', color: '#374151' }}>{s}</button>
                        ))}
                      </div>
                    )}
                  </div>

                  {needsKey && (
                    <div>
                      <label htmlFor="admin-model-apikey" style={labelStyle}>API key</label>
                      <input id="admin-model-apikey" type="password" autoComplete="new-password" data-1p-ignore data-lpignore="true" data-bwignore name="vandalizer-model-api-key" value={newModel.api_key} onChange={e => { const v = e.target.value; setNewModel(prev => ({ ...prev, api_key: v })) }} placeholder={prov?.keyPlaceholder ?? 'API key'} style={inputStyle} />
                      {prov?.keyHelp && <div style={{ fontSize: 11, color: '#6b7280', marginTop: 4 }}>{prov.keyHelp}</div>}
                    </div>
                  )}

                  {needsEndpoint && (
                    <div>
                      <label htmlFor="admin-model-endpoint" style={labelStyle}>Endpoint</label>
                      <input id="admin-model-endpoint" value={newModel.endpoint} onChange={e => { const v = e.target.value; setNewModel(prev => ({ ...prev, endpoint: v })) }} placeholder={prov?.endpointPlaceholder ?? 'https://…/v1'} style={inputStyle} />
                    </div>
                  )}

                  <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
                    <label style={checkboxLabel}>
                      <input type="checkbox" checked={newModel.multimodal} onChange={e => { const v = e.target.checked; setNewModel(prev => ({ ...prev, multimodal: v, supports_pdf: v ? prev.supports_pdf : false })) }} style={checkStyle} />
                      Handles images / PDFs
                    </label>
                    <label style={checkboxLabel}>
                      <input type="checkbox" checked={newModel.thinking} onChange={e => { const v = e.target.checked; setNewModel(prev => ({ ...prev, thinking: v })) }} style={checkStyle} />
                      Extended thinking
                    </label>
                  </div>
                </div>

                {/* Advanced settings — everything from the old form lives here */}
                <details style={{ marginTop: 14 }}>
                  <summary style={{ cursor: 'pointer', fontSize: 13, color: '#4b5563', fontWeight: 500 }}>Advanced settings</summary>
                  <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 12 }}>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                      <div>
                        <label htmlFor="admin-model-tag" style={labelStyle}>Tag</label>
                        <input id="admin-model-tag" value={newModel.tag} onChange={e => { const v = e.target.value; setNewModel(prev => ({ ...prev, tag: v })) }} placeholder="provider" style={inputStyle} />
                      </div>
                      <div>
                        <label htmlFor="admin-model-protocol" style={labelStyle}>API protocol</label>
                        <select id="admin-model-protocol" value={newModel.api_protocol} onChange={e => { const v = e.target.value; setNewModel(prev => ({ ...prev, api_protocol: v })) }} style={inputStyle}>
                          <option value="">Auto-detect</option>
                          <option value="openai">OpenAI</option>
                          <option value="anthropic">Anthropic</option>
                          <option value="google">Google (Gemini)</option>
                          <option value="openrouter">OpenRouter</option>
                          <option value="ollama">Ollama</option>
                          <option value="vllm">VLLM</option>
                        </select>
                      </div>
                      <div>
                        <label htmlFor="admin-model-speed" style={labelStyle}>Speed</label>
                        <select id="admin-model-speed" value={newModel.speed} onChange={e => { const v = e.target.value; setNewModel(prev => ({ ...prev, speed: v })) }} style={inputStyle}>
                          <option value="">Not set</option>
                          <option value="fast">Fast</option>
                          <option value="standard">Standard</option>
                          <option value="slow">Slow</option>
                        </select>
                      </div>
                      <div>
                        <label htmlFor="admin-model-tier" style={labelStyle}>Tier</label>
                        <select id="admin-model-tier" value={newModel.tier} onChange={e => { const v = e.target.value; setNewModel(prev => ({ ...prev, tier: v })) }} style={inputStyle}>
                          <option value="">Not set</option>
                          <option value="high">High</option>
                          <option value="standard">Standard</option>
                          <option value="basic">Basic</option>
                        </select>
                      </div>
                      <div>
                        <label htmlFor="admin-model-privacy" style={labelStyle}>Privacy</label>
                        <select id="admin-model-privacy" value={newModel.privacy} onChange={e => { const v = e.target.value; setNewModel(prev => ({ ...prev, privacy: v })) }} style={inputStyle}>
                          <option value="">Not set</option>
                          <option value="internal">Internal</option>
                          <option value="external">External</option>
                        </select>
                      </div>
                      {!needsEndpoint && (
                        <div>
                          <label htmlFor="admin-model-endpoint-adv" style={labelStyle}>Endpoint (optional)</label>
                          <input id="admin-model-endpoint-adv" value={newModel.endpoint} onChange={e => { const v = e.target.value; setNewModel(prev => ({ ...prev, endpoint: v })) }} placeholder="https://..." style={inputStyle} />
                        </div>
                      )}
                    </div>

                    <div>
                      <label htmlFor="admin-model-context-window" style={labelStyle}>Context window (tokens)</label>
                      <div style={{ display: 'flex', gap: 8, alignItems: 'stretch' }}>
                        <input
                          id="admin-model-context-window"
                          type="number"
                          min={1}
                          value={newModel.context_window}
                          onChange={e => {
                            const v = parseInt(e.target.value, 10)
                            setNewModel(prev => ({ ...prev, context_window: Number.isFinite(v) && v > 0 ? v : 0 }))
                            setProbeResult(null)
                          }}
                          placeholder="e.g. 65536"
                          style={{ ...inputStyle, flex: 1 }}
                        />
                        <button
                          onClick={handleProbeContextWindow}
                          disabled={probingContext || !newModel.name.trim()}
                          title="Ask the endpoint what context window it actually serves. Catches the case where the model card says 131k but the deployment was launched with a smaller --max-model-len."
                          style={{
                            padding: '0 14px', borderRadius: 'var(--ui-radius, 12px)',
                            border: '1px solid #d1d5db', background: '#fff', fontSize: 13,
                            cursor: probingContext || !newModel.name.trim() ? 'not-allowed' : 'pointer',
                            opacity: probingContext || !newModel.name.trim() ? 0.6 : 1,
                            whiteSpace: 'nowrap',
                          }}
                        >
                          {probingContext ? 'Probing…' : 'Probe endpoint'}
                        </button>
                      </div>
                      <div style={{ fontSize: 11, color: '#6b7280', marginTop: 4 }}>
                        The serving cap (e.g. vLLM&rsquo;s <code>--max-model-len</code>), not the model card&rsquo;s theoretical max. Compaction and the oversize-doc check use this to decide what fits.
                      </div>
                      {probeResult && (
                        <div role="status" aria-live="polite" style={{
                          marginTop: 6, padding: '6px 10px', borderRadius: 'var(--ui-radius, 12px)',
                          background: probeResult.ok ? '#ecfdf5' : '#fef3c7',
                          border: `1px solid ${probeResult.ok ? '#a7f3d0' : '#fcd34d'}`,
                          color: probeResult.ok ? '#065f46' : '#92400e',
                          fontSize: 12,
                        }}>
                          {probeResult.message}
                        </div>
                      )}
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                      <div>
                        <label htmlFor="admin-model-timeout" style={labelStyle}>Request timeout (seconds)</label>
                        <input
                          id="admin-model-timeout"
                          type="number"
                          min={0}
                          value={newModel.request_timeout_seconds || ''}
                          onChange={e => { const v = parseInt(e.target.value, 10); setNewModel(prev => ({ ...prev, request_timeout_seconds: Number.isFinite(v) && v > 0 ? v : 0 })) }}
                          placeholder="system default"
                          style={inputStyle}
                        />
                        <div style={{ fontSize: 11, color: '#6b7280', marginTop: 4 }}>
                          Overrides the shared LLM timeout for this model — raise it for slow self-hosted models. Blank = system default.
                        </div>
                      </div>
                      <div>
                        <label htmlFor="admin-model-reserve" style={labelStyle}>Response reserve (output tokens)</label>
                        <input
                          id="admin-model-reserve"
                          type="number"
                          min={0}
                          value={newModel.response_reserve_tokens || ''}
                          onChange={e => { const v = parseInt(e.target.value, 10); setNewModel(prev => ({ ...prev, response_reserve_tokens: Number.isFinite(v) && v > 0 ? v : 0 })) }}
                          placeholder="auto"
                          style={inputStyle}
                        />
                        <div style={{ fontSize: 11, color: '#6b7280', marginTop: 4 }}>
                          Tokens reserved for the model&rsquo;s answer; also caps runaway reasoning. More output room means less input room. Blank = scaled to the context window.
                        </div>
                      </div>
                    </div>

                    <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
                      <label style={checkboxLabel}>
                        <input type="checkbox" checked={newModel.external} onChange={e => { const v = e.target.checked; setNewModel(prev => ({ ...prev, external: v })) }} style={checkStyle} />
                        External
                      </label>
                      <label style={checkboxLabel}>
                        <input type="checkbox" checked={newModel.supports_structured} onChange={e => { const v = e.target.checked; setNewModel(prev => ({ ...prev, supports_structured: v })) }} style={checkStyle} />
                        Supports structured output
                      </label>
                      {newModel.multimodal && (
                        <label style={checkboxLabel}>
                          <input type="checkbox" checked={newModel.supports_pdf} onChange={e => { const v = e.target.checked; setNewModel(prev => ({ ...prev, supports_pdf: v })) }} style={checkStyle} />
                          Supports PDF input
                        </label>
                      )}
                    </div>
                  </div>
                </details>

                {error && (
                  <div style={{ marginTop: 12, padding: '8px 12px', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 'var(--ui-radius, 12px)', color: '#991b1b', fontSize: 13 }}>
                    {error}
                  </div>
                )}

                {wizardTesting && (
                  <div role="status" aria-live="polite" style={{ marginTop: 12, fontSize: 13, color: '#6b7280' }}>
                    Testing connection…
                  </div>
                )}
                {modelTest && !wizardTesting && (
                  <div style={{ marginTop: 12 }}>
                    <ModelTestDiagnostics result={modelTest} />
                  </div>
                )}

                <div style={{ display: 'flex', gap: 8, marginTop: 14 }}>
                  {!modelTest ? (
                    <>
                      <button onClick={handleSaveModel} disabled={savingModel || wizardTesting} style={{ ...primaryBtn, opacity: savingModel || wizardTesting ? 0.6 : 1 }}>
                        {savingModel ? 'Saving…' : wizardTesting ? 'Testing…' : 'Save & test connection'}
                      </button>
                      {!isEditing && <button onClick={() => { setWizardStep(1); setModelTest(null) }} style={secondaryBtn}>Back</button>}
                      <button onClick={closeModelForm} style={secondaryBtn}>Cancel</button>
                    </>
                  ) : (
                    <>
                      <button onClick={closeModelForm} style={primaryBtn}>Done</button>
                      <button onClick={handleSaveModel} disabled={savingModel || wizardTesting} style={{ ...secondaryBtn, opacity: savingModel || wizardTesting ? 0.6 : 1 }}>
                        {savingModel || wizardTesting ? 'Testing…' : 'Save & re-test'}
                      </button>
                    </>
                  )}
                </div>
              </>
            )}
          </div>
          )
        })()}
      </div>
    </div>
  )
}
