import { useEffect, useState, useCallback, useRef } from 'react'
import {
  ShieldCheck, Users, Settings,
  Cpu, Lock, Globe, Plus, Trash2,
  CheckCircle2, XCircle,
  Play, AlertCircle,
  X,
} from 'lucide-react'
import {
  getSystemConfig, updateSystemConfig, updateCompliancePolicyConfig,
  testOcr, testPrompt, testWebSearch, getReadiness,
} from '../../api/admin'
import type { TestPromptResult, ReadinessReport, ReadinessItem } from '../../api/admin'
import type {
  SystemConfigData, OcrProvider,
} from '../../api/admin'
import { AuthPanel } from './config/AuthPanel'
import { ModelEditor } from './config/ModelEditor'
import type { ModelEditorHandle } from './config/ModelEditor'
import { ThemePanel } from './config/ThemePanel'
import { sectionStyle, sectionHeaderStyle, sectionBodyStyle, labelStyle, inputStyle, checkStyle, hintStyle } from './config/styles'

// Starting point for the Docling-Serve options blob — the options sites most
// often need to set (OCR engine, languages, table fidelity, image handling)
// rather than an exhaustive list. Offered via "Insert example options" so an
// admin edits real JSON instead of authoring it from the docs.
const DOCLING_OPTIONS_PLACEHOLDER = `{
  "do_ocr": true,
  "ocr_engine": "easyocr",
  "ocr_lang": ["en"],
  "pdf_backend": "dlparse_v4",
  "table_mode": "accurate",
  "include_images": true,
  "images_scale": 2
}`

// ──────────────────────────────────────────
// Setup readiness checklist
// ──────────────────────────────────────────

