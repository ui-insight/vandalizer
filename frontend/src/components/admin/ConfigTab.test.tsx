import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { ConfigTab } from './ConfigTab'
import type { SystemConfigData } from '../../api/admin'

// ---------------------------------------------------------------------------
// Characterization tests for ConfigTab (plan 013, Step 1).
//
// These pin down what the component does *today*, before the Available
// Models / Authentication / UI Theme panels are extracted into
// `components/admin/config/`. They are the safety net for that move: each
// one covers behavior an earlier plan established and a careless extraction
// would silently break.
//
//   1. every panel heading renders                — "nothing vanished" guard
//   2. the load-failure guard (plan 003)          — no form, no Save, on a failed GET
//   3. the "***" API-key sentinel (plans 003/011) — Save never sends an empty key
//   4. the auth-methods floor (plan 003)          — last method's checkbox is disabled
//   5. models are addressed by id (plan 011)      — delete sends the model's id
//   6. theme save hits the theme endpoint         — not the general config endpoint
//
// Assertions are on user-visible text and on request payloads, never on
// component internals, so they survive the panels moving into their own files.
// ---------------------------------------------------------------------------

const mockGetSystemConfig = vi.fn()
const mockUpdateSystemConfig = vi.fn()
const mockUpdateCompliancePolicyConfig = vi.fn()
const mockAddModel = vi.fn()
const mockUpdateModel = vi.fn()
const mockDeleteModel = vi.fn()
const mockSetDefaultModel = vi.fn()
const mockTestOcr = vi.fn()
const mockTestModel = vi.fn()
const mockTestPrompt = vi.fn()
const mockProbeModel = vi.fn()
const mockGetReadiness = vi.fn()
const mockAddOAuthProvider = vi.fn()
const mockUpdateOAuthProvider = vi.fn()
const mockDeleteOAuthProvider = vi.fn()
const mockUpdateAuthMethods = vi.fn()
const mockParseSamlMetadata = vi.fn()

vi.mock('../../api/admin', () => ({
  getSystemConfig: (...a: unknown[]) => mockGetSystemConfig(...a),
  updateSystemConfig: (...a: unknown[]) => mockUpdateSystemConfig(...a),
  updateCompliancePolicyConfig: (...a: unknown[]) => mockUpdateCompliancePolicyConfig(...a),
  addModel: (...a: unknown[]) => mockAddModel(...a),
  updateModel: (...a: unknown[]) => mockUpdateModel(...a),
  deleteModel: (...a: unknown[]) => mockDeleteModel(...a),
  setDefaultModel: (...a: unknown[]) => mockSetDefaultModel(...a),
  testOcr: (...a: unknown[]) => mockTestOcr(...a),
  testModel: (...a: unknown[]) => mockTestModel(...a),
  testPrompt: (...a: unknown[]) => mockTestPrompt(...a),
  probeModel: (...a: unknown[]) => mockProbeModel(...a),
  getReadiness: (...a: unknown[]) => mockGetReadiness(...a),
  addOAuthProvider: (...a: unknown[]) => mockAddOAuthProvider(...a),
  updateOAuthProvider: (...a: unknown[]) => mockUpdateOAuthProvider(...a),
  deleteOAuthProvider: (...a: unknown[]) => mockDeleteOAuthProvider(...a),
  updateAuthMethods: (...a: unknown[]) => mockUpdateAuthMethods(...a),
  parseSamlMetadata: (...a: unknown[]) => mockParseSamlMetadata(...a),
}))

const mockGetThemeConfig = vi.fn()
const mockUpdateThemeConfig = vi.fn()

vi.mock('../../api/config', () => ({
  getThemeConfig: (...a: unknown[]) => mockGetThemeConfig(...a),
  updateThemeConfig: (...a: unknown[]) => mockUpdateThemeConfig(...a),
}))

const mockConfirm = vi.fn()

vi.mock('../shared/useConfirm', () => ({
  useConfirm: () => mockConfirm,
}))

const mockBrandingRefresh = vi.fn()

vi.mock('../../contexts/BrandingContext', () => ({
  useBranding: () => ({ refresh: mockBrandingRefresh }),
  DEFAULT_ORG_NAME: 'Vandalizer',
  DEFAULT_ICON_URL: '/images/joevandal.png',
}))

// ---------------------------------------------------------------------------
// Fixture
// ---------------------------------------------------------------------------

const THEME = {
  highlight_color: '#eab308',
  highlight_text_color: '#000000',
  highlight_complement: '#1e40af',
  ui_radius: '12px',
  org_name: '',
  logo_data_url: '',
  icon_data_url: '',
  icon_hide_in_nav: false,
}

/** A full, realistic system config. `ocr_api_key` holds the backend's "***"
 *  sentinel, which is what a real successful load always returns. */
function makeConfig(overrides: Partial<SystemConfigData> = {}): SystemConfigData {
  return {
    extraction_config: {
      mode: 'one_pass',
      one_pass: { thinking: true, structured_output: true, model: 'gpt-4o' },
      chunking: { enabled: false, max_keys_per_chunk: 10 },
      repetition: { enabled: false },
      use_images: false,
    },
    quality_config: {
      verification_gates: {
        require_validation: false,
        min_extraction_accuracy: 0.7,
        min_extraction_consistency: 0.8,
        min_workflow_grade: 'C',
      },
      quality_tiers: { excellent: { min_score: 90 }, good: { min_score: 70 }, fair: { min_score: 50 } },
    },
    auth_methods: ['password', 'oauth'],
    oauth_providers: [
      { id: 'prov-1', provider: 'azure', display_name: 'Campus Azure', client_id: 'client-abc', redirect_uri: '', tenant_id: 'tenant-1' },
    ],
    available_models: [
      { id: 'model-alpha', name: 'gpt-4o', tag: 'openai', external: true, thinking: false, api_protocol: 'openai', endpoint: 'https://api.openai.com/v1', api_key: '***', context_window: 128000 },
      { id: 'model-beta', name: 'llama3.1', tag: 'ollama', external: false, thinking: false, api_protocol: 'ollama', endpoint: 'http://localhost:11434/v1', context_window: 32768 },
    ],
    default_model: 'gpt-4o',
    ocr_endpoint: 'https://ocr.example.edu',
    ocr_api_key: '***',
    llm_endpoint: '',
    highlight_color: '#eab308',
    ui_radius: '12px',
    default_team_id: '',
    compliance_config: { enabled: false, check_on_upload: true, rules: '', chunk_size: 8000, chunk_overlap: 200 },
    retention_config: { enabled: false, policies: {} },
    ...overrides,
  }
}

/** Render and wait until the loaded form (not the spinner) is on screen. */
async function renderConfigTab() {
  const utils = render(<ConfigTab />)
  await screen.findByText('Available Models')
  return utils
}

/** Queries scoped to the Available Models panel. Model names also appear in
 *  the Prompt Playground's model picker, so panel-scoped queries are needed to
 *  talk about the model *list*. `cfg-models` is the setup-checklist jump
 *  target, so the id is part of the panel's contract. */
function modelsPanel() {
  const el = document.getElementById('cfg-models')
  if (!el) throw new Error('Available Models panel (#cfg-models) not found')
  return within(el)
}