// A graded "is this install set up" surface. A dismissible banner auto-shows
// while a blocker (no working LLM) is unresolved; the full checklist always
// lives at the top of the config page. `onJump` scrolls to the relevant
// section so each item is one click from being fixed.
function SetupChecklist({ report, onJump, onDismiss }: { report: ReadinessReport; onJump: (target: string) => void; onDismiss?: () => void }) {
  const sevColor: Record<string, string> = { blocker: '#dc2626', recommended: '#d97706', optional: '#6b7280' }
  const statusPill = (item: ReadinessItem) => {
    if (item.status === 'configured') return { label: 'Done', bg: '#dcfce7', fg: '#166534' }
    if (item.status === 'incomplete') return { label: 'Needs attention', bg: '#fef9c3', fg: '#854d0e' }
    return item.severity === 'blocker'
      ? { label: 'Required', bg: '#fee2e2', fg: '#991b1b' }
      : { label: 'Recommended', bg: '#ffedd5', fg: '#9a3412' }
  }
  return (
    <div style={{ marginBottom: 20, border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)', overflow: 'hidden' }}>
      <div style={{ padding: '12px 16px', borderBottom: '1px solid #f1f5f9', display: 'flex', alignItems: 'center', gap: 8 }}>
        {report.ready
          ? <ShieldCheck size={18} style={{ color: '#16a34a' }} />
          : <AlertCircle size={18} style={{ color: '#d97706' }} />}
        <span style={{ fontSize: 14, fontWeight: 700, color: '#111' }}>
          {report.ready ? 'System ready' : 'Finish setting up your workspace'}
        </span>
        {!report.ready && report.blockers_remaining > 0 && (
          <span style={{ fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 9999, background: '#fee2e2', color: '#991b1b' }}>
            {report.blockers_remaining} blocker{report.blockers_remaining > 1 ? 's' : ''} left
          </span>
        )}
        <div style={{ flex: 1 }} />
        {onDismiss && (
          <button onClick={onDismiss} title="Dismiss" style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#9ca3af', padding: 2 }}>
            <X size={16} />
          </button>
        )}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        {report.items.map(item => {
          const pill = statusPill(item)
          const done = item.status === 'configured'
          return (
            <div key={item.key} style={{ display: 'flex', alignItems: 'flex-start', gap: 12, padding: '12px 16px', borderTop: '1px solid #f8fafc' }}>
              <div style={{ marginTop: 1 }}>
                {done
                  ? <CheckCircle2 size={18} style={{ color: '#16a34a' }} />
                  : <div style={{ width: 18, height: 18, borderRadius: 9999, border: `2px solid ${sevColor[item.severity]}` }} />}
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <span style={{ fontSize: 13, fontWeight: 600, color: '#111' }}>{item.title}</span>
                  <span style={{ fontSize: 10, fontWeight: 700, padding: '1px 7px', borderRadius: 9999, background: pill.bg, color: pill.fg }}>{pill.label}</span>
                </div>
                <div style={{ fontSize: 12, color: '#4b5563', marginTop: 2 }}>{item.summary}</div>
                {!done && <div style={{ fontSize: 12, color: '#9ca3af', marginTop: 2 }}>Unlocks: {item.unlocks}</div>}
              </div>
              {!done && (
                <button
                  onClick={() => onJump(item.action_target)}
                  style={{ flexShrink: 0, padding: '5px 12px', borderRadius: 'var(--ui-radius, 12px)', border: '1px solid #d1d5db', background: '#fff', fontSize: 12, fontWeight: 600, cursor: 'pointer', color: '#111' }}
                >
                  {item.action_label}
                </button>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ──────────────────────────────────────────
// Config Tab
// ──────────────────────────────────────────

export function ConfigTab() {
  const [cfg, setCfg] = useState<SystemConfigData | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Extraction config
  const [extractionMode, setExtractionMode] = useState('one_pass')
  const [chunkingEnabled, setChunkingEnabled] = useState(false)
  const [maxKeysPerChunk, setMaxKeysPerChunk] = useState(10)
  const [repetitionEnabled, setRepetitionEnabled] = useState(false)
  const [onePassThinking, setOnePassThinking] = useState(true)
  const [onePassStructured, setOnePassStructured] = useState(true)
  const [onePassModel, setOnePassModel] = useState('')
  const [twoPassP1Thinking, setTwoPassP1Thinking] = useState(true)
  const [twoPassP1Structured, setTwoPassP1Structured] = useState(false)
  const [twoPassP1Model, setTwoPassP1Model] = useState('')
  const [twoPassP2Thinking, setTwoPassP2Thinking] = useState(false)
  const [twoPassP2Structured, setTwoPassP2Structured] = useState(true)
  const [twoPassP2Model, setTwoPassP2Model] = useState('')
  const [useImages, setUseImages] = useState(false)

  // Quality config
  const [requireValidation, setRequireValidation] = useState(false)
  const [minAccuracy, setMinAccuracy] = useState(70)
  const [minConsistency, setMinConsistency] = useState(80)
  const [minWorkflowGrade, setMinWorkflowGrade] = useState('C')
  const [excellentThreshold, setExcellentThreshold] = useState(90)
  const [goodThreshold, setGoodThreshold] = useState(70)
  const [fairThreshold, setFairThreshold] = useState(50)

  // Endpoints
  const [ocrEndpoint, setOcrEndpoint] = useState('')
  const [ocrApiKey, setOcrApiKey] = useState('')
  // Tracks whether the user actually edited the key field (vs. it merely
  // holding the load's initial value). Only a dirty key is sent on save —
  // this is defense in depth so a form rendered without a successful config
  // load can never overwrite the stored key with ''. See the `!cfg || loadError`
  // early return below, which is the primary guard.
  const [ocrApiKeyDirty, setOcrApiKeyDirty] = useState(false)
  const [ocrTesting, setOcrTesting] = useState(false)
  const [ocrTestResult, setOcrTestResult] = useState<{ ok: boolean; message: string } | null>(null)
  const [ocrProvider, setOcrProvider] = useState<OcrProvider>('raw')
  // Held as text, not a parsed object, so a half-typed edit isn't destroyed on
  // every keystroke. Parsed on save; a parse error blocks the save with a
  // message rather than silently sending {}.
  const [ocrOptionsText, setOcrOptionsText] = useState('')
  const [ocrOptionsError, setOcrOptionsError] = useState<string | null>(null)
  const [ocrAsync, setOcrAsync] = useState(false)
  const [ocrTimeout, setOcrTimeout] = useState(120)

  // Web Search — powers the agentic chat web_search tool
  const [webSearchProvider, setWebSearchProvider] = useState('')
  const [webSearchEndpoint, setWebSearchEndpoint] = useState('')
  const [webSearchApiKey, setWebSearchApiKey] = useState('')
  // Same dirty-tracking defense as the OCR key: only a user-edited key is
  // sent on save, so the '***' sentinel can never overwrite the stored key.
  const [webSearchApiKeyDirty, setWebSearchApiKeyDirty] = useState(false)
  const [webSearchTesting, setWebSearchTesting] = useState(false)
  const [webSearchTestResult, setWebSearchTestResult] = useState<{ ok: boolean; message: string } | null>(null)

  // System readiness / setup checklist
  const [readiness, setReadiness] = useState<ReadinessReport | null>(null)
  const [setupDismissed, setSetupDismissed] = useState(false)
  const refreshReadiness = useCallback(async () => {
    try {
      setReadiness(await getReadiness())
    } catch {
      // Readiness is advisory — never block the config page on it.
    }
  }, [])

  // Available Models panel. It owns the model list's own state and save path;
  // the parent keeps the loaded config in sync (the Prompt Playground and the
  // Extraction Configuration panel both read `available_models`) and lends the
  // panel the shared error banner.
  const modelEditorRef = useRef<ModelEditorHandle>(null)
  const applyModelConfigPatch = useCallback((patch: {
    available_models?: SystemConfigData['available_models']
    default_model?: string
  }) => {
    setCfg(prev => (prev ? { ...prev, ...patch } : prev))
  }, [])

  // Authentication panel. Its provider writes re-read the whole config, so it
  // hands the fresh copy back rather than owning the loaded config itself.
  const replaceConfig = useCallback((next: SystemConfigData) => { setCfg(next) }, [])

  // Prompt playground
  const [playgroundModel, setPlaygroundModel] = useState('')
  const [playgroundSystem, setPlaygroundSystem] = useState('')
  const [playgroundUser, setPlaygroundUser] = useState('')
  const [playgroundSending, setPlaygroundSending] = useState(false)
  const [playgroundResult, setPlaygroundResult] = useState<TestPromptResult | null>(null)
  const [playgroundError, setPlaygroundError] = useState<string | null>(null)

  // Support contacts
  const [supportContacts, setSupportContacts] = useState<{ user_id: string; email: string; name: string }[]>([])
  const [showAddContact, setShowAddContact] = useState(false)
  const [newContact, setNewContact] = useState({ user_id: '', email: '', name: '' })

  // Compliance activation
  const [complianceEnabled, setComplianceEnabled] = useState(false)
  const [complianceCheckOnUpload, setComplianceCheckOnUpload] = useState(true)
  const [complianceRules, setComplianceRules] = useState('')
  const [complianceChunkSize, setComplianceChunkSize] = useState(8000)
  const [complianceChunkOverlap, setComplianceChunkOverlap] = useState(200)
  const [complianceSaving, setComplianceSaving] = useState(false)
  const [complianceSaved, setComplianceSaved] = useState(false)

  // Retention policy
  type RetentionPolicyForm = { retention_days: number; soft_delete_grace_days: number; warning_days_before?: number }
  const [retentionEnabled, setRetentionEnabled] = useState(false)
  const [retentionPolicies, setRetentionPolicies] = useState<Record<string, RetentionPolicyForm>>({})
  const [activityRetentionDays, setActivityRetentionDays] = useState(180)
  const [chatRetentionDays, setChatRetentionDays] = useState(365)
  const [workflowResultRetentionDays, setWorkflowResultRetentionDays] = useState(365)
  const [staleActivityMinutes, setStaleActivityMinutes] = useState(30)
  const [retentionSaving, setRetentionSaving] = useState(false)
  const [retentionSaved, setRetentionSaved] = useState(false)

  useEffect(() => { void refreshReadiness() }, [refreshReadiness])

  // Extracted so the error panel's Retry control can re-run the exact same
  // load the mount effect performs, resetting loadError/loading each time.
  const loadConfig = useCallback(() => {
    setLoading(true)
    setLoadError(null)
    return getSystemConfig().then(c => {
      setCfg(c)
      setOcrEndpoint(c.ocr_endpoint || '')
      setOcrApiKey(c.ocr_api_key || '')
      setOcrApiKeyDirty(false)
      setWebSearchProvider(c.web_search_provider || '')
      setWebSearchEndpoint(c.web_search_endpoint || '')
      setWebSearchApiKey(c.web_search_api_key || '')
      setWebSearchApiKeyDirty(false)
      setOcrProvider(c.ocr_provider === 'docling' ? 'docling' : 'raw')
      setOcrOptionsText(
        c.ocr_options && Object.keys(c.ocr_options).length
          ? JSON.stringify(c.ocr_options, null, 2)
          : ''
      )
      setOcrOptionsError(null)
      setOcrAsync(!!c.ocr_async)
      setOcrTimeout(c.ocr_timeout_seconds || 120)
      // auth_methods is seeded into AuthPanel from `cfg` on mount; a reload
      // unmounts and remounts that subtree, which re-seeds it.
      setSupportContacts((c as unknown as Record<string, unknown>).support_contacts as typeof supportContacts || [])
      // Extraction config
      const ec = c.extraction_config || {}
      setExtractionMode((ec as Record<string, unknown>).mode as string || 'one_pass')
      const chunking = (ec as Record<string, unknown>).chunking as Record<string, unknown> || {}
      setChunkingEnabled(!!chunking.enabled)
      setMaxKeysPerChunk((chunking.max_keys_per_chunk as number) || 10)
      setRepetitionEnabled(!!((ec as Record<string, unknown>).repetition as Record<string, unknown>)?.enabled)
      setUseImages(!!(ec as Record<string, unknown>).use_images)
      const onePass = (ec as Record<string, unknown>).one_pass as Record<string, unknown> || {}
      setOnePassThinking(onePass.thinking !== false)
      setOnePassStructured((onePass.structured_output ?? onePass.structured) !== false)
      setOnePassModel((onePass.model as string) || '')
      const twoPass = (ec as Record<string, unknown>).two_pass as Record<string, unknown> || {}
      const pass1 = (twoPass.pass1 as Record<string, unknown> ?? twoPass.pass_1 as Record<string, unknown>) || {}
      const pass2 = (twoPass.pass2 as Record<string, unknown> ?? twoPass.pass_2 as Record<string, unknown>) || {}
      setTwoPassP1Thinking(pass1.thinking !== false)
      setTwoPassP1Structured(!!(pass1.structured_output ?? pass1.structured))
      setTwoPassP1Model((pass1.model as string) || '')
      setTwoPassP2Thinking(!!(pass2.thinking))
      setTwoPassP2Structured((pass2.structured_output ?? pass2.structured) !== false)
      setTwoPassP2Model((pass2.model as string) || '')
      // Quality config
      const qc = (c.quality_config || {}) as Record<string, unknown>
      const gates = (qc.verification_gates || {}) as Record<string, unknown>
      setRequireValidation(!!gates.require_validation)
      setMinAccuracy(Math.round(((gates.min_extraction_accuracy as number) ?? 0.7) * 100))
      setMinConsistency(Math.round(((gates.min_extraction_consistency as number) ?? 0.8) * 100))
      setMinWorkflowGrade((gates.min_workflow_grade as string) || 'C')
      const tiers = (qc.quality_tiers || {}) as Record<string, Record<string, unknown>>
      setExcellentThreshold((tiers.excellent?.min_score as number) ?? 90)
      setGoodThreshold((tiers.good?.min_score as number) ?? 70)
      setFairThreshold((tiers.fair?.min_score as number) ?? 50)
      // Compliance config
      const comp = c.compliance_config || ({} as Partial<typeof c.compliance_config>)
      setComplianceEnabled(!!comp.enabled)
      setComplianceCheckOnUpload(comp.check_on_upload !== false)
      setComplianceRules(comp.rules || '')
      setComplianceChunkSize(comp.chunk_size || 8000)
      setComplianceChunkOverlap(comp.chunk_overlap ?? 200)
      // Retention config
      const rc = (c.retention_config || {}) as Record<string, unknown>
      setRetentionEnabled(!!rc.enabled)
      setRetentionPolicies((rc.policies as Record<string, RetentionPolicyForm>) || {})
      setActivityRetentionDays((rc.activity_retention_days as number) ?? 180)
      setChatRetentionDays((rc.chat_retention_days as number) ?? 365)
      setWorkflowResultRetentionDays((rc.workflow_result_retention_days as number) ?? 365)
      setStaleActivityMinutes((rc.activity_stale_threshold_minutes as number) ?? 30)
    }).catch(e => {
      setLoadError(e instanceof Error ? e.message : 'Failed to load configuration')
    }).finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    void loadConfig()
  }, [loadConfig])

  const handleSaveConfig = async () => {
    // Parse before touching the saving state so a malformed options blob fails
    // loudly at the field rather than being silently dropped from the payload.
    let parsedOcrOptions: Record<string, unknown> = {}
    if (ocrOptionsText.trim()) {
      try {
        const parsed = JSON.parse(ocrOptionsText)
        if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
          throw new Error('OCR options must be a JSON object')
        }
        parsedOcrOptions = parsed as Record<string, unknown>
      } catch (e) {
        const message = e instanceof Error ? e.message : 'Invalid JSON'
        setOcrOptionsError(message)
        setError(`OCR options: ${message}`)
        return
      }
    }
    setOcrOptionsError(null)
    setSaving(true)
    setSaved(false)
    setError(null)
    try {
      await updateSystemConfig({
        extraction_config: {
          mode: extractionMode,
          one_pass: { thinking: onePassThinking, structured: onePassStructured, model: onePassModel || '' },
          two_pass: {
            pass_1: { thinking: twoPassP1Thinking, structured: twoPassP1Structured, model: twoPassP1Model || '' },
            pass_2: { thinking: twoPassP2Thinking, structured: twoPassP2Structured, model: twoPassP2Model || '' },
          },
          chunking: { enabled: chunkingEnabled, max_keys_per_chunk: maxKeysPerChunk },
          repetition: { enabled: repetitionEnabled },
          use_images: useImages,
        },
        quality_config: {
          verification_gates: {
            require_validation: requireValidation,
            min_extraction_accuracy: minAccuracy / 100,
            min_extraction_consistency: minConsistency / 100,
            min_workflow_grade: minWorkflowGrade,
          },
          quality_tiers: {
            excellent: { min_score: excellentThreshold },
            good: { min_score: goodThreshold },
            fair: { min_score: fairThreshold },
          },
        },
        ocr_endpoint: ocrEndpoint,
        ocr_provider: ocrProvider,
        ocr_options: parsedOcrOptions,
        ocr_async: ocrAsync,
        ocr_timeout_seconds: ocrTimeout,
        // Only send the key when the user actually touched the field. An
        // untouched field after a successful load holds the "***" sentinel,
        // which the backend already treats as "keep the stored key" — so
        // omitting it here is equivalent and avoids ever sending ''.
        ...(ocrApiKeyDirty ? { ocr_api_key: ocrApiKey } : {}),
        web_search_provider: webSearchProvider,
        web_search_endpoint: webSearchEndpoint,
        ...(webSearchApiKeyDirty ? { web_search_api_key: webSearchApiKey } : {}),
      })
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
      void refreshReadiness()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const handleTestOcr = async () => {
    setOcrTesting(true)
    setOcrTestResult(null)
    try {
      // Send the form's current values so unsaved edits are what gets tested;
      // an untouched key field holds the "***" sentinel, meaning the saved key.
      const res = await testOcr({ ocr_endpoint: ocrEndpoint, ocr_api_key: ocrApiKey, ocr_provider: ocrProvider })
      setOcrTestResult({ ok: res.status !== 'warning', message: res.message })
    } catch (e) {
      setOcrTestResult({ ok: false, message: e instanceof Error ? e.message : 'Test failed' })
    } finally {
      setOcrTesting(false)
    }
  }

  const handleTestWebSearch = async () => {
    setWebSearchTesting(true)
    setWebSearchTestResult(null)
    try {
      const res = await testWebSearch()
      setWebSearchTestResult({ ok: true, message: res.message })
    } catch (e) {
      setWebSearchTestResult({ ok: false, message: e instanceof Error ? e.message : 'Test failed' })
    } finally {
      setWebSearchTesting(false)
    }
  }

  const handleSendPlaygroundPrompt = async () => {
    if (!playgroundUser.trim()) return
    setPlaygroundSending(true)
    setPlaygroundError(null)
    setPlaygroundResult(null)
    try {
      const res = await testPrompt({
        model_name: playgroundModel || cfg?.default_model || '',
        system_prompt: playgroundSystem,
        user_prompt: playgroundUser,
      })
      setPlaygroundResult(res)
    } catch (e) {
      setPlaygroundError(e instanceof Error ? e.message : 'Request failed')
    } finally {
      setPlaygroundSending(false)
    }
  }

  const saveSupportContacts = async (contacts: typeof supportContacts) => {
    try {
      await updateSystemConfig({ support_contacts: contacts } as Record<string, unknown>)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save support contacts')
    }
  }

  if (loading) return <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>Loading config...</div>

  // Structural guard: without this, a failed load left `cfg` null but still
  // rendered the form against pristine useState defaults, and Save would
  // write those defaults over real stored config (wiping the OCR API key,
  // resetting extraction_config/quality_config). Never remove this without
  // an equivalent guard in its place.
  if (!cfg || loadError) {
    return (
      <div style={{ padding: 40, textAlign: 'center' }}>
        <div style={{
          display: 'inline-block', padding: '16px 20px', background: '#fef2f2', border: '1px solid #fecaca',
          borderRadius: 'var(--ui-radius, 12px)', color: '#991b1b', fontSize: 14, maxWidth: 480,
        }}>
          <div style={{ fontWeight: 600, marginBottom: 6 }}>Could not load configuration</div>
          <div style={{ marginBottom: 12 }}>
            {loadError || 'The configuration failed to load.'} Saving is disabled until it loads
            successfully, so this cannot overwrite stored settings with blank defaults.
          </div>
          <button
            onClick={() => void loadConfig()}
            style={{
              padding: '6px 16px', borderRadius: 'var(--ui-radius, 12px)', border: '1px solid #991b1b',
              fontSize: 13, fontWeight: 600, cursor: 'pointer', background: '#fff', color: '#991b1b',
            }}
          >
            Retry
          </button>
        </div>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Sticky save bar */}
      <div style={{
        position: 'sticky', top: 0, zIndex: 20,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        background: '#fff', borderBottom: '1px solid #e5e7eb',
        padding: '12px 20px', margin: '0 0 -4px',
        boxShadow: '0 2px 8px rgba(0,0,0,0.06)',
      }}>
        <span style={{ fontSize: 14, fontWeight: 600, color: '#374151', display: 'flex', alignItems: 'center', gap: 8 }}>
          <Settings size={16} color="#6b7280" /> System Configuration
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {saved && <span role="status" aria-live="polite" style={{ fontSize: 13, color: '#16a34a' }}>Configuration saved!</span>}
          <button
            onClick={handleSaveConfig}
            disabled={saving}
            style={{
              padding: '8px 20px', borderRadius: 'var(--ui-radius, 12px)', border: 'none',
              backgroundColor: '#111827', color: '#fff', fontSize: 13, fontWeight: 600, cursor: 'pointer',
              opacity: saving ? 0.6 : 1,
            }}
          >
            {saving ? 'Saving...' : 'Save Configuration'}
          </button>
        </div>
      </div>

      {error && (
        <div style={{ padding: '10px 16px', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 'var(--ui-radius, 12px)', color: '#991b1b', fontSize: 13 }}>
          {error}
        </div>
      )}

      {/* Setup readiness — auto-shows while a blocker is unresolved; once the
          system is ready it can be dismissed for the session. */}
      {readiness && !(readiness.ready && setupDismissed) && (
        <SetupChecklist
          report={readiness}
          onJump={(target) => {
            const id = `cfg-${target}`
            document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
            // First-run: if the admin is being sent to connect their first model,
            // drop them straight into the guided wizard instead of leaving them to
            // find the "Add Model" button. The panel itself decides whether to —
            // only when none exists and the form isn't already open.
            if (target === 'models') {
              modelEditorRef.current?.openFirstRunWizard()
            }
          }}
          onDismiss={readiness.ready ? () => setSetupDismissed(true) : undefined}
        />
      )}

      <ModelEditor
        ref={modelEditorRef}
        models={cfg.available_models}
        defaultModel={cfg.default_model}
        onConfigPatch={applyModelConfigPatch}
        onReadinessChange={refreshReadiness}
        error={error}
        onError={setError}
      />

      {/* Prompt Playground */}
      <div style={sectionStyle}>
        <div style={sectionHeaderStyle}>
          <Play size={18} color="#6b7280" /> Prompt Playground
          <span style={{ fontSize: 12, fontWeight: 400, color: '#6b7280' }}>
            — send a prompt to a configured model and see the raw round-trip
          </span>
        </div>
        <div style={sectionBodyStyle}>
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 220px', gap: 16, alignItems: 'start' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div>
                <label htmlFor="admin-playground-system" style={labelStyle}>System Prompt (optional)</label>
                <textarea
                  id="admin-playground-system"
                  value={playgroundSystem}
                  onChange={e => setPlaygroundSystem(e.target.value)}
                  placeholder="e.g. You are a helpful assistant. Reply concisely."
                  rows={3}
                  style={{ ...inputStyle, fontFamily: 'ui-monospace, monospace', fontSize: 13, resize: 'vertical' }}
                />
              </div>
              <div>
                <label htmlFor="admin-playground-user" style={labelStyle}>User Prompt</label>
                <textarea
                  id="admin-playground-user"
                  value={playgroundUser}
                  onChange={e => setPlaygroundUser(e.target.value)}
                  placeholder="Ask anything. The text below will be sent verbatim to the selected model."
                  rows={5}
                  style={{ ...inputStyle, fontFamily: 'ui-monospace, monospace', fontSize: 13, resize: 'vertical' }}
                />
              </div>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div>
                <label htmlFor="admin-playground-model" style={labelStyle}>Model</label>
                <select
                  id="admin-playground-model"
                  value={playgroundModel}
                  onChange={e => setPlaygroundModel(e.target.value)}
                  style={inputStyle}
                >
                  <option value="">
                    {cfg?.default_model ? `Default (${cfg.default_model})` : 'Default'}
                  </option>
                  {cfg?.available_models?.map((m, i) => (
                    <option key={i} value={m.name}>{m.name}</option>
                  ))}
                </select>
              </div>
              <button
                onClick={handleSendPlaygroundPrompt}
                disabled={playgroundSending || !playgroundUser.trim()}
                style={{
                  padding: '10px 16px', borderRadius: 'var(--ui-radius, 12px)', border: 'none',
                  backgroundColor: '#111827', color: '#fff', fontSize: 13, fontWeight: 600,
                  cursor: playgroundSending || !playgroundUser.trim() ? 'not-allowed' : 'pointer',
                  opacity: playgroundSending || !playgroundUser.trim() ? 0.6 : 1,
                  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                }}
              >
                <Play size={14} /> {playgroundSending ? 'Sending...' : 'Send'}
              </button>
              {playgroundResult && (
                <div role="status" aria-live="polite" style={{ fontSize: 12, color: '#6b7280', lineHeight: 1.6 }}>
                  <div>Model: <span style={{ color: '#111', fontFamily: 'ui-monospace, monospace' }}>{playgroundResult.request.model}</span></div>
                  <div>Latency: {playgroundResult.latency_ms} ms</div>
                  {playgroundResult.tokens && (
                    <div>
                      Tokens: {playgroundResult.tokens.request ?? '?'} in / {playgroundResult.tokens.response ?? '?'} out
                      {playgroundResult.tokens.total != null && ` / ${playgroundResult.tokens.total} total`}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>

          {playgroundError && (
            <div role="alert" style={{ marginTop: 16, padding: '10px 14px', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 'var(--ui-radius, 12px)', color: '#991b1b', fontSize: 13 }}>
              {playgroundError}
            </div>
          )}

          {playgroundResult && (
            <div style={{ marginTop: 16, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <div>
                <div style={{ fontSize: 12, fontWeight: 600, color: '#374151', marginBottom: 6, display: 'flex', alignItems: 'center', gap: 6 }}>
                  Request sent
                </div>
                <pre style={{
                  margin: 0, padding: 12, background: '#f9fafb', border: '1px solid #e5e7eb',
                  borderRadius: 'var(--ui-radius, 12px)', fontSize: 12, lineHeight: 1.5,
                  fontFamily: 'ui-monospace, monospace', color: '#111',
                  whiteSpace: 'pre-wrap', wordBreak: 'break-word', maxHeight: 400, overflow: 'auto',
                }}>
{`[system]
${playgroundResult.request.system_prompt || '(none)'}

[user]
${playgroundResult.request.user_prompt}`}
                </pre>
              </div>
              <div>
                <div style={{ fontSize: 12, fontWeight: 600, color: '#374151', marginBottom: 6, display: 'flex', alignItems: 'center', gap: 6 }}>
                  {playgroundResult.ok ? (
                    <><CheckCircle2 size={13} color="#059669" aria-hidden="true" /> Response</>
                  ) : (
                    <><XCircle size={13} color="#dc2626" aria-hidden="true" /> Error</>
                  )}
                </div>
                <pre style={{
                  margin: 0, padding: 12,
                  background: playgroundResult.ok ? '#f9fafb' : '#fef2f2',
                  border: `1px solid ${playgroundResult.ok ? '#e5e7eb' : '#fecaca'}`,
                  borderRadius: 'var(--ui-radius, 12px)', fontSize: 12, lineHeight: 1.5,
                  fontFamily: 'ui-monospace, monospace',
                  color: playgroundResult.ok ? '#111' : '#991b1b',
                  whiteSpace: 'pre-wrap', wordBreak: 'break-word', maxHeight: 400, overflow: 'auto',
                }}>
                  {playgroundResult.ok ? (playgroundResult.response_text || '(empty response)') : (playgroundResult.error || 'Unknown error')}
                </pre>
              </div>
            </div>
          )}
        </div>
      </div>

      <AuthPanel
        providers={cfg.oauth_providers}
        initialAuthMethods={cfg.auth_methods || ['password']}
        onConfigReplace={replaceConfig}
        onReadinessChange={refreshReadiness}
        onError={setError}
      />

      {/* Endpoints */}
      <div id="cfg-ocr" style={sectionStyle}>
        <div style={sectionHeaderStyle}>
          <Globe size={18} color="#6b7280" /> Endpoints
        </div>
        <div style={sectionBodyStyle}>
          <div>
            <label style={labelStyle} htmlFor="ocr-provider">OCR Service Type</label>
            <select
              id="ocr-provider" value={ocrProvider}
              onChange={e => setOcrProvider(e.target.value as OcrProvider)}
              style={{ ...inputStyle, maxWidth: 500 }}
            >
              <option value="raw">Plain text response (Marker, Surya, Tesseract wrapper, custom)</option>
              <option value="docling">Docling-Serve</option>
            </select>
            <div style={hintStyle}>
              {ocrProvider === 'docling'
                ? 'Uploads to Docling-Serve’s /v1/convert/file API and reads the Markdown from the JSON response. Paste either the service root or a full convert URL below.'
                : 'Posts the PDF as multipart field "file" and treats the whole response body as the extracted text.'}
            </div>
          </div>
          <div style={{ marginTop: 12 }}>
            <label style={labelStyle}>OCR Endpoint</label>
            <input
              type="url" value={ocrEndpoint} onChange={e => setOcrEndpoint(e.target.value)}
              placeholder={ocrProvider === 'docling' ? 'https://docling.example.edu' : 'https://...'}
              style={{ ...inputStyle, maxWidth: 500 }}
            />
          </div>
          {ocrProvider === 'docling' && (
            <>
              <div style={{ marginTop: 12 }}>
                <label style={labelStyle} htmlFor="ocr-options">Conversion Options (JSON)</label>
                <textarea
                  id="ocr-options" rows={10} spellCheck={false}
                  value={ocrOptionsText}
                  onChange={e => { setOcrOptionsText(e.target.value); setOcrOptionsError(null) }}
                  placeholder={DOCLING_OPTIONS_PLACEHOLDER}
                  style={{
                    ...inputStyle, maxWidth: 640, fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
                    fontSize: 12, lineHeight: 1.5,
                    borderColor: ocrOptionsError ? '#dc2626' : undefined,
                  }}
                />
                <div style={hintStyle}>
                  Sent as form fields with every conversion request — the same option names
                  Docling-Serve accepts (<code>do_ocr</code>, <code>ocr_engine</code>,{' '}
                  <code>ocr_lang</code>, <code>pdf_backend</code>, <code>table_mode</code>,{' '}
                  <code>do_picture_description</code>, <code>picture_description_api</code>, …).
                  Leave blank to use Docling&rsquo;s own defaults. Vandalizer always requests
                  Markdown output.
                </div>
                {ocrOptionsError && (
                  <div role="alert" style={{ fontSize: 12, color: '#dc2626', marginTop: 4 }}>
                    {ocrOptionsError}
                  </div>
                )}
                {!ocrOptionsText.trim() && (
                  <button
                    type="button"
                    onClick={() => setOcrOptionsText(DOCLING_OPTIONS_PLACEHOLDER)}
                    style={{
                      marginTop: 6, padding: '4px 10px', fontSize: 12, fontWeight: 500,
                      borderRadius: 'var(--ui-radius, 12px)', border: '1px solid #e5e7eb',
                      background: '#fff', color: '#374151', cursor: 'pointer',
                    }}
                  >
                    Insert example options
                  </button>
                )}
              </div>
              <div style={{ marginTop: 12, display: 'flex', gap: 24, flexWrap: 'wrap' }}>
                <div>
                  <label style={labelStyle} htmlFor="ocr-timeout">Request Timeout (seconds)</label>
                  <input
                    id="ocr-timeout" type="number" min={10} max={3600}
                    value={ocrTimeout}
                    onChange={e => setOcrTimeout(parseInt(e.target.value) || 120)}
                    style={{ ...inputStyle, maxWidth: 160 }}
                  />
                </div>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: '#374151', alignSelf: 'flex-end', paddingBottom: 8 }}>
                  <input type="checkbox" checked={ocrAsync} onChange={e => setOcrAsync(e.target.checked)} />
                  Use async conversion API
                </label>
              </div>
              <div style={hintStyle}>
                Async submits the job and polls for the result, which avoids timeouts on
                large scanned PDFs where OCR takes minutes. Requires Docling-Serve&rsquo;s
                async endpoints to be enabled.
              </div>
            </>
          )}
          <div style={{ marginTop: 12 }}>
            <label style={labelStyle}>OCR API Key (optional)</label>
            <input
              type="password" autoComplete="new-password" data-1p-ignore data-lpignore="true" data-bwignore
              name="vandalizer-ocr-api-key"
              value={ocrApiKey} onChange={e => { setOcrApiKey(e.target.value); setOcrApiKeyDirty(true) }}
              placeholder="Bearer token..." style={{ ...inputStyle, maxWidth: 500 }}
            />
          </div>
          <div style={{ marginTop: 12, display: 'flex', alignItems: 'center', gap: 12 }}>
            <button
              onClick={handleTestOcr}
              disabled={ocrTesting || !ocrEndpoint}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 6, padding: '6px 14px',
                fontSize: 13, fontWeight: 500, borderRadius: 'var(--ui-radius, 12px)',
                border: '1px solid #e5e7eb', background: '#fff', cursor: ocrEndpoint ? 'pointer' : 'not-allowed',
                color: '#374151', opacity: ocrTesting ? 0.6 : 1,
              }}
            >
              <Play size={14} /> {ocrTesting ? 'Testing...' : 'Test Connection'}
            </button>
            {ocrTestResult && (
              <span role="status" aria-live="polite" style={{ fontSize: 13, color: ocrTestResult.ok ? '#059669' : '#dc2626', fontWeight: 500 }}>
                {ocrTestResult.ok ? <CheckCircle2 size={14} aria-hidden="true" style={{ verticalAlign: -2, marginRight: 4 }} /> : <XCircle size={14} aria-hidden="true" style={{ verticalAlign: -2, marginRight: 4 }} />}
                {ocrTestResult.message}
              </span>
            )}
          </div>

          {/* Web Search — powers the agentic chat web_search tool */}
          <div style={{ marginTop: 24, paddingTop: 24, borderTop: '1px solid #f0f0f0' }}>
            <div style={{ fontSize: 14, fontWeight: 600, color: '#374151', marginBottom: 4 }}>Web Search</div>
            <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 16 }}>
              Lets the chat assistant search the web when an answer isn't in the user's documents or knowledge bases. The assistant favors local sources first and only reaches for the web when needed.
            </div>
            <div>
              <label style={labelStyle}>Provider</label>
              <select
                value={webSearchProvider} onChange={e => setWebSearchProvider(e.target.value)}
                style={{ ...inputStyle, maxWidth: 500, background: '#fff', cursor: 'pointer' }}
              >
                <option value="">Disabled</option>
                <option value="mindrouter">MindRouter (campus search proxy)</option>
                <option value="tavily">Tavily</option>
                <option value="searxng">SearXNG (self-hosted)</option>
                <option value="brave">Brave Search API</option>
              </select>
            </div>
            <div style={{ marginTop: 12 }}>
              <label style={labelStyle}>Search Endpoint{webSearchProvider === 'tavily' ? ' (optional, defaults to api.tavily.com)' : webSearchProvider === 'mindrouter' ? ' (optional, defaults to mindrouter.uidaho.edu/v1/search)' : ''}</label>
              <input
                type="url" value={webSearchEndpoint} onChange={e => setWebSearchEndpoint(e.target.value)}
                placeholder={webSearchProvider === 'searxng' ? 'https://searx.your-domain.edu' : webSearchProvider === 'mindrouter' ? 'https://mindrouter.uidaho.edu/v1/search' : 'https://...'}
                style={{ ...inputStyle, maxWidth: 500 }}
              />
            </div>
            <div style={{ marginTop: 12 }}>
              <label style={labelStyle}>API Key{webSearchProvider === 'searxng' ? ' (optional)' : ''}</label>
              <input
                type="password" autoComplete="new-password" data-1p-ignore data-lpignore="true" data-bwignore
                name="vandalizer-web-search-api-key"
                value={webSearchApiKey} onChange={e => { setWebSearchApiKey(e.target.value); setWebSearchApiKeyDirty(true) }}
                placeholder="API key..." style={{ ...inputStyle, maxWidth: 500 }}
              />
            </div>
            <div style={{ marginTop: 12, display: 'flex', alignItems: 'center', gap: 12 }}>
              <button
                onClick={handleTestWebSearch}
                disabled={webSearchTesting || !webSearchProvider}
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: 6, padding: '6px 14px',
                  fontSize: 13, fontWeight: 500, borderRadius: 'var(--ui-radius, 12px)',
                  border: '1px solid #e5e7eb', background: '#fff', cursor: webSearchProvider ? 'pointer' : 'not-allowed',
                  color: '#374151', opacity: webSearchTesting ? 0.6 : 1,
                }}
              >
                <Play size={14} /> {webSearchTesting ? 'Testing...' : 'Test Search'}
              </button>
              {webSearchTestResult && (
                <span role="status" aria-live="polite" style={{ fontSize: 13, color: webSearchTestResult.ok ? '#059669' : '#dc2626', fontWeight: 500 }}>
                  {webSearchTestResult.ok ? <CheckCircle2 size={14} aria-hidden="true" style={{ verticalAlign: -2, marginRight: 4 }} /> : <XCircle size={14} aria-hidden="true" style={{ verticalAlign: -2, marginRight: 4 }} />}
                  {webSearchTestResult.message}
                </span>
              )}
            </div>
            <div style={{ fontSize: 12, color: '#9ca3af', marginTop: 10 }}>
              Note: Test Search and chat use the saved configuration — click Save above before testing new values.
            </div>
          </div>
        </div>
      </div>

      <ThemePanel
        initialColor={cfg.highlight_color || '#eab308'}
        initialRadius={parseInt(cfg.ui_radius) || 12}
      />

      {/* Extraction Configuration */}
      <div style={sectionStyle}>
        <div style={sectionHeaderStyle}>
          <Cpu size={18} color="#6b7280" /> Extraction Configuration
        </div>
        <div style={sectionBodyStyle}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            {/* Mode */}
            <div>
              <label style={labelStyle}>Extraction Mode</label>
              <div style={{ display: 'flex', gap: 8 }}>
                {['one_pass', 'two_pass'].map(mode => (
                  <button
                    key={mode}
                    onClick={() => setExtractionMode(mode)}
                    style={{
                      padding: '8px 20px', borderRadius: 'var(--ui-radius, 12px)', border: '1px solid #d1d5db',
                      fontSize: 13, fontWeight: 500, cursor: 'pointer', textTransform: 'capitalize',
                      backgroundColor: extractionMode === mode ? 'var(--highlight-color, #eab308)' : '#fff',
                      color: extractionMode === mode ? 'var(--highlight-text-color, #000)' : '#374151',
                    }}
                  >
                    {mode.replace('_', '-')}
                  </button>
                ))}
              </div>
            </div>

            {/* Mode-specific options */}
            {extractionMode === 'one_pass' ? (
              <div style={{ padding: 16, background: '#f9fafb', borderRadius: 'var(--ui-radius, 12px)' }}>
                <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12 }}>One-Pass Settings</div>
                <label style={{ display: 'flex', alignItems: 'center', fontSize: 14, marginBottom: 8, cursor: 'pointer' }}>
                  <input type="checkbox" checked={onePassThinking} onChange={e => setOnePassThinking(e.target.checked)} style={checkStyle} />
                  Thinking
                </label>
                <label style={{ display: 'flex', alignItems: 'center', fontSize: 14, marginBottom: 12, cursor: 'pointer' }}>
                  <input type="checkbox" checked={onePassStructured} onChange={e => setOnePassStructured(e.target.checked)} style={checkStyle} />
                  Structured
                </label>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <label style={{ fontSize: 13, color: '#5f6368' }}>Model:</label>
                  <select value={onePassModel} onChange={e => setOnePassModel(e.target.value)} style={{ ...inputStyle, maxWidth: 260 }}>
                    <option value="">Default</option>
                    {cfg?.available_models?.map(m => (
                      <option key={m.tag} value={m.name}>{m.tag || m.name}</option>
                    ))}
                  </select>
                </div>
              </div>
            ) : (
              <div style={{ padding: 16, background: '#f9fafb', borderRadius: 'var(--ui-radius, 12px)' }}>
                <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12 }}>Two-Pass Settings</div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                  <div>
                    <div style={{ fontSize: 12, fontWeight: 600, color: '#6b7280', marginBottom: 8 }}>Pass 1 (Draft)</div>
                    <label style={{ display: 'flex', alignItems: 'center', fontSize: 14, marginBottom: 8, cursor: 'pointer' }}>
                      <input type="checkbox" checked={twoPassP1Thinking} onChange={e => setTwoPassP1Thinking(e.target.checked)} style={checkStyle} />
                      Thinking
                    </label>
                    <label style={{ display: 'flex', alignItems: 'center', fontSize: 14, marginBottom: 12, cursor: 'pointer' }}>
                      <input type="checkbox" checked={twoPassP1Structured} onChange={e => setTwoPassP1Structured(e.target.checked)} style={checkStyle} />
                      Structured
                    </label>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <label style={{ fontSize: 13, color: '#5f6368' }}>Model:</label>
                      <select value={twoPassP1Model} onChange={e => setTwoPassP1Model(e.target.value)} style={{ ...inputStyle, maxWidth: 200 }}>
                        <option value="">Default</option>
                        {cfg?.available_models?.map(m => (
                          <option key={m.tag} value={m.name}>{m.tag || m.name}</option>
                        ))}
                      </select>
                    </div>
                  </div>
                  <div>
                    <div style={{ fontSize: 12, fontWeight: 600, color: '#6b7280', marginBottom: 8 }}>Pass 2 (Final)</div>
                    <label style={{ display: 'flex', alignItems: 'center', fontSize: 14, marginBottom: 8, cursor: 'pointer' }}>
                      <input type="checkbox" checked={twoPassP2Thinking} onChange={e => setTwoPassP2Thinking(e.target.checked)} style={checkStyle} />
                      Thinking
                    </label>
                    <label style={{ display: 'flex', alignItems: 'center', fontSize: 14, marginBottom: 12, cursor: 'pointer' }}>
                      <input type="checkbox" checked={twoPassP2Structured} onChange={e => setTwoPassP2Structured(e.target.checked)} style={checkStyle} />
                      Structured
                    </label>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <label style={{ fontSize: 13, color: '#5f6368' }}>Model:</label>
                      <select value={twoPassP2Model} onChange={e => setTwoPassP2Model(e.target.value)} style={{ ...inputStyle, maxWidth: 200 }}>
                        <option value="">Default</option>
                        {cfg?.available_models?.map(m => (
                          <option key={m.tag} value={m.name}>{m.tag || m.name}</option>
                        ))}
                      </select>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Chunking */}
            <div>
              <label style={{ display: 'flex', alignItems: 'center', fontSize: 14, fontWeight: 500, cursor: 'pointer' }}>
                <input type="checkbox" checked={chunkingEnabled} onChange={e => setChunkingEnabled(e.target.checked)} style={checkStyle} />
                Enable Chunking
              </label>
              {chunkingEnabled && (
                <div style={{ marginTop: 12, paddingLeft: 24 }}>
                  <label style={labelStyle}>Max Keys Per Chunk</label>
                  <input
                    type="number" min={1} max={100} value={maxKeysPerChunk}
                    onChange={e => setMaxKeysPerChunk(Number(e.target.value))}
                    style={{ ...inputStyle, maxWidth: 120 }}
                  />
                </div>
              )}
            </div>

            {/* Repetition */}
            <label style={{ display: 'flex', alignItems: 'center', fontSize: 14, fontWeight: 500, cursor: 'pointer' }}>
              <input type="checkbox" checked={repetitionEnabled} onChange={e => setRepetitionEnabled(e.target.checked)} style={checkStyle} />
              Enable Repetition/Consensus
            </label>

            {/* Use Images (multimodal) — only shown when multimodal models exist */}
            {cfg?.available_models?.some(m => m.multimodal) && (
              <div>
                <label style={{ display: 'flex', alignItems: 'center', fontSize: 14, fontWeight: 500, cursor: 'pointer' }}>
                  <input type="checkbox" checked={useImages} onChange={e => setUseImages(e.target.checked)} style={checkStyle} />
                  Use Document Images (Multimodal)
                </label>
                <div style={{ fontSize: 12, color: '#6b7280', marginTop: 4, paddingLeft: 24 }}>
                  Send document files directly to multimodal LLMs instead of OCR text. Requires a multimodal model to be selected for extraction.
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Quality & Verification Gates */}
      <div style={sectionStyle}>
        <div style={sectionHeaderStyle}>
          <ShieldCheck size={18} color="#6b7280" /> Quality &amp; Verification Gates
        </div>
        <div style={sectionBodyStyle}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <label style={{ display: 'flex', alignItems: 'center', fontSize: 14, fontWeight: 500, cursor: 'pointer' }}>
              <input type="checkbox" checked={requireValidation} onChange={e => setRequireValidation(e.target.checked)} style={checkStyle} />
              Require validation before verification submission
            </label>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 16 }}>
              <div>
                <label style={labelStyle}>Min Extraction Accuracy (%)</label>
                <input type="number" min={0} max={100} value={minAccuracy} onChange={e => setMinAccuracy(Number(e.target.value))} style={{ ...inputStyle, maxWidth: 120 }} />
              </div>
              <div>
                <label style={labelStyle}>Min Extraction Consistency (%)</label>
                <input type="number" min={0} max={100} value={minConsistency} onChange={e => setMinConsistency(Number(e.target.value))} style={{ ...inputStyle, maxWidth: 120 }} />
              </div>
              <div>
                <label style={labelStyle}>Min Workflow Grade</label>
                <select value={minWorkflowGrade} onChange={e => setMinWorkflowGrade(e.target.value)} style={{ ...inputStyle, maxWidth: 120 }}>
                  <option value="A">A</option>
                  <option value="B">B</option>
                  <option value="C">C</option>
                  <option value="D">D</option>
                  <option value="F">F</option>
                </select>
              </div>
            </div>

            <div style={{ borderTop: '1px solid #e5e7eb', paddingTop: 16 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 12 }}>Quality Tiers</div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 16 }}>
                <div>
                  <label style={labelStyle}>Excellent threshold</label>
                  <input type="number" min={0} max={100} value={excellentThreshold} onChange={e => setExcellentThreshold(Number(e.target.value))} style={{ ...inputStyle, maxWidth: 120 }} />
                </div>
                <div>
                  <label style={labelStyle}>Good threshold</label>
                  <input type="number" min={0} max={100} value={goodThreshold} onChange={e => setGoodThreshold(Number(e.target.value))} style={{ ...inputStyle, maxWidth: 120 }} />
                </div>
                <div>
                  <label style={labelStyle}>Fair threshold</label>
                  <input type="number" min={0} max={100} value={fairThreshold} onChange={e => setFairThreshold(Number(e.target.value))} style={{ ...inputStyle, maxWidth: 120 }} />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Support Contacts */}
      <div style={sectionStyle}>
        <div style={sectionHeaderStyle}>
          <Users size={18} color="#6b7280" /> Support Contacts
          <div style={{ flex: 1 }} />
          <button
            onClick={() => { setNewContact({ user_id: '', email: '', name: '' }); setShowAddContact(true) }}
            style={{
              display: 'flex', alignItems: 'center', gap: 4, padding: '6px 12px',
              borderRadius: 'var(--ui-radius, 12px)', border: '1px solid #d1d5db',
              fontSize: 13, fontWeight: 500, cursor: 'pointer', background: '#fff',
            }}
          >
            <Plus size={14} /> Add Contact
          </button>
        </div>
        <div style={sectionBodyStyle}>
          <p style={{ fontSize: 13, color: '#6b7280', marginBottom: 12 }}>
            People listed here will receive email alerts and in-app notifications when new support tickets are created. They will also have access to the Support Center to manage all tickets.
          </p>
          {supportContacts.length > 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {supportContacts.map((c, i) => (
                <div key={i} style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '10px 16px', background: '#f9fafb', borderRadius: 'var(--ui-radius, 12px)',
                  border: '1px solid #e5e7eb',
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <span style={{ fontSize: 14, fontWeight: 600, color: '#111' }}>{c.name}</span>
                    <span style={{ fontSize: 13, color: '#6b7280' }}>{c.email}</span>
                    <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 9999, background: '#f3f4f6', color: '#6b7280', fontWeight: 600 }}>{c.user_id}</span>
                  </div>
                  <button
                    onClick={() => {
                      const updated = supportContacts.filter((_, idx) => idx !== i)
                      setSupportContacts(updated)
                      saveSupportContacts(updated)
                    }}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#ef4444', padding: 4 }}
                    title="Remove contact"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ fontSize: 13, color: '#9ca3af' }}>No support contacts configured.</div>
          )}
          {showAddContact && (
            <div style={{ marginTop: 16, padding: 16, background: '#f9fafb', borderRadius: 'var(--ui-radius, 12px)', border: '1px solid #e5e7eb' }}>
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12 }}>Add Support Contact</div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
                <div>
                  <label style={labelStyle}>Name</label>
                  <input value={newContact.name} onChange={e => setNewContact({ ...newContact, name: e.target.value })} placeholder="Jane Doe" style={inputStyle} />
                </div>
                <div>
                  <label style={labelStyle}>User ID</label>
                  <input value={newContact.user_id} onChange={e => setNewContact({ ...newContact, user_id: e.target.value })} placeholder="jdoe" style={inputStyle} />
                </div>
                <div>
                  <label style={labelStyle}>Email</label>
                  <input value={newContact.email} onChange={e => setNewContact({ ...newContact, email: e.target.value })} placeholder="jdoe@example.com" style={inputStyle} />
                </div>
              </div>
              <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                <button
                  onClick={() => {
                    if (!newContact.name.trim() || !newContact.user_id.trim()) return
                    const updated = [...supportContacts, { ...newContact }]
                    setSupportContacts(updated)
                    saveSupportContacts(updated)
                    setShowAddContact(false)
                  }}
                  disabled={!newContact.name.trim() || !newContact.user_id.trim()}
                  style={{
                    padding: '6px 14px', borderRadius: 'var(--ui-radius, 12px)', border: 'none',
                    background: '#111827', color: '#fff', fontSize: 13, fontWeight: 600, cursor: 'pointer',
                    opacity: (!newContact.name.trim() || !newContact.user_id.trim()) ? 0.5 : 1,
                  }}
                >
                  Add
                </button>
                <button
                  onClick={() => setShowAddContact(false)}
                  style={{ padding: '6px 14px', borderRadius: 'var(--ui-radius, 12px)', border: '1px solid #d1d5db', background: '#fff', fontSize: 13, cursor: 'pointer' }}
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Compliance Activation */}
      <div style={sectionStyle}>
        <div style={sectionHeaderStyle}>
          <Lock size={18} color="#6b7280" /> Document Compliance Checks
        </div>
        <div style={{ padding: '0 20px 16px', display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div style={{ fontSize: 13, color: '#6b7280', lineHeight: 1.5 }}>
            When enabled, every uploaded document is scanned in chunks by an LLM
            against the policy below. Documents containing sensitive or policy-violating
            content are flagged in the document library.
          </div>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
            <input type="checkbox" checked={complianceEnabled} onChange={e => setComplianceEnabled(e.target.checked)} />
            <span style={{ fontSize: 14, fontWeight: 500 }}>Activate compliance checks</span>
          </label>
          {complianceEnabled && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12, padding: '8px 0' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={complianceCheckOnUpload}
                  onChange={e => setComplianceCheckOnUpload(e.target.checked)}
                />
                <span style={{ fontSize: 13 }}>Run checks automatically on every upload</span>
              </label>
              <div>
                <label style={labelStyle}>Compliance policy (sent to the validator LLM)</label>
                <textarea
                  value={complianceRules}
                  onChange={e => setComplianceRules(e.target.value)}
                  placeholder="Describe what content should be flagged…"
                  rows={6}
                  style={{ ...inputStyle, fontFamily: 'inherit', resize: 'vertical' }}
                />
                <div style={{ fontSize: 12, color: '#6b7280', marginTop: 4 }}>
                  Plain English. The validator decides whether each chunk passes or fails based on this rule set.
                </div>
              </div>
              <div style={{ display: 'flex', gap: 12 }}>
                <div style={{ flex: 1 }}>
                  <label style={labelStyle}>Chunk size (chars)</label>
                  <input
                    type="number"
                    min={500}
                    value={complianceChunkSize}
                    onChange={e => setComplianceChunkSize(Number(e.target.value) || 8000)}
                    style={inputStyle}
                  />
                </div>
                <div style={{ flex: 1 }}>
                  <label style={labelStyle}>Chunk overlap (chars)</label>
                  <input
                    type="number"
                    min={0}
                    value={complianceChunkOverlap}
                    onChange={e => setComplianceChunkOverlap(Number(e.target.value) || 0)}
                    style={inputStyle}
                  />
                </div>
              </div>
            </div>
          )}
          <div>
            <button
              onClick={async () => {
                setComplianceSaving(true)
                setComplianceSaved(false)
                try {
                  await updateCompliancePolicyConfig({
                    enabled: complianceEnabled,
                    check_on_upload: complianceCheckOnUpload,
                    rules: complianceRules,
                    chunk_size: complianceChunkSize,
                    chunk_overlap: complianceChunkOverlap,
                  })
                  setComplianceSaved(true)
                  setTimeout(() => setComplianceSaved(false), 3000)
                } catch {
                  setError('Failed to save compliance configuration')
                } finally {
                  setComplianceSaving(false)
                }
              }}
              disabled={complianceSaving}
              style={{
                padding: '8px 20px', borderRadius: 'var(--ui-radius, 12px)', border: 'none',
                background: '#111827', color: '#fff', fontSize: 13, fontWeight: 600, cursor: 'pointer',
                opacity: complianceSaving ? 0.6 : 1,
              }}
            >
              {complianceSaving ? 'Saving...' : 'Save Compliance Settings'}
            </button>
            {complianceSaved && <span role="status" aria-live="polite" style={{ marginLeft: 10, fontSize: 13, color: '#16a34a' }}>Saved!</span>}
          </div>
        </div>
      </div>

      {/* Retention Policy */}
      <div style={sectionStyle}>
        <div style={sectionHeaderStyle}>
          <ShieldCheck size={18} color="#6b7280" /> Document Retention Policy
        </div>
        <div style={{ padding: '0 20px 16px', display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div style={{ fontSize: 13, color: '#6b7280', lineHeight: 1.5 }}>
            When enforcement is on, documents are auto-scheduled for soft-deletion after their
            classification-specific retention window. Soft-deleted documents become unrecoverable
            after the grace period expires. Items on retention hold are never auto-deleted.
          </div>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={retentionEnabled}
              onChange={e => setRetentionEnabled(e.target.checked)}
              style={checkStyle}
            />
            <span style={{ fontSize: 14, fontWeight: 500 }}>Activate retention enforcement</span>
          </label>
          {retentionEnabled && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16, padding: '8px 0' }}>
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 8 }}>
                  Per-classification rules
                </div>
                <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ backgroundColor: '#f9fafb', color: '#6b7280', textAlign: 'left' }}>
                      <th style={{ padding: '8px 12px', fontWeight: 500 }}>Tier</th>
                      <th style={{ padding: '8px 12px', fontWeight: 500 }}>Retention (days)</th>
                      <th style={{ padding: '8px 12px', fontWeight: 500 }}>Grace before purge (days)</th>
                      <th style={{ padding: '8px 12px', fontWeight: 500 }}>Warn before (days)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[
                      { name: 'unrestricted', label: 'Unrestricted', color: '#22c55e' },
                      { name: 'internal', label: 'Internal', color: '#3b82f6' },
                      { name: 'ferpa', label: 'FERPA', color: '#f59e0b' },
                      { name: 'cui', label: 'CUI', color: '#f97316' },
                      { name: 'itar', label: 'ITAR', color: '#ef4444' },
                    ].map(level => {
                      const p = retentionPolicies[level.name] || { retention_days: 0, soft_delete_grace_days: 0 }
                      const update = (patch: Partial<RetentionPolicyForm>) => {
                        setRetentionPolicies(prev => ({
                          ...prev,
                          [level.name]: { ...p, ...patch },
                        }))
                      }
                      return (
                        <tr key={level.name} style={{ borderTop: '1px solid #f3f4f6' }}>
                          <td style={{ padding: '8px 12px' }}>
                            <span style={{
                              display: 'inline-flex', alignItems: 'center', gap: 6,
                              padding: '2px 10px', borderRadius: 9999,
                              fontSize: 12, fontWeight: 600,
                              backgroundColor: `${level.color}1a`, color: level.color,
                              border: `1px solid ${level.color}66`,
                            }}>
                              <span style={{ width: 6, height: 6, borderRadius: 9999, backgroundColor: level.color }} />
                              {level.label}
                            </span>
                          </td>
                          <td style={{ padding: '8px 12px' }}>
                            <input
                              type="number"
                              min={0}
                              value={p.retention_days || 0}
                              onChange={e => update({ retention_days: Number(e.target.value) || 0 })}
                              style={{ ...inputStyle, padding: '6px 10px', width: 120 }}
                            />
                          </td>
                          <td style={{ padding: '8px 12px' }}>
                            <input
                              type="number"
                              min={0}
                              value={p.soft_delete_grace_days || 0}
                              onChange={e => update({ soft_delete_grace_days: Number(e.target.value) || 0 })}
                              style={{ ...inputStyle, padding: '6px 10px', width: 120 }}
                            />
                          </td>
                          <td style={{ padding: '8px 12px' }}>
                            <input
                              type="number"
                              min={0}
                              value={p.warning_days_before ?? ''}
                              placeholder="—"
                              aria-label="Retention period (days)"
                              onChange={e => {
                                const v = e.target.value
                                update({ warning_days_before: v === '' ? undefined : Number(v) || 0 })
                              }}
                              style={{ ...inputStyle, padding: '6px 10px', width: 120 }}
                            />
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>

              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 8 }}>
                  Other retention windows
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}>
                  <div>
                    <label style={labelStyle}>Activity logs (days)</label>
                    <input
                      type="number"
                      min={0}
                      value={activityRetentionDays}
                      onChange={e => setActivityRetentionDays(Number(e.target.value) || 0)}
                      style={inputStyle}
                    />
                  </div>
                  <div>
                    <label style={labelStyle}>Chat conversations (days)</label>
                    <input
                      type="number"
                      min={0}
                      value={chatRetentionDays}
                      onChange={e => setChatRetentionDays(Number(e.target.value) || 0)}
                      style={inputStyle}
                    />
                  </div>
                  <div>
                    <label style={labelStyle}>Workflow results (days)</label>
                    <input
                      type="number"
                      min={0}
                      value={workflowResultRetentionDays}
                      onChange={e => setWorkflowResultRetentionDays(Number(e.target.value) || 0)}
                      style={inputStyle}
                    />
                  </div>
                  <div>
                    <label style={labelStyle}>Stale activity threshold (min)</label>
                    <input
                      type="number"
                      min={0}
                      value={staleActivityMinutes}
                      onChange={e => setStaleActivityMinutes(Number(e.target.value) || 0)}
                      style={inputStyle}
                    />
                  </div>
                </div>
              </div>
            </div>
          )}
          <div>
            <button
              onClick={async () => {
                setRetentionSaving(true)
                setRetentionSaved(false)
                try {
                  await updateSystemConfig({
                    retention_config: {
                      enabled: retentionEnabled,
                      policies: retentionPolicies,
                      activity_retention_days: activityRetentionDays,
                      chat_retention_days: chatRetentionDays,
                      workflow_result_retention_days: workflowResultRetentionDays,
                      activity_stale_threshold_minutes: staleActivityMinutes,
                    },
                  })
                  setRetentionSaved(true)
                  setTimeout(() => setRetentionSaved(false), 3000)
                } catch {
                  setError('Failed to save retention configuration')
                } finally {
                  setRetentionSaving(false)
                }
              }}
              disabled={retentionSaving}
              style={{
                padding: '8px 20px', borderRadius: 'var(--ui-radius, 12px)', border: 'none',
                background: '#111827', color: '#fff', fontSize: 13, fontWeight: 600, cursor: 'pointer',
                opacity: retentionSaving ? 0.6 : 1,
              }}
            >
              {retentionSaving ? 'Saving...' : 'Save Retention Settings'}
            </button>
            {retentionSaved && <span role="status" aria-live="polite" style={{ marginLeft: 10, fontSize: 13, color: '#16a34a' }}>Saved!</span>}
          </div>
        </div>
      </div>

      {/* Save config button */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <button
          onClick={handleSaveConfig}
          disabled={saving}
          style={{
            padding: '10px 24px', borderRadius: 'var(--ui-radius, 12px)', border: 'none',
            backgroundColor: '#111827', color: '#fff', fontSize: 14, fontWeight: 600, cursor: 'pointer',
            opacity: saving ? 0.6 : 1,
          }}
        >
          {saving ? 'Saving...' : 'Save Configuration'}
        </button>
        {saved && <span role="status" aria-live="polite" style={{ fontSize: 13, color: '#16a34a' }}>Configuration saved!</span>}
      </div>
    </div>
  )
}