beforeEach(() => {
  mockGetSystemConfig.mockReset().mockResolvedValue(makeConfig())
  mockUpdateSystemConfig.mockReset().mockResolvedValue({ status: 'ok' })
  mockUpdateCompliancePolicyConfig.mockReset().mockResolvedValue({ enabled: false, check_on_upload: true, rules: '' })
  mockAddModel.mockReset().mockResolvedValue({ status: 'ok', models: [] })
  mockUpdateModel.mockReset().mockResolvedValue({ status: 'ok', models: [] })
  mockDeleteModel.mockReset().mockResolvedValue({ status: 'ok' })
  mockSetDefaultModel.mockReset().mockResolvedValue({ status: 'ok', default_model: '' })
  mockTestOcr.mockReset().mockResolvedValue({ status: 'ok', status_code: 200, message: 'OK' })
  mockTestModel.mockReset().mockResolvedValue({ ok: true, checks: [], summary: 'Connected' })
  mockTestPrompt.mockReset()
  mockProbeModel.mockReset()
  mockGetReadiness.mockReset().mockResolvedValue({ ready: true, blockers_remaining: 0, items: [] })
  mockAddOAuthProvider.mockReset().mockResolvedValue({ status: 'ok' })
  mockUpdateOAuthProvider.mockReset().mockResolvedValue({ status: 'ok' })
  mockDeleteOAuthProvider.mockReset().mockResolvedValue({ status: 'ok' })
  mockUpdateAuthMethods.mockReset().mockResolvedValue({ status: 'ok' })
  mockParseSamlMetadata.mockReset()
  mockGetThemeConfig.mockReset().mockResolvedValue({ ...THEME })
  mockUpdateThemeConfig.mockReset().mockResolvedValue({ ...THEME })
  mockConfirm.mockReset().mockResolvedValue(true)
  mockBrandingRefresh.mockReset().mockResolvedValue(undefined)
})

// ---------------------------------------------------------------------------
// 1. Every panel renders
// ---------------------------------------------------------------------------

describe('ConfigTab — panel inventory', () => {
  it('renders every configuration panel heading', async () => {
    await renderConfigTab()

    for (const heading of [
      'Available Models',
      'Prompt Playground',
      'Authentication',
      'Endpoints',
      'UI Theme & Branding',
      'Extraction Configuration',
      'Quality & Verification Gates',
      'Support Contacts',
      'Document Compliance Checks',
      'Document Retention Policy',
    ]) {
      expect(screen.getByText(heading)).toBeInTheDocument()
    }
  })

  it('renders each configured model and OAuth provider', async () => {
    await renderConfigTab()

    expect(modelsPanel().getByText('gpt-4o')).toBeInTheDocument()
    expect(modelsPanel().getByText('llama3.1')).toBeInTheDocument()
    expect(screen.getByText('Campus Azure')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// 2. Load-failure guard (plan 003)
// ---------------------------------------------------------------------------

describe('ConfigTab — load-failure guard (plan 003)', () => {
  it('renders an error instead of the form, with no reachable Save control', async () => {
    mockGetSystemConfig.mockRejectedValue(new Error('boom'))

    render(<ConfigTab />)
    await screen.findByText('Could not load configuration')

    expect(screen.queryByText('Available Models')).not.toBeInTheDocument()
    expect(screen.queryByText('Authentication')).not.toBeInTheDocument()
    expect(screen.queryByText('UI Theme & Branding')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Save Configuration/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Save Theme/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Update Methods/i })).not.toBeInTheDocument()
    // Retry is the only control offered.
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// 3. The "***" API-key sentinel (plans 003 / 011)
// ---------------------------------------------------------------------------

describe('ConfigTab — "***" API-key sentinel (plans 003 / 011)', () => {
  it('never sends an empty OCR key for an untouched field, and sends an edited one', async () => {
    await renderConfigTab()

    fireEvent.click(screen.getAllByRole('button', { name: /Save Configuration/i })[0])
    await waitFor(() => expect(mockUpdateSystemConfig).toHaveBeenCalledTimes(1))

    const untouched = mockUpdateSystemConfig.mock.calls[0][0] as Record<string, unknown>
    // The stored key must never be clobbered: not blanked...
    expect(untouched.ocr_api_key).not.toBe('')
    // ...and today it is omitted entirely, because the field was never edited.
    expect('ocr_api_key' in untouched).toBe(false)
    // The rest of the sticky-save payload still goes out.
    expect(untouched.ocr_endpoint).toBe('https://ocr.example.edu')

    // Once the admin actually types a key, it is sent verbatim.
    fireEvent.change(screen.getByPlaceholderText('Bearer token...'), { target: { value: 'new-ocr-secret' } })
    fireEvent.click(screen.getAllByRole('button', { name: /Save Configuration/i })[0])
    await waitFor(() => expect(mockUpdateSystemConfig).toHaveBeenCalledTimes(2))

    const edited = mockUpdateSystemConfig.mock.calls[1][0] as Record<string, unknown>
    expect(edited.ocr_api_key).toBe('new-ocr-secret')
  })

  it('prefills an edited OAuth provider secret with the sentinel and echoes it back', async () => {
    await renderConfigTab()

    fireEvent.click(screen.getByRole('button', { name: 'Edit provider' }))
    const secret = await screen.findByLabelText('Client Secret')
    // The real secret is never delivered to the browser — the form shows "***".
    expect(secret).toHaveValue('***')

    fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }))
    await waitFor(() => expect(mockUpdateOAuthProvider).toHaveBeenCalledTimes(1))

    const [providerId, payload] = mockUpdateOAuthProvider.mock.calls[0] as [string, Record<string, unknown>]
    expect(providerId).toBe('prov-1')
    // Echoing "***" is what tells the backend to keep the stored secret.
    expect(payload.client_secret).toBe('***')
  })
})

// ---------------------------------------------------------------------------
// 4. Auth-methods floor (plan 003)
// ---------------------------------------------------------------------------

describe('ConfigTab — auth-methods floor (plan 003)', () => {
  it('disables the last enabled method so it cannot be unchecked', async () => {
    mockGetSystemConfig.mockResolvedValue(makeConfig({ auth_methods: ['password'] }))
    await renderConfigTab()

    const password = screen.getByLabelText('password')
    const oauth = screen.getByLabelText('OAuth / SAML')
    expect(password).toBeChecked()
    expect(password).toBeDisabled()
    expect(oauth).not.toBeChecked()
    expect(oauth).not.toBeDisabled()
  })

  it('leaves both methods enabled when two are configured', async () => {
    await renderConfigTab()

    expect(screen.getByLabelText('password')).not.toBeDisabled()
    expect(screen.getByLabelText('OAuth / SAML')).not.toBeDisabled()
  })

  it('sends the selected methods to the auth-methods endpoint', async () => {
    await renderConfigTab()

    fireEvent.click(screen.getByRole('button', { name: 'Update Methods' }))
    await waitFor(() => expect(mockUpdateAuthMethods).toHaveBeenCalledWith(['password', 'oauth']))
  })
})

// ---------------------------------------------------------------------------
// 5. Models are addressed by stable id (plan 011)
// ---------------------------------------------------------------------------

describe('ConfigTab — models addressed by id (plan 011)', () => {
  it('deletes the clicked model by its id, not its list position', async () => {
    await renderConfigTab()

    fireEvent.click(screen.getAllByTitle('Delete model')[1])
    await waitFor(() => expect(mockDeleteModel).toHaveBeenCalledWith('model-beta'))
    expect(mockDeleteModel).toHaveBeenCalledTimes(1)
    await waitFor(() => expect(modelsPanel().queryByText('llama3.1')).not.toBeInTheDocument())
    expect(modelsPanel().getByText('gpt-4o')).toBeInTheDocument()
  })

  it('tests the clicked model by its id', async () => {
    await renderConfigTab()

    fireEvent.click(screen.getAllByTitle('Test model')[1])
    await waitFor(() => expect(mockTestModel).toHaveBeenCalledWith('model-beta'))
  })
})

// ---------------------------------------------------------------------------
// 6. Theme save
// ---------------------------------------------------------------------------

describe('ConfigTab — theme save', () => {
  it('saves the theme through the theme endpoint, not the config endpoint', async () => {
    await renderConfigTab()

    // Two bound inputs show the colour (a native picker and a hex field).
    const hexField = screen.getAllByDisplayValue('#eab308')[1]
    fireEvent.change(hexField, { target: { value: '#123456' } })

    fireEvent.click(screen.getByRole('button', { name: 'Save Theme' }))
    await waitFor(() => expect(mockUpdateThemeConfig).toHaveBeenCalledTimes(1))

    expect(mockUpdateThemeConfig).toHaveBeenCalledWith(expect.objectContaining({
      highlight_color: '#123456',
      ui_radius: '12px',
    }))
    expect(mockUpdateSystemConfig).not.toHaveBeenCalled()
    await waitFor(() => expect(mockBrandingRefresh).toHaveBeenCalled())
  })
})
